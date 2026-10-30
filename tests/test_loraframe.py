# SPDX-License-Identifier: MIT
"""Host checks of the LoRa frame of the station (firmware/src/loraframe.cpp) against a transcription of the
official RNode firmware (framing, split and assembly as on the air) and against the Semtech time-on-air
model of software/reference/obliczenia.py: frames byte by byte for lengths 1-508, assembly of station frames
by the reference and of reference frames (including the third header-only frame at 508 B) by the station,
a differential run on random frame streams, hostile cases, frame and datagram timing, the declared bitrate."""

import math
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "firmware" / "src"
sys.path.insert(0, str(ROOT / "software" / "reference"))
import obliczenia  # noqa: E402

HARNESS = r"""
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include "loraframe.h"

// Wywołania ze skutkami liczone przed printf: kolejność argumentów zależy od kompilatora (GCC, Clang).

static void printHex(const uint8_t* data, size_t length) {
    for (size_t i = 0; i < length; ++i) printf("%02x", data[i]);
}

static std::vector<uint8_t> fromHex(const std::string& text) {
    std::vector<uint8_t> out;
    for (size_t i = 0; i + 1 < text.size(); i += 2) out.push_back(static_cast<uint8_t>(std::stoul(text.substr(i, 2), nullptr, 16)));
    return out;
}

int main() {
    loraframe::Splitter splitter;
    loraframe::Assembler assembler;
    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream in(line);
        std::string command;
        in >> command;
        if (command == "S") {  // S <len> <random hex>: dane (i * 7 + len) & 0xFF, wspólny Splitter
            size_t length;
            std::string randomHex;
            in >> length >> randomHex;
            std::vector<uint8_t> data(length);
            for (size_t i = 0; i < length; ++i) data[i] = static_cast<uint8_t>(i * 7 + length);
            loraframe::Frame frames[2];
            const size_t count = splitter.split(data.data(), length, fromHex(randomHex)[0], frames);
            printf("%zu", count);
            for (size_t i = 0; i < count; ++i) { printf(" "); printHex(frames[i].bytes, frames[i].length); }
            printf("\n");
        } else if (command == "P") {  // P <ms> <frame hex>
            unsigned long ms;
            std::string frameHex;
            in >> ms >> frameHex;
            const std::vector<uint8_t> frame = fromHex(frameHex);
            const loraframe::Outcome outcome = assembler.push(frame.data(), frame.size(), static_cast<uint32_t>(ms));
            if (outcome == loraframe::Outcome::COMPLETE) {
                printf("complete %zu ", assembler.length());
                printHex(assembler.datagram(), assembler.length());
                printf("\n");
            } else {
                printf("%s\n", outcome == loraframe::Outcome::STORED ? "stored" : "ignored");
            }
        } else if (command == "X") {  // X <ms>
            unsigned long ms;
            in >> ms;
            assembler.expire(static_cast<uint32_t>(ms));
            printf("pending %d\n", assembler.pending());
        } else if (command == "R") {
            assembler.reset();
            printf("pending %d\n", assembler.pending());
        } else if (command == "Q") {
            const loraframe::Stats& s = assembler.stats();
            printf("stats %lu %lu %lu %lu\n", static_cast<unsigned long>(s.split_lost), static_cast<unsigned long>(s.header_only),
                   static_cast<unsigned long>(s.assembly_timeout), static_cast<unsigned long>(s.bad_length));
        } else if (command == "T") {  // T <len>
            size_t length;
            in >> length;
            printf("T %zu %zu %lu %lu %lu\n", length, loraframe::frameCount(length), static_cast<unsigned long>(loraframe::airtimeUs(length)),
                   static_cast<unsigned long>(loraframe::airtimeMs(length)), static_cast<unsigned long>(loraframe::reservedTxMs(length)));
        } else if (command == "B") {
            printf("B %lu\n", static_cast<unsigned long>(loraframe::declaredBitrate()));
        } else if (command == "K") {
            printf("K %zu %zu %u\n", loraframe::MAX_DATAGRAM, loraframe::MAX_RAW, lora::PREAMBLE_SYMBOLS);
        } else if (command == "H") {  // H <random hex> <split 0/1> <previous nibble>
            std::string randomHex;
            int split, previous;
            in >> randomHex >> split >> previous;
            printf("%02x\n", loraframe::header(fromHex(randomHex)[0], split != 0, static_cast<uint8_t>(previous)));
        }
    }
    return 0;
}
"""

