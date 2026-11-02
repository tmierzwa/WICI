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
-- silently be assigned to a different key on the same medium.
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
REJECTED_MAX = 256         # wierszy env_rejected (po najwyżej 255 B ramki)
REJECTED_PER_SENDER = 16   # wierszy env_rejected na numer nadawcy: przejęta stacja nie zużywa nośnika


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
        except Exception as e:   # noqa: BLE001 - błąd otwarcia bazy wraca do wątku, który tworzy Przyjecie
            if hasattr(self, "store"):
                self.store.close()
            self.error = e
            self.ready.set()
            return
        self.saved = -1 if body is None else self.store.db.total_changes   # nowy nośnik: pierwsza migawka od razu
        if self.copies is not None:
            self.last_copy_at = self.copies.newest(self.key)
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
        if not self.discard:
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
        a copy on the computer disk and the announce when they are due. Nothing in the recovery mode."""
        self.rejected = rejected_summary(self.store.db)   # także po ZAMKNIJ ZDARZENIE (zamkniecie.purge)
        if not self._save() or self.recovery:
            return   # w trybie odzyskania także bez kopii: trzy dobre kopie zostają
        if self.copies is not None and self.clock() >= self.next_copy:
            self._copy()   # przed wysyłką: po odzyskaniu nowa kopia z nowym P wychodzi pierwsza
        changes_before = self.store.db.total_changes
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
        """Copy on the computer disk; a failure is retried after a minute and logged once, without an alarm."""
        now = self.clock()
        try:
            self.copies.write(self.medium, self.key, kopie.with_marker(self.store.db, now), now,
                              kopie.frozen_before(self.store.db))
        except SAVE_ERRORS as e:
            self.next_copy = now + kopie.RETRY_S
            if not self.copy_failed:
                self.copy_failed = True
                self._log_action("", "kopia_nieudana", f"{type(e).__name__}: {e}")
            return
        self.next_copy, self.last_copy_at = now + kopie.INTERVAL_S, now
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
        self._save()

    def call(self, fn, timeout=None):
        """Run fn(store) in the database thread and return its result (or raise its exception) once the
        change is on the medium. StorageError after the change means "not yet durable", not "rejected":
        the change stays in the database and the next snapshot that succeeds writes it. With timeout
        (seconds) Late is raised when the job has not finished by then; the job still completes."""
        done, result = threading.Event(), {}

        def job():
            try:
                result["value"] = fn(self.store)
                if not self._save():
                    raise nosnik.StorageError(f"zapis bazy na nośniku nie powiódł się: {self.save_error}")
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
        return result["value"]

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
        """Authenticate a numbered WICI frame and durably admit it; "partial", "complete" or "duplicate".

        Runs on the database thread. NotAuthenticated: the envelope does not authenticate a known
        station (nothing stored, counted in memory). envelope_inbox.PermanentRejection (an authenticated
        part that can never be admitted: replay window, fragment conflict, SA1 content) is raised only
        after its bytes are durably set aside in env_rejected. Any other exception (inbox full,
        quarantine full, failed snapshot, Late after `timeout`) is transient.
        """
        from . import envelope_inbox

        queued = time.monotonic()

        def admit(store):
            started = time.monotonic()
            try:
                outcome = self._receive_envelope_frame(net_id, wire, bearer)
            except NotAuthenticated as exc:
                outcome = f"bez uwierzytelnienia ({exc.reason})"
                self._count_unauthenticated(net_id, wire, exc.reason)
                raise
            except envelope_inbox.PermanentRejection as exc:
                outcome = f"odłożona ({exc})"
                try:
                    self._set_aside(net_id, wire, str(exc))
                except Exception as error:
                    outcome = f"bez przyjęcia ({error!r})"
                    raise
                raise
            except Exception as exc:
                outcome = f"bez przyjęcia ({exc!r})"
                raise
            finally:
                self.log(f"stanowisko: koperta WICI {outcome}: kolejka {(started - queued) * 1000:.1f} ms, "
                         f"przyjęcie {(time.monotonic() - started) * 1000:.1f} ms")
            return outcome
        return self.call(admit, timeout)

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

    def _count_unauthenticated(self, net_id, wire, reason):
        """Count a frame without an authenticated envelope for the alarm; in memory only, nothing on the medium."""
        raw = bytes(wire)
        entry = self.unauthenticated.setdefault(reason, {"count": 0})
        entry.update(count=entry["count"] + 1, at=self.clock(), net_id=net_id,
                     sender=int.from_bytes(raw[1:3], "big") if len(raw) >= 3 else None)

    def _set_aside(self, net_id, wire, reason):
        """Keep an authenticated, never admissible frame for the duty officer before its HACK; StorageError when it
        is not durable.

        A new frame is snapshotted at once. A repeat of stored bytes only counts, and so does a frame over the
        sender's cap or the table's cap (its bytes are not kept: they can never be admitted anyway, and the first
        evidence stays); those counts reach the medium with the next regular snapshot, at most one per TICK_S.
        The sender number is authenticated here, so a captured station uses at most its own share of the medium."""
        raw, now, db = bytes(wire), self.clock(), self.store.db
        sender = int.from_bytes(raw[1:3], "big")
        durable = db.total_changes == self.saved   # wszystko, także wcześniej odłożone bajty, jest na nośniku
        with db:
            if db.execute("UPDATE env_rejected SET count = count + 1, at=? WHERE net_id=? AND frame=?",
                          (now, net_id, raw)).rowcount:
                new = False
            elif (db.execute("SELECT count(*) FROM env_rejected WHERE net_id=? AND sender=?",
                             (net_id, sender)).fetchone()[0] >= REJECTED_PER_SENDER
                  or db.execute("SELECT count(*) FROM env_rejected").fetchone()[0] >= REJECTED_MAX):
                db.execute("INSERT INTO env_rejected_overflow VALUES(?,?,1,?) ON CONFLICT(net_id, sender) "
                           "DO UPDATE SET count = count + 1, at = excluded.at", (net_id, sender, now))
                new, durable = False, True   # nic do zachowania poza licznikiem
            else:
                db.execute("INSERT INTO env_rejected(net_id, sender, reason, first_at, at, frame, count) "
                           "VALUES(?,?,?,?,?,?,1)", (net_id, sender, reason, now, now, raw))
                new = True
        self.counts["envelope_rejected"] += 1
        self.rejected = rejected_summary(db)
        if (new or not durable) and not self._save():
            raise nosnik.StorageError(f"odłożona ramka WICI nie jest jeszcze na nośniku: {self.save_error}")

    def send_wici(self, bearer, dest, content):
        """Called by Wysylka on the DB thread: reserve the nonce durably, seal and queue for KISS TX.

        None when WICI-Link cannot carry this reply now (offline, station without a number, sending blocked
        after a recovery, uncertain counters), so bearers.Bearers may try Reticulum."""
        from .. import envelope
        from . import wici_link

        link = bearer.status(self.clock())
        if self.recovery or not link["online"] or not link["room"]:
            return None   # bez miejsca w drodze nie zamyka koperty: licznik zostaje na następną próbę
        row = self.store.db.execute(
            "SELECT n.station FROM numery n JOIN trusted t ON t.source=n.source "
            "WHERE n.net_id=? AND n.source=?", (bearer.network, dest)).fetchone()
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
        row = self.store.db.execute("SELECT n.public_key FROM numery n JOIN trusted t ON t.source=n.source "
                                    "WHERE n.net_id=? AND n.station=?",
                                    (net_id, station_id)).fetchone()
        if row is None or len(row[0]) != 64:
            raise envelope.EnvelopeError("unknown numbered station")
        if not hasattr(self, "envelope_sender"):
            self.envelope_sender = envelope_sender.Sender(self.store.db, self._save)
        return self.envelope_sender.seal(private[:32], row[0][:32], net_id, active["id"], station_id,
                                         content, max_payload)

    def _receive_envelope_frame(self, net_id, wire, bearer=None):
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
            part = envelope.open_part(key, raw)
        except envelope.EnvelopeError as exc:
            raise NotAuthenticated("envelope authentication failed") from exc
        trusted = self.store.db.execute("SELECT 1 FROM trusted WHERE source=?", (source,)).fetchone() is not None
        if not hasattr(self, "envelope_inboxes"):
            self.envelope_inboxes = {}
        inbox = self.envelope_inboxes.get(net_id)
        if inbox is None:
            inbox = envelope_inbox.Inbox(self.store.db, net_id, self._save)
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
                "WHERE source=? AND id=? AND revision=?", (self.clock(), source, value[2], value[3]))
            self.wysylka.accepted(self.store.db, source, value[2], value[3])

        def remember_bearer():
            # Fresh parts only: a replayed frame must not move the reply route.
            if bearer is not None and trusted:
                self.store.db.execute("INSERT OR REPLACE INTO bearer_route VALUES(?,?)", (source, bearer))
                self.last_bearer[source] = bearer

        # The KISS caller must be able to answer HACK inside 200 ms. The normal
        # one-second tick sends RECEIVED after the durable snapshot, without
        # putting LXMF path discovery or copy work on the hop-ACK path.
        return inbox.receive(part, key, int(self.clock()), accept, remember_bearer)

    def _receive(self, source, content, bearer=None):
        at = self.clock()
        fresh = False

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
        if bearer is not None and fresh:
            self.last_bearer[source] = bearer
        after = self.store.db.execute("SELECT count(*) FROM received WHERE source=?", (source,)).fetchone()[0]
        self.counts["received" if after > known else "duplicate"] += 1
        self.tick()   # RECEIVED od razu po COMMIT, jeśli jest miejsce w drodze

    def stop(self, save=True):
        """End the database thread; save=False (ZNISZCZ DANE) skips the last snapshot."""
        self.discard = self.discard or not save
        self.stopped = True
        self.jobs.put(None)
        self.thread.join(10)
