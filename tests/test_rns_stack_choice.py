# SPDX-License-Identifier: MIT
"""Stack choice in the station program on the computer: the microReticulum port ("host") or the
station Reticulum core ("host-core", firmware/reticulum-core.md, stage R0).

Both programs run firmware/src/host/node_host.cpp on the same FRAM image file in turn. A station
keeps its identity when it moves from the port to the core (and back): both read the same identity
key record in FRAM. The address follows the identity: "wici.sa1" on the port, "lxmf.delivery" on the
core from stage R3. The core program has the P1 interface with IFAC and announces
(stage R1); without a network key it is offline like the port.
Needs PlatformIO and network access for the pinned stack sources:

  WICI_PIO=/path/to/pio python3 -m unittest tests.test_rns_stack_choice
"""

import hashlib
import hmac
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


def run(env: str, fram: Path, commands=(), extra=()) -> list:
    """Start the program on the FRAM image, send commands, quit; JSON events from its output."""
    args = [str(PROGRAMS[env]), "--fram", str(fram), "--listen", str(free_port()), "--peer", str(free_port()), *extra]
    stdin = "".join(f"{c}\n" for c in commands) + "quit\n"
    result = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise AssertionError(f"{env} exited with {result.returncode}: {result.stdout}{result.stderr}")
    return [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]


def stored_key(fram: Path) -> bytes:
    # Rekord tożsamości (framfs.h): dwa sloty po 128 B od 0x044000, numer w bajtach 4..7, klucz 8..71.
    image = fram.read_bytes()
    slots = [image[0x044000 + i * 128:0x044000 + i * 128 + 74] for i in range(2)]
    slots = [s for s in slots if len(s) == 74 and s[:4] not in (bytes(4), b"\xff" * 4)]
    return max(slots, key=lambda s: int.from_bytes(s[4:8], "little"))[8:72]


def drbg(entropy: bytes, nonce: bytes, length: int) -> bytes:
    # HMAC-DRBG z SHA-256 jak firmware/src/drbg.cpp (SP 800-90A, 10.1.2): instantiate, generate.
    def mac(key, data):
        return hmac.new(key, data, hashlib.sha256).digest()
    key, value = bytes(32), b"\x01" * 32
    for round in (0, 1):
        key = mac(key, value + bytes([round]) + entropy + nonce)
        value = mac(key, value)
    out = b""
    while len(out) < length:
        value = mac(key, value)
        out += value
    return out[:length]


# Ziarno, przy którym surowy klucz X25519 z generatora wymaga przycięcia w obu bajtach (sprawdza test):
# brak któregokolwiek kroku przycięcia w rdzeniu zawsze zmienia tożsamość odczytaną przez port.
SEED = b"\x01" * 32


def address_of(identity_hash: str, name: bytes) -> str:
    # RNS/Destination.py: Destination.hash dla celu o nazwie name tożsamości stacji.
    name_hash = hashlib.sha256(name).digest()[:10]
    return hashlib.sha256(name_hash + bytes.fromhex(identity_hash)).digest()[:16].hex()


def sa1_address(identity_hash: str) -> str:
    return address_of(identity_hash, b"wici.sa1")   # cel stacji na porcie


