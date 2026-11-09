# SPDX-License-Identifier: MIT
"""The durable WICI envelope vectors (tests/vectors/envelope.json) against docs/spec/transport.md, „Koperta WICI”.

The file is the only source of the bytes. It is checked three times: with the formulas of the specification written
out here (X25519, HKDF-SHA-256, ChaCha20-Poly1305 with the nonce and AAD from „Format”), independently of
wici/envelope.py; with wici/envelope.py, the code of the receiving post; and with the station code
(firmware/src/envelope.cpp) through tests/native/envelope_vector_check.cpp, under ASan and UBSan.
"""

import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "software" / "laptop"))
import test_envelope_cross_language as cross  # noqa: E402  (native build under sanitizers)

VECTOR = json.loads((ROOT / "tests" / "vectors" / "envelope.json").read_text(encoding="utf-8"))
ENVELOPES = VECTOR["envelopes"]
REJECTED = VECTOR["rejected"]["cases"]
REJECTED_KEYS = VECTOR["rejected_keys"]["cases"]
HAS_CRYPTO = importlib.util.find_spec("cryptography") is not None
HEADER, TAG, TYPE_SA1, TYPE_PROOF = 9, 16, 0, 1

setUpModule, tearDownModule = cross.setUpModule, cross.tearDownModule


def h(name):
    return bytes.fromhex(VECTOR[name])


def u16(number):
    return number.to_bytes(2, "big")


def kind_of(item, number):
    return (1 << 6) | (number << 4) | item["message_type"]   # wersja 1, część, rodzaj


def numbered(item):
    """(part number, wire hex) of each part of an envelope: 0 for a whole one, otherwise 1 and 2."""
    return enumerate(item["wire"], start=0 if len(item["wire"]) == 1 else 1)


@unittest.skipUnless(HAS_CRYPTO, "cryptography for the envelope")
class SpecificationFormulas(unittest.TestCase):
    @staticmethod
    def direction_key(sender_private, recipient_public, sender, recipient):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import x25519
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        private = x25519.X25519PrivateKey.from_private_bytes(sender_private)
        info = (b"WICI env v1" + u16(sender) + u16(recipient) + private.public_key().public_bytes_raw() +
                recipient_public)
        shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(recipient_public))
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=u16(VECTOR["net_id"]) + b"\x01", info=info).derive(shared)

    @staticmethod
    def decrypt(key, wire):
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
        header = wire[:HEADER]
        nonce = header[1:5] + header[:1] + b"\x00\x00\x00" + header[5:9]
        return ChaCha20Poly1305(key).decrypt(nonce, wire[HEADER:], header)

    def test_keys(self):
        from cryptography.hazmat.primitives.asymmetric import x25519
        for private, public in (("sender_x25519_private", "sender_x25519_public"),
                                ("recipient_x25519_private", "recipient_x25519_public")):
            key = x25519.X25519PrivateKey.from_private_bytes(h(private))
            self.assertEqual(key.public_key().public_bytes_raw(), h(public))
        self.assertEqual(self.direction_key(h("sender_x25519_private"), h("recipient_x25519_public"),
                                            VECTOR["sender"], VECTOR["recipient"]), h("key_sender_to_recipient"))
        self.assertEqual(self.direction_key(h("recipient_x25519_private"), h("sender_x25519_public"),
                                            VECTOR["recipient"], VECTOR["sender"]), h("key_recipient_to_sender"))

    def test_envelopes(self):
        key = h("key_sender_to_recipient")
        for item in ENVELOPES:
            plaintext = b""
            for number, text in numbered(item):
                wire = bytes.fromhex(text)
                header = bytes([kind_of(item, number)]) + u16(VECTOR["sender"]) + u16(VECTOR["recipient"]) + \
                    item["counter"].to_bytes(4, "big")
                self.assertEqual(wire[:HEADER], header)
                plaintext += self.decrypt(key, wire)
            self.assertEqual(plaintext, bytes.fromhex(item["plaintext"]))

    def test_authentic_rejected_envelopes_fail_on_format_and_not_on_the_tag(self):
        from cryptography.exceptions import InvalidTag
        key = h("key_sender_to_recipient")
        for case in REJECTED:
            with self.subTest(case["name"]):
                wire = bytes.fromhex(case["wire"])
                if case["authentic"]:
                    self.decrypt(key, wire)
                elif len(wire) >= HEADER + TAG:
                    with self.assertRaises(InvalidTag):
                        self.decrypt(key, wire)


