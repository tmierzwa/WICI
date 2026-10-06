# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply explicit routing corrections, then require a fresh KiCad DRC.

The local autorouter produced narrow necks. This widens them and adjusts two
connected vertex groups without reducing any clearance rule. It also moves
the reset switch and adds copper extensions to its previous connection points.
"""
from pathlib import Path
import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'cad/radio-usb-controller.kicad_pcb'
b = k.LoadBoard(str(path))


def point(x, y):
    return k.VECTOR2I(k.FromMM(x), k.FromMM(y))


def power_region(p):
    return 114.3 < k.ToMM(p.x) < 115.95 and 89.8 < k.ToMM(p.y) < 91.4


removed = []  # keep SWIG wrappers alive until the board has been saved
for t in list(b.GetTracks()):
    name = t.GetNetname()
    if name == '/V3' and power_region(t.GetStart()):
        b.Remove(t); removed.append(t)
        continue
    if name == '/V3' and not isinstance(t, k.PCB_VIA) and power_region(t.GetEnd()):
        b.Remove(t); removed.append(t)
        continue
    if name == '/UART_TX' and not isinstance(t, k.PCB_VIA) and t.GetLayer() == k.F_Cu:
        b.Remove(t); removed.append(t)
        continue
    if not isinstance(t, k.PCB_VIA) and t.GetWidth() < k.FromMM(.18):
        t.SetWidth(k.FromMM(.2))


def via(name, x, y):
    v = k.PCB_VIA(b)
    v.SetPosition(point(x, y)); v.SetWidth(k.FromMM(.6))
    v.SetDrill(k.FromMM(.3)); v.SetViaType(k.VIATYPE_THROUGH)
    v.SetLayerPair(k.F_Cu, k.B_Cu); v.SetNet(b.FindNet(name)); b.Add(v)


def track(name, points, width=.2):
    for a, z in zip(points, points[1:]):
        t = k.PCB_TRACK(b); t.SetStart(point(*a)); t.SetEnd(point(*z))
        t.SetWidth(k.FromMM(width)); t.SetLayer(k.F_Cu); t.SetNet(b.FindNet(name)); b.Add(t)


# Supply pin 24 goes outwards to its decoupler rather than around the adjacent
# ground pad. The bulk capacitor connects to that same supply branch.
track('/V3', [(114.75, 91.1625), (114.75, 93.05), (115.8, 93.05)], .25)
via('/V3', 115.8, 93.05)
track('/V3', [(118.05, 91), (115.8315, 91), (115.669, 91.1625), (114.75, 91.1625)])
track('/UART_TX', [(116.1625, 87.25), (117.25, 87.25), (117.95, 87.95),
                   (118.415, 87.95), (118.6675, 88.2028)])

for f in b.GetFootprints():
    if f.GetReference() == 'SW1':
        old = [(p.GetPosition(), p.GetNet()) for p in f.Pads()]
        refpos = f.Reference().GetPosition()
        p = f.GetPosition()
        assert k.ToMM(p.x) == 110 and k.ToMM(p.y) == 105, 'Already finalized or different placement'
        f.SetPosition(k.VECTOR2I(p.x - k.FromMM(2), p.y))
        f.Reference().SetPosition(refpos)
        for (before, net), pad in zip(old, f.Pads()):
            if net.GetNetname() == '/GND':
                continue  # new through-hole ground pads directly meet the plane
            via(net.GetNetname(), k.ToMM(before.x), k.ToMM(before.y))
            t = k.PCB_TRACK(b)
            t.SetStart(before); t.SetEnd(pad.GetPosition())
            t.SetWidth(k.FromMM(.25)); t.SetLayer(k.F_Cu); t.SetNet(net)
            b.Add(t)
for d in b.GetDrawings():
    if isinstance(d, k.PCB_TEXT) and d.GetText() == 'WICI R01 / REVIEW ONLY':
        d.SetPosition(k.VECTOR2I(k.FromMM(115), k.FromMM(113)))
# Move the routed signal bundle away from the ground plane below USB.
# The previous back-side reset links move to the inner layer; their positions
# are outside the USB corridor. Every via remains a through via.
for t in b.GetTracks():
    if isinstance(t, k.PCB_VIA):
        continue
    if t.GetLayer() == k.In1_Cu:
        t.SetLayer(k.B_Cu)
    elif t.GetLayer() == k.B_Cu:
        t.SetLayer(k.In1_Cu)
b.BuildConnectivity()
k.SaveBoard(str(path), b)
print('Routing corrections applied. Run DRC with zone refill and schematic parity.')
