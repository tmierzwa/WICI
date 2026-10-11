# SPDX-License-Identifier: MIT
"""Enclosure assumptions in hardware/obudowa against the N1 board files and the R02 panel rules.

N1 values are typed in from hardware/dev-bench/plytka-nosna.md and bom.csv, independently of
zalozenia.py, so a parser error shows up here. Panel rules come from hardware/r02/obudowa.md.
"""
from pathlib import Path
import math
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hardware/obudowa"))
import zalozenia as z  # noqa: E402


class N1Geometry(unittest.TestCase):
    def test_outline(self):
        self.assertEqual(z.n1_outline(), (170.0, 100.0))

    def test_holes(self):
        holes = z.n1_holes()
        self.assertEqual(len(holes), 9)
        corners = {(h["x"], h["y"]) for h in holes if not h["arduino"]}
        self.assertEqual(corners, {(3.5, 3.5), (68.0, 3.5), (166.5, 3.5), (3.5, 96.5), (166.5, 96.5)})
        self.assertEqual(sum(h["arduino"] for h in holes), 4)

    def test_panel_parts(self):
        parts = z.n1_parts()
        xs = [parts[f"SW{i}"]["x"] for i in range(1, 5)]
        self.assertEqual([round(b - a, 3) for a, b in zip(xs, xs[1:])], [16.0, 16.0, 16.0])
        self.assertTrue(all(parts[f"SW{i}"]["y"] == 32.5 for i in range(1, 5)))
        for ref in ("SW5", "SW6", "D1", "BZ1", "J7", "J5", "J6"):
            self.assertIn(ref, parts)


class PanelConcept(unittest.TestCase):
    def setUp(self):
        self.parts = {p["id"]: p for p in z.PANEL}
        w, h, _ = z.ENCLOSURE["outer"]
        fw, fh, _ = z.ENCLOSURE["foil_recess"]
        self.foil = ((w - fw) / 2, (h - fh) / 2, (w + fw) / 2, (h + fh) / 2)

    def test_navigation_row(self):
        nav = [p for p in z.PANEL if p["kind"] == "nav"]
        self.assertEqual([p["id"] for p in nav], ["WSTECZ", "GÓRA", "DÓŁ", "OK"])
        for a, b in zip(nav, nav[1:]):
            pitch = b["xy"][0] - a["xy"][0]
            self.assertEqual(pitch, z.RULES["nav_pitch"])
            self.assertGreaterEqual(pitch - a["hole"], z.RULES["nav_gap_min"])

    def test_side_column_apart_from_navigation(self):
        last = max(p["xy"][0] + p["hole"] / 2 for p in z.PANEL if p["kind"] == "nav")
        for name in ("CISZA", "WYŁĄCZNIK"):
            self.assertGreaterEqual(self.parts[name]["xy"][0] - last, z.RULES["side_column_gap_min"])

    def test_window_covers_active_area(self):
        (ww, wh), (aw, ah) = z.DISPLAY["window"], z.DISPLAY["active"]
        margin = z.RULES["window_margin_min"]
        self.assertGreaterEqual((ww - aw) / 2, margin)
        self.assertGreaterEqual((wh - ah) / 2, margin)

    def test_everything_inside_foil(self):
        x0, y0, x1, y1 = self.foil
        (ww, wh), (cx, cy) = z.DISPLAY["window"], z.DISPLAY["window_center"]
        boxes = [(cx - ww / 2, cy - wh / 2, cx + ww / 2, cy + wh / 2)]
        for p in z.PANEL:
            x, y = p["xy"]
            half = [s / 2 for s in p["size"]] if "size" in p else [(p["hole"] or 0) / 2] * 2
            boxes.append((x - half[0], y - half[1], x + half[0], y + half[1]))
        for bx0, by0, bx1, by1 in boxes:
            self.assertTrue(x0 <= bx0 and bx1 <= x1 and y0 <= by0 and by1 <= y1, (bx0, by0, bx1, by1))

    def test_seal_sticker_covers_hole(self):
        seal = self.parts["SERWIS"]
        self.assertEqual(seal["kind"], "seal")
        self.assertGreaterEqual(min(seal["size"]) - seal["hole"], 6.0)  # >= 3 mm adhesive around the hole

    def test_connectors_on_bottom_wall(self):
        w, _, _ = z.ENCLOSURE["outer"]
        xs = sorted(c["x"] for c in z.CONNECTORS)
        self.assertTrue(all(10 < x < w - 10 for x in xs))
        self.assertTrue(all(b - a >= 30 for a, b in zip(xs, xs[1:])))

    def test_nav_buttons_do_not_overlap_window(self):
        (_, wh), (_, cy) = z.DISPLAY["window"], z.DISPLAY["window_center"]
        for p in z.PANEL:
            if p["kind"] == "nav":
                self.assertGreater(p["xy"][1] - p["hole"] / 2, cy + wh / 2)


class Skeleton(unittest.TestCase):
    def test_render_data_is_fresh(self):
        self.assertEqual(z.LAYOUT_JSON.read_text(encoding="utf-8"), z.layout_json(),
                         "run: python3 hardware/obudowa/zalozenia.py --json")

    def test_build_refuses_without_measurements(self):
        missing = z.missing_measurements()
        self.assertTrue(missing, "all measured: replace this test with geometry checks")
        result = subprocess.run([sys.executable, str(ROOT / "hardware/obudowa/build.py")],
                                capture_output=True, text=True, cwd=ROOT / "hardware/obudowa")
        self.assertEqual(result.returncode, 2)
        for name in missing:
            self.assertIn(name, result.stdout)

    def test_measurements_are_not_guessed(self):
        for name, (description, source, value) in z.MEASUREMENTS.items():
            self.assertTrue(description and source, name)
            self.assertTrue(value is None or (isinstance(value, (int, float)) and math.isfinite(value)), name)


if __name__ == "__main__":
    unittest.main()
