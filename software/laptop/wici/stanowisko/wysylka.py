# SPDX-License-Identifier: MIT
"""Sending from the receiving station: intents of RECEIVED, STATUS, REPLY and BULLETIN (stage S3).

docs/spec/stanowisko-osp.md, „Wysyłka”: every message to a station has an intent in SQLite, written in the
same transaction as the event that caused it. Order as in the station: RECEIVED and STATUS, then REPLY and
BULLETIN. At most 4 messages are in flight. After FAILED the intent is retried after 1, 2, 5 and 15 min, then
every 15 min, and from 6 h after the first try every 60 min, each interval ±20% (as `retryDelayS` in
firmware/src/station.cpp). Every retry is a new LXMF message; after DELIVERED the intent is done. A not yet
delivered STATUS for the same (id, revision) is replaced by the newer one. A repeated REQUEST gets the stored
RECEIVED and the newest STATUS again.

The `event` of STATUS, REPLY and BULLETIN is max(last value of its counter + 1, seconds since 2026-01-01
00:00 UTC + P), with counters per STATUS of an id, REPLY of an id and all BULLETIN (oprogramowanie.md,
„Wiadomości SA1”). P is the lasting offset of numbering (0 until the recovery of stage S6). The database keeps
the computer time of the last numbered message without P, and the application does not start when the clock
is earlier than that time.

All functions run in the database thread (przyjecie.Przyjecie); messages in flight live only in memory, so
after a restart their intents are sent again, which the station handles by deduplication.
"""

import random as _random
import secrets

from . import wzorzec

RECEIVED, STATUS, REPLY, BULLETIN = 1, 2, 3, 4
IN_FLIGHT = 4
EPOCH_2026 = 1_767_225_600   # 2026-01-01 00:00 UTC
MAX_EVENT = 2_147_483_647
RETRY_S = (60, 120, 300, 900)              # po 1., 2., 3. i dalszych nieudanych próbach
LATE_AFTER_S, LATE_RETRY_S = 6 * 3600, 3600
STUCK_S = 1800   # LXMF zawsze kończy DELIVERED albo FAILED; to tylko zabezpieczenie przed zgubioną wiadomością

SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    dest BLOB NOT NULL CHECK(length(dest)=16),
    kind INTEGER NOT NULL CHECK(kind BETWEEN 1 AND 4),
    id TEXT NOT NULL,
    revision INTEGER,
    payload BLOB NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    first_try REAL,
    next_try REAL NOT NULL DEFAULT 0,
    done INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS outbox_waiting ON outbox(done, seq);
