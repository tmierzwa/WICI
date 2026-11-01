# SPDX-License-Identifier: MIT
"""WICI-Link v2 wire and bounded KISS framing for the receiving station node.

This module only authenticates and parses link frames. The caller must durably admit
DATA before it asks the node to send HACK; a valid MAC alone is never an admission.
"""

from dataclasses import dataclass
import hmac
import sqlite3

HEADER, TAG, ORIGIN_SIGNATURE, MAX_FRAME = 11, 8, 64, 255
MAX_PAYLOAD = MAX_FRAME - HEADER - ORIGIN_SIGNATURE - TAG
BROADCAST = 0xFFFF
DATA, HACK, BEACON = 0, 1, 2
ACKREQ, DOWN = 1, 2
FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD
ORIGIN_LABEL = b"WICI K1 origin v1"


class LinkError(ValueError):
    pass


def _id(value):
    return type(value) is int and 1 <= value <= 0xFFFE


def _u16(value):
    if not _id(value):
        raise LinkError("network or station number outside 1..65534")
    return value.to_bytes(2, "big")


def derive_key(ifac, net_id):
    """RFC 5869 HKDF-SHA-256: K_link from the 16-byte network IFAC."""
    key = bytes(ifac)
    if len(key) != 16:
        raise LinkError("IFAC must be 16 bytes")
    prk = hmac.digest(_u16(net_id), key, "sha256")
    return hmac.digest(prk, b"WICI link v2\x01", "sha256")


def origin_message(net_id, envelope):
    data = bytes(envelope)
    if not 25 <= len(data) <= MAX_PAYLOAD:
        raise LinkError("origin proof needs one bounded envelope")
    return ORIGIN_LABEL + _u16(net_id) + data


@dataclass(frozen=True)
class Frame:
    kind: int
    flags: int
    network: int
    source: int
    destination: int
    hops: int
    ttl: int
    sequence: int
    payload: bytes = b""
    origin_signature: bytes = bytes(ORIGIN_SIGNATURE)


def _valid(frame):
    if (type(frame.kind) is not int or not _id(frame.network) or not _id(frame.source) or
            not (_id(frame.destination) or frame.destination == BROADCAST) or
            type(frame.flags) is not int or frame.flags & ~3 or
            type(frame.hops) is not int or type(frame.ttl) is not int or
            not 0 <= frame.hops <= frame.ttl <= 15 or frame.ttl == 0 or
            type(frame.sequence) is not int or not 0 <= frame.sequence <= 0xFFFF or
            len(frame.payload) > MAX_PAYLOAD or len(frame.origin_signature) != ORIGIN_SIGNATURE):
        return False
    if frame.kind == DATA:
        return len(frame.payload) >= 25 and (frame.destination != BROADCAST or not frame.flags & ACKREQ)
    if frame.kind == HACK:
        return _id(frame.destination) and frame.flags == 0 and not frame.payload
    if frame.kind == BEACON:
        return frame.destination == BROADCAST and frame.flags == 0 and len(frame.payload) == 9
    return False


def encode(key, frame):
    if len(key) != 32 or not _valid(frame):
        raise LinkError("invalid WICI-Link frame")
    head = (bytes([(2 << 6) | (frame.kind << 3) | frame.flags]) +
            _u16(frame.network) + _u16(frame.source) + frame.destination.to_bytes(2, "big") +
            bytes([(frame.hops << 4) | frame.ttl]) + frame.sequence.to_bytes(2, "big") + b"\0")
    body = head + bytes(frame.payload) + (bytes(frame.origin_signature) if frame.kind == DATA else b"")
    return body + hmac.digest(bytes(key), body, "sha256")[:TAG]


