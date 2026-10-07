"""Executable contract model for station prototype 0.4; not a radio driver."""

import json
import math
import re
import sqlite3
import struct
import unicodedata
from pathlib import Path

MAX_DATAGRAM = 600
CHUNK = 86
MAX_CONTENT = 480
PREFIX = bytes.fromhex("aa" * 8 + "d391d391")
HEADER = struct.Struct(">BB8sBBH")


def crc16(data: bytes) -> int:
    """Compute the CCITT-FALSE check in radio.md."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xFFFF
    return crc


def fragment(data: bytes, message_id: bytes) -> list[bytes]:
    """Encode a datagram into the exact P1 air frames in radio.md."""
    if not 1 <= len(data) <= MAX_DATAGRAM or len(message_id) != 8:
        raise ValueError("Invalid datagram or message id")
    count = math.ceil(len(data) / CHUNK)
    frames = []
    for index in range(count):
        body = HEADER.pack(1, 0, message_id, index, count, len(data))
        body += data[index * CHUNK:(index + 1) * CHUNK]
        checked = bytes([len(body)]) + body
        frames.append(PREFIX + checked + struct.pack(">H", crc16(checked)))
    return frames


def parse_frame(frame: bytes) -> tuple[bytes, int, int, int, bytes]:
    """Reject corrupt or noncanonical P1 fragments before buffering them."""
    if not frame.startswith(PREFIX) or len(frame) < len(PREFIX) + 18:
        raise ValueError("Invalid preamble or truncated frame")
    checked = frame[len(PREFIX):-2]
    length = checked[0]
    if not 15 <= length <= 100 or len(checked) != length + 1:
        raise ValueError("Invalid frame length")
    if crc16(checked) != struct.unpack(">H", frame[-2:])[0]:
        raise ValueError("Invalid CRC")
    version, flags, mid, index, count, total = HEADER.unpack(checked[1:15])
    if version != 1 or flags != 0 or not 1 <= total <= MAX_DATAGRAM:
        raise ValueError("Unsupported version, flags or size")
    if count != math.ceil(total / CHUNK) or not 0 <= index < count:
        raise ValueError("Invalid fragment index or count")
    chunk = checked[15:]
    expected = min(CHUNK, total - index * CHUNK)
    if len(chunk) != expected:
        raise ValueError("Noncanonical fragment length")
    return mid, index, count, total, chunk


def assemble(frames: list[bytes]) -> bytes:
    """Model assembly and duplicate rejection for one P1 datagram."""
    if not frames:
        raise ValueError("No frames")
    chunks = {}
    identity = None
    for frame in frames:
        mid, index, count, total, chunk = parse_frame(frame)
        key = (mid, count, total)
        if identity is not None and identity != key:
            raise ValueError("Mixed datagrams")
        identity = key
        if index in chunks and chunks[index] != chunk:
            raise ValueError("Conflicting duplicate")
        chunks[index] = chunk
    assert identity is not None
    _, count, total = identity
    if len(chunks) != count:
        raise ValueError("Incomplete datagram")
    data = b"".join(chunks[index] for index in range(count))
    if len(data) != total:
        raise ValueError("Invalid assembled length")
    return data


def _integer(value: object, low: int, high: int) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Invalid integer")


def _text(value: object, maximum: int, minimum: int = 0) -> None:
    if type(value) is not str or not minimum <= len(value.encode("utf-8")) <= maximum:
        raise ValueError("Invalid UTF-8 text size")
    if any(unicodedata.category(c) in ("Cc", "Cf") for c in value):
        raise ValueError("Control or format character")


def validate_message(value: object) -> None:
    """Validate every SA1 message shape from oprogramowanie.md."""
    if type(value) is not list or len(value) < 4:
        raise ValueError("Expected message array")
    _integer(value[0], 1, 1)
    _integer(value[1], 0, 5)
    if type(value[2]) is not str or re.fullmatch(r"[0-9a-f]{32}", value[2]) is None:
        raise ValueError("Invalid message id")
    kind = value[1]
    lengths = (9, 6, 6, 6, 5, 9)
    if len(value) != lengths[kind]:
        raise ValueError("Invalid message arity")
    if kind == 4:
        _integer(value[3], 1, 2147483647)
        _text(value[4], 192)
        return
    _integer(value[3], 0, 65535)
    if kind in (0, 5):
        _integer(value[4], 0, 4)
        _integer(value[5], 1, 65535)
        _text(value[6], 64, 1)
        _text(value[7], 96)
        _integer(value[8], 0, 2)
    elif kind == 1:
        _integer(value[4], 1, 1)
        _integer(value[5], 1, 1)
    elif kind == 2:
        _integer(value[4], 2, 2147483647)
        _integer(value[5], 2, 3)
    else:
        _integer(value[4], 1, 2147483647)
        _text(value[5], 96)


def encode_message(value: list) -> bytes:
    """Encode bounded SA1 content with the standard library JSON encoder."""
    validate_message(value)
    wire = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(wire) > MAX_CONTENT:
        raise ValueError("Content too large")
    return wire


def decode_message(wire: bytes) -> list:
    """Decode bounded SA1 content without accepting extra fields or bools."""
    if len(wire) > MAX_CONTENT:
        raise ValueError("Content too large")
    try:
        value = json.loads(wire.decode("utf-8"))
        validate_message(value)
    except (UnicodeError, RecursionError, TypeError, ValueError) as error:
        raise ValueError("Invalid SA1 message") from error
    return value


def status_after(current_event: int, current_state: int, event: int, state: int) -> tuple[int, int]:
    """Apply newer status events without accepting a contradictory replay."""
    _integer(event, 1, 2147483647)
    _integer(state, 1, 3)
    if event < current_event:
        return current_event, current_state
    if event == current_event and state != current_state:
        raise ValueError("Conflicting event")
    if event > current_event and state < current_state:
        raise ValueError("Status regression")
    return event, state


def accept_from_osp(pinned: bytes, source: bytes, wire: bytes, signature_valid: bool) -> list:
    """Accept RECEIVED, STATUS, REPLY or BULLETIN at a station only from the signed, pinned OSP."""
    if signature_valid is not True or len(pinned) != 16 or source != pinned:
        raise ValueError("Untrusted sender")
    value = decode_message(wire)
    if value[1] not in (1, 2, 3, 4):
        raise ValueError("Unexpected message type for a station")
    return value


class OSPStore:
    """Model atomic OSP reception, quarantine of unknown senders and ACK outbox creation."""

    def __init__(self, path: Path, trusted: tuple[bytes, ...] = ()):
        """Open a test database with the specified SQLite durability settings and pinned shelters."""
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(Path(__file__).with_name("schema.sql").read_text())
        with self.db:
            self.db.executemany("INSERT OR IGNORE INTO trusted VALUES(?)", [(s,) for s in trusted])

    def _store(self, table: str, source: bytes, mid: str, revision: int, canonical: bytes) -> None:
        """Insert one message key into a table; reject the same key with other content."""
        previous = self.db.execute(
            f"SELECT payload FROM {table} WHERE source=? AND id=? AND revision=?",
            (source, mid, revision),
        ).fetchone()
        if previous is not None and previous[0] != canonical:
            raise ValueError("Conflicting request")
        self.db.execute(f"INSERT OR IGNORE INTO {table} VALUES(?,?,?,?)", (source, mid, revision, canonical))

    def receive(self, source: bytes, wire: bytes, signature_valid: bool, before_commit=None) -> bytes | None:
        """Commit a verified REQUEST or TEST with its ACK; quarantine an unknown sender without ACK."""
        if signature_valid is not True or len(source) != 16:
            raise ValueError("Unverified sender")
        value = decode_message(wire)
        if value[1] not in (0, 5):
            raise ValueError("Expected REQUEST or TEST")
        canonical = encode_message(value)
        _, _, mid, revision, *_ = value
        ack = encode_message([1, 1, mid, revision, 1, 1])
        with self.db:
            if self.db.execute("SELECT 1 FROM trusted WHERE source=?", (source,)).fetchone() is None:
                self._store("quarantine", source, mid, revision, canonical)
                if before_commit is not None:
                    before_commit()
                return None
            self._store("received", source, mid, revision, canonical)
            self.db.execute(
                "INSERT OR IGNORE INTO ack_outbox VALUES(?,?,?,?)",
                (source, mid, revision, ack),
            )
            if before_commit is not None:
                before_commit()
        return ack

    def approve(self, source: bytes) -> list[bytes]:
        """Record the duty officer's approval; move quarantined messages to requests with ACKs atomically."""
        if len(source) != 16:
            raise ValueError("Invalid sender")
        acks = []
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO trusted VALUES(?)", (source,))
            rows = self.db.execute(
                "SELECT id, revision, payload FROM quarantine WHERE source=? ORDER BY id, revision", (source,)
            ).fetchall()
            for mid, revision, canonical in rows:
                self._store("received", source, mid, revision, canonical)
                ack = encode_message([1, 1, mid, revision, 1, 1])
                self.db.execute("INSERT OR IGNORE INTO ack_outbox VALUES(?,?,?,?)", (source, mid, revision, ack))
                acks.append(ack)
            self.db.execute("DELETE FROM quarantine WHERE source=?", (source,))
        return acks

    def close(self) -> None:
        """Close the model database after a test."""
        self.db.close()
