# SPDX-License-Identifier: MIT
"""Checks of the P1 register table for the CC1120 against the SWRU295E equations."""

from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "firmware" / "tools"))
import p1_registers as p1  # noqa: E402

# Values of the SmartRF Studio export shipped by TI in swrc253e for the same
# receiver chain (868 MHz, 2-FSK, deviation 3.998 kHz, RX filter 25 kHz).
TI_EXPORT = {
    "SYNC_CFG1": 0x0B, "DCFILT_CFG": 0x1C, "IQIC": 0xC6, "CHAN_BW": 0x08, "MDMCFG0": 0x05,
    "AGC_REF": 0x20, "AGC_CFG1": 0xA9, "AGC_CFG0": 0xCF, "FIFO_CFG": 0x00, "SETTLING_CFG": 0x03,
    "FS_CFG": 0x12, "IF_MIX_CFG": 0x00, "FREQOFF_CFG": 0x22, "FS_DIG1": 0x00, "FS_DIG0": 0x5F,
    "FS_CAL1": 0x40, "FS_CAL0": 0x0E, "FS_DIVTWO": 0x03, "FS_DSM0": 0x33, "FS_DVC0": 0x17,
    "FS_PFD": 0x50, "FS_PRE": 0x6E, "FS_REG_DIV_CML": 0x14, "FS_SPARE": 0xAC, "FS_VCO0": 0xB4,
    "XOSC5": 0x0E, "XOSC1": 0x03, "PA_CFG0": 0x7D, "TOC_CFG": 0x0A,
}


class EquationTests(unittest.TestCase):
    """Encode and decode the P1 parameters with the user's guide equations."""

    def test_symbol_rate_matches_ti_defaults(self):
        exponent, mantissa = p1.symbol_rate_fields(1200)
        self.assertEqual((exponent, mantissa), (4, 0x3A92A))  # reset value of SYMBOL_RATE2..0
        exponent, mantissa = p1.symbol_rate_fields(4800)
        self.assertEqual((exponent, mantissa), (6, 0x3A92A))
        self.assertAlmostEqual(p1.symbol_rate_hz(exponent, mantissa), 4800, delta=0.01)

    def test_deviation_matches_ti_export(self):
        exponent, mantissa = p1.deviation_fields(4000)
        self.assertEqual((exponent, mantissa), (3, 6))
        self.assertAlmostEqual(p1.deviation_hz(exponent, mantissa), 3997.803, places=2)

    def test_filter_bandwidth_table(self):
        self.assertEqual(p1.channel_bandwidth_fields(25_000), (0, 8))
        self.assertEqual(p1.channel_bandwidth_fields(50_000), (0, 4))
        self.assertAlmostEqual(p1.channel_bandwidth_hz(0, 8), 25_000)
        self.assertAlmostEqual(p1.channel_bandwidth_hz(1, 4), 31_250)
        self.assertGreaterEqual(p1.channel_bandwidth_hz(0, 8), 2 * p1.P1["symbol_rate"])

    def test_frequency_word(self):
        self.assertEqual(p1.frequency_word(868_000_000), 0x6C8000)  # TI export FREQ2..0
        word = p1.frequency_word(p1.P1["carrier_hz"])
        self.assertEqual(word, 0x6CB0CD)
        step = p1.F_XOSC / 2**16 / p1.LO_DIVIDER
        self.assertLess(abs(p1.frequency_hz(word) - p1.P1["carrier_hz"]), step / 2)
        self.assertAlmostEqual(p1.frequency_hz(word, 1) - p1.frequency_hz(word), step / 4)

    def test_output_power(self):
        self.assertEqual(p1.power_ramp(13), 61)
        self.assertEqual(p1.power_dbm(61), 13.0)
        self.assertEqual(p1.power_dbm(0x3F), 14.0)
        with self.assertRaises(ValueError):
            p1.power_ramp(15)

    def test_max_debt_matches_model(self):
        sys.path.insert(0, str(ROOT / "software" / "reference"))
        from obliczenia import p1_tx_seconds
        self.assertEqual(p1.max_debt_ms(), round(12 * p1_tx_seconds(600, ramp_ms=2.0) * 1000))
        self.assertEqual(p1.max_debt_ms(), 16228)  # radio.md: about 16 s
        # Stanowisko odczekuje po starcie bez rekordu długu największy dług, jaki samo zapisuje
        # (seria do 1400 ms, rezerwacja z najdłuższych ramek), nie mniejszy niż w modelu.
        measure = (ROOT / "firmware" / "src" / "measure.h").read_text(encoding="utf-8")
        series = int(re.search(r"SERIES_MAX_MS = (\d+);", measure).group(1))
        self.assertIn("MAX_DEBT_MS = SERIES_MAX_MS * 12;", measure)
        self.assertGreaterEqual(series * 12, p1.max_debt_ms())

    def test_low_if_allows_image_compensation(self):
        bandwidth = p1.channel_bandwidth_hz(0, 8)
        f_if = 0x40 * p1.F_XOSC / 2**15  # FREQ_IF_CFG reset value, in Hz
        self.assertGreater(f_if, 2 * bandwidth)
        self.assertLessEqual(f_if + bandwidth / 2, 100_000)


