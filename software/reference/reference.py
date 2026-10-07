"""Executable contract model for station prototype 0.5; not a radio driver."""

import hashlib
import json
import math
import re
import sqlite3
import struct
import unicodedata
from pathlib import Path

MAX_DATAGRAM = 600
CHUNK = 86
MAX_CONTENT = 256
TEXT_REJECTED_CATEGORIES = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")
TEXT_REJECTED_CHARS = ('"', "\\")
QUARANTINE_PER_SENDER = 4
QUARANTINE_TOTAL = 256
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
        checked = bytes([len(body) + 2]) + body  # LEN counts BODY and CRC (radio.md, F79)
        frames.append(PREFIX + checked + struct.pack(">H", crc16(checked)))
    return frames


def parse_frame(frame: bytes) -> tuple[bytes, int, int, int, bytes]:
    """Reject corrupt or noncanonical P1 fragments before buffering them."""
    if not frame.startswith(PREFIX) or len(frame) < len(PREFIX) + 18:
        raise ValueError("Invalid preamble or truncated frame")
    checked = frame[len(PREFIX):-2]
    length = checked[0]  # bytes after LEN: BODY and the 2-byte CRC
    if not 17 <= length <= 102 or len(checked) != length - 1:
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
    """Accept NFC text within a UTF-8 byte limit, without quotes, backslashes or invisible code points."""
    if type(value) is not str or not minimum <= len(value.encode("utf-8")) <= maximum:
        raise ValueError("Invalid UTF-8 text size")
    if any(c in TEXT_REJECTED_CHARS for c in value):
        raise ValueError("Quotation mark or backslash")
    if any(unicodedata.category(c) in TEXT_REJECTED_CATEGORIES for c in value):
        raise ValueError("Control, format, separator, private or unassigned character")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("Text is not NFC")


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
        _integer(value[4], 0, 9)
        _integer(value[5], 1, 65535)
        _text(value[6], 64, 1)
        _text(value[7], 96)
        _integer(value[8], 0, 2)
    elif kind == 1:
        _integer(value[4], 1, 1)
        _integer(value[5], 1, 1)
    elif kind == 2:
        _integer(value[4], 2, 2147483647)
        _integer(value[5], 2, 6)
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
    _integer(state, 1, 6)
    if event < current_event:
        return current_event, current_state
    if event == current_event and state != current_state:
        raise ValueError("Conflicting event")
    if event > current_event and (state == 1 or current_state == 6):
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


def check_button_configuration(address: str, phrases: tuple[str, ...]) -> int:
    """Model `configure`: reject an address or phrase if the worst button-made REQUEST exceeds MAX_CONTENT."""
    worst = [1, 0, "f" * 32, 65535, 9, 999, address, "", 2]
    size = len(encode_message(worst))
    for phrase in phrases:
        worst[7] = phrase
        size = max(size, len(encode_message(worst)))
    return size


class RevokedSender(ValueError):
    """A message from a revoked identity: rejected, counted, never quarantined."""


class QuarantineFull(ValueError):
    """A quarantine limit (per sender or in total) would be exceeded."""


def _ack(mid: str, revision: int) -> bytes:
    return encode_message([1, 1, mid, revision, 1, 1])


