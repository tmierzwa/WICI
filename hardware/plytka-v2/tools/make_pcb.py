# SPDX-License-Identifier: MIT
"""Preliminary placement of the v2 board: outline, mounting holes and footprints, no tracks.

usage: make_pcb.py KICAD_FOOTPRINT_DIR   (run with the KiCad Python, it needs pcbnew)
Writes cad/plytka-v2.kicad_pcb from tools/design.py. Board millimetres: origin at the top-left corner of
the outline, x right, y down, top side towards the lid. Assumptions (README, "Rozmieszczenie wstępne"):
- outline 200 x 120 mm with R4 corners and 12 x 12 mm notches for the lid screw bosses, at lid x 10-210,
  y 10-130 of the Hammond 1599KBAT (hardware/r02/obudowa.md); board = lid - 10 mm;
- panel items at the positions of hardware/obudowa/zalozenia.py (PANEL, CONNECTORS);
- DevKitC and Wio in sockets on the bottom side (decision 2026-10-31), away from the AA holder zone;
- mounting holes on an assumed 80 mm grid until the Hammond STEP model gives the bosses.
Small parts are packed automatically into the region of their block; the script stops if one does not fit.
"""
from pathlib import Path
import re
import sys
import uuid

import pcbnew

from design import PARTS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'cad' / 'plytka-v2.kicad_pcb'
W, H, NOTCH, RADIUS = 200.0, 120.0, 12.0, 4.0
LID_OFFSET = 10.0
GAP = 0.6  # clearance between packed bodies, mm
NS = uuid.UUID('4d0c3a2e-8b1f-4f7e-9a51-6c2b7e0d9f31')   # as make_schematic.py, so footprints link to symbols

# Panel: lid positions from hardware/obudowa/zalozenia.py minus LID_OFFSET.
DISPLAY_CENTER = (42.0, 32.0)          # window centre (52, 42) on the lid
DISPLAY_OUTLINE = (62.8, 42.82)
PANEL_POWER = (175.0, 90.0)            # PV6 main switch on the lid (185, 100), wired to J3
# Zones kept free (hardware/r02/obudowa.md, "Płyta bazowa"): (side, x0, y0, x1, y1, name, parts allowed inside).
# 'B' AA holder BH4AAW 61.25 x 57 x 14.6 mm in the base under the board (bottom parts <= 3 mm there, so only the
# solder tails of THT parts); 'T' the display (64 x 45 mm), the PV6 body, the CISZA guard (30 x 40 mm), the
# navigation buttons (22 mm) and 10 mm around the preparation button seen through the hole under the sticker.
ZONES = [
    ('T', 10.0, 9.5, 74.0, 54.5, 'ekran Sharp', set()),
    ('B', 10.0, 58.0, 72.0, 116.0, 'koszyk ogniw 4 × AA', set()),
    ('T', 164.0, 79.0, 186.0, 101.0, 'przycisk PV6 wyłącznika', set()),
    ('T', 160.0, 28.0, 190.0, 68.0, 'osłona CISZY', {'SW5'}),
    ('T', 130.0, 102.0, 150.0, 122.0, 'otwór przygotowania', {'SW6', 'H4'}),
] + [('T', x - 11.0, 77.0, x + 11.0, 99.0, name, {ref}) for ref, x, name in
     (('SW4', 20.0, 'WSTECZ'), ('SW1', 52.0, 'GÓRA'), ('SW2', 84.0, 'DÓŁ'), ('SW3', 116.0, 'OK'))]

