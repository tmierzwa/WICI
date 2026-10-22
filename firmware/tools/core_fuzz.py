# SPDX-License-Identifier: MIT
"""Fuzz the station Reticulum core with libFuzzer (tests/native/rnscore_fuzz.cpp).

Builds the core and the Crypto units it uses (tools/stack_deps.py) with clang, -fsanitize=fuzzer and
ASan with UBSan, writes a seed corpus from tests/vectors (announces, packets, proofs, IFAC datagrams,
LXMF messages, a known destination followed by packets through the station, damaged table slots) and
runs the target for the given time. A crash leaves its input in <out>/crashes and the exit code is not
zero; `--replay FILE` runs one input again. Without libFuzzer (Apple clang) `--driver` builds the
target with its own main, which replays the corpus and mutates it for the same time (simpler, no
coverage). firmware/reticulum-core.md, acceptance criterion 4.

    python3 tools/core_fuzz.py --seconds 60 --out /tmp/fuzz
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

FIRMWARE = Path(__file__).resolve().parents[1]
ROOT = FIRMWARE.parent
CORE = FIRMWARE / "lib" / "reticulum_core" / "src"
STACK = FIRMWARE / ".pio" / "stack"
TARGET = ROOT / "tests" / "native" / "rnscore_fuzz.cpp"
VECTORS = ROOT / "tests" / "vectors"
# Z biblioteki Crypto tylko to, czego rdzeń używa (jak tests/test_rnscore.py).
CRYPTO_UNITS = ["AES256.cpp", "AESCommon.cpp", "BigNumberUtil.cpp", "BlockCipher.cpp", "ChaCha.cpp", "Cipher.cpp", "Crypto.cpp",
                "Curve25519.cpp", "Ed25519.cpp", "Hash.cpp", "NoiseSource.cpp", "RNG.cpp", "SHA256.cpp", "SHA512.cpp"]
SANITIZE = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer", "-g", "-O1"]
# Rodzaje rekordów wejścia (rnscore_fuzz.cpp).
INBOUND, IFAC, LXMF, POLL, TABLE, OWN = range(6)
SECOND = 0x80   # bit rodzaju: przez interfejs 1 (USB)
# Pierwszy bajt POLL: bit 0 łącze wolne, bity 1 i 2 odmowa interfejsu 0 i 1 w mayTransmit.
FREE, FREE_REFUSING_1, FREE_REFUSING_0 = b"\x01", b"\x05", b"\x03"
DAY = 255

sys.path.insert(0, str(FIRMWARE / "tools"))
import stack_deps  # noqa: E402


def record(kind: int, data: bytes = b"", step: int = 0) -> bytes:
    return bytes([kind, step]) + len(data).to_bytes(2, "little") + data


def source_array(source: str, name: str) -> bytes:
    body = re.search(rf"{name}\[[^\]]*\] = \{{([^}}]*)\}};", source).group(1)
    return bytes(int(x, 16) for x in re.findall(r"0x([0-9a-f]{2})", body))


def check_keys() -> None:
    """The keys in rnscore_fuzz.cpp are the ones of the vectors (otherwise the corpus checks nothing)."""
    reticulum = json.loads((VECTORS / "reticulum.json").read_text())
    lxmf = json.loads((VECTORS / "lxmf.json").read_text())["lxmf"]
    source = TARGET.read_text()
    expected = {"STATION_KEY": reticulum["identity"][0]["private_key"], "IFAC_KEY": reticulum["ifac"]["ifac_key"],
                "SENDER_KEY": lxmf["sender_public_key"], "LXMF_DESTINATION": lxmf["destination_hash"]}
    for name, value in expected.items():
        if source_array(source, name) != bytes.fromhex(value):
            raise SystemExit(f"{TARGET.name}: {name} differs from tests/vectors")
    if int(reticulum["ifac"]["ifac_size"]) != 16:
        raise SystemExit("tests/vectors: ifac_size is not 16 (rnscore_fuzz.cpp)")


def corpus(out: Path) -> int:
    reticulum = json.loads((VECTORS / "reticulum.json").read_text())
    lxmf = json.loads((VECTORS / "lxmf.json").read_text())["lxmf"]
    seeds = []
    announces = [bytes.fromhex(a["raw"]) for a in reticulum["announce"]]
    seeds += [record(INBOUND, raw) for raw in announces]
    raws = [bytes.fromhex(p[h]["raw"]) for p in reticulum["packet"] for h in ("header_1", "header_2") if h in p]
    seeds += [record(INBOUND, raw) for raw in raws]
    proof = reticulum["proof"]
    seeds += [record(INBOUND, bytes.fromhex(proof[k])) for k in ("packet", "implicit_packet", "explicit_packet")]
    seeds += [record(IFAC, bytes.fromhex(c["wire"])) for c in reticulum["ifac"]["checked"]]
    received = lxmf["received"]
    seeds += [record(LXMF, bytes.fromhex(m["data"])) for m in received[:: max(1, len(received) // 64)]]
    # Znany cel (ważne ogłoszenie), potem pakiety do niego i przez stację, wygasanie po dobach, własne pakiety.
    known = [a for a in reticulum["announce"] if a["valid"] and a["name"] == "plain"][0]
    destination = bytes.fromhex(known["raw"])[2:18]
    packets = b"".join(record(INBOUND, raw) for raw in raws)
    seeds.append(record(INBOUND, bytes.fromhex(known["raw"])) + packets + record(POLL, b"\x01", 50)
                 + record(OWN, b"\x00" + destination + b"report") + record(OWN, b"\x01" + destination)
                 + record(OWN, b"\x02" + bytes(16)) + record(POLL, b"\x01", DAY) + record(POLL, b"\x01", DAY))
    # Dwa interfejsy: ogłoszenie przez P1 z odmową USB (zaległa retransmisja), potem przez USB z odmową P1,
    # zapytania i pakiet przez stację przyjęte przez USB, wreszcie oba wolne.
    seeds.append(record(INBOUND, bytes.fromhex(known["raw"])) + record(POLL, FREE_REFUSING_1, 50)
                 + record(POLL, FREE_REFUSING_1, 50) + record(POLL, FREE, 10)
                 + record(INBOUND | SECOND, bytes.fromhex(known["raw"]), 50) + record(POLL, FREE_REFUSING_0, 50)
                 + b"".join(record(INBOUND | SECOND, raw) for raw in raws) + record(POLL, FREE, 50)
                 + record(OWN, b"\x01" + destination) + record(POLL, FREE_REFUSING_0, 50) + record(POLL, FREE, DAY))
    # Pakiet do celu "lxmf.delivery" stacji (odszyfrowanie na wrogich danych), przekazanie przez stację
    # (HEADER_2, transport: tożsamość stacji) do znanego celu i dowód wracający przez tablicę odwrotną.
    identity = reticulum["identity"][0]
    station = bytes.fromhex(identity["hash"])
    address = hashlib.sha256(hashlib.sha256(b"lxmf.delivery").digest()[:10] + station).digest()[:16]
    seeds.append(record(INBOUND, b"\x00\x00" + address + b"\x00" + bytes(range(96))))
    through = b"\x50\x01" + station + destination + b"\x00" + b"through the station"
    proved = hashlib.sha256(bytes([through[0] & 0x0F]) + through[18:]).digest()[:16]
    seeds.append(record(INBOUND, bytes.fromhex(known["raw"])) + record(INBOUND, through, 10)
                 + record(INBOUND, b"\x03\x00" + proved + b"\x00" + bytes(64), 10) + record(POLL, b"\x01", 50))
    # Wroga treść tablicy: zatwierdzony nagłówek gniazda 0 (znacznik 0xA5, format 2) i przypadkowe bajty.
    seeds.append(record(INBOUND, bytes.fromhex(known["raw"])) + record(TABLE, bytes(3) + b"\xa5\x02" + bytes(range(64)))
                 + packets)
    seeds.append(record(TABLE, b"\x00\x02\x38" + b"\xa5\x02\x01\x00" + b"\xff" * 120))
    out.mkdir(parents=True, exist_ok=True)
    for n, seed in enumerate(seeds):
        (out / f"seed-{n:03d}").write_bytes(seed)
    return len(seeds)


def build(out: Path, cxx: str, driver: bool) -> Path:
    if not (STACK / "Crypto" / ".wici-stamp").is_file():
        stack_deps.fetch(FIRMWARE)
    coverage = [] if driver else ["-fsanitize=fuzzer-no-link"]
    base = [cxx, "-std=c++17", *SANITIZE, f"-I{CORE}", "-isystem", str(STACK / "Crypto")]
    objects = []
    for source in sorted(CORE.glob("*.cpp")):
        objects.append(out / f"core_{source.stem}.o")
        subprocess.run([*base, *coverage, "-fno-exceptions", "-fno-rtti", "-Wall", "-Wextra", "-Werror", "-c", str(source),
                        "-o", str(objects[-1])], check=True, capture_output=True, text=True)
    for name in CRYPTO_UNITS:
        objects.append(out / f"crypto_{Path(name).stem}.o")
        subprocess.run([*base, "-w", "-c", str(STACK / "Crypto" / name), "-o", str(objects[-1])], check=True,
                       capture_output=True, text=True)
    target = ["-DWICI_FUZZ_DRIVER"] if driver else ["-fsanitize=fuzzer"]
    binary = out / "rnscore_fuzz"
    subprocess.run([*base, *target, "-Wall", "-Wextra", "-Werror", str(TARGET), *map(str, objects), "-o", str(binary)],
                   check=True, capture_output=True, text=True)
    return binary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--out", help="directory for the corpus and crashes (default: temporary)")
    parser.add_argument("--driver", action="store_true", help="own main instead of libFuzzer (no coverage)")
    parser.add_argument("--replay", help="run one input (a crash file) and exit")
    parser.add_argument("--cxx", default=os.environ.get("CXX", "clang++"))
    args = parser.parse_args()
    if not shutil.which(args.cxx):
        raise SystemExit(f"no {args.cxx}")
    check_keys()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(args.out).resolve() if args.out else Path(tmp)
        objects = out / "build"
        objects.mkdir(parents=True, exist_ok=True)
        try:
            binary = build(objects, args.cxx, args.driver or bool(args.replay))
        except subprocess.CalledProcessError as e:
            print(f"{' '.join(e.cmd)}\n{e.stderr[-4000:]}", file=sys.stderr)
            return 2
        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1", UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
        if args.replay:
            return subprocess.run([str(binary), args.replay], env=env).returncode
        seeds = corpus(out / "corpus")
        crashes = out / "crashes"
        crashes.mkdir(exist_ok=True)
        if args.driver:
            files = sorted(str(p) for p in (out / "corpus").iterdir())
            code = subprocess.run([str(binary), "--mutate", str(args.seconds), *files], env=env).returncode
        else:
            code = subprocess.run([str(binary), str(out / "corpus"), f"-max_total_time={args.seconds}", "-max_len=4096",
                                   "-timeout=10", "-rss_limit_mb=2048", "-print_final_stats=1",
                                   f"-artifact_prefix={crashes}/"], env=env).returncode
        found = sorted(p.name for p in crashes.iterdir())
        print(json.dumps({"seeds": seeds, "seconds": args.seconds, "exit": code, "crashes": found}))
        return 1 if code or found else 0


if __name__ == "__main__":
    sys.exit(main())
