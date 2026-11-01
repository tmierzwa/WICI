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
        radio = bytes.fromhex(run(native("wici_hop_auth_check", "wici_hop_auth", "envelope", "wici_link", "sha2",
                                         "envelope_counter", crypto=True)).strip())
        # K_hop = HKDF(X25519 secret, salt = net_id || 0x02, info = "WICI hop v1" || ids || public keys),
        # tag = HMAC(K_hop, "WICI hop tag v1" || frame) (docs/spec/wici-link.md).
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import x25519
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        a = x25519.X25519PrivateKey.from_private_bytes(bytes([8]) + bytes(30) + bytes([0x40]))
        b = x25519.X25519PrivateKey.from_private_bytes(bytes([16]) + bytes(30) + bytes([0x40]))
        public = [k.public_key().public_bytes_raw() for k in (a, b)]
        info = b"WICI hop v1" + (1).to_bytes(2, "big") + (2).to_bytes(2, "big") + public[0] + public[1]
        shared = a.exchange(x25519.X25519PublicKey.from_public_bytes(public[1]))
        key = HKDF(hashes.SHA256(), 32, (100).to_bytes(2, "big") + b"\x02", info).derive(shared)
        self.assertEqual(radio[-8:], hmac.digest(key, b"WICI hop tag v1" + radio[:-8], "sha256")[:8])

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
            # Identical repeat. The station reports a duplicate and rate-limits its HACK
            # (wici_destination.cpp, 5 s); the receiver HACKs it again.
            (7, 2, 101, b"world", "duplicate", "partial"),
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
                receiver.append(inbox.receive(self.envelope.Part(2, 4, counter, 0, number, data), bytes(32), now,
                                              lambda full: None))
            except self.envelope.EnvelopeError:
                receiver.append("rejected")
        self.assertEqual(station, [s for *_, s, _ in steps])
        self.assertEqual(receiver, [r for *_, r in steps])

    def test_small_order_keys_are_refused_at_provisioning(self):
        from wici import configdoc
        weak = sorted(configdoc.SMALL_ORDER)
        p = 2**255 - 19
        # Every listed X25519 value gives an all-zero shared secret, also with bit 255 set.
        scalar = self.x25519.X25519PrivateKey.from_private_bytes(bytes(range(32)))
        for point in weak:
            if point in _ED25519_ONLY:
                continue
            for value in (point, point[:31] + bytes([point[31] | 0x80])):
                with self.subTest(x25519=value.hex()), self.assertRaises(ValueError):
                    scalar.exchange(self.x25519.X25519PublicKey.from_public_bytes(value))
        # The eight Ed25519 torsion points (and y = p, p + 1) are all listed.
        for point in _torsion():
            self.assertTrue(configdoc.small_order(point), point.hex())
        for y in (p, p + 1):
            self.assertTrue(configdoc.small_order(y.to_bytes(32, "little")))
        honest = self.ed25519.Ed25519PrivateKey.from_private_bytes(bytes(32)).public_key().public_bytes_raw()
        samples = [*weak, *(w[:31] + bytes([w[31] | 0x80]) for w in weak), honest, bytes(range(32))]
        binary = native("envelope_keys_check", "config", "jsonlite", "sa1", "sha2")
        flags = run(binary, "--small", stdin="".join(s.hex() + "\n" for s in samples)).split()
        self.assertEqual(flags, ["1" if configdoc.small_order(s) else "0" for s in samples])
        self.assertEqual(flags[-2:], ["0", "0"])

        def card(x_private, ed_private, number):
            key = (self.x25519.X25519PrivateKey.from_private_bytes(x_private).public_key().public_bytes_raw() +
                   self.ed25519.Ed25519PrivateKey.from_private_bytes(ed_private).public_key().public_bytes_raw())
            return {"lxmf": configdoc.destination(key, "lxmf.delivery").hex(), "key": key.hex(), "id": number,
                    "net_id": 100, "x25519": key[:32].hex()}

        network = {"id": 100, "station": 4, "root": 1, "parent": 1, "backup_parent": 0,
                   "receiver_main": 2, "receiver_backup": 3}
        neighbour = {"id": 1, "ed25519": honest.hex(), "x25519": "cd" * 32}
        station = {"role": "stacja", "addresses": ["Szkoła"], "stations": 2, "phrases": [], "ifac": "11" * 16,
                   "radio": {"profile": "p1"}, "network": network, "priority_keys": [neighbour],
                   "receiver": {"main": card(bytes([1] * 32), bytes([2] * 32), 2),
                                "backup": card(bytes([3] * 32), bytes([4] * 32), 3)}}
        identity = "01" + "00" * 31
        weak_backup = dict(station["receiver"]["backup"])
        weak_backup["key"] = weak_backup["key"][:64] + identity     # identity point as the Ed25519 half
        weak_backup["lxmf"] = configdoc.destination(bytes.fromhex(weak_backup["key"]), "lxmf.delivery").hex()
        cases = (
            (station, "ok", []),
            (dict(station, priority_keys=[dict(neighbour, ed25519=identity)]), "priority_keys", ["priority_keys.0"]),
            (dict(station, priority_keys=[dict(neighbour, x25519="00" * 32)]), "priority_keys", ["priority_keys.0"]),
            (dict(station, receiver=dict(station["receiver"], backup=weak_backup)), "receiver",
             ["receiver.backup.key"]),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configure.json"
            for doc, detail, fields in cases:
                path.write_bytes(configdoc.encode(doc))
                with self.subTest(detail=detail):
                    self.assertEqual(run(binary, str(path), "p1").strip(), detail)
                    self.assertEqual([field for field, _ in configdoc.check(doc)], fields)


# Ed25519-only entries of SMALL_ORDER: order-8 points that are ordinary X25519 values.
_ED25519_ONLY = frozenset(bytes.fromhex(h) for h in (
    "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a",
    "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05"))


def _torsion():
    """Encodings of the eight Ed25519 points of order dividing 8, computed from scratch."""
    p = 2**255 - 19
    d = -121665 * pow(121666, p - 2, p) % p

    def add(a, b):
        t = d * a[0] * b[0] * a[1] * b[1] % p
        return ((a[0] * b[1] + b[0] * a[1]) * pow(1 + t, p - 2, p) % p,
                (a[1] * b[1] + a[0] * b[0]) * pow(1 - t, p - 2, p) % p)

    # Decode the listed order-8 point (RFC 8032, 5.1.3), then check that it generates eight points.
    i = pow(2, (p - 1) // 4, p)
    y = int.from_bytes(bytes.fromhex("c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a"), "little")
    x2 = (y * y - 1) * pow(d * y * y + 1, p - 2, p) % p
    x = pow(x2, (p + 3) // 8, p)
    if (x * x - x2) % p:
        x = x * i % p
    assert (x * x - x2) % p == 0
    order8, point, points = (x, y), (0, 1), []
    for _ in range(8):
        points.append(point)
        point = add(point, order8)
    assert point == (0, 1) and len(set(points)) == 8 and add(add(order8, order8), add(order8, order8)) != (0, 1)
    return [(y | (x & 1) << 255).to_bytes(32, "little") for x, y in points]


if __name__ == "__main__":
    unittest.main()
