# SPDX-License-Identifier: MIT
"""Export the N1 fabrication and assembly files from the checked board.

Gerbers, drills and positions use the drill/place origin that make_board.py
sets at the lower-left board corner (kicad-cli calls it 'plot' for drills). The
schematic PDF goes next to the project (hardware/dev-bench/schemat.pdf).

usage: export_fabrication.py [--kicad-cli PATH]
Run only after ERC/DRC = 0. KiCad exports carry creation times, so files
are compared by geometry, not bytes; the ZIP is a convenience for the fab.
"""
from pathlib import Path
import argparse
import csv
import os
import shutil
import subprocess
import zipfile

from design import BOARD_W, BOARD_H, EXTRAS, NOTCH_P5, PARTS

ROOT = Path(__file__).resolve().parents[1]
REV = 'N1'
SMD_PACKAGES = ('R_', 'C_', 'SOT-', 'D_SOD')

# English one-line descriptions for the assembler BOM; bom.csv keeps the Polish detail.
DESCRIPTION = {
    'Adafruit 85': 'Arduino R3 stacking header kit (1x10, 2x 1x8, 1x6), long tails',
    'TFM-110-01-L-D': 'Tiger Eye 2x10 terminal strip, 1.27 mm, through-hole, mates Samtec SFM',
    'PPTC221LFBN-RC': '1x22 female header, 2.54 mm, vertical, THT',
    'PPTC091LFBN-RC': '1x9 female header, 2.54 mm, vertical, THT',
    '61300911121': '1x9 male pin header, 2.54 mm, THT',
    '61300211121': '1x2 male pin header, 2.54 mm, THT',
    '1715721': '2-pole screw terminal, 5.08 mm, THT',
    'B3F-4055': 'tactile switch 12x12 mm, THT',
    '100SP1T1B4M2QE': 'toggle switch SPDT ON-NONE-ON, PCB pins, THT',
    'B3F-1000': 'tactile switch 6x6 mm, THT',
    'WP7113ID': 'LED 5 mm red diffused, THT',
    'CEM-1203(42)': 'magnetic buzzer 12 mm, external drive, THT (hand solder only)',
    'MMBT3904LT1G': 'NPN transistor 40 V 200 mA, SOT-23',
    '1N4148W-7-F': 'switching diode 75 V, SOD-123',
    'BAT54SLT1G': 'dual Schottky diode series, SOT-23',
    'CL21A106KAYNNNC': 'MLCC 10 uF 25 V X5R 0805',
    'CL21B104KBCNNNC': 'MLCC 100 nF 50 V X7R 0805',
}


def smd(footprint):
    return footprint.split(':')[1].startswith(SMD_PACKAGES)


def describe(p):
    if p['mpn'] in DESCRIPTION:
        return DESCRIPTION[p['mpn']]
    if p['ref'][0] == 'R':
        return f"resistor {p['value'].replace('R', ' ohm')} 1 % {p['footprint'].split(':')[1][2:6]}"
    raise SystemExit(f"no English description for {p['mpn']}")


def write_assembly_bom(path):
    """Assembler BOM, one row per part number, English, with the build split."""
    groups = {}
    for p in PARTS:
        if p['bom']:
            groups.setdefault((p['mpn'], p['value'] if p['ref'][0] in 'RC' else '', p['variant']), []).append(p)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Designator', 'Qty per board', 'Value', 'Manufacturer', 'MPN', 'Description',
                    'Footprint', 'Type', 'Fit', 'Placed by'])
        for (mpn, _value, variant), items in sorted(groups.items(), key=lambda kv: (not smd(kv[1][0]['footprint']),
                                                                                    kv[1][0]['ref'])):
            p = items[0]
            kit = mpn == 'Adafruit 85'
            fit = {'A': 'variant A only', 'B': 'variant B only', 'AB': 'all'}[variant]
            w.writerow([' '.join(i['ref'] for i in items), '1 kit' if kit else len(items),
                        p['value'] if p['ref'][0] in 'RC' else '', p['manufacturer'].replace('ü', 'u'), mpn,
                        describe(p), p['footprint'].split(':')[1], 'SMD' if smd(p['footprint']) else 'THT', fit,
                        'assembler' if smd(p['footprint']) else 'owner (hand solder)'])
        for refs, qty, manufacturer, mpn, _spec, _variant, _note in EXTRAS:
            if mpn:  # loose items with a part number; standoffs are bought by the owner
                w.writerow(['', qty, '', manufacturer.replace('ü', 'u'), mpn,
                            {'60900213421': 'jumper 2.54 mm', 'B32-1310': 'cap for B3F tactile switch'}[mpn],
                            'loose item', 'loose', 'all', f'owner ({refs})'])


def write_cpl(positions, path):
    """SMD placement list in the column names assemblers expect (mm, top side)."""
    with positions.open(newline='') as f, path.open('w', newline='') as out:
        w = csv.writer(out)
        w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
        for r in csv.DictReader(f):
            if r['Package'].startswith(SMD_PACKAGES):
                w.writerow([r['Ref'], f"{float(r['PosX']):.3f}", f"{float(r['PosY']):.3f}", 'Top',
                            f"{float(r['Rot']):.0f}"])


