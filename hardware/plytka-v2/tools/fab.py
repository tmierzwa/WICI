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
# Rotation JLC adds to the KiCad angle, by footprint name: the JLC library models of these packages are turned
# against the KiCad footprints. SOIC and the LTC3115-1 TSSOP: as on the two boards already assembled at JLC
# (hardware/dev-bench, hardware/przetwornica-3v3, previews of 2026-10-31). SOT-23 family, SC-70 and TSOT: the
# public table of the Fabrication Toolkit for KiCad (bennymeg, transformations.csv, read 2026-11-10). WSON-12: that
# table has no WSON entry, its DFN entry (270) is used; not confirmed. Every other package: 0, not confirmed.
# The JLC placement preview decides; the README lists what to look at.
TURN = [(r'^SOT-23', 180), (r'^TSOT-23', 180), (r'^SOT-363', 180), (r'^SOIC-', 270), (r'^LTC3115-1_FE20', 270),
        (r'^WSON-', 270)]


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
        turn = next((t for pattern, t in TURN if re.match(pattern, name)), 0)
        pos = fp.GetPosition()
        rows.append([ref, f'{k.ToMM(pos.x):.3f}mm', f'{-k.ToMM(pos.y):.3f}mm', 'Top',
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
