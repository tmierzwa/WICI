# SPDX-License-Identifier: MIT
"""Compare the fixed-buffer MCU envelope with the Python reference, byte for byte, and run the
native WICI-Link checks that share its build."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hmac
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "firmware" / "src"
NATIVE = ROOT / "tests" / "native"
CRYPTO = ROOT / "firmware" / ".pio" / "stack" / "Crypto"
UNITS = ("AuthenticatedCipher.cpp", "BigNumberUtil.cpp", "ChaCha.cpp", "ChaChaPoly.cpp", "Cipher.cpp",
         "Crypto.cpp", "Curve25519.cpp", "Ed25519.cpp", "Hash.cpp", "NoiseSource.cpp", "Poly1305.cpp",
         "RNG.cpp", "SHA256.cpp", "SHA512.cpp")
COMPILER = shutil.which("clang++") or shutil.which("g++")
FLAGS = ["-std=c++17", "-fno-exceptions", "-fno-rtti", "-fsanitize=address,undefined",
         "-fno-omit-frame-pointer", "-g", "-O1", f"-I{SRC}", "-isystem", str(CRYPTO)]
sys.path.insert(0, str(ROOT / "software" / "reference"))
sys.path.insert(0, str(ROOT / "software" / "laptop"))


def setUpModule():
    global BUILD
    BUILD = tempfile.TemporaryDirectory()


def tearDownModule():
    BUILD.cleanup()


def _object(source, warnings):
    obj = Path(BUILD.name) / (source.parent.name + "_" + source.stem + ".o")
    if not obj.exists():
        built = subprocess.run([COMPILER, *FLAGS, *warnings, "-c", str(source), "-o", str(obj)],
                               capture_output=True, text=True)
        if built.returncode:
            raise AssertionError(f"C++ build failed in {source.name}:\n{built.stderr[-4000:]}")
    return obj


def native(check, *firmware, crypto=False):
    """Build tests/native/<check>.cpp with the named firmware/src units under ASan/UBSan; return its path."""
    if not COMPILER:
        raise unittest.SkipTest("C++ compiler unavailable")
    if crypto and not (CRYPTO / ".wici-stamp").exists():
        raise unittest.SkipTest("pinned Crypto sources unavailable (firmware/tools/stack_deps.py)")
    strict = ["-Wall", "-Wextra", "-Werror"]
    jobs = [(SRC / f"{name}.cpp", strict) for name in firmware] + [(NATIVE / f"{check}.cpp", strict)]
    jobs += [(CRYPTO / unit, ["-w"]) for unit in UNITS] if crypto else []
    with ThreadPoolExecutor() as pool:
        objects = list(pool.map(lambda job: _object(*job), jobs))
    binary = Path(BUILD.name) / check
    built = subprocess.run([COMPILER, *FLAGS, *map(str, objects), "-o", str(binary)], capture_output=True, text=True)
    if built.returncode:
        raise AssertionError(f"C++ link failed for {check}:\n{built.stderr[-4000:]}")
    return binary


def run(binary, *args, stdin=None):
    return subprocess.run([str(binary), *args], input=stdin, check=True, capture_output=True, text=True).stdout


RELAY = ("wici_relay", "wici_seen", "wici_link", "sha2")
DURABLE = ("envelope_counter", "envelope_parts", "envelope_replay", "sha2")


class NativeWiciLink(unittest.TestCase):
    def test_pairwise_hop_auth_rejects_spoofed_or_untagged_unicast(self):
        run(native("wici_hop_auth_check", "wici_hop_auth", "envelope", "wici_link", "sha2", "envelope_counter",
                   crypto=True))

    def test_root_kiss_gateway_requires_matching_timely_hack(self):
        run(native("wici_gateway_check", "wici_gateway", "wici_route", "wici_flood", "wici_seq", "wici_link",
                   "kiss", "sha2", "wici_epoch", "wici_beacon", crypto=True))

    def test_shelter_radio_coordinator_hack_retry_and_restart(self):
        run(native("wici_radio_check", "wici_radio", "wici_destination", "wici_hop", "wici_flood", "wici_route",
                   "wici_seq", "wici_origin", "wici_epoch", "wici_beacon", "envelope", *RELAY, *DURABLE[:3],
                   crypto=True))

    def test_durable_envelope_flood_ring(self):
        run(native("wici_flood_check", "wici_flood"))

    def test_relay_hop_coordinator_crash_retry_and_hack(self):
        run(native("wici_hop_check", "wici_hop", "wici_flood", "wici_route", "wici_seq", *RELAY))

    def test_durable_link_sequence_reservation(self):
        run(native("wici_seq_check", "wici_seq"))

    def test_memory_bearer_one_relay_crash_and_return_route(self):
        run(native("wici_network_check", "wici_route", *RELAY))

    def test_durable_wici_down_routes_and_parent_rank(self):
        run(native("wici_route_check", "wici_route"))

    def test_durable_wici_relay_queue(self):
        run(native("wici_relay_check", *RELAY))

    def test_wici_link_mac_and_frame_filter(self):
        lines = run(native("wici_link_check", "wici_link", "sha2")).splitlines()
        ifac = bytes(range(16))
        prk = hmac.digest((100).to_bytes(2, "big"), ifac, "sha256")
        key = hmac.digest(prk, b"WICI link v2\x01", "sha256")
        header = bytes.fromhex("8100640004") + bytes.fromhex("000107123400")
        body = bytes(range(25))
        unsigned = header + body + bytes(64)
        expected = unsigned + hmac.digest(key, unsigned, "sha256")[:8]
        self.assertEqual(lines, [key.hex(), expected.hex()])
        from wici.stanowisko import wici_link
        frame = wici_link.Frame(wici_link.DATA, wici_link.ACKREQ, 100, 4, 1, 0, 7, 0x1234, body)
        self.assertEqual(wici_link.derive_key(ifac, 100), key)
        self.assertEqual(wici_link.encode(key, frame), expected)
        self.assertEqual(wici_link.decode(key, 100, expected), frame)
        stream = wici_link.KissStream()
        packed = wici_link.kiss_encode(expected)
        self.assertEqual(stream.feed(packed[:13]), [])
        self.assertEqual(stream.feed(packed[13:]), [expected])
        with self.assertRaises(wici_link.LinkError):
            wici_link.decode(key, 100, expected[:13] + bytes([expected[13] ^ 1]) + expected[14:])
        self.assertEqual(wici_link.KissStream().feed(bytes([0xC0, 0, 0xDB, 0x00, 0xC0])), [])
        sent, admitted = [], []
        receiver = wici_link.Receiver(100, 1, key, sent.append, admitted.append)
        self.assertEqual(receiver.feed(packed), 1)
        self.assertEqual(admitted, [body])
        hack_wire, = wici_link.KissStream().feed(sent[0])
        hack = wici_link.decode(key, 100, hack_wire)
        self.assertEqual((hack.kind, hack.source, hack.destination, hack.sequence),
                         (wici_link.HACK, 1, 4, 0x1234))
        failed = wici_link.Receiver(100, 1, key, sent.append, lambda _: (_ for _ in ()).throw(OSError()))
        self.assertEqual(failed.feed(packed), 0)
        self.assertEqual(len(sent), 1)


class CrossLanguageEnvelope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import envelope
            from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
        except ImportError as exc:
            raise unittest.SkipTest(f"cryptography dependency unavailable: {exc}") from exc
        cls.envelope, cls.ed25519, cls.x25519 = envelope, ed25519, x25519

    def test_origin_signature_matches_python(self):
        signature = run(native("wici_origin_check", "wici_origin", crypto=True)).strip()
        from wici.stanowisko.wici_link import origin_message
        payload = bytes([0x40, 0, 4, 0, 2]) + bytes(20)
        expected = self.ed25519.Ed25519PrivateKey.from_private_bytes(bytes(range(32, 64))).sign(
            origin_message(100, payload))
        self.assertEqual(signature, expected.hex())

    def test_durable_station_fragment_slot(self):
        run(native("envelope_parts_check", "envelope_parts", "sha2"))

    def test_counter_reservation_survives_restart_and_write_failure(self):
        run(native("envelope_counter_check", "envelope_counter", "sha2"))

    def test_vectors_authentication_and_reserved_kinds(self):
        envelope = self.envelope
        a, b = bytes(range(32)), bytes(range(32, 64))
        bp = self.x25519.X25519PrivateKey.from_private_bytes(b).public_key().public_bytes_raw()
        key = envelope.derive_key(a, bp, 0x1234, 10, 20, own_id=10)
        whole, = envelope.seal(key, 10, 20, 7, b"[1,1,2]", 236)
        first, second = envelope.seal(key, 10, 20, 0xFFFFFFFF, bytes(range(256)), 153)
        # Kind type 1 (formerly "TEST łącza") and 15 are reserved: correctly encrypted, still rejected.
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
        reserved = []
        for kind in (0x41, 0x4F):
            header = bytes([kind]) + whole[1:9]
            reserved.append(header + ChaCha20Poly1305(key).encrypt(envelope._nonce(header), b"[1,1,2]", header))
            with self.assertRaises(envelope.EnvelopeError):
                envelope.open_part(key, reserved[-1])
        binary = native("envelope_check", "envelope", "wici_link", "wici_destination", *DURABLE, crypto=True)
        actual = dict(line.split("=", 1) for line in run(binary, *(f.hex() for f in reserved)).splitlines())
        self.assertEqual(actual, {"key": key.hex(), "whole": whole.hex(), "first": first.hex(),
                                  "second": second.hex(), "reserved": "rejected"})

    def test_fragment_admission_matches_receiver_inbox(self):
        import sqlite3
        from wici.stanowisko import envelope_inbox
        # (counter, part, time s, plaintext, station result, receiver result)
        steps = (
            (7, 2, 100, b"world", "partial", "partial"),
            (7, 2, 101, b"world", "partial", "partial"),          # identical repeat: HACK again
            (7, 2, 101, b"other", "rejected", "rejected"),        # conflicting content
            (7, 1, 102, b"hello ", "complete", "complete"),
            (7, 1, 103, b"hello ", "duplicate", "duplicate"),     # replay bit proves admission
            (8, 1, 200, b"a", "partial", "partial"),
            (8, 2, 321, b"b", "partial", "partial"),              # 121 s: the first part expired
            (8, 1, 441, b"a", "complete", "complete"),            # 120 s is still in time
            (9, 1, 500, b"x", "partial", "partial"),
            (9, 2, 400, b"y", "partial", "partial"),              # clock went back: pending part expired
            (9, 1, 401, b"x", "complete", "complete"),
            (80, 1, 402, b"z", "partial", "partial"),
            (80, 2, 403, b"w", "complete", "complete"),
            (16, 1, 404, b"q", "rejected", "rejected"),           # 64 below the highest: outside the window
            (17, 1, 405, b"q", "partial", "partial"),
            # Documented capacity difference (transport.md): the station keeps one pending
            # message per receiver identity, the receiver up to four per station.
            (18, 1, 406, b"r", "rejected", "partial"),
        )
        station = run(native("envelope_fragments_check", *DURABLE[1:]),
                      stdin="".join(f"{c} {n} {t} {d.hex()}\n" for c, n, t, d, _, _ in steps)).split()
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        inbox = envelope_inbox.Inbox(db, 100, lambda: True)
        receiver = []
        for counter, number, now, data, _, _ in steps:
            try:
                receiver.append(inbox.receive(self.envelope.Part(2, 4, counter, 0, number, data), now,
                                              lambda full: None))
            except self.envelope.EnvelopeError:
                receiver.append("rejected")
        self.assertEqual(station, [s for *_, s, _ in steps])
        self.assertEqual(receiver, [r for *_, r in steps])


if __name__ == "__main__":
    unittest.main()