def lxmf_address(identity_hash: str) -> str:
    return address_of(identity_hash, b"lxmf.delivery")   # cel stacji na rdzeniu (od R3)


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

    def ready(self, env: str, commands=(), extra=()):
        events = run(env, self.fram, commands, extra)
        self.assertEqual(events[0]["event"], "ready", events)
        return events[0], events[1:]

    def test_port_identity_kept_on_core(self):
        port, _ = self.ready("host")
        core, _ = self.ready("host-core")
        self.assertTrue(port["identity_new"])
        self.assertFalse(core["identity_new"])
        self.assertEqual(core["identity"], port["identity"])
        self.assertEqual((port["address"], core["address"]), (sa1_address(port["identity"]), lxmf_address(core["identity"])))

    def test_core_identity_kept_on_port(self):
        raw = drbg(SEED, b"WICI rnscore identity", 64)
        self.assertNotEqual(raw[0] & 0x07, 0)      # ziarno wymaga obu kroków przycięcia
        self.assertNotEqual(raw[31] & 0xC0, 0x40)
        core, _ = self.ready("host-core", extra=["--seed", SEED.hex()])
        again, _ = self.ready("host-core")
        port, _ = self.ready("host")
        self.assertTrue(core["identity_new"])
        self.assertFalse(again["identity_new"])
        self.assertFalse(port["identity_new"])
        self.assertEqual(core["address"], lxmf_address(core["identity"]))
        # Zapisany klucz to wynik generatora z kluczem X25519 przyciętym (RFC 7748), bo port go nie przycina;
        # stałe ziarno, żeby próba nie zależała od losowego klucza, który bywa przycięty sam z siebie.
        clamped = bytes([raw[0] & 0xF8]) + raw[1:31] + bytes([(raw[31] & 0x7F) | 0x40]) + raw[32:]
        self.assertEqual(stored_key(self.fram), clamped)
        self.assertEqual({e["identity"] for e in (core, again, port)}, {core["identity"]})
        self.assertEqual((again["address"], port["address"]), (core["address"], sa1_address(core["identity"])))

    def test_node_without_address(self):
        # Węzeł stanowiska (--node) nie ma celu "wici.sa1": adres zerowy w obu stosach, tożsamość ta sama.
        port = run("host", self.fram, extra=["--node"])[0]
        core = run("host-core", self.fram, extra=["--node"])[0]
        self.assertEqual((port["event"], port["node"], core["event"], core["node"]), ("ready", True, "ready", True))
        self.assertEqual(port["address"], "00" * 16)
        self.assertEqual((core["identity"], core["address"]), (port["identity"], port["address"]))

    def test_core_offline_without_network_key(self):
        # Bez klucza sieci (IFAC) interfejs P1 nie nadaje: stos nie ogłasza i nie wysyła; cel nieznany.
        _, events = self.ready("host-core", ["announce", "send " + "00" * 16 + " 01", "path " + "00" * 16, "status"])
        announced, sent, path, status = events
        self.assertEqual((status["event"], status["online"], status["offline"]), ("status", False, 1))
        self.assertEqual(announced, {"event": "announced", "ok": False})
        self.assertEqual(sent, {"event": "sent", "handle": 0})
        self.assertEqual(path, {"event": "path", "known": False, "path": False})

    def test_core_announce_with_network_key(self):
        # Z kluczem sieci ogłoszenie trafia do kolejki P1; w ciszy pełnej i z wyjątkiem stos go nie przyjmuje.
        _, events = self.ready("host-core", ["announce", "silence full", "announce", "silence exception", "announce",
                                             "silence off", "status"],
                               extra=["--ifac", "5749434954335f696661635f74657374"])
        announced = [e["ok"] for e in events if e["event"] == "announced"]
        status = events[-1]
        self.assertEqual(announced, [True, False, False])
        self.assertEqual((status["online"], status["q_queued"]), (True, 1))
        # Dwie odmowy w ciszy; ogłoszenie z kolejki odpada przy wejściu w ciszę, jeśli łącze go jeszcze nie nadaje.
        self.assertIn(status["silenced"], (2, 3))

    def test_core_no_begin_after_halt(self):
        # Po halt() (zniszczenie tożsamości) begin() odmawia do restartu, choć klucz jest jeszcze w FRAM:
        # kolejność „halt, potem kasowanie FRAM” nie jest warunkiem (audyt rdzenia, U10).
        ifac = ["--ifac", "5749434954335f696661635f74657374"]
        first, events = self.ready("host-core", ["halt", "begin", "announce", "status"], extra=ifac)
        halted, began, announced, status = events
        self.assertEqual(halted, {"event": "halted"})
        self.assertEqual(began, {"event": "begin", "ok": False, "address": "00" * 16})
        self.assertEqual(announced, {"event": "announced", "ok": False})
        self.assertEqual(status["online"], False)
        again, _ = self.ready("host-core", extra=ifac)   # restart: ta sama tożsamość z FRAM
        self.assertEqual((again["identity"], again["identity_new"]), (first["identity"], False))


if __name__ == "__main__":
    unittest.main()