def decode(key, net_id, wire):
    """Authenticate before reading routing fields. Reject unknown versions and reserved bits."""
    raw = bytes(wire)
    if len(key) != 32 or not _id(net_id) or not HEADER + TAG <= len(raw) <= MAX_FRAME:
        raise LinkError("invalid frame length, key or network")
    if not hmac.compare_digest(raw[-TAG:], hmac.digest(bytes(key), raw[:-TAG], "sha256")[:TAG]):
        raise LinkError("WICI-Link MAC failed")
    first = raw[0]
    if first >> 6 != 2 or first & 4 or raw[10] != 0 or int.from_bytes(raw[1:3], "big") != net_id:
        raise LinkError("unsupported frame header or wrong network")
    kind = (first >> 3) & 7
    signature_size = ORIGIN_SIGNATURE if kind == DATA else 0
    if len(raw) < HEADER + TAG + signature_size:
        raise LinkError("invalid authenticated frame length")
    frame = Frame((first >> 3) & 7, first & 3, net_id, int.from_bytes(raw[3:5], "big"),
                  int.from_bytes(raw[5:7], "big"), raw[7] >> 4, raw[7] & 15,
                  int.from_bytes(raw[8:10], "big"),
                  raw[HEADER:-TAG - signature_size],
                  raw[-TAG - signature_size:-TAG] if signature_size else bytes(ORIGIN_SIGNATURE))
    if not _valid(frame):
        raise LinkError("invalid authenticated frame")
    return frame


def kiss_encode(raw):
    """One KISS data frame, command byte 0, with escaped FEND/FESC."""
    if not 1 <= len(raw) <= MAX_FRAME:
        raise LinkError("KISS payload outside radio frame limit")
    escaped = bytearray([FEND, 0])
    for byte in raw:
        if byte == FEND:
            escaped.extend((FESC, TFEND))
        elif byte == FESC:
            escaped.extend((FESC, TFESC))
        else:
            escaped.append(byte)
    escaped.append(FEND)
    return bytes(escaped)


class KissStream:
    """Incremental decoder. Invalid escapes and oversized frames are discarded until FEND."""

    def __init__(self):
        self.buffer = bytearray()
        self.in_frame = False
        self.escaped = False
        self.dropped = False

    def feed(self, data):
        frames = []
        for byte in data:
            if byte == FEND:
                if self.in_frame and not self.dropped and not self.escaped and len(self.buffer) >= 2 and self.buffer[0] == 0:
                    frames.append(bytes(self.buffer[1:]))
                self.buffer.clear()
                self.in_frame, self.escaped, self.dropped = True, False, False
                continue
            if not self.in_frame or self.dropped:
                continue
            if self.escaped:
                self.escaped = False
                if byte == TFEND:
                    byte = FEND
                elif byte == TFESC:
                    byte = FESC
                else:
                    self.dropped = True
                    continue
            elif byte == FESC:
                self.escaped = True
                continue
            if len(self.buffer) >= MAX_FRAME + 1:
                self.dropped = True
            else:
                self.buffer.append(byte)
        return frames


class Receiver:
    """KISS-side receive adapter for a root node. `admit(envelope)` must return only
    after SQLite and the encrypted medium are durable. A failed admission gets no HACK.
    The radio node enforces CAD, silence debt and transmit limits when sent a KISS frame.
    """

    def __init__(self, network, root, key, write, admit, silent=lambda: False):
        if not _id(network) or not _id(root) or len(key) != 32:
            raise LinkError("invalid receiver network binding")
        self.network, self.root, self.key = network, root, bytes(key)
        self.write, self.admit, self.silent = write, admit, silent
        self.stream = KissStream()

    def feed(self, data):
        """Process one serial read; return the count of authenticated DATA frames admitted."""
        accepted = 0
        for raw in self.stream.feed(data):
            try:
                frame = decode(self.key, self.network, raw)
                if frame.kind != DATA or frame.destination not in (self.root, BROADCAST):
                    continue
                self.admit(frame.payload)
                accepted += 1
                if frame.flags & ACKREQ and not self.silent():
                    hack = Frame(HACK, 0, self.network, self.root, frame.source, 0, 1, frame.sequence)
                    self.write(kiss_encode(encode(self.key, hack)))
            except (LinkError, ValueError, OSError, sqlite3.Error):
                continue  # failed authentication/admission/write: never claim successful hop receipt
        return accepted
