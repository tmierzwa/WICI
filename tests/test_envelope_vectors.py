# SPDX-License-Identifier: MIT
"""The fixed WICI envelope vector (tests/vectors/envelope.json) against docs/spec/transport.md, „Koperta WICI”.

The vector is checked twice: with the formulas of the specification written out here (X25519, HKDF-SHA-256,
ChaCha20-Poly1305 with the nonce and AAD from „Format”), independently of wici/envelope.py, and with
wici/envelope.py itself. The MCU envelope is compared with envelope.py byte for byte in
tests/test_envelope_cross_language.py.
"""

import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "software" / "laptop"))
VECTOR = json.loads((ROOT / "tests" / "vectors" / "envelope.json").read_text())
HAS_CRYPTO = importlib.util.find_spec("cryptography") is not None


def h(name):
    return bytes.fromhex(VECTOR[name])


@unittest.skipUnless(HAS_CRYPTO, "cryptography for the envelope")
class EnvelopeVectorTest(unittest.TestCase):
    def test_specification_formulas(self):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import x25519
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        u16 = lambda n: n.to_bytes(2, "big")
        sender, recipient = x25519.X25519PrivateKey.from_private_bytes(h("sender_x25519_private")), \
            x25519.X25519PrivateKey.from_private_bytes(h("recipient_x25519_private"))
        pk_a, pk_b = sender.public_key().public_bytes_raw(), recipient.public_key().public_bytes_raw()
        self.assertEqual((pk_a, pk_b), (h("sender_x25519_public"), h("recipient_x25519_public")))
        shared = sender.exchange(x25519.X25519PublicKey.from_public_bytes(pk_b))
        info = b"WICI env v1" + u16(VECTOR["sender"]) + u16(VECTOR["recipient"]) + pk_a + pk_b
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=u16(VECTOR["net_id"]) + b"\x01",
                   info=info).derive(shared)
        self.assertEqual(key, h("key_sender_to_recipient"))
        for item in VECTOR["envelopes"]:
            wires = [bytes.fromhex(w) for w in item["wire"]]
            plaintext = b""
            for number, wire in enumerate(wires, start=0 if len(wires) == 1 else 1):
                kind = (1 << 6) | (number << 4) | 0   # wersja 1, część, rodzaj SA1
                src, dst, ctr = u16(VECTOR["sender"]), u16(VECTOR["recipient"]), item["counter"].to_bytes(4, "big")
                header = bytes([kind]) + src + dst + ctr
                self.assertEqual(wire[:9], header)
                nonce = src + dst + bytes([kind]) + b"\x00\x00\x00" + ctr
                plaintext += ChaCha20Poly1305(key).decrypt(nonce, wire[9:], header)
            self.assertEqual(plaintext, bytes.fromhex(item["plaintext"]))

    def test_reference_implementation(self):
        from wici import envelope
        key = envelope.derive_key(h("sender_x25519_private"), h("recipient_x25519_public"), VECTOR["net_id"],
                                  VECTOR["sender"], VECTOR["recipient"], VECTOR["sender"])
        self.assertEqual(key, h("key_sender_to_recipient"))
        self.assertEqual(envelope.derive_key(h("recipient_x25519_private"), h("sender_x25519_public"),
                                             VECTOR["net_id"], VECTOR["sender"], VECTOR["recipient"],
                                             VECTOR["recipient"]), key)
        for item in VECTOR["envelopes"]:
            sealed = envelope.seal(key, VECTOR["sender"], VECTOR["recipient"], item["counter"],
                                   bytes.fromhex(item["plaintext"]), item["max_payload"])
            self.assertEqual([w.hex() for w in sealed], item["wire"])


if __name__ == "__main__":
    unittest.main()
