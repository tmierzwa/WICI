# SPDX-License-Identifier: MIT
"""Stack choice in the station program on the computer: the microReticulum port ("host") or the
station Reticulum core ("host-core", firmware/reticulum-core.md, stage R0).

Both programs run firmware/src/host/node_host.cpp on the same FRAM image file in turn. A station
keeps its identity and address when it moves from the port to the core (and back): both read the
same identity key record in FRAM. The core program in R0 has no interface yet, so it does not
announce or send. Needs PlatformIO and network access for the pinned stack sources:

  WICI_PIO=/path/to/pio python3 -m unittest tests.test_rns_stack_choice
"""

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / "firmware"
PIO = os.environ.get("WICI_PIO")
PROGRAMS = {env: FIRMWARE / ".pio" / "build" / env / "program" for env in ("host", "host-core")}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run(env: str, fram: Path, commands=()) -> list:
    """Start the program on the FRAM image, send commands, quit; JSON events from its output."""
    args = [str(PROGRAMS[env]), "--fram", str(fram), "--listen", str(free_port()), "--peer", str(free_port())]
    stdin = "".join(f"{c}\n" for c in commands) + "quit\n"
    result = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise AssertionError(f"{env} exited with {result.returncode}: {result.stdout}{result.stderr}")
    return [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]


def sa1_address(identity_hash: str) -> str:
    # RNS/Destination.py: Destination.hash dla celu "wici.sa1" tożsamości stacji.
    name_hash = hashlib.sha256(b"wici.sa1").digest()[:10]
    return hashlib.sha256(name_hash + bytes.fromhex(identity_hash)).digest()[:16].hex()


@unittest.skipUnless(PIO, "WICI_PIO not set")
class StackChoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for env in PROGRAMS:
            subprocess.run([PIO, "run", "-e", env, "-d", str(FIRMWARE)], check=True, capture_output=True)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fram = Path(self.tmp.name) / "fram.bin"

    def ready(self, env: str, commands=()):
        events = run(env, self.fram, commands)
        self.assertEqual(events[0]["event"], "ready", events)
        return events[0], events[1:]

    def test_port_identity_kept_on_core(self):
        port, _ = self.ready("host")
        core, _ = self.ready("host-core")
        self.assertTrue(port["identity_new"])
        self.assertFalse(core["identity_new"])
        self.assertEqual((core["identity"], core["address"]), (port["identity"], port["address"]))

    def test_core_identity_kept_on_port(self):
        core, _ = self.ready("host-core")
        again, _ = self.ready("host-core")
        port, _ = self.ready("host")
        self.assertTrue(core["identity_new"])
        self.assertFalse(again["identity_new"])
        self.assertFalse(port["identity_new"])
        self.assertEqual(core["address"], sa1_address(core["identity"]))
        self.assertEqual({(e["identity"], e["address"]) for e in (core, again, port)}, {(core["identity"], core["address"])})

    def test_core_without_interface_yet(self):
        # R0: stos działa (tożsamość), ale bez interfejsu nie ogłasza, nie wysyła i nie zna tras.
        _, events = self.ready("host-core", ["status", "announce", "send " + "00" * 16 + " 01", "path " + "00" * 16])
        status, announced, sent, path = events
        self.assertEqual((status["event"], status["online"], status["p1_iface"]), ("status", False, False))
        self.assertEqual(announced, {"event": "announced", "ok": False})
        self.assertEqual(sent, {"event": "sent", "handle": 0})
        self.assertEqual(path, {"event": "path", "known": False, "path": False})


if __name__ == "__main__":
    unittest.main()
