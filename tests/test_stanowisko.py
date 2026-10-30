# SPDX-License-Identifier: MIT
"""Receiving station application (software/laptop/wici/stanowisko, PLAN.md stages S1-S10).

The unit tests run with any Python. The stack test (S1) runs the application stack in this process
behind two "host" programs of the firmware (station and OSP node on the emulated radio link, the node USB
data port as a pseudo-terminal), like firmware/tools/rns_osp_node.py, and needs Reticulum at e40191b,
LXMF at c3ff2d6 and pyserial in this Python, and the built program:

  pio run -e host -d firmware
  WICI_HOST_PROGRAM=firmware/.pio/build/host/program /path/to/venv/bin/python -m unittest tests.test_stanowisko
"""

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "software" / "laptop"))
sys.path.insert(0, str(ROOT / "firmware" / "tools"))

from wici.stanowisko import stos  # noqa: E402

PROGRAM = os.environ.get("WICI_HOST_PROGRAM")
HAS_STACK = all(importlib.util.find_spec(m) for m in ("RNS", "LXMF", "serial"))


class ConfigTest(unittest.TestCase):
    def test_one_kiss_interface_without_transport_or_shared_instance(self):
        text = stos.config("/dev/ttyACM0")
        self.assertIn("enable_transport = No", text)
        self.assertIn("share_instance = No", text)
        self.assertIn("type = KISSInterface", text)
        self.assertIn("port = /dev/ttyACM0", text)
        self.assertIn("flow_control = Yes", text)
        self.assertIn(f"bitrate = {stos.BITRATE}", text)
        self.assertEqual(text.count("type = "), 1)   # bez AutoInterface, TCP i UDP
        # Awaria portu nie kończy procesu (panic): interfejs KISS łączy się ponownie, a aplikacja działa dalej.
        self.assertIn("panic_on_interface_error = No", text)

    def test_bitrate_meets_the_radio_criterion(self):
        # radio.md, kryterium bitrate: 500 B × 8 / bitrate nie krócej niż odstęp dla 2 skoków (około 95 s).
        self.assertGreaterEqual(500 * 8 / stos.BITRATE, 95)

    def test_rejects_values_that_would_break_the_config(self):
        for bad in (0, 1201, -5):
            with self.assertRaises(ValueError):
                stos.config("/dev/ttyACM0", bad)
        for bad in ("COM5\n[[x]]", "a]b"):
            with self.assertRaises(ValueError):
                stos.config(bad)


