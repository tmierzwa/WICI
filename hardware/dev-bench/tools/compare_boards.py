# SPDX-License-Identifier: MIT
"""Compare two carrier boards by geometry and nets, ignoring UUIDs and item order.

usage (KiCad Python): compare_boards.py A.kicad_pcb B.kicad_pcb
Exit code 0 when footprints (with their graphics and texts), pads (position,
net, shape, size, drill, layers), tracks, vias, zones (outline, settings and
filled copper) and board drawings match. Filled copper is compared by area:
KiCad splits fills into polygons at seams that move between runs, so the
symmetric difference of the fills on each layer must stay below 0.001 mm^2.
Fill both boards the same way (DRC with --refill-zones) before comparing.
KiCad gives footprints new UUIDs on every generation and orders the file by
them, so a byte comparison of two generated boards always differs.
"""
import sys

import pcbnew as k


def mm(v):
    return round(k.ToMM(v), 4)


def xy(p):
    return mm(p.x), mm(p.y)


def shape(d):
    """Geometry of a board or footprint graphic: kind, layer, width and points."""
    if isinstance(d, k.PCB_TEXT):
        return ('text', d.GetLayer(), d.GetText(), xy(d.GetPosition()), round(d.GetTextAngleDegrees(), 3),
                mm(d.GetTextSize().x), mm(d.GetTextThickness()), d.IsVisible())
    pts = ()
    if d.GetShape() == k.SHAPE_T_POLY:
        o = d.GetPolyShape()
        pts = tuple(xy(o.CVertex(i)) for i in range(o.TotalVertices()))
    return ('shape', d.GetLayer(), int(d.GetShape()), xy(d.GetStart()), xy(d.GetEnd()), mm(d.GetWidth()),
            bool(d.IsSolidFill()), pts)


def fills(b):
    """Filled copper per (net, layer) as one polygon set."""
    out = {}
    for z in b.Zones():
        if z.GetIsRuleArea() or not z.IsFilled():
            continue
        for layer in z.GetLayerSet().Seq():
            if z.HasFilledPolysForLayer(layer):
                out.setdefault((z.GetNetname(), layer), k.SHAPE_POLY_SET()).BooleanAdd(z.GetFilledPolysList(layer))
    return out


def area(polys):
    return sum(polys.Outline(i).Area() - sum(polys.Hole(i, h).Area() for h in range(polys.HoleCount(i)))
               for i in range(polys.OutlineCount())) / 1e12  # nm^2 -> mm^2


def fill_differences(a, b):
    fa, fb = fills(a), fills(b)
    out = []
    for key in sorted(set(fa) | set(fb), key=str):
        if key not in fa or key not in fb:
            out.append((key, 'missing'))
            continue
        x, y = fa[key].CloneDropTriangulation(), fb[key].CloneDropTriangulation()
        x.BooleanSubtract(fb[key])
        y.BooleanSubtract(fa[key])
        d = area(x) + area(y)
        if d > 1e-3:
            out.append((key, f'{d:.4f} mm2'))
    return out


def summary(path):
    b = k.LoadBoard(path)
    out = set()
    for f in b.GetFootprints():
        ref = f.GetReference()
        out.add(('fp', ref, f.GetFPIDAsString(), xy(f.GetPosition()),
                 round(f.GetOrientationDegrees(), 3), f.GetLayer(), f.GetValue(), int(f.GetAttributes())))
        for field in f.GetFields():
            out.add(('field', ref, field.GetName(), field.GetText(), xy(field.GetPosition()), field.IsVisible(),
                     mm(field.GetTextSize().x)))
        for g in f.GraphicalItems():
            out.add(('fp_graphic', ref) + shape(g))
        for p in f.Pads():
            out.add(('pad', ref, p.GetNumber(), xy(p.GetPosition()), p.GetNetname(),
                     int(p.GetLocalZoneConnection()), int(p.GetAttribute()), int(p.GetShape(k.F_Cu)),
                     xy(p.GetSize(k.F_Cu)), round(p.GetOrientationDegrees(), 3), xy(p.GetDrillSize()),
                     int(p.GetDrillShape()), p.GetLayerSet().FmtHex(), xy(p.GetOffset(k.F_Cu))))
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
        key = (z.GetNetname(), z.GetIsRuleArea(), z.GetLayerSet().FmtHex(), pts)
        out.add(('zone',) + key + (mm(z.GetLocalClearance() or 0), mm(z.GetMinThickness()),
                                    int(z.GetPadConnection()), mm(z.GetThermalReliefGap()),
                                    mm(z.GetThermalReliefSpokeWidth()), int(z.GetIslandRemovalMode()),
                                    z.GetAssignedPriority()))
    for d in b.GetDrawings():
        out.add(('drawing', d.GetClass()) + shape(d))
    return out, b


def main():
    (a, board_a), (b, board_b) = summary(sys.argv[1]), summary(sys.argv[2])
    only_a, only_b = sorted(map(str, a - b)), sorted(map(str, b - a))
    for line in only_a[:20]:
        print('<', line)
    for line in only_b[:20]:
        print('>', line)
    fill = fill_differences(board_a, board_b)
    for key, what in fill:
        print('fill differs', key, what)
    print(f'{len(a)} items; {len(only_a)} only in A, {len(only_b)} only in B; '
          f'{len(fills(board_a))} filled net layers, {len(fill)} differ')
    sys.exit(1 if only_a or only_b or fill else 0)


if __name__ == '__main__':
    main()
