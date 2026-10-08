# SPDX-License-Identifier: MIT
"""Kontrola tekstów SA1 w stacji (sa1::checkText) porównana z _text() modelu.

Mały program testowy kompilowany kompilatorem komputera (sa1.cpp, jsonlite.cpp) czyta wiersze
``maksimum minimum hex`` i wypisuje ``OK`` albo powód odrzucenia. Porównanie obejmuje każdy
znak Unicode osobno, sekwencje łączone (NFC i NFD, Hangul, porządek klas, wykluczenia,
singletony) i losowe krótkie teksty. Wymaga tej samej wersji bazy Unicode w Pythonie
co w firmware/src/unicode_tables.h.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "firmware" / "src"
TOOL = ROOT / "firmware" / "tools" / "unicode_tables.py"

_spec = importlib.util.spec_from_file_location("sa1_unicode_reference", ROOT / "software" / "reference" / "reference.py")
reference = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reference)

HARNESS = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sa1.h"
#include "unicode_tables.h"

int main(int argc, char** argv) {
    if (argc > 1 && strcmp(argv[1], "version") == 0) { puts(ucd::UNIDATA_VERSION); return 0; }
    static char line[4096];
    static char text[2048];
    while (fgets(line, sizeof(line), stdin)) {
        unsigned maximum = 0, minimum = 0;
        int used = 0;
        if (sscanf(line, "%u %u %n", &maximum, &minimum, &used) != 2) return 2;
        const char* p = line + used;
        size_t n = 0;
        while (p[0] && p[1] && p[0] != '\n' && n + 1 < sizeof(text)) {
            unsigned byte = 0;
            sscanf(p, "%2x", &byte);
            text[n++] = static_cast<char>(byte);
            p += 2;
        }
        text[n] = '\0';
        const char* why = sa1::checkText(text, maximum, minimum);
        puts(why ? why : "OK");
    }
    return 0;
}
"""


def compiler():
    for name in ("c++", "g++", "clang++"):
        path = shutil.which(name)
        if path:
            return path
    return None


def header_version() -> str | None:
    match = re.search(r'UNIDATA_VERSION = "([^"]+)"', (SRC / "unicode_tables.h").read_text(encoding="utf-8"))
    return match.group(1) if match else None


SAME_VERSION = header_version() == unicodedata.unidata_version
VERSION_MESSAGE = (f"Python unicodedata {unicodedata.unidata_version} differs from Unicode {header_version()} "
                   "in firmware/src/unicode_tables.h; use a Python with the same Unicode version")


def expected(text: str, maximum: int, minimum: int) -> str:
    """Odpowiedź modelu; tekst niekodowalny w UTF-8 (samotny surogat) stacja widzi jako niepoprawne UTF-8."""
    try:
        reference._text(text, maximum, minimum)
    except UnicodeEncodeError:
        return "Invalid UTF-8"
    except ValueError as error:
        return str(error)
    return "OK"


