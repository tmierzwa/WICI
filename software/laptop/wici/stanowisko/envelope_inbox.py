# SPDX-License-Identifier: MIT
"""Transactional receiver-side replay and two-fragment admission for WICI envelopes.

The caller supplies `admit` to write SA1 effects on the same SQLite connection and
`persist` to durably snapshot the database before a hop acknowledgement is allowed.
"""

from .. import envelope

PARTIAL, COMPLETE, DUPLICATE = "partial", "complete", "duplicate"
MAX_PENDING, PER_SENDER, FRAGMENT_S = 256, 4, 120

SCHEMA = """
CREATE TABLE IF NOT EXISTS env_replay (
    network INTEGER NOT NULL, sender INTEGER NOT NULL, recipient INTEGER NOT NULL,
    highest INTEGER NOT NULL, mask BLOB NOT NULL,
    PRIMARY KEY(network, sender, recipient)
);
CREATE TABLE IF NOT EXISTS env_parts (
    network INTEGER NOT NULL, sender INTEGER NOT NULL, recipient INTEGER NOT NULL, counter INTEGER NOT NULL,
    message_type INTEGER NOT NULL, started INTEGER NOT NULL,
    first BLOB, second BLOB,
    PRIMARY KEY(network, sender, recipient, counter, message_type)
);
"""


class Inbox:
    def __init__(self, db, network, persist):
        if type(network) is not int or not 1 <= network <= 0xFFFE:
            raise envelope.EnvelopeError("invalid network binding")
        self.db, self.network, self.persist = db, network, persist
        db.executescript(SCHEMA)

    def receive(self, part, now, admit):
        """Admit an authenticated Part and return a state safe to HACK only after persist().

        `admit(full)` must use this SQLite connection without committing or opening
        a nested transaction. A failed callback rolls back replay and fragment state.
        """
        if (type(now) is not int or now < 0 or part.message_type != envelope.TYPE_SA1 or
                part.number not in (0, 1, 2) or not 0 <= part.counter <= 0xFFFFFFFF or
                not 1 <= part.sender <= 0xFFFE or not 1 <= part.recipient <= 0xFFFE or
                part.sender == part.recipient or
                len(part.plaintext) > (envelope.MAX_SA1 if part.number == 0 else envelope.MAX_SA1 // 2) or
                (part.number != 0 and not part.plaintext)):
            raise envelope.EnvelopeError("invalid part for SA1 inbox")
        with self.db:
            row = self.db.execute("SELECT highest, mask FROM env_replay WHERE network=? AND sender=? AND recipient=?",
                                  (self.network, part.sender, part.recipient)).fetchone()
            window = envelope.ReplayWindow(row[0], int.from_bytes(row[1], "big")) if row else envelope.ReplayWindow()
            if window.highest >= 0 and window.highest - part.counter >= envelope.WINDOW:
                # Outside the bitmap we cannot prove this counter was ever admitted.
                # A hop ACK here could retire a message that the application never saw.
                raise envelope.EnvelopeError("counter outside replay window")
            try:
                proposed = window.accept(part.counter)
            except envelope.EnvelopeError:
                result = DUPLICATE  # bitmap proves this counter was admitted durably
            else:
                self.db.execute("DELETE FROM env_parts WHERE started < ? OR started > ?",
                                (now - FRAGMENT_S, now))
                if part.number == 0:
                    full, result = part.plaintext, COMPLETE
                else:
                    key = (self.network, part.sender, part.recipient, part.counter, part.message_type)
                    previous = self.db.execute(
                        "SELECT started, first, second FROM env_parts WHERE network=? AND sender=? AND recipient=? AND counter=? AND message_type=?",
                        key).fetchone()
                    if previous is None:
                        count = self.db.execute("SELECT count(*) FROM env_parts").fetchone()[0]
                        per_sender = self.db.execute("SELECT count(*) FROM env_parts WHERE network=? AND sender=?",
                                                     (self.network, part.sender)).fetchone()[0]
                        if count >= MAX_PENDING or per_sender >= PER_SENDER:
                            raise envelope.EnvelopeError("fragment inbox full")
                        assembly = envelope.Assembly.start(part, now)
                    else:
                        assembly = envelope.Assembly(part.sender, part.recipient, part.counter, part.message_type,
                                                     previous[0], previous[1], previous[2])
                        assembly, full = assembly.add(part, now)
                    if previous is None:
                        full = None
                    if full is None:
                        self.db.execute("INSERT OR REPLACE INTO env_parts VALUES(?,?,?,?,?,?,?,?)",
                                        (*key, assembly.started_at, assembly.first, assembly.second))
                        result = PARTIAL
                    else:
                        result = COMPLETE
                if result == COMPLETE:
                    admit(full)
                    self.db.execute("INSERT OR REPLACE INTO env_replay VALUES(?,?,?,?,?)",
                                    (self.network, part.sender, part.recipient, proposed.highest,
                                     proposed.mask.to_bytes(8, "big")))
                    self.db.execute("DELETE FROM env_parts WHERE network=? AND sender=? AND recipient=? AND counter=? AND message_type=?",
                                    (self.network, part.sender, part.recipient, part.counter, part.message_type))
        if not self.persist():
            raise OSError("envelope state was not durably saved")
        return result
