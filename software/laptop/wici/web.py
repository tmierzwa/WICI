# SPDX-License-Identifier: MIT
"""Local panel: HTTP on 127.0.0.1 only, opened in the default browser of the laptop.

Access needs the session token in an HttpOnly, SameSite=Strict cookie, and station operations a login
with an envelope password (session.Session), because they write to the journal in the encrypted database. The launcher opens
/start?t=<ticket>; a ticket works once, so the browser history does not reveal a working link, and a
second START asks the running instance for a new one (POST /api/ticket with the session token) and
names the stick it runs from, which may come back under another drive letter. The Host header must name the loopback address (no DNS rebinding) and every
POST must carry JSON with a loopback Origin, so another web page in the same browser cannot drive
the station. Static files are read from the package, also when it runs from a zip archive.
"""

import hmac
import json
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlsplit

from . import VERSION, configdoc, database
from .prep import OperationError
from .session import NotLoggedIn

STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8"), "/logo.svg": ("logo.svg", "image/svg+xml"),
          "/logo-dark.svg": ("logo-dark.svg", "image/svg+xml")}
BODY_MAX = 64 * 1024
LONG_POLL = 20


class Panel:
    """State shared by request handlers: version counter for long polling and the operations."""

    def __init__(self, station, prep, session, token, info):
        self.station, self.prep, self.session, self.token, self.info = station, prep, session, token, info
        self.version = 0
        self.tickets = set()
        self.cond = threading.Condition()
        self.server = None

    def ticket(self):
        """One-time START link argument."""
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

    def snapshot(self, since):
        with self.cond:
            if since == self.version:
                self.cond.wait(LONG_POLL)
            version = self.version
        return {"v": version, "station": self.station.state, "session": self.session.describe(),
                "journal": self.session.recent(), "destroy": self.prep.destroy_state if self.prep else None,
                "app": self.info}


