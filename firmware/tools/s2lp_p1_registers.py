#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Register table of profile P1 for the ST S2-LP (dev bench B, X-NUCLEO-S2868A2).

The values come from three sources, named in the ``source`` column of the output:

* ``P1``: computed from the profile parameters in ``docs/spec/radio.md`` with the
  equations of the S2-LP datasheet DS11896 (Rev 5, ST, 2018): base frequency (eq. 7, 8, 9),
  charge pump (table 37), data rate (eq. 14), deviation (eq. 10), channel filter
  (table 44), intermediate frequency (eq. 15), plus the BASIC packet fields of
  chapter 7 and the register descriptions of table 62. The searches for the
  mantissa and exponent follow the reference code in the ST S2-LP library
  (``S2LP_Radio.cpp``, stm32duino/S2-LP, BSD-3-Clause, Copyright (c) 2017
  STMicroelectronics), so the rounding matches ST's own driver.
* ``ST``: settings that the ST library writes in ``S2LP::begin`` and
  ``S2LPRadioInit`` without a profile parameter behind them (PA Bessel filter,
  SMPS switching frequency, PA power formula).
* ``reset``: register reset values from table 62 written explicitly, so the
  verification read covers them.

Run without arguments to print the table as Markdown; ``--write`` regenerates
``firmware/src/s2lp_p1_registers.h``; ``--check`` fails when that header is stale.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "firmware" / "src" / "s2lp_p1_registers.h"

F_XO = 50_000_000  # Hz, crystal of the X-NUCLEO-S2868A2
DIG_DOMAIN_XTAL_THRESH = 30_000_000  # ST library: above this the digital clock is f_xo / 2
F_DIG = F_XO // 2 if F_XO > DIG_DOMAIN_XTAL_THRESH else F_XO
REFDIV = 1  # XO_RCO_CONF0.REFDIV = 0 (reset value): reference divider off
HIGH_BAND = (825_900_000, 1_056_000_000)  # BS = 0, B = 4
VCO_CENTER_HZ = 3_600_000_000
IF_HZ = 300_000  # recommended IF (section 5.5.5)

# Profile P1 (docs/spec/radio.md, "Profil P1 do prototypu"); same values as firmware/tools/p1_registers.py.
P1 = {
    "carrier_hz": 869_525_000,
    "symbol_rate": 4800,
    "deviation_hz": 4000,
    "rx_filter_hz": 25_000,  # nearest setting inside 24-32 kHz
    "tx_power_dbm": 13,
    "preamble_bytes": 8,  # 8 x 0xAA
    "sync_word": (0xD3, 0x91, 0xD3, 0x91),
    "max_packet_bytes": 103,  # LEN + BODY + CRC
    "cca_threshold_dbm": -100,  # initial value, set in T4
}

# Channel filter table of the ST library (s_vectnBandwidth26M, 100 Hz units at f_dig = 26 MHz),
# index = M + 9 * E; the same values as table 44.
BANDWIDTH_26M = [
    8001, 7951, 7684, 7368, 7051, 6709, 6423, 5867, 5414,
    4509, 4259, 4032, 3808, 3621, 3417, 3254, 2945, 2703,
    2247, 2124, 2015, 1900, 1807, 1706, 1624, 1471, 1350,
    1123, 1062, 1005, 950, 903, 853, 812, 735, 675,
    561, 530, 502, 474, 451, 426, 406, 367, 337,
    280, 265, 251, 237, 226, 213, 203, 184, 169,
    140, 133, 126, 119, 113, 106, 101, 92, 84,
    70, 66, 63, 59, 56, 53, 51, 46, 42,
    35, 33, 31, 30, 28, 27, 25, 23, 21,
    18, 17, 16, 15, 14, 13, 13, 12, 11,
]

MOD_2GFSK_BT05 = 0xA  # MOD2.MOD_TYPE: 2-GFSK, BT = 0.5
PREAMBLE_SEL_1010 = 1  # table 52: 2-(G)FSK pattern 1010, i.e. bytes 0xAA
GPIO_OUT_LP = 0b10  # GPIO_MODE: digital output, low power
GPIO_NIRQ = 0  # table 60
GPIO_SYNC = 15  # table 60: sync word detected
GPIO_GND = 20  # table 60 (reset value of GPIO1-3)


