# SPDX-License-Identifier: MIT
"""WICI envelope v1 codec (docs/spec/transport.md).

The caller must reserve each outgoing counter durably before calling seal().
ReplayWindow is a value object: persist its proposed state atomically with SA1
admission, never when the first fragment merely arrives.
"""

from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


HEADER = 9
TAG = 16
OVERHEAD = HEADER + TAG
MAX_SA1 = 256
MAX_FRAME = MAX_SA1 + OVERHEAD
MIN_PAYLOAD = 153
WINDOW = 64
VERSION = 1
TYPE_SA1 = 0  # the only kind type in v1; 1..15 are reserved and rejected


class EnvelopeError(ValueError):
    pass


def _u16(value):
    if type(value) is not int or not 1 <= value <= 0xFFFE:
        raise EnvelopeError("station number must be in 1..65534")
    return value.to_bytes(2, "big")


def _u32(value):
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise EnvelopeError("counter must be in 0..2^32-1")
    return value.to_bytes(4, "big")


def _kind(part, message_type):
    if part not in (0, 1, 2) or message_type != TYPE_SA1:
        raise EnvelopeError("invalid envelope kind")
    return (VERSION << 6) | (part << 4) | message_type


def derive_key(private_key, peer_public_key, net_id, sender, recipient, own_id):
    """Directional X25519/HKDF key; IDs and net_id are unsigned big-endian u16."""
    if type(net_id) is not int or not 1 <= net_id <= 0xFFFE:
        raise EnvelopeError("net_id must be in 1..65534")
    sender_id, recipient_id = _u16(sender), _u16(recipient)
    if own_id not in (sender, recipient) or sender == recipient:
        raise EnvelopeError("own_id must be one endpoint of a directed pair")
    private = x25519.X25519PrivateKey.from_private_bytes(bytes(private_key))
    own_public = private.public_key().public_bytes_raw()
    peer_public = bytes(peer_public_key)
    if len(peer_public) != 32:
        raise EnvelopeError("peer X25519 key must be 32 bytes")
    try:
        shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(peer_public))
    except ValueError as exc:  # all-zero shared secret: small-order peer point
        raise EnvelopeError("weak peer X25519 key") from exc
    # The caller may be either side. The public keys in info always follow wire direction.
    sender_public, recipient_public = (own_public, peer_public) if sender == own_id else (peer_public, own_public)
    info = b"WICI env v1" + sender_id + recipient_id + sender_public + recipient_public
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=net_id.to_bytes(2, "big") + b"\x01", info=info).derive(shared)


def _nonce(header):
    return header[1:5] + header[:1] + b"\x00\x00\x00" + header[5:9]


def seal(key, sender, recipient, counter, plaintext, max_payload, message_type=TYPE_SA1):
    """Return one or two independently authenticated envelopes for a reserved counter."""
    raw = bytes(plaintext)
    if len(raw) > MAX_SA1 or max_payload < MIN_PAYLOAD:
        raise EnvelopeError("payload exceeds envelope contract")
    src, dst, ctr = _u16(sender), _u16(recipient), _u32(counter)
    if sender == recipient or len(key) != 32:
        raise EnvelopeError("invalid key or direction")
    # MIN_PAYLOAD fits a 128-byte half, so two parts always suffice.
    half = (len(raw) + 1) // 2
    parts = (raw,) if len(raw) + OVERHEAD <= max_payload else (raw[:half], raw[half:])
    result = []
    for index, body in enumerate(parts):
        header = bytes([_kind(0 if len(parts) == 1 else index + 1, message_type)]) + src + dst + ctr
        result.append(header + ChaCha20Poly1305(bytes(key)).encrypt(_nonce(header), body, header))
    return tuple(result)


@dataclass(frozen=True)
class Part:
    sender: int
    recipient: int
    counter: int
    message_type: int
    number: int  # 0 = whole, 1 and 2 = fragments
    plaintext: bytes


def open_part(key, frame):
    wire = bytes(frame)
    if len(key) != 32 or not OVERHEAD <= len(wire) <= MAX_SA1 + OVERHEAD:
        raise EnvelopeError("invalid key or envelope length")
    header, kind = wire[:HEADER], wire[0]
    if kind >> 6 != VERSION or kind & 0x0F != TYPE_SA1 or (kind >> 4) & 3 == 3:
        raise EnvelopeError("unsupported envelope kind")
    sender, recipient = int.from_bytes(header[1:3], "big"), int.from_bytes(header[3:5], "big")
    _u16(sender)
    _u16(recipient)
    if sender == recipient:
        raise EnvelopeError("sender and recipient must differ")
    if ((kind >> 4) & 3) and len(wire) - OVERHEAD > MAX_SA1 // 2:
        raise EnvelopeError("fragment exceeds 128 bytes")
    try:
        body = ChaCha20Poly1305(bytes(key)).decrypt(_nonce(header), wire[HEADER:], header)
    except InvalidTag as exc:
        raise EnvelopeError("envelope authentication failed") from exc
    return Part(sender, recipient, int.from_bytes(header[5:9], "big"), kind & 0x0F, (kind >> 4) & 3, body)


@dataclass(frozen=True)
class ReplayWindow:
    highest: int = -1
    mask: int = 0

    def accept(self, counter):
        """Return the next state, or raise; the caller commits it with the SA1 transaction."""
        _u32(counter)
        if self.highest == -1:
            return ReplayWindow(counter, 1)
        if counter > self.highest:
            shift = counter - self.highest
            return ReplayWindow(counter, ((self.mask << shift) | 1) & ((1 << WINDOW) - 1))
        distance = self.highest - counter
        if distance >= WINDOW or self.mask & (1 << distance):
            raise EnvelopeError("replayed or stale counter")
        return ReplayWindow(self.highest, self.mask | (1 << distance))


@dataclass(frozen=True)
class Assembly:
    """One pending two-part message; persist this value before acknowledging a fragment."""

    sender: int
    recipient: int
    counter: int
    message_type: int
    started_at: int
    first: bytes | None = None
    second: bytes | None = None

    @classmethod
    def start(cls, part, now):
        if part.number not in (1, 2):
            raise EnvelopeError("expected a fragment")
        return cls(part.sender, part.recipient, part.counter, part.message_type, now,
                   part.plaintext if part.number == 1 else None,
                   part.plaintext if part.number == 2 else None)

    def add(self, part, now):
        """Return (proposed assembly, full plaintext or None); caller commits before HACK."""
        if now < self.started_at or now - self.started_at > 120:
            raise EnvelopeError("fragment assembly expired")
        if (part.sender, part.recipient, part.counter, part.message_type) != (
                self.sender, self.recipient, self.counter, self.message_type) or part.number not in (1, 2):
            raise EnvelopeError("fragment belongs to another message")
        old = self.first if part.number == 1 else self.second
        if old is not None and old != part.plaintext:
            raise EnvelopeError("conflicting fragment")
        first = part.plaintext if part.number == 1 else self.first
        second = part.plaintext if part.number == 2 else self.second
        if first is not None and second is not None:
            full = first + second
            if len(full) > MAX_SA1:
                raise EnvelopeError("assembled SA1 exceeds 256 bytes")
            return None, full
        return Assembly(self.sender, self.recipient, self.counter, self.message_type,
                        self.started_at, first, second), None
