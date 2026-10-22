# SPDX-License-Identifier: MIT
"""Station Reticulum stack under hostile traffic, clock jumps and power loss (host, sanitizers).

Builds tests/native/rns_stress.cpp with the station's stack layer (rns_node, p1iface, framfs) and the
pinned stack sources from firmware/.pio/stack, with AddressSanitizer and UndefinedBehaviorSanitizer
and the system allocator instead of the stack's TLSF pool (the pool hides heap errors from ASan).
Each run of the program is one start of a station; FRAM, clock and identity stay in files between
runs. Scenarios: valid traffic over weeks of simulated time, mutated traffic from a node with the
network key (IFAC), power loss in any FRAM write, bit flips in FRAM and a clock set back.

Needs a C++ compiler with sanitizers and the stack sources (python3 firmware/tools/stack_deps.py,
or a PlatformIO build of any image). Without them the tests are skipped, unless WICI_RNS_SANITIZE=1
(CI), which fetches the sources and fails instead of skipping. A scenario that hits a known defect of
the port (KNOWN_DEFECTS, review of 2026-10-21) is skipped with the defect's name; any other sanitizer
report, hang or broken invariant fails. WICI_RNS_SEEDS=N runs N fuzzing seeds instead of 4.

The harness feeds every datagram through the station's own IFAC code (rnsnode::debugIfacWrap) and
checks that the port and microStore read the simulated clock; each passing run must have delivered
traffic to the stack (P1 counter rx_ok). Not simulated: microStore::millis (the compaction cooldown of
the file store) reads the host's monotonic clock, so clock jumps do not move it. POSIX only (mmap, fork
of sanitizer runtimes).

  python3 -m unittest tests.test_rns_hostile -v
"""

from concurrent.futures import ThreadPoolExecutor
import configparser
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / "firmware"
SRC = FIRMWARE / "src"
STACK = FIRMWARE / ".pio" / "stack"
HARNESS = ROOT / "tests" / "native" / "rns_stress.cpp"
REQUIRED = os.environ.get("WICI_RNS_SANITIZE") == "1"
SEEDS = int(os.environ.get("WICI_RNS_SEEDS", "4"))

sys.path.insert(0, str(FIRMWARE / "tools"))
import stack_deps  # noqa: E402

WICI_UNITS = ["framfs.cpp", "kiss.cpp", "p1frame.cpp", "p1iface.cpp", "rns_node.cpp"]
SANITIZE = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g", "-O1"]
POWER_CUT = 75
INVARIANT = 3
ENV = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:abort_on_error=0:halt_on_error=1",
           UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")


def stack_flags():
    """Stack configuration shared with the images: [stack] rns_flags from platformio.ini."""
    ini = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";",))
    ini.read(FIRMWARE / "platformio.ini")
    flags = []
    for line in ini["stack"]["rns_flags"].splitlines():
        line = line.split(";")[0].strip()
        if line and not line.startswith("-I"):
            flags.append(line)
    # Allokator systemowy zamiast puli TLSF: ASan widzi każdy blok osobno.
    return flags + ["-DNATIVE", "-DRNS_DEFAULT_ALLOCATOR=RNS_HEAP_ALLOCATOR", "-DRNS_CONTAINER_ALLOCATOR=RNS_HEAP_ALLOCATOR"]


def compiler():
    for name in ("clang++", "c++", "g++"):
        if shutil.which(name):
            return name
    return None


def sources():
    port = STACK / "microReticulum" / "src"
    stack = [p for p in port.rglob("*.cpp") if p.name != "main.cpp"] + list(port.rglob("*.c"))
    stack += sorted((STACK / "Crypto").glob("*.cpp"))
    return stack, [SRC / name for name in WICI_UNITS]


def build(out_dir: Path) -> Path:
    """Compile the stack, the station units and the harness; objects are cached in out_dir."""
    cxx = compiler()
    cc = "clang" if cxx == "clang++" else "cc"
    includes = [f"-I{SRC}", f"-I{ROOT / 'tests' / 'native'}"]
    for folder in stack_deps.INCLUDES:
        includes += ["-isystem", str(STACK / folder)]
    flags = stack_flags() + SANITIZE
    key = hashlib.sha256(" ".join([cxx] + flags + includes).encode()).hexdigest()[:12]
    objects_dir = out_dir / key
    objects_dir.mkdir(parents=True, exist_ok=True)
    stack, wici = sources()
    # Nagłówki WICI i stan łat stosu: zmiana któregoś przebudowuje wszystko.
    newest = max([p.stat().st_mtime for p in SRC.glob("*.h")] +
                 [p.stat().st_mtime for p in STACK.glob("*/.wici-stamp")])

    def compile_one(source: Path):
        rel = source.relative_to(ROOT if ROOT in source.parents else STACK)
        obj = objects_dir / (str(rel).replace("/", "_") + ".o")
        if obj.exists() and obj.stat().st_mtime > max(newest, source.stat().st_mtime):
            return obj
        quiet = ["-w"] if STACK in source.parents else ["-Wall", "-Wextra", "-Werror"]
        if source == HARNESS:
            quiet.append("-Wno-deprecated-declarations")   # generator buduje pakiety dawnym API portu
        if source.suffix == ".c":
            cmd = [cc, *flags, *includes, "-w", "-c", str(source), "-o", str(obj)]
        else:
            cmd = [cxx, "-std=gnu++17", "-fexceptions", "-frtti", *flags, *includes, *quiet, "-c", str(source), "-o", str(obj)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"{source}:\n{result.stderr[-4000:]}")
        return obj

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        objects = list(pool.map(compile_one, stack + wici + [HARNESS]))
    binary = objects_dir / "rns_stress"
    subprocess.run([cxx, *SANITIZE, *objects, "-o", str(binary)], check=True, capture_output=True, text=True)
    return binary


