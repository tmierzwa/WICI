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
import os
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REV = 'N1'


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
    with zipfile.ZipFile(base / f'wici-plytka-nosna-{REV}-gerber.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(list(g.iterdir()) + list(d.iterdir())):
            if f.suffix.lower() != '.pdf':
                z.write(f, f.name)
    print('exported to', base)


if __name__ == '__main__':
    main()
