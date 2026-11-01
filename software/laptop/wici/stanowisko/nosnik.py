# SPDX-License-Identifier: MIT
"""The station medium: accounts, database snapshots and the receiver identity (stage S4).

docs/spec/stanowisko-osp.md, „Nośnik i szyfrowanie”: a random data key protects the medium; the station
password wraps it, so a new password rewraps only the key. The format is that of the shelter laptop
(database.py): PBKDF2-HMAC-SHA256 from the operating system (syscrypto.py), 16 B salt, the iteration count
in every wrap, `version` 1 in the account file and a version byte in every sealed blob.

    klucze/zestaw.key, klucze/konta.json   database.Kit: `recovery` is the station password (6 words),
                                           `accounts` are the duty officers (5 words, plus zestaw.key)
    baza/kopia-a, baza/kopia-b             the database in memory, sealed after every change (two files in
                                           turn, fsync); the header carries the station password wrap, so
                                           a lost account file does not lose the data
    tozsamosc                              the main receiver identity, sealed with the data key
    siec/                                  Reticulum and LXMF storage (paths, ratchets of the receiver)

The backup identity never reaches the medium: preparation makes it in memory and writes only a package
sealed with its own password (at least 6 words) for the envelopes off the station (O10).
"""

import hmac
import json
import os
from pathlib import Path

from .. import configdoc, database, passwords, syscrypto

STATION_WORDS = BACKUP_WORDS = 6
OFFICERS_MAX = 20
IDENTITY_AAD = b"wici tozsamosc odbiorcy"
CARD_AAD = b"wici karta odbiorcy"
BACKUP_AAD = b"wici paczka zapasowa"
LINK_AAD = b"wici link stanowiska v1"
BACKUP_KIND, CARD_KIND = "paczka-zapasowa", "karta-odbiorcy"
LoginError, StorageError = database.LoginError, database.StorageError


def officer(i):
    return f"dyzurny-{i}"


def validate_link(link):
    """Return a canonical numbered KISS binding before creating any medium files."""
    if (not isinstance(link, dict) or set(link) != {"net_id", "root", "ifac"} or
            any(type(link[name]) is not int or not 1 <= link[name] <= 0xFFFE for name in ("net_id", "root")) or
            not isinstance(link["ifac"], str) or len(link["ifac"]) != 32 or
            any(c not in "0123456789abcdefABCDEF" for c in link["ifac"])):
        raise StorageError("niepoprawne ustawienia WICI-Link")
    return {**link, "ifac": link["ifac"].lower()}


