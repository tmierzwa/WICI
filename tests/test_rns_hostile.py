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
(CI), which fetches the sources and fails instead of skipping. Any sanitizer report, hang or broken
invariant fails; the three crashes found in the review of 2026-10-21 are fixed by port patches 0005-0007
and stay as regression scenarios (--defect). WICI_RNS_SEEDS=N runs N fuzzing seeds instead of 4.

The harness feeds every datagram through the station's own IFAC code (rnsnode::debugIfacWrap) and
checks that the port and microStore read the simulated clock; each passing run must have delivered
traffic to the stack (P1 counter rx_ok). Not simulated: microStore::millis (the compaction cooldown of
the file store) reads the host's monotonic clock, so clock jumps do not move it. POSIX only (mmap, fork
of sanitizer runtimes).

The same scenarios run on the station Reticulum core (CoreHostileStackTests: rns_node_core.cpp and
firmware/lib/reticulum_core instead of rns_node.cpp; the port only generates the traffic), including
power loss in a write of the core's table of known destinations in FRAM (stage R2). The core also
gets a flood of hostile datagrams (--defect flood): at most one asymmetric operation per loop() pass,
replayed valid announces take no verification tokens, and a station packet sent during the flood is
delivered. Sixty simulated days of hostile traffic (--hostile-days, acceptance criterion 5 in
firmware/reticulum-core.md): daily reports delivered, the receiver entry kept, no heap allocation by the
station after start and the table in FRAM within 5% of its size after a week.

  python3 -m unittest tests.test_rns_hostile -v
