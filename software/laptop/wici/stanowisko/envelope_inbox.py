# SPDX-License-Identifier: MIT
"""Transactional receiver-side replay and two-fragment admission for WICI envelopes.

The caller supplies `admit` to write SA1 effects on the same SQLite connection and
`persist` to durably snapshot the database before a hop acknowledgement is allowed.
Replay and fragment state is bound to the pair key, like the station's FRAM records,
so a station re-provisioned under the same number starts a fresh window.

PermanentRejection marks an authenticated part that this inbox can never admit (no retry
changes the answer); the caller may set its bytes aside durably and acknowledge the hop.
Every other failure (inbox full, storage) is transient and must stay unacknowledged.
"""

import hashlib

from .. import envelope

PARTIAL, COMPLETE, DUPLICATE = "partial", "complete", "duplicate"
MAX_PENDING, PER_SENDER, FRAGMENT_S = 256, 4, 120

SCHEMA = """
CREATE TABLE IF NOT EXISTS env_replay (
    network INTEGER NOT NULL, sender INTEGER NOT NULL, recipient INTEGER NOT NULL, key_id BLOB NOT NULL,
    highest INTEGER NOT NULL, mask BLOB NOT NULL,
    PRIMARY KEY(network, sender, recipient, key_id)
);
CREATE TABLE IF NOT EXISTS env_parts (
    network INTEGER NOT NULL, sender INTEGER NOT NULL, recipient INTEGER NOT NULL, key_id BLOB NOT NULL,
    counter INTEGER NOT NULL, started INTEGER NOT NULL, first BLOB, second BLOB,
    PRIMARY KEY(network, sender, recipient, key_id, counter)
);
"""


class PermanentRejection(envelope.EnvelopeError):
    """The part can never be admitted: invalid, outside the replay window or conflicting."""


class Inbox:
    def __init__(self, db, network, persist):
        if type(network) is not int or not 1 <= network <= 0xFFFE:
            raise envelope.EnvelopeError("invalid network binding")
        self.db, self.network, self.persist = db, network, persist
        db.executescript(SCHEMA)

    def receive(self, part, key, now, admit, fresh=None):
        """Admit a Part authenticated with `key` and return a state safe to HACK only after persist().

        `admit(full)` and `fresh()` must use this SQLite connection without committing or
        opening a nested transaction; `fresh()` runs only for a part not admitted before.
        A failed callback rolls back replay and fragment state; `admit` raises
        PermanentRejection for SA1 that can never be admitted.
        """
        if type(now) is not int or now < 0 or len(key) != 32:
            raise envelope.EnvelopeError("invalid inbox call")   # błąd wywołującego, nie stacji: bez HACK
        if (part.number not in (0, 1, 2) or not 0 <= part.counter <= 0xFFFFFFFF or
                not 1 <= part.sender <= 0xFFFE or not 1 <= part.recipient <= 0xFFFE or
                part.sender == part.recipient or
                len(part.plaintext) > (envelope.MAX_SA1 if part.number == 0 else envelope.MAX_SA1 // 2) or
                (part.number != 0 and not part.plaintext)):
            raise PermanentRejection("invalid part for SA1 inbox")
        pair = (self.network, part.sender, part.recipient, hashlib.sha256(bytes(key)).digest())
        message = (*pair, part.counter)
        with self.db:
            row = self.db.execute("SELECT highest, mask FROM env_replay WHERE network=? AND sender=? AND recipient=? "
                                  "AND key_id=?", pair).fetchone()
            window = envelope.ReplayWindow(row[0], int.from_bytes(row[1], "big")) if row else envelope.ReplayWindow()
            if window.highest >= 0 and window.highest - part.counter >= envelope.WINDOW:
                # Outside the bitmap we cannot prove this counter was ever admitted, so it is never
                # admitted: the caller keeps the bytes before the hop ACK, and the station's SA1 retry
                # (new counter, until RECEIVED) delivers the message.
                raise PermanentRejection("counter outside replay window")
            try:
                proposed = window.accept(part.counter)
            except envelope.EnvelopeError:
                result = DUPLICATE  # bitmap proves this counter was admitted durably
            else:
                self.db.execute("DELETE FROM env_parts WHERE started < ? OR started > ?",
                                (now - FRAGMENT_S, now))
                previous = self.db.execute(
                    "SELECT started, first, second FROM env_parts WHERE network=? AND sender=? AND recipient=? "
                    "AND key_id=? AND counter=?", message).fetchone()
                if part.number == 0:
                    if previous is not None:
                        # As on the station: one counter cannot carry both a whole message and a fragment.
                        raise PermanentRejection("whole envelope over a pending fragment")
                    full, result = part.plaintext, COMPLETE
                elif previous is not None and previous[part.number] == part.plaintext:
                    # Powtórzenie zapisanej części: ponowny HACK bez zapisu i bez fresh() (transport.md,
                    # „Podział na części”), jak DUPLICATE na stacji. Ta sama ramka nie przestawia drogi odpowiedzi.
                    result = DUPLICATE
                else:
                    if previous is None:
                        count = self.db.execute("SELECT count(*) FROM env_parts").fetchone()[0]
                        per_sender = self.db.execute("SELECT count(*) FROM env_parts WHERE network=? AND sender=?",
                                                     (self.network, part.sender)).fetchone()[0]
                        if count >= MAX_PENDING or per_sender >= PER_SENDER:
                            raise envelope.EnvelopeError("fragment inbox full")   # transient
                    try:
                        if previous is None:
                            assembly = envelope.Assembly.start(part, now)
                        else:
                            assembly = envelope.Assembly(part.sender, part.recipient, part.counter,
                                                         envelope.TYPE_SA1, previous[0], previous[1], previous[2])
                            assembly, full = assembly.add(part, now)
                    except envelope.EnvelopeError as exc:   # conflicting or foreign fragment, too long SA1
                        raise PermanentRejection(str(exc)) from exc
                    if previous is None:
                        full = None
                    if full is None:
                        self.db.execute("INSERT OR REPLACE INTO env_parts VALUES(?,?,?,?,?,?,?,?)",
                                        (*message, assembly.started_at, assembly.first, assembly.second))
                        result = PARTIAL
                    else:
                        result = COMPLETE
                if result == COMPLETE:
                    admit(full)
                    self.db.execute("INSERT OR REPLACE INTO env_replay VALUES(?,?,?,?,?,?)",
                                    (*pair, proposed.highest, proposed.mask.to_bytes(8, "big")))
                    self.db.execute("DELETE FROM env_parts WHERE network=? AND sender=? AND recipient=? "
                                    "AND key_id=? AND counter=?", message)
            if fresh is not None and result != DUPLICATE:
                fresh()
        if not self.persist():
            raise OSError("envelope state was not durably saved")
        return result
