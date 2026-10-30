# SPDX-License-Identifier: MIT
"""Start the receiving station application (stages S1-S2: stack and reception, without the panel yet).

    python -m wici.stanowisko --port /dev/ttyACM0|COM5 [--stan KATALOG] [--bitrate 42]

Prints one JSON line on stdout: "ready" with the receiver address. The database is baza.sqlite in the
state directory. Logs (Reticulum and reception, never the content of reports) go to stderr. Ends on
Ctrl+C or end of stdin.
"""

import argparse
import json
import sys
import threading
from pathlib import Path

from .. import store
from .przyjecie import Przyjecie
from .stos import BITRATE, Stos


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
    przyjecie = Przyjecie(state / "baza.sqlite", stos.send)
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
