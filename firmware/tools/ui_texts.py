#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Screen texts of the station, generated from the canonical list in the specification.

``docs/spec/oprogramowanie.md`` ("Teksty ekranu") is the only canonical list of
screen texts; this script reads its tables (texts with identifiers, menu and
button labels, category labels, ready phrases) and writes them as string tables
for the firmware, so the image cannot drift from the specification. The time
units and the decimal separator come from the prose of the same section.

Run without arguments to print the texts; ``--write`` regenerates
``firmware/src/ui_texts.h``; ``--check`` fails when that header is stale.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "spec" / "oprogramowanie.md"
HEADER = ROOT / "firmware" / "src" / "ui_texts.h"

LANGS = ("PL", "UK", "EN")
UNITS = {"PL": ("MIN", "H", "D"), "UK": ("ХВ", "ГОД", "Д"), "EN": ("MIN", "H", "D")}  # [czas]: minutes, hours, days
DECIMAL = {"PL": ",", "UK": ",", "EN": "."}  # the EN version uses a decimal point
MAX_COLUMNS = 20  # the screen shows at most 5 lines of 20 characters
FOLD = str.maketrans("ĄĆĘŁŃÓŚŹŻ", "ACELNOSZZ")


def tables(markdown: str) -> list[list[list[str]]]:
    """All Markdown tables of a text, each as rows of stripped cells (without the separator row)."""
    result: list[list[list[str]]] = []
    current: list[list[str]] | None = None
    for line in markdown.splitlines():
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r"-+", cell) for cell in cells):
                continue
            if current is None:
                current = []
                result.append(current)
            current.append(cells)
        else:
            current = None
    return result


def identifier(label: str) -> str:
    """C++ enumerator from a Polish label: letters folded to ASCII, words joined with underscores."""
    name = re.sub(r"\s*\(.*\)", "", label).translate(FOLD)
    return re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")


def load(spec: Path = SPEC) -> dict:
    """Read the canonical tables; returns texts, labels, buttons, menu, categories and phrases."""
    text = spec.read_text(encoding="utf-8")
    start = text.index("## Ekran i przyciski stacji")
    end = text.index("## Stanowisko dyżurnego OSP")
    section = text[start:end]
    found = tables(section)
    menu_table = next(t for t in found if t[0][:2] == ["Menu", "Działanie"])
    texts_table = next(t for t in found if t[0][:2] == ["ID", "Ekran PL"])
    labels_table = next(t for t in found if t[0] == ["PL", "UK", "EN"])
    categories_table = next(t for t in found if t[0][0] == "Kategoria")
    phrases_table = next(t for t in found if t[0][0].startswith("PL (wysyłane)"))

    texts = {}
    for row in texts_table[1:]:
        key = row[0].strip("`")
        texts[key] = tuple("" if cell == "–" else cell for cell in row[1:4])
    buttons = None
    labels = {}
    for row in labels_table[1:]:
        if "(przyciski)" in row[0]:
            buttons = tuple(tuple(part.strip() for part in re.sub(r"\s*\(.*\)", "", cell).split("/")) for cell in row)
            continue
        labels[identifier(row[0])] = tuple(re.sub(r"\s*\(.*\)", "", cell) for cell in row)
    menu = []
    for row in menu_table[1:]:
        name = row[0]
        if "/" in name:
            menu.append(("JEZYK", (name, name, name)))  # the label is always in three languages
        else:
            menu.append((identifier(name), labels[identifier(name)]))
    categories = [tuple(row[1:4]) for row in categories_table[1:]]
    phrases = [tuple(row[0:3]) for row in phrases_table[1:]]
    assert buttons and len(buttons) == 3 and all(len(b) == 4 for b in buttons), buttons
    assert len(categories) == 10 and len(menu) == 5, (len(categories), len(menu))
    return {"texts": texts, "labels": labels, "buttons": buttons, "menu": menu, "categories": categories, "phrases": phrases}


def charset(data: dict) -> set[str]:
    """Every character that can appear on the screen from the canonical tables and units."""
    chars: set[str] = set()
    for group in (data["texts"].values(), data["labels"].values(), data["categories"], data["phrases"], data["menu"]):
        for entry in group:
            strings = entry[1] if isinstance(entry[1], tuple) else entry
            for s in strings:
                chars.update(s)
    for button_set in data["buttons"]:
        for s in button_set:
            chars.update(s)
    for units in UNITS.values():
        for s in units:
            chars.update(s)
    chars.update(DECIMAL.values())
    return chars


