# SPDX-License-Identifier: MIT
"""Station Reticulum core (firmware/lib/reticulum_core) against vectors from reference Reticulum.

Builds the core with the Crypto library from firmware/.pio/stack and tests/native/rnscore_check.cpp,
with AddressSanitizer and UndefinedBehaviorSanitizer, the core as C++17 without exceptions and RTTI
and with -Wall -Wextra -Werror (firmware/reticulum-core.md, design requirements). The check program
answers one command per line; expected values come from tests/vectors/reticulum.json (made by
Reticulum in Python, tests/test_rns_vectors.py). Skipped without a compiler or the stack sources,
unless WICI_RNS_SANITIZE=1 (CI), which fetches the sources and fails instead.

Core32Tests run the same checks on a 32-bit build (-m32 -funsigned-char): size_t of 32 bits, 32-bit
limbs in Curve25519 and Ed25519 of the Crypto library and unsigned char, as on nRF52840 and ESP32-S3
(a 64-bit computer uses 64-bit limbs, BigNumberUtil.h). x86 tolerates unaligned access, which Xtensa
does not; UBSan reports only part of it (misaligned pointers of typed accesses). Alignment of uint64_t
differs too (4 B on i386, 8 B on the boards). Skipped when the compiler cannot build 32-bit programs
(macOS, Linux without gcc-multilib), unless WICI_RNS_SANITIZE=1 on Linux.

  python3 -m unittest tests.test_rnscore -v
"""

import hashlib
import json
import os
import re
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
# Samotest kryptografii rdzenia z obrazów płytek (kod WICI w firmware/src, hexstr.h).
SELFTEST = FIRMWARE / "src" / "core_selftest.cpp"
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


def compiler(names=("clang++", "c++", "g++")):
    for name in names:
        if shutil.which(name):
            return name
    return None


def build(out_dir: Path, cxx: str, flags=()) -> Path:
    base = [cxx, "-std=c++17", *flags, *SANITIZE, f"-I{CORE}", f"-I{SELFTEST.parent}", "-isystem", str(STACK / "Crypto")]
    objects = []
    for source in [*sorted(CORE.glob("*.cpp")), SELFTEST]:
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
    subprocess.run([cxx, *flags, *SANITIZE, *map(str, objects), "-o", str(binary)], check=True, capture_output=True,
                   text=True)
    return binary


def builds_32bit(cxx: str) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "probe.cpp"
        source.write_text("#include <iostream>\nint main() { std::cout << sizeof(void*); return sizeof(size_t) != 4; }\n")
        built = subprocess.run([cxx, "-m32", *SANITIZE, str(source), "-o", str(Path(tmp) / "probe")], capture_output=True)
        return built.returncode == 0 and subprocess.run([str(Path(tmp) / "probe")], capture_output=True).returncode == 0


