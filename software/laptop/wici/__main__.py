# SPDX-License-Identifier: MIT
"""Start the application: one instance per laptop, panel in the default browser.

    python -m wici [--port COM5|/dev/ttyACM1|tcp:127.0.0.1:7300] [--http 8080] [--no-browser] [--selftest]

A second START opens the panel of the instance that already runs, with a new one-time link; a lock file held
by the running instance makes a quick double click wait for it instead of starting a second one. Without a
console (pythonw, START-MAC.app) a failed start or browser shows a system message, and a failed start exits
with code 3, so the START programs do not show a second one.
--selftest checks the runtime of the USB package on this system (modules, SQLite, ports, HTTP) and exits;
CI runs it on every system.
"""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser

from . import VERSION, configdoc, serialport, store
from .awake import Awake
from .database import StorageError
from .prep import Prep
from .session import Session, usb_root
from .usbproto import CONTRACT, Station
from .web import Panel, serve


def from_stick():
    """True when START ran the application from the stick, because the copy on the disk did not start
    (WICI_Z_PAMIECI, build/launcher/kopia.sh and start-windows.c): the stick must then stay in."""
    return os.environ.get("WICI_Z_PAMIECI") == "1"


def info():
    """What the panel shows in its footer and the limits it counts while typing (configdoc stays the authority)."""
    return {"version": VERSION, "python": sys.version.split()[0], "platform": sys.platform,
            "contract": CONTRACT, "limits": {"addresses": configdoc.ADDRESSES, "address": configdoc.ADDRESS_MAX,
                                             "phrases": configdoc.PHRASES, "phrase": configdoc.PHRASE_MAX,
                                             "message": configdoc.SA1_MAX, "profiles": list(configdoc.PROFILES)}}


def running_instance(path, usb=None):
    """URL of a panel that already runs on this laptop, or None; usb: the stick this START runs from."""
    try:
        inst = json.loads(path.read_text(encoding="utf-8"))
        base = f"http://127.0.0.1:{int(inst['port'])}"
        direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # bez proxy systemu dla 127.0.0.1
        with direct.open(f"{base}/health", timeout=1) as r:
            if json.loads(r.read().decode()).get("app") != "wici":
                return None
        body = json.dumps({"usb": str(usb)} if usb else {}).encode()
        req = urllib.request.Request(f"{base}/api/ticket", body, {"Cookie": f"wici={inst['token']}",
                                                                 "Content-Type": "application/json"})
        with direct.open(req, timeout=5) as r:
            return f"{base}/start?t={json.loads(r.read().decode())['ticket']}"
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def instance_lock(path):
    """Exclusive lock of the running instance, released by the system also when the process is killed; None when held."""
    f = open(path, "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def alert(text):
    """Message for a person without a console: system dialog where there is one, and stderr."""
    print(f"WICI: {text}", file=sys.stderr, flush=True)
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, "WICI", 0x10)
        elif sys.platform == "darwin":
            subprocess.run(["osascript", "-e", "on run argv", "-e", 'display alert "WICI" message (item 1 of argv)',
                            "-e", "end run", text], timeout=600, capture_output=True)
        elif sys.stderr is not None and sys.stderr.isatty():
            pass                                 # Linux z terminala: komunikat już jest w terminalu
        elif shutil.which("zenity"):
            subprocess.run(["zenity", "--error", "--title=WICI", f"--text={text}"], timeout=600, capture_output=True)
        elif shutil.which("notify-send"):
            subprocess.run(["notify-send", "WICI", text], timeout=10, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        pass


STARTING_S = 30   # s: tyle drugi START czeka na instancję, która się jeszcze uruchamia
REPORTED = 3      # kod wyjścia po błędzie pokazanym przez alert(): programy START nie pokazują drugiego


def write_instance(path, port, token):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"port": port, "token": token, "pid": os.getpid()}), encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(tmp, 0o600)   # token daje dostęp do panelu
    os.replace(tmp, path)


def browse(url):
    try:
        opened = webbrowser.open(url)
    except Exception:   # noqa: BLE001 - webbrowser zgłasza różne wyjątki zależnie od systemu
        opened = False
    if not opened:
        alert(f"Nie udało się otworzyć przeglądarki. Otwórz w niej adres (działa raz):\n{url}")


def database_selftest(tmp):
    """Encrypted database of this runtime: accounts, snapshot on disk and stick, reopening on 'another laptop'."""
    import sqlite3

    from . import database
    (tmp / "usb").mkdir()
    kit, key = database.Kit.create(tmp / "usb" / "keys", {"gospodarz": "las rzeka most okno chleb"}, "odtworzenie",
                                   iterations=1000)
    assert kit.unlock("gospodarz", "Las  Rzeka most okno chleb") == key
    db = database.Database(key, tmp / "dysk", tmp / "usb" / "kopia", kit.recovery(), store.SCHEMA)
    store.Journal(db).add("WICI-000000", "", "selftest", True, "Szkoła nr 5")
    try:
        db.write(lambda c: c.execute("DELETE FROM journal"))
        raise AssertionError("journal accepted DELETE")
    except sqlite3.DatabaseError:
        pass
    db.flush()
    db.hand_back()
    if any(b"Szko" in p.read_bytes() for p in (tmp / "usb" / "kopia").iterdir()) or any((tmp / "dysk").iterdir()):
        raise AssertionError("plain data or snapshots left behind")
    other = database.Database(key, tmp / "inny", tmp / "usb" / "kopia", None, store.SCHEMA)
    rows = store.Journal(other).recent()
    other.close()
    if [r["detail"] for r in rows] != ["Szkoła nr 5"]:
        raise AssertionError(rows)
    return "ok"


