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
reception transaction (wysylka.py, stage S3); due intents go to the stack only once the medium holds every
change, so nothing leaves before the change is durable. A change made through call() is on the medium when
call() returns.

The sealed snapshot of the whole database costs time in proportion to its size, so a writer thread writes it
(and the copy every 5 min) while the database thread goes on; the database thread only takes the bytes
(serialize). A reception does not wait for a snapshot before its HACK or RECEIVED: the raw WICI-Link frame or
LXMF message and its reception time go to the intake journal on the medium with fsync
(nosnik.journal_append), a cost that does not grow with the database, and a later snapshot makes them
redundant. On start the receptions journaled after the loaded snapshot are admitted again, in order and with
their own times, by the same code (stanowisko-osp.md, „Przyjęcie koperty WICI-Link”).
"""

import contextlib
import hashlib
import json
import os
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
-- Dziennik działań: kto (konto dyżurnego, pusty dla samej aplikacji), co i kiedy, przy czym (stacja, id i
-- rewizja zgłoszenia, gdy dotyczy); bez treści zgłoszeń i komunikatów; tylko dopisywanie.
CREATE TABLE IF NOT EXISTS dziennik (
    id INTEGER PRIMARY KEY,
    at REAL NOT NULL,
    account TEXT NOT NULL,
    op TEXT NOT NULL,
    detail TEXT NOT NULL,
    source BLOB,
    mid TEXT,
    revision INTEGER
);
CREATE TRIGGER IF NOT EXISTS dziennik_no_update BEFORE UPDATE ON dziennik
BEGIN SELECT RAISE(ABORT, 'dziennik tylko do dopisywania'); END;
CREATE TRIGGER IF NOT EXISTS dziennik_no_delete BEFORE DELETE ON dziennik
BEGIN SELECT RAISE(ABORT, 'dziennik tylko do dopisywania'); END;
-- Karty zaufanych stacji (nazwa WICI-xxxxxx, adres schronienia, odcisk) do wyświetlania w panelu.
CREATE TABLE IF NOT EXISTS karty (
    source BLOB PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    fingerprint TEXT NOT NULL
);
-- Numbered WICI envelope identities; retained after removing trust so a number cannot
-- silently be assigned to a different key on the same medium (only the panel rebind moves it).
CREATE TABLE IF NOT EXISTS numery (
    net_id INTEGER NOT NULL,
    station INTEGER NOT NULL,
    source BLOB NOT NULL,
    public_key BLOB NOT NULL,
    PRIMARY KEY (net_id, station),
    UNIQUE (net_id, source)
);
CREATE TABLE IF NOT EXISTS env_send_guard (
    id INTEGER PRIMARY KEY CHECK(id=1),
    blocked INTEGER NOT NULL CHECK(blocked=1)
);
-- Ramki WICI-Link z kopertą uwierzytelnioną przez znaną stację, których nie da się przyjąć nigdy (licznik poza
-- oknem, sprzeczna część, błędne SA1): surowe bajty do wglądu dyżurnego i alarmu. Po zapisie idzie HACK, jak
-- z przekaźnika. Najwyżej REJECTED_PER_SENDER wierszy na nadawcę i REJECTED_MAX łącznie; dalsze ramki tylko
-- liczy env_rejected_overflow, a zapisane zostają (pierwsze dowody są najcenniejsze).
CREATE TABLE IF NOT EXISTS env_rejected (
    id INTEGER PRIMARY KEY,
    net_id INTEGER NOT NULL,
    sender INTEGER NOT NULL,
    reason TEXT NOT NULL,
    first_at REAL NOT NULL,
    at REAL NOT NULL,
    frame BLOB NOT NULL,
    count INTEGER NOT NULL,
    UNIQUE (net_id, frame)
);
CREATE TABLE IF NOT EXISTS env_rejected_overflow (
    net_id INTEGER NOT NULL,
    sender INTEGER NOT NULL,
    count INTEGER NOT NULL,
    at REAL NOT NULL,
    PRIMARY KEY (net_id, sender)
);
CREATE TABLE IF NOT EXISTS bearer_route (
    source BLOB PRIMARY KEY,
    bearer TEXT NOT NULL CHECK(bearer IN ('wici', 'reticulum'))
);
CREATE TABLE IF NOT EXISTS bearer_override (
    source BLOB PRIMARY KEY,
    bearer TEXT NOT NULL CHECK(bearer IN ('wici', 'reticulum'))
);
-- Koperty WICI wysłane do stacji: licznik koperty -> intencja (skrót treści), żeby dowód doręczenia stacji
-- zamknął intencję także po ponowieniu pod nowym licznikiem. Klucz kierunku odbiorca -> stacja (key_id) oddziela
-- liczniki nowej tożsamości od starych. Wiersze starsze niż WICI_SENT_S są usuwane.
CREATE TABLE IF NOT EXISTS wici_sent (
    net_id INTEGER NOT NULL,
    receiver INTEGER NOT NULL,
    station INTEGER NOT NULL,
    key_id BLOB NOT NULL,
    counter INTEGER NOT NULL,
    payload_hash BLOB NOT NULL,
    at REAL NOT NULL,
    PRIMARY KEY (net_id, receiver, station, key_id, counter)
);
-- Wpisy decyzji, które nie idą radiem: stan 3 ze źródłem i czasem potwierdzenia, stan 4 z adresatem i czasem.
CREATE TABLE IF NOT EXISTS decyzje (
    id INTEGER PRIMARY KEY,
    source BLOB NOT NULL,
    mid TEXT NOT NULL,
    state INTEGER NOT NULL,
    detail TEXT NOT NULL,
    at REAL NOT NULL,
    account TEXT NOT NULL
);
"""
SAVE_ERRORS = (OSError, sqlite3.Error, syscrypto.CryptoError, nosnik.StorageError)
JOURNAL_RECORDS, JOURNAL_S = 256, 60   # migawka najpóźniej po tylu rekordach dziennika przyjęć albo sekundach
REJECTED_MAX = 256         # wierszy env_rejected (po najwyżej 255 B ramki)
REJECTED_PER_SENDER = 16   # wierszy env_rejected na numer nadawcy: przejęta stacja nie zużywa nośnika
WICI_SENT_S = 7 * 86400    # jak długo spóźniony dowód doręczenia zamyka intencję


