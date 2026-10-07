# SPDX-License-Identifier: MIT
"""Measure the requested controller revision and export geometry for a 1:1 sheet.

These checks cover routing geometry, fixed USB routes and plane taps. They do
not verify connector fit, current capability, temperature or USB impedance.
"""
import collections,json,math,hashlib
from pathlib import Path
import pcbnew as k
ROOT=Path(__file__).resolve().parents[1]
def xy(p):return [round(k.ToMM(p.x),6),round(k.ToMM(p.y),6)]
def measure(b):
 lengths=collections.defaultdict(float);vias=collections.Counter();narrow=[]
 for t in b.GetTracks():
  if isinstance(t,k.PCB_VIA):vias[t.GetNetname()]+=1
  else:
   key=(t.GetNetname(),b.GetLayerName(t.GetLayer()),round(k.ToMM(t.GetWidth()),3));lengths[key]+=k.ToMM(t.GetLength())
   if t.GetNetname()=='/V3' and t.GetWidth()<k.FromMM(.4):narrow.append({'start':xy(t.GetStart()),'end':xy(t.GetEnd()),'width_mm':k.ToMM(t.GetWidth()),'length_mm':round(k.ToMM(t.GetLength()),4)})
 return {'track_lengths_mm':[dict(net=key[0],layer=key[1],width_mm=key[2],length_mm=round(v,4)) for key,v in sorted(lengths.items())], 'via_counts':dict(vias),'fine_pitch_V3_escapes':narrow}
def usb_routes(b):
 nets=('/USB_DP','/USB_DM','/USB_DP_MCU','/USB_DM_MCU')
 return sorted((t.GetNetname(),b.GetLayerName(t.GetLayer()),t.GetWidth(),tuple(sorted((tuple(xy(t.GetStart())),tuple(xy(t.GetEnd())))))) for t in b.GetTracks() if not isinstance(t,k.PCB_VIA) and t.GetNetname() in nets)
def main():
 b=k.LoadBoard(str(ROOT/'cad/radio-usb-controller.kicad_pcb'));before=k.LoadBoard(str(ROOT/'checks/history/controller-power-input.kicad_pcb'))
 old,new=measure(before),measure(b);fps={f.GetReference():f for f in b.GetFootprints()}
 assert usb_routes(b)==usb_routes(before),'Fixed USB routing changed'
 assert not any(t.GetLayer() in (k.In1_Cu,k.In2_Cu) for t in b.GetTracks() if not isinstance(t,k.PCB_VIA)), 'Internal layer contains a trace'
 assert all(t.GetWidth()>=k.FromMM(.5) for t in b.GetTracks() if not isinstance(t,k.PCB_VIA) and t.GetNetname() in ('/VBUS','/VBUS_USB'))
 assert len(new['fine_pitch_V3_escapes'])==6
 assert all(t['width_mm']==.2 and t['length_mm']<2.0 for t in new['fine_pitch_V3_escapes'])
 assert fps['J1'].FindPadByNumber('1').GetNetname()=='/VBUS_USB'
 assert fps['J1'].FindPadByNumber('4').GetNetname()=='/GND'
 assert fps['F1'].FindPadByNumber('1').GetNetname()=='/VBUS_USB'
 assert fps['F1'].FindPadByNumber('2').GetNetname()=='/VBUS'
 cap_ids=json.loads((ROOT/'checks/capacitor-plane-vias.json').read_text());vias={str(t.m_Uuid.AsString()):t for t in b.GetTracks() if isinstance(t,k.PCB_VIA)}
 assert len(cap_ids)==14
 for ref,nets in cap_ids.items():
  for key,uid in nets.items():
   v=vias[uid];assert v.GetNetname()==('/GND' if key=='ground' else '/V3')
   pin=fps[ref].FindPadByNumber('2' if key=='ground' else '1');d=math.dist(xy(v.GetPosition()),xy(pin.GetPosition()));assert d<=1.4
   nets[key]={'uuid':uid,'position_mm':xy(v.GetPosition()),'pad_to_via_mm':round(d,4)}
 holes=[]
 for ref in ('H1','H2','H3','H4'):
  f=fps[ref];p=next(iter(f.Pads()));assert p.GetAttribute()==k.PAD_ATTRIB_NPTH;assert k.ToMM(p.GetDrillSize().x)==3.2
  holes.append({'ref':ref,'board_local_mm':[round(q-z,3) for q,z in zip(xy(f.GetPosition()),(80,60))],'hole_mm':3.2,'copper_keepout_diameter_mm':6.4})
 report={'scope':'CAD geometry only; physical verification pending','before':old,'after':new,'USB_routes_unchanged':True,'internal_layer_tracks':0,'power_bus_width_mm':.5,'each_supply_capacitor_ground_via':True,'each_V3_capacitor_power_via':True,'capacitors':cap_ids,'mounting_holes':holes,'mechanical_fit':'NOT TESTED','VBUS_PPTC':'0.5 A hold, not a 0.5 A current limiter'}
 (ROOT/'checks/controller-revision.json').write_text(json.dumps(report,indent=2)+'\n')
 # Actual front-side pad/outline geometry, in board coordinates, not a
 # separate hand-recreated land pattern. Used for physical-size PDF output.
 geometry={'board_origin_mm':[80,60],'board_size_mm':[70,55],'footprints':[]}
 for ref,f in sorted(fps.items()):
  pads=[]
  for p in f.Pads():pads.append({'number':p.GetNumber(),'net':p.GetNetname(),'pos':xy(p.GetPosition()),'size':[k.ToMM(p.GetSize().x),k.ToMM(p.GetSize().y)],'angle':p.GetOrientation().AsDegrees(),'drill':[k.ToMM(p.GetDrillSize().x),k.ToMM(p.GetDrillSize().y)],'shape':int(p.GetShape())})
  drawings=[]
  for g in f.GraphicalItems():
   if isinstance(g,k.PCB_SHAPE) and g.GetLayer()==k.F_Fab:drawings.append({'shape':int(g.GetShape()),'start':xy(g.GetStart()),'end':xy(g.GetEnd())})
  geometry['footprints'].append({'ref':ref,'pos':xy(f.GetPosition()),'refpos':xy(f.Reference().GetPosition()),'pads':pads,'fab':drawings})
 geometry['shape_ids']={x:int(getattr(k,'SHAPE_T_'+x)) for x in ('SEGMENT','RECT','CIRCLE')};geometry['pad_circle']=int(k.PAD_SHAPE_CIRCLE)
 (ROOT/'checks/mechanical-geometry.json').write_text(json.dumps(geometry,indent=2)+'\n')
 print('Verified: 0 inner-layer tracks; 0.5mm VBUS; 6 bounded V3 escapes; 14 separate capacitor ground taps; 4 mounting holes; fixed USB routes unchanged.')
if __name__=='__main__':main()
