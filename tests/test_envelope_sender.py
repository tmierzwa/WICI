# SPDX-License-Identifier: MIT
"""Nonce reservation must survive restarts and fail closed on stale media."""

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "software" / "laptop"))

try:
    from wici import envelope
    from wici.stanowisko.envelope_sender import Sender
except ImportError:
    envelope = Sender = None


@unittest.skipIf(Sender is None, "cryptography dependency unavailable")
class SenderTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.snapshots = []
        self.sender = Sender(self.db, lambda: self.snapshots.append(self.db.serialize()) or True)
        self.private = bytes(range(1, 33))
        self.peer_private = bytes(range(33, 65))
        from cryptography.hazmat.primitives.asymmetric import x25519
        self.peer = x25519.X25519PrivateKey.from_private_bytes(self.peer_private).public_key().public_bytes_raw()
        self.own = x25519.X25519PrivateKey.from_private_bytes(self.private).public_key().public_bytes_raw()

    def tearDown(self):
        self.db.close()

    def seal(self, sender=None):
        return (sender or self.sender).seal(self.private, self.peer, 12, 4, 9, b"hello", 236)[0]

    def test_restart_skips_reserved_values(self):
        first = self.seal()
        second = self.seal()
        self.assertEqual((int.from_bytes(first[5:9], "big"), int.from_bytes(second[5:9], "big")), (0, 1))
        self.assertEqual(len(self.snapshots), 1)
        restored = sqlite3.connect(":memory:")
        restored.deserialize(self.snapshots[-1])
        later = Sender(restored, lambda: True).seal(self.private, self.peer, 12, 4, 9, b"hello", 236)[0]
        self.assertEqual(int.from_bytes(later[5:9], "big"), 64)
        opened = envelope.open_part(envelope.derive_key(self.peer_private, self.own, 12, 4, 9, 9), later)
        self.assertEqual(opened.plaintext, b"hello")
        restored.close()

    def test_failed_snapshot_never_seals(self):
        failed = Sender(self.db, lambda: False)
        with self.assertRaises(OSError):
            self.seal(failed)
        with self.assertRaises(envelope.EnvelopeError):
            self.seal(failed)

    def test_restored_copy_refuses_old_identity(self):
        self.db.execute("CREATE TABLE kopia (id INTEGER)")
        with self.assertRaises(envelope.EnvelopeError):
            self.seal()

    def test_recovery_completion_keeps_nonce_guard(self):
        self.db.execute("CREATE TABLE env_send_guard (id INTEGER PRIMARY KEY, blocked INTEGER)")
        self.db.execute("INSERT INTO env_send_guard VALUES(1,1)")
        with self.assertRaises(envelope.EnvelopeError):
            self.seal()

    def test_exhausted_counter_requires_rotation(self):
        key = envelope.derive_key(self.private, self.peer, 12, 4, 9, 4)
        import hashlib
        self.db.execute("INSERT INTO env_send VALUES(?,?,?,?,?)", (12, 4, 9, hashlib.sha256(key).digest(), 1 << 32))
        with self.assertRaises(envelope.EnvelopeError):
            self.seal()


if __name__ == "__main__":
    unittest.main()
