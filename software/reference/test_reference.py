"""Acceptance cases for the reference contract; no claim of RF or electrical tests."""

import json
import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path

from reference import (MAX_CONTENT, OSPStore, PREFIX, QuarantineFull, RevokedSender, accept_from_osp, assemble,
                       check_button_configuration, crc16, decode_message, encode_message, fragment, parse_frame,
                       status_after)

MID = "00112233445566778899aabbccddeeff"
REQUEST = [1, 0, MID, 0, 0, 2, "Testowa 10, wejście od podwórza", "Brak wody", 0]
TEST = [1, 5] + REQUEST[2:]
PUBKEY = bytes(range(64))


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

    def test_len_counts_body_and_crc(self):
        # F79: LEN is the number of bytes after it (BODY and CRC), so the radio packet engines
        # in variable length mode deliver the CRC with the body.
        for length in (1, 86, 87, 600):
            for frame in fragment(b"x" * length, b"12345678"):
                self.assertEqual(frame[len(PREFIX)], len(frame) - len(PREFIX) - 1)
        self.assertEqual(fragment(b"x", b"12345678")[0][len(PREFIX)], 17)
        self.assertEqual(fragment(b"x" * 86, b"12345678")[0][len(PREFIX)], 102)
        frame = fragment(b"x" * 10, b"12345678")[0]
        checked = bytearray(frame[len(PREFIX):-2])
        checked[0] -= 2  # the former meaning (BODY only) is rejected
        with self.assertRaises(ValueError):
            parse_frame(PREFIX + checked + struct.pack(">H", crc16(checked)))

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
                  [1, 3, MID, 0, 1, "Jedziemy"], [1, 4, MID, 1, "Woda o 18:00"], TEST]
        for value in values:
            self.assertEqual(decode_message(encode_message(value)), value)

    def test_worst_case_sizes_fit_content_limit(self):
        # No escapes remain once quotes, backslashes and controls are rejected; multibyte text fills each field.
        worst = {
            "request": ([1, 0, MID, 65535, 9, 65535, "ą" * 32, "😀" * 24, 2], 222),
            "test": ([1, 5, MID, 65535, 9, 65535, "ą" * 32, "😀" * 24, 2], 222),
            "bulletin": ([1, 4, MID, 2147483647, "ż" * 96], 246),
            "reply": ([1, 3, MID, 65535, 2147483647, "€" * 32], 156),
            "status": ([1, 2, MID, 65535, 2147483647, 6], 59),
            "received": ([1, 1, MID, 65535, 1, 1], 50),
        }
        for name, (value, size) in worst.items():
            with self.subTest(kind=name):
                wire = encode_message(value)
                self.assertEqual(len(wire), size)
                self.assertLessEqual(len(wire), MAX_CONTENT)
                self.assertEqual(decode_message(wire), value)
        with self.assertRaises(ValueError):
            encode_message([1, 4, MID, 2147483647, "ż" * 96 + "x"])

    def test_quote_backslash_separators_private_unassigned_rejected(self):
        for char in ('"', "\\", "\u2028", "\u2029", "\ue000", "\U000f0000", "\u0378"):
            for value in (REQUEST[:6] + [char] + REQUEST[7:], REQUEST[:7] + [char] + REQUEST[8:],
                          [1, 3, MID, 0, 1, char], [1, 4, MID, 1, char]):
                with self.subTest(codepoint=ord(char), kind=value[1]):
                    with self.assertRaises(ValueError):
                        encode_message(value)
                    with self.assertRaises(ValueError):
                        decode_message(json.dumps(value, ensure_ascii=True).encode("ascii"))

    def test_text_must_be_nfc(self):
        decomposed = "Za\u0307o\u0301\u0142c\u0301"  # "Zażółć" in NFD
        for value in (REQUEST[:6] + [decomposed] + REQUEST[7:], [1, 4, MID, 1, decomposed]):
            with self.assertRaises(ValueError):
                encode_message(value)
        nfc = REQUEST[:7] + ["Zażółć"] + REQUEST[8:]
        self.assertEqual(decode_message(encode_message(nfc)), nfc)

    def test_reject_bool_control_oversize_and_extra(self):
        for index, invalid in ((0, True), (4, 10), (5, 0), (6, "ą" * 33), (7, "\n"), (8, 3)):
            value = REQUEST.copy()
            value[index] = invalid
            with self.assertRaises(ValueError):
                encode_message(value)
        with self.assertRaises(ValueError):
            encode_message(REQUEST + [0])
        with self.assertRaises(ValueError):
            decode_message(b" " * (MAX_CONTENT + 1))
        for invalid in (TEST[:-1], [1, 6] + REQUEST[2:], TEST[:4] + [10] + TEST[5:]):
            with self.assertRaises(ValueError):
                encode_message(invalid)

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

    def test_button_request_fits_one_opportunistic_packet(self):
        # About 284 B for the reference Reticulum/LXMF versions (conception, chapter 05; D01 open).
        size = check_button_configuration("ś" * 32, ("Potrzeba ustała", "ł" * 48))
        self.assertLessEqual(size, MAX_CONTENT)
        self.assertLessEqual(size, 284)
        with self.assertRaises(ValueError):
            check_button_configuration('Testowa "10"', ())
        with self.assertRaises(ValueError):
            check_button_configuration("Testowa 10", ("ł" * 49,))

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
        self.assertEqual(status_after(2, 5, 3, 3), (3, 3))
        self.assertEqual(status_after(3, 3, 4, 6), (4, 6))
        with self.assertRaises(ValueError):
            status_after(4, 6, 5, 2)
        with self.assertRaises(ValueError):
            status_after(1, 1, 2, 7)


