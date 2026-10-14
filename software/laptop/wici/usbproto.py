# SPDX-License-Identifier: MIT
"""Laptop side of the USB contract "usb":2 (docs/spec/protokol-usb.md).

`Link` is one session on one open port: a reader thread splits JSON lines, a request waits for the
final answer to its `seq` (after `pending` it waits for the button on the station). `Station` finds the
station among USB CDC ports by waiting for `hello`, keeps the session, polls `status` and reconnects.
"""

import base64
import hashlib
import json
import sys
import threading
import time

from . import serialport

CONTRACT = 2
LINE_MAX = 1024
PART_MAX = 512
TIMEOUT = 3          # odpowiedź na zwykłe polecenie
CONFIRM_TIMEOUT = 35  # odpowiedź końcowa po `pending` (przycisk na stacji w ciągu 30 s)
COMMIT_TIMEOUT = {"configure": 10, "import": 10, "firmware": 60}
HELLO_WAIT = 2.5
# Windows kolejkuje operacje na uchwycie bez FILE_FLAG_OVERLAPPED: zapis czeka na trwający odczyt.
READ_SLICE = 0.03 if sys.platform == "win32" else 0.2
POLL = 1.5


class ProtocolError(Exception):
    """No answer in time, a broken line or an answer that does not fit the contract."""


class Rejected(Exception):
    def __init__(self, reply):
        self.reason, self.detail = reply.get("reason", ""), reply.get("detail")
        super().__init__(f"{self.reason}{': ' + str(self.detail) if self.detail else ''}")


def encode(message):
    """Compact UTF-8 JSON without \\u sequences; texts were checked, so no escapes are produced."""
    line = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    if "\\" in line:
        raise ValueError("line would need an escape sequence")
    data = line.encode("utf-8")
    if len(data) > LINE_MAX:
        raise ValueError(f"line too long: {len(data)} B")
    return data + b"\n"


class Link:
    def __init__(self, port, on_message=None):
        self.port, self.on_message = port, on_message or (lambda m: None)
        self.seq = 0
        self.hello = None
        self.closed = None
        self.lock = threading.Lock()          # jedno polecenie naraz: stacja czyta następny wiersz po odpowiedzi
        self.cond = threading.Condition()
        self.replies = {}
        self.pending = None
        self.thread = threading.Thread(target=self._reader, name="wici-usb", daemon=True)
        self.thread.start()

    def _reader(self):
        buffer = b""
        try:
            while self.closed is None:
                data = self.port.read(READ_SLICE)
                if not data:
                    continue
                buffer += data
                *lines, buffer = buffer.split(b"\n")
                if len(buffer) > 4 * LINE_MAX:   # strumień bez LF (np. ramki KISS węzła): to nie jest ten kontrakt
                    buffer = b""
                for raw in lines:
                    self._line(raw.rstrip(b"\r"))
        except (serialport.PortClosed, OSError) as e:
            reason = str(e) or "port closed"
        else:
            reason = self.closed
        with self.cond:
            if self.closed is None:
                self.closed = reason
            self.cond.notify_all()
        self.on_message({"type": "_closed", "reason": reason})

    def _line(self, raw):
        if not raw.startswith(b"{"):
            return
        try:
            message = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return
        if not isinstance(message, dict) or message.get("usb") != CONTRACT and message.get("type") != "hello":
            return
        if message.get("type") == "hello":
            self.hello = message
        if "re" in message:
            with self.cond:
                if message.get("type") == "pending":
                    self.pending = message
                else:
                    self.replies[message["re"]] = message
                self.cond.notify_all()
        self.on_message(message)

    def wait_hello(self, timeout=HELLO_WAIT):
        end = time.monotonic() + timeout
        while self.hello is None and self.closed is None and time.monotonic() < end:
            time.sleep(0.02)
        return self.hello

    def request(self, type_, timeout=TIMEOUT, on_pending=None, **fields):
        """Send one command and return its final answer; `Rejected` for `rejected`."""
        with self.lock:
            for attempt in range(2):
                self.seq += 1
                seq = self.seq
                with self.cond:
                    self.pending = None
                port = self.port
                if port is None or self.closed is not None:
                    raise serialport.PortClosed(self.closed or "closed")
                port.write(encode({"usb": CONTRACT, "seq": seq, "type": type_, **fields}))
                reply = self._wait(seq, timeout, on_pending)
                if reply.get("type") == "rejected" and reply.get("reason") == "seq":
                    if attempt == 0:
                        continue   # stacja liczy dalej od numeru laptopa; klucz powtórzenia chroni przed podwójnym skutkiem
                    raise ProtocolError("seq")
                if reply.get("type") == "rejected":
                    raise Rejected(reply)
                return reply
        raise ProtocolError("seq")

    def _wait(self, seq, timeout, on_pending):
        deadline = time.monotonic() + timeout
        with self.cond:
            while True:
                if self.pending is not None and self.pending.get("re") == seq:
                    if on_pending:
                        on_pending(self.pending)
                    deadline = time.monotonic() + max(CONFIRM_TIMEOUT, self.pending.get("confirm_s", 30) + 5)
                    self.pending = None
                if seq in self.replies:
                    return self.replies.pop(seq)
                if self.closed is not None:
                    raise serialport.PortClosed(self.closed)
                left = deadline - time.monotonic()
                if left <= 0:
                    raise ProtocolError(f"no answer to {seq}")
                self.cond.wait(min(left, 0.5))

    def write_transfer(self, op, data, **extra):
        """Upload `data` in parts (configure, import, firmware) and return the `xfer_commit` answer."""
        begin = self.request("xfer_begin", op=op, size=len(data), sha256=hashlib.sha256(data).hexdigest(), **extra)
        xfer, step = begin["xfer"], min(int(begin.get("max_part", PART_MAX)), PART_MAX)
        offset = 0
        while offset < len(data):
            part = data[offset:offset + step]
            reply = self.request("xfer_part", xfer=xfer, offset=offset, data=base64.b64encode(part).decode("ascii"))
            offset = int(reply.get("next", offset + len(part)))
        return self.request("xfer_commit", timeout=COMMIT_TIMEOUT.get(op, TIMEOUT), xfer=xfer)

    def read_transfer(self, op, **extra):
        begin = self.request("xfer_begin", op=op, **extra)
        xfer, size, digest = begin["xfer"], int(begin["size"]), begin["sha256"]
        data = b""
        while len(data) < size:
            reply = self.request("xfer_read", xfer=xfer, offset=len(data), length=min(PART_MAX, size - len(data)))
            part = base64.b64decode(reply["data"])
            if not part:
                raise ProtocolError("empty part")
            data += part
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ProtocolError("transfer checksum")
        return data

    def close(self):
        """Stop the reader first, then close the port once: a reopened port may get the same fd or handle."""
        with self.cond:
            if self.closed is None:
                self.closed = "closed by laptop"
            self.cond.notify_all()
        if threading.current_thread() is not self.thread:
            self.thread.join(2)
        with self.cond:
            if self.port is None:
                return
            port, self.port = self.port, None
        port.close()


