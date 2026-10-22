# SPDX-License-Identifier: MIT
"""Test vectors for the station Reticulum core, made by reference Reticulum (Python) at the pinned commit.

Stage R0 of the core (firmware/reticulum-core.md): identity (keys, hash, signatures, including a
non-canonical signature with S + L), encryption to an identity (token, including damaged tokens and
tokens with a valid HMAC over a bad ciphertext, as a node with the key could send them) and
packets (HEADER_1 as packed by Reticulum, HEADER_2 as rewritten by its transport, packet hash). Every
expected value is what the reference implementation computes or returns; nothing is computed here
by other code. Randomness (ephemeral X25519 key, token IV, announce random hash) is replaced by a
seeded generator only for the duration of each call, so the output is the same on every run.

Run with a Python that has Reticulum at the pinned commit (e40191b, version 1.5.5):
  .venv-rns/bin/python firmware/tools/rns_vectors.py > tests/vectors/reticulum.json
tests/test_rns_vectors.py compares the committed file with a fresh run when WICI_RNS_PYTHON is set.
"""

import hashlib
import json
import os
import sys
from unittest import mock

import RNS
from RNS.Cryptography import X25519PrivateKey
from RNS.Cryptography.AES import AES_256_CBC

RNS_VERSION = "1.5.5"
RNS_COMMIT = "e40191b3d193b46b7f2d8a44424a594cd758839b"
APP_NAME = "wici"
ASPECT = "sa1"
# Rząd grupy Ed25519 (RFC 8032): podpis z S + L jest niekanoniczny i ma zostać odrzucony.
ED25519_L = 2**252 + 27742317777372353535851937790883648493


def seeded(label: str, length: int) -> bytes:
    out, counter = b"", 0
    while len(out) < length:
        out += hashlib.sha256(f"wici-r0:{label}:{counter}".encode()).digest()
        counter += 1
    return out[:length]


class Deterministic:
    """Replaces the randomness Reticulum draws while one vector is made."""

    def __init__(self, label: str):
        self.label, self.draws = label, 0

    def urandom(self, n: int) -> bytes:
        self.draws += 1
        return seeded(f"{self.label}:urandom:{self.draws}", n)

    def x25519(self):
        self.draws += 1
        return X25519PrivateKey.from_private_bytes(seeded(f"{self.label}:x25519:{self.draws}", 32))

    def __enter__(self):
        self.patches = [mock.patch("os.urandom", self.urandom),
                        mock.patch.object(X25519PrivateKey, "generate", self.x25519)]
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()


def identity(label: str) -> RNS.Identity:
    return RNS.Identity.from_bytes(seeded(f"identity:{label}", 64))


def identity_vectors():
    out = []
    for label in ("a", "b"):
        ident = identity(label)
        signatures = []
        for message in (b"", b"WICI", seeded(f"message:{label}", 500)):
            signature = ident.sign(message)
            s = int.from_bytes(signature[32:], "little") + ED25519_L
            non_canonical = signature[:32] + s.to_bytes(32, "little")
            tampered = bytes([message[0] ^ 1]) + message[1:] if message else b"\x00"
            signatures.append({
                "message": message.hex(),
                "signature": signature.hex(),
                "valid": ident.validate(signature, message),
                "tampered_message": tampered.hex(),
                "tampered_valid": ident.validate(signature, tampered),
                "non_canonical_signature": non_canonical.hex(),
                "non_canonical_valid": ident.validate(non_canonical, message),
            })
        destination = RNS.Destination(ident, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, ASPECT)
        out.append({
            "private_key": ident.get_private_key().hex(),
            "public_key": ident.get_public_key().hex(),
            "hash": ident.hash.hex(),
            "destination_wici_sa1": destination.hash.hex(),
            "signatures": signatures,
        })
    return out


def token_vectors():
    out = []
    ident = identity("a")
    receiver = RNS.Identity.from_bytes(ident.get_private_key())
    for length in (0, 1, 15, 16, 17, 300):
        plaintext = seeded(f"plaintext:{length}", length)
        with Deterministic(f"token:{length}"):
            token = ident.encrypt(plaintext)
        # Kolejność losowań w Identity.encrypt: klucz efemeryczny, potem IV w Token.encrypt.
        ephemeral = seeded(f"token:{length}:x25519:1", 32)
        iv = seeded(f"token:{length}:urandom:2", 16)
        if X25519PrivateKey.from_private_bytes(ephemeral).public_key().public_bytes() != token[:32] or iv != token[32:48]:
            sys.exit(f"token {length}: recorded ephemeral key or IV differs from the token")
        out.append({
            "identity_private_key": ident.get_private_key().hex(),
            "ephemeral_private_key": ephemeral.hex(),
            "iv": iv.hex(),
            "plaintext": plaintext.hex(),
            "token": token.hex(),
            "decrypted": receiver.decrypt(token).hex(),
        })
    return out


