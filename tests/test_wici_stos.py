# SPDX-License-Identifier: MIT
"""The numbered laptop bearer preserves hop admission and outbound ordering."""

import unittest

from software.laptop.wici.stanowisko import wici_link
from software.laptop.wici.stanowisko.wici_stos import WiciStos


class Port:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)


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
        self.bearer = WiciStos("fake", 100, 5, 3, bytes(range(16)), bytes(16),
                               self.accepted.append, clock=self.clock)
        self.bearer.port = self.port
        self.bearer.running = True
        self.key = wici_link.derive_key(bytes(range(16)), 100)

    def feed(self, frame):
        self.bearer._receive(wici_link.encode(self.key, frame))

    def test_inbound_hack_follows_durable_callback(self):
        data = wici_link.Frame(wici_link.DATA, wici_link.ACKREQ, 100, 4, 5, 0, 7, 41, bytes(25))
        self.feed(data)
        self.assertEqual(self.accepted, [bytes(25)])
        reply = wici_link.decode(self.key, 100, unpack(self.port.writes[-1]))
        self.assertEqual((reply.kind, reply.source, reply.destination, reply.sequence),
                         (wici_link.HACK, 5, 4, 41))
        writes = len(self.port.writes)
        self.bearer.received = lambda _: (_ for _ in ()).throw(OSError("snapshot failed"))
        self.feed(data)
        self.assertEqual(len(self.port.writes), writes)
        self.assertEqual(self.bearer.dropped["admission"], 1)

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
        wrong = wici_link.Frame(wici_link.HACK, 0, 100, 3, 5, 0, 1, 91)
        self.feed(wrong)
        self.assertIsNone(item.result)
        self.feed(wici_link.Frame(wici_link.HACK, 0, 100, 4, 5, 0, 1, 91))
        self.assertIsNone(item.result)
        self.bearer._tick()
        virtual2 = wici_link.decode(self.key, 100, unpack(self.port.writes[-1]))
        self.assertEqual(virtual2.payload, second)
        self.feed(wici_link.Frame(wici_link.DATA, virtual.flags, 100, 5, 4, 1, 7, 92, second))
        self.feed(wici_link.Frame(wici_link.HACK, 0, 100, 4, 5, 0, 1, 91))
        self.assertIsNone(item.result)
        self.feed(wici_link.Frame(wici_link.HACK, 0, 100, 4, 5, 0, 1, 92))
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
        self.assertFalse(item.result)
        self.assertIsNone(self.bearer.active)


if __name__ == "__main__":
    unittest.main()
