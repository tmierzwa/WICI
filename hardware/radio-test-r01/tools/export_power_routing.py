# SPDX-License-Identifier: GPL-3.0-or-later
"""Export a routing job with both internal planes inactive.

Autoroute settings must precede plane/keepout scopes in Freerouting 2.5.0.
The final KiCad DRC, not the router status, determines CAD acceptance.
"""
from pathlib import Path
import sys,pcbnew as k
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'tools'))
from sexpr import parse,dump,children,child,Atom as A
b=k.LoadBoard(str(root/'cad/radio-usb-controller.kicad_pcb'))
assert k.ExportSpecctraDSN(b,str(root/'checks/controller-power.dsn'))
p=root/'checks/controller-power.dsn';d=parse(p.read_text().replace('(string_quote ")','(string_quote "QUOTE")'));st=child(d,'structure')
# Only outer layers
# may carry newly routed signals; existing locked USB and power are fixed.
first_plane=next(i for i,x in enumerate(st) if isinstance(x,list) and x[0]=='plane')
st.insert(first_plane,[A('autoroute_settings'),[A('fanout'),A('off')],[A('autoroute'),A('on')],[A('postroute'),A('on')],
 [A('layer_rule'),A('F.Cu'),[A('active'),A('on')],[A('preferred_direction'),A('horizontal')]],
 [A('layer_rule'),A('In1.Cu'),[A('active'),A('off')]],
 [A('layer_rule'),A('In2.Cu'),[A('active'),A('off')]],
 [A('layer_rule'),A('B.Cu'),[A('active'),A('on')],[A('preferred_direction'),A('vertical')]]])
# The default KiCad DSN permits 0.05mm pad-to-pad spacing; pin geometry is
# fixed, but routing must respect the project's 0.2mm clearance everywhere.
rule=child(st,'rule');rule[:]=[x for x in rule if not (isinstance(x,list) and x[0]=='clearance' and len(x)>2)]
p.write_text(dump(d).replace('(string_quote "QUOTE")','(string_quote ")')+'\n')
print('Exported locked-power/USB routing job; internal layers inactive.')