def crafted_token_vectors():
    """Damaged tokens and tokens with a valid HMAC; decrypted is what Identity.decrypt returns (None = rejected)."""
    ident = identity("a")
    with Deterministic("crafted"):
        valid = ident.encrypt(b"WICI")
    eph = X25519PrivateKey.from_private_bytes(seeded("crafted:ephemeral", 32))
    shared = eph.exchange(ident.pub)
    derived = RNS.Cryptography.hkdf(length=RNS.Identity.DERIVED_KEY_LENGTH, derive_from=shared,
                                    salt=ident.get_salt(), context=ident.get_context())
    iv = seeded("crafted:iv", 16)

    def signed(ciphertext: bytes) -> bytes:
        # Węzeł z kluczem sieci może wysłać dowolny szyfrogram z poprawnym HMAC (klucz z ECDH z kluczem celu).
        parts = iv + ciphertext
        return eph.public_key().public_bytes() + parts + RNS.Cryptography.HMAC.new(derived[:32], parts).digest()

    def block(last: int) -> bytes:
        # Jeden blok AES-256-CBC, którego tekst jawny kończy się bajtem dopełnienia last.
        return AES_256_CBC.encrypt(seeded(f"crafted:block:{last}", 15) + bytes([last]), derived[32:], iv)

    cases = {
        "bad_hmac": valid[:-1] + bytes([valid[-1] ^ 1]),
        "bad_iv": valid[:40] + bytes([valid[40] ^ 1]) + valid[41:],
        "bad_ciphertext": valid[:48] + bytes([valid[48] ^ 1]) + valid[49:],
        "truncated_to_ephemeral_key": valid[:32],
        "truncated_to_iv": valid[:48],
        "only_ephemeral_key_and_hmac": valid[:32] + valid[-32:],
        "valid_hmac_empty_ciphertext": signed(b""),
        "valid_hmac_ciphertext_not_whole_blocks": signed(block(1) + b"\x00"),
        "valid_hmac_padding_above_block": signed(block(0x20)),
        # Python nie sprawdza bajtów dopełnienia ani zera: tekst jawny to blok bez last bajtów.
        "valid_hmac_padding_zero": signed(block(0)),
        "valid_hmac_padding_inconsistent": signed(block(2)),
    }
    return [{"name": name, "identity_private_key": ident.get_private_key().hex(), "token": token.hex(),
             "decrypted": None if (p := ident.decrypt(token)) is None else p.hex()}
            for name, token in cases.items()]


def parsed(raw: bytes) -> dict:
    p = RNS.Packet(None, raw)
    if not p.unpack():
        return {"raw": raw.hex(), "valid": False}
    return {
        "raw": raw.hex(),
        "valid": True,
        "header_type": p.header_type,
        "context_flag": p.context_flag,
        "transport_type": p.transport_type,
        "destination_type": p.destination_type,
        "packet_type": p.packet_type,
        "hops": p.hops,
        "transport_id": p.transport_id.hex() if p.transport_id else None,
        "destination_hash": p.destination_hash.hex(),
        "context": p.context,
        "data": p.data.hex(),
        "hash": p.get_hash().hex(),
        "truncated_hash": p.getTruncatedHash().hex(),
    }


def header_two(raw: bytes, transport_id: bytes) -> bytes:
    # Jak Transport.outbound w Pythonie: HEADER_2, TRANSPORT, niższe bity flag bez zmian, identyfikator po skokach.
    flags = (RNS.Packet.HEADER_2 << 6) | (RNS.Transport.TRANSPORT << 4) | (raw[0] & 0b00001111)
    return bytes([flags, raw[1]]) + transport_id + raw[2:]


def packet_vectors():
    out = []
    ident = identity("b")
    single = RNS.Destination(ident, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, ASPECT)
    plain = RNS.Destination(None, RNS.Destination.OUT, RNS.Destination.PLAIN, "rnstransport", "path", "request")
    transport_id = seeded("transport-id", 16)
    for name, destination, data, context in (
        ("single_data", single, seeded("data:single", 120), RNS.Packet.NONE),
        ("single_data_empty", single, b"", RNS.Packet.NONE),
        ("plain_path_request", plain, single.hash + transport_id + seeded("tag", 16), RNS.Packet.NONE),
    ):
        with Deterministic(f"packet:{name}"):
            packet = RNS.Packet(destination, data, context=context, create_receipt=False)
            packet.pack()
        h1 = parsed(packet.raw)
        h2 = parsed(header_two(packet.raw, transport_id))
        out.append({"name": name, "header_1": h1, "header_2": h2})
    for name, raw in (("too_short", b"\x00"), ("header_2_too_short", bytes([0x50, 0]) + transport_id[:8])):
        out.append({"name": name, "header_1": parsed(raw)})
    return out


def main():
    if RNS.__version__ != RNS_VERSION:
        sys.exit(f"Reticulum {RNS.__version__}, expected {RNS_VERSION} ({RNS_COMMIT})")
    vectors = {
        "source": {"reticulum": RNS_VERSION, "commit": RNS_COMMIT, "tool": "firmware/tools/rns_vectors.py"},
        "identity": identity_vectors(),
        "token": token_vectors(),
        "crafted_token": crafted_token_vectors(),
        "packet": packet_vectors(),
    }
    json.dump(vectors, sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