class Late(TimeoutError):
    """call() did not finish in time. The job still runs, and its change still becomes durable."""


class NotAuthenticated(Exception):
    """A frame with a valid network MAC whose envelope this receiver does not authenticate to a known station:
    identity not bound to the network, envelope length, receiver number, unknown station, envelope MAC.

    The network key alone does not identify the sender, so the bytes are no evidence and nothing is stored;
    the frame is only counted. It still gets its HACK (admit_wici_frame): the relays took the frame without
    checking the envelope, and withholding the HACK would only turn them away from the root. The message
    arrives by the station's SA1 retry (new counter, until RECEIVED) once the duty officer adds the station
    or the receiver identity matches. `reason` is one of a few fixed texts."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def rejected_summary(db):
    """{"frames": stored frames, "total": every receipt incl. repeats and over the per-sender cap, "newest": time}."""
    frames, total, newest = db.execute("SELECT count(*), coalesce(sum(count), 0), max(at) FROM env_rejected").fetchone()
    over, over_at = db.execute("SELECT coalesce(sum(count), 0), max(at) FROM env_rejected_overflow").fetchone()
    return {"frames": frames, "total": total + over,
            "newest": max((t for t in (newest, over_at) if t is not None), default=None)}


def envelope_rejections(db, limit=50):
    """Alarm data for the panel (inside call): WICI-Link frames set aside as never admissible, newest first,
    and per sender the frames counted without storing them over REJECTED_PER_SENDER."""
    rows = [{"net_id": n, "sender": s, "reason": r, "first_at": f, "at": a, "count": c, "frame": frame.hex()}
            for n, s, r, f, a, c, frame in db.execute(
                "SELECT net_id, sender, reason, first_at, at, count, frame FROM env_rejected "
                "ORDER BY id DESC LIMIT ?", (limit,))]
    overflow = [{"net_id": n, "sender": s, "count": c, "at": a} for n, s, c, a in db.execute(
        "SELECT net_id, sender, count, at FROM env_rejected_overflow ORDER BY at DESC")]
    return {**rejected_summary(db), "rows": rows, "overflow": overflow}


class Przyjecie:
    """Reception and sending in their own thread, on the database of an unlocked medium (nosnik.Nosnik and its
    data key). send and outcome are those of the stack (stos.Stos).

    Raises wysylka.ClockBehind when the computer clock is earlier than the last numbered message."""

    TICK_S = 1   # jak często wątek bazy sprawdza intencje bez nowych zadań

    ANNOUNCE_S = 6 * 3600   # ogłoszenie adresu odbiorcy co 6 h ±20% (stanowisko-osp.md, „Ogłoszenia”)

    def __init__(self, medium, key, send, outcome, clock=None, log=None, random=random.random, copies=None,
                 announce=None, online=None):
        """copies: kopie.Kopie on the computer disk, written every 5 min (stage S5); None without copies.
        announce, online: the stack's announce and connection state (stage S8): the receiver address is
        announced every 6 h ±20% and after every reconnection to the station."""
        self.medium, self.key, self.clock = medium, key, clock or time.time
        self.announce, self.online, self.random = announce, online, random
        self.next_announce, self.was_online = None, None
        self.copies, self.next_copy, self.copy_failed = copies, 0, False
        self.last_copy_at = None   # czas najnowszej kopii na dysku komputera (panel, przekazanie zmiany)
        self.log = log or (lambda line: print(line, file=sys.stderr, flush=True))
        self.wysylka = wysylka.Wysylka(send, outcome, self.log, random)
        self.jobs = queue.Queue()
        self.last_bearer = {}  # source -> last authenticated receive path; DB thread only
        self.bearer_override = {}  # operator choice takes precedence until explicitly cleared
        self.counts = {"received": 0, "duplicate": 0, "quarantined": 0, "rejected": 0, "quarantine_full": 0,
                       "envelope_rejected": 0}
        self.identity_cache = None   # (klucz prywatny, wpis karty) raz na sesję; wątek bazy
        self.rejected = {"frames": 0, "total": 0, "newest": None}   # alarm ramek odłożonych (rejected_summary)
        # Ramki bez uwierzytelnienia koperty: tylko w pamięci, przyczyna -> {count, at, net_id, sender}; nadawca
        # to deklaracja z nagłówka, nie fakt. Kluczami są stałe przyczyny NotAuthenticated, więc słownik jest mały.
        self.unauthenticated = {}
        self.ready = threading.Event()
        self.error = self.save_error = None
        self.discard = False   # ZNISZCZ DANE: bez ostatniej migawki przy zatrzymaniu
        self.stopped = False   # po stop() wywołania call() kończą się błędem zamiast czekać bez końca
        # Zapisy na nośniku i dysku komputera (migawka, kopia) w wątku zapisu, po kolei; stan niżej należy do
        # wątku bazy. `saved`: wszystkie zmiany do tego total_changes przetrwają zanik (migawka albo dziennik
        # przyjęć); `durable` budzi wywołania call() czekające na swoją migawkę.
        self.writer = queue.Queue()
        self.writes, self.in_flight, self.want = [], False, False
        self.fail_seq, self.fail_cover, self.journal_error = 0, -1, None
        self.journal_count, self.journal_first = 0, None
        self.replaying, self.intake, self.captured = False, None, -1
        self.durable = threading.Condition()
        self.writer_thread = threading.Thread(target=self._write_loop, name="przyjecie-zapis", daemon=True)
        self.writer_thread.start()
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
            # Usunięta treść (ZAMKNIJ ZDARZENIE, kwarantanna) nadpisana zerami, nie zostaje w wolnych stronach
            # migawki i kopii. Ustawienie połączenia, więc po deserialize.
            self.store.db.execute("PRAGMA secure_delete=ON")
            self.store.db.executescript(SCHEMA)
            self.last_bearer = dict(self.store.db.execute("SELECT source, bearer FROM bearer_route"))
            self.bearer_override = dict(self.store.db.execute("SELECT source, bearer FROM bearer_override"))
            columns = {row[1] for row in self.store.db.execute("PRAGMA table_info(dziennik)")}
            for column, kind in (("source", "BLOB"), ("mid", "TEXT"), ("revision", "INTEGER")):
                if column not in columns:   # baza z etapu S4-S8
                    self.store.db.execute(f"ALTER TABLE dziennik ADD COLUMN {column} {kind}")
            self.wysylka.open(self.store.db, self.clock())
            self.saved = -1 if body is None else self.store.db.total_changes   # nowy nośnik: pierwsza migawka od razu
            self.base_gen, self.base_id = self.medium.gen, self.medium.journal_id
            # Baza ze znacznikiem „kopia” (odtworzona z kopii): tryb odzyskania, bez nadawania do finish_recovery.
            self.recovery = self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='kopia'").fetchone() is not None
            self._replay()
        except Exception as e:   # noqa: BLE001 - błąd otwarcia bazy wraca do wątku, który tworzy Przyjecie
            if hasattr(self, "store"):
                self.store.close()
            self.medium.journal_close()
            self.writer.put(None)
            self.error = e
            self.ready.set()
            return
        if self.copies is not None:
            self.last_copy_at = self.copies.newest(self.key)
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
        if self.discard:
            self._flush()
        else:
            self._save_now()
        self.writer.put(None)
        self.writer_thread.join(30)
        self.medium.journal_close()
        self.store.close()

    def _replay(self):
        """Admit again, in order and with their own times, the frames journaled after the loaded snapshot; the
        first tick then writes a snapshot with them (stanowisko-osp.md, „Przyjęcie koperty WICI-Link”)."""
        records = self.medium.journal_records(self.key)
        if not records:
            return
        self.replaying = True
        try:
            for raw in records:
                r = json.loads(raw)
                try:
                    if r["kind"] == "wici":
                        self._admit_frame(r["net"], bytes.fromhex(r["wire"]), r["bearer"], r["at"])
                    else:
                        self._receive(bytes.fromhex(r["source"]), bytes.fromhex(r["content"]), r["bearer"], r["at"])
                except Exception:   # noqa: BLE001 - jak przy pierwszym przyjęciu: odmowa zostaje odmową
                    pass
        finally:
            self.replaying = False
        self.log(f"stanowisko: z dziennika przyjęć ponownie przyjęto {len(records)} wiadomości")

    # ---- zapis na nośniku -------------------------------------------------------------------------

    def _write_loop(self):
        while (job := self.writer.get()) is not None:
            job()

    def _submit(self, kind, fn, **info):
        """Run fn() in the writer thread; the database thread settles the result in _finish_writes."""
        item = {"kind": kind, "error": None, "done": threading.Event(), **info}

        def run():
            try:
                fn()
            except BaseException as e:   # noqa: BLE001 - wynik zapisu rozstrzyga wątek bazy
                item["error"] = e
            item["done"].set()
            self.jobs.put(self._finish_writes)
        self.writes.append(item)
        self.writer.put(run)

    def _snapshot(self, urgent=False, force=False):
        """Take a snapshot for the writer when a change is not yet durable, or when the intake journal is due
        for compaction (JOURNAL_RECORDS, JOURNAL_S; force: whenever it has records). One write at a time: an
        urgent request during a write waits for its end. The database thread spends only the serialize() on it."""
        total = self.store.db.total_changes
        if self.in_flight:
            self.want = self.want or (urgent and total > self.captured)
            return
        if total <= self.saved and not (self.journal_count and (
                force or self.journal_count >= JOURNAL_RECORDS or time.monotonic() - self.journal_first >= JOURNAL_S)):
            return
        body = self.store.db.serialize()
        gen, mark = max(self.base_gen + 1, self.medium.next_gen()), os.urandom(8).hex()
        # Ramki przyjęte od tej chwili idą do dziennika za tą migawką, nawet zanim trafi na nośnik.
        self.base_gen, self.base_id, self.journal_count, self.journal_first = gen, mark, 0, None
        self.in_flight, self.want, self.captured = True, False, total
        self._submit("snapshot", lambda: self.medium.save(self.key, body, gen, mark), gen=gen, changes=total)

    def _finish_writes(self):
        """In the database thread: the results of finished writes, in order of submission. Intents that waited
        for a snapshot go with the next tick (TICK_S)."""
        while self.writes and self.writes[0]["done"].is_set():
            item = self.writes.pop(0)
            if item["kind"] == "snapshot":
                self._snapshot_written(item)
            else:
                self._copy_written(item)
        with self.durable:
            self.durable.notify_all()

    def _snapshot_written(self, item):
        self.in_flight = False
        error = item["error"]
        if error is not None:
            if self.save_error is None:
                self.log(f"stanowisko: zapis bazy na nośniku nie powiódł się: {error!r}")
            with self.durable:
                self.save_error, self.fail_seq, self.fail_cover = error, self.fail_seq + 1, item["changes"]
            self.want = False   # następna próba w ticku, co TICK_S
            return
        with self.durable:
            self.saved, self.save_error = max(self.saved, item["changes"]), None
        try:
            self.medium.journal_prune(item["gen"])
        except OSError as e:   # stary dziennik nie wróci: należy do starszej migawki
            self.log(f"stanowisko: usunięcie starego dziennika przyjęć nie powiodło się: {e!r}")
        if self.want or self.store.db.total_changes > self.saved:
            self._snapshot(urgent=True)

    def _flush(self):
        """In the database thread: wait until every submitted write is settled."""
        while self.writes:
            self.writes[0]["done"].wait()
            self._finish_writes()

    def flush(self):
        """For an operation inside call() that writes the medium or the copies itself (new station password,
        removing copies): no snapshot or copy is being written meanwhile."""
        self._flush()

    def _save_now(self):
        """In the database thread: a snapshot of every change, written before this returns; True when the medium
        holds every change. For the rare cases that must not go on before it (a new outbound counter block,
        the end of the session, which so leaves no intake journal behind)."""
        self._flush()
        if self.store.db.total_changes > self.saved or self.journal_count:
            self._snapshot(urgent=True, force=True)
            self._flush()
        return self.store.db.total_changes <= self.saved

    def _journal_frame(self):
        """Inbox `persist` for the reception being admitted (self.intake: journal record and total_changes before
        it): True once it survives a power cut, so its HACK or RECEIVED may go. Nothing to do when every change is
        durable already; else the raw reception and its time go to the intake journal, a cost that does not grow
        with the database."""
        total = self.store.db.total_changes
        if self.replaying or total <= self.saved:
            return True
        if self.intake is None:
            return self._save_now()   # zmiana poza przyjęciem ramki: nie ma czego dopisać do dziennika
        if self.medium.gen >= self.base_gen and self.medium.journal_id != self.base_id and not self.in_flight:
            # Migawka zapisana poza wątkiem zapisu (nowe hasło stanowiska) obejmuje wszystko: dziennik idzie za nią.
            # Porównanie znacznika, nie tylko numeru: po nieudanej migawce w pamięci numer może się zgadzać.
            self.base_gen, self.base_id = self.medium.gen, self.medium.journal_id
        if self.base_id is None:
            return self._save_now()   # nośnik bez migawki z dziennikiem (pierwszy start, starszy format)
        record, before = self.intake
        try:
            self.medium.journal_append(self.key, self.base_gen, self.base_id, json.dumps(record).encode())
        except SAVE_ERRORS as e:
            if self.journal_error is None:
                self.log(f"stanowisko: zapis dziennika przyjęć nie powiódł się: {e!r}")
            self.journal_error = e
            return False
        self.journal_error = None
        self.journal_count += 1
        if self.journal_first is None:
            self.journal_first = time.monotonic()
        if self.saved >= before:   # wszystko sprzed ramki było trwałe, a ramka jest w dzienniku
            with self.durable:
                self.saved = total
                self.durable.notify_all()
        return True

    def tick(self):
        """Pass due intents to the stack (in the database thread), only once the medium holds every change;
        a copy on the computer disk and the announce when they are due. Nothing in the recovery mode."""
        self.rejected = rejected_summary(self.store.db)   # także po ZAMKNIJ ZDARZENIE (zamkniecie.purge)
        self._snapshot()
        if self.saved < self.store.db.total_changes or self.recovery:
            return   # w trybie odzyskania także bez kopii: trzy dobre kopie zostają
        if self.copies is not None and self.clock() >= self.next_copy:
            self._copy()   # przed wysyłką: po odzyskaniu nowa kopia z nowym P wychodzi pierwsza
        changes_before = self.store.db.total_changes
        with self.store.db:
            self.store.db.execute("DELETE FROM wici_sent WHERE at < ?", (self.clock() - WICI_SENT_S,))
        self.wysylka.tick(self.store.db, self.clock())
        # Same zapisy ewidencji wysyłki (próba, DELIVERED, następna próba) nie wymagają osobnej migawki: po
        # zaniku wiadomość wyjdzie ponownie, a stacja ją odrzuci jako powtórzenie. Trafią do następnej migawki.
        if self.saved == changes_before:
            self.saved = self.store.db.total_changes
        self._announce()

    def _announce(self):
        if self.announce is None:
            return
        now = self.clock()
        online = bool(self.online()) if self.online else True
        # Start ogłasza stos sam (Stos.start); tu: ponowne połączenie ze stacją i co 6 h ±20%. Do pierwszego
        # połączenia (przed startem stosu) stan zostaje nieznany, więc samo połączenie po starcie nie ogłasza.
        again = online and self.was_online is False
        if online or self.was_online is not None:
            self.was_online = online
        if self.next_announce is None:
            self.next_announce = now + self.ANNOUNCE_S * (0.8 + 0.4 * self.random())
        if again or now >= self.next_announce:
            self.next_announce = now + self.ANNOUNCE_S * (0.8 + 0.4 * self.random())
            try:
                self.announce()
            except Exception as e:   # noqa: BLE001 - ogłoszenie wróci przy następnej okazji
                self.log(f"stanowisko: ogłoszenie nie powiodło się: {e!r}")

    def _copy(self):
        """Copy on the computer disk, written by the writer thread from the bytes taken here (the integrity check
        too); a failure is retried after a minute and logged once, without an alarm."""
        now, body, frozen = self.clock(), self.store.db.serialize(), kopie.frozen_before(self.store.db)
        self.next_copy = now + kopie.INTERVAL_S

        def write():
            with contextlib.closing(sqlite3.connect(":memory:")) as db:
                db.deserialize(body)
                self.copies.write(self.medium, self.key, kopie.with_marker(db, now), now, frozen)
        self._submit("copy", write, at=now)

    def _copy_written(self, item):
        e = item["error"]
        if e is not None and not isinstance(e, SAVE_ERRORS):
            self.log(f"stanowisko: kopia na dysku komputera: {e!r}")
        if e is not None:
            self.next_copy = item["at"] + kopie.RETRY_S
            if not self.copy_failed:
                self.copy_failed = True
                self._log_action("", "kopia_nieudana", f"{type(e).__name__}: {e}")
            return
        self.last_copy_at = item["at"]
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
                # A restored SQLite snapshot can be older than a transmitted WICI
                # counter reservation. The legacy recovery offset protects SA1 event
                # numbers, but cannot prove a nonce upper bound for the same key.
                db.execute("INSERT OR REPLACE INTO env_send_guard VALUES(1,1)")
                db.execute("DROP TABLE IF EXISTS env_rekey_stage")
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

    def _log_action(self, account, op, detail="", source=None, mid=None, revision=None):
        """Entry in the action log in the database thread (inside call or tick)."""
        with self.store.db:
            self.store.db.execute("INSERT INTO dziennik(at, account, op, detail, source, mid, revision) "
                                  "VALUES(?,?,?,?,?,?,?)", (self.clock(), account, op, detail, source, mid, revision))
        self._snapshot(urgent=True)

    def call(self, fn, timeout=None, durable=True):
        """Run fn(store) in the database thread and return its result (or raise its exception) once the
        change is on the medium. StorageError after the change means "not yet durable", not "rejected":
        the change stays in the database and the next snapshot that succeeds writes it. With timeout
        (seconds) Late is raised when the job has not finished by then; the job still completes.
        durable=False: fn makes its change durable itself (the intake journal of a WICI-Link frame)."""
        done, result = threading.Event(), {}

        def job():
            try:
                result["value"] = fn(self.store)
                ticket = self.store.db.total_changes
                if durable and ticket > self.saved:
                    result["ticket"], result["fails"] = ticket, self.fail_seq
                    self._snapshot(urgent=True)
            except BaseException as e:   # noqa: BLE001 - wyjątek wraca do wywołującego
                result["error"] = e
            done.set()
        if self.stopped:
            raise RuntimeError("wątek bazy zatrzymany")
        self.jobs.put(job)
        end = None if timeout is None else time.monotonic() + timeout
        while not done.wait(1 if end is None else max(0, min(1, end - time.monotonic()))):
            if not self.thread.is_alive():
                raise RuntimeError("wątek bazy zatrzymany")
            if end is not None and time.monotonic() >= end:
                raise Late(f"przyjęcie trwa dłużej niż {timeout * 1000:.0f} ms")
        if "error" in result:
            raise result["error"]
        if "ticket" in result:
            self._wait_durable(result["ticket"], result["fails"], end, timeout)
        return result["value"]

    def _wait_durable(self, ticket, fails, end, timeout):
        """Until a snapshot holds the changes up to ticket; StorageError when the write that held them failed."""
        with self.durable:
            while self.saved < ticket:
                if self.fail_seq > fails and self.fail_cover >= ticket:
                    raise nosnik.StorageError(f"zapis bazy na nośniku nie powiódł się: {self.save_error}")
                if not self.thread.is_alive():
                    raise RuntimeError("wątek bazy zatrzymany")
                if end is not None and time.monotonic() >= end:
                    raise Late(f"przyjęcie trwa dłużej niż {timeout * 1000:.0f} ms")
                self.durable.wait(1 if end is None else max(0, min(1, end - time.monotonic())))

    def action(self, account, op, detail=""):
        """Entry in the action log (dziennik działań), durable when this returns."""
        self.call(lambda store: self._log_action(account, op, detail))

    def envelope_alarm(self, limit=50):
        """Alarm of WICI-Link frames the stanowisko acknowledged without admitting (stanowisko-osp.md,
        „Przyjęcie koperty WICI-Link”), for the panel: {"active", "frames", "total", "newest", "rows",
        "overflow", "unauthenticated"}. rows and overflow are the durable set-aside of authenticated
        envelopes (until ZAMKNIJ ZDARZENIE); unauthenticated maps each reason to {"count", "at", "net_id",
        "sender"} counted in memory since the start (sender only as claimed). active while any of them
        is non-empty: such a sender got a HACK, so nothing but this alarm tells the duty officer."""
        def read(store):
            data = envelope_rejections(store.db, limit)
            data["unauthenticated"] = {reason: dict(entry) for reason, entry in self.unauthenticated.items()}
            return data
        data = self.call(read)
        data["active"] = data["total"] > 0 or bool(data["unauthenticated"])
        return data

    def deliver(self, source, content, bearer=None):
        """A REQUEST or TEST with a checked signature from source (16 B "lxmf.delivery" hash)."""
        self.jobs.put(lambda: self._receive(source, content, bearer))

    def receive_envelope_frame(self, net_id, wire, bearer=None, timeout=None):
        """Authenticate a numbered WICI frame and durably admit it; "partial", "complete", "duplicate" or
        "proof" (a station's delivery proof that closed the intents it names).

        Runs on the database thread. NotAuthenticated: the envelope does not authenticate a known
        station (nothing stored, counted in memory). envelope_inbox.PermanentRejection (an authenticated
        part that can never be admitted: replay window, fragment conflict, SA1 content) is raised only
        after its bytes are durably set aside in env_rejected. Any other exception (inbox full,
        quarantine full, failed intake journal, Late after `timeout`) is transient. Durable here means in
        the intake journal (_journal_frame); the snapshot follows later.
        """
        from . import envelope_inbox

        queued = time.monotonic()

        def admit(store):
            started = time.monotonic()
            try:
                outcome = self._admit_frame(net_id, wire, bearer, self.clock())
            except NotAuthenticated as exc:
                outcome = f"bez uwierzytelnienia ({exc.reason})"
                raise
            except envelope_inbox.PermanentRejection as exc:
                outcome = f"odłożona ({exc})"
                raise
            except Exception as exc:
                outcome = f"bez przyjęcia ({exc!r})"
                raise
            finally:
                self.log(f"stanowisko: koperta WICI {outcome}: kolejka {(started - queued) * 1000:.1f} ms, "
                         f"przyjęcie {(time.monotonic() - started) * 1000:.1f} ms")
            return outcome
        return self.call(admit, timeout, durable=False)

    def _admit_frame(self, net_id, wire, bearer, at):
        """One WICI-Link frame received at `at`, live or again from the intake journal (_replay)."""
        from . import envelope_inbox

        self.intake = ({"kind": "wici", "at": at, "net": net_id, "bearer": bearer, "wire": bytes(wire).hex()},
                       self.store.db.total_changes)
        try:
            return self._receive_envelope_frame(net_id, wire, bearer, at)
        except NotAuthenticated as exc:
            self._count_unauthenticated(net_id, wire, exc.reason, at)
            raise
        except envelope_inbox.PermanentRejection as exc:
            self._set_aside(net_id, wire, str(exc), at)
            raise
        finally:
            self.intake = None

    def admit_wici_frame(self, net_id, wire, timeout):
        """WiciStos callback: return once the root may send HACK, raise otherwise (Late after timeout).

        The HACK means "settled here", not "admitted": a frame set aside as never admissible is
        acknowledged like a relay acknowledges (the bytes are durable and the alarm is up), and a frame
        whose envelope is not authenticated is acknowledged after counting it ("unauthenticated"); a
        hop retry would change neither."""
        from . import envelope_inbox

        try:
            return self.receive_envelope_frame(net_id, wire, bearer="wici", timeout=timeout)
        except envelope_inbox.PermanentRejection:
            return "rejected"
        except NotAuthenticated:
            return "unauthenticated"

    def _count_unauthenticated(self, net_id, wire, reason, at):
        """Count a frame without an authenticated envelope for the alarm; in memory only, nothing on the medium."""
        raw = bytes(wire)
        entry = self.unauthenticated.setdefault(reason, {"count": 0})
        entry.update(count=entry["count"] + 1, at=at, net_id=net_id,
                     sender=int.from_bytes(raw[1:3], "big") if len(raw) >= 3 else None)

    def _set_aside(self, net_id, wire, reason, now):
        """Keep an authenticated, never admissible frame for the duty officer before its HACK; StorageError when it
        is not durable (the frame goes to the intake journal, as every admitted one).

        A repeat of stored bytes only counts, and so does a frame over the sender's cap or the table's cap (its
        bytes are not kept: they can never be admitted anyway, and the first evidence stays). The sender number
        is authenticated here, so a captured station uses at most its own share of the medium."""
        raw, db = bytes(wire), self.store.db
        sender = int.from_bytes(raw[1:3], "big")
        with db:
            if db.execute("UPDATE env_rejected SET count = count + 1, at=? WHERE net_id=? AND frame=?",
                          (now, net_id, raw)).rowcount:
                pass
            elif (db.execute("SELECT count(*) FROM env_rejected WHERE net_id=? AND sender=?",
                             (net_id, sender)).fetchone()[0] >= REJECTED_PER_SENDER
                  or db.execute("SELECT count(*) FROM env_rejected").fetchone()[0] >= REJECTED_MAX):
                db.execute("INSERT INTO env_rejected_overflow VALUES(?,?,1,?) ON CONFLICT(net_id, sender) "
                           "DO UPDATE SET count = count + 1, at = excluded.at", (net_id, sender, now))
            else:
                db.execute("INSERT INTO env_rejected(net_id, sender, reason, first_at, at, frame, count) "
                           "VALUES(?,?,?,?,?,?,1)", (net_id, sender, reason, now, now, raw))
        self.counts["envelope_rejected"] += 1
        self.rejected = rejected_summary(db)
        if not self._journal_frame():
            raise nosnik.StorageError(f"odłożona ramka WICI nie jest jeszcze na nośniku: {self.journal_error}")

    def send_wici(self, bearer, dest, content):
        """Called by Wysylka on the DB thread: reserve the nonce durably, seal and queue for KISS TX.

        None when WICI-Link cannot carry this reply now (offline, station without a number, sending blocked
        after a recovery, uncertain counters), so bearers.Bearers may try Reticulum."""
        from .. import envelope
        from . import wici_link

        link = bearer.status(self.clock())
        if self.recovery or not link["online"] or not link["room"]:
            return None   # bez miejsca w drodze nie zamyka koperty: licznik zostaje na następną próbę
        # Zaufanie rozstrzyga tylko wysylka.SENDABLE: do stacji spoza listy wychodzi tu sam RECEIVED.
        row = self.store.db.execute("SELECT station FROM numery WHERE net_id=? AND source=?",
                                    (bearer.network, dest)).fetchone()
        if row is None:
            return None
        try:
            frames = self._seal_envelope_message(bearer.network, row[0], content, wici_link.MAX_PAYLOAD)
        except envelope.EnvelopeError as exc:
            self.log(f"stanowisko: koperta WICI do {dest.hex()} nie wyszła: {exc}")
            return None
        return bearer.send_frames(frames)

    def _active_identity(self, net_id):
        """(private key, card entry) of the receiver identity bound to net_id; EnvelopeError otherwise.

        Read once per unlocked session, at first use, so the HACK path decrypts nothing: the identity and
        card change only through nowa-tozsamosc, aktywuj-tozsamosc, aktywuj-zapasowa and odtworz, which
        run while the application is stopped (__main__.py)."""
        from .. import envelope

        if self.identity_cache is None:
            card = self.medium.card(self.key)
            private = self.medium.identity(self.key)
            active = nosnik.card_entry(card, private) if card and card.get("v") == 2 else None
            self.identity_cache = (private, active)
        private, active = self.identity_cache
        if active is None or active.get("net_id") != net_id:
            raise envelope.EnvelopeError("receiver identity is not bound to this network")
        return private, active

    def _seal_envelope_message(self, net_id, station_id, content, max_payload):
        from .. import envelope
        from . import envelope_sender

        if self.recovery:
            raise envelope.EnvelopeError("recovery mode cannot send WICI envelopes")
        wzorzec.decode_message(content)  # refuse malformed SA1 before consuming a nonce
        private, active = self._active_identity(net_id)
        row = self.store.db.execute("SELECT public_key FROM numery WHERE net_id=? AND station=?",
                                    (net_id, station_id)).fetchone()
        if row is None or len(row[0]) != 64:
            raise envelope.EnvelopeError("unknown numbered station")
        if not hasattr(self, "envelope_sender"):
            self.envelope_sender = envelope_sender.Sender(self.store.db, self._save_now)
        frames = self.envelope_sender.seal(private[:32], row[0][:32], net_id, active["id"], station_id,
                                           content, max_payload)
        # Without this row a later proof is ignored and the intent is only resent: no loss.
        with self.store.db:
            self.store.db.execute(
                "INSERT OR REPLACE INTO wici_sent VALUES(?,?,?,?,?,?,?)",
                (net_id, active["id"], station_id, self._send_key_id(private, row[0], net_id, active["id"], station_id),
                 int.from_bytes(frames[0][5:9], "big"), hashlib.sha256(content).digest(), self.clock()))
        return frames

    @staticmethod
    def _send_key_id(private, station_key, net_id, receiver, station):
        """Fingerprint of the receiver -> station envelope key, as in envelope_sender (env_send.key_id)."""
        from .. import envelope

        key = envelope.derive_key(private[:32], station_key[:32], net_id, receiver, station, own_id=receiver)
        return hashlib.sha256(key).digest()

    def _receive_envelope_frame(self, net_id, wire, bearer, at):
        from .. import envelope
        from . import envelope_inbox

        # The link MAC passed, but the network key does not name the sender: only the envelope MAC does.
        try:
            private, active = self._active_identity(net_id)
        except envelope.EnvelopeError as exc:
            raise NotAuthenticated("receiver identity not bound to this network") from exc
        raw = bytes(wire)
        if len(raw) < envelope.OVERHEAD or len(raw) > envelope.MAX_FRAME:
            raise NotAuthenticated("invalid envelope length")
        sender, recipient = int.from_bytes(raw[1:3], "big"), int.from_bytes(raw[3:5], "big")
        if recipient != active.get("id"):
            raise NotAuthenticated("wrong receiver number")
        station = self.store.db.execute("SELECT source, public_key FROM numery WHERE net_id=? AND station=?",
                                        (net_id, sender)).fetchone()
        if station is None or len(station[1]) != 64:
            raise NotAuthenticated("unknown station number")
        source, station_key = station
        try:
            key = envelope.derive_key(private[:32], station_key[:32], net_id, sender, recipient, own_id=recipient)
            part = envelope.open_part(key, raw, (envelope.TYPE_SA1, envelope.TYPE_PROOF))
        except envelope.EnvelopeError as exc:
            raise NotAuthenticated("envelope authentication failed") from exc
        trusted = self.store.db.execute("SELECT 1 FROM trusted WHERE source=?", (source,)).fetchone() is not None
        if not hasattr(self, "envelope_inboxes"):
            self.envelope_inboxes = {}
        inbox = self.envelope_inboxes.get(net_id)
        if inbox is None:
            inbox = envelope_inbox.Inbox(self.store.db, net_id, self._journal_frame)
            self.envelope_inboxes[net_id] = inbox
        def accept(content):
            try:
                value = wzorzec.decode_message(content)
                self.store.db.execute("UPDATE removed SET messages = messages + 1 WHERE source=?", (source,))
                self.store.receive_in_transaction(source, content, True)
            except wzorzec.QuarantineFull:
                raise   # miejsce może się zwolnić: bez HACK, stacja ponowi
            except ValueError as exc:   # SA1 nie do przyjęcia: treść, typ albo konflikt klucza odbioru
                raise envelope_inbox.PermanentRejection(f"SA1: {exc}") from exc
            self.store.db.execute(
                "INSERT OR IGNORE INTO received_at SELECT source, id, revision, ? FROM received "
                "WHERE source=? AND id=? AND revision=?", (at, source, value[2], value[3]))
            self.wysylka.accepted(self.store.db, source, value[2], value[3])

        def fresh():
            # Fresh parts and proofs only: a replayed frame must not move the reply route.
            if bearer is not None and trusted:
                self.store.db.execute("INSERT OR REPLACE INTO bearer_route VALUES(?,?)", (source, bearer))
                self.last_bearer[source] = bearer
            self.wysylka.contact(self.store.db, source)

        def close(counters):
            sent = (net_id, recipient, sender, self._send_key_id(private, station_key, net_id, recipient, sender))
            marks = ",".join("?" * len(counters))
            where = f"net_id=? AND receiver=? AND station=? AND key_id=? AND counter IN ({marks})"
            hashes = {bytes(row[0]) for row in self.store.db.execute(
                f"SELECT payload_hash FROM wici_sent WHERE {where}", (*sent, *counters))}
            self.wysylka.proved(self.store.db, source, hashes)

        # The KISS caller must be able to answer HACK inside 200 ms. The normal
        # one-second tick sends RECEIVED once the change is durable, without
        # putting LXMF path discovery or copy work on the hop-ACK path.
        if part.message_type == envelope.TYPE_PROOF:
            return inbox.receive_proof(part, key, int(at), close, fresh)
        return inbox.receive(part, key, int(at), accept, fresh)

    def _receive(self, source, content, bearer=None, at=None):
        at = self.clock() if at is None else at
        fresh = False
        record = {"kind": "lxmf", "at": at, "source": bytes(source).hex(), "content": bytes(content).hex(),
                  "bearer": bearer}

        def before_commit():
            # W tej samej transakcji co zgłoszenie i RECEIVED; nowa rewizja dostaje czas pierwszego odbioru.
            # Tylko nowa rewizja przenosi trasę odpowiedzi: powtórzenie może być odtworzonym pakietem.
            nonlocal fresh
            value = wzorzec.decode_message(content)
            fresh = self.store.db.execute(
                "INSERT OR IGNORE INTO received_at SELECT source, id, revision, ? FROM received "
                "WHERE source=? AND id=? AND revision=?", (at, source, value[2], value[3])).rowcount == 1
            self.wysylka.accepted(self.store.db, source, value[2], value[3])
            if bearer is not None and fresh:
                self.store.db.execute("INSERT OR REPLACE INTO bearer_route VALUES(?,?)", (source, bearer))

        known = self.store.db.execute("SELECT count(*) FROM received WHERE source=?", (source,)).fetchone()[0]
        before = self.store.db.total_changes
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
        self.intake = (record, before)
        try:
            self._journal_frame()   # bez dziennika RECEIVED czeka na migawkę (tick)
        finally:
            self.intake = None
        if ack is None:
            self.counts["quarantined"] += 1
            return
        if bearer is not None and fresh:
            self.last_bearer[source] = bearer
        after = self.store.db.execute("SELECT count(*) FROM received WHERE source=?", (source,)).fetchone()[0]
        self.counts["received" if after > known else "duplicate"] += 1
        if not self.replaying:
            self.tick()   # RECEIVED od razu po COMMIT, jeśli jest miejsce w drodze

    def stop(self, save=True):
        """End the database thread; save=False (ZNISZCZ DANE) skips the last snapshot."""
        self.discard = self.discard or not save
        self.stopped = True
        self.jobs.put(None)
        self.thread.join(10)
