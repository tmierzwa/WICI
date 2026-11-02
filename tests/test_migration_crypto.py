# SPDX-License-Identifier: MIT
"""Cross-language migration vectors and authenticated corruption checks."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.test_envelope_cross_language import CRYPTO, ROOT, SRC, UNITS

sys.path.insert(0, str(ROOT / "software" / "laptop"))
from wici import migration_crypto as mc  # noqa: E402


class MigrationCryptoTest(unittest.TestCase):
    def test_cpp_python_vectors(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler or not (CRYPTO / ".wici-stamp").exists():
            self.skipTest("C++ compiler or pinned Crypto sources unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "migration_crypto_check"
            flags = ["-std=c++17", "-fno-exceptions", "-fno-rtti", "-fsanitize=address,undefined",
                     "-fno-omit-frame-pointer", "-g", "-O1", f"-I{SRC}", "-isystem", str(CRYPTO)]
            sources = [SRC / "migration_crypto.cpp", SRC / "sha2.cpp",
                       ROOT / "tests" / "native" / "migration_crypto_check.cpp",
                       *(CRYPTO / unit for unit in UNITS)]
            objects = []
            for index, source in enumerate(sources):
                obj = Path(directory) / f"unit{index}.o"
                warnings = ["-Wall", "-Wextra", "-Werror"] if index < 3 else ["-w"]
                built = subprocess.run([compiler, *flags, *warnings, "-c", str(source), "-o", str(obj)],
                                       capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, f"{source.name}: {built.stderr[-4000:]}")
                objects.append(obj)
            built = subprocess.run([compiler, "-fsanitize=address,undefined", *(str(x) for x in objects),
                                    "-o", str(binary)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr[-4000:])
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr[-4000:])
        actual = {key: bytes.fromhex(value) for key, value in
                  (line.split("=", 1) for line in result.stdout.splitlines())}
        source, target = bytes(range(32)), bytes(range(32, 64))
        mid, identity, digest = bytes(range(96, 112)), bytes(range(112, 128)), bytes(range(64, 96))
        self.assertEqual(actual["source_public"], mc.public_key(source))
        self.assertEqual(actual["target_public"], mc.public_key(target))
        confirm_key, package_key = mc.derive(source, actual["target_public"], mid)
        self.assertEqual((actual["confirm_key"], actual["package_key"]), (confirm_key, package_key))
        self.assertEqual(mc.derive(target, actual["source_public"], mid), (confirm_key, package_key))
        header = mc.make_header(mid, identity, actual["source_public"], digest, 517)
        self.assertEqual(actual["header"], header)
        self.assertEqual(actual["cipher"], mc.seal_part(package_key, header, 7, bytes(range(256)) * 2))
        self.assertEqual(mc.open_part(package_key, header, 7, actual["cipher"]), bytes(range(256)) * 2)
        for kind in ("imported", "retired", "aborted"):
            self.assertEqual(actual[kind], mc.confirmation(confirm_key, kind, mid, digest))
        with self.assertRaises(ValueError):
            mc.open_part(package_key, header, 8, actual["cipher"])
        with self.assertRaises(ValueError):
            mc.open_part(package_key, header, 7, bytes([actual["cipher"][0] ^ 1]) + actual["cipher"][1:])
        with self.assertRaises(ValueError):
            mc.parse_header(header, mid, 516)


if __name__ == "__main__":
    unittest.main()
