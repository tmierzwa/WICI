# SPDX-License-Identifier: MIT
"""WICI-Link v3 wire and bounded KISS framing for the receiving station node.

This module only authenticates and parses link frames. The caller must durably admit
DATA before it asks the node to send HACK; a valid MAC alone is never an admission.
"""

from dataclasses import dataclass
import hmac

HEADER, TAG, MAX_FRAME = 11, 8, 255
VERSION = 3  # v3: DATA without the v2 origin signature; v2 frames are rejected
MAX_PAYLOAD = MAX_FRAME - HEADER - TAG - 8  # 228 B: unicast radio frames carry an 8 B hop tag
BROADCAST = 0xFFFF
DATA, HACK, BEACON = 0, 1, 2
ACKREQ, DOWN = 1, 2
FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD
KISS_DATA, KISS_REFUSED = 0, 1  # the root returns a frame it cannot transmit with command 1
# Laptop to root: a HACK with command 2 is sent without learning a down route to the envelope's sender (the
# admission was not fresh or the sender not authenticated); command 0 lets the root learn it (wici-link.md).
KISS_HACK_NO_LEARN = 2


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
    return hmac.digest(prk, b"WICI link v3\x01", "sha256")


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


def _valid(frame):
    if (type(frame.kind) is not int or not _id(frame.network) or not _id(frame.source) or
            not (_id(frame.destination) or frame.destination == BROADCAST) or
            type(frame.flags) is not int or frame.flags & ~3 or
            type(frame.hops) is not int or type(frame.ttl) is not int or
            not 0 <= frame.hops <= frame.ttl <= 15 or frame.ttl == 0 or
            type(frame.sequence) is not int or not 0 <= frame.sequence <= 0xFFFF or
            len(frame.payload) > MAX_PAYLOAD):
        return False
    if frame.kind == DATA:
        return len(frame.payload) >= 25 and (frame.destination != BROADCAST or not frame.flags & ACKREQ)
    if frame.kind == HACK:
        return _id(frame.destination) and frame.flags == 0 and not frame.payload
    if frame.kind == BEACON:
        return frame.destination == BROADCAST and frame.flags == 0 and len(frame.payload) == 137
    return False


def encode(key, frame):
    if len(key) != 32 or not _valid(frame):
        raise LinkError("invalid WICI-Link frame")
    head = (bytes([(VERSION << 6) | (frame.kind << 3) | frame.flags]) +
            _u16(frame.network) + _u16(frame.source) + frame.destination.to_bytes(2, "big") +
            bytes([(frame.hops << 4) | frame.ttl]) + frame.sequence.to_bytes(2, "big") + b"\0")
    body = head + bytes(frame.payload)
    return body + hmac.digest(bytes(key), body, "sha256")[:TAG]


def decode(key, net_id, wire):
    """Authenticate before reading routing fields. Reject unknown versions and reserved bits."""
    raw = bytes(wire)
    if len(key) != 32 or not _id(net_id) or not HEADER + TAG <= len(raw) <= MAX_FRAME:
        raise LinkError("invalid frame length, key or network")
    if not hmac.compare_digest(raw[-TAG:], hmac.digest(bytes(key), raw[:-TAG], "sha256")[:TAG]):
        raise LinkError("WICI-Link MAC failed")
    first = raw[0]
    if first >> 6 != VERSION or first & 4 or raw[10] != 0 or int.from_bytes(raw[1:3], "big") != net_id:
        raise LinkError("unsupported frame header or wrong network")
    frame = Frame((first >> 3) & 7, first & 3, net_id, int.from_bytes(raw[3:5], "big"),
                  int.from_bytes(raw[5:7], "big"), raw[7] >> 4, raw[7] & 15,
                  int.from_bytes(raw[8:10], "big"), raw[HEADER:-TAG])
    if not _valid(frame):
        raise LinkError("invalid authenticated frame")
    return frame


def kiss_encode(raw, command=KISS_DATA):
    """One KISS frame (command byte 0 by default) with escaped FEND/FESC."""
    if not 1 <= len(raw) <= MAX_FRAME:
        raise LinkError("KISS payload outside radio frame limit")
    escaped = bytearray([FEND, command])
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
    """Incremental decoder. Invalid escapes and oversized frames are discarded until FEND.

    feed() returns data frames (command 0); feed_commands() also returns frames the root
    refused to transmit (command 1, the same bytes the laptop wrote), as (command, bytes).
    """

    def __init__(self):
        self.buffer = bytearray()
        self.in_frame = False
        self.escaped = False
        self.dropped = False

    def feed(self, data):
        return [frame for command, frame in self.feed_commands(data) if command == KISS_DATA]

    def feed_commands(self, data):
        frames = []
        for byte in data:
            if byte == FEND:
                if (self.in_frame and not self.dropped and not self.escaped and len(self.buffer) >= 2 and
                        self.buffer[0] in (KISS_DATA, KISS_REFUSED)):
                    frames.append((self.buffer[0], bytes(self.buffer[1:])))
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
