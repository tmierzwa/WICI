# SPDX-License-Identifier: MIT
"""Durable numbered-link airtime caps survive restart and torn writes."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WiciAirtime(unittest.TestCase):
    def test_durable_pool_and_beacon_caps(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "airtime_check"
            subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", f"-I{ROOT / 'firmware' / 'src'}",
                            str(ROOT / "firmware" / "src" / "wici_airtime.cpp"),
                            str(ROOT / "tests" / "native" / "wici_airtime_check.cpp"),
                            "-o", str(binary)], check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)
