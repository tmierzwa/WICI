# SPDX-License-Identifier: MIT
"""Checks of the P1 register table for the S2-LP (bench B) against the DS11896 equations, of the S2-LP
driver against the SPI protocol with a fake bus, and of the bench B board file against the N1 connection table."""

from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "firmware" / "tools"))
import s2lp_p1_registers as s2  # noqa: E402

SPEC = s2.P1


class EquationTests(unittest.TestCase):
    """Encode and decode the P1 parameters with the datasheet equations."""

    def test_synth_word(self):
        word = s2.synth_word(SPEC["carrier_hz"])
        self.assertEqual(word, 0x22C7EFA)
        step = s2.F_XO / 2**19 / 4
        self.assertLessEqual(abs(s2.synth_hz(word) - SPEC["carrier_hz"]), step / 2)

    def test_charge_pump_for_50_mhz_and_low_vco(self):
        # VCO = 4 x 869.525 MHz = 3478 MHz < 3600 MHz, reference 50 MHz: table 37 row "3460 / 50".
        self.assertEqual(s2.charge_pump(SPEC["carrier_hz"]), (0x03, 0))

    def test_data_rate(self):
        exponent, mantissa = s2.data_rate_fields(SPEC["symbol_rate"])
        self.assertEqual((exponent, mantissa), (4, 0x92A7))
        self.assertAlmostEqual(s2.data_rate_hz(exponent, mantissa), 4800, delta=0.5)

    def test_deviation(self):
        exponent, mantissa = s2.deviation_fields(SPEC["deviation_hz"])
        self.assertEqual((exponent, mantissa), (1, 80))
        self.assertAlmostEqual(s2.deviation_hz(exponent, mantissa), 4000, delta=6)

    def test_channel_filter_inside_profile_range(self):
        exponent, mantissa = s2.channel_filter_fields(SPEC["rx_filter_hz"])
        bandwidth = s2.channel_filter_hz(exponent, mantissa)
        self.assertGreaterEqual(bandwidth, 24_000)
        self.assertLessEqual(bandwidth, 32_000)
        # Table 44 at 26 MHz: E = 5, M = 1 is 26.5 kHz; scaled by 25/26.
        self.assertEqual((exponent, mantissa), (5, 1))

    def test_intermediate_frequency(self):
        analog, digital = s2.if_offsets(s2.IF_HZ)
        self.assertAlmostEqual(s2.F_XO / 12 * (analog + 100) / 2**11, 300_000, delta=2_000)
        self.assertAlmostEqual(s2.F_DIG / 12 * (digital + 100) / 2**11, 300_000, delta=2_000)

    def test_rssi_threshold(self):
        self.assertEqual(s2.rssi_threshold(-100) - 146, -100)


class TableTests(unittest.TestCase):
    def setUp(self):
        self.table = {r.name: r for r in s2.build()}

    def test_addresses_unique_and_ordered(self):
        addresses = [r.address for r in s2.build()]
        self.assertEqual(addresses, sorted(set(addresses)))

    def test_packet_format_matches_frame(self):
        # radio.md, "Ramka w eterze": 8 x 0xAA, D3 91 D3 91, LEN = BODY + CRC, chip CRC and whitening off.
        self.assertEqual(self.table["PCKTCTRL6"].value >> 2, 32)
        self.assertEqual(self.table["PCKTCTRL5"].value, 32)  # pairs of bits
        self.assertEqual(self.table["PCKTCTRL3"].value & 0x03, 1)  # pattern 1010
        self.assertEqual(self.table["PCKTCTRL3"].value & 0xF4, 0)  # BASIC, normal RX, MSB first
        self.assertEqual(self.table["PCKTCTRL2"].value, 0x01)  # variable length, no coding
        self.assertEqual(self.table["PCKTCTRL1"].value, 0x00)  # no CRC, no whitening, FIFO source, no FEC
        self.assertEqual(self.table["PCKTCTRL4"].value, 0x00)  # 1-byte LEN, no address
        sync = tuple(self.table[f"SYNC{i}"].value for i in (3, 2, 1, 0))
        self.assertEqual(sync, SPEC["sync_word"])

    def test_modulation_is_2gfsk_bt05(self):
        self.assertEqual(self.table["MOD2"].value >> 4, 0xA)

    def test_digital_divider_on_for_50_mhz(self):
        self.assertEqual(self.table["XO_RCO_CONF1"].value & 0x10, 0)  # PD_CLKDIV = 0
        self.assertEqual(self.table["XO_RCO_CONF0"].value & 0x08, 0)  # REFDIV = 0, D = 1

    def test_header_is_current(self):
        self.assertEqual(s2.HEADER.read_text(encoding="utf-8"), s2.header(s2.build()))