class TableTests(unittest.TestCase):
    """The generated table and header stay consistent with the sources."""

    def setUp(self):
        self.table = {reg.name: reg for reg in p1.build()}

    def test_addresses_unique_and_ordered(self):
        addresses = [reg.address for reg in p1.build()]
        self.assertEqual(addresses, sorted(addresses))
        self.assertEqual(len(addresses), len(set(addresses)))

    def test_profile_fields(self):
        t = self.table
        self.assertEqual([t[f"SYNC{i}"].value for i in (3, 2, 1, 0)], [0xD3, 0x91, 0xD3, 0x91])
        self.assertEqual(t["SYNC_CFG0"].value & 0x1C, 0b101 << 2)  # 32-bit sync word
        self.assertEqual(t["PREAMBLE_CFG1"].value, 0b1010 << 2)  # 8 bytes of 0xAA
        self.assertEqual(t["MODCFG_DEV_E"].value, 0x0B)  # 2-GFSK, DEV_E = 3
        self.assertEqual((t["SYMBOL_RATE2"].value, t["SYMBOL_RATE1"].value, t["SYMBOL_RATE0"].value), (0x63, 0xA9, 0x2A))
        self.assertEqual((t["FREQ2"].value, t["FREQ1"].value, t["FREQ0"].value), (0x6C, 0xB0, 0xCD))
        self.assertEqual(t["PA_CFG2"].value, 0x7D)
        self.assertEqual(t["PKT_CFG1"].value & 0x0C, 0)  # chip CRC off: P1 uses CRC-16/CCITT-FALSE
        self.assertEqual(t["PKT_LEN"].value, 103)
        self.assertEqual(t["FS_CFG"].value & 0x0F, 0b0010)  # 820-960 MHz, LO divider 4
        self.assertEqual(t["AGC_CS_THR"].value, (p1.P1["cca_threshold_dbm"] - p1.RSSI_OFFSET_DB) & 0xFF)

    def test_ti_export_values_kept(self):
        computed_too = {"CHAN_BW", "FS_CFG"}  # derived from P1 and equal to the export
        for name, value in TI_EXPORT.items():
            self.assertEqual(self.table[name].value, value, name)
            if name not in computed_too:
                self.assertEqual(self.table[name].source, "TI", name)

    def test_header_is_current(self):
        self.assertEqual(p1.HEADER.read_text(encoding="utf-8"), p1.header(p1.build()))

    def test_header_lists_every_register_once(self):
        text = p1.HEADER.read_text(encoding="utf-8")
        for reg in p1.build():
            self.assertEqual(text.count(f'"{reg.name}"'), 1, reg.name)
        self.assertIn("constexpr RegisterValue REGISTERS[]", text)
        self.assertIn("SPDX-License-Identifier: MIT", text)


if __name__ == "__main__":
    unittest.main()
