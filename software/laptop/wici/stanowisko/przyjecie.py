# SPDX-License-Identifier: MIT
"""Reception of REQUEST and TEST at the receiving station (stage S2; O01-O03).

docs/spec/stanowisko-osp.md, „Przyjęcie” and „Zaufanie”: a trusted REQUEST or TEST is committed in one SQLite
transaction together with its RECEIVED (the reference OSPStore), and RECEIVED goes out only after COMMIT and
after the sealed snapshot of the database is on the medium (nosnik.py, „Nośnik i szyfrowanie”). A repeated REQUEST gets the same RECEIVED; the same key with other
content is a conflict without overwriting. A station off the trusted list goes to quarantine without RECEIVED;
a removed station too, counted for the alarm „możliwe przejęcie stacji”. Reception time is the computer clock.

One worker thread owns the database: the stack calls deliver() from its own threads and does not wait for
fsync, and the panel (stage S7) runs its operations through call(). Messages arrive here only with a checked
signature (stos.Stos holds those from an unknown sender until its announce). RECEIVED is an intent in the
reception transaction (wysylka.py, stage S3); the same thread writes the snapshot and then passes due
intents to the stack, so nothing leaves before the change is durable. A change made through call() is on
the medium when call() returns.
"""

import queue
import random
import sqlite3
import sys
import threading
import time

from .. import syscrypto
from . import kopie, nosnik, wysylka, wzorzec

# Czas odbioru według zegara komputera, osobno od schematu modelu (stanowisko-osp.md, „Przyjęcie”).
SCHEMA = """
CREATE TABLE IF NOT EXISTS received_at (
    source BLOB NOT NULL,
    id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    at REAL NOT NULL,
    PRIMARY KEY(source,id,revision),
    FOREIGN KEY(source,id,revision) REFERENCES received(source,id,revision)
);
-- Dziennik działań: kto (konto dyżurnego, pusty dla samej aplikacji), co i kiedy; tylko dopisywanie.
CREATE TABLE IF NOT EXISTS dziennik (
    id INTEGER PRIMARY KEY,
    at REAL NOT NULL,
    account TEXT NOT NULL,
    op TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS dziennik_no_update BEFORE UPDATE ON dziennik
BEGIN SELECT RAISE(ABORT, 'dziennik tylko do dopisywania'); END;
CREATE TRIGGER IF NOT EXISTS dziennik_no_delete BEFORE DELETE ON dziennik
BEGIN SELECT RAISE(ABORT, 'dziennik tylko do dopisywania'); END;
"""
SAVE_ERRORS = (OSError, sqlite3.Error, syscrypto.CryptoError, nosnik.StorageError)