class BoardFileTests(unittest.TestCase):
    """board_bench_b.h against the ESP32-S3 column of hardware/dev-bench/polaczenia.md."""

    NETS = {
        "SPI_SCK": "SPI_SCK", "SPI_MOSI": "SPI_MOSI", "SPI_MISO": "SPI_MISO", "RF_CS": "RADIO_CS",
        "RF_RESET": "RADIO_SDN", "RF_GPIO0": "RADIO_GPIO0", "RF_GPIO1": "RADIO_GPIO1", "RF_GPIO2": "RADIO_GPIO2",
        "RF_GPIO3": "RADIO_GPIO3", "FRAM_CS": "FRAM_CS", "LCD_CS": "DISPLAY_CS", "LCD_EXTCOMIN": "DISPLAY_EXTCOMIN",
        "LCD_DISP": "DISPLAY_DISP", "LED_ALARM": "LED_ALARM", "BUZZER": "BUZZER", "BTN_UP": "BTN_UP",
        "BTN_DOWN": "BTN_DOWN", "BTN_OK": "BTN_OK", "BTN_BACK": "BTN_BACK", "SW_CISZA": "SW_SILENCE",
        "BTN_PREP": "BTN_PREP", "VTEST": "VTEST",
    }

    def test_every_net_on_its_gpio(self):
        board = (ROOT / "firmware" / "src" / "board_bench_b.h").read_text(encoding="utf-8")
        constants = {m.group(1): int(m.group(2)) for m in re.finditer(r"constexpr uint8_t (\w+) = (\d+);", board)}
        table = (ROOT / "hardware" / "dev-bench" / "polaczenia.md").read_text(encoding="utf-8")
        found = {}
        for m in re.finditer(r"^\| (\w+) \| [^|]+ \| [^|]+ \| GPIO(\d+) \(J[56]\.\d+\) \|", table, re.M):
            found[m.group(1)] = int(m.group(2))
        self.assertEqual(set(found), set(self.NETS))
        for net, constant in self.NETS.items():
            with self.subTest(net=net):
                self.assertEqual(constants[constant], found[net])


if __name__ == "__main__":
    unittest.main()


# Atrapa Arduino i SPI: zapisuje bajty z MOSI i stan CS, odpowiada na MISO jak S2-LP (dwa bajty
# statusu, potem rejestry od adresu z drugiego bajtu, z autoinkrementacją).
STUBS = {
    "Arduino.h": r"""
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdio>
constexpr uint8_t OUTPUT = 1, HIGH = 1, LOW = 0;
inline void pinMode(uint8_t, uint8_t) {}
void digitalWrite(uint8_t pin, uint8_t level);
inline void delay(uint32_t) {}
inline void delayMicroseconds(uint32_t) {}
uint32_t micros();
""",
    "SPI.h": r"""
#pragma once
#include "Arduino.h"
constexpr uint8_t MSBFIRST = 1, SPI_MODE0 = 0;
struct SPISettings { SPISettings(uint32_t, uint8_t, uint8_t) {} };
struct SPIClass {
    void beginTransaction(const SPISettings&) {}
    void endTransaction() {}
    uint8_t transfer(uint8_t out);
};
""",
}

