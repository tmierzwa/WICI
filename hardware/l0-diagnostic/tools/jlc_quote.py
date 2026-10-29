#!/usr/bin/env python3
"""BOM and CPL for a JLCPCB PCBA quote of the whole L0 board (SMD and THT).

Built from the N1.1 board (J7 moved for the 13.5 mm panel FPC, F118); an order
still waits for the 1:1 fit of N1.1. SMD rows come from the N1 JLC files (R12 as
1 kOhm, as L0 requires). THT rows use JLC library parts chosen
from the jlcparts snapshot of 2026-10-28; their positions are the pad-box centres
from the board file, each pad checked against a hole in the PTH drill file.
"""
import csv
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
N1 = ROOT / 'hardware/dev-bench'
ASSEMBLY = N1 / 'fabrication/N1/assembly'
OUT = ROOT / 'hardware/l0-diagnostic/wycena-jlc'
BOARD_H, ORIGIN = 100.0, 30.0  # board height and its corner on the KiCad page

# ref list, comment, LCSC part; all through-hole, all from the JLC library
THT = [
    ('J5,J6', 'ZX-PM2.54-1-22PY (gniazdo 1x22 2,54 mm, zamiennik PPTC221LFBN-RC)', 'C7499337'),
    ('SW1,SW2,SW3,SW4', 'B3F-4055', 'C84931'),
    ('SW6', 'B3F-1000', 'C93157'),
    ('SW5', '100SP1T1B4M2QE (global sourcing)', 'C273353'),
    ('D1', 'WP7113ID', 'C6926004'),
    ('BZ1', 'YS-MBZ12085C05R42 (zamiennik CEM-1203(42), rozstaw do sprawdzenia)', 'C409842'),
    ('J11', 'A2541WV-9P (zamiennik 61300911121)', 'C225484'),
    ('JP1,JP2', 'A2541WV-2P (zamiennik 61300211121)', 'C225477'),
    ('J12', '1715721', 'C480516'),
]
# stations A/B only, not fitted in L0 (MONTAZ-I-TESTY.md, section 1)
# JLC preview 2026-10-29: 2.54 mm header models lie along x at 0 deg (KiCad: along y);
# the LED model has the anode on pad 1, where KiCad has the cathode
JLC_THT_ROTATION = {'PinHeader_': 90, 'PinSocket_': 90, 'LED_D5.0mm': 180}
DNP = {'J1', 'J2', 'J3', 'J4', 'J9', 'J10', 'JP3'}


def footprints(pcb):
    """{ref: (footprint, rot, [(pad x, pad y)])}, pads in board coordinates, y up (as positions.csv)."""
    out = {}
    for m in re.finditer(r'\(footprint "[^":]*:([^"]+)"', pcb):
        depth, i = 0, m.start()
        while True:
            depth += {'(': 1, ')': -1}.get(pcb[i], 0)
            if depth == 0:
                break
            i += 1
        fp = pcb[m.start():i]
        ref = re.search(r'\(property "Reference" "([^"]+)"', fp).group(1)
        at = re.search(r'\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', fp)
        x0, y0, rot = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
        a = math.radians(rot)
        pads = []
        for p in re.finditer(r'\(pad "[^"]*" thru_hole \w+\s*\(at ([-\d.]+) ([-\d.]+)[^)]*\)\s*\(size ([\d.]+) ([\d.]+)\)', fp):
            px, py = float(p.group(1)), float(p.group(2))
            x = x0 + px * math.cos(a) + py * math.sin(a)
            y = y0 - px * math.sin(a) + py * math.cos(a)
            pads.append((x - ORIGIN, BOARD_H - (y - ORIGIN)))
        out[ref] = (m.group(1), rot, pads)
    return out


def holes(drl):
    return [(float(x), float(y)) for x, y in re.findall(r'^X([-\d.]+)Y([-\d.]+)$', drl, re.M)]


def main():
    fps = footprints((N1 / 'cad/plytka-nosna.kicad_pcb').read_text(encoding='utf-8'))
    pth = holes((N1 / 'fabrication/N1/drill/plytka-nosna-PTH.drl').read_text())
    OUT.mkdir(exist_ok=True)

    with (ASSEMBLY / 'jlc-bom.csv').open(newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    header, smd = rows[0], rows[1:]
    for r in smd:  # R12: 10 kOhm on the N1 BOM, 1 kOhm in L0
        refs = r[1].split(',')
        if 'R12' in refs and r[0].startswith('10k'):
            r[1] = ','.join(x for x in refs if x != 'R12')
        if r[0].startswith('1k '):
            r[1] += ',R12'
    with (OUT / 'bom-jlc-L0.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(smd)
        for refs, comment, lcsc in THT:
            w.writerow([comment, refs, fps[refs.split(',')[0]][0], lcsc])

    with (ASSEMBLY / 'jlc-cpl.csv').open(newline='', encoding='utf-8') as f:
        cpl = list(csv.reader(f))
    placed = {r[0] for r in cpl[1:]}
    with (OUT / 'cpl-jlc-L0.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerows(cpl)
        for refs, _, _ in THT:
            for ref in refs.split(','):
                fp, rot, pads = fps[ref]
                rot += next((v for k, v in JLC_THT_ROTATION.items() if fp.startswith(k)), 0)
                for px, py in pads:
                    assert any(math.hypot(px - hx, py - hy) < 0.01 for hx, hy in pth), (ref, px, py)
                xs, ys = [p[0] for p in pads], [p[1] for p in pads]
                w.writerow([ref, f'{(min(xs) + max(xs)) / 2:.3f}', f'{(min(ys) + max(ys)) / 2:.3f}', 'Top',
                            f'{rot % 360:.0f}'])
                placed.add(ref)

    missing = set(fps) - placed - DNP - {r for r in fps if r.startswith(('H', 'TP'))}
    assert not missing, f'parts with no row and not DNP: {sorted(missing)}'
    print(f'{len(placed)} placed, {len(DNP)} DNP -> {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
