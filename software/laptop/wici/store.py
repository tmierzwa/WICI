# SPDX-License-Identifier: MIT
"""Laptop state: where it lives on each system and the preparation journal in SQLite.

Windows and macOS keep the state on the laptop disk (docs/spec/oprogramowanie.md, "Pakiet USB"); Linux
started from the stick sets WICI_STATE to the ext4 partition of the stick. The journal is append-only:
what was sent to which station, when and with what result. It holds no SA1 content and no network
access code, only the SHA-256 of the configuration. It lives in the encrypted database
(database.Database), which a login opens (session.Session).
"""

import datetime
import os
import sys
from pathlib import Path


def state_dir():
    env = os.environ.get("WICI_STATE")
    if env:
        path = Path(env)
    elif sys.platform == "win32":
        path = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "WICI"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "WICI"
    else:
        path = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "wici"
    path.mkdir(parents=True, exist_ok=True)
    return path


SCHEMA = """
CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    station TEXT NOT NULL,
    lxmf TEXT NOT NULL,
    op TEXT NOT NULL,
    ok INTEGER NOT NULL,
    detail TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS journal_append_only BEFORE UPDATE ON journal
BEGIN SELECT RAISE(ABORT, 'journal is append-only'); END;
CREATE TRIGGER IF NOT EXISTS journal_no_delete BEFORE DELETE ON journal
BEGIN SELECT RAISE(ABORT, 'journal is append-only'); END;
"""


class Journal:
    def __init__(self, db):
        """db: database.Database with SCHEMA applied."""
        self.db = db

    def add(self, station, lxmf, op, ok, detail=""):
        at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.db.write(lambda c: c.execute("INSERT INTO journal (at, station, lxmf, op, ok, detail) VALUES (?,?,?,?,?,?)",
                                          (at, station or "", lxmf or "", op, 1 if ok else 0, detail)))

    def recent(self, limit=50):
        rows = self.db.read(lambda c: c.execute("SELECT at, station, lxmf, op, ok, detail FROM journal "
                                                "ORDER BY id DESC LIMIT ?", (limit,)).fetchall())
        return [dict(zip(("at", "station", "lxmf", "op", "ok", "detail"), r)) for r in rows]

    def close(self):
        self.db.close()