class Station:
    """Connection to one station: discovery, session, `status` polling and reconnection in a thread.

    A port that opened but sent no `hello` (the diagnostic interface, a node outside preparation mode,
    somebody else's device) is not opened again until it disappears or `rescan()` is called: opening
    a port raises DTR, which resets e.g. an Arduino connected to the same laptop.
    """

    def __init__(self, port=None, on_change=None):
        self.forced = port                 # nazwa portu z wiersza poleceń; bez niej: wyszukiwanie
        self.on_change = on_change or (lambda: None)
        self.link = None
        self.state = {"phase": "searching", "port": None, "hello": None, "status": None, "problem": None,
                      "skipped": []}
        self.ignored = set()
        self.lock = threading.Lock()       # stan i bieżące połączenie
        self.operation = threading.Lock()  # jedna czynność naraz: transfer nie może przerwać innego
        self.running = True
        self.wake = threading.Event()
        self.thread = threading.Thread(target=self._run, name="wici-station", daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.running = False
        self.wake.set()
        self._drop(self.link)

    def rescan(self):
        self.ignored.clear()
        self.wake.set()

    def _set(self, link=None, **changes):
        """Change the state; with `link`, only while that link is still the current one."""
        with self.lock:
            if link is not None and self.link is not link:
                return
            if all(self.state.get(k) == v for k, v in changes.items()):
                return
            self.state = {**self.state, **changes}
        self.on_change()

    def _message(self, message):
        link = self.link
        if message.get("type") == "hello" and link is not None:
            self._set(link, hello=message)
        elif message.get("type") in ("_closed", "event"):
            self.wake.set()   # przerwane połączenie albo zmiana w stacji: najbliższy obieg to obsłuży

    def _drop(self, link):
        """Close `link` and go back to searching, unless a newer link has replaced it meanwhile."""
        if link is None:
            return
        with self.lock:
            current = self.link is link
            if current:
                self.link = None
        link.close()
        if current:
            self._set(phase="searching", port=None, hello=None, status=None)

    def _run(self):
        while self.running:
            link = self.link
            if link is None or link.closed is not None:
                self._drop(link)
                self._connect()
                if self.link is None:
                    self.wake.wait(1.0)
                    self.wake.clear()
                    continue
                link = self.link
            if self.state["phase"] == "connected" and self.operation.acquire(blocking=False):
                try:
                    self._set(link, status=link.request("status"))
                except Rejected:
                    pass
                except (ProtocolError, OSError):
                    self._drop(link)   # brak odpowiedzi w limicie: nowa sesja (zamknięcie i otwarcie portu)
                    continue
                finally:
                    self.operation.release()
            self.wake.wait(POLL)
            self.wake.clear()

    def _connect(self):
        present = [self.forced] if self.forced else serialport.candidates()
        self.ignored &= set(present)       # odłączony port: przy ponownym podłączeniu znów sprawdzany
        problem = None
        for name in present:
            if name in self.ignored and not self.forced:
                continue
            try:
                port = serialport.open_port(name)
            except serialport.PortError as e:
                problem = {"kind": e.kind, "port": name, "detail": e.detail}
                continue
            link = Link(port, self._message)
            hello = link.wait_hello()
            if hello is None:
                link.close()
                self.ignored.add(name)    # port diagnostyki, węzeł poza trybem przygotowania, cudze urządzenie
                continue
            with self.lock:
                self.link = link
            if CONTRACT not in hello.get("contracts", []):
                self._set(phase="incompatible", port=name, hello=hello, status=None, problem=None)
            else:
                self._set(phase="connected", port=name, hello=hello, problem=None)
            return
        self._set(problem=problem, skipped=sorted(self.ignored))

    def call(self, fn):
        """Run `fn(link)` on the connected station, one operation at a time; `ProtocolError` without one."""
        with self.operation:
            link = self.link
            if link is None or link.closed is not None or self.state["phase"] != "connected":
                raise ProtocolError("not connected")
            try:
                return fn(link)
            except (ProtocolError, OSError):
                self._drop(link)
                raise
            finally:
                self.wake.set()
