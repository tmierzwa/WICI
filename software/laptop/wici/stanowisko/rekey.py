# SPDX-License-Identifier: MIT
"""Receiver identity lifecycle: offline replacement after restoring an old database copy
(stanowisko-osp.md, „Wysyłka”, step 3) and activation of the backup identity („Tożsamość zapasowa”).

The restored sender stays blocked while the new card is installed on stations.
Only a distinct private identity makes a counter reset safe; a guessed upper
counter bound from an older copy would risk nonce reuse.

The backup identity has no counter state outside the database of the medium
that activates it. Its package is therefore marked as used before the first
medium exists; every later activation of that package (a second medium, a lost
medium, an interrupted activation) starts with the outbound guard set, which
only the replacement above releases. One package file thus yields at most one
database lineage that seals envelopes under the backup key, and restores within
that lineage are guarded by recovery.
"""

import contextlib
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

from .. import database
from . import nosnik, przyjecie, wzorzec

USED = "uzyta"   # package field: time of the first activation


def _open_guarded(medium, key):
    body = medium.load(key)
    if body is None:
        raise database.StorageError("brak bazy na nośniku")
    db = sqlite3.connect(":memory:")
    try:
        db.deserialize(body)
        if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise database.StorageError("baza na nośniku nie przeszła sprawdzenia integralności")
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='kopia'").fetchone():
            raise database.StorageError("najpierw zakończ odzyskiwanie w panelu dyżurnego")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='env_send_guard'").fetchone() or \
                not db.execute("SELECT 1 FROM env_send_guard WHERE id=1 AND blocked=1").fetchone():
            raise database.StorageError("nadawanie kopert nie jest zablokowane po odzyskaniu")
        return db
    except BaseException:
        db.close()
        raise


def _card_digest(card):
    return hashlib.sha256(json.dumps(card, sort_keys=True, separators=(",", ":")).encode()).digest()


def stage(medium, key, approvers, card_path):
    """New private identity and card on the medium and in card_path; the outbound guard stays set."""
    medium.approve(key, approvers)
    card_path = Path(card_path)
    if card_path.exists():   # never the card the stations already hold
        raise database.StorageError(f"plik karty już istnieje: {card_path}")
    with contextlib.closing(_open_guarded(medium, key)) as db:
        old = medium.card(key)
        link = medium.link(key)
        if not old or old.get("v") != 2 or not link:
            raise database.StorageError("wymiana tożsamości wymaga numerowanej karty i ustawień WICI-Link")
        try:
            main, backup = old["main"], old["backup"]
            main_public, backup_public = bytes.fromhex(main["key"]), bytes.fromhex(backup["key"])
            valid = (len(main_public) == len(backup_public) == 64 and
                     main["net_id"] == backup["net_id"] == link["net_id"]
                     and all(type(entry["id"]) is int and 1 <= entry["id"] <= 0xFFFE
                             for entry in (main, backup)) and main["id"] != backup["id"] and
                     main["x25519"] == main_public[:32].hex() and
                     backup["x25519"] == backup_public[:32].hex())
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            raise database.StorageError("numerowana karta odbiorcy jest niespójna")
        # A previous stage may have lost power after replacing only one file.
        # The outbound guard is still durable, so mint another fresh identity.
        private = os.urandom(64)
        public = nosnik.public_identity(private)
        if public in (main_public, backup_public):
            raise database.StorageError("nowa tożsamość powtarza klucz z karty")
        card = nosnik.receiver_card(public, backup_public, link["net_id"], main["id"], backup["id"])
        medium.save_identity(key, private)
        medium.save_card(key, card)
        card_path.parent.mkdir(parents=True, exist_ok=True)
        with card_path.open("x", encoding="utf-8") as output:
            json.dump(card, output, indent=1)
            output.flush()
            os.fsync(output.fileno())
        database._fsync_dir(card_path.parent)
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS env_rekey_stage (id INTEGER PRIMARY KEY CHECK(id=1), card_digest BLOB NOT NULL)")
            db.execute("INSERT OR REPLACE INTO env_rekey_stage VALUES(1,?)", (_card_digest(card),))
        medium.save(key, db.serialize())
        return card


