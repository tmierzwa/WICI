# SPDX-License-Identifier: MIT
"""Copper of the v2 board: rules, planes, hand-made copper and the routing jobs for Freerouting.

usage (KiCad Python, from tools/):
    route_pcb.py prepare            after make_pcb.py: 4 layers, net classes, rules, keepouts, hand-made copper,
                                    plane vias; writes the board and the job of stage 1, checks/routing.dsn
    route_pcb.py stage N SES        takes the session of stage N-1 into the board and writes the job of stage N,
                                    checks/routing-N.dsn; says "open nets: none" and writes no job when all is joined
    route_pcb.py finish             after the last stage: removes unused hand-made stubs, adds the ground and
                                    3.3 V planes and fills them
    route_pcb.py planes             no routing: planes only

Stack (README, "Ścieżki"): L1 parts and routing, L2 (In1) unbroken ground, L3 (In2) +3V3 plane with the
two bootstrap traces of the converter as on its test board, L4 routing. Freerouting routes only L1 and L4; GND
and +3V3 reach their planes through the vias placed here, so the router never sees those two nets.
"""
from pathlib import Path
import hashlib
import json
import math
import re
import sys

import pcbnew as k

from make_pcb import AT_CONNECTOR, OUTLINE, SWITCH, SWITCH_AT, SWITCH_TURN, switch_xy, stable as stable_footprints

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / 'cad' / 'plytka-v2.kicad_pcb'
DSN = ROOT / 'checks' / 'routing.dsn'


def dsn_of(stage):
    return DSN if stage == 1 else ROOT / 'checks' / f'routing-{stage}.dsn'
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
    'HV12': (0.6, 0.8, 0.4, 0.31, HV_POWER),          # up to 33 V continuous, 53.3 V TVS clamp, -53.3 V reversed
    'HV': (0.3, 0.6, 0.3, 0.31, HV_SIGNAL),            # same voltages, small currents
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
# For the router only (export_dsn): areas whose pads grow by HV_GROW on each side, (x0, y0, x1, y1).
HV_GROW = 0.31
HV_AREAS = [(74, 97, 100, 120), (108, 98, 132, 120), (149, 92, 189, 120), (133, 20, 173, 58)]

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
(rule "v2 VSYS path" (condition "A.NetClass == 'VSYS' && A.Type == 'Track' && !A.intersectsCourtyard('U7') && !A.intersectsCourtyard('C46') && !A.intersectsCourtyard('U5')")
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


ANCHORS = ROOT / 'checks' / 'routing-anchors.json'


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

    def anchor(self, x, y, name, d):
        """A point where the router may join hand-made copper: export_dsn() puts a one-pad part there."""
        self.anchors = getattr(self, 'anchors', [])
        if not any(math.hypot(x - ax, y - ay) < 0.01 for ax, ay, _, _ in self.anchors):
            self.anchors.append((round(x, 4), round(y, 4), name, d))

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


def setup(board, router_clearance, later=()):
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
    if later:                           # stage 1 of the router: these nets wait in a class that route.sh skips
        nc = k.NETCLASS('Later')
        nc.SetTrackWidth(mm(DEFAULT[0]))
        nc.SetViaDiameter(mm(DEFAULT[1]))
        nc.SetViaDrill(mm(DEFAULT[2]))
        nc.SetClearance(mm(DEFAULT[3]))
        nc.SetPriority(len(CLASSES))
        ns.SetNetclass('Later', nc)
        hv = k.NETCLASS('LaterHV')      # the same for high-voltage nets: new tracks keep the 0.31 mm from them
        hv.SetTrackWidth(mm(DEFAULT[0]))
        hv.SetViaDiameter(mm(DEFAULT[1]))
        hv.SetViaDrill(mm(DEFAULT[2]))
        hv.SetClearance(mm(CLASSES['HV'][3]))
        hv.SetPriority(len(CLASSES) + 1)
        ns.SetNetclass('LaterHV', hv)
        for n in sorted(later):
            ns.SetNetclassPatternAssignment(n, 'LaterHV' if n in HV_POWER + HV_SIGNAL else 'Later')
    ns.RecomputeEffectiveNetclasses()
    board.SynchronizeNetsAndNetClasses(True)


def first_stage_nets(board):
    """Nets of the first router stage: every net of a power class and every net with a pad in the areas of the
    12 V parts (HV_AREAS). Freerouting stops for good after ten passes without a better score, and on the whole
    board at once that happened with about forty connections open; the two halves each come to an end."""
    nets = {n for name, v in CLASSES.items() if name != 'Plane' for n in v[4]}
    for p in board.GetPads():
        x, y = k.ToMM(p.GetPosition().x), k.ToMM(p.GetPosition().y)
        if p.GetNetname() and any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in HV_AREAS):
            nets.add(p.GetNetname())
    return nets - set(PLANE_NETS)


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
    # PWM leaves to the left as well (the DevKitC is there): on L4 under the inductor side of the IC, between the
    # bootstrap vias and the ground vias of the capacitors.
    c.track(R((4.3, -2.55), (2.25, -4.6), (-17.2, -4.6)), 'PWM_SYNC', 0.2, B)
    via(-17.2, -4.6, 'PWM_SYNC')
    c.track(R((14.9, 1.0), (14.9, 4.6), (13.3, 4.6)), 'VSYS', 0.8, B)   # the three input vias joined on L4 too
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
CONV_COPPER = [(-6.75, -13.35, -3.4, -4.3, 'CONV_SW2'), (3.4, -13.35, 6.75, -4.3, 'CONV_SW1'),
               (-6.75, -3.0, -5.1, -1.6, 'CONV_SW2'), (5.1, -3.0, 6.75, -1.6, 'CONV_SW1'),
               (-5.2, -4.3, -3.4, -3.45, 'CONV_SW2'), (3.4, -4.3, 5.2, -3.45, 'CONV_SW1'),
               (-15.65, -2.85, -7.65, 4.55, '+3V3'), (7.65, -2.85, 15.65, -0.85, 'VSYS'),
               (12.55, -0.85, 15.65, 6.35, 'VSYS'), (-15.65, -7.15, -7.65, -4.45, 'GND'),
               (7.65, -7.15, 15.65, -4.45, 'GND')]


