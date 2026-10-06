"""Acceptance cases for the reference contract; no claim of RF or electrical tests."""

import json
import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path

from reference import (OSPStore, PREFIX, assemble, crc16, decode_message,
                       encode_message, fragment, parse_frame, status_after)

MID = "00112233445566778899aabbccddeeff"
REQUEST = [1, 0, MID, 0, 0, 2, "Testowa 10, wejście od podwórza", "Brak wody", 0]


class AirContract(unittest.TestCase):
    """Check external CRC vectors, frame boundaries and adversarial assembly."""

    def test_crc_known_answer(self):
        self.assertEqual(crc16(b"123456789"), 0x29B1)

    def test_all_lengths_and_fifo_bound(self):
        for length in range(1, 601):
            data = bytes(i % 256 for i in range(length))
            frames = fragment(data, b"12345678")
            self.assertLessEqual(len(frames), 7)
            self.assertLessEqual(max(len(f) - len(PREFIX) for f in frames), 103)
            self.assertEqual(assemble(list(reversed(frames)) + frames[:1]), data)

    def test_oversize_and_empty(self):
        for data in (b"", b"x" * 601):
            with self.assertRaises(ValueError):
                fragment(data, b"12345678")

    def test_corruption_missing_and_mixed(self):
        frames = fragment(b"x" * 600, b"12345678")
        corrupt = bytearray(frames[0])
        corrupt[-3] ^= 1
        with self.assertRaises(ValueError):
            parse_frame(bytes(corrupt))
        with self.assertRaises(ValueError):
            assemble(frames[:-1])
        other = fragment(b"y" * 600, b"87654321")
        with self.assertRaises(ValueError):
            assemble(frames + other)

    def test_conflicting_duplicate_with_valid_crc(self):
        frames = fragment(b"x" * 100, b"12345678")
        checked = bytearray(frames[0][len(PREFIX):-2])
        checked[-1] ^= 1
        altered = PREFIX + checked + struct.pack(">H", crc16(checked))
        with self.assertRaises(ValueError):
            assemble(frames + [altered])

    def test_forged_count_rejected_even_with_valid_crc(self):
        frame = fragment(b"x", b"12345678")[0]
        checked = bytearray(frame[len(PREFIX):-2])
        checked[12] = 7
        forged = PREFIX + checked + struct.pack(">H", crc16(checked))
        with self.assertRaises(ValueError):
            parse_frame(forged)


class Messages(unittest.TestCase):
    """Exercise all SA1 shapes and byte limits, including Polish UTF-8."""

    def test_every_shape(self):
        values = [REQUEST, [1, 1, MID, 0, 1, 1], [1, 2, MID, 0, 2, 2],
                  [1, 3, MID, 0, 1, "Jedziemy"], [1, 4, MID, 1, "Woda o 18:00"]]
        for value in values:
            self.assertEqual(decode_message(encode_message(value)), value)

    def test_worst_json_escape_size(self):
        value = [1, 0, MID, 65535, 4, 65535, "\\" * 64, '"' * 96, 2]
        wire = encode_message(value)
        self.assertLessEqual(len(wire), 480)
        self.assertEqual(decode_message(wire), value)
        self.assertLessEqual(len(encode_message([1, 4, MID, 2147483647, "\\" * 192])), 480)

    def test_reject_bool_control_oversize_and_extra(self):
        for index, invalid in ((0, True), (5, 0), (6, "ą" * 33), (7, "\n"), (8, 3)):
            value = REQUEST.copy()
            value[index] = invalid
            with self.assertRaises(ValueError):
                encode_message(value)
        with self.assertRaises(ValueError):
            encode_message(REQUEST + [0])
        with self.assertRaises(ValueError):
            decode_message(b" " * 481)

    def test_unicode_controls_and_formatting_rejected(self):
        for char in ("\u0085", "\u009b", "\u202e", "\u200b", "\u00ad"):
            for value in (REQUEST[:6] + [char] + REQUEST[7:],
                          REQUEST[:7] + [char] + REQUEST[8:],
                          [1, 3, MID, 0, 1, char], [1, 4, MID, 1, char]):
                with self.subTest(codepoint=ord(char), kind=value[1]):
                    with self.assertRaises(ValueError):
                        encode_message(value)
                    external_wire = json.dumps(value, ensure_ascii=True).encode("ascii")
                    with self.assertRaises(ValueError):
                        decode_message(external_wire)
        polish = REQUEST.copy()
        polish[7] = "Zażółć gęślą jaźń — 2 osoby"
        self.assertEqual(decode_message(encode_message(polish)), polish)

    def test_status_cannot_reuse_received_event_or_state(self):
        for event, state in ((1, 2), (1, 3), (2, 1)):
            external_wire = json.dumps([1, 2, MID, 0, event, state]).encode("ascii")
            with self.subTest(event=event, state=state):
                with self.assertRaises(ValueError):
                    decode_message(external_wire)

    def test_status_order_and_contradiction(self):
        self.assertEqual(status_after(3, 3, 1, 1), (3, 3))
        self.assertEqual(status_after(1, 1, 2, 2), (2, 2))
        with self.assertRaises(ValueError):
            status_after(2, 2, 2, 3)
        with self.assertRaises(ValueError):
            status_after(2, 2, 3, 1)


class DurableReception(unittest.TestCase):
    """Check crash boundaries, sender separation and deduplication across restart."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "osp.db"
        self.store = OSPStore(self.path)
        self.source = b"S" * 16
        self.wire = encode_message(REQUEST)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_restart_and_duplicate(self):
        ack = self.store.receive(self.source, self.wire, True)
        self.store.close()
        self.store = OSPStore(self.path)
        spaced = json.dumps(REQUEST, ensure_ascii=False).encode()
        self.assertEqual(self.store.receive(self.source, spaced, True), ack)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM received").fetchone()[0], 1)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM ack_outbox").fetchone()[0], 1)

    def test_interruption_before_commit_leaves_no_ack(self):
        def interrupted():
            raise RuntimeError("Simulated interruption before COMMIT")
        with self.assertRaises(RuntimeError):
            self.store.receive(self.source, self.wire, True, interrupted)
        self.store.close()
        self.store = OSPStore(self.path)
        for table in ("received", "ack_outbox"):
            self.assertEqual(self.store.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)
        self.store.receive(self.source, self.wire, True)

    def test_database_rejects_ack_without_request(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.db:
                self.store.db.execute("INSERT INTO ack_outbox VALUES(?,?,?,?)", (self.source, MID, 0, b"ack"))

    def test_conflicting_reuse_and_separate_sender(self):
        self.store.receive(self.source, self.wire, True)
        changed = REQUEST.copy()
        changed[7] = "Inne zgłoszenie"
        with self.assertRaises(ValueError):
            self.store.receive(self.source, encode_message(changed), True)
        self.store.receive(b"T" * 16, self.wire, True)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM received").fetchone()[0], 2)

    def test_unsigned_message_never_creates_request(self):
        with self.assertRaises(ValueError):
            self.store.receive(self.source, self.wire, False)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM received").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
