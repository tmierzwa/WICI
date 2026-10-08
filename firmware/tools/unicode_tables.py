#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Tablice Unicode do kontroli tekstów SA1 w stacji (firmware/src/unicode_tables.h).

Model (software/reference/reference.py, ``_text``) odrzuca znaki z kategorii Cc, Cf, Cs,
Co, Cn, Zl i Zp oraz tekst, który nie jest w postaci NFC. Stacja robi to samo na podstawie
tablic wyznaczonych tutaj z modułu ``unicodedata`` Pythona; wersja bazy Unicode trafia do
nagłówka (``UNIDATA_VERSION``), a test tests/test_sa1_unicode.py porównuje stację z modelem
tylko przy tej samej wersji.

Zawartość nagłówka:

* ``REJECTED_*``: zbiór odrzucanych kategorii jako punkty zmiany przynależności w każdej
  płaszczyźnie (16 bitów przesunięcia w płaszczyźnie i stan na jej początku).
* ``NFC_NO``: przedziały znaków, które nie występują w NFC (NFC_QC=No: pełne wykluczenia
  z kompozycji, w tym singletony i rozkłady zaczynające się od znaku łączącego).
* ``NFC_SECOND``: znaki, które mogą być drugim składnikiem kompozycji pierwotnej
  (NFC_QC=Maybe; jamo V i T Hangul liczy kod algorytmicznie).
* ``CCC_*``: przedziały niezerowej klasy łączenia kanonicznego (ccc).
* ``DECOMP_*``: rozkłady kanoniczne kompozycji pierwotnych (pary: pierwszy znak i numer
  drugiego w ``NFC_SECOND``), posortowane według znaku, z indeksem według pary do składania.
  Rozkładów wykluczonych nie ma: tekst z takim znakiem i tak nie jest w NFC.

