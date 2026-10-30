# SPDX-License-Identifier: MIT
"""Start the receiving station application (stage S1: the stack only).

    python -m wici.stanowisko --port /dev/ttyACM0|COM5 [--stan KATALOG] [--bitrate 42]

Prints one JSON line per event on stdout: "ready" with the receiver address, "message" for every SA1
message (sender, size, signature; never the content, as the shelter laptop log). The Reticulum log goes
to stderr. Ends on Ctrl+C or end of stdin.
"""

import argparse
import json
import sys
import threading

from .. import store
from .stos import BITRATE, Stos


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="wici.stanowisko", description="Aplikacja stanowiska odbiorczego WICI")
    parser.add_argument("--port", required=True, help="port szeregowy stacji stanowiska (węzła)")
    parser.add_argument("--stan", help="katalog stanu (domyślnie: katalog stanu aplikacji / stanowisko)")
    parser.add_argument("--bitrate", type=int, default=BITRATE, help="bitrate interfejsu KISS w konfiguracji Reticulum")
    args = parser.parse_args(argv)
    state = args.stan or store.state_dir() / "stanowisko"
    stos = Stos(state, args.port, lambda source, content, ok: emit(
        "message", **{"from": source.hex(), "bytes": len(content), "signature": ok}), args.bitrate)
    stos.start()
    emit("ready", address=stos.address.hex())
    done = threading.Event()
    threading.Thread(target=lambda: (sys.stdin.read(), done.set()), daemon=True).start()
    try:
        done.wait()
    except KeyboardInterrupt:
        pass
    stos.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
