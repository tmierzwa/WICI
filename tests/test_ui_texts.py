# SPDX-License-Identifier: MIT
"""The screen texts and the bitmap font of the firmware stay generated from the specification."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "firmware" / "tools"))
import ui_texts  # noqa: E402

try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


class TextTests(unittest.TestCase):
    def setUp(self):
        self.data = ui_texts.load()

    def test_header_is_current(self):
        self.assertEqual(ui_texts.HEADER.read_text(encoding="utf-8"), ui_texts.header(self.data))

    def test_every_text_has_three_languages(self):
        for key, strings in self.data["texts"].items():
            self.assertEqual(len(strings), 3, key)
            self.assertTrue(strings[1] and strings[2], key)
            if key != "odpowiedzi_po_polsku":
                self.assertTrue(strings[0], key)

    def test_menu_labels_and_categories_fit_twenty_columns(self):
        # oprogramowanie.md: pozycje menu i etykiety kategorii <= 20 znaków; etykieta języka 19.
        for _, strings in self.data["menu"]:
            for s in strings:
                self.assertLessEqual(len(s), 20, s)
        self.assertEqual(len(self.data["menu"][4][1][0]), 19)
        for strings in self.data["categories"]:
            for s in strings:
                self.assertLessEqual(len(s), 20, s)
        self.assertEqual([key for key, _ in self.data["menu"]], ["ZGLOSZENIE", "WIADOMOSCI", "TEST", "STAN", "JEZYK"])
        self.assertEqual(self.data["buttons"][0], ("GÓRA", "DÓŁ", "OK", "WSTECZ"))

    def test_header_cites_specification_texts(self):
        text = ui_texts.HEADER.read_text(encoding="utf-8")
        for key, strings in self.data["texts"].items():
            if key in ui_texts.PAGE_ONLY:   # tylko strona i panel: poza obrazem stacji
                self.assertNotIn(f"    {key.upper()},", text)
                continue
            self.assertIn(f"    {key.upper()},", text)
            for s in strings:
                if s:
                    self.assertIn(f'"{s}"', text, key)


class FontTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT / "firmware" / "tools"))
        import font_bitmap
        self.font_bitmap = font_bitmap

    def test_font_file_and_license_are_shipped(self):
        self.assertTrue(self.font_bitmap.FONT.exists())
        license_text = (ROOT / "firmware" / "fonts" / "LICENSE.txt").read_text(encoding="utf-8")
        self.assertIn("Bitstream Vera Fonts Copyright", license_text)
        self.assertEqual(license_text, (ROOT / "LICENSES" / "Bitstream-Vera.txt").read_text(encoding="utf-8"))

    def test_glyph_header_covers_character_set(self):
        text = self.font_bitmap.HEADER.read_text(encoding="utf-8")
        chars = self.font_bitmap.charset()
        self.assertEqual(text.count("\n    {0x"), len(chars))
        for ch in chars:
            self.assertIn(f"{{0x{ord(ch):04X},", text, ch)
        self.assertIn(f"GLYPH_COUNT = {len(chars)};", text)
        self.assertIn("SPDX-License-Identifier: MIT AND Bitstream-Vera", text)

    @unittest.skipUnless(HAVE_PIL, "Pillow not installed")
    def test_glyph_header_is_current(self):
        glyphs = self.font_bitmap.render(self.font_bitmap.charset())
        self.assertEqual(self.font_bitmap.HEADER.read_text(encoding="utf-8"), self.font_bitmap.header(glyphs))


if __name__ == "__main__":
    unittest.main()
