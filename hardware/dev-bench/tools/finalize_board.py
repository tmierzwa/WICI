# SPDX-License-Identifier: MIT
"""Import the kept Freerouting session and add the ground pours.

usage (KiCad Python, from tools/): finalize_board.py ../checks/routing.ses
Run once on a freshly placed board from make_board.py. The session belongs to
that exact placement; a placement change needs a new routing run.
"""
from pathlib import Path
import sys

import pcbnew as k

from design import BOARD_W, BOARD_H, NOTCH_P5, SLOT_P20, SOLID_GND_PADS

ROOT = Path(__file__).resolve().parents[1]
OX, OY = 30.0, 30.0


def stitch(b, gnd, step=4.0, via=.8, drill=.4, gap=.35):
    """Ground vias on a grid wherever they keep clearance to all copper,
    holes and edges, so the two pours do not split into islands."""
    def seg_dist(p, a, z):
        ax, ay, zx, zy, px, py = a.x, a.y, z.x, z.y, p[0], p[1]
        dx, dy = zx - ax, zy - ay
        L = dx * dx + dy * dy
        t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
        return ((ax + t * dx - px) ** 2 + (ay + t * dy - py) ** 2) ** .5
    r = k.FromMM(via / 2 + gap)
    tracks = [(t.GetStart(), t.GetEnd(), t.GetWidth() / 2) for t in b.GetTracks()]
    blocks = []
    for f in b.GetFootprints():
        for pd in f.Pads():
            q = pd.GetBoundingBox()
            blocks.append((q.GetLeft(), q.GetTop(), q.GetRight(), q.GetBottom()))
        if not f.GetReference().startswith(('J', 'H')):
            q = f.GetCourtyard(k.F_CrtYd).BBox() if f.GetCourtyard(k.F_CrtYd).OutlineCount() else f.GetBoundingBox(False)
            blocks.append((q.GetLeft(), q.GetTop(), q.GetRight(), q.GetBottom()))
    for x0, y0, x1, y1 in (NOTCH_P5, SLOT_P20):
        blocks.append((k.FromMM(OX + x0 - 1), k.FromMM(OY + y0 - 1), k.FromMM(OX + x1 + 1), k.FromMM(OY + y1 + 1)))
    n = 0
    y = 2.0
    while y < BOARD_H - 1.9:
        x = 2.0
        while x < BOARD_W - 1.9:
            p = (k.FromMM(OX + x), k.FromMM(OY + y))
            ok = all(seg_dist(p, a, z) > w + r for a, z, w in tracks)
            ok = ok and not any(l - r < p[0] < rr + r and t - r < p[1] < bb + r for l, t, rr, bb in blocks)
            if ok:
                v = k.PCB_VIA(b)
                v.SetPosition(k.VECTOR2I(*p))
                v.SetWidth(k.FromMM(via))
                v.SetDrill(k.FromMM(drill))
                v.SetViaType(k.VIATYPE_THROUGH)
                v.SetLayerPair(k.F_Cu, k.B_Cu)
                v.SetNet(gnd)
                b.Add(v)
                n += 1
            x += step
        y += step
    print(n, 'stitching vias')


def main(ses):
    path = ROOT / 'cad/plytka-nosna.kicad_pcb'
    b = k.LoadBoard(str(path))
    if any(True for _ in b.GetTracks()):
        raise RuntimeError('board already routed; rebuild with make_board.py first')
    if not k.ImportSpecctraSES(b, ses):
        raise RuntimeError('Specctra session import failed')
    # Drop router vias that carry copper on one layer only.
    tracks = [t for t in b.GetTracks() if not isinstance(t, k.PCB_VIA)]
    pads = list(b.GetPads())
    removed = []
    for v in [t for t in b.GetTracks() if isinstance(t, k.PCB_VIA)]:
        p = v.GetPosition()
        layers = {t.GetLayer() for t in tracks if t.GetNetCode() == v.GetNetCode()
                  and (t.GetStart() == p or t.GetEnd() == p)}
        layers |= {k.F_Cu, k.B_Cu} if any(pd.GetNetCode() == v.GetNetCode() and pd.HitTest(p) for pd in pads) else set()
        if len(layers) < 2 and v.GetNetname() != '/GND':
            b.Remove(v)
            removed.append(v)
    gnd = b.FindNet('/GND')
    for layer in (k.F_Cu, k.B_Cu):
        z = k.ZONE(b)
        z.SetLayer(layer)
        z.SetNet(gnd)
        z.SetLocalClearance(k.FromMM(.3))
        z.SetMinThickness(k.FromMM(.25))
        z.SetPadConnection(k.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(k.FromMM(.4))
        z.SetThermalReliefSpokeWidth(k.FromMM(.5))
        z.SetIslandRemovalMode(k.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetAssignedPriority(0)
        o = z.Outline()
        o.NewOutline()
        for x, y in [(0, 0), (BOARD_W, 0), (BOARD_W, BOARD_H), (0, BOARD_H)]:
            o.Append(k.VECTOR2I(k.FromMM(OX + x), k.FromMM(OY + y)))
        b.Add(z)
    # Pads whose thermal spokes would end on a cut-off island get solid copper.
    for ref, num in SOLID_GND_PADS:
        b.FindFootprintByReference(ref).FindPadByNumber(num).SetLocalZoneConnection(k.ZONE_CONNECTION_FULL)
    k.ZONE_FILLER(b).Fill(b.Zones())
    b.BuildConnectivity()
    k.SaveBoard(str(path), b)
    print('routing imported, ground pours filled; run DRC with --refill-zones')


if __name__ == '__main__':
    main(sys.argv[1])