# Hand-made power copper outside the converter, absolute (x0, y0, x1, y1, net, layer): filled zones on the board,
# wide stand-in tracks in the DSN (as CONV_COPPER). Filled by switch() and power_input().
SLABS = []


def slab(c, x0, y0, x1, y1, net, layer=F):
    c.zone(rect(x0, y0, x1, y1), net, layer, priority=3 + len(SLABS), clearance=0.3)
    SLABS.append((x0, y0, x1, y1, net, layer))


def switch(c):
    """Copper of the 12 V switch (LM74800 U5, Q2, Q3) by hand; coordinates relative to the centre of U5 as SWITCH
    in make_pcb.py. U5 pins: left column 1 DGATE, 2 A, 3 VSNS, 4 SW, 5 OV, 6 EN from the top; right column 12 VS,
    11 CAP, 10 C, 9 OUT, 8 HGATE, 7 GND from the top. Q2 left: sources (fused 12 V) in its left column, gate at
    the bottom, drains towards U5; Q3 right, turned: drains towards U5, sources (VSYS) right, gate at the top.
    The common drain joins the two drain columns on L4 through three vias each. The gate tracks pass the end of
    the drain column and run under the body; the two sense tracks A and OUT cross on L4. Every first segment at
    a U5 pin stays inside the U5 courtyard, where the pin pitch sets the spacing."""
    def P(*pts):
        return [switch_xy(x, y) for x, y in pts]

    def via(x, y, n, size=0.6, drill=0.3):
        c.via(*switch_xy(x, y), n, size, drill)

    def area(x0, y0, x1, y1, net, layer=F):
        (ax, ay), (bx, by) = switch_xy(x0, y0), switch_xy(x1, y1)
        slab(c, min(ax, bx), min(ay, by), max(ax, bx), max(ay, by), net, layer)

    px, e = 1.4375, 1.95                                            # pin columns of U5; bends just past the pad ends
    # Fused 12 V: the three source pins of Q2 in one copper area, two vias to the feed on L4.
    area(-14.6, -2.4, -10.1, 0.95, 'V12_F')
    for y in (-1.7, 0.4):
        via(-13.9, y, 'V12_F', 0.8, 0.4)
    # Common drain: a bar over each drain column, three vias beside it, one area on L4.
    for sx in (-1, 1):
        c.track(P((sx * 6.125, -1.905), (sx * 6.125, 1.905)), 'V12_MID', 1.0)
        for y in ((-1.95, 0.7, 1.9) if sx < 0 else (-1.9, -0.7, 1.95)):
            c.track(P((sx * 6.125, y), (sx * 7.6, y)), 'V12_MID', 0.6)
            via(sx * 7.6, y, 'V12_MID', 0.8, 0.4)
    area(-8.3, -2.9, 8.3, 2.9, 'V12_MID', B)
    area(4.7, 1.5, 6.3, 9.1, 'V12_MID', B)       # finger to C30 and R46, beside the ground via of C30
    area(3.0, 7.7, 6.3, 9.1, 'V12_MID', B)
    # VSYS: the three source pins of Q3 in one area, two vias to the trunk on L4.
    area(10.1, -0.95, 14.6, 2.3, 'VSYS')
    for y in (-0.3, 1.7):
        via(13.9, y, 'VSYS', 0.8, 0.4)
    # DGATE: pin 1, over the top end of the Q2 drain column, under the body to the gate at the bottom left.
    c.track(P((-px, -1.25), (-e, -1.25)), 'S12_DGATE', 0.2)
    c.track(P((-e, -1.25), (-2.7, -2.0)), 'S12_DGATE', 0.2)
    c.track(P((-2.7, -2.0), (-2.7, -3.0), (-8.55, -3.0), (-8.55, 1.905), (-10.6, 1.905)), 'S12_DGATE', 0.3)
    # A (pin 2): via beside U5, on L4 under Q2 to the source copper.
    c.track(P((-px, -0.75), (-e, -0.75)), 'V12_F', 0.15)
    c.track(P((-e, -0.75), (-4.0, -1.25)), 'V12_F', 0.15)
    via(-4.0, -1.25, 'V12_F')
    c.track(P((-4.0, -1.25), (-4.6, -0.65), (-13.4, -0.65)), 'V12_F', 0.6, B)
    via(-13.4, -0.65, 'V12_F')
    # VSNS (pin 3) and C (pin 10) straight into the drain pads.
    c.track(P((-px, -0.25), (-5.6, -0.4)), 'V12_MID', 0.15)
    c.track(P((px, -0.25), (5.6, -0.4)), 'V12_MID', 0.15)
    # SW (pin 4) to the bottom pad of R30, OV (pin 5) to the top pads of R30 and R31, EN (pin 6) to a via.
    c.track(P((-px, 0.25), (-3.0, 0.25), (-3.0, 5.5125), (-1.5, 5.5125)), 'S12_SW', 0.2)
    c.track(P((-px, 0.75), (-e, 0.75)), 'S12_OV', 0.15)
    c.track(P((-e, 0.75), (-2.45, 1.3)), 'S12_OV', 0.15)
    c.track(P((-2.45, 1.3), (-2.45, 3.0), (-1.9, 3.5), (-1.5, 3.6875), (1.1, 3.6875)), 'S12_OV', 0.2)
    c.track(P((-px, 1.25), (-px, 2.45)), 'S12_EN', 0.2)
    via(-px, 2.45, 'S12_EN')
    c.track(P((-px, 2.45), (-px, 4.3)), 'S12_EN', 0.2, B)           # out of the common-drain area; router goes on
    # VS (pin 12) to C31 and through a via to the common drain; CAP (pin 11) to C31.
    c.track(P((px, -1.25), (0.6, -2.9)), 'V12_MID', 0.2)
    c.track(P((0.25, -3.4), (0.25, -2.25)), 'V12_MID', 0.6)
    via(0.25, -2.25, 'V12_MID')
    c.track(P((px, -0.75), (e, -0.75)), 'S12_CAP', 0.15)
    c.track(P((e, -0.75), (2.7, -2.0)), 'S12_CAP', 0.15)
    c.track(P((2.7, -2.0), (2.5, -2.9), (2.15, -3.4)), 'S12_CAP', 0.3)
    # OUT (pin 9): via beside U5, on L4 under Q3 to the VSYS copper.
    c.track(P((px, 0.25), (e, 0.25)), 'VSYS', 0.15)
    c.track(P((e, 0.25), (4.0, 0.75)), 'VSYS', 0.15)
    via(4.0, 0.75, 'VSYS')
    c.track(P((4.0, 0.75), (12.9, 0.75)), 'VSYS', 0.6, B)
    via(12.9, 0.75, 'VSYS')
    # HGATE (pin 8): past the bottom end of the Q3 drain column, under the body to the gate at the top right;
    # tap to R32, then R32-C32 (dV/dt) and the grounds.
    c.track(P((px, 0.75), (e, 0.75)), 'S12_HGATE', 0.15)
    c.track(P((e, 0.75), (2.7, 1.5)), 'S12_HGATE', 0.15)
    c.track(P((2.7, 1.5), (2.7, 3.0), (8.55, 3.0), (8.55, -1.905), (10.6, -1.905)), 'S12_HGATE', 0.3)
    c.track(P((6.1375, 3.0), (6.1375, 5.2)), 'S12_HGATE', 0.3)
    c.track(P((7.9625, 5.2), (10.15, 5.2)), 'S12_DVDT', 0.3)
    c.track(P((px, 1.25), (px, 2.5)), 'GND', 0.2)
    via(px, 2.5, 'GND')
    for (x0, y0), (x1, y1) in (((1.1, 5.5125), (1.1, 6.9)), ((3.7, 5.15), (3.7, 3.95)), ((12.05, 5.2), (13.4, 5.2))):
        c.track(P((x0, y0), (x1, y1)), 'GND', 0.4)
        via(x1, y1, 'GND')
    c.track(P((3.7, 7.05), (3.7, 8.4)), 'V12_MID', 0.6)              # VS side of C30 to the common drain on L4
    via(3.7, 8.4, 'V12_MID')
    # Supply filter of the button controller: R46 from the same via, C35 and D10 behind it.
    c.track(P((3.7, 8.4), (3.7, 11.5)), 'V12_MID', 0.6)
    c.track(P((9.6225, 11.5), (11.95, 10.6)), 'V12_FLT', 0.3)
    c.track(P((9.6225, 11.5), (11.95, 13.5)), 'V12_FLT', 0.3)
    for (x0, y0), (x1, y1) in (((13.85, 10.6), (15.3, 10.6)), ((15.25, 13.5), (15.25, 12.0))):
        c.track(P((x0, y0), (x1, y1)), 'GND', 0.4)
        via(x1, y1, 'GND')


