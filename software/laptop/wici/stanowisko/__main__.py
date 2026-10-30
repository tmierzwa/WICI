# SPDX-License-Identifier: MIT
"""Start the receiving station application (stages S1-S3: stack, reception and sending, without the panel yet).

    python -m wici.stanowisko --port /dev/ttyACM0|COM5 [--stan KATALOG] [--bitrate 42]

Prints one JSON line on stdout: "ready" with the receiver address. The database is baza.sqlite in the
state directory. Logs (Reticulum and reception, never the content of reports) go to stderr. Ends on
Ctrl+C or end of stdin. When the computer clock is earlier than the last numbered message, prints
"clock_behind" and ends with code 2 without starting the stack: the duty officer sets the clock first.
"""

import argparse
import json
import sys
import threading
import time
from pathlib import Path

from .. import store
from .przyjecie import Przyjecie
from .stos import BITRATE, Stos
from .wysylka import ClockBehind


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="wici.stanowisko", description="Aplikacja stanowiska odbiorczego WICI")
    parser.add_argument("--port", required=True, help="port szeregowy stacji stanowiska (węzła)")
    parser.add_argument("--stan", help="katalog stanu (domyślnie: katalog stanu aplikacji / stanowisko)")
    parser.add_argument("--bitrate", type=int, default=BITRATE, help="bitrate interfejsu KISS w konfiguracji Reticulum")
    args = parser.parse_args(argv)
    state = Path(args.stan) if args.stan else store.state_dir() / "stanowisko"
    state.mkdir(parents=True, exist_ok=True)
    przyjecie = None
    stos = Stos(state, args.port, lambda source, content: przyjecie.deliver(source, content), args.bitrate)
    try:
        przyjecie = Przyjecie(state / "baza.sqlite", stos.send, stos.outcome)
    except ClockBehind as e:
        last = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.args[0]))
        emit("clock_behind", last_sent=last,
             message=f"Zegar komputera wskazuje czas wcześniejszy niż ostatnie nadanie ({last}). "
                     "Ustaw zegar według instrukcji dyżurnego i uruchom aplikację ponownie.")
        return 2
    stos.start()
    emit("ready", address=stos.address.hex())
    done = threading.Event()
    threading.Thread(target=lambda: (sys.stdin.read(), done.set()), daemon=True).start()
    try:
        done.wait()
    except KeyboardInterrupt:
        pass
    stos.stop()
    przyjecie.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