"""

import binascii
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
import zlib

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
CORE = FIRMWARE / "lib" / "reticulum_core" / "src"
CORE_UNITS = ["drbg.cpp", "framfs.cpp", "kiss.cpp", "p1frame.cpp", "p1iface.cpp", "rns_node_core.cpp", "sha2.cpp"]
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


def sources(core: bool):
    port = STACK / "microReticulum" / "src"
    stack = [p for p in port.rglob("*.cpp") if p.name != "main.cpp"] + list(port.rglob("*.c"))
    # RNG z ziarna zamiast Crypto/RNG.cpp, który na hoście miesza czas rzeczywisty (rng_seeded.cpp).
    stack += sorted(p for p in (STACK / "Crypto").glob("*.cpp") if p.name != "RNG.cpp")
    stack.append(ROOT / "tests" / "native" / "rng_seeded.cpp")
    if core:
        return stack, [SRC / name for name in CORE_UNITS] + sorted(CORE.glob("*.cpp"))
    return stack, [SRC / name for name in WICI_UNITS]


def build(out_dir: Path, core: bool = False) -> Path:
    """Compile the stack, the station units and the harness; objects are cached in out_dir."""
    cxx = compiler()
    cc = "clang" if cxx == "clang++" else "cc"
    includes = [f"-I{SRC}", f"-I{ROOT / 'tests' / 'native'}"]
    for folder in stack_deps.INCLUDES:
        includes += ["-isystem", str(STACK / folder)]
    flags = stack_flags() + SANITIZE
    key = hashlib.sha256(" ".join([cxx] + flags + includes + (["core"] if core else [])).encode()).hexdigest()[:12]
    objects_dir = out_dir / key
    objects_dir.mkdir(parents=True, exist_ok=True)
    stack, wici = sources(core)
    # Nagłówki WICI i rdzenia oraz stan łat stosu: zmiana któregoś przebudowuje wszystko.
    newest = max([p.stat().st_mtime for p in SRC.glob("*.h")] + [p.stat().st_mtime for p in CORE.glob("*.h")] +
                 [p.stat().st_mtime for p in STACK.glob("*/.wici-stamp")])

    def compile_one(source: Path):
        rel = source.relative_to(ROOT if ROOT in source.parents else STACK)
        obj = objects_dir / (str(rel).replace("/", "_") + ".o")
        if obj.exists() and obj.stat().st_mtime > max(newest, source.stat().st_mtime):
            return obj
        quiet = ["-w"] if STACK in source.parents else ["-Wall", "-Wextra", "-Werror"]
        # Nagłówki rdzenia tylko dla jednostek WICI i rdzenia: na systemie plików bez rozróżniania wielkości
        # liter "packet.h" rdzenia przesłoniłby "Packet.h" portu.
        local = [f"-I{CORE}"] if core and STACK not in source.parents and source != HARNESS else []
        if core and STACK not in source.parents:
            quiet.append("-DRNSCORE_COUNT_OPERATIONS")   # licznik operacji asymetrycznych (identity.h)
        if source == HARNESS:
            quiet.append("-Wno-deprecated-declarations")   # generator buduje pakiety dawnym API portu
            if core:
                quiet.append("-DWICI_RNS_CORE")
        if source.suffix == ".c":
            cmd = [cc, *flags, *includes, "-w", "-c", str(source), "-o", str(obj)]
        else:
            cmd = [cxx, "-std=gnu++17", "-fexceptions", "-frtti", *flags, *local, *includes, *quiet, "-c", str(source), "-o", str(obj)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"{source}:\n{result.stderr[-4000:]}")
        return obj

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        objects = list(pool.map(compile_one, stack + wici + [HARNESS]))
    binary = objects_dir / "rns_stress"
    subprocess.run([cxx, *SANITIZE, *objects, "-o", str(binary)], check=True, capture_output=True, text=True)
    return binary


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
    core = False

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
        cls.binary = build(FIRMWARE / ".pio" / "sanitize", cls.core)
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def station(self):
        return Station(self.binary, Path(tempfile.mkdtemp(dir=self.tmp.name)))

    def assertClean(self, run, *allowed):
        code, outcome, report, stderr = run
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

    def test_same_seed_same_traffic(self):
        # Generator i stacja są deterministyczne: te same --seed i zegar symulowany dają te same bajty
        # w obie strony (skrót "traffic") i ten sam wynik, także po restarcie. Bez tego usterka z jednego
        # przebiegu nie dałaby się odtworzyć (RNG z ziarna: tests/native/rng_seeded.cpp).
        runs = []
        for _ in range(2):
            s = self.station()
            runs.append([self.assertClean(s.run("--seed", 21, "--events", 1500, "--mutate", 30, "--long-jumps")),
                         self.assertClean(s.run("--seed", 22, "--events", 800, "--gap", 86400))])
        self.assertEqual(runs[0], runs[1])

    # Awarie z przeglądu 2026-10-21, poprawione łatami portu 0005-0007: jeden pakiet albo jedna sekwencja.
    def test_regression_token_without_ciphertext(self):
        # Token z poprawnym HMAC (klucz z ECDH z kluczem publicznym stacji), ale bez szyfrogramu.
        self.assertClean(self.station().run("--defect", "token48", "--events", 0))

    def test_regression_short_announce(self):
        # Ogłoszenie krótsze niż klucz publiczny 64 B: dawniej odczyt poza buforem w Ed25519.
        self.assertClean(self.station().run("--defect", "short-announce", "--events", 0))

    def test_regression_held_announce(self):
        # Ogłoszenie i zaraz zapytanie o trasę do tego celu: dawniej wstawienie odłożonego ogłoszenia
        # do _announce_table w pętli po niej (Transport::jobs).
        self.assertClean(self.station().run("--defect", "held-announce", "--events", 0))

    def test_mutated_traffic_from_node_with_network_key(self):
        failures = []
        for seed in range(100, 100 + SEEDS):
            code, outcome, report, stderr = self.station().run("--seed", seed, "--events", 3000, "--mutate", 30, "--long-jumps")
            if report or outcome.get("result") != "ok":
                failures.append((seed, outcome, (report or stderr)[-3000:]))
            elif outcome["iface"]["rx_ok"] == 0 or outcome["iface"]["ifac_invalid"] + outcome["iface"]["too_large"] == 0:
                failures.append((seed, outcome, "valid and rejected datagrams both expected"))
        if failures:
            self.fail(f"{len(failures)} of {SEEDS} seeds failed; first: {failures[0]}")

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
        for suffix in ("", ".clock", ".id", ".receiver"):
            src = Path(str(station.fram) + suffix)
            if src.exists():
                shutil.copy(src, Path(str(s.fram) + suffix))
        return s


class CoreHostileStackTests(HostileStackTests):
    """The scenarios above on the station Reticulum core (stages R1 and R2)."""

    core = True

    def test_valid_traffic_over_weeks_and_restarts(self):
        # Jak na porcie; tablica znanych celów z FRAM po restarcie (etap R2).
        s = self.station()
        first = self.assertClean(s.run("--seed", 11, "--events", 2500, "--long-jumps"))
        self.assertTrue(first["new"])
        self.assertEqual(first["iface"]["ifac_invalid"], 0, first)
        self.assertGreater(first["paths"], 5)
        self.assertGreater(first["received"], 0, first)
        second = self.assertClean(s.run("--seed", 12, "--events", 1500, "--long-jumps", "--gap", 86400))
        self.assertEqual(second["identity"], first["identity"])
        self.assertFalse(second["new"])
        self.assertGreater(second["fs_files"], 0, second)
        self.assertClean(s.run("--seed", 13, "--events", 1500, "--gap", 30 * 86400))

    def test_flood_one_asymmetric_operation_per_loop(self):
        # Zalew wrogimi datagramami szybszy niż przetwarzanie: najwyżej jedna operacja asymetryczna na obieg
        # loop() (sprawdza program prób), nadmiar odpada w kolejce odbioru i na limicie weryfikacji ogłoszeń,
        # a po zalewie ogłoszenie odbiorcy z karty i pakiet do stacji przechodzą. W trakcie zalewu pakiet
        # stacji do odbiorcy dostaje potwierdzenie. Powtórzone nagranie poprawnego ogłoszenia i kolizje
        # nie zabierają żetonów weryfikacji. Ogłoszenie odbiorcy w trakcie zalewu z fałszywymi podpisami
        # (węzeł z kluczem sieci) może nie przejść: wynik jest w "flood" (path_round -1 to głodzenie).
        outcome = self.assertClean(self.station().run("--defect", "flood", "--events", 0))
        flood = outcome["flood"]
        self.assertGreaterEqual(flood["delivered_round"], 0, flood)
        self.assertEqual(flood["replay_limited"], 0, flood)
        self.assertGreater(flood["replay_accepted"], 0, flood)
        self.assertGreater(outcome["iface"]["rx_queue_full"], 0, outcome)
        self.assertGreater(outcome["iface"]["ann_limited"], 0, outcome)
        self.assertGreater(outcome["iface"]["ifac_invalid"], 0, outcome)
        self.assertGreater(outcome["iface"]["ifac_missing"], 0, outcome)

    def test_forward_flood_one_asymmetric_operation_per_loop(self):
        # Pakiety ze stacją jako następnym skokiem, dwa na obieg loop(): każde przekazanie to podpis IFAC, więc
        # najwyżej jedna operacja asymetryczna na obieg (sprawdza program prób); nadmiar odpada w kolejce
        # odbioru albo P1, przekazania wychodzą.
        outcome = self.assertClean(self.station().run("--defect", "forward-flood", "--events", 0))
        self.assertGreater(outcome["flood"]["routes"], 10, outcome)
        self.assertGreater(outcome["iface"]["fwd"], 0, outcome)
        self.assertGreater(outcome["iface"]["rx_queue_full"], 0, outcome)

    def test_rebroadcast_load_one_asymmetric_operation_per_loop(self):
        # Nowe ogłoszenia węzłów (retransmisje) i zapytania o znane cele (odpowiedzi z pamięci podręcznej) szybciej,
        # niż stacja je przetwarza: retransmisje po jednej i tylko w obiegach bez kroku odbioru.
        outcome = self.assertClean(self.station().run("--defect", "rebroadcast-load", "--events", 0))
        self.assertGreater(outcome["iface"]["ann_rebroadcast"], 0, outcome)
        self.assertGreater(outcome["iface"]["pr_responses"], 0, outcome)

    def test_own_path_requests_two_operations_at_most_every_30_s(self):
        # Zapytania o cel stacji z nowymi znacznikami szybciej, niż stacja je przetwarza, przez 70 s: odpowiedzi
        # wychodzą, nowy podpis ogłoszenia (z IFAC dwie operacje w obiegu) najwyżej raz na 30 s.
        outcome = self.assertClean(self.station().run("--defect", "own-path-requests", "--events", 0))
        self.assertGreater(outcome["iface"]["pr_responses"], 1, outcome)
        self.assertIn(outcome["flood"]["double_passes"], range(1, 4), outcome)

    def test_sixty_days_of_hostile_traffic(self):
        # Kryterium odbioru 5 (reticulum-core.md): 60 dni na zegarze symulowanym, co dzień 10 minut ruchu z wiersza
        # „Wrogi węzeł” (przebieg 2): w każdej sekundzie ogłoszenie nowego celu, zapytanie o trasę, pakiet przez
        # stację do przypadkowego celu i do jednego celu, czyli 2 400 datagramów dziennie, 144 000 przez 60 dni;
        # co dzień zgłoszenie do odbiorcy z karty potwierdzone w tym samym oknie. Cztery starty stacji, dwa
        # zakończone w środku okna ruchu (dzień przerwany nie wlicza się do 60). Po starcie stacja nie przydziela pamięci (program prób), wpis odbiorcy
        # zostaje, a zajętość tablicy w FRAM na końcu jest w granicach ±5% stanu po tygodniu.
        s = self.station()
        runs = [("--hostile-days", 7), ("--hostile-days", 18, "--stop-after-s", 300),
                ("--hostile-days", 18, "--stop-after-s", 37), ("--hostile-days", 19)]
        outcomes = [self.assertClean(s.run("--seed", 60 + n, "--events", 0, "--window-s", 600, *run)) for n, run in enumerate(runs)]
        days = sum(o["flood"]["days"] for o in outcomes)
        self.assertEqual(days, 60, outcomes[-1])
        self.assertEqual(sum(o["flood"]["reports"] for o in outcomes), days)
        datagrams = sum(o["flood"]["datagrams"] for o in outcomes)
        self.assertEqual(datagrams, 60 * 2400 + (300 + 37) * 4)
        self.assertEqual(len({o["identity"] for o in outcomes}), 1)
        for o in outcomes:   # null: program prób bez ASan, przydziały niezmierzone (kryterium nie przechodzi)
            self.assertIsNotNone(o["flood"]["allocations"], "rns_stress without ASan: allocations not measured")
            self.assertEqual(o["flood"]["allocations"], 0, o)
        week, end = outcomes[0]["fs_used"], outcomes[-1]["fs_used"]
        self.assertLessEqual(abs(end - week), week * 0.05, (week, end))

    def test_damaged_receiver_slot(self):
        # Uszkodzone gniazdo odbiorcy z karty w FRAM (błędne CRC): zgłoszenie do odbiorcy wychodzi (wpis
        # z kluczy karty od nowa), gniazdo w liczniku table_corrupt.
        outcome = self.assertClean(self.station().run("--defect", "damaged-receiver", "--events", 300))
        self.assertEqual(outcome["iface"]["table_corrupt"], 1, outcome)

    def test_fram_targeted_damage(self):
        # Kryterium odbioru 4, celowe uszkodzenia rekordów FRAM rdzenia (lib/reticulum_core/src/table.h, gniazda
        # 568 B od framfs::FS_BASE; framfs.h, dwa rekordy klucza tożsamości): każde pole sprawdzane przy
        # montowaniu i odczycie osobno, także z poprawnym CRC tam, gdzie liczy się sprawdzenie poza CRC.
        # Stacja startuje i pracuje bez awarii, z tą samą tożsamością; wpis odbiorcy wraca z karty.
        base = self.station()
        outcome = self.assertClean(base.run("--seed", 71, "--events", 2000))
        image = bytearray(base.fram.read_bytes())
        live = [n for n in range(TABLE_SLOTS) if image[slot_at(n)] == 0xA5]
        self.assertGreater(len(live), 10)
        for n in live:   # układ gniazda zgodny z table.cpp (CRC-32 bajtów 1..560)
            b = image[slot_at(n):slot_at(n) + TABLE_SLOT]
            self.assertEqual(int.from_bytes(b[561:565], "little"), zlib.crc32(b[1:561]), n)
        free = [n for n in range(TABLE_SLOTS) if n not in live]
        rng = random.Random(9)

        def resealed(data, n):
            at = slot_at(n)
            data[at + 561:at + 565] = zlib.crc32(bytes(data[at + 1:at + 561])).to_bytes(4, "little")

        def marker(data):
            for n in rng.sample(live, 3):
                data[slot_at(n)] = 0x00

        def version(data):
            for n in rng.sample(live, 3):
                data[slot_at(n) + 1] = 7

        def slot_number(data):
            for n in rng.sample(live, 3):
                data[slot_at(n) + 2] ^= 0x01

        def content(data):
            for n in rng.sample(live, 5):
                data[slot_at(n) + rng.randrange(40, 561)] ^= 1 << rng.randrange(8)

        def announce_length(data):   # długość ogłoszenia ponad 465 B z poprawnym CRC
            for n in rng.sample(live, 3):
                data[slot_at(n) + 10:slot_at(n) + 12] = (0xFFFF).to_bytes(2, "little")
                resealed(data, n)

        def duplicate(data):   # dwie zatwierdzone kopie jednego celu z tym samym numerem zapisu
            source, target = rng.choice(live), rng.choice(free)
            data[slot_at(target):slot_at(target) + TABLE_SLOT] = data[slot_at(source):slot_at(source) + TABLE_SLOT]
            data[slot_at(target) + 2:slot_at(target) + 4] = target.to_bytes(2, "little")
            resealed(data, target)

        def sequence_end(data):   # numer zapisu na końcu zakresu: następne zapisy zawijają numer
            n = rng.choice(live)
            data[slot_at(n) + 4:slot_at(n) + 8] = (0xFFFFFFFF).to_bytes(4, "little")
            resealed(data, n)

        def every_slot(data):   # wszystkie gniazda z nagłówkiem zatwierdzonym i przypadkową treścią
            for n in range(TABLE_SLOTS):
                at = slot_at(n)
                data[at:at + TABLE_SLOT] = bytes([0xA5, 2]) + n.to_bytes(2, "little") + rng.randbytes(TABLE_SLOT - 4)

        cases = {"marker": marker, "version": version, "slot_number": slot_number, "content": content,
                 "announce_length": announce_length, "duplicate": duplicate, "sequence_end": sequence_end,
                 "every_slot": every_slot}
        for name, damage in cases.items():
            with self.subTest(damage=name):
                s = self.copy(base)
                data = bytearray(image)
                damage(data)
                s.fram.write_bytes(bytes(data))
                after = self.assertClean(s.run("--seed", 72, "--events", 800, "--gap", 5))
                self.assertEqual(after["identity"], outcome["identity"])
                again = self.assertClean(s.run("--seed", 73, "--events", 400, "--gap", 5))
                self.assertEqual(again["identity"], outcome["identity"])

        with self.subTest(damage="receiver_foreign_key"):
            s = self.copy(base)
            after = self.assertClean(s.run("--seed", 74, "--events", 0, "--receiver-foreign-key"))
            self.assertTrue(after["flood"]["receiver_reads"], after)

        # Rekordy klucza tożsamości: uszkodzony nowszy rekord. Z drugim poprawnym stacja startuje z tą samą
        # tożsamością; bez niego zgłasza utratę tożsamości (nie tworzy nowej).
        keys = [identity_record(image, n) for n in range(2)]
        newest = max(range(2), key=lambda n: keys[n] or 0)
        with self.subTest(damage="identity_record"):
            s = self.copy(base)
            data = bytearray(image)
            data[IDENTITY_BASE + newest * IDENTITY_SLOT + 8 + rng.randrange(64)] ^= 0x10
            s.fram.write_bytes(bytes(data))
            after = self.assertClean(s.run("--seed", 75, "--events", 400, "--gap", 5), "identity_lost")
            if keys[1 - newest]:
                self.assertEqual(after["identity"], outcome["identity"])
            else:
                self.assertEqual(after["result"], "identity_lost")


# Układ FRAM rdzenia (lib/reticulum_core/src/table.h, src/framfs.h).
FS_BASE, TABLE_SLOT, TABLE_SLOTS = 0x048000, 568, 257
IDENTITY_BASE, IDENTITY_SLOT, KEY_MAGIC = 0x044000, 128, 0x5749444B


def slot_at(n):
    return FS_BASE + n * TABLE_SLOT


def identity_record(image, n):
    """Numer zapisu poprawnego rekordu klucza tożsamości (framfs::loadKey: znacznik, CRC-16 bajtów 0..71,
    numer różny od 0 i 0xFFFFFFFF) albo None."""
    b = image[IDENTITY_BASE + n * IDENTITY_SLOT:IDENTITY_BASE + n * IDENTITY_SLOT + 74]
    seq = int.from_bytes(b[4:8], "little")
    valid = (int.from_bytes(b[0:4], "little") == KEY_MAGIC and int.from_bytes(b[72:74], "little") == binascii.crc_hqx(bytes(b[:72]), 0xFFFF)
             and seq not in (0, 0xFFFFFFFF))
    return seq if valid else None

if __name__ == "__main__":
    unittest.main()
