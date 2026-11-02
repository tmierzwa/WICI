# SPDX-License-Identifier: MIT
"""Durable migration barrier restart, torn write and corruption behavior."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tests.test_envelope_cross_language import ROOT, SRC


class MigrationStateTest(unittest.TestCase):
    def test_power_cut_and_fail_closed(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            self.skipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "migration_state_check"
            command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                       "-fsanitize=address,undefined", "-fno-omit-frame-pointer", f"-I{SRC}",
                       str(SRC / "migration_state.cpp"), str(SRC / "sha2.cpp"),
                       str(ROOT / "tests" / "native" / "migration_state_check.cpp"), "-o", str(binary)]
            built = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr[-4000:])
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr[-4000:])


if __name__ == "__main__":
    unittest.main()
