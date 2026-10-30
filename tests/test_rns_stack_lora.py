# SPDX-License-Identifier: MIT
"""Station Reticulum stack over the LoRa link against reference Reticulum (Python), without a radio.

The LoRa link (stage L7, lora-interfejs/PLAN.md): the same programs as in tests/test_rns_stack.py with --link lora.
rns_interop.py talks to the
station through an RNodeInterface of Reticulum on the pseudo-terminal of firmware/tools/rnode_emulator.py (frames of
the RNode firmware over UDP), rns_osp_node.py joins the node, a relay and stations on a shared emulated medium. The
emulator and the station frame come from one reading of the RNode source: these tests show interworking with
RNodeInterface, not over-the-air conformance with real firmware (the RAK4631 hardware trial).

Needs the same environment as tests/test_rns_stack.py:

  WICI_PIO=/path/to/pio WICI_RNS_PYTHON=/path/to/venv/bin/python python3 -m unittest tests.test_rns_stack_lora
"""

import json
import subprocess
import unittest

# Wspólne ścieżki, kroki i odczyt wyniku z tests/test_rns_stack.py (bez klas prób, żeby nie biegły drugi raz).
from tests.test_rns_stack import CORE_PROGRAM, CORE_STEPS, FIRMWARE, PIO, PORT_PROGRAM, RNS_PYTHON, results


# Kroki LoRa rns_interop.py (--link lora): B największy datagram w dwóch ramkach, J ramki 509 B, D dług ciszy 12t.
LORA_STEPS = {"B": ["lora_big_announce_to_python", "lora_big_announce_two_frames", "lora_big_announce_to_station",
                    "lora_big_announce_frames_255", "lora_big_packet_to_python", "lora_big_packet_receipt",
                    "lora_big_packet_two_frames", "lora_big_packet_to_station", "lora_big_packet_proof",
                    "lora_big_packet_frames_from_python"],
              "J": ["frames_509_rejected_and_counted"],
              "D": ["debt_12t_between_packets"]}


@unittest.skipUnless(PIO and RNS_PYTHON, "WICI_PIO and WICI_RNS_PYTHON not set")
class LoraInteropTests(unittest.TestCase):
    """rns_interop.py --link lora on the port: RNodeInterface (IFAC 16 B) - RNode emulator - UDP frames - station."""

    program_env = "host-port"
    program = PORT_PROGRAM
    extra = []
    steps = ["1", "2", "3", "4", "5", "B", "J", "D"]

    @classmethod
    def setUpClass(cls):
        subprocess.run([PIO, "run", "-e", cls.program_env, "-d", str(FIRMWARE)], check=True, capture_output=True)
        command = [RNS_PYTHON, str(FIRMWARE / "tools" / "rns_interop.py"), "--program", str(cls.program), "--link", "lora",
                   "--steps", ",".join(cls.steps)] + cls.extra
        cls.results = results(subprocess.run(command, capture_output=True, text=True, timeout=1800))

    def test_every_step_check_passed(self):
        # Dokładnie sprawdzenia wybranych kroków, i wszystkie przechodzą.
        expected = sorted(name for step in self.steps for name in {**CORE_STEPS, **LORA_STEPS}[step])
        self.assertEqual(sorted(self.results["checks"]), expected)
        failed = [name for name, ok in self.results["checks"].items() if not ok]
        self.assertEqual(failed, [], json.dumps(self.results, indent=2))

    def test_link_and_declared_bitrate(self):
        # Przepływność deklarowana stosowi z czasu ogłoszenia stacji w LoRa (loraframe::declaredBitrate), nie 271 b/s z P1.
        self.assertEqual(self.results["link"], "lora")
        self.assertGreater(self.results["declared_bitrate"], 4000)

    def test_ifac_drops_counted(self):
        status = self.results["station_status"]
        self.assertGreaterEqual(status["ifac_missing"], 1)
        self.assertGreaterEqual(status["ifac_invalid"], 1)

    def test_509_byte_frames_counted(self):
        self.assertEqual(self.results["frames_509"]["lora_bad_length"], 1)
        self.assertEqual(self.results["frames_509"]["datagrams_in"], 0)


class LoraInteropCoreTests(LoraInteropTests):
    """The same on the station Reticulum core: the steps of CORE_STEPS (LXMF) and the LoRa steps."""

    program_env = "host"
    program = CORE_PROGRAM
    extra = ["--lxmf"]
    steps = list(CORE_STEPS) + list(LORA_STEPS)


@unittest.skipUnless(PIO and RNS_PYTHON, "WICI_PIO and WICI_RNS_PYTHON not set")
class OspNodeLoraTests(unittest.TestCase):
    """rns_osp_node.py --link lora on the core: node, relay and stations on the emulated LoRa medium, LXMRouter in Python
    behind USB with bitrate 41 b/s (D19)."""

    @classmethod
    def setUpClass(cls):
        subprocess.run([PIO, "run", "-e", "host", "-d", str(FIRMWARE)], check=True, capture_output=True)
        command = [RNS_PYTHON, str(FIRMWARE / "tools" / "rns_osp_node.py"), "--program", str(CORE_PROGRAM), "--lxmf", "--link", "lora"]
        cls.results = results(subprocess.run(command, capture_output=True, text=True, timeout=3000))

    def test_every_check_passed(self):
        failed = [name for name, ok in self.results["checks"].items() if not ok]
        self.assertEqual(failed, [], json.dumps(self.results, indent=2))

    def test_lora_checks_present(self):
        for name in ("usb_493_500_dropped_and_counted", "lora_without_ifac_not_to_computer", "lxmf_no_retry_before_proof",
                     "lxmf_three_attempts", "lxmf_interval_from_bitrate_alone", "received_status_one_hop",
                     "received_status_two_hops", "lxmf_two_hops_with_proof_before_retry", "node_forwards_without_computer",
                     "bulletin_50_paced"):
            self.assertIn(name, self.results["checks"])

    def test_lxmf_interval_set_by_bitrate(self):
        # 3 próby i odstęp ≥201 s przy bitrate 41 b/s: samo ustawienie interfejsu KISS.
        self.assertEqual(self.results["bitrate"], 41)
        self.assertEqual(self.results["lxmf"]["max_attempts"], 3)
        self.assertGreaterEqual(self.results["lxmf"]["interval_s"], 201)

    def test_burst_of_6_without_loss(self):
        burst = self.results["burst"]
        self.assertEqual((burst["sent"], burst["received"], burst["usb_rx_drop"]), (6, 6, 0))


if __name__ == "__main__":
    unittest.main()
