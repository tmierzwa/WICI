# SPDX-License-Identifier: MIT
"""Copies of the station database on the computer disk and on the second medium (stage S5).

docs/spec/stanowisko-osp.md, „Nośnik i szyfrowanie”: every 5 min the application writes a copy of the
database, the receiver identity and the account file to the internal disk of the station computer (full
disk encryption), checked with `PRAGMA integrity_check`, sealed with the same data key, which the station
password wraps; it keeps the three newest. A failed write is retried and goes to the action log, without
an alarm for the duty officer. At every shift handover a copy goes also to the second medium.

A copy carries the marker „kopia” in its own database (table `kopia`), never in the working database: a
database opened from a copy starts the recovery mode (stage S6). One copy is one file
kopia-<time>.wici: header (time, wrap of the station password) and a sealed JSON with the database,
the sealed identity and the account files, so the station password alone opens it (key_from_recovery).
"""

import base64
import contextlib
import json
import os
import sqlite3
import time
from pathlib import Path

from .. import database, syscrypto

INTERVAL_S, RETRY_S, KEEP = 300, 60, 3
PREFIX, SUFFIX = "kopia-", ".wici"
MARKER = "CREATE TABLE kopia (at REAL NOT NULL)"


def with_marker(db, at):
    """Body of a copy of db with the marker „kopia”, after an integrity check (SQLite backup API)."""
    with contextlib.closing(sqlite3.connect(":memory:")) as copy:
        db.backup(copy)
        with copy:
            copy.execute(MARKER)
            copy.execute("INSERT INTO kopia VALUES (?)", (at,))
        check = copy.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise database.StorageError(f"kopia bazy nie przeszła sprawdzenia integralności: {check}")
        return copy.serialize()


def _b64(data):
    return base64.b64encode(data).decode("ascii")


class Kopie:
    """Copies in one directory: the computer disk (state directory) or the second medium."""

    def __init__(self, directory):
        self.dir = Path(directory)

    def files(self):
        """Copy files, newest first (by the time in the name)."""
        try:
            return sorted((p for p in self.dir.iterdir() if p.name.startswith(PREFIX) and p.name.endswith(SUFFIX)),
                          key=lambda p: p.name, reverse=True)
        except FileNotFoundError:
            return []

    def write(self, medium, key, body, at):
        """A new copy from the database body with the marker, the identity and the account files; the
        oldest beyond three go. A write broken off leaves only a .tmp file and the previous copies."""
        payload = {"v": 1, "baza": _b64(body), "tozsamosc": _b64((medium.root / "tozsamosc").read_bytes()),
                   "konta": _b64((medium.kit.dir / database.ACCOUNTS).read_bytes()),
                   "zestaw": _b64((medium.kit.dir / database.KIT_KEY).read_bytes())}
        name = f"{PREFIX}{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(at))}{SUFFIX}"
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / (name + ".tmp")
        database._write_durable(tmp, self._seal(key, medium.kit.recovery(), at, json.dumps(payload).encode()))
        os.replace(tmp, self.dir / name)
        database._fsync_dir(self.dir)
        for old in self.files()[KEEP:]:
            old.unlink(missing_ok=True)
        return self.dir / name

    @staticmethod
    def _seal(key, recovery, at, data):
        header = json.dumps({"at": at, "recovery": recovery}).encode()
        head = database.MAGIC + len(header).to_bytes(4, "big") + header
        return head + syscrypto.seal(key, data, head)

    @staticmethod
    def read(path, key):
        """(time, payload) of a copy that opens with key; StorageError otherwise."""
        try:
            head, header, sealed = database._split(Path(path).read_bytes())
            payload = json.loads(syscrypto.open_(key, sealed, head))
            if payload.get("v") != 1:
                raise ValueError("nieznana wersja kopii")
            return header["at"], {k: base64.b64decode(v) for k, v in payload.items() if k != "v"}
        except (OSError, ValueError, KeyError, TypeError, syscrypto.CryptoError) as e:
            raise database.StorageError(f"kopia nieczytelna: {path.name}: {e}") from None

    @staticmethod
    def unlock(path, password):
        """Data key of a copy from the station password alone (its header carries the wrap)."""
        try:
            _, header, _ = database._split(Path(path).read_bytes())
        except (OSError, ValueError) as e:
            raise database.StorageError(f"kopia nieczytelna: {e}") from None
        key = database._unwrap(header.get("recovery") or {}, password, database.RECOVERY_AAD)
        if key is None:
            raise database.LoginError("Złe hasło stanowiska dla tej kopii.")
        return key

    def newest(self, key):
        """Time of the newest copy that opens, or None."""
        for path in self.files():
            try:
                return self.read(path, key)[0]
            except database.StorageError:
                continue
        return None

    def rewrap(self, key, recovery):
        """After a new station password: every copy written again with the new wrap in its header."""
        for path in self.files():
            at, payload = self.read(path, key)
            data = {"v": 1, **{k: _b64(v) for k, v in payload.items()}}
            tmp = path.with_name(path.name + ".tmp")
            database._write_durable(tmp, self._seal(key, recovery, at, json.dumps(data).encode()))
            os.replace(tmp, path)

    def remove(self):
        """Delete every copy (removal after the archive, ZNISZCZ DANE); names of files that stayed."""
        left = []
        for path in self.files() + list(self.dir.glob(PREFIX + "*.tmp")):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                left.append(path.name)
        return left


def disk_dir(state, medium):
    """Copies of this medium on the computer disk: a directory per medium, named by its kit key."""
    return Path(state) / "kopie" / (database.kit_id(medium.kit.dir) or "brak")[:16]
