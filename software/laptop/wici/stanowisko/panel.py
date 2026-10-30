# SPDX-License-Identifier: MIT
"""Duty officer panel of the receiving station (stage S7; docs/spec/stanowisko-osp.md, „Panel dyżurnego”).

HTTP on 127.0.0.1 only, with the security of the laptop panel (web.SecureHandler: loopback Host, the
session token in a cookie from a one-time /start link, JSON POST with a loopback Origin). Every
operation needs a logged-in duty officer (account and envelope password checked against the medium);
the panel locks after 5 min without activity. Adding a station to the trusted list and other operations
named in the specification also need a second duty officer, who types his account and password in the
same dialog. Every operation goes to the action log under the account.

Dyzur holds the operations and the views, without HTTP, so tests call it directly.
"""

import hashlib
import json
import secrets
import threading
import time
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .. import VERSION, configdoc, database, web
from . import kopie, nosnik, wysylka, wzorzec, zamkniecie

LOCK_S = 300
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8")}
TEXT_MAX = 200   # pola wpisów lokalnych (źródło, adresat): nie idą radiem
BULLETIN_BYTES = 192   # tekst komunikatu (oprogramowanie.md, „Wiadomości SA1”)
LABELS = {"podmiot": "podmiot dysponujący siłami", "funkcja": "funkcja osoby", "kanal": "kanał",
          "czas": "czas", "adresat": "komu przekazano", "text": "treść odpowiedzi", "path": "katalog",
          "account": "konto", "password": "hasło"}


class NotLoggedIn(Exception):
    pass


def station_name(public_key):
    """WICI-xxxxxx: 6 hex digits of the identity hash (firmware/src/main.cpp, setStationName)."""
    return "WICI-" + hashlib.sha256(public_key).digest()[:3].hex().upper()


def fingerprint(public_key):
    """First 8 B of SHA-256 of the key in groups of 4 digits, as on the station screen (usbproto.cpp)."""
    h = hashlib.sha256(public_key).hexdigest()[:16]
    return " ".join(h[i:i + 4] for i in range(0, 16, 4))


def short_number(mid):
    """Short number of a report: first 16 bits of id modulo 10 000, four digits (oprogramowanie.md)."""
    return f"{int(mid[:4], 16) % 10000:04d}"


def _text(body, key, maximum=TEXT_MAX):
    value = body.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"wpisz pole: {LABELS.get(key, key)}")
    return value.strip()


def _source(body):
    try:
        source = bytes.fromhex(body.get("source", ""))
    except (TypeError, ValueError):
        source = b""
    if len(source) != 16:
        raise ValueError("adres stacji: 32 cyfry szesnastkowe")
    return source


def _report(body):
    mid, revision = body.get("id"), body.get("revision")
    if not isinstance(mid, str) or len(mid) != 32 or type(revision) is not int:
        raise ValueError("zgłoszenie: id i revision")
    return _source(body), mid, revision


