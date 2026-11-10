# SPDX-License-Identifier: MIT
"""Copper of the v2 board, first draft (not for ordering): rules, planes, hand-made copper and the routing job.

usage (KiCad Python, from tools/):
    route_pcb.py prepare            after make_pcb.py: 4 layers, net classes, rules, keepouts, converter copper,
                                    plane vias; writes the board and checks/routing.dsn for Freerouting
    route_pcb.py import SES         imports a Freerouting session made from exactly that DSN, adds the ground
                                    and 3.3 V planes and fills them

Stack (README, "Ścieżki, szkic"): L1 parts and routing, L2 (In1) unbroken ground, L3 (In2) +3V3 plane with the
two bootstrap traces of the converter as on its test board, L4 routing. Freerouting routes only L1 and L4; GND
and +3V3 reach their planes through the vias placed here, so the router never sees those two nets.
"""
from pathlib import Path
import hashlib
import math
import re
import sys

import pcbnew as k

from make_pcb import OUTLINE, stable as stable_footprints

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / 'cad' / 'plytka-v2.kicad_pcb'
DSN = ROOT / 'checks' / 'routing.dsn'
F, IN1, IN2, B = k.F_Cu, k.In1_Cu, k.In2_Cu, k.B_Cu
CONV_AT = (128.6, 57.0)              # centre of U7, as CONV_AT in make_pcb.py

# Net classes: name -> (track, via diameter, via drill, clearance for the router, nets). Clearance in KiCad is
# 0.15 mm for every class; the high-voltage spacing is a rule in the .kicad_dru (see DRU). Freerouting gets 0.2 mm
# for the high-voltage classes too: with 0.3 mm it cannot leave the 0.5 mm pins of U5 and the 0.65 mm pins of U6
# (draft of 2026-11-10: 47 connections of the 12 V path left open), so DRC lists where the rule is not met.
# Widths: IPC-2152, 35 um outer copper, 1 A at 10 K rise needs about 0.3 mm; 0.6 mm for the 12 V path (the pad
# width of the SOIC MOSFETs) also carries the TVS surge (11 A for 1 ms; Onderdonk gives about 190 A for 1 ms on
# 0.6 x 0.035 mm) and drops 0.25 A by about 2 mV per 10 mm. A 1.0 mm class could not reach the SOIC pins. VSYS carries up to 0.55 A from the cells
# at 4 V (0.5 A at 3.3 V out, 85 %).
HV_POWER = ['12V_IN', 'V12_F', 'V12_MID']
HV_SIGNAL = ['V12_FLT', 'V12_SW', 'Q4_G', 'Q5_D', 'ON_DIV', 'S12_DGATE', 'S12_HGATE', 'S12_CAP', 'S12_SW',
             'S12_DVDT', 'VCTL', 'Q8_G', 'PWR_ENB', 'ON', 'Q5_G', 'Q10_G']
CLASSES = {
    'HV12': (0.6, 0.8, 0.4, 0.2, HV_POWER),          # up to 33 V continuous, 53.3 V TVS clamp, -53.3 V reversed
    'HV': (0.3, 0.6, 0.3, 0.2, HV_SIGNAL),            # same voltages, small currents
    'VSYS': (0.8, 0.8, 0.4, 0.2, ['VSYS', 'BAT_IN', 'BAT_R']),
    'Power': (0.5, 0.6, 0.3, 0.2, ['+5V', '+3V3_RF', 'BZ_P', 'BZ_N', 'BST_SW', 'CONV_VCC']),
    'USB': (0.25, 0.6, 0.3, 0.2, ['USB_DP', 'USB_DN']),
    'Plane': (0.4, 0.6, 0.3, 0.2, ['GND', '+3V3']),   # only plane vias and their stubs
}
DEFAULT = (0.2, 0.6, 0.3, 0.2)
# IPC-2221B table 6-1, 31-100 V: bare outer copper (pads, B2) 0.6 mm; outer copper under the solder mask (tracks,
# tented vias, zone fills, B4) 0.13 mm, taken as 0.3 mm. Inner layers (B1, 0.1 mm) carry no high voltage.
HV_CLEARANCE = 0.6
HV_MASKED = 0.3
PLANE_NETS = ('GND', '+3V3')

