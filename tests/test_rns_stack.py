# SPDX-License-Identifier: MIT
"""Station Reticulum stack against reference Reticulum (Python), without a radio.

Builds the "host-port" PlatformIO program (microReticulum port, P1 interface, IFAC, FRAM tables, emulated
P1 link) and runs firmware/tools/rns_interop.py with it, then firmware/tools/rns_osp_node.py (the OSP
node of decision D19 with the computer of the receiving station on a KISS interface). The same
rns_interop.py runs on the "host" program (station Reticulum core since stage R6-3, firmware/reticulum-core.md) with
the steps the core already has (CORE_STEPS, extended with each stage step) and, from stage R3, with
the station destination "lxmf.delivery" and LXMF SA1 messages (--lxmf, steps L1 and L2 with LXMRouter), and
rns_osp_node.py runs on "host" with --lxmf (stage R4b: USB interface of the node on the core, with a
flood from the computer side during a report through P1).
Needs network access for the pinned stack sources and a Python with Reticulum at e40191b, LXMF at
c3ff2d6 and pyserial, so it runs only when both are given:

  WICI_PIO=/path/to/pio WICI_RNS_PYTHON=/path/to/venv/bin/python python3 -m unittest tests.test_rns_stack

WICI_RNS_FILL=256 adds the RAM measurement with a full path table (slow: about 3 min more).

The LoRa link (stage L7, lora-interfejs/PLAN.md): the same programs with --link lora. rns_interop.py talks to the
station through an RNodeInterface of Reticulum on the pseudo-terminal of firmware/tools/rnode_emulator.py (frames of
the RNode firmware over UDP), rns_osp_node.py joins the node, a relay and stations on a shared emulated medium. The
emulator and the station frame come from one reading of the RNode source: these tests show interworking with
RNodeInterface, not over-the-air conformance with real firmware (the RAK4631 hardware trial).
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


PORT_PROGRAM = FIRMWARE / ".pio" / "build" / "host-port" / "program"
CORE_PROGRAM = FIRMWARE / ".pio" / "build" / "host" / "program"
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
        subprocess.run([PIO, "run", "-e", "host-port", "-d", str(FIRMWARE)], check=True, capture_output=True)
        program = PORT_PROGRAM
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
        subprocess.run([PIO, "run", "-e", "host", "-d", str(FIRMWARE)], check=True, capture_output=True)
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
        subprocess.run([PIO, "run", "-e", "host-port", "-d", str(FIRMWARE)], check=True, capture_output=True)
        command = [RNS_PYTHON, str(FIRMWARE / "tools" / "rns_osp_node.py"), "--program", str(PORT_PROGRAM)]
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
        subprocess.run([PIO, "run", "-e", "host", "-d", str(FIRMWARE)], check=True, capture_output=True)
        command = [RNS_PYTHON, str(FIRMWARE / "tools" / "rns_osp_node.py"), "--program", str(CORE_PROGRAM), "--lxmf"]
        cls.results = results(subprocess.run(command, capture_output=True, text=True, timeout=1800))

    def test_core_checks_present(self):
        for name in ("station_card_receiver", "computer_packets_k1", "flood_report_delivered", "flood_one_operation_per_loop",
                     "flood_p1_steps_run", "flood_usb_announces_limited", "flood_bad_announces_not_pinned",
                     "cheap_flood_rebroadcast_reaches_computer", "cheap_flood_one_operation_per_loop", "usb_ifac_flag_dropped",
                     "route_on_p1_unpins_computer_destination", "ninth_destination_evicts_oldest",
                     "computer_destinations_after_restart"):
            self.assertIn(name, self.results["checks"])


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
    behind USB with bitrate 42 b/s (D19)."""

    @classmethod
    def setUpClass(cls):
        subprocess.run([PIO, "run", "-e", "host", "-d", str(FIRMWARE)], check=True, capture_output=True)
        command = [RNS_PYTHON, str(FIRMWARE / "tools" / "rns_osp_node.py"), "--program", str(CORE_PROGRAM), "--lxmf", "--link", "lora"]
        cls.results = results(subprocess.run(command, capture_output=True, text=True, timeout=3000))

    def test_every_check_passed(self):
        # BULLETIN do 50 stacji (bulletin_50_without_loss) to otwarty problem: test_bulletin_50_flow_control niżej.
        failed = [name for name, ok in self.results["checks"].items() if not ok and name != "bulletin_50_without_loss"]
        self.assertEqual(failed, [], json.dumps(self.results, indent=2))

    def test_lora_checks_present(self):
        for name in ("usb_493_500_dropped_and_counted", "lora_without_ifac_not_to_computer", "lxmf_no_retry_before_proof",
                     "lxmf_three_attempts", "lxmf_interval_from_bitrate_alone", "received_status_one_hop",
                     "received_status_two_hops", "lxmf_two_hops_with_proof_before_retry", "node_forwards_without_computer"):
            self.assertIn(name, self.results["checks"])

    def test_lxmf_interval_set_by_bitrate(self):
        # 3 próby i odstęp ≥196 s przy bitrate 42 b/s: samo ustawienie interfejsu KISS.
        self.assertEqual(self.results["bitrate"], 42)
        self.assertEqual(self.results["lxmf"]["max_attempts"], 3)
        self.assertGreaterEqual(self.results["lxmf"]["interval_s"], 196)

    def test_burst_of_6_without_loss(self):
        burst = self.results["burst"]
        self.assertEqual((burst["sent"], burst["received"], burst["usb_rx_drop"]), (6, 6, 0))

    @unittest.expectedFailure
    def test_bulletin_50_flow_control(self):
        # Otwarte: czas kanału jednego pakietu (13t, ok. 5 s) przekracza 5 s blokady interfejsu KISS w Pythonie, który
        # sam zwalnia kontrolę przepływu, więc seria 50 pakietów przepełnia bufor USB węzła (zmierzono: 31 z 50 dotarło,
        # 19 odrzuconych). Do rozstrzygnięcia: wielkość bufora USB węzła albo odstęp BULLETIN w aplikacji stanowiska.
        bulletin = self.results["bulletin"]
        self.assertEqual((bulletin["sent"], bulletin["received"], bulletin["usb_rx_drop"]), (50, 50, 0))


if __name__ == "__main__":
    unittest.main()
