# SPDX-License-Identifier: MIT
"""Station Reticulum stack against reference Reticulum (Python), without a radio.

Builds the "host" PlatformIO program (microReticulum port, P1 interface, IFAC, FRAM tables, emulated
P1 link) and runs firmware/tools/rns_interop.py with it, then firmware/tools/rns_osp_node.py (the OSP
node of decision D19 with the computer of the receiving station on a KISS interface). Needs network
access for the pinned stack sources and a Python with Reticulum at e40191b and pyserial, so it runs
only when both are given:

  WICI_PIO=/path/to/pio WICI_RNS_PYTHON=/path/to/venv/bin/python python3 -m unittest tests.test_rns_stack

WICI_RNS_FILL=256 adds the RAM measurement with a full path table (slow: about 3 min more).
"""

import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / "firmware"
PIO = os.environ.get("WICI_PIO")
RNS_PYTHON = os.environ.get("WICI_RNS_PYTHON")


PROGRAM = FIRMWARE / ".pio" / "build" / "host" / "program"


@unittest.skipUnless(PIO and RNS_PYTHON, "WICI_PIO and WICI_RNS_PYTHON not set")
class StackInteropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([PIO, "run", "-e", "host", "-d", str(FIRMWARE)], check=True, capture_output=True)
        program = PROGRAM
        command = [RNS_PYTHON, str(FIRMWARE / "tools" / "rns_interop.py"), "--program", str(program)]
        fill = os.environ.get("WICI_RNS_FILL")
        if fill:
            command += ["--fill", fill]
        run = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        cls.results = json.loads(run.stdout)

    def test_every_check_passed(self):
        failed = [name for name, ok in self.results["checks"].items() if not ok]
        self.assertEqual(failed, [], json.dumps(self.results, indent=2))

    def test_announce_reaches_packet_through_silence_debt(self):
        # Ogłoszenie stacji, ogłoszenie Pythona i pakiet stacji przechodzą przez dług 12 x TX.
        self.assertLess(self.results["announce_to_packet_s"], 60)

    def test_ifac_drops_counted(self):
        status = self.results["station_status"]
        self.assertGreaterEqual(status["ifac_missing"], 1)
        self.assertGreaterEqual(status["ifac_invalid"], 1)


@unittest.skipUnless(PIO and RNS_PYTHON, "WICI_PIO and WICI_RNS_PYTHON not set")
class OspNodeInteropTests(unittest.TestCase):
    """Station in the OSP node configuration with Reticulum (Python) on the computer behind USB (D19)."""

    @classmethod
    def setUpClass(cls):
        subprocess.run([PIO, "run", "-e", "host", "-d", str(FIRMWARE)], check=True, capture_output=True)
        command = [RNS_PYTHON, str(FIRMWARE / "tools" / "rns_osp_node.py"), "--program", str(PROGRAM)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        cls.results = json.loads(run.stdout)

    def test_every_check_passed(self):
        failed = [name for name, ok in self.results["checks"].items() if not ok]
        self.assertEqual(failed, [], json.dumps(self.results, indent=2))

    def test_burst_passes_flow_control(self):
        # Gotowość po każdym pakiecie: kolejka KISS w Pythonie pusta szybciej niż blokada 5 s.
        burst = self.results["burst"]
        self.assertEqual((burst["received"], burst["usb_rns_in"], burst["usb_rx_drop"]), (burst["sent"], burst["sent"], 0))
        self.assertGreaterEqual(burst["usb_ready"], burst["sent"])


if __name__ == "__main__":
    unittest.main()
