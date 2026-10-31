# SPDX-License-Identifier: MIT
"""Test board of the 3.3 V converter (LTC3115-1) for the efficiency measurement before the v2 schematic.

Run with the Python of KiCad 10 (it has pcbnew):
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 tools/build.py

Writes cad/przetwornica-3v3.kicad_pcb. The circuit follows hardware/r02/zasilanie.md (750 kHz, 15 uH,
1 MOhm / 432 kOhm, type III compensation) and the layout follows figure 17 of the LTC3115-1 data sheet
(rev. E, FE package): inductor above the IC, SW2 and the output on the left, SW1 and the input on the
right, BST connections on the inner layer In2, an unbroken ground plane on In1 under the power loop.
Board-local millimetres, x to the right and y down; positions of the circuit are relative to U1.
"""

import csv
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent.parent
LIB = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
OUT = HERE / "cad" / "przetwornica-3v3.kicad_pcb"

BOARD_W, BOARD_H = 56.0, 48.0
U1_AT = (28.0, 19.0)          # U1 centre on the board
VIA, VIA_DRILL = 0.6, 0.3
SIGNAL, POWER = 0.2, 0.6      # track widths

board = pcbnew.BOARD()
board.SetCopperLayerCount(4)
board.GetDesignSettings().SetAuxOrigin(pcbnew.VECTOR2I(0, pcbnew.FromMM(BOARD_H)))  # lower-left
TOP, IN1, IN2, BOT = pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu

NETS = {}


def net(name):
    if name not in NETS:
        item = pcbnew.NETINFO_ITEM(board, name)
        board.Add(item)
        NETS[name] = item
    return NETS[name]


def pt(x, y):
    """Point relative to U1."""
    return pcbnew.VECTOR2I(pcbnew.FromMM(U1_AT[0] + x), pcbnew.FromMM(U1_AT[1] + y))


def abs_pt(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


# ---- parts ------------------------------------------------------------------------------------

BOM = []   # (ref, value, footprint, lcsc, mpn, assembled by JLC)


def place(ref, lib, name, value, x, y, rot, nets, lcsc="", mpn="", jlc=True, fp=None):
    """Footprint at (x, y) relative to U1, rotated rot degrees. nets: pad number -> net name, or a list of
    ((x, y), net) anchors: each pad gets the net of the nearest anchor (robust against rotation)."""
    fp = fp or pcbnew.FootprintLoad(str(LIB / f"{lib}.pretty"), name)
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.Value().SetVisible(False)          # values go to the BOM; the silk keeps only what the bench needs
    if any(k in name for k in ("0402", "0603", "0805", "1210", "2512", "CP_Radial", "TestPoint", "PinHeader", "Terminal")):  # own labels
        fp.Reference().SetVisible(False)
    fp.SetPosition(pt(x, y))
    fp.SetOrientationDegrees(rot)
    board.Add(fp)
    for pad in fp.Pads():
        if isinstance(nets, dict):
            name_ = nets.get(pad.GetNumber())
        else:
            px, py = pcbnew.ToMM(pad.GetPosition().x) - U1_AT[0], pcbnew.ToMM(pad.GetPosition().y) - U1_AT[1]
            name_ = min(nets, key=lambda a: (a[0][0] - px) ** 2 + (a[0][1] - py) ** 2)[1]
        if name_:
            pad.SetNet(net(name_))
    if value:
        BOM.append((ref, value, f"{lib}:{name}" if lib else name, lcsc, mpn, jlc))
    return fp


def two(ref, lib, name, value, x, y, rot, a, b, lcsc="", mpn="", jlc=True):
    """Two-pad part; a and b are ((x, y), net) anchors for its two ends."""
    return place(ref, lib, name, value, x, y, rot, [a, b], lcsc, mpn, jlc)


def ltc3115_fe():
    """TSSOP-20 FE with the exposed pad of variation CA (2.74 x 4.95 mm, data sheet page 40) as pad 21."""
    fp = pcbnew.FootprintLoad(str(LIB / "Package_SO.pretty"), "TSSOP-20_4.4x6.5mm_P0.65mm")
    fp.SetFPID(pcbnew.LIB_ID("WICI", "LTC3115-1_FE20_CA"))
    ep = pcbnew.PAD(fp)
    ep.SetNumber("21")
    ep.SetShape(pcbnew.PAD_SHAPE_RECT)
    ep.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    layers = pcbnew.PAD.SMDMask()
    layers.RemoveLayer(pcbnew.F_Paste)
    ep.SetLayerSet(layers)
    ep.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(2.74), pcbnew.FromMM(4.95)))
    fp.Add(ep)
    # Paste in four windows between the rows of thermal vias (x +-0.75, y 0 and +-1.6), about 40% of the pad:
    # no paste over the via holes, less floating of the IC.
    paste = pcbnew.LSET()
    paste.AddLayer(pcbnew.F_Paste)
    for y, h in ((-0.8, 0.8), (0.8, 0.8), (-2.225, 0.45), (2.225, 0.45)):
        window = pcbnew.PAD(fp)
        window.SetShape(pcbnew.PAD_SHAPE_RECT)
        window.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        window.SetLayerSet(paste)
        window.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(2.2), pcbnew.FromMM(h)))
        window.SetPosition(pcbnew.VECTOR2I(0, pcbnew.FromMM(y)))
        fp.Add(window)
    return fp


