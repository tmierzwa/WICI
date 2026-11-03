# SPDX-License-Identifier: MIT
"""Numbered WICI-Link bearer on the receiving station's KISS USB port."""

from dataclasses import dataclass
import queue
import random
import sys
import threading
import time

from .. import serialport
from . import wici_link
from .wysylka import FLOODED, FORWARDED

# The root sends a HACK only up to 200 - 87 - 20 = 93 ms after the end of radio reception
# (wici-link.md, „Cel i root”); USB and the serial read take part of that.
HACK_BUDGET_S = 0.08
FRESH = ("partial", "complete", "proof")   # outcomes of `received` that let the root learn a down route
# Repeat HACKs as on every node (wici-link.md, rule 4): a frame seen in the last hour, or a new frame with a known
# envelope, gets a HACK at most once per REPEAT_HACK_S, except the first repeat of a frame first answered as new
# (the sender's retry after a lost HACK). Without the limit a replayed recording cost the root 13 x 87 ms per HACK.
REPEAT_HACK_S = 5
SEEN_S = 3600


@dataclass
class Delivery:
    frames: tuple[bytes, ...]
    destination: int
    part: int = 0
    sequence: int | None = None
    next_hop: int | None = None
    echo: bytes = b""  # wici_link.mac_echo of the part on air: the HACK must repeat it
    on_air: bytes = b""  # the root's echo of the last attempt: a retry sends these bytes again
    submissions: int = 0
    attempts: int = 0
    sent_at: float = 0.0
    retry_at: float = 0.0
    relayed: bool = False   # a part's HACK came from a relay: only the station's proof closes the intent
    flooded: bool = False   # a part left as a flood (no HACK at all)
    last_own: bool = False  # the last part's HACK came from the station itself
    result: bool | str | None = None


