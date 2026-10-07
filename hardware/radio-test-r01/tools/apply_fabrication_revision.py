# SPDX-License-Identifier: MIT
"""Apply R01.3 stackup, legend and assembly metadata to the routed controller.

Copper routing remains unchanged. J2 finished holes become 1.1 mm per its
selected manufacturer's drawing. Physical fit and production approval remain
separate from these CAD changes.
"""
from pathlib import Path
import json
import pcbnew as k
from sexpr import Atom as A,parse,dump,child,children
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'cad/radio-usb-controller.kicad_pcb';b=k.LoadBoard(str(p));parts=json.loads((ROOT/'assembly-parts.json').read_text())
for f in b.GetFootprints():
 ref=f.GetReference()
 if ref in parts:
  f.GetField(k.FIELD_T_DATASHEET).SetText(parts[ref]['datasheet'])
  for name,key in [('Manufacturer','manufacturer'),('MPN','mpn')]:
   f.SetField(name,parts[ref][key]);field=f.GetField(name);field.SetVisible(False);field.SetLayer(k.F_Fab);field.SetPosition(f.GetPosition())
 else:f.SetAttributes(f.GetAttributes()|k.FP_EXCLUDE_FROM_POS_FILES|k.FP_EXCLUDE_FROM_BOM)
 if ref=='J2':
  f.SetFPID(k.LIB_ID('WICI','IDC_61201021621'))
  for d in f.Pads():d.SetDrillSize(k.VECTOR2I(k.FromMM(1.1),k.FromMM(1.1)))
for d in b.GetDrawings():
 if isinstance(d,k.PCB_TEXT) and d.GetText() in ('WICI R01 / REVIEW ONLY','WICI R01.3'):d.SetText('WICI R01.3')
b.GetTitleBlock().SetTitle('WICI R01.3 USB controller');b.GetTitleBlock().SetRevision('R01.3');b.GetDesignSettings().SetAuxOrigin(k.VECTOR2I(k.FromMM(80),k.FromMM(115)))
k.SaveBoard(str(p),b)
# Exact standard JLC04161H-7628 laminate dimensions; 1.6 mm is nominal.
board=parse(p.read_text());setup=child(board,'setup');setup[:]=[x for x in setup if not(isinstance(x,list) and x and x[0]=='stackup')]
stack=[A('stackup')]
for name,kind in [('F.SilkS','Top Silk Screen'),('F.Paste','Top Solder Paste'),('F.Mask','Top Solder Mask')]:
 stack.append([A('layer'),name,[A('type'),kind],*([[A('thickness'),.01524],[A('epsilon_r'),3.8],[A('color'),'Green']] if name=='F.Mask' else [])])
rows=[('F.Cu','copper',.035,'Copper',None),('dielectric 1','prepreg',.2104,'FR4 7628',4.4),('In1.Cu','copper',.0152,'Copper',None),('dielectric 2','core',1.065,'FR4',4.6),('In2.Cu','copper',.0152,'Copper',None),('dielectric 3','prepreg',.2104,'FR4 7628',4.4),('B.Cu','copper',.035,'Copper',None)]
for name,kind,t,material,er in rows:
 layer=[A('layer'),name,[A('type'),kind],[A('thickness'),t]]
 if er:layer.extend([[A('material'),material],[A('epsilon_r'),er]])
 stack.append(layer)
for name,kind in [('B.Mask','Bottom Solder Mask'),('B.Paste','Bottom Solder Paste'),('B.SilkS','Bottom Silk Screen')]:
 stack.append([A('layer'),name,[A('type'),kind],*([[A('thickness'),.01524],[A('epsilon_r'),3.8],[A('color'),'Green']] if name=='B.Mask' else [])])
stack.extend([[A('copper_finish'),'Lead-free HASL'],[A('dielectric_constraints'),A('yes')]])
setup.insert(1,stack);child(child(board,'general'),'thickness')[1]=1.6
p.write_text(dump(board)+'\n')
stackdata={'revision':'R01.3','reference_fab':'JLCPCB','reference_stack':'JLC04161H-7628','source':'https://jlcpcb.com/impedance','nominal_finished_thickness_mm':1.6,'laminate_without_mask_mm':round(sum(row[2] for row in rows),6),'mask_model_thickness_mm':.01524,'mask_model_epsilon_r':3.8,'loss_tangent':'KiCad serializes default 0.02; not a qualified material loss tangent','layers':[dict(layer=name,type=kind,thickness_mm=t,material=mat,epsilon_r=er) for name,kind,t,mat,er in rows],'note':'Manufacturer nominal 1.6mm stack; coating model is nonuniform in the real board. No controlled-impedance qualification. Another fab must confirm equivalent construction, not substitute an unspecified stack.'}
(ROOT/'checks/stackup.json').write_text(json.dumps(stackdata,indent=2)+'\n')
print('Applied R01.3 legend, standard 1.6mm stack, 39 MPNs, J2 1.1mm holes and lower-left output origin.')