class Dyzur:
    """The panel operations on a running station: przyjecie (database thread), medium and key, stack."""

    def __init__(self, przyjecie, medium, key, stos=None, clock=time.time, monotonic=time.monotonic):
        self.p, self.medium, self.key, self.stos = przyjecie, medium, key, stos
        self.clock, self.monotonic = clock, monotonic
        self.user, self.touched = None, 0.0
        self.lock = threading.RLock()
        self.on_quit = lambda: None   # po ZNISZCZ DANE aplikacja kończy pracę (__main__)
        self.wezel = None             # stan węzła z portu diagnostyki (wezel.py), gdy port jest

    # ---- konto -------------------------------------------------------------------------------

    def login(self, account, password):
        with self.lock:
            self.medium.login(account, password, self.key)
            self.user, self.touched = account, self.monotonic()
        self.p.action(account, "logowanie")

    def logout(self, op="wylogowanie"):
        with self.lock:
            user, self.user = self.user, None
        if user:
            self.p.action(user, op)

    def touch(self):
        """Activity in the panel (keys, mouse): moves the 5 min lock."""
        self.current()

    def current(self):
        """The logged-in account; NotLoggedIn when nobody is or the panel locked after 5 min."""
        with self.lock:
            if self.user and self.monotonic() - self.touched > LOCK_S:
                self.logout("blokada_5_min")
            if not self.user:
                raise NotLoggedIn()
            self.touched = self.monotonic()
            return self.user

    def second(self, body):
        """The second duty officer's consent in the same dialog: another account and its password."""
        user = self.current()
        account, password = body.get("account2"), body.get("password2")
        if not isinstance(account, str) or not isinstance(password, str) or not password:
            raise ValueError("potrzebna zgoda drugiego dyżurnego: jego konto i hasło")
        if account == user:
            raise database.LoginError("Zgoda musi pochodzić od innego dyżurnego.")
        self.medium.login(account, password, self.key)
        return user, account

    def _logged(self, store, user, op, detail="", source=None, mid=None, revision=None):
        self.p._log_action(user, op, detail, source, mid, revision)

    # ---- decyzje ------------------------------------------------------------------------------

    def status(self, body):
        """Decision for one report: 2 PRZECZYTANE; 3 with the source and time of the confirmation that help
        was sent (entity, function, channel); 4 with the addressee and time; 5 only with a REPLY; 6."""
        user = self.current()
        source, mid, revision = _report(body)
        state = body.get("state")
        if state not in (2, 3, 4, 5, 6):
            raise ValueError("stan od 2 do 6")
        detail = ""
        if state == 3:
            detail = json.dumps({k: _text(body, k) for k in ("podmiot", "funkcja", "kanal", "czas")}, ensure_ascii=False)
        elif state == 4:
            detail = json.dumps({k: _text(body, k) for k in ("adresat", "czas")}, ensure_ascii=False)
        reply = configdoc.clean_text(body["reply"]) if state == 5 and isinstance(body.get("reply"), str) else None
        if state == 5 and not reply:
            raise ValueError("stan 5 tylko razem z odpowiedzią REPLY z instrukcją")

        def decide(store):
            now = self.clock()
            if reply:
                self.p.wysylka.reply(store, source, mid, revision, reply, now)
            event = self.p.wysylka.status(store, source, mid, revision, state, now)
            with store.db:
                if detail:
                    store.db.execute("INSERT INTO decyzje(source, mid, state, detail, at, account) VALUES(?,?,?,?,?,?)",
                                     (source, mid, state, detail, now, user))
            self._logged(store, user, f"stan_{state}", detail, source, mid, revision)
            return event
        return {"event": self.p.call(decide)}

    def read_tests(self, body):
        """PRZECZYTANE for several TEST at once, after the officer checked the address of each."""
        items = body.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("zaznacz TEST do potwierdzenia")
        return {"events": [self.status({**item, "state": 2})["event"] for item in items]}

    def reply(self, body):
        user = self.current()
        source, mid, revision = _report(body)
        text = configdoc.clean_text(_text(body, "text", 400))

        def send(store):
            event = self.p.wysylka.reply(store, source, mid, revision, text, self.clock())
            self._logged(store, user, "odpowiedz", "", source, mid, revision)
            return event
        return {"event": self.p.call(send)}

    def bulletin(self, body):
        """BULLETIN with a new id, one intent per trusted station; they go one after another (wysylka.py)."""
        user = self.current()
        text = configdoc.clean_text(_text(body, "text", 400))

        def send(store):
            mid = self.p.wysylka.bulletin(store, text, self.clock())
            self._logged(store, user, "komunikat", "", None, mid)
            return mid
        return {"id": self.p.call(send)}

    def silence(self, body):
        """Radio silence as the duty officer records it: order received, silence on at the node, order lifted;
        who ordered and when, as the officer writes them. With "bulletin" the order goes on to the stations
        as BULLETIN with a fixed text (oprogramowanie.md, „Cisza radiowa”: the receiver passes it on)."""
        user = self.current()
        state = body.get("state")
        if state not in zamkniecie.SILENCE:
            raise ValueError("stan ciszy: polecenie, wlaczona albo odwolana")
        facts = {"stan": state, "organ": _text(body, "organ", 60), "kiedy": _text(body, "kiedy", 40)}
        text = None
        if body.get("bulletin"):
            text = (f"Cisza radiowa odwołana ({facts['organ']}, {facts['kiedy']}). Wyłącz CISZA na stacji."
                    if state == "odwolana" else
                    f"CISZA RADIOWA od {facts['kiedy']}, polecenie: {facts['organ']}. Włącz CISZA na stacji. "
                    "Pilne sprawy przez gońca.")
            if len(text.encode("utf-8")) > BULLETIN_BYTES:
                raise ValueError("komunikat o ciszy za długi: skróć organ albo czas")

        def run(store):
            now = self.clock()
            self._logged(store, user, "cisza", json.dumps(facts, ensure_ascii=False))
            with store.db:
                if state == "odwolana":
                    store.db.execute("DELETE FROM settings WHERE key='cisza'")
                else:
                    store.db.execute("INSERT OR REPLACE INTO settings VALUES('cisza', ?)",
                                     (json.dumps({**facts, "at": now, "account": user}, ensure_ascii=False),))
            if text is not None:
                mid = self.p.wysylka.bulletin(store, text, now)
                self._logged(store, user, "komunikat", "", None, mid)
                return mid
        return {"bulletin": self.p.call(run)}

    # ---- kwarantanna i zaufanie --------------------------------------------------------------

    def quarantine(self, body):
        """Approve one quarantined message (without trusting the sender) or reject it."""
        user = self.current()
        source, mid, revision = _report(body)
        if body.get("decision") not in ("approve", "reject"):
            raise ValueError("decyzja: approve albo reject")

        def decide(store):
            if body["decision"] == "approve":
                store.approve_message(source, mid, revision)
                # RECEIVED i czas przyjęcia: osobna transakcja, ale ta sama migawka na nośniku (call zapisuje po fn).
                with store.db:
                    store.db.execute("INSERT OR IGNORE INTO received_at VALUES(?,?,?,?)",
                                     (source, mid, revision, self.clock()))
                    self.p.wysylka.accepted(store.db, source, mid, revision)
            else:
                with store.db:
                    if store.db.execute("DELETE FROM quarantine WHERE source=? AND id=? AND revision=?",
                                        (source, mid, revision)).rowcount != 1:
                        raise ValueError("nie ma takiej wiadomości w kwarantannie")
            self._logged(store, user, f"kwarantanna_{body['decision']}", "", source, mid, revision)
        self.p.call(decide)
        return {"ok": True}

    def trust(self, body):
        """Add a station from its card, after comparing the fingerprint with the station screen, with the
        consent of two logged-in duty officers."""
        user, other = self.second(body)
        card = body.get("card")
        if not isinstance(card, dict):
            raise ValueError("wczytaj kartę stacji")
        try:
            key = bytes.fromhex(card.get("key", ""))
            lxmf = bytes.fromhex(card.get("lxmf", ""))
        except (TypeError, ValueError):
            key = lxmf = b""
        if len(key) != 64 or nosnik.lxmf_address(key) != lxmf:
            raise ValueError("karta stacji uszkodzona: adres nie należy do klucza")
        typed = "".join(str(body.get("fingerprint", "")).split()).lower()
        if typed != fingerprint(key).replace(" ", ""):
            raise ValueError("odcisk nie zgadza się z kartą: porównaj z ekranem stacji")
        address = card.get("address") if isinstance(card.get("address"), list) else []
        name = station_name(key)

        def add(store):
            store.add_trusted(lxmf, key, (user, other))
            with store.db:
                store.db.execute("INSERT OR REPLACE INTO karty VALUES(?,?,?,?)",
                                 (lxmf, name, json.dumps(address, ensure_ascii=False), fingerprint(key)))
            self._logged(store, user, "zaufana_dodana", f"zgoda {user} i {other}", lxmf)
        self.p.call(add)
        return {"name": name}

    def untrust(self, body):
        user = self.current()
        source = _source(body)

        def remove(store):
            store.remove_trusted(source)
            self._logged(store, user, "zaufana_usunieta", "", source)
        self.p.call(remove)
        return {"ok": True}

    # ---- węzeł, kopie, zmiana -----------------------------------------------------------------

    def announce(self, body):
        user = self.current()
        if self.stos is None:
            raise ValueError("stos nie działa")
        self.stos.announce()
        self.p.action(user, "ogloszenie")
        return {"ok": True}

    def backup(self, body):
        """Copy with the marker „kopia” on the second medium (directory chosen by the officer)."""
        user = self.current()
        directory = Path(_text(body, "path", 1000))
        if not directory.is_dir():
            raise ValueError("nie ma takiego katalogu: podłącz drugi nośnik")

        def copy(store):
            now = self.clock()
            path = kopie.Kopie(directory / "wici-kopie").write(self.medium, self.key, kopie.with_marker(store.db, now), now,
                                                              kopie.frozen_before(store.db))
            self._logged(store, user, "kopia_drugi_nosnik", path.name)
            return path.name
        return {"file": self.p.call(copy)}

    def handover(self, body):
        """Shift handover: optional copy on the second medium, entry in the log, logout."""
        user = self.current()
        result = self.backup(body) if body.get("path") else {}
        self.p.action(user, "przekazanie_zmiany")
        self.logout()
        return result

    def recovery(self, body):
        user = self.current()
        n = body.get("recoveries")
        return {"p": self.p.finish_recovery(user, n, body.get("clock_ok") is True)}

    def new_password(self, body):
        """New envelope password for an account, or the station password (rewraps the medium and the copies).
        Own account by one officer; another account or the station password only with a second officer, or one
        person could take the second password and give consent alone."""
        user = self.current()
        account = _text(body, "account")
        other = self.second(body)[1] if account != user else None
        detail = account + (f", zgoda {other}" if other else "")
        if account != "stanowisko":
            password = self.medium.new_password(account, self.key)
            self.p.action(user, "nowe_haslo", detail)
            return {"account": account, "password": password}

        def change(store):
            # W wątku bazy, więc kopia co 5 min nie wchodzi w środek przepakowania. Hasło wraca zawsze, także
            # gdy kopie się nie przepakują: nośnik ma już nowe opakowanie, a bez hasła nie otworzy się po restarcie.
            password = self.medium.new_station_password(self.key, store.db.serialize())
            failed = None
            if self.p.copies is not None:
                try:
                    self.p.copies.rewrap(self.key, self.medium.kit.recovery())
                except (OSError, database.StorageError) as e:
                    failed = str(e)
            self._logged(store, user, "nowe_haslo", detail + (f"; kopie nieprzepakowane: {failed}" if failed else ""))
            return password, failed
        password, failed = self.p.call(change)
        return {"account": account, "password": password, "copies_failed": failed}

    # ---- zakończenie (S9) --------------------------------------------------------------------------

    def export(self, body):
        """Register to CSV: on the station medium, or to another directory with a second duty officer."""
        user, other = self.current(), None
        if body.get("path"):
            user, other = self.second(body)
            directory = Path(_text(body, "path", 1000))
            if not directory.is_dir():
                raise ValueError("nie ma takiego katalogu: podłącz nośnik")
        else:
            directory = self.medium.root / zamkniecie.EXPORT

        def run(store):
            now = self.clock()
            data = zamkniecie.csv_bytes(zamkniecie.register(store.db))
            path = zamkniecie.write_new(directory, f"rejestr-{zamkniecie.stamp(now)}.csv", data)
            self._logged(store, user, "eksport", path.name + (f", zgoda {other}" if other else ""))
            return str(path)
        return {"file": self.p.call(run)}

    def close(self, body):
        """ZAMKNIJ ZDARZENIE: archive with the register on the medium, then the content of reports goes.
        Returns the archive password once (until D13 sets the administrator key)."""
        user = self.current()
        if body.get("confirm") != "ZAMKNIJ ZDARZENIE":
            raise ValueError("wpisz potwierdzenie: ZAMKNIJ ZDARZENIE")

        def run(store):
            if wysylka.setting(store.db, "zamkniete", None) is not None:
                raise ValueError("zdarzenie jest już zamknięte")
            now = self.clock()
            self._logged(store, user, "zamkniecie")   # przed archiwum: rejestr w archiwum ma ten wpis
            sealed, password = zamkniecie.archive(store.db, now, self.medium.iterations)
            path = zamkniecie.write_new(self.medium.root / zamkniecie.EXPORT,
                                        f"archiwum-{zamkniecie.stamp(now)}.wici", sealed)
            zamkniecie.purge(store.db)
            with store.db:
                store.db.execute("INSERT OR REPLACE INTO settings VALUES('zamkniete', ?)", (now,))
            # Jawne CSV z nośnika: treść zgłoszeń zostaje tylko w archiwum (decyzja autora 2026-10-30).
            removed, left = zamkniecie.remove_exports(self.medium.root / zamkniecie.EXPORT)
            self._logged(store, user, "eksport_usuniety", f"usunięto {len(removed)} plików CSV"
                         + (f"; nie usunięto: {', '.join(left)}" if left else ""))
            return str(path), password
        path, password = self.p.call(run)
        return {"file": path, "password": password}

    def purge_copies(self, body):
        """„Usuń kopie” after the administrator confirmed the archive: copies on the computer disk and, when
        connected, on the second medium."""
        user = self.current()
        who, when = _text(body, "kto"), _text(body, "kiedy")
        if self.p.call(lambda store: wysylka.setting(store.db, "zamkniete", None)) is None:
            raise ValueError("najpierw ZAMKNIJ ZDARZENIE")
        copies = [self.p.copies] if self.p.copies is not None else []
        if body.get("path"):
            copies.append(kopie.Kopie(Path(_text(body, "path", 1000)) / "wici-kopie"))

        def run(store):
            # W wątku bazy: kopia co 5 min nie powstanie między usunięciem a wpisem.
            failed = [name for copy in copies for name in copy.remove()]
            with store.db:
                store.db.execute("INSERT OR REPLACE INTO settings VALUES('kopie_usuniete', ?)", (self.clock(),))
            self._logged(store, user, "kopie_usuniete", f"odbiór archiwum potwierdził {who}, {when}"
                         + (f"; nie usunięto: {', '.join(failed)}" if failed else ""))
            return failed
        return {"failed": self.p.call(run)}

    def destroy(self, body):
        """ZNISZCZ DANE: the database thread stops without a last snapshot, the stack stops, the medium files
        and the copies go; the application ends. Physical destruction of both media decides (instruction)."""
        self.current()
        if body.get("confirm") != "ZNISZCZ DANE":
            raise ValueError("wpisz potwierdzenie: ZNISZCZ DANE")
        self.p.stop(save=False)
        if self.stos is not None:
            self.stos.stop()
        copies = [self.p.copies] if self.p.copies is not None else []
        if body.get("path"):
            copies.append(kopie.Kopie(Path(str(body["path"])) / "wici-kopie"))
        failed = zamkniecie.destroy(self.medium, copies)
        with self.lock:
            self.user, self.key = None, None
        self.on_quit()
        return {"failed": failed}

    # ---- widok --------------------------------------------------------------------------------

    @staticmethod
    def _name(store, source):
        row = store.db.execute("SELECT name FROM karty WHERE source=?", (source,)).fetchone()
        return row[0] if row else source.hex()[:8]

    def view(self):
        """Everything the panel shows, read in the database thread."""
        now = self.clock()
        node = self.stos.status(now) if self.stos is not None else {"online": False, "since_rx": None, "dropped": {}}

        def read(store):
            db = store.db
            names = {s: (n, json.loads(a)) for s, n, a in db.execute("SELECT source, name, address FROM karty")}
            statuses = {}
            for dest, mid, event, state in db.execute("SELECT dest, id, event, state FROM statuses"):
                if event > statuses.get((dest, mid), (0, 0))[0]:
                    statuses[(dest, mid)] = (event, state)
            replies = {(d, m) for d, m in db.execute("SELECT DISTINCT dest, id FROM replies")}
            decisions = {}
            for source, mid, state, detail, at, account in db.execute(
                    "SELECT source, mid, state, detail, at, account FROM decyzje ORDER BY id"):
                decisions.setdefault((source, mid), []).append(
                    {"state": state, "detail": json.loads(detail), "at": at, "account": account})
            newest = {}
            for source, mid, revision, payload, at in db.execute(
                    "SELECT r.source, r.id, r.revision, r.payload, a.at FROM received r "
                    "LEFT JOIN received_at a USING(source, id, revision)"):
                if payload is None:
                    continue   # treść usunięta po ZAMKNIJ ZDARZENIE
                current = newest.get((source, mid))
                if current is None or revision > current[0]:
                    newest[(source, mid)] = (revision, payload, at)
            reports, tests = [], []
            for (source, mid), (revision, payload, at) in newest.items():
                _, kind, _, _, category, people, address, text, urgency = wzorzec.decode_message(payload)
                event, state = statuses.get((source, mid), (1, 1))
                item = {"source": source.hex(), "station": names.get(source, (source.hex()[:8],))[0],
                        "id": mid, "number": short_number(mid), "revision": revision, "category": category,
                        "people": people, "address": address, "text": text, "urgency": urgency, "at": at,
                        "state": state, "reply": (source, mid) in replies,
                        "decisions": decisions.get((source, mid), [])}
                (tests if kind == 5 else reports).append(item)
            reports.sort(key=lambda r: (-r["urgency"], r["at"] or 0))
            tests.sort(key=lambda r: r["at"] or 0)
            quarantine = [{"source": s.hex(), "id": m, "number": short_number(m), "revision": r,
                           "content": wzorzec.decode_message(p)} for s, m, r, p in
                          db.execute("SELECT source, id, revision, payload FROM quarantine ORDER BY rowid")]
            removed = [{"source": s.hex(), "station": names.get(s, (s.hex()[:8],))[0], "messages": n}
                       for s, n in db.execute("SELECT source, messages FROM removed WHERE messages > 0")]
            trusted = [{"source": s.hex(), "station": names.get(s, (s.hex()[:8], []))[0],
                        "address": names.get(s, ("", []))[1]} for (s,) in db.execute("SELECT source FROM trusted")]
            waiting, oldest = db.execute("SELECT count(*), min(first_try) FROM outbox WHERE done=0").fetchone()
            log = [{"at": a, "account": u, "op": o, "detail": d,
                    "station": names[s][0] if s in names else "", "number": short_number(m) if m else ""}
                   for a, u, o, d, s, m in db.execute(
                       "SELECT at, account, op, detail, source, mid FROM dziennik ORDER BY id DESC LIMIT 50")]
            bulletins = []
            for mid, payload, total, done, failed in db.execute(
                    "SELECT id, payload, count(*), sum(done), sum(attempts > 0 AND done = 0) FROM outbox "
                    "WHERE kind=? GROUP BY id ORDER BY min(seq) DESC LIMIT 20", (wysylka.BULLETIN,)):
                bulletins.append({"id": mid, "number": short_number(mid), "text": wzorzec.decode_message(payload)[4] if payload else "",
                                  "total": total, "done": done, "retrying": failed})
            silence = wysylka.setting(db, "cisza", None)
            closed = {"silence": json.loads(silence) if silence else None,
                      "closed": wysylka.setting(db, "zamkniete", None),
                      "copies_purged": wysylka.setting(db, "kopie_usuniete", None)}
            return reports, tests, quarantine, removed, trusted, waiting, oldest, log, bulletins, closed
        reports, tests, quarantine, removed, trusted, waiting, oldest, log, bulletins, closed = self.p.call(read)
        in_flight = len(self.p.wysylka.flight)
        open_reports = [r for r in reports if r["state"] not in (3, 5, 6)]
        return {
            "reports": reports, "tests": tests, "quarantine": quarantine, "removed": removed, "trusted": trusted,
            "node": {**node, "in_flight": in_flight, "waiting": waiting - in_flight if waiting else 0,
                     "oldest_s": None if oldest is None else now - oldest,
                     "diagnostics": self.wezel is not None, "info": self.wezel.status() if self.wezel else None},
            "recovery": self.p.recovery, "copy_age_s": None if self.p.last_copy_at is None else now - self.p.last_copy_at,
            "saved": self.p.save_error is None, "log": log, "bulletins": bulletins, **closed,
            "handover": {"open": len(open_reports), "forwarded_unconfirmed": sum(r["state"] == 4 for r in reports),
                         "unsent": waiting or 0, "quarantine": len(quarantine), "removed_alarm": len(removed)},
        }

    def health(self):
        node = self.stos.status(self.clock()) if self.stos is not None else {"online": False, "dropped": {}}
        return {"app": "wici-stanowisko", "version": VERSION, "saved": self.p.save_error is None,
                "recovery": self.p.recovery, "online": node["online"], "since_rx": node.get("since_rx"),
                "copy_age_s": None if self.p.last_copy_at is None else self.clock() - self.p.last_copy_at,
                "counts": dict(self.p.counts), "dropped": node.get("dropped", {}),
                "node": self.wezel.status() if self.wezel else None}


