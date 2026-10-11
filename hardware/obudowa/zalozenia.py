# SPDX-License-Identifier: MIT
"""Enclosure assumptions for the WICI station: what is known today and what still has to be measured.

Single source of truth for the enclosure work. Three kinds of data live here:
- CONCEPT: the front panel layout proposed in hardware/r02/obudowa.md (2026-10-08), typed in
  from that document; it drives the concept render, not a production drawing;
- N1: geometry of carrier board N1 read from its KiCad and fabrication files, so the L0
  enclosure follows the board instead of a copy of it;
- MEASUREMENTS: values that only a fit check of real parts can give. They stay None until
  measured; build.py refuses to produce geometry while any of them is missing.

Usage: python3 hardware/obudowa/zalozenia.py --json   (refreshes render/uklad.json)
"""
from pathlib import Path
import argparse
import csv
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
N1_PCB = ROOT / "hardware/dev-bench/cad/plytka-nosna.kicad_pcb"
N1_POSITIONS = ROOT / "hardware/dev-bench/fabrication/N1/assembly/positions.csv"
LAYOUT_JSON = HERE / "render/uklad.json"

# --- CONCEPT: hardware/r02/obudowa.md, sections "Obudowa", "Okno ekranu", "Układ panelu" ---
# Millimetres from the outer top-left corner of the lid; x to the right, y down.
ENCLOSURE = {
    "model": "Hammond 1599KBAT",
    "outer": (220.0, 140.0, 40.0),
    "inner": (213.6, 133.6, 33.0),
    "foil_recess": (206.25, 126.5, 1.0),
    "material": "ABS UL94 V-0",
}
DISPLAY = {
    "panel": "Sharp LS027B7DH01A",
    "outline": (62.8, 42.82, 1.64),
    "active": (58.8, 35.28),
    "pixels": (400, 240),
    "window": (61.5, 38.0),
    "window_center": (52.0, 42.0),
}
# kind: nav = E-Switch PV6 (hole 16 mm), power = PV6 recessed ~3 mm in a foil ring,
# guard = toggle switch with flip guard (CW Industries GT-4R), led = 5 mm alarm LED,
# seal = hole over the preparation button covered by a numbered VOID sticker (F113;
# replaces the sealed service cover of obudowa.md for the pilot).
PANEL = [
    {"id": "WSTECZ", "kind": "nav", "xy": (30.0, 98.0), "hole": 16.0, "uk": "НАЗАД", "en": "BACK"},
    {"id": "GÓRA", "kind": "nav", "xy": (62.0, 98.0), "hole": 16.0, "uk": "ВГОРУ", "en": "UP"},
    {"id": "DÓŁ", "kind": "nav", "xy": (94.0, 98.0), "hole": 16.0, "uk": "ВНИЗ", "en": "DOWN"},
    {"id": "OK", "kind": "nav", "xy": (126.0, 98.0), "hole": 16.0, "uk": "OK", "en": "OK"},
    {"id": "ALARM", "kind": "led", "xy": (185.0, 22.0), "hole": 5.0},
    {"id": "CISZA", "kind": "guard", "xy": (185.0, 58.0), "hole": None},
    {"id": "WYŁĄCZNIK", "kind": "power", "xy": (185.0, 100.0), "hole": 16.0},
    {"id": "PRZYGOTOWANIE", "kind": "seal", "xy": (150.0, 122.0), "hole": 4.0, "size": (22.0, 12.0)},
]
# Bottom wall, x from the left outer edge. Axis height above the board is a measurement.
CONNECTORS = [
    {"id": "USB-C", "x": 60.0, "part": "USB-C z zatyczką na uwięzi"},
    {"id": "12 V", "x": 110.0, "part": "Switchcraft EN3, 2 styki, otwór 15,5 mm"},
    {"id": "ANTENA", "x": 170.0, "part": "SMA-F przepustowe z nakrętką na ściance"},
]
# Rules stated in obudowa.md; tests check the layout against them.
RULES = {
    "nav_pitch": 32.0,         # spacing of the navigation row
    "nav_gap_min": 16.0,       # free space between navigation buttons (gloves)
    "side_column_gap_min": 30.0,  # CISZA and power switch from the navigation row
    "window_margin_min": 1.0,  # window around the active area, each side
}

