# SPDX-License-Identifier: MIT
"""The receiving station application (stages S1-S7: stack, reception, sending, medium, copies, recovery, panel).

    python -m wici.stanowisko przygotuj --nosnik KATALOG --dyzurni 4 --paczka PLIK --karta PLIK
    python -m wici.stanowisko start --nosnik KATALOG --port /dev/ttyACM0|COM5 [--bitrate 41]
    python -m wici.stanowisko odtworz --nosnik PUSTY_KATALOG [--kopie KATALOG ...]
    python -m wici.stanowisko nowa-tozsamosc --nosnik KATALOG --karta NOWY_PLIK
    python -m wici.stanowisko aktywuj-tozsamosc --nosnik KATALOG --karta PLIK --karta-na-stacjach
    python -m wici.stanowisko aktywuj-zapasowa --nosnik PUSTY_KATALOG --dyzurni 4 --paczka PLIK --karta PLIK

przygotuj (preparation of the station, on a computer without a network; stanowisko-osp.md, „Przygotowanie”):
makes the medium (accounts of the duty officers, station password, main identity), the backup identity
only in memory, written as a package sealed with its own password to --paczka (for the envelope off the
station, never on the medium), and the receiver card for the stations to --karta. Prints "envelopes" once:
every password with its envelope.

start: reads the station password (first line of stdin, or typed without echo at a terminal), prints one
JSON line "ready" with the receiver address and the one-time link of the duty officer panel (opened in
the browser; panel.py), and writes a copy of the database to the computer disk every
5 min (kopie.py) and works until Ctrl+C or end of stdin. Logs (Reticulum and
reception, never the content of reports or passwords) go to stderr. A wrong password prints "login_failed"
and ends with code 3. When the computer clock is earlier than the last numbered message, prints
"clock_behind" and ends with code 2 without starting the stack: the duty officer sets the clock first.
A medium restored from a copy starts in the recovery mode ("ready" with "recovery": true): no sending until
the duty officer confirms the clock and the number of recoveries (panel, stage S7).

odtworz (damaged medium, stanowisko-osp.md, „Nośnik i szyfrowanie”): reads from stdin the station password
and two lines "konto hasło" of two different duty officers, takes the newest copy that the password opens
(computer disk first, then the given directories, e.g. the second medium) and writes it to the empty medium.

nowa-tozsamosc, aktywuj-tozsamosc (stanowisko-osp.md, „Wysyłka”, recovery step 3; rekey.py): with the application
stopped, the same three stdin lines as odtworz; a fresh receiver identity and card, then the end of the WICI-Link
sending block once the stations have the card.
aktywuj-zapasowa (takeover of the station, stanowisko-osp.md, „Tożsamość zapasowa”; rekey.py): reads the package
password from stdin and puts the backup identity on a new medium with new accounts, the card the stations hold
and, for a numbered card, the WICI-Link settings. Prints "envelopes" once, with "guarded": a package used before
starts with WICI-Link sending blocked until nowa-tozsamosc and aktywuj-tozsamosc.
"""

import argparse
import getpass
import json
import sys
import threading
import time
import webbrowser
from pathlib import Path

from .. import configdoc, database, passwords, store
from . import bearers, kopie, nosnik, panel, wezel, zamkniecie
from .przyjecie import Przyjecie
from .stos import BITRATE, Stos
from .wici_stos import WiciStos
from .wysylka import ClockBehind


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def write_new(path, doc):
    """A new file only: an existing package or card is never overwritten."""
    with open(path, "x", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)


