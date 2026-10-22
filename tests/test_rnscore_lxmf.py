# SPDX-License-Identifier: MIT
"""LXMF SA1 messages in the station Reticulum core against vectors from reference LXMF in Python.

Builds the core like tests/test_rnscore.py (ASan, UBSan, C++17 without exceptions and RTTI, -Werror)
with tests/native/rnscore_lxmf_check.cpp, which answers one command per line. Expected values come
from tests/vectors/lxmf.json (made by LXMF c3ff2d6 on Reticulum e40191b, firmware/tools/lxmf_vectors.py). Without WICI_RNS_PYTHON the vector file is checked only for shape;
with it (a Python with Reticulum and LXMF at the pinned commits) it must match a fresh run byte for byte.
Skipped without a compiler or the stack sources, unless WICI_RNS_SANITIZE=1 (CI).

  python3 -m unittest tests.test_rnscore_lxmf -v
"""

import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "tests" / "native" / "rnscore_lxmf_check.cpp"
VECTORS_FILE = ROOT / "tests" / "vectors" / "lxmf.json"
VECTORS = json.loads(VECTORS_FILE.read_text())
TOOL = ROOT / "firmware" / "tools" / "lxmf_vectors.py"
RNS_PYTHON = os.environ.get("WICI_RNS_PYTHON")

sys.path.insert(0, str(ROOT / "tests"))
import test_rnscore as core  # noqa: E402  (budowa rdzenia, sanitizery, źródła stosu)


def build(out_dir: Path) -> Path:
    cxx = core.compiler()
    base = [cxx, "-std=c++17", *core.SANITIZE, f"-I{core.CORE}", "-isystem", str(core.STACK / "Crypto")]
    objects = []
    for source in sorted(core.CORE.glob("*.cpp")):
        objects.append(out_dir / f"core_{source.stem}.o")
        subprocess.run([*base, "-fno-exceptions", "-fno-rtti", "-Wall", "-Wextra", "-Werror", "-c", str(source),
                        "-o", str(objects[-1])], check=True, capture_output=True, text=True)
    for name in core.CRYPTO_UNITS:
        objects.append(out_dir / f"crypto_{Path(name).stem}.o")
        subprocess.run([*base, "-w", "-c", str(core.STACK / "Crypto" / name), "-o", str(objects[-1])],
                       check=True, capture_output=True, text=True)
    objects.append(out_dir / "rnscore_lxmf_check.o")
    subprocess.run([*base, "-Wall", "-Wextra", "-Werror", "-c", str(CHECK), "-o", str(objects[-1])],
                   check=True, capture_output=True, text=True)
    binary = out_dir / "rnscore_lxmf_check"
    subprocess.run([cxx, *core.SANITIZE, *map(str, objects), "-o", str(binary)], check=True, capture_output=True, text=True)
    return binary


