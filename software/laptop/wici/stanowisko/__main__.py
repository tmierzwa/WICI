# SPDX-License-Identifier: MIT
"""The receiving station application (stages S1-S7: stack, reception, sending, medium, copies, recovery, panel).

    python -m wici.stanowisko przygotuj --nosnik KATALOG --dyzurni 4 --paczka PLIK --karta PLIK
    python -m wici.stanowisko start --nosnik KATALOG --port /dev/ttyACM0|COM5 [--bitrate 41]
    python -m wici.stanowisko odtworz --nosnik PUSTY_KATALOG [--kopie KATALOG ...]

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
"""

import argparse
import getpass
import json
import sys
import threading
import time
import webbrowser
from pathlib import Path

from .. import database, passwords, store
from . import kopie, nosnik, panel, wezel, zamkniecie
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
            link = nosnik.validate_link({"net_id": args.net_id, "root": args.root_id, "ifac": args.ifac})
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
    if link is not None:
        from cryptography.hazmat.primitives.asymmetric import x25519
        own_public = x25519.X25519PrivateKey.from_private_bytes(identity_key[:32]).public_key().public_bytes_raw().hex()
        active = next((entry for entry in (card.get("main"), card.get("backup"))
                       if isinstance(entry, dict) and entry.get("x25519") == own_public), None) if card else None
        if active is None or active.get("net_id") != link["net_id"] or active["id"] == link["root"]:
            emit("login_failed", message="tożsamość odbiorcy i ustawienia WICI-Link nie są zgodne")
            return 3
        stos = WiciStos(args.port, link["net_id"], link["root"], bytes.fromhex(link["ifac"]),
                        bytes.fromhex(active["lxmf"]),
                        lambda frame: przyjecie.receive_envelope_frame(link["net_id"], frame))
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
    prep.add_argument("--iteracje", type=int, default=database.ITERATIONS, help=argparse.SUPPRESS)
    run = commands.add_parser("start", help="praca stanowiska")
    run.add_argument("--nosnik", required=True, help="katalog na nośniku stanowiska")
    run.add_argument("--port", required=True, help="port szeregowy stacji stanowiska (węzła); tcp:<host>:<port> dla świata symulatora")
    run.add_argument("--bitrate", type=int, default=BITRATE, help="bitrate interfejsu KISS w konfiguracji Reticulum")
    run.add_argument("--panel", type=int, default=8090, help="port panelu dyżurnego na 127.0.0.1")
    run.add_argument("--bez-przegladarki", action="store_true", help="nie otwieraj panelu w przeglądarce")
    run.add_argument("--diagnostyka", help="port diagnostyki węzła (drugi interfejs USB; domyślnie odszukany "
                     "obok --port; „brak” wyłącza; dla świata symulatora tcp:127.0.0.1:7391)")
    run.add_argument("--kopie", help="katalog kopii co 5 min na dysku komputera (domyślnie: katalog stanu aplikacji)")
    back = commands.add_parser("odtworz", help="odtworzenie nośnika z kopii (zgoda dwóch dyżurnych)")
    back.add_argument("--nosnik", required=True, help="pusty katalog na nowym nośniku stanowiska")
    back.add_argument("--kopie", action="append", default=[], help="dodatkowy katalog kopii, np. drugi nośnik")
    arch = commands.add_parser("archiwum", help="otwarcie archiwum zamkniętego zdarzenia (hasło archiwum na wejściu)")
    arch.add_argument("--plik", required=True, help="plik archiwum .wici")
    arch.add_argument("--do", required=True, help="katalog na baza.sqlite i rejestr.csv")
    args = parser.parse_args(argv)
    return {"przygotuj": prepare, "start": start, "odtworz": restore, "archiwum": open_archive}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
