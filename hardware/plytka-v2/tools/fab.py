# SPDX-License-Identifier: MIT
"""JLC assembly files of board v2: fabrication/jlc-bom.csv and fabrication/jlc-cpl.csv.

usage: fab.py   (KiCad Python, after build.sh has made the board)
In both files: every part JLC fits, SMT and through-hole (owner's decision of 2026-11-10: JLC fits everything).
Left out: parts marked "do not fit" (D20), mounting holes and the parts of design.HAND (none now), all from
tools/design.py.
"""
import csv
import math
from pathlib import Path
import re

import pcbnew as k

from design import PARTS

ROOT = Path(__file__).resolve().parents[1]
# Rotation and position come from the JLC library footprint of each part (tools/jlc_models.txt): its pads are laid
# over the pads of the board in the four rotations, the one that fits is the rotation, and the place where the
# origin of the library footprint lands is the position. The library differs per part number, not per package
# (two SOT-23-6 parts here need different rotations), so there is no table by package. The result agrees with
# every rotation seen in the JLC placement previews of 2026-11-10 and of the earlier boards.
# Parts on the bottom side: the angle is taken as seen from below, with the board turned over left to right; for
# a model drawn as the KiCad footprint this gives 180 - KiCad angle, the rule of the Fabrication Toolkit for KiCad.
# No board of this project had bottom parts fitted by JLC yet: the bottom parts need the JLC preview.
# Plain chip resistors and capacitors have no entry: both libraries draw them along x, centre at the origin.
CHIP = r'^[RC]_(0805|1206|1210|2512)_'
FIT = 0.6        # mm, largest distance between a library pad and its pad on the board (pad sizes differ a little)
# One footprint, two parts: the fuse holder is two clips, one at each pair of pads.
SPLIT = {'F1': ('1', '2')}


def models():
    found = {}
    for line in (ROOT / 'tools/jlc_models.txt').read_text().splitlines():
        if line and not line.startswith('#'):
            code, _, origin, _, pads = line.split()
            ox, oy = map(float, origin.split(','))
            found[code] = [(n, (float(x) - ox) * 0.254, (float(y) - oy) * 0.254)
                           for n, x, y in (p.split(',') for p in pads.split(';'))]
    return found


def fit(model, pads, bottom):
    """Rotation for the placement file and board position (mm) of the model origin.

    model: (number, x, y) of the library pads around the library origin; pads: (number, x, y) on the board."""
    best = []
    for turn in (0, 90, 180, 270):
        angle = math.radians(-turn if bottom else turn)
        c, s = math.cos(angle), math.sin(angle)
        # y points down: this turns counter-clockwise as seen from the top; bottom parts are mirrored first and turn the other way
        moved = [(n, (-x if bottom else x) * c + y * s, -(-x if bottom else x) * s + y * c) for n, x, y in model]
        once = [n for n, _, _ in moved if sum(m[0] == n for m in moved) == 1 and sum(p[0] == n for p in pads) == 1]
        a = [m for m in moved if m[0] in once] or moved
        b = [p for p in pads if p[0] in once] or pads
        assert len(a) == len(b), 'a library footprint with repeated pad numbers must list all pads'
        dx = sum(p[1] for p in b) / len(b) - sum(m[1] for m in a) / len(a)
        dy = sum(p[2] for p in b) / len(b) - sum(m[2] for m in a) / len(a)
        error = max(min(math.hypot(x + dx - px, y + dy - py) for pn, px, py in pads if pn == n) for n, x, y in moved)
        best.append((round(error, 3), turn, dx, dy))
    return min(best)


def main():
    board = k.LoadBoard(str(ROOT / 'cad/plytka-v2.kicad_pcb'))
    fitted = {p['ref']: p for p in PARTS if p['bom'] and not p['hand']}
    out = ROOT / 'fabrication'
    out.mkdir(exist_ok=True)
    rows = []
    library = models()
    for fp in sorted(board.GetFootprints(), key=lambda f: (re.sub(r'\d', '', f.GetReference()),
                                                           int(re.sub(r'\D', '', f.GetReference()) or 0))):
        ref = fp.GetReference()
        if ref not in fitted:
            continue
        assert not fp.IsDNP(), ref
        tht = bool(fp.GetAttributes() & k.FP_THROUGH_HOLE)
        assert tht or fp.GetAttributes() & k.FP_SMD, f'{ref}: the footprint is marked neither SMD nor through-hole'
        assert tht or not fp.IsFlipped(), f'{ref}: SMT part on the bottom side'
        name = fp.GetFPID().GetUniStringLibItemName()
        side = 'Bottom' if fp.IsFlipped() else 'Top'
        lcsc = fitted[ref]['lcsc']
        if lcsc not in library:
            assert re.match(CHIP, name), f'{ref}: no JLC footprint of {lcsc} in tools/jlc_models.txt'
            rows.append([ref, f'{k.ToMM(fp.GetPosition().x):.3f}mm', f'{-k.ToMM(fp.GetPosition().y):.3f}mm', side,
                         f'{fp.GetOrientationDegrees() % 360:.0f}'])
            continue
        pads = [(p.GetNumber(), k.ToMM(p.GetPosition().x), k.ToMM(p.GetPosition().y)) for p in fp.Pads()]
        for letter, number in zip('AB', SPLIT.get(ref, [None])):
            part = [('x', x, y) for n, x, y in pads if n == number] if number else pads
            numbers = {n for n, _, _ in library[lcsc]}
            error, turn, x, y = fit(library[lcsc], [p for p in part if p[0] in numbers], fp.IsFlipped())
            assert error < FIT, f'{ref}: the JLC footprint of {lcsc} does not fit the board pads ({error} mm)'
            rows.append([ref + letter if number else ref, f'{x:.3f}mm', f'{-y:.3f}mm', side, f'{turn}'])
    names = lambda ref: [ref + letter for letter in 'AB'] if ref in SPLIT else [ref]
    assert {r[0] for r in rows} == {n for ref in fitted for n in names(ref)}
    with (out / 'jlc-cpl.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
        w.writerows(rows)
    groups = {}
    for p in fitted.values():
        assert p['lcsc'], f"{p['ref']}: no LCSC number"
        groups.setdefault((p['lcsc'], p['footprint'].split(':')[-1]), []).append(p)
    with (out / 'jlc-bom.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #'])
        for (lcsc, footprint), items in groups.items():
            values = ' / '.join(dict.fromkeys(i['value'] for i in items))
            w.writerow([f"{values} ({items[0]['mpn']})", ','.join(n for i in items for n in names(i['ref'])), footprint, lcsc])
    hand = sorted(p['ref'] for p in PARTS if p['bom'] and p['hand'])
    print(f'fabrication/: {len(rows)} parts placed by JLC in {len(groups)} BOM lines; by hand: {" ".join(hand) or "none"}')


if __name__ == '__main__':
    main()
