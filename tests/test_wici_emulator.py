# SPDX-License-Identifier: MIT
"""Emulator WICI-Link (tests/native/wici_emulator): powtarzalność, zgodność wariantów z obecnym kodem i kalibracja.

Krótkie przebiegi pod ASan i UBSan. Pełną macierz raportu uruchamia run.py matrix; nie jest częścią testów.
"""

from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "native" / "wici_emulator"))
import run as emulator  # noqa: E402

SHORT = ("hops=6", "reports=8", "spread=60", "hours=3", "p=900")
DECISIONS = ("learn=1", "alternate=1", "leave=1800", "hold=7200", "flood=700")


def setUpModule():
    global BUILD, BINARIES
    if not emulator.available():
        raise unittest.SkipTest("C++ compiler or pinned Crypto sources unavailable (firmware/tools/stack_deps.py)")
    BUILD = tempfile.TemporaryDirectory()
    BINARIES = emulator.build(BUILD.name, sanitize=True)


def tearDownModule():
    BUILD.cleanup()


def run(binary, *args):
    done = subprocess.run([str(BINARIES[binary]), *args], check=True, capture_output=True, text=True)
    return done.stdout


class Emulator(unittest.TestCase):
    def test_same_seed_gives_identical_run_and_another_seed_differs(self):
        first = run("base", "koniec", "seed=7", *SHORT)
        self.assertEqual(first, run("base", "koniec", "seed=7", *SHORT))
        self.assertNotEqual(first, run("base", "koniec", "seed=8", *SHORT))
        self.assertEqual(json.loads(first)["closed"], 8)

    def test_decisions_run_repeatably_too(self):
        first = run("variant", "koniec", "seed=7", *SHORT, *DECISIONS)
        self.assertEqual(first, run("variant", "koniec", "seed=7", *SHORT, *DECISIONS))

    def test_patched_copy_with_flags_off_is_the_current_code(self):
        # Różnica w jednym bajcie wyniku znaczy, że variant.patch zmienia coś poza przełącznikami.
        for scenario in ("koniec", "cala_siec", "zmiana_rodzica"):
            self.assertEqual(run("base", scenario, "seed=3", *SHORT), run("variant", scenario, "seed=3", *SHORT), scenario)

    def test_firmware_sources_are_untouched_by_the_variant(self):
        # Rozstrzygnięcia żyją w łatce do czasu decyzji: firmware nie zna przełączników.
        for source in (ROOT / "firmware" / "src").glob("wici_*"):
            self.assertNotIn("wici_variant", source.read_text(encoding="utf-8"), source.name)

    def test_k1_rule_from_main_never_floods_over_the_contended_cap(self):
        # Limit 25% z #187: rozsyłanie nie wychodzi ponad limit, gdy czeka K1, które może wyjść; łatka tego nie zmienia.
        attack = ("atak_k1", "seed=1", "p=900", "skip=700", "hours=2", "reports=10", "spread=3600", "fakeevery=2")
        routed = json.loads(run("variant", *attack))
        self.assertEqual(routed["flood_over_cap"], 0)
        self.assertGreater(routed["flood"], 1000)
        self.assertEqual(run("base", *attack), run("variant", *attack))

    def test_refused_flood_copy_is_not_marked_seen(self):
        # Kopia spoza rodziców nie może zablokować prawdziwej kopii od rodzica; tryb 3 pokazuje, że miara to wykrywa.
        case = ("regula_rodzica", "seed=1", "p=900", "n=60", "hours=1", "reports=5", "spread=600", "downrounds=1")
        self.assertEqual(json.loads(run("variant", *case, "floodparent=1"))["parent_seen_unsent"], 0)
        self.assertGreater(json.loads(run("variant", *case, "floodparent=3"))["parent_seen_unsent"], 0)

    def test_attacker_as_current_parent_passes_only_with_current_parent(self):
        # Napastnik z fałszywie niską rangą zostaje rodzicem dynamicznym stacji 5: tylko tryb 2 przepuszcza jego rozsyłanie.
        case = ("regula_rodzica", "seed=1", "p=900", "skip=700", "hops=10", "hours=1", "reports=10", "spread=1800",
                "evilparent=5", "fakeevery=2")
        strict = json.loads(run("variant", *case, "floodparent=1"))
        current = json.loads(run("variant", *case, "floodparent=2"))
        self.assertGreater(strict["victim_on_attacker_pm"], 0)
        self.assertGreater(current["flood"], 10 * strict["flood"])

    def test_stale_route_to_a_refusing_station_is_counted(self):
        # Stara droga przez stację, która nie ma nadawcy za rodzica: reguła odmawia bez HACK, obecny kod nie.
        case = ("regula_rodzica", "seed=1", "p=900", "skip=700", "hours=1", "reports=10", "spread=1800", "downrounds=1",
                "stale=1", "learn=1")
        self.assertEqual(json.loads(run("variant", *case, "floodparent=0"))["refused_unicast"], 0)
        self.assertGreater(json.loads(run("variant", *case, "floodparent=1"))["refused_unicast"], 0)

    def test_flood_reach_matches_the_closed_form(self):
        # Jedno rozsyłanie w pustym łańcuchu: p^hops, bez kolizji. Sprawdza model kanału i tor rozsyłania.
        result = json.loads(run("base", "kalibracja", "hops=6", "p=800", "reports=40", "seed=2"))
        self.assertEqual(result["expected_permille"], 262)
        self.assertLess(abs(result["reached"] * 1000 / result["trials"] - result["expected_permille"]), 200)

    def test_relay_that_acks_and_drops_is_left_only_under_the_decision(self):
        args = ("seed=1", "hops=10", "reports=6", "spread=60", "hours=3", "p=950")
        today = json.loads(run("base", "porzucanie_dziecko", *args))
        decided = json.loads(run("variant", "porzucanie_dziecko", *args, *DECISIONS))
        self.assertGreater(decided["closed"], today["closed"])
        self.assertGreaterEqual(decided["leaves"], 1)

    def test_k1_frames_without_route_do_not_silence_a_relay(self):
        # Przed #187 ramki z gniazd K1 bez drogi czekały przy limicie 25% na siebie nawzajem i przekaźnik milkł
        # na ponad 300 s w tym przebiegu. Obecny kod i odrzucony wariant pierwszy (k1flood) już nie milkną.
        args = ("seed=2", "p=900", "skip=700", "hours=12", "learn=1", "alternate=1", "flood=700")
        self.assertLess(json.loads(run("variant", "koniec", *args))["longest_mute_s"], 60)
        self.assertLess(json.loads(run("variant", "koniec", *args, "k1flood=1"))["longest_mute_s"], 60)

    def test_count_threshold_leaves_a_dropping_parent(self):
        args = ("seed=1", "hops=10", "reports=6", "spread=60", "hours=4", "p=950", *DECISIONS[:2], "hold=7200")
        today = json.loads(run("base", "porzucanie_dziecko", "seed=1", "hops=10", "reports=6", "spread=60", "hours=4", "p=950"))
        decided = json.loads(run("variant", "porzucanie_dziecko", *args, "leaven=2", "permessage=1"))
        self.assertGreater(decided["closed"], today["closed"])
        self.assertGreaterEqual(decided["child_left_s"], 600)

    def test_relay_probe_helps_only_against_a_plain_dropper(self):
        args = ("seed=1", "hops=8", "reports=6", "spread=60", "hours=8", "p=950", *DECISIONS[:2], "hold=7200", "leaven=2")
        plain = json.loads(run("variant", "porzucanie_koniec", *args))
        probing = json.loads(run("variant", "porzucanie_koniec", *args, "probe=1200"))
        self.assertGreater(probing["closed"], plain["closed"])
        self.assertGreater(probing["probes"], 0)
        # Próbka nie liczy się jako zgłoszenie.
        self.assertEqual(probing["reports"], 6)


if __name__ == "__main__":
    unittest.main()