@unittest.skipUnless(compiler(), "no host C++ compiler")
@unittest.skipUnless(SAME_VERSION, VERSION_MESSAGE)
class CheckTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        (root / "harness.cpp").write_text(HARNESS, encoding="utf-8")
        cls.binary = root / "harness"
        subprocess.run([compiler(), "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", f"-I{SRC}", str(root / "harness.cpp"),
                        str(SRC / "sa1.cpp"), str(SRC / "jsonlite.cpp"), "-o", str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def station(self, cases: list[tuple[str, int, int]]) -> list[str]:
        lines = "".join(f"{maximum} {minimum} {text.encode('utf-8', 'surrogatepass').hex()}\n" for text, maximum, minimum in cases)
        out = subprocess.run([str(self.binary)], input=lines, capture_output=True, text=True, check=True).stdout
        return out.splitlines()

    def compare(self, cases: list[tuple[str, int, int]]):
        got = self.station(cases)
        self.assertEqual(len(got), len(cases))
        mismatches = [(text, want, have) for (text, maximum, minimum), have in zip(cases, got)
                      if (want := expected(text, maximum, minimum)) != have]
        shown = [(" ".join(f"U+{ord(c):04X}" for c in text), want, have) for text, want, have in mismatches[:10]]
        self.assertEqual(shown, [], f"{len(mismatches)} mismatches")

    def test_version_matches_header(self):
        out = subprocess.run([str(self.binary), "version"], capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(out, unicodedata.unidata_version)

    def test_every_code_point(self):
        # U+0000 pomijamy: tekst w C kończy się na NUL, a jsonlite odrzuca \u0000 wcześniej.
        self.compare([(chr(c), 192, 0) for c in range(1, 0x110000)])

    def test_combining_sequences(self):
        hangul = ["가", "각", "각", "가", "각", "ᄀ가",
                  "가ᆧ", "가ᇃ", "각ᆨ", "힣", "ᄓᅡ",
                  "ᄀ̀ᅡ", "힣", "힤"]
        cases = [
            "é", "é", "é́", "á̖", "á̖", "á̖", "à̖",
            "Å", "Å", "Å", "Ω", "Ω", "̈́", "̈́", "क़", "क़",
            "⫝̸", "⫝̸", "שׁ", "שׁ", "\U0001D15E", "\U0001D157\U0001D165",
            "ཱི", "ཱི", "Ḍ̇", "Ḍ̇", "Ḍ̇", "Ḍ̇",
            "Ǖ", "Ǖ", "Ǖ", "ẛ̣", "ẛ̣", "ᾴ", "ᾴ",
            "ά", "ά", "ୋ", "ୋ", "ொ", "ൊ", "ো", "ো",
            "ဦ", "ဦ", "が", "が", "\U00011131\U00011127", "\U0001112E",
            "\U000113C2\U000113B8", "́", "́e", " ́", "à̀", "à֮", "à֮",
            "آ", "آ", "ؤ", "ؤ", "é́", "é̀",
            "Zażółć gęślą jaźń", "ZAŻÓŁĆ GĘŚLĄ JAŹŃ", unicodedata.normalize("NFD", "Zażółć gęślą jaźń"),
            unicodedata.normalize("NFD", "ZAŻÓŁĆ GĘŚLĄ JAŹŃ"), "Ґанок їжака є й", "й", "й",
            "ї", "ї", "Ї", "Ї", "ё", "ё", "Й", "Й",
            "Привіт, як справи?", unicodedata.normalize("NFD", "Привіт, як справи? Їжак, ґанок, йод"),
            "a\"́", "́\\", " \"", "­́", "é‍", "￾", "\U0010FFFF",
            "a͏́", "Ạ̊", "Ạ̊", "Ạ̊", "Ạ̊",
            "\uD800", "a\uDC00", "\"\uD800", "",
        ] + hangul
        self.compare([(text, 192, 0) for text in cases])

    def test_sizes_and_order_of_checks(self):
        cases = [("", 64, 1), ("a", 64, 1), ("a" * 64, 64, 1), ("a" * 65, 64, 1), ("ą" * 48, 96, 0),
                 ("ą" * 49, 96, 0), ("é" * 32, 96, 0), ("\u0007\"", 96, 0), ("\"\u0007", 96, 0),
                 ("é\u0007", 96, 0), ("́͸", 96, 0), ("a" * 192, 192, 0), ("a" * 193, 192, 0)]
        self.compare(cases)

    def test_random_strings(self):
        rng = random.Random(20261008)
        pools = [
            (0x20, 0x7E), (0xA0, 0x24F), (0x300, 0x36F), (0x370, 0x3FF), (0x400, 0x4FF), (0x591, 0x5C7),
            (0x900, 0x97F), (0x980, 0x9FF), (0xB00, 0xBFF), (0xD00, 0xD7F), (0x1000, 0x109F), (0x1100, 0x11FF),
            (0x1DC0, 0x1EFF), (0x1F00, 0x1FFF), (0x2000, 0x206F), (0x20D0, 0x214F), (0x2AD0, 0x2ADF),
            (0x3040, 0x30FF), (0xAC00, 0xAC40), (0xF900, 0xFB4F), (0xFE20, 0xFE2F), (0x11100, 0x1114F),
            (0x11300, 0x113FF), (0x1D150, 0x1D1FF), (0x1F600, 0x1F64F),
        ]
        marks = [0x300, 0x301, 0x302, 0x303, 0x304, 0x306, 0x307, 0x308, 0x30A, 0x30C, 0x316, 0x323, 0x327,
                 0x328, 0x331, 0x338, 0x342, 0x345, 0x5B0, 0x5C1, 0x93C, 0x9BE, 0xBBE, 0x1161, 0x11A8, 0x3099]
        cases = []
        for _ in range(5000):
            length = rng.randint(1, 8)
            chars = []
            for _ in range(length):
                if rng.random() < 0.35:
                    chars.append(chr(rng.choice(marks)))
                else:
                    low, high = rng.choice(pools)
                    chars.append(chr(rng.randint(low, high)))
            text = "".join(chars)
            if rng.random() < 0.3:
                text = unicodedata.normalize(rng.choice(["NFC", "NFD"]), text)
            cases.append((text, 96, 0))
        self.compare(cases)

    def test_invalid_utf8(self):
        lines = "".join(f"96 0 {data.hex()}\n" for data in (b"\xc3", b"\xc0\x80", b"\xe0\x80\x80", b"\xed\xa0\x80",
                                                            b"\xf4\x90\x80\x80", b"\xff", b"a\x80", b"\xf0\x9f\x98"))
        out = subprocess.run([str(self.binary)], input=lines, capture_output=True, text=True, check=True).stdout.split("\n")
        self.assertEqual(out[:8], ["Invalid UTF-8"] * 8)


@unittest.skipUnless(SAME_VERSION, VERSION_MESSAGE)
class GeneratedHeaderTests(unittest.TestCase):
    def test_header_is_current(self):
        result = subprocess.run([sys.executable, str(TOOL), "--check"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