def vsys_trunk(c):
    """VSYS on L4, 1.0 mm: from the source vias of Q3 past the preparation button to the bulk capacitor C50, then
    up to the input copper of the converter (its L4 track at y + 4.6). The cells join at C50: from D7 on top
    between the clips of F1 (the fuse is on the other side), then on L4 under the OK hole and past the spacer of H5."""
    c50 = c.b.FindFootprintByReference('C50').FindPadByNumber('1').GetPosition()
    cx, cy = k.ToMM(c50.x), k.ToMM(c50.y)
    assert (round(cx, 2), round(cy, 2)) == (133.65, 84.0), (cx, cy)
    v0, v1 = switch_xy(13.9, -0.3), switch_xy(13.9, 1.7)
    c.track([v0, v1, (151.5, 104.7), (151.5, 101.0), (146.5, 94.4), (137.5, 94.4), (cx, 90.5), (cx, cy)], 'VSYS', 1.0, B)
    c.track([(cx, cy), (136.5, 81.2), (136.5, CONV_AT[1] + 4.6)], 'VSYS', 1.0, B)
    d7 = c.b.FindFootprintByReference('D7').FindPadByNumber('1').GetPosition()
    c.track([(k.ToMM(d7.x), k.ToMM(d7.y)), (74.2, 103.0), (99.5, 103.0)], 'VSYS', 0.8)
    c.via(99.5, 103.0, 'VSYS', 0.8, 0.4)
    c.track([(99.5, 103.0), (110.0, 103.0), (118.5, 100.2), (124.5, 98.2), (128.6, 93.6), (cx, 88.5), (cx, cy)],
            'VSYS', 0.8, B)


def power_input(c):
    """12 V from J2 to the fuse on L4, the TVS D4 between the fuse output and ground (three vias), the feed."""
    j2 = c.b.FindFootprintByReference('J2').FindPadByNumber('1').GetPosition()
    assert c.b.FindFootprintByReference('J2').FindPadByNumber('1').GetNetname() == '12V_IN'
    c.track([(k.ToMM(j2.x), k.ToMM(j2.y)), (84.75, 114.47), (80.2, 114.47), (77.1, 111.4), (77.1, 100.5)], '12V_IN', 1.0, B)
    c.track([(88.35, 108.4), (90.4, 106.1), (94.9, 105.5)], 'V12_F', 1.0)
    # Fused 12 V on L4, 1.2 mm: both clips of F1.2, through the corridor above the EN3 notch, under the
    # preparation button and the SMA socket to the sources of Q2.
    v0, v1 = switch_xy(-13.9, 0.4), switch_xy(-13.9, -1.7)
    c.track([(94.9, 100.5), (94.9, 105.5), (110.5, 105.5), (118.0, 113.0), (v0[0], 113.0), v0, v1], 'V12_F', 1.2, B)
    for x, y in ((82.1, 108.4), (83.2, 110.3), (84.9, 110.3)):
        c.track([(84.05, 108.4) if x < 83 else (x, 109.2), (x, y)], 'GND', 0.6)
        c.via(x, y, 'GND')


