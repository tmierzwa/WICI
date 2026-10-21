# SPDX-License-Identifier: MIT
"""Start the application: one instance per laptop, panel in the default browser.

    python -m wici [--port COM5|/dev/ttyACM1|tcp:127.0.0.1:7300] [--http 8080] [--no-browser] [--selftest]

A second START opens the panel of the instance that already runs. --selftest checks the runtime of
the USB package on this system (modules, SQLite, ports, HTTP) and exits; CI runs it on every system.
"""

import argparse
import json
import os
import secrets
import sys
import threading
import urllib.error
import urllib.request
import webbrowser

from . import VERSION, serialport, store
from .awake import Awake
from .prep import Prep
from .usbproto import Station
from .web import Panel, serve


def info():
    return {"version": VERSION, "python": sys.version.split()[0], "platform": sys.platform}


def running_instance(path):
    """URL of a panel that already runs on this laptop, or None."""
    try:
        inst = json.loads(path.read_text(encoding="utf-8"))
        direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # bez proxy systemu dla 127.0.0.1
        with direct.open(f"http://127.0.0.1:{int(inst['port'])}/health", timeout=1) as r:
            if json.loads(r.read().decode()).get("app") == "wici":
                return f"http://127.0.0.1:{int(inst['port'])}/start?t={inst['token']}"
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def write_instance(path, port, token):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"port": port, "token": token, "pid": os.getpid()}), encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(tmp, 0o600)   # token daje dostęp do panelu
    os.replace(tmp, path)


def open_browser(url):
    threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()


def selftest():
    import ctypes
    import hashlib
    import sqlite3
    import tempfile
    import unicodedata
    from importlib import resources
    from pathlib import Path

    from . import configdoc, syscrypto
    from .web import STATIC
    checks = []
    for _, (name, _) in STATIC.items():
        assert resources.files("wici").joinpath("ui", name).read_bytes(), name
    assert ctypes.sizeof(serialport.DCB) == 28 and ctypes.sizeof(serialport.COMMTIMEOUTS) == 20
    if sys.platform == "win32":
        import winreg  # noqa: F401
        from ctypes import wintypes  # noqa: F401
        ctypes.WinDLL("kernel32", use_last_error=True)
    checks.append(f"ports {serialport.candidates()}")
    station = Station()
    station._connect()                      # sondowanie portów jak przy starcie, bez wątku
    checks.append(f"phase {station.state['phase']}")
    import subprocess
    import webbrowser  # noqa: F401
    subprocess.run([sys.executable, "-c", "pass"], check=True, timeout=30)
    checks.append(f"stdlib {os.path.normpath(next((p for p in sys.path if p.endswith('.zip')), '-'))}")
    assert unicodedata.normalize("NFC", "Szkoła") == "Szkoła"
    assert hashlib.sha256(b"").hexdigest().startswith("e3b0c442")
    checks.append(f"crypto {syscrypto.selfcheck()}")
    assert configdoc.check({"role": "wezel", "ifac": "11" * 16, "radio": {"profile": "p1"}}) == []
    with tempfile.TemporaryDirectory() as tmp:
        journal = store.Journal(Path(tmp) / "j.sqlite")
        journal.add("WICI-000000", "", "selftest", True)
        try:
            journal.db.execute("DELETE FROM journal")
            raise AssertionError("journal accepted DELETE")
        except sqlite3.DatabaseError:
            pass
        token = secrets.token_urlsafe(24)
        panel = Panel(Station(), None, journal, token, info())
        server = serve(panel, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args):
                return None

        opener = urllib.request.build_opener(NoRedirect)
        try:
            opener.open(f"{base}/start?t={token}", timeout=5)
            raise AssertionError("no redirect")
        except urllib.error.HTTPError as e:
            assert e.code == 303
            cookie = e.headers["Set-Cookie"].split(";")[0]
        req = urllib.request.Request(f"{base}/api/state?v=-1", headers={"Cookie": cookie})
        with urllib.request.urlopen(req, timeout=5) as r:
            assert json.loads(r.read())["station"]["phase"] == "searching"
        body = json.dumps({"doc": {"role": "wezel", "ifac": "AB" * 16, "radio": {"profile": "p1"}}}).encode()
        req = urllib.request.Request(f"{base}/api/config/check", body, {"Cookie": cookie, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            assert json.loads(r.read())["problems"] == []
        server.shutdown()
        server.server_close()
        journal.close()
    print("selftest ok", info(), *checks)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="wici", description="Przygotowanie stacji WICI")
    parser.add_argument("--port", help="port stacji (bez niego: wyszukiwanie)")
    parser.add_argument("--http", type=int, default=8080, help="port panelu na 127.0.0.1")
    parser.add_argument("--no-browser", action="store_true", help="nie otwieraj przeglądarki")
    parser.add_argument("--selftest", action="store_true", help="sprawdź środowisko i zakończ")
    for stream in (sys.stdout, sys.stderr):      # pythonw: brak konsoli; Windows: cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    state = store.state_dir()
    instance = state / "instance.json"
    url = running_instance(instance)
    if url:
        if not args.no_browser:
            webbrowser.open(url)
        print(url)
        return 0
    journal = store.Journal(state / "dziennik.sqlite")
    token = secrets.token_urlsafe(24)
    panel = Panel(None, None, journal, token, info())
    station = Station(args.port, on_change=panel.changed)
    panel.station, panel.prep = station, Prep(station, journal)
    server = serve(panel, args.http)
    port = server.server_address[1]
    write_instance(instance, port, token)
    awake = Awake()
    station.start()
    url = f"http://127.0.0.1:{port}/start?t={token}"
    print(f"WICI {VERSION}: panel {url}", flush=True)
    if not args.no_browser:
        open_browser(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        station.stop()
        awake.release()
        server.server_close()
        journal.close()
        try:
            instance.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
