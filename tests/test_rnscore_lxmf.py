# SPDX-License-Identifier: MIT
"""MessagePack and LXMF in the station Reticulum core against vectors from reference Python code.

Builds the core like tests/test_rnscore.py (ASan, UBSan, C++17 without exceptions and RTTI, -Werror)
with tests/native/rnscore_lxmf_check.cpp, which answers one command per line. Expected values come
from tests/vectors/lxmf.json (made by u-msgpack-python in Reticulum e40191b and LXMF c3ff2d6,
firmware/tools/lxmf_vectors.py). Without WICI_RNS_PYTHON the vector file is checked only for shape;
with it (a Python with Reticulum and LXMF at the pinned commits) it must match a fresh run byte for byte.
Skipped without a compiler or the stack sources, unless WICI_RNS_SANITIZE=1 (CI).

  python3 -m unittest tests.test_rnscore_lxmf -v
"""

import json
import os
from pathlib import Path
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
                                             "umsgpack": "2.7.1", "tool": "firmware/tools/lxmf_vectors.py"})

    def test_deviations_are_accepted_by_reference(self):
        # Odstępstwo to wejście, które Python przyjmuje, a rdzeń odrzuca; innych rodzajów nie ma.
        deviations = [c for c in VECTORS["msgpack"] if c.get("core_deviation")]
        self.assertTrue(all(c["accepted"] for c in deviations))
        self.assertEqual({c["core_deviation"] for c in deviations}, {"depth", "ext", "map_key"})

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
    def depth_and(data: bytes) -> bytes:
        return bytes([VECTORS["msgpack_max_depth"]]) + data

    def test_msgpack_validate(self):
        # Ta sama decyzja i długość pierwszej wartości co unpackb, poza odstępstwami (odrzucone).
        cases = VECTORS["msgpack"]
        got = self.ask([("mp_validate", self.depth_and(bytes.fromhex(c["data"]))) for c in cases])
        expected = ["none" if not c["accepted"] or c["core_deviation"] else str(c["consumed"]) for c in cases]
        self.assertEqual(dict(zip((c["name"] for c in cases), got)), dict(zip((c["name"] for c in cases), expected)))
        self.assertGreater(sum(c["accepted"] and not c["core_deviation"] for c in cases), 60)

    def test_msgpack_writer(self):
        # Pisarz składa te same bajty co packb (tablica, mapa, float64, bin); ponad 65 535 odmawia.
        cases = VECTORS["msgpack_writer"]
        commands = []
        for c in cases:
            if c["op"] in "am":
                commands.append(("mp_write", c["op"].encode() + c["value"].to_bytes(4, "big")))
            elif c["op"] == "f":
                commands.append(("mp_write", b"f" + bytes.fromhex(c["value"])))
            else:
                commands.append(("mp_write", b"b" + (bytes(range(256)) * (c["value"] // 256) + bytes(range(c["value"] % 256)))))
        got = self.ask(commands)
        expected = []
        for (_, arg), c in zip(commands, cases):
            if c["op"] in "amb" and c["value"] > 65535:
                expected.append("none")
            else:
                expected.append(c["packed"] + (arg[1:].hex() if c["op"] == "b" else ""))
        self.assertEqual(got, expected)

    def test_msgpack_depth_limit(self):
        # Limit głębokości jest parametrem, ale nie większym niż MAX_DEPTH (8): stos poziomów ma stały rozmiar.
        by_name = {c["name"]: bytes.fromhex(c["data"]) for c in VECTORS["msgpack"]}
        got = self.ask([("mp_validate", bytes([d]) + by_name["depth_8"]) for d in (0, 7, 8, 9, 255)] +
                       [("mp_validate", bytes([255]) + by_name["depth_9"]),
                        ("mp_validate", bytes([0]) + b"\x01"), ("mp_validate", bytes([0]) + b"\x90")])
        self.assertEqual(got, ["none", "none", "9", "9", "9", "none", "1", "none"])

    def test_bad_input(self):
        result = subprocess.run([str(self.binary)], input="mp_validate abc\nmp_validate zz\nmp_validate \nmp_write 7a00\nunknown 00\n\n",
                                capture_output=True, text=True, env=core.ENV, timeout=60)
        self.assertEqual(result.stdout.splitlines(), ["error"] * 6)


if __name__ == "__main__":
    unittest.main()