# Explicit rules, within the standard JLCPCB capability for 2 and 4 layers (no extra cost): 0.15 mm spacing,
# 0.2 mm track (0.15 mm only where the router necks a track down into a fine-pitch pin; JLC: 0.127 mm on two
# layers, 0.09 mm on four), via 0.6/0.3 mm, 0.5 mm copper to the board edge and the panel holes. The high-voltage rule skips
# pad pairs and the fan-out inside the fine-pitch ICs U5 (0.5 mm) and U6 (0.65 mm): their pins are rated by the
# maker and the pin pitch is smaller than the rule. A condition must stay on one line: kicad-cli drops the whole
# file without a word when one rule does not parse (build.sh checks with a canary rule).
DRU = f'''(version 1)
(rule "v2 copper spacing" (constraint clearance (min 0.15mm)))
(rule "v2 track width" (constraint track_width (min 0.15mm)))
(rule "v2 via diameter" (constraint via_diameter (min 0.6mm)))
(rule "v2 finished hole" (constraint hole_size (min 0.3mm)))
(rule "v2 annular ring" (constraint annular_width (min 0.15mm)))
(rule "v2 copper to edge" (constraint edge_clearance (min 0.5mm)))
(rule "v2 copper to hole" (constraint hole_clearance (min 0.3mm)))
(rule "v2 thermal spokes" (constraint min_resolved_spokes 1))
(rule "v2 high voltage, masked copper" (condition "(A.NetClass == 'HV12' || A.NetClass == 'HV') && A.Type != 'Pad' && B.Type != 'Pad'")
  (layer outer) (constraint clearance (min {HV_MASKED}mm)))
(rule "v2 high voltage, bare pads" (condition "(A.NetClass == 'HV12' || A.NetClass == 'HV') && (A.Type == 'Pad' || B.Type == 'Pad') && !(A.Type == 'Pad' && B.Type == 'Pad') && !(A.intersectsCourtyard('U5') && B.intersectsCourtyard('U5')) && !(A.intersectsCourtyard('U6') && B.intersectsCourtyard('U6'))")
  (layer outer) (constraint clearance (min {HV_CLEARANCE}mm)))
(rule "v2 12 V path" (condition "A.NetClass == 'HV12' && A.Type == 'Track' && !A.intersectsCourtyard('U5')") (constraint track_width (min 0.6mm)))
(rule "v2 VSYS path" (condition "A.NetClass == 'VSYS' && A.Type == 'Track' && !A.intersectsCourtyard('U7') && !A.intersectsCourtyard('C46')")
  (constraint track_width (min 0.6mm)))
(rule "v2 power tracks" (condition "A.NetClass == 'Power' && A.Type == 'Track' && !A.intersectsCourtyard('U7')")
  (constraint track_width (min 0.4mm)))
'''

# Areas kept free of copper on both outer layers, (x, y, radius): the six mounting holes (spacer <= 6 mm on top,
# screw head 5.6 mm below; lessons: no copper within 6.4 mm), 1 mm round the six panel holes (nuts and terminals
# reach through, wires bend at the edge), and on the top layer 10 mm round the preparation button, which is seen
# through the hole in the sticker (r02/obudowa.md).
MOUNTING = [(130.0, 20.0), (190.0, 20.0), (10.0, 100.0), (70.0, 100.0), (130.0, 100.0), (190.0, 100.0)]
PANEL = [(20.0, 88.0), (52.0, 88.0), (84.0, 88.0), (116.0, 88.0), (175.0, 88.0), (175.0, 52.0)]
SERVICE = (141.0, 106.0)


def mm(v):
    return k.FromMM(v)


def pt(x, y):
    return k.VECTOR2I(mm(x), mm(y))


def rel(x, y):
    """Point relative to the centre of U7."""
    return CONV_AT[0] + x, CONV_AT[1] + y