def srp1038a():
    """Bourns SRP1038A: recommended layout 13.6 mm outside, 5.4 mm inside, pads 3.5 mm high."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("WICI", "L_Bourns_SRP1038A"))
    for num, x in (("1", -4.75), ("2", 4.75)):
        pad = pcbnew.PAD(fp)
        pad.SetNumber(num)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(4.1), pcbnew.FromMM(3.5)))
        pad.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), 0))
        fp.Add(pad)
    for y in (-5.1, 5.1):                      # silk only along the body edges between the pads
        line = pcbnew.PCB_SHAPE(fp)
        line.SetShape(pcbnew.SHAPE_T_SEGMENT)
        line.SetLayer(pcbnew.F_SilkS)
        line.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(-2.4), pcbnew.FromMM(y)))
        line.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(2.4), pcbnew.FromMM(y)))
        line.SetWidth(pcbnew.FromMM(0.12))
        fp.Add(line)
    for layer, w, h in ((pcbnew.F_CrtYd, 14.1, 10.5), (pcbnew.F_Fab, 11.0, 10.0)):
        box = pcbnew.PCB_SHAPE(fp)
        box.SetShape(pcbnew.SHAPE_T_RECT)
        box.SetLayer(layer)
        box.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(-w / 2), pcbnew.FromMM(-h / 2)))
        box.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(w / 2), pcbnew.FromMM(h / 2)))
        box.SetWidth(pcbnew.FromMM(0.1 if layer == pcbnew.F_Fab else 0.05))
        fp.Add(box)
    return fp


C0603, R0603 = ("Capacitor_SMD", "C_0603_1608Metric"), ("Resistor_SMD", "R_0603_1608Metric")

U1_NETS = {"1": "GND", "2": "RUN", "3": "SW2", "4": "VOUT", "5": "GND", "6": "GND", "7": "VC", "8": "FB",
           "9": "RT", "10": "GND", "11": "GND", "12": "VCC", "13": "VIN", "14": "VCC", "15": "BST2",
           "16": "BST1", "17": "VIN", "18": "SW1", "19": "PWM", "20": "GND", "21": "GND"}
place("U1", "", "LTC3115-1_FE20_CA", "LTC3115EFE-1#PBF", 0, 0, 0, U1_NETS, "C580689", "LTC3115EFE-1#PBF",
      fp=ltc3115_fe())
place("L1", "", "L_Bourns_SRP1038A", "15uH", 0, -11.5, 0, {"1": "SW2", "2": "SW1"}, "C780183",
      "Bourns SRP1038A-150M", fp=srp1038a())

# Input and output capacitors: 1210, pads one above the other, power pad towards the IC.
CIN, COUT = ("C596319", "Yageo CC1210KKX7R9BB106"), ("C2918506", "CS3225X5R226K160NRL")
for ref, x in (("C1", 9.0), ("C2", 12.4)):
    two(ref, "Capacitor_SMD", "C_1210_3225Metric", "10uF 50V X7R", x, -3.6, 90,
        ((x, -2.0), "VIN"), ((x, -5.2), "GND"), *CIN)
for ref, x in (("C3", -9.0), ("C4", -12.4)):
    two(ref, "Capacitor_SMD", "C_1210_3225Metric", "22uF 16V X5R", x, -3.6, 90,
        ((x, -2.0), "VOUT"), ((x, -5.2), "GND"), *COUT)

# Bootstrap capacitors inside the switch-node copper, BST end towards the IC (lower pad); 0402 fits
# between the courtyards of U1 and L1. They see about VCC (4.45 V), 16 V is enough.
C0402 = ("Capacitor_SMD", "C_0402_1005Metric")
two("C5", *C0402, "100nF 16V", 5.4, -4.6, 90, ((5.4, -4.1), "BST1"), ((5.4, -5.1), "SW1"), "C1525", "CL05B104KO5NNNC")
two("C6", *C0402, "100nF 16V", -5.4, -4.6, 90, ((-5.4, -4.1), "BST2"), ((-5.4, -5.1), "SW2"), "C1525", "CL05B104KO5NNNC")
# VIN pin bypass, VCC/PVCC bypass.
two("C7", *C0603, "100nF", 5.4, 1.75, 0, ((4.6, 1.75), "VIN"), ((6.2, 1.75), "GND"), "C14663", "CC0603KRX7R9BB104")
# VCC needs at least 4.7 uF effective (data sheet page 11); 10 uF 25 V 0805 keeps about 6 uF at 4.45 V.
two("C8", "Capacitor_SMD", "C_0805_2012Metric", "10uF 25V X5R", 2.4, 4.8, 0, ((1.4, 4.8), "VCC"), ((3.4, 4.8), "GND"),
    "C15850", "CL21A106KAYNNNE")
# Pull-downs keep RUN and PWM/SYNC low with the jumper removed. 10 MOhm on RUN adds only VIN / 10 MOhm
# (0.6-1.3 uA) to the no-load current; it keeps the IC off at power-up, but once running the 0.5 uA RUN
# hysteresis current (data sheet page 11) holds it on, so "off" is JP4 on pins 2-3. 100 kOhm on PWM/SYNC
# draws current only in PWM mode and holds the pin low against coupling from the SW1 copper.
two("R9", *R0603, "10M 1%", 6.0, 12.04, 0, ((5.2, 12.04), "RUN"), ((6.8, 12.04), "GND"), "C7250", "0603WAF1005T5E")
two("R10", *R0603, "100k 1%", 14.6, 1.5, 0, ((13.8, 1.5), "GND"), ((15.4, 1.5), "PWM"), "C25803", "0603WAF1003T5E")
# Bulk input capacitor for the bench leads and the ammeter in series (data sheet page 11). A general-purpose
# electrolytic: its ESR damps the lead inductance, a low-ESR polymer would damp it less.
place("C12", "Capacitor_THT", "CP_Radial_D6.3mm_P2.50mm", "47uF 25V", 22.0, 3.5, 270,
      [((22.0, 3.5), "VIN"), ((22.0, 6.0), "GND")], "C134708", "Lelon SG-470M1EBK-0607")

# Feedback and compensation below the IC, away from the switch nodes: a row of 0603 parts standing upright,
# the feedback bus along their upper pads (y 5.725), the lower pads at y 7.275, the second row at 9.5.
ROW1, ROW2 = 6.5, 9.5
two("R1", *R0603, "47.5k 1%", -1.8, ROW1, 90, ((-1.8, 5.7), "RT"), ((-1.8, 7.3), "GND"), "C23061", "0603WAF4752T5E")
two("R2", *R0603, "1M 1%", -9.0, ROW1, 90, ((-9.0, 5.7), "FB"), ((-9.0, 7.3), "VOUT"), "C22935", "0603WAF1004T5E")
two("R3", *R0603, "432k 1%", -7.2, ROW1, 90, ((-7.2, 5.7), "FB"), ((-7.2, 7.3), "GND"), "C23171", "0603WAF4323T5E")
two("C9", *C0603, "82pF C0G", -5.4, ROW1, 90, ((-5.4, 5.7), "FB"), ((-5.4, 7.3), "VC"), "C1683", "0603CG820J500NT")
two("C10", *C0603, "3.9nF", -3.6, ROW1, 90, ((-3.6, 5.7), "FB"), ((-3.6, 7.3), "NC"), "C1618", "0603B392K500NT")
two("R4", *R0603, "20k 1%", -3.6, ROW2, 90, ((-3.6, 8.7), "NC"), ((-3.6, 10.3), "VC"), "C4184", "0603WAF2002T5E")
two("C11", *C0603, "82pF C0G", -10.8, ROW1, 90, ((-10.8, 5.7), "FB"), ((-10.8, 7.3), "NF"), "C1683", "0603CG820J500NT")
two("R5", *R0603, "20k 1%", -10.8, ROW2, 90, ((-10.8, 8.7), "NF"), ((-10.8, 10.3), "VOUT"), "C4184", "0603WAF2002T5E")

# Loads on jumpers: 110 Ohm (30 mA), second 110 Ohm (with the first 60 mA), 22 Ohm (150 mA, like a TX pulse).
R2512 = ("Resistor_SMD", "R_2512_6332Metric")
LOADS = (("R6", "JP1", -14.4, "110R 1W 1%", "C7467343", "FRC2512F1100TS"),
         ("R7", "JP2", -18.6, "110R 1W 1%", "C7467343", "FRC2512F1100TS"),
         ("R8", "JP3", -22.8, "22R 1W 1%", "C2999530", "FRC2512F22R0TS"))
for ref, jp, x, value, lcsc, mpn in LOADS:
    load = f"OBC_{jp}"
    two(ref, *R2512, value, x, 10.8, 90, ((x, 7.8), "VOUT"), ((x, 13.8), load), lcsc, mpn)
    place(jp, "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical", "zworka", x, 18.0, 0,
          {"1": load, "2": "GND"}, "C32713268", "hanxia HX PZ2.54-1x2P ZZ")

# RUN and PWM/SYNC: three-pin jumpers (VIN/RUN/GND, VCC/PWM/GND); pin 2 is the IC pin.
place("JP4", "Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical", "RUN", 14.0, 9.5, 0,
      {"1": "VIN", "2": "RUN", "3": "GND"}, "C32713269", "hanxia HX PZ2.54-1x3P ZZ")
place("JP5", "Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical", "PWM/SYNC", 18.0, 9.5, 0,
      {"1": "VCC", "2": "PWM", "3": "GND"}, "C32713269", "hanxia HX PZ2.54-1x3P ZZ")

# Power terminals: input on the right, output (external load) on the left.
TB = ("TerminalBlock_Phoenix", "TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal")
place("J1", *TB, "VIN", 22.5, -2.0, 90, {"1": "VIN", "2": "GND"}, "C480516", "Phoenix Contact 1715721")
place("J2", *TB, "VOUT", -22.5, -2.0, 270, {"1": "VOUT", "2": "GND"}, "C480516", "Phoenix Contact 1715721")

# Probe pads for the voltmeter, input and output at the capacitors (the switch nodes are probed at the
# inductor pads, which stick out of its body by 1.3 mm).
TPF = ("TestPoint", "TestPoint_Pad_D1.5mm")
for ref, x, y, n in (("TP1", 15.5, -2.0, "VIN"), ("TP2", 15.5, -5.6, "GND"),
                     ("TP3", -15.5, -2.0, "VOUT"), ("TP4", -15.5, -5.6, "GND")):
    place(ref, *TPF, "", x, y, 0, {"1": n})

for x, y in ((2.5, 2.5), (BOARD_W - 2.5, 2.5), (2.5, BOARD_H - 2.5), (BOARD_W - 2.5, BOARD_H - 2.5)):
    hole = pcbnew.FootprintLoad(str(LIB / "MountingHole.pretty"), "MountingHole_3.2mm_M3")
    hole.SetPosition(abs_pt(x, y))
    hole.SetReference("H")
    hole.Reference().SetVisible(False)
    hole.Value().SetVisible(False)
    board.Add(hole)

# ---- copper -------------------------------------------------------------------------------------


def track(points, name, width=SIGNAL, layer=TOP):
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pt(x0, y0))
        t.SetEnd(pt(x1, y1))
        t.SetWidth(pcbnew.FromMM(width))
        t.SetLayer(layer)
        t.SetNet(net(name))
        board.Add(t)


def via(x, y, name, size=VIA, drill=VIA_DRILL):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pt(x, y))
    v.SetWidth(pcbnew.FromMM(size))
    v.SetDrill(pcbnew.FromMM(drill))
    v.SetNet(net(name))
    board.Add(v)


def zone(corners, name, layer=TOP, priority=1, absolute=False):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net(name))
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(pcbnew.FromMM(0.25))
    z.SetMinThickness(pcbnew.FromMM(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if priority else pcbnew.ZONE_CONNECTION_THT_THERMAL)
    z.SetThermalReliefGap(pcbnew.FromMM(0.3))
    z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.5))
    outline = z.Outline()
    outline.NewOutline()
    for x, y in corners:
        outline.Append(*(abs_pt(x, y) if absolute else pt(x, y)))
    board.Add(z)


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


# Power copper on the top layer (figure 17): switch nodes, input and output with their capacitors.
# As in figure 17 the switch-node copper wraps outside pins 1-2 and 19-20 down to pins 3 and 18; the RUN and
# PWM/SYNC vias sit inside it. The input and output copper leaves pins 17 and 4 below it.
zone(rect(-7.0, -13.6, -3.15, -1.35), "SW2", priority=3)
zone(rect(3.15, -13.6, 7.0, -1.35), "SW1", priority=3)
zone([(-3.15, -1.15), (-7.4, -1.15), (-7.4, -3.4), (-27.2, -3.4), (-27.2, 8.9), (-12.2, 8.9), (-12.2, -0.6),
      (-3.15, -0.6)], "VOUT", priority=3)
zone([(3.15, -1.15), (7.4, -1.15), (7.4, -3.4), (27.2, -3.4), (27.2, 4.6), (19.0, 4.6), (19.0, -0.6), (3.15, -0.6)],
     "VIN", priority=3)                                         # with a lobe under J1 for C12
zone(rect(-17.0, -8.6, -7.4, -4.0), "GND", priority=2)
zone(rect(7.4, -8.6, 17.0, -4.0), "GND", priority=2)
# Ground everywhere else: top fill, In1 unbroken plane, In2 and bottom fills around the signal routes.
for layer in (TOP, IN1, IN2, BOT):
    zone(rect(0.3, 0.3, BOARD_W - 0.3, BOARD_H - 0.3), "GND", layer=layer, priority=0, absolute=True)

# U1 ground pins (1, 5, 6, 10, 20, 11) straight into the exposed pad, under the body; thermal vias in the pad.
for y in (-2.925, -0.325, 0.325, 2.925):
    track([(-2.3, y), (-1.2, y)], "GND", 0.3)
track([(2.3, -2.925), (1.2, -2.925)], "GND", 0.3)
track([(3.4, 2.925), (3.4, 4.4)], "GND", 0.3)                  # pin 11 to the ground pad of C8
for x in (-0.75, 0.75):
    for y in (-1.6, 0.0, 1.6):
        via(x, y, "GND")

# VCC: pins 14 and 12 tied under the body (between the pins and the exposed pad), down to C8, then on the
# bottom layer to the PWM/SYNC jumper (high = PWM).
track([(2.3, 0.975), (1.75, 0.975), (1.75, 4.2), (1.45, 4.5)], "VCC", 0.25)
track([(2.3, 2.275), (1.75, 2.275)], "VCC", 0.25)
track([(1.45, 4.8), (1.45, 6.2)], "VCC", 0.25)
via(1.45, 6.2, "VCC")
track([(1.45, 6.2), (18.0, 6.2), (18.0, 9.5)], "VCC", SIGNAL, BOT)

# Bootstrap: pin 16 (BST1) and pin 15 (BST2) down to In2, up again next to C5 and C6.
# The BST1 via sits below the input copper so that it does not narrow the path from pin 17.
track([(3.4, -0.325), (5.6, 0.0)], "BST1")
via(5.6, 0.0, "BST1")
track([(5.6, 0.0), (5.6, -2.4), (5.4, -3.0)], "BST1", 0.3, IN2)
via(5.4, -3.0, "BST1")
track([(5.4, -3.0), (5.4, -4.1)], "BST1", 0.3)
track([(3.4, 0.325), (4.3, 0.55)], "BST2")
via(4.3, 0.55, "BST2")
# BST2 crosses under the IC between the rows of thermal vias (y -0.8), away from the VC via, up to C6.
track([(4.3, 0.55), (3.0, -0.8), (-3.0, -0.8), (-5.4, -1.5), (-5.4, -3.0)], "BST2", 0.3, IN2)
via(-5.4, -3.0, "BST2")
track([(-5.4, -3.0), (-5.4, -4.1)], "BST2", 0.3)

# VIN pin 13 with its own 100 nF (C7), then on In2 to the input copper and to the RUN jumper (pin 1).
track([(3.4, 1.625), (4.6, 1.75)], "VIN", 0.3)
track([(4.6, 1.75), (4.6, 2.9)], "VIN", 0.3)
via(4.6, 2.9, "VIN")
track([(6.2, 1.75), (7.1, 1.75)], "GND", 0.3)
via(7.1, 1.75, "GND")
track([(4.6, 2.9), (14.0, 2.9), (14.0, 9.5)], "VIN", 0.3, IN2)
track([(14.0, 2.9), (14.5, 2.4), (14.5, -1.0)], "VIN", 0.3, IN2)
via(14.5, -1.0, "VIN")

# PWM/SYNC (pin 19) and RUN (pin 2) on the bottom layer to the middle pins of their jumpers; RUN passes
# under the exposed pad between the two columns of thermal vias.
track([(3.4, -2.275), (4.3, -2.55)], "PWM")
via(4.3, -2.55, "PWM")
track([(4.3, -2.55), (4.55, -2.3), (16.5, -2.3), (16.5, 4.0), (20.0, 4.0), (20.0, 12.04), (18.0, 12.04)],
      "PWM", SIGNAL, BOT)
via(16.5, 1.5, "PWM")
track([(15.375, 1.5), (16.5, 1.5)], "PWM")                      # R10 pull-down
track([(-3.4, -2.275), (-4.3, -2.55)], "RUN")
via(-4.3, -2.55, "RUN")
track([(-4.3, -2.55), (0.0, -2.55), (0.0, 12.04), (14.0, 12.04)], "RUN", SIGNAL, BOT)
via(4.4, 12.04, "RUN")
track([(4.4, 12.04), (5.225, 12.04)], "RUN")                    # R9 pull-down

# VC (pin 7) on In2 to the compensation network, FB (pin 8) and RT (pin 9) on top.
track([(-3.4, 0.975), (-4.45, 0.8)], "VC")
via(-4.45, 0.8, "VC")
track([(-4.45, 0.8), (-4.5, 11.2)], "VC", SIGNAL, IN2)
via(-4.5, 11.2, "VC")
track([(-5.4, 7.275), (-5.4, 10.3), (-3.6, 10.3)], "VC")
track([(-4.5, 11.2), (-4.5, 10.3)], "VC")
track([(-3.4, 1.625), (-5.1, 1.625), (-5.1, 5.725)], "FB")
track([(-10.8, 5.725), (-3.6, 5.725)], "FB")
track([(-3.4, 2.275), (-4.0, 2.275), (-4.0, 3.6), (-1.8, 3.6), (-1.8, 5.725)], "RT")
track([(-3.6, 7.275), (-3.6, 8.725)], "NC")
track([(-10.8, 7.275), (-10.8, 8.725)], "NF")
track([(-9.0, 7.275), (-9.0, 10.3), (-13.5, 10.3), (-13.5, 8.6)], "VOUT")
for x in (-7.2, -1.8):
    track([(x, 7.275), (x, 8.1)], "GND")
    via(x, 8.1, "GND")

# Grounds of the input and output capacitors and of the probe pads: vias into the planes.
for x in (-13.0, -11.8, -9.6, -8.4, 8.4, 9.6, 11.8, 13.0):     # just below the capacitor ground pads
    for y in (-6.2, -7.2):
        via(x, y, "GND")
for _, jp, x, *_ in LOADS:
    track([(x, 13.76), (x, 18.0)], f"OBC_{jp}", POWER)

# Edge, texts.
edge = pcbnew.PCB_SHAPE(board)
edge.SetShape(pcbnew.SHAPE_T_RECT)
edge.SetLayer(pcbnew.Edge_Cuts)
edge.SetStart(abs_pt(0, 0))
edge.SetEnd(abs_pt(BOARD_W, BOARD_H))
edge.SetWidth(pcbnew.FromMM(0.1))
board.Add(edge)


def text(s, x, y, size=1.0, layer=pcbnew.F_SilkS):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(pt(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
    t.SetTextThickness(pcbnew.FromMM(size * 0.15))
    board.Add(t)


text("WICI 3V3 LTC3115-1 test", 4.0, 26.6, 1.2)
for (_, jp, x, *_), label in zip(LOADS, ("30", "+30", "150")):
    text(label, x, 23.0, 1.0)
text("mA", -11.2, 23.0, 1.0)
for x, label in ((14.0, "RUN"), (18.0, "PWM")):
    text(label, x, 17.4, 1.0)
for y, label in ((9.5, "1"), (14.58, "0")):
    text(label, 16.0, y, 1.0)
text("VIN", 22.5, -10.4, 1.0)
text("VOUT", -22.5, -10.4, 1.0)

# Mixed assembly (JLC, also hand soldering after reflow): every SMD pad at least 2.5 mm from every
# through-hole pad, copper edge to edge, as for the v2 board (docs/spec/elektronika.md).
smd_pads = [p for f in board.GetFootprints() for p in f.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
tht_pads = [p for f in board.GetFootprints() for p in f.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
close = sorted({f"{a.GetParentFootprint().GetReference()}-{b.GetParentFootprint().GetReference()}"
                for a in smd_pads for b in tht_pads
                if a.GetEffectiveShape(TOP).Collide(b.GetEffectiveShape(TOP), pcbnew.FromMM(2.5))})
if close:
    raise SystemExit(f"SMD pad closer than 2.5 mm to a THT pad: {close}")

filler = pcbnew.ZONE_FILLER(board)
filler.Fill(board.Zones())
OUT.parent.mkdir(exist_ok=True)
board.Save(str(OUT))

with open(HERE / "bom.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["pozycja", "wartość", "footprint", "LCSC", "MPN", "montaż"])
    for ref, value, foot, lcsc, mpn, jlc in BOM:
        w.writerow([ref, value, foot, lcsc, mpn, "JLC" if jlc else "ręcznie (pw-lab)"])

# JLC assembly files: BOM grouped by LCSC number, placement from the lower-left corner (y up), SMD and THT.
# TSSOP turns 270 degrees for JLC like SOIC on the dev-bench board; check pin 1 in the JLC preview.
# Through-hole footprints have their origin on pin 1, so their CPL position is the body centre.
JLC = HERE / "fabrication"
JLC.mkdir(exist_ok=True)
groups = {}
for ref, value, foot, lcsc, mpn, jlc in BOM:
    if jlc:
        groups.setdefault(lcsc, []).append((ref, value, foot.split(":")[-1]))
with open(JLC / "jlc-bom.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
    for lcsc, items in groups.items():
        w.writerow([items[0][1], ",".join(i[0] for i in items), items[0][2], lcsc])
with open(JLC / "jlc-cpl.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for fp in board.GetFootprints():
        if any(fp.GetReference() == i[0] for items in groups.values() for i in items):
            pos = fp.GetBoundingBox(False).GetCenter() if fp.GetAttributes() & pcbnew.FP_THROUGH_HOLE else fp.GetPosition()
            rot = fp.GetOrientationDegrees() + (270 if fp.GetReference() == "U1" else 0)
            w.writerow([fp.GetReference(), f"{pcbnew.ToMM(pos.x):.3f}", f"{BOARD_H - pcbnew.ToMM(pos.y):.3f}",
                        "Top", f"{rot % 360:.0f}"])
print(f"{OUT}: {len(BOM)} parts, {len(NETS)} nets")
