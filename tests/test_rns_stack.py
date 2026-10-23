# SPDX-License-Identifier: MIT
"""Station Reticulum stack against reference Reticulum (Python), without a radio.

Builds the "host" PlatformIO program (microReticulum port, P1 interface, IFAC, FRAM tables, emulated
P1 link) and runs firmware/tools/rns_interop.py with it, then firmware/tools/rns_osp_node.py (the OSP
node of decision D19 with the computer of the receiving station on a KISS interface). The same
rns_interop.py runs on the "host-core" program (station Reticulum core, firmware/reticulum-core.md) with
the steps the core already has (CORE_STEPS, extended with each stage step) and, from stage R3, with
the station destination "lxmf.delivery" and LXMF SA1 messages (--lxmf, steps L1 and L2 with LXMRouter), and
rns_osp_node.py runs on "host-core" with --lxmf (stage R4b: USB interface of the node on the core, with a
flood from the computer side during a report through P1).
Needs network access for the pinned stack sources and a Python with Reticulum at e40191b, LXMF at
c3ff2d6 and pyserial, so it runs only when both are given:

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
CORE_PROGRAM = FIRMWARE / ".pio" / "build" / "host-core" / "program"
# Kroki rns_interop.py na rdzeniu (z --lxmf: cel stacji "lxmf.delivery" i wiadomości SA1 w LXMF): wyjście
# etapu R1 (firmware/reticulum-core.md, „Etapy”), z krokiem 3r (szyfrowanie do ratchetu), którego port nie
# przechodzi, krok 6 z etapu R2 (trasa i tożsamość celu z tablicy w FRAM po restarcie), 9 (zapytania o trasę
# w obie strony) i wyjście etapu R3 (L1, L2: wymiana z LXMRouter w obie strony z dowodem dostarczenia).
CORE_STEPS = {
    "1": ["station_announce_in_python"],
    "2": ["python_announce_in_station"],
    "3": ["station_packet_accepted", "station_to_python_packet", "station_receipt_delivered"],
    "3r": ["ratchet_packet_decrypted", "ratchet_receipt_delivered"],
    "4": ["python_to_station_packet", "python_receipt_delivered"],
    "4a": ["rejected_packet_without_proof", "non_sa1_rejected_with_proof", "off_card_sender_rejected", "forged_source_rejected",
           "bad_signature_rejected", "stamp_rejected"],
    "5": ["ifac_missing_dropped", "ifac_invalid_dropped"],
    "6": ["identity_restored", "table_limit_after_restart", "path_and_identity_restored", "send_after_restart_without_announce",
          "receipt_after_restart"],
    "7": ["receiver_entry_kept_in_full_table"],
    "8": ["receiver_known_from_card", "announce_blocked_in_silence", "send_from_card_key_in_exception"],
    "9": ["station_answers_path_request", "station_path_request_answered"],
    "L1": ["station_lxmf_announce", "lxmf_station_to_router", "lxmf_station_receipt_delivered"],
    "L2": ["lxmf_router_to_station", "lxmf_router_delivered"],
}



def results(run: subprocess.CompletedProcess) -> dict:
    """Wynik skryptu (JSON na stdout); bez niego błąd z kodem wyjścia i końcem stderr skryptu."""
    try:
        return json.loads(run.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"script exited with {run.returncode} without a JSON result; stderr:\n{run.stderr[-4000:]}") from None

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
        cls.results = results(subprocess.run(command, capture_output=True, text=True, timeout=1800))

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
class CoreInteropTests(unittest.TestCase):
    """rns_interop.py on the station Reticulum core, with the steps of CORE_STEPS only."""

    @classmethod
    def setUpClass(cls):
        subprocess.run([PIO, "run", "-e", "host-core", "-d", str(FIRMWARE)], check=True, capture_output=True)
        command = [RNS_PYTHON, str(FIRMWARE / "tools" / "rns_interop.py"), "--program", str(CORE_PROGRAM),
                   "--steps", ",".join(CORE_STEPS), "--lxmf"]
        cls.results = results(subprocess.run(command, capture_output=True, text=True, timeout=1800))

    def test_every_step_check_passed(self):
        # Dokładnie te sprawdzenia, które dają wybrane kroki, i wszystkie przechodzą.
        expected = sorted(name for names in CORE_STEPS.values() for name in names)
        self.assertEqual(sorted(self.results["checks"]), expected)
        failed = [name for name, ok in self.results["checks"].items() if not ok]
        self.assertEqual(failed, [], json.dumps(self.results, indent=2))

    def test_station_announce_app_data(self):
        # Dane aplikacji ogłoszenia stacji (polecenie "announce 57494349") w Pythonie bez zmian.
        self.assertEqual(self.results["station_app_data"], "57494349")

    def test_station_display_name(self):
        # Ogłoszenie bez danych aplikacji: nazwa WICI-xxxxxx z 6 cyfr skrótu tożsamości (oprogramowanie.md).
        self.assertEqual(self.results["station_display_name"], "WICI-" + self.results["station_identity"][:6].upper())

    def test_ifac_drops_counted(self):
        status = self.results["station_status"]
        self.assertEqual((status["ifac_missing"], status["ifac_invalid"], status["rx_malformed"], status["rx_invalid"]),
                         (1, 1, 0, 0))

    def test_announce_reaches_packet_through_silence_debt(self):
        # Jak na porcie: ogłoszenie stacji, ogłoszenie Pythona i pakiet stacji przechodzą przez dług 12 x TX.
        self.assertLess(self.results["announce_to_packet_s"], 60)


@unittest.skipUnless(PIO and RNS_PYTHON, "WICI_PIO and WICI_RNS_PYTHON not set")
class OspNodeInteropTests(unittest.TestCase):
    """Station in the OSP node configuration with Reticulum (Python) on the computer behind USB (D19)."""

    @classmethod
    def setUpClass(cls):
        subprocess.run([PIO, "run", "-e", "host", "-d", str(FIRMWARE)], check=True, capture_output=True)
        command = [RNS_PYTHON, str(FIRMWARE / "tools" / "rns_osp_node.py"), "--program", str(PROGRAM)]
        cls.results = results(subprocess.run(command, capture_output=True, text=True, timeout=1800))

    def test_every_check_passed(self):
        failed = [name for name, ok in self.results["checks"].items() if not ok]
        self.assertEqual(failed, [], json.dumps(self.results, indent=2))

    def test_burst_passes_flow_control(self):
        # Gotowość po każdym pakiecie: kolejka KISS w Pythonie pusta szybciej niż blokada 5 s.
        burst = self.results["burst"]
        self.assertEqual((burst["received"], burst["usb_rns_in"], burst["usb_rx_drop"]), (burst["sent"], burst["sent"], 0))
        self.assertGreaterEqual(burst["usb_ready"], burst["sent"])



@unittest.skipUnless(PIO and RNS_PYTHON, "WICI_PIO and WICI_RNS_PYTHON not set")
class OspNodeCoreTests(OspNodeInteropTests):
    """rns_osp_node.py on the station Reticulum core (stage R4b): LXMF SA1, computer destinations after a
    restart of the node and a flood from USB."""

    @classmethod
    def setUpClass(cls):
        subprocess.run([PIO, "run", "-e", "host-core", "-d", str(FIRMWARE)], check=True, capture_output=True)
        command = [RNS_PYTHON, str(FIRMWARE / "tools" / "rns_osp_node.py"), "--program", str(CORE_PROGRAM), "--lxmf"]
        cls.results = results(subprocess.run(command, capture_output=True, text=True, timeout=1800))

    def test_core_checks_present(self):
        for name in ("station_card_receiver", "computer_destination_pinned_after_restart", "flood_report_delivered",
                     "flood_one_operation_per_loop", "flood_p1_steps_run", "flood_usb_announces_limited"):
            self.assertIn(name, self.results["checks"])


if __name__ == "__main__":
    unittest.main()
