# SPDX-License-Identifier: MIT
"""Apply the bounded controller power/mechanical revision to the preserved R01.

Input is checks/history/controller-power-input.kicad_pcb, not an arbitrary
router result. Output requires fresh ERC/DRC and physical connector-fit checks.
"""
import json,math,uuid
from pathlib import Path
import pcbnew as k
ROOT=Path(__file__).resolve().parents[1]
b=k.LoadBoard(str(ROOT/'checks/history/controller-power-input.kicad_pcb'))
fps={f.GetReference():f for f in b.GetFootprints()}
fps['C3'].SetPosition(k.VECTOR2I(k.FromMM(114.75),k.FromMM(94.2)))
fps['C5'].SetPosition(k.VECTOR2I(k.FromMM(109.25),k.FromMM(79.5)))
NS=uuid.UUID('467d264c-787d-4b39-8f3c-c13d337d015a')
def pt(x,y):return k.VECTOR2I(k.FromMM(x),k.FromMM(y))
def xy(p):return (k.ToMM(p.x),k.ToMM(p.y))
def pad(ref,p):return xy(fps[ref].FindPadByNumber(str(p)).GetPosition())
def track(net,points,width=.5,layer=k.F_Cu):
 for a,z in zip(points,points[1:]):
  t=k.PCB_TRACK(b);t.SetStart(pt(*a));t.SetEnd(pt(*z));t.SetWidth(k.FromMM(width));t.SetLayer(layer);t.SetNet(b.FindNet('/'+net));t.SetLocked(True);b.Add(t)
def via(net,pos):
 v=k.PCB_VIA(b);v.SetPosition(pt(*pos));v.SetWidth(k.FromMM(.6));v.SetDrill(k.FromMM(.3));v.SetViaType(k.VIATYPE_THROUGH);v.SetLayerPair(k.F_Cu,k.B_Cu);v.SetNet(b.FindNet('/'+net));v.SetLocked(True);b.Add(v)
 return str(v.m_Uuid.AsString())
newnet=k.NETINFO_ITEM(b,'/VBUS_USB');b.Add(newnet)
for ref,p in [('J1',1),('U3',5),('C14',1)]:fps[ref].FindPadByNumber(str(p)).SetNet(newnet)
removed=[]
for t in list(b.GetTracks()):
 if t.GetNetname() not in ('/USB_DP','/USB_DM','/USB_DP_MCU','/USB_DM_MCU'):
  b.Remove(t);removed.append(t)
# Add the fuse and four mechanical holes with matching schematic UUID paths.
parts=json.loads((ROOT/'connections.json').read_text())
places={'F1':(140,72,180),'H1':(84,64,0),'H2':(146,64,0),'H3':(84,111,0),'H4':(146,111,0)}
for p in parts:
 ref=p['ref']
 if ref not in places:continue
 lib,name=p['footprint'].split(':');f=k.FootprintLoad(str(ROOT/'cad/footprints'/(lib+'.pretty')),name)
 f.SetReference(ref);f.SetValue(p['value']);f.SetFPID(k.LIB_ID(lib,name))
 path=k.KIID_PATH();path.push_back(k.KIID(str(uuid.uuid5(NS,'root'))));path.push_back(k.KIID(str(uuid.uuid5(NS,ref))));f.SetPath(path)
 x,y,angle=places[ref];f.SetPosition(pt(x,y));f.SetOrientation(k.EDA_ANGLE(angle,k.DEGREES_T))
 for d in f.Pads():
  if d.GetNumber() in p['nets']:d.SetNet(b.FindNet('/'+p['nets'][d.GetNumber()]))
 f.Reference().SetTextSize(pt(.8-0,.8-0));f.Reference().SetTextThickness(k.FromMM(.12));f.Value().SetVisible(False)
 f.Reference().SetPosition(pt(x,y-2 if ref=='F1' else y-4 if y>100 else y+4))
 b.Add(f);fps[ref]=f
 if ref.startswith('H'):
  zone=k.ZONE(b);ls=k.LSET()
  for layer in (k.F_Cu,k.In1_Cu,k.In2_Cu,k.B_Cu):ls.AddLayer(layer)
  zone.SetDoNotAllowPads(False);zone.SetDoNotAllowFootprints(False);zone.SetLayerSet(ls);zone.SetIsRuleArea(True);zone.SetDoNotAllowTracks(True);zone.SetDoNotAllowVias(True);zone.SetDoNotAllowZoneFills(True)
  outline=zone.Outline();outline.NewOutline()
  for i in range(64):
   a=2*math.pi*i/64;outline.Append(pt(x+3.2*math.cos(a),y+3.2*math.sin(a)))
  b.Add(zone)
