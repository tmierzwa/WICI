#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bitmap font of the station screen, rendered from DejaVu Sans Mono Bold.

The screen (Sharp LS027B7DH01, 400 x 240) shows 5 lines of 20 characters, so a
character cell is 20 px wide and the line pitch is 48 px. The glyphs are
rendered with Pillow from ``firmware/fonts/DejaVuSansMono-Bold.ttf`` (DejaVu
2.37, Bitstream Vera license, ``firmware/fonts/LICENSE.txt``) at 33 px into a
20 x 40 px cell and packed one bit per pixel, MSB first, three bytes per row.
The character set is ASCII, the Polish and Ukrainian alphabets and every
character of the canonical screen texts (``ui_texts.py``), plus U+FFFD for
characters without a glyph.

Run ``--write`` to regenerate ``firmware/src/font_glyphs.h``; ``--check`` fails
when that header is stale; ``--preview FILE.png`` draws a sample screen from the
packed glyphs. Pillow is required for ``--write`` and ``--preview``.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
FONT = ROOT / "firmware" / "fonts" / "DejaVuSansMono-Bold.ttf"
HEADER = ROOT / "firmware" / "src" / "font_glyphs.h"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ui_texts  # noqa: E402

SIZE_PX = 33
WIDTH = 20
HEIGHT = 40
ROW_BYTES = (WIDTH + 7) // 8
LINE_PITCH = 48
SCREEN = (400, 240)
POLISH = "ĄĆĘŁŃÓŚŹŻąćęłńóśźż"
UKRAINIAN = "АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯабвгґдеєжзиіїйклмнопрстуфхцчшщьюя"
REPLACEMENT = "�"


def charset() -> list[str]:
    chars = {chr(c) for c in range(0x20, 0x7F)} | set(POLISH) | set(UKRAINIAN) | {REPLACEMENT}
    chars |= ui_texts.charset(ui_texts.load())
    return sorted(chars)


def render(chars: list[str]) -> dict[str, bytes]:
    """Packed rows of every character; raises when a glyph is missing or leaves the cell."""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(str(FONT), SIZE_PX)
    glyphs = {}
    for ch in chars:
        if ch != REPLACEMENT and font.getmask(ch).getbbox() is None and not ch.isspace():
            raise ValueError(f"no glyph for U+{ord(ch):04X}")
        image = Image.new("L", (WIDTH + 8, HEIGHT + 8), 0)
        ImageDraw.Draw(image).text((0, 0), ch, font=font, fill=255, anchor="la")
        bbox = image.point(lambda v: 255 if v >= 128 else 0).getbbox()
        if bbox and (bbox[2] > WIDTH or bbox[3] > HEIGHT):
            raise ValueError(f"U+{ord(ch):04X} leaves the cell: {bbox}")
        rows = bytearray()
        for y in range(HEIGHT):
            bits = 0
            for x in range(WIDTH):
                if image.getpixel((x, y)) >= 128:
                    bits |= 1 << (ROW_BYTES * 8 - 1 - x)
            rows += bits.to_bytes(ROW_BYTES, "big")
        glyphs[ch] = bytes(rows)
    return glyphs


def header(glyphs: dict[str, bytes]) -> str:
    digest = hashlib.sha256(FONT.read_bytes()).hexdigest()[:16]
    out = [
        "// SPDX-License-Identifier: MIT AND Bitstream-Vera",
        "// SPDX-FileCopyrightText: 2003 Bitstream, Inc. (Bitstream Vera); DejaVu changes are in public domain",
        "// Font ekranu stacji: wygenerowany przez firmware/tools/font_bitmap.py z DejaVu Sans Mono Bold 2.37",
        f"// (firmware/fonts/DejaVuSansMono-Bold.ttf, sha256 {digest}...), {SIZE_PX} px w komórce {WIDTH} x {HEIGHT} px.",
        "// Kształty liter są pochodną fontu Bitstream Vera / DejaVu (licencja w firmware/fonts/LICENSE.txt);",
        "// nazwa bitmapy nie zawiera nazw Bitstream ani Vera. Nie edytować ręcznie.",
        "#pragma once",
        "",
        "#include <stddef.h>",
        "#include <stdint.h>",
        "",
        "namespace font {",
        "",
        f"constexpr uint8_t WIDTH = {WIDTH};",
        f"constexpr uint8_t HEIGHT = {HEIGHT};",
        f"constexpr uint8_t ROW_BYTES = {ROW_BYTES};  // bit 7 bajtu 0 = lewy piksel wiersza",
        f"constexpr uint8_t LINE_PITCH = {LINE_PITCH};",
        f"constexpr size_t GLYPH_COUNT = {len(glyphs)};",
        f"constexpr uint16_t REPLACEMENT = 0x{ord(REPLACEMENT):04X};",
        "",
        "struct Glyph {",
        "    uint16_t codepoint;",
        "    uint8_t rows[HEIGHT * ROW_BYTES];",
        "};",
        "",
        "// Posortowane rosnąco według kodu (wyszukiwanie połówkowe).",
        "constexpr Glyph GLYPHS[GLYPH_COUNT] = {",
    ]
    for ch in sorted(glyphs, key=ord):
        rows = glyphs[ch]
        chunks = [", ".join(f"0x{b:02X}" for b in rows[i:i + ROW_BYTES * 8]) for i in range(0, len(rows), ROW_BYTES * 8)]
        out.append(f"    {{0x{ord(ch):04X},  // {'U+FFFD' if ch == REPLACEMENT else repr(ch)}")
        out.append("     {" + ",\n      ".join(chunks) + "}},")
    out += ["};", "", "}  // namespace font", ""]
    return "\n".join(out)


def preview(glyphs: dict[str, bytes], lines: list[str], path: Path) -> None:
    from PIL import Image

    image = Image.new("1", SCREEN, 1)
    for row, line in enumerate(lines[:5]):
        for col, ch in enumerate(line[:WIDTH]):
            rows = glyphs.get(ch, glyphs[REPLACEMENT])
            for y in range(HEIGHT):
                bits = int.from_bytes(rows[y * ROW_BYTES:(y + 1) * ROW_BYTES], "big")
                for x in range(WIDTH):
                    if bits & (1 << (ROW_BYTES * 8 - 1 - x)):
                        image.putpixel((col * WIDTH + x, (LINE_PITCH - HEIGHT) // 2 + row * LINE_PITCH + y), 0)
    image.save(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help=f"write {HEADER.relative_to(ROOT)}")
    parser.add_argument("--check", action="store_true", help="exit 1 when the header is stale")
    parser.add_argument("--preview", metavar="FILE", help="render a sample screen to a PNG file")
    parser.add_argument("lines", nargs="*", help="text lines of the preview")
    args = parser.parse_args()
    glyphs = render(charset())
    text = header(glyphs)
    if args.write:
        HEADER.write_text(text, encoding="utf-8")
        print(f"wrote {HEADER.relative_to(ROOT)}: {len(glyphs)} glyphs")
    if args.check:
        if not HEADER.exists() or HEADER.read_text(encoding="utf-8") != text:
            print(f"{HEADER.relative_to(ROOT)} is stale; run firmware/tools/font_bitmap.py --write")
            return 1
        print(f"{HEADER.relative_to(ROOT)} is current")
    if args.preview:
        preview(glyphs, args.lines or ["RADIO WŁĄCZONE", "KONTAKT >99 D TEMU", "12 V: 0,0 V", "", "NOWE WIADOMOŚCI: 0"], Path(args.preview))
        print(f"wrote {args.preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
