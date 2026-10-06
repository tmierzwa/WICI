# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare a separately regenerated WICI controller with its candidate CAD.

UUIDs and zone-fill cache are excluded. No physical performance is certified.
"""
from pathlib import Path
import json,hashlib
import pcbnew as k
import argparse
parser=argparse.ArgumentParser();parser.add_argument('replay',type=Path);args=parser.parse_args()
a=Path(__file__).resolve().parents[1];r=args.replay
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def geometry(p):
 b=k.LoadBoard(str(p)); tracks=[];vias=[];pads=[];fps=[];zones=[]
 for t in b.GetTracks():
  if isinstance(t,k.PCB_VIA):vias.append((t.GetNetname(),t.GetPosition().x,t.GetPosition().y,t.GetWidth(k.F_Cu),t.GetDrillValue(),t.TopLayer(),t.BottomLayer()))
  else:
   ends=sorted([(t.GetStart().x,t.GetStart().y),(t.GetEnd().x,t.GetEnd().y)])
   tracks.append((t.GetNetname(),t.GetLayer(),t.GetWidth(),tuple(ends)))
 for f in b.GetFootprints():
  fps.append((f.GetReference(),str(f.GetFPID().GetLibNickname())+":"+str(f.GetFPID().GetLibItemName()),f.GetPosition().x,f.GetPosition().y,f.GetOrientationDegrees()))
  for d in f.Pads():pads.append((f.GetReference(),d.GetNumber(),d.GetNetname(),d.GetPosition().x,d.GetPosition().y,d.GetSize().x,d.GetSize().y,d.GetDrillSize().x,d.GetDrillSize().y,d.GetShape(),d.GetOrientationDegrees()))
 for z in b.Zones():
  points=[]
  for n in range(z.Outline().OutlineCount()):
   poly=z.Outline().Outline(n);points.append(tuple((poly.CPoint(i).x,poly.CPoint(i).y) for i in range(poly.PointCount())))
  zones.append((z.GetNetname(),tuple(z.GetLayerSet().Seq()),z.GetIsRuleArea(),tuple(points)))
 return {n:sorted(x) for n,x in [('tracks',tracks),('vias',vias),('pads',pads),('footprints',fps),('zone_outlines',zones)]}
x=geometry(a/'cad/radio-usb-controller.kicad_pcb');y=geometry(r/'cad/radio-usb-controller.kicad_pcb')
assert x==y, [n for n in x if x[n]!=y[n]]
for name in ['cad/radio-usb-controller.kicad_sch','connections.json','connections.csv','bom.csv']:
 assert sha(a/name)==sha(r/name),name
checks={}
for name in ['erc','drc']:
 for tree in [a,r]:
  data=json.loads((tree/f'checks/{name}-controller.json').read_text())
  count=sum(len(s['violations']) for s in data['sheets']) if name=='erc' else len(data['violations'])+len(data['unconnected_items'])+len(data['schematic_parity'])
  assert count==0
 checks[name]=0
result={'scope':'Replay with preserved SES; no independent circuit review or physical test. UUIDs and zone-fill cache excluded from geometric comparison.','steps':['make_schematic.py','improve_controller_power.py','import_routing.py checks/controller-power.ses','finalize_power_routing.py','apply_fabrication_revision.py','ERC and DRC with zone refill'], 'schematic_BOM_connections_identical':True,'geometry_identical':True,'compared_geometry_counts':{n:len(v) for n,v in x.items()},'checks':checks,'candidate_pcb_sha256':sha(a/'cad/radio-usb-controller.kicad_pcb'),'candidate_schematic_sha256':sha(a/'cad/radio-usb-controller.kicad_sch'),'replay_erc_report':json.loads((r/'checks/erc-controller.json').read_text()),'replay_drc_report':json.loads((r/'checks/drc-controller.json').read_text())}
(a/'checks/replay-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print('Replay geometry, schematic, BOM and connections identical; ERC/DRC 0.')
