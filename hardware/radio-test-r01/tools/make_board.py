# SPDX-License-Identifier: GPL-3.0-or-later
"""Place the controller candidate and export a local routing job.

This is a review candidate. Routing and ERC/DRC do not establish radio,
USB, mechanical, thermal, or firmware qualification.
"""
import json
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET
import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
NS = uuid.UUID('467d264c-787d-4b39-8f3c-c13d337d015a')


def uid(name):
    return str(uuid.uuid5(NS, name))


def pt(x, y):
    return k.VECTOR2I(k.FromMM(80 + x), k.FromMM(60 + y))


# Local millimetres, all components on the front. USB faces the right edge.
PLACEMENTS = {
    'U1': (32, 27, 0), 'J1': (53, 25, 0), 'U2': (46, 14, 180),
    'U3': (48, 26, 0), 'Y1': (20.5, 26.25, 0), 'U4': (32, 14, 0),
    'Q1': (43, 21, 0), 'J2': (12, 37, 0), 'J3': (46, 6, 90),
    'J4': (39, 40, 0), 'SW1': (30, 45, 0), 'D1': (57, 43, 0),
    'R1': (40, 25, 0), 'R2': (40, 27, 0), 'R3': (46, 22.5, 270),
    'R4': (43, 18, 0), 'R5': (24, 35, 0), 'R6': (25, 18, 0),
    'R7': (32.7, 34, 90), 'R8': (23, 40.5, 0), 'R9': (21, 43, 0),
    'R10': (37, 15, 90), 'R11': (37, 11, 90), 'R12': (52, 43, 0),
    'C1': (50.5, 14, 0), 'C2': (41.5, 14, 180),
    'C3': (34.75, 34, 270), 'C4': (38.5, 22, 0),
    'C5': (29.25, 20, 90), 'C6': (24.5, 23.75, 180),
    'C7': (24.5, 28.75, 180), 'C8': (24.5, 31.5, 180),
    'C9': (39, 31, 0), 'C10': (20, 22, 0), 'C11': (32, 10, 0),
    'C12': (24, 38, 0), 'C13': (20.5, 35, 90), 'C14': (49, 18, 0),
    'TP1': (55.5, 12, 0), 'TP2': (41, 10, 0), 'TP3': (55, 15, 0),
    'TP4': (20, 32, 0), 'TP5': (24, 26.25, 0),
    'TP6': (21, 46, 0), 'TP7': (27, 38, 0),
}