class CoreTests(unittest.TestCase):
    FLAGS = ()
    COMPILERS = ("clang++", "c++", "g++")

    @classmethod
    def setUpClass(cls):
        if os.name != "posix":
            raise unittest.SkipTest("POSIX only")
        cls.cxx = compiler(cls.COMPILERS)
        if not cls.cxx:
            raise unittest.SkipTest("no C++ compiler")
        if not (STACK / "Crypto" / ".wici-stamp").is_file():
            if not REQUIRED:
                raise unittest.SkipTest("stack sources not fetched (python3 firmware/tools/stack_deps.py)")
            stack_deps.fetch(FIRMWARE)
        cls.tmp = tempfile.TemporaryDirectory()
        try:
            cls.binary = build(Path(cls.tmp.name), cls.cxx, cls.FLAGS)
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

    def test_announce_validate(self):
        # Ogłoszenia z Destination.announce i spreparowane: przyjęte te same co Identity.validate_announce,
        # z tymi samymi polami.
        cases = VECTORS["announce"]
        got = dict(zip((c["name"] for c in cases), self.ask([("validate_announce", bytes.fromhex(c["raw"])) for c in cases])))
        expected = {}
        for c in cases:
            if not c["valid"]:
                expected[c["name"]] = "none"
                continue
            raw = bytes.fromhex(c["raw"])
            data = raw[35:] if raw[0] & 0x40 else raw[19:]   # HEADER_2: identyfikator transportu przed celem
            r = 32 if raw[0] & 0x20 else 0   # flaga kontekstu: klucz ratchetu po skrócie losowym
            app = data[148 + r:]
            expected[c["name"]] = " ".join([data[:64].hex(), data[64:74].hex(), data[74:84].hex(),
                                            data[84:116].hex() if r else "-", app.hex() if app else "-"])
            if "random_hash" in c:
                self.assertEqual((c["random_hash"], c["ratchet"], c["app_data"]),
                                 (data[74:84].hex(), data[84:116].hex() if r else None, app.hex()))
        self.assertEqual(got, expected)

    def test_announce_build(self):
        # Z tym samym kluczem, skrótem losowym, ratchetem i danymi aplikacji pakiet bajt w bajt jak w Pythonie.
        # Odstępstwo: 481 B danych rdzeń odmawia (przez węzeł transportowy przechodzi najwyżej 465 B).
        built = [c for c in VECTORS["announce"] if "private_key" in c]
        self.assertEqual(len(built), 6)
        got = self.ask([("build_announce", bytes.fromhex(c["private_key"] + c["random_hash"]) +
                         (b"\x01" + bytes.fromhex(c["ratchet"]) if c["ratchet"] else b"\x00") + bytes.fromhex(c["app_data"]))
                        for c in built])
        self.assertEqual(got, ["none" if c["name"] == "data_481" else c["raw"] for c in built])

    def test_announce_random_hash_time(self):
        # Czas w skrócie losowym: int(time.time()) jako 5 B big-endian (wektory: 1 790 000 000 s).
        c = VECTORS["announce"][0]
        random = bytes.fromhex(c["random_hash"])
        got = self.ask([("random_hash", random[:5] + (1_790_000_000).to_bytes(8, "big"))])
        self.assertEqual(got, [c["random_hash"]])

    def test_announce_every_length(self):
        # Każda długość obciętego ogłoszenia z ratchetem: odrzucone bez błędu pamięci, poza pełnym.
        raw = bytes.fromhex(next(c for c in VECTORS["announce"] if c["name"] == "ratchet")["raw"])
        got = self.ask([("validate_announce", raw[:n]) for n in range(len(raw) + 1)])
        self.assertEqual([g == "none" for g in got], [n < len(raw) for n in range(len(raw) + 1)])

    def test_ratchet_token(self):
        # Identity.encrypt(ratchet=...): z tym samym kluczem efemerycznym i IV bajt w bajt jak w Pythonie.
        # Python odszyfrowuje go tylko z ratchetem, więc odszyfrowanie samym kluczem tożsamości odpada.
        tokens = [t for t in VECTORS["ratchet_token"] if "token" in t]
        got = self.ask([("encrypt_ratchet", bytes.fromhex(t["identity_public_key"] + t["ratchet"] + t["ephemeral_private_key"] +
                                                          t["iv"] + t["plaintext"])) for t in tokens])
        self.assertEqual(got, [t["token"] for t in tokens])
        for t in tokens:
            self.assertEqual((t["decrypted_with_ratchet"], t["decrypted_without_ratchet"]), (t["plaintext"], None))
        prv = bytes.fromhex(VECTORS["identity"][0]["private_key"])
        self.assertEqual(self.ask([("decrypt", prv + bytes.fromhex(t["token"])) for t in tokens]), ["none"] * len(tokens))

    def test_encrypt_to_unusual_ratchet(self):
        # Ratchet niskiego rzędu (Python: błąd w exchange) i w kodowaniu niekanonicznym (Python redukuje).
        entry = VECTORS["ratchet_token"][-1]
        cases = entry["unusual_ratchets"]
        got = self.ask([("encrypt_ratchet", bytes.fromhex(entry["identity_public_key"] + c["ratchet"] + c["ephemeral_private_key"] +
                                                          c["iv"]) + b"WICI") for c in cases])
        self.assertEqual(got, [c["token"] or "none" for c in cases])
        self.assertEqual([c["token"] is None for c in cases], [True, True, True, False])

    def test_proof(self):
        # Identity.prove (niejawny i jawny) bajt w bajt; PacketReceipt.validate_proof: te same wyniki.
        v = VECTORS["proof"]
        prv, packet_hash = bytes.fromhex(v["identity_private_key"]), bytes.fromhex(v["packet_hash"])
        pub = bytes.fromhex(self.ask([("public_key", prv)])[0])
        cases = {c["name"]: c for c in v["cases"]}
        got = self.ask([("prove", prv + packet_hash + b"\x01"), ("prove", prv + packet_hash + b"\x00")])
        self.assertEqual(got, [cases["implicit"]["proof"], cases["explicit"]["proof"]])
        got = self.ask([("validate_proof", pub + packet_hash + bytes.fromhex(c["proof"])) for c in v["cases"]])
        self.assertEqual(dict(zip(cases, got)), {n: "1" if c["valid"] else "0" for n, c in cases.items()})

    def test_proof_packet(self):
        # Pakiet PROOF z Identity.prove: cel = ucięty skrót pakietu, SINGLE, kontekst NONE, bez szyfrowania.
        v = VECTORS["proof"]
        cases = {c["name"]: c for c in v["cases"]}
        dest = bytes.fromhex(v["packet_hash"])[:16]
        got = self.ask([("pack", bytes([0, 0, 0, 0, 3, 0]) + bytes(16) + dest + b"\x00" + bytes.fromhex(cases[n]["proof"]))
                        for n in ("implicit", "explicit")])
        self.assertEqual(got, [v["implicit_packet"], v["explicit_packet"]])

    def test_destination_hash(self):
        # Destination.hash celu SINGLE "wici.sa1" każdej tożsamości z wektorów.
        identities = VECTORS["identity"]
        got = self.ask([("destination_hash", bytes.fromhex(i["hash"]) + b"wici.sa1") for i in identities])
        self.assertEqual(got, [i["destination_wici_sa1"] for i in identities])

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

    def test_ed25519_edge_cases(self):
        # Klucze i R niskiego rzędu, kodowania niekanoniczne, składowa skrętna: ta sama decyzja co
        # Identity.validate w Pythonie (wejścia spreparowane w tools/rns_vectors.py).
        cases = VECTORS["ed25519_edge"]
        got = self.ask([("validate", self.validate_args(bytes.fromhex(c["public_key"]), bytes.fromhex(c["signature"]),
                                                        bytes.fromhex(c["message"]))) for c in cases])
        expected = {c["name"]: "1" if c["valid"] else "0" for c in cases}
        # Odstępstwo z tabeli różnic (reticulum-core.md): klucz neutralny z bitem znaku rdzeń odrzuca.
        self.assertEqual(expected["non_canonical_key_sign_bit"], "1")
        expected["non_canonical_key_sign_bit"] = "0"
        self.assertEqual(dict(zip((c["name"] for c in cases), got)), expected)

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
        # Bufor wyjścia o 1 B za mały: odmowa przed kryptografią (ASan sprawdza, że nic nie wyszło poza bufor).
        got = self.ask([("encrypt_short", pub + bytes.fromhex(t["ephemeral_private_key"] + t["iv"] + t["plaintext"]))
                        for pub, t in zip(public_keys, tokens)])
        self.assertEqual(got, ["none"] * len(tokens))

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

    def test_packet_pack_mtu_boundary(self):
        # Granica MTU przy buforze wyjściowym większym od MTU (harness: 2 × MTU): MTU−1 i MTU przyjęte, MTU+1 odrzucone,
        # osobno dla HEADER_1 (19 B nagłówka) i HEADER_2 (35 B).
        commands = []
        for header_type, header in ((0, 19), (1, 35)):
            for total in (499, 500, 501):
                commands.append(("pack", bytes([header_type, 0, 0, 0, 0, 0]) + bytes(32) + bytes(1)
                                 + bytes([0xAB]) * (total - header)))
        got = self.ask(commands)
        self.assertEqual([None if line == "none" else len(line) // 2 for line in got], [499, 500, None] * 2)

    def test_packet_every_length(self):
        # Każda długość obciętego pakietu HEADER_2: do 35 B (nagłówek bez danych) odrzucony, dalej przyjęty;
        # ASan pilnuje odczytu poza buforem.
        raw = bytes.fromhex(VECTORS["packet"][0]["header_2"]["raw"])
        got = self.ask([("unpack", raw[:n]) for n in range(len(raw) + 1)])
        self.assertEqual([line == "none" for line in got], [n <= 35 for n in range(len(raw) + 1)])

    def test_huge_lengths(self):
        # Długość danych bliska SIZE_MAX (błąd wywołującego): pack i buildAnnounce odmawiają, suma długości
        # się nie zawija (przy 32-bitowym size_t na płytkach też, Core32Tests).
        prv = bytes.fromhex(VECTORS["identity"][0]["private_key"])
        self.assertEqual(self.ask([("huge_lengths", prv)]), ["0 0"])

    @staticmethod
    def pack_args(h: dict) -> bytes:
        return bytes([h["header_type"], h["context_flag"], h["transport_type"], h["destination_type"], h["packet_type"],
                      h["hops"]]) + bytes.fromhex(h["transport_id"] or "00" * 16) + bytes.fromhex(h["destination_hash"]) + \
            bytes([h["context"]]) + bytes.fromhex(h["data"])

    def test_hkdf(self):
        # RNS.Cryptography.hkdf bez kontekstu: długości wokół bloku, sól pusta (32 B zer), krótka i 64 B.
        cases = VECTORS["hkdf"]
        got = self.ask([("hkdf", c["length"].to_bytes(2, "big") + bytes([len(c["salt"]) // 2]) + bytes.fromhex(c["salt"] + c["ikm"]))
                        for c in cases])
        self.assertEqual(got, [c["okm"] for c in cases])

    def test_hkdf_refuses_like_python(self):
        # Python zgłasza błąd dla długości 0 i pustego materiału.
        got = self.ask([("hkdf", bytes([0, 0, 0, 1])), ("hkdf", bytes([0, 32, 0]))])
        self.assertEqual(got, ["none", "none"])

    def test_ifac(self):
        # Klucz IFAC z frazy sieci, kod i maska bajt w bajt jak Transport.handle_outgoing_ifac, sprawdzenie
        # jak Transport.handle_ifac (przyjęty tylko datagram poprawny, z pakietem bez flagi IFAC).
        v = VECTORS["ifac"]
        phrase = bytes([len(v["passphrase"])]) + v["passphrase"].encode()
        self.assertEqual(self.ask([("ifac_key", phrase)]), [v["ifac_key"]])
        got = self.ask([("ifac_apply", phrase + bytes.fromhex(c["raw"])) for c in v["applied"]])
        self.assertEqual(got, [c["wire"] for c in v["applied"]])
        got = self.ask([("ifac_check", phrase + bytes.fromhex(c["wire"])) for c in v["applied"]])
        self.assertEqual(got, [c["raw"] for c in v["applied"]])
        got = self.ask([("ifac_check", phrase + bytes.fromhex(c["wire"])) for c in v["checked"]])
        self.assertEqual(dict(zip((c["name"] for c in v["checked"]), got)),
                         {c["name"]: c["raw"] or "none" for c in v["checked"]})

    def test_ifac_every_length(self):
        # Każda długość obciętego datagramu: odrzucony bez błędu pamięci, poza pełnym; bez flagi 0x80 odrzucony.
        v = VECTORS["ifac"]
        phrase = bytes([len(v["passphrase"])]) + v["passphrase"].encode()
        wire = bytes.fromhex(v["applied"][0]["wire"])
        got = self.ask([("ifac_check", phrase + wire[:n]) for n in range(len(wire) + 1)] +
                       [("ifac_check", phrase + bytes([wire[0] & 0x7F]) + wire[1:])])
        self.assertEqual(got, ["none"] * len(wire) + [v["applied"][0]["raw"], "none"])

    # Transport bez przekazywania (transport.h): jedna stacja z kluczem z wektorów, pakiety z wektorów
    # i z poleceń sprawdzonych wyżej. Wiersz t_*: wynik, 9 liczników (duplikaty, pominięte, odrzucone,
    # ogłoszenia, odebrane, bez dowodu, wysłane, doręczone, po limicie), wywołania, pakiet do nadania.
    STATION = bytes.fromhex(VECTORS["identity"][0]["private_key"])
    EPHEMERAL = bytes(range(1, 33))
    IV = bytes(range(100, 116))

    @staticmethod
    def parsed(line: str):
        parts = line.split()
        return parts[0], list(map(int, parts[1:10])), parts[10:-1], parts[-1]

    def packet(self, flags: int, destination: bytes, data: bytes, context: int = 0, transport_id: bytes = bytes(16),
               hops: int = 0) -> bytes:
        header = bytes([(flags >> 6) & 1, (flags >> 5) & 1, (flags >> 4) & 1, (flags >> 2) & 3, flags & 3, hops])
        return bytes.fromhex(self.ask([("pack", header + transport_id + destination + bytes([context]) + data)])[0])

    def proof_packet(self, private_key: bytes, raw: bytes, implicit: bool = True) -> bytes:
        packet_hash = bytes.fromhex(self.ask([("unpack", raw)])[0].split()[-1])
        proof = bytes.fromhex(self.ask([("prove", private_key + packet_hash + bytes([1 if implicit else 0]))])[0])
        return self.packet(0x03, packet_hash[:16], proof)

    def announce_of(self, private_key: bytes, app_data: bytes = b"", ratchet: bytes = None, random_hash: bytes = None) -> bytes:
        random_hash = random_hash or bytes(5) + (1_790_000_000).to_bytes(5, "big")
        flag = b"\x01" + ratchet if ratchet else b"\x00"
        return bytes.fromhex(self.ask([("build_announce", private_key + random_hash + flag + app_data)])[0])

    def test_transport_announce_ratchet_send_and_proof(self):
        # Ogłoszenie z ratchetem: wpis z trasą 1 skok; to samo ogłoszenie drugi raz to kopia już sprawdzonego
        # (bez weryfikacji, licznik duplikatów) i nie zmienia trasy.
        # Pakiet do celu zaszyfrowany do ratchetu (jak encrypt_ratchet), dowód niejawny celu doręcza go raz.
        a = next(c for c in VECTORS["announce"] if c["name"] == "ratchet")
        raw = bytes.fromhex(a["raw"])
        dest = raw[2:18]
        key = bytes.fromhex(a["private_key"])
        pub = bytes.fromhex(self.ask([("public_key", key)])[0])
        payload = b"WICI to a ratchet"
        token = self.ask([("encrypt_ratchet", pub + bytes.fromhex(a["ratchet"]) + self.EPHEMERAL + self.IV + payload)])[0]
        lines = self.ask([("t_begin", self.STATION), ("t_in", raw), ("t_known", dest), ("t_in", raw),
                          ("t_send", dest + self.EPHEMERAL + self.IV + (7).to_bytes(4, "big") + (60000).to_bytes(4, "big") + payload)])
        self.assertEqual(self.parsed(lines[1]), ("ok", [0, 0, 0, 1, 0, 0, 0, 0, 0], [f"announce:{dest.hex()}:{a['app_data']}"], "-"))
        self.assertEqual(lines[2], f"1 1 1 {dest.hex()} {a['ratchet']} {pub.hex()} {raw[19:].hex()}")
        self.assertEqual(self.parsed(lines[3]), ("ok", [1, 0, 0, 1, 0, 0, 0, 0, 0], [], "-"))
        result, counters, _, sent = self.parsed(lines[4])
        self.assertEqual((result, counters[6]), ("sent", 1))
        self.assertEqual(sent, (bytes([0x00, 0x00]) + dest + b"\x00").hex() + token)
        proof = self.proof_packet(key, bytes.fromhex(sent))
        lines = self.ask([("t_begin", self.STATION), ("t_in", raw),
                          ("t_send", dest + self.EPHEMERAL + self.IV + (7).to_bytes(4, "big") + (60000).to_bytes(4, "big") + payload),
                          ("t_in", proof), ("t_in", proof)])
        self.assertEqual(self.parsed(lines[3])[1:3], ([0, 0, 0, 1, 0, 0, 1, 1, 0], ["receipt:7:1"]))
        self.assertEqual(self.parsed(lines[4])[1], [1, 0, 0, 1, 0, 0, 1, 1, 0])   # ten sam dowód: duplikat
        # Dowód pakietu stacji nie bierze żetonu limitu pracy (mayReceive): przy pustym wiadrze nadal doręcza.
        lines = self.ask([("t_begin", self.STATION), ("t_in", raw), ("t_refuse", b"\x01"),
                          ("t_send", dest + self.EPHEMERAL + self.IV + (7).to_bytes(4, "big") + (60000).to_bytes(4, "big") + payload),
                          ("t_in", proof), ("t_limited", b"")])
        self.assertEqual(self.parsed(lines[4])[1:3], ([0, 0, 0, 1, 0, 0, 1, 1, 0], ["receipt:7:1"]))
        self.assertEqual(lines[5], "0")

    def test_transport_receipt_timeout_and_wrong_proofs(self):
        # Dowód jawny innego pakietu, dowód innej tożsamości i poprawny dowód niejawny z celem innym niż
        # skrót pakietu (bez weryfikacji, tabela różnic) nie doręczają; po limicie wynik "nie".
        a = next(c for c in VECTORS["announce"] if c["name"] == "plain")
        raw, key = bytes.fromhex(a["raw"]), bytes.fromhex(a["private_key"])
        dest = raw[2:18]
        send = ("t_send", dest + self.EPHEMERAL + self.IV + (9).to_bytes(4, "big") + (5000).to_bytes(4, "big") + b"x")
        lines = self.ask([("t_begin", self.STATION), ("t_in", raw), send])
        sent = bytes.fromhex(self.parsed(lines[2])[3])
        other = self.packet(0x00, dest, b"another packet")
        wrong_hash = self.proof_packet(key, other, implicit=False)
        wrong_key = self.proof_packet(self.STATION, sent)
        wrong_destination = self.packet(0x03, bytes(16), self.proof_packet(key, sent)[19:])
        lines = self.ask([("t_begin", self.STATION), ("t_in", raw), send, ("t_in", wrong_hash), ("t_in", wrong_key),
                          ("t_in", wrong_destination), ("t_clock", (5999).to_bytes(8, "big")),
                          ("t_clock", (6000).to_bytes(8, "big"))])
        self.assertEqual([self.parsed(line)[1][2] for line in lines[3:6]], [1, 2, 3])
        self.assertEqual(self.parsed(lines[6])[2], [])
        self.assertEqual(self.parsed(lines[7])[1:3], ([0, 0, 3, 1, 0, 0, 1, 0, 1], ["receipt:9:0"]))

    def test_transport_receipts_bounded(self):
        # 8 czekających potwierdzeń; dziewiąty pakiet odmówiony bez wysłania.
        a = next(c for c in VECTORS["announce"] if c["name"] == "plain")
        raw = bytes.fromhex(a["raw"])
        dest = raw[2:18]
        sends = [("t_send", dest + self.EPHEMERAL + self.IV + (h).to_bytes(4, "big") + (60000).to_bytes(4, "big") + b"x")
                 for h in range(1, 10)]
        lines = self.ask([("t_begin", self.STATION), ("t_in", raw)] + sends)
        self.assertEqual([self.parsed(line)[0] for line in lines[2:]], ["sent"] * 8 + ["receipts_full"])
        self.assertEqual(self.parsed(lines[-1])[3], "-")

    def test_transport_packet_to_station(self):
        # Pakiet do stacji: odszyfrowany, dowód niejawny jak Identity.prove; duplikat odrzucony przed
        # deszyfrowaniem; odmowa warstwy aplikacji bez dowodu; zły HMAC odrzucony.
        address = self.ask([("t_begin", self.STATION)])[0]
        station_pub = bytes.fromhex(self.ask([("public_key", self.STATION)])[0])
        token = bytes.fromhex(self.ask([("encrypt", station_pub + self.EPHEMERAL + self.IV + b"report")])[0])
        raw = self.packet(0x00, bytes.fromhex(address), token)
        expected_proof = self.proof_packet(self.STATION, raw)
        token2 = bytes.fromhex(self.ask([("encrypt", station_pub + self.EPHEMERAL + bytes(16) + b"refused")])[0])
        raw2 = self.packet(0x00, bytes.fromhex(address), token2)
        bad = self.packet(0x00, bytes.fromhex(address), token[:-1] + bytes([token[-1] ^ 1]))
        lines = self.ask([("t_begin", self.STATION), ("t_in", raw), ("t_in", raw), ("t_config", bytes([255, 0])),
                          ("t_in", raw2), ("t_in", bad)])
        self.assertEqual(self.parsed(lines[1]), ("ok", [0, 0, 0, 0, 1, 0, 0, 0, 0], [f"packet:{b'report'.hex()}"],
                                                 expected_proof.hex()))
        self.assertEqual(self.parsed(lines[2])[1], [1, 0, 0, 0, 1, 0, 0, 0, 0])
        self.assertEqual(self.parsed(lines[4]), ("ok", [1, 0, 0, 0, 2, 1, 0, 0, 0], [f"packet:{b'refused'.hex()}"], "-"))
        self.assertEqual(self.parsed(lines[5])[1], [1, 0, 1, 0, 2, 1, 0, 0, 0])

    def test_transport_packet_to_station_without_token(self):
        # Hak mayReceive (limit pracy stacji) odmawia: pakiet odpada przed odszyfrowaniem, bez dowodu, bez
        # warstwy aplikacji i bez zapisu skrótu, więc ta sama kopia nie jest duplikatem i po zwolnieniu
        # żetonu przechodzi z dowodem; dopiero wtedy kolejna kopia to duplikat. Pakiet do innego celu nie
        # pyta o żeton (pominięty wcześniej).
        address = self.ask([("t_begin", self.STATION)])[0]
        station_pub = bytes.fromhex(self.ask([("public_key", self.STATION)])[0])
        token = bytes.fromhex(self.ask([("encrypt", station_pub + self.EPHEMERAL + self.IV + b"report")])[0])
        raw = self.packet(0x00, bytes.fromhex(address), token)
        lines = self.ask([("t_begin", self.STATION), ("t_refuse", b"\x01"), ("t_in", raw), ("t_in", raw),
                          ("t_in", self.packet(0x00, bytes(16), token)), ("t_limited", b""),
                          ("t_refuse", b"\x00"), ("t_in", raw), ("t_in", raw), ("t_limited", b"")])
        self.assertEqual(self.parsed(lines[2]), ("ok", [0, 0, 0, 0, 0, 0, 0, 0, 0], [], "-"))
        self.assertEqual(self.parsed(lines[3]), ("ok", [0, 0, 0, 0, 0, 0, 0, 0, 0], [], "-"))
        self.assertEqual(self.parsed(lines[4])[1], [0, 1, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(lines[5], "2")
        self.assertEqual(self.parsed(lines[7]), ("ok", [0, 1, 0, 0, 1, 0, 0, 0, 0], [f"packet:{b'report'.hex()}"],
                                                 self.proof_packet(self.STATION, raw).hex()))
        self.assertEqual(self.parsed(lines[8])[1], [1, 1, 0, 0, 1, 0, 0, 0, 0])
        self.assertEqual(lines[9], "2")

    def test_transport_outside_subset(self):
        # Pakiety poza podzbiorem R1 albo nie do stacji: pominięte bez listy skrótów; za krótki: unpack.
        address = bytes.fromhex(self.ask([("t_begin", self.STATION)])[0])
        cases = [self.packet(0x50, address, b"x" * 64, transport_id=bytes(range(16))),   # HEADER_2 dla innego węzła
                 self.packet(0x08, bytes(16), bytes(32)),       # PLAIN (zapytanie o trasę: R2)
                 self.packet(0x04, address, b"x"),              # GROUP
                 self.packet(0x02, address, bytes(64)),         # LINKREQUEST
                 self.packet(0x00, bytes(16), bytes(64)),       # DATA do cudzego celu
                 self.packet(0x03, bytes(16), bytes(63))]       # dowód o złej długości: odrzucony
        lines = self.ask([("t_begin", self.STATION)] + [("t_in", raw) for raw in cases] + [("t_in", b"\x00")])
        self.assertEqual([self.parsed(line)[1][1:3] for line in lines[1:-1]], [[1, 0], [2, 0], [3, 0], [4, 0], [5, 0], [5, 1]])
        self.assertEqual(self.parsed(lines[-1])[0], "malformed")

    @staticmethod
    def blob(n: int, emitted: int) -> bytes:
        # Skrót losowy ogłoszenia: 5 B losowych i 5 B czasu emisji (RNS/Destination.py: announce).
        return bytes([n]) * 5 + emitted.to_bytes(5, "big")

    @staticmethod
    def hops(raw: bytes, hops: int) -> bytes:
        return raw[:1] + bytes([hops]) + raw[2:]

    def known(self, commands, dest):
        lines = self.ask(commands + [("t_known", dest)])
        return lines[:-1], lines[-1].split()

    def test_transport_should_add(self):
        # RNS/Transport.py: should_add. Skoki po odbiorze są o 1 większe niż w pakiecie.
        a = next(c for c in VECTORS["announce"] if c["name"] == "plain")
        key = bytes.fromhex(a["private_key"])
        dest = bytes.fromhex(a["raw"])[2:18]
        first = ("t_in", self.hops(self.announce_of(key, random_hash=self.blob(1, 1000)), 1))
        cases = {
            "higher hops, same emission": (self.blob(2, 1000), 3, "2"),
            "higher hops, newer emission": (self.blob(2, 1001), 3, "4"),
            "equal hops, older emission": (self.blob(2, 999), 1, "2"),
            "equal hops, same blob": (self.blob(1, 1000), 1, "2"),
            "fewer hops, newer emission": (self.blob(2, 1001), 0, "1"),
        }
        for name, (blob, hops, expected) in cases.items():
            with self.subTest(name):
                _, entry = self.known([("t_begin", self.STATION), first,
                                       ("t_in", self.hops(self.announce_of(key, random_hash=blob), hops))], dest)
                self.assertEqual(entry[:3], [expected, "0", "1"])
        # Trasa po PATHFINDER_E (ta sama chwila co DESTINATION_TIMEOUT, ale bez wygaśnięcia, bo to nie
        # „dłużej niż”): wyższe skoki ze starszą emisją, ale nowym skrótem losowym przyjęte.
        week = 7 * 24 * 3600 * 1000
        _, entry = self.known([("t_begin", self.STATION), first, ("t_clock", (1000 + week).to_bytes(8, "big")),
                               ("t_in", self.hops(self.announce_of(key, random_hash=self.blob(3, 500)), 5))], dest)
        self.assertEqual(entry[:3], ["6", "0", "1"])

    def test_transport_path_expires_unused(self):
        # RNS/Transport.py: jobs: trasa nieużywana dłużej niż DESTINATION_TIMEOUT znika (tożsamość zostaje);
        # wysyłka HEADER_2 odświeża jej czas, HEADER_1 nie. Trasa 2 skoki: pakiet idzie do następnego skoku.
        a = next(c for c in VECTORS["announce"] if c["name"] == "plain")
        key = bytes.fromhex(a["private_key"])
        pub = bytes.fromhex(self.ask([("public_key", key)])[0])
        raw = self.hops(self.announce_of(key, random_hash=self.blob(1, 1000)), 1)
        dest = raw[2:18]
        relay = bytes(range(16))
        transported = bytes([raw[0] | 0x50, raw[1]]) + relay + raw[2:]   # HEADER_2 od węzła transportowego
        week = 7 * 24 * 3600 * 1000
        payload = b"alarm"
        token = self.ask([("encrypt", pub + self.EPHEMERAL + self.IV + payload)])[0]

        def send(handle):
            return ("t_send", dest + self.EPHEMERAL + self.IV + handle.to_bytes(4, "big") + (60000).to_bytes(4, "big") + payload)

        lines, entry = self.known([("t_begin", self.STATION), ("t_in", transported),
                                   ("t_clock", (1000 + week // 2).to_bytes(8, "big")), send(1),
                                   ("t_clock", (1000 + week + 1000).to_bytes(8, "big"))], dest)
        self.assertEqual(self.parsed(lines[3])[3], (bytes([0x50, 0x00]) + relay + dest + b"\x00").hex() + token)
        self.assertEqual(entry[:4], ["2", "0", "1", relay.hex()])   # wysyłka HEADER_2 odświeżyła trasę
        lines, entry = self.known([("t_begin", self.STATION), ("t_in", transported),
                                   ("t_clock", (1000 + week).to_bytes(8, "big")), ("t_known", dest),
                                   ("t_clock", (1000 + week + 1000).to_bytes(8, "big")), send(2)], dest)
        self.assertEqual(lines[3].split()[2], "1")
        self.assertEqual(entry[2], "0")   # po tygodniu bez użycia brak trasy, cel znany
        self.assertEqual(self.parsed(lines[5])[3], (bytes([0x00, 0x00]) + dest + b"\x00").hex() + token)
        local = self.hops(raw, 0)   # trasa 1 skok: HEADER_1 nie odświeża czasu trasy
        lines, entry = self.known([("t_begin", self.STATION), ("t_in", local),
                                   ("t_clock", (1000 + week).to_bytes(8, "big")), send(3),
                                   ("t_clock", (1000 + week + 1000).to_bytes(8, "big"))], dest)
        self.assertEqual(entry[2], "0")

    def test_transport_clock_back_after_restart(self):
        # Zegar cofnięty przy starcie (dziennik czasu pracy zawiódł, licznik od zera): trasa zapisana przed
        # restartem z czasem z przyszłości nie wygasa w pierwszym przeglądzie, a ratchet sprzed startu
        # o nieznanym wieku nie zostaje na zawsze (table.cpp: czas z przyszłości nie przedłuża wpisu).
        a = next(c for c in VECTORS["announce"] if c["name"] == "plain")
        key = bytes.fromhex(a["private_key"])
        dest = bytes.fromhex(a["raw"])[2:18]
        month = 30 * 24 * 3600 * 1000
        _, entry = self.known([("t_begin", self.STATION), ("t_clock", month.to_bytes(8, "big")),
                               ("t_in", self.hops(self.announce_of(key, ratchet=bytes([1]) * 32, random_hash=self.blob(1, 1000)), 1)),
                               ("t_restart", b"\x00\x01" + (1000).to_bytes(8, "big")),
                               ("t_clock", (2000).to_bytes(8, "big"))], dest)
        self.assertEqual(entry[:3], ["2", "0", "1"])   # trasa jest, ratchetu nie ma

    def test_transport_ratchet_kept(self):
        # Ogłoszenie bez ratchetu zostawia zapisany (known_ratchets); ratchet ze starszego ogłoszenia
        # (odtworzonego) nie zastępuje nowszego (tabela różnic); nowszy go zastępuje.
        a = next(c for c in VECTORS["announce"] if c["name"] == "plain")
        key = bytes.fromhex(a["private_key"])
        dest = bytes.fromhex(a["raw"])[2:18]
        r1, r2, r3 = bytes([1]) * 32, bytes([2]) * 32, bytes([3]) * 32
        steps = [(r1, 1000, r1), (None, 1001, r1), (r2, 999, r1), (r3, 1002, r3)]
        commands = [("t_begin", self.STATION)]
        for n, (ratchet, emitted, _) in enumerate(steps):
            commands += [("t_in", self.announce_of(key, ratchet=ratchet, random_hash=self.blob(n + 1, emitted))), ("t_known", dest)]
        lines = self.ask(commands)
        self.assertEqual([lines[2 + 2 * n].split()[4] for n in range(len(steps))], [r.hex() for *_, r in steps])
        # Czas emisji ratchetu z FRAM: po restarcie odtworzone starsze ogłoszenie też go nie cofa.
        lines = self.ask([("t_begin", self.STATION), ("t_in", self.announce_of(key, ratchet=r1, random_hash=self.blob(1, 1000))),
                          ("t_restart", b""), ("t_in", self.announce_of(key, ratchet=r2, random_hash=self.blob(2, 999))),
                          ("t_known", dest)])
        self.assertEqual(lines[-1].split()[4], r1.hex())

    def test_transport_announce_filters(self):
        # Kolizja klucza ze znanym celem odrzucona przed weryfikacją; odpowiedź na zapytanie o trasę
        # (kontekst PATH_RESPONSE) daje trasę bez wywołania warstwy aplikacji; echo własnego ogłoszenia
        # pominięte.
        a = next(c for c in VECTORS["announce"] if c["name"] == "plain")
        key = bytes.fromhex(a["private_key"])
        raw = self.announce_of(key, random_hash=self.blob(1, 1000))
        dest = raw[2:18]
        other = self.announce_of(bytes([7]) * 64, random_hash=self.blob(2, 1001))
        collision = other[:2] + dest + other[18:]
        response = raw[:18] + bytes([0x0B]) + raw[19:]
        lines = self.ask([("t_begin", self.STATION), ("t_in", raw), ("t_in", collision), ("t_known", dest)])
        self.assertEqual(self.parsed(lines[2])[1][2], 1)
        self.assertEqual(lines[3].split()[:3], ["1", "0", "1"])
        lines = self.ask([("t_begin", self.STATION), ("t_in", response), ("t_known", dest)])
        self.assertEqual(self.parsed(lines[1])[1:3], ([0, 0, 0, 1, 0, 0, 0, 0, 0], []))
        self.assertEqual(lines[2].split()[2], "1")
        lines = self.ask([("t_begin", self.STATION), ("t_announce", bytes(5))])
        own = bytes.fromhex(self.parsed(lines[1])[3])
        lines = self.ask([("t_begin", self.STATION), ("t_announce", bytes(5)), ("t_in", self.hops(own, 2)),
                          ("t_known", own[2:18])])
        self.assertEqual((self.parsed(lines[2])[1][1], lines[3]), (1, "none"))

    def test_transport_explicit_proof(self):
        # Dowód jawny (skrót pakietu i podpis) doręcza potwierdzenie raz.
        a = next(c for c in VECTORS["announce"] if c["name"] == "plain")
        raw, key = bytes.fromhex(a["raw"]), bytes.fromhex(a["private_key"])
        dest = raw[2:18]
        send = ("t_send", dest + self.EPHEMERAL + self.IV + (5).to_bytes(4, "big") + (60000).to_bytes(4, "big") + b"x")
        lines = self.ask([("t_begin", self.STATION), ("t_in", raw), send])
        proof = self.proof_packet(key, bytes.fromhex(self.parsed(lines[2])[3]), implicit=False)
        lines = self.ask([("t_begin", self.STATION), ("t_in", raw), send, ("t_in", proof)])
        self.assertEqual(self.parsed(lines[3])[1:3], ([0, 0, 0, 1, 0, 0, 1, 1, 0], ["receipt:5:1"]))

    def test_transport_eviction_keeps_pinned(self):
        # Pełna tablica (limit 2): wypierany najdawniej używany cel bez ochrony, cel chroniony zostaje.
        keys = [bytes([i + 1]) * 64 for i in range(4)]
        announces = [self.announce_of(k) for k in keys]
        dests = [a[2:18] for a in announces]
        lines = self.ask([("t_begin", self.STATION), ("t_config", bytes([2, 1]) + dests[0]),
                          ("t_in", announces[0]), ("t_in", announces[1]), ("t_clock", (5000).to_bytes(8, "big")),
                          ("t_in", announces[2]), ("t_clock", (9000).to_bytes(8, "big")), ("t_in", announces[3])] +
                         [("t_known", d) for d in dests])
        self.assertEqual([line == "none" for line in lines[-4:]], [False, True, True, False])

    @staticmethod
    def entries(lines):
        return [line.split()[:6] if line != "none" else None for line in lines]

    def test_transport_table_survives_restart(self):
        # Wpisy z FRAM po restarcie: klucz, ratchet, trasa i ogłoszenie w pamięci podręcznej (jak destination_table
        # i known_destinations w Pythonie); pakiet po restarcie ten sam co przed nim (szyfrowany do ratchetu).
        a = next(c for c in VECTORS["announce"] if c["name"] == "ratchet")
        raw = bytes.fromhex(a["raw"])
        dest = raw[2:18]
        card_key = bytes.fromhex(self.ask([("public_key", bytes([7]) * 64)])[0])
        card_dest = bytes.fromhex(self.ask([("destination_hash", bytes.fromhex(self.ask([("identity_hash", card_key)])[0])
                                             + b"wici.sa1")])[0])
        send = ("t_send", dest + self.EPHEMERAL + self.IV + (3).to_bytes(4, "big") + (60000).to_bytes(4, "big") + b"after")
        lines = self.ask([("t_begin", self.STATION), ("t_in", raw), ("t_known", dest), send, ("t_restart", b""),
                          ("t_known", dest), send, ("t_known", card_dest)])
        self.assertEqual(lines[4], "1 1")
        self.assertEqual(lines[5], lines[2])
        self.assertEqual(self.parsed(lines[6])[3], self.parsed(lines[3])[3])
        self.assertEqual(lines[7], "none")

    def test_transport_table_writes_only_on_change(self):
        # Powtórzone ogłoszenie (także z węzła transportowego, skoki większe) nie zapisuje gniazda; nowszy
        # czas emisji zapisuje jedno gniazdo (znacznik 0, treść, znacznik zatwierdzenia, unieważnienie starego).
        keys = [bytes([9]) * 64]
        first = self.announce_of(keys[0])
        newer = self.announce_of(keys[0], random_hash=bytes(5) + (1_790_000_100).to_bytes(5, "big"))
        lines = self.ask([("t_begin", self.STATION), ("t_writes", b""), ("t_in", first), ("t_writes", b""),
                          ("t_clock", (2000).to_bytes(8, "big")), ("t_in", first), ("t_writes", b""),
                          ("t_in", newer), ("t_writes", b"")])
        counts = [int(lines[i]) for i in (1, 3, 6, 8)]
        self.assertEqual([b - a for a, b in zip(counts, counts[1:])], [3, 0, 4])

    def test_transport_table_power_loss_in_every_write(self):
        # Zanik zasilania w każdym zapisie gniazda (zapisana połowa bajtów, dalsze zapisy przepadają), potem
        # restart: każdy wpis ma treść sprzed zmiany albo po niej, cel chroniony zostaje, tablica w limicie
        # i dalej przyjmuje zapisy.
        keys = [bytes([i + 11]) * 64 for i in range(4)]
        dests = [self.announce_of(k)[2:18] for k in keys]
        a1, b, c, d = (self.announce_of(k) for k in keys)
        a2 = self.announce_of(keys[0], random_hash=bytes(5) + (1_790_000_100).to_bytes(5, "big"))
        prefix = [("t_begin", self.STATION), ("t_config", bytes([3, 1]) + dests[0]), ("t_in", a1), ("t_in", b),
                  ("t_clock", (9000).to_bytes(8, "big"))]
        change = [("t_in", a2), ("t_in", c), ("t_in", d)]
        check = [("t_known", x) for x in dests]
        before = self.entries(self.ask(prefix + check)[-4:])
        whole = self.ask(prefix + [("t_writes", b"")] + change + [("t_writes", b""), ("t_restart", b"\x03")] + check)
        writes = int(whole[len(prefix) + 4]) - int(whole[len(prefix)])
        after = self.entries(whole[-4:])
        self.assertEqual([x is not None for x in after], [True, False, True, True])
        self.assertEqual(writes, 11)
        for cut in range(writes):
            with self.subTest(write=cut):
                lines = self.ask(prefix + [("t_cut", cut.to_bytes(4, "big"))] + change + [("t_restart", b"\x03")] + check +
                                 [("t_in", d), ("t_known", dests[3])])
                got = self.entries(lines[-6:-2])
                for i in range(4):
                    self.assertIn(got[i], (before[i], after[i]), f"destination {i}")
                self.assertIsNotNone(got[0])
                self.assertLessEqual(sum(x is not None for x in got), 3)
                self.assertIsNotNone(self.entries(lines[-1:])[0])

    def test_transport_table_damaged_slots(self):
        # Przekłamany bajt gniazda: wpis wypada przy odczycie (CRC), pozostałe zostają; obszar z obcą treścią
        # (system plików portu) to pusta tablica bez zapisów.
        keys = [bytes([i + 21]) * 64 for i in range(2)]
        announces = [self.announce_of(k) for k in keys]
        dests = [x[2:18] for x in announces]
        lines = self.ask([("t_begin", self.STATION), ("t_in", announces[0]), ("t_in", announces[1]),
                          ("t_poke", (200).to_bytes(4, "big") + b"\x5a"), ("t_restart", b""),
                          ("t_known", dests[0]), ("t_known", dests[1])])
        self.assertEqual(lines[4], "2 2")
        self.assertEqual(lines[5:7][0], "none")
        self.assertNotEqual(lines[6], "none")
        rng = __import__("random").Random(5)
        garbage = bytes(rng.randrange(256) for _ in range(64 * 1024))
        lines = self.ask([("t_begin", self.STATION), ("t_poke", bytes(4) + garbage), ("t_restart", b""), ("t_writes", b"")])
        self.assertEqual(lines[2:4], ["0 0", "0"])

    def test_transport_table_read_error_keeps_entry(self):
        # Błąd odczytu FRAM (nie CRC): wpis zostaje, wysyłka zawodzi tylko ten raz. Ogłoszenie przy błędzie
        # odczytu odpada bez drugiego wpisu tego samego celu, a jego powtórka przechodzi.
        key = bytes([33]) * 64
        first = self.announce_of(key)
        newer = self.announce_of(key, random_hash=bytes(5) + (1_790_000_100).to_bytes(5, "big"))
        dest = first[2:18]
        send = ("t_send", dest + self.EPHEMERAL + self.IV + (5).to_bytes(4, "big") + (60000).to_bytes(4, "big") + b"x")
        lines = self.ask([("t_begin", self.STATION), ("t_in", first), ("t_readfail", b"\x01"), send, send, ("t_known", dest),
                          ("t_readfail", b"\x02"), ("t_in", newer), ("t_known", dest), ("t_in", newer), ("t_known", dest),
                          ("t_restart", b""), ("t_readfail", b"\x00")])
        self.assertEqual((self.parsed(lines[3])[0], self.parsed(lines[4])[0]), ("unknown", "sent"))
        self.assertNotEqual(lines[5], "none")
        self.assertEqual(lines[8].split()[-1], first[19:].hex())
        self.assertEqual(lines[10].split()[-1], newer[19:].hex())
        self.assertEqual((lines[11], lines[12]), ("1 1", "0"))

    def test_transport_table_damaged_key_field(self):
        # Przekłamany bajt w polu klucza gniazda: ogłoszenie z właściwym kluczem nie jest kolizją (pełny odczyt
        # z CRC zwalnia uszkodzone gniazdo, licznik 1) i cel wraca do tablicy.
        key = bytes([34]) * 64
        first = self.announce_of(key)
        newer = self.announce_of(key, random_hash=bytes(5) + (1_790_000_100).to_bytes(5, "big"))
        dest = first[2:18]
        poke = ("t_poke", (96).to_bytes(4, "big") + bytes([first[19] ^ 0xFF]))
        lines = self.ask([("t_begin", self.STATION), ("t_in", first), poke, ("t_in", newer), ("t_known", dest),
                          ("t_readfail", b"\x00")])
        self.assertEqual(lines[4].split()[-1], newer[19:].hex())
        self.assertEqual(lines[5], "1")

    def test_transport_table_old_copy_does_not_return(self):
        # Zanik po zatwierdzeniu nowej kopii wpisu, przed unieważnieniem starej (gniazdo 1): po restarcie
        # zostaje nowsza (gniazdo 0), a starsza jest unieważniana, więc po wyparciu nowszej (nowy cel trafia
        # w zwolnione gniazdo 0) i kolejnym restarcie cel nie wraca.
        keys = [bytes([35]) * 64, bytes([36]) * 64, bytes([37]) * 64]
        later = bytes(5) + (1_790_000_100).to_bytes(5, "big")
        a1, d1, other = (self.announce_of(k) for k in keys)
        a2, d2 = self.announce_of(keys[0], random_hash=later), self.announce_of(keys[1], random_hash=later)
        dest = d1[2:18]
        lines = self.ask([("t_begin", self.STATION), ("t_in", a1), ("t_in", d1), ("t_in", a2), ("t_cut", (3).to_bytes(4, "big")),
                          ("t_in", d2), ("t_restart", b"\x02"), ("t_known", dest), ("t_clock", (5000).to_bytes(8, "big")),
                          ("t_in", a2), ("t_in", other), ("t_restart", b"\x02"), ("t_known", dest), ("t_known", other[2:18])])
        self.assertEqual(lines[6], "2 2")
        self.assertEqual(lines[7].split()[-1], d2[19:].hex())
        self.assertEqual(lines[11], "2 2")
        self.assertEqual(lines[12], "none")
        self.assertNotEqual(lines[13], "none")

    def dual_copy(self, newer_in_later_slot: bool, damage=()):
        """Polecenia dające dwie kopie celu po zaniku zasilania przed unieważnieniem starej, z uszkodzeniami (t_poke).

        Stara kopia w gnieździe 1; nowsza w gnieździe 0 (przed starą w indeksowaniu) albo 2 (po niej). Zwraca polecenia,
        skrót celu i ogłoszenia: starej oraz nowszej."""
        keys = [bytes([35]) * 64, bytes([36]) * 64]
        later = bytes(5) + (1_790_000_100).to_bytes(5, "big")
        a1, d1 = (self.announce_of(k) for k in keys)
        a2, d2 = (self.announce_of(k, random_hash=later) for k in keys)
        cut = ("t_cut", (3).to_bytes(4, "big"))
        commands = [("t_begin", self.STATION), ("t_in", a1), ("t_in", d1)]
        commands += [cut, ("t_in", d2)] if newer_in_later_slot else [("t_in", a2), cut, ("t_in", d2)]
        newer_slot = 2 if newer_in_later_slot else 0
        for slot, offset, value in damage:   # slot: "new" albo "old"; offset w gnieździe
            commands.append(("t_poke", ((newer_slot if slot == "new" else 1) * 568 + offset).to_bytes(4, "big") + value))
        return commands, d1[2:18], d1, d2

    def test_transport_table_two_copies_keep_last_valid(self):
        # Dwie kopie tego samego celu (zanik zasilania przed unieważnieniem starej): zostaje ostatnia w pełni poprawna.
        # Nowsza wygrywa tylko z całym ciałem pod CRC; uszkodzone ciało albo nagłówek nowszej nie kasują starej.
        damages = {
            "intact": ((), "new"),
            "new body": ((("new", 200, b"\x5a"),), "old"),
            "new header": ((("new", 8, b"\xff"),), "old"),    # znaczniki w nagłówku, CRC je obejmuje
            "new sequence": ((("new", 7, b"\x7f"),), "old"),   # numer zapisu większy, ciało nie pasuje do CRC
            "old body": ((("old", 200, b"\x5a"),), "new"),
            "both": ((("new", 200, b"\x5a"), ("old", 200, b"\x5a")), None),
        }
        for later_slot in (False, True):
            for name, (damage, winner) in damages.items():
                with self.subTest(newer_in_later_slot=later_slot, damage=name):
                    commands, dest, old, new = self.dual_copy(later_slot, damage)
                    expected = {"old": old, "new": new, None: None}[winner]
                    lines = self.ask(commands + [("t_restart", b"\x02"), ("t_known", dest), ("t_restart", b"\x02"),
                                                 ("t_known", dest)])
                    for line in (lines[-3], lines[-1]):
                        self.assertEqual(None if line == "none" else line.split()[-1],
                                         None if expected is None else expected[19:].hex())

    def test_transport_table_two_copies_single_read_error(self):
        # Jednorazowy błąd odczytu w dowolnym odczycie startu (nagłówek kopii, numer zapisu, pełny odczyt zwycięzcy)
        # niczego nie unieważnia: po następnym, czystym starcie zostaje ostatnia w pełni poprawna kopia.
        for later_slot in (False, True):
            for name, damage, winner in (("intact", (), "new"), ("new body", (("new", 200, b"\x5a"),), "old")):
                commands, dest, old, new = self.dual_copy(later_slot, damage)
                expected = {"old": old, "new": new}[winner][19:].hex()
                counted = self.ask(commands + [("t_reads", b""), ("t_restart", b"\x02"), ("t_reads", b"")])
                reads = int(counted[-1]) - int(counted[-3])
                # Odczyty nagłówków wszystkich gniazd (jeden na gniazdo), potem dodatkowe przy dwóch kopiach.
                slots = int(self.ask([("t_begin", self.STATION), ("t_reads", b""), ("t_restart", b""),
                                      ("t_reads", b"")])[-1]) - int(self.ask([("t_begin", self.STATION),
                                                                              ("t_reads", b"")])[-1])
                self.assertGreater(reads, slots)
                for nth in list(range(1, 5)) + list(range(slots + 1, reads + 1)):
                    with self.subTest(newer_in_later_slot=later_slot, damage=name, failing_read=nth):
                        lines = self.ask(commands + [("t_failat", nth.to_bytes(2, "big")), ("t_restart", b"\x02"),
                                                     ("t_known", dest), ("t_restart", b"\x02"), ("t_known", dest)])
                        self.assertEqual(lines[-1].split()[-1], expected)

    # Cel PLAIN "rnstransport.path.request" (Destination bez tożsamości: skrót skrótu nazwy).
    PATH_REQUEST = hashlib.sha256(hashlib.sha256(b"rnstransport.path.request").digest()[:10]).digest()[:16]

    def path_request(self, dest: bytes, tag: bytes, requestor: bytes = b"", hops: int = 0) -> bytes:
        return self.packet(0x08, self.PATH_REQUEST, dest + requestor + tag, hops=hops)

    def fields_of(self, raw_hex: str):
        return self.ask([("unpack", bytes.fromhex(raw_hex))])[0].split()

    def test_path_request_for_station(self):
        # Zapytanie o cel stacji: od razu ogłoszenie z kontekstem PATH_RESPONSE (Destination.announce
        # z path_response) z nowym podpisem i danymi aplikacji ostatniego ogłoszenia; ten sam znacznik drugi
        # raz: duplikat; inny znacznik w ciągu sekundy: bez odpowiedzi (limit), później nowa odpowiedź.
        address = bytes.fromhex(self.ask([("t_begin", self.STATION)])[0])
        lines = self.ask([("t_begin", self.STATION), ("t_announce", bytes(5) + b"WICI"),
                          ("t_in", self.path_request(address, b"A" * 16)), ("t_in", self.path_request(address, b"A" * 16)),
                          ("t_in", self.path_request(address, b"B" * 16, requestor=bytes(range(16)))),
                          ("t_clock", (31001).to_bytes(8, "big")), ("t_in", self.path_request(address, b"C" * 5)),
                          ("t_paths", b"")])
        own = self.fields_of(self.parsed(lines[1])[3])
        first, third = self.parsed(lines[2])[3], self.parsed(lines[6])[3]
        f = self.fields_of(first)
        self.assertEqual(f[:9], ["0", "0", "0", "0", "1", "0", "-", address.hex(), "11"])
        self.assertEqual(f[9][:148], own[9][:148])         # klucz i skrót nazwy jak w ogłoszeniu własnym
        self.assertTrue(f[9].endswith(b"WICI".hex()))      # dane aplikacji z announce()
        self.assertEqual(self.parsed(lines[3])[1][0], 1)   # duplikat znacznika
        self.assertEqual([self.parsed(lines[i])[3] for i in (3, 4)], ["-", "-"])
        t = self.fields_of(third)
        self.assertNotEqual(t[9], f[9])                    # nowy czas emisji i podpis
        self.assertTrue(t[9].endswith(b"WICI".hex()))
        self.assertNotEqual(self.ask([("validate_announce", bytes.fromhex(third))])[0], "none")
        self.assertEqual(lines[7], "3 3 2 1 0 0 0")

    def test_path_request_for_known_destination(self):
        # Trasa znana: odpowiedź po PATH_REQUEST_GRACE (0,4 s) jako HEADER_2 z identyfikatorem transportu stacji,
        # liczbą skoków trasy, kontekstem PATH_RESPONSE i ogłoszeniem z pamięci podręcznej; jedno nadanie
        # (PATHFINDER_R). Retransmisja samego ogłoszenia (wstrzymana na czas odpowiedzi, held_announces) wraca
        # po odpowiedzi: dwa nadania bez kontekstu, drugie po PATHFINDER_G + PATHFINDER_RW. Pytający, który jest
        # następnym skokiem, i cel bez trasy: bez odpowiedzi.
        a = next(c for c in VECTORS["announce"] if c["name"] == "ratchet")
        raw = bytes.fromhex(a["raw"])
        dest = raw[2:18]
        identity = self.ask([("identity_hash", bytes.fromhex(self.ask([("public_key", self.STATION)])[0]))])[0]
        lines = self.ask([("t_begin", self.STATION), ("t_in", raw), ("t_in", self.path_request(dest, b"T" * 16)),
                          ("t_clock", (1400).to_bytes(8, "big")), ("t_clock", (1401).to_bytes(8, "big")),
                          ("t_clock", (8000).to_bytes(8, "big")), ("t_clock", (20000).to_bytes(8, "big")),
                          ("t_in", self.path_request(dest, b"U" * 16, requestor=dest)), ("t_clock", (30000).to_bytes(8, "big")),
                          ("t_in", self.path_request(bytes(16), b"V" * 16)), ("t_paths", b"")])
        self.assertEqual([self.parsed(lines[i])[3] for i in (2, 3)], ["-", "-"])
        out = self.fields_of(self.parsed(lines[4])[3])
        self.assertEqual(out[:9], ["1", "1", "1", "0", "1", "1", identity, dest.hex(), "11"])
        self.assertEqual(out[9], raw[19:].hex())
        for i in (5, 6):
            rebroadcast = self.fields_of(self.parsed(lines[i])[3])
            self.assertEqual(rebroadcast[:8] + rebroadcast[9:-1], out[:8] + out[9:-1])   # bez skrótu pakietu (kontekst)
            self.assertEqual(rebroadcast[8], "0")
        self.assertEqual([self.parsed(lines[i])[3] for i in (7, 8, 9)], ["-"] * 3)
        self.assertEqual(lines[10], "3 2 1 0 0 0 0")

    def test_path_request_for_station_reuses_signature(self):
        # Odpowiedź w ciągu 30 s od ogłoszenia własnego: te same dane (bez nowego podpisu) z kontekstem
        # PATH_RESPONSE. Interfejs bez miejsca (mayTransmit): bez odpowiedzi i bez podpisu, licznik limitu.
        address = bytes.fromhex(self.ask([("t_begin", self.STATION)])[0])
        lines = self.ask([("t_begin", self.STATION), ("t_announce", bytes(5) + b"WICI"),
                          ("t_clock", (2000).to_bytes(8, "big")), ("t_in", self.path_request(address, b"A" * 16)),
                          ("t_busy", b"\x01"), ("t_clock", (4000).to_bytes(8, "big")),
                          ("t_in", self.path_request(address, b"B" * 16)), ("t_paths", b"")])
        own, reply = self.fields_of(self.parsed(lines[1])[3]), self.fields_of(self.parsed(lines[3])[3])
        self.assertEqual(reply[9], own[9])               # te same dane ogłoszenia i podpis
        self.assertEqual(reply[8], "11")                 # kontekst PATH_RESPONSE
        self.assertEqual(self.parsed(lines[6])[3], "-")
        self.assertEqual(lines[7], "2 2 1 1 0 0 0")

    def test_retransmissions_one_per_poll(self):
        # Dwie odpowiedzi z pamięci podręcznej zaległe naraz: poll() nadaje najwyżej jedną (najwcześniejszą),
        # a poll() obiegu z kryptografią odbioru (bez nadawania) żadnej; interfejs zajęty też wstrzymuje.
        # Ogłoszenia jako odpowiedzi na zapytanie (kontekst PATH_RESPONSE): bez własnej retransmisji.
        keys = [bytes([51]) * 64, bytes([52]) * 64]
        announces = [x[:18] + bytes([0x0B]) + x[19:] for x in (self.announce_of(k) for k in keys)]
        lines = self.ask([("t_begin", self.STATION), ("t_in", announces[0]), ("t_in", announces[1]),
                          ("t_in", self.path_request(announces[1][2:18], b"P" * 16)),
                          ("t_in", self.path_request(announces[0][2:18], b"Q" * 16)),
                          ("t_poll", (1500).to_bytes(8, "big")), ("t_busy", b"\x01"), ("t_clock", (1501).to_bytes(8, "big")),
                          ("t_busy", b"\x00"), ("t_clock", (1502).to_bytes(8, "big")), ("t_clock", (1503).to_bytes(8, "big")),
                          ("t_clock", (1504).to_bytes(8, "big"))])
        self.assertEqual([self.parsed(lines[i])[3] for i in (5, 7)], ["-", "-"])
        first, second = self.fields_of(self.parsed(lines[9])[3]), self.fields_of(self.parsed(lines[10])[3])
        self.assertEqual((first[7], second[7]), (announces[1][2:18].hex(), announces[0][2:18].hex()))
        self.assertEqual(self.parsed(lines[11])[3], "-")

    def test_held_announce_released_with_response(self):
        # Wstrzymana retransmisja żyje tylko z wpisem odpowiedzi swojego celu: cel wyparty z tablicy (limit 1)
        # przed nadaniem odpowiedzi, więc odpowiedź i wstrzymana retransmisja znikają, miejsce wraca.
        a, b = self.announce_of(bytes([53]) * 64), self.announce_of(bytes([54]) * 64)
        lines = self.ask([("t_begin", self.STATION), ("t_config", bytes([1, 1])), ("t_in", self.hops(a, 1)),
                          ("t_in", self.path_request(a[2:18], b"H" * 16)), ("t_held", b""),
                          ("t_clock", (1001).to_bytes(8, "big")), ("t_in", self.hops(b, 1))] +
                         [("t_clock", (1100 + 200 * i).to_bytes(8, "big")) for i in range(10)] + [("t_held", b"")])
        self.assertEqual((lines[4], lines[-1]), ("1", "0"))

    def test_path_request_gate_keeps_waiting_entries(self):
        # Pełna tablica zapytań „w drodze” (8): nowe zapytanie wypiera najstarszy żywy wpis bez oczekiwania,
        # nie wpis czekający na odkrycie (najstarszy), więc ogłoszenie celu nadal idzie jako odpowiedź.
        identity = self.station_identity()
        ann = self.announce_of(bytes([37]) * 64)
        dest = ann[2:18]
        lines = self.ask([("t_begin", self.STATION), ("t_in", self.path_request(dest, b"A" * 16)),
                          ("t_in", self.path_request(dest, b"B" * 16))] +
                         [("t_in", self.path_request(bytes([i]) * 16, bytes([i]) * 16)) for i in range(1, 9)] +
                         [("t_in", ann), ("t_clock", (1001).to_bytes(8, "big")), ("t_out", b"")])
        self.assertEqual(lines[-1], self.via(ann[:18] + bytes([0x0B]) + ann[19:], identity, 1).hex())

    def test_path_request_gate(self):
        # RNS/Transport.py: preprocess_inbound (inflight_path_requests): drugie zapytanie o cel bez trasy w ciągu
        # 45 s zostaje bez odpowiedzi i czeka (discovery_path_requests); ogłoszenie celu idzie wtedy od razu jako
        # odpowiedź HEADER_2 z identyfikatorem stacji. Po PATH_REQUEST_TIMEOUT (15 s bez przepływności interfejsu)
        # oczekiwanie wygasa: ogłoszenie bez odpowiedzi.
        identity = self.station_identity()
        ann = self.announce_of(bytes([36]) * 64)
        dest = ann[2:18]
        ask = [("t_begin", self.STATION), ("t_in", self.path_request(dest, b"A" * 16)), ("t_in", self.path_request(dest, b"B" * 16)),
               ("t_out", b"")]
        # Odpowiedź w następnym poll() (w obiegu ogłoszenia była weryfikacja podpisu), nie od razu.
        lines = self.ask(ask + [("t_in", ann), ("t_out", b""), ("t_clock", (1001).to_bytes(8, "big")), ("t_out", b"")])
        self.assertEqual((lines[3], lines[5]), ("-", "-"))
        self.assertEqual(lines[7], self.via(ann[:18] + bytes([0x0B]) + ann[19:], identity, 1).hex())
        lines = self.ask(ask + [("t_clock", (16001).to_bytes(8, "big")), ("t_in", ann), ("t_out", b"")])
        self.assertEqual(lines[-1], "-")
        # Po 45 s pierwsze zapytanie już nie jest „w drodze”: następne zapytanie jest nowym pierwszym.
        lines = self.ask([("t_begin", self.STATION), ("t_in", self.path_request(dest, b"A" * 16)),
                          ("t_clock", (46001).to_bytes(8, "big")), ("t_in", self.path_request(dest, b"B" * 16)),
                          ("t_in", ann), ("t_out", b"")])
        self.assertEqual(lines[-1], "-")

    def test_path_request_not_gated_by_other_packet(self):
        # Pakiet innego typu niż zapytanie (SINGLE DATA, GROUP DATA, PLAIN PROOF) do celu zapytań o trasę,
        # z celem stacji i znacznikiem, nie jest zapytaniem „w drodze”: następne zapytanie o cel stacji dostaje
        # od razu odpowiedź (tabela różnic, preprocess_inbound).
        address = bytes.fromhex(self.ask([("t_begin", self.STATION)])[0])
        for flags in (0x00, 0x04, 0x0B):
            other = self.packet(flags, self.PATH_REQUEST, address + b"S" * 16)
            lines = self.ask([("t_begin", self.STATION), ("t_announce", bytes(5) + b"WICI"), ("t_in", other),
                              ("t_in", self.path_request(address, b"A" * 16))])
            self.assertEqual(self.parsed(lines[2])[3], "-", flags)
            self.assertNotEqual(self.parsed(lines[3])[3], "-", flags)

    def test_path_request_filter(self):
        # Bez znacznika: odrzucone; PLAIN po więcej niż 1 skoku i ogłoszenie PLAIN: odpadają (packet_filter);
        # znacznik dłuższy niż 16 B liczy się po pierwszych 16 B.
        address = bytes.fromhex(self.ask([("t_begin", self.STATION)])[0])
        lines = self.ask([("t_begin", self.STATION), ("t_in", self.path_request(address, b"")),
                          ("t_in", self.path_request(address, b"X" * 16, hops=2)),
                          ("t_in", self.packet(0x09, self.PATH_REQUEST, bytes(200))),
                          ("t_in", self.path_request(address, b"Y" * 16 + b"1", requestor=bytes(16))),
                          ("t_in", self.path_request(address, b"Y" * 16 + b"2", requestor=bytes(16))), ("t_paths", b"")])
        self.assertEqual([self.parsed(line)[1][:3] for line in lines[1:6]],
                         [[0, 0, 1], [0, 1, 1], [0, 1, 2], [0, 1, 2], [1, 1, 2]])
        # Przed pierwszym ogłoszeniem odpowiedź ma puste dane aplikacji (Python: default_app_data None).
        self.assertEqual(lines[6], "1 1 1 0 0 0 0")

    def test_own_path_request(self):
        # RNS/Transport.py: request_path węzła z transportem: cel, identyfikator transportu, znacznik; PLAIN,
        # HEADER_1, rozgłaszany; drugi raz o ten sam cel przed upływem 20 s: bez nadania.
        self.ask([("t_begin", self.STATION)])
        identity = bytes.fromhex(self.ask([("identity_hash", bytes.fromhex(self.ask([("public_key", self.STATION)])[0]))])[0])
        dest, tag = bytes(range(16)), bytes(range(100, 116))
        lines = self.ask([("t_begin", self.STATION), ("t_request", dest + tag), ("t_request", dest + tag),
                          ("t_clock", (21001).to_bytes(8, "big")), ("t_request", dest + tag)])
        self.assertEqual(self.parsed(lines[1])[3], self.path_request(dest, tag, requestor=identity).hex())
        self.assertEqual(self.parsed(lines[2])[0], "none")
        self.assertEqual(self.parsed(lines[4])[0], "ok")

    def station_identity(self) -> bytes:
        return bytes.fromhex(self.ask([("identity_hash", bytes.fromhex(self.ask([("public_key", self.STATION)])[0]))])[0])

    @staticmethod
    def via(raw: bytes, transport_id: bytes, hops: int) -> bytes:
        # Ten sam pakiet w transporcie (HEADER_2, TRANSPORT) z identyfikatorem transportu i liczbą skoków.
        return bytes([raw[0] | 0x50, hops]) + transport_id + raw[2:]

    def test_forward_header2(self):
        # RNS/Transport.py: _inbound: pakiet z identyfikatorem stacji do celu z trasą 2 skoki idzie do następnego
        # skoku (nowy identyfikator transportu, skoki + 1); z trasą 1 skok jako HEADER_1 rozgłaszany (bez flagi
        # kontekstu); powtórzony: duplikat; cel bez trasy: porzucony. Dowód przekazanego pakietu wraca według
        # tablicy odwrotnej jeden raz.
        identity = self.station_identity()
        relay = bytes(range(16))
        far, near = (self.announce_of(bytes([k]) * 64) for k in (31, 32))
        far_dest, near_dest = far[2:18], near[2:18]
        data = self.packet(0x50, far_dest, b"x" * 40, transport_id=identity, hops=3)
        flagged = self.packet(0x70, near_dest, b"y" * 40, transport_id=identity, hops=0)
        unknown = self.packet(0x50, bytes(16), b"z" * 40, transport_id=identity)
        data_hash = bytes.fromhex(self.fields_of(data.hex())[-1])
        proof = self.packet(0x03, data_hash[:16], bytes(64), hops=2)
        lines = self.ask([("t_begin", self.STATION), ("t_in", self.via(far, relay, 1)), ("t_in", near), ("t_in", data),
                          ("t_in", data), ("t_in", flagged), ("t_in", unknown), ("t_forward", b""), ("t_in", proof),
                          ("t_in", self.hops(proof, 3)), ("t_forward", b"")])
        self.assertEqual(self.parsed(lines[3])[3], (bytes([data[0], 4]) + relay + data[18:]).hex())
        self.assertEqual(self.parsed(lines[4])[1][0], 1)
        self.assertEqual(self.parsed(lines[4])[3], "-")
        self.assertEqual(self.parsed(lines[5])[3], (bytes([0x00, 1]) + flagged[18:]).hex())
        self.assertEqual(self.parsed(lines[6])[3], "-")
        self.assertEqual(lines[7], "2 1 0 0 0 2 2")
        self.assertEqual(self.parsed(lines[8])[3], self.hops(proof, 3).hex())
        self.assertEqual(self.parsed(lines[9])[3], "-")   # ten sam dowód: duplikat
        self.assertEqual(lines[10], "2 1 1 0 0 1 2")

    def test_forward_reverse_timeout(self):
        # Wpis tablicy odwrotnej po REVERSE_TIMEOUT (8 min) nie przekazuje dowodu.
        identity = self.station_identity()
        far = self.announce_of(bytes([33]) * 64)
        data = self.packet(0x50, far[2:18], b"x" * 40, transport_id=identity)
        proof = self.packet(0x03, bytes.fromhex(self.fields_of(data.hex())[-1])[:16], bytes(64))
        lines = self.ask([("t_begin", self.STATION), ("t_in", self.via(far, bytes(range(16)), 1)), ("t_in", data),
                          ("t_clock", (1000 + 8 * 60 * 1000 + 1).to_bytes(8, "big")), ("t_in", proof), ("t_forward", b"")])
        self.assertEqual(self.parsed(lines[4])[3], "-")
        self.assertEqual(lines[5].split()[:3], ["1", "0", "0"])

    def test_forward_proof_other_destination_type(self):
        # Dowód z typem celu PLAIN albo GROUP (Python: packet_filter przepuszcza go do 1 skoku) odpada przed
        # tablicą odwrotną (tabela różnic), więc nie zużywa wpisu: prawdziwy dowód SINGLE nadal wraca.
        identity = self.station_identity()
        far = self.announce_of(bytes([36]) * 64)
        data = self.packet(0x50, far[2:18], b"x" * 40, transport_id=identity)
        proof = self.packet(0x03, bytes.fromhex(self.fields_of(data.hex())[-1])[:16], bytes(64))
        lines = self.ask([("t_begin", self.STATION), ("t_in", self.via(far, bytes(range(16)), 1)), ("t_in", data),
                          ("t_in", bytes([0x07]) + proof[1:]), ("t_in", bytes([0x0B]) + proof[1:]), ("t_in", proof),
                          ("t_forward", b"")])
        self.assertEqual([self.parsed(lines[i])[3] for i in (3, 4)], ["-", "-"])
        self.assertEqual(self.parsed(lines[5])[3], self.hops(proof, 1).hex())
        self.assertEqual(lines[6].split()[:3], ["1", "0", "1"])

    def test_announce_rebroadcast(self):
        # RNS/Transport.py: _inbound i jobs: przyjęte ogłoszenie idzie dalej jako HEADER_2 z identyfikatorem
        # stacji i skokami po odbiorze, po losowej zwłoce do PATHFINDER_RW (tu 176 ms), drugi raz po
        # PATHFINDER_G + PATHFINDER_RW, potem wpis znika. Odpowiedź na zapytanie o trasę nie idzie dalej.
        identity = self.station_identity()
        ann = self.announce_of(bytes([34]) * 64)
        lines = self.ask([("t_begin", self.STATION), ("t_in", ann), ("t_clock", (1176).to_bytes(8, "big")),
                          ("t_clock", (1177).to_bytes(8, "big")), ("t_clock", (6677).to_bytes(8, "big")),
                          ("t_clock", (6678).to_bytes(8, "big")), ("t_clock", (20000).to_bytes(8, "big")), ("t_forward", b"")])
        self.assertEqual([self.parsed(lines[i])[3] for i in (2, 4, 6)], ["-"] * 3)
        expected = self.via(ann, identity, 1).hex()
        self.assertEqual([self.parsed(lines[i])[3] for i in (3, 5)], [expected] * 2)
        self.assertEqual(lines[7], "0 0 0 0 2 0 0")
        response = ann[:18] + bytes([0x0B]) + ann[19:]
        lines = self.ask([("t_begin", self.STATION), ("t_in", response), ("t_clock", (2000).to_bytes(8, "big")), ("t_forward", b"")])
        self.assertEqual((self.parsed(lines[2])[3], lines[3]), ("-", "0 0 0 0 0 0 0"))

    def test_announce_rebroadcast_heard(self):
        # Po pierwszym nadaniu: dwie lokalne powtórki sąsiadów (te same skoki) albo przekazanie o skok dalej
        # przed czasem ponowienia usuwają wpis, więc drugiego nadania nie ma (LOCAL_REBROADCASTS_MAX).
        ann = self.announce_of(bytes([35]) * 64)
        first = [("t_begin", self.STATION), ("t_in", ann), ("t_clock", (1177).to_bytes(8, "big"))]
        cases = {"local rebroadcasts": [("t_in", self.via(ann, bytes([1]) * 16, 1)), ("t_in", self.via(ann, bytes([2]) * 16, 1))],
                 "passed on": [("t_in", self.via(ann, bytes([3]) * 16, 2))]}
        for name, heard in cases.items():
            with self.subTest(name):
                lines = self.ask(first + heard + [("t_clock", (7000).to_bytes(8, "big")), ("t_forward", b"")])
                self.assertNotEqual(self.parsed(lines[2])[3], "-")
                self.assertEqual(self.parsed(lines[-2])[3], "-")
                self.assertEqual(lines[-1], "0 0 0 0 1 0 0")
        # Jedna lokalna powtórka nie wystarcza: drugie nadanie zostaje.
        lines = self.ask(first + cases["local rebroadcasts"][:1] + [("t_clock", (7000).to_bytes(8, "big"))])
        self.assertNotEqual(self.parsed(lines[-1])[3], "-")

    # Dwa interfejsy (etap R4, węzeł stanowiska): 0 to P1, 1 to USB. t_begin z liczbą interfejsów, t_inif
    # z numerem interfejsu odbioru, t_outif: pakiety do nadania z numerem interfejsu.
    TWO = STATION + b"\x02"

    def test_interfaces_route_and_forward(self):
        # RNS/Transport.py: trasa pamięta interfejs ogłoszenia (IDX_PT_RVCD_IF); pakiet w transporcie idzie
        # interfejsem trasy: z P1 do celu za USB (ostatni skok: HEADER_1), z USB do celu za P1 (następny skok).
        # Dowód wraca tylko, gdy przyszedł interfejsem, którym pakiet wyszedł (IDX_RT_OUTB_IF), i wychodzi tym,
        # którym pakiet przyszedł (IDX_RT_RCVD_IF). Interfejs spoza liczby interfejsów: pakiet odrzucony.
        identity = self.station_identity()
        relay = bytes(range(16))
        near, far = (self.announce_of(bytes([k]) * 64) for k in (61, 62))
        near_dest, far_dest = near[2:18], far[2:18]
        to_near = self.packet(0x50, near_dest, b"n" * 40, transport_id=identity)
        to_far = self.packet(0x50, far_dest, b"f" * 40, transport_id=identity)
        proof_of = lambda raw: self.packet(0x03, bytes.fromhex(self.fields_of(raw.hex())[-1])[:16], bytes(64))
        lines = self.ask([("t_begin", self.TWO), ("t_inif", b"\x01" + near), ("t_inif", b"\x00" + self.via(far, relay, 1)),
                          ("t_route", near_dest), ("t_route", far_dest), ("t_outif", b""),
                          ("t_inif", b"\x00" + to_near), ("t_outif", b""), ("t_inif", b"\x01" + to_far), ("t_outif", b""),
                          ("t_inif", b"\x00" + proof_of(to_near)), ("t_outif", b""), ("t_inif", b"\x00" + proof_of(to_far)),
                          ("t_outif", b""), ("t_forward", b""), ("t_inif", b"\x02" + near)])
        self.assertEqual((lines[3], lines[4]), ("1", "0"))
        self.assertEqual(lines[7], "1:" + (bytes([0x00, 1]) + to_near[18:]).hex())
        self.assertEqual(lines[9], "0:" + (bytes([to_far[0], 1]) + relay + to_far[18:]).hex())
        self.assertEqual(lines[11], "-")   # dowód pakietu wysłanego przez USB przyszedł przez P1
        self.assertEqual(lines[13], "1:" + self.hops(proof_of(to_far), 1).hex())
        self.assertEqual(lines[14].split()[:3], ["2", "0", "1"])
        self.assertEqual(self.parsed(lines[15])[0], "malformed")
        # Transport z jednym interfejsem nie przyjmuje pakietu z interfejsu 1.
        lines = self.ask([("t_begin", self.STATION), ("t_inif", b"\x01" + near), ("t_inif", b"\x00" + near)])
        self.assertEqual([self.parsed(line)[0] for line in lines[1:]], ["malformed", "ok"])

    def test_interfaces_announces_and_path_requests(self):
        # Retransmisja przyjętego ogłoszenia, ogłoszenie własne i własne zapytanie o trasę idą wszystkimi
        # interfejsami (attached_interface = None), także tym, którym ogłoszenie przyszło. Odpowiedź na
        # zapytanie o trasę (z pamięci podręcznej i o cel stacji) idzie tylko interfejsem zapytania.
        identity = self.station_identity()
        address = bytes.fromhex(self.ask([("t_begin", self.TWO)])[0])
        near, far = (self.announce_of(bytes([k]) * 64) for k in (63, 64))
        relay = bytes(range(16))
        dest, tag = bytes(range(16)), bytes(range(100, 116))
        clock = lambda ms: ("t_clock", ms.to_bytes(8, "big"))
        lines = self.ask([("t_begin", self.TWO), ("t_inif", b"\x01" + near), clock(1177), ("t_outif", b""),
                          clock(6700), clock(6800), ("t_inif", b"\x00" + self.via(far, relay, 1)), clock(7000), clock(12600),
                          clock(12700), ("t_outif", b""),
                          ("t_inif", b"\x01" + self.path_request(far[2:18], b"R" * 16)), clock(20000), clock(20401),
                          ("t_outif", b""), ("t_announce", bytes(5) + b"WICI"), ("t_outif", b""),
                          ("t_inif", b"\x01" + self.path_request(address, b"S" * 16)), ("t_outif", b""),
                          ("t_request", dest + tag), ("t_outif", b"")])
        rebroadcast = self.via(near, identity, 1).hex()
        self.assertEqual(lines[3], f"0:{rebroadcast} 1:{rebroadcast}")
        # Drugie nadanie ogłoszenia z USB i dwa nadania ogłoszenia z P1: każde oboma interfejsami.
        self.assertEqual([x[:2] for x in lines[10].split()], ["0:", "1:"] * 3)
        response = lines[14].split()
        self.assertEqual(len(response), 1)
        self.assertTrue(response[0].startswith("1:"))
        self.assertEqual(self.fields_of(response[0][2:])[8], "11")   # PATH_RESPONSE
        own = lines[16].split()
        self.assertEqual((own[0][:2], own[1][:2], own[0][2:]), ("0:", "1:", own[1][2:]))
        reply = lines[18].split()
        self.assertEqual(len(reply), 1)
        self.assertTrue(reply[0].startswith("1:"))
        self.assertEqual(self.fields_of(reply[0][2:])[8], "11")
        request = self.path_request(dest, tag, requestor=identity).hex()
        self.assertEqual(lines[20], f"0:{request} 1:{request}")

    def test_interfaces_send_and_proof(self):
        # Pakiet stacji do celu z trasą idzie interfejsem trasy, do celu bez trasy (wygasłej) wszystkimi;
        # dowód pakietu do stacji idzie interfejsem, którym pakiet przyszedł (Identity.prove: attached_interface).
        address = bytes.fromhex(self.ask([("t_begin", self.TWO)])[0])
        near = self.announce_of(bytes([65]) * 64)
        near_dest = near[2:18]
        send = ("t_send", near_dest + self.EPHEMERAL + self.IV + (7).to_bytes(4, "big") + (60000).to_bytes(4, "big") + b"x")
        station_pub = bytes.fromhex(self.ask([("public_key", self.STATION)])[0])
        token = bytes.fromhex(self.ask([("encrypt", station_pub + self.EPHEMERAL + self.IV + b"report")])[0])
        raw = self.packet(0x00, address, token)
        week = 7 * 24 * 3600 * 1000
        lines = self.ask([("t_begin", self.TWO), ("t_inif", b"\x01" + near), ("t_outif", b""), send, ("t_outif", b""),
                          ("t_inif", b"\x01" + raw), ("t_outif", b""), ("t_clock", (1000 + week + 2000).to_bytes(8, "big")),
                          ("t_outif", b""), send, ("t_outif", b"")])
        self.assertEqual([x[:2] for x in lines[4].split()], ["1:"])
        self.assertEqual(lines[6], "1:" + self.proof_packet(self.STATION, raw).hex())
        sent = lines[10].split()
        self.assertEqual(([x[:2] for x in sent], sent[0][2:]), (["0:", "1:"], sent[1][2:]))

    def test_interfaces_table_restart(self):
        # Interfejs trasy jest w gnieździe tablicy (bit w bajcie znaczników): po restarcie trasa przez USB dalej
        # idzie przez USB. Gniazdo zapisane przez transport z jednym interfejsem (jak przed etapem R4, bit zero)
        # po restarcie z dwoma interfejsami ma trasę przez P1.
        near, other = self.announce_of(bytes([66]) * 64), self.announce_of(bytes([67]) * 64)
        lines = self.ask([("t_begin", self.TWO), ("t_inif", b"\x01" + near), ("t_inif", b"\x00" + other),
                          ("t_restart", b""), ("t_route", near[2:18]), ("t_route", other[2:18])])
        self.assertEqual(lines[4:], ["1", "0"])
        lines = self.ask([("t_begin", self.STATION), ("t_in", near), ("t_restart", b"\x00\x02"), ("t_route", near[2:18])])
        self.assertEqual(lines[3], "0")

    def test_interfaces_discovery_response(self):
        # Zapytanie o cel z zapytaniem „w drodze” czeka na ogłoszenie (discovery_path_requests) z interfejsem
        # pytającego (requesting_interfaces): odpowiedź idzie tylko nim.
        identity = self.station_identity()
        ann = self.announce_of(bytes([68]) * 64)
        dest = ann[2:18]
        lines = self.ask([("t_begin", self.TWO), ("t_inif", b"\x00" + self.path_request(dest, b"A" * 16)),
                          ("t_inif", b"\x01" + self.path_request(dest, b"B" * 16)), ("t_inif", b"\x00" + ann),
                          ("t_outif", b""), ("t_clock", (1001).to_bytes(8, "big")), ("t_outif", b"")])
        self.assertEqual(lines[4], "-")
        self.assertEqual(lines[6], "1:" + self.via(ann[:18] + bytes([0x0B]) + ann[19:], identity, 1).hex())

    def test_interfaces_refusing_interface_does_not_block(self):
        # Interfejs, który nie przyjmie ogłoszenia (mayTransmit), nie wstrzymuje drugiego i sam nie traci
        # próby: dostaje ją, gdy przyjmie (jedno zaległe ogłoszenie na cel i interfejs, jak announce_queue).
        identity = self.station_identity()
        ann = self.announce_of(bytes([69]) * 64)
        dest = ann[2:18]
        rebroadcast = self.via(ann, identity, 1).hex()
        discovery = self.via(ann[:18] + bytes([0x0B]) + ann[19:], identity, 1).hex()
        clock = lambda ms: ("t_clock", ms.to_bytes(8, "big"))
        # USB odmawia: odpowiedź odkrycia tylko dla USB czeka, a retransmisje idą przez P1; po zwolnieniu USB
        # odpowiedź odkrycia i jedno zaległe nadanie retransmisji.
        lines = self.ask([("t_begin", self.TWO), ("t_inif", b"\x01" + self.path_request(dest, b"A" * 16)),
                          ("t_inif", b"\x01" + self.path_request(dest, b"B" * 16)), ("t_busy", b"\x02"),
                          ("t_inif", b"\x00" + ann), clock(1600), ("t_outif", b""), clock(7200), ("t_outif", b""),
                          ("t_busy", b"\x00"), clock(7300), ("t_outif", b""), clock(7400), ("t_outif", b""),
                          clock(7500), ("t_outif", b""), ("t_forward", b"")])
        self.assertEqual(lines[6], "0:" + rebroadcast)
        self.assertEqual(lines[8], "0:" + rebroadcast)
        self.assertEqual(lines[11], "1:" + discovery)
        self.assertEqual(lines[13], "1:" + rebroadcast)
        self.assertEqual(lines[15], "-")
        self.assertEqual(lines[16].split()[4:], ["3", "0", "0"])   # nadania (P1, P1, zaległe USB)
        # P1 odmawia, USB przyjmuje: próby idą przez USB, a P1 dostaje zaległe nadanie, gdy przyjmie.
        lines = self.ask([("t_begin", self.TWO), ("t_busy", b"\x01"), ("t_inif", b"\x01" + ann), clock(1600),
                          ("t_outif", b""), clock(7200), ("t_outif", b""), clock(7300), ("t_outif", b""),
                          ("t_busy", b"\x00"), clock(7400), ("t_outif", b""), clock(7500), ("t_outif", b""),
                          ("t_forward", b"")])
        self.assertEqual(lines[4], "1:" + rebroadcast)
        self.assertEqual(lines[6], "1:" + rebroadcast)
        self.assertEqual(lines[8], "-")
        self.assertEqual(lines[11], "0:" + rebroadcast)
        self.assertEqual(lines[13], "-")
        self.assertEqual(lines[14].split()[4:], ["3", "0", "0"])

    def test_interfaces_emit_returns_accepting_mask(self):
        # emit zwraca maskę interfejsów, które przyjęły ramkę; skrót trafia na listę tylko przy niezerowej masce.
        frame = bytes(range(1, 40))
        other = frame[::-1]
        lines = self.ask([("t_begin", self.TWO), ("t_emit", b"\x01\x03" + frame), ("t_emit", b"\x03\x03" + other),
                          ("t_emit", b"\x00\x03" + other)])
        self.assertEqual(lines[1:], ["2 1", "0 1", "3 2"])

    def test_interfaces_own_response_limit_per_interface(self):
        # Limit odpowiedzi na zapytanie o cel stacji (OWN_RESPONSE_MIN_MS) liczy się osobno na interfejs:
        # zapytanie z USB nie wstrzymuje odpowiedzi na zapytanie z P1; drugie z tego samego interfejsu tak.
        address = bytes.fromhex(self.ask([("t_begin", self.TWO)])[0])
        lines = self.ask([("t_begin", self.TWO), ("t_inif", b"\x01" + self.path_request(address, b"S" * 16)),
                          ("t_outif", b""), ("t_inif", b"\x00" + self.path_request(address, b"T" * 16)), ("t_outif", b""),
                          ("t_inif", b"\x00" + self.path_request(address, b"U" * 16)), ("t_outif", b"")])
        self.assertEqual([x[:2] for x in lines[2].split()], ["1:"])
        self.assertEqual([x[:2] for x in lines[4].split()], ["0:"])
        self.assertEqual(lines[6], "-")

    def test_interfaces_route_on_missing_interface(self):
        # Gniazdo z trasą przez USB po restarcie z jednym interfejsem: brak trasy (jak wpis path_table bez
        # interfejsu przy wczytaniu w Pythonie). Pakiet stacji idzie wszystkimi interfejsami, pakiet
        # w transporcie do tego celu nie ma trasy; znany cel zostaje.
        identity = self.station_identity()
        near = self.announce_of(bytes([70]) * 64)
        near_dest = near[2:18]
        send = ("t_send", near_dest + self.EPHEMERAL + self.IV + (7).to_bytes(4, "big") + (60000).to_bytes(4, "big") + b"x")
        transit = self.packet(0x50, near_dest, b"n" * 40, transport_id=identity)
        lines = self.ask([("t_begin", self.TWO), ("t_inif", b"\x01" + near), ("t_restart", b"\x00\x01"),
                          ("t_route", near_dest), ("t_outif", b""), send, ("t_outif", b""), ("t_in", transit),
                          ("t_outif", b""), ("t_forward", b"")])
        self.assertEqual(lines[3], "none")
        self.assertEqual([x[:2] for x in lines[6].split()], ["0:"])
        self.assertEqual(lines[8], "-")
        self.assertEqual(lines[9].split()[:2], ["0", "1"])

    def test_interfaces_routes_by_interface(self):
        # Cele z trasą przez USB z indeksu tablicy (węzeł stanowiska odtwarza z nich cele komputera po
        # restarcie): najpierw ostatnio używana trasa, z limitem; trasa przez P1 osobno. Po restarcie z dwoma
        # interfejsami te same, z jednym interfejsem żadna trasa przez USB. Filtr skoków: ogłoszenia z 0 skokami
        # dają trasy o 1 skoku (cele samego komputera), żadnej o 2.
        first, second, radio = (self.announce_of(bytes([n]) * 64) for n in (73, 74, 75))
        clock = lambda s: ("t_clock", (s * 1000).to_bytes(8, "big"))
        lines = self.ask([("t_begin", self.TWO), clock(10), ("t_inif", b"\x01" + first), clock(20),
                          ("t_inif", b"\x01" + second), clock(30), ("t_inif", b"\x00" + radio),
                          ("t_routes", b"\x01\x08"), ("t_routes", b"\x01\x01"), ("t_routes", b"\x00\x08"),
                          ("t_routes", b"\x01\x08\x01"), ("t_routes", b"\x01\x08\x02"),
                          ("t_restart", b"\x00\x02"), ("t_routes", b"\x01\x08"),
                          ("t_restart", b"\x00\x01"), ("t_routes", b"\x01\x08"), ("t_routes", b"\x00\x08")])
        usb = f"{second[2:18].hex()}:1 {first[2:18].hex()}:1"
        self.assertEqual(lines[7:12], [usb, f"{second[2:18].hex()}:1", f"{radio[2:18].hex()}:0", usb, "-"])
        self.assertEqual(lines[12:14], ["3 3", usb])
        self.assertEqual(lines[14:17], ["3 1", "-", f"{radio[2:18].hex()}:0"])

    def test_interfaces_forward_same_interface_and_discovery_both(self):
        # Pakiet w transporcie z USB do celu za USB wraca tym samym interfejsem, a dowód też. Odpowiedź
        # odkrycia, gdy pytają oba interfejsy, idzie oboma w jednym poll().
        identity = self.station_identity()
        near = self.announce_of(bytes([71]) * 64)
        near_dest = near[2:18]
        to_near = self.packet(0x50, near_dest, b"n" * 40, transport_id=identity)
        proof = self.packet(0x03, bytes.fromhex(self.fields_of((bytes([0x00, 1]) + to_near[18:]).hex())[-1])[:16], bytes(64))
        lines = self.ask([("t_begin", self.TWO), ("t_inif", b"\x01" + near), ("t_outif", b""), ("t_inif", b"\x01" + to_near),
                          ("t_outif", b""), ("t_inif", b"\x01" + proof), ("t_outif", b"")])
        self.assertEqual(lines[4], "1:" + (bytes([0x00, 1]) + to_near[18:]).hex())
        self.assertEqual(lines[6], "1:" + self.hops(proof, 1).hex())
        ann = self.announce_of(bytes([72]) * 64)
        dest = ann[2:18]
        discovery = self.via(ann[:18] + bytes([0x0B]) + ann[19:], identity, 1).hex()
        lines = self.ask([("t_begin", self.TWO), ("t_inif", b"\x00" + self.path_request(dest, b"A" * 16)),
                          ("t_inif", b"\x00" + self.path_request(dest, b"B" * 16)),
                          ("t_inif", b"\x01" + self.path_request(dest, b"C" * 16)), ("t_inif", b"\x00" + ann),
                          ("t_outif", b""), ("t_clock", (1001).to_bytes(8, "big")), ("t_outif", b"")])
        self.assertEqual(lines[5], "-")
        self.assertEqual(lines[7], f"0:{discovery} 1:{discovery}")

    def test_full_hash_matches_sha256(self):
        # Pusty wejściowy ciąg, granice bloku SHA-256 (55, 56, 64 B) i długi ciąg.
        inputs = [b"", b"WICI", bytes(55), bytes(56), bytes(64), bytes(range(256)) * 20]
        got = self.ask([("full_hash", data) for data in inputs])
        self.assertEqual(got, [hashlib.sha256(data).hexdigest() for data in inputs])

    def test_board_selftest(self):
        # Samotest z obrazów z rdzeniem (core_selftest.cpp) przechodzi na komputerze: próby przy starcie
        # i wszystkie (RNS SELFTEST).
        quick = "1 token_decrypt:1 token_encrypt:1 sign:1 validate:1"
        self.assertEqual(self.ask([("selftest", b"\x04"), ("selftest", b"\x09")]),
                         [quick, quick + " validate_reject:1 public_key:1 announce_validate:1 announce_build:1 ifac:1"])

    def test_board_selftest_vectors_from_python(self):
        # Każda stała szesnastkowa samotestu jest całą wartością z wektorów Reticulum w Pythonie.
        source = SELFTEST.read_text()
        constants = {name: "".join(re.findall(r'"([0-9a-f]*)"', body))
                     for name, body in re.findall(r"constexpr char (\w+)\[\] =\s*((?:\s*\"[0-9a-f]*\")+);", source)}
        self.assertEqual(len(constants), 15)   # z frazą IFAC (tekst szesnastkowy jak w konfiguracji)
        values = set()

        def collect(node):
            if isinstance(node, dict):
                for value in node.values():
                    collect(value)
            elif isinstance(node, list):
                for value in node:
                    collect(value)
            elif isinstance(node, str):
                values.add(node)
        collect(VECTORS)
        self.assertEqual({n for n, c in constants.items() if c not in values}, set())
        self.assertEqual(constants["IFAC_PASSPHRASE"], VECTORS["ifac"]["passphrase"])

    def test_bad_input(self):
        result = subprocess.run([str(self.binary)], input="full_hash abc\nfull_hash zz\nunknown 00\n\n", capture_output=True,
                                text=True, env=ENV, timeout=60)
        self.assertEqual(result.stdout.splitlines(), ["error"] * 4)


class Core32Tests(CoreTests):
    """Te same próby w programie 32-bitowym: typy i limby biblioteki Crypto jak na płytkach."""
    FLAGS = ("-m32", "-funsigned-char")
    # Na Linuksie g++ z gcc-multilib ma 32-bitowe biblioteki sanitizerów; clang ich zwykle nie ma.
    COMPILERS = ("g++", "clang++", "c++")

    @classmethod
    def setUpClass(cls):
        cxx = compiler(cls.COMPILERS)
        if os.name == "posix" and cxx and not builds_32bit(cxx):
            if REQUIRED and sys.platform.startswith("linux"):
                raise RuntimeError(f"{cxx} cannot build 32-bit programs (apt-get install g++-multilib)")
            raise unittest.SkipTest("no 32-bit C++ toolchain")
        super().setUpClass()


if __name__ == "__main__":
    unittest.main()
