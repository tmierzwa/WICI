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


@dataclass
class Delivery:
    frames: tuple[bytes, ...]
    part: int = 0
    sequence: int | None = None
    next_hop: int | None = None
    submissions: int = 0
    attempts: int = 0
    sent_at: float = 0.0
    retry_at: float = 0.0
    result: bool | None = None


class WiciStos:
    """The DB thread owns nonce reservation; this thread owns the serial port.

    The root echoes an outbound frame only after accepting it into the radio
    scheduler. A matching next-hop HACK completes one fragment. A received DATA
    is HACKed only after the database thread confirms durable admission.
    """

    def __init__(self, port, network, root, ttl, ifac, address, received, log=None, clock=time.monotonic,
                 signing_key=None):
        from cryptography.hazmat.primitives.asymmetric import ed25519
        if signing_key is None or len(signing_key) != 64:
            raise ValueError("numbered receiver needs its signing identity")
        self.signer = ed25519.Ed25519PrivateKey.from_private_bytes(signing_key[32:])
        self.port_name, self.network, self.root, self.ttl = port, network, root, ttl
        self.key = wici_link.derive_key(ifac, network)
        self.address = bytes(address)
        if len(self.address) != 16:
            raise ValueError("invalid receiver address")
        self.received = received
        self.log = log or (lambda line: print(line, file=sys.stderr, flush=True))
        self.clock = clock
        self.requests = queue.Queue(maxsize=4)
        self.stream = wici_link.KissStream()
        self.port = None
        self.running = False
        self.thread = None
        self.active = None
        self.last_rx = None
        self.dropped = {"bad_link": 0, "admission": 0, "outbound": 0}

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True, name="wici-link")
        self.thread.start()

    def stop(self):
        self.running = False
        if self.port is not None:
            self.port.close()
        if self.thread is not None:
            self.thread.join(2)

    def announce(self):
        # Root beacons are scheduled by the radio node.
        return None

    def status(self, now):
        return {"online": self.port is not None,
                "since_rx": None if self.last_rx is None else max(0, now - self.last_rx),
                "dropped": dict(self.dropped)}

    def send_frames(self, frames):
        if not self.running or self.port is None or not 1 <= len(frames) <= 2:
            return None
        item = Delivery(tuple(bytes(frame) for frame in frames))
        try:
            self.requests.put_nowait(item)
        except queue.Full:
            return None
        return item

    @staticmethod
    def outcome(item):
        return item.result

    def _write(self, frame):
        self.port.write(wici_link.kiss_encode(wici_link.encode(self.key, frame)))

    def _submit(self, item, now):
        part = item.frames[item.part]
        sender = int.from_bytes(part[1:3], "big")
        frame = wici_link.Frame(wici_link.DATA, wici_link.ACKREQ | wici_link.DOWN,
                                self.network, sender, self.root, 0, self.ttl, 0, part,
                                self.signer.sign(wici_link.origin_message(self.network, part)))
        self._write(frame)
        item.submissions += 1
        item.sent_at = now
        # The root echoes only after radio TX. Airtime debt can hold a queued
        # frame for minutes, so missing echoes back off without a false HACK timeout.
        item.retry_at = now + min(30, 2 ** min(item.submissions, 5))

    def _receive(self, wire):
        try:
            frame = wici_link.decode(self.key, self.network, wire)
        except wici_link.LinkError:
            self.dropped["bad_link"] += 1
            return
        self.last_rx = time.time()
        item = self.active
        if (item is not None and frame.kind == wici_link.DATA and frame.source == self.root and
                frame.destination == wici_link.BROADCAST and frame.flags == wici_link.DOWN and
                frame.payload == item.frames[item.part]):
            # Emergency flood has no HACK. Report failure so Wysylka creates
            # a fresh envelope counter for the next SA1 attempt.
            item.result = False
            self.active = None
            return
        if (item is not None and frame.kind == wici_link.DATA and frame.source == self.root and
                frame.flags == (wici_link.ACKREQ | wici_link.DOWN) and
                frame.payload == item.frames[item.part] and item.sequence is None):
            item.sequence, item.next_hop = frame.sequence, frame.destination
            item.attempts += 1
            item.sent_at = self.clock()
            item.retry_at = item.sent_at + 0.6
            return
        if (item is not None and frame.kind == wici_link.HACK and frame.destination == self.root and
                frame.source == item.next_hop and frame.sequence == item.sequence):
            item.part += 1
            item.sequence = item.next_hop = None
            item.submissions = item.attempts = 0
            item.retry_at = 0
            if item.part == len(item.frames):
                item.result = True
                self.active = None
            return
        if frame.kind != wici_link.DATA or frame.destination != self.root:
            return
        try:
            self.received(frame.payload)
        except Exception as exc:  # noqa: BLE001 - no HACK after failed admission
            self.dropped["admission"] += 1
            self.log(f"stanowisko: odmowa koperty WICI: {exc!r}")
            return
        if frame.flags & wici_link.ACKREQ:
            reply = wici_link.Frame(wici_link.HACK, 0, self.network, self.root,
                                    frame.source, 0, 1, frame.sequence)
            self._write(reply)

    def _tick(self):
        now = self.clock()
        if self.active is None:
            try:
                self.active = self.requests.get_nowait()
            except queue.Empty:
                return
        item = self.active
        if item.sequence is not None:
            if now < item.retry_at:
                return
            if item.attempts >= 3:
                item.result = False
                self.active = None
                self.dropped["outbound"] += 1
            else:
                item.sequence = item.next_hop = None
                item.retry_at = now + 10 + random.uniform(0.5, 2)
            return
        if now < item.retry_at:
            return
        if item.submissions >= 30:
            item.result = False
            self.active = None
            self.dropped["outbound"] += 1
            return
        self._submit(item, now)

    def _run(self):
        while self.running:
            if self.port is None:
                try:
                    self.port = serialport.open_port(self.port_name)
                    self.stream = wici_link.KissStream()
                except OSError:
                    time.sleep(2)
                    continue
            try:
                for wire in self.stream.feed(self.port.read(0.05)):
                    self._receive(wire)
                self._tick()
            except OSError as exc:
                self.log(f"stanowisko: port WICI odłączony: {exc}")
                self.port.close()
                self.port = None
                if self.active is not None:
                    self.active.result = False
                    self.active = None