@unittest.skipUnless(PROGRAM and HAS_STACK, "WICI_HOST_PROGRAM or Reticulum, LXMF and pyserial not available")
class StackTest(unittest.TestCase):
    """S1: the application stack behind the OSP node, with a station that has the application as card receiver."""

    @classmethod
    def setUpClass(cls):
        import rns_osp_node
        import udp_ports
        cls.work = tempfile.TemporaryDirectory()
        work = Path(cls.work.name)
        station_port, node_port = udp_ports.free_udp_ports(2)
        cls.node = rns_osp_node.Program(PROGRAM, str(work / "node.bin"), node_port, station_port, 12, node=True)
        cls.station = rns_osp_node.Program(PROGRAM, str(work / "station.bin"), station_port, node_port, 12)
        if not cls.node.ready or not cls.station.ready:
            raise RuntimeError("host programs did not start")
        cls.messages = []
        cls.stos = stos.Stos(work / "stan", cls.node.ready["usb"], lambda *m: cls.messages.append(m),
                             log=lambda line: None)
        cls.stos.start()
        cls.station_address = bytes.fromhex(cls.station.ready["address"])

    @classmethod
    def tearDownClass(cls):
        import RNS
        RNS.Reticulum.panic_on_interface_error = False
        cls.stos.stop()
        cls.node.stop()
        cls.station.stop()
        cls.work.cleanup()

    @staticmethod
    def wait_for(condition, timeout):
        end = time.time() + timeout
        while time.time() < end:
            if condition():
                return True
            time.sleep(0.05)
        return False

    def sa1_destination(self):
        import sa1_lxmf
        return sa1_lxmf.sa1_of(self.stos.identity)

    def make_receiver_of_station(self):
        self.station.command(f"receiver {self.sa1_destination().hex()} {self.stos.identity.get_public_key().hex()}")
        self.assertIsNotNone(self.station.wait("receiver", 5))

    def test_1_flow_control_and_bitrate_from_config(self):
        import RNS
        self.assertTrue(self.wait_for(lambda: self.node.status().get("usb_flow") is True, 10))
        kiss = next(i for i in RNS.Transport.interfaces if type(i).__name__ == "KISSInterface")
        self.assertEqual(kiss.bitrate, stos.BITRATE)
        self.assertFalse(RNS.Reticulum.transport_enabled())

    def test_2_announce_reaches_the_station(self):
        self.stos.announce()
        e = self.station.wait("announce", 120, lambda e: e["dest"] == self.stos.address.hex())
        self.assertIsNotNone(e)

    def report(self, text):
        """A report from the station through the node: (source, signature_ok) at the application; receipt checked."""
        import sa1_lxmf
        self.make_receiver_of_station()
        content = b'["WICI",1,"stanowisko","' + text.encode() + b'"]'
        data = sa1_lxmf.envelope(self.station_address, self.sa1_destination(), content)
        self.station.command(f"send {self.sa1_destination().hex()} {data.hex()} 120")
        sent = self.station.wait("sent", 10)
        self.assertTrue(sent and sent["handle"] > 0)
        self.assertTrue(self.wait_for(lambda: any(m[1] == content for m in self.messages), 120))
        receipt = self.station.wait("receipt", 180, lambda e: e["handle"] == sent["handle"])
        self.assertTrue(receipt and receipt["delivered"])
        source, _, signature_ok = next(m for m in self.messages if m[1] == content)
        self.assertEqual(source, self.station_address)
        return signature_ok

    def test_3_report_before_the_station_announce_has_no_checked_signature(self):
        # Nadawca jeszcze nieznany (SOURCE_UNKNOWN): podpisu nie da się sprawdzić. Zapytanie o trasę
        # i sprawdzenie po ogłoszeniu należą do etapu S2 (stanowisko-osp.md, „Przyjęcie”).
        self.assertFalse(self.report("S1 przed ogłoszeniem stacji"))

    def test_4_application_message_reaches_the_station_and_is_delivered(self):
        import LXMF
        import RNS
        import sa1_lxmf
        self.make_receiver_of_station()
        self.station.command("announce 57494349")
        self.assertTrue(self.wait_for(lambda: RNS.Identity.recall(self.station_address) is not None, 120))
        content = b'["WICI",1,"stanowisko","S1 aplikacja do stacji"]'
        message = self.stos.send(self.station_address, content)
        self.assertIsNotNone(message)
        expected = sa1_lxmf.envelope(self.sa1_destination(), self.station_address, content).hex()
        self.assertIsNotNone(self.station.wait("packet", 120, lambda e: e["data"] == expected))
        self.assertTrue(self.wait_for(lambda: message.state == LXMF.LXMessage.DELIVERED, 240))

    def test_5_report_after_the_station_announce_has_a_checked_signature(self):
        import RNS
        self.station.command("announce 57494349")
        self.assertTrue(self.wait_for(lambda: RNS.Identity.recall(self.station_address) is not None, 120))
        self.assertTrue(self.report("S1 po ogłoszeniu stacji"))

    def test_6_identity_survives_a_restart(self):
        import RNS
        path = Path(self.work.name) / "stan" / "tozsamosc"
        self.assertEqual(RNS.Identity.from_file(str(path)).hash, self.stos.identity.hash)
        self.assertEqual(stos.Stos._identity(path).hash, self.stos.identity.hash)


if __name__ == "__main__":
    unittest.main()
