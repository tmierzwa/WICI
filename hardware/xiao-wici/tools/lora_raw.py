# SPDX-License-Identifier: MIT
"""Shared pieces of the D21 bench tools for the lora-raw firmware (hardware/lora-raw).

Device protocol (USB serial, JSON lines from the device): see hardware/lora-raw/src/main.cpp.
Airtime comes from the reference model (software/reference/obliczenia.py, lora_frame_seconds), the same
formula as firmware/src/lora_profile.h. WICI-Link v3 encoding and keys come from the station app
(software/laptop/wici/stanowisko/wici_link.py). Only the standard library is used here; pyserial is
imported by open_port() alone, so the tests run without it.
"""

import hmac
import json
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
for _path in (ROOT / "software" / "laptop", ROOT / "software" / "reference"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from obliczenia import lora_frame_seconds  # noqa: E402
from wici.stanowisko import wici_link  # noqa: E402

FIRMWARE = "lora-raw-0.1"
PROFILE = {"mhz": 869.525, "bw_khz": 125, "sf": 7, "cr": 5, "preamble": 24, "sync_word": 0x12,
           "crc": True, "explicit_header": True}
SF = 7
TYPE_NAMES = {wici_link.DATA: "DATA", wici_link.HACK: "HACK", wici_link.BEACON: "BEACON"}
HOP_TAG = 8


def airtime_s(length):
    """Time on air of one frame in the pilot profile (24-symbol preamble, explicit header, CRC)."""
    return lora_frame_seconds(length, SF)


def parse_device_line(line):
    """One JSON record from the device, or None for an empty or non-JSON line."""
    text = line.decode("utf-8", "replace") if isinstance(line, bytes) else line
    text = text.strip()
    if not text.startswith("{"):
        return None
    try:
        record = json.loads(text)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def v3_header(raw):
    """Plain header fields of a frame whose version bits are 3, without authentication; None otherwise."""
    raw = bytes(raw)
    if len(raw) < wici_link.HEADER or raw[0] >> 6 != wici_link.VERSION:
        return None
    first = raw[0]
    kind = (first >> 3) & 7
    destination = int.from_bytes(raw[5:7], "big")
    return {
        "version": first >> 6,
        "type": kind,
        "type_name": TYPE_NAMES.get(kind, f"reserved{kind}"),
        "flags": first & 7,
        "ackreq": bool(first & wici_link.ACKREQ),
        "down": bool(first & wici_link.DOWN),
        "net_id": int.from_bytes(raw[1:3], "big"),
        "l_src": int.from_bytes(raw[3:5], "big"),
        "l_dst": destination,
        "unicast": destination != wici_link.BROADCAST,
        "hops": raw[7] >> 4,
        "ttl": raw[7] & 15,
        "seq": int.from_bytes(raw[8:10], "big"),
        "opts": raw[10],
    }


def mac_ok(key, raw):
    """Network MAC check: last 8 B of a broadcast frame; on a unicast frame the 8 B before the hop tag."""
    raw = bytes(raw)
    header = v3_header(raw)
    if header is None:
        return False
    end = len(raw) - (HOP_TAG if header["unicast"] else 0)
    body_end = end - wici_link.TAG
    if body_end < wici_link.HEADER:
        return False
    expected = hmac.digest(bytes(key), raw[:body_end], "sha256")[:wici_link.TAG]
    return hmac.compare_digest(expected, raw[body_end:end])


def frame_class(raw, crc=True):
    """Summary class of a received frame: crc_error, a v3 type name, or other (not version 3)."""
    if not crc:
        return "crc_error"
    header = v3_header(raw)
    return header["type_name"] if header else "other"


class Summary:
    """Frames and airtime per class and per l_src; occupancy = airtime / observation time."""

    def __init__(self):
        self.frames = {}
        self.airtime = {}
        self.by_source = {}
        self.total_airtime = 0.0

    def add(self, cls, length, source=None):
        air = airtime_s(length)
        self.frames[cls] = self.frames.get(cls, 0) + 1
        self.airtime[cls] = self.airtime.get(cls, 0.0) + air
        if source is not None:
            self.by_source[str(source)] = self.by_source.get(str(source), 0.0) + air
        self.total_airtime += air
        return air

    def result(self, duration_s):
        return {
            "duration_s": round(duration_s, 3),
            "frames": dict(sorted(self.frames.items())),
            "airtime_s": {k: round(v, 6) for k, v in sorted(self.airtime.items())},
            "airtime_by_l_src_s": {k: round(v, 6) for k, v in sorted(self.by_source.items(), key=lambda i: int(i[0]))},
            "airtime_total_s": round(self.total_airtime, 6),
            "occupancy_pct": round(100 * self.total_airtime / duration_s, 3) if duration_s > 0 else None,
        }


def receive_record(record, host_ts, key=None):
    """JSONL record of one device rx line: raw bytes, device time, RSSI/SNR, airtime, v3 header."""
    raw = bytes.fromhex(record["rx"])
    crc = bool(record.get("crc", True))
    air = airtime_s(len(raw))
    out = {"host_ts": round(host_ts, 6), "t_us": record.get("t_us"), "len": len(raw), "hex": raw.hex(),
           "rssi": record.get("rssi"), "snr": record.get("snr"), "crc": crc, "airtime_s": round(air, 6),
           "start_us": record["t_us"] - round(air * 1e6) if isinstance(record.get("t_us"), int) else None,
           "class": frame_class(raw, crc)}
    header = v3_header(raw)
    if header:
        out["v3"] = header
        if key is not None:
            out["mac_ok"] = mac_ok(key, raw)
    if len(raw) != record.get("len", len(raw)):
        out["len_mismatch"] = record.get("len")
    return out


class Pacer:
    """Keeps the cumulative channel occupancy of our own transmissions at `target`, from measured times.

    After every TxDone the next start is due at first_start + total_air / target (device clock), so each
    start keeps sum(air) / (start - first_start) equal to the target; a late start (USB latency) only
    shortens the next gap, and the long-run share converges to the target exactly.
    """

    def __init__(self, target):
        if not 0 < target < 1:
            raise ValueError("target occupancy must be in (0, 1)")
        self.target = target
        self.first_start = None
        self.last_done = None
        self.total_air = 0

    def done(self, start_us, done_us):
        if self.first_start is None:
            self.first_start = start_us
        self.total_air += done_us - start_us
        self.last_done = done_us

    def next_start_us(self):
        return None if self.first_start is None else self.first_start + self.total_air / self.target

    def wait_s(self, device_now_us):
        due = self.next_start_us()
        return 0.0 if due is None else max(0.0, (due - device_now_us) / 1e6)

    def occupancy(self):
        if self.first_start is None or self.last_done == self.first_start:
            return None
        return self.total_air / (self.last_done - self.first_start)


def junk_frame(rng, min_len=20, max_len=255):
    """Random bytes in the profile, no key; never starts with v3 version bits so it is never parsed as v3."""
    length = rng.randint(min_len, max_len)
    raw = bytearray(rng.randbytes(length))
    raw[0] &= 0x3F  # version bits 0: plainly not a WICI-Link v3 frame
    return bytes(raw)


def _station(rng, choices):
    return rng.choice(choices) if choices else rng.randint(1, 0xFFFE)


def keyed_frame(rng, key, net_id, kind, sources=(), destinations=()):
    """A frame with a valid network MAC as a captured station could send; returns (raw, fields).

    data: broadcast DATA (DOWN) with a random 25-228 B envelope; beacon: BEACON with garbage signatures;
    unicast: ACKREQ DATA to a station with a random hop tag; hack: HACK to a station with a random hop tag.
    """
    source = _station(rng, sources)
    sequence = rng.randint(0, 0xFFFF)
    if kind == "data":
        frame = wici_link.Frame(wici_link.DATA, wici_link.DOWN, net_id, source, wici_link.BROADCAST, 0,
                                rng.randint(1, 15), sequence, rng.randbytes(rng.randint(25, wici_link.MAX_PAYLOAD)))
        tag = b""
    elif kind == "beacon":
        content = b"".join(rng.randint(1, 0xFFFE).to_bytes(2, "big") for _ in range(4)) + b"\0"
        frame = wici_link.Frame(wici_link.BEACON, 0, net_id, source, wici_link.BROADCAST, 0, 1, sequence,
                                content + rng.randbytes(128))
        tag = b""
    elif kind == "unicast":
        frame = wici_link.Frame(wici_link.DATA, wici_link.ACKREQ, net_id, source, _station(rng, destinations), 0,
                                rng.randint(1, 15), sequence, rng.randbytes(rng.randint(25, wici_link.MAX_PAYLOAD)))
        tag = rng.randbytes(HOP_TAG)
    elif kind == "hack":
        frame = wici_link.Frame(wici_link.HACK, 0, net_id, source, _station(rng, destinations), 0, 1, sequence)
        tag = rng.randbytes(HOP_TAG)
    else:
        raise ValueError(f"unknown keyed frame kind {kind!r}")
    raw = wici_link.encode(key, frame) + tag
    return raw, {"kind": kind, "l_src": frame.source, "l_dst": frame.destination, "seq": sequence}


def parse_mix(text):
    """'data=2,beacon=1' -> [('data', 2.0), ('beacon', 1.0)]."""
    mix = []
    for item in text.split(","):
        name, _, weight = item.partition("=")
        name = name.strip()
        if name not in ("data", "beacon", "unicast", "hack"):
            raise ValueError(f"unknown frame kind {name!r}")
        value = float(weight) if weight else 1.0
        if value < 0:
            raise ValueError("negative weight")
        mix.append((name, value))
    if not mix or sum(w for _, w in mix) <= 0:
        raise ValueError("empty mix")
    return mix


def parse_ids(text):
    return [int(v) for v in text.split(",") if v.strip()] if text else []


class Device:
    """Line protocol over a serial-like port (write(bytes), readline() -> bytes with a timeout)."""

    def __init__(self, port, clock=time.monotonic):
        self.port = port
        self.clock = clock

    def command(self, text):
        self.port.write((text + "\n").encode("ascii"))

    def read(self):
        """(host time, record) for the next JSON line, or (host time, None) on timeout or noise."""
        line = self.port.readline()
        return self.clock(), parse_device_line(line) if line else None

    def wait_for(self, predicate, timeout_s, on_other=None):
        until = self.clock() + timeout_s
        while self.clock() < until:
            host_ts, record = self.read()
            if record is None:
                continue
            if predicate(record):
                return host_ts, record
            if on_other:
                on_other(host_ts, record)
        raise TimeoutError("no expected record from the lora-raw device")

    def info(self, timeout_s=3.0):
        self.command("info")
        _, record = self.wait_for(lambda r: "info" in r, timeout_s)
        return record


def check_info(info):
    """Raise unless the device runs lora-raw in the pilot profile with a working radio."""
    if info.get("info") != FIRMWARE:
        raise RuntimeError(f"expected {FIRMWARE}, got {info.get('info')!r}")
    if not info.get("ready"):
        raise RuntimeError(f"radio not ready (begin code {info.get('begin')})")
    wrong = {k: info.get(k) for k, v in PROFILE.items() if info.get(k) != v}
    if wrong:
        raise RuntimeError(f"device profile differs from the pilot profile: {wrong}")


def open_port(name):
    import serial  # pyserial, only needed with hardware
    return serial.Serial(name, 115200, timeout=0.2)


def network_key(ifac_hex, net_id):
    ifac = bytes.fromhex(ifac_hex)
    return wici_link.derive_key(ifac, net_id)


def new_rng(seed=None):
    return random.Random(seed)
