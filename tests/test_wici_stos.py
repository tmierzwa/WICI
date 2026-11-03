# SPDX-License-Identifier: MIT
"""The numbered laptop bearer preserves hop admission and outbound ordering."""

import dataclasses
import threading
import time
import unittest
import unittest.mock

from software.laptop.wici.stanowisko import wici_link, wici_stos
from software.laptop.wici.stanowisko.wici_stos import WiciStos


class Port:
    def __init__(self, reads=()):
        self.writes = []
        self.reads = list(reads)
        self.closed = False

    def write(self, data):
        self.writes.append(data)

    def read(self, timeout):
        if self.reads:
            data = self.reads.pop(0)
            if isinstance(data, Exception):
                raise data
            return data
        time.sleep(timeout)
        return b""

    def close(self):
        self.closed = True


class Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


def unpack(data):
    frames = wici_link.KissStream().feed(data)
    assert len(frames) == 1
    return frames[0]


class WiciBearerTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.port = Port()
        self.accepted = []
        self.limits = []
        self.logs = []
        self.bearer = WiciStos("fake", 100, 5, 3, bytes(range(16)), bytes(16),
                               self.admit, log=self.logs.append, clock=self.clock)
        self.bearer.port = self.port
        self.bearer.running = True
        self.key = wici_link.derive_key(bytes(range(16)), 100)
        self.echoes = {}  # seq -> mac_echo of the DATA fed with it

    def admit(self, payload, timeout):
        self.limits.append(timeout)
        self.accepted.append(payload)
        return "complete"

    def feed(self, frame):
        wire = wici_link.encode(self.key, frame)
        if frame.kind == wici_link.DATA:
            self.echoes[frame.sequence] = wici_link.mac_echo(wire)
        self.bearer._receive(wire)

    def hack(self, source, sequence, destination=5):
        """A HACK for the DATA fed with this seq: it repeats the start of that frame's MAC."""
        return wici_link.Frame(wici_link.HACK, 0, 100, source, destination, 0, 1, sequence, self.echoes[sequence])

    def refuse(self, data):
        """The root returns the bytes it could not transmit with KISS command 1."""
        refused = bytearray(data)
        refused[1] = wici_link.KISS_REFUSED
        for command, wire in wici_link.KissStream().feed_commands(bytes(refused)):
            self.assertEqual(command, wici_link.KISS_REFUSED)
            self.bearer._refused(wire)

    def sent(self):
        return wici_link.decode(self.key, 100, unpack(self.port.writes[-1]))

    @staticmethod
    def part(recipient, fill=0):
        return bytes([0x40, 0, 1]) + recipient.to_bytes(2, "big") + bytes([fill] * 20)

    def test_inbound_hack_follows_durable_callback(self):
        data = wici_link.Frame(wici_link.DATA, wici_link.ACKREQ, 100, 4, 5, 0, 7, 41, bytes(25))
        self.feed(data)
        self.assertEqual(self.accepted, [bytes(25)])
        reply = wici_link.decode(self.key, 100, unpack(self.port.writes[-1]))
        self.assertEqual((reply.kind, reply.source, reply.destination, reply.sequence, reply.payload),
                         (wici_link.HACK, 5, 4, 41, self.echoes[41]))
        # The admission gets what is left of the HACK budget after the serial read.
        self.assertTrue(0 < self.limits[0] <= wici_stos.HACK_BUDGET_S)
        writes = len(self.port.writes)
        self.bearer.received = lambda *_: (_ for _ in ()).throw(OSError("snapshot failed"))
        self.feed(data)
        self.assertEqual(len(self.port.writes), writes)
        self.assertEqual(self.bearer.dropped["admission"], 1)

    def test_only_a_fresh_admission_lets_the_root_learn_a_route(self):
        for outcome, command in (("complete", wici_link.KISS_DATA), ("partial", wici_link.KISS_DATA),
                                 ("proof", wici_link.KISS_DATA),   # fresh, authenticated by the envelope MAC
                                 ("duplicate", wici_link.KISS_HACK_NO_LEARN),
                                 ("rejected", wici_link.KISS_HACK_NO_LEARN),
                                 ("unauthenticated", wici_link.KISS_HACK_NO_LEARN)):
            with self.subTest(outcome):
                self.bearer.received = lambda *_: outcome
                self.clock.value += wici_stos.REPEAT_HACK_S   # each a first receipt, the repeat allowance free
                self.feed(wici_link.Frame(wici_link.DATA, wici_link.ACKREQ, 100, 4, 5, 0, 7, 45,
                                          bytes([len(self.port.writes)] * 25)))
                written = self.port.writes[-1]
                self.assertEqual(written[1], command)   # KISS command byte after FEND
                reply = wici_link.decode(self.key, 100, unpack(written[:1] + bytes(1) + written[2:]))
                self.assertEqual((reply.kind, reply.destination, reply.sequence), (wici_link.HACK, 4, 45))

    def test_repeat_hacks_are_limited_except_the_owed_first_retry(self):
        # L4/E8: a keyless replay of a recorded frame cost the root 13 x 87 ms per HACK without any limit.
        data = wici_link.Frame(wici_link.DATA, wici_link.ACKREQ, 100, 4, 5, 0, 7, 45, bytes(25))
        hacks = lambda: len(self.port.writes)
        self.feed(data)
        self.assertEqual(hacks(), 1)
        self.bearer.received = lambda *_: "duplicate"
        self.feed(data)                      # the sender's first retry (its HACK was lost): owed
        self.feed(data)                      # a replay: the repeat allowance
        self.feed(data)                      # a replay within 5 s: no HACK
        self.assertEqual((hacks(), self.bearer.dropped["repeat"]), (3, 1))
        # A copy of the same envelope in another frame (another route or seq) is a repeat too.
        self.feed(dataclasses.replace(data, source=6, sequence=46))
        self.assertEqual((hacks(), self.bearer.dropped["repeat"]), (3, 2))
        self.clock.value += wici_stos.REPEAT_HACK_S
        self.feed(data)
        self.assertEqual(hacks(), 4)
        # After an hour the frame is forgotten; its envelope still makes it a limited repeat.
        self.clock.value += wici_stos.SEEN_S + 1
        self.feed(data)
        self.feed(data)
        self.assertEqual((hacks(), self.bearer.dropped["repeat"]), (5, 3))

    def test_late_admission_gets_no_hack(self):
        # Past the deadline the admission still completes on the database thread; the
        # station's retry is then a duplicate and gets its HACK at once.
        self.bearer.received = lambda *_: (_ for _ in ()).throw(TimeoutError("late"))
        late = wici_link.Frame(wici_link.DATA, wici_link.ACKREQ, 100, 4, 5, 0, 7, 43, bytes(25))
        self.feed(late)
        self.assertEqual(self.port.writes, [])
        self.assertEqual(self.bearer.dropped["late"], 1)
        self.assertEqual(self.bearer.dropped["admission"], 0)
        # The retry is owed its HACK, also when a replay has just used the repeat allowance.
        self.bearer.received = lambda *_: "duplicate"
        self.feed(dataclasses.replace(late, sequence=42, payload=bytes([1] * 25)))
        self.feed(late)
        self.assertEqual((len(self.port.writes), self.bearer.dropped["repeat"]), (2, 0))
        self.feed(late)
        self.assertEqual((len(self.port.writes), self.bearer.dropped["repeat"]), (2, 1))
        # A frame read long ago is still admitted, with no time left for a HACK decision.
        self.bearer.received = self.admit
        self.bearer._receive(wici_link.encode(self.key, wici_link.Frame(
            wici_link.DATA, wici_link.ACKREQ, 100, 4, 5, 0, 7, 44, bytes(25))), time.monotonic() - 1)
        self.assertEqual(self.limits, [0])

    def test_buffered_frame_budget_counts_from_the_previous_read(self):
        # The second frame waits in the USB buffer while the first is admitted; its read returns at once,
        # so its HACK budget must not start afresh at that read.
        frames = [wici_link.kiss_encode(wici_link.encode(self.key, wici_link.Frame(
            wici_link.DATA, wici_link.ACKREQ, 100, 4, 5, 0, 7, seq, bytes(25)))) for seq in (51, 52)]
        self.port.reads = list(frames)
        done = threading.Event()

        def slow(payload, timeout):
            self.limits.append(timeout)
            if len(self.limits) == 1:
                time.sleep(0.06)
            else:
                done.set()
        self.bearer.received = slow
        thread = threading.Thread(target=self.bearer._run, daemon=True)
        thread.start()
        self.assertTrue(done.wait(5))
        self.bearer.running = False
        thread.join(2)
        self.assertLessEqual(self.limits[1], wici_stos.HACK_BUDGET_S - 0.06)

    def test_two_parts_require_two_distinct_hacks(self):
        first, second = bytes([0x40, 0, 1, 0, 4]) + bytes(20), bytes([0x40, 0, 1, 0, 4]) + bytes([1] * 20)
        item = self.bearer.send_frames((first, second))
        self.assertIsNotNone(item)
        self.bearer._tick()
        virtual = wici_link.decode(self.key, 100, unpack(self.port.writes[-1]))
        self.assertEqual((virtual.source, virtual.destination, virtual.flags, virtual.ttl),
                         (1, 5, wici_link.ACKREQ | wici_link.DOWN, 3))
        # v3: the envelope is the whole DATA payload, no origin signature follows it.
        self.assertEqual(virtual.payload, first)
        self.assertEqual(len(unpack(self.port.writes[-1])), wici_link.HEADER + len(first) + wici_link.TAG)
        echo = wici_link.Frame(wici_link.DATA, virtual.flags, 100, 5, 4, 1, 7, 91, first)
        self.feed(echo)
        wrong = self.hack(3, 91)
        self.feed(wrong)
        self.assertIsNone(item.result)
        self.feed(self.hack(4, 91))
        self.assertIsNone(item.result)
        self.bearer._tick()
        virtual2 = wici_link.decode(self.key, 100, unpack(self.port.writes[-1]))
        self.assertEqual(virtual2.payload, second)
        self.feed(wici_link.Frame(wici_link.DATA, virtual.flags, 100, 5, 4, 1, 7, 92, second))
        self.feed(self.hack(4, 91))
        self.assertIsNone(item.result)
        # A recorded HACK for an older frame with seq 92 (after the 16-bit seq wrapped) has another echo.
        stale = self.hack(4, 92)
        self.feed(dataclasses.replace(stale, payload=bytes([stale.payload[0], stale.payload[1] ^ 1])))
        self.assertIsNone(item.result)
        self.feed(self.hack(4, 92))
        self.assertTrue(item.result)

    def test_typical_request_fits_one_frame(self):
        from software.laptop.wici import envelope
        # A typical REQUEST is 174 B of SA1; its 199 B envelope fits the 228 B DATA limit.
        parts = envelope.seal(bytes(32), 1, 4, 7, bytes(174), wici_link.MAX_PAYLOAD)
        self.assertEqual([len(p) for p in parts], [199])
        self.assertEqual([len(p) for p in envelope.seal(bytes(32), 1, 4, 8, bytes(222), wici_link.MAX_PAYLOAD)],
                         [136, 136])  # the largest REQUEST (247 B envelope) still takes two
        item = self.bearer.send_frames(parts)
        self.bearer._tick()
        wire = unpack(self.port.writes[-1])
        self.assertEqual(len(wire) + 8, 226)  # on air with the hop tag the root adds
        self.assertEqual(wici_link.decode(self.key, 100, wire).payload, parts[0])
        self.assertIsNone(item.result)

    def test_no_root_echo_causes_retry_without_claiming_delivery(self):
        part = bytes([0x40, 0, 1, 0, 4]) + bytes(20)
        item = self.bearer.send_frames((part,))
        self.bearer._tick()
        self.assertEqual(item.submissions, 1)
        self.clock.value = 102.1
        self.bearer._tick()
        self.assertEqual(item.submissions, 2)
        self.assertIsNone(item.result)

    def test_unacknowledged_exception_is_admitted_without_hack(self):
        data = wici_link.Frame(wici_link.DATA, 0, 100, 4, 5, 0, 7, 42, bytes(25))
        self.feed(data)
        self.assertEqual(self.accepted, [bytes(25)])
        self.assertEqual(self.port.writes, [])

    def test_emergency_flood_echo_does_not_claim_delivery(self):
        part = bytes([0x40, 0, 1, 0, 4]) + bytes(20)
        item = self.bearer.send_frames((part,))
        self.bearer._tick()
        self.feed(wici_link.Frame(wici_link.DATA, wici_link.DOWN, 100, 5,
                                  wici_link.BROADCAST, 1, 7, 92, part))
        # On air without any HACK: the intent stays open for the station's proof (E1).
        self.assertEqual(item.result, wici_stos.FLOODED)
        self.assertEqual(self.bearer.flight, {})
        self.assertIsNone(self.bearer.outstanding)

    def test_flood_of_one_part_goes_on_with_the_next(self):
        first, second = bytes([0x40, 0, 1, 0, 4]) + bytes(20), bytes([0x40, 0, 1, 0, 4]) + bytes([1] * 20)
        item = self.bearer.send_frames((first, second))
        self.bearer._tick()
        self.feed(wici_link.Frame(wici_link.DATA, wici_link.DOWN, 100, 5, wici_link.BROADCAST, 1, 7, 92, first))
        self.assertIsNone(item.result)
        self.bearer._tick()
        self.assertEqual(self.sent().payload, second)
        self.feed(wici_link.Frame(wici_link.DATA, wici_link.ACKREQ | wici_link.DOWN, 100, 5, 4, 1, 7, 93, second))
        self.feed(self.hack(4, 93))
        self.assertEqual(item.result, wici_stos.FLOODED)

    def test_only_the_stations_own_hack_proves_delivery(self):
        # E1: a relay's HACK means it holds the part (custody), not that the station settled it.
        first, second = bytes([0x40, 0, 1, 0, 4]) + bytes(20), bytes([0x40, 0, 1, 0, 4]) + bytes([1] * 20)
        # A relay held part 1 and the station took part 2 itself: the route moved, so the next try comes on the
        # failure schedule (FLOODED), not after the relay's custody; the station proves the message if part 1
        # still reaches it.
        for hops, expected in (((4, 4), True), ((3, 3), wici_stos.FORWARDED), ((3, 4), wici_stos.FLOODED),
                               ((4, 3), wici_stos.FORWARDED)):
            with self.subTest(hops):
                item = self.bearer.send_frames((first, second))
                for index, (hop, part) in enumerate(zip(hops, (first, second))):
                    self.bearer._tick()
                    self.assertEqual(self.sent().payload, part)
                    self.feed(wici_link.Frame(wici_link.DATA, wici_link.ACKREQ | wici_link.DOWN, 100, 5, hop, 1, 7,
                                              80 + index, part))
                    self.feed(self.hack(hop, 80 + index))
                self.assertEqual(item.result, expected)

    def destinations(self):
        return [wici_link.decode(self.key, 100, unpack(w)).payload[4] for w in self.port.writes]

    def echo(self, station, sequence, payload):
        self.feed(wici_link.Frame(wici_link.DATA, wici_link.ACKREQ | wici_link.DOWN, 100, 5, station, 1, 7,
                                  sequence, payload))

    def test_root_slot_holds_one_submission_until_echo_or_refusal(self):
        first = self.bearer.send_frames((self.part(4),))
        second = self.bearer.send_frames((self.part(9),))
        self.bearer._tick()
        self.bearer._tick()
        self.assertEqual(self.destinations(), [4])   # the root has one downward slot
        self.echo(4, 70, self.part(4))
        self.bearer._tick()
        # Echoed: the root keeps 4 until its HACK or 600 ms and would refuse 9 meanwhile (Root::transmit).
        self.assertEqual(self.destinations(), [4])
        self.clock.value += 0.7   # no HACK in time: 4 waits for its retry, 9 goes out
        self.bearer._tick()
        self.assertEqual(self.destinations(), [4, 9])
        self.echo(9, 71, self.part(9))
        self.feed(self.hack(9, 71))
        self.clock.value += 13   # 4's retry after its HACK timeout is due
        self.bearer._tick()
        self.assertEqual(self.destinations(), [4, 9, 4])
        self.echo(4, 72, self.part(4))
        self.feed(self.hack(4, 72))
        self.assertTrue(first.result)
        self.assertTrue(second.result)

    def test_undeliverable_station_does_not_hold_back_others(self):
        stuck = self.bearer.send_frames((self.part(4),))
        other = self.bearer.send_frames((self.part(9),))
        self.bearer._tick()
        self.clock.value += 2.1   # no echo and no refusal by its retry time: the slot is free again
        self.bearer._tick()
        self.assertEqual(self.destinations(), [4, 9])
        self.echo(9, 70, self.part(9))
        self.feed(self.hack(9, 70))
        self.assertTrue(other.result)
        self.assertIsNone(stuck.result)
        for _ in range(29):   # station 4 never echoes: 30 submissions with backoff, then failure
            self.clock.value += 31
            self.bearer._tick()
        self.assertEqual(stuck.submissions, 30)
        self.clock.value += 31
        self.bearer._tick()
        self.assertFalse(stuck.result)
        self.assertEqual(self.bearer.dropped["outbound"], 1)

    def test_same_station_keeps_one_item_in_flight(self):
        first = self.bearer.send_frames((self.part(4, 1),))
        second = self.bearer.send_frames((self.part(4, 2),))
        self.bearer._tick()
        self.assertEqual(len(self.port.writes), 1)
        self.assertEqual(self.sent().payload, self.part(4, 1))
        self.echo(4, 71, self.part(4, 1))
        self.feed(self.hack(4, 71))
        self.assertTrue(first.result)
        self.assertIsNone(second.result)
        self.bearer._tick()
        self.assertEqual(self.sent().payload, self.part(4, 2))

    def test_stations_take_turns(self):
        for station in (4, 9, 12):
            self.bearer.send_frames((self.part(station),))
        for _ in range(3):
            self.bearer._tick()
            self.refuse(self.port.writes[-1])
        self.clock.value += 3   # all three due again: the turn goes on after 12
        self.bearer._tick()
        self.assertEqual(self.destinations(), [4, 9, 12, 4])

    def test_refused_frame_is_not_sent_and_retried_on_schedule(self):
        item = self.bearer.send_frames((self.part(4),))
        self.bearer._tick()
        retry_at = item.retry_at
        self.refuse(self.port.writes[-1])
        self.assertIsNone(self.bearer.outstanding)
        self.assertEqual(self.bearer.dropped["refused"], 1)
        self.assertIsNone(item.result)
        self.bearer._tick()
        self.assertEqual(item.submissions, 1)   # the per-item backoff still applies
        self.clock.value = retry_at
        self.bearer._tick()
        self.assertEqual(item.submissions, 2)
        self.echo(4, 72, self.part(4))
        self.feed(self.hack(4, 72))
        self.assertTrue(item.result)

    def test_at_most_four_unfinished_items_so_bearers_can_fall_back(self):
        items = [self.bearer.send_frames((self.part(station),)) for station in (4, 4, 9, 12)]
        self.assertTrue(all(items))
        self.bearer._tick()   # drained into the link thread, still unfinished
        self.assertFalse(self.bearer.status(0)["room"])   # Wysylka checks this before sealing a counter
        self.assertIsNone(self.bearer.send_frames((self.part(13),)))
        self.echo(4, 73, self.part(4))
        self.feed(self.hack(4, 73))
        self.assertTrue(items[0].result)
        self.assertTrue(self.bearer.status(0)["room"])
        self.assertIsNotNone(self.bearer.send_frames((self.part(13),)))

    def test_disconnect_fails_every_unfinished_item(self):
        items = [self.bearer.send_frames((self.part(4, n),)) for n in range(3)]
        self.bearer._tick()
        late = self.bearer.send_frames((self.part(9),))   # still in the hand-off queue
        self.bearer._disconnect()
        self.assertEqual([item.result for item in [*items, late]], [False] * 4)
        self.assertEqual(self.bearer.unfinished, 0)
        self.assertTrue(self.port.closed)

    def test_link_thread_survives_unexpected_errors(self):
        ports = [Port([RuntimeError("bug")]), Port()]
        opened = []

        def open_port(name):
            opened.append(ports[len(opened)])
            return opened[-1]

        item = self.bearer.send_frames((self.part(4),))
        self.bearer._tick()
        self.bearer.port = None
        self.bearer.FAULT_PAUSE_S = 0
        with unittest.mock.patch.object(wici_stos.serialport, "open_port", open_port):
            thread = threading.Thread(target=self.bearer._run, daemon=True)
            thread.start()
            deadline = time.monotonic() + 5
            while len(opened) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.bearer.thread = thread
            self.bearer.stop()
        self.assertEqual(len(opened), 2)
        self.assertTrue(ports[0].closed)
        self.assertTrue(ports[1].closed)   # the link thread closes its own port when stopped
        self.assertFalse(item.result)   # the item in flight is reported failed, as on a disconnect
        self.assertTrue(any("RuntimeError" in line for line in self.logs), self.logs)


if __name__ == "__main__":
    unittest.main()
