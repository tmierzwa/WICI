# SPDX-License-Identifier: MIT
"""Reception of REQUEST and TEST at the receiving station (stage S2; O01-O03).

docs/spec/stanowisko-osp.md, „Przyjęcie” and „Zaufanie”: a trusted REQUEST or TEST is committed in one SQLite
transaction together with its RECEIVED (the reference OSPStore, journal_mode=DELETE, synchronous=FULL), and
RECEIVED goes out only after COMMIT. A repeated REQUEST gets the same RECEIVED; the same key with other
content is a conflict without overwriting. A station off the trusted list goes to quarantine without RECEIVED;
a removed station too, counted for the alarm „możliwe przejęcie stacji”. Reception time is the computer clock.

One worker thread owns the database: the stack calls deliver() from its own threads and does not wait for
fsync, and the panel (stage S7) runs its operations through call(). Messages arrive here only with a checked
signature (stos.Stos holds those from an unknown sender until its announce). Sending RECEIVED is a single
attempt for now; the intent queue with retries is stage S3 (the ack_outbox rows stay for it).
"""

import queue
import sqlite3
import sys
import threading
import time
from pathlib import Path

from . import wzorzec

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
"""


class Przyjecie:
    """Reception in its own thread. send(target, content) is the stack's send (stos.Stos.send)."""

    def __init__(self, path, send, clock=time.time, log=None):
        self.path, self.send, self.clock = path, send, clock
        self.log = log or (lambda line: print(line, file=sys.stderr, flush=True))
        self.jobs = queue.Queue()
        self.counts = {"received": 0, "duplicate": 0, "quarantined": 0, "rejected": 0, "quarantine_full": 0}
        self.ready = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, name="przyjecie", daemon=True)
        self.thread.start()
        self.ready.wait()
        if self.error:
            raise self.error

    def _run(self):
        try:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            self.store = wzorzec.OSPStore(self.path)
            self.store.db.executescript(SCHEMA)
        except Exception as e:   # noqa: BLE001 - błąd otwarcia bazy wraca do wątku, który tworzy Przyjecie
            self.error = e
            self.ready.set()
            return
        self.ready.set()
        while True:
            job = self.jobs.get()
            if job is None:
                break
            try:
                job()
            except Exception as e:   # noqa: BLE001 - wątek bazy działa dalej; stacja ponowi wiadomość
                self.log(f"stanowisko: błąd w wątku bazy: {e!r}")
        self.store.close()

    def call(self, fn):
        """Run fn(store) in the database thread and return its result (or raise its exception)."""
        done, result = threading.Event(), {}

        def job():
            try:
                result["value"] = fn(self.store)
            except BaseException as e:   # noqa: BLE001 - wyjątek wraca do wywołującego
                result["error"] = e
            done.set()
        self.jobs.put(job)
        done.wait()
        if "error" in result:
            raise result["error"]
        return result["value"]

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
        # Po COMMIT (receive zatwierdził transakcję): RECEIVED, także powtórnie dla powtórzonego REQUEST.
        if self.send(source, ack) is None:
            self.log(f"stanowisko: RECEIVED do {source.hex()} czeka na trasę")

    def stop(self):
        self.jobs.put(None)
        self.thread.join(10)