@unittest.skipUnless(HAS_CRYPTO, "cryptography for the envelope")
class PostCode(unittest.TestCase):
    def setUp(self):
        from wici import envelope
        self.envelope = envelope
        self.key = h("key_sender_to_recipient")
        self.all_paths = (envelope.TYPE_SA1, envelope.TYPE_PROOF)

    def test_keys_from_both_sides_of_both_directions(self):
        derive = self.envelope.derive_key
        net, sender, recipient = VECTOR["net_id"], VECTOR["sender"], VECTOR["recipient"]
        sender_keys = h("sender_x25519_private"), h("recipient_x25519_public")
        recipient_keys = h("recipient_x25519_private"), h("sender_x25519_public")
        self.assertEqual(derive(*sender_keys, net, sender, recipient, sender), self.key)
        self.assertEqual(derive(*recipient_keys, net, sender, recipient, recipient), self.key)
        self.assertEqual(derive(*sender_keys, net, recipient, sender, sender), h("key_recipient_to_sender"))
        self.assertEqual(derive(*recipient_keys, net, recipient, sender, recipient), h("key_recipient_to_sender"))

    def test_seal(self):
        for item in ENVELOPES:
            with self.subTest(item["note"]):
                sealed = self.envelope.seal(self.key, VECTOR["sender"], VECTOR["recipient"], item["counter"],
                                            bytes.fromhex(item["plaintext"]), item["max_payload"], item["message_type"])
                self.assertEqual([wire.hex() for wire in sealed], item["wire"])

    def test_open(self):
        for item in ENVELOPES:
            with self.subTest(item["note"]):
                plaintext = b""
                for number, text in numbered(item):
                    part = self.envelope.open_part(self.key, bytes.fromhex(text), self.all_paths)
                    self.assertEqual((part.sender, part.recipient, part.counter, part.message_type, part.number),
                                     (VECTOR["sender"], VECTOR["recipient"], item["counter"], item["message_type"],
                                      number))
                    plaintext += part.plaintext
                self.assertEqual(plaintext, bytes.fromhex(item["plaintext"]))

    def test_sa1_path_opens_only_sa1(self):
        for item in ENVELOPES:
            for _, text in numbered(item):
                if item["message_type"] == TYPE_SA1:
                    self.envelope.open_part(self.key, bytes.fromhex(text))
                else:
                    with self.assertRaises(self.envelope.EnvelopeError):
                        self.envelope.open_part(self.key, bytes.fromhex(text))

    def test_rejected(self):
        paths = {"sa1": (self.envelope.TYPE_SA1,), "proof": self.all_paths}
        for case in REJECTED:
            with self.subTest(case["name"]):
                with self.assertRaises(self.envelope.EnvelopeError) as caught:
                    self.envelope.open_part(self.key, bytes.fromhex(case["wire"]), paths[case["path"]])
                self.assertEqual(str(caught.exception), case["error_python"])

    def test_rejected_keys(self):
        for case in REJECTED_KEYS:
            with self.subTest(case["name"]):
                with self.assertRaises(self.envelope.EnvelopeError) as caught:
                    self.envelope.derive_key(bytes.fromhex(case["private"]), bytes.fromhex(case["peer_public"]),
                                             case["net_id"], case["sender"], case["recipient"], case["own_id"])
                self.assertEqual(str(caught.exception), case["error_python"])


class StationCode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = cross.native("envelope_vector_check", "envelope", "envelope_counter", "sha2", crypto=True)
        cls.key = VECTOR["key_sender_to_recipient"]

    def answers(self, commands):
        commands = list(commands)
        lines = cross.run(self.binary, stdin="".join(line + "\n" for line in commands)).splitlines()
        self.assertEqual(len(lines), len(commands))
        return lines

    def test_keys_from_both_sides_of_both_directions(self):
        net, sender, recipient = VECTOR["net_id"], VECTOR["sender"], VECTOR["recipient"]
        sender_keys = f"{VECTOR['sender_x25519_private']} {VECTOR['recipient_x25519_public']}"
        recipient_keys = f"{VECTOR['recipient_x25519_private']} {VECTOR['sender_x25519_public']}"
        answers = self.answers((f"derive {sender_keys} {net} {sender} {recipient} {sender}",
                                f"derive {recipient_keys} {net} {sender} {recipient} {recipient}",
                                f"derive {sender_keys} {net} {recipient} {sender} {sender}",
                                f"derive {recipient_keys} {net} {recipient} {sender} {recipient}"))
        back = VECTOR["key_recipient_to_sender"]
        self.assertEqual(answers, [f"OK {self.key}", f"OK {self.key}", f"OK {back}", f"OK {back}"])

    def test_seal(self):
        answers = self.answers(
            f"seal {self.key} {VECTOR['sender']} {VECTOR['recipient']} {item['counter']} {item['max_payload']} "
            f"{item['message_type']} {item['plaintext'] or '-'}" for item in ENVELOPES)
        for item, answer in zip(ENVELOPES, answers, strict=True):
            self.assertEqual(answer, "OK " + " ".join(item["wire"]), item["note"])

    def test_open_sa1_and_refuse_proofs(self):
        """A station opens SA1 only: `openPart` has no path for a delivery proof."""
        expected, commands = [], []
        for item in ENVELOPES:
            plain = bytes.fromhex(item["plaintext"])
            half = (len(plain) + 1) // 2
            bodies = {0: plain, 1: plain[:half], 2: plain[half:]}
            for number, text in numbered(item):
                commands.append(f"open {self.key} {text}")
                expected.append("REJECT" if item["message_type"] == TYPE_PROOF else
                                f"OK {VECTOR['sender']} {VECTOR['recipient']} {item['counter']} {number} "
                                f"{bodies[number].hex() or '-'}")
        self.assertEqual(self.answers(commands), expected)

    def test_rejected(self):
        answers = self.answers(f"open {self.key} {case['wire'] or '-'}" for case in REJECTED)
        for case, answer in zip(REJECTED, answers, strict=True):
            self.assertEqual(answer, "REJECT", case["name"])

    def test_rejected_keys(self):
        answers = self.answers(
            f"derive {case['private']} {case['peer_public']} {case['net_id']} {case['sender']} {case['recipient']} "
            f"{case['own_id']}" for case in REJECTED_KEYS)
        for case, answer in zip(REJECTED_KEYS, answers, strict=True):
            self.assertEqual(answer, "REJECT", case["name"])


class VectorFile(unittest.TestCase):
    def test_covers_both_message_types_and_paths(self):
        self.assertEqual({item["message_type"] for item in ENVELOPES}, {TYPE_SA1, TYPE_PROOF})
        self.assertEqual({case["path"] for case in REJECTED}, {"sa1", "proof"})

    def test_names_are_unique(self):
        names = [case["name"] for case in REJECTED + REJECTED_KEYS]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