def prepare(args):
    if args.net_id is None and (args.root_id is not None or args.ifac is not None):
        raise SystemExit("--root-id i --ifac wymagają --net-id")
    import RNS
    main_identity, backup_identity = RNS.Identity(), RNS.Identity()
    for path in (args.paczka, args.karta):
        if Path(path).exists():
            raise SystemExit(f"plik już istnieje: {path}")
    if Path(args.paczka).resolve().is_relative_to(Path(args.nosnik).resolve()):
        raise SystemExit("paczka zapasowa nie może leżeć na nośniku stanowiska")
    card = nosnik.receiver_card(main_identity.get_public_key(), backup_identity.get_public_key(),
                                args.net_id, args.main_id, args.backup_id)
    link = None
    if args.net_id is not None:
        if args.root_id is None or args.ifac is None:
            raise SystemExit("numerowana sieć wymaga --root-id i --ifac")
        if args.root_id in (args.main_id, args.backup_id):
            raise SystemExit("numer korzenia musi być różny od numerów odbiorcy")
        try:
            link = nosnik.validate_link({"net_id": args.net_id, "root": args.root_id, "ifac": args.ifac,
                                         "ttl": args.ttl})
        except database.StorageError as exc:
            raise SystemExit(str(exc)) from None
    medium, _, envelopes = nosnik.Nosnik.create(args.nosnik, args.dyzurni, main_identity.get_private_key(),
                                                args.iteracje, card=card, link=link)
    backup_password = passwords.generate(nosnik.BACKUP_WORDS)
    write_new(args.paczka, nosnik.backup_package(backup_identity.get_private_key(), backup_identity.get_public_key(),
                                                 backup_password, args.iteracje))
    write_new(args.karta, card)
    emit("envelopes", envelopes={**envelopes, "paczka-zapasowa": backup_password}, card=card)
    return 0


def read_password():
    if sys.stdin.isatty():
        return getpass.getpass("Hasło stanowiska: ")
    return sys.stdin.readline().strip()


def start(args):
    medium = nosnik.Nosnik(args.nosnik)
    try:
        key = medium.unlock(read_password())
        identity_key = medium.identity(key)
    except (database.LoginError, database.StorageError) as e:
        emit("login_failed", message=str(e))
        return 3
    przyjecie = None
    try:
        link = medium.link(key)
        card = medium.card(key)
    except database.StorageError as exc:
        emit("login_failed", message=str(exc))
        return 3
    if args.reticulum_port and link is None:
        emit("login_failed", message="dodatkowy port wymaga numerowanego nośnika WICI-Link")
        return 3
    if link is not None:
        if args.reticulum_port == args.port:
            emit("login_failed", message="port Reticulum musi być inny niż port WICI-Link")
            return 3
        active = nosnik.card_entry(card, identity_key)
        if active is None or active.get("net_id") != link["net_id"] or active["id"] == link["root"]:
            emit("login_failed", message="tożsamość odbiorcy i ustawienia WICI-Link nie są zgodne")
            return 3
        numbered = WiciStos(args.port, link["net_id"], link["root"], link["ttl"], bytes.fromhex(link["ifac"]),
                            bytes.fromhex(active["lxmf"]),
                            lambda frame: przyjecie.receive_envelope_frame(link["net_id"], frame,
                                                                             bearer="wici"))
        if args.reticulum_port:
            legacy = Stos(medium.network, args.reticulum_port,
                          lambda source, content: przyjecie.deliver(source, content, bearer="reticulum"),
                          identity_key, args.bitrate)
            stos = bearers.Bearers({"wici": numbered, "reticulum": legacy}, "wici")
            send = stos.send
        else:
            stos = numbered
            send = lambda dest, content: przyjecie.send_wici(stos, dest, content)
    elif card and card.get("v") == 2:
        emit("login_failed", message="brak klucza WICI-Link na numerowanym nośniku")
        return 3
    else:
        stos = Stos(medium.network, args.port, lambda source, content: przyjecie.deliver(source, content),
                    identity_key, args.bitrate)
        send = stos.send
    try:
        copies = kopie.Kopie(Path(args.kopie) if args.kopie else kopie.disk_dir(store.state_dir() / "stanowisko", medium))
        przyjecie = Przyjecie(medium, key, send, stos.outcome, copies=copies, announce=stos.announce,
                              online=lambda: stos.status(time.time())["online"])
        if isinstance(stos, bearers.Bearers):
            stos.reception = przyjecie
    except ClockBehind as e:
        last = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.args[0]))
        emit("clock_behind", last_sent=last,
             message=f"Zegar komputera wskazuje czas wcześniejszy niż ostatnie nadanie ({last}). "
                     "Ustaw zegar według instrukcji dyżurnego i uruchom aplikację ponownie.")
        return 2
    przyjecie.action("", "start")
    stos.start()
    dyzur = panel.Dyzur(przyjecie, medium, key, stos)
    diagnostics = None if args.diagnostyka == "brak" else args.diagnostyka or (
        None if args.port.startswith("tcp:") else wezel.find_diagnostics(args.port))
    if diagnostics:
        dyzur.wezel = wezel.Wezel(diagnostics, lambda silence, first: przyjecie.action(
            "", "cisza_wezel", json.dumps({"silence": silence, "start": first}))).start()
    web = panel.Panel(dyzur)
    server = panel.serve(web, args.panel)
    threading.Thread(target=server.serve_forever, daemon=True, name="panel").start()
    url = f"http://127.0.0.1:{server.server_address[1]}/start?t={web.ticket()}"
    emit("ready", address=stos.address.hex(), recovery=przyjecie.recovery, panel=url, diagnostics=diagnostics)
    if not args.bez_przegladarki:
        webbrowser.open(url)
    done = threading.Event()
    dyzur.on_quit = done.set   # ZNISZCZ DANE
    threading.Thread(target=lambda: (sys.stdin.read(), done.set()), daemon=True).start()
    try:
        done.wait()
    except KeyboardInterrupt:
        pass
    server.shutdown()
    if dyzur.wezel is not None:
        dyzur.wezel.stop()
    stos.stop()
    przyjecie.stop()
    return 0


