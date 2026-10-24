# SPDX-License-Identifier: MIT
"""Laptop database: SQLite in process memory, sealed snapshots on the laptop disk and the kit USB stick.

docs/spec/oprogramowanie.md ("Szyfrowanie w spoczynku", "Pakiet USB"). The open database never reaches
the disk in plain form. After a change the disk writer serializes it, seals it with the data key
(syscrypto) and writes one of two files (kopia-a, kopia-b) with fsync. Changes that arrive meanwhile
go into the next snapshot, and every write waits only for the first snapshot that covers it. The USB
writer copies the newest sealed snapshot to the stick in the background.

Every snapshot carries its generation and the history of sessions (which application run continued
from which generation), both covered by the MAC. At start the copy that continues the other one wins,
so a laptop that comes back with an older copy does not overwrite a newer one; two copies that
continue neither each other are a conflict for the person at the panel.

The data key is random. keys/konta.json on the stick wraps it for every account with a key from
PBKDF2(password, keys/zestaw.key + salt), and once more with the recovery password alone. The recovery
wrap is also in every snapshot header, so a lost account file does not lose the data. A successful
unwrap is the password check; there is no separate login hash.
"""

import collections
import datetime
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import sys
import threading
import time
import unicodedata
from pathlib import Path

from . import syscrypto

ITERATIONS = 600_000
ITERATIONS_RANGE = (1_000, 10_000_000)  # z pliku: poza zakresem opakowanie nieczytelne (zawieszenie, przepełnienie)
MAGIC = b"WICI-KOPIA\n"
NAMES = ("kopia-a", "kopia-b")          # na zmianę: zapis nie nadpisuje najnowszej kopii
KIT_KEY, ACCOUNTS = "zestaw.key", "konta.json"
LOGIN_LIMIT, LOGIN_WINDOW = 5, 60.0      # nieudane próby na minutę
RETRY = 1.0                              # s między próbami po błędzie zapisu
WRONG_USB = "inna pamięć USB niż pamięć zestawu"
NO_USB = "brak pamięci USB zestawu"


class LoginError(Exception):
    pass


class StorageError(Exception):
    pass


