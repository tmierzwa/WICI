# SPDX-License-Identifier: MIT
"""Python reference of firmware/src/migration_crypto.* (station migration v1) for the cross-language
vectors in tests/test_migration_crypto.py. Neither package ships it: the laptop only relays the package.
"""

import hmac

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


HEADER = 101
PART = 512
TAG = 16


def _fixed(value, length):
    raw = bytes(value)
    if len(raw) != length:
        raise ValueError(f"expected {length} bytes")
    return raw


def public_key(private_key):
    return x25519.X25519PrivateKey.from_private_bytes(_fixed(private_key, 32)).public_key().public_bytes_raw()


def derive(private_key, peer_public, mid):
    private = x25519.X25519PrivateKey.from_private_bytes(_fixed(private_key, 32))
    peer = x25519.X25519PublicKey.from_public_bytes(_fixed(peer_public, 32))
    mid = _fixed(mid, 16)
    shared = private.exchange(peer)
    if shared == bytes(32):
        raise ValueError("invalid X25519 peer key")

    def expand(label):
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=mid, info=label + mid).derive(shared)

    return expand(b"WICI migrate"), expand(b"WICI migrate pkg")


def make_header(mid, identity_digest, ephemeral_public, package_hash, plaintext_size):
    if not 1 <= plaintext_size <= 0xFFFFFFFF:
        raise ValueError("invalid package size")
    return (b"\x01" + _fixed(mid, 16) + _fixed(identity_digest, 16) +
            _fixed(ephemeral_public, 32) + _fixed(package_hash, 32) + plaintext_size.to_bytes(4, "big"))


def parse_header(header, mid, max_size):
    raw = _fixed(header, HEADER)
    if raw[0] != 1 or raw[1:17] != _fixed(mid, 16):
        raise ValueError("wrong migration header")
    size = int.from_bytes(raw[97:101], "big")
    if not 1 <= size <= max_size:
        raise ValueError("invalid package size")
    return {"identity_digest": raw[17:33], "ephemeral_public": raw[33:65],
            "package_hash": raw[65:97], "plaintext_size": size}


def _nonce(index):
    if type(index) is not int or not 0 <= index <= 0xFFFFFFFF:
        raise ValueError("invalid part index")
    return b"WMIG" + bytes(4) + index.to_bytes(4, "big")


def seal_part(package_key, header, index, plaintext):
    raw = bytes(plaintext)
    if not 1 <= len(raw) <= PART:
        raise ValueError("invalid part size")
    header = _fixed(header, HEADER)
    if header[0] != 1:
        raise ValueError("invalid header version")
    return ChaCha20Poly1305(_fixed(package_key, 32)).encrypt(
        _nonce(index), raw, header + index.to_bytes(4, "big"))


def open_part(package_key, header, index, ciphertext):
    raw = bytes(ciphertext)
    if not TAG < len(raw) <= PART + TAG:
        raise ValueError("invalid part size")
    header = _fixed(header, HEADER)
    if header[0] != 1:
        raise ValueError("invalid header version")
    try:
        return ChaCha20Poly1305(_fixed(package_key, 32)).decrypt(
            _nonce(index), raw, header + index.to_bytes(4, "big"))
    except InvalidTag as exc:
        raise ValueError("invalid part authentication") from exc


def confirmation(confirm_key, kind, mid, package_hash=None):
    if kind not in ("imported", "retired", "aborted"):
        raise ValueError("invalid confirmation kind")
    message = kind.encode("ascii") + _fixed(mid, 16)
    if kind != "aborted":
        message += _fixed(package_hash, 32)
    return hmac.digest(_fixed(confirm_key, 32), message, "sha256")