CREATE TABLE IF NOT EXISTS counters (
    kind INTEGER NOT NULL,
    id TEXT NOT NULL,
    last INTEGER NOT NULL,
    PRIMARY KEY(kind, id)
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value NOT NULL);
"""


class ClockBehind(RuntimeError):
    """The computer clock is earlier than the last numbered message: the duty officer sets the clock."""


def retry_delay(attempts, age, random=_random.random):
    """Seconds to the next try after the attempts-th FAILED, age seconds after the first try."""
    jitter = 0.8 + 0.4 * random()
    if age >= LATE_AFTER_S:
        return LATE_RETRY_S * jitter
    return RETRY_S[min(max(attempts, 1), len(RETRY_S)) - 1] * jitter


def setting(db, key, default):
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return default if row is None else row[0]


class Wysylka:
    """The intent queue. send(dest, content) returns a message or None (no path yet); outcome(message)
    returns True for DELIVERED, False for FAILED and None while it is in flight (stos.Stos)."""

    def __init__(self, send, outcome, log, random=_random.random):
        self.send, self.outcome, self.log, self.random = send, outcome, log, random
        self.flight = {}   # seq -> (wiadomość, czas przekazania do LXMF)

    def open(self, db, now):
        """Create the tables and check the clock at start (stanowisko-osp.md, „Wysyłka”)."""
        db.executescript(SCHEMA)
        last = setting(db, "last_sent", None)
        if last is not None and now < last:
            raise ClockBehind(last)

    # Zapisy poniżej działają w bieżącej transakcji wywołującego; zatwierdza ją wywołujący.

    def number(self, db, kind, mid, now):
        """Next `event` for STATUS or REPLY of id mid, or for BULLETIN; stores the counter and the time."""
        key = "" if kind == BULLETIN else mid
        row = db.execute("SELECT last FROM counters WHERE kind=? AND id=?", (kind, key)).fetchone()
        last = row[0] if row else (1 if kind == STATUS else 0)   # STATUS zaczyna od 2: event=1 ma RECEIVED
        event = max(last + 1, int(now) - EPOCH_2026 + setting(db, "p", 0))
        if event > MAX_EVENT:
            raise ValueError("licznik event wyczerpany")
        db.execute("INSERT OR REPLACE INTO counters VALUES(?,?,?)", (kind, key, event))
        db.execute("INSERT OR REPLACE INTO settings VALUES('last_sent', max(?, coalesce("
                   "(SELECT value FROM settings WHERE key='last_sent'), ?)))", (now, now))
        return event

    def enqueue(self, db, dest, kind, mid, revision, payload):
        if kind == STATUS:   # nieodesłany STATUS tej samej pary (id, revision) zastępuje nowszy
            db.execute("DELETE FROM outbox WHERE done=0 AND dest=? AND kind=? AND id=? AND revision=?",
                       (dest, STATUS, mid, revision))
        db.execute("INSERT INTO outbox(dest, kind, id, revision, payload) VALUES(?,?,?,?,?)",
                   (dest, kind, mid, revision, payload))

    def accepted(self, db, source, mid, revision):
        """In the reception transaction: RECEIVED of an accepted REQUEST or TEST, and for a repeated one
        also the newest STATUS of its id. An intent still waiting goes out at once instead of a new one:
        the repeat shows that the station is reachable now."""
        row = db.execute("SELECT payload FROM ack_outbox WHERE source=? AND id=? AND revision=?",
                         (source, mid, revision)).fetchone()
        if row is None:
            return   # kwarantanna: bez RECEIVED
        waiting = "UPDATE outbox SET next_try=0 WHERE done=0 AND dest=? AND kind=? AND id=?"
        if db.execute(waiting + " AND revision=?", (source, RECEIVED, mid, revision)).rowcount == 0:
            self.enqueue(db, source, RECEIVED, mid, revision, row[0])
        status = db.execute("SELECT revision, event, state FROM statuses WHERE dest=? AND id=? "
                            "ORDER BY event DESC LIMIT 1", (source, mid)).fetchone()
        if status is not None and db.execute(waiting, (source, STATUS, mid)).rowcount == 0:
            payload = wzorzec.encode_message([1, STATUS, mid, *status])
            self.enqueue(db, source, STATUS, mid, status[0], payload)

    # Zdarzenia z panelu (etap S7). Licznik, intencja i zapis modelu wzorcowego w jednej transakcji: model
    # zatwierdza ją swoim `with self.db`, a błąd w dowolnym miejscu wycofuje całość.

    def status(self, store, dest, mid, revision, state, now):
        with store.db:
            event = self.number(store.db, STATUS, mid, now)
            payload = wzorzec.encode_message([1, STATUS, mid, revision, event, state])
            self.enqueue(store.db, dest, STATUS, mid, revision, payload)
            store.send_status(dest, mid, revision, event, state)
        return event

    def reply(self, store, dest, mid, revision, text, now):
        with store.db:
            event = self.number(store.db, REPLY, mid, now)
            payload = wzorzec.encode_message([1, REPLY, mid, revision, event, text])
            self.enqueue(store.db, dest, REPLY, mid, revision, payload)
            store.send_reply(dest, mid, revision, event, text)
        return event

    def bulletin(self, store, text, now):
        """BULLETIN with a new id to every trusted station, one intent per station; returns the id."""
        mid = secrets.token_hex(16)
        with store.db:
            event = self.number(store.db, BULLETIN, mid, now)
            payload = wzorzec.encode_message([1, BULLETIN, mid, event, text])
            for (dest,) in store.db.execute("SELECT source FROM trusted ORDER BY source").fetchall():
                self.enqueue(store.db, dest, BULLETIN, mid, None, payload)
        return mid

    def tick(self, db, now):
        """Collect the outcome of messages in flight and pass due intents to LXMF, at most IN_FLIGHT."""
        for seq, (message, since) in list(self.flight.items()):
            result = self.outcome(message)
            if result is None and now - since < STUCK_S:
                continue
            del self.flight[seq]
            with db:
                if result:
                    db.execute("UPDATE outbox SET done=1 WHERE seq=?", (seq,))
                else:
                    self._failed(db, seq, now)
        free = IN_FLIGHT - len(self.flight)
        if free <= 0:
            return
        rows = db.execute("SELECT seq, dest, payload FROM outbox WHERE done=0 AND next_try<=? "
                          "ORDER BY kind > 2, seq LIMIT ?", (now, free + len(self.flight))).fetchall()
        for seq, dest, payload in rows:
            if free == 0:
                break
            if seq in self.flight:
                continue   # nigdy dwie wysyłki tej samej intencji naraz
            with db:
                db.execute("UPDATE outbox SET first_try=coalesce(first_try, ?) WHERE seq=?", (now, seq))
            try:
                message = self.send(dest, payload)
            except Exception as e:   # noqa: BLE001 - jak FAILED: intencja wraca po odstępie
                self.log(f"stanowisko: wysyłka do {dest.hex()} nie powiodła się: {e!r}")
                message = None
            if message is None:   # bez trasy do stacji albo błąd stosu
                with db:
                    self._failed(db, seq, now)
                continue
            self.flight[seq] = (message, now)
            free -= 1

    def _failed(self, db, seq, now):
        row = db.execute("SELECT attempts + 1, coalesce(first_try, ?) FROM outbox WHERE seq=?", (now, seq)).fetchone()
        if row is None:
            return   # intencję zastąpił nowszy STATUS
        attempts, first = row
        delay = retry_delay(attempts, now - first, self.random)
        db.execute("UPDATE outbox SET attempts=?, next_try=? WHERE seq=?", (attempts, now + delay, seq))
