# SPDX-License-Identifier: MIT
"""Write the project file and footprint table of the preliminary v2 schematic.

usage: prepare_libraries.py   (run with the KiCad Python, it needs pcbnew)
KiCad library footprints are referenced from the KiCad 10.0.6 installation; nothing is vendored until the
PCB exists. Own footprints (WICI) are taken from the boards that already define them: the toggle from
hardware/dev-bench, the LTC3115-1 and SRP1038A land patterns from the JLC test board (hardware/przetwornica-3v3).
"""
import json
from pathlib import Path
import re
import shutil
import uuid

import pcbnew

from design import PARTS

ROOT = Path(__file__).resolve().parents[1]
HW = ROOT.parent
NAME = 'plytka-v2'
OWN_FROM_TEST_BOARD = {'U1': 'LTC3115-1_FE20_CA', 'L1': 'L_Bourns_SRP1038A'}
NS = uuid.UUID('4d0c3a2e-8b1f-4f7e-9a51-6c2b7e0d9f31')  # as in make_schematic.py


def main():
    cad = ROOT / 'cad'
    wici = cad / 'footprints' / 'WICI.pretty'
    wici.mkdir(parents=True, exist_ok=True)
    shutil.copy(HW / 'dev-bench/cad/footprints/WICI.pretty/Toggle_ESwitch_100SP1T1B4M2QE.kicad_mod', wici)
    board = pcbnew.LoadBoard(str(HW / 'przetwornica-3v3/cad/przetwornica-3v3.kicad_pcb'))
    for fp in board.GetFootprints():
        name = OWN_FROM_TEST_BOARD.get(fp.GetReference())
        if name:
            own = pcbnew.FOOTPRINT(fp)
            own.SetFPID(pcbnew.LIB_ID('', name))
            own.SetPosition(pcbnew.VECTOR2I(0, 0))
            own.SetOrientationDegrees(0)
            own.SetReference('REF**')
            pcbnew.FootprintSave(str(wici), own)
            # FootprintSave gives new uuids on every run; number them so the file only changes with the footprint
            path = wici / (name + '.kicad_mod')
            n = iter(range(10 ** 6))
            path.write_text(re.sub(r'\(uuid "[^"]+"\)', lambda m: f'(uuid "{uuid.uuid5(NS, f"{name}.{next(n)}")}")',
                                   path.read_text()))
    libs = sorted({p['footprint'].split(':')[0] for p in PARTS})
    rows = []
    for lib in libs:
        uri = '${KIPRJMOD}/footprints/WICI.pretty' if lib == 'WICI' else '${KICAD10_FOOTPRINT_DIR}/' + lib + '.pretty'
        rows.append(f'  (lib (name "{lib}") (type "KiCad") (uri "{uri}") (options "") '
                    f'(descr "{"own, CERN-OHL-P-2.0" if lib == "WICI" else "KiCad 10.0.6 library"}"))')
    (cad / 'fp-lib-table').write_text('(fp_lib_table\n  (version 7)\n' + '\n'.join(rows) + ')\n')
    pro = {'boards': [], 'libraries': {'pinned_footprint_libs': [], 'pinned_symbol_libs': []},
           'meta': {'filename': NAME + '.kicad_pro', 'version': 3},
           'schematic': {'page_layout_descr_file': ''}, 'sheets': [], 'text_variables': {}}
    (cad / (NAME + '.kicad_pro')).write_text(json.dumps(pro, indent=2) + '\n')
    print(f'{len(libs)} footprint libraries, own footprints in {wici.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