# --- MEASUREMENTS: none of these may be guessed; fill in from the fit check ---
# Each entry: description, how to obtain it, value (None = not measured yet).
MEASUREMENTS = {
    "devkitc_top": ("Wysokość najwyższego punktu DevKitC w gniazdach J5/J6 nad górną powierzchnią N1 [mm]",
                    "suwmiarka po wpięciu DevKitC rev.1.1 w N1", None),
    "button_top": ("Wysokość nasadki B32-1310 na B3F-4055 nad N1 [mm], przycisk zwolniony",
                   "suwmiarka na zmontowanej N1", None),
    "display_top": ("Wysokość szkła panelu Sharp nad N1 po przyklejeniu na piance [mm]",
                    "suwmiarka po teście ekranu i przyklejeniu", None),
    "fpc_free_length": ("Długość taśmy FPC panelu od szkła do czoła J7 po wpięciu [mm]",
                        "przymiarka z rzeczywistym panelem", None),
    "wio_position": ("Położenie i wysokość Wio SX1262 z adapterem oraz wyjście anteny u.FL na N1 [mm]",
                     "po montażu adaptera Wio w L0", None),
    "usb_otg_position": ("Położenie gniazda USB/OTG DevKitC względem obrysu N1 (x, y, wysokość osi) [mm]",
                         "po wpięciu DevKitC", None),
    "hammond_bosses": ("Położenie i wysokość słupków pokrywy Hammond 1599KBAT [mm]",
                       "model STEP Hammonda albo próbka", None),
    "hammond_lid_screws": ("Położenie śrub pokrywy Hammond 1599KBAT (od frontu czy od spodu)",
                           "model STEP Hammonda albo próbka", None),
    "pilot_board": ("Płytka MCU+SX1262 stacji pilotażowej: model, obrys, złącze anteny",
                    "decyzja przed pilotażem (elektronika.md, stacja pilotażowa)", None),
    "guard_footprint": ("Obrys podstawy i wysokość klapki GT-4R z przełącznikiem GTS [mm]",
                        "karta producenta i próbka", None),
}


def missing_measurements() -> list[str]:
    """Names of measurements that are still None."""
    return [name for name, (_, _, value) in MEASUREMENTS.items() if value is None]


# --- N1 geometry from the board files ---
def n1_parts() -> dict[str, dict]:
    """Component positions of N1 from positions.csv (origin bottom-left, y up, mm)."""
    with N1_POSITIONS.open(encoding="utf-8", newline="") as handle:
        return {row["Ref"]: {"value": row["Val"], "x": float(row["PosX"]), "y": float(row["PosY"]),
                             "rot": float(row["Rot"])} for row in csv.DictReader(handle)}


def _pcb_text() -> str:
    return N1_PCB.read_text(encoding="utf-8")


def _aux_origin(text: str) -> tuple[float, float]:
    x, y = re.search(r"\(aux_axis_origin ([\d.]+) ([\d.]+)\)", text).groups()
    return float(x), float(y)


def n1_outline() -> tuple[float, float]:
    """Width and height of the N1 outline from the Edge.Cuts lines."""
    text = _pcb_text()
    points = []
    for block in re.findall(r"\(gr_line\s+\(start ([\d.]+) ([\d.]+)\)\s+\(end ([\d.]+) ([\d.]+)\).*?\(layer \"Edge\.Cuts\"\)",
                            text, re.S):
        points += [(float(block[0]), float(block[1])), (float(block[2]), float(block[3]))]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3)


def n1_holes() -> list[dict]:
    """Mounting holes of N1 in positions.csv coordinates (origin bottom-left, y up)."""
    text = _pcb_text()
    ox, oy = _aux_origin(text)
    holes = []
    for lib, x, y in re.findall(r"\(footprint \"((?:MountingHole|WICI):MountingHole[^\"]*)\".*?\(at ([\d.]+) ([\d.]+)\)",
                                text, re.S):
        holes.append({"footprint": lib, "x": round(float(x) - ox, 3), "y": round(oy - float(y), 3),
                      "arduino": "Arduino" in lib})
    return sorted(holes, key=lambda h: (h["y"], h["x"]))


# --- Concept layout for the render ---
def layout() -> dict:
    """Concept data passed to render/stacja.html; derived only from CONCEPT above."""
    return {
        "source": "hardware/r02/obudowa.md (2026-10-08), naklejka zamiast pokrywy serwisowej (F113); koncepcja, nie rysunek wykonawczy",
        "enclosure": ENCLOSURE,
        "display": DISPLAY,
        "panel": PANEL,
        "connectors": CONNECTORS,
        "screen_rows": ["RADIO WŁĄCZONE", "KONTAKT 12 MIN TEMU", "OGNIWA: OKOŁO 46 H", "", "NOWE WIADOMOŚCI: 1"],
        "unmeasured": missing_measurements(),
    }


def layout_json() -> str:
    return json.dumps(layout(), ensure_ascii=False, indent=1) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="refresh render/uklad.json")
    args = parser.parse_args()
    if args.json:
        LAYOUT_JSON.write_text(layout_json(), encoding="utf-8")
        print(f"zapisano {LAYOUT_JSON.relative_to(ROOT)}")
    width, height = n1_outline()
    print(f"N1: {width} x {height} mm, {len(n1_holes())} otworów, {len(n1_parts())} części")
    missing = missing_measurements()
    print(f"Brakujące pomiary: {len(missing)}/{len(MEASUREMENTS)}")


if __name__ == "__main__":
    main()
