# SPDX-License-Identifier: MIT
"""Durable outbound nonce reservation for a numbered receiver identity.

An instance is owned by the database thread. `persist` must snapshot this SQLite
connection to the encrypted medium and return only after the write is durable.
Unused values in a reserved block are deliberately skipped after a restart.
"""

import hashlib

from .. import envelope

BLOCK = 64
LIMIT = 1 << 32

SCHEMA = """
CREATE TABLE IF NOT EXISTS env_send (
    network INTEGER NOT NULL, sender INTEGER NOT NULL, recipient INTEGER NOT NULL,
    key_id BLOB NOT NULL, reserved_until INTEGER NOT NULL,
    PRIMARY KEY(network, sender, recipient, key_id)
);
"""


class Sender:
    def __init__(self, db, persist):
        self.db, self.persist = db, persist
        self.next = {}
        self.failed = False
        db.executescript(SCHEMA)

    def seal(self, private_key, peer_public_key, network, sender, recipient, plaintext,
             max_payload, message_type=envelope.TYPE_SA1):
        """Reserve and seal one SA1 intent; never reuse a (key, nonce) after failure."""
        if self.failed:
            raise envelope.EnvelopeError("outbound counter state is uncertain")
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='kopia'").fetchone():
            raise envelope.EnvelopeError("restored copy cannot send with the old receiver identity")
        if (self.db.execute("SELECT 1 FROM sqlite_master WHERE name='env_send_guard'").fetchone() and
                self.db.execute("SELECT 1 FROM env_send_guard WHERE id=1 AND blocked=1").fetchone()):
            raise envelope.EnvelopeError("outbound counter boundary needs reconciliation or new identity")
        key = envelope.derive_key(private_key, peer_public_key, network, sender, recipient, sender)
        binding = (network, sender, recipient, hashlib.sha256(key).digest())
        counter = self.next.get(binding)
        if counter is None or counter % BLOCK == 0:
            row = self.db.execute(
                "SELECT reserved_until FROM env_send WHERE network=? AND sender=? AND recipient=? AND key_id=?",
                binding).fetchone()
            start = row[0] if row else 0
            if counter is not None:
                start = max(start, counter)
            if not 0 <= start < LIMIT:
                raise envelope.EnvelopeError("outbound counter exhausted; rotate identity")
            boundary = min(start + BLOCK, LIMIT)
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO env_send VALUES(?,?,?,?,?)", (*binding, boundary))
            try:
                durable = self.persist()
            except BaseException:
                self.failed = True
                raise
            if not durable:
                self.failed = True
                raise OSError("outbound counter reservation was not durably saved")
            counter = start
        # A seal error still burns this counter; it may never be reused for another plaintext.
        self.next[binding] = counter + 1
        return envelope.seal(key, sender, recipient, counter, plaintext, max_payload, message_type)