# Fixed parts: ref -> (x, y, rotation, side); x, y is the centre of the footprint body.
FIXED = {
    'SW4': (20.0, 88.0, 0, 'T'), 'SW1': (52.0, 88.0, 0, 'T'), 'SW2': (84.0, 88.0, 0, 'T'), 'SW3': (116.0, 88.0, 0, 'T'),
    'D1': (175.0, 12.0, 0, 'T'), 'SW5': (175.0, 48.0, 0, 'T'), 'SW6': (140.0, 112.0, 0, 'T'),
    'J3': (194.0, 92.0, 90, 'T'),
    'J4': (50.0, 115.8, 0, 'T'),         # USB-C, opening at the bottom edge (bottom wall, lid x 60)
    'J2': (100.0, 115.0, 0, 'T'),        # wires to the EN3 socket (bottom wall, lid x 110)
    'J1': (68.0, 115.0, 0, 'T'),         # wires to the AA holder
    'BZ1': (150.0, 20.0, 0, 'T'),        # >= 20 mm from the radio
    'F1': (114.0, 103.0, 0, 'B'), 'C50': (132.0, 84.0, 0, 'B'),
    'JP3': (172.0, 74.0, 90, 'T'),      # outside the CISZA guard zone
    'H1': (60.0, 4.8, 0, 'T'), 'H2': (140.0, 4.8, 0, 'T'), 'H3': (66.0, 104.0, 0, 'T'), 'H4': (128.0, 111.0, 0, 'T'),
}
# FPC connector placed by its footprint origin, 13.8 mm below the panel glass as on v1.1
# (hardware/dev-bench/tools/design.py: 9.4 mm glass to connector face plus 4.4 mm to the origin).
J7_AT = (DISPLAY_CENTER[0], DISPLAY_CENTER[1] + DISPLAY_OUTLINE[1] / 2 + 13.8, 180)
AT_EDGE = {'J4'}                        # may overhang the bottom edge towards the wall
# Sockets of the modules, bottom side: (x, y of pin 1, rotation). Seen from below the modules sit as on v1.1,
# so seen from the top the two rows swap sides.
SOCKETS = {
    'J6': (86.0, 9.0, 0), 'J5': (86.0 + 22.86, 9.0, 0),          # DevKitC J3 / J1, row spacing as v1.1
    'J9': (142.4, 67.4, 0), 'J8': (142.4 + 15.24, 67.4, 0),      # Wio J2 / J1, spacing from the Seeed drawing
}
# Packing regions per block: (side, x0, y0, x1, y1, start, refs). The first part goes as close as possible to
# the start point, every next one as close as possible to that first part (the IC of the block);
# 'C11>U4' places C11 as close as possible to U4 instead.
REGIONS = [
    ('T', 112, 8, 146, 40, (128, 20), ['U1', 'C3', 'R20', 'U4', 'C11>U4', 'U3', 'C12>U3', 'C13', 'R18']),
    ('T', 136, 56, 172, 86, (150.0, 75.0), ['C1', 'C2', 'R11', 'R12', 'R64']),
    ('T', 54, 56, 80, 78, (60, 66), ['U2', 'L1', 'C4', 'C6', 'C7', 'R13', 'R19', 'C8', 'C9', 'R21', 'R22', 'C10']),
    ('T', 10, 70, 130, 81, (10, 72), ['R5', 'R6', 'R7', 'R8', 'R9', 'R10', 'R16']),
    ('T', 154, 8, 166, 40, (160, 12), ['Q1', 'R1', 'R2', 'D2', 'R3', 'R4']),
    ('T', 112, 42, 146, 74, (124, 54), ['U7', 'C44', 'C45', 'C46', 'C47', 'L2', 'C43', 'C42', 'C41', 'C40', 'R60',
                                       'R61', 'R62', 'C48', 'C49', 'R67', 'C51', 'R68', 'R63']),
    ('T', 80, 96, 122, 113, (100, 108), ['D4', 'U5', 'Q2', 'Q3', 'C30', 'C31', 'R30', 'R31', 'R32', 'C32']),
    ('T', 124, 92, 162, 106, (134, 100), ['Q4', 'R33', 'D5', 'R34', 'Q5', 'R35', 'R36', 'D15', 'R37', 'R38', 'R39',
                                         'C33', 'D6']),
    ('T', 54, 95, 82, 114, (68, 106), ['D7', 'R40', 'Q6', 'R41', 'Q7', 'R43', 'R44', 'R45', 'C34', 'D11']),
    ('T', 146, 102, 188, 119, (160, 112), ['U6', 'C36', 'C37', 'R70', 'R71', 'C53', 'D13', 'D8', 'D9', 'R46', 'C35',
                                          'D10', 'R47', 'R48', 'D16', 'Q11', 'R72', 'Q8', 'R49', 'R50', 'D12']),
    ('T', 140, 84, 164, 94, (150, 89), ['Q9', 'R51', 'Q10', 'R53', 'R54', 'D14', 'R55', 'C52']),
    ('T', 26, 98, 60, 113, (50, 109), ['U8', 'R65', 'R66', 'R73', 'R74', 'D17', 'Q12', 'R75']),
]
# Placement rules checked on the result: (part, part, largest pad-to-pad distance in mm).
CLOSE = [
    ('U8', 'J4', 10.0), ('D4', 'J2', 10.0),                      # ESD and TVS at their connectors (obudowa.md)
    ('C44', 'U7', 5.0), ('C45', 'U7', 5.0), ('C46', 'U7', 5.0), ('C47', 'U7', 5.0),
    ('C40', 'U7', 6.0), ('C41', 'U7', 6.0), ('C42', 'U7', 6.0), ('C43', 'U7', 6.0),
    ('C1', 'J9', 8.0), ('C2', 'J9', 8.0),                        # at the Wio, between its two rows
    ('C36', 'U6', 5.0), ('C11', 'U4', 5.0),
]
def mm(v):
    return pcbnew.FromMM(v)