def main():
    b = k.BOARD()
    b.SetCopperLayerCount(4)
    b.GetDesignSettings().SetBoardThickness(k.FromMM(1.6))
    ds = b.GetDesignSettings()
    ds.m_MinClearance = k.FromMM(.2)
    ds.m_TrackMinWidth = k.FromMM(.18)
    ds.m_ViasMinSize = k.FromMM(.6)
    ds.m_MinThroughDrill = k.FromMM(.3)
    ds.m_CopperEdgeClearance = k.FromMM(.5)
    parts = json.loads((ROOT / 'connections.json').read_text())
    xml = ET.parse(ROOT / 'checks/schematic.net.xml')
    nc = {}
    for n in xml.findall('./nets/net'):
        if n.attrib['name'].startswith('unconnected-'):
            assert len(n.findall('node')) == 1
            node = n.find('node')
            nc[node.attrib['ref'], node.attrib['pin']] = n.attrib['name']
    nets = {}
    for name in sorted({n for p in parts for n in p['nets'].values()}):
        net = k.NETINFO_ITEM(b, '/' + name)
        b.Add(net)
        nets[name] = net
    for name in nc.values():
        net = k.NETINFO_ITEM(b, name)
        b.Add(net)
        nets[name] = net
    fps = {}
    for p in parts:
        ref = p['ref']
        lib, name = p['footprint'].split(':')
        f = k.FootprintLoad(str(ROOT / 'cad/footprints' / (lib + '.pretty')), name)
        if f is None:
            raise RuntimeError(p['footprint'])
        f.SetReference(ref)
        f.SetValue(p['value'])
        f.SetFPID(k.LIB_ID(lib, name))
        path = k.KIID_PATH()
        path.push_back(k.KIID(uid('root')))
        path.push_back(k.KIID(uid(ref)))
        f.SetPath(path)
        x, y, angle = PLACEMENTS[ref]
        f.SetPosition(pt(x, y))
        f.SetOrientation(k.EDA_ANGLE(angle, k.DEGREES_T))
        for pad in f.Pads():
            netname = p['nets'].get(pad.GetNumber(), nc.get((ref, pad.GetNumber())))
            if netname:
                pad.SetNet(nets[netname])
        f.Reference().SetTextSize(k.VECTOR2I(k.FromMM(.8), k.FromMM(.8)))
        f.Reference().SetTextThickness(k.FromMM(.12))
        f.Value().SetVisible(False)
        b.Add(f)
        fps[ref] = f
    for start, end in [((0, 0), (70, 0)), ((70, 0), (70, 55)),
                       ((70, 55), (0, 55)), ((0, 55), (0, 0))]:
        e = k.PCB_SHAPE(b)
        e.SetShape(k.SHAPE_T_SEGMENT)
        e.SetStart(pt(*start))
        e.SetEnd(pt(*end))
        e.SetLayer(k.Edge_Cuts)
        e.SetWidth(k.FromMM(.05))
        b.Add(e)

    def track(net, points, width=.2, layer=k.F_Cu):
        for a, z in zip(points, points[1:]):
            t = k.PCB_TRACK(b)
            t.SetStart(a); t.SetEnd(z); t.SetWidth(k.FromMM(width))
            t.SetLayer(layer); t.SetNet(nets[net]); t.SetLocked(True)
            b.Add(t)

    def pos(ref, pad):
        return fps[ref].FindPadByNumber(str(pad)).GetPosition()

    # Fixed USB routes; no vias or unrelated tracks in the data path.
    # The final stackup and differential impedance remain a release gate.
    track('USB_DP_MCU', [pos('U1', 33), pt(37, 25.75), pt(37.75, 25), pos('R1', 2)])
    track('USB_DM_MCU', [pos('U1', 32), pt(37.2, 26.25), pt(37.95, 27), pos('R2', 2)])
    track('USB_DP', [pos('R1', 1), pt(45, 25), pos('U3', 1)])
    track('USB_DM', [pos('R2', 1), pt(45, 27), pos('U3', 3)])
    track('USB_DP', [pos('U3', 1), pos('U3', 6)])
    track('USB_DM', [pos('U3', 3), pos('U3', 4)])
    track('USB_DP', [pos('R3', 2), pt(46, 24), pt(45, 25)])
    track('USB_DP', [pos('U3', 6), pt(50.5, 23.7), pt(56.4, 23.7),
                     pt(57, 24.3), pt(57, 25.5), pos('J1', 3)])
    track('USB_DM', [pos('U3', 4), pt(52.45, 26.95), pos('J1', 2)])

    # Large ground and 3.3 V pours. Power taps are routed by the
    # routing job; connected copper must be confirmed after zone refill.
    for netname, layer in [('GND', k.In1_Cu), ('V3', k.In2_Cu)]:
        zone = k.ZONE(b)
        zone.SetLayer(layer); zone.SetNet(nets[netname])
        zone.SetLocalClearance(k.FromMM(.2))
        zone.SetPadConnection(k.ZONE_CONNECTION_FULL)
        zone.SetMinThickness(k.FromMM(.2))
        outline = zone.Outline(); outline.NewOutline()
        for x, y in [(.5, .5), (69.5, .5), (69.5, 54.5), (.5, 54.5)]:
            outline.Append(pt(x, y))
        b.Add(zone)
    for text, x, y in [('WICI R01 / REVIEW ONLY', 35, 51),
                       ('RADIO: 3V3 ONLY', 13, 31), ('USB', 64, 38),
                       ('SWD: SENSE ONLY', 47, 3)]:
        t = k.PCB_TEXT(b); t.SetText(text); t.SetPosition(pt(x, y))
        t.SetLayer(k.F_SilkS); t.SetTextSize(k.VECTOR2I(k.FromMM(1), k.FromMM(1)))
        t.SetTextThickness(k.FromMM(.15)); b.Add(t)
    # Give every component a readable front-side reference. Find empty space
    # outside actual footprint geometry; the final DRC still checks the text.
    boxes = []
    def rectangle(item):
        q = item.GetBoundingBox()
        return tuple(k.ToMM(z) for z in (q.GetLeft(), q.GetTop(), q.GetRight(), q.GetBottom()))
    for f in fps.values():
        q = f.GetBoundingBox(False, False)
        boxes.append(tuple(k.ToMM(z) for z in (q.GetLeft(), q.GetTop(), q.GetRight(), q.GetBottom())))
    boxes.extend(rectangle(d) for d in b.GetDrawings() if isinstance(d, k.PCB_TEXT))
    def overlaps(a, z):
        return a[0] < z[2] and z[0] < a[2] and a[1] < z[3] and z[1] < a[3]
    for ref, f in fps.items():
        cx, cy, _ = PLACEMENTS[ref]
        cx += 80; cy += 60
        candidates = [(cx + dx / 2, cy + dy / 2) for dx in range(-20, 21) for dy in range(-20, 21)]
        candidates.sort(key=lambda xy: (xy[0] - cx) ** 2 + (xy[1] - cy) ** 2)
        hw, hh = .45 * len(ref) + .2, .65
        for x, y in candidates:
            rect = (x - hw, y - hh, x + hw, y + hh)
            if rect[0] < 80.5 or rect[2] > 149.5 or rect[1] < 60.5 or rect[3] > 114.5:
                continue
            if not any(overlaps(rect, q) for q in boxes):
                f.Reference().SetPosition(k.VECTOR2I(k.FromMM(x), k.FromMM(y)))
                f.Reference().SetTextAngle(k.EDA_ANGLE(0, k.DEGREES_T))
                boxes.append(rect)
                break
        else:
            raise RuntimeError('No clear silkscreen space for ' + ref)
    b.BuildConnectivity()
    target = ROOT / 'cad/radio-usb-controller.kicad_pcb'
    k.SaveBoard(str(target), b)
    if not k.ExportSpecctraDSN(b, str(ROOT / 'checks/controller.dsn')):
        raise RuntimeError('DSN export failed')
    print(f'Placed {len(fps)} components. Candidate: {target}')


if __name__ == '__main__':
    # Pad 2 of the resistors must face left towards the MCU.
    PLACEMENTS['R1'] = (40, 25, 180)
    PLACEMENTS['R2'] = (40, 27, 180)
    main()
