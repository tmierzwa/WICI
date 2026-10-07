# SPDX-License-Identifier: MIT
"""Import the kept Freerouting session and add the ground pours.

usage (KiCad Python, from tools/): finalize_board.py ../checks/routing.ses
Run once on a freshly placed board from make_board.py. The session belongs to
that exact placement; a placement change needs a new routing run.
"""
from pathlib import Path
import sys

import pcbnew as k

from design import BOARD_W, BOARD_H, SOLID_GND_PADS

ROOT = Path(__file__).resolve().parents[1]
OX, OY = 30.0, 30.0


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