ROUTES = {
    "/api/operator/login": lambda d, b: (d.login(_text(b, "account"), _text(b, "password")), {"ok": True})[1],
    "/api/operator/logout": lambda d, b: (d.logout(), {"ok": True})[1],
    "/api/operator/touch": lambda d, b: (d.touch(), {"ok": True})[1],
    "/api/operator/status": lambda d, b: d.status(b),
    "/api/operator/tests": lambda d, b: d.read_tests(b),
    "/api/operator/reply": lambda d, b: d.reply(b),
    "/api/operator/bulletin": lambda d, b: d.bulletin(b),
    "/api/operator/silence": lambda d, b: d.silence(b),
    "/api/operator/quarantine": lambda d, b: d.quarantine(b),
    "/api/operator/trust": lambda d, b: d.trust(b),
    "/api/operator/trust/remove": lambda d, b: d.untrust(b),
    "/api/operator/announce": lambda d, b: d.announce(b),
    "/api/operator/backup": lambda d, b: d.backup(b),
    "/api/operator/handover": lambda d, b: d.handover(b),
    "/api/operator/recovery": lambda d, b: d.recovery(b),
    "/api/operator/password": lambda d, b: d.new_password(b),
    "/api/operator/export": lambda d, b: d.export(b),
    "/api/operator/close": lambda d, b: d.close(b),
    "/api/operator/backup/purge": lambda d, b: d.purge_copies(b),
    "/api/operator/destroy": lambda d, b: d.destroy(b),
}


