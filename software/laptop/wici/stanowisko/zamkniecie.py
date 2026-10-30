# SPDX-License-Identifier: MIT
"""Register export, closing the event and destroying the data of the receiving station (stage S9).

docs/spec/stanowisko-osp.md, „Eksport rejestru” and „ZNISZCZ DANE i ZAMKNIJ ZDARZENIE”. The register is
one CSV row per register event (reception of a report or revision, decision, reply, bulletin, handing to
a service, quarantine decision, change of the trusted list, copy and recovery, shift handover), built
from the reference model tables and the action log; it has no keys, passwords or LXMF addresses, only the
station name WICI-xxxxxx.

ZAMKNIJ ZDARZENIE writes an archive with the database and the register and then deletes the content of
reports. The archive is for the data administrator; until D13 sets his key, it is sealed with a key
wrapped by a new archive password (6 words from the list, PBKDF2 as the medium), shown once for the
envelope that goes with the archive. `python -m wici.stanowisko archiwum` opens it.
"""

import csv
import datetime
import io
import json
import os
import shutil
import time
import zipfile
from pathlib import Path

from .. import database, passwords, syscrypto
from . import wzorzec

COLUMNS = ("czas", "rodzaj", "stacja", "numer", "id", "rewizja", "kategoria", "osoby", "pilnosc", "adres", "tresc",
           "stan", "adresat", "potwierdzil", "kanal", "dyzurny")
# Zdarzenia rejestru z dziennika działań; logowania, ogłoszenia i nowe hasła zostają tylko w dzienniku.
REGISTER = {"stan_2", "stan_3", "stan_4", "stan_5", "stan_6", "odpowiedz", "komunikat", "cisza", "kwarantanna_approve",
            "kwarantanna_reject", "zaufana_dodana", "zaufana_usunieta", "kopia_drugi_nosnik", "odtworzenie",
            "odzyskanie_koniec", "przekazanie_zmiany", "eksport", "zamkniecie", "kopie_usuniete"}
# Cisza radiowa wpisywana przez dyżurnego (stanowisko-osp.md, „Eksport rejestru”: wiersz „cisza”); stan węzła
# odczytany z jego portu diagnostyki dojdzie osobno.
SILENCE = {"polecenie": "polecenie ciszy otrzymane", "wlaczona": "cisza włączona na węźle", "odwolana": "cisza odwołana"}
ARCHIVE_WORDS = 6
ARCHIVE_AAD = b"wici archiwum"
ARCHIVE_KIND = "archiwum-stanowiska"
EXPORT = "eksport"


def _when(at):
    return datetime.datetime.fromtimestamp(at).astimezone().isoformat(timespec="seconds")


def register(db):
    """Rows of the register (dicts with COLUMNS), oldest first."""
    from .panel import short_number   # panel importuje ten moduł; numer krótki liczony w jednym miejscu
    names = dict(db.execute("SELECT source, name FROM karty"))
    payloads = {(s, m, r): p for s, m, r, p in db.execute("SELECT source, id, revision, payload FROM received")}
    bulletins = {m: p for m, p in db.execute("SELECT id, payload FROM outbox WHERE kind=4 GROUP BY id")}

    def row(at, kind, source=None, mid=None, revision=None, account=""):
        r = dict.fromkeys(COLUMNS, "")
        r.update(czas=_when(at), rodzaj=kind, dyzurny=account)
        if source is not None:
            r["stacja"] = names.get(source, "")
        if mid:
            r.update(numer=short_number(mid), id=mid)
        if revision is not None:
            r["rewizja"] = revision
        payload = payloads.get((source, mid, revision))
        if payload:
            _, _, _, _, category, people, address, text, urgency = wzorzec.decode_message(payload)
            r.update(kategoria=category, osoby=people, pilnosc=urgency, adres=address, tresc=text)
        return r

    rows = []
    for source, mid, revision, payload, at in db.execute(
            "SELECT r.source, r.id, r.revision, r.payload, a.at FROM received r JOIN received_at a USING(source, id, revision)"):
        kind = "odbior_test" if payload and wzorzec.decode_message(payload)[1] == 5 else "odbior"
        rows.append((at, row(at, kind, source, mid, revision)))
    for at, account, op, detail, source, mid, revision in db.execute(
            "SELECT at, account, op, detail, source, mid, revision FROM dziennik ORDER BY id"):
        if op not in REGISTER:
            continue
        r = row(at, op, source, mid, revision, account)
        if op.startswith("stan_"):
            r["stan"] = op[5:]
            facts = json.loads(detail) if detail.startswith("{") else {}
            r["adresat"] = facts.get("adresat", "")
            r["potwierdzil"] = ", ".join(facts[k] for k in ("podmiot", "funkcja") if k in facts)
            r["kanal"] = facts.get("kanal", "")
        elif op == "cisza":
            facts = json.loads(detail)
            r["tresc"] = f"{SILENCE[facts['stan']]}: {facts['organ']}, {facts['kiedy']}"
        elif op == "komunikat" and bulletins.get(mid):
            r["tresc"] = wzorzec.decode_message(bulletins[mid])[4]
        rows.append((at, r))
    rows.sort(key=lambda pair: pair[0])
    return [r for _, r in rows]


