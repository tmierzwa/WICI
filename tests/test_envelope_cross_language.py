# SPDX-License-Identifier: MIT
"""Compare the fixed-buffer MCU envelope with the Python reference, byte for byte."""

from pathlib import Path
import hmac
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "firmware" / "src"
CRYPTO = ROOT / "firmware" / ".pio" / "stack" / "Crypto"
UNITS = ("AuthenticatedCipher.cpp", "BigNumberUtil.cpp", "ChaCha.cpp", "ChaChaPoly.cpp", "Cipher.cpp",
         "Crypto.cpp", "Curve25519.cpp", "Ed25519.cpp", "Hash.cpp", "NoiseSource.cpp", "Poly1305.cpp",
         "RNG.cpp", "SHA256.cpp", "SHA512.cpp")
sys.path.insert(0, str(ROOT / "software" / "reference"))


class CrossLanguageEnvelope(unittest.TestCase):
    def test_origin_signature_matches_python(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler or not (CRYPTO / ".wici-stamp").exists():
            raise unittest.SkipTest("C++ compiler or pinned Crypto sources unavailable")
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from software.laptop.wici.stanowisko.wici_link import origin_message
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "origin_check"
            command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-error=cpp",
                       "-fsanitize=address,undefined", f"-I{SRC}",
                       f"-I{ROOT / 'firmware' / 'lib' / 'reticulum_core' / 'src'}",
                       "-isystem", str(CRYPTO),
                       str(SRC / "wici_origin.cpp"),
                       *(str(ROOT / "firmware" / "lib" / "reticulum_core" / "src" / name)
                         for name in ("identity.cpp", "hash.cpp")),
                       str(ROOT / "tests" / "native" / "wici_origin_check.cpp"),
                       *(str(CRYPTO / unit) for unit in UNITS), "-o", str(binary)]
            built = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr[-4000:])
            checked = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            signature = checked.stdout.strip()
        envelope = bytes([0x40, 0, 4, 0, 2]) + bytes(20)
        expected = ed25519.Ed25519PrivateKey.from_private_bytes(bytes(range(32, 64))).sign(
            origin_message(100, envelope))
        self.assertEqual(signature, expected.hex())

    def test_root_kiss_gateway_requires_matching_timely_hack(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "gateway_check"
            command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                       "-fsanitize=address,undefined", f"-I{SRC}",
                       *(str(SRC / name) for name in ("wici_gateway.cpp", "wici_route.cpp", "wici_flood.cpp", "wici_seq.cpp",
                                                      "wici_link.cpp", "kiss.cpp", "sha2.cpp")),
                       str(ROOT / "tests" / "native" / "wici_gateway_check.cpp"), "-o", str(binary)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_shelter_radio_coordinator_hack_retry_and_restart(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler or not (CRYPTO / ".wici-stamp").exists():
            raise unittest.SkipTest("C++ compiler or pinned Crypto sources unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "radio_check"
            sanitizer = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g", "-O1"]
            base = [compiler, "-std=c++17", "-fno-exceptions", "-fno-rtti", *sanitizer,
                    f"-I{SRC}", f"-I{ROOT / 'firmware' / 'lib' / 'reticulum_core' / 'src'}",
                    "-isystem", str(CRYPTO)]
            sources = [SRC / name for name in (
                "wici_radio.cpp", "wici_destination.cpp", "wici_hop.cpp", "wici_flood.cpp",
                "wici_relay.cpp", "wici_seen.cpp", "wici_route.cpp", "wici_seq.cpp",
                "wici_link.cpp", "envelope.cpp", "envelope_counter.cpp", "envelope_parts.cpp", "envelope_replay.cpp",
                "sha2.cpp", "wici_origin.cpp")]
            sources += [ROOT / "firmware" / "lib" / "reticulum_core" / "src" / name
                        for name in ("identity.cpp", "hash.cpp")]
            sources += [ROOT / "tests" / "native" / "wici_radio_check.cpp"]
            sources += [CRYPTO / unit for unit in UNITS]
            objects = []
            for index, source in enumerate(sources):
                obj = Path(directory) / f"unit{index}.o"
                warnings = ["-Wall", "-Wextra", "-Werror"] if index < 15 else ["-w"]
                built = subprocess.run([*base, *warnings, "-c", str(source), "-o", str(obj)],
                                       capture_output=True, text=True)
                if built.returncode:
                    self.fail(f"C++ radio build failed in {source.name}:\n{built.stderr[-4000:]}")
                objects.append(obj)
            built = subprocess.run([compiler, *sanitizer, *(str(obj) for obj in objects), "-o", str(binary)],
                                   capture_output=True, text=True)
            if built.returncode:
                self.fail(f"C++ radio link failed:\n{built.stderr[-4000:]}")
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_durable_station_fragment_slot(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "parts_check"
            command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                       f"-I{SRC}", str(SRC / "envelope_parts.cpp"),
                       str(ROOT / "tests" / "native" / "envelope_parts_check.cpp"), "-o", str(binary)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_durable_envelope_flood_ring(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "flood_check"
            command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                       f"-I{SRC}", str(SRC / "wici_flood.cpp"),
                       str(ROOT / "tests" / "native" / "wici_flood_check.cpp"), "-o", str(binary)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_relay_hop_coordinator_crash_retry_and_hack(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "hop_check"
            command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                       f"-I{SRC}", str(SRC / "wici_hop.cpp"), str(SRC / "wici_flood.cpp"), str(SRC / "wici_relay.cpp"),
                       str(SRC / "wici_seen.cpp"), str(SRC / "wici_route.cpp"), str(SRC / "wici_seq.cpp"),
                       str(SRC / "wici_link.cpp"), str(SRC / "sha2.cpp"),
                       str(ROOT / "tests" / "native" / "wici_hop_check.cpp"), "-o", str(binary)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_durable_link_sequence_reservation(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "seq_check"
            command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                       f"-I{SRC}", str(SRC / "wici_seq.cpp"),
                       str(ROOT / "tests" / "native" / "wici_seq_check.cpp"), "-o", str(binary)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_memory_bearer_one_relay_crash_and_return_route(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "network_check"
            command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                       f"-I{SRC}", str(SRC / "wici_relay.cpp"), str(SRC / "wici_seen.cpp"),
                       str(SRC / "wici_route.cpp"), str(SRC / "wici_link.cpp"), str(SRC / "sha2.cpp"),
                       str(ROOT / "tests" / "native" / "wici_network_check.cpp"), "-o", str(binary)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_durable_wici_down_routes_and_parent_rank(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "route_check"
            command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                       f"-I{SRC}", str(SRC / "wici_route.cpp"),
                       str(ROOT / "tests" / "native" / "wici_route_check.cpp"), "-o", str(binary)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_durable_wici_relay_queue(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "relay_check"
            command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                       f"-I{SRC}", str(SRC / "wici_relay.cpp"), str(SRC / "wici_seen.cpp"), str(SRC / "wici_link.cpp"),
                       str(SRC / "sha2.cpp"), str(ROOT / "tests" / "native" / "wici_relay_check.cpp"),
                       "-o", str(binary)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_wici_link_mac_and_frame_filter(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "link_check"
            command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                       f"-I{SRC}", str(SRC / "wici_link.cpp"), str(SRC / "sha2.cpp"),
                       str(ROOT / "tests" / "native" / "wici_link_check.cpp"), "-o", str(binary)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            lines = subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout.splitlines()
        ifac = bytes(range(16))
        salt = (100).to_bytes(2, "big")
        prk = hmac.digest(salt, ifac, "sha256")
        key = hmac.digest(prk, b"WICI link v2\x01", "sha256")
        header = bytes.fromhex("8100640004") + bytes.fromhex("000107123400")
        body = bytes(range(25))
        unsigned = header + body + bytes(64)
        expected = unsigned + hmac.digest(key, unsigned, "sha256")[:8]
        self.assertEqual(lines, [key.hex(), expected.hex()])
        sys.path.insert(0, str(ROOT / "software" / "laptop"))
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

    def test_counter_reservation_survives_restart_and_write_failure(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "counter_check"
            command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                       f"-I{SRC}", str(SRC / "envelope_counter.cpp"),
                       str(ROOT / "tests" / "native" / "envelope_counter_check.cpp"), "-o", str(binary)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_vectors_and_authentication(self):
        try:
            import envelope
        except ImportError as exc:
            raise unittest.SkipTest(f"cryptography dependency unavailable: {exc}") from exc
        compiler = shutil.which("clang++") or shutil.which("g++")
        if not compiler or not (CRYPTO / ".wici-stamp").exists():
            raise unittest.SkipTest("C++ compiler or pinned Crypto sources unavailable")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "envelope_check"
            sanitizer = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g", "-O1"]
            base = [compiler, "-std=c++17", "-fno-exceptions", "-fno-rtti", *sanitizer,
                    f"-I{SRC}", "-isystem", str(CRYPTO)]
            objects = []
            sources = [SRC / "envelope.cpp", SRC / "sha2.cpp", SRC / "envelope_counter.cpp", SRC / "envelope_replay.cpp",
                       SRC / "envelope_parts.cpp", SRC / "wici_link.cpp", SRC / "wici_destination.cpp",
                       ROOT / "tests" / "native" / "envelope_check.cpp",
                       *(CRYPTO / unit for unit in UNITS)]
            for index, source in enumerate(sources):
                obj = Path(directory) / f"unit{index}.o"
                warnings = ["-Wall", "-Wextra", "-Werror"] if index < 8 else ["-w"]
                built = subprocess.run([*base, *warnings, "-c", str(source), "-o", str(obj)],
                                       capture_output=True, text=True)
                if built.returncode:
                    self.fail(f"C++ envelope build failed in {source.name}:\n{built.stderr[-4000:]}")
                objects.append(obj)
            built = subprocess.run([compiler, *sanitizer, *(str(obj) for obj in objects), "-o", str(binary)],
                                   capture_output=True, text=True)
            if built.returncode:
                self.fail(f"C++ envelope link failed:\n{built.stderr[-4000:]}")
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, env=os.environ)
        actual = dict(line.split("=", 1) for line in result.stdout.splitlines())
        from cryptography.hazmat.primitives.asymmetric import x25519
        a, b = bytes(range(32)), bytes(range(32, 64))
        bp = x25519.X25519PrivateKey.from_private_bytes(b).public_key().public_bytes_raw()
        key = envelope.derive_key(a, bp, 0x1234, 10, 20, own_id=10)
        whole, = envelope.seal(key, 10, 20, 7, b"[1,1,2]", 236)
        first, second = envelope.seal(key, 10, 20, 0xFFFFFFFF, bytes(range(256)), 153)
        self.assertEqual(actual, {"key": key.hex(), "whole": whole.hex(), "first": first.hex(), "second": second.hex()})


if __name__ == "__main__":
    unittest.main()
