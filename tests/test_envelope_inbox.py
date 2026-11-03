# SPDX-License-Identifier: MIT
"""Durable receiver admission: fragments, replay, crash and transaction rollback."""

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "software" / "laptop"))

try:
    from wici import envelope
    from wici.stanowisko import envelope_inbox
except ImportError:
    envelope = envelope_inbox = None


@unittest.skipIf(envelope is None, "cryptography dependency unavailable")
class EnvelopeInboxTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE admitted (message BLOB NOT NULL)")
        self.snapshot = None
        self.inbox = envelope_inbox.Inbox(self.db, 100, self.persist)

    def tearDown(self):
        self.db.close()

    def persist(self):
        self.snapshot = self.db.serialize()
        return True

    def admit(self, message):
        self.db.execute("INSERT INTO admitted VALUES(?)", (message,))

    def part(self, counter, number, data):
        return envelope.Part(4, 2, counter, 0, number, data)

    def receive(self, part, *args, key=bytes(32)):
        return self.inbox.receive(part, key, *args)

    def restart(self):
        self.db.close()
        self.db = sqlite3.connect(":memory:")
        self.db.deserialize(self.snapshot)
        self.inbox = envelope_inbox.Inbox(self.db, 100, self.persist)

    def test_fragments_survive_restart_and_replay_is_idempotent(self):
        self.assertEqual(self.receive(self.part(7, 2, b"world"), 100, self.admit), envelope_inbox.PARTIAL)
        self.restart()
        # A repeat of the stored part is a duplicate: HACK again, no write and no fresh() (transport.md).
        fresh, before = [], self.db.execute("SELECT * FROM env_parts").fetchall()
        self.assertEqual(self.receive(self.part(7, 2, b"world"), 101, self.admit, lambda: fresh.append(1)),
                         envelope_inbox.DUPLICATE)
        self.assertEqual((fresh, self.db.execute("SELECT * FROM env_parts").fetchall()), ([], before))
        self.assertEqual(self.receive(self.part(7, 1, b"hello "), 102, self.admit), envelope_inbox.COMPLETE)
        self.restart()
        self.assertEqual(self.receive(self.part(7, 1, b"hello "), 103, self.admit), envelope_inbox.DUPLICATE)
        self.assertEqual(self.db.execute("SELECT message FROM admitted").fetchall(), [(b"hello world",)])

    def test_conflict_expiry_and_failed_admission(self):
        self.receive(self.part(8, 1, b"old"), 100, self.admit)
        with self.assertRaises(envelope.EnvelopeError):
            self.receive(self.part(8, 1, b"other"), 101, self.admit)
        self.assertEqual(self.db.execute("SELECT first FROM env_parts").fetchone()[0], b"old")
        self.assertEqual(self.receive(self.part(8, 2, b"new"), 221, self.admit), envelope_inbox.PARTIAL)
        self.assertEqual(self.db.execute("SELECT first, second FROM env_parts").fetchone(), (None, b"new"))

        def fail(_):
            raise ValueError("SA1 admission failed")

        with self.assertRaisesRegex(ValueError, "SA1 admission"):
            self.receive(self.part(8, 1, b"fresh"), 222, fail)
        self.assertEqual(self.db.execute("SELECT count(*) FROM env_replay").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT first, second FROM env_parts").fetchone(), (None, b"new"))
        self.assertEqual(self.receive(self.part(8, 1, b"fresh"), 223, self.admit), envelope_inbox.COMPLETE)

    def test_new_pair_key_under_the_same_number_starts_a_fresh_window(self):
        for counter in range(100, 200):
            self.receive(self.part(counter, 0, b"old"), 100, self.admit)
        self.assertEqual(self.receive(self.part(0, 0, b"new"), 101, self.admit, key=bytes([1]) * 32),
                         envelope_inbox.COMPLETE)
        with self.assertRaises(envelope.EnvelopeError):
            self.receive(self.part(0, 0, b"old"), 102, self.admit)

    def test_whole_message_over_a_pending_fragment_is_rejected(self):
        self.assertEqual(self.receive(self.part(9, 1, b"half"), 100, self.admit), envelope_inbox.PARTIAL)
        with self.assertRaises(envelope.EnvelopeError):
            self.receive(self.part(9, 0, b"whole"), 101, self.admit)
        self.assertEqual(self.db.execute("SELECT count(*) FROM admitted").fetchone()[0], 0)

    def test_persist_failure_never_authorizes_hack(self):
        def unavailable():
            return False

        self.inbox.persist = unavailable
        with self.assertRaises(OSError):
            self.receive(self.part(1, 0, b"message"), 100, self.admit)
        self.assertIsNone(self.snapshot)
        self.inbox.persist = self.persist
        self.assertEqual(self.receive(self.part(1, 0, b"message"), 101, self.admit), envelope_inbox.DUPLICATE)
        self.restart()
        self.assertEqual(self.db.execute("SELECT count(*) FROM admitted").fetchone()[0], 1)

    def test_stale_counter_is_not_acknowledged_as_a_duplicate(self):
        self.receive(self.part(2, 0, b"first"), 100, self.admit)
        self.receive(self.part(65, 0, b"later"), 101, self.admit)
        with self.assertRaisesRegex(envelope.EnvelopeError, "outside replay window"):
            self.receive(self.part(1, 0, b"never admitted"), 102, self.admit)
        self.assertEqual(self.receive(self.part(2, 0, b"first"), 103, self.admit),
                         envelope_inbox.DUPLICATE)
        self.restart()
        with self.assertRaisesRegex(envelope.EnvelopeError, "outside replay window"):
            self.receive(self.part(1, 0, b"never admitted"), 104, self.admit)
        self.assertEqual(self.db.execute("SELECT message FROM admitted ORDER BY rowid").fetchall(),
                         [(b"first",), (b"later",)])
