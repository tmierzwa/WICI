# SPDX-License-Identifier: MIT
"""Test vectors for LXMF SA1 messages in the station Reticulum core, made by reference LXMF in Python.

Stage R3 of the core (firmware/reticulum-core.md): an SA1 message (title "SA1", content up to 256 B, empty
fields) in one opportunistic packet, LXMF c3ff2d6 on Reticulum e40191b. Every expected value is what the
reference code computes or returns: the packet data and message hash from LXMessage.pack, and what
LXMessage.unpack_from_bytes makes of received data (exception, or the hash, timestamp, content and
signature_validated). The core accepts only a verified SA1 message from the sender's lxmf.delivery
destination (the vectors give the core the key of "sender"); "core_rejects" names why the core rejects an input, and for inputs the reference accepts
with a valid signature it is a deviation (firmware/reticulum-core.md, table of differences). Keys are
seeded and Ed25519 is deterministic, so the output is the same on every run.

Run with a Python that has Reticulum (e40191b, version 1.5.5) and LXMF (c3ff2d6, version 1.2.0):
  .venv-rns/bin/python firmware/tools/lxmf_vectors.py > tests/vectors/lxmf.json
tests/test_rnscore_lxmf.py compares the committed file with a fresh run when WICI_RNS_PYTHON is set.
"""

import hashlib
import io
import json
import struct
import sys

import RNS
import RNS.vendor.umsgpack as umsgpack
import LXMF
from LXMF.LXMessage import LXMessage

from rns_vectors import ED25519_L, seeded

RNS_VERSION = "1.5.5"
RNS_COMMIT = "e40191b3d193b46b7f2d8a44424a594cd758839b"
LXMF_VERSION = "1.2.0"
LXMF_COMMIT = "c3ff2d6dc2f256daab896dadc044dd5a913ecbb7"
# Najdłuższe dane, które rdzeń przyjmuje (lxmf.h: LXMF_MAX_RECEIVED), i najdłuższa treść SA1.
MAX_RECEIVED = 399
SA1_CONTENT_MAX = 256
REQUEST = '[1,0,"0123456789abcdef0123456789abcdef",3,0,2,"ul. Długa 5, wejście od podwórza","osoba na wózku",2]'.encode()


def packb(value) -> bytes:
    return umsgpack.packb(value)


def sa1_shape(payload: bytes) -> bool:
    """The SA1 payload the core accepts, checked on the encoding: array of 4 (0x94), a number (int or float,
    not bool), bin "SA1", bin content of 1-256 B, an empty map or nil; bytes after the value are ignored."""
    if not payload or payload[0] != 0x94:
        return False
    fp = io.BytesIO(payload[1:])
    try:
        timestamp, title, content = (umsgpack.unpack(fp) for _ in range(3))
        fields_code = fp.read(1)
    except Exception:
        return False
    return (type(timestamp) in (int, float) and type(title) is bytes and title == b"SA1" and type(content) is bytes
            and 1 <= len(content) <= SA1_CONTENT_MAX and fields_code in (b"\x80", b"\xc0"))


class Lxmf:
    """Sender and receiver lxmf.delivery destinations with seeded identities; the receiver knows the senders."""

    def __init__(self):
        self.sender = RNS.Identity.from_bytes(seeded("lxmf:sender", 64))
        self.receiver = RNS.Identity.from_bytes(seeded("lxmf:receiver", 64))
        self.other = RNS.Identity.from_bytes(seeded("lxmf:other", 64))
        self.source = self.delivery(self.sender)
        self.destination = self.delivery(self.receiver)
        self.other_source = self.delivery(self.other)
        # Cel nadawcy o innej nazwie: Python przyjmuje podpis każdego znanego celu tej tożsamości.
        self.sender_wici = RNS.Destination(self.sender, RNS.Destination.OUT, RNS.Destination.SINGLE, "wici", "sa1")
        # Identity.recall w unpack_from_bytes znajduje nadawców jak po ich ogłoszeniach.
        for n, (dest, ident) in enumerate(((self.source, self.sender), (self.other_source, self.other),
                                           (self.sender_wici, self.sender))):
            RNS.Identity.remember(seeded(f"lxmf:announce:{n}", 32), dest.hash, ident.get_public_key())

    @staticmethod
    def delivery(identity):
        return RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, LXMF.APP_NAME, "delivery")

    def built(self, name: str, content: bytes, timestamp: float, title: bytes = b"SA1") -> dict:
        message = LXMessage(self.destination, self.source, content, title, None, desired_method=LXMessage.OPPORTUNISTIC)
        message.timestamp = timestamp
        message.pack()
        return {"name": name, "timestamp": timestamp, "content": content.hex(),
                "data": message.packed[16:].hex(), "hash": message.hash.hex()}

    def signed(self, payload: bytes, signer=None, source=None) -> bytes:
        """Packet data around any payload with a valid signature (any sender can make it)."""
        source = source or self.source
        hashed = self.destination.hash + source.hash + payload
        signature = (signer or self.sender).sign(hashed + hashlib.sha256(hashed).digest())
        return source.hash + signature + payload

    def received(self, name: str, data: bytes) -> dict:
        case = {"name": name, "data": data.hex()}
        try:
            message = LXMessage.unpack_from_bytes(self.destination.hash + data)
        except Exception as e:   # LXMRouter.lxmf_delivery odrzuca wiadomość
            case.update(accepted=False, error=type(e).__name__, core_rejects="reference_rejects")
            return case
        case.update(accepted=True, signature_validated=message.signature_validated, hash=message.hash.hex())
        if not message.signature_validated:
            reason = "signature"
        elif len(data) > MAX_RECEIVED:
            reason = "length"
        elif data[:16] != self.source.hash:
            # Rdzeń dostaje klucz nadawcy "sender" i wymaga, by skrót nadawcy był jego celem lxmf.delivery.
            reason = "sender_key"
        elif not sa1_shape(data[80:]):
            reason = "not_sa1"
        else:
            reason = None
            case.update(timestamp=message.timestamp, content=message.content.hex())
        case["core_rejects"] = reason
        return case