# Each supply capacitor has a separate ground via, and V3 capacitors also
# have their own plane via. No daisy-chain main supply routing remains.
taps={
 'C1':(None,(132.45,74)), 'C2':((123.35,74),(119.55,74)),
 'C3':((115.8,93.25),(114.75,96.15)), 'C4':((117.55,81),(119.45,83.1)),
 'C5':((108.25,80.45),(109.25,77.55)), 'C6':((105.45,82.75),(102.55,83.75)),
 'C7':((105.45,87.7),(102.55,88.75)), 'C8':((105.45,92.5),(102.55,91.5)),
 'C9':((118.05,92),(120.95,91)), 'C10':((98.05,82),(101.95,82)),
 'C11':((110.05,70),(113.95,70)), 'C12':(None,(104.95,99.1)),
 'C13':((101.5,95.95),(99.2,94.05)), 'C14':(None,(130.95,78)),
}
capvias={}
for ref,(v3,gnd) in taps.items():
 capvias[ref]={'ground':via('GND',gnd)};track('GND',[pad(ref,2),gnd])
 if v3:capvias[ref]['V3']=via('V3',v3);track('V3',[pad(ref,1),v3])
# LDO output connects directly to its local bulk capacitor and plane tap.
track('V3',[pad('U2',5),(123.5,74.95),pad('C2',1)])
via('V3',(123.8,75.6));track('V3',[pad('U2',5),(123.8,75.6)])
# Short fine-pitch escapes only; power branches beyond the escape are 0.5mm.
for p,escape,ref in [(1,(106.6,84.25),'C6'),(9,(105.95,88.25),'C7'),(24,(114.75,92.6),'C3'),(36,(117,84.25),'C4'),(48,(109.25,81.4),'C5')]:
 track('V3',[pad('U1',p),escape],.2)
 end=pad(ref,1)
 if p==36:
  track('V3',[escape,(117,83.2)],.2);track('V3',[(117,83.2),end])
 elif p==1:track('V3',[escape,(106.1,83.75),end])
 elif p==9:track('V3',[escape,(105.45,88.75),end])
 else:track('V3',[escape,end])
# Dedicated taps for the other supply loads and test point.
for ref,p,pos in [('U4',8,(115.5,72.095)),('Y1',1,(98.4,87.075)),('Y1',4,(98.4,85.425)),('Q1',2,(121.1,81.95)),('R4',1,(121.1,78)),('R5',1,(102.1,95)),('R8',1,(101.05,100.5)),('R10',1,(118,75.9125)),('R11',1,(118,71.9125)),('TP2',1,(122,70))]:
 via('V3',pos);track('V3',[pad(ref,p),pos])
# VBUS: host side remains the ESD reference; F1 feeds controller power.
# All bulk current paths are 0.5mm. The 0.5 A PPTC is not a USB current limiter.
track('VBUS_USB',[pad('J1',1),(132,84),(132,80),(141.4,70.6),(141.4,72)],layer=k.B_Cu)
via('VBUS_USB',(141.4,72))
track('VBUS_USB',[pad('U3',5),(130.2,86)])
via('VBUS_USB',(130.2,86))
track('VBUS_USB',[(130.2,86),(132,84)],layer=k.B_Cu)
via('VBUS_USB',(127.05,78));track('VBUS_USB',[pad('C14',1),(127.05,78)])
track('VBUS_USB',[(127.05,78),(127.05,80),(130,82.95),(132,84)],layer=k.B_Cu)
track('VBUS',[pad('F1',2),(136.6,71),(129.55,71),pad('C1',1)])
track('VBUS',[pad('C1',1),(128.3,74),(128.3,74.95),pad('U2',1)])
track('VBUS',[pad('U2',3),(128.3,73.05),(128.3,74)])
track('VBUS',[pad('F1',2),pad('TP1',1)])
# Keep MCU ground returns short, into the adjacent continuous ground plane.
for p,points in [(8,[pad('U1',8),(106.4,87.75),(106.4,86.75)]),
 (23,[pad('U1',23),(114.25,92.25),(112.8,92.25),(112.8,92.8)]),
 (35,[pad('U1',35),(117.15,84.75),(117.85,84.05)]),
 (47,[pad('U1',47),(109.75,81.75),(110.7,81.75),(110.7,81.15)])]:
 track('GND',points,.2);via('GND',points[-1])
for ref,p,pos in [('U2',2,(126.25,74)),('U3',2,(125.9,86)),('Y1',2,(102.5,87.075)),('U4',1,(108.55,72.095)),('U4',2,(108.55,73.365)),('U4',3,(108.55,74.635)),('U4',4,(108.55,75.905)),('U4',7,(115.5,73.365)),('TP3',1,(134,75))]:
 track('GND',[pad(ref,p),pos],.4);via('GND',pos)
# Radio power is a direct plane connection through the THT pin; no long
# narrow trace joins J2 to C13. Pin 2 and the cap tap meet the In2 plane.
# First attempt moves all In2 signals to bottom; DRC decides which paths
# need rerouting, without reducing clearances or hiding violations.
for t in b.GetTracks():
 if not isinstance(t,k.PCB_VIA) and t.GetLayer()==k.In2_Cu:t.SetLayer(k.B_Cu)
b.BuildConnectivity();k.SaveBoard(str(ROOT/'cad/radio-usb-controller.kicad_pcb'),b)
(ROOT/'checks/capacitor-plane-vias.json').write_text(json.dumps(capvias,indent=2)+'\n')
print('Power/fuse/mounting candidate written; DRC pending.')
