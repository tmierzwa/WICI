# SPDX-License-Identifier: MIT
"""Vendor the referenced KiCad 10.0.6 footprints and draw the own ones.

usage: prepare_footprints.py <KiCad footprints dir>
The toggle land pattern follows the E-Switch 100SP1T1B4M2QE drawing T111597
rev. G (three terminals at 4.70 mm, recommended hole 1.85 mm; body 12.70 mm
along the terminals, 6.86 mm across).
"""
from pathlib import Path
import shutil
import sys

from design import PARTS
from sexpr import Atom as A, dump

ROOT = Path(__file__).resolve().parents[1]

TOGGLE = '''(footprint "Toggle_ESwitch_100SP1T1B4M2QE"
 (version 20241229) (generator "pcbnew") (layer "F.Cu")
 (descr "E-Switch 100SP1T1B4M2QE SPDT toggle, PCB terminals 4.70 mm, holes 1.85 mm (drawing T111597 rev. G). Own land pattern.")
 (attr through_hole)
 (property "Reference" "REF**" (at 0 -5.2 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
 (property "Value" "100SP1T1B4M2QE" (at 0 5.2 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
 (fp_rect (start -6.35 -3.43) (end 6.35 3.43) (stroke (width 0.1) (type solid)) (fill none) (layer "F.Fab"))
 (fp_rect (start -6.47 -3.55) (end 6.47 3.55) (stroke (width 0.12) (type solid)) (fill none) (layer "F.SilkS"))
 (fp_rect (start -6.85 -3.95) (end 6.85 3.95) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))
 (fp_text user "1" (at -4.7 2.4 0) (layer "F.SilkS") (effects (font (size 1.0 1.0) (thickness 0.15))))
 (pad "1" thru_hole rect (at -4.7 0) (size 2.8 2.8) (drill 1.85) (layers "*.Cu" "*.Mask"))
 (pad "2" thru_hole circle (at 0 0) (size 2.8 2.8) (drill 1.85) (layers "*.Cu" "*.Mask"))
 (pad "3" thru_hole circle (at 4.7 0) (size 2.8 2.8) (drill 1.85) (layers "*.Cu" "*.Mask"))
)
'''

# Arduino Uno R3 holes sit 3.56 mm from header pins, so the KiCad M3 courtyard
# (6.4 mm) overlaps the headers. This hole keeps 3.2 mm with a courtyard only around the hole:
# fasteners there are M2.5 or nylon M3 with a head of at most 4.4 mm.
UNO_HOLE = '''(footprint "MountingHole_3.2mm_Arduino"
 (version 20241229) (generator "pcbnew") (layer "F.Cu")
 (descr "Arduino Uno R3 mounting hole, 3.2 mm NPTH, courtyard only around the hole, next to the headers. Own footprint.")
 (attr exclude_from_pos_files exclude_from_bom)
 (property "Reference" "REF**" (at 0 -3.2 0) (layer "F.SilkS") (hide yes) (effects (font (size 1 1) (thickness 0.15))))
 (property "Value" "MountingHole_3.2mm_Arduino" (at 0 3.2 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
 (fp_circle (center 0 0) (end 1.7 0) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))
 (fp_circle (center 0 0) (end 2.1 0) (stroke (width 0.1) (type solid)) (fill none) (layer "Cmts.User"))
 (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "*.Cu" "*.Mask"))
)
'''


def prepare(source):
    """Copy only referenced footprints and register project-local libraries."""
    out = ROOT / 'cad/footprints'
    names = sorted({p['footprint'] for p in PARTS})
    libs = set()
    for name in names:
        lib, fp = name.split(':')
        libs.add(lib)
        target = out / (lib + '.pretty')
        target.mkdir(parents=True, exist_ok=True)
        if lib == 'WICI':
            continue
        shutil.copy2(source / (lib + '.pretty') / (fp + '.kicad_mod'), target)
    (out / 'WICI.pretty/Toggle_ESwitch_100SP1T1B4M2QE.kicad_mod').write_text(TOGGLE)
    (out / 'WICI.pretty/MountingHole_3.2mm_Arduino.kicad_mod').write_text(UNO_HOLE)
    table = [A('fp_lib_table'), [A('version'), 7]]
    for lib in sorted(libs):
        table.append([A('lib'), [A('name'), lib], [A('type'), 'KiCad'],
                      [A('uri'), '${KIPRJMOD}/footprints/' + lib + '.pretty'], [A('options'), ''],
                      [A('descr'), 'KiCad 10.0.6 subset or own (WICI), see KICAD-LIBRARY-LICENSE.md']])
    (ROOT / 'cad/fp-lib-table').write_text(dump(table) + '\n')
    print(f'{len(names)} footprints prepared in {len(libs)} libraries')


if __name__ == '__main__':
    prepare(Path(sys.argv[1]))