def lxmf_vectors():
    lx = Lxmf()
    t = 1790000000.123456
    built = [
        lx.built("request", REQUEST, t),
        lx.built("received", b'[1,1,"0123456789abcdef0123456789abcdef",3,1,1]', 1790000123.5),
        lx.built("content_1", b"x", 0.0),
        lx.built("content_255", b"c" * 255, t),
        lx.built("content_256", "ż".encode() * 128, t),
        lx.built("timestamp_negative", b"y", -1.5),
        lx.built("timestamp_2_53", b"y", 2.0**53),
        # Rdzeń takich nie składa: treść pusta i ponad 256 B, tytuł inny niż SA1.
        lx.built("content_0", b"", t),
        lx.built("content_257", b"c" * 257, t),
        lx.built("title_other", b"z", t, title=b"SA2"),
    ]

    base = bytes.fromhex(built[0]["data"])
    signature, payload = base[16:80], base[80:]
    s = int.from_bytes(signature[32:], "little") + ED25519_L
    short = bytes.fromhex(built[2]["data"])
    longest = bytes.fromhex(built[4]["data"])

    def payload_of(*parts: bytes) -> bytes:
        return bytes([0x90 | len(parts)]) + b"".join(parts)

    ts, title, content, empty = packb(t), packb(b"SA1"), packb(REQUEST), b"\x80"
    received = [lx.received(f"built_{b['name']}", bytes.fromhex(b["data"])) for b in built]
    received += [
        lx.received("signature_flipped_first", base[:16] + bytes([base[16] ^ 1]) + base[17:]),
        lx.received("signature_flipped_last", base[:79] + bytes([base[79] ^ 0x80]) + base[80:]),
        lx.received("signature_non_canonical", base[:48] + s.to_bytes(32, "little") + base[80:]),
        lx.received("signed_by_other_identity", lx.signed(payload, lx.other)),
        # Klucz nadawcy z wektora nie pasuje do skrótu nadawcy tej wiadomości (test podaje klucz "sender").
        lx.received("other_sender_own_signature", lx.signed(payload, lx.other, lx.other_source)),
        lx.received("sender_wici_sa1_destination", lx.signed(payload, lx.sender, lx.sender_wici)),
        lx.received("source_hash_flipped", bytes([base[0] ^ 1]) + base[1:]),
        lx.received("trailing_bytes", lx.signed(payload + b"\x00\xc1")),
        lx.received("timestamp_int", lx.signed(payload_of(packb(1790000000), title, content, empty))),
        lx.received("timestamp_negative_fixint", lx.signed(payload_of(packb(-5), title, content, empty))),
        lx.received("timestamp_int64_min", lx.signed(payload_of(packb(-2**63), title, content, empty))),
        lx.received("timestamp_uint64_max", lx.signed(payload_of(packb(2**64 - 1), title, content, empty))),
        lx.received("timestamp_int8_positive", lx.signed(payload_of(b"\xd0\x05", title, content, empty))),
        lx.received("timestamp_uint16_small", lx.signed(payload_of(b"\xcd\x00\x05", title, content, empty))),
        lx.received("timestamp_float32", lx.signed(payload_of(b"\xca" + struct.pack(">f", 1.5), title, content, empty))),
        lx.received("timestamp_truncated", lx.signed(b"\x94\xcb\x00\x00")),
        lx.received("fields_nil", lx.signed(payload_of(ts, title, content, b"\xc0"))),
        lx.received("title_bin16", lx.signed(payload_of(ts, b"\xc5\x00\x03SA1", content, empty))),
        lx.received("content_bin32", lx.signed(payload_of(ts, title, b"\xc6" + len(REQUEST).to_bytes(4, "big") + REQUEST, empty))),
        lx.received("content_length_beyond_data", lx.signed(b"\x94" + ts + title + b"\xc6\xff\xff\xff\xff")),
        # Python przyjmuje, rdzeń nie (odstępstwa): kształt inny niż SA1.
        lx.received("fields_not_empty", lx.signed(payload_of(ts, title, content, packb({LXMF.FIELD_RENDERER: 0})))),
        lx.received("fields_ticket_not_number", lx.signed(payload_of(ts, title, content, packb({LXMF.FIELD_TICKET: ["x", bytes(16)]})))),
        lx.received("fields_nested_depth_9", lx.signed(payload_of(ts, title, content, b"\x81\x01" + b"\x91" * 8 + b"\xc0"))),
        lx.received("title_str", lx.signed(payload_of(ts, packb("SA1"), content, empty))),
        lx.received("content_str", lx.signed(payload_of(ts, title, packb(REQUEST.decode()), empty))),
        lx.received("content_empty", lx.signed(payload_of(ts, title, packb(b""), empty))),
        lx.received("content_257", lx.signed(payload_of(ts, title, packb(b"c" * 257), empty))),
        lx.received("title_empty", lx.signed(payload_of(ts, packb(b""), content, empty))),
        lx.received("title_int", lx.signed(payload_of(ts, packb(5), content, empty))),
        lx.received("timestamp_nil", lx.signed(payload_of(packb(None), title, content, empty))),
        lx.received("timestamp_bool", lx.signed(payload_of(packb(True), title, content, empty))),
        lx.received("array16_of_4", lx.signed(b"\xdc\x00\x04" + ts + title + content + empty)),
        lx.received("payload_5_elements_stamp", lx.signed(payload_of(ts, title, content, empty, packb(bytes(32))))),
        lx.received("payload_map", lx.signed(packb({0: t, 1: b"SA1", 2: REQUEST, 3: {}}))),
        lx.received("length_399", lx.signed(payload + bytes(MAX_RECEIVED - len(base)))),
        lx.received("length_400", lx.signed(payload + bytes(MAX_RECEIVED + 1 - len(base)))),
        # Python odrzuca (wyjątek).
        lx.received("fields_list", lx.signed(payload_of(ts, title, content, b"\x90"))),
        lx.received("fields_duplicate_key", lx.signed(payload_of(ts, title, content, b"\x82\x01\x01\x01\x02"))),
        lx.received("fields_reserved_code", lx.signed(payload_of(ts, title, content, b"\x81\x01\xc1"))),
        lx.received("title_invalid_utf8", lx.signed(payload_of(ts, b"\xa1\xff", content, empty))),
        lx.received("payload_3_elements", lx.signed(payload_of(ts, title, content))),
        lx.received("payload_not_container", lx.signed(packb(b"SA1x"))),
        lx.received("payload_empty", lx.signed(b"")),
    ]
    # Każdy bajt payloadu z jednym bitem zmienionym i każda długość obcięta dla trzech wiadomości.
    received += [lx.received(f"payload_flip_{i}", base[:80 + i] + bytes([base[80 + i] ^ (1 << (i % 8))]) + base[81 + i:])
                 for i in range(len(payload))]
    for label, message in (("request", base), ("content_1", short), ("content_256", longest)):
        received += [lx.received(f"truncated_{label}_{n}", message[:n]) for n in range(len(message))]
    return {"sender_private_key": lx.sender.get_private_key().hex(), "sender_public_key": lx.sender.get_public_key().hex(),
            "other_public_key": lx.other.get_public_key().hex(), "source_hash": lx.source.hash.hex(),
            "other_source_hash": lx.other_source.hash.hex(), "destination_hash": lx.destination.hash.hex(),
            "built": built, "received": received}


def main():
    RNS.loglevel = RNS.LOG_NONE
    if RNS.__version__ != RNS_VERSION:
        sys.exit(f"Reticulum {RNS.__version__}, expected {RNS_VERSION} ({RNS_COMMIT})")
    if LXMF.__version__ != LXMF_VERSION:
        sys.exit(f"LXMF {LXMF.__version__}, expected {LXMF_VERSION} ({LXMF_COMMIT})")
    vectors = {
        "source": {"reticulum": RNS_VERSION, "commit": RNS_COMMIT, "lxmf": LXMF_VERSION, "lxmf_commit": LXMF_COMMIT,
                   "tool": "firmware/tools/lxmf_vectors.py"},
        "lxmf": lxmf_vectors(),
    }
    json.dump(vectors, sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
