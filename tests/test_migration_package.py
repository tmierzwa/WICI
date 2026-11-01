# SPDX-License-Identifier: MIT
"""Differential C++/Python vectors for a complete 256 KiB encrypted export."""

from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.test_envelope_cross_language import CRYPTO, ROOT, SRC, UNITS

sys.path.insert(0, str(ROOT / "software" / "laptop"))
from wici import migration_crypto as mc  # noqa: E402


class MigrationPackageTest(unittest.TestCase):
    def test_export_vector(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler or not (CRYPTO / ".wici-stamp").exists():
            self.skipTest("C++ compiler or pinned Crypto sources unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "migration_package_check"
            flags = ["-std=c++17", "-fno-exceptions", "-fno-rtti", "-fsanitize=address,undefined",
                     "-fno-omit-frame-pointer", "-g", "-O1", f"-I{SRC}", "-isystem", str(CRYPTO)]
            sources = [*(SRC / name for name in ("migration_package.cpp", "migration_image.cpp", "migration_crypto.cpp",
                                                   "migration_state.cpp", "sha2.cpp")), ROOT / "tests" / "native" / "migration_package_check.cpp",
                       *(CRYPTO / unit for unit in UNITS)]
            objects = []
            for index, source in enumerate(sources):
                obj = Path(directory) / f"unit{index}.o"
                warnings = ["-Wall", "-Wextra", "-Werror"] if index < 6 else ["-w"]
                built = subprocess.run([compiler, *flags, *warnings, "-c", str(source), "-o", str(obj)],
                                       capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, f"{source.name}: {built.stderr[-4000:]}")
                objects.append(obj)
            built = subprocess.run([compiler, "-fsanitize=address,undefined", *(str(x) for x in objects),
                                    "-o", str(binary)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr[-4000:])
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr[-4000:])
        actual = {key: bytes.fromhex(value) for key, value in
                  (line.split("=", 1) for line in run.stdout.splitlines())}
        plain = bytes(((i >> 7) & 255) for i in range(256 * 1024))
        source, target = bytes(range(32)), bytes(range(32, 64))
        mid, identity = bytes(range(96, 112)), bytes(range(112, 128))
        confirm_key, package_key = mc.derive(source, mc.public_key(target), mid)
        self.assertNotEqual(confirm_key, package_key)
        header = mc.make_header(mid, identity, mc.public_key(source), sha256(plain).digest(), len(plain))
        self.assertEqual(actual["header"], header)
        chunks = [mc.seal_part(package_key, header, index, plain[index * 512:(index + 1) * 512])
                  for index in range(512)]
        self.assertEqual(actual["first"], chunks[0])
        self.assertEqual(actual["last"], chunks[-1])
        self.assertEqual(actual["sha"], sha256(header + b"".join(chunks)).digest())


if __name__ == "__main__":
    unittest.main()
