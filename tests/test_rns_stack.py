# SPDX-License-Identifier: MIT
"""Station Reticulum stack against reference Reticulum (Python), without a radio.

Builds the "host" PlatformIO program (microReticulum port, P1 interface, IFAC, FRAM tables, emulated
P1 link) and runs firmware/tools/rns_interop.py with it. Needs network access for the pinned stack
sources and a Python with Reticulum at e40191b, so it runs only when both are given:

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


@unittest.skipUnless(PIO and RNS_PYTHON, "WICI_PIO and WICI_RNS_PYTHON not set")
class StackInteropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([PIO, "run", "-e", "host", "-d", str(FIRMWARE)], check=True, capture_output=True)
        program = FIRMWARE / ".pio" / "build" / "host" / "program"
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


if __name__ == "__main__":
    unittest.main()
