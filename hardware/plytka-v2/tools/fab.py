# SPDX-License-Identifier: MIT
"""JLC assembly files of board v2: fabrication/jlc-bom.csv and fabrication/jlc-cpl.csv.

usage: fab.py   (KiCad Python, after build.sh has made the board)
In both files: every part the SMT assembler fits. Left out: parts marked "do not fit" (D20), mounting holes,
through-hole parts and the SMT parts of design.HAND_SMT (soldered by hand), all from tools/design.py.
"""
import csv
from pathlib import Path
import re

import pcbnew as k

from design import PARTS

ROOT = Path(__file__).resolve().parents[1]
# Rotation JLC adds to the KiCad angle: the JLC library models of these parts are turned against the KiCad
# footprints. First source: the two boards already assembled at JLC (SOIC, the LTC3115-1 TSSOP) and the public
# table of the Fabrication Toolkit for KiCad (SOT-23 family). Then every part was compared with the JLC placement
# preview of 2026-11-10 (pin 1 mark of the model against pin 1 of the board), which changed four entries: the WSON-12
# model lies as the KiCad footprint (0, not 270 as for DFN), and the models of the TSOT-23-8, of the SC-70-6 and of
# the USBLC6-2SC6 are a quarter turn away from the other SOT-23 parts (270, not 180).
TURN = [(r'^TSOT-23', 270), (r'^SOT-363', 270), (r'^SOT-23', 180), (r'^SOIC-', 270), (r'^LTC3115-1_FE20', 270)]
TURN_PART = {'C7519': 270}          # by LCSC number: USBLC6-2SC6 (U8), unlike the other SOT-23-6 (U2)
# Position: JLC puts the centre of its model there. For these footprints the KiCad origin is not that centre and
# the centre of all pads is used (USB-C socket: in the preview the model sat 1.5 mm off its pads).
CENTRE_OF_PADS = (r'^USB_C_Receptacle_HRO_TYPE-C-31-M-12',)


def main():
    board = k.LoadBoard(str(ROOT / 'cad/plytka-v2.kicad_pcb'))
    fitted = {p['ref']: p for p in PARTS if p['bom'] and not p['hand']}
    out = ROOT / 'fabrication'
    out.mkdir(exist_ok=True)
    rows = []
    for fp in sorted(board.GetFootprints(), key=lambda f: (re.sub(r'\d', '', f.GetReference()),
                                                           int(re.sub(r'\D', '', f.GetReference()) or 0))):
        ref = fp.GetReference()
        if ref not in fitted:
            continue
        assert not fp.IsDNP() and not fp.IsFlipped(), ref
        assert fp.GetAttributes() & k.FP_SMD, f'{ref}: the footprint is not marked SMD'
        name = fp.GetFPID().GetUniStringLibItemName()
        turn = TURN_PART.get(fitted[ref]['lcsc'], next((t for pattern, t in TURN if re.match(pattern, name)), 0))
        x, y = k.ToMM(fp.GetPosition().x), k.ToMM(fp.GetPosition().y)
        if any(re.match(pattern, name) for pattern in CENTRE_OF_PADS):
            boxes = [p.GetBoundingBox() for p in fp.Pads()]
            x = k.ToMM(min(b.GetLeft() for b in boxes) + max(b.GetRight() for b in boxes)) / 2
            y = k.ToMM(min(b.GetTop() for b in boxes) + max(b.GetBottom() for b in boxes)) / 2
        rows.append([ref, f'{x:.3f}mm', f'{-y:.3f}mm', 'Top',
                     f'{(fp.GetOrientationDegrees() + turn) % 360:.0f}'])
    assert {r[0] for r in rows} == set(fitted), set(fitted) ^ {r[0] for r in rows}
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
            w.writerow([f"{values} ({items[0]['mpn']})", ','.join(i['ref'] for i in items), footprint, lcsc])
    hand = sorted(p['ref'] for p in PARTS if p['bom'] and p['hand'])
    print(f'fabrication/: {len(rows)} parts placed by JLC in {len(groups)} BOM lines; by hand: {" ".join(hand)}')


if __name__ == '__main__':
    main()