# Usterki portu znalezione w przeglądzie 2026-10-21: (nazwa, napisy w raporcie sanitizera). Próba,
# która trafi na jedną z nich, jest pomijana z jej nazwą, a nie zaliczana; inna awaria jest błędem
# próby. Testy test_known_defect_* sprawdzają, że usterka wciąż występuje.
# Napisy szukane w śladzie wadliwego dostępu (bez śladów zwolnienia i przydziału bloku).
KNOWN_DEFECTS = [
    ("announce-table-use-after-free", ("heap-use-after-free", "Transport::jobs()", "Transport.cpp:665")),
    ("token-without-ciphertext", ("PKCS7.h:67", "Token::decrypt")),
    ("short-announce", ("Ed25519::decodePoint", "Identity::validate_announce")),
]


def known_defect(report):
    if not report:
        return None
    access = report.split("freed by thread")[0].split("allocated by thread")[0]
    for name, markers in KNOWN_DEFECTS:
        if all(m in access for m in markers):
            return name
    return None


def sanitizer_report(stderr: str):
    for marker in ("ERROR: AddressSanitizer", "runtime error:", "ERROR: LeakSanitizer"):
        at = stderr.find(marker)
        if at >= 0:
            return stderr[max(0, at - 200):at + 6000]
    return None


class Station:
    """One station: FRAM, clock and identity files in a folder; each run() is one start."""

    def __init__(self, binary: Path, folder: Path):
        self.binary = binary
        self.fram = folder / "fram.bin"

    def run(self, *args, timeout=240):
        try:
            result = subprocess.run([str(self.binary), str(self.fram), *map(str, args)], capture_output=True, text=True,
                                    timeout=timeout, env=ENV)
        except subprocess.TimeoutExpired as e:
            raise AssertionError(f"station hangs (no result in {timeout} s): {args}") from e
        report = sanitizer_report(result.stderr)
        lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
        outcome = json.loads(lines[-1]) if lines else {}
        return result.returncode, outcome, report, result.stderr


class HostileStackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "posix":
            raise unittest.SkipTest("POSIX only (mmap)")
        if not compiler():
            raise unittest.SkipTest("no C++ compiler")
        if not all((STACK / name / ".wici-stamp").is_file() for name, *_ in stack_deps.DEPS):
            if not REQUIRED:
                raise unittest.SkipTest("stack sources not fetched (python3 firmware/tools/stack_deps.py)")
            stack_deps.fetch(FIRMWARE)
        cls.binary = build(FIRMWARE / ".pio" / "sanitize")
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def station(self):
        return Station(self.binary, Path(tempfile.mkdtemp(dir=self.tmp.name)))

    def assertClean(self, run, *allowed):
        code, outcome, report, stderr = run
        defect = known_defect(report)
        if defect:
            self.skipTest(f"blocked by known port defect: {defect}")
        self.assertIsNone(report, report)
        self.assertIn(outcome.get("result"), ("ok",) + allowed, f"exit {code}: {outcome}\n{stderr[-2000:]}")
        if outcome["result"] == "ok":
            self.assertGreater(outcome["iface"]["rx_ok"], 0, f"no traffic reached the stack: {outcome}")
        return outcome

    def test_valid_traffic_over_weeks_and_restarts(self):
        # Ruch bez mutacji, skoki zegara do 8 dni, restarty po dniu i po 30 dniach przerwy.
        s = self.station()
        first = self.assertClean(s.run("--seed", 11, "--events", 2500, "--long-jumps"))
        self.assertTrue(first["new"])
        self.assertEqual(first["iface"]["ifac_invalid"], 0, first)
        self.assertGreater(first["paths"], 5)
        second = self.assertClean(s.run("--seed", 12, "--events", 1500, "--long-jumps", "--gap", 86400))
        self.assertEqual(second["identity"], first["identity"])
        self.assertFalse(second["new"])
        self.assertClean(s.run("--seed", 13, "--events", 1500, "--gap", 30 * 86400))

    def assertDefect(self, run, name):
        report = run[2]
        self.assertIsNotNone(report, f"{name} no longer reproduces: remove it from KNOWN_DEFECTS together with this test")
        self.assertEqual(known_defect(report), name, report)

    # Usterki, które wciąż występują (przegląd 2026-10-21). Poprawka w łatach portu usuwa test i wpis
    # z KNOWN_DEFECTS; do tego czasu test przechodzi, gdy usterka występuje dokładnie w ten sposób.
    def test_known_defect_token_without_ciphertext(self):
        # Token z poprawnym HMAC (klucz z ECDH z kluczem publicznym stacji), ale bez szyfrogramu.
        self.assertDefect(self.station().run("--defect", "token48", "--events", 0), "token-without-ciphertext")

    def test_known_defect_short_announce(self):
        # Ogłoszenie krótsze niż klucz publiczny 64 B: odczyt poza buforem w Ed25519.
        self.assertDefect(self.station().run("--defect", "short-announce", "--events", 0), "short-announce")

    def test_known_defect_announce_table_use_after_free(self):
        # Ogłoszenie i zaraz zapytanie o trasę do tego celu: Transport::jobs wstawia odłożone ogłoszenie
        # do _announce_table w pętli po niej.
        self.assertDefect(self.station().run("--defect", "held-announce", "--events", 0), "announce-table-use-after-free")

    def test_mutated_traffic_from_node_with_network_key(self):
        failures, known = [], set()
        for seed in range(100, 100 + SEEDS):
            code, outcome, report, stderr = self.station().run("--seed", seed, "--events", 3000, "--mutate", 30, "--long-jumps")
            if known_defect(report):
                known.add(known_defect(report))
            elif report or outcome.get("result") != "ok":
                failures.append((seed, outcome, (report or stderr)[-3000:]))
            elif outcome["iface"]["rx_ok"] == 0 or outcome["iface"]["ifac_invalid"] + outcome["iface"]["too_large"] == 0:
                failures.append((seed, outcome, "valid and rejected datagrams both expected"))
        if failures:
            self.fail(f"{len(failures)} of {SEEDS} seeds failed; first: {failures[0]}")
        if known:
            self.skipTest(f"blocked by known port defects: {', '.join(sorted(known))}")

    def test_power_loss_in_any_fram_write(self):
        # Stacja po pracy; potem zanik zasilania w wybranym zapisie i start z tym, co zostało w FRAM.
        base = self.station()
        outcome = self.assertClean(base.run("--seed", 21, "--events", 1500))
        # Punkty w pierwszych 90% zapisów próby (liczba zapisów zależy od czasu kompaktowania
        # microStore, który biegnie zegarem gospodarza); przebieg bez cięcia też musi być czysty.
        writes = self.run_writes(base)
        rng = random.Random(7)
        points = sorted({0, 1, writes * 9 // 10} | {rng.randrange(max(1, writes * 9 // 10)) for _ in range(10)})
        cuts = 0
        for point in points:
            with self.subTest(write=point):
                s = self.copy(base)
                code, cut, report, stderr = s.run("--seed", 22, "--events", 1500, "--cut-after-writes", point)
                self.assertIsNone(report, report)
                if code != POWER_CUT:
                    self.assertClean((code, cut, report, stderr))
                cuts += code == POWER_CUT
                after = self.assertClean(s.run("--seed", 23, "--events", 800, "--gap", 5))
                self.assertEqual(after["identity"], outcome["identity"])
        self.assertGreaterEqual(cuts, len(points) - 1, f"power cut reached in {cuts} of {len(points)} points")

    def test_fram_bit_flips(self):
        # Przekłamania bitów w używanej części FRAM: stacja startuje albo zgłasza błąd pamięci, bez awarii.
        base = self.station()
        outcome = self.assertClean(base.run("--seed", 31, "--events", 2000))
        image = base.fram.read_bytes()
        used = [i for i, b in enumerate(image) if b != 0xFF]
        rng = random.Random(3)
        for trial in range(8):
            with self.subTest(trial=trial):
                s = self.copy(base)
                data = bytearray(image)
                for i in rng.sample(used, min(len(used), 1 + trial * 3)):
                    data[i] ^= 1 << rng.randrange(8)
                s.fram.write_bytes(bytes(data))
                after = self.assertClean(s.run("--seed", 40 + trial, "--events", 800, "--gap", 5), "identity_lost")
                if after["result"] == "ok":
                    self.assertEqual(after["identity"], outcome["identity"])

    def test_clock_set_back(self):
        # Zegar cofnięty o rok (np. utracony dziennik czasu) i potem dalej do przodu.
        s = self.station()
        self.assertClean(s.run("--seed", 51, "--events", 1500, "--long-jumps"))
        self.assertClean(s.run("--seed", 52, "--events", 1500, "--set-clock", 1735689600))
        self.assertClean(s.run("--seed", 53, "--events", 1500, "--gap", 60 * 86400))

    def run_writes(self, station):
        probe = self.copy(station)
        return max(1, self.assertClean(probe.run("--seed", 22, "--events", 1500))["writes"])

    def copy(self, station):
        s = self.station()
        for suffix in ("", ".clock", ".id"):
            src = Path(str(station.fram) + suffix)
            if src.exists():
                shutil.copy(src, Path(str(s.fram) + suffix))
        return s


if __name__ == "__main__":
    unittest.main()