def activate(medium, key, approvers, card_path):
    """Clear the guard only for the exact staged card after station provisioning."""
    medium.approve(key, approvers)
    with contextlib.closing(_open_guarded(medium, key)) as db:
        try:
            external = json.loads(Path(card_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise database.StorageError(f"karta odbiorcy nieczytelna: {exc}") from None
        card = medium.card(key)
        if not card or external != card or nosnik.card_entry(card, medium.identity(key)) is not card.get("main"):
            raise database.StorageError("karta nie zgadza się z nową tożsamością na nośniku")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='env_rekey_stage'").fetchone() or not db.execute(
                "SELECT 1 FROM env_rekey_stage WHERE id=1 AND card_digest=?", (_card_digest(card),)).fetchone():
            raise database.StorageError("nowej tożsamości nie przygotowano po tym odzyskaniu")
        with db:
            db.execute("DELETE FROM env_send_guard WHERE id=1")
            db.execute("DROP TABLE env_rekey_stage")
            db.execute("INSERT INTO dziennik(at, account, op, detail) VALUES(?,?,?,?)",
                       (time.time(), approvers[0][0], "nowa_tozsamosc",
                        f"karta na stacjach, zgoda {approvers[0][0]} i {approvers[1][0]}"))
        medium.save(key, db.serialize())
        return card


def activate_backup(package_path, password, root, officers, card, link=None, iterations=database.ITERATIONS):
    """The backup identity from its package on a new medium with new duty officer accounts.

    Returns (medium, data key, envelopes, guarded): guarded is True when the package was used before,
    so the medium may receive but seals no envelope until stage() and activate() replace the identity."""
    package_path = Path(package_path)
    try:
        doc = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise database.StorageError(f"paczka zapasowa nieczytelna: {exc}") from None
    private = nosnik.open_backup(doc, password)
    entry = nosnik.card_entry(card, private) if isinstance(card, dict) else None
    if entry is None or entry is not card.get("backup"):
        raise database.StorageError("karta odbiorcy nie zawiera tej tożsamości zapasowej")
    if (card.get("v") == 2) != (link is not None):
        raise database.StorageError("numerowana karta wymaga ustawień WICI-Link, a tylko ona je przyjmuje")
    if link is not None and (nosnik.validate_link(link)["net_id"] != entry["net_id"] or
                             link["root"] in (card["main"]["id"], entry["id"])):
        raise database.StorageError("ustawienia WICI-Link nie pasują do karty odbiorcy")
    if nosnik.Nosnik(root).exists():
        raise database.StorageError("ten nośnik jest już przygotowany")
    guarded = USED in doc
    if not guarded:
        # Durable before the medium exists: an interruption from here on only makes a retry guarded.
        tmp = package_path.with_name(package_path.name + ".tmp")
        database._write_durable(tmp, json.dumps({**doc, USED: time.time()}, indent=1).encode("utf-8"))
        os.replace(tmp, package_path)
        database._fsync_dir(package_path.parent)
    with contextlib.closing(wzorzec.OSPStore(":memory:")) as store:
        store.db.executescript(przyjecie.SCHEMA)
        with store.db:
            if guarded:
                store.db.execute("INSERT INTO env_send_guard VALUES(1,1)")
            store.db.execute("INSERT INTO dziennik(at, account, op, detail) VALUES(?,?,?,?)",
                             (time.time(), "", "aktywacja_zapasowej",
                              "paczka użyta wcześniej: nadawanie kopert zablokowane do nowej tożsamości"
                              if guarded else "pierwsze użycie paczki"))
        body = store.db.serialize()
    return (*nosnik.Nosnik.create(root, officers, private, iterations, card=card, link=link, body=body), guarded)
