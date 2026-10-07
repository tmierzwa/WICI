# SPDX-License-Identifier: MIT
"""Host checks of Arduino-free firmware units: the P1 CRC and the test frame of TXPKT/RXPER."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "firmware" / "src"
sys.path.insert(0, str(ROOT / "software" / "reference"))
from reference import crc16  # noqa: E402

HARNESS = r"""
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "crc16.h"
#include "testframe.h"

int main(int argc, char** argv) {
    if (argc == 3 && !strcmp(argv[1], "crc")) {
        printf("%04X\n", p1::crc16(reinterpret_cast<const uint8_t*>(argv[2]), strlen(argv[2])));
        return 0;
    }
    if (argc == 4 && !strcmp(argv[1], "frame")) {
        uint8_t frame[testframe::MAX_LENGTH];
        const size_t length = strtoul(argv[2], nullptr, 10);
        const uint16_t seq = strtoul(argv[3], nullptr, 10);
        if (!testframe::build(frame, length, seq)) { printf("build failed\n"); return 1; }
        for (size_t i = 0; i < length; ++i) printf("%02X", frame[i]);
        printf("\n");
        uint16_t back = 0;
        const bool ok = testframe::check(frame, length, &back);
        frame[2] ^= 0x01;  // one flipped bit must fail the check (length 4 flips a CRC byte)
        const bool corrupt = testframe::check(frame, length, nullptr);
        printf("%s %u %s\n", ok ? "ok" : "bad", back, corrupt ? "accepted" : "rejected");
        return 0;
    }
    return 2;
}
"""


def compiler():
    for name in ("c++", "g++", "clang++"):
        path = shutil.which(name)
        if path:
            return path
    return None


@unittest.skipUnless(compiler(), "no host C++ compiler")
class HostUnitTests(unittest.TestCase):
    """Compile crc16.h and testframe.cpp with the host compiler and compare with the model."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        (root / "harness.cpp").write_text(HARNESS, encoding="utf-8")
        cls.binary = root / "harness"
        subprocess.run([compiler(), "-std=c++17", "-Wall", "-Wextra", "-Werror", f"-I{SRC}", str(root / "harness.cpp"),
                        str(SRC / "testframe.cpp"), "-o", str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_harness(self, *args):
        return subprocess.run([str(self.binary), *args], capture_output=True, text=True, check=True).stdout.split()

    def test_crc_matches_spec_vector_and_model(self):
        self.assertEqual(self.run_harness("crc", "123456789"), ["29B1"])
        for text in ("", "A", "WICI 0.5"):
            self.assertEqual(int(self.run_harness("crc", text)[0] if text else "FFFF", 16), crc16(text.encode()))

    def test_frame_round_trip_and_corruption(self):
        for length, seq in ((4, 0), (18, 1), (103, 65535), (50, 1234)):
            frame_hex, ok, back, corrupt = self.run_harness("frame", str(length), str(seq))
            frame = bytes.fromhex(frame_hex)
            self.assertEqual(len(frame), length)
            self.assertEqual(int.from_bytes(frame[:2], "big"), seq)
            self.assertEqual(int.from_bytes(frame[-2:], "big"), crc16(frame[:-2]))
            self.assertEqual((ok, int(back), corrupt), ("ok", seq, "rejected"), (length, seq))

    def test_filler_depends_on_sequence_and_is_not_constant(self):
        a = bytes.fromhex(self.run_harness("frame", "40", "7")[0])
        b = bytes.fromhex(self.run_harness("frame", "40", "8")[0])
        self.assertNotEqual(a[2:-2], b[2:-2])
        self.assertGreater(len(set(a[2:-2])), 10)

    def test_rejects_bad_lengths(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_harness("frame", "3", "1")
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_harness("frame", "104", "1")


if __name__ == "__main__":
    unittest.main()
