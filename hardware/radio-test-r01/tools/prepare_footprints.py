# SPDX-License-Identifier: GPL-3.0-or-later
"""Vendor the exact KiCad footprints and build a USB footprint from dimensions.

The USB pad coordinates and finished-hole sizes follow the manufacturer's
61400416121 drawing revision 001.003, 2024-01-30, rather than assuming the
downloaded CAD model's 2.3 mm shield holes are correct.
"""
import json
from pathlib import Path
import shutil
import sys
from sexpr import Atom as A, dump

ROOT=Path(__file__).resolve().parents[1]


def prepare(source):
    """Copy only referenced footprints and register project-local libraries."""
    parts=json.loads((ROOT/'connections.json').read_text())
    names=sorted({p['footprint'] for p in parts if p['footprint']})
    libs=set()
    for name in names:
        lib,fp=name.split(':');libs.add(lib)
        target=ROOT/'cad/footprints'/(lib+'.pretty')
        target.mkdir(parents=True,exist_ok=True)
        if lib=='WICI':continue
        original=source/(lib+'.pretty')/(fp+'.kicad_mod')
        if not original.exists():raise FileNotFoundError(original)
        shutil.copy2(original,target)
    body='''(footprint "USB_B_61400416121"
 (version 20241229) (generator "pcbnew") (layer "F.Cu")
 (descr "Own land pattern from Wuerth 61400416121 drawing 001.003, 2024-01-30. Finished holes: signal 0.92mm, shield 2.5mm. Review mechanical fit before fabrication.")
 (attr through_hole)
 (property "Reference" "REF**" (at 6.7 -8 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
 (property "Value" "USB_B_61400416121" (at 6.7 10 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
 (fp_rect (start -1.51 -4.77) (end 14.99 7.27) (stroke (width 0.1) (type solid)) (fill none) (layer "F.Fab"))
 (fp_rect (start -2.1 -6.9) (end 15.5 9.4) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))
 (fp_line (start -1.65 -4.9) (end 2.6 -4.9) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))
 (fp_line (start -1.65 7.4) (end 2.6 7.4) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))
 (fp_line (start -1.65 -4.9) (end -1.65 7.4) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))
 (pad "1" thru_hole rect (at 0 0) (size 1.5 1.5) (drill 0.92) (layers "*.Cu" "*.Mask"))
 (pad "2" thru_hole circle (at 0 2.5) (size 1.5 1.5) (drill 0.92) (layers "*.Cu" "*.Mask"))
 (pad "3" thru_hole circle (at 2 2.5) (size 1.5 1.5) (drill 0.92) (layers "*.Cu" "*.Mask"))
 (pad "4" thru_hole circle (at 2 0) (size 1.5 1.5) (drill 0.92) (layers "*.Cu" "*.Mask"))
 (pad "5" thru_hole circle (at 4.71 7.27) (size 3.6 3.6) (drill 2.5) (layers "*.Cu" "*.Mask"))
 (pad "5" thru_hole circle (at 4.71 -4.77) (size 3.6 3.6) (drill 2.5) (layers "*.Cu" "*.Mask"))
)'''
    (ROOT/'cad/footprints/WICI.pretty/USB_B_61400416121.kicad_mod').write_text(body+'\n')
    (ROOT/'cad/footprints/WICI.pretty/PPTC_1206_1.8x1.8_Gap1.0.kicad_mod').write_text("""(footprint "PPTC_1206_1.8x1.8_Gap1.0"
 (version 20241229) (generator "pcbnew") (layer "F.Cu")
 (descr "Common enlarged land pattern covering Bourns MF-NSMF and Littelfuse 1206L recommended pads. Pads 1.8x1.8mm, gap 1mm. Prototype verification required.")
 (attr smd)
 (property "Reference" "REF**" (at 0 -2 0) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
 (property "Value" "PPTC 0.5A" (at 0 2 0) (layer "F.Fab") (effects (font (size 0.8 0.8) (thickness 0.12))))
 (fp_rect (start -1.7 -0.9) (end 1.7 0.9) (stroke (width 0.1) (type solid)) (fill none) (layer "F.Fab"))
 (fp_rect (start -2.55 -1.15) (end 2.55 1.15) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))
 (pad "1" smd roundrect (at -1.4 0) (size 1.8 1.8) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.15))
 (pad "2" smd roundrect (at 1.4 0) (size 1.8 1.8) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.15))
)
""")
    # KiCad-derived IDC with the selected manufacturer's 1.1 mm finished holes.
    from sexpr import parse, children, child
    idc=parse((source/'Connector_IDC.pretty/IDC-Header_2x05_P2.54mm_Vertical.kicad_mod').read_text())
    idc[1]='IDC_61201021621'
    for pad in children(idc,'pad'):
        drill=child(pad,'drill')
        if drill:drill[1]=1.1
    (ROOT/'cad/footprints/WICI.pretty/IDC_61201021621.kicad_mod').write_text(dump(idc)+'\n')
    table=[A('fp_lib_table'),[A('version'),7]]
    for lib in sorted(libs):
        table.append([A('lib'),[A('name'),lib],[A('type'),'KiCad'],
            [A('uri'),'${KIPRJMOD}/footprints/'+lib+'.pretty'],[A('options'),''],[A('descr'),'Pinned project footprint subset']])
    (ROOT/'cad/fp-lib-table').write_text(dump(table)+'\n')
    print(f'{len(names)} unique footprints prepared')


if __name__=='__main__':prepare(Path(sys.argv[1]))