# Reference: official RNode firmware (framing, split, assembly), shared with the RNode emulator.
sys.path.insert(0, str(ROOT / "firmware" / "tools"))
from rnode_framing import FLAG_SPLIT, MTU, RNodeReceiver, rnode_transmit  # noqa: E402,F401


def compiler():
    for name in ("c++", "g++", "clang++"):
        path = shutil.which(name)
        if path:
            return path
    return None


def pattern(length):
    return bytes((i * 7 + length) & 0xFF for i in range(length))


@unittest.skipUnless(compiler(), "no host C++ compiler")
class LoraFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        (root / "harness.cpp").write_text(HARNESS, encoding="utf-8")
        cls.binary = root / "harness"
        subprocess.run([compiler(), "-std=c++17", "-Wall", "-Wextra", "-Werror", f"-I{SRC}", str(root / "harness.cpp"),
                        str(SRC / "loraframe.cpp"), "-o", str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_script(self, script):
        out = subprocess.run([str(self.binary)], input="\n".join(script) + "\n", capture_output=True, text=True, check=True)
        return out.stdout.splitlines()

    def station_frames(self, length, random_byte=0x35):
        out = self.run_script([f"S {length} {random_byte:02x}"])[0].split()
        return [bytes.fromhex(frame) for frame in out[1:]]

    # --- ramki ---------------------------------------------------------------

    def test_constants(self):
        self.assertEqual(self.run_script(["K"]), ["K 508 492 24"])

    def test_frames_match_rnode_for_every_length(self):
        lines = self.run_script([f"S {length} 35" for length in range(1, 509)])
        for length, line in zip(range(1, 509), lines):
            station = [bytes.fromhex(f) for f in line.split()[1:]]
            reference = rnode_transmit(pattern(length), station[0][0] >> 4)  # the nibble is checked separately
            if length == MTU:
                self.assertEqual(reference[2], station[0][:1], "RNode: third, header-only frame at 508 B")
                reference = reference[:2]  # the station never sends it
            self.assertEqual(station, reference, f"length {length}")
            self.assertEqual(line.split()[0], str(len(station)))
            self.assertTrue(all(len(f) <= 255 for f in station))

    def test_boundary_lengths(self):
        self.assertEqual([len(f) for f in self.station_frames(254)], [255])
        self.assertEqual([len(f) for f in self.station_frames(255)], [255, 2])
        self.assertEqual([len(f) for f in self.station_frames(508)], [255, 255])
        self.assertEqual(self.station_frames(509), [])
        self.assertEqual(self.station_frames(0), [])
        self.assertEqual(self.station_frames(1)[0][0], 0x30, "no split flag, nibble from the random byte")
        self.assertEqual(self.station_frames(300)[0][0], 0x31)

    def test_split_nibble_differs_from_previous_split_datagram(self):
        out = self.run_script(["S 300 35", "S 20 35", "S 300 35", "S 300 35", "S 300 4f", "S 508 4a"])
        heads = [int(line.split()[1][:2], 16) for line in out]
        self.assertEqual(heads, [0x31, 0x30, 0x41, 0x31, 0x41, 0x51])  # a datagram in one frame keeps the random nibble
        splits = [h for h in heads if h & FLAG_SPLIT]
        self.assertTrue(all((a >> 4) != (b >> 4) for a, b in zip(splits, splits[1:])))
        self.assertEqual(self.run_script(["H 35 1 255", "H 35 1 3", "H 3f 1 3", "H f5 1 15", "H 35 0 3", "H 35 1 4"]),
                         ["31", "41", "41", "01", "30", "31"])

    # --- składanie ------------------------------------------------------------

    def test_station_frames_assemble_in_rnode(self):
        for length in (1, 2, 253, 254, 255, 256, 400, 507, 508):
            receiver = RNodeReceiver()
            delivered = [p for f in self.station_frames(length) if (p := receiver.receive(f)) is not None]
            self.assertEqual(delivered, [pattern(length)], f"length {length}")

    def test_rnode_frames_assemble_in_station(self):
        for length in (1, 2, 253, 254, 255, 256, 400, 507, 508):
            frames = rnode_transmit(pattern(length), 9)
            out = self.run_script([f"P {i} {frame.hex()}" for i, frame in enumerate(frames)] + ["Q"])
            complete = [line for line in out if line.startswith("complete")]
            self.assertEqual(complete, [f"complete {length} {pattern(length).hex()}"], f"length {length}")
            if length == MTU:
                self.assertEqual(len(frames), 3)
                self.assertEqual(out[2], "ignored")
                self.assertEqual(out[-1], "stats 0 1 0 0")  # the third frame counted as header-only
            else:
                self.assertEqual(out[-1], "stats 0 0 0 0")

    def test_differential_random_frame_streams(self):
        rng = random.Random(56775)
        for _ in range(200):
            script, receiver, expected = [], RNodeReceiver(), []
            for step in range(rng.randrange(1, 40)):
                header = (rng.randrange(3) << 4) | (rng.random() < 0.7)  # few nibbles: collisions
                frame = bytes([header]) + bytes(rng.randrange(256) for _ in range(rng.randrange(1, 255)))
                script.append(f"P {step} {frame.hex()}")
                packet = receiver.receive(frame)
                if packet is not None:
                    expected.append(f"complete {len(packet)} {packet.hex()}")
            got = [line for line in self.run_script(script) if line.startswith("complete")]
            self.assertEqual(got, expected)

    # --- przypadki wrogie ------------------------------------------------------

    @staticmethod
    def frame(nibble, split, body):
        return bytes([(nibble << 4) | split]) + body

    def test_second_part_without_first_is_a_first_part(self):
        a2 = self.frame(5, 1, b"tail")
        out = self.run_script([f"P 0 {a2.hex()}", "Q"])
        self.assertEqual(out, ["stored", "stats 0 0 0 0"])

    def test_interleaved_senders_deliver_nothing(self):
        a1, a2 = self.frame(1, 1, b"A1"), self.frame(1, 1, b"A2")
        b1, b2 = self.frame(2, 1, b"B1"), self.frame(2, 1, b"B2")
        out = self.run_script([f"P {i} {f.hex()}" for i, f in enumerate((a1, b1, a2, b2))] + ["Q"])
        self.assertEqual(out, ["stored"] * 4 + ["stats 3 0 0 0"])  # the three replaced first parts

    def test_one_byte_and_empty_frames_are_ignored(self):
        a1, a2 = self.frame(4, 1, b"first"), self.frame(4, 1, b"second")
        out = self.run_script([f"P 0 {a1.hex()}", "P 1 31", "P 2 30", "P 3 ", f"P 4 {a2.hex()}", "Q"])
        self.assertEqual(out, ["stored", "ignored", "ignored", "ignored", f"complete 11 {(b'firstsecond').hex()}", "stats 0 3 0 0"])

    def test_changed_nibble_starts_a_new_first_part(self):
        out = self.run_script([f"P 0 {self.frame(1, 1, b'old').hex()}", f"P 1 {self.frame(2, 1, b'new').hex()}",
                               f"P 2 {self.frame(2, 1, b'end').hex()}", "Q"])
        self.assertEqual(out, ["stored", "stored", f"complete 6 {b'newend'.hex()}", "stats 1 0 0 0"])

    def test_unsplit_frame_in_the_middle_drops_the_pending_part(self):
        out = self.run_script([f"P 0 {self.frame(1, 1, b'first').hex()}", f"P 1 {self.frame(1, 0, b'alone').hex()}",
                               f"P 2 {self.frame(1, 1, b'second').hex()}", "R", "Q"])
        self.assertEqual(out, ["stored", f"complete 5 {b'alone'.hex()}", "stored", "pending 0", "stats 1 0 0 0"])

    def test_pending_first_part_expires_one_second_after_its_frame(self):
        first, second = self.frame(3, 1, b"first"), self.frame(3, 1, b"second")
        ok = self.run_script([f"P 100 {first.hex()}", f"P 1099 {second.hex()}", "Q"])
        self.assertEqual(ok, ["stored", f"complete 11 {b'firstsecond'.hex()}", "stats 0 0 0 0"])
        late = self.run_script([f"P 100 {first.hex()}", f"P 1100 {second.hex()}", "X 2099", "X 2100", "Q"])
        self.assertEqual(late, ["stored", "stored", "pending 1", "pending 0", "stats 0 0 2 0"])
        # The age counts from the receive time of the frame, not from the time of the handling.
        self.assertEqual(self.run_script([f"P 0 {first.hex()}", "X 999", "X 1000", "Q"]), ["stored", "pending 1", "pending 0", "stats 0 0 1 0"])

    def test_receive_clock_wraps_around(self):
        first, second = self.frame(3, 1, b"first"), self.frame(3, 1, b"second")
        out = self.run_script([f"P {2 ** 32 - 256} {first.hex()}", f"P 300 {second.hex()}", "Q"])
        self.assertEqual(out[1], f"complete 11 {b'firstsecond'.hex()}")

    def test_header_only_frame_does_not_disturb_a_pending_part(self):
        out = self.run_script([f"P 0 {self.frame(6, 1, b'a').hex()}", f"P 1 {self.frame(7, 1, b'').hex()}",
                               f"P 2 {self.frame(6, 1, b'b').hex()}", "Q"])
        self.assertEqual(out, ["stored", "ignored", f"complete 2 {b'ab'.hex()}", "stats 0 1 0 0"])

    def test_oversize_frame_is_counted_and_ignored(self):
        out = self.run_script([f"P 0 {self.frame(1, 0, bytes(255)).hex()}", "Q"])
        self.assertEqual(out, ["ignored", "stats 0 0 0 1"])

    # --- czas -------------------------------------------------------------------

    def test_air_time_matches_the_model_for_every_length(self):
        lines = self.run_script([f"T {length}" for length in range(0, 510)])
        for length, line in enumerate(lines):
            fields = line.split()
            if not 1 <= length <= 508:
                self.assertEqual(fields[2:], ["0", "0", "0", "0"], f"length {length}")
                continue
            first = min(length, 254)
            frames = [first + 1] + ([length - first + 1] if length > first else [])
            seconds = [obliczenia.lora_frame_seconds(b, 7, preamble_symbols=24) for b in frames]
            self.assertEqual(int(fields[2]), len(frames))
            self.assertEqual(int(fields[3]), round(sum(seconds) * 1e6), f"length {length}")
            self.assertEqual(int(fields[4]), sum(math.ceil(round(s * 1e6) / 1000) + 3 for s in seconds), f"length {length}")
            self.assertEqual(fields[5], fields[4])

    def test_largest_datagram_and_frame_times(self):
        # Plan: a frame of 255 B takes 416 ms in the air (419 ms with the ramp), the largest datagram 838 ms.
        self.assertEqual(self.run_script(["T 254", "T 508"]), ["T 254 1 416000 419 419", "T 508 2 832000 838 838"])

    def test_declared_bitrate_follows_the_model_announce(self):
        announce = obliczenia.p1_datagram(19 + 170 + 16)
        self.assertEqual(announce, 221)
        seconds = obliczenia.lora_frame_seconds(announce + 1, 7, preamble_symbols=24)
        self.assertEqual(self.run_script(["B"]), [f"B {int(8 * announce / seconds)}"])
        self.assertTrue(4000 < int(8 * announce / seconds) < 5000)


if __name__ == "__main__":
    unittest.main()