def band_factor(carrier: int) -> int:
    return 4 if HIGH_BAND[0] <= carrier <= HIGH_BAND[1] else 8


def synth_word(carrier: int) -> int:
    """S2LPRadioComputeSynthWord: SYNT = round(f * 2^19 * B * D / f_xo) (eq. 7)."""
    target = (carrier << 19) * band_factor(carrier) * REFDIV
    word = target // F_XO
    below, above = F_XO * word, F_XO * (word + 1)
    return word + 1 if above - target < target - below else word


def synth_hz(word: int, band: int = 4) -> float:
    return F_XO * word / (1 << 19) / band / REFDIV


def charge_pump(carrier: int) -> tuple[int, int]:
    """S2LPRadioSearchWCP: (PLL_CP_ISEL, PLL_PFD_SPLIT_EN) by VCO frequency and reference (table 37)."""
    vco = carrier * band_factor(carrier)
    high_ref = F_XO / REFDIV > DIG_DOMAIN_XTAL_THRESH
    if vco >= VCO_CENTER_HZ:
        return (0x02, 0) if high_ref else (0x01, 1)
    return (0x03, 0) if high_ref else (0x02, 1)


def data_rate_hz(exponent: int, mantissa: int) -> float:
    """Eq. 14 for DATARATE_E < 15."""
    if exponent == 0:
        return F_DIG * mantissa / 2**32
    return F_DIG * (65536 + mantissa) * 2**exponent / 2**33


def data_rate_fields(rate: int) -> tuple[int, int]:
    """S2LPRadioSearchDatarateME: (DATARATE_E, DATARATE_M) nearest to the rate."""
    for exponent in range(12):
        largest = (F_DIG * 0xFFFF) >> 32 if exponent == 0 else (F_DIG * (0xFFFF + 65536)) >> (33 - exponent)
        if rate <= largest:
            break
    if exponent == 0:
        target = rate << 32
        mantissa = target // F_DIG
        below, above = F_DIG * mantissa, F_DIG * (mantissa + 1)
    else:
        target = rate << (33 - exponent)
        mantissa = target // F_DIG - 65536
        below, above = F_DIG * (mantissa + 65536), F_DIG * (mantissa + 1 + 65536)
    if above - target < target - below:
        mantissa += 1
    return exponent, mantissa


def deviation_hz(exponent: int, mantissa: int) -> float:
    """Eq. 10 with B = 4, D = 1 (as S2LPRadioComputeFreqDeviation)."""
    if exponent == 0:
        return F_XO * mantissa / 2**22
    return F_XO * (256 + mantissa) * 2**exponent / 2**23


def deviation_fields(deviation: int) -> tuple[int, int]:
    """S2LPRadioSearchFreqDevME: (FDEV_E, FDEV_M) nearest to the deviation."""
    for exponent in range(12):
        largest = (F_XO * 255) >> 22 if exponent == 0 else (F_XO * (256 + 255)) >> (23 - exponent)
        if deviation < largest:
            break
    if exponent == 0:
        target = deviation << 22
        mantissa = target // F_XO
        below, above = F_XO * mantissa, F_XO * (mantissa + 1)
    else:
        target = deviation << (23 - exponent)
        mantissa = target // F_XO - 256
        below, above = F_XO * (mantissa + 256), F_XO * (mantissa + 1 + 256)
    if above - target < target - below:
        mantissa += 1
    return exponent, mantissa


def channel_filter_hz(exponent: int, mantissa: int) -> float:
    """Table 44 scaled by f_dig / 26 MHz."""
    return 100 * BANDWIDTH_26M[mantissa + 9 * exponent] * F_DIG / 26_000_000


