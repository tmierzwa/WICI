# SPDX-License-Identifier: MIT
"""Host checks of Arduino-free firmware units: the P1 CRC, the test frame of TXPKT/RXPER and the FRAM journal."""

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
#include <vector>
#include "crc16.h"
#include "journal.h"
#include "testframe.h"

// FRAM w RAM: 512 KiB skasowane do 0xFF jak nowy układ.
struct RamStorage : journal::Storage {
    std::vector<uint8_t> bytes = std::vector<uint8_t>(512 * 1024, 0xFF);
    bool read(uint32_t address, uint8_t* data, size_t count) override {
        if (address + count > bytes.size()) return false;
        memcpy(data, &bytes[address], count);
        return true;
    }
    bool write(uint32_t address, const uint8_t* data, size_t count) override {
        if (address + count > bytes.size()) return false;
        memcpy(&bytes[address], data, count);
        return true;
    }
};

int journalScenario() {
    RamStorage ram;
    journal::Journal j(ram);
    printf("fresh %d %d %u %u %u\n", j.begin(), j.debtFresh(), j.debtValid(), j.clock().seq, j.eventSeq());
    printf("write %d %d\n", j.writeDebt(16228, 10), j.writeDebt(5000, 20));
    journal::Journal j2(ram);
    j2.begin();
    printf("reread %u %u %u %u\n", j2.debt().seq, j2.debt().a, j2.debt().b, j2.debtValid());
    // Zanik zasilania: treść rekordu 3 bez znacznika zatwierdzenia.
    journal::SmallRecord lost; lost.seq = 3; lost.a = 999; lost.b = 30;
    uint8_t body[journal::SMALL_RECORD];
    journal::encodeSmall(lost, body);
    ram.write(journal::DEBT_BASE + (3 % journal::DEBT_SLOTS) * journal::SMALL_RECORD, body, sizeof(body));
    journal::Journal j3(ram);
    j3.begin();
    printf("uncommitted %u %u %u\n", j3.debt().seq, j3.debt().a, j3.debtValid());
    // Uszkodzony bajt rekordu 2: zostaje rekord 1.
    ram.bytes[journal::DEBT_BASE + (2 % journal::DEBT_SLOTS) * journal::SMALL_RECORD + 5] ^= 0x01;
    journal::Journal j4(ram);
    j4.begin();
    printf("corrupt %u %u %u\n", j4.debt().seq, j4.debt().a, j4.debtValid());
    // Pierścień długu: po 40 zapisach 32 poprawne rekordy, najnowszy numer 41.
    for (int i = 0; i < 40; ++i) j4.writeDebt(100 + i, 40 + i);
    journal::Journal j5(ram);
    j5.begin();
    printf("ring %u %u %u\n", j5.debt().seq, j5.debt().a, j5.debtValid());
    // Zegar i zdarzenia z zawinięciem bufora 512 wpisów.
    printf("clock %d\n", j5.writeClock(100, 3));
    for (int i = 1; i <= 600; ++i) { char text[16]; snprintf(text, sizeof(text), "e%d", i); j5.writeEvent(i, text); }
    journal::Journal j6(ram);
    j6.begin();
    journal::EventRecord e0, e511, e512;
    const bool r0 = j6.readEvent(0, e0), r511 = j6.readEvent(511, e511), r512 = j6.readEvent(512, e512);
    printf("events %u %u %u %d %s %d %s %d\n", j6.clock().a, j6.clock().b, j6.eventSeq(), r0, e0.text, r511, e511.text, r512);
    // Długi tekst zdarzenia jest obcinany do 53 znaków.
    j6.writeEvent(7, "0123456789012345678901234567890123456789012345678901234567890123456789");
    journal::EventRecord longest;
    j6.readEvent(0, longest);
    printf("long %zu\n", strlen(longest.text));
    return 0;
}

int main(int argc, char** argv) {
    if (argc == 3 && !strcmp(argv[1], "crc")) {
        printf("%04X\n", p1::crc16(reinterpret_cast<const uint8_t*>(argv[2]), strlen(argv[2])));
        return 0;
    }
    if (argc == 2 && !strcmp(argv[1], "journal")) return journalScenario();
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
                        str(SRC / "testframe.cpp"), str(SRC / "journal.cpp"), "-o", str(cls.binary)], check=True)

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

    def test_journal_scenario(self):
        lines = subprocess.run([str(self.binary), "journal"], capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertEqual(lines, [
            "fresh 1 1 0 0 0",
            "write 1 1",
            "reread 2 5000 20 2",
            "uncommitted 2 5000 2",
            "corrupt 1 16228 1",
            "ring 41 139 32",
            "clock 1",
            "events 100 3 600 1 e600 1 e89 0",
            "long 53",
        ])

    def test_rejects_bad_lengths(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_harness("frame", "3", "1")
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_harness("frame", "104", "1")


if __name__ == "__main__":
    unittest.main()
