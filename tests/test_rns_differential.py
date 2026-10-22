# SPDX-License-Identifier: MIT
"""Station Reticulum core against Reticulum in Python on the same traffic (differential transport trial).

Builds the core check program as tests/test_rnscore.py does (sanitizers) and runs
firmware/tools/rns_differential.py with a Python that has Reticulum at the pinned commit: the same
announces, path requests, packets in transport, proofs and packets for the station, and mutated copies,
go to the core and to Reticulum acting as the same station; both must transmit the same packets and
keep the same paths (firmware/reticulum-core.md, acceptance criterion 2). Skipped without
WICI_RNS_PYTHON; the stack sources are needed as for tests/test_rnscore.py (WICI_RNS_SANITIZE=1 fetches them).

  WICI_RNS_PYTHON=/path/to/venv/bin/python python3 -m unittest tests.test_rns_differential -v
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "firmware" / "tools" / "rns_differential.py"
RNS_PYTHON = os.environ.get("WICI_RNS_PYTHON")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_rnscore  # noqa: E402


@unittest.skipUnless(RNS_PYTHON, "WICI_RNS_PYTHON not set")
class DifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_rnscore.CoreTests.setUpClass()   # kompilator i źródła stosu jak w test_rnscore (albo pominięcie)
        cls.core = test_rnscore.CoreTests

    @classmethod
    def tearDownClass(cls):
        cls.core.tearDownClass()

    def trial(self, seed: int, mutations: int):
        run = subprocess.run([RNS_PYTHON, "-I", str(TOOL), "--check", str(self.core.binary), "--seed", str(seed),
                              "--mutations", str(mutations)], capture_output=True, text=True, timeout=900, cwd=tempfile.gettempdir())
        lines = [line for line in run.stdout.splitlines() if line.startswith("{")]
        self.assertTrue(lines, run.stderr[-4000:])
        result = json.loads(lines[-1])
        self.assertEqual(result["differences"], [], json.dumps(result["differences"][:3], indent=1)[:6000])
        self.assertEqual(run.returncode, 0, run.stderr[-4000:])

    def test_same_traffic_same_decisions(self):
        self.trial(seed=1, mutations=64)

    def test_mutated_traffic_other_seed(self):
        self.trial(seed=2, mutations=64)
