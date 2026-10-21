# SPDX-License-Identifier: MIT
"""The kit on the USB stick and the database opened by a login (docs/spec/oprogramowanie.md).

A new kit stick has no accounts: the panel creates them during preparation (gospodarz and deputies)
together with the recovery password and shows every password once, numbered for its envelope. A
stick with accounts asks for a login; the database opens only then, because the account password
unwraps its key. Station operations write to the journal in that database, so they need a login too.
"""

import os
import sys
import threading
from pathlib import Path

from . import database, passwords, store

HOST = "gospodarz"
LABELS = {HOST: "Gospodarz"}


def label(account):
    if account in LABELS:
        return LABELS[account]
    if account.startswith("zastepca-"):
        return "Zastępca " + account.split("-", 1)[1]
    return account


def usb_root():
    """Root of the kit stick: the one START runs from (app/wici.pyz), WICI_USB, or None (development)."""
    env = os.environ.get("WICI_USB")
    if env:
        return Path(env)
    app = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
    if app and app.name == "wici.pyz" and app.parent.name == "app":
        return app.resolve().parent.parent
    return None


class NotLoggedIn(Exception):
    pass


class Session:
    def __init__(self, usb, state, iterations=database.ITERATIONS, on_change=None):
        """usb: root of the kit stick; state: the laptop state directory (store.state_dir())."""
        self.usb, self.state, self.iterations = Path(usb), Path(state), iterations
        self.kit = database.Kit(self.usb / "keys")
        self.copy_dir, self.disk_dir = self.usb / "kopia", self.state / "baza"
        self.on_change = on_change or (lambda: None)
        self.lock = threading.RLock()
        self.db = self.journal = self.user = None
        self.pending = None                         # (konto, klucz danych, konflikt) do wyboru kopii

    # ---- stan dla panelu ----------------------------------------------------------------------

    def describe(self):
        with self.lock:
            if self.db:
                kit = "open"
            elif not self.kit.exists():
                kit = "new"
            else:
                kit = "ready" if self.kit.readable() else "broken"
            accounts = []
            if kit in ("ready", "open"):
                accounts = [{"id": a, "label": label(a)} for a in self.kit.names()]
            conflict = None
            if self.pending:
                c = self.pending[2]
                conflict = {side: {"gen": copy.gen, "at": copy.at} for side, copy in (("disk", c.disk), ("usb", c.usb))}
            return {"kit": kit, "user": self.user, "user_label": label(self.user) if self.user else None,
                    "accounts": accounts, "conflict": conflict, "db": self.db.status() if self.db else None,
                    "usb": str(self.usb)}

    def recent(self):
        with self.lock:
            return self.journal.recent() if self.journal else []

    def add(self, station, lxmf, op, ok, detail=""):
        """Journal entry of the logged-in session; station operations call it through Prep."""
        with self.lock:
            if not self.journal:
                raise NotLoggedIn()
            self.journal.add(station, lxmf, op, ok, detail)

    # ---- zestaw i logowanie -------------------------------------------------------------------

    def create(self, deputies):
        """New kit: accounts, recovery password and the envelopes to fill; logs the gospodarz in."""
        if not 0 <= deputies <= 5:
            raise ValueError("zastępców: od 0 do 5")
        with self.lock:
            accounts = [HOST] + [f"zastepca-{i}" for i in range(1, deputies + 1)]
            chosen = {a: passwords.generate() for a in accounts}
            recovery = passwords.recovery()
            _, key = database.Kit.create(self.kit.dir, chosen, recovery, self.iterations)
            self._open(HOST, key)
            self.journal.add("", "", "kit_create", True, f"konta {len(accounts)}")
            return {"envelopes": self._envelopes(chosen, recovery)}

    def login(self, account, password):
        with self.lock:
            key = self.kit.unlock(account, password)
            self._open(account, key)

    def recover(self, password, deputies=2):
        """Recovery password: the database opens without the account file, which is written anew."""
        with self.lock:
            if self.kit.readable():
                raise database.StorageError("plik kont jest cały: zaloguj się hasłem konta")
            key = database.key_from_recovery([self.copy_dir, self.disk_dir], password)
            if not 0 <= deputies <= 5:
                raise ValueError("zastępców: od 0 do 5")
            accounts = [HOST] + [f"zastepca-{i}" for i in range(1, deputies + 1)]
            chosen = {a: passwords.generate() for a in accounts}
            recovery = passwords.recovery()
            database.Kit.create(self.kit.dir, chosen, recovery, self.iterations, data_key=key)
            self._open(HOST, key)
            self.journal.add("", "", "kit_recover", True, f"konta {len(accounts)}")
            return {"envelopes": self._envelopes(chosen, recovery)}

    def choose(self, prefer):
        with self.lock:
            if not self.pending or prefer not in ("disk", "usb"):
                raise database.StorageError("nie ma kopii do wyboru")
            account, key, _ = self.pending
            self._open(account, key, prefer)
            self.journal.add("", "", "copy_choose", True, prefer)

    def _open(self, account, key, prefer=None):
        try:
            db = database.Database(key, self.disk_dir, self.copy_dir, self.kit.recovery(), store.SCHEMA, prefer,
                                   on_change=self.on_change)
        except database.Conflict as c:
            self.pending = (account, key, c)
            raise
        self.pending = None
        self.db, self.journal, self.user = db, store.Journal(db), account
        if prefer is None:
            self.journal.add("", "", "login", True, account)

    def _envelopes(self, chosen, recovery):
        out = [{"no": i, "account": a, "label": label(a), "password": pw} for i, (a, pw) in enumerate(chosen.items(), 1)]
        out.append({"no": len(out) + 1, "account": "odtworzenie", "label": "Hasło odtworzenia", "password": recovery})
        return out

    # ---- po zalogowaniu -----------------------------------------------------------------------

    def _need(self):
        if not self.db:
            raise NotLoggedIn()

    def new_password(self, account):
        """New password after an envelope was opened; shown once."""
        with self.lock:
            self._need()
            pw = passwords.generate()
            self.kit.set_password(account, self.db.key, pw, self.iterations)
            self.journal.add("", "", "password_new", True, account)
            return {"envelopes": [{"no": None, "account": account, "label": label(account), "password": pw}]}

    def logout(self):
        with self.lock:
            self._need()
            self.journal.add("", "", "logout", True, self.user)
            db, self.db, self.journal, self.user = self.db, None, None, None
            db.close()

    def hand_back(self):
        """'Oddaj laptop': last copy on the stick, then nothing of the kit stays on the laptop disk."""
        with self.lock:
            self._need()
            self.journal.add("", "", "hand_back", True, self.user)
            self.db.hand_back()
            self.db = self.journal = self.user = None
            (self.state / "dziennik.sqlite").unlink(missing_ok=True)   # jawny dziennik z etapu 1, jeśli został

    def close(self):
        with self.lock:
            if self.db:
                db, self.db, self.journal, self.user = self.db, None, None, None
                db.close()