class Copper:
    def __init__(self, board):
        self.b = board

    def net(self, name):
        n = self.b.FindNet(name)
        assert n is not None and n.GetNetCode() > 0, name
        return n

    def track(self, points, name, width, layer=F, locked=True):
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            t = k.PCB_TRACK(self.b)
            t.SetStart(pt(x0, y0))
            t.SetEnd(pt(x1, y1))
            t.SetWidth(mm(width))
            t.SetLayer(layer)
            t.SetNet(self.net(name))
            t.SetLocked(locked)
            self.b.Add(t)

    def via(self, x, y, name, size=0.6, drill=0.3):
        v = k.PCB_VIA(self.b)
        v.SetPosition(pt(x, y))
        v.SetWidth(mm(size))
        v.SetDrill(mm(drill))
        v.SetNet(self.net(name))
        v.SetLocked(True)
        self.b.Add(v)
        return v

    def zone(self, corners, name, layer=F, priority=1, clearance=0.25, full=True, keepout=False, rule_name=''):
        z = k.ZONE(self.b)
        z.SetLayer(layer)
        if keepout:
            z.SetIsRuleArea(True)
            z.SetDoNotAllowTracks(True)
            z.SetDoNotAllowVias(True)
            z.SetDoNotAllowZoneFills(True)
            z.SetDoNotAllowPads(False)
            z.SetDoNotAllowFootprints(False)
            z.SetZoneName(rule_name)
        else:
            z.SetNet(self.net(name))
            z.SetAssignedPriority(priority)
            z.SetLocalClearance(mm(clearance))
            z.SetMinThickness(mm(0.25))
            z.SetPadConnection(k.ZONE_CONNECTION_FULL if full else k.ZONE_CONNECTION_THT_THERMAL)
            z.SetThermalReliefGap(mm(0.3))
            z.SetThermalReliefSpokeWidth(mm(0.5))
            z.SetIslandRemovalMode(k.ISLAND_REMOVAL_MODE_ALWAYS)
        o = z.Outline()
        o.NewOutline()
        for x, y in corners:
            o.Append(mm(x), mm(y))
        self.b.Add(z)
        return z


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def circle(x, y, r, n=32):
    return [(x + r * math.cos(2 * math.pi * i / n), y + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def setup(board, router_clearance):
    """Four copper layers and the net classes. router_clearance=True gives the high-voltage classes their 0.6 mm
    as class clearance for the DSN (Freerouting knows no custom rules); the saved board keeps 0.15 mm and the rule
    in the .kicad_dru, which skips pad pairs (the pins of one part are rated by its maker)."""
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.m_MinClearance = mm(0.15)
    ds.m_TrackMinWidth = mm(0.15)
    ds.m_ViasMinSize = mm(0.6)
    ds.m_MinThroughDrill = mm(0.3)
    ds.m_CopperEdgeClearance = mm(0.5)
    ds.m_HoleClearance = mm(0.3)
    ns = ds.m_NetSettings
    d = ns.GetDefaultNetclass()
    d.SetTrackWidth(mm(DEFAULT[0]))
    d.SetViaDiameter(mm(DEFAULT[1]))
    d.SetViaDrill(mm(DEFAULT[2]))
    d.SetClearance(mm(DEFAULT[3] if router_clearance else 0.15))
    ns.ClearNetclassPatternAssignments()
    for prio, (name, (track, vd, vdr, clear, nets)) in enumerate(CLASSES.items()):
        nc = k.NETCLASS(name)
        nc.SetTrackWidth(mm(track))
        nc.SetViaDiameter(mm(vd))
        nc.SetViaDrill(mm(vdr))
        nc.SetClearance(mm(clear if router_clearance else 0.15))
        nc.SetPriority(prio)
        ns.SetNetclass(name, nc)
        for n in nets:
            assert board.FindNet(n) is not None, n
            ns.SetNetclassPatternAssignment(n, name)
    ns.RecomputeEffectiveNetclasses()
    board.SynchronizeNetsAndNetClasses(True)


def converter(c):
    """Copper of the LTC3115-1 group after figure 17, copied from the test board (przetwornica-3v3/tools/build.py)
    with the positions of the 0805 parts of make_pcb.py. Coordinates relative to U7; pins at x +-2.86, rows
    0.65 mm, pin 1 top left; exposed pad 2.74 x 4.95 mm."""
    def R(*pts):
        return [rel(x, y) for x, y in pts]

    def via(x, y, n, size=0.6, drill=0.3):
        c.via(*rel(x, y), n, size, drill)

    # Power copper on top: switch nodes, input and output copper reaching the outer ends of pins 3, 4, 17, 18.
    c.zone(R(*rect(-7.0, -13.6, -3.15, -1.35)), 'CONV_SW2', priority=3)     # up to the middle of the L2 pads
    c.zone(R(*rect(3.15, -13.6, 7.0, -1.35)), 'CONV_SW1', priority=3)
    c.track(R((-3.4, -0.975), (-7.65, -0.975)), '+3V3', 0.35)      # pins 4 and 17 into the output and input copper:
    c.track(R((3.4, -0.975), (7.65, -0.975)), 'VSYS', 0.35)        # the 0.55 mm strips alone fill too thin
    c.zone(R((-3.15, -1.15), (-7.4, -1.15), (-7.4, -3.1), (-15.9, -3.1), (-15.9, 4.8), (-7.4, 4.8), (-7.4, -0.6),
             (-3.15, -0.6)), '+3V3', priority=4)
    c.zone(R((3.15, -1.15), (7.4, -1.15), (7.4, -3.1), (15.9, -3.1), (15.9, 6.6), (12.3, 6.6), (12.3, -0.6),
             (3.15, -0.6)), 'VSYS', priority=4)
    c.zone(R(*rect(-15.9, -7.4, -7.4, -4.2)), 'GND', priority=2)
    c.zone(R(*rect(7.4, -7.4, 15.9, -4.2)), 'GND', priority=2)
    for x in (-14.7, -12.7, -10.75, -8.6, 8.6, 10.75, 12.7, 14.7):     # grounds of the input and output capacitors
        via(x, -6.7, 'GND')
    for x in (-8.6, -11.75, -14.7):                                     # output copper to the +3V3 plane
        for y in (1.0, 3.6):
            via(x, y, '+3V3')
    for x, y in ((13.3, 4.6), (14.9, 4.6), (14.9, 1.0)):              # input copper to the VSYS routing on L4
        via(x, y, 'VSYS', 0.8, 0.4)
    # Exposed pad: ground pins into it, six thermal vias.
    for y in (-2.925, -0.325, 0.325, 2.925):
        c.track(R((-2.3, y), (-1.2, y)), 'GND', 0.3)
    c.track(R((2.3, -2.925), (1.2, -2.925)), 'GND', 0.3)
    c.track(R((3.4, 2.925), (3.4, 5.0)), 'GND', 0.3)                    # pin 11 to the ground pad of C47
    for x in (-0.75, 0.75):
        for y in (-1.6, 0.0, 1.6):
            via(x, y, 'GND')
    via(4.6, 6.6, 'GND')
    c.track(R((3.55, 5.4), (3.9, 6.2), (4.6, 6.6)), 'GND', 0.4)
    # VCC: pins 14 and 12 under the body to C47.
    c.track(R((2.3, 0.975), (1.75, 0.975), (1.75, 5.2)), 'CONV_VCC', 0.25)
    c.track(R((2.3, 2.275), (1.75, 2.275)), 'CONV_VCC', 0.25)
    # VIN pin 13 to its own 100 nF (C46), then on L4 into the input copper; C46 to ground.
    c.track(R((3.4, 1.625), (4.9, 1.75)), 'VSYS', 0.3)
    c.track(R((5.35, 1.8), (5.35, 3.1)), 'VSYS', 0.4)
    via(5.35, 3.1, 'VSYS')
    c.track(R((5.35, 3.1), (5.35, 4.6), (13.3, 4.6)), 'VSYS', 0.8, B)
    c.track(R((7.25, 1.8), (7.25, 3.1)), 'GND', 0.4)
    via(7.25, 3.1, 'GND')
    # Bootstrap on the inner layer In2, as on the test board; BST2 crosses under the IC between the via rows.
    c.track(R((3.4, -0.325), (5.6, 0.0)), 'CONV_BST1', 0.2)
    via(5.6, 0.0, 'CONV_BST1')
    c.track(R((5.6, 0.0), (5.8, -0.6), (5.8, -3.7)), 'CONV_BST1', 0.3, IN2)
    via(5.8, -3.7, 'CONV_BST1')
    c.track(R((5.8, -3.7), (5.8, -4.9)), 'CONV_BST1', 0.3)
    c.track(R((3.4, 0.325), (4.3, 0.55)), 'CONV_BST2', 0.2)
    via(4.3, 0.55, 'CONV_BST2')
    c.track(R((4.3, 0.55), (3.0, -0.8), (-3.0, -0.8), (-5.8, -1.5), (-5.8, -3.7)), 'CONV_BST2', 0.3, IN2)
    via(-5.8, -3.7, 'CONV_BST2')
    c.track(R((-5.8, -3.7), (-5.8, -4.9)), 'CONV_BST2', 0.3)
    # PWM/SYNC (pin 19) and RUN (pin 2): vias in the switch copper as in figure 17; PWM on L4 to R63, the router
    # takes both on from there.
    c.track(R((3.4, -2.275), (4.3, -2.55)), 'PWM_SYNC', 0.2)
    via(4.3, -2.55, 'PWM_SYNC')
    c.track(R((4.3, -2.55), (8.6, -2.55), (8.6, 0.6)), 'PWM_SYNC', 0.2, B)
    via(8.6, 0.6, 'PWM_SYNC')
    c.track(R((8.6, 0.6), (9.45, 1.3), (9.45, 1.8)), 'PWM_SYNC', 0.2)
    c.track(R((11.35, 1.8), (11.35, 3.1)), 'GND', 0.4)
    via(11.35, 3.1, 'GND')
    c.track(R((-3.4, -2.275), (-4.3, -2.55)), 'RUN', 0.2)
    via(-4.3, -2.55, 'RUN')
    # Exits on L4 to vias outside the group, where the router takes over (it cannot reach into the keepout).
    c.track(R((-4.3, -2.55), (-17.2, -2.55)), 'RUN', 0.2, B)
    via(-17.2, -2.55, 'RUN')
    c.track(R((8.6, -2.55), (17.2, -2.55)), 'PWM_SYNC', 0.2, B)
    via(17.2, -2.55, 'PWM_SYNC')
    c.track(R((14.9, 4.6), (17.4, 4.6)), 'VSYS', 0.8, B)
    via(17.4, 4.6, 'VSYS', 0.8, 0.4)
    # VC (pin 7) on L4 down to the compensation, FB (pin 8) and RT (pin 9) on top; FB bus above the row.
    c.track(R((-3.4, 0.975), (-4.3, 0.975)), 'CONV_VC', 0.2)
    via(-4.3, 0.975, 'CONV_VC')
    c.track(R((-4.3, 0.975), (-5.65, 2.3), (-5.65, 9.6)), 'CONV_VC', 0.2, B)
    via(-5.65, 9.6, 'CONV_VC')
    c.track(R((-5.65, 9.6), (-7.0, 9.6), (-7.0, 8.5)), 'CONV_VC', 0.2)
    c.track(R((-5.65, 9.6), (-5.65, 12.7), (-4.3, 12.7)), 'CONV_VC', 0.2)
    c.track(R((-3.4, 1.625), (-5.1, 1.625), (-5.1, 5.6)), 'CONV_FB', 0.2)
    c.track(R((-15.1, 5.6), (-4.3, 5.6)), 'CONV_FB', 0.2)
    for x in (-15.1, -12.4, -9.7, -7.0, -4.3):
        c.track(R((x, 5.6), (x, 6.7)), 'CONV_FB', 0.2)
    c.track(R((-3.4, 2.275), (-4.0, 2.275), (-4.0, 3.6), (-1.6, 3.6), (-1.6, 6.7)), 'CONV_RT', 0.2)
    c.track(R((-4.3, 8.5), (-4.3, 10.9)), 'CONV_CMP1', 0.2)
    c.track(R((-15.1, 8.5), (-15.1, 10.9)), 'CONV_CMP2', 0.2)
    for x, n in ((-1.6, 'GND'), (-9.7, 'GND'), (-12.4, '+3V3')):
        c.track(R((x, 8.5), (x, 9.6)), n, 0.3)
        via(x, 9.6, n)
    c.track(R((-15.1, 12.7), (-15.1, 13.8)), '+3V3', 0.3)
    via(-15.1, 13.8, '+3V3')


# Power copper of the converter as rectangles (x0, y0, x1, y1, net), relative to U7, 0.25 mm inside the zones.
# Freerouting does not see unfilled zones, and a keepout over the group makes it give up every net with a fixed
# via inside (RUN, PWM_SYNC, VSYS). For the DSN only, each rectangle becomes a wide track of its own net; the
# switch-node rectangles leave out the PWM, RUN and bootstrap vias, which figure 17 puts into that copper, and
# still close it (the router once ran PWM_SYNC on L1 straight across both switch nodes above U7).
EXITS = [(-17.2, -2.55), (17.2, -2.55), (17.4, 4.6)]   # RUN, PWM_SYNC and VSYS leave the group here, on L4
CONV_COPPER = [(-6.75, -13.35, -3.4, -4.3, 'CONV_SW2'), (3.4, -13.35, 6.75, -4.3, 'CONV_SW1'),
               (-6.75, -3.0, -5.1, -1.6, 'CONV_SW2'), (5.1, -3.0, 6.75, -1.6, 'CONV_SW1'),
               (-5.2, -4.3, -3.4, -3.45, 'CONV_SW2'), (3.4, -4.3, 5.2, -3.45, 'CONV_SW1'),
               (-15.65, -2.85, -7.65, 4.55, '+3V3'), (7.65, -2.85, 15.65, -0.85, 'VSYS'),
               (12.55, -0.85, 15.65, 6.35, 'VSYS'), (-15.65, -7.15, -7.65, -4.45, 'GND'),
               (7.65, -7.15, 15.65, -4.45, 'GND')]


def pin_bars(c):
    """The drain pins (5-8) and source pins (1-3) of each SOIC MOSFET joined along their row by a track of pad
    width: the drain-drain path of Q2 and Q3 carries the full 12 V current, and the router reaches a row anywhere."""
    for ref in ('Q2', 'Q3'):
        fp = c.b.FindFootprintByReference(ref)
        for pins in (('1', '2', '3'), ('5', '6', '7', '8')):
            pads = [fp.FindPadByNumber(n) for n in pins]
            xy = sorted((k.ToMM(p.GetPosition().x), k.ToMM(p.GetPosition().y)) for p in pads)
            c.track([xy[0], xy[-1]], pads[0].GetNetname(), 0.6)


def keepouts(c):
    """Copper-free areas."""
    for i, (x, y) in enumerate(MOUNTING):
        for layer in (F, B, IN1, IN2):
            c.zone(circle(x, y, 3.2), None, layer, keepout=True, rule_name=f'otwór {i + 1}')
    for x, y in PANEL:
        for layer in (F, B):
            c.zone(circle(x, y, 11.0), None, layer, keepout=True, rule_name='otwór panelu')
    c.zone(circle(*SERVICE, 10.0), None, F, keepout=True, rule_name='przycisk przygotowania')


def pad_box(p, grow=0.0):
    bb = p.GetBoundingBox()
    return (k.ToMM(bb.GetX()) - grow, k.ToMM(bb.GetY()) - grow, k.ToMM(bb.GetRight()) + grow,
            k.ToMM(bb.GetBottom()) + grow)


def in_box(x, y, b):
    return b[0] <= x <= b[2] and b[1] <= y <= b[3]


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1e-12)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def plane_vias(c):
    """One via per SMD pad of GND and +3V3 into its plane (lessons: each decoupling capacitor has its own via),
    placed just outside the pad, away from the part, clear of every pad, track, via and kept-free area."""
    b = c.b
    hv = set(HV_POWER + HV_SIGNAL)
    pads = list(b.GetPads())
    blocked = []                        # (box, extra clearance) of foreign copper
    for p in pads:
        blocked.append((p, pad_box(p), HV_CLEARANCE if p.GetNetname() in hv else 0.2))
    vias = [(k.ToMM(v.GetPosition().x), k.ToMM(v.GetPosition().y)) for v in b.GetTracks() if isinstance(v, k.PCB_VIA)]
    segs = [(t.GetNetname(), k.ToMM(t.GetStart().x), k.ToMM(t.GetStart().y), k.ToMM(t.GetEnd().x),
             k.ToMM(t.GetEnd().y), k.ToMM(t.GetWidth()) / 2) for t in b.GetTracks() if not isinstance(t, k.PCB_VIA)]
    areas = [(x, y, 3.2) for x, y in MOUNTING] + [(x, y, 11.0) for x, y in PANEL] + [(*SERVICE, 10.0)]
    conv = [rel(x, y) for x, y in ((-16.4, -19.0), (16.4, 14.6))]
    missing = []
    for p in pads:
        name = p.GetNetname()
        if name not in PLANE_NETS or p.GetAttribute() != k.PAD_ATTRIB_SMD:
            continue
        fp = p.GetParentFootprint()
        px, py = k.ToMM(p.GetPosition().x), k.ToMM(p.GetPosition().y)
        if conv[0][0] <= px <= conv[1][0] and conv[0][1] <= py <= conv[1][1]:
            continue                    # the converter group has its own vias
        if fp.GetReference() in ('J4', 'J7'):
            continue                    # shield and mounting pads of the connectors reach the fill directly
        fx, fy = k.ToMM(fp.GetPosition().x), k.ToMM(fp.GetPosition().y)
        x0, y0, x1, y1 = pad_box(p)
        hw, hh = (x1 - x0) / 2, (y1 - y0) / 2
        away = math.atan2(py - fy, px - fx) if (px, py) != (fx, fy) else 0.0
        best = None
        for step in range(16):
            ang = away + (step + 1) // 2 * (1 if step % 2 else -1) * math.pi / 8
            ux, uy = math.cos(ang), math.sin(ang)
            reach = min(hw / abs(ux) if abs(ux) > 1e-6 else 1e9, hh / abs(uy) if abs(uy) > 1e-6 else 1e9)
            for extra in (0.55, 0.8, 1.1, 1.5):
                vx, vy = px + ux * (reach + extra), py + uy * (reach + extra)
                if not (1.0 < vx < 199.0 and 1.0 < vy < 119.0):
                    continue
                if any(math.hypot(vx - ax, vy - ay) < r + 0.5 for ax, ay, r in areas):
                    continue
                if any(math.hypot(vx - qx, vy - qy) < 0.85 for qx, qy in vias):
                    continue
                ok = True
                for q, box, gap in blocked:
                    if q.GetNetname() == name and q is p:
                        continue
                    g = gap if q.GetNetname() != name else 0.1
                    if in_box(vx, vy, (box[0] - 0.3 - g, box[1] - 0.3 - g, box[2] + 0.3 + g, box[3] + 0.3 + g)):
                        ok = False
                        break
                    # the stub from the pad centre to the via must not cross a foreign pad
                    if q.GetNetname() != name and any(
                            in_box(px + (vx - px) * t, py + (vy - py) * t, (box[0] - 0.3 - g, box[1] - 0.3 - g,
                                                                             box[2] + 0.3 + g, box[3] + 0.3 + g))
                            for t in (0.4, 0.6, 0.8)):
                        ok = False
                        break
                if not ok:
                    continue
                if any(n != name and (seg_dist(vx, vy, ax, ay, bx, by) < 0.3 + w + 0.2
                                      or seg_dist((px + vx) / 2, (py + vy) / 2, ax, ay, bx, by) < 0.2 + w + 0.2)
                       for n, ax, ay, bx, by, w in segs):
                    continue
                best = (vx, vy)
                break
            if best:
                break
        if best is None:
            missing.append(f'{fp.GetReference()}.{p.GetNumber()}')
            continue
        c.track([(px, py), best], name, min(0.4, 2 * hw, 2 * hh))
        c.via(*best, name)
        vias.append(best)
        segs.append((name, px, py, *best, 0.2))
    return missing


def planes(c):
    """In1 ground, In2 +3V3, both outer layers ground fill. Plane edges keep 0.5 mm from the board edge."""
    outline = [(0, 0), (200, 0), (200, 125), (0, 125)]     # clipped by the board edge, tongue included
    c.zone(outline, 'GND', IN1, priority=0, clearance=0.3, full=False)
    c.zone(outline, '+3V3', IN2, priority=0, clearance=0.3, full=False)
    for layer in (F, B):
        c.zone(outline, 'GND', layer, priority=0, clearance=0.3, full=False)


def stable(text):
    """Board text that does not depend on the random UUIDs KiCad gives new items: tracks, vias and zones sorted by
    their content (UUIDs aside), then footprints sorted and all UUIDs renumbered as in make_pcb.py."""
    starts = [m.start() for m in re.finditer(r'^\t\(', text, re.M)]
    ends = starts[1:] + [text.rindex(')')]
    blocks = [text[a:b] for a, b in zip(starts, ends)]
    kinds = ('\t(segment', '\t(via', '\t(arc', '\t(zone')
    slots = [i for i, b in enumerate(blocks) if b.startswith(kinds)]
    key = lambda b: re.sub(r'\(uuid "[0-9a-f-]+"\)', '', b)
    for i, b in zip(slots, sorted((blocks[i] for i in slots), key=key)):
        blocks[i] = b
    return stable_footprints(text[:starts[0]] + ''.join(blocks) + text[ends[-1]:])


def form_end(text, start):
    """Index after the balanced s-expression that opens at text[start] == '('."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return i + 1
    raise ValueError('unbalanced DSN')


def drop_inner_layers(text):
    """Remove every DSN item on In1.Cu or In2.Cu: the layer definitions themselves and the shape, keepout or wire
    that holds a path, circle, polygon or rect on those layers."""
    while True:
        m = re.search(r'\((\w+) "?In[12]\.Cu', text)
        if not m:
            return text
        start = m.start()
        if m.group(1) != 'layer':           # the enclosing item: walk back to its opening bracket
            depth = 0
            for i in range(m.start() - 1, -1, -1):
                if text[i] == ')':
                    depth += 1
                elif text[i] == '(':
                    if depth == 0:
                        start = i
                        break
                    depth -= 1
        end = form_end(text, start)
        line_start = text.rfind('\n', 0, start)
        if text[line_start + 1:start].strip() == '' and text[end:end + 1] == '\n':
            start, end = line_start, end    # the whole line
        text = text[:start] + text[end:]


def export_dsn():
    """Specctra DSN for Freerouting: the router uses only L1 and L4; the plane nets stay in the network and
    route.sh tells Freerouting to skip their class (Plane)."""
    board = k.LoadBoard(str(BOARD))     # a copy: the stand-in tracks never reach the saved board
    setup(board, router_clearance=True)
    for x0, y0, x1, y1, n in CONV_COPPER:
        w = min(x1 - x0, y1 - y0)
        a, b = ((x0 + w / 2, (y0 + y1) / 2), (x1 - w / 2, (y0 + y1) / 2)) if x1 - x0 >= y1 - y0 else \
            (((x0 + x1) / 2, y0 + w / 2), ((x0 + x1) / 2, y1 - w / 2))
        if a == b:
            b = (b[0] + 0.001, b[1])
        Copper(board).track([rel(*a), rel(*b)], n, w)
    # Freerouting keeps only its 0.2 mm class clearance to the outline; a 0.5 mm band inside every straight edge
    # gives it the 0.5 mm of the rules (it ran 0.27 mm from the EN3 notch before).
    pts = [(x, y) for x, y, _ in OUTLINE]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        length = math.hypot(x1 - x0, y1 - y0)
        nx, ny = -(y1 - y0) / length * 0.5, (x1 - x0) / length * 0.5
        Copper(board).zone([(x0, y0), (x1, y1), (x1 + nx, y1 + ny), (x0 + nx, y0 + ny)], None, F, keepout=True,
                           rule_name='krawędź')
        Copper(board).zone([(x0, y0), (x1, y1), (x1 + nx, y1 + ny), (x0 + nx, y0 + ny)], None, B, keepout=True,
                           rule_name='krawędź')
    DSN.parent.mkdir(exist_ok=True)
    if not k.ExportSpecctraDSN(board, str(DSN)):
        raise RuntimeError('DSN export failed')
    text = DSN.read_text()
    # Freerouting reads the inner layers as signal layers (it knows no plane without a filled zone) and a wire
    # keepout there also blocks its vias, so the job leaves them out: the router sees two layers, and the vias it
    # makes come back as through vias that join the planes.
    text = drop_inner_layers(text)
    text = re.sub(r'(\(layer B\.Cu\s*\(type signal\)\s*\(property\s*\(index )3\)', r'\g<1>1)', text)
    text = text.replace(str(ROOT) + '/', '')
    # KiCad writes the zones (planes) in an order that changes from run to run; sort them, so the same placement
    # always gives the same DSN and build.sh can tell whether the kept session belongs to it.
    planes, first = [], None
    while (i := text.find('\n    (plane ')) >= 0:
        end = form_end(text, i + 5)
        planes.append(text[i:end])
        first = i if first is None else first
        text = text[:i] + text[end:]
    if planes:
        text = text[:first] + ''.join(sorted(planes)) + text[first:]
    DSN.write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


def prepare():
    board = k.LoadBoard(str(BOARD))
    if any(True for _ in board.GetTracks()):
        raise SystemExit('board already has copper; run make_pcb.py first')
    setup(board, router_clearance=False)
    c = Copper(board)
    converter(c)
    pin_bars(c)
    keepouts(c)
    missing = plane_vias(c)
    board.Save(str(BOARD))
    BOARD.write_text(stable(BOARD.read_text()))     # fixed UUIDs, so the DSN lists the zones in the same order
    (ROOT / 'cad' / 'plytka-v2.kicad_dru').write_text(DRU)
    digest = export_dsn()
    print(f'prepared: {len(board.GetTracks())} hand-made tracks and vias, DSN sha256 {digest[:12]}')
    if missing:
        print('no room for a plane via at: ' + ' '.join(missing))


def import_session(ses):
    board = k.LoadBoard(str(BOARD))
    if not k.ImportSpecctraSES(board, str(ses)):
        raise SystemExit('Specctra session import failed')
    # The job had two layers, so KiCad reads the router vias as blind/buried between layer indexes 0 and 1:
    # make them through vias again.
    for v in board.GetTracks():
        if isinstance(v, k.PCB_VIA) and not v.IsLocked():
            v.SetViaType(k.VIATYPE_THROUGH)
            v.SetLayerPair(F, B)
    # Router vias that join copper on one layer only (Freerouting leaves a few after optimising) go away;
    # plane vias stay, they connect to In1 or In2.
    tracks = [t for t in board.GetTracks() if not isinstance(t, k.PCB_VIA)]
    pads = list(board.GetPads())
    for v in [t for t in board.GetTracks() if isinstance(t, k.PCB_VIA) and not t.IsLocked()]:
        if v.GetNetname() in PLANE_NETS:
            continue
        p = v.GetPosition()
        layers = {t.GetLayer() for t in tracks if t.GetNetCode() == v.GetNetCode() and (t.GetStart() == p or t.GetEnd() == p)}
        layers |= {F} if any(pd.GetNetCode() == v.GetNetCode() and pd.HitTest(p) for pd in pads) else set()
        if len(layers) < 2:
            board.Delete(v)
    # Exit vias of the converter group that the router did not use (it joined the net elsewhere) go away with
    # their stub on L4.
    for x, y in EXITS:
        p = k.VECTOR2I(mm(CONV_AT[0] + x), mm(CONV_AT[1] + y))
        v = next(t for t in board.GetTracks() if isinstance(t, k.PCB_VIA) and t.GetPosition() == p)
        touching = [t for t in board.GetTracks() if not isinstance(t, k.PCB_VIA) and p in (t.GetStart(), t.GetEnd())]
        if all(t.IsLocked() for t in touching):
            for t in touching + [v]:
                board.Delete(t)
    c = Copper(board)
    planes(c)
    setup(board, router_clearance=False)
    k.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()
    board.Save(str(BOARD))
    BOARD.write_text(stable(BOARD.read_text()))
    print('session imported, planes filled')


if __name__ == '__main__':
    if sys.argv[1:2] == ['prepare']:
        prepare()
    elif sys.argv[1:2] == ['planes']:
        board = k.LoadBoard(str(BOARD))
        planes(Copper(board))
        setup(board, router_clearance=False)
        k.ZONE_FILLER(board).Fill(board.Zones())
        board.Save(str(BOARD))
        BOARD.write_text(stable(BOARD.read_text()))
        print('no routing session: planes only')
    elif sys.argv[1:2] == ['import']:
        import_session(sys.argv[2])
    else:
        raise SystemExit(__doc__)