class Conflict(Exception):
    """The disk and the stick hold copies that do not continue each other; open again with prefer=."""

    def __init__(self, disk, usb):
        super().__init__("kopia na dysku i kopia na pamięci USB rozeszły się")
        self.disk, self.usb = disk, usb


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_password(text):
    """Envelope passwords are words: letter case, Unicode form and spacing do not matter."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split()).encode("utf-8")


def _wrap_key(password, salt, iterations, pepper=b""):
    k = syscrypto.pbkdf2(normalize_password(password), pepper + salt, iterations)
    return hmac.digest(k, b"wici konto", "sha256")


def _slot(data_key, password, aad, iterations, pepper=b""):
    salt = os.urandom(16)
    key = _wrap_key(password, salt, iterations, pepper)
    return {"salt": salt.hex(), "iterations": iterations, "wrap": syscrypto.seal(key, data_key, aad).hex()}


def _unwrap(slot, password, aad, pepper=b""):
    try:
        iterations = slot["iterations"]
        if type(iterations) is not int or not ITERATIONS_RANGE[0] <= iterations <= ITERATIONS_RANGE[1]:
            return None
        key = _wrap_key(password, bytes.fromhex(slot["salt"]), iterations, pepper)
        return syscrypto.open_(key, bytes.fromhex(slot["wrap"]), aad)
    except (syscrypto.CryptoError, ValueError, KeyError, TypeError):
        return None


SLOT = (("salt", str), ("iterations", int), ("wrap", str))


def _account_aad(name):
    return b"wici konto\0" + name.encode("utf-8")


RECOVERY_AAD = b"wici odtworzenie"


def _fsync(fd):
    if sys.platform == "darwin":
        import fcntl
        try:
            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)   # macOS: samo fsync nie opróżnia pamięci podręcznej dysku
            return
        except OSError:
            pass
    os.fsync(fd)


def _fsync_dir(path):
    if sys.platform != "win32":                  # Windows: FlushFileBuffers obejmuje też wpis katalogu
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        except OSError:
            pass                                 # część systemów nie pozwala na fsync katalogu FAT32
        finally:
            os.close(fd)


def _write_durable(path, data):
    with open(path, "wb") as f:
        f.write(data)
        f.flush()
        _fsync(f.fileno())
    _fsync_dir(path.parent)


def kit_id(keys_dir):
    """Fingerprint of a kit stick: SHA-256 of keys/zestaw.key (written once by Kit.create); None without it."""
    try:
        return hashlib.sha256((Path(keys_dir) / KIT_KEY).read_bytes()).hexdigest()
    except OSError:
        return None


def has_copies(usb_dir):
    try:
        return any((Path(usb_dir) / n).exists() for n in NAMES)
    except OSError:
        return False


def _valid(doc):
    """Structure of konta.json: version 1, accounts {name: slot}, recovery slot; a slot has salt, iterations, wrap."""
    def slot(s):
        return isinstance(s, dict) and all(isinstance(s.get(f), t) for f, t in SLOT)
    if not isinstance(doc, dict) or not isinstance(doc.get("accounts"), dict):
        return False
    return (doc.get("version") == 1 and slot(doc.get("recovery"))
            and all(isinstance(n, str) and slot(s) for n, s in doc["accounts"].items()))


class Kit:
    """Accounts of a kit on its USB stick: keys/zestaw.key and keys/konta.json."""

    def __init__(self, keys_dir):
        self.dir = Path(keys_dir)
        self.failures = collections.deque()
        self.lock = threading.Lock()

    @classmethod
    def create(cls, keys_dir, passwords, recovery, iterations=ITERATIONS, data_key=None):
        """New kit: a random data key wrapped for every account (name -> password) and by the recovery password.

        With data_key (from the recovery password) the accounts are written anew for an existing database;
        then an unreadable account file is replaced."""
        kit = cls(keys_dir)
        if not kit.dir.parent.is_dir():
            raise StorageError("brak pamięci USB zestawu")
        kit.dir.mkdir(exist_ok=True)              # bez parents: wyjęta pamięć nie staje się katalogiem na dysku
        if (kit.dir / ACCOUNTS).exists() and (data_key is None or kit.readable()):
            raise StorageError("ta pamięć ma już konta zestawu")
        if data_key is None and has_copies(kit.dir.parent / "kopia"):
            # nowy klucz danych nadpisałby kopie, których nikt już nie otworzy: tylko hasło odtworzenia
            raise StorageError("ta pamięć ma kopię bazy zestawu: użyj hasła odtworzenia")
        pepper = None
        if data_key is not None:                   # odtworzenie: cały klucz zestawu zostaje, więc i jego kit_id
            try:
                pepper = (kit.dir / KIT_KEY).read_bytes()
            except OSError:
                pass
        if pepper is None or len(pepper) != 32:
            pepper = os.urandom(32)
            _write_durable(kit.dir / KIT_KEY, pepper)
        data_key = data_key or os.urandom(32)
        accounts = {name: _slot(data_key, pw, _account_aad(name), iterations, pepper) for name, pw in passwords.items()}
        kit._save({"version": 1, "accounts": accounts,
                   "recovery": _slot(data_key, recovery, RECOVERY_AAD, iterations)})
        return kit, data_key

    def _load(self):
        try:
            doc = json.loads((self.dir / ACCOUNTS).read_text(encoding="utf-8"))
            pepper = (self.dir / KIT_KEY).read_bytes()
        except FileNotFoundError:
            raise StorageError("brak plików kont zestawu na pamięci USB") from None
        except (OSError, ValueError) as e:
            raise StorageError(f"plik kont zestawu nieczytelny: {e}") from None
        if not _valid(doc) or len(pepper) != 32:
            raise StorageError("plik kont zestawu w nieznanym formacie")
        return doc, pepper

    def _save(self, doc):
        tmp = self.dir / (ACCOUNTS + ".tmp")
        _write_durable(tmp, json.dumps(doc, indent=1).encode("utf-8"))
        os.replace(tmp, self.dir / ACCOUNTS)
        _fsync_dir(self.dir)                     # sama zmiana nazwy też musi przetrwać zanik zasilania

    def exists(self):
        return (self.dir / ACCOUNTS).exists()

    def readable(self):
        try:
            self._load()
            return True
        except StorageError:
            return False

    def names(self):
        return list(self._load()[0]["accounts"])

    def recovery(self):
        return self._load()[0]["recovery"]

    def throttled(self, attempt):
        """Run a password attempt (account or recovery) under the limit of 5 failures a minute."""
        with self.lock:
            now = time.monotonic()
            while self.failures and now - self.failures[0] > LOGIN_WINDOW:
                self.failures.popleft()
            if len(self.failures) >= LOGIN_LIMIT:
                raise LoginError("Za dużo nieudanych prób. Poczekaj minutę.")
            try:
                return attempt()
            except LoginError:
                self.failures.append(now)
                raise

    def unlock(self, name, password):
        """Data key for a correct password; LoginError otherwise, at most 5 failures a minute."""
        def attempt():
            doc, pepper = self._load()
            slot = doc["accounts"].get(name)
            key = _unwrap(slot, password, _account_aad(name), pepper) if slot else None
            if key is None:
                raise LoginError("Zła nazwa konta albo hasło.")
            return key
        return self.throttled(attempt)

    def set_password(self, name, data_key, new, iterations=ITERATIONS):
        """New password for an account, by someone already logged in (after an envelope was opened)."""
        with self.lock:
            doc, pepper = self._load()
            if name not in doc["accounts"]:
                raise StorageError(f"nie ma konta {name}")
            doc["accounts"][name] = _slot(data_key, new, _account_aad(name), iterations, pepper)
            self._save(doc)


def _other(name):
    return NAMES[1] if name == NAMES[0] else NAMES[0]


class Copy:
    """One verified snapshot file."""

    def __init__(self, place, path, header, raw, body):
        self.place, self.path, self.raw, self.body = place, path, raw, body
        self.gen, self.at, self.recovery = int(header["gen"]), header["at"], header.get("recovery")
        self.history = [tuple(h) for h in header["history"]]


def _split(raw):
    if not raw.startswith(MAGIC):
        raise ValueError("nie kopia WICI")
    n = int.from_bytes(raw[len(MAGIC):len(MAGIC) + 4], "big")
    end = len(MAGIC) + 4 + n
    return raw[:end], json.loads(raw[len(MAGIC) + 4:end]), raw[end:]


def _read(path, data_key, place):
    try:
        raw = path.read_bytes()
        head, header, sealed = _split(raw)
        return Copy(place, path, header, raw, syscrypto.open_(data_key, sealed, head))
    except (OSError, ValueError, KeyError, TypeError, syscrypto.CryptoError):
        return None   # brak, uszkodzony, przerwany zapis albo inny klucz: decyduje drugi plik


def _continues(newer, older):
    """True when `newer` is `older` or was written later on top of it."""
    h, o = newer.history, older.history
    if h[:len(o)] != o:
        return False
    if len(h) == len(o):
        return newer.gen >= older.gen
    return h[len(o)][1] >= older.gen       # następna sesja zaczęła od pokolenia co najmniej tak nowego


def key_from_recovery(dirs, password):
    """Data key from the recovery password and the header of any copy, when the account file is lost."""
    tried = {}                                   # opakowanie -> klucz: PBKDF2 raz na opakowanie, nie raz na plik
    for d in dirs:
        for name in NAMES:
            try:
                _, header, _ = _split((Path(d) / name).read_bytes())
                slot = header.get("recovery") or {}
                seen = json.dumps(slot, sort_keys=True)
            except (OSError, ValueError, AttributeError, TypeError):
                continue
            if seen not in tried:
                tried[seen] = _unwrap(slot, password, RECOVERY_AAD)
            key = tried[seen]
            if key is not None and _read(Path(d) / name, key, "") is not None:
                return key
    raise LoginError("Złe hasło odtworzenia albo brak kopii.")


class Database:
    """The open database and its snapshot writers.

    write(fn) runs fn(conn) in one transaction and returns once a disk snapshot covers it, so a 201
    sent after it is durable. read(fn) runs fn(conn) under the same lock.

    kit_id (kit_id() of the kit stick at login): the stick is checked before every write and removal
    there, so a different stick under the same path gets nothing."""

    def __init__(self, data_key, disk_dir, usb_dir=None, recovery=None, schema="", prefer=None, on_change=None,
                 kit_id=None):
        self.key, self.kit_fp = data_key, kit_id
        self.on_change = on_change or (lambda: None)
        self.disk_dir = Path(disk_dir)
        self.usb_dir = Path(usb_dir) if usb_dir else None
        self.disk_dir.mkdir(parents=True, exist_ok=True)
        if self.usb_dir:
            try:
                self.usb_dir.mkdir(exist_ok=True)    # teraz, przy pamięci zestawu: później pod tą literą może być inna
            except OSError:
                pass                                 # wątek pamięci USB zgłosi błąd zapisu
        found = [c for d, place in ((self.disk_dir, "disk"), (self.usb_dir, "usb")) if d
                 for c in (_read(d / n, data_key, place) for n in NAMES) if c]
        disk = max((c for c in found if c.place == "disk"), key=lambda c: c.gen, default=None)
        usb = max((c for c in found if c.place == "usb"), key=lambda c: c.gen, default=None)
        # Plik z najnowszą kopią w danym miejscu; zapis idzie zawsze do drugiego, więc ona zostaje przy przerwaniu.
        self.disk_last, self.usb_last = (disk.path.name if disk else None), (usb.path.name if usb else None)
        base = self._choose(disk, usb, prefer)
        self.conn = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
        if base:
            self.conn.deserialize(base.body)
        self.recovery = recovery or (base.recovery if base else None)   # plik kont ma aktualne hasło odtworzenia
        # Pokolenia rosną ponad każdą znalezioną kopię, także odrzuconą w konflikcie, więc jej pliki nie wygrają później.
        self.gen = max((c.gen for c in found), default=0)
        self.history = (base.history if base else []) + [(secrets.token_hex(8), base.gen if base else 0)]
        self.lock = threading.Lock()                 # połączenie SQLite
        self.cond = threading.Condition()            # liczniki zapisu
        self.changes = self.disk_done = self.usb_done = 0
        self.disk_error = None                       # (zmiany objęte nieudaną próbą, komunikat)
        self.usb_error = None
        self.usb_at = usb.at if usb else None
        self.pending = None                          # najnowsza migawka dla pamięci USB: (zmiany, pokolenie, bajty)
        if self.usb_dir and base and (usb is None or not _continues(usb, base)):
            self.pending, self.usb_done = (0, base.gen, base.raw), -1   # pamięć nie ma jeszcze tej kopii
        self.stopping = self.destroying = False
        self.conn.executescript(schema)
        self.threads = [threading.Thread(target=self._disk_loop, daemon=True, name="wici-kopia-dysk")]
        if self.usb_dir:
            self.threads.append(threading.Thread(target=self._usb_loop, daemon=True, name="wici-kopia-usb"))
        for t in self.threads:
            t.start()

    def _choose(self, disk, usb, prefer):
        if not disk or not usb:
            return disk or usb
        if _continues(disk, usb):
            return disk
        if _continues(usb, disk):
            return usb
        if prefer not in ("disk", "usb"):
            raise Conflict(disk, usb)
        problem = self._stick(self.usb_dir)
        if problem:
            raise StorageError(problem)
        win, lose = (disk, usb) if prefer == "disk" else (usb, disk)
        # Odrzucona kopia zostaje na pamięci zestawu (dysk laptopa wraca do właściciela), zaszyfrowana jak była;
        # jej pliki znikają z miejsca, w którym leżały, żeby przy następnym starcie nie wywołały tego samego konfliktu.
        _write_durable(self.usb_dir / f"konflikt-{lose.place}-{lose.gen}", lose.raw)
        for name in NAMES:
            (self.disk_dir if lose.place == "disk" else self.usb_dir).joinpath(name).unlink(missing_ok=True)
        return win

    def _stick(self, usb_dir):
        """None when the stick at usb_dir is this kit's; otherwise why not (NO_USB, WRONG_USB)."""
        if self.kit_fp is None:
            return None
        found = kit_id(usb_dir.parent / "keys")
        return NO_USB if found is None else None if found == self.kit_fp else WRONG_USB

    def _ours(self, usb_dir):
        return self._stick(usb_dir) is None

    # ---- dostęp -------------------------------------------------------------------------------

    def read(self, fn):
        with self.lock:
            return fn(self.conn)

    def write(self, fn, timeout=30.0):
        """fn(conn) in one transaction; returns once a disk snapshot covers it.

        StorageError after COMMIT means "not yet durable", not "rejected": the change stays in the open
        database and the next snapshot that succeeds writes it."""
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                result = fn(self.conn)
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            try:
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            with self.cond:
                self.changes += 1
                mine = self.changes
                self.cond.notify_all()
        with self.cond:
            deadline = time.monotonic() + timeout
            while self.disk_done < mine:
                if self.destroying:
                    raise StorageError("dane zniszczono")
                if self.disk_error and self.disk_error[0] >= mine:
                    raise StorageError(f"zapis kopii na dysku nie powiódł się: {self.disk_error[1]}")
                left = deadline - time.monotonic()
                if left <= 0:
                    raise StorageError("zapis kopii na dysku trwa za długo")
                self.cond.wait(left)
        return result

    def move_usb(self, usb_dir):
        """The stick came back under another path (drive letter, mount point): copies go there from now on.

        Only when its newest copy is one this session continues, which also proves it is the same kit; a copy
        written meanwhile on another laptop is a conflict for the next start (False, nothing changes)."""
        usb_dir = Path(usb_dir)
        if not self._ours(usb_dir):
            return False
        copies = [c for c in (_read(usb_dir / n, self.key, "usb") for n in NAMES) if c]
        newest = max(copies, key=lambda c: c.gen, default=None)
        if not self.usb_dir or newest is None or not _continues(self, newest):   # ta baza ma history i gen jak kopia
            return False
        with self.cond:
            self.usb_dir, self.usb_error, self.usb_last = usb_dir, None, newest.path.name
            self.cond.notify_all()                   # wątek pamięci USB przerywa czekanie po błędzie
        self.on_change()
        return True

    def status(self):
        # Dostępność nośnika nie zależy od kolejnej operacji zapisu.
        usb_dir = self.usb_dir
        problem = self._stick(usb_dir) if usb_dir else NO_USB
        if usb_dir and not usb_dir.is_dir():
            problem = NO_USB
        with self.cond:
            return {"gen": self.gen, "saved": self.disk_done == self.changes,
                    "disk_error": self.disk_error[1] if self.disk_error else None,
                    "usb": bool(usb_dir), "usb_present": problem is None,
                    "usb_problem": problem, "usb_saved": bool(usb_dir) and problem is None
                    and self.usb_error is None and self.usb_done == self.changes,
                    "usb_at": self.usb_at, "usb_error": self.usb_error}

    # ---- zapis migawek ------------------------------------------------------------------------

    def _seal(self):
        with self.lock:
            with self.cond:
                if self.destroying:
                    return None
                upto = self.changes
            body = self.conn.serialize()
        self.gen += 1
        header = json.dumps({"gen": self.gen, "history": self.history, "at": _now(), "recovery": self.recovery})
        head = MAGIC + len(header.encode()).to_bytes(4, "big") + header.encode()
        return upto, self.gen, head + syscrypto.seal(self.key, body, head)

    def _disk_loop(self):
        while True:
            with self.cond:
                while self.changes == self.disk_done and not self.stopping:
                    self.cond.wait()
                if self.destroying or self.changes == self.disk_done or (self.stopping and self.disk_error):
                    return
            try:
                sealed = self._seal()
                if sealed is None or self.destroying:
                    return
                upto, gen, blob = sealed
                target = _other(self.disk_last)
                _write_durable(self.disk_dir / target, blob)
                self.disk_last = target
            except (OSError, sqlite3.Error, syscrypto.CryptoError) as e:
                with self.cond:
                    self.disk_error = (self.changes, str(e))
                    self.cond.notify_all()
                self.on_change()
                with self.cond:
                    self.cond.wait(RETRY)
                continue
            with self.cond:
                if self.destroying:
                    return                           # ZNISZCZ DANE w trakcie zapisu: bez kopii na pamięć USB
                self.disk_done, self.disk_error, self.pending = upto, None, (upto, gen, blob)
                self.cond.notify_all()
            self.on_change()

    def _usb_loop(self):
        while True:
            with self.cond:
                while (self.pending is None or self.pending[0] == self.usb_done) and not self.stopping:
                    self.cond.wait()
                if (self.destroying or self.pending is None or self.pending[0] == self.usb_done
                        or (self.stopping and self.usb_error)):
                    return
                upto, gen, blob = self.pending
                usb_dir, target = self.usb_dir, _other(self.usb_last)
            try:
                problem = self._stick(usb_dir)      # wyjęta albo pod tą ścieżką jest teraz inna pamięć
                if problem:
                    raise OSError(problem)
                _write_durable(usb_dir / target, blob)
            except OSError as e:
                with self.cond:
                    first = self.usb_error is None
                    self.usb_error = str(e)
                    self.cond.notify_all()
                if first:
                    self.on_change()
                with self.cond:
                    self.cond.wait(RETRY)
                continue
            with self.cond:
                if usb_dir == self.usb_dir:
                    self.usb_last = target
                self.usb_done, self.usb_at, self.usb_error = upto, _now(), None
                self.cond.notify_all()
            self.on_change()

    def flush(self, usb=True, timeout=30.0):
        """Wait until the disk (and the stick) hold every change; StorageError when they cannot."""
        if usb and self.usb_dir:
            problem = self._stick(self.usb_dir)
            if problem or not self.usb_dir.is_dir():
                raise StorageError(problem or NO_USB)
        with self.cond:
            deadline = time.monotonic() + timeout
            while self.disk_done != self.changes or (usb and self.usb_dir and self.usb_done != self.disk_done):
                left = deadline - time.monotonic()
                if left <= 0:
                    raise StorageError(self.usb_error or (self.disk_error or (0, "zapis kopii trwa za długo"))[1])
                self.cond.wait(left)

    def close(self, timeout=10.0):
        try:
            self.flush(timeout=timeout)
        finally:
            with self.cond:
                self.stopping = True
                self.cond.notify_all()
            for t in self.threads:
                t.join(5.0)
            with self.lock:
                self.conn.close()

    def hand_back(self):
        """'Oddaj laptop': the last copy on the stick, then the snapshots leave the laptop disk."""
        if not self.usb_dir:
            raise StorageError("brak pamięci USB zestawu: bez niej dane zostałyby tylko na tym laptopie")
        problem = self._stick(self.usb_dir)
        if problem:
            raise StorageError(problem)
        self.flush(usb=True)
        self.close()
        for name in NAMES:
            (self.disk_dir / name).unlink(missing_ok=True)

    def destroy(self, keys_dir=None):
        """ZNISZCZ DANE on the laptop: the key leaves memory, the copies leave the disk and the stick.

        Deleting files does not erase flash or SSD; against reading the stick itself only destroying
        it works, which the instruction requires."""
        with self.cond:
            self.stopping = self.destroying = True
            self.changes, self.pending = self.disk_done, None   # niezapisane zmiany nie trafiają już nigdzie
            self.cond.notify_all()
        for t in self.threads:
            t.join(5.0)
        with self.lock:
            self.conn.close()
        self.key = None
        # Na pamięci usuwa się tylko pliki tego zestawu: inna pamięć pod tą ścieżką zostaje nietknięta.
        ours = self.usb_dir is not None and self._ours(self.usb_dir)
        dirs = [self.disk_dir] + ([self.usb_dir] if ours else [])
        keep_keys = not keys_dir or (self.kit_fp is not None and kit_id(keys_dir) != self.kit_fp)
        files = [] if keep_keys else [Path(keys_dir) / n for n in (ACCOUNTS, KIT_KEY, ACCOUNTS + ".tmp")]
        # Zapis, który utknął (np. na pamięci USB), może skończyć się już po usunięciu: osoba musi o tym wiedzieć.
        failed = [f"zapis kopii w toku ({t.name})" for t in self.threads if t.is_alive()]
        for d in dirs:
            try:
                files += [f for f in d.iterdir() if f.name in NAMES or f.name.startswith("konflikt-")]
            except FileNotFoundError:
                pass                                 # wyjęta pamięć: jej pliki niszczy się fizycznie
            except OSError:
                failed.append(str(d))
        for f in files:                              # każdy plik, nawet gdy inny się nie dał
            try:
                f.unlink(missing_ok=True)
            except OSError:
                failed.append(f.name)
        if failed:
            raise StorageError("nie udało się usunąć: " + ", ".join(failed))