class VectorFileTests(unittest.TestCase):
    def test_pinned_source(self):
        self.assertEqual(VECTORS["source"], {"reticulum": "1.5.5", "commit": "e40191b3d193b46b7f2d8a44424a594cd758839b",
                                             "lxmf": "1.2.0", "lxmf_commit": "c3ff2d6dc2f256daab896dadc044dd5a913ecbb7",
                                             "tool": "firmware/tools/lxmf_vectors.py"})

    def test_shape(self):
        # Wzorzec przyjmuje wiadomości z LXMessage.pack z poprawnym podpisem i tym samym skrótem; rdzeń
        # odrzuca tylko z podanych powodów, a odstępstwa (Python przyjmuje z poprawnym podpisem) to kształt
        # inny niż SA1, długość, klucz nadawcy.
        lx = VECTORS["lxmf"]
        received = {c["name"]: c for c in lx["received"]}
        for b in lx["built"]:
            self.assertTrue(received[f"built_{b['name']}"]["signature_validated"])
            self.assertEqual(received[f"built_{b['name']}"]["hash"], b["hash"])
        self.assertEqual({c["core_rejects"] for c in lx["received"]},
                         {None, "reference_rejects", "signature", "not_sa1", "length", "sender_key"})
        for c in lx["received"]:
            if c["core_rejects"] in ("not_sa1", "length", "sender_key"):
                self.assertTrue(c["accepted"] and c["signature_validated"], c["name"])

    @unittest.skipUnless(RNS_PYTHON, "WICI_RNS_PYTHON not set")
    def test_matches_reference_implementation(self):
        fresh = subprocess.run([RNS_PYTHON, str(TOOL)], check=True, capture_output=True, text=True).stdout
        self.assertEqual(fresh, VECTORS_FILE.read_text(), "regenerate: python firmware/tools/lxmf_vectors.py > tests/vectors/lxmf.json")


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "posix":
            raise unittest.SkipTest("POSIX only")
        if not core.compiler():
            raise unittest.SkipTest("no C++ compiler")
        if not (core.STACK / "Crypto" / ".wici-stamp").is_file():
            if not core.REQUIRED:
                raise unittest.SkipTest("stack sources not fetched (python3 firmware/tools/stack_deps.py)")
            core.stack_deps.fetch(core.FIRMWARE)
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
        result = subprocess.run([str(self.binary)], input=stdin, capture_output=True, text=True, env=core.ENV, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), len(commands), result.stdout)
        return lines

    @staticmethod
    def pack_args(lx: dict, timestamp: float, content: bytes) -> bytes:
        return bytes.fromhex(lx["sender_private_key"] + lx["destination_hash"] + lx["source_hash"]) + \
            struct.pack(">d", timestamp) + content

    def receive(self, cases, key=None):
        lx = VECTORS["lxmf"]
        prefix = bytes.fromhex((key or lx["sender_public_key"]) + lx["destination_hash"])
        return self.ask([("lxmf_receive", prefix + bytes.fromhex(c["data"])) for c in cases])

    def test_pack(self):
        # LXMessage.pack bajt w bajt (podpis Ed25519 jest deterministyczny) i ten sam skrót; treści pustej,
        # ponad 256 B i tytułu innego niż SA1 rdzeń nie składa.
        lx = VECTORS["lxmf"]
        built = [b for b in lx["built"] if b["name"] != "title_other"]
        got = self.ask([("lxmf_pack", self.pack_args(lx, b["timestamp"], bytes.fromhex(b["content"]))) for b in built])
        self.assertEqual(dict(zip((b["name"] for b in built), got)),
                         {b["name"]: "none" if b["name"] in ("content_0", "content_257") else f"{b['data']} {b['hash']}"
                          for b in built})

    def test_receive(self):
        # Przyjęte tylko to, co Python przyjmuje z poprawnym podpisem i co jest wiadomością SA1 od celu
        # lxmf.delivery podanego klucza; skrót, czas i treść jak w Pythonie.
        cases = VECTORS["lxmf"]["received"]
        got = self.receive(cases)
        expected, actual = {}, {}
        for c, line in zip(cases, got):
            expected[c["name"]] = "none" if c["core_rejects"] else f"{c['hash']} T {c['content']}"
            parts = line.split(" ")
            if len(parts) == 3:
                self.assertEqual(float(parts[1]), float(c["timestamp"]), c["name"])
                parts[1] = "T"
            actual[c["name"]] = " ".join(parts)
        self.assertEqual(actual, expected)
        self.assertGreaterEqual(sum(line != "none" for line in got), 19)

    def test_reject_reason(self):
        # Powód odrzucenia dla diagnostyki stacji: zły podpis, klucz innego nadawcy, kształt i znaczek pracy
        # (payload jako tablica 5 elementów, 0x95); wiadomość przyjęta ma powód "none".
        lx = VECTORS["lxmf"]
        prefix = bytes.fromhex(lx["sender_public_key"] + lx["destination_hash"])
        cases = lx["received"]
        got = self.ask([("lxmf_reason", prefix + bytes.fromhex(c["data"])) for c in cases])
        # Zmiany bajtów w przypadkach "signature" wykrywa czasem wcześniej sprawdzenie kształtu albo klucza.
        rejected = {"shape", "stamp", "source", "signature"}
        expected = {None: {"none"}, "signature": rejected, "sender_key": {"source"}, "not_sa1": {"shape"},
                    "length": {"shape"}, "reference_rejects": rejected}
        for c, reason in zip(cases, got):
            self.assertIn(reason, {"stamp"} if c["name"] == "payload_5_elements_stamp" else expected[c["core_rejects"]], c["name"])
        names = dict(zip((c["name"] for c in cases), got))
        self.assertEqual([names[n] for n in ("signature_flipped_first", "signature_flipped_last", "signed_by_other_identity",
                                             "source_hash_flipped")], ["signature", "signature", "signature", "source"])

    def test_receive_with_key_of_other_sender(self):
        # Ta sama wiadomość z kluczem jej nadawcy jest przyjęta, a z kluczem innej tożsamości nie.
        lx = VECTORS["lxmf"]
        case = next(c for c in lx["received"] if c["name"] == "other_sender_own_signature")
        self.assertEqual(case["core_rejects"], "sender_key")
        got = self.receive([case], lx["other_public_key"])[0].split(" ")
        self.assertEqual(got[0], case["hash"])
        self.assertEqual(self.receive([case])[0], "none")

    def test_roundtrip_and_mutations(self):
        # Wiadomość złożona przez rdzeń rdzeń przyjmuje; zmiana dowolnego bitu danych daje odrzucenie.
        lx = VECTORS["lxmf"]
        content = '[1,2,"0123456789abcdef0123456789abcdef",3,7,2]'.encode()
        data, digest = self.ask([("lxmf_pack", self.pack_args(lx, 1790000001.0, content))])[0].split(" ")
        data = bytes.fromhex(data)
        mutated = [data[:i] + bytes([data[i] ^ (1 << bit)]) + data[i + 1:] for i in range(len(data)) for bit in range(8)]
        got = self.receive([{"data": d.hex()} for d in [data] + mutated])
        self.assertEqual(got[0], f"{digest} 1790000001 {content.hex()}")
        self.assertEqual(got[1:], ["none"] * len(mutated))

    def test_every_length(self):
        # Każdy przedrostek wiadomości 399 B (podpisanej z dopełnieniem zerami) i ta sama z jednym bajtem więcej:
        # bez błędu pamięci (ASan); przyjęta tylko cała, 400 B już nie (LXMF_MAX_RECEIVED).
        base = bytes.fromhex(next(c for c in VECTORS["lxmf"]["received"] if c["name"] == "length_399")["data"])
        got = self.receive([{"data": base[:n].hex()} for n in range(len(base) + 1)] + [{"data": (base + b"\x00").hex()}])
        self.assertEqual([n for n, line in enumerate(got) if line != "none"], [399])

    def test_bad_input(self):
        result = subprocess.run([str(self.binary)], input="lxmf_receive abc\nlxmf_receive zz\nlxmf_pack 00\nunknown 00\n\n",
                                capture_output=True, text=True, env=core.ENV, timeout=60)
        self.assertEqual(result.stdout.splitlines(), ["error"] * 5)


if __name__ == "__main__":
    unittest.main()