class Przyjecie:
    """Reception and sending in their own thread, on the database of an unlocked medium (nosnik.Nosnik and its
    data key). send and outcome are those of the stack (stos.Stos).

    Raises wysylka.ClockBehind when the computer clock is earlier than the last numbered message."""

    TICK_S = 1   # jak często wątek bazy sprawdza intencje bez nowych zadań

    def __init__(self, medium, key, send, outcome, clock=None, log=None, random=random.random, copies=None):
        """copies: kopie.Kopie on the computer disk, written every 5 min (stage S5); None without copies."""
        self.medium, self.key, self.clock = medium, key, clock or time.time
        self.copies, self.next_copy, self.copy_failed = copies, 0, False
        self.log = log or (lambda line: print(line, file=sys.stderr, flush=True))
        self.wysylka = wysylka.Wysylka(send, outcome, self.log, random)
        self.jobs = queue.Queue()
        self.counts = {"received": 0, "duplicate": 0, "quarantined": 0, "rejected": 0, "quarantine_full": 0}
        self.ready = threading.Event()
        self.error = self.save_error = None
        self.thread = threading.Thread(target=self._run, name="przyjecie", daemon=True)
        self.thread.start()
        self.ready.wait()
        if self.error:
            raise self.error

    def _run(self):
        try:
            # Baza tylko w pamięci procesu; na nośnik trafia zaszyfrowana migawka (_save).
            self.store = wzorzec.OSPStore(":memory:")
            body = self.medium.load(self.key)
            if body is not None:
                self.store.db.deserialize(body)
            self.store.db.executescript(SCHEMA)
            self.wysylka.open(self.store.db, self.clock())
        except Exception as e:   # noqa: BLE001 - błąd otwarcia bazy wraca do wątku, który tworzy Przyjecie
            if hasattr(self, "store"):
                self.store.close()
            self.error = e
            self.ready.set()
            return
        self.saved = -1 if body is None else self.store.db.total_changes   # nowy nośnik: pierwsza migawka od razu
        # Baza ze znacznikiem „kopia” (odtworzona z kopii): tryb odzyskania, bez nadawania do finish_recovery.
        self.recovery = self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='kopia'").fetchone() is not None
        self.ready.set()
        due = time.monotonic()
        while True:
            # Intencje co TICK_S także przy ciągłym strumieniu zadań, nie tylko gdy kolejka stoi.
            if time.monotonic() >= due:
                due = time.monotonic() + self.TICK_S
                job = self.tick
            else:
                try:
                    job = self.jobs.get(timeout=max(0, due - time.monotonic()))
                except queue.Empty:
                    continue
            if job is None:
                break
            try:
                job()
            except Exception as e:   # noqa: BLE001 - wątek bazy działa dalej; stacja ponowi wiadomość
                self.log(f"stanowisko: błąd w wątku bazy: {e!r}")
        self._save()
        self.store.close()

    def _save(self):
        """Snapshot of the database on the medium when it changed; True when the medium holds every change."""
        changes = self.store.db.total_changes
        if changes == self.saved:
            return True
        try:
            self.medium.save(self.key, self.store.db.serialize())
        except SAVE_ERRORS as e:
            if self.save_error is None:
                self.log(f"stanowisko: zapis bazy na nośniku nie powiódł się: {e!r}")
            self.save_error = e
            return False
        self.saved, self.save_error = changes, None
        return True

    def tick(self):
        """Pass due intents to the stack (in the database thread), only once the medium holds every change;
        a copy on the computer disk when it is due."""
        if not self._save() or self.recovery:
            return   # w trybie odzyskania także bez kopii: trzy dobre kopie zostają
        if self.copies is not None and self.clock() >= self.next_copy:
            self._copy()   # przed wysyłką: po odzyskaniu nowa kopia z nowym P wychodzi pierwsza
        self.wysylka.tick(self.store.db, self.clock())

    def _copy(self):
        """Copy on the computer disk; a failure is retried after a minute and logged once, without an alarm."""
        now = self.clock()
        try:
            self.copies.write(self.medium, self.key, kopie.with_marker(self.store.db, now), now)
        except SAVE_ERRORS as e:
            self.next_copy = now + kopie.RETRY_S
            if not self.copy_failed:
                self.copy_failed = True
                self._log_action("", "kopia_nieudana", f"{type(e).__name__}: {e}")
            return
        self.next_copy = now + kopie.INTERVAL_S
        if self.copy_failed:
            self.copy_failed = False
            self._log_action("", "kopia_wznowiona")

    def finish_recovery(self, account, recoveries, clock_confirmed):
        """End of the recovery mode (stanowisko-osp.md, „Wysyłka”): the duty officer confirmed the clock
        (±1 min against an independent source) and gave the number of recoveries since the date of the copy.
        In one transaction P = P of the copy + 86 400 s × (1 + recoveries), the entry in the action log
        and the marker gone; then a new copy with the new P, and only then sending."""
        if type(recoveries) is not int or recoveries < 0:
            raise ValueError("liczba odzyskań: 0 lub więcej")
        if clock_confirmed is not True:
            raise ValueError("najpierw potwierdź zegar komputera")

        def finish(store):
            if not self.recovery:
                raise ValueError("baza nie jest w trybie odzyskania")
            db = store.db
            copy_at = db.execute("SELECT at FROM kopia").fetchone()[0]
            p = wysylka.setting(db, "p", 0) + wysylka.RECOVERY_S * (1 + recoveries)
            with db:
                db.execute("INSERT OR REPLACE INTO settings VALUES('p', ?)", (p,))
                db.execute("INSERT INTO dziennik(at, account, op, detail) VALUES(?,?,?,?)",
                           (self.clock(), account, "odzyskanie_koniec",
                            f"kopia z {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(copy_at))}, "
                            f"odzyskań od daty kopii {recoveries}, P {p}"))
                db.execute("DROP TABLE kopia")
            self.recovery = False
            if self.copies is not None:
                self.next_copy = 0   # nowa kopia z nowym P przed pierwszym nadaniem (tick)
            return p
        p = self.call(finish)
        self.call(lambda store: self.tick())
        return p

    def _log_action(self, account, op, detail=""):
        with self.store.db:
            self.store.db.execute("INSERT INTO dziennik(at, account, op, detail) VALUES(?,?,?,?)",
                                  (self.clock(), account, op, detail))
        self._save()

    def call(self, fn):
        """Run fn(store) in the database thread and return its result (or raise its exception) once the
        change is on the medium. StorageError after the change means "not yet durable", not "rejected":
        the change stays in the database and the next snapshot that succeeds writes it."""
        done, result = threading.Event(), {}

        def job():
            try:
                result["value"] = fn(self.store)
                if not self._save():
                    raise nosnik.StorageError(f"zapis bazy na nośniku nie powiódł się: {self.save_error}")
            except BaseException as e:   # noqa: BLE001 - wyjątek wraca do wywołującego
                result["error"] = e
            done.set()
        self.jobs.put(job)
        done.wait()
        if "error" in result:
            raise result["error"]
        return result["value"]

    def action(self, account, op, detail=""):
        """Entry in the action log (dziennik działań), durable when this returns."""
        self.call(lambda store: self._log_action(account, op, detail))

    def deliver(self, source, content):
        """A REQUEST or TEST with a checked signature from source (16 B "lxmf.delivery" hash)."""
        self.jobs.put(lambda: self._receive(source, content))

    def _receive(self, source, content):
        at = self.clock()

        def before_commit():
            # W tej samej transakcji co zgłoszenie i RECEIVED; nowa rewizja dostaje czas pierwszego odbioru.
            value = wzorzec.decode_message(content)
            self.store.db.execute(
                "INSERT OR IGNORE INTO received_at SELECT source, id, revision, ? FROM received "
                "WHERE source=? AND id=? AND revision=?", (at, source, value[2], value[3]))
            self.wysylka.accepted(self.store.db, source, value[2], value[3])

        known = self.store.db.execute("SELECT count(*) FROM received WHERE source=?", (source,)).fetchone()[0]
        try:
            ack = self.store.receive(source, content, True, before_commit=before_commit)
        except wzorzec.QuarantineFull:
            self.counts["quarantine_full"] += 1
            self.log(f"stanowisko: kwarantanna pełna, wiadomość od {source.hex()} odrzucona")
            return
        except ValueError as e:
            self.counts["rejected"] += 1
            self.log(f"stanowisko: wiadomość od {source.hex()} odrzucona: {e}")
            return
        except sqlite3.Error as e:   # bez COMMIT i bez RECEIVED: stacja ponowi zgłoszenie
            self.counts["rejected"] += 1
            self.log(f"stanowisko: zapis wiadomości od {source.hex()} nie powiódł się: {e}")
            return
        if ack is None:
            self.counts["quarantined"] += 1
            return
        after = self.store.db.execute("SELECT count(*) FROM received WHERE source=?", (source,)).fetchone()[0]
        self.counts["received" if after > known else "duplicate"] += 1
        self.tick()   # RECEIVED od razu po COMMIT, jeśli jest miejsce w drodze

    def stop(self):
        self.jobs.put(None)
        self.thread.join(10)