def restore(args):
    lines = [sys.stdin.readline().strip() for _ in range(3)]
    approvers = [tuple(line.split(" ", 1)) for line in lines[1:] if " " in line]
    directories = [Path(store.state_dir() / "stanowisko" / "kopie")] + [Path(d) for d in args.kopie]
    try:
        path, key = kopie.find(directories, lines[0])
        kopie.restore(path, key, args.nosnik, approvers, time.time())
    except (database.LoginError, database.StorageError) as e:
        emit("restore_failed", message=str(e))
        return 3
    emit("restored", copy=path.name, at=kopie.Kopie.read(path, key)[0])
    return 0


def receiver_rekey(args):
    """Run only while the receiver application is stopped."""
    from . import rekey
    lines = [sys.stdin.readline().strip() for _ in range(3)]
    approvers = [tuple(line.split(" ", 1)) for line in lines[1:] if " " in line]
    medium = nosnik.Nosnik(args.nosnik)
    try:
        key = medium.unlock(lines[0])
        if args.command == "nowa-tozsamosc":
            card = rekey.stage(medium, key, approvers, args.karta)
            emit("identity_staged", card=str(args.karta), main_id=card["main"]["id"])
        else:
            if not args.karta_na_stacjach:
                raise database.StorageError("najpierw zainstaluj nową kartę na stacjach (--karta-na-stacjach)")
            card = rekey.activate(medium, key, approvers, args.karta)
            emit("identity_activated", main_id=card["main"]["id"])
    except (database.LoginError, database.StorageError, OSError) as exc:
        emit("identity_failed", message=str(exc))
        return 3
    return 0


def activate_backup(args):
    from . import rekey
    password = sys.stdin.readline().strip()
    try:
        card = json.loads(Path(args.karta).read_text(encoding="utf-8"))
        link = None if args.ifac is None else {
            "net_id": card["backup"]["net_id"], "root": args.root_id, "ifac": args.ifac, "ttl": args.ttl}
        _, _, envelopes, guarded = rekey.activate_backup(args.paczka, password, args.nosnik, args.dyzurni, card,
                                                         link, args.iteracje)
    except (database.LoginError, database.StorageError, OSError, ValueError, KeyError, TypeError) as exc:
        emit("backup_failed", message=str(exc))
        return 3
    emit("envelopes", envelopes=envelopes, guarded=guarded)
    return 0