def via_fits(c, x, y, net, r=0.3):
    """True when a via of radius r at x, y keeps 0.62 mm from every foreign pad when one of the two nets is a
    high-voltage net (0.22 mm otherwise), 0.35 mm from foreign tracks and vias on any layer (it goes through the
    board) and stays out of the kept-free areas."""
    hv = set(HV_POWER + HV_SIGNAL)
    if any(math.hypot(x - ax, y - ay) < ar + r + 0.3 for ax, ay, ar in
           [(mx, my, 3.2) for mx, my in MOUNTING] + [(mx, my, 11.0) for mx, my in PANEL] + [(*SERVICE, 10.0)]):
        return False
    for p in c.b.GetPads():
        if p.GetNetname() != net:
            x0, y0, x1, y1 = pad_box(p)
            gap = 0.62 if net in hv or p.GetNetname() in hv else 0.22
            if math.hypot(max(x0 - x, x - x1, 0.0), max(y0 - y, y - y1, 0.0)) < r + gap:
                return False
    for t in c.b.GetTracks():
        if isinstance(t, k.PCB_VIA):
            if math.hypot(x - k.ToMM(t.GetPosition().x), y - k.ToMM(t.GetPosition().y)) < r + 0.3 + 0.35 and \
                    (t.GetNetname() != net or math.hypot(x - k.ToMM(t.GetPosition().x), y - k.ToMM(t.GetPosition().y)) > 0.01):
                return False
        elif t.GetNetname() != net and seg_dist(x, y, k.ToMM(t.GetStart().x), k.ToMM(t.GetStart().y), k.ToMM(t.GetEnd().x),
                                                k.ToMM(t.GetEnd().y)) < r + k.ToMM(t.GetWidth()) / 2 + 0.35:
            return False
    return True


def narrow_pins(c):
    """Fixed tracks out of pins that a 0.5 mm power track cannot enter with the spacing of the router: the three
    5 V pins of the display connector J7 (0.5 mm pitch, pads 0.3 mm) leave as 0.4 mm tracks into one bar, pin 5
    of U2 as a 0.5 mm track. Each ends in a via: Freerouting joins a fixed track only at a via or a pad."""
    def at(ref, pad):
        f = c.b.FindFootprintByReference(ref)
        assert f.FindPadByNumber(pad).GetNetname() == '+5V', (ref, pad)
        p = f.FindPadByNumber(pad).GetPosition()
        return k.ToMM(p.x), k.ToMM(p.y)

    pins = [at('J7', n) for n in ('6', '7', '8')]
    for x, y in pins:
        c.track([(x, y), (x, y + 1.3)], '+5V', 0.4)
    y = pins[0][1] + 1.3
    c.track([(pins[0][0], y), (pins[2][0], y)], '+5V', 0.5)
    c.track([(pins[1][0], y), (pins[1][0], y + 1.0)], '+5V', 0.5)
    assert via_fits(c, pins[1][0], y + 1.0, '+5V')
    c.via(pins[1][0], y + 1.0, '+5V')
    x, y = at('U2', '5')
    side = 1 if x > k.ToMM(c.b.FindFootprintByReference('U2').GetPosition().x) else -1
    c.track([(x, y), (x + side * 2.0, y)], '+5V', 0.5)
    if via_fits(c, x + side * 2.0, y, '+5V'):
        c.via(x + side * 2.0, y, '+5V')
    c.anchor(x + side * 2.0, y, '+5V', 0.5)


FEED = [(110.5, 105.5), (118.0, 113.0), (150.0, 113.0)]     # the fused 12 V on L4 under the UV divider block


def feed_taps(c, ends):
    """The small 12 V loads of the UV divider block (Q4, R33, D5, D13) each get a via of their own and a 0.6 mm
    track on L4 straight to the fused 12 V feed below them: the router cannot branch off a fixed track."""
    def nearest(x, y):
        best = None
        for (ax, ay), (bx, by) in zip(FEED, FEED[1:]):
            t = max(0.0, min(1.0, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)))
            q = (ax + t * (bx - ax), ay + t * (by - ay))
            if best is None or math.hypot(x - q[0], y - q[1]) < math.hypot(x - best[0], y - best[1]):
                best = q
        return best

    def has_via(x, y):
        return any(isinstance(t, k.PCB_VIA) and t.GetNetname() == 'V12_F' and
                   math.hypot(k.ToMM(t.GetPosition().x) - x, k.ToMM(t.GetPosition().y) - y) < 0.01 for t in c.b.GetTracks())

    for ref, pad in (('Q4', '2'), ('R33', '1'), ('D5', '1'), ('D13', '2')):
        p = c.b.FindFootprintByReference(ref).FindPadByNumber(pad)
        assert p.GetNetname() == 'V12_F', (ref, pad)
        px, py = ends[(ref, pad)][:2] if (ref, pad) in ends else (k.ToMM(p.GetPosition().x), k.ToMM(p.GetPosition().y))
        if not has_via(px, py):
            spots = sorted(((px + d * math.cos(a * math.pi / 8), py + d * math.sin(a * math.pi / 8))
                            for d in (1.4, 1.7, 2.0, 2.4, 2.8) for a in range(16)),
                           key=lambda q: math.hypot(q[0] - nearest(*q)[0], q[1] - nearest(*q)[1]) + math.hypot(q[0] - px, q[1] - py))
            for vx, vy in spots:
                if via_fits(c, vx, vy, 'V12_F', 0.4) and all(
                        via_fits(c, px + (vx - px) * t, py + (vy - py) * t, 'V12_F', 0.3) for t in (0.25, 0.5, 0.75)):
                    break
            else:
                raise SystemExit(f'no room for the 12 V via of {ref}')
            c.track([(px, py), (vx, vy)], 'V12_F', 0.6)
            c.via(vx, vy, 'V12_F', 0.8, 0.4)
            px, py = vx, vy
        c.track([(px, py), nearest(px, py)], 'V12_F', 0.6, B)


