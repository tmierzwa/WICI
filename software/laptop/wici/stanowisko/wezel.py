# SPDX-License-Identifier: MIT
"""State of the station node from its diagnostics port (stage S11, author's decision 2026-10-30).

The node has two USB interfaces on one cable (firmware/src/main.cpp): data, where Reticulum speaks KISS, and
diagnostics with text commands. The application opens diagnostics next to KISS and every POLL_S sends only
`INFO`; from its JSON line it takes `silence` (CISZA switch or command), `radio_ok` and `tx_wait_ms` (silence
debt). Nothing changes in KISS, Reticulum or the firmware. A change of `silence` goes to the action log as
`cisza_wezel` (a "cisza" row in the register, next to the duty officer's entries), the rest to the node view.
Without the port the application works as before: the panel says the node state is unknown, without an alarm.
"""

import json
import threading
import time

from .. import serialport

POLL_S = 10
REPLY_S = 3   # odpowiedź INFO przychodzi w ułamku sekundy; dłużej oznacza, że port nie należy do węzła


def find_diagnostics(data_port):
    """The other interface of the same USB device as the data port (same serial number), or None."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return None
    ports = list(list_ports.comports())
    data = next((p for p in ports if p.device == data_port), None)
    if data is None or not data.serial_number:
        return None
    others = [p.device for p in ports if p.serial_number == data.serial_number and p.device != data_port]
    return others[0] if len(others) == 1 else None


class Wezel:
    """Polls INFO on the diagnostics port in its own thread. changed(silence, first) is called when `silence`
    changes, and on the first reading when the node is already silent."""

    def __init__(self, port, changed, log=None, opener=serialport.open_port, monotonic=time.monotonic):
        self.port, self.changed, self.opener, self.monotonic = port, changed, opener, monotonic
        self.log = log or (lambda line: None)
        self.info, self.at = None, None   # ostatnie INFO i chwila odczytu (zegar monotoniczny)
        self.running = threading.Event()
        self.thread = None

    def start(self):
        self.running.set()
        self.thread = threading.Thread(target=self._run, daemon=True, name="wezel")
        self.thread.start()
        return self

    def stop(self):
        self.running.clear()

    def _run(self):
        link = None
        while self.running.is_set():
            try:
                if link is None:
                    link = self.opener(self.port)
                self.poll(link)
            except (OSError, ValueError) as e:
                self.log(f"port diagnostyki węzła {self.port}: {e}")
                if link is not None:
                    link.close()
                link = None
            for _ in range(POLL_S * 10):
                if not self.running.is_set():
                    break
                time.sleep(0.1)
        if link is not None:
            link.close()

    def poll(self, link):
        """One INFO: write the command and read lines until the JSON line of INFO (other lines are the node log)."""
        link.write(b"INFO\n")
        buffer, deadline = b"", self.monotonic() + REPLY_S
        while self.monotonic() < deadline:
            buffer += link.read(0.2)
            *lines, buffer = buffer.split(b"\n")
            for line in lines:
                if line.startswith(b'{"contract"'):
                    self._update(json.loads(line))
                    return
        raise ValueError("brak odpowiedzi INFO")

    def _update(self, info):
        before = None if self.info is None else self.info.get("silence")
        self.at, self.info = self.monotonic(), info   # najpierw czas: status() czyta info bez blokady
        silence = bool(info.get("silence"))
        if before is None and silence or before is not None and bool(before) != silence:
            self.changed(silence, before is None)

    def status(self):
        """For the panel: None before the first INFO, otherwise silence, radio_ok, silence debt and age."""
        if self.info is None:
            return None
        return {"silence": bool(self.info.get("silence")), "radio_ok": bool(self.info.get("radio_ok")),
                "tx_wait_s": round(self.info.get("tx_wait_ms", 0) / 1000), "age_s": self.monotonic() - self.at}