def write_fab_notes(path, drills):
    notch_w = round(BOARD_W - NOTCH_P5[0], 2)
    notch_h = round(NOTCH_P5[3] - NOTCH_P5[1], 2)
    smd_count = sum(1 for p in PARTS if p['bom'] and smd(p['footprint']))
    path.write_text(f"""WICI carrier board {REV} - fabrication and assembly notes
=====================================================
Open hardware, CERN-OHL-P-2.0. Source: https://github.com/tmierzwa/WICI (hardware/dev-bench).
Quantity: 5 boards (pilot). Prototype tool board, no RF, no impedance control.

PCB
- 2 layers, FR-4 (Tg >= 130 C), finished thickness 1.6 mm +/-10 %.
- Copper 35 um (1 oz) both sides. Min track/space 0.2 mm, min annular ring 0.175 mm (J9/J10).
- Surface finish: lead-free HASL (all parts hand soldered or reflowed; ENIG acceptable).
- Solder mask green both sides; silkscreen white, top side only (bottom silk file is empty).
- Outline {BOARD_W:.0f} x {BOARD_H:.0f} mm (Edge_Cuts) with a rectangular notch {notch_w} x {notch_h} mm on the
  right edge; notch inner corners at router radius (up to 1 mm is fine).
- Drill sizes in the Excellon files are finished hole sizes. PTH and NPTH in separate files.
  Hole sizes: {drills}.
- No plated slots, no castellations, no blind/buried vias. Vias 0.8/0.4 mm, may be tented or open.
- Electrical test 100 %. IPC-A-600 class 2.
- Fab order number: if needed, on the bottom side (no bottom silkscreen), clear of pads.
- Origin of Gerbers, drills and positions: lower-left board corner.

Assembly (optional quote)
- Top side only. Assembler places the {smd_count} SMD parts (0805, 1206, SOT-23, SOD-123):
  assembly/bom-assembly.csv rows with 'Placed by = assembler', positions in assembly/cpl-smd.csv.
- All through-hole parts, connectors and modules are fitted by the owner; do not fit them.
- Polarity: Q1 and D3 SOT-23 pin 1 per footprint; D2 cathode band at the marked side
  (assembly/montaz.pdf). No fiducials: use pads or add panel rails with fiducials.
- Modules (nRF52840-DK, ESP32-S3-DevKitC-1, CC1120EM, X-NUCLEO-S2868A2, Adafruit 4694/4719) are not
  part of the order.
""", encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--kicad-cli', default=os.environ.get(
        'KICAD_CLI', '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'))
    cli = ap.parse_args().kicad_cli
    if subprocess.check_output([cli, 'version'], text=True).strip() != '10.0.6':
        raise SystemExit('KiCad 10.0.6 required')
    base = ROOT / 'fabrication' / REV
    g, d, a = base / 'gerbers', base / 'drill', base / 'assembly'
    for folder in (g, d, a):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
    board = ROOT / 'cad/plytka-nosna.kicad_pcb'

    def pcb(*args):
        subprocess.run([cli, 'pcb', 'export', *map(str, args), str(board)], check=True,
                       stdout=subprocess.DEVNULL)
    pcb('gerbers', '--layers', 'F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,Edge.Cuts',
        '--subtract-soldermask', '--use-drill-file-origin', '--output', str(g) + '/')
    pcb('drill', '--format', 'excellon', '--excellon-units', 'mm', '--excellon-zeros-format', 'decimal',
        '--excellon-separate-th', '--drill-origin', 'plot', '--generate-map', '--map-format', 'pdf',
        '--output', str(d) + '/')
    pcb('pos', '--format', 'csv', '--units', 'mm', '--side', 'front', '--use-drill-file-origin',
        '--output', a / 'positions.csv')
    pcb('pdf', '--layers', 'F.Fab,F.SilkS,Edge.Cuts', '--mode-single', '--black-and-white',
        '--sketch-pads-on-fab-layers', '--scale', '1.5', '--output', a / 'montaz.pdf')
    pcb('pdf', '--layers', 'Edge.Cuts,F.Fab,F.SilkS,Dwgs.User', '--mode-single', '--black-and-white',
        '--sketch-pads-on-fab-layers', '--drill-shape-opt', '2', '--scale', '1',
        '--output', base / 'mechanika-1-do-1.pdf')
    subprocess.run([cli, 'sch', 'export', 'pdf', '--output', str(ROOT / 'schemat.pdf'),
                    str(ROOT / 'cad/plytka-nosna.kicad_sch')], check=True, stdout=subprocess.DEVNULL)
    shutil.copyfile(ROOT / 'bom.csv', a / 'bom.csv')
    write_assembly_bom(a / 'bom-assembly.csv')
    write_cpl(a / 'positions.csv', a / 'cpl-smd.csv')
    sizes = set()
    for f in d.glob('*.drl'):
        for line in f.read_text().splitlines():
            if line.startswith('T') and 'C' in line:
                sizes.add((f.stem.rsplit('-', 1)[1], float(line.split('C')[1])))
    drills = '; '.join(f"{kind} " + ', '.join(f'{x:g}' for x in sorted(v for k, v in sizes if k == kind)) + ' mm'
                       for kind in ('PTH', 'NPTH'))
    write_fab_notes(base / 'FAB-NOTES.txt', drills)
    with zipfile.ZipFile(base / f'wici-plytka-nosna-{REV}-gerber.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(list(g.iterdir()) + list(d.iterdir())):
            if f.suffix.lower() != '.pdf':
                z.write(f, f.name)
        z.write(base / 'FAB-NOTES.txt', 'FAB-NOTES.txt')
    print('exported to', base)


if __name__ == '__main__':
    main()
