# SPDX-License-Identifier: GPL-3.0-or-later
"""Export PCB geometry for independent parsing checks of fabrication outputs."""
from pathlib import Path
import json,hashlib
import pcbnew as k
ROOT=Path(__file__).resolve().parents[1];p=ROOT/'cad/radio-usb-controller.kicad_pcb';b=k.LoadBoard(str(p));parts=json.loads((ROOT/'assembly-parts.json').read_text())
def xy(v):return [round(k.ToMM(v.x)-80,6),round(115-k.ToMM(v.y),6)]
pads=[];pos=[];drill=[]
for f in b.GetFootprints():
 ref=f.GetReference()
 if ref in parts:
  assert f.GetFieldText('MPN')==parts[ref]['mpn'] and f.GetFieldText('Manufacturer')==parts[ref]['manufacturer']
  pos.append(dict(ref=ref,pos=xy(f.GetPosition()),angle=f.GetOrientationDegrees(),side='top'))
 for d in f.Pads():
  x=dict(ref=ref,pin=d.GetNumber(),pos=xy(d.GetPosition()),net=d.GetNetname());
  if d.GetAttribute()!=k.PAD_ATTRIB_NPTH:pads.append(x)
  if d.GetDrillSize().x:drill.append(dict(pos=x['pos'],diameter_mm=k.ToMM(d.GetDrillSize().x),plated=d.GetAttribute()!=k.PAD_ATTRIB_NPTH,ref=ref))
for t in b.GetTracks():
 if isinstance(t,k.PCB_VIA):drill.append(dict(pos=xy(t.GetPosition()),diameter_mm=k.ToMM(t.GetDrillValue()),plated=True,ref='via'))
assert len(pos)==39
result={'pcb_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'origin':'PCB lower left, +X right, +Y up, mm; no mirroring','pads':pads,'placements':pos,'drills':drill}
(ROOT/'checks/fabrication-geometry.json').write_text(json.dumps(result,indent=2)+'\n')
print('Exported 39 placements and',len(drill),'drills for output verification.')
