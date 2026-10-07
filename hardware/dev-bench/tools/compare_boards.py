# SPDX-License-Identifier: MIT
"""Compare two carrier boards by geometry and nets, ignoring UUIDs and item order.

usage (KiCad Python): compare_boards.py A.kicad_pcb B.kicad_pcb
Exit code 0 when footprints, pads, tracks, vias, zones and drawings match.
KiCad gives footprints new UUIDs on every generation and orders the file by
them, so a byte comparison of two generated boards always differs.
"""
import sys

import pcbnew as k


def mm(v):
    return round(k.ToMM(v), 4)


def xy(p):
    return mm(p.x), mm(p.y)


def summary(path):
    b = k.LoadBoard(path)
    out = set()
    for f in b.GetFootprints():
        out.add(('fp', f.GetReference(), f.GetFPIDAsString(), xy(f.GetPosition()),
                 round(f.GetOrientationDegrees(), 3), f.GetLayer()))
        for p in f.Pads():
            out.add(('pad', f.GetReference(), p.GetNumber(), xy(p.GetPosition()), p.GetNetname(),
                     int(p.GetLocalZoneConnection())))
    for t in b.GetTracks():
        ends = tuple(sorted([xy(t.GetStart()), xy(t.GetEnd())]))
        if t.GetClass() == 'PCB_VIA':
            v = t.Cast()
            size = (mm(v.GetWidth(k.F_Cu)), mm(v.GetDrillValue()))
        else:
            size = mm(t.GetWidth())
        out.add((t.GetClass(), ends, size, t.GetLayer(), t.GetNetname()))
    for z in b.Zones():
        o = z.Outline()
        pts = tuple(xy(o.CVertex(i)) for i in range(o.TotalVertices()))
        out.add(('zone', z.GetNetname(), z.GetIsRuleArea(), z.GetLayerSet().FmtHex(), pts))
    for d in b.GetDrawings():
        box = d.GetBoundingBox()
        out.add(('drawing', d.GetClass(), d.GetLayer(), xy(box.GetOrigin()), xy(box.GetEnd()),
                 d.GetText() if isinstance(d, k.PCB_TEXT) else ''))
    return out


def main():
    a, b = summary(sys.argv[1]), summary(sys.argv[2])
    only_a, only_b = sorted(map(str, a - b)), sorted(map(str, b - a))
    for line in only_a[:20]:
        print('<', line)
    for line in only_b[:20]:
        print('>', line)
    print(f'{len(a)} items; {len(only_a)} only in A, {len(only_b)} only in B')
    sys.exit(1 if only_a or only_b else 0)


if __name__ == '__main__':
    main()