def cstring(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def rows(entries, indent="    ") -> str:
    return "\n".join(f"{indent}{{{', '.join(cstring(s) for s in strings)}}}," for strings in entries)


def header(data: dict) -> str:
    texts = data["texts"]
    labels = data["labels"]
    ids = list(texts)
    out = [
        "// SPDX-License-Identifier: MIT",
        "// Teksty ekranu stacji: wygenerowane przez firmware/tools/ui_texts.py z jedynej kanonicznej",
        '// listy w docs/spec/oprogramowanie.md ("Teksty ekranu"). Nie edytować ręcznie.',
        "#pragma once",
        "",
        "#include <stddef.h>",
        "#include <stdint.h>",
        "",
        "namespace ui_texts {",
        "",
        f"constexpr size_t LANGS = {len(LANGS)};",
        "enum class Lang : uint8_t { " + ", ".join(f"{lang} = {i}" for i, lang in enumerate(LANGS)) + " };",
        f"constexpr size_t MAX_COLUMNS = {MAX_COLUMNS};  // wiersz ekranu",
        "",
        "// Teksty z identyfikatorami (kolumny PL, UK, EN); pusty napis = brak tekstu w tym języku.",
        "enum class Id : uint8_t {",
        "\n".join(f"    {key.upper()}," for key in ids),
        "    COUNT",
        "};",
        "",
        "constexpr const char* const TEXTS[static_cast<size_t>(Id::COUNT)][LANGS] = {",
        rows(texts.values()),
        "};",
        "",
        "// Pozycje menu, nazwy przycisków i etykiety (tabela PL/UK/EN).",
        "enum class Label : uint8_t {",
        "\n".join(f"    {key}," for key in labels),
        "    COUNT",
        "};",
        "",
        "constexpr const char* const LABELS[static_cast<size_t>(Label::COUNT)][LANGS] = {",
        rows(labels.values()),
        "};",
        "",
        "// Przyciski: GÓRA, DÓŁ, OK, WSTECZ.",
        "constexpr const char* const BUTTONS[LANGS][4] = {",
        rows(data["buttons"]),
        "};",
        "",
        "// Menu główne w kolejności ze specyfikacji; etykieta języka jest zawsze trójjęzyczna.",
        f"constexpr size_t MENU_ITEMS = {len(data['menu'])};",
        "enum class Menu : uint8_t { " + ", ".join(f"{key} = {i}" for i, (key, _) in enumerate(data["menu"])) + " };",
        "constexpr const char* const MENU[MENU_ITEMS][LANGS] = {",
        rows(strings for _, strings in data["menu"]),
        "};",
        "",
        "// Etykiety kategorii 0-9.",
        "constexpr const char* const CATEGORIES[10][LANGS] = {",
        rows(data["categories"]),
        "};",
        "",
        "// Gotowe frazy: do SA1 trafia wersja PL, ekran pokazuje tłumaczenie.",
        f"constexpr size_t PHRASES_COUNT = {len(data['phrases'])};",
        "constexpr const char* const PHRASES[PHRASES_COUNT][LANGS] = {",
        rows(data["phrases"]),
        "};",
        "",
        "// Jednostki [czas] (minuty, godziny, doby) i separator dziesiętny napięcia.",
        "constexpr const char* const UNITS[LANGS][3] = {",
        rows(UNITS[lang] for lang in LANGS),
        "};",
        "constexpr char DECIMAL[LANGS] = {" + ", ".join(f"'{DECIMAL[lang]}'" for lang in LANGS) + "};",
        "",
        "inline const char* text(Id id, Lang lang) { return TEXTS[static_cast<size_t>(id)][static_cast<size_t>(lang)]; }",
        "inline const char* label(Label id, Lang lang) { return LABELS[static_cast<size_t>(id)][static_cast<size_t>(lang)]; }",
        "",
        "}  // namespace ui_texts",
        "",
    ]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help=f"write {HEADER.relative_to(ROOT)}")
    parser.add_argument("--check", action="store_true", help="exit 1 when the header is stale")
    args = parser.parse_args()
    data = load()
    text = header(data)
    if args.write:
        HEADER.write_text(text, encoding="utf-8")
        print(f"wrote {HEADER.relative_to(ROOT)}: {len(data['texts'])} texts, {len(data['labels'])} labels")
    elif args.check:
        if not HEADER.exists() or HEADER.read_text(encoding="utf-8") != text:
            print(f"{HEADER.relative_to(ROOT)} is stale; run firmware/tools/ui_texts.py --write")
            return 1
        print(f"{HEADER.relative_to(ROOT)} is current")
    else:
        for key, strings in data["texts"].items():
            print(key, "|", " | ".join(strings))
        for key, strings in data["labels"].items():
            print(key, "|", " | ".join(strings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