class OSPStore:
    """Model atomic OSP reception, per-message quarantine, revocation, ACK outbox and content purge."""

    def __init__(self, path: Path, trusted: dict[bytes, bytes] | None = None):
        """Open a test database with the specified SQLite durability settings and station cards (source -> public key)."""
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(Path(__file__).with_name("schema.sql").read_text())
        with self.db:
            for source, pubkey in (trusted or {}).items():
                self._insert_trusted(source, pubkey)

    def _insert_trusted(self, source: bytes, pubkey: bytes) -> None:
        if len(source) != 16 or len(pubkey) != 64:
            raise ValueError("Invalid station card")
        if self.db.execute("SELECT 1 FROM revoked WHERE source=?", (source,)).fetchone() is not None:
            raise RevokedSender("Revoked identity cannot be trusted again")
        previous = self.db.execute("SELECT pubkey FROM trusted WHERE source=?", (source,)).fetchone()
        if previous is not None and previous[0] != pubkey:
            raise ValueError("Conflicting public key for a trusted station")
        self.db.execute("INSERT OR IGNORE INTO trusted VALUES(?,?)", (source, pubkey))

    def _check_key(self, table: str, source: bytes, mid: str, revision: int, digest: bytes) -> bool:
        """Return True if the reception key exists with the same digest; raise on the same key with other content."""
        previous = self.db.execute(
            f"SELECT sha256 FROM {table} WHERE source=? AND id=? AND revision=?", (source, mid, revision)
        ).fetchone()
        if previous is not None and previous[0] != digest:
            raise ValueError("Conflicting request")
        return previous is not None

    def _accept(self, source: bytes, mid: str, revision: int, canonical: bytes, digest: bytes) -> bytes:
        """Insert a request and its ACK in the current transaction; idempotent for the same reception key."""
        if not self._check_key("received", source, mid, revision, digest):
            self.db.execute("INSERT INTO received VALUES(?,?,?,?,?)", (source, mid, revision, digest, canonical))
        ack = _ack(mid, revision)
        self.db.execute("INSERT OR IGNORE INTO ack_outbox VALUES(?,?,?,?)", (source, mid, revision, ack))
        return ack

    def receive(self, source: bytes, wire: bytes, signature_valid: bool, before_commit=None) -> bytes | None:
        """Commit a verified REQUEST or TEST with its ACK; quarantine an unknown sender without ACK.

        Deduplication is by (source, id, revision, SHA-256 of canonical content); the same key with other content
        is a conflict. A message already accepted (also after purge or single-message approval) returns its ACK.
        A revoked sender is counted and rejected with RevokedSender; nothing is quarantined.
        """
        if signature_valid is not True or len(source) != 16:
            raise ValueError("Unverified sender")
        if self.db.execute("SELECT 1 FROM revoked WHERE source=?", (source,)).fetchone() is not None:
            with self.db:
                self.db.execute("UPDATE revoked SET rejected = rejected + 1 WHERE source=?", (source,))
            raise RevokedSender("Revoked sender")
        value = decode_message(wire)
        if value[1] not in (0, 5):
            raise ValueError("Expected REQUEST or TEST")
        canonical = encode_message(value)
        digest = hashlib.sha256(canonical).digest()
        _, _, mid, revision, *_ = value
        with self.db:
            trusted = self.db.execute("SELECT 1 FROM trusted WHERE source=?", (source,)).fetchone() is not None
            if trusted or self._check_key("received", source, mid, revision, digest):
                ack = self._accept(source, mid, revision, canonical, digest)
            else:
                ack = None
                if not self._check_key("quarantine", source, mid, revision, digest):
                    per_sender, total = self.db.execute(
                        "SELECT sum(source=?), count(*) FROM quarantine", (source,)).fetchone()
                    if (per_sender or 0) >= QUARANTINE_PER_SENDER or total >= QUARANTINE_TOTAL:
                        raise QuarantineFull("Quarantine limit reached")
                    self.db.execute("INSERT INTO quarantine VALUES(?,?,?,?,?)",
                                    (source, mid, revision, digest, canonical))
            if before_commit is not None:
                before_commit()
        return ack

    def approve_message(self, source: bytes, mid: str, revision: int) -> bytes:
        """Duty officer approves one quarantined message: move it to received with its ACK atomically.

        The sender is not added to trusted stations; its next message is quarantined again.
        """
        with self.db:
            row = self.db.execute(
                "SELECT sha256, payload FROM quarantine WHERE source=? AND id=? AND revision=?",
                (source, mid, revision),
            ).fetchone()
            if row is None:
                raise ValueError("No such quarantined message")
            ack = self._accept(source, mid, revision, row[1], row[0])
            self.db.execute("DELETE FROM quarantine WHERE source=? AND id=? AND revision=?", (source, mid, revision))
        return ack

    def add_trusted(self, source: bytes, pubkey: bytes, approvers: tuple[str, str]) -> None:
        """Add a station from its card (64 B public key) with the consent of two different people."""
        if (len(approvers) != 2 or any(type(a) is not str or not a.strip() for a in approvers)
                or approvers[0].strip() == approvers[1].strip()):
            raise ValueError("Two different approvers required")
        with self.db:
            self._insert_trusted(source, pubkey)

    def revoke(self, source: bytes) -> None:
        """Mark an identity as revoked: drop trust and its quarantine; later messages are rejected and counted."""
        if len(source) != 16:
            raise ValueError("Invalid sender")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO revoked(source) VALUES(?)", (source,))
            self.db.execute("DELETE FROM trusted WHERE source=?", (source,))
            self.db.execute("DELETE FROM quarantine WHERE source=?", (source,))

    def rejected_count(self, source: bytes) -> int:
        """Messages rejected from a revoked identity (diagnostics and possible takeover alarm)."""
        row = self.db.execute("SELECT rejected FROM revoked WHERE source=?", (source,)).fetchone()
        return 0 if row is None else row[0]

    def send_reply(self, dest: bytes, mid: str, revision: int, event: int, text: str) -> bytes:
        """Record a REPLY to an accepted request and return its SA1 content."""
        wire = encode_message([1, 3, mid, revision, event, text])
        with self.db:
            if self.db.execute("SELECT 1 FROM received WHERE source=? AND id=? AND revision=?",
                               (dest, mid, revision)).fetchone() is None:
                raise ValueError("No accepted request")
            self.db.execute("INSERT INTO replies VALUES(?,?,?,?,?)", (dest, mid, revision, event, text))
        return wire

    def send_status(self, dest: bytes, mid: str, revision: int, event: int, state: int) -> bytes:
        """Record a STATUS after an accepted request; state 5 requires an existing REPLY for this id (U10)."""
        wire = encode_message([1, 2, mid, revision, event, state])
        with self.db:
            if self.db.execute("SELECT 1 FROM received WHERE source=? AND id=? AND revision=?",
                               (dest, mid, revision)).fetchone() is None:
                raise ValueError("No accepted request")
            if state == 5 and self.db.execute("SELECT 1 FROM replies WHERE dest=? AND id=?",
                                              (dest, mid)).fetchone() is None:
                raise ValueError("State 5 requires a REPLY with instructions")
            row = self.db.execute("SELECT event, state FROM statuses WHERE dest=? AND id=? AND revision=?",
                                  (dest, mid, revision)).fetchone()
            current = row if row is not None else (1, 1)
            new_event, new_state = status_after(current[0], current[1], event, state)
            self.db.execute("INSERT OR REPLACE INTO statuses VALUES(?,?,?,?,?)",
                            (dest, mid, revision, new_event, new_state))
        return wire

    def purge_content(self) -> None:
        """CLOSE EVENT (S15): delete message content and quarantine; keep identities and reception keys with digests."""
        with self.db:
            self.db.execute("UPDATE received SET payload=NULL")
            self.db.execute("UPDATE replies SET text=NULL")
            self.db.execute("DELETE FROM quarantine")

    def close(self) -> None:
        """Close the model database after a test."""
        self.db.close()
