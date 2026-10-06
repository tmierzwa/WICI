# SPDX-License-Identifier: GPL-3.0-or-later
"""Finish the preserved outer-layer routing session, then require fresh DRC.

The router necked three HSE tracks below the fabrication rule and left two
SMD ground pads without plane taps. This applies those local corrections and widens power rounding stubs.
"""
from pathlib import Path
import pcbnew as k
ROOT=Path(__file__).resolve().parents[1];p=ROOT/'cad/radio-usb-controller.kicad_pcb';b=k.LoadBoard(str(p));fps={f.GetReference():f for f in b.GetFootprints()}
def pt(x,y):return k.VECTOR2I(k.FromMM(x),k.FromMM(y))
for t in b.GetTracks():
 if not isinstance(t,k.PCB_VIA) and t.GetWidth()<k.FromMM(.18):t.SetWidth(k.FromMM(.2))
for t in b.GetTracks():
 if not isinstance(t,k.PCB_VIA) and (t.GetNetname() in ('/VBUS','/VBUS_USB') or t.GetNetname()=='/V3' and not t.IsLocked()):t.SetWidth(k.FromMM(.5))
for ref,pos in [('R9',(102.95,103)),('D1',(136.0625,102))]:
 d=fps[ref].FindPadByNumber('2' if ref=='R9' else '1');assert d.GetNetname()=='/GND'
 v=k.PCB_VIA(b);v.SetPosition(pt(*pos));v.SetWidth(k.FromMM(.6));v.SetDrill(k.FromMM(.3));v.SetViaType(k.VIATYPE_THROUGH);v.SetLayerPair(k.F_Cu,k.B_Cu);v.SetNet(d.GetNet());b.Add(v)
 t=k.PCB_TRACK(b);t.SetStart(d.GetPosition());t.SetEnd(pt(*pos));t.SetWidth(k.FromMM(.4));t.SetLayer(k.F_Cu);t.SetNet(d.GetNet());b.Add(t)
b.BuildConnectivity();k.SaveBoard(str(p),b)
print('Outer-layer routing finalized; fresh DRC required.')