def escapes(c):
    """Short fixed tracks out of the pads of the fine-pitch parts on the 12 V side, so that everything after them
    keeps the high-voltage spacing. SOT-23 with a high-voltage pad: pads 1 and 2 are 0.35 mm apart, so each track
    leaves along the pad, shifted away from the neighbour until it is 0.62 mm from it (a 0.6 mm track of the
    12 V class overhangs its pad on the far side), and ends 0.7 mm beyond the pad. U6 (0.65 mm pitch): straight
    one straight track per pin, fanned to a 1.4 mm pitch 1.7 mm beyond the pads (a track that starts inside the
    courtyard is covered by the exemption of the rule; two segments made Freerouting oscillate).
    Returns {(ref, pad): (end x, end y, direction x, direction y)}."""
    hv = set(HV_POWER + HV_SIGNAL)
    ends = {}
    for fp in c.b.GetFootprints():
        ref = fp.GetReference()
        name = fp.GetFPID().GetUniStringLibItemName()
        pads = [p for p in fp.Pads() if p.GetNetname()]
        if ref in SWITCH or name not in ('SOT-23', 'TSOT-23-8'):
            continue
        fx, fy = k.ToMM(fp.GetPosition().x), k.ToMM(fp.GetPosition().y)
        if not (any(p.GetNetname() in hv for p in pads)
                or any(x0 <= fx <= x1 and y0 <= fy <= y1 for x0, y0, x1, y1 in HV_AREAS)):
            continue
        boxes = {p.GetNumber(): pad_box(p) for p in pads}
        for p in pads:
            x0, y0, x1, y1 = boxes[p.GetNumber()]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            horizontal = x1 - x0 > y1 - y0
            out = ((1 if cx > fx else -1), 0) if horizontal else (0, (1 if cy > fy else -1))
            lat = (0, 1) if horizontal else (1, 0)
            length, width = (x1 - x0, y1 - y0) if horizontal else (y1 - y0, x1 - x0)
            pos = cx * lat[0] + cy * lat[1]                         # coordinate across the pad
            centre = fx * lat[0] + fy * lat[1]
            n = p.GetNetname()
            w = 0.6 if n in HV_POWER or n in CLASSES['VSYS'][4] else 0.3
            if name == 'SOT-23':
                # neighbours on the same side
                side = [q for q in pads if q is not p and
                        ((boxes[q.GetNumber()][0] + boxes[q.GetNumber()][2]) / 2 - fx) * out[0]
                        + ((boxes[q.GetNumber()][1] + boxes[q.GetNumber()][3]) / 2 - fy) * out[1] > 0]
                shift = 0.0
                if side:
                    q = boxes[side[0].GetNumber()]
                    qpos = (q[0] + q[2]) / 2 * lat[0] + (q[1] + q[3]) / 2 * lat[1]
                    gap = abs(qpos - pos) - width
                    shift = max(0.0, 0.62 - gap - (width - w) / 2) * (1 if pos > qpos else -1)
                sx, sy = cx + lat[0] * shift, cy + lat[1] * shift
                ex, ey = sx + out[0] * (length / 2 + 0.7), sy + out[1] * (length / 2 + 0.7)
                c.track([(sx, sy), (ex, ey)], n, w)
            else:
                w = 0.25
                mx, my = cx + out[0] * (length / 2 + 0.7), cy + out[1] * (length / 2 + 0.7)
                spread = (pos - centre) * 1.2
                ex, ey = mx + out[0] * 1.0 + lat[0] * spread, my + out[1] * 1.0 + lat[1] * spread
                c.track([(cx, cy), (ex, ey)], n, w)        # one segment: it starts inside the courtyard
            ends[(ref, p.GetNumber())] = (ex, ey, *out)
    # A via at the end of each escape track (not for GND and +3V3: plane_vias() adds theirs): Freerouting joins a
    # fixed track only at a via or a pad, and from a via it can go on on either layer.
    for (ref, pad), (ex, ey, _, _) in sorted(ends.items()):
        n = c.b.FindFootprintByReference(ref).FindPadByNumber(pad).GetNetname()
        if n in PLANE_NETS:
            continue
        if via_fits(c, ex, ey, n):
            c.via(ex, ey, n)
        c.anchor(ex, ey, n, 0.6 if n in HV_POWER or n in CLASSES['VSYS'][4] else 0.25)
    return ends


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


def plane_vias(c, ends):
    """One via per SMD pad of GND and +3V3 into its plane (lessons: each decoupling capacitor has its own via),
    placed just outside the pad, away from the part, clear of every pad, track, via and kept-free area."""
    b = c.b
    hv = set(HV_POWER + HV_SIGNAL)
    pads = list(b.GetPads())
    blocked = []                        # (box, extra clearance) of foreign copper
    for p in pads:
        blocked.append((p, pad_box(p), HV_CLEARANCE if p.GetNetname() in hv else 0.2))
    vias = [(k.ToMM(v.GetPosition().x), k.ToMM(v.GetPosition().y), k.ToMM(v.GetWidth(F)) / 2)
            for v in b.GetTracks() if isinstance(v, k.PCB_VIA)]
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
        if fp.GetReference() in SWITCH or fp.GetReference() == 'D4':
            continue                    # vias placed by switch() and power_input()
        fx, fy = k.ToMM(fp.GetPosition().x), k.ToMM(fp.GetPosition().y)
        x0, y0, x1, y1 = pad_box(p)
        hw, hh = (x1 - x0) / 2, (y1 - y0) / 2
        away = math.atan2(py - fy, px - fx) if (px, py) != (fx, fy) else 0.0
        own = (px, py)
        if (fp.GetReference(), p.GetNumber()) in ends:      # go on from the end of the escape track
            px, py, dx, dy = ends[(fp.GetReference(), p.GetNumber())]
            away, hw, hh = math.atan2(dy, dx), 0.0, 0.0
        best = None
        for step in range(16):
            ang = away + (step + 1) // 2 * (1 if step % 2 else -1) * math.pi / 8
            ux, uy = math.cos(ang), math.sin(ang)
            reach = min(hw / abs(ux) if abs(ux) > 1e-6 else 1e9, hh / abs(uy) if abs(uy) > 1e-6 else 1e9) if hw else 0.0
            for extra in (0.55, 0.8, 1.1, 1.5):
                vx, vy = px + ux * (reach + extra), py + uy * (reach + extra)
                if not (1.0 < vx < 199.0 and 1.0 < vy < 119.0):
                    continue
                if any(math.hypot(vx - ax, vy - ay) < r + 0.5 for ax, ay, r in areas):
                    continue
                if any(math.hypot(vx - qx, vy - qy) < qr + 0.3 + 0.32 for qx, qy, qr in vias):
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
        if best is None and (px, py) == own:
            # A pin between two others (U9.2): straight out along the pad on a 0.2 mm track to the first free spot.
            ox, oy = ((1 if px > fx else -1), 0) if hw > hh else (0, (1 if py > fy else -1))
            for d in (0.6, 0.8, 1.0, 1.3, 1.6, 2.0, 2.5, 3.0):
                vx, vy = px + ox * (max(hw, hh) + d), py + oy * (max(hw, hh) + d)
                if via_fits(c, vx, vy, name):
                    c.track([(px, py), (vx, vy)], name, 0.2)
                    c.via(vx, vy, name)
                    vias.append((vx, vy, 0.3))
                    segs.append((name, px, py, vx, vy, 0.1))
                    break
            else:
                missing.append(f'{fp.GetReference()}.{p.GetNumber()}')
            continue
        if best is None:
            missing.append(f'{fp.GetReference()}.{p.GetNumber()}')
            continue
        c.track([(px, py), best], name, min(0.4, 2 * hw, 2 * hh) if (px, py) == own else 0.3)
        c.via(*best, name)
        vias.append((*best, 0.3))
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


