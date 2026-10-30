# SPDX-License-Identifier: MIT
"""firmware/tools/rnode_trial.py without Reticulum and without hardware: sizes, marker, criteria of step 4 point 2.

The roles themselves run against the RNode emulator and the host program in tests/test_rns_stack_lora.py."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "firmware" / "tools"))

import rnode_framing  # noqa: E402
import rnode_trial  # noqa: E402


def snapshot(rx=0, header=0, tx=0, late=0, held=0, drop=0, heap_min=200000):
    return {"INFO": {"loop_max_ms": 40, "rx_service_max_ms": 2, "rx_stalled": False, "lock_timeouts": 0, "lock_misses": 0,
                     "rx_mode_lost": 0},
            "P1": {"rx_datagrams": rx, "header_only": header, "tx_datagrams": tx, "rx_late": late, "rx_ring_overflow": 0,
                   "assembly_timeout": 0, "split_lost": 0},
            "RNS": {"ifac_invalid": 0, "ann_limited": 0, "ann_held": held, "ann_drop": drop, "too_large": 0,
                    "rx_stack_free": 1500, "heap_size": 300000, "heap_free": 250000, "heap_min": heap_min}}


class SizesTests(unittest.TestCase):
    def test_announce_sizes_fill_508_bytes(self):
        # RNode: 492 B + IFAC 16 B; USB: 476 B, stacja dokłada identyfikator transportu 16 B i IFAC 16 B.
        self.assertEqual((rnode_trial.RNODE_APP_DATA, rnode_trial.RNODE_PACKET), (325, 492))
        self.assertEqual((rnode_trial.USB_APP_DATA, rnode_trial.USB_PACKET), (309, 476))
        self.assertEqual(rnode_trial.USB_PACKET + rnode_trial.TRANSPORT_ID + rnode_trial.IFAC_BYTES, rnode_framing.MTU)

    def test_marker_round_trip(self):
        data = rnode_trial.app_data(b"\x01\x02\x03\x04", 77, 325)
        self.assertEqual(len(data), 325)
        self.assertEqual(rnode_trial.parse_app_data(data), ("01020304", 77))
        self.assertIsNone(rnode_trial.parse_app_data(b"receiver"))
        self.assertIsNone(rnode_trial.parse_app_data(None))

    def test_rnode_interface_config(self):
        text = rnode_framing.rnode_interface("/dev/ttyACM0", "00" * 16, 10)
        for line in ("type = RNodeInterface", "frequency = 869525000", "bandwidth = 125000", "spreadingfactor = 7",
                     "codingrate = 5", "txpower = 10", "ifac_size = 128", "passphrase = " + "00" * 16):
            self.assertIn(line, text)
        with self.assertRaises(ValueError):
            rnode_framing.rnode_interface("/dev/x\n[[other]]", "00" * 16)


class CriteriaTests(unittest.TestCase):
    def test_rnode_direction_passes(self):
        table = rnode_trial.criteria("rnode", 100, snapshot(rx=10, header=10), snapshot(rx=109, header=109))
        self.assertEqual(table["rx_datagrams_delta"]["value"], 99)
        self.assertEqual(rnode_trial.verdict(table), "passed")

    def test_rnode_direction_failures(self):
        table = rnode_trial.criteria("rnode", 100, snapshot(), snapshot(rx=98, header=97, late=1, heap_min=80000))
        for name in ("rx_datagrams_delta", "header_only_delta", "rx_late_delta", "heap_min_30_percent"):
            self.assertIs(table[name]["pass"], False, name)
        self.assertEqual(rnode_trial.verdict(table), "failed")

    def test_missing_field_is_never_a_pass(self):
        before, after = snapshot(), snapshot(rx=100, header=100)
        del before["P1"]["rx_late"], after["P1"]["rx_late"]
        after["INFO"] = None   # brak odpowiedzi INFO
        table = rnode_trial.criteria("rnode", 100, before, after)
        self.assertIsNone(table["rx_late_delta"]["pass"])
        self.assertIsNone(table["rx_stalled"]["pass"])
        self.assertEqual(rnode_trial.verdict(table), "incomplete")

    def test_usb_direction_with_loratx_lines(self):
        lines = [{"time": 100.0 + 84 * i, "loratx": "sent", "len": 508, "frames": 2, "tx_wait_ms": 10056} for i in range(100)]
        lines.append({"time": 9000.0, "loratx": "sent", "len": 221, "frames": 1, "tx_wait_ms": 4000})
        table = rnode_trial.criteria("usb", 100, snapshot(), snapshot(tx=200, held=60), lines)
        self.assertEqual(table["loratx_508_two_frames"]["value"], 100)
        self.assertEqual(table["loratx_gap_s_min"]["value"], 84.0)
        self.assertEqual(table["loratx_tx_wait_ms_max"]["value"], 10056)
        self.assertEqual(table["ann_held_delta"]["value"], 60)
        self.assertEqual(rnode_trial.verdict(table), "passed")
        table = rnode_trial.criteria("usb", 100, snapshot(), snapshot(tx=200, drop=3), lines[:90])
        self.assertIs(table["loratx_508_two_frames"]["pass"], False)
        self.assertIs(table["ann_drop_delta"]["pass"], False)

    def test_console_reply_kinds(self):
        self.assertEqual(rnode_trial.p1_part({"lora": {"rx_datagrams": 3}}), {"rx_datagrams": 3})
        self.assertIsNone(rnode_trial.p1_part({"loratx": "sent", "len": 508}))
        self.assertTrue(rnode_trial.is_info({"contract": 2}))
        self.assertTrue(rnode_trial.is_rns({"rns": True, "paths": 4}))


if __name__ == "__main__":
    unittest.main()
