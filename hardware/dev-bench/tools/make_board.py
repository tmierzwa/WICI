# SPDX-License-Identifier: MIT
"""Place the carrier from design.py and export the Specctra routing job.

Run with the Python of KiCad 10.0.6 after make_schematic.py and the netlist
export (checks/netlist.xml). Nets, including unconnected pins, come from the
schematic netlist, so board and schematic cannot disagree on connectivity.
"""
from pathlib import Path
import math
import uuid
import xml.etree.ElementTree as ET

import pcbnew as k

from make_project import POWER

from design import (PARTS, BOARD_W, BOARD_H, NOTCH_P5, SLOT_P20, EM_P1, EM_W, EM_H, EM_X_U, EM_Y_U, EM_SMA,
                    PANEL_X, PANEL_Y, PANEL_W, PANEL_H, FPC_GAP, DEVKIT_X, DEVKIT_USB_Y, uno)

ROOT = Path(__file__).resolve().parents[1]
NS = uuid.UUID('9b1f0b57-36c4-4f4e-9d0c-2f6a1c8f2a10')
OX, OY = 30.0, 30.0  # board origin on the KiCad page


def uid(name):
    return str(uuid.uuid5(NS, name))


def pt(x, y):
    return k.VECTOR2I(k.FromMM(OX + x), k.FromMM(OY + y))


def mm(v):
    return round(k.ToMM(v), 4)


def line(b, a, z, layer, width):
    s = k.PCB_SHAPE(b)
    s.SetShape(k.SHAPE_T_SEGMENT)
    s.SetStart(pt(*a))
    s.SetEnd(pt(*z))
    s.SetLayer(layer)
    s.SetWidth(k.FromMM(width))
    b.Add(s)


def poly(b, points, layer, width):
    for a, z in zip(points, points[1:] + points[:1]):
        line(b, a, z, layer, width)


def text(b, s, x, y, size=1.0, layer=k.F_SilkS, bold=False, angle=0):
    t = k.PCB_TEXT(b)
    t.SetText(s)
    t.SetPosition(pt(x, y))
    t.SetLayer(layer)
    t.SetTextSize(k.VECTOR2I(k.FromMM(size), k.FromMM(size)))
    t.SetTextThickness(k.FromMM(max(0.15, size * 0.15)))
    t.SetBold(bold)
    t.SetTextAngle(k.EDA_ANGLE(angle, k.DEGREES_T))
    b.Add(t)
    return t


def netlist():
    """(ref, pin) -> net name from the KiCad XML netlist of the schematic."""
    xml = ET.parse(ROOT / 'checks/netlist.xml')
    out = {}
    for n in xml.findall('./nets/net'):
        for node in n.findall('node'):
            out[node.attrib['ref'], node.attrib['pin']] = n.attrib['name']
    return out