class DurableReception(unittest.TestCase):
    """Check crash boundaries, sender separation and deduplication across restart."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "osp.db"
        self.trusted = {b"S" * 16: PUBKEY, b"T" * 16: bytes(64)}
        self.store = OSPStore(self.path, self.trusted)
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

    def test_test_message_follows_request_path(self):
        ack = self.store.receive(self.source, encode_message(TEST), True)
        self.assertEqual(decode_message(ack), [1, 1, MID, 0, 1, 1])
        self.assertEqual(self.store.receive(self.source, encode_message(TEST), True), ack)
        status = encode_message([1, 2, MID, 0, 2, 2])
        with self.assertRaises(ValueError):
            self.store.receive(self.source, status, True)

    def test_request_and_test_with_same_key_conflict(self):
        self.store.receive(self.source, self.wire, True)
        with self.assertRaises(ValueError):
            self.store.receive(self.source, encode_message(TEST), True)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM received").fetchone()[0], 1)

    def test_purge_keeps_reception_keys(self):
        ack = self.store.receive(self.source, self.wire, True)
        self.store.send_reply(self.source, MID, 0, 2, "Woda o 18:00 przy remizie")
        self.store.purge_content()
        self.store.close()
        self.store = OSPStore(self.path)
        rows = self.store.db.execute("SELECT payload, length(sha256) FROM received").fetchall()
        self.assertEqual(rows, [(None, 32)])
        self.assertEqual(self.store.db.execute("SELECT text FROM replies").fetchall(), [(None,)])
        self.assertEqual(self.store.receive(self.source, self.wire, True), ack)
        changed = REQUEST.copy()
        changed[7] = "Inne zgłoszenie"
        with self.assertRaises(ValueError):
            self.store.receive(self.source, encode_message(changed), True)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM received").fetchone()[0], 1)

    def test_state_5_requires_reply(self):
        self.store.receive(self.source, self.wire, True)
        with self.assertRaises(ValueError):
            self.store.send_status(self.source, MID, 0, 2, 5)
        self.assertEqual(decode_message(self.store.send_status(self.source, MID, 0, 2, 2)), [1, 2, MID, 0, 2, 2])
        self.store.send_reply(self.source, MID, 0, 3, "Przyjdźcie do remizy")
        self.assertEqual(decode_message(self.store.send_status(self.source, MID, 0, 4, 5))[5], 5)
        with self.assertRaises(ValueError):
            self.store.send_status(self.source, MID, 0, 4, 3)
        with self.assertRaises(ValueError):
            self.store.send_status(b"T" * 16, MID, 0, 2, 2)

    def test_unsigned_message_never_creates_request(self):
        with self.assertRaises(ValueError):
            self.store.receive(self.source, self.wire, False)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM received").fetchone()[0], 0)


class Trust(unittest.TestCase):
    """Check quarantine of unknown shelters and pinned-OSP acceptance at the station."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "osp.db"
        self.store = OSPStore(self.path)
        self.unknown = b"U" * 16
        self.wire = encode_message(REQUEST)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def count(self, table):
        return self.store.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def test_unknown_sender_quarantined_without_ack(self):
        self.assertIsNone(self.store.receive(self.unknown, self.wire, True))
        self.store.close()
        self.store = OSPStore(self.path)
        self.assertIsNone(self.store.receive(self.unknown, self.wire, True))
        self.assertEqual((self.count("quarantine"), self.count("received"), self.count("ack_outbox")), (1, 0, 0))

    def test_approval_of_one_message_does_not_trust_sender(self):
        self.store.receive(self.unknown, self.wire, True)
        second = encode_message(TEST[:3] + [1] + TEST[4:])
        self.store.receive(self.unknown, second, True)
        ack = self.store.approve_message(self.unknown, MID, 0)
        self.assertEqual(decode_message(ack), [1, 1, MID, 0, 1, 1])
        self.assertEqual((self.count("quarantine"), self.count("received"), self.count("ack_outbox"),
                          self.count("trusted")), (1, 1, 1, 0))
        self.assertEqual(self.store.receive(self.unknown, self.wire, True), ack)
        self.assertIsNone(self.store.receive(self.unknown, second, True))
        third = encode_message(REQUEST[:3] + [2] + REQUEST[4:])
        self.assertIsNone(self.store.receive(self.unknown, third, True))
        self.assertEqual(self.count("quarantine"), 2)
        with self.assertRaises(ValueError):
            self.store.approve_message(self.unknown, MID, 0)

    def test_add_trusted_requires_card_and_two_people(self):
        for pubkey, approvers in ((b"k" * 32, ("A", "B")), (PUBKEY, ("A", "A")), (PUBKEY, ("A",)),
                                  (PUBKEY, ("A", " "))):
            with self.assertRaises(ValueError):
                self.store.add_trusted(self.unknown, pubkey, approvers)
        self.store.add_trusted(self.unknown, PUBKEY, ("Dyżurny A", "Dyżurny B"))
        self.assertIsNotNone(self.store.receive(self.unknown, self.wire, True))
        with self.assertRaises(ValueError):
            self.store.add_trusted(self.unknown, bytes(64), ("Dyżurny A", "Dyżurny B"))

    def test_revoked_sender_rejected_counted_not_quarantined(self):
        self.store.add_trusted(self.unknown, PUBKEY, ("A", "B"))
        other = b"V" * 16
        self.store.receive(other, self.wire, True)
        self.store.revoke(self.unknown)
        self.store.revoke(other)
        for source in (self.unknown, other, other):
            with self.assertRaises(RevokedSender):
                self.store.receive(source, self.wire, True)
        self.store.close()
        self.store = OSPStore(self.path)
        self.assertEqual((self.store.rejected_count(self.unknown), self.store.rejected_count(other)), (1, 2))
        self.assertEqual((self.count("quarantine"), self.count("received"), self.count("trusted")), (0, 0, 0))
        with self.assertRaises(RevokedSender):
            self.store.add_trusted(other, PUBKEY, ("A", "B"))

    def test_quarantine_limits(self):
        def request(revision):
            return encode_message(REQUEST[:3] + [revision] + REQUEST[4:])
        for revision in range(4):
            self.assertIsNone(self.store.receive(self.unknown, request(revision), True))
        self.assertIsNone(self.store.receive(self.unknown, request(3), True))
        with self.assertRaises(QuarantineFull):
            self.store.receive(self.unknown, request(4), True)
        self.assertEqual(self.count("quarantine"), 4)
        for sender in range(0x60, 0x60 + 63):
            for revision in range(4):
                self.store.receive(bytes([sender]) * 16, request(revision), True)
        self.assertEqual(self.count("quarantine"), 256)
        with self.assertRaises(QuarantineFull):
            self.store.receive(b"\xff" * 16, request(0), True)
        self.assertEqual(self.count("quarantine"), 256)

    def test_quarantine_conflict_rejected(self):
        self.store.receive(self.unknown, self.wire, True)
        changed = REQUEST.copy()
        changed[7] = "Inne zgłoszenie"
        with self.assertRaises(ValueError):
            self.store.receive(self.unknown, encode_message(changed), True)

    def test_station_accepts_only_pinned_osp(self):
        osp = b"O" * 16
        status = encode_message([1, 2, MID, 0, 2, 2])
        self.assertEqual(accept_from_osp(osp, osp, status, True)[1], 2)
        for received in (encode_message([1, 1, MID, 0, 1, 1]), encode_message([1, 4, MID, 1, "Komunikat"])):
            accept_from_osp(osp, osp, received, True)
        with self.assertRaises(ValueError):
            accept_from_osp(osp, b"X" * 16, encode_message([1, 1, MID, 0, 1, 1]), True)
        with self.assertRaises(ValueError):
            accept_from_osp(osp, osp, status, False)
        with self.assertRaises(ValueError):
            accept_from_osp(osp, osp, self.wire, True)


if __name__ == "__main__":
    unittest.main()