class Nosnik:
    def __init__(self, root, iterations=database.ITERATIONS):
        self.root, self.iterations = Path(root), iterations
        self.kit = database.Kit(self.root / "klucze")
        self.base, self.network = self.root / "baza", self.root / "siec"
        self.gen, self.last = 0, None   # pokolenie i plik najnowszej migawki

    def exists(self):
        return self.kit.exists() or database.has_copies(self.base) or any(
            (self.root / name).exists() for name in ("tozsamosc", "karta-odbiorcy", "wici-link"))

    @classmethod
    def create(cls, root, officers, identity_key, iterations=database.ITERATIONS, card=None, link=None):
        """Preparation: accounts of the duty officers, the station password and the main identity.

        Returns (medium, data key, envelopes {account: password}, with "stanowisko" for the station password)."""
        if not 1 <= officers <= OFFICERS_MAX:
            raise ValueError(f"dyżurnych: od 1 do {OFFICERS_MAX}")
        if link is not None:
            link = validate_link(link)
        medium = cls(root, iterations)
        if medium.exists():
            raise StorageError("ten nośnik jest już przygotowany")
        medium.root.mkdir(parents=True, exist_ok=True)
        chosen = {officer(i): passwords.generate() for i in range(1, officers + 1)}
        station = passwords.generate(STATION_WORDS)
        _, key = database.Kit.create(medium.kit.dir, chosen, station, iterations)
        medium.save_identity(key, identity_key)
        if card is not None:
            medium.save_card(key, card)
        if link is not None:
            medium.save_link(key, link)
        return medium, key, {"stanowisko": station, **chosen}

    # ---- hasła ----------------------------------------------------------------------------------

    def unlock(self, password):
        """Data key from the station password (start of the application); at most 5 failures a minute."""
        def attempt():
            try:
                slot = self.kit.recovery()
            except StorageError:
                slot = None   # plik kont zginął: opakowanie jest też w nagłówku każdej migawki
            key = database._unwrap(slot, password, database.RECOVERY_AAD) if slot else None
            if key is None:
                try:
                    key = database.key_from_recovery([self.base], password)
                except LoginError:
                    raise LoginError("Złe hasło stanowiska.") from None
            return key
        return self.kit.throttled(attempt)

    def login(self, name, password, key):
        """Check a duty officer's password against the open medium; LoginError otherwise."""
        if not hmac.compare_digest(self.kit.unlock(name, password), key):
            raise LoginError("Zła nazwa konta albo hasło.")   # konto z innego nośnika

    def new_password(self, name, key):
        """New envelope password for an account, set by a logged-in officer; returns it once."""
        password = passwords.generate()
        self.kit.set_password(name, key, password, self.iterations)
        return password

    def new_station_password(self, key, body=None):
        """New station password (after its envelope was opened); rewraps only the data key.

        Both snapshot files are written again with the new wrap in their header, so the old password
        opens nothing on the medium. body: the current database (from the database thread), else the newest
        snapshot."""
        password = passwords.generate(STATION_WORDS)
        with self.kit.lock:
            doc, _ = self.kit._load()
            doc["recovery"] = database._slot(key, password, database.RECOVERY_AAD, self.iterations)
            self.kit._save(doc)
        body = self.load(key) if body is None else body
        if body is not None:
            for _ in database.NAMES:
                self.save(key, body)
        return password

    def names(self):
        return self.kit.names()

    # ---- baza -----------------------------------------------------------------------------------

    def load(self, key):
        """Body of the newest snapshot that opens with key (SQLite serialize), or None for a new medium."""
        found = [c for c in (database._read(self.base / n, key, "nosnik") for n in database.NAMES) if c]
        newest = max(found, key=lambda c: c.gen, default=None)
        self.gen = newest.gen if newest else 0
        self.last = newest.path.name if newest else None
        return newest.body if newest else None

    def save(self, key, body):
        """Seal body and write it with fsync over the older of the two files."""
        self.base.mkdir(exist_ok=True)
        try:
            recovery = self.kit.recovery()
        except StorageError:
            recovery = None
        header = json.dumps({"gen": self.gen + 1, "history": [], "at": database._now(), "recovery": recovery})
        head = database.MAGIC + len(header.encode()).to_bytes(4, "big") + header.encode()
        target = database._other(self.last)
        database._write_durable(self.base / target, head + syscrypto.seal(key, body, head))
        self.gen, self.last = self.gen + 1, target

    # ---- tożsamość odbiorcy ----------------------------------------------------------------------

    def save_identity(self, key, private_key):
        tmp = self.root / "tozsamosc.tmp"
        database._write_durable(tmp, syscrypto.seal(key, private_key, IDENTITY_AAD))
        os.replace(tmp, self.root / "tozsamosc")
        database._fsync_dir(self.root)

    def identity(self, key):
        """Private key (64 B) of the main receiver identity."""
        try:
            return syscrypto.open_(key, (self.root / "tozsamosc").read_bytes(), IDENTITY_AAD)
        except (OSError, syscrypto.CryptoError) as e:
            raise StorageError(f"tożsamość odbiorcy nieczytelna: {e}") from None

    def save_card(self, key, card):
        """Keep the receiver-number binding on the encrypted medium, including after a reboot."""
        if not isinstance(card, dict) or card.get("wici") != CARD_KIND or card.get("v") not in (1, 2):
            raise StorageError("niepoprawna karta odbiorcy")
        tmp = self.root / "karta-odbiorcy.tmp"
        data = json.dumps(card, sort_keys=True, separators=(",", ":")).encode()
        database._write_durable(tmp, syscrypto.seal(key, data, CARD_AAD))
        os.replace(tmp, self.root / "karta-odbiorcy")
        database._fsync_dir(self.root)

    def card(self, key):
        """The sealed receiver card, or None on a medium prepared before numbered cards."""
        path = self.root / "karta-odbiorcy"
        if not path.exists():
            return None
        try:
            card = json.loads(syscrypto.open_(key, path.read_bytes(), CARD_AAD))
        except (OSError, ValueError, syscrypto.CryptoError) as e:
            raise StorageError(f"karta odbiorcy nieczytelna: {e}") from None
        if not isinstance(card, dict) or card.get("wici") != CARD_KIND or card.get("v") not in (1, 2):
            raise StorageError("karta odbiorcy jest uszkodzona")
        return card

    def save_link(self, key, link):
        link = validate_link(link)
        tmp = self.root / "wici-link.tmp"
        database._write_durable(tmp, syscrypto.seal(key, json.dumps(link, sort_keys=True).encode(), LINK_AAD))
        os.replace(tmp, self.root / "wici-link")
        database._fsync_dir(self.root)

    def link(self, key):
        path = self.root / "wici-link"
        if not path.exists():
            return None
        try:
            link = json.loads(syscrypto.open_(key, path.read_bytes(), LINK_AAD))
        except (OSError, ValueError, syscrypto.CryptoError) as exc:
            raise StorageError(f"ustawienia WICI-Link nieczytelne: {exc}") from None
        try:
            return validate_link(link)
        except StorageError:
            raise StorageError("ustawienia WICI-Link uszkodzone") from None


