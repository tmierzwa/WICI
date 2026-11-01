# SPDX-License-Identifier: MIT
"""Offline receiver identity replacement after restoring an old database copy.

The restored sender stays blocked while the new card is installed on stations.
Only a distinct private identity makes a counter reset safe; a guessed upper
counter bound from an older copy would risk nonce reuse.
"""

import contextlib
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ed25519, x25519

from .. import database
from . import nosnik


def public_identity(private):
    if len(private) != 64:
        raise database.StorageError("receiver identity has the wrong length")
    return (x25519.X25519PrivateKey.from_private_bytes(private[:32]).public_key().public_bytes_raw() +
            ed25519.Ed25519PrivateKey.from_private_bytes(private[32:]).public_key().public_bytes_raw())


def _open_guarded(medium, key):
    body = medium.load(key)
    if body is None:
        raise database.StorageError("receiver database is unavailable")
    db = sqlite3.connect(":memory:")
    try:
        db.deserialize(body)
        if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise database.StorageError("receiver database failed integrity check")
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='kopia'").fetchone():
            raise database.StorageError("finish recovery before replacing the receiver identity")
        if not db.execute("SELECT 1 FROM env_send_guard WHERE id=1 AND blocked=1").fetchone():
            raise database.StorageError("receiver is not blocked for recovery")
        return db
    except BaseException:
        db.close()
        raise


def _approvers(medium, key, approvals):
    if len(approvals) != 2 or approvals[0][0] == approvals[1][0]:
        raise database.LoginError("two distinct duty officers must approve receiver rekeying")
    for name, password in approvals:
        medium.login(name, password, key)


def _card_digest(card):
    return hashlib.sha256(json.dumps(card, sort_keys=True, separators=(",", ":")).encode()).digest()


def stage(medium, key, approvals, card_path):
    """Replace the sealed identity and card; leave the outbound guard set."""
    _approvers(medium, key, approvals)
    card_path = Path(card_path)
    if card_path.exists():
        raise FileExistsError(card_path)
    with contextlib.closing(_open_guarded(medium, key)) as db:
        old = medium.card(key)
        link = medium.link(key)
        if not old or old.get("v") != 2 or not link:
            raise database.StorageError("numbered receiver card and link are required")
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
            raise database.StorageError("numbered receiver card is inconsistent")
        # A previous stage may have lost power after replacing only one file.
        # The outbound guard is still durable, so mint another fresh identity.
        private = os.urandom(64)
        public = public_identity(private)
        if public in (main_public, backup_public):
            raise database.StorageError("new receiver identity duplicates an existing card key")
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


def activate(medium, key, approvals, card_path):
    """Clear the guard only for the exact staged card after station provisioning."""
    _approvers(medium, key, approvals)
    with contextlib.closing(_open_guarded(medium, key)) as db:
        try:
            external = json.loads(Path(card_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise database.StorageError(f"receiver card is unreadable: {exc}") from None
        card = medium.card(key)
        try:
            matches = card and external == card and public_identity(medium.identity(key)).hex() == card["main"]["key"]
        except (KeyError, TypeError):
            matches = False
        if not matches:
            raise database.StorageError("staged receiver card and identity do not match")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='env_rekey_stage'").fetchone() or not db.execute(
                "SELECT 1 FROM env_rekey_stage WHERE id=1 AND card_digest=?", (_card_digest(card),)).fetchone():
            raise database.StorageError("receiver rekey was not staged after this recovery")
        with db:
            db.execute("DELETE FROM env_send_guard WHERE id=1")
            db.execute("DROP TABLE env_rekey_stage")
            db.execute("INSERT INTO dziennik(at, account, op, detail) VALUES(?,?,?,?)",
                       (time.time(), approvals[0][0], "receiver_rekey", "fresh identity, station card installed"))
        medium.save(key, db.serialize())
        return card
