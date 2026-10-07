# SPDX-License-Identifier: MIT
"""Place the carrier from design.py and export the Specctra routing job.

Run with the Python of KiCad 10.0.6 after make_schematic.py and the netlist
export (checks/netlist.xml). Nets, including unconnected pins, come from the
schematic netlist, so board and schematic cannot disagree on connectivity.
"""
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET

import pcbnew as k

from make_project import POWER

from design import (PARTS, BOARD_W, BOARD_H, NOTCH_P5, SLOT_P20, EM_P1, EM_W, EM_H, EM_X_U, EM_Y_U,
                    LCD_X, LCD_Y, FRAM_X, FRAM_Y, DEVKIT_X, DEVKIT_USB_Y, uno)

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
    ds.m_ViasMinSize = k.FromMM(.6)
    ds.m_MinThroughDrill = k.FromMM(.3)
    ds.m_CopperEdgeClearance = k.FromMM(.5)
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
    assert pad('J7', 9)[0] == round(LCD_X + 41.91, 3) and pad('J8', 9)[0] == round(FRAM_X + 22.86, 3)
    assert pad('J5', 22)[1] == round(DEVKIT_USB_Y - 7.96, 3)
    assert round(pad('J6', 1)[0] - pad('J5', 1)[0], 3) == 22.86

    # Outline with the P5 notch and the P20 slot.
    nx0, ny0, nx1, ny1 = NOTCH_P5
    outline = [(0, 0), (BOARD_W, 0), (BOARD_W, ny0), (nx0, ny0), (nx0, ny1), (BOARD_W, ny1),
               (BOARD_W, BOARD_H), (0, BOARD_H)]
    poly(b, outline, k.Edge_Cuts, .05)

    # Keep tracks and vias 0.7 mm away from the P5 notch (the router treats
    # only the outer outline as board edge). Over the P20 pin list no vias and
    # no pads, so the underside there carries only masked tracks.
    for (x0, y0, x1, y1), tracks in ((NOTCH_P5, False), (SLOT_P20, True)):
        z = k.ZONE(b)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(not tracks)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowZoneFills(False)
        z.SetDoNotAllowPads(tracks)
        z.SetDoNotAllowFootprints(False)
        z.SetLayerSet(k.LSET.AllCuMask())
        o = z.Outline()
        o.NewOutline()
        for x, y in [(x0 - .7, y0 - .7), (min(x1 + .7, BOARD_W), y0 - .7), (min(x1 + .7, BOARD_W), y1 + .7), (x0 - .7, y1 + .7)]:
            o.Append(pt(x, y))
        b.Add(z)

    # Module outlines on the fab and silkscreen layers for assembly orientation.
    ex, ey = uno(EM_X_U, EM_Y_U + EM_H)
    poly(b, [(ex, ey), (ex + EM_W, ey), (ex + EM_W, ey + EM_H), (ex, ey + EM_H)], k.F_Fab, .1)
    poly(b, [(LCD_X, LCD_Y), (LCD_X + 63.5, LCD_Y), (LCD_X + 63.5, LCD_Y + 55.88), (LCD_X, LCD_Y + 55.88)], k.F_Fab, .1)
    poly(b, [(FRAM_X, FRAM_Y), (FRAM_X + 25.4, FRAM_Y), (FRAM_X + 25.4, FRAM_Y + 17.78), (FRAM_X, FRAM_Y + 17.78)], k.F_Fab, .1)
    dy0 = DEVKIT_USB_Y - 62.865
    poly(b, [(DEVKIT_X, dy0), (DEVKIT_X + 25.4, dy0), (DEVKIT_X + 25.4, DEVKIT_USB_Y), (DEVKIT_X, DEVKIT_USB_Y)], k.F_Fab, .1)
    ux0, uy0 = uno(0, 53.34)
    poly(b, [(ux0, uy0), (BOARD_W - .3, uy0), (BOARD_W - .3, uy0 + 53.34), (ux0, uy0 + 53.34)], k.F_Fab, .1)
    b.BuildConnectivity()
    return b, fps


def silkscreen(b, fps):
    """Assembly and variant texts; reference designators in free space."""
    texts = [
        ('WICI płytka nośna N1', 34, 97.4, 1.2, True),
        ('A: nRF52840-DK pod spodem, CC1120EM w J9/J10, JP1 JP2 zdjęte', 134, 6.0, .9, False),
        ('B: DevKitC w J5/J6, X-NUCLEO-S2868A2 w J1-J4, JP1 JP2 założone', 134, 8.4, .9, False),
        ('NIGDY OBA MCU ANI OBA RADIA NARAZ', 134, 12.0, 1.1, True),
        ('GÓRA', 14, 77.6, 1.0, False), ('DÓŁ', 30, 77.6, 1.0, False),
        ('OK', 46, 77.6, 1.0, False), ('WSTECZ', 62, 77.6, 1.0, False),
        ('CISZA: 1-2', 14, 93.5, .9, False), ('PRZYGOT.', 28.25, 93.5, .9, False),
        ('ALARM', 37.3, 93.5, .9, False), ('BRZĘCZYK', 49.25, 96.0, .9, False),
        ('VTEST 0-15 V', 152.5, 98.6, .9, False),
        
        ('GND SCK MOSI MISO RFCS FRCS LCDCS G0 G2', 115.2, 94.8, .8, False),
        ('CC1120EM: SMA tutaj, pin 1 od strony SMA', 125.6, 48.0, .8, False),
        ('ESP32-S3-DevKitC-1, USB w dół', 86.2, 33.5, .8, False),
        ('Sharp 4694', 39.8, 31.0, 1.0, False), ('FRAM 4719', 86.2, 13.0, .9, False),
    ]
    for s, x, y, size, bold in texts:
        text(b, s, x, y, size, bold=bold)
    text(b, 'JP1 3V3 (B)', 92.8, 24.0, .8)
    text(b, 'JP2 5V (B)', 68.3, 81.3, .8, angle=90)
    boxes = []

    def box(item):
        q = item.GetBoundingBox()
        return tuple(k.ToMM(z) for z in (q.GetLeft(), q.GetTop(), q.GetRight(), q.GetBottom()))
    for f in fps.values():
        q = f.GetBoundingBox(False)
        boxes.append(tuple(k.ToMM(z) for z in (q.GetLeft(), q.GetTop(), q.GetRight(), q.GetBottom())))
    boxes.extend(box(d) for d in b.GetDrawings() if isinstance(d, k.PCB_TEXT))
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