def export_dsn(stage, only=None):
    """Specctra DSN for Freerouting: the router uses only L1 and L4; the plane nets stay in the network and
    route.sh tells Freerouting to skip their class (Plane). Stage 1 (checks/routing.dsn) routes the nets of
    first_stage_nets(), the others wait in the class Later; stage 2 (checks/routing-2.dsn) is written from the
    board with the tracks of stage 1 and routes the rest."""
    board = k.LoadBoard(str(BOARD))     # a copy: the stand-in tracks never reach the saved board
    first = first_stage_nets(board)
    every = {n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    # A net that is complete already (hand-made copper, or an earlier stage) is never offered to the router: it
    # would add a second path, also on the bootstrap and switch nodes of the converter.
    later = (every - first) | (every - incomplete(board)) if stage == 1 else every - set(only)
    setup(board, router_clearance=True, later=later - set(PLANE_NETS))
    dsn = dsn_of(stage)
    # Freerouting joins new tracks to pads, but leaves the ends of fixed tracks and fixed vias unconnected. Each
    # anchor (ends of the escape tracks, hand-made vias of signal nets, the 12 V tap) becomes a one-pad part in the
    # job only; the track the router ends there lies on the real hand-made copper.
    for i, (x, y, n, d) in enumerate(json.loads(ANCHORS.read_text())):
        fp = k.FOOTPRINT(board)
        fp.SetReference(f'AN{i}')
        fp.SetFPID(k.LIB_ID('AN', f'anchor{i}'))
        fp.SetPosition(pt(x, y))
        pad = k.PAD(fp)
        pad.SetNumber('1')
        pad.SetAttribute(k.PAD_ATTRIB_SMD)
        pad.SetShape(F, k.PAD_SHAPE_CIRCLE)
        pad.SetSize(F, k.VECTOR2I(mm(d), mm(d)))
        layers = k.LSET()
        layers.AddLayer(F)
        pad.SetLayerSet(layers)
        pad.SetPosition(pt(x, y))
        pad.SetNet(board.FindNet(n))
        fp.Add(pad)
        board.Add(fp)
    for x0, y0, x1, y1, n in CONV_COPPER:
        w = min(x1 - x0, y1 - y0)
        a, b = ((x0 + w / 2, (y0 + y1) / 2), (x1 - w / 2, (y0 + y1) / 2)) if x1 - x0 >= y1 - y0 else \
            (((x0 + x1) / 2, y0 + w / 2), ((x0 + x1) / 2, y1 - w / 2))
        if a == b:
            b = (b[0] + 0.001, b[1])
        Copper(board).track([rel(*a), rel(*b)], n, w)
    # The high-voltage classes get 0.31 mm in the job (copper under the mask) and every pad in the areas with
    # 12 V parts grows by 0.31 mm on each side, so the router keeps 0.62 mm between a pad there and foreign copper.
    # The DSN keeps one pad shape per footprint name, so a footprint with grown pads gets a name of its own.
    for fp in board.GetFootprints():
        grown = False
        if fp.GetReference().startswith('AN'):
            continue
        for p in fp.Pads():
            x, y = k.ToMM(p.GetPosition().x), k.ToMM(p.GetPosition().y)
            # ...and, on the whole board, the pads of THT parts and of parts with two or three pads (not the filters packed
            # tightly at their connectors, where no track would pass any more): a high-voltage track on its
            # way to the DevKitC rows passes them (it ran 0.32 mm from a pin of J5 before).
            wide = p.GetAttribute() == k.PAD_ATTRIB_PTH or (len(list(fp.Pads())) <= 3 and
                                                            fp.GetReference() not in AT_CONNECTOR)
            if p.GetNetname() and (wide or any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in HV_AREAS)):
                size = p.GetSize(F)
                gx = gy = mm(2 * HV_GROW)
                if fp.GetReference() in ('U5', 'U6'):   # only at the pad ends: grown sideways, the pads would
                    gx, gy = (gx, 0) if size.x > size.y else (0, gy)   # cover the fan-out tracks of their neighbours
                p.SetSize(F, k.VECTOR2I(size.x + gx, size.y + gy))
                grown = True
        if grown:
            fp.SetFPID(k.LIB_ID('HV', fp.GetFPID().GetUniStringLibItemName() + '_' + fp.GetReference()))
    for z in board.Zones():             # the power copper of switch() as wide tracks, as the converter copper above
        if z.GetIsRuleArea() or z.GetNetname() not in ('V12_F', 'V12_MID', 'VSYS'):
            continue
        bb = z.GetBoundingBox()
        if abs(k.ToMM(bb.GetCenter().x) - CONV_AT[0]) < 18 and abs(k.ToMM(bb.GetCenter().y) - CONV_AT[1]) < 15:
            continue
        x0, y0, x1, y1, n, layer = (k.ToMM(bb.GetX()), k.ToMM(bb.GetY()), k.ToMM(bb.GetRight()),
                                    k.ToMM(bb.GetBottom()), z.GetNetname(), z.GetLayer())
        x0, y0, x1, y1 = x0 + 0.05, y0 + 0.05, x1 - 0.05, y1 - 0.05
        w = min(x1 - x0, y1 - y0)
        a, b = ((x0 + w / 2, (y0 + y1) / 2), (x1 - w / 2, (y0 + y1) / 2)) if x1 - x0 >= y1 - y0 else \
            (((x0 + x1) / 2, y0 + w / 2), ((x0 + x1) / 2, y1 - w / 2))
        if a == b:
            b = (b[0] + 0.001, b[1])
        Copper(board).track([a, b], n, w, layer)
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
    dsn.parent.mkdir(exist_ok=True)
    if not k.ExportSpecctraDSN(board, str(dsn)):
        raise RuntimeError('DSN export failed')
    text = dsn.read_text()
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
    dsn.write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