def build():
    b = k.BOARD()
    b.SetCopperLayerCount(2)
    ds = b.GetDesignSettings()
    ds.SetBoardThickness(k.FromMM(1.6))
    ds.m_MinClearance = k.FromMM(.2)
    ds.m_TrackMinWidth = k.FromMM(.2)
    ds.m_ViasMinSize = k.FromMM(.8)
    ds.m_MinThroughDrill = k.FromMM(.4)
    ds.m_CopperEdgeClearance = k.FromMM(.5)
    ds.m_HoleClearance = k.FromMM(.3)
    # Revision for the Gerber X2 attributes, the job file and the assembly drawing.
    tb = b.GetTitleBlock()
    tb.SetTitle('WICI carrier board N1')
    tb.SetRevision('N1')
    tb.SetCompany('WICI (CERN-OHL-P-2.0)')
    # Fabrication files take the lower-left board corner as origin.
    ds.SetAuxOrigin(pt(0, BOARD_H))
    nl = netlist()
    nets = {}
    for name in sorted(set(nl.values())):
        net = k.NETINFO_ITEM(b, name)
        b.Add(net)
        nets[name] = net
    fps = {}
    for p in PARTS:
        lib, name = p['footprint'].split(':')
        f = k.FootprintLoad(str(ROOT / 'cad/footprints' / (lib + '.pretty')), name)
        if f is None:
            raise RuntimeError(p['footprint'])
        f.SetReference(p['ref'])
        f.SetValue(p['value'])
        f.SetFPID(k.LIB_ID(lib, name))
        path = k.KIID_PATH()
        path.push_back(k.KIID(uid('root')))
        path.push_back(k.KIID(uid(p['ref'])))
        f.SetPath(path)
        x, y, angle = p['place']
        f.SetPosition(pt(x, y))
        f.SetOrientation(k.EDA_ANGLE(angle, k.DEGREES_T))
        variant = {'A': 'tylko A', 'B': 'tylko B', 'AB': 'A i B'}[p['variant']]
        for field, value in (('Manufacturer', p['manufacturer']), ('MPN', p['mpn']), ('Variant', variant)):
            f.SetField(field, value)
            f.GetField(field).SetVisible(False)
        for pad in f.Pads():
            num = pad.GetNumber()
            if num and (p['ref'], num) in nl:
                pad.SetNet(nets[nl[p['ref'], num]])
            elif num:
                raise RuntimeError(f"{p['ref']}.{num} missing from netlist")
        f.Reference().SetTextSize(k.VECTOR2I(k.FromMM(1.0), k.FromMM(1.0)))
        f.Reference().SetTextThickness(k.FromMM(.15))
        f.Value().SetVisible(False)
        if p['ref'].startswith('H'):
            f.Reference().SetVisible(False)
        b.Add(f)
        fps[p['ref']] = f

    def pad(ref, num):
        q = fps[ref].FindPadByNumber(str(num)).GetPosition()
        return round(mm(q.x) - OX, 3), round(mm(q.y) - OY, 3)

    # Geometry assertions: Arduino grid, header direction and module pins.
    assert pad('J1', 1) == uno(27.94, 2.54) and pad('J1', 8) == (round(uno(27.94 + 7 * 2.54, 2.54)[0], 3), 73.8)
    assert pad('J2', 6) == (round(uno(63.5, 2.54)[0], 3), 73.8)
    assert pad('J3', 8) == (round(uno(45.72, 50.8)[0], 3), 25.54), pad('J3', 8)
    assert pad('J4', 10) == (round(uno(18.796, 50.8)[0], 3), 25.54), pad('J4', 10)
    assert pad('J9', 19)[1] == round(EM_P1[1] + 9 * 1.27, 3) and pad('J9', 2)[0] == round(EM_P1[0] + 1.27, 3)
    assert round(pad('J10', 1)[0] - pad('J9', 1)[0], 3) == 30.48
    # FPC connector: pad 1 (panel SCLK) on the right, pads 0.5 mm apart, entry towards the panel.
    assert pad('J7', 1)[0] > pad('J7', 10)[0] and round(pad('J7', 1)[0] - pad('J7', 10)[0], 3) == 4.5
    assert round((pad('J7', 1)[0] + pad('J7', 10)[0]) / 2, 3) == round(PANEL_X + PANEL_W / 2, 3)
    assert pad('J7', 1)[1] > pad('J7', 'MP')[1] > PANEL_Y + PANEL_H
    # The panel lies flat on tape: no part under its glass.
    for ref, f in fps.items():
        q = f.GetBoundingBox(False)
        x0, y0, x1, y1 = (mm(v) for v in (q.GetLeft(), q.GetTop(), q.GetRight(), q.GetBottom()))
        assert not (x0 - OX < PANEL_X + PANEL_W and PANEL_X < x1 - OX and
                    y0 - OY < PANEL_Y + PANEL_H and PANEL_Y < y1 - OY), ('part under the panel', ref)
    assert pad('J5', 22)[1] == round(DEVKIT_USB_Y - 7.96, 3)
    assert round(pad('J6', 1)[0] - pad('J5', 1)[0], 3) == 22.86

    # Outline with the P5 notch.
    nx0, ny0, nx1, ny1 = NOTCH_P5
    outline = [(0, 0), (BOARD_W, 0), (BOARD_W, ny0), (nx0, ny0), (nx0, ny1), (BOARD_W, ny1),
               (BOARD_W, BOARD_H), (0, BOARD_H)]
    poly(b, outline, k.Edge_Cuts, .05)

    def keepout(points, fill, layers=None):
        z = k.ZONE(b)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowZoneFills(not fill)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        z.SetLayerSet(layers or k.LSET.AllCuMask())
        o = z.Outline()
        o.NewOutline()
        for x, y in points:
            o.Append(pt(x, y))
        b.Add(z)

    # Keep tracks and vias 0.7 mm away from the P5 notch (the router treats
    # only the outer outline as board edge). Over the P20 pin row no copper on
    # B.Cu and no vias, because the DK pin tips may touch the underside; F.Cu
    # tracks there are 1.6 mm of laminate away from the pins.
    bottom = k.LSET()
    bottom.AddLayer(k.B_Cu)
    for (x0, y0, x1, y1), fill, layers in ((NOTCH_P5, True, None), (SLOT_P20, False, bottom)):
        keepout([(x0 - .7, y0 - .7), (min(x1 + .7, BOARD_W), y0 - .7), (min(x1 + .7, BOARD_W), y1 + .7),
                 (x0 - .7, y1 + .7)], fill, layers)
    # No tracks under standoff faces and screw heads (M3 radius 3.3, M2.5 3.0 mm;
    # Arduino holes 2.6 mm, they take nylon or M2.5 screws with a head of at most 4.4 mm).
    for p in PARTS:
        if p['ref'].startswith('H'):
            hx, hy, _ = p['place']
            r = {'M2.5': 3.0, 'UNO': 2.6}.get(p['value'], 3.3)
            keepout([(hx + r * math.cos(i * math.pi / 12), hy + r * math.sin(i * math.pi / 12)) for i in range(24)], True)

    # Module outlines on the fab and silkscreen layers for assembly orientation;
    # the CC1120EM and the DevKitC also fit rotated by 180 degrees.
    ex, ey = uno(EM_X_U, EM_Y_U + EM_H)
    dy0 = DEVKIT_USB_Y - 62.865
    ux0, uy0 = uno(0, 53.34)
    for layer, width in ((k.F_Fab, .1), (k.F_SilkS, .15)):
        poly(b, [(ex, ey), (ex + EM_W, ey), (ex + EM_W, ey + EM_H), (ex, ey + EM_H)], layer, width)
        poly(b, [(PANEL_X, PANEL_Y), (PANEL_X + PANEL_W, PANEL_Y), (PANEL_X + PANEL_W, PANEL_Y + PANEL_H),
                 (PANEL_X, PANEL_Y + PANEL_H)], layer, width)
        g = .6 if layer == k.F_SilkS else 0  # silk clear of the socket outlines
        poly(b, [(DEVKIT_X - g, dy0), (DEVKIT_X + 25.4 + g, dy0), (DEVKIT_X + 25.4 + g, DEVKIT_USB_Y),
                 (DEVKIT_X - g, DEVKIT_USB_Y)], layer, width)
    # FPC tail (5.5 mm wide stiffener) from the glass edge to the connector entry, fab layer only.
    fx = PANEL_X + PANEL_W / 2
    poly(b, [(fx - 2.75, PANEL_Y + PANEL_H), (fx + 2.75, PANEL_Y + PANEL_H),
             (fx + 2.75, PANEL_Y + PANEL_H + FPC_GAP), (fx - 2.75, PANEL_Y + PANEL_H + FPC_GAP)], k.F_Fab, .1)
    poly(b, [(ux0, uy0), (BOARD_W - .3, uy0), (BOARD_W - .3, uy0 + 53.34), (ux0, uy0 + 53.34)], k.F_Fab, .1)
    # SMA position of the CC1120EM: a circle on the silkscreen.
    c = k.PCB_SHAPE(b)
    c.SetShape(k.SHAPE_T_CIRCLE)
    c.SetCenter(pt(*EM_SMA))
    c.SetEnd(pt(EM_SMA[0] + 3.0, EM_SMA[1]))
    c.SetLayer(k.F_SilkS)
    c.SetWidth(k.FromMM(.15))
    b.Add(c)
    # 50 mm scale bar below the outline for checking the 1:1 print.
    sy = BOARD_H + 6
    line(b, (0, sy), (50, sy), k.Dwgs_User, .3)
    for x in (0, 10, 20, 30, 40, 50):
        line(b, (x, sy - (1.5 if x in (0, 50) else .8)), (x, sy), k.Dwgs_User, .2)
    text(b, 'skala: 50 mm przy wydruku 1:1', 25, sy + 2.5, 1.5, layer=k.Dwgs_User)
    # Copper-free band over the DK header P20, drawn for the 1:1 fit print.
    px0, py0, px1, py1 = SLOT_P20
    for p0, p1 in (((px0, py0), (px1, py0)), ((px1, py0), (px1, py1)), ((px1, py1), (px0, py1)), ((px0, py1), (px0, py0))):
        line(b, p0, p1, k.Dwgs_User, .2)
    text(b, 'pas bez miedzi nad P20 płytki DK', (px0 + px1) / 2, py1 + 1.6, 1.0, layer=k.Dwgs_User)
    b.BuildConnectivity()
    return b, fps


