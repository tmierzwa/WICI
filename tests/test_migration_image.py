# SPDX-License-Identifier: MIT
"""Snapshot region and cache erasure boundaries under ASan/UBSan."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tests.test_envelope_cross_language import ROOT, SRC


class MigrationImageTest(unittest.TestCase):
    def test_layout(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            self.skipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "migration_image_check"
            cmd = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                   "-fno-omit-frame-pointer", f"-I{SRC}", str(SRC / "migration_image.cpp"), str(SRC / "sha2.cpp"),
                   str(ROOT / "tests" / "native" / "migration_image_check.cpp"), "-o", str(binary)]
            built = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr[-4000:])
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr[-4000:])


if __name__ == "__main__":
    unittest.main()
