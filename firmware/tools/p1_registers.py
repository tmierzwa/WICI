#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Register table of profile P1 for the CC1120 (dev bench A).

The values come from two sources, named in the ``source`` column of the output:

* ``P1``: computed from the profile parameters in ``docs/spec/radio.md`` with the
  equations of the CC112X user's guide SWRU295E (TI, 2013): symbol rate (eq. 6-9),
  deviation (eq. 1-2), RX filter bandwidth (eq. 10, table 17), RF frequency
  (eq. 26-27), output power (eq. 21), plus the sync word, preamble and packet
  engine fields described in section 8 and chapter 11 of the same document.
* ``TI``: registers whose description reads "use values from SmartRF Studio".
  SmartRF Studio is a Windows-only tool and was not run here; the values are
  taken from the SmartRF Studio export that TI ships in the swrc253e example
  package (``cc112x_easy_link_reg_config.h`` and ``cc112x_serial_mode_reg_config.h``,
  BSD-3-Clause, Copyright (C) 2013 Texas Instruments): 868 MHz, 2-FSK, deviation
  3.998 kHz, RX filter 25 kHz, which is the same receiver chain as P1. Rate
  dependent entries (upsampler, timing offset) come from the 4.8 kbit/s block
  of the serial-mode export.

Run without arguments to print the table as Markdown; ``--write`` regenerates
``firmware/src/p1_registers.h``; ``--check`` fails when that header is stale.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "firmware" / "src" / "p1_registers.h"

F_XOSC = 32_000_000  # Hz, crystal of the CC1120EM-868-915 module
LO_DIVIDER = 4  # FS_CFG.FSD_BANDSELECT = 0010 (820-960 MHz)

# Profile P1 (docs/spec/radio.md, "Profil P1 do prototypu").
P1 = {
    "carrier_hz": 869_525_000,
    "symbol_rate": 4800,  # 2-GFSK: 1 bit per symbol
    "deviation_hz": 4000,
    "rx_filter_hz": 25_000,  # nearest setting inside 24-32 kHz (table 17)
    "tx_power_dbm": 13,
    "preamble_bytes": 8,  # 8 x 0xAA
    "sync_word": (0xD3, 0x91, 0xD3, 0x91),
    "max_packet_bytes": 103,  # LEN + BODY + CRC
    "cca_threshold_dbm": -100,  # initial value, set in T4
    "max_datagram_bytes": 600,
    "chunk_bytes": 86,  # data per fragment
    "fragment_overhead_bytes": 29,  # preamble 8, sync 4, LEN 1, header 14, CRC 2
    "ramp_ms_assumed": 2.0,  # per fragment until measured (software/reference/obliczenia.py)
    "debt_factor": 12,  # silence debt = 12 x reserved TX time
}