def channel_filter_fields(bandwidth: int) -> tuple[int, int]:
    """(CHFLT_E, CHFLT_M) of the table entry nearest to the bandwidth (S2LPRadioSearchChannelBwME)."""
    index = min(range(len(BANDWIDTH_26M)), key=lambda i: (abs(bandwidth - BANDWIDTH_26M[i] * F_DIG // 260_000), i))
    return index // 9, index % 9


def if_offsets(intermediate: int) -> tuple[int, int]:
    """S2LPRadioComputeIF: (IF_OFFSET_ANA, IF_OFFSET_DIG) for the IF (eq. 15)."""
    analog = ((intermediate << 13) * 3) // F_XO - 100
    digital = ((intermediate << 13) * 3) // F_DIG - 100
    return analog, digital


def pa_level(dbm: int) -> int:
    """S2LPRadioSetPALeveldBm: PA_LEVEL = 29 - 2 x dBm (ST library approximation, to be measured)."""
    return 1 if dbm > 14 else 29 - 2 * dbm


def rssi_threshold(dbm: int) -> int:
    """RSSI_TH in dBm = RSSI_TH - 146 (table 62)."""
    return dbm + 146


@dataclass(frozen=True)
class Register:
    address: int
    name: str
    value: int
    source: str
    note: str
    verify_mask: int = 0xFF


def build() -> list[Register]:
    carrier = P1["carrier_hz"]
    word = synth_word(carrier)
    cp_isel, pfd_split = charge_pump(carrier)
    bs = 0 if band_factor(carrier) == 4 else 1
    dr_e, dr_m = data_rate_fields(P1["symbol_rate"])
    fdev_e, fdev_m = deviation_fields(P1["deviation_hz"])
    bw_e, bw_m = channel_filter_fields(P1["rx_filter_hz"])
    if_ana, if_dig = if_offsets(IF_HZ)
    preamble_pairs = 4 * P1["preamble_bytes"]  # pairs of '10'
    sync = P1["sync_word"]
    regs = [
        Register(0x00, "GPIO0_CONF", (GPIO_NIRQ << 3) | GPIO_OUT_LP, "P1",
                 "GPIO0 (ESP32-S3 GPIO14, J11) = nIRQ, active low; no interrupt unmasked yet"),
        Register(0x01, "GPIO1_CONF", (GPIO_GND << 3) | GPIO_OUT_LP, "reset", "GPIO1 (GPIO21) = digital GND"),
        Register(0x02, "GPIO2_CONF", (GPIO_SYNC << 3) | GPIO_OUT_LP, "P1",
                 "GPIO2 (ESP32-S3 GPIO4, J11) = sync word detected, as IOCFG2 on bench A"),
        Register(0x03, "GPIO3_CONF", (GPIO_GND << 3) | GPIO_OUT_LP, "reset", "GPIO3 (GPIO42) = digital GND"),
        Register(0x05, "SYNT3", (cp_isel << 5) | (bs << 4) | ((word >> 24) & 0x0F), "P1",
                 f"PLL_CP_ISEL = {cp_isel} (VCO {carrier * 4 / 1e6:.0f} MHz < 3600, f_xo 50 MHz, table 37), "
                 f"BS = {bs} (B = 4), SYNT[27:24]"),
        Register(0x06, "SYNT2", (word >> 16) & 0xFF, "P1",
                 f"SYNT = 0x{word:07X}: {synth_hz(word) / 1e6:.6f} MHz, step {F_XO / 2**19 / 4:.1f} Hz (eq. 7)"),
        Register(0x07, "SYNT1", (word >> 8) & 0xFF, "P1", "SYNT[15:8]"),
        Register(0x08, "SYNT0", word & 0xFF, "P1", "SYNT[7:0]"),
        Register(0x09, "IF_OFFSET_ANA", if_ana, "P1", f"IF 300 kHz at f_xo 50 MHz (eq. 15; reset value is for 26 MHz)"),
        Register(0x0A, "IF_OFFSET_DIG", if_dig, "P1", "IF 300 kHz at f_dig 25 MHz (eq. 15)"),
        Register(0x0D, "CHNUM", 0x00, "reset", "channel 0: carrier = base frequency"),
        Register(0x0E, "MOD4", dr_m >> 8, "P1",
                 f"DATARATE_M = 0x{dr_m:04X}, DATARATE_E = {dr_e}: {data_rate_hz(dr_e, dr_m):.1f} Bd (eq. 14)"),
        Register(0x0F, "MOD3", dr_m & 0xFF, "P1", "DATARATE_M[7:0]"),
        Register(0x10, "MOD2", (MOD_2GFSK_BT05 << 4) | dr_e, "P1", "2-GFSK BT 0.5, DATARATE_E"),
        Register(0x11, "MOD1", fdev_e, "P1",
                 f"no PA or frequency interpolation, CONST_MAP 0 (bit 1 = +FDEV), FDEV_E = {fdev_e}"),
        Register(0x12, "MOD0", fdev_m, "P1", f"FDEV_M = {fdev_m}: deviation {deviation_hz(fdev_e, fdev_m):.1f} Hz (eq. 10)"),
        Register(0x13, "CHFLT", (bw_m << 4) | bw_e, "P1",
                 f"CHFLT_M = {bw_m}, CHFLT_E = {bw_e}: RX filter {channel_filter_hz(bw_e, bw_m):.0f} Hz (table 44 x 25/26)"),
        Register(0x18, "RSSI_TH", rssi_threshold(P1["cca_threshold_dbm"]), "P1",
                 f"carrier sense at {P1['cca_threshold_dbm']} dBm (RSSI_TH - 146; offset not measured, T4)"),
        Register(0x2B, "PCKTCTRL6", (32 << 2) | (preamble_pairs >> 8), "P1", "32-bit sync word, PREAMBLE_LEN[9:8]"),
        Register(0x2C, "PCKTCTRL5", preamble_pairs & 0xFF, "P1",
                 f"{preamble_pairs} preamble pairs = {P1['preamble_bytes']} bytes"),
        Register(0x2D, "PCKTCTRL4", 0x00, "P1", "1-byte length field, no address field"),
        Register(0x2E, "PCKTCTRL3", PREAMBLE_SEL_1010, "P1",
                 "BASIC packet, normal RX mode (reset value 0x20 is direct through GPIO), MSB first, preamble 1010 = 0xAA"),
        Register(0x2F, "PCKTCTRL2", 0x01, "P1", "variable length: LEN = payload = BODY + CRC (radio.md, F79); no Manchester, no 3-of-6"),
        Register(0x30, "PCKTCTRL1", 0x00, "P1",
                 "chip CRC off (P1 CRC by software), no whitening, TX from FIFO (reset value 0x2C sends PN9), no FEC"),
        Register(0x31, "PCKTLEN1", 0x00, "P1", "TX length MSB"),
        Register(0x32, "PCKTLEN0", P1["max_packet_bytes"] - 1, "P1", "TX length: longest BODY + CRC; the P1 driver sets it per packet"),
        Register(0x33, "SYNC3", sync[0], "P1", "sync word D3 91 D3 91, byte order on air to be checked against bench A"),
        Register(0x34, "SYNC2", sync[1], "P1", "sync word byte 2"),
        Register(0x35, "SYNC1", sync[2], "P1", "sync word byte 1"),
        Register(0x36, "SYNC0", sync[3], "P1", "sync word byte 0"),
        Register(0x40, "PCKT_FLT_OPTIONS", 0x40, "reset", "no address filters, CRC filter off"),
        Register(0x61, "PA_POWER1", pa_level(P1["tx_power_dbm"]), "ST",
                 f"PA level for slot 1 (index 7): 29 - 2 x {P1['tx_power_dbm']} dBm (ST library formula; measure in T4)"),
        Register(0x62, "PA_POWER0", 0x07, "ST", "PA_MAXDBM off, no ramp, DIG_SMOOTH off (FSK), PA_LEVEL_MAX_IDX = 7"),
        Register(0x63, "PA_CONFIG1", 0x01, "ST", "FIR off for FSK (reset 0x03 with FIR_EN cleared)"),
        Register(0x64, "PA_CONFIG0", 0x88, "ST", "PA Bessel filter 12.5 kHz for data rate < 16 kbps (reset 0x8A, PA_FC = 0)"),
        Register(0x65, "SYNTH_CONFIG2", 0xD0 | (pfd_split << 2), "P1", f"PLL_PFD_SPLIT_EN = {pfd_split} (table 37)"),
        Register(0x6C, "XO_RCO_CONF1", 0x45, "reset", "PD_CLKDIV = 0: digital clock f_xo / 2 = 25 MHz, needed for 50 MHz"),
        Register(0x6D, "XO_RCO_CONF0", 0x30, "reset", "REFDIV = 0: reference divider off (D = 1)"),
        Register(0x76, "PM_CONF3", 0x90, "ST", "SMPS rate multiplier on, KRM = 0x1000: 3.125 MHz (S2LP::begin)"),
    ]
    return sorted(regs, key=lambda r: r.address)


def markdown(table: list[Register]) -> str:
    rows = ["| Rejestr | Adres | Wartość | Źródło | Uwagi |", "|---|---|---|---|---|"]
    for r in table:
        rows.append(f"| {r.name} | 0x{r.address:02X} | 0x{r.value:02X} | {r.source} | {r.note} |")
    return "\n".join(rows) + "\n"


def header(table: list[Register]) -> str:
    carrier = P1["carrier_hz"]
    lines = [
        "// SPDX-License-Identifier: MIT",
        "// Generated by firmware/tools/s2lp_p1_registers.py; do not edit by hand.",
        "// Profile P1 for the S2-LP on the X-NUCLEO-S2868A2 (f_xo = 50 MHz, f_dig = 25 MHz): values marked P1",
        "// are computed with the DS11896 equations and the ST library searches, ST values come from the",
        "// ST S2-LP library init, reset values are written explicitly. See firmware/README.md.",
        "#pragma once",
        "",
        "#include <stddef.h>",
        "#include <stdint.h>",
        "",
        '#include "s2lp.h"',
        "",
        "namespace p1s2 {",
        "",
        "using s2lp::RegisterValue;  // {address, value, verifyMask, name}",
        "",
        f"constexpr uint32_t F_XO_HZ = {F_XO};",
        f"constexpr uint8_t BAND_FACTOR = {band_factor(carrier)};",
        f"constexpr uint8_t REF_DIVIDER = {REFDIV};",
        f"constexpr uint32_t CARRIER_HZ = {carrier};",
        f"constexpr uint16_t SYMBOL_RATE = {P1['symbol_rate']};",
        f"constexpr uint16_t DEVIATION_HZ = {P1['deviation_hz']};",
        f"constexpr uint16_t RX_FILTER_HZ = {round(channel_filter_hz(*channel_filter_fields(P1['rx_filter_hz'])))};",
        f"constexpr int8_t TX_POWER_DBM = {P1['tx_power_dbm']};",
        f"constexpr uint8_t MAX_PACKET_BYTES = {P1['max_packet_bytes']};",
        "",
        "constexpr RegisterValue REGISTERS[] = {",
    ]
    for r in table:
        lines.append(f'    {{0x{r.address:02X}, 0x{r.value:02X}, 0x{r.verify_mask:02X}, "{r.name}"}},  // {r.source}: {r.note}')
    lines += [
        "};",
        "constexpr size_t REGISTER_COUNT = sizeof(REGISTERS) / sizeof(REGISTERS[0]);",
        "",
        "}  // namespace p1s2",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help=f"write {HEADER.relative_to(ROOT)}")
    parser.add_argument("--check", action="store_true", help="exit 1 when the header is stale")
    args = parser.parse_args()
    table = build()
    text = header(table)
    if args.write:
        HEADER.write_text(text, encoding="utf-8")
        print(f"wrote {HEADER.relative_to(ROOT)} ({len(table)} registers)")
        return 0
    if args.check:
        current = HEADER.read_text(encoding="utf-8") if HEADER.exists() else ""
        if current != text:
            print(f"{HEADER.relative_to(ROOT)} is stale; run firmware/tools/s2lp_p1_registers.py --write")
            return 1
        print(f"{HEADER.relative_to(ROOT)} is current ({len(table)} registers)")
        return 0
    print(markdown(table), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