Bez argumentów wypisuje rozmiary tablic; ``--write`` zapisuje nagłówek, ``--check`` kończy
się kodem 1, gdy zapisany nagłówek różni się od wygenerowanego.
"""

from __future__ import annotations

import argparse
import bisect
from pathlib import Path
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "firmware" / "src" / "unicode_tables.h"
REJECTED_CATEGORIES = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")
MAX_CP = 0x10FFFF
# Hangul (Unicode, rozdział 3.12): sylaby są składane i rozkładane algorytmicznie.
HANGUL_S = range(0xAC00, 0xAC00 + 11172)
HANGUL_V = range(0x1161, 0x1176)
HANGUL_T = range(0x11A8, 0x11C3)


def is_surrogate(c: int) -> bool:
    return 0xD800 <= c <= 0xDFFF


def ranges(predicate) -> list[tuple[int, int]]:
    """Przedziały domknięte kolejnych znaków spełniających warunek."""
    out: list[tuple[int, int]] = []
    start = None
    for c in range(MAX_CP + 1):
        if predicate(c):
            if start is None:
                start = c
        elif start is not None:
            out.append((start, c - 1))
            start = None
    if start is not None:
        out.append((start, MAX_CP))
    return out


def build() -> dict:
    """Wyznacza wszystkie tablice z unicodedata i sprawdza założenia kodu w sa1.cpp."""
    rejected = [unicodedata.category(chr(c)) in REJECTED_CATEGORIES for c in range(MAX_CP + 1)]
    # Punkty zmiany w każdej płaszczyźnie: przesunięcie x, gdzie stan(x) != stan(x - 1).
    planes = []
    for plane in range(17):
        base = plane << 16
        toggles = [x for x in range(1, 0x10000) if rejected[base + x] != rejected[base + x - 1]]
        planes.append((rejected[base], toggles))

    decompositions: dict[int, tuple[int, ...]] = {}
    for c in range(MAX_CP + 1):  # Hangul pomijamy: sa1.cpp liczy go algorytmicznie
        mapping = "" if c in HANGUL_S else unicodedata.decomposition(chr(c))
        if mapping and not mapping.startswith("<"):
            decompositions[c] = tuple(int(x, 16) for x in mapping.split())
    # Kompozycja pierwotna: rozkład na dwa znaki, a NFC znaku daje ten sam znak.
    composites = {c: d for c, d in decompositions.items() if len(d) == 2 and unicodedata.normalize("NFC", chr(c)) == chr(c)}
    for c, (first, second) in composites.items():
        assert first in composites or first not in decompositions, f"rozkład U+{c:04X} wymaga wykluczonego znaku"
        assert second not in decompositions, f"drugi składnik U+{c:04X} ma rozkład"
        assert unicodedata.combining(chr(first)) == 0, f"U+{c:04X} zaczyna się od znaku łączącego"
    second = sorted({d[1] for d in composites.values()} - set(HANGUL_V) - set(HANGUL_T))
    assert len(second) < 256
    nfc_no = ranges(lambda c: not is_surrogate(c) and unicodedata.normalize("NFC", chr(c)) != chr(c))
    for c in range(MAX_CP + 1):
        if not is_surrogate(c) and c in decompositions and c not in composites:
            assert any(a <= c <= b for a, b in nfc_no), f"U+{c:04X} wykluczony, a nie w NFC_NO"

    ccc: list[list[int]] = []
    for c in range(MAX_CP + 1):
        value = unicodedata.combining(chr(c))
        if value:
            if ccc and ccc[-1][1] == c - 1 and ccc[-1][2] == value and c - ccc[-1][0] < 256:
                ccc[-1][1] = c
            else:
                ccc.append([c, c, value])

    entries = sorted(composites.items())
    assert entries[-1][0] < 0x20000 and max(d[0] for _, d in entries) < (1 << 24)
    plane1 = bisect.bisect_left([c for c, _ in entries], 0x10000)
    order = sorted(range(len(entries)), key=lambda i: (entries[i][1][0], second.index(entries[i][1][1])))

    # Bufor rozkładu w sa1.cpp: najwyżej 3 znaki na 2 bajty UTF-8 (1,5 znaku na bajt).
    expansion = max(len(unicodedata.normalize("NFD", chr(c))) / len(chr(c).encode("utf-8"))
                    for c in range(MAX_CP + 1) if not is_surrogate(c))
    assert expansion <= 1.5, expansion
    return {"planes": planes, "nfc_no": nfc_no, "second": second, "ccc": ccc, "entries": entries,
            "plane1": plane1, "order": order}


def hexlist(values, width: int, per_line: int) -> list[str]:
    items = [f"0x{v:0{width}X}" for v in values]
    return ["    " + ", ".join(items[i:i + per_line]) + "," for i in range(0, len(items), per_line)]


def sizes(t: dict) -> dict[str, int]:
    toggles = sum(len(p[1]) for p in t["planes"])
    return {
        "REJECTED_TOGGLES": 2 * toggles,
        "REJECTED_PLANE_START": 2 * 18,
        "NFC_NO": 8 * len(t["nfc_no"]),
        "NFC_SECOND": 4 * len(t["second"]),
        "CCC_RANGES + CCC_VALUES": 5 * len(t["ccc"]),
        "DECOMP_CP": 2 * len(t["entries"]),
        "DECOMP_PAIR": 4 * len(t["entries"]),
        "COMPOSE_ORDER": 2 * len(t["order"]),
    }


def header(t: dict) -> str:
    total = sum(sizes(t).values())
    starts = [0]
    for _, toggles in t["planes"]:
        starts.append(starts[-1] + len(toggles))
    initial = sum(1 << p for p, (state, _) in enumerate(t["planes"]) if state)
    second_index = {c: i for i, c in enumerate(t["second"])}
    out = [
        "// SPDX-License-Identifier: MIT",
        "// Generated by firmware/tools/unicode_tables.py --write; do not edit by hand.",
        f"// Unicode {unicodedata.unidata_version} (Python unicodedata). Check: python3 firmware/tools/unicode_tables.py --check",
        "// Tablice kontroli tekstów SA1 (sa1.cpp, jak _text() w software/reference/reference.py):",
        "// odrzucane kategorie Cc, Cf, Cs, Co, Cn, Zl, Zp oraz dane do dokładnej kontroli NFC.",
        f"// Razem {total} B w pamięci programu.",
        "#pragma once",
        "",
        "#include <stddef.h>",
        "#include <stdint.h>",
        "",
        "namespace ucd {",
        "",
        f"constexpr const char* UNIDATA_VERSION = \"{unicodedata.unidata_version}\";",
        "",
        "// Odrzucane kategorie: w płaszczyźnie p przesunięcia, w których zmienia się przynależność,",
        "// to REJECTED_TOGGLES[REJECTED_PLANE_START[p] .. REJECTED_PLANE_START[p + 1]); bit p",
        "// REJECTED_PLANE_INITIAL mówi, czy znak p << 16 jest odrzucany.",
        f"constexpr uint32_t REJECTED_PLANE_INITIAL = 0x{initial:05X};",
        "const uint16_t REJECTED_PLANE_START[18] = {",
        *hexlist(starts, 4, 9),
        "};",
        f"const uint16_t REJECTED_TOGGLES[{starts[-1]}] = {{",
        *hexlist([x for _, toggles in t["planes"] for x in toggles], 4, 12),
        "};",
        "",
        "// NFC_QC=No: przedziały domknięte {pierwszy, ostatni}.",
        f"const uint32_t NFC_NO[{len(t['nfc_no'])}][2] = {{",
        *["    {" + f"0x{a:05X}, 0x{b:05X}" + "}," for a, b in t["nfc_no"]],
        "};",
        "",
        "// NFC_QC=Maybe bez jamo Hangul: drugie składniki kompozycji pierwotnych, rosnąco.",
        f"const uint32_t NFC_SECOND[{len(t['second'])}] = {{",
        *hexlist(t["second"], 5, 10),
        "};",
        "",
        "// Niezerowa klasa łączenia kanonicznego: CCC_RANGES[i] = pierwszy << 8 | (długość - 1).",
        f"const uint32_t CCC_RANGES[{len(t['ccc'])}] = {{",
        *hexlist([(a << 8) | (b - a) for a, b, _ in t["ccc"]], 7, 8),
        "};",
        f"const uint8_t CCC_VALUES[{len(t['ccc'])}] = {{",
        *["    " + ", ".join(str(v) for _, _, v in t["ccc"][i:i + 20]) + "," for i in range(0, len(t["ccc"]), 20)],
        "};",
        "",
        "// Rozkłady kanoniczne kompozycji pierwotnych, rosnąco według znaku: DECOMP_CP to 16 młodszych",
        "// bitów znaku (od DECOMP_PLANE1 płaszczyzna 1), DECOMP_PAIR = pierwszy << 8 | numer drugiego",
        "// w NFC_SECOND. COMPOSE_ORDER: numery wpisów posortowane według DECOMP_PAIR (do składania).",
        f"constexpr size_t DECOMP_COUNT = {len(t['entries'])};",
        f"constexpr size_t DECOMP_PLANE1 = {t['plane1']};",
        f"const uint16_t DECOMP_CP[{len(t['entries'])}] = {{",
        *hexlist([c & 0xFFFF for c, _ in t["entries"]], 4, 12),
        "};",
        f"const uint32_t DECOMP_PAIR[{len(t['entries'])}] = {{",
        *hexlist([(d[0] << 8) | second_index[d[1]] for _, d in t["entries"]], 7, 8),
        "};",
        f"const uint16_t COMPOSE_ORDER[{len(t['order'])}] = {{",
        *["    " + ", ".join(str(i) for i in t["order"][j:j + 16]) + "," for j in range(0, len(t["order"]), 16)],
        "};",
        "",
        "}  // namespace ucd",
        "",
    ]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help=f"zapisuje {HEADER.relative_to(ROOT)}")
    parser.add_argument("--check", action="store_true", help="kod 1, gdy nagłówek jest nieaktualny")
    args = parser.parse_args()
    tables = build()
    text = header(tables)
    if args.write:
        HEADER.write_text(text, encoding="utf-8")
        print(f"wrote {HEADER.relative_to(ROOT)} (Unicode {unicodedata.unidata_version}, {sum(sizes(tables).values())} B)")
        return 0
    if args.check:
        current = HEADER.read_text(encoding="utf-8") if HEADER.exists() else ""
        if current != text:
            print(f"{HEADER.relative_to(ROOT)} is stale (Unicode {unicodedata.unidata_version}); "
                  "run firmware/tools/unicode_tables.py --write")
            return 1
        print(f"{HEADER.relative_to(ROOT)} is current (Unicode {unicodedata.unidata_version})")
        return 0
    for name, size in sizes(tables).items():
        print(f"{name}: {size} B")
    print(f"total: {sum(sizes(tables).values())} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
