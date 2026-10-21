# SPDX-License-Identifier: MIT
"""The kit on the USB stick and the database opened by a login (docs/spec/oprogramowanie.md).

A new kit stick has no accounts: the panel creates them during preparation (gospodarz and deputies)
together with the recovery password and shows every password once, numbered for its envelope. A
stick with accounts asks for a login; the database opens only then, because the account password
unwraps its key. Station operations write to the journal in that database, so they need a login too.
"""

import hmac
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


def _new_accounts(deputies):
    """Accounts gospodarz and zastepca-1..n with fresh envelope passwords, and a recovery password."""
    if not 0 <= deputies <= 5:
        raise ValueError("zastępców: od 0 do 5")
    accounts = [HOST] + [f"zastepca-{i}" for i in range(1, deputies + 1)]
    return {a: passwords.generate() for a in accounts}, passwords.recovery()


class Session:
    def __init__(self, usb, state, iterations=database.ITERATIONS, on_change=None):
        """usb: root of the kit stick; state: the laptop state directory (store.state_dir())."""
        self.usb, self.state, self.iterations = Path(usb), Path(state), iterations
        self.kit = database.Kit(self.usb / "keys")
        # Migawki każdego zestawu w osobnym katalogu baza/<8 znaków z klucza danych>: inny zestaw na tym samym
        # laptopie nie nadpisuje cudzych. baza/kopia-* bez podkatalogu to układ sprzed tego podziału.
        self.copy_dir, self.base_dir = self.usb / "kopia", self.state / "baza"
        self.on_change = on_change or (lambda: None)
        self.lock = threading.RLock()
        self.db = self.journal = self.user = None
        self.accounts = []                          # lista kont z chwili logowania: pamięć może zostać wyjęta
        self.pending = None                         # (konto, klucz danych, konflikt) do wyboru kopii
        self.destroyed = False                      # po ZNISZCZ DANE: do ponownego uruchomienia nic się nie otwiera
        self.destroyed_usb = None                   # po ZNISZCZ DANE: czy pamięć zestawu była podłączona

    # ---- stan dla panelu ----------------------------------------------------------------------

    def describe(self):
        with self.lock:
            accounts = self.accounts
            if self.destroyed:
                kit = "destroyed"
            elif self.db:
                kit = "open"
            elif not self.usb.is_dir():
                kit = "missing"
            else:
                try:
                    accounts, kit = self.kit.names(), "ready"
                except database.StorageError:
                    # uszkodzony plik kont albo kopia bez niego: dane są, otwiera je hasło odtworzenia;
                    # sam klucz zestawu bez kopii (przerwane tworzenie kont) to dalej nowy zestaw
                    kit = "broken" if self.kit.exists() or database.has_copies(self.copy_dir) else "new"
            accounts = [{"id": a, "label": label(a)} for a in (accounts if kit in ("ready", "open") else [])]
            conflict = None
            if self.pending:
                c = self.pending[2]
                conflict = {side: {"gen": copy.gen, "at": copy.at} for side, copy in (("disk", c.disk), ("usb", c.usb))}
            return {"kit": kit, "user": self.user, "user_label": label(self.user) if self.user else None,
                    "accounts": accounts, "conflict": conflict, "db": self.db.status() if self.db else None,
                    "usb": str(self.usb), "destroyed_usb": self.destroyed_usb}

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
        with self.lock:
            self._free()
            chosen, recovery = _new_accounts(deputies)
            _, key = database.Kit.create(self.kit.dir, chosen, recovery, self.iterations)
            self._open(HOST, key)
            self.journal.add("", "", "kit_create", True, f"konta {len(chosen)}")
            return {"envelopes": self._envelopes(chosen, recovery)}

    def login(self, account, password):
        with self.lock:
            self._free()
            key = self.kit.unlock(account, password)
            self._open(account, key)

    def recover(self, password, deputies=2):
        """Recovery password: the database opens without the account file, which is written anew."""
        with self.lock:
            self._free()
            chosen, recovery = _new_accounts(deputies)    # przed PBKDF2: zła liczba nie zużywa próby
            if self.kit.readable():
                raise database.StorageError("plik kont jest cały: zaloguj się hasłem konta")
            try:
                laptop = sorted(d for d in self.base_dir.iterdir() if d.is_dir())
            except OSError:
                laptop = []
            dirs = [self.copy_dir, self.base_dir] + laptop
            key = self.kit.throttled(lambda: database.key_from_recovery(dirs, password))
            database.Kit.create(self.kit.dir, chosen, recovery, self.iterations, data_key=key)
            self._open(HOST, key)
            self.journal.add("", "", "kit_recover", True, f"konta {len(chosen)}")
            return {"envelopes": self._envelopes(chosen, recovery)}

    def choose(self, prefer):
        with self.lock:
            self._free()
            if not self.pending or prefer not in ("disk", "usb"):
                raise database.StorageError("nie ma kopii do wyboru")
            account, key, _ = self.pending
            self._open(account, key, prefer)
            self.journal.add("", "", "copy_choose", True, prefer)

    def _open(self, account, key, prefer=None):
        disk_dir = self.base_dir / hmac.digest(key, b"wici baza", "sha256")[:4].hex()
        for f in self._legacy(key):                  # układ sprzed podkatalogów: kopie tego zestawu przechodzą
            if not (disk_dir / f.name).exists():
                disk_dir.mkdir(parents=True, exist_ok=True)
                os.replace(f, disk_dir / f.name)
        fingerprint = database.kit_id(self.kit.dir)
        if fingerprint is None:                      # pamięć wyjęta tuż po odczycie kont: bez odcisku nie ma ochrony
            raise database.StorageError(database.NO_USB + ": włóż ją i zaloguj się ponownie")
        try:
            db = database.Database(key, disk_dir, self.copy_dir, self.kit.recovery(), store.SCHEMA, prefer,
                                   on_change=self.on_change, kit_id=fingerprint)
        except database.Conflict as c:
            self.pending = (account, key, c)
            raise
        self.pending = None
        self.db, self.journal, self.user = db, store.Journal(db), account
        self.accounts = self.kit.names()
        if prefer is None:
            self.journal.add("", "", "login", True, account)

    def _legacy(self, key):
        """baza/kopia-* without a kit folder that this data key opens."""
        files = (self.base_dir / n for n in database.NAMES)
        return [f for f in files if f.is_file() and database._read(f, key, "disk")]

    def _our_stick(self):
        """StorageError unless the stick at the path is the kit of the open database."""
        found = database.kit_id(self.kit.dir)
        if found is None:
            raise database.StorageError(database.NO_USB + ": włóż ją, bez niej dane zostałyby tylko na tym laptopie")
        if found != self.db.kit_fp:
            raise database.StorageError(database.WRONG_USB)

    def _envelopes(self, chosen, recovery):
        out = [{"no": i, "account": a, "label": label(a), "password": pw} for i, (a, pw) in enumerate(chosen.items(), 1)]
        out.append({"no": len(out) + 1, "account": "odtworzenie", "label": "Hasło odtworzenia", "password": recovery})
        return out

    def adopt(self, usb):
        """Second START from the kit stick under another path (drive letter, mount point): the panel follows it.

        Only while the old path holds no kit (gone, or another drive took its letter); with an open database only
        when the new path holds the same kit (kit_id) with a copy this session continues
        (database.Database.move_usb). Otherwise nothing changes and the panel keeps warning."""
        usb = Path(usb)
        with self.lock:
            if self.destroyed or usb == self.usb or not usb.is_dir():
                return False
            if self.db:
                if database.kit_id(self.kit.dir) == self.db.kit_fp or not self.db.move_usb(usb / "kopia"):
                    return False                 # stara ścieżka ma nadal ten zestaw albo nowa nie jest nim
            elif self.kit.exists():
                return False
            failures = self.kit.failures             # limit prób logowania nie zeruje się przez ponowny START
            self.usb, self.kit, self.copy_dir, self.pending = usb, database.Kit(usb / "keys"), usb / "kopia", None
            self.kit.failures = failures
            if self.journal:
                self.journal.add("", "", "usb_moved", True, str(usb))
        self.on_change()
        return True

    # ---- po zalogowaniu -----------------------------------------------------------------------

    def _need(self):
        if not self.db:
            raise NotLoggedIn()

    def _free(self):
        if self.destroyed:
            raise database.StorageError("dane zestawu zniszczono: aplikację można zamknąć")
        if self.db:
            raise database.StorageError("ktoś jest już zalogowany: najpierw wyloguj")

    def new_password(self, account):
        """New password after an envelope was opened; shown once."""
        with self.lock:
            self._need()
            self._our_stick()                        # opakowanie cudzym kluczem zestawu zepsułoby jego konto
            pw = passwords.generate()
            self.kit.set_password(account, self.db.key, pw, self.iterations)
            self.accounts = self.kit.names()
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
            self._our_stick()                        # także gdy literę dysku zajęła inna pamięć
            self.journal.add("", "", "hand_back", True, self.user)
            legacy, disk = self._legacy(self.db.key), self.db.disk_dir
            self.db.hand_back()
            self.db = self.journal = self.user = None
            for f in legacy:
                f.unlink(missing_ok=True)
            _rmdir(disk)
            (self.state / "dziennik.sqlite").unlink(missing_ok=True)   # jawny dziennik z etapu 1, jeśli został

    def flush(self):
        """Every change of the open database on the disk and the kit stick (e.g. before ZAMKNIJ ZDARZENIE).

        Nothing without a login; StorageError at once without the kit stick, else as database.Database.flush."""
        with self.lock:
            if not self.db:
                return
            self._our_stick()
            db = self.db
        db.flush()                                   # bez blokady sesji: panel odświeża stan w trakcie

    def destroy(self):
        """ZNISZCZ DANE on the laptop: the key leaves memory, the snapshots leave the disk, the copies and
        the account files leave the stick (database.Database.destroy). Returns whether the stick was there."""
        with self.lock:
            self._need()
            db, usb = self.db, database.kit_id(self.kit.dir) == self.db.kit_fp
            self.db = self.journal = self.user = self.pending = None
            self.accounts, self.destroyed, self.destroyed_usb = [], True, usb
            failed = []
            legacy = self._legacy(db.key)
            try:
                db.destroy(self.kit.dir)
            except database.StorageError as e:
                failed.append(str(e))
            for f in legacy:
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    failed.append(f"nie udało się usunąć: {f.name}")
            _rmdir(db.disk_dir)
            try:
                (self.state / "dziennik.sqlite").unlink(missing_ok=True)   # jawny dziennik z etapu 1
            except OSError:
                failed.append("nie udało się usunąć: dziennik.sqlite")
        self.on_change()
        if failed:
            raise database.StorageError("; ".join(failed))
        return {"usb": usb}

    def close(self):
        with self.lock:
            if self.db:
                db, self.db, self.journal, self.user = self.db, None, None, None
                db.close()


def _rmdir(path):
    try:
        path.rmdir()                                 # pusty katalog zestawu na dysku laptopa
    except OSError:
        pass
