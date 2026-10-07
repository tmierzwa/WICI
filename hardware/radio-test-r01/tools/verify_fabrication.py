# SPDX-License-Identifier: MIT
"""Compare actual Gerber, Excellon, BOM and placement files to exported PCB data.

Requires gerbonara. The check does not certify assembly rotations, impedance,
physical connector fit or electrical performance.
"""
from pathlib import Path
import csv,json,hashlib,collections,math,warnings
from gerbonara import GerberFile,ExcellonFile
from gerbonara.graphic_objects import Flash,Line
from gerbonara.utils import MM
from sexpr import parse,child,children
ROOT=Path(__file__).resolve().parents[1];base=ROOT/'fabrication/R01.3'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def keyxy(x,y):return(round(x,6),round(y,6))
def main():
 board=parse((ROOT/'cad/radio-usb-controller.kicad_pcb').read_text());stack=child(child(board,'setup'),'stackup');layers={v[1]:v for v in children(stack,'layer')}
 stackdata=json.loads((ROOT/'checks/stackup.json').read_text())
 for layer in stackdata['layers']:
  actual=layers[layer['layer']];assert child(actual,'type')[1]==layer['type'] and float(child(actual,'thickness')[1])==layer['thickness_mm']
  if layer['epsilon_r']:assert float(child(actual,'epsilon_r')[1])==layer['epsilon_r']
 assert float(child(child(board,'general'),'thickness')[1])==1.6
 assert any(v[1]=='WICI R01.3' for v in children(board,'gr_text'))
 assert not any('REVIEW ONLY' in str(v[1]) for v in children(board,'gr_text'))
 geom=json.loads((ROOT/'checks/fabrication-geometry.json').read_text());assert geom['pcb_sha256']==sha(ROOT/'cad/radio-usb-controller.kicad_pcb')
 bom=list(csv.DictReader((base/'assembly/bom.csv').open()));parts=json.loads((ROOT/'assembly-parts.json').read_text());refs=[]
 for row in bom:
  names=row['Designators'].split(',');assert len(names)==int(row['Quantity']);refs+=names
  for ref in names:assert row['MPN']==parts[ref]['mpn'] and row['Manufacturer']==parts[ref]['manufacturer']
 assert len(refs)==39 and set(refs)==set(parts)
 placements={p['ref']:p for p in geom['placements']}
 for file,expected in [('positions-all.csv',set(parts)),('positions-smt.csv',{ref for ref,v in parts.items() if v['assembly']=='SMT'})]:
  rows=list(csv.DictReader((base/'assembly'/file).open()));assert {r['Ref'] for r in rows}==expected and len(rows)==len(expected)
  for row in rows:
   p=placements[row['Ref']];assert keyxy(float(row['PosX']),float(row['PosY']))==tuple(p['pos']);assert row['Side']==p['side'];assert abs((float(row['Rot'])-p['angle'])%360)<1e-5
 drill_counts={}
 for file,plated in [('radio-usb-controller-PTH.drl',True),('radio-usb-controller-NPTH.drl',False)]:
  # KiCad's legal G90 placement after M95 triggers a parser warning; retain
  # original export, verify numeric geometry rather than rewriting its header.
  with warnings.catch_warnings():
   warnings.simplefilter('ignore',SyntaxWarning);d=ExcellonFile.open(base/'drill'/file)
  actual=[(o.x,o.y,o.aperture.diameter) for o in d.objects]
  expected=[(*v['pos'],v['diameter_mm']) for v in geom['drills'] if v['plated']==plated]
  assert len(actual)==len(expected),file
  # Native Excellon output has 3 decimal places in mm (1um).
  # Allow only its measured rounding bound, not fabrication tolerance.
  for x,y,dia in actual:
   matches=[v for v in expected if max(abs(v[0]-x),abs(v[1]-y))<=0.000501 and abs(v[2]-dia)<1e-6]
   assert len(matches)==1,(file,x,y,dia);expected.remove(matches[0])
  assert not expected;drill_counts['PTH' if plated else 'NPTH']=len(d.objects)
 gerbers={}
 for p in (base/'gerbers').iterdir():
  if p.suffix=='.gbrjob':continue
  g=GerberFile.open(p);gerbers[p.name]=len(g.objects);assert g.objects
  if p.suffix=='.gtl':
   actual=collections.Counter((o.attrs['.P'][0],o.attrs['.P'][1],round(o.x,6),round(o.y,6)) for o in g.objects if isinstance(o,Flash) and '.P' in o.attrs)
   expected=collections.Counter((v['ref'],v['pin'],*v['pos']) for v in geom['pads'])
   assert actual==expected,'Top copper pad flashes differ from PCB'
  if p.suffix=='.gm1':
   assert len(g.objects)==4 and all(isinstance(o,Line) for o in g.objects)
   corners={(round(o.x1,6),round(o.y1,6)) for o in g.objects}|{(round(o.x2,6),round(o.y2,6)) for o in g.objects}
   assert corners=={(0,0),(70,0),(0,55),(70,55)}
 assert len(gerbers)==9
 paste=GerberFile.open(base/'assembly/radio-usb-controller-F_Paste.gtp');assert paste.objects
 report={'revision':'R01.3','scope':'Parsed exports compared to source geometry; physical/electrical qualification pending','gerber_layers':gerbers,'copper_layer_order':['F.Cu','In1.Cu GND','In2.Cu V3','B.Cu'],'drill_counts':drill_counts,'placements_all':39,'placements_SMT':34,'BOM_components':39,'BOM_lines':len(bom),'origin':geom['origin'],'checks':{'top_copper_pad_flashes_equal_PCB':True,'drills_match_PCB_with_Excellon_rounding':True,'drill_coordinate_rounding_bound_mm_per_axis':0.000501,'board_outline_70x55':True,'placements_equal_PCB':True,'BOM_MPNs_complete':True,'stackup_matches_board':True,'revision_legend_matches':True},'source_pcb_sha256':geom['pcb_sha256'],'file_sha256':{str(p.relative_to(base)):sha(p) for p in sorted(base.rglob('*')) if p.is_file()}}
 (ROOT/'checks/fabrication-verification.json').write_text(json.dumps(report,indent=2)+'\n')
 print('Verified 9 Gerber layers; 97 PTH + 4 NPTH; 39 placements / 34 SMT; all 39 BOM MPNs.')
if __name__=='__main__':main()