def tx_seconds(datagram_bytes: int) -> float:
    """Air time of a datagram in P1 with the assumed ramp, as software/reference/obliczenia.py."""
    fragments = -(-datagram_bytes // P1["chunk_bytes"])
    return (8 * (datagram_bytes + P1["fragment_overhead_bytes"] * fragments) / P1["symbol_rate"]
            + fragments * P1["ramp_ms_assumed"] / 1000)


def max_debt_ms() -> int:
    """Largest possible silence debt: 12 x TX time of a 600 B datagram (radio.md, "Dostęp do kanału")."""
    return int(round(P1["debt_factor"] * tx_seconds(P1["max_datagram_bytes"]) * 1000))

# RSSI offset of the CC1120EM-868-915 as reported by SmartRF Studio for this
# band. It is an assumption until measured on the bench (T4, generator at a
# known level); the CS threshold register below depends on it.
RSSI_OFFSET_DB = -99


# --- SWRU295E equations -----------------------------------------------------

def symbol_rate_fields(rate: float) -> tuple[int, int]:
    """Return (SRATE_E, SRATE_M) for a symbol rate in symbols per second (eq. 8, 9)."""
    scaled = rate * 2**39 / F_XOSC
    exponent = int(math.floor(math.log2(scaled))) - 20
    if exponent <= 0:
        raise ValueError("SRATE_E = 0 is not handled")
    mantissa = int(round(scaled / 2**exponent - 2**20))
    if mantissa == 2**20:
        exponent += 1
        mantissa = 0
    return exponent, mantissa


def symbol_rate_hz(exponent: int, mantissa: int) -> float:
    """Decode the symbol rate (eq. 6, 7)."""
    if exponent == 0:
        return mantissa * F_XOSC / 2**38
    return (2**20 + mantissa) * 2**exponent * F_XOSC / 2**39


def deviation_fields(deviation: float) -> tuple[int, int]:
    """Return (DEV_E, DEV_M) for a deviation in Hz (eq. 1, 2)."""
    scaled = deviation * 2**24 / F_XOSC
    exponent = int(math.floor(math.log2(scaled / 256)))
    if exponent <= 0:
        raise ValueError("DEV_E = 0 is not handled")
    mantissa = int(round(scaled / 2**exponent - 256))
    return exponent, mantissa


def deviation_hz(exponent: int, mantissa: int) -> float:
    """Decode the deviation (eq. 1, 2)."""
    if exponent == 0:
        return F_XOSC * mantissa / 2**23
    return F_XOSC * (256 + mantissa) * 2**exponent / 2**24


def channel_bandwidth_fields(bandwidth: float) -> tuple[int, int]:
    """Return (ADC_CIC_DECFACT, BB_CIC_DECFACT) closest to a filter bandwidth in Hz (eq. 10)."""
    best = None
    for adc, decimation in ((0, 20), (1, 32)):
        limit = 25 if decimation == 20 else 16  # CC1120 ranges in the CHAN_BW description
        for bb in range(1, limit + 1):
            value = F_XOSC / (decimation * bb * 8)
            error = abs(value - bandwidth)
            if best is None or error < best[0]:
                best = (error, adc, bb)
    return best[1], best[2]


def channel_bandwidth_hz(adc: int, bb: int) -> float:
    """Decode the RX filter bandwidth with CHFILT_BYPASS = 0 (eq. 10)."""
    return F_XOSC / ((32 if adc else 20) * bb * 8)


def frequency_word(carrier: float) -> int:
    """Return the 24-bit FREQ word for a carrier in Hz (eq. 26, 27, FREQOFF = 0)."""
    return int(round(carrier * LO_DIVIDER * 2**16 / F_XOSC))


def frequency_hz(word: int, offset: int = 0) -> float:
    """Decode FREQ (unsigned 24 bit) and FREQOFF (signed 16 bit) to a carrier in Hz."""
    return (word * F_XOSC / 2**16 + offset * F_XOSC / 2**18) / LO_DIVIDER


def power_ramp(dbm: float) -> int:
    """Return PA_POWER_RAMP for an output power in dBm (eq. 21)."""
    ramp = int(round(2 * (dbm + 18) - 1))
    if not 3 <= ramp <= 63:
        raise ValueError("PA_POWER_RAMP outside 3..63")
    return ramp


def power_dbm(ramp: int) -> float:
    """Decode PA_POWER_RAMP (eq. 21)."""
    return (ramp + 1) / 2 - 18


def preamble_field(count_bytes: int) -> int:
    """Return PREAMBLE_CFG1.NUM_PREAMBLE for a whole number of preamble bytes."""
    table = {0: 0, 1: 2, 2: 4, 3: 5, 4: 6, 5: 7, 6: 8, 7: 9, 8: 10, 12: 11, 24: 12, 30: 13}
    return table[count_bytes]


def carrier_sense_threshold(dbm: int) -> int:
    """Return AGC_CS_THR (two's complement, 1 dB) for a threshold at the antenna."""
    raw = dbm - RSSI_OFFSET_DB
    if not -128 <= raw <= 127:
        raise ValueError("carrier sense threshold outside the register range")
    return raw & 0xFF


# --- table ------------------------------------------------------------------

@dataclass(frozen=True)
class Register:
    name: str
    address: int
    value: int
    source: str
    note: str
    verify_mask: int = 0xFF


def build() -> list[Register]:
    """Return the P1 register table in address order."""
    srate_e, srate_m = symbol_rate_fields(P1["symbol_rate"])
    dev_e, dev_m = deviation_fields(P1["deviation_hz"])
    adc, bb = channel_bandwidth_fields(P1["rx_filter_hz"])
    freq = frequency_word(P1["carrier_hz"])
    ramp = power_ramp(P1["tx_power_dbm"])
    s3, s2, s1, s0 = P1["sync_word"]
    bw_khz = channel_bandwidth_hz(adc, bb) / 1000
    ti = "SmartRF Studio export in TI swrc253e (868 MHz, 25 kHz, 4 kHz)"
    ti48 = "SmartRF Studio export in TI swrc253e, 4.8 kbit/s block"
    return [
        Register("IOCFG3", 0x0000, 0xB0, "TI", "GPIO3 not wired: analog pad, high impedance"),
        Register("IOCFG2", 0x0001, 0x06, "P1", "GPIO2 (bench D3) = PKT_SYNC_RXTX, packet on air"),
        Register("IOCFG1", 0x0002, 0xB0, "TI", "GPIO1 is the SPI SO line: analog pad, high impedance"),
        Register("IOCFG0", 0x0003, 0x01, "P1", "GPIO0 (bench D2) = RXFIFO_THR_PKT, end of received packet"),
        Register("SYNC3", 0x0004, s3, "P1", "sync word D3 91 D3 91, byte 3"),
        Register("SYNC2", 0x0005, s2, "P1", "sync word byte 2"),
        Register("SYNC1", 0x0006, s1, "P1", "sync word byte 1"),
        Register("SYNC0", 0x0007, s0, "P1", "sync word byte 0"),
        Register("SYNC_CFG1", 0x0008, 0x0B, "TI", "sync threshold 11, no PQT gating"),
        Register("SYNC_CFG0", 0x0009, 0x17, "P1", "32-bit sync word, bit error qualifier off (reset value, explicit)"),
        Register("DEVIATION_M", 0x000A, dev_m, "P1",
                 f"DEV_M = {dev_m}: deviation {deviation_hz(dev_e, dev_m):.1f} Hz (eq. 1)"),
        Register("MODCFG_DEV_E", 0x000B, (0b001 << 3) | dev_e, "P1", f"normal modem, 2-GFSK, DEV_E = {dev_e}"),
        Register("DCFILT_CFG", 0x000C, 0x1C, "TI", "DC filter for the 25 kHz chain"),
        Register("PREAMBLE_CFG1", 0x000D, preamble_field(P1["preamble_bytes"]) << 2, "P1",
                 f"{P1['preamble_bytes']} preamble bytes of 0xAA"),
        Register("PREAMBLE_CFG0", 0x000E, 0x2A, "P1", "preamble detector on, PQT 10 (reset value, explicit)"),
        Register("FREQ_IF_CFG", 0x000F, 0x40, "P1", "low IF 62.5 kHz (reset value, explicit); IQIC needs IF > 2 x BW"),
        Register("IQIC", 0x0010, 0xC6, "TI", "image compensation on"),
        Register("CHAN_BW", 0x0011, (adc << 6) | bb, "P1",
                 f"ADC_CIC_DECFACT = {adc}, BB_CIC_DECFACT = {bb}: RX filter {bw_khz:.1f} kHz (eq. 10)"),
        Register("MDMCFG1", 0x0012, 0x46, "P1", "FIFO mode, NRZ, DVGA 9 dB (reset value, explicit)"),
        Register("MDMCFG0", 0x0013, 0x05, "TI", "data filter off: BW / symbol rate < 10"),
        Register("SYMBOL_RATE2", 0x0014, (srate_e << 4) | (srate_m >> 16), "P1",
                 f"SRATE_E = {srate_e}, SRATE_M = 0x{srate_m:05X}: {symbol_rate_hz(srate_e, srate_m):.1f} Bd (eq. 6)"),
        Register("SYMBOL_RATE1", 0x0015, (srate_m >> 8) & 0xFF, "P1", "SRATE_M[15:8]"),
        Register("SYMBOL_RATE0", 0x0016, srate_m & 0xFF, "P1", "SRATE_M[7:0]"),
        Register("AGC_REF", 0x0017, 0x20, "TI", "AGC reference for 25 kHz"),
        Register("AGC_CS_THR", 0x0018, carrier_sense_threshold(P1["cca_threshold_dbm"]), "P1",
                 f"carrier sense at {P1['cca_threshold_dbm']} dBm with RSSI offset {RSSI_OFFSET_DB} dB (assumed, T4)"),
        Register("AGC_CFG1", 0x001C, 0xA9, "TI", "freeze gain and RSSI after sync, window 32 samples"),
        Register("AGC_CFG0", 0x001D, 0xCF, "TI", "hysteresis 10 dB"),
        Register("FIFO_CFG", 0x001E, 0x00, "TI", "no CRC autoflush, threshold 0"),
        Register("SETTLING_CFG", 0x0020, 0x03, "TI", "no automatic calibration: manual SCAL per errata"),
        Register("FS_CFG", 0x0021, 0x12, "P1", "lock detector on, 820-960 MHz band (LO divider 4)"),
        Register("PKT_CFG2", 0x0026, 0x04, "P1", "CCA = RSSI below threshold, FIFO packet mode (reset value, explicit)"),
        Register("PKT_CFG1", 0x0027, 0x01, "P1", "no whitening, no address, chip CRC off (P1 CRC differs), status appended"),
        Register("PKT_CFG0", 0x0028, 0x00, "P1", "fixed packet length from PKT_LEN (see README: P1 LEN counts BODY only)"),
        Register("RFEND_CFG1", 0x0029, 0x3F, "P1", "stay in RX after a packet (receiver always on), no RX timeout"),
        Register("PA_CFG2", 0x002B, 0x40 | ramp, "P1", f"PA_POWER_RAMP = {ramp}: {power_dbm(ramp):.1f} dBm (eq. 21)"),
        Register("PA_CFG1", 0x002C, 0x56, "TI", "ramp 3 symbols (0.625 ms at 4800 Bd)"),
        Register("PA_CFG0", 0x002D, 0x7D, "TI", f"upsampler P = 32 for 4.8 kBd ({ti48})"),
        Register("PKT_LEN", 0x002E, P1["max_packet_bytes"], "P1", "longest P1 packet LEN + BODY + CRC"),
        Register("IF_MIX_CFG", 0x2F00, 0x00, "TI", ti),
        Register("FREQOFF_CFG", 0x2F01, 0x22, "TI", "frequency offset correction on, loop 1/64 during packet"),
        Register("TOC_CFG", 0x2F02, 0x0A, "TI", f"timing offset blocks 16/32 symbols ({ti48})"),
        Register("FREQ2", 0x2F0C, freq >> 16, "P1",
                 f"FREQ = 0x{freq:06X}: {frequency_hz(freq) / 1e6:.6f} MHz, step {F_XOSC / 2**16 / LO_DIVIDER:.1f} Hz (eq. 26, 27)"),
        Register("FREQ1", 0x2F0D, (freq >> 8) & 0xFF, "P1", "FREQ[15:8]"),
        Register("FREQ0", 0x2F0E, freq & 0xFF, "P1", "FREQ[7:0]"),
        Register("FS_DIG1", 0x2F12, 0x00, "TI", ti),
        Register("FS_DIG0", 0x2F13, 0x5F, "TI", ti),
        Register("FS_CAL1", 0x2F16, 0x40, "TI", ti),
        Register("FS_CAL0", 0x2F17, 0x0E, "TI", ti),
        Register("FS_DIVTWO", 0x2F19, 0x03, "TI", ti),
        Register("FS_DSM0", 0x2F1B, 0x33, "TI", ti),
        Register("FS_DVC0", 0x2F1D, 0x17, "TI", ti),
        Register("FS_PFD", 0x2F1F, 0x50, "TI", ti),
        Register("FS_PRE", 0x2F20, 0x6E, "TI", ti),
        Register("FS_REG_DIV_CML", 0x2F21, 0x14, "TI", ti),
        Register("FS_SPARE", 0x2F22, 0xAC, "TI", ti),
        Register("FS_VCO0", 0x2F27, 0xB4, "TI", ti),
        Register("XOSC5", 0x2F32, 0x0E, "TI", ti),
        Register("XOSC1", 0x2F36, 0x03, "TI", "low phase noise differential buffer; bit 0 is read-only XOSC_STABLE", 0xFE),
    ]


def markdown(table: list[Register]) -> str:
    """Render the table for documentation."""
    lines = ["| Rejestr | Adres | Wartość | Źródło | Uwaga |", "|---|---|---|---|---|"]
    for reg in table:
        lines.append(f"| {reg.name} | 0x{reg.address:04X} | 0x{reg.value:02X} | {reg.source} | {reg.note} |")
    return "\n".join(lines) + "\n"


def header(table: list[Register]) -> str:
    """Render the C++ header consumed by the firmware."""
    out = [
        "// SPDX-License-Identifier: MIT",
        "// Generated by firmware/tools/p1_registers.py; do not edit by hand.",
        "// Profile P1 for the CC1120 (f_xosc = 32 MHz): values marked P1 are computed with",
        "// the SWRU295E equations, values marked TI come from the SmartRF Studio export in",
        "// TI swrc253e (868 MHz, 2-FSK, 25 kHz, 4 kHz). See firmware/README.md.",
        "#pragma once",
        "",
        "#include <stddef.h>",
        "#include <stdint.h>",
        "",
        "#include \"cc1120.h\"",
        "",
        "namespace p1 {",
        "",
        "using cc1120::RegisterValue;  // {address, value, verifyMask, name}",
        "",
        f"constexpr uint32_t F_XOSC_HZ = {F_XOSC};",
        f"constexpr uint8_t LO_DIVIDER = {LO_DIVIDER};",
        f"constexpr uint32_t CARRIER_HZ = {P1['carrier_hz']};",
        f"constexpr uint16_t SYMBOL_RATE = {P1['symbol_rate']};",
        f"constexpr uint16_t DEVIATION_HZ = {P1['deviation_hz']};",
        f"constexpr uint16_t RX_FILTER_HZ = {int(round(channel_bandwidth_hz(*channel_bandwidth_fields(P1['rx_filter_hz']))))};",
        f"constexpr int8_t TX_POWER_DBM = {P1['tx_power_dbm']};",
        f"constexpr int8_t RSSI_OFFSET_DB = {RSSI_OFFSET_DB};  // assumed until measured in T4",
        f"constexpr int8_t CCA_THRESHOLD_DBM = {P1['cca_threshold_dbm']};",
        f"constexpr uint8_t MAX_PACKET_BYTES = {P1['max_packet_bytes']};",
        f"constexpr uint8_t DEBT_FACTOR = {P1['debt_factor']};",
        f"constexpr uint32_t MAX_DEBT_MS = {max_debt_ms()};  // 12 x TX of a 600 B datagram with {P1['ramp_ms_assumed']} ms ramp per fragment",
        "",
        "constexpr RegisterValue REGISTERS[] = {",
    ]
    for reg in table:
        out.append(f"    {{0x{reg.address:04X}, 0x{reg.value:02X}, 0x{reg.verify_mask:02X}, \"{reg.name}\"}},  // {reg.source}: {reg.note}")
    out += [
        "};",
        "constexpr size_t REGISTER_COUNT = sizeof(REGISTERS) / sizeof(REGISTERS[0]);",
        "",
        "}  // namespace p1",
        "",
    ]
    return "\n".join(out)


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
            print(f"{HEADER.relative_to(ROOT)} is stale; run firmware/tools/p1_registers.py --write")
            return 1
        print(f"{HEADER.relative_to(ROOT)} is current ({len(table)} registers)")
        return 0
    print(markdown(table), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