def load(board, footprint_dir, fpid):
    lib, name = fpid.split(':')
    path = ROOT / 'cad/footprints/WICI.pretty' if lib == 'WICI' else Path(footprint_dir) / (lib + '.pretty')
    fp = pcbnew.FootprintLoad(str(path), name)
    assert fp is not None, fpid
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    fp.SetParent(board)   # flipping needs the layer stack of the board
    return fp


def body(fp):
    """Bounding box of the footprint without its texts, in mm: (x0, y0, x1, y1)."""
    bb = fp.GetBoundingBox(False)
    return (pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()), pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))


def put(fp, x, y, rot, side, anchor='body'):
    """Place a footprint with its body centre, pin 1 or origin (anchor) at x, y on the given side."""
    fp.SetOrientationDegrees(rot)
    if side == 'B':
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    if anchor in ('pin1', 'origin'):
        ref = (next(p for p in fp.Pads() if p.GetNumber() == '1').GetPosition() if anchor == 'pin1'
               else fp.GetPosition())
        rx, ry = pcbnew.ToMM(ref.x), pcbnew.ToMM(ref.y)
    else:
        x0, y0, x1, y1 = body(fp)
        rx, ry = (x0 + x1) / 2, (y0 + y1) / 2
    fp.Move(pcbnew.VECTOR2I(mm(x - rx), mm(y - ry)))


def is_tht(fp):
    return any(p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH) for p in fp.Pads())


def overlaps(a, b, gap=GAP):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def inside_board(box):
    x0, y0, x1, y1 = box
    if x0 < 1 or y0 < 1 or x1 > W - 1 or y1 > H - 1:
        return False
    corner = [(0, 0), (W - NOTCH, 0), (0, H - NOTCH), (W - NOTCH, H - NOTCH)]
    return not any(overlaps(box, (cx, cy, cx + NOTCH, cy + NOTCH), 1.0) for cx, cy in corner)


