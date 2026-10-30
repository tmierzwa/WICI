# SPDX-License-Identifier: MIT
"""Station Reticulum stack over the LoRa link against reference Reticulum (Python), without a radio.

The LoRa link (stage L7, lora-interfejs/PLAN.md): the same programs as in tests/test_rns_stack.py with --link lora.
rns_interop.py talks to the
station through an RNodeInterface of Reticulum on the pseudo-terminal of firmware/tools/rnode_emulator.py (frames of
the RNode firmware over UDP), rns_osp_node.py joins the node, a relay and stations on a shared emulated medium. The
emulator and the station frame come from one reading of the RNode source: these tests show interworking with
RNodeInterface, not over-the-air conformance with real firmware (the RAK4631 hardware trial). rnode_trial.py, the tool
of hardware step 4 point 2, runs here with 3 announces each way against the same emulator and host program.

Needs the same environment as tests/test_rns_stack.py:

  WICI_PIO=/path/to/pio WICI_RNS_PYTHON=/path/to/venv/bin/python python3 -m unittest tests.test_rns_stack_lora
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
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


@unittest.skipUnless(PIO and RNS_PYTHON, "WICI_PIO and WICI_RNS_PYTHON not set")
class RnodeTrialToolTests(unittest.TestCase):
    """tools/rnode_trial.py (step 4, point 2) on the core with 3 announces each way: rnode-announce through the RNode
    emulator to the station (host --link lora), and usb-announce on the USB pseudo-terminal of a node (host --node) whose
    rebroadcasts reach rnode-listen through the emulator. The station diagnostic console does not exist in the host
    program, so the criteria run on its status mapped to the console fields."""

    COUNT = 3

    @classmethod
    def setUpClass(cls):
        subprocess.run([PIO, "run", "-e", "host", "-d", str(FIRMWARE)], check=True, capture_output=True)
        sys.path.insert(0, str(FIRMWARE / "tools"))
        import rnode_emulator
        from rns_interop import NETWORK_KEY
        from rns_osp_node import Program
        from udp_ports import free_udp_ports
        tool = [RNS_PYTHON, str(FIRMWARE / "tools" / "rnode_trial.py")]
        work = Path(tempfile.mkdtemp(prefix="wici_rnode_trial_test_"))
        count = ["--count", str(cls.COUNT)]

        def read(path):
            return json.loads(path.read_text()) if path.exists() else {}

        # RNode -> stacja: ogłoszenia 325 B (508 B w eterze), stacja weryfikuje każde.
        station_port, radio_port = free_udp_ports(2)
        station = Program(str(CORE_PROGRAM), str(work / "station.bin"), station_port, radio_port, 12, link="lora")
        emulator, pty = rnode_emulator.spawn(radio_port, station_port)
        try:
            cls.station_before = station.status()
            cls.announce_run = subprocess.run(tool + ["rnode-announce", "--port", pty, "--passphrase", NETWORK_KEY, "--interval", "2",
                                                      "--timeout", "5", "--out", str(work / "announce.json")] + count,
                                              capture_output=True, text=True, timeout=300)
            cls.announce = read(work / "announce.json")
            cls.station_after = station.status()
            # Trasa w stacji: ogłoszenie przyjęte po weryfikacji podpisu (zdarzenie "announce" rdzeń daje tylko dla
            # "lxmf.delivery", a próba ma osobny cel).
            cls.station_paths = {}
            for sent in cls.announce.get("sent", []):
                station.command(f"path {sent['dest']}")
                cls.station_paths[sent["dest"]] = station.wait("path", 5) or {}
        finally:
            station.stop()
            rnode_emulator.stop(emulator)

        # Komputer za USB węzła -> retransmisja z identyfikatorem transportu (508 B w eterze) -> RNode -> rnode-listen.
        node_port, radio_port = free_udp_ports(2)
        node = Program(str(CORE_PROGRAM), str(work / "node.bin"), node_port, radio_port, 12, node=True, link="lora")
        emulator, pty = rnode_emulator.spawn(radio_port, node_port)
        try:
            with open(work / "listen.log", "w") as log:
                listen = subprocess.Popen(tool + ["rnode-listen", "--port", pty, "--passphrase", NETWORK_KEY, "--timeout", "240",
                                                  "--out", str(work / "listen.json")] + count,
                                          stdout=subprocess.PIPE, stderr=log, text=True)
                for line in listen.stdout:
                    if "listening" in line:
                        break
                # Interwał 1 s: wszystkie trzy mieszczą się na liście oczekujących węzła (4), który wypuszcza je w limicie 2%.
                cls.usb_run = subprocess.run(tool + ["usb-announce", "--port", node.ready["usb"], "--interval", "1",
                                                     "--out", str(work / "usb.json")] + count,
                                             capture_output=True, text=True, timeout=120)
                listen.stdout.read()
                cls.listen_code = listen.wait(timeout=300)
                listen.stdout.close()
            cls.usb = read(work / "usb.json")
            cls.listen = read(work / "listen.json")
            cls.listen_log = (work / "listen.log").read_text()[-4000:]
            cls.node_tx = [e["length"] for e in node.air if e["event"] == "tx"]
        finally:
            node.stop()
            rnode_emulator.stop(emulator)

    def test_rnode_announce_508_bytes_on_air(self):
        self.assertEqual(self.announce_run.returncode, 0, self.announce_run.stderr[-4000:])
        a = self.announce
        self.assertEqual((a["app_data_bytes"], a["packet_bytes"], a["on_air_bytes"]), (325, 492, 508))
        self.assertEqual([s["seq"] for s in a["sent"]], list(range(self.COUNT)))

    def test_station_verified_every_announce(self):
        self.assertEqual(len(self.station_paths), self.COUNT)
        for dest, p in self.station_paths.items():
            self.assertTrue(p.get("known") and p.get("path"), (dest, p))

    def test_criteria_from_station_counters(self):
        # Stan programu host w polach konsoli (P1, RNS); pól, których host nie podaje (rx_late, INFO), brak: bez zaliczenia.
        import rnode_trial

        def snapshot(s):
            return {"P1": {"rx_datagrams": s["datagrams_in"], "header_only": s["lora_header_only"],
                           "assembly_timeout": s["lora_assembly_timeout"], "split_lost": s["lora_split_lost"]},
                    "RNS": {k: s[k] for k in ("ifac_invalid", "ann_limited")}}

        table = rnode_trial.criteria("rnode", self.COUNT, snapshot(self.station_before), snapshot(self.station_after))
        for name in ("rx_datagrams_delta", "header_only_delta", "assembly_timeout_delta", "split_lost_delta",
                     "ifac_invalid_delta", "ann_limited_delta"):
            self.assertIs(table[name]["pass"], True, json.dumps(table, indent=1))
        self.assertEqual(table["rx_datagrams_delta"]["value"], self.COUNT)
        self.assertIsNone(table["rx_late_delta"]["pass"])
        self.assertEqual(rnode_trial.verdict(table), "incomplete")

    def test_usb_announce_rebroadcast_508_bytes(self):
        self.assertEqual(self.usb_run.returncode, 0, self.usb_run.stderr[-4000:])
        self.assertEqual((self.usb["app_data_bytes"], self.usb["packet_bytes"], self.usb["on_air_bytes"]), (309, 476, 508))
        self.assertGreaterEqual(self.node_tx.count(508), self.COUNT, self.node_tx)

    def test_listener_counted_every_rebroadcast(self):
        self.assertEqual(self.listen_code, 0, self.listen_log)
        run = self.listen["runs"][self.usb["run"]]
        self.assertEqual((run["unique"], run["missing"], run["app_data_bytes"]), (self.COUNT, [], [309]), self.listen_log)
        self.assertTrue(run["passed"])


if __name__ == "__main__":
    unittest.main()
