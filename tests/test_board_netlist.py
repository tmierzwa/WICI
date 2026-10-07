# SPDX-License-Identifier: MIT
"""Board files of bench-n1 and bench-b against the KiCad netlist of carrier N1.

Each GPIO constant in firmware/src/board_bench_n1.h and board_bench_b.h is traced
from the carrier net through the connector pin to the MCU pin. The header pinouts
below are typed in from the manufacturers' documents, independently of
hardware/dev-bench/tools/design.py, so an error in the generator is caught too:
nRF52840-DK PCA10056 user guide "Arduino signals routing" (also the Adafruit core
variant pca10056), ESP32-S3-DevKitC-1 user guide v1.1, headers J1 and J3.
"""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NETLIST = ROOT / "hardware" / "dev-bench" / "checks" / "netlist.xml"


def p(port, pin):
    """nRF52840 GPIO number as in the Adafruit core: P0.xx = xx, P1.xx = 32 + xx."""
    return 32 * port + pin


# Carrier connectors J2 (A0-A5), J3 (D0-D7), J4 (D8-SCL) on the Arduino Uno R3 header of the DK.
NRF_DK = {
    ("J2", 1): p(0, 3), ("J2", 2): p(0, 4), ("J2", 3): p(0, 28), ("J2", 4): p(0, 29), ("J2", 5): p(0, 30),
    ("J2", 6): p(0, 31),
    **{("J3", i + 1): p(1, 1 + i) for i in range(8)},                      # D0-D7 = P1.01-P1.08
    ("J4", 1): p(1, 10), ("J4", 2): p(1, 11), ("J4", 3): p(1, 12), ("J4", 4): p(1, 13),  # D8-D11
    ("J4", 5): p(1, 14), ("J4", 6): p(1, 15), ("J4", 8): p(0, 2), ("J4", 9): p(0, 26),   # D12, D13, AREF, SDA
    ("J4", 10): p(0, 27),                                                   # SCL
}

# Carrier sockets J5 = DevKitC J1, J6 = DevKitC J3, pin 1 at the antenna end; None = power or no GPIO.
DEVKIT_J1 = [None, None, None, 4, 5, 6, 7, 15, 16, 17, 18, 8, 3, 46, 9, 10, 11, 12, 13, 14, None, None]
DEVKIT_J3 = [None, 43, 44, 1, 2, 42, 41, 40, 39, 38, 37, 36, 35, 0, 45, 48, 47, 21, 20, 19, None, None]
ESP_DEVKIT = {**{("J5", i + 1): g for i, g in enumerate(DEVKIT_J1) if g is not None},
              **{("J6", i + 1): g for i, g in enumerate(DEVKIT_J3) if g is not None}}

# Board-file constant -> carrier net.
NETS = {
    "SPI_SCK": "SPI_SCK", "SPI_MOSI": "SPI_MOSI", "SPI_MISO": "SPI_MISO", "RADIO_CS": "RF_CS",
    "RADIO_GPIO0": "RF_GPIO0", "RADIO_GPIO1": "RF_GPIO1", "RADIO_GPIO2": "RF_GPIO2", "RADIO_GPIO3": "RF_GPIO3",
    "FRAM_CS": "FRAM_CS", "DISPLAY_CS": "LCD_CS", "DISPLAY_EXTCOMIN": "LCD_EXTCOMIN", "DISPLAY_DISP": "LCD_DISP",
    "LED_ALARM": "LED_ALARM", "BUZZER": "BUZZER", "BTN_UP": "BTN_UP", "BTN_DOWN": "BTN_DOWN", "BTN_OK": "BTN_OK",
    "BTN_BACK": "BTN_BACK", "SW_SILENCE": "SW_CISZA", "BTN_PREP": "BTN_PREP", "VTEST": "VTEST",
    "RADIO_RESET": "RF_RESET", "RADIO_SDN": "RF_RESET",
}


def netlist():
    """Net name -> set of (ref, pin); nets joined by a 33 ohm series resistor are merged."""
    root = ET.parse(NETLIST).getroot()
    values = {c.get("ref"): c.findtext("value") for c in root.iter("comp")}
    nets = {}
    for net in root.iter("net"):
        nets[net.get("name").lstrip("/")] = {(n.get("ref"), int(n.get("pin"))) for n in net.iter("node")}
    for ref, value in values.items():
        if value == "33R":
            a, b = (name for name, nodes in nets.items() if any(r == ref for r, _ in nodes))
            main, other = sorted((a, b), key=len)  # SPI_SCK with SPI_SCK_DK or SPI_SCK_DEVKIT
            nets[main] |= nets.pop(other)
    return nets


def constants(header):
    text = (ROOT / "firmware" / "src" / header).read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"constexpr uint8_t (\w+) = ([^;]+);", text):
        expr = m.group(2).strip()
        if re.fullmatch(r"(32 \+ )?\d+", expr):
            out[m.group(1)] = eval(expr)  # only "n" or "32 + n"
    return out


class BoardNetlistTests(unittest.TestCase):
    def check(self, header, pinout):
        nets = netlist()
        found = constants(header)
        checked = 0
        for name, net in NETS.items():
            if name not in found:
                continue
            with self.subTest(header=header, constant=name):
                gpios = {pinout[node] for node in nets[net] if node in pinout}
                self.assertEqual(gpios, {found[name]}, f"{net}: {sorted(nets[net])}")
                checked += 1
        return checked

    def test_bench_n1_on_nrf52840_dk(self):
        self.assertEqual(self.check("board_bench_n1.h", NRF_DK), 21)

    def test_bench_b_on_esp32_s3_devkitc(self):
        self.assertEqual(self.check("board_bench_b.h", ESP_DEVKIT), 22)

    def test_no_signal_on_strapping_usb_uart_or_psram_pins(self):
        nets = netlist()
        used = {node for name, nodes in nets.items() if not name.startswith("unconnected") for node in nodes}
        forbidden = {0, 3, 45, 46, 19, 20, 43, 44, 35, 36, 37, 38, 47, 48}
        for node, gpio in ESP_DEVKIT.items():
            with self.subTest(pin=node, gpio=gpio):
                self.assertFalse(gpio in forbidden and node in used)


if __name__ == "__main__":
    unittest.main()