def outline(board):
    """Rectangle with R4 outer corners and 12 x 12 mm corner notches, as segments and arcs on Edge.Cuts."""
    n, r = NOTCH, RADIUS
    pts = [(n, 0), (W - n, 0), (W - n, n), (W, n), (W, H - n), (W - n, H - n), (W - n, H), (n, H), (n, H - n),
           (0, H - n), (0, n), (n, n)]
    convex = {0, 1, 3, 4, 6, 7, 9, 10}   # outer corners get the radius; inner corners of the notches stay sharp
    segs = [[pts[i], pts[(i + 1) % len(pts)]] for i in range(len(pts))]

    def toward(a, b, d):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = (dx * dx + dy * dy) ** 0.5
        return (a[0] + dx / length * d, a[1] + dy / length * d)

    def edge(shape, *points):
        item = pcbnew.PCB_SHAPE(board, shape)
        v = [pcbnew.VECTOR2I(mm(x), mm(y)) for x, y in points]
        if shape == pcbnew.SHAPE_T_ARC:
            item.SetArcGeometry(*v)
        else:
            item.SetStart(v[0])
            item.SetEnd(v[1])
        item.SetLayer(pcbnew.Edge_Cuts)
        item.SetWidth(mm(0.1))
        board.Add(item)

    for i in sorted(convex):
        c, before, after = pts[i], segs[i - 1], segs[i]
        start, end = toward(c, before[0], r), toward(c, after[1], r)
        before[1], after[0] = start, end
        centre = (start[0] + end[0] - c[0], start[1] + end[1] - c[1])
        edge(pcbnew.SHAPE_T_ARC, start, toward(centre, c, r), end)
    for a, b in segs:
        edge(pcbnew.SHAPE_T_SEGMENT, a, b)


def zone_marks(board):
    """Outline of each kept-free zone on the fabrication layer of its side, with its name."""
    for side, x0, y0, x1, y1, name, _ in ZONES:
        layer = pcbnew.F_Fab if side == 'T' else pcbnew.B_Fab
        rect = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_RECTANGLE)
        rect.SetStart(pcbnew.VECTOR2I(mm(x0), mm(y0)))
        rect.SetEnd(pcbnew.VECTOR2I(mm(x1), mm(y1)))
        rect.SetLayer(layer)
        rect.SetWidth(mm(0.15))
        board.Add(rect)
        text = pcbnew.PCB_TEXT(board)
        text.SetText(name)
        text.SetPosition(pcbnew.VECTOR2I(mm((x0 + x1) / 2), mm(y0 + 3)))
        text.SetLayer(layer)
        text.SetTextSize(pcbnew.VECTOR2I(mm(1.5), mm(1.5)))
        text.SetMirrored(side == 'B')
        board.Add(text)


def stable(text):
    """Footprints sorted by reference and fixed UUIDs: a rebuild without changes gives the same file.
    KiCad orders footprints by their random UUID, which the Python API cannot set."""
    starts = [m.start() for m in re.finditer(r'^\t\(', text, re.M)]
    ends = starts[1:] + [text.rindex(')')]
    blocks = [text[a:b] for a, b in zip(starts, ends)]
    slots = [i for i, b in enumerate(blocks) if b.startswith('\t(footprint ')]
    ordered = sorted((blocks[i] for i in slots),
                     key=lambda b: [int(t) if t.isdigit() else t for t in
                                    re.split(r'(\d+)', re.search(r'\(property "Reference" "([^"]+)"', b).group(1))])
    for i, b in zip(slots, ordered):
        blocks[i] = b
    text = text[:starts[0]] + ''.join(blocks) + text[ends[-1]:]
    count = iter(range(1 << 30))
    return re.sub(r'\(uuid "[0-9a-f-]+"\)', lambda m: f'(uuid "{uuid.uuid5(NS, f"pcb.{next(count)}")}")', text)