class Panel:
    """HTTP side: tickets for /start, version counter for long polling of /api/operator/queue."""

    def __init__(self, dyzur):
        self.dyzur, self.token = dyzur, secrets.token_urlsafe(32)
        self.tickets, self.version, self.cond, self.server = set(), 0, threading.Condition(), None

    def ticket(self):
        t = secrets.token_urlsafe(24)
        with self.cond:
            self.tickets.add(t)
        return t

    def redeem(self, ticket):
        with self.cond:
            if ticket in self.tickets:
                self.tickets.discard(ticket)
                return True
        return False

    def changed(self):
        with self.cond:
            self.version += 1
            self.cond.notify_all()


def make_handler(panel):
    static = {path: resources.files("wici.stanowisko").joinpath("ui", name).read_bytes()
              for path, (name, _) in STATIC.items()}

    class Handler(web.SecureHandler):
        token = panel.token

        def do_GET(self):
            url = urlsplit(self.path)
            if not self._host_ok():
                return self._send(403, b"host")
            if url.path == "/health":
                return self._json(200, panel.dyzur.health())
            if url.path == "/start":
                return self._start(panel.redeem, url.query)
            if not self._authorized():
                return self._send(403, "Otwórz panel odnośnikiem z aplikacji stanowiska.".encode(),
                                  "text/plain; charset=utf-8")
            if url.path in STATIC:
                return self._send(200, static[url.path], STATIC[url.path][1])
            if url.path == "/api/operator/queue":
                try:
                    since = int(parse_qs(url.query).get("v", ["-1"])[0])
                except ValueError:
                    since = -1
                with panel.cond:
                    if since == panel.version:
                        panel.cond.wait(web.LONG_POLL)
                    version = panel.version
                d = panel.dyzur
                with d.lock:
                    if d.user and d.monotonic() - d.touched > LOCK_S:
                        d.logout("blokada_5_min")
                    user = d.user
                return self._json(200, {"v": version, "user": user, "accounts": d.medium.names(),
                                        **(d.view() if user else {"recovery": d.p.recovery})})
            self._send(404, b"{}")

        def do_POST(self):
            body = self._post_body()
            if body is None:
                return
            route = ROUTES.get(urlsplit(self.path).path)
            if route is None:
                return self._send(404, b"{}")
            try:
                code, value = 200, route(panel.dyzur, body)
            except NotLoggedIn:
                code, value = 401, {"error": "Zaloguj się hasłem z koperty.", "code": "login"}
            except database.LoginError as e:
                code, value = 401, {"error": str(e), "code": "password"}
            except database.StorageError as e:
                code, value = 409, {"error": str(e), "code": "storage"}
            except (ValueError, wysylka.ClockBehind) as e:
                code, value = 400, {"error": str(e), "code": "invalid"}
            except Exception as e:   # noqa: BLE001 - panel zawsze dostaje odpowiedź, nie zerwane połączenie
                code, value = 500, {"error": "Nieoczekiwany błąd aplikacji. Spróbuj ponownie.", "code": type(e).__name__}
            finally:
                panel.changed()
            self._json(code, value)

    return Handler


def serve(panel, port=8090):
    """Bind 127.0.0.1:port, or a free port when it is taken."""
    return web.serve(panel, port, make_handler(panel))