def open_archive(args):
    """For the data administrator: the archive of a closed event to a new directory."""
    try:
        zamkniecie.open_archive(args.plik, sys.stdin.readline().strip(), args.do)
    except (database.LoginError, database.StorageError, FileExistsError) as e:
        emit("archive_failed", message=str(e))
        return 3
    emit("archive_opened", directory=str(args.do))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="wici.stanowisko", description="Aplikacja stanowiska odbiorczego WICI")
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("przygotuj", help="przygotowanie nośnika stanowiska, paczki zapasowej i karty")
    prep.add_argument("--nosnik", required=True, help="katalog na nośniku stanowiska (dysk USB SSD)")
    prep.add_argument("--dyzurni", type=int, required=True, help="liczba kont dyżurnych")
    prep.add_argument("--paczka", required=True, help="nowy plik paczki tożsamości zapasowej (poza nośnikiem)")
    prep.add_argument("--karta", required=True, help="nowy plik karty odbiorcy dla stacji")
    prep.add_argument("--net-id", type=int, help="numer sieci WICI (1..65534)")
    prep.add_argument("--main-id", type=int, help="numer głównej tożsamości odbiorcy")
    prep.add_argument("--backup-id", type=int, help="numer zapasowej tożsamości odbiorcy")
    prep.add_argument("--root-id", type=int, help="numer radiowego węzła stanowiska")
    prep.add_argument("--ifac", help="16 bajtów kodu sieci WICI w zapisie hex")
    prep.add_argument("--ttl", type=int, default=configdoc.TTL_DEFAULT,
                      help="limit skoków ramek stanowiska w dół (1..15, jak network.ttl stacji)")
    prep.add_argument("--iteracje", type=int, default=database.ITERATIONS, help=argparse.SUPPRESS)
    run = commands.add_parser("start", help="praca stanowiska")
    run.add_argument("--nosnik", required=True, help="katalog na nośniku stanowiska")
    run.add_argument("--port", required=True, help="port szeregowy stacji stanowiska (węzła); tcp:<host>:<port> dla świata symulatora")
    run.add_argument("--bitrate", type=int, default=BITRATE, help="bitrate interfejsu KISS w konfiguracji Reticulum")
    run.add_argument("--reticulum-port", help="opcjonalny drugi port KISS Reticulum obok numerowanego WICI-Link")
    run.add_argument("--panel", type=int, default=8090, help="port panelu dyżurnego na 127.0.0.1")
    run.add_argument("--bez-przegladarki", action="store_true", help="nie otwieraj panelu w przeglądarce")
    run.add_argument("--diagnostyka", help="port diagnostyki węzła (drugi interfejs USB; domyślnie odszukany "
                     "obok --port; „brak” wyłącza; dla świata symulatora tcp:127.0.0.1:7391)")
    run.add_argument("--kopie", help="katalog kopii co 5 min na dysku komputera (domyślnie: katalog stanu aplikacji)")
    back = commands.add_parser("odtworz", help="odtworzenie nośnika z kopii (zgoda dwóch dyżurnych)")
    back.add_argument("--nosnik", required=True, help="pusty katalog na nowym nośniku stanowiska")
    back.add_argument("--kopie", action="append", default=[], help="dodatkowy katalog kopii, np. drugi nośnik")
    for name, purpose in (("nowa-tozsamosc", "nowa tożsamość odbiorcy po odzyskaniu (zgoda dwóch dyżurnych)"),
                          ("aktywuj-tozsamosc", "koniec blokady nadawania WICI-Link po instalacji nowej karty")):
        operation = commands.add_parser(name, help=purpose)
        operation.add_argument("--nosnik", required=True, help="katalog na nośniku stanowiska")
        operation.add_argument("--karta", required=True, help="plik nowej karty odbiorcy")
        if name == "aktywuj-tozsamosc":
            operation.add_argument("--karta-na-stacjach", action="store_true",
                                   help="potwierdzenie, że wszystkie numerowane stacje mają nową kartę")
    spare = commands.add_parser("aktywuj-zapasowa", help="tożsamość zapasowa z paczki na nowym nośniku")
    spare.add_argument("--nosnik", required=True, help="pusty katalog na nowym nośniku stanowiska")
    spare.add_argument("--dyzurni", type=int, required=True, help="liczba nowych kont dyżurnych")
    spare.add_argument("--paczka", required=True, help="plik paczki tożsamości zapasowej (zapisywalny: oznaczenie użycia)")
    spare.add_argument("--karta", required=True, help="plik karty odbiorcy, którą mają stacje")
    spare.add_argument("--root-id", type=int, help="numer radiowego węzła stanowiska (karta numerowana)")
    spare.add_argument("--ifac", help="16 bajtów kodu sieci WICI w zapisie hex (karta numerowana)")
    spare.add_argument("--ttl", type=int, default=configdoc.TTL_DEFAULT, help="limit skoków ramek stanowiska w dół")
    spare.add_argument("--iteracje", type=int, default=database.ITERATIONS, help=argparse.SUPPRESS)
    arch = commands.add_parser("archiwum", help="otwarcie archiwum zamkniętego zdarzenia (hasło archiwum na wejściu)")
    arch.add_argument("--plik", required=True, help="plik archiwum .wici")
    arch.add_argument("--do", required=True, help="katalog na baza.sqlite i rejestr.csv")
    args = parser.parse_args(argv)
    return {"przygotuj": prepare, "start": start, "odtworz": restore, "nowa-tozsamosc": receiver_rekey,
            "aktywuj-tozsamosc": receiver_rekey, "aktywuj-zapasowa": activate_backup,
            "archiwum": open_archive}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