def main():
    footprint_dir = sys.argv[1]
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    rules = board.GetDesignSettings()
    rules.m_MinClearance = mm(0.15)      # JLC two-layer capability; TSOT-23-8 has 0.25 mm between pads
    rules.m_NetSettings.GetDefaultNetclass().SetClearance(mm(0.15))
    nets = {}
    for p in PARTS:
        for net in p['nets'].values():
            if net not in nets:
                nets[net] = pcbnew.NETINFO_ITEM(board, net)
                board.Add(nets[net])
    outline(board)
    zone_marks(board)
    parts = {p['ref']: p for p in PARTS}
    placed = []                          # (side, box) of every placed body; THT parts block both sides
    footprints = {}

    def add(ref, fp):
        fp.SetReference(ref)
        fp.SetValue(parts[ref]['value'])
        fp.SetPath(pcbnew.KIID_PATH('/' + str(uuid.uuid5(NS, ref))))   # link to the schematic symbol
        fp.SetSheetfile('plytka-v2.kicad_sch')
        for pad in fp.Pads():
            net = parts[ref]['nets'].get(pad.GetNumber())
            if net:
                pad.SetNet(nets[net])
        board.Add(fp)
        footprints[ref] = fp
        box = body(fp)
        sides = ('T', 'B') if is_tht(fp) else ('B' if fp.IsFlipped() else 'T',)
        for s in sides:
            placed.append((s, box))

    def free(ref, box, sides, own, edge=False):
        """Body fits on the board, clear of bodies on the given sides and of the zones on its own side;
        the solder tails of a THT part under a zone (<= 3 mm over the AA holder) are allowed."""
        return ((edge or inside_board(box)) and not any(s in sides and overlaps(box, b) for s, b in placed)
                and not any(z[0] == own and ref not in z[6] and overlaps(box, z[1:5]) for z in ZONES))

    def fix(ref, x, y, rot, side, anchor='body'):
        fp = load(board, footprint_dir, parts[ref]['footprint'])
        put(fp, x, y, rot, side, anchor)
        if not free(ref, body(fp), ('T', 'B') if is_tht(fp) else (side,), side, edge=ref in AT_EDGE):
            sys.exit(f'{ref} overlaps an earlier part, a kept-free zone or the board edge')
        add(ref, fp)

    for ref, (x, y, rot) in SOCKETS.items():
        fix(ref, x, y, rot, 'B', 'pin1')
    # Bodies of the modules hanging under the sockets (DevKitC 25.4 x 62.7 mm, Wio 17.5 x 21 mm).
    for left, right, pins, length, margin in (('J6', 'J5', 22, 62.7, 1.5), ('J9', 'J8', 7, 21.0, 2.0)):
        p1 = [footprints[r].Pads()[0].GetPosition() for r in (left, right)]
        xs = sorted(pcbnew.ToMM(p.x) for p in p1)
        y0 = min(pcbnew.ToMM(p.y) for p in p1) - margin
        placed.append(('B', (xs[0] - 1.77, y0, xs[1] + 1.77, y0 + length)))
    fix('J7', *J7_AT, 'T', 'origin')
    for ref, (x, y, rot, side) in FIXED.items():
        fix(ref, x, y, rot, side)
    for side, x0, y0, x1, y1, start, refs in REGIONS:
        target = start
        for entry in refs:
            ref, _, near = entry.partition('>')
            goal = target
            if near:
                b = body(footprints[near])
                goal = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
            best = None
            for rot in (0, 90):
                fp = load(board, footprint_dir, parts[ref]['footprint'])
                put(fp, 0, 0, rot, side)
                bx0, by0, bx1, by1 = body(fp)
                w, h = bx1 - bx0, by1 - by0
                sides = ('T', 'B') if is_tht(fp) else (side,)
                y = y0
                while y + h <= y1:
                    x = x0
                    while x + w <= x1:
                        cost = (x + w / 2 - goal[0]) ** 2 + (y + h / 2 - goal[1]) ** 2
                        if (best is None or cost < best[0]) and free(ref, (x, y, x + w, y + h), sides, side):
                            best = (cost, x + w / 2, y + h / 2, rot)
                        x += 0.5
                    y += 0.5
            if best is None:
                sys.exit(f'{ref} does not fit into its region {x0, y0, x1, y1}')
            fix(ref, best[1], best[2], best[3], side)
            if entry == refs[0]:
                target = (best[1], best[2])
    missing = sorted(set(parts) - set(footprints))
    assert not missing, ('not placed', missing)
    for a, b, limit in CLOSE:
        d = min(((pcbnew.ToMM(p.GetPosition().x - q.GetPosition().x)) ** 2
                 + (pcbnew.ToMM(p.GetPosition().y - q.GetPosition().y)) ** 2) ** 0.5
                for p in footprints[a].Pads() for q in footprints[b].Pads())
        if d > limit:
            sys.exit(f'{a} is {d:.1f} mm from {b}, limit {limit:g} mm')
    board.Save(str(OUT))
    OUT.write_text(stable(OUT.read_text()))
    print(f'{len(footprints)} footprints placed, outline {W:g} x {H:g} mm')


if __name__ == '__main__':
    main()
