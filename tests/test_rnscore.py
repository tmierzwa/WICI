# SPDX-License-Identifier: MIT
"""Station Reticulum core (firmware/lib/reticulum_core) against vectors from reference Reticulum.

Builds the core with the Crypto library from firmware/.pio/stack and tests/native/rnscore_check.cpp,
with AddressSanitizer and UndefinedBehaviorSanitizer, the core as C++17 without exceptions and RTTI
and with -Wall -Wextra -Werror (firmware/reticulum-core.md, design requirements). The check program
answers one command per line; expected values come from tests/vectors/reticulum.json (made by
Reticulum in Python, tests/test_rns_vectors.py). Skipped without a compiler or the stack sources,
unless WICI_RNS_SANITIZE=1 (CI), which fetches the sources and fails instead.

  python3 -m unittest tests.test_rnscore -v
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / "firmware"
CORE = FIRMWARE / "lib" / "reticulum_core" / "src"
STACK = FIRMWARE / ".pio" / "stack"
CHECK = ROOT / "tests" / "native" / "rnscore_check.cpp"
VECTORS = json.loads((ROOT / "tests" / "vectors" / "reticulum.json").read_text())
REQUIRED = os.environ.get("WICI_RNS_SANITIZE") == "1"
# Z biblioteki Crypto tylko to, czego rdzeń używa.
CRYPTO_UNITS = ["AES256.cpp", "AESCommon.cpp", "BigNumberUtil.cpp", "BlockCipher.cpp", "ChaCha.cpp", "Cipher.cpp", "Crypto.cpp",
                "Curve25519.cpp", "Ed25519.cpp", "Hash.cpp", "NoiseSource.cpp", "RNG.cpp", "SHA256.cpp", "SHA512.cpp"]
SANITIZE = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g", "-O1"]
# Rdzeń nie używa sterty, więc wyciek to błąd (LeakSanitizer działa na Linuksie, nie na macOS).
LEAKS = "1" if sys.platform.startswith("linux") else "0"
ENV = dict(os.environ, ASAN_OPTIONS=f"detect_leaks={LEAKS}:halt_on_error=1", UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")

sys.path.insert(0, str(FIRMWARE / "tools"))
import stack_deps  # noqa: E402


def compiler():
    for name in ("clang++", "c++", "g++"):
        if shutil.which(name):
            return name
    return None


def build(out_dir: Path) -> Path:
    cxx = compiler()
    base = [cxx, "-std=c++17", *SANITIZE, f"-I{CORE}", "-isystem", str(STACK / "Crypto")]
    objects = []
    for source in sorted(CORE.glob("*.cpp")):
        objects.append(out_dir / f"core_{source.stem}.o")
        subprocess.run([*base, "-fno-exceptions", "-fno-rtti", "-Wall", "-Wextra", "-Werror", "-c", str(source),
                        "-o", str(objects[-1])], check=True, capture_output=True, text=True)
    for name in CRYPTO_UNITS:
        objects.append(out_dir / f"crypto_{Path(name).stem}.o")
        subprocess.run([*base, "-w", "-c", str(STACK / "Crypto" / name), "-o", str(objects[-1])],
                       check=True, capture_output=True, text=True)
    objects.append(out_dir / "rnscore_check.o")
    subprocess.run([*base, "-Wall", "-Wextra", "-Werror", "-c", str(CHECK), "-o", str(objects[-1])],
                   check=True, capture_output=True, text=True)
    binary = out_dir / "rnscore_check"
    subprocess.run([cxx, *SANITIZE, *map(str, objects), "-o", str(binary)], check=True, capture_output=True, text=True)
    return binary


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "posix":
            raise unittest.SkipTest("POSIX only")
        if not compiler():
            raise unittest.SkipTest("no C++ compiler")
        if not (STACK / "Crypto" / ".wici-stamp").is_file():
            if not REQUIRED:
                raise unittest.SkipTest("stack sources not fetched (python3 firmware/tools/stack_deps.py)")
            stack_deps.fetch(FIRMWARE)
        cls.tmp = tempfile.TemporaryDirectory()
        try:
            cls.binary = build(Path(cls.tmp.name))
        except subprocess.CalledProcessError as e:
            cls.tmp.cleanup()
            raise RuntimeError(f"{' '.join(e.cmd)}\n{e.stderr[-4000:]}") from e

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def ask(self, commands):
        """Run the check program on (command, data) pairs; one output line per command."""
        stdin = "".join(f"{command} {data.hex()}\n" for command, data in commands)
        result = subprocess.run([str(self.binary)], input=stdin, capture_output=True, text=True, env=ENV, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), len(commands), result.stdout)
        return lines

    def test_identity_hash(self):
        # Identity.hash = truncated_hash(klucz publiczny), wartości z Reticulum w Pythonie.
        identities = VECTORS["identity"]
        got = self.ask([("truncated_hash", bytes.fromhex(i["public_key"])) for i in identities])
        self.assertEqual(got, [i["hash"] for i in identities])

    def test_public_key_and_hash(self):
        # Load_private_key: X25519 przycięty jak w RFC 7748, Ed25519 z ziarna; wartości z Pythona.
        identities = VECTORS["identity"]
        got = self.ask([("public_key", bytes.fromhex(i["private_key"])) for i in identities] +
                       [("identity_hash", bytes.fromhex(i["public_key"])) for i in identities])
        self.assertEqual(got, [i["public_key"] for i in identities] + [i["hash"] for i in identities])

    def test_signatures(self):
        # Podpis Ed25519 jest deterministyczny, więc ma być bajt w bajt taki jak w Pythonie.
        commands, expected = [], []
        for ident in VECTORS["identity"]:
            prv, pub = bytes.fromhex(ident["private_key"]), bytes.fromhex(ident["public_key"])
            for s in ident["signatures"]:
                message = bytes.fromhex(s["message"])
                commands.append(("sign", prv + message))
                expected.append(s["signature"])
                for signature, text, valid in ((s["signature"], s["message"], s["valid"]),
                                               (s["signature"], s["tampered_message"], s["tampered_valid"]),
                                               (s["non_canonical_signature"], s["message"], s["non_canonical_valid"])):
                    commands.append(("validate", self.validate_args(pub, bytes.fromhex(signature), bytes.fromhex(text))))
                    expected.append("1" if valid else "0")
        self.assertEqual(self.ask(commands), expected)

    def test_signature_with_wrong_length(self):
        # Python odrzuca podpis o złej długości (wyjątek w verify, validate zwraca False).
        ident = VECTORS["identity"][0]
        pub = bytes.fromhex(ident["public_key"])
        s = ident["signatures"][1]
        signature, message = bytes.fromhex(s["signature"]), bytes.fromhex(s["message"])
        got = self.ask([("validate", self.validate_args(pub, sig, message))
                        for sig in (signature[:63], signature + b"\x00", b"")])
        self.assertEqual(got, ["0", "0", "0"])

    @staticmethod
    def validate_args(public_key: bytes, signature: bytes, message: bytes) -> bytes:
        return public_key + len(signature).to_bytes(2, "big") + signature + message

    def test_token_decrypt(self):
        # Tokeny z Identity.encrypt w Pythonie (0, 1, 15, 16, 17 i 300 B tekstu jawnego).
        tokens = VECTORS["token"]
        got = self.ask([("decrypt", bytes.fromhex(t["identity_private_key"] + t["token"])) for t in tokens])
        self.assertEqual(got, [t["decrypted"] for t in tokens])

    def test_token_encrypt(self):
        # Z tym samym kluczem efemerycznym i IV token ma być bajt w bajt taki jak w Pythonie.
        tokens = VECTORS["token"]
        commands = []
        for t in tokens:
            commands.append(("public_key", bytes.fromhex(t["identity_private_key"])))
        public_keys = [bytes.fromhex(k) for k in self.ask(commands)]
        got = self.ask([("encrypt", pub + bytes.fromhex(t["ephemeral_private_key"] + t["iv"] + t["plaintext"]))
                        for pub, t in zip(public_keys, tokens)])
        self.assertEqual(got, [t["token"] for t in tokens])

    def test_crafted_tokens(self):
        # Uszkodzone tokeny, tokeny z poprawnym HMAC i klucze efemeryczne niskiego rzędu albo spoza ciała:
        # odpowiedź ma być ta sama co z Identity.decrypt (None = odrzucony).
        cases = VECTORS["crafted_token"]
        got = self.ask([("decrypt", bytes.fromhex(c["identity_private_key"] + c["token"])) for c in cases])
        self.assertEqual(dict(zip((c["name"] for c in cases), got)),
                         {c["name"]: "none" if c["decrypted"] is None else c["decrypted"] for c in cases})

    def test_token_every_length(self):
        # Każda długość od 0 do 2 bloków ponad narzut: odrzucenie bez błędu pamięci (ASan), poza pełną długością.
        t = VECTORS["token"][3]
        prv, token = bytes.fromhex(t["identity_private_key"]), bytes.fromhex(t["token"])
        got = self.ask([("decrypt", prv + token[:n]) for n in range(len(token) + 1)])
        self.assertEqual(got, ["none"] * len(token) + [t["decrypted"]])

    def test_encrypt_to_low_order_key(self):
        # Python zgłasza błąd w exchange, gdy klucz X25519 celu jest niskiego rzędu (wspólny sekret zerowy).
        t = VECTORS["token"][0]
        ed25519 = bytes.fromhex(VECTORS["identity"][0]["public_key"])[32:]
        rest = bytes.fromhex(t["ephemeral_private_key"] + t["iv"]) + b"WICI"
        got = self.ask([("encrypt", x25519 + ed25519 + rest) for x25519 in (bytes(32), (1).to_bytes(32, "little"))])
        self.assertEqual(got, ["none", "none"])

    @staticmethod
    def unpacked(h: dict) -> str:
        # Wiersz programu prób dla pakietu z wektora (pola jak w Packet.unpack, skrót z get_hash).
        if not h["valid"]:
            return "none"
        return " ".join(str(h[k]) for k in ("header_type", "context_flag", "transport_type", "destination_type",
                                             "packet_type", "hops")) + \
            f" {h['transport_id'] or '-'} {h['destination_hash']} {h['context']} {h['data']} {h['hash']}"

    def test_packet_unpack(self):
        # Pakiety złożone przez Reticulum (HEADER_1, HEADER_2 po transporcie) i spreparowane: te same pola
        # i skrót co w Pythonie, odrzucone te same.
        cases = [(f"{p['name']}:{h}", p[h]) for p in VECTORS["packet"] for h in ("header_1", "header_2") if h in p]
        got = self.ask([("unpack", bytes.fromhex(h["raw"])) for _, h in cases])
        self.assertEqual(dict(zip((n for n, _ in cases), got)), {n: self.unpacked(h) for n, h in cases})
        for _, h in cases:
            if h["valid"]:
                self.assertEqual(h["truncated_hash"], h["hash"][:32])

    def test_packet_pack(self):
        # Z pól przyjętego pakietu pack składa te same bajty (Packet.pack w Pythonie albo przepisanie transportu).
        commands, expected = [], []
        for p in VECTORS["packet"]:
            for h in (p.get("header_1"), p.get("header_2")):
                # Bit IFAC (0x80) pack nie ustawia; flaga kontekstu, skoki, MTU i LRPROOF: osobno niżej.
                if not h or not h["valid"] or h["hops"] != 0 or len(h["raw"]) // 2 > 500 or int(h["raw"][:2], 16) & 0xA0 \
                        or h["context"] == 0xFF:
                    continue
                commands.append(("pack", self.pack_args(h)))
                expected.append(h["raw"])
        self.assertGreaterEqual(len(commands), 7)
        self.assertEqual(self.ask(commands), expected)

    def test_packet_pack_flags_and_limits(self):
        # Flaga kontekstu i typy w bajcie flag; odmowa przy 128 skokach, pustych danych, ponad MTU (500 B) i dla LRPROOF.
        by_name = {p["name"]: p["header_1"] for p in VECTORS["packet"]}
        context = by_name["context_flag_set"]
        types = by_name["link_proof_types"]
        hops = by_name["hops_127"]
        empty = dict(hops, data="")
        over = dict(by_name["above_mtu"])
        at_mtu = dict(over, data=over["data"][:2 * (500 - 19)])
        too_many = dict(hops, hops=128)
        link_proof = dict(hops, context=0xFF)   # LRPROOF: łącza poza rdzeniem
        got = self.ask([("pack", self.pack_args(h))
                        for h in (context, types, hops, empty, over, at_mtu, too_many, link_proof)])
        self.assertEqual(got[:3], [context["raw"], types["raw"], hops["raw"]])
        self.assertEqual(got[3:5], ["none", "none"])
        self.assertEqual(len(got[5]) // 2, 500)
        self.assertEqual(got[6:], ["none", "none"])

    def test_packet_every_length(self):
        # Każda długość obciętego pakietu HEADER_2: do 35 B (nagłówek bez danych) odrzucony, dalej przyjęty;
        # ASan pilnuje odczytu poza buforem.
        raw = bytes.fromhex(VECTORS["packet"][0]["header_2"]["raw"])
        got = self.ask([("unpack", raw[:n]) for n in range(len(raw) + 1)])
        self.assertEqual([line == "none" for line in got], [n <= 35 for n in range(len(raw) + 1)])

    @staticmethod
    def pack_args(h: dict) -> bytes:
        return bytes([h["header_type"], h["context_flag"], h["transport_type"], h["destination_type"], h["packet_type"],
                      h["hops"]]) + bytes.fromhex(h["transport_id"] or "00" * 16) + bytes.fromhex(h["destination_hash"]) + \
            bytes([h["context"]]) + bytes.fromhex(h["data"])

    def test_full_hash_matches_sha256(self):
        # Pusty wejściowy ciąg, granice bloku SHA-256 (55, 56, 64 B) i długi ciąg.
        inputs = [b"", b"WICI", bytes(55), bytes(56), bytes(64), bytes(range(256)) * 20]
        got = self.ask([("full_hash", data) for data in inputs])
        self.assertEqual(got, [hashlib.sha256(data).hexdigest() for data in inputs])

    def test_bad_input(self):
        result = subprocess.run([str(self.binary)], input="full_hash abc\nfull_hash zz\nunknown 00\n\n", capture_output=True,
                                text=True, env=ENV, timeout=60)
        self.assertEqual(result.stdout.splitlines(), ["error"] * 4)


if __name__ == "__main__":
    unittest.main()