SPI_HARNESS = r"""
#include "s2lp.h"
#include <cstring>
uint8_t regs[256];
bool selected = false;
size_t position = 0;
uint8_t header = 0, address = 0;
uint32_t clock = 0;
uint32_t micros() { return clock += 10; }
void digitalWrite(uint8_t pin, uint8_t level) {
    if (pin == 10) {
        if (level == LOW && !selected) position = 0;
        if (level == HIGH && selected) printf("CS\n");
        selected = level == LOW;
    }
}
uint8_t SPIClass::transfer(uint8_t out) {
    uint8_t in = 0;
    if (position == 0) { header = out; in = regs[0x8D]; }
    else if (position == 1) {
        address = out; in = regs[0x8E];
        if (header == 0x80) {
            printf("CMD %02X\n", out);
            if (out == 0x70) regs[0x8E] = 0x01;  // SRES -> READY, XO on
            if (out == 0x67) regs[0x8E] = 0x01;
        }
    } else {
        const uint8_t a = static_cast<uint8_t>(address + position - 2);
        if (header == 0x01) in = regs[a];
        else if (header == 0x00) { regs[a] = out; printf("W %02X %02X\n", a, out); }
    }
    ++position;
    return in;
}
int main() {
    regs[0x8D] = 0x52; regs[0x8E] = 0x07; regs[0xF0] = 0x03; regs[0xF1] = 0x91;
    SPIClass spi;
    s2lp::Radio radio(spi, 10, 9, 1000000);
    radio.begin();
    radio.reset();
    const s2lp::Identity id = radio.identify();
    printf("ID %02X %02X %d %02X %02X %s %d\n", id.partNumber, id.version, id.s2lp, id.status.mcState1,
           id.status.mcState0, s2lp::stateName(radio.status().state()), radio.status().xoOn());
    const s2lp::RegisterValue table[] = {{0x05, 0x62, 0xFF, "SYNT3"}, {0x06, 0x2C, 0xFF, "SYNT2"}};
    s2lp::VerifyResult r = radio.configure(table, 2);
    printf("CONFIG %u %u\n", r.checked, r.mismatches);
    regs[0x06] = 0x00;
    r = radio.verify(table, 2);
    printf("VERIFY %u %s %02X %02X\n", r.mismatches, r.firstName, r.expected, r.actual);
    return 0;
}
"""


def host_compiler():
    for name in ("c++", "g++", "clang++"):
        if shutil.which(name):
            return shutil.which(name)
    return None


@unittest.skipUnless(host_compiler(), "no host C++ compiler")
class DriverTests(unittest.TestCase):
    """s2lp.cpp against the SPI protocol of DS11896 section 9.1, with a fake SPI bus."""

    def test_spi_sequence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, text in STUBS.items():
                (root / name).write_text(text, encoding="utf-8")
            (root / "harness.cpp").write_text(SPI_HARNESS, encoding="utf-8")
            src = ROOT / "firmware" / "src"
            subprocess.run([host_compiler(), "-std=c++17", "-Wall", "-Wextra", "-Werror", f"-I{root}", f"-I{src}",
                            str(root / "harness.cpp"), str(src / "s2lp.cpp"), "-o", str(root / "harness")], check=True)
            out = subprocess.run([str(root / "harness")], capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertEqual(out[0:2], ["CMD 70", "CS"])  # reset ends with SRES
        identity = next(line for line in out if line.startswith("ID"))
        # PARTNUM and VERSION in one burst from 0xF0; status bytes MC_STATE1, MC_STATE0; READY with XO on.
        self.assertEqual(identity, "ID 03 91 1 52 01 READY 1")
        self.assertIn("W 05 62", out)
        self.assertIn("W 06 2C", out)
        self.assertIn("CONFIG 2 0", out)
        self.assertIn("VERIFY 1 SYNT2 2C 00", out)