def silkscreen(b, fps):
    """Assembly and variant texts; reference designators in free space."""
    texts = [
        ('WICI płytka nośna N1', 34, 97.4, 1.2, True),
        ('A: nRF52840-DK pod spodem, CC1120EM w J9/J10, JP3; JP1 JP2 zdjęte', 134, 5.5, 1.0, False),
        ('B: DevKitC w J5/J6, X-NUCLEO-S2868A2 w J1-J4, JP1 JP2; JP3 zdjęta', 134, 8.0, 1.0, False),
        ('NIGDY OBA MCU ANI OBA RADIA NARAZ', 134, 11.5, 1.1, True),
        ('GÓRA', 14, 77.6, 1.0, False), ('DÓŁ', 30, 77.6, 1.0, False),
        ('OK', 46, 77.6, 1.0, False), ('WSTECZ', 62, 77.6, 1.0, False),
        ('CISZA: 1-2', 14, 93.5, 1.0, False), ('PRZYGOT.', 28.25, 93.5, 1.0, False),
        ('ALARM', 37.3, 93.5, 1.0, False), ('BRZĘCZYK', 49.25, 96.0, 1.0, False),
        ('VTEST 0-15 V', 139.5, 98.6, 1.0, False), ('+', 150.0, 98.6, 1.0, True), ('GND', 155.6, 98.6, 1.0, False),
        ('GND SCK MO MI RF FR LCD G0 G2', 115.2, 94.8, 1.0, False),
        ('CC1120EM (A): SMA w kółku', 125.6, 48.0, 1.0, False),
        ('DevKitC (B): USB w dół', 86.2, 33.5, 1.0, False), ('USB', 86.2, 96.6, 1.0, True),
        ('Sharp LS027B7DH01A ekranem do góry, na taśmie', 40.0, 24.0, 1.0, False),
        ('bez części pod panelem', 40.0, 26.5, 1.0, False), ('FRAM', 86.0, 7.0, 1.0, False),
    ]
    for s, x, y, size, bold in texts:
        text(b, s, x, y, size, bold=bold)
    text(b, 'JP1 3V3 (B)', 92.8, 24.0, 1.0)
    text(b, 'JP2 5V (B)', 68.0, 81.3, 1.0, angle=90)
    text(b, 'JP3 RADIO (A)', 132.3, 84.6, 1.0)
    boxes = []

    def box(item):
        q = item.GetBoundingBox()
        return tuple(k.ToMM(z) for z in (q.GetLeft(), q.GetTop(), q.GetRight(), q.GetBottom()))
    for f in fps.values():
        q = f.GetBoundingBox(False)
        boxes.append(tuple(k.ToMM(z) for z in (q.GetLeft(), q.GetTop(), q.GetRight(), q.GetBottom())))
    boxes.extend(box(d) for d in b.GetDrawings()
                 if isinstance(d, k.PCB_TEXT) or (isinstance(d, k.PCB_SHAPE) and d.GetLayer() == k.F_SilkS))
    # Cut-outs and module windows count as occupied for designator text.
    for x0, y0, x1, y1 in (NOTCH_P5,):
        boxes.append((OX + x0 - .5, OY + y0 - .5, OX + x1 + .5, OY + y1 + .5))

    def overlaps(a, z):
        return a[0] < z[2] and z[0] < a[2] and a[1] < z[3] and z[1] < a[3]
    for ref, f in fps.items():
        if ref.startswith('H'):
            continue
        q = f.GetBoundingBox(False)
        cx, cy = k.ToMM(q.Centre().x), k.ToMM(q.Centre().y)
        hw, hh = .5 * len(ref) + .3, .75
        cands = [(cx + dx / 2, cy + dy / 2) for dx in range(-30, 31) for dy in range(-30, 31)]
        cands.sort(key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)
        for x, y in cands:
            r = (x - hw, y - hh, x + hw, y + hh)
            if r[0] < OX + .8 or r[2] > OX + BOARD_W - .8 or r[1] < OY + .8 or r[3] > OY + BOARD_H - .8:
                continue
            own = [box(g) for g in f.GraphicalItems() if g.GetLayer() == k.F_SilkS]
            if any(overlaps(r, z) for z in own) \
                    or any(overlaps(r, z) for z in boxes if z != tuple(k.ToMM(v) for v in (q.GetLeft(), q.GetTop(), q.GetRight(), q.GetBottom()))) \
                    or any(overlaps(r, (k.ToMM(pd.GetBoundingBox().GetLeft()) - .2, k.ToMM(pd.GetBoundingBox().GetTop()) - .2,
                                        k.ToMM(pd.GetBoundingBox().GetRight()) + .2, k.ToMM(pd.GetBoundingBox().GetBottom()) + .2))
                           for pd in f.Pads()):
                continue
            f.Reference().SetPosition(k.VECTOR2I(k.FromMM(x), k.FromMM(y)))
            f.Reference().SetTextAngle(k.EDA_ANGLE(0, k.DEGREES_T))
            boxes.append(r)
            break
        else:
            raise RuntimeError('no silkscreen space for ' + ref)


def main():
    b, fps = build()
    silkscreen(b, fps)
    target = ROOT / 'cad/plytka-nosna.kicad_pcb'
    k.SaveBoard(str(target), b)
    # Net classes for the routing job, equal to the project file (make_project.py).
    ns = b.GetDesignSettings().m_NetSettings
    d = ns.GetDefaultNetclass()
    for nc, width in ((d, .25), (k.NETCLASS('Power'), .4)):
        nc.SetTrackWidth(k.FromMM(width))
        nc.SetClearance(k.FromMM(.2))
        nc.SetViaDiameter(k.FromMM(.8))
        nc.SetViaDrill(k.FromMM(.4))
        if nc is not d:
            nc.SetPriority(0)
            ns.SetNetclass('Power', nc)
    for n in POWER:
        ns.SetNetclassPatternAssignment('/' + n, 'Power')
    ns.RecomputeEffectiveNetclasses()
    b.SynchronizeNetsAndNetClasses(True)
    if not k.ExportSpecctraDSN(b, str(ROOT / 'checks/routing.dsn')):
        raise RuntimeError('DSN export failed')
    print(f'placed {len(fps)} footprints: {target}')


if __name__ == '__main__':
    main()