def prepare():
    board = k.LoadBoard(str(BOARD))
    if any(True for _ in board.GetTracks()):
        raise SystemExit('board already has copper; run make_pcb.py first')
    setup(board, router_clearance=False)
    c = Copper(board)
    converter(c)
    switch(c)
    vsys_trunk(c)
    power_input(c)
    narrow_pins(c)
    ends = escapes(c)
    feed_taps(c, ends)
    # VSYS for the enable switch Q9 (and R51 beside it): from the via at the end of its escape track on L4, past
    # the ground vias of C41, to the input via of the converter.
    ex, ey = ends[('Q9', '2')][:2]
    tx, ty = rel(14.9, 1.0)
    assert via_fits(c, ex, ey, 'VSYS') or any(isinstance(t, k.PCB_VIA) and t.GetNetname() == 'VSYS' and
                                             t.HitTest(pt(ex, ey)) for t in board.GetTracks()), 'Q9.2 has no via'
    c.track([(ex, ey), (tx + 1.1, ey + abs(tx + 1.1 - ex)), (tx + 1.1, ty - 1.1), (tx, ty)], 'VSYS', 0.6, B)
    # ...and R51 to that escape track on L1, below Q9 (the router cannot branch off this fixed copper either).
    r51 = board.FindFootprintByReference('R51').FindPadByNumber('1')
    assert r51.GetNetname() == 'VSYS'
    rx, ry = k.ToMM(r51.GetPosition().x), k.ToMM(r51.GetPosition().y)
    path = [(rx, ry), (rx, ey + 0.95), (ex - 0.95, ey + 0.95), (ex, ey)]    # between the Q9 gate via and the
    c.track(path, 'VSYS', 0.6)                                               # ground vias of C40, C41; DRC checks it
    c36 = c.b.FindFootprintByReference('C36').FindPadByNumber('1').GetPosition()      # VCTL: fan of pin 6 into C36
    c.track([ends[('U6', '6')][:2], (k.ToMM(c36.x), k.ToMM(c36.y))], 'VCTL', 0.3)
    keepouts(c)
    missing = plane_vias(c, ends)
    big = set(PLANE_NETS) | set(HV_POWER) | set(CLASSES['VSYS'][4])
    for v in board.GetTracks():         # every hand-made via of a signal net is a point the router may start from
        if isinstance(v, k.PCB_VIA) and v.GetNetname() not in big:
            c.anchor(k.ToMM(v.GetPosition().x), k.ToMM(v.GetPosition().y), v.GetNetname(), k.ToMM(v.GetWidth(F)))
    ANCHORS.write_text('[\n' + ',\n'.join(json.dumps(a) for a in sorted(c.anchors)) + '\n]\n')
    board.Save(str(BOARD))
    BOARD.write_text(stable(BOARD.read_text()))     # fixed UUIDs, so the DSN lists the zones in the same order
    (ROOT / 'cad' / 'plytka-v2.kicad_dru').write_text(DRU)
    digest = export_dsn(1)
    print(f'prepared: {len(board.GetTracks())} hand-made tracks and vias, DSN sha256 {digest[:12]}')
    if missing:
        raise SystemExit('no room for a plane via at: ' + ' '.join(missing))


def absorb_vias(board, final):
    """Vias that join copper on one layer only go away (plane vias stay)."""
    tracks = [t for t in board.GetTracks() if not isinstance(t, k.PCB_VIA)]
    pads = list(board.GetPads())
    for v in [t for t in board.GetTracks() if isinstance(t, k.PCB_VIA) and (final or not t.IsLocked())]:
        if v.GetNetname() in PLANE_NETS:
            continue
        p = v.GetPosition()
        layers = {t.GetLayer() for t in tracks if t.GetNetCode() == v.GetNetCode() and t.HitTest(p)}
        layers |= {F} if any(pd.GetNetCode() == v.GetNetCode() and pd.HitTest(p) for pd in pads) else set()
        layers |= {z.GetLayer() for z in board.Zones() if z.GetNetCode() == v.GetNetCode() and z.GetBoundingBox().Contains(p)}
        if len(layers) < 2:
            board.Delete(v)


def absorb(board, ses):
    """Import a Freerouting session into the board and tidy up what the router left."""
    open_before = incomplete(board)
    if not k.ImportSpecctraSES(board, str(ses)):
        raise SystemExit('Specctra session import failed')
    # The session also repeats pieces of fixed tracks at the pins they end on; a net that was complete before
    # takes nothing from the router.
    for t in list(board.GetTracks()):
        if not t.IsLocked() and t.GetNetname() not in open_before:
            board.Delete(t)
    # The job had two layers, so KiCad reads the router vias as blind/buried between layer indexes 0 and 1:
    # make them through vias again.
    for v in board.GetTracks():
        if isinstance(v, k.PCB_VIA) and not v.IsLocked():
            v.SetViaType(k.VIATYPE_THROUGH)
            v.SetLayerPair(F, B)
    # Router vias that join copper on one layer only (Freerouting leaves a few after optimising) go away;
    # plane vias stay, they connect to In1 or In2.
    absorb_vias(board, False)
    # Freerouting narrows a track where it enters a thin pin (neck-down; without it it left many nets open): every
    # track gets at least the smallest width of its class back; DRC then checks the spacing of the widened tracks.
    floor = {n: 0.4 for n in CLASSES['Power'][4]}
    floor.update({n: 0.6 for cl in ('VSYS', 'HV12') for n in CLASSES[cl][4]})
    for t in board.GetTracks():
        if not isinstance(t, k.PCB_VIA) and not t.IsLocked() and t.GetWidth() < mm(floor.get(t.GetNetname(), 0.15)):
            t.SetWidth(mm(floor.get(t.GetNetname(), 0.15)))