def make_handler(panel):
    static = {path: resources.files("wici").joinpath("ui", name).read_bytes() for path, (name, _) in STATIC.items()}

    class Handler(BaseHTTPRequestHandler):
        server_version = "WICI/" + VERSION
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass   # dziennik aplikacji nie zapisuje żądań

        def _send(self, code, body=b"", ctype="application/json; charset=utf-8", headers=()):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; object-src 'none'; "
                                                        "base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            for k, v in headers:
                self.send_header(k, v)
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, code, value):
            self._send(code, json.dumps(value, ensure_ascii=False).encode("utf-8"))

        def _host_ok(self):
            port = self.server.server_address[1]
            return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def _authorized(self):
            for part in self.headers.get("Cookie", "").split(";"):
                name, _, value = part.strip().partition("=")
                if name == "wici" and hmac.compare_digest(value.encode(), panel.token.encode()):
                    return True
            return False

        def do_GET(self):
            url = urlsplit(self.path)
            if not self._host_ok():
                return self._send(403, b"host")
            if url.path == "/health":
                return self._json(200, {"app": "wici", "version": VERSION})
            if url.path == "/start":
                if not panel.redeem(parse_qs(url.query).get("t", [""])[0]):
                    return self._send(403, "Nieważny odnośnik. Uruchom START ponownie.".encode(), "text/plain; charset=utf-8")
                cookie = f"wici={panel.token}; HttpOnly; SameSite=Strict; Path=/"
                return self._send(303, headers=[("Location", "/"), ("Set-Cookie", cookie)])
            if not self._authorized():
                return self._send(403, "Otwórz panel przez START.".encode(), "text/plain; charset=utf-8")
            if url.path in STATIC:
                return self._send(200, static[url.path], STATIC[url.path][1])
            if url.path == "/api/state":
                try:
                    since = int(parse_qs(url.query).get("v", ["-1"])[0])
                except ValueError:
                    since = -1
                return self._json(200, panel.snapshot(since))
            self._send(404, b"{}")

        do_HEAD = do_GET

        def do_POST(self):
            # Odpowiedź bez odczytu treści: połączenie zamykane, żeby reszta treści nie stała się następnym żądaniem.
            self.close_connection = True
            if not self._host_ok() or not self._authorized():
                return self._send(403, b"{}")
            origin = self.headers.get("Origin")
            port = self.server.server_address[1]
            if origin not in (None, f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return self._send(403, b"{}")
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._send(415, b"{}")
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = BODY_MAX + 1
            if not 0 <= length <= BODY_MAX:
                return self._send(413, b"{}")
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            except (UnicodeDecodeError, ValueError):
                return self._send(400, b"{}")
            self.close_connection = False
            path = urlsplit(self.path).path
            route = ROUTES.get(path)
            if route is None or not isinstance(body, dict):
                return self._send(404, b"{}")
            try:
                if path in NEEDS_LOGIN and not panel.session.user:
                    raise NotLoggedIn()
                result = route(panel, body)
            except OperationError as e:
                return self._json(409, {"error": e.message, "field": e.field, "code": e.code})
            except NotLoggedIn:
                return self._json(401, {"error": "Zaloguj się hasłem z koperty.", "code": "login"})
            except database.LoginError as e:
                return self._json(401, {"error": str(e), "code": "password"})
            except database.Conflict:
                return self._json(409, {"error": "Kopia na dysku i kopia na pamięci USB rozeszły się. Wybierz, "
                                                 "z którą pracować dalej.", "code": "conflict"})
            except database.StorageError as e:
                text = str(e)
                return self._json(409, {"error": text[:1].upper() + text[1:] + ".", "code": "storage"})
            except ValueError as e:
                return self._json(400, {"error": str(e), "code": "invalid"})
            except Exception as e:   # noqa: BLE001 - panel zawsze dostaje odpowiedź, nie zerwane połączenie
                return self._json(500, {"error": "Nieoczekiwany błąd aplikacji. Spróbuj ponownie; jeśli się powtarza, "
                                                 "uruchom START jeszcze raz.", "code": type(e).__name__})
            finally:
                panel.changed()
            self._json(200, result)

    return Handler


def check(panel, body):
    doc = configdoc.normalize(body.get("doc"))
    problems = configdoc.check(doc)
    size = None
    if not problems:
        try:
            size = len(configdoc.encode(doc))
        except ValueError as e:
            problems = [("", str(e))]
    return {"doc": doc, "problems": [{"field": f, "message": m} for f, m in problems], "size": size,
            "max": configdoc.DOC_MAX}


def quit_app(panel, body):
    threading.Thread(target=panel.server.shutdown, daemon=True).start()
    return {"ok": True}


def hand_back(panel, body):
    panel.session.hand_back()
    return quit_app(panel, body)


def destroy(panel, body):
    """ZNISZCZ DANE: the laptop destroys its data at once, then the station gets `destroy` (OK on the station).

    The station is asked whenever the laptop part started, also when a file could not be deleted."""
    if body.get("confirm") != "ZNISZCZ":
        raise ValueError("brak potwierdzenia")
    try:
        result = panel.session.destroy()        # NotLoggedIn: nic się nie dzieje, także na stacji
    except database.StorageError:
        panel.prep.destroy_station()            # dane laptopa już niszczone, tylko nie każdy plik zniknął
        raise
    return {**result, "station": panel.prep.destroy_station()}


def ticket(panel, body):
    """Second START: a new link to this panel, and the path of the stick it runs from (Session.adopt)."""
    usb = body.get("usb")
    if isinstance(usb, str) and usb and panel.session:
        try:
            panel.session.adopt(usb)
        except (OSError, ValueError, database.StorageError):
            pass                                     # panel dalej ostrzega o kopii na pamięci USB
    return {"ticket": panel.ticket()}


def _text(body, key):
    value = body.get(key)
    if not isinstance(value, str) or not value or len(value) > 200:
        raise ValueError(f"brak pola {key}")
    return value


def _deputies(body):
    n = body.get("deputies", 2)
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError("liczba zastępców")
    return n


ROUTES = {
    "/api/config/check": check,
    "/api/config/read": lambda panel, body: panel.prep.read_config(),
    "/api/config/write": lambda panel, body: panel.prep.write_config(body.get("doc")),
    "/api/card": lambda panel, body: panel.prep.card(),
    "/api/ifac/new": lambda panel, body: {"ifac": configdoc.new_ifac()},
    "/api/rescan": lambda panel, body: (panel.station.rescan(), {"ok": True})[1],
    "/api/quit": quit_app,
    "/api/kit/create": lambda panel, body: panel.session.create(_deputies(body)),
    "/api/login": lambda panel, body: (panel.session.login(_text(body, "account"), _text(body, "password")), {"ok": True})[1],
    "/api/recover": lambda panel, body: panel.session.recover(_text(body, "password"), _deputies(body)),
    "/api/copy/choose": lambda panel, body: (panel.session.choose(_text(body, "prefer")), {"ok": True})[1],
    "/api/password/new": lambda panel, body: panel.session.new_password(_text(body, "account")),
    "/api/logout": lambda panel, body: (panel.session.logout(), {"ok": True})[1],
    "/api/hand-back": hand_back,
    "/api/destroy": destroy,
    "/api/ticket": ticket,
}


# Czynności na stacji piszą do dziennika w zaszyfrowanej bazie, więc wymagają zalogowania.
NEEDS_LOGIN = {"/api/config/read", "/api/config/write", "/api/card", "/api/password/new", "/api/logout",
               "/api/hand-back", "/api/destroy"}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows: SO_REUSEADDR pozwoliłby drugiemu serwerowi zająć ten sam port; tam zostaje wyłączone.
    allow_reuse_address = sys.platform != "win32"


def serve(panel, port=8080):
    """Bind 127.0.0.1:port, or any free port when it is taken by another program."""
    handler = make_handler(panel)
    try:
        server = Server(("127.0.0.1", port), handler)
    except OSError:
        server = Server(("127.0.0.1", 0), handler)
    panel.server = server
    return server