def csv_bytes(rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def write_new(directory, name, data):
    """A new file with fsync; an existing one is never overwritten (a second one in the same second gets -2)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stem, suffix = Path(name).stem, Path(name).suffix
    for n in range(1, 100):
        path = directory / (name if n == 1 else f"{stem}-{n}{suffix}")
        try:
            f = open(path, "xb")
            break
        except FileExistsError:
            continue
    else:
        raise FileExistsError(name)
    with f:
        f.write(data)
        f.flush()
        database._fsync(f.fileno())
    database._fsync_dir(directory)
    return path


def stamp(at):
    return time.strftime("%Y%m%dT%H%M%S", time.localtime(at))


def archive(db, at, iterations=database.ITERATIONS):
    """(sealed archive bytes, archive password): zip with baza.sqlite and rejestr.csv."""
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("baza.sqlite", db.serialize())
        z.writestr("rejestr.csv", csv_bytes(register(db)))
    password = passwords.generate(ARCHIVE_WORDS)
    key = os.urandom(32)
    header = json.dumps({"wici": ARCHIVE_KIND, "v": 1, "at": _when(at),
                         "slot": database._slot(key, password, ARCHIVE_AAD, iterations)}).encode()
    head = database.MAGIC + len(header).to_bytes(4, "big") + header
    return head + syscrypto.seal(key, data.getvalue(), head), password


def open_archive(path, password, target):
    """Write baza.sqlite and rejestr.csv of an archive to the directory target (for the administrator)."""
    try:
        head, header, sealed = database._split(Path(path).read_bytes())
    except (OSError, ValueError) as e:
        raise database.StorageError(f"archiwum nieczytelne: {e}") from None
    if header.get("wici") != ARCHIVE_KIND or header.get("v") != 1:
        raise database.StorageError("to nie jest archiwum stanowiska WICI w znanej wersji")
    key = database._unwrap(header.get("slot") or {}, password, ARCHIVE_AAD)
    if key is None:
        raise database.LoginError("Złe hasło archiwum.")
    names = ("baza.sqlite", "rejestr.csv")
    existing = [name for name in names if (Path(target) / name).exists()]
    if existing:
        raise FileExistsError(f"w katalogu już jest {', '.join(existing)}: wskaż pusty katalog")
    with zipfile.ZipFile(io.BytesIO(syscrypto.open_(key, sealed, head))) as z:
        for name in names:
            write_new(target, name, z.read(name))


def remove_exports(directory):
    """Plain register CSV files out of the export directory at ZAMKNIJ ZDARZENIE (the archive has the register):
    (names removed, names that stayed)."""
    removed, left = [], []
    for path in sorted(Path(directory).glob("rejestr-*.csv")):
        try:
            path.unlink()
            removed.append(path.name)
        except OSError:
            left.append(path.name)
    return removed, left


def purge(db):
    """Content of reports out of the database (ZAMKNIJ ZDARZENIE), in one transaction: payloads, replies,
    quarantine (reference purge_content) and the texts of REPLY and BULLETIN intents. Reception keys,
    identities, the trusted list, decisions and the action log stay."""
    with db:
        db.execute("UPDATE received SET payload=NULL")
        db.execute("UPDATE replies SET text=NULL")
        db.execute("DELETE FROM quarantine")
        db.execute("UPDATE outbox SET payload=X'', done=1 WHERE kind IN (3, 4)")


def destroy(medium, copies=(), extra=()):
    """ZNISZCZ DANE: identity, database, accounts, stack storage and exports off the medium, and the copies
    (computer disk, second medium when connected). Names of what could not be deleted."""
    failed = []
    for copy in copies:
        failed += copy.remove()
    for path in [medium.kit.dir, medium.base, medium.network, medium.root / EXPORT, *extra]:
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            pass
        except OSError as e:
            failed.append(f"{path.name}: {e.strerror}")
    for name in ("tozsamosc", "tozsamosc.tmp"):
        try:
            (medium.root / name).unlink(missing_ok=True)
        except OSError:
            failed.append(name)
    return failed