def incomplete(board):
    """Names of the nets (planes aside) whose pads are not all joined."""
    k.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    pads = {}
    for p in board.GetPads():
        if p.GetNetname() and p.GetNetname() not in PLANE_NETS:
            pads.setdefault(p.GetNetname(), []).append(p)
    found = set()
    for name, group in pads.items():
        joined = {(q.GetPosition().x, q.GetPosition().y, q.GetParentFootprint().GetReference())
                  for q in map(k.Cast_to_PAD, [i for i in conn.GetConnectedItems(group[0]) if i.Type() == k.PCB_PAD_T])}
        joined.add((group[0].GetPosition().x, group[0].GetPosition().y, group[0].GetParentFootprint().GetReference()))
        if len(joined) < len({(q.GetPosition().x, q.GetPosition().y, q.GetParentFootprint().GetReference()) for q in group}):
            found.add(name)
    return found


def near(p):
    return {(math.floor(p[0]) + i, math.floor(p[1]) + j) for i in (0, 1) for j in (0, 1)}


def hand_made():
    """Keys of the hand-made tracks and vias: the wiring of the job of stage 1 lists exactly them."""
    text = DSN.read_text()
    text = text[text.index('(wiring'):]
    keys = set()
    for layer, nums in re.findall(r'\(wire \(path (\S+) \S+((?:\s+-?[\d.]+)+)\)', text):
        v = [float(n) for n in nums.split()]
        pts = list(zip(v[0::2], v[1::2]))
        for a, b in zip(pts, pts[1:]):
            for qa in near(a):          # the job gives 0.1 um; a value at x.5 um may round either way
                for qb in near(b):
                    keys.add((layer, *sorted((qa, qb))))
    for x, y in re.findall(r'\(via \S+\s+(-?[\d.]+) (-?[\d.]+)', text):
        keys.update(('via', *q) for q in near((float(x), float(y))))
    return keys


def is_hand(t, keys):
    um = lambda p: (round(k.ToMM(p.x) * 1000), round(-k.ToMM(p.y) * 1000))
    if t.GetLayer() not in (F, B) and not isinstance(t, k.PCB_VIA):
        return True                     # the bootstrap tracks on In2
    if isinstance(t, k.PCB_VIA):
        return ('via', *um(t.GetPosition())) in keys
    return ('F.Cu' if t.GetLayer() == F else 'B.Cu', *sorted((um(t.GetStart()), um(t.GetEnd())))) in keys


def next_stage(stage, ses):
    """After a stage: the nets it left open are routed again from nothing in the next one (Freerouting cannot
    branch off a fixed track), everything else is fixed copper. From stage 3 on the nets with router tracks
    within 3 mm of a pad of an open net go again too: with all its neighbours fixed, an open net stayed open.
    Every track is locked on the board (KiCad drops the unlocked ones when it reads the next session).
    Returns False when nothing is open any more (then no job is written)."""
    board = k.LoadBoard(str(BOARD))
    absorb(board, ses)
    keys = hand_made()
    open_nets = incomplete(board)
    again = set(open_nets)
    if stage >= 3:
        spots = [(k.ToMM(p.GetPosition().x), k.ToMM(p.GetPosition().y)) for p in board.GetPads()
                 if p.GetNetname() in open_nets]
        for t in board.GetTracks():
            if t.GetNetname() in again or t.GetNetname() in PLANE_NETS or is_hand(t, keys):
                continue
            a, b = t.GetStart(), t.GetEnd()
            if any(seg_dist(x, y, k.ToMM(a.x), k.ToMM(a.y), k.ToMM(b.x), k.ToMM(b.y)) < 3.0 for x, y in spots):
                again.add(t.GetNetname())
    for t in list(board.GetTracks()):
        if t.GetNetname() in again and not is_hand(t, keys):
            board.Delete(t)
        else:
            t.SetLocked(True)
    print(f'stage {stage - 1}: open nets:', ' '.join(sorted(open_nets)) or 'none',
          '; routed again with them:' if again - open_nets else '', ' '.join(sorted(again - open_nets)))
    board.Save(str(BOARD))
    BOARD.write_text(stable(BOARD.read_text()))
    if not open_nets:
        return False
    digest = export_dsn(stage, again)
    print(f'stage {stage - 1} imported, DSN of stage {stage} sha256 {digest[:12]}')
    return True


def prune(board):
    """Hand-made tracks that were only offered to the router and stayed unused (an escape track or an exit of the
    converter whose net the router joined elsewhere) go away: every track with a loose end, until none is left."""
    while True:
        k.ZONE_FILLER(board).Fill(board.Zones())
        board.BuildConnectivity()
        conn = board.GetConnectivity()
        loose = [t for t in board.GetTracks() if not isinstance(t, k.PCB_VIA) and t.GetNetname() not in PLANE_NETS
                 and conn.TestTrackEndpointDangling(t, True)]
        if not loose:
            return
        for t in loose:
            board.Delete(t)
        absorb_vias(board, final=True)


def finish():
    """After the last stage (its session is on the board already): tidy up, planes, fill."""
    board = k.LoadBoard(str(BOARD))
    for t in board.GetTracks():
        t.SetLocked(True)
    absorb_vias(board, final=True)
    for t in list(board.GetTracks()):
        if not isinstance(t, k.PCB_VIA) and t.GetLength() < mm(0.05):
            board.Delete(t)
    prune(board)
    if incomplete(board):
        print('still open:', ' '.join(sorted(incomplete(board))))
    c = Copper(board)
    planes(c)
    setup(board, router_clearance=False)
    k.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()
    board.Save(str(BOARD))
    BOARD.write_text(stable(BOARD.read_text()))
    print('routing finished, planes filled')


if __name__ == '__main__':
    if sys.argv[1:2] == ['prepare']:
        prepare()
    elif sys.argv[1:2] == ['stage']:
        next_stage(int(sys.argv[2]), sys.argv[3])
    elif sys.argv[1:2] == ['planes']:
        board = k.LoadBoard(str(BOARD))
        planes(Copper(board))
        setup(board, router_clearance=False)
        k.ZONE_FILLER(board).Fill(board.Zones())
        board.Save(str(BOARD))
        BOARD.write_text(stable(BOARD.read_text()))
        print('no routing session: planes only')
    elif sys.argv[1:2] == ['finish']:
        finish()
    else:
        raise SystemExit(__doc__)
