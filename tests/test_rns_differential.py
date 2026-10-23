# SPDX-License-Identifier: MIT
"""Station Reticulum core against Reticulum in Python on the same traffic (differential transport trial).

Builds the core check program as tests/test_rnscore.py does (sanitizers) and runs
firmware/tools/rns_differential.py with a Python that has Reticulum at the pinned commit: the same
announces, path requests, packets in transport, proofs and packets for the station, and mutated copies,
go to the core and to Reticulum acting as the same station; both must transmit the same packets and
keep the same paths (firmware/reticulum-core.md, acceptance criterion 2). Skipped without
WICI_RNS_PYTHON; the stack sources are needed as for tests/test_rnscore.py (WICI_RNS_SANITIZE=1 fetches them).

GeneratorTrafficTests: the traffic generator of the hostile trial (tests/native/rns_stress.cpp, built as in
tests/test_rns_hostile.py with the station core) writes its datagrams (--dump), and Reticulum in Python checks
that the unmutated ones are valid (rns_differential.py --stress-dump): IFAC, unpacking, announce signatures,
decryption and proofs. The same check stays when the generator moves to the core primitives (stage R6-2).

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
import test_rns_hostile  # noqa: E402


@unittest.skipUnless(RNS_PYTHON, "WICI_RNS_PYTHON not set")
class DifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_rnscore.CoreTests.setUpClass()   # kompilator i źródła stosu jak w test_rnscore (albo pominięcie)
        cls.core = test_rnscore.CoreTests

    @classmethod
    def tearDownClass(cls):
        cls.core.tearDownClass()

    def trial(self, seed: int, mutations: int, interfaces: int = 1):
        run = subprocess.run([RNS_PYTHON, "-I", str(TOOL), "--check", str(self.core.binary), "--seed", str(seed),
                              "--mutations", str(mutations), "--interfaces", str(interfaces)],
                             capture_output=True, text=True, timeout=900, cwd=tempfile.gettempdir())
        lines = [line for line in run.stdout.splitlines() if line.startswith("{")]
        self.assertTrue(lines, run.stderr[-4000:])
        result = json.loads(lines[-1])
        self.assertEqual(result["differences"], [], json.dumps(result["differences"][:3], indent=1)[:6000])
        self.assertEqual(run.returncode, 0, run.stderr[-4000:])

    def test_same_traffic_same_decisions(self):
        self.trial(seed=1, mutations=64)

    def test_mutated_traffic_other_seed(self):
        self.trial(seed=2, mutations=96)

    def test_two_interfaces(self):
        # Węzeł stanowiska (etap R4): drugi interfejs (USB) po obu stronach; pakiety z interfejsem nadania,
        # trasy z interfejsem ogłoszenia.
        self.trial(seed=3, mutations=96, interfaces=2)


@unittest.skipUnless(RNS_PYTHON, "WICI_RNS_PYTHON not set")
class GeneratorTrafficTests(unittest.TestCase):
    # Przebiegi jak w tests/test_rns_hostile.py: ruch przez tygodnie, ruch z mutacjami (sprawdzane tylko
    # niezmutowane datagramy) i próby regresji z poprawnymi ogłoszeniami, zapytaniami i żądaniami łącza.
    RUNS = [("--seed", 11, "--events", 2500, "--long-jumps"), ("--seed", 21, "--events", 1500, "--mutate", 30),
            ("--defect", "held-announce", "--events", 0), ("--defect", "link-mtu", "--events", 0)]

    @classmethod
    def setUpClass(cls):
        test_rns_hostile.CoreHostileStackTests.setUpClass()   # kompilator i źródła stosu (albo pominięcie)
        cls.hostile = test_rns_hostile.CoreHostileStackTests

    @classmethod
    def tearDownClass(cls):
        cls.hostile.tearDownClass()

    def test_unmutated_traffic_is_valid_reticulum(self):
        for run in self.RUNS:
            with self.subTest(run=run), tempfile.TemporaryDirectory() as folder:
                dump = Path(folder) / "dump.jsonl"
                station = test_rns_hostile.Station(self.hostile.binary, Path(folder))
                code, outcome, report, stderr = station.run(*run, "--dump", dump)
                self.assertIsNone(report, report)
                self.assertEqual(outcome.get("result"), "ok", stderr[-2000:])
                check = subprocess.run([RNS_PYTHON, "-I", str(TOOL), "--stress-dump", str(dump)], capture_output=True,
                                       text=True, timeout=600, cwd=tempfile.gettempdir())
                lines = [line for line in check.stdout.splitlines() if line.startswith("{")]
                self.assertTrue(lines, check.stderr[-4000:])
                result = json.loads(lines[-1])
                self.assertEqual(result["problems"], [], json.dumps(result["problems"][:3], indent=1))
                self.assertGreater(result["checked"], 0, result)
                self.assertEqual(check.returncode, 0, check.stderr[-4000:])