# ---- paczka zapasowa i karta odbiorcy --------------------------------------------------------------

def lxmf_address(public_key):
    return configdoc.destination(public_key, "lxmf.delivery")


def backup_package(private_key, public_key, password, iterations=database.ITERATIONS):
    """The backup identity sealed with its own password, for the envelope (JSON)."""
    return {"wici": BACKUP_KIND, "v": 1, "lxmf": lxmf_address(public_key).hex(),
            **database._slot(private_key, password, BACKUP_AAD, iterations)}


def open_backup(doc, password):
    """Private key of the backup identity from its package; LoginError for a wrong password."""
    if not (isinstance(doc, dict) and doc.get("wici") == BACKUP_KIND and doc.get("v") == 1):
        raise StorageError("to nie jest paczka tożsamości zapasowej WICI w znanej wersji")
    key = database._unwrap(doc, password, BACKUP_AAD)
    if key is None:
        raise LoginError("Złe hasło paczki zapasowej albo uszkodzona paczka.")
    return key


def receiver_card(main_public, backup_public, net_id=None, main_id=None, backup_id=None):
    """Receiver card for the stations (oprogramowanie.md, „Karty”): both identities, address and full key."""
    numbered = (net_id, main_id, backup_id)
    if any(v is not None for v in numbered):
        if any(type(v) is not int or not 1 <= v <= 0xFFFE for v in numbered) or main_id == backup_id:
            raise ValueError("numery karty odbiorcy muszą być różne i należeć do zakresu 1..65534")
    def identity(public, number):
        result = {"lxmf": lxmf_address(public).hex(), "key": public.hex()}
        if net_id is not None:
            result.update(id=number, net_id=net_id, x25519=public[:32].hex())
        return result
    return {"wici": CARD_KIND, "v": 2 if net_id is not None else 1,
            "main": identity(main_public, main_id), "backup": identity(backup_public, backup_id)}
