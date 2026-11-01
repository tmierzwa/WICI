# SPDX-License-Identifier: MIT
"""Two connected pair boards: verify byte exact 19/44/255 B WICI frames over SX1262.

This is a physical payload check for the diagnostic firmware's TXHEX/RXHEX
path. It does not replace the D21 test on RAK4631 and the prototype.
"""

import argparse
import json
from pathlib import Path
import sys
import time

import serial

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "laptop"))
from wici.stanowisko import wici_link  # noqa: E402


def read_lines(ports):
    for label, port in ports.items():
        while port.in_waiting:
            yield label, port.readline().decode("ascii", "replace").strip()


def wait_ready(ports):
    for port in ports.values():
        port.reset_input_buffer()
    seen = set()
    until = time.monotonic() + 5
    next_info = 0.0
    while time.monotonic() < until and len(seen) < 2:
        if time.monotonic() >= next_info:
            for label, port in ports.items():
                if label not in seen:
                    port.write(b"INFO\n")
            next_info = time.monotonic() + 0.5
        for label, line in read_lines(ports):
            parts = line.split()
            if len(parts) >= 5 and parts[:2] == ["INFO", "pair-0.4"] and parts[3] == "1":
                seen.add(label)
        time.sleep(0.02)
    if len(seen) != 2:
        raise RuntimeError(f"both diagnostic boards must be ready; seen={sorted(seen)}")


def exercise(ports, sender, raw):
    receiver = "B" if sender == "A" else "A"
    payload = raw.hex()
    command = f"TXHEX {payload}\n".encode()
    for offset in range(0, len(command), 48):
        ports[sender].write(command[offset:offset + 48])
        time.sleep(0.01)  # S3 USB-Serial/JTAG has a small receive FIFO
    transmitted = received = None
    observed = []
    until = time.monotonic() + 8
    while time.monotonic() < until and (transmitted is None or received is None):
        for label, line in read_lines(ports):
            observed.append((label, line[:120]))
            fields = line.split()
            if not fields:
                continue
            if fields[0] == "ERR":
                raise RuntimeError(f"{label}: {line}")
            if label == sender and fields[0] == "TXHEX" and len(fields) == 4 and fields[3] == payload:
                if fields[1] != "0":
                    raise RuntimeError(f"radio TX failed: {line}")
                transmitted = int(fields[2])
            if label == receiver and fields[0] == "RXHEX" and len(fields) == 5 and fields[4] == payload:
                received = {"rssi_dbm": float(fields[2]), "snr_db": float(fields[3])}
        time.sleep(0.01)
    if transmitted is None or received is None:
        raise RuntimeError(f"missing byte exact TX/RX for {sender}->{receiver}, {len(raw)} B: {observed}")
    return {"direction": f"{sender}->{receiver}", "bytes": len(raw), **received}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("a")
    parser.add_argument("b")
    args = parser.parse_args()
    key = wici_link.derive_key(bytes(range(16)), 100)
    frames = [
        ("A", wici_link.Frame(wici_link.DATA, wici_link.ACKREQ, 100, 4, 5, 0, 7, 41,
                               b"\x40\x00\x04\x00\x01" + bytes(range(20)))),
        ("B", wici_link.Frame(wici_link.HACK, 0, 100, 5, 4, 0, 1, 41)),
        ("A", wici_link.Frame(wici_link.DATA, wici_link.ACKREQ, 100, 4, 5, 0, 7, 42,
                               b"\x40\x00\x04\x00\x01" + bytes(range(231)))),
        ("B", wici_link.Frame(wici_link.DATA, wici_link.ACKREQ | wici_link.DOWN,
                               100, 5, 4, 0, 7, 43,
                               b"\x40\x00\x01\x00\x04" + bytes(range(231)))),
    ]
    ports = {"A": serial.Serial(args.a, 115200, timeout=0.1),
             "B": serial.Serial(args.b, 115200, timeout=0.1)}
    try:
        wait_ready(ports)
        results = []
        for sender, frame in frames:
            raw = wici_link.encode(key, frame)
            results.append(exercise(ports, sender, raw))
            time.sleep(7)  # diagnostic image enforces 13 airtimes between starts
        print(json.dumps({"ok": True, "frames": results}, indent=2))
    finally:
        for port in ports.values():
            port.close()


if __name__ == "__main__":
    main()