class WiciStos:
    """The DB thread owns nonce reservation; this thread owns the serial port.

    The root has one downward slot: it echoes an outbound frame only after radio TX
    and returns a frame it cannot take now with KISS command 1. So at most one
    submission is outstanding at the root, until its echo, its refusal or its retry
    time; the next one is chosen round robin across destination stations, so an
    unreachable station does not hold back the others. Items already echoed wait for
    their next-hop HACK concurrently; a matching HACK completes one fragment. At most
    IN_FLIGHT items are unfinished, as before, so a busy link lets Bearers fall back.

    `received(payload, timeout)` admits a DATA addressed to the root; it returns only
    after the frame is settled (durable admission, durable set-aside of a frame that can
    never be admitted, or an unauthenticated frame counted) and raises otherwise,
    TimeoutError when `timeout` passed first. Only a return is answered with HACK; the
    returned outcome decides whether the root may learn a down route (FRESH).
    """

    IN_FLIGHT = 4
    FAULT_PAUSE_S = 1   # po nieoczekiwanym błędzie: bez pętli otwierania portu na pełnych obrotach
    READ_WAITING_S = 0.001   # odczyt krótszy niż to zastał bajty w buforze

    def __init__(self, port, network, root, ttl, ifac, address, received, log=None, clock=time.monotonic):
        self.port_name, self.network, self.root, self.ttl = port, network, root, ttl
        self.key = wici_link.derive_key(ifac, network)
        self.address = bytes(address)
        if len(self.address) != 16:
            raise ValueError("invalid receiver address")
        self.received = received
        self.log = log or (lambda line: print(line, file=sys.stderr, flush=True))
        self.clock = clock
        self.lock = threading.Lock()
        self.unfinished = 0   # items handed out by send_frames without a result; under lock
        self.requests = queue.Queue()
        self.stream = wici_link.KissStream()
        self.port = None
        self.running = False
        self.thread = None
        self.waiting = []        # items behind another one to the same station; this thread only
        self.flight = {}         # destination station -> its current item; this thread only
        self.outstanding = None  # item submitted to the root without echo or refusal yet
        self.turn = 0            # destination of the last submission
        self.last_rx = None
        self.dropped = {"bad_link": 0, "admission": 0, "late": 0, "outbound": 0, "refused": 0, "repeat": 0}
        self.seen = {}           # MAC of a frame answered with HACK -> [first seen, first repeat still owed]
        self.repeat_at = None    # last repeat HACK under the limit

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True, name="wici-link")
        self.thread.start()

    def stop(self):
        # Only the link thread closes its port (reads time out after 50 ms): no close racing a reopen.
        self.running = False
        if self.thread is not None:
            self.thread.join(2)

    def announce(self):
        # Root beacons are scheduled by the radio node.
        return None

    def status(self, now):
        # room: send_frames przyjmie teraz wiadomość (jedyny nadawca to wątek bazy, więc to nie wyścig).
        # Wysyłka sprawdza to przed zamknięciem koperty, bo zamknięcie zużywa licznik koperty.
        with self.lock:
            room = self.unfinished < self.IN_FLIGHT
        return {"online": self.port is not None, "room": room,
                "since_rx": None if self.last_rx is None else max(0, now - self.last_rx),
                "dropped": dict(self.dropped)}

    def send_frames(self, frames):
        if not self.running or self.port is None or not 1 <= len(frames) <= 2:
            return None
        frames = tuple(bytes(frame) for frame in frames)
        item = Delivery(frames, int.from_bytes(frames[0][3:5], "big"))
        with self.lock:
            if self.unfinished >= self.IN_FLIGHT:
                return None
            self.unfinished += 1
        self.requests.put(item)
        return item

    @staticmethod
    def outcome(item):
        return item.result

    def _write(self, frame, command=wici_link.KISS_DATA):
        self.port.write(wici_link.kiss_encode(wici_link.encode(self.key, frame), command))

    def _finish(self, item, result):
        item.result = result
        if self.flight.get(item.destination) is item:
            del self.flight[item.destination]
        else:
            self.waiting.remove(item)
        if self.outstanding is item:
            self.outstanding = None
        with self.lock:
            self.unfinished -= 1

    def _next_part(self, item):
        item.part += 1
        item.sequence = item.next_hop = None
        item.on_air = b""
        item.submissions = item.attempts = 0
        item.retry_at = 0
        if item.part == len(item.frames):
            # A relay holds an earlier part, but the station itself took the last one: the route moved to it, so
            # the next try goes there at once (as after a flood) instead of waiting out that relay's custody; the
            # station's proof closes the intent if the earlier part reaches it meanwhile.
            self._finish(item, FORWARDED if item.relayed and not item.last_own else
                         FLOODED if item.relayed or item.flooded else True)

    def _submit(self, item, now):
        if item.on_air:
            # A retry: the root sends its echo again unchanged to the same next hop (Root::transmit).
            self.port.write(wici_link.kiss_encode(item.on_air, wici_link.KISS_DATA))
        else:
            part = item.frames[item.part]
            sender = int.from_bytes(part[1:3], "big")
            self._write(wici_link.Frame(wici_link.DATA, wici_link.ACKREQ | wici_link.DOWN,
                                        self.network, sender, self.root, 0, self.ttl, 0, part))
        item.submissions += 1
        item.sent_at = now
        # The root echoes only after radio TX. Airtime debt can hold a queued
        # frame for minutes, so missing echoes back off without a false HACK timeout.
        item.retry_at = now + min(30, 2 ** min(item.submissions, 5))
        self.outstanding, self.turn = item, item.destination

    def _sent(self, payload):
        """The item in flight whose current fragment is this payload."""
        return next((item for item in self.flight.values() if item.frames[item.part] == payload), None)

    def _refused(self, wire):
        """The root cannot take the frame we wrote now (KISS command 1, the same bytes)."""
        try:
            frame = wici_link.decode(self.key, self.network, wire)
        except wici_link.LinkError:
            self.dropped["bad_link"] += 1
            return
        item = self.outstanding
        if item is None or frame.kind != wici_link.DATA or frame.payload != item.frames[item.part]:
            return
        # Not sent, and the slot is ours again. With one submission at a time the refusal is
        # the root's own state, so the item keeps its backoff and the 30-submission limit.
        self.outstanding = None
        self.dropped["refused"] += 1

    def _receive(self, wire, read_at=None):
        read_at = time.monotonic() if read_at is None else read_at
        try:
            frame = wici_link.decode(self.key, self.network, wire)
        except wici_link.LinkError:
            self.dropped["bad_link"] += 1
            return
        self.last_rx = time.time()
        if frame.kind == wici_link.DATA and frame.source == self.root and frame.flags & wici_link.DOWN:
            item = self._sent(frame.payload)
            if item is not None and frame.destination == wici_link.BROADCAST and frame.flags == wici_link.DOWN:
                # A flood has no HACK: the part is on air, and only the station's proof closes the intent.
                if self.outstanding is item:
                    self.outstanding = None
                item.flooded, item.last_own = True, False
                self._next_part(item)
                return
            if (item is not None and frame.flags == (wici_link.ACKREQ | wici_link.DOWN) and
                    item.sequence is None):
                item.sequence, item.next_hop = frame.sequence, frame.destination
                item.echo = wici_link.mac_echo(wire)
                item.on_air = bytes(wire)
                if self.outstanding is item:
                    self.outstanding = None
                item.attempts += 1
                item.sent_at = self.clock()
                item.retry_at = item.sent_at + 0.6
                return
        if frame.kind == wici_link.HACK and frame.destination == self.root:
            item = next((i for i in self.flight.values()
                         if i.next_hop == frame.source and i.sequence == frame.sequence and
                         i.echo == frame.payload), None)
            if item is not None:
                # Only the station's own HACK says it settled the part; a relay's says it holds it.
                item.last_own = frame.source == item.destination
                item.relayed = item.relayed or not item.last_own
                self._next_part(item)
                return
        if frame.kind != wici_link.DATA or frame.destination != self.root:
            return
        try:
            outcome = self.received(frame.payload, max(0.0, HACK_BUDGET_S - (time.monotonic() - read_at)))
        except TimeoutError:
            self.dropped["late"] += 1
            # The admission completes on the database thread: the station's retry is owed its HACK.
            self.seen.setdefault(bytes(wire[-wici_link.TAG:]), [self.clock(), True])
            self.log(f"stanowisko: koperta WICI od {frame.source} seq {frame.sequence} bez HACK: przyjęcie po "
                     f"{(time.monotonic() - read_at) * 1000:.0f} ms, za późno")
            return
        except Exception as exc:  # noqa: BLE001 - no HACK after failed admission
            self.dropped["admission"] += 1
            self.log(f"stanowisko: odmowa koperty WICI: {exc!r}")
            return
        if frame.flags & wici_link.ACKREQ:
            if not self._hack_allowed(wire, outcome):
                self.dropped["repeat"] += 1
                return
            reply = wici_link.Frame(wici_link.HACK, 0, self.network, self.root,
                                    frame.source, 0, 1, frame.sequence, wici_link.mac_echo(wire))
            # Only a fresh part authenticated by the envelope MAC proves that its sender is behind this
            # neighbour now; a duplicate, a set-aside or an unauthenticated frame may be replayed or forged.
            self._write(reply, wici_link.KISS_DATA if outcome in FRESH else wici_link.KISS_HACK_NO_LEARN)

    def _hack_allowed(self, wire, outcome):
        now = self.clock()
        while self.seen and now - next(iter(self.seen.values()))[0] > SEEN_S:
            del self.seen[next(iter(self.seen))]
        mac = bytes(wire[-wici_link.TAG:])
        seen = self.seen.get(mac)
        if seen is None:
            self.seen[mac] = [now, outcome != "duplicate"]
            if outcome != "duplicate":
                return True
        elif seen[1]:
            seen[1] = False
            return True
        if self.repeat_at is not None and now - self.repeat_at < REPEAT_HACK_S:
            return False
        self.repeat_at = now
        return True

    def _tick(self):
        now = self.clock()
        while True:
            try:
                self.waiting.append(self.requests.get_nowait())
            except queue.Empty:
                break
        for item in list(self.waiting):
            if item.destination not in self.flight:
                self.waiting.remove(item)
                self.flight[item.destination] = item
        for item in list(self.flight.values()):
            # Echoed items wait for their HACK side by side; without it, 3 attempts, then failure.
            if item.sequence is not None and now >= item.retry_at:
                if item.attempts >= 3:
                    self._finish(item, False)
                    self.dropped["outbound"] += 1
                else:
                    # As on every hop: the same bytes after 0.5-2 s, while the next hop still owes their HACK.
                    item.sequence = item.next_hop = None
                    item.retry_at = now + random.uniform(0.5, 2)
        if self.outstanding is not None and now < self.outstanding.retry_at:
            return   # the root's slot holds our frame until its echo or refusal
        self.outstanding = None
        if any(i.sequence is not None and now < i.retry_at for i in self.flight.values()):
            # The root keeps a sent downlink until its HACK or 600 ms (Root::transmit) and refuses the next
            # one meanwhile; submitting now would only spend a submission and grow the backoff.
            return
        # Round robin: the next destination after the last submitted one goes first.
        order = sorted(self.flight)
        for destination in [d for d in order if d > self.turn] + [d for d in order if d <= self.turn]:
            item = self.flight[destination]
            if item.sequence is not None or now < item.retry_at:
                continue
            if item.submissions >= 30:
                self._finish(item, False)
                self.dropped["outbound"] += 1
                continue
            self._submit(item, now)
            return

    def _disconnect(self):
        try:
            self.port.close()
        except OSError:
            pass
        self.port = None
        while True:
            try:
                self.waiting.append(self.requests.get_nowait())
            except queue.Empty:
                break
        for item in [*self.flight.values(), *self.waiting]:
            self._finish(item, False)

    def _run(self):
        drained_at = time.monotonic()   # koniec poprzedniego odczytu: wcześniej odczytane bajty już nie czekały
        while self.running:
            if self.port is None:
                try:
                    self.port = serialport.open_port(self.port_name)
                    self.stream = wici_link.KissStream()
                except OSError:
                    time.sleep(2)
                    continue
                drained_at = time.monotonic()
            try:
                started = time.monotonic()
                data = self.port.read(0.05)
                returned = time.monotonic()
                # Odczyt wraca, gdy tylko są bajty. Gdy wrócił od razu, bajty czekały w buforze (np. podczas
                # poprzedniego przyjęcia) od chwili nie wcześniejszej niż poprzedni odczyt: termin HACK liczy się
                # od niej, nie od odczytu. Gdy czekał, bajty przyszły w chwili powrotu.
                read_at = drained_at if returned - started < self.READ_WAITING_S else returned
                drained_at = returned
                for command, wire in self.stream.feed_commands(data):
                    if command == wici_link.KISS_REFUSED:
                        self._refused(wire)
                    else:
                        self._receive(wire, read_at)
                self._tick()
            except OSError as exc:
                self.log(f"stanowisko: port WICI odłączony: {exc}")
                self._disconnect()
            except Exception as exc:  # noqa: BLE001 - the link thread outlives any single fault
                self.log(f"stanowisko: błąd łącza WICI, port otwierany ponownie: {exc!r}")
                self._disconnect()
                time.sleep(self.FAULT_PAUSE_S)
        if self.port is not None:
            self._disconnect()
