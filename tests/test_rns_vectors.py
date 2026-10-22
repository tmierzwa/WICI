# SPDX-License-Identifier: MIT
"""Test vectors for the station Reticulum core (tests/vectors/reticulum.json).

The vectors are made by reference Reticulum in Python at the pinned commit (firmware/tools/rns_vectors.py).
Without Reticulum this test only checks the file's shape and pin; with WICI_RNS_PYTHON (a Python with
Reticulum at e40191b, as in the CI interop job) it regenerates the vectors and requires the committed
file to match byte for byte, so the file cannot drift from what the reference implementation computes.

  WICI_RNS_PYTHON=/path/to/venv/bin/python python3 -m unittest tests.test_rns_vectors
"""

import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "tests" / "vectors" / "reticulum.json"
TOOL = ROOT / "firmware" / "tools" / "rns_vectors.py"
RNS_PYTHON = os.environ.get("WICI_RNS_PYTHON")


class VectorFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vectors = json.loads(VECTORS.read_text())

    def test_pinned_source(self):
        self.assertEqual(self.vectors["source"],
                         {"reticulum": "1.5.5", "commit": "e40191b3d193b46b7f2d8a44424a594cd758839b",
                          "tool": "firmware/tools/rns_vectors.py"})

    def test_shape(self):
        for ident in self.vectors["identity"]:
            self.assertEqual(len(bytes.fromhex(ident["private_key"])), 64)
            self.assertEqual(len(bytes.fromhex(ident["public_key"])), 64)
            self.assertEqual(len(bytes.fromhex(ident["hash"])), 16)
            for s in ident["signatures"]:
                self.assertEqual(len(bytes.fromhex(s["signature"])), 64)
                # Wzorzec: podpis poprawny przyjęty, zmieniona treść i podpis z S + L odrzucone.
                self.assertEqual((s["valid"], s["tampered_valid"], s["non_canonical_valid"]), (True, False, False))
        for t in self.vectors["token"]:
            self.assertEqual(t["decrypted"], t["plaintext"])
        # Wzorzec przyjmuje tylko dopełnienie 0 i niespójne bajty dopełnienia (nie sprawdza ich) oraz
        # niekanoniczne kodowania klucza efemerycznego (redukuje je); klucze niskiego rzędu odrzuca.
        accepted = {t["name"] for t in self.vectors["crafted_token"] if t["decrypted"] is not None}
        self.assertEqual(accepted, {"valid_hmac_padding_zero", "valid_hmac_padding_inconsistent",
                                    "ephemeral_non_canonical_p_plus_9", "ephemeral_non_canonical_high_bit",
                                    "ephemeral_non_canonical_all_ones"})
        self.assertEqual(sum(t["name"].startswith("ephemeral_low_order_") for t in self.vectors["crafted_token"]), 7)
        for p in self.vectors["packet"]:
            self.assertIn("header_1", p)

    @unittest.skipUnless(RNS_PYTHON, "WICI_RNS_PYTHON not set")
    def test_matches_reference_implementation(self):
        fresh = subprocess.run([RNS_PYTHON, str(TOOL)], check=True, capture_output=True, text=True).stdout
        self.assertEqual(fresh, VECTORS.read_text(), "regenerate: python firmware/tools/rns_vectors.py > tests/vectors/reticulum.json")


if __name__ == "__main__":
    unittest.main()