def selftest():
    import ctypes
    import hashlib
    import tempfile
    import unicodedata
    from importlib import resources
    from pathlib import Path

    from . import syscrypto
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
    checks.append(f"usb {usb_root()}")   # START uruchamia kopię z dysku i podaje pamięć w WICI_USB
    checks.append(f"z_pamieci {int(from_stick())}")   # 1: kopia na dysku nie uruchomiła się, START użył pamięci
    assert unicodedata.normalize("NFC", "Szkoła") == "Szkoła"
    if configdoc.unicode_warning():                 # tekst sprawdzany inną wersją Unicode niż w stacji
        print(f"WICI: {configdoc.unicode_warning()}", file=sys.stderr, flush=True)
    assert hashlib.sha256(b"").hexdigest().startswith("e3b0c442")
    checks.append(f"crypto {syscrypto.selfcheck()}")
    from . import passwords
    assert len(passwords.generate().split()) == passwords.ACCOUNT_WORDS
    assert configdoc.check({"role": "wezel", "ifac": "11" * 16, "radio": {"profile": "p1"}}) == []
    with tempfile.TemporaryDirectory() as tmp:
        lock = instance_lock(Path(tmp) / "instance.lock")
        assert lock and instance_lock(Path(tmp) / "instance.lock") is None, "lock"
        lock.close()
        checks.append(f"db {database_selftest(Path(tmp))}")
        token = secrets.token_urlsafe(24)
        (Path(tmp) / "zestaw").mkdir()
        session = Session(Path(tmp) / "zestaw", Path(tmp) / "stan", iterations=1000)
        panel = Panel(Station(), None, session, token, info())
        server = serve(panel, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args):
                return None

        opener = urllib.request.build_opener(NoRedirect)
        try:
            opener.open(f"{base}/start?t={panel.ticket()}", timeout=5)
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

        def post(path, value):
            req = urllib.request.Request(f"{base}{path}", json.dumps(value).encode(),
                                         {"Cookie": cookie, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())

        envelopes = post("/api/kit/create", {"deputies": 1})["envelopes"]
        assert [e["account"] for e in envelopes] == ["gospodarz", "zastepca-1", "odtworzenie"]
        post("/api/logout", {})
        post("/api/login", {"account": "zastepca-1", "password": envelopes[1]["password"]})
        assert session.user == "zastepca-1"
        checks.append("panel ok")
        server.shutdown()
        server.server_close()
        session.close()
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
    try:
        return run(args)
    except Exception as e:   # noqa: BLE001 - bez konsoli błąd startu byłby niewidoczny
        traceback.print_exc()
        alert(f"Aplikacja nie uruchomiła się: {e}. Uruchom START ponownie albo użyj innego laptopa.")
        return REPORTED


def claim(instance, usb):
    """(URL of the panel that already runs, None), or (None, lock) when this process becomes the instance.

    The running instance holds the lock; while it is still starting (a quick second double click, a login
    holding the session) there is neither a lock nor an answer, so the second START waits for it."""
    for _ in range(STARTING_S):
        url = running_instance(instance, usb)
        if url:
            return url, None
        lock = instance_lock(instance.with_name("instance.lock"))
        if lock:
            return None, lock
        time.sleep(1)
    raise RuntimeError("inna instancja aplikacji na tym laptopie nie odpowiada")


def run(args):
    state = store.state_dir()
    instance = state / "instance.json"
    usb = usb_root()
    url, lock = claim(instance, usb)
    if url:
        if not args.no_browser:
            browse(url)
        print(url)
        return 0
    token = secrets.token_urlsafe(24)
    panel = Panel(None, None, None, token, info())
    if usb is None:                              # uruchomienie ze źródeł: pamięć zestawu udaje katalog stanu
        usb = state / "pamiec-usb"
        usb.mkdir(exist_ok=True)
        print(f"WICI: brak pamięci USB zestawu, konta i kopia w {usb}", flush=True)
    panel.session = Session(usb, state, on_change=panel.changed)
    station = Station(args.port, on_change=panel.changed)
    panel.station, panel.prep = station, Prep(station, panel.session, on_change=panel.changed)
    server = serve(panel, args.http)
    port = server.server_address[1]
    write_instance(instance, port, token)
    awake = Awake()
    station.start()
    url = f"http://127.0.0.1:{port}/start?t={panel.ticket()}"
    print(f"WICI {VERSION}: panel {url}", flush=True)
    if not args.no_browser:
        threading.Thread(target=browse, args=(url,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        station.stop()
        awake.release()
        server.server_close()
        try:
            panel.session.close()
        except StorageError as e:
            print(f"WICI: ostatnia kopia bazy nie została zapisana: {e}", file=sys.stderr, flush=True)
        try:
            instance.unlink()
        except OSError:
            pass
        lock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
