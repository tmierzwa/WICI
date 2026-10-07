"""Film o WICI w stylu 3Blue1Brown (Manim CE).

Wymaga wcześniejszego uruchomienia tts.py (build/timing.json i build/audio).
Render: manim -qh wici_film.py WICI
"""

import json
import random
from pathlib import Path

import numpy as np
from manim import *

HERE = Path(__file__).parent
TIMING = json.loads((HERE / "build" / "timing.json").read_text())
AUDIO = HERE / "build" / "audio"

SERIF = "HEAD"  # nagłówki: Avenir Next Demi Bold
SANS = "Avenir Next"
SFX_TITLE = HERE / "sfx" / "title.mp3"  # ElevenLabs sound-generation, zob. README
LOGO = HERE.parent / "logo" / "WICI-na-ciemnym.svg"  # znak z media/logo
SEG_GAP = 0.45
FW = config.frame_width

config.background_color = "#0f1216"

ACCENT = YELLOW_C
WATER = BLUE_C
RADIO = TEAL_C
ALERT = RED_C
OK = GREEN_C
DIM = GREY_C


def T(s, size=36, color=WHITE, font=SANS, **kw):
    if font == SERIF:
        font = SANS
        kw.setdefault("weight", SEMIBOLD)
    return Text(s, font=font, font_size=size, color=color, **kw)


# ---------- ikony ----------

def house(w=0.8, h=0.6, lit=True):
    body = Rectangle(width=w, height=h, stroke_color=GREY_B, stroke_width=2)
    roof = Polygon(body.get_corner(UL), body.get_corner(UR), body.get_top() + UP * h * 0.6,
                   stroke_color=GREY_B, stroke_width=2)
    win = Square(h * 0.38, stroke_width=0, fill_color=ACCENT if lit else GREY_E,
                 fill_opacity=1).move_to(body.get_center() + UP * h * 0.08)
    g = VGroup(body, roof, win)
    g.window = win
    return g


def phone(h=1.6):
    w = h * 0.52
    case = RoundedRectangle(width=w, height=h, corner_radius=0.12, stroke_color=GREY_A,
                            stroke_width=3, fill_color="#1b2027", fill_opacity=1)
    screen = Rectangle(width=w * 0.82, height=h * 0.78, stroke_width=0,
                       fill_color="#232a33", fill_opacity=1).move_to(case)
    bars = VGroup(*[Rectangle(width=w * 0.07, height=h * 0.03 * (i + 1), stroke_width=0,
                              fill_color=WHITE, fill_opacity=1) for i in range(4)])
    bars.arrange(RIGHT, buff=w * 0.04, aligned_edge=DOWN)
    bars.move_to(screen.get_corner(UR) + DL * h * 0.07, aligned_edge=UR)
    g = VGroup(case, screen, bars)
    g.screen, g.bars = screen, bars
    return g


def building(w, h, color, label=None, door=False):
    body = Rectangle(width=w, height=h, stroke_color=color, stroke_width=3,
                     fill_color=color, fill_opacity=0.08)
    roof = Polygon(body.get_corner(UL) + LEFT * 0.1, body.get_corner(UR) + RIGHT * 0.1,
                   body.get_top() + UP * h * 0.35, stroke_color=color, stroke_width=3)
    g = VGroup(body, roof)
    if door:
        d = Rectangle(width=w * 0.45, height=h * 0.6, stroke_color=color, stroke_width=2)
        d.align_to(body, DOWN)
        lines = VGroup(*[Line(d.get_left(), d.get_right(), stroke_color=color, stroke_width=1.5)
                         .shift(UP * (i - 1.5) * h * 0.12) for i in range(4)])
        g.add(d, lines)
    if label:
        g.add(T(label, 26, color).next_to(body, DOWN, buff=0.2))
    g.body = body
    return g


def mast(h=2.2, color=GREY_B):
    base_w = h * 0.38
    l = Line(DOWN * h / 2 + LEFT * base_w / 2, UP * h / 2, stroke_color=color)
    r = Line(DOWN * h / 2 + RIGHT * base_w / 2, UP * h / 2, stroke_color=color)
    cross = VGroup()
    for k in range(1, 4):
        a = l.point_from_proportion(k / 4)
        b = r.point_from_proportion(k / 4)
        cross.add(Line(a, b, stroke_color=color, stroke_width=2))
        if k < 3:
            cross.add(Line(a, r.point_from_proportion((k + 1) / 4), stroke_color=color, stroke_width=1.5))
    waves = VGroup(*[Arc(radius=0.18 * i, start_angle=PI / 4, angle=PI / 2, stroke_color=color,
                         stroke_width=2).move_arc_center_to(UP * h / 2) for i in (1, 2)])
    return VGroup(l, r, cross, waves)


class Battery(VGroup):
    def __init__(self, w=0.9, h=0.45, label=None, level=1.0, **kw):
        super().__init__(**kw)
        self.box = RoundedRectangle(width=w, height=h, corner_radius=0.06, stroke_color=GREY_A, stroke_width=3)
        tip = Rectangle(width=w * 0.07, height=h * 0.4, stroke_width=0, fill_color=GREY_A,
                        fill_opacity=1).next_to(self.box, RIGHT, buff=0)
        self.level = ValueTracker(level)
        self.inner_w = w - 0.1
        self.fill = always_redraw(self._fill)
        self.add(self.box, tip, self.fill)
        if label:
            self.add(T(label, 22, GREY_A).next_to(self.box, DOWN, buff=0.12))

    def _fill(self):
        v = max(self.level.get_value(), 0.001)
        col = interpolate_color(ALERT, OK, min(1, v * 1.6))
        r = Rectangle(width=self.inner_w * v, height=self.box.height - 0.1, stroke_width=0,
                      fill_color=col, fill_opacity=0.9)
        return r.move_to(self.box.get_left() + RIGHT * (0.05 + self.inner_w * v / 2))


def laptop(w=1.6):
    scr = RoundedRectangle(width=w, height=w * 0.62, corner_radius=0.05, stroke_color=GREY_A,
                           stroke_width=3, fill_color="#1b2027", fill_opacity=1)
    inner = Rectangle(width=w * 0.86, height=w * 0.5, stroke_width=0, fill_color=BLUE_E,
                      fill_opacity=0.6).move_to(scr)
    base = Polygon(scr.get_corner(DL) + LEFT * 0.15, scr.get_corner(DR) + RIGHT * 0.15,
                   scr.get_corner(DR) + RIGHT * 0.25 + DOWN * 0.12,
                   scr.get_corner(DL) + LEFT * 0.25 + DOWN * 0.12,
                   stroke_color=GREY_A, stroke_width=3, fill_color="#1b2027", fill_opacity=1)
    return VGroup(scr, inner, base)


def router(w=1.3):
    box = RoundedRectangle(width=w, height=w * 0.3, corner_radius=0.08, stroke_color=GREY_A,
                           stroke_width=3, fill_color="#1b2027", fill_opacity=1)
    ants = VGroup(*[Line(box.get_top() + RIGHT * x, box.get_top() + RIGHT * x * 1.3 + UP * w * 0.45,
                         stroke_color=GREY_A, stroke_width=4) for x in (-w * 0.32, w * 0.32)])
    leds = VGroup(*[Dot(radius=0.035, color=OK) for _ in range(4)]).arrange(RIGHT, buff=0.1).move_to(box)
    return VGroup(box, ants, leds)


def wifi(center, r=0.25, n=3, color=WHITE, angle=PI / 2):
    return VGroup(*[Arc(radius=r * (i + 1), start_angle=angle - PI / 4, angle=PI / 2,
                        stroke_color=color, stroke_width=3).move_arc_center_to(center)
                    for i in range(n)])


def radio_module(w=1.1):
    pcb = RoundedRectangle(width=w, height=w * 0.7, corner_radius=0.05, stroke_color=RADIO,
                           stroke_width=3, fill_color="#0f3a35", fill_opacity=1)
    chip = Square(w * 0.3, stroke_color=GREY_A, stroke_width=2, fill_color=BLACK,
                  fill_opacity=1).move_to(pcb).shift(LEFT * w * 0.15)
    pins = VGroup(*[Line(UP * 0.04, DOWN * 0.04, stroke_color=GREY_B, stroke_width=2)
                    .move_to(chip.get_bottom() + DOWN * 0.04 + RIGHT * (i - 1.5) * w * 0.07)
                    for i in range(4)])
    conn = Rectangle(width=w * 0.12, height=w * 0.18, stroke_width=0, fill_color=GOLD,
                     fill_opacity=1).move_to(pcb.get_right() + LEFT * w * 0.1)
    return VGroup(pcb, chip, pins, conn)


def person(h=0.9, color=GREY_A):
    head = Circle(radius=h * 0.16, stroke_color=color, stroke_width=3).shift(UP * h * 0.3)
    body = Arc(radius=h * 0.3, start_angle=0, angle=PI, stroke_color=color,
               stroke_width=3).shift(DOWN * h * 0.2)
    body.add_line_to(body.get_start())
    return VGroup(head, body)


def drop(r=0.22, color=WATER):
    c = Circle(radius=r, stroke_width=0, fill_color=color, fill_opacity=1)
    t = Polygon(LEFT * r * 0.95 + UP * r * 0.3, RIGHT * r * 0.95 + UP * r * 0.3, UP * r * 2.1,
                stroke_width=0, fill_color=color, fill_opacity=1)
    return VGroup(c, t)


def pill(w=0.6, color=ALERT):
    p = RoundedRectangle(width=w, height=w * 0.42, corner_radius=w * 0.21, stroke_width=0,
                         fill_color=color, fill_opacity=1)
    half = RoundedRectangle(width=w, height=w * 0.42, corner_radius=w * 0.21, stroke_width=0,
                            fill_color=WHITE, fill_opacity=1)
    clip = VGroup(p, Rectangle(width=w / 2, height=w * 0.42, stroke_width=0, fill_color=WHITE,
                               fill_opacity=1).align_to(p, RIGHT).shift(LEFT * w * 0.0))
    clip[1].stretch_to_fit_width(w * 0.3).align_to(p, RIGHT).shift(LEFT * w * 0.2)
    cap = half.copy().set_fill(WHITE).stretch_to_fit_width(w * 0.55).align_to(p, RIGHT)
    return VGroup(p, cap).rotate(PI / 6)


def check(size=0.3, color=OK):
    return VMobject(stroke_color=color, stroke_width=6).set_points_as_corners(
        [LEFT * size * 0.5, DOWN * size * 0.4 + LEFT * size * 0.1, UP * size * 0.5 + RIGHT * size * 0.55])


def crossed(text, size=30):
    # przekreślenie na wysokości małych liter: wzorcem jest dodatkowe „x” przed tekstem
    full = T("x" + text, size, DIM)
    y = full[0].get_center()[1]
    t = VGroup(*full[1:])
    return VGroup(t, Line([t.get_left()[0] - 0.08, y, 0], [t.get_right()[0] + 0.08, y, 0],
                          stroke_color=ALERT, stroke_width=4))


def logo(width=4.0):
    # Manim nie skaluje grubości linii z SVG: sygnał ma 52 z 2407 jednostek szerokości znaku
    m = SVGMobject(str(LOGO)).scale_to_fit_width(width)
    m[0].set_stroke(width=52 / 2407 * width * 100)
    return m


def aa_cells(n=4, w=0.34, color=GREY_A):
    cells = VGroup()
    for _ in range(n):
        body = RoundedRectangle(width=w, height=w * 0.36, corner_radius=w * 0.08, stroke_color=color,
                                stroke_width=2, fill_color=OK, fill_opacity=0.55)
        tip = Rectangle(width=w * 0.07, height=w * 0.14, stroke_width=0, fill_color=color,
                        fill_opacity=1).next_to(body, RIGHT, buff=0)
        cells.add(VGroup(body, tip))
    return cells.arrange(RIGHT, buff=w * 0.12)


def station(w=3.0):
    """Stacja WICI: ekran, przyciski, ogniwa AA i gniazdo anteny. Obrys w kolorze zestawu."""
    h = w * 0.62
    body = RoundedRectangle(width=w, height=h, corner_radius=w * 0.06, stroke_color=ACCENT,
                            stroke_width=4, fill_color="#1b2027", fill_opacity=1)
    screen = Rectangle(width=w * 0.56, height=h * 0.5, stroke_color=GREY_B, stroke_width=2,
                       fill_color="#aab3a6", fill_opacity=1)
    screen.move_to(body.get_corner(UL) + RIGHT * (w * 0.08 + screen.width / 2) + DOWN * (h * 0.12 + screen.height / 2))
    buttons = VGroup(*[Circle(radius=w * 0.055, stroke_color=GREY_A, stroke_width=2, fill_color="#2b323c",
                              fill_opacity=1) for _ in range(4)]).arrange_in_grid(2, 2, buff=w * 0.06)
    buttons.move_to([(screen.get_right()[0] + body.get_right()[0]) / 2, screen.get_y(), 0])
    cells = aa_cells(4, w * 0.11).move_to([screen.get_x(), (screen.get_bottom()[1] + body.get_bottom()[1]) / 2, 0])
    jack = Rectangle(width=w * 0.06, height=w * 0.08, stroke_width=0, fill_color=GOLD,
                     fill_opacity=1).move_to(body.get_corner(UR) + LEFT * w * 0.15 + UP * w * 0.04)
    g = VGroup(body, screen, buttons, cells, jack)
    g.body, g.screen, g.buttons, g.cells, g.jack = body, screen, buttons, cells, jack
    return g


def inverter(w=1.3):
    """Przetwornica 12 V → 230 V z zestawu WICI."""
    box = RoundedRectangle(width=w, height=w * 0.62, corner_radius=0.08, stroke_color=ACCENT, stroke_width=3,
                           fill_color="#1b2027", fill_opacity=1)
    sine = FunctionGraph(lambda x: 0.12 * w * np.sin(x * 2 * PI / (w * 0.5)), x_range=[-w * 0.3, w * 0.3],
                         stroke_color=ACCENT, stroke_width=3).move_to(box).shift(UP * w * 0.08)
    volts = T("230 V", 18, GREY_A).next_to(sine, DOWN, buff=w * 0.06)
    return VGroup(box, sine, volts)


def charger(w=1.3):
    """Ładowarka telefonów z zestawu WICI: osobne porty USB 5 V."""
    box = RoundedRectangle(width=w, height=w * 0.62, corner_radius=0.08, stroke_color=ACCENT, stroke_width=3,
                           fill_color="#1b2027", fill_opacity=1)
    ports = VGroup(*[Rectangle(width=w * 0.13, height=w * 0.07, stroke_color=GREY_A, stroke_width=2)
                     for _ in range(4)]).arrange(RIGHT, buff=w * 0.07).move_to(box).shift(UP * w * 0.08)
    volts = T("USB 5 V", 18, GREY_A).next_to(ports, DOWN, buff=w * 0.08)
    return VGroup(box, ports, volts)


def label2(lines, size=22, color=GREY_A):
    return VGroup(*[T(l, size, color) for l in lines]).arrange(DOWN, buff=0.06)


def window_frame(w=1.0, h=1.4):
    f = Rectangle(width=w, height=h, stroke_color=GREY_B, stroke_width=4)
    return VGroup(f, Line(f.get_top(), f.get_bottom(), stroke_color=GREY_B, stroke_width=2),
                  Line(f.get_left(), f.get_right(), stroke_color=GREY_B, stroke_width=2))


# ---------- scena ----------

class WICI(MovingCameraScene):
    timing, audio, out = TIMING, AUDIO, HERE / "build"
    seg_gap, sub_chunk = SEG_GAP, 96

    def setup(self):
        super().setup()
        self.subs = []  # (start, end, text) -> build/subs.json, nakładane przez napisy.py

    def _schedule(self, start, sentences, seg_end):
        for i, s in enumerate(sentences):
            a = start + s["start"]
            b = start + sentences[i + 1]["start"] if i + 1 < len(sentences) else seg_end
            words = s["text"].split()
            n = -(-len(s["text"]) // self.sub_chunk)
            target = len(s["text"]) / n
            chunks, cur = [], []
            for w in words:
                if cur and len(chunks) < n - 1 and len(" ".join(cur + [w])) > target + 6:
                    chunks.append(" ".join(cur))
                    cur = []
                cur.append(w)
            chunks.append(" ".join(cur))
            total = sum(len(c) for c in chunks)
            t = a
            spoken_end = start + s["end"]
            for c in chunks:
                d = (spoken_end - a) * len(c) / total
                self.subs.append((t, t + d if c != chunks[-1] else b, c))
                t += d

    # narracja

    def narr(self, key, *steps):
        info = self.timing[key]
        t0 = self.renderer.time
        dur = info["duration"]
        self.add_sound(str(self.audio / f"{key}.wav"))
        self._schedule(t0, info["sentences"], t0 + dur + self.seg_gap - 0.05)
        starts = [s["start"] for s in info["sentences"]]
        for st in steps:
            if isinstance(st, tuple) and st[0] in ("at", "t"):
                target = t0 + (starts[st[1]] if st[0] == "at" else st[1])
                if target - self.renderer.time > 1 / config.frame_rate:
                    self.wait(target - self.renderer.time)
            elif isinstance(st, tuple):
                anims, rt = st
                anims = anims if isinstance(anims, (list, tuple)) else [anims]
                self.play(*anims, run_time=rt)
            elif callable(st) and not isinstance(st, Animation):
                st()
            else:
                self.play(st)
        rest = t0 + dur + self.seg_gap - self.renderer.time
        if rest > 1 / config.frame_rate:
            self.wait(rest)

    def clear_all(self, rt=0.8):
        mobs = list(self.mobjects)
        if mobs:
            self.play(*[FadeOut(m) for m in mobs], run_time=rt)

    # ---------- części ----------

    def write_subs(self):
        (self.out / "subs.json").write_text(json.dumps(
            {"duration": self.renderer.time, "subs": [[round(a, 3), round(b, 3), t] for a, b, t in self.subs]},
            ensure_ascii=False, indent=0))

    def construct(self):
        random.seed(3)
        self.part_blackout()
        self.title_card()
        self.part_masts()
        self.part_question()
        self.part_message()
        self.part_hops()
        self.part_station()
        self.part_statuses()
        self.part_status()
        self.part_call()
        self.write_subs()

    def part_blackout(self):
        houses = VGroup(*[house(0.7 + 0.25 * random.random(), 0.55 + 0.2 * random.random())
                          for _ in range(8)]).arrange(RIGHT, buff=0.45, aligned_edge=DOWN)
        houses.move_to(UP * 1.7)
        ground = Line(LEFT * 7.5, RIGHT * 7.5, stroke_color=GREY_D).next_to(houses, DOWN, buff=0)
        glows = VGroup(*[Circle(radius=0.35, stroke_width=0, fill_color=ACCENT, fill_opacity=0.12)
                         .move_to(h.window) for h in houses])
        self.narr("s1a",
                  ([FadeIn(houses, lag_ratio=0.1, shift=UP * 0.2), FadeIn(glows), Create(ground)], 1.6),
                  ("at", 1),
                  ([LaggedStart(*[AnimationGroup(h.window.animate.set_fill(GREY_E), FadeOut(g))
                                  for h, g in zip(houses, glows)], lag_ratio=0.18)], 1.8))

        ph = phone(2.2).move_to(DOWN * 0.75)
        nosig = T("brak\nsieci", 26, ALERT).move_to(ph.screen)
        nosig.scale_to_fit_width(min(nosig.width, ph.screen.width * 0.8))
        self.narr("s1b",
                  ([VGroup(houses, ground).animate.set_opacity(0.2), FadeIn(ph, shift=UP * 0.5)], 1.2),
                  ("at", 1),
                  ([LaggedStart(*[FadeOut(b) for b in reversed(ph.bars)], lag_ratio=0.5)], 1.6),
                  (FadeIn(nosig), 0.7))
        self.clear_all(0.6)

        school = building(3.4, 1.9, GREY_A, "schronienie").move_to(LEFT * 3.6 + DOWN * 0.3)
        dots = VGroup(*[Dot(radius=0.06, color=WHITE) for _ in range(50)]).arrange_in_grid(5, 10, buff=0.16)
        dots.move_to(school.body)
        d, p = drop(), pill()
        dw = VGroup(d, T("woda", 26, WATER)).arrange(RIGHT, buff=0.2)
        pk = VGroup(p, T("leki", 26, ALERT)).arrange(RIGHT, buff=0.2)
        need = VGroup(dw, pk).arrange(RIGHT, buff=0.8).next_to(school[1], UP, buff=0.4)
        self.narr("s1c",
                  ([Create(school, lag_ratio=0.1)], 1.0),
                  ([LaggedStart(*[GrowFromCenter(x) for x in dots], lag_ratio=0.03)], 1.6),
                  ("at", 1),
                  ([FadeIn(dw, shift=DOWN * 0.3)], 0.7),
                  ([FadeIn(pk, shift=DOWN * 0.3)], 0.7))

        osp = building(1.8, 1.4, ALERT, "służby", door=True).move_to(RIGHT * 4.6)
        osp.shift(UP * (school.body.get_bottom()[1] - osp.body.get_bottom()[1]))
        ly = osp.body.get_center()[1]
        link = DashedLine([school.body.get_right()[0] + 0.25, ly, 0], [osp.body.get_left()[0] - 0.25, ly, 0],
                          stroke_color=GREY_B, dash_length=0.12)
        km = T("kilka kilometrów", 24, GREY_B).next_to(link, DOWN, buff=0.25)
        q = T("?", 96, ACCENT, font=SERIF).next_to(link, UP, buff=0.2)
        self.narr("s1d",
                  ([FadeIn(osp, shift=LEFT * 0.4)], 1.0),
                  ([Create(link), FadeIn(km)], 1.2),
                  ("at", 1),
                  (FadeIn(q), 0.8))
        self.wait(0.4)
        self.clear_all(0.8)

    def title_card(self):
        self.add_sound(str(SFX_TITLE), gain=-11)
        title = logo(4.6).shift(UP * 0.5)
        sub = T("sieć łączności na czas, gdy nic nie działa", 34, GREY_B).next_to(title, DOWN, buff=0.5)
        line = Line(LEFT * 3, RIGHT * 3, stroke_color=ACCENT).next_to(sub, DOWN, buff=0.35)
        self.play(FadeIn(title, scale=0.92), run_time=1.2)
        self.play(FadeIn(sub, shift=UP * 0.2), Create(line), run_time=1.0)
        self.wait(1.6)
        self.play(FadeOut(VGroup(title, sub, line)), run_time=0.7)

    def part_masts(self):
        pl = phone(1.5).move_to(LEFT * 5.6 + DOWN * 1.4)
        pr = phone(1.5).move_to(RIGHT * 5.6 + DOWN * 1.4)
        direct = DashedLine(pl.get_right(), pr.get_left(), stroke_color=GREY_B)
        cross = Cross(stroke_color=ALERT, stroke_width=8).scale(0.4).move_to(direct)
        self.narr("s2a",
                  ([FadeIn(pl, shift=RIGHT * 0.3), FadeIn(pr, shift=LEFT * 0.3)], 1.0),
                  (Create(direct), 1.0),
                  ("at", 1),
                  (Create(cross), 0.6))

        ml = mast().move_to(LEFT * 3 + UP * 0.2)
        mr = mast().move_to(RIGHT * 3 + UP * 0.2)
        cloud = VGroup(*[Circle(radius=r, stroke_width=0, fill_color=GREY_D, fill_opacity=1).shift(v)
                         for r, v in [(0.6, LEFT * 0.6), (0.75, UP * 0.2), (0.6, RIGHT * 0.65),
                                      (0.45, DOWN * 0.25 + RIGHT * 0.1)]]).move_to(UP * 2.6)
        cloud_l = VGroup(T("sieć", 22, GREY_A), T("operatora", 22, GREY_A)).arrange(DOWN, buff=0.08).move_to(cloud)
        top_l, top_r = ml[0].get_end(), mr[0].get_end()
        lines = VGroup(Line(pl.get_top(), top_l), Line(top_l, cloud.get_left() + DOWN * 0.2),
                       Line(cloud.get_right() + DOWN * 0.2, top_r), Line(top_r, pr.get_top()))
        lines.set_stroke(GREY_B, 2.5)
        path = VMobject().set_points_as_corners([pl.get_top(), top_l, cloud.get_center(), top_r, pr.get_top()])
        msg = Dot(radius=0.09, color=ACCENT)
        self.narr("s2b",
                  ([FadeOut(direct), FadeOut(cross), FadeIn(ml, shift=UP * 0.3),
                    FadeIn(mr, shift=UP * 0.3), FadeIn(cloud), FadeIn(cloud_l)], 1.0),
                  (Create(lines, lag_ratio=0.5), 1.2),
                  ([MoveAlongPath(msg, path, rate_func=linear)], 2.2),
                  (FadeOut(msg), 0.3))

        bl = Battery(label="zasilanie masztu").next_to(ml, DOWN, buff=0.3)
        br = Battery(label="zasilanie masztu").next_to(mr, DOWN, buff=0.3)
        hours = T("godziny…", 24, GREY_B).next_to(VGroup(bl, br), DOWN, buff=0.3).set_x(0)
        self.narr("s2c",
                  ([FadeIn(bl), FadeIn(br)], 0.8),
                  ("at", 1),
                  ([bl.level.animate.set_value(0.0), br.level.animate.set_value(0.12), FadeIn(hours)], 3.0))

        broken = lines[1]
        flash_pt = broken.get_center()
        self.narr("s2d",
                  ([broken.animate.set_stroke(ALERT, 4)], 0.5),
                  ([FadeOut(broken, scale=1.3), ml[3].animate.set_opacity(0.1),
                    lines[0].animate.set_stroke(GREY_D)], 0.8),
                  ("at", 1),
                  ([Circumscribe(VGroup(cloud, Dot(flash_pt)), color=ALERT, shape=Circle)], 1.4),
                  ([Indicate(pl, color=WHITE, scale_factor=1.05)], 1.0))
        self.clear_all()

    def part_question(self):
        l1 = T("Czego potrzeba,", 48, WHITE, font=SERIF)
        l2 = T("żeby przenieść krótką wiadomość", 48, WHITE, font=SERIF)
        l3 = T("na kilka kilometrów?", 48, WHITE, font=SERIF)
        q = VGroup(l1, l2, l3).arrange(DOWN, buff=0.3).shift(UP * 0.8)
        c1, c2 = crossed("prąd z sieci", 34), crossed("internet", 34)
        cond = VGroup(c1, c2).arrange(RIGHT, buff=1.2).next_to(q, DOWN, buff=0.8)
        self.narr("s3a",
                  ("at", 1),
                  ([FadeIn(l1)], 1.1), ([FadeIn(l2)], 1.1), ([FadeIn(l3)], 0.9),
                  ("t", TIMING["s3a"]["sentences"][1]["start"] + 4.9),
                  ([FadeIn(c1[0]), Create(c1[1])], 0.7),
                  ([FadeIn(c2[0]), Create(c2[1])], 0.7))
        self.wait(0.3)
        self.clear_all()

    def part_message(self):
        card = RoundedRectangle(width=8.8, height=3.6, corner_radius=0.15, stroke_color=GREY_B,
                                fill_color="#171c22", fill_opacity=1).shift(UP * 0.4)
        head = T("ZGŁOSZENIE", 28, ACCENT, weight=HEAVY).move_to(card.get_top() + DOWN * 0.45)
        rows_data = [("Gdzie:", "szkoła, ul. Polna 3, wejście od boiska"),
                     ("Ile osób:", "50"), ("Czego brakuje:", "woda, leki"), ("Pilność:", "wysoka")]
        rows = VGroup()
        for k, v in rows_data:
            rows.add(T(f"{k}  {v}", 26, WHITE, t2c={k: GREY_B}))
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.28).next_to(head, DOWN, buff=0.4)
        rows.align_to(card, LEFT).shift(RIGHT * 0.6)
        self.narr("s4a",
                  ([FadeIn(card, shift=UP * 0.3), FadeIn(head)], 1.0),
                  ("at", 1),
                  ([LaggedStart(*[FadeIn(r, shift=RIGHT * 0.2) for r in rows], lag_ratio=0.6)], 3.2))

        small = Square(0.36, stroke_color=ACCENT, stroke_width=2, fill_color=ACCENT,
                       fill_opacity=0.9).move_to(DOWN * 0.2)
        lbl = T("mniej niż 200 bajtów", 30, ACCENT).next_to(small, DOWN, buff=0.35)
        self.narr("s4b",
                  ([ReplacementTransform(VGroup(card, head, rows), small)], 1.4),
                  (FadeIn(lbl, shift=UP * 0.2), 0.6))

        # zdjęcie ~2,5 MB vs 174 B: stosunek pól ~14 000, boków ~120
        side = 0.36 * 120
        photo = Square(side, stroke_color=BLUE_C, stroke_width=3, fill_color=BLUE_E, fill_opacity=0.35)
        photo.move_to(small.get_corner(DL), aligned_edge=DL)
        frame = self.camera.frame
        ptxt = T("jedno zdjęcie z telefonu", 48, BLUE_B, font=SERIF).scale_to_fit_width(side * 0.78)
        ptxt.move_to(photo).shift(UP * side * 0.1)
        ratio = T("ponad 10 000 razy więcej", 48, WHITE).scale_to_fit_width(side * 0.6)
        ratio.next_to(ptxt, DOWN, buff=side * 0.06)
        ring = Circle(radius=2.5, stroke_color=ACCENT, stroke_width=24).move_to(small)
        self.add(photo, small)
        self.bring_to_back(photo)
        self.narr("s4c",
                  ([frame.animate.set_width(side * 1.25).move_to(photo.get_center() + DOWN * side * 0.05),
                    lbl.animate.set_opacity(0)], 3.0),
                  ([FadeIn(ptxt), FadeIn(ring)], 0.6),
                  (FadeIn(ratio), 0.6))
        self.wait(0.4)
        self.play(frame.animate.set_width(FW).move_to(ORIGIN), FadeOut(ptxt), FadeOut(ratio),
                  FadeOut(ring), run_time=2.2)
        self.remove(photo)

        ra = radio_module(1.4).move_to(LEFT * 3.6 + UP * 0.3)
        rb = radio_module(1.4).move_to(RIGHT * 3.6 + UP * 0.3)
        aa = Line(ra.get_top(), ra.get_top() + UP * 1.3, stroke_color=GREY_A, stroke_width=4)
        ab = Line(rb.get_top(), rb.get_top() + UP * 1.3, stroke_color=GREY_A, stroke_width=4)
        arc_path = ArcBetweenPoints(aa.get_end(), ab.get_end(), angle=-PI / 4)
        bar_bg = Rectangle(width=6, height=0.22, stroke_color=GREY_B, stroke_width=2).move_to(DOWN * 1.5)
        bar = Rectangle(width=0.01, height=0.22, stroke_width=0, fill_color=ACCENT, fill_opacity=1)
        bar.align_to(bar_bg, LEFT).set_y(bar_bg.get_y())
        bar_l = T("czas nadawania: około 1 sekundy", 26, GREY_A).next_to(bar_bg, UP, buff=0.25)
        waves = VGroup(*[Arc(radius=0.3 * i, start_angle=-PI / 4, angle=PI / 2, stroke_color=RADIO,
                             stroke_width=3).move_arc_center_to(aa.get_end()) for i in (1, 2, 3)])
        self.narr("s4d",
                  (small.animate.move_to(UP * 2.9).scale(0.8), 0.8),
                  ("at", 1),
                  ([FadeIn(ra), FadeIn(rb), Create(aa), Create(ab)], 1.0),
                  ("at", 2),
                  ([FadeIn(bar_bg), FadeIn(bar_l), small.animate.move_to(aa.get_end())], 0.6),
                  ([MoveAlongPath(small, arc_path), LaggedStart(*[Create(w) for w in waves], lag_ratio=0.3),
                    bar.animate.stretch_to_fit_width(4.2, about_edge=LEFT)], 0.8),
                  (FadeOut(waves), 0.4))

        power = T("moc jak pilot do bramy", 28, RADIO).next_to(ra, DOWN, buff=0.45)
        remote = VGroup(RoundedRectangle(width=0.35, height=0.6, corner_radius=0.08, stroke_color=GREY_A,
                                         stroke_width=3),
                        *[Circle(radius=0.06, stroke_color=GREY_A, stroke_width=2).shift(UP * y)
                          for y in (0.12, -0.08)]).next_to(power, RIGHT, buff=0.3)
        cells = aa_cells(4, 0.5).move_to([1.9, ra.get_y(), 0])
        bat = VGroup(cells, T("zwykłe baterie", 22, GREY_A).next_to(cells, DOWN, buff=0.2))
        wire = Line(ra.get_right(), cells.get_left(), stroke_color=GREY_B, stroke_width=3)
        self.narr("s4e",
                  ([FadeOut(VGroup(bar_bg, bar, bar_l, small, rb, ab))], 0.6),
                  ([FadeIn(power, shift=UP * 0.2), FadeIn(remote)], 0.8),
                  ("at", 1),
                  ([FadeIn(bat), Create(wire)], 1.0))
        self.clear_all()

    def part_hops(self):
        R = 2.8
        pos = {"A": np.array([-5.4, -1.6, 0]), "B": np.array([-2.9, -0.9, 0]),
               "C": np.array([-0.4, -0.2, 0]), "D": np.array([2.1, 0.5, 0]),
               "OSP": np.array([4.6, 1.2, 0]), "E": np.array([-0.6, 1.0, 0])}
        # zabudowa w tle
        blocks = VGroup()
        for _ in range(140):
            x, y = random.uniform(-7, 7), random.uniform(-2.9, 3.6)
            blocks.add(Rectangle(width=random.uniform(0.15, 0.4), height=random.uniform(0.12, 0.3),
                                 stroke_width=0, fill_color=GREY_D, fill_opacity=0.5).move_to([x, y, 0]))

        def node(name, color, label=None):
            c = Dot(pos[name], radius=0.14, color=color)
            g = VGroup(Circle(radius=0.26, stroke_color=color, stroke_width=3).move_to(pos[name]), c)
            if label:
                g.add(T(label, 22, color).next_to(c, DOWN, buff=0.3))
            return g

        A = node("A", ACCENT, "schronienie")
        OSP = node("OSP", ALERT, "służby")
        rng = Circle(radius=R, stroke_color=RADIO, stroke_width=2, fill_color=RADIO,
                     fill_opacity=0.07).move_to(pos["A"])
        rng_l = T("około 1 km?", 26, RADIO).move_to(pos["A"] + np.array([1.2, 1.6, 0]))
        self.narr("s5a",
                  ([FadeIn(blocks, lag_ratio=0.01), FadeIn(A), FadeIn(OSP)], 1.4),
                  ("at", 1),
                  ([GrowFromCenter(rng), FadeIn(rng_l)], 1.4))

        # dawne wici
        mapg = VGroup(blocks, A, OSP, rng, rng_l)
        mapg.save_state()
        huts = VGroup(*[house(0.7, 0.5, lit=False) for _ in range(5)]).arrange(RIGHT, buff=1.6).shift(DOWN * 0.3)
        for h in huts:
            h.window.set_fill(GREY_D)
        word = T("wici", 72, ACCENT, font=SERIF).shift(UP * 2.2)
        fire = Dot(radius=0.12, color=ORANGE).move_to(huts[0].get_top() + UP * 0.15)
        hops = [ArcBetweenPoints(huts[i].get_top() + UP * 0.15, huts[i + 1].get_top() + UP * 0.15, angle=-PI / 2.2)
                for i in range(4)]
        self.narr("s5b",
                  ([mapg.animate.set_opacity(0), FadeIn(huts, lag_ratio=0.15), FadeIn(word)], 1.4),
                  ("at", 1),
                  (FadeIn(fire, scale=2), 0.4),
                  *[([MoveAlongPath(fire, hp), huts[i + 1].window.animate.set_fill(ORANGE)], 0.9)
                    for i, hp in enumerate(hops)])
        self.play(FadeOut(VGroup(huts, word, fire)), Restore(mapg), run_time=0.9)

        names = ["B", "C", "D"]
        mids = {n: node(n, RADIO) for n in names}
        rings = {n: Circle(radius=R, stroke_color=RADIO, stroke_width=1.2, stroke_opacity=0.35).move_to(pos[n])
                 for n in names}
        chain = ["A", "B", "C", "D", "OSP"]
        links = {(a, b): Line(pos[a], pos[b], stroke_color=GREY_B, stroke_width=2.5, buff=0.3)
                 for a, b in zip(chain, chain[1:])}
        msg = Square(0.18, stroke_width=0, fill_color=ACCENT, fill_opacity=1).move_to(pos["A"])
        hop_anims = []
        for a, b in zip(chain, chain[1:]):
            hop_anims.append(([MoveAlongPath(msg, ArcBetweenPoints(pos[a], pos[b], angle=-PI / 5)),
                               Flash(pos[b], color=RADIO, line_length=0.18, flash_radius=0.35)], 0.75))
        ok = check(0.4).next_to(OSP[1], UR, buff=0.15)
        self.narr("s5c",
                  ([FadeOut(rng_l), rng.animate.set_fill(opacity=0).set_stroke(opacity=0.35, width=1.2)], 0.5),
                  ([LaggedStart(*[AnimationGroup(FadeIn(mids[n], scale=0.5), Create(rings[n])) for n in names],
                                lag_ratio=0.4)], 1.4),
                  ([Create(l) for l in links.values()], 0.6),
                  ("at", 1),
                  (FadeIn(msg), 0.2),
                  *hop_anims,
                  (Create(ok), 0.4))

        E = node("E", RADIO)
        ringE = Circle(radius=R, stroke_color=RADIO, stroke_width=1.2, stroke_opacity=0.35).move_to(pos["E"])
        lBE = Line(pos["B"], pos["E"], stroke_color=GREY_B, stroke_width=2.5, buff=0.3)
        lED = Line(pos["E"], pos["D"], stroke_color=GREY_B, stroke_width=2.5, buff=0.3)
        msg.move_to(pos["A"])
        walker = person(0.5, ACCENT).move_to(pos["B"] + DOWN * 0.55)
        u = (pos["D"] - pos["B"]) / np.linalg.norm(pos["D"] - pos["B"])
        goal = pos["D"] - u * R * 0.8 + DOWN * 0.55
        steps = DashedLine(walker.get_center(), goal, stroke_color=ACCENT, stroke_width=2, dash_length=0.08)
        self.narr("s5d",
                  ([FadeOut(ok), FadeOut(msg)], 0.4),
                  ("at", 1),
                  ([mids["C"].animate.set_color(GREY_D), FadeOut(rings["C"]),
                    links[("B", "C")].animate.set_stroke(ALERT), links[("C", "D")].animate.set_stroke(ALERT)], 0.8),
                  ([FadeOut(links[("B", "C")]), FadeOut(links[("C", "D")])], 0.6),
                  ("at", 2),
                  ([FadeIn(E, scale=0.5), Create(ringE)], 0.8),
                  ([Create(lBE), Create(lED)], 0.5),
                  (FadeIn(msg), 0.1),
                  *[([MoveAlongPath(msg, ArcBetweenPoints(pos[a], pos[b], angle=-PI / 5))], 0.45)
                    for a, b in [("A", "B"), ("B", "E"), ("E", "D"), ("D", "OSP")]],
                  (Create(ok2 := check(0.4).next_to(OSP[1], UR, buff=0.15)), 0.3),
                  ("at", 3),
                  ([FadeOut(ok2), FadeOut(msg), E.animate.set_color(GREY_D), FadeOut(ringE),
                    FadeOut(lBE), FadeOut(lED)], 0.6),
                  (FadeIn(walker, shift=UP * 0.1), 0.3),
                  ([MoveAlongPath(walker, Line(walker.get_center(), goal)), Create(steps)], 1.8),
                  (ShowPassingFlash(Line(goal + UP * 0.55, pos["D"], buff=0.3).set_stroke(ACCENT, width=6),
                                    time_width=0.6), 0.5),
                  (ShowPassingFlash(links[("D", "OSP")].copy().set_stroke(ACCENT, width=6), time_width=0.6), 0.5),
                  (Create(check(0.4).next_to(OSP[1], UR, buff=0.15)), 0.3))
        self.clear_all()

    def part_station(self):
        title = T("jedna stacja", 44, WHITE, font=SERIF).to_corner(UL, buff=0.5).shift(RIGHT * 0.3)
        st = station(3.0).move_to([-3.3, -0.6, 0])
        st_l = T("stacja WICI", 22, GREY_A).next_to(st, DOWN, buff=0.2)
        levels = VGroup()
        for n, name in enumerate(["stacja", "+ laptop", "+ router"], 1):
            t = VGroup(T(str(n), 22, DIM, weight=HEAVY), T(name, 22, DIM)).arrange(RIGHT, buff=0.15)
            box = RoundedRectangle(width=t.width + 0.4, height=0.5, corner_radius=0.15, stroke_color=GREY_D,
                                   stroke_width=2)
            levels.add(VGroup(box, t.move_to(box)))
        levels.arrange(RIGHT, buff=0.18).to_edge(RIGHT, buff=0.6).set_y(title.get_y())

        def level(i):
            box, t = levels[i]
            return [box.animate.set_stroke(WHITE), t.animate.set_color(WHITE)]

        self.narr("s6a", (FadeIn(title), 1.0),
                  ([FadeIn(st, shift=UP * 0.2), FadeIn(st_l)], 0.8),
                  ("at", 1),
                  ([FadeIn(levels)], 0.6),
                  (level(0), 0.5),
                  ("t", self.timing["s6a"]["sentences"][1]["start"] + 3.6),
                  (Indicate(st.screen, color=None, scale_factor=1.08), 0.7),
                  (Indicate(st.buttons, color=None, scale_factor=1.15), 0.7),
                  (Indicate(st.cells, color=None, scale_factor=1.15), 0.7))

        wall = VMobject(stroke_color=GREY_D, stroke_width=3).set_points_as_corners(
            [[-6.3, -2.5, 0], [-6.3, 1.0, 0], [-0.5, 1.0, 0], [-0.5, -2.5, 0]])
        mx = -1.3
        mst = Line([mx, 1.0, 0], [mx, 2.1, 0], stroke_color=WHITE, stroke_width=5)
        jack = st.jack.get_center()
        cable = VMobject(stroke_color=GREY_B, stroke_width=3).set_points_as_corners(
            [jack, [jack[0], 0.7, 0], [mx, 0.7, 0], [mx, 1.0, 0]])
        ant_l = T("antena na zewnątrz, możliwie wysoko", 22, GREY_A).next_to(mst.get_end(), UR, buff=0.25).shift(RIGHT * 0.5)
        waves = wifi(mst.get_end(), 0.22, 3, RADIO, angle=0)
        bars = VGroup(*[Rectangle(width=0.07, height=0.06 * (k + 1), stroke_width=0, fill_color="#1b2027",
                                  fill_opacity=1) for k in range(4)]).arrange(RIGHT, buff=0.04, aligned_edge=DOWN)
        online = VGroup(T("w sieci", 22, "#1b2027"), bars).arrange(RIGHT, buff=0.15).move_to(st.screen)
        self.narr("s6b",
                  (st.screen.animate.set_fill("#c8d0c2"), 0.6),
                  ([Create(wall), Create(cable), Create(mst), FadeIn(ant_l)], 1.2),
                  ([LaggedStart(*[Create(w) for w in waves], lag_ratio=0.3), FadeIn(online)], 0.8))

        op = person(0.8).move_to([-5.5, -0.5, 0])
        op_l = label2(["ty lub", "opiekun"], 20).next_to(op, DOWN, buff=0.15)
        need = VGroup(T("woda, leki", 22, "#1b2027"), T("50 osób", 22, "#1b2027")).arrange(DOWN, buff=0.1)
        need.move_to(st.screen)
        top = mst.get_end()
        n1, n2 = np.array([4.3, 1.7, 0]), np.array([5.0, -1.2, 0])
        nbs = VGroup(*[VGroup(Circle(radius=0.26, stroke_color=RADIO, stroke_width=3).move_to(c),
                              Dot(c, radius=0.13, color=RADIO)) for c in (n1, n2)])
        nb_l = VGroup(T("sąsiednia stacja", 20, RADIO).next_to(nbs[0], RIGHT, buff=0.2),
                      T("w stronę służb", 20, RADIO).next_to(nbs[1], DOWN, buff=0.2))
        # sygnał biegnie po linii łączącej stacje, zamiast przelatującego punktu
        l_out = Line(top, n2, buff=0.3, stroke_color=GREY_D, stroke_width=2)
        l_in = Line(n1, top, buff=0.3, stroke_color=GREY_D, stroke_width=2)
        l_nb = Line(n1, n2, buff=0.3, stroke_color=GREY_D, stroke_width=2)

        def pulse(line, color, back=False):
            ln = line.copy().set_stroke(color, width=6)
            return ShowPassingFlash(ln.reverse_points() if back else ln, time_width=0.5)
        self.narr("s6c",
                  ([FadeIn(op, shift=RIGHT * 0.2), FadeIn(op_l)], 0.6),
                  ([Indicate(st.buttons, color=ACCENT, scale_factor=1.15), FadeOut(online), FadeIn(need)], 1.0),
                  ([FadeIn(nbs), FadeIn(nb_l), Create(l_out), Create(l_in), Create(l_nb)], 0.6),
                  (pulse(l_out, ACCENT), 0.8),
                  (pulse(l_out, OK, back=True), 0.8),
                  ("at", 1),
                  (pulse(l_in, ACCENT, back=True), 0.55),
                  (pulse(l_nb, ACCENT), 0.55),
                  (pulse(l_nb, OK, back=True), 0.55),
                  (pulse(l_in, OK), 0.55))

        # rozszerzenia: laptop i router, zasilane przez przetwornice z zestawu
        sx, sy, sw = 3.6, 0.9, 1.9
        lp = laptop().move_to([-0.5, 1.1, 0])
        base_y = lp[2].get_y()
        rt = router()
        rt.shift([-3.3 - rt[0].get_x(), base_y - rt[0].get_y(), 0])
        rt_l = T("router", 22, GREY_A).next_to(rt[0], DOWN, buff=0.25)
        lp_l = T("stary laptop", 22, GREY_A).next_to(lp, DOWN, buff=0.25)
        st_small = st.copy()
        st_small.scale_to_fit_width(sw).move_to([sx, sy, 0])
        st_small[1].set_fill("#c8d0c2")
        need_small = need.copy().scale(sw / 3.0).move_to(st_small[1])
        st_l2 = T("stacja WICI", 22, GREY_A).next_to(st_small, DOWN, buff=0.2)
        jx, jy = st_small[4].get_center()[:2]
        stub = Line([jx, jy, 0], [jx, jy + 0.9, 0], stroke_color=WHITE, stroke_width=4)
        usb = Line([lp[2].get_right()[0], base_y, 0], [st_small[0].get_left()[0], base_y, 0],
                   stroke_color=GREY_B, stroke_width=3)
        eth = Line(rt[0].get_right(), lp[2].get_left(), stroke_color=GREY_B, stroke_width=3)
        old = VGroup(wall, cable, mst, ant_l, waves, op, op_l, nbs, nb_l, l_out, l_in, l_nb)
        big = phone(2.0).move_to([-6.0, 1.0, 0])
        wf = wifi(rt[1][0].get_end() + UP * 0.05, 0.16, 3, WHITE, angle=PI * 0.8)
        form = VGroup(logo(0.62),
                      *[Rectangle(width=0.7, height=0.12, stroke_color=GREY_B, stroke_width=1) for _ in range(3)],
                      RoundedRectangle(width=0.48, height=0.16, corner_radius=0.05, stroke_width=0,
                                       fill_color=ACCENT, fill_opacity=1)).arrange(DOWN, buff=0.12)
        form.next_to(big.bars, DOWN, buff=0.15).set_x(big.screen.get_x())
        nos = VGroup(crossed("aplikacja", 26), crossed("konto", 26), crossed("internet", 26)).arrange(RIGHT, buff=0.6)
        nos.move_to([lp.get_x(), (lp.get_top()[1] + title.get_bottom()[1]) / 2, 0])
        self.narr("s6d",
                  ([FadeOut(old), FadeOut(st_l), Transform(st, st_small), Transform(need, need_small)], 1.0),
                  ([FadeIn(st_l2), Create(stub), FadeIn(lp, shift=UP * 0.2), FadeIn(lp_l), *level(1)], 0.8),
                  (Create(usb), 0.6),
                  ("at", 1),
                  ([FadeIn(rt, shift=UP * 0.2), FadeIn(rt_l), Create(eth), *level(2)], 0.8),
                  ([FadeIn(big, shift=RIGHT * 0.2), Create(wf)], 0.8),
                  (FadeIn(form, lag_ratio=0.2), 0.7),
                  ("at", 2),
                  ([LaggedStart(*[AnimationGroup(FadeIn(n[0]), Create(n[1])) for n in nos], lag_ratio=0.5)], 1.4))

        ry = -1.3
        inv = inverter(1.3).move_to([-1.0, ry, 0])
        inv_l = label2(["przetwornica", "12 V → 230 V"]).next_to(inv, DOWN, buff=0.15)
        bat_a = Battery(1.0, 0.48).move_to([1.6, ry, 0])
        bat_a_l = label2(["akumulator", "samochodowy"]).next_to(bat_a.box, DOWN, buff=0.15)
        chg = charger(1.3).move_to([-6.0, ry, 0])
        chg_l = label2(["ładowarka", "telefonów"]).next_to(chg, DOWN, buff=0.15)
        bat_c = Battery(1.0, 0.48).move_to([-3.7, ry, 0])
        bat_c_l = label2(["drugi akumulator", "samochodowy"]).next_to(bat_c.box, DOWN, buff=0.15)
        PW = dict(stroke_color=ORANGE, stroke_width=3)
        it = inv[0].get_top()[1]
        w_a = Line(bat_a.box.get_left(), inv[0].get_right(), **PW)
        rx, lx = rt[0].get_x() + 0.5, lp.get_x() + 1.03
        w_rt = VMobject(**PW).set_points_as_corners(
            [[inv.get_x() - 0.25, it, 0], [inv.get_x() - 0.25, -0.5, 0], [rx, -0.5, 0], [rx, rt[0].get_bottom()[1], 0]])
        w_lp = VMobject(**PW).set_points_as_corners(
            [[inv.get_x() + 0.25, it, 0], [inv.get_x() + 0.25, -0.5, 0], [lx, -0.5, 0], [lx, lp[2].get_bottom()[1], 0]])
        stx = st_small[0].get_right()[0] + 0.3
        w_st = VMobject(**PW).set_points_as_corners(
            [[inv.get_x() + 0.5, it, 0], [inv.get_x() + 0.5, -0.72, 0], [stx, -0.72, 0], [stx, sy - 0.2, 0],
             [st_small[0].get_right()[0], sy - 0.2, 0]])
        w_c = Line(bat_c.box.get_left(), chg[0].get_right(), **PW)
        w_ph = Line([big.get_x(), chg[0].get_top()[1], 0], big.get_bottom(), **PW)
        key = VGroup(
            VGroup(RoundedRectangle(width=0.36, height=0.26, corner_radius=0.05, stroke_color=ACCENT, stroke_width=3),
                   T("zestaw WICI", 22, ACCENT)).arrange(RIGHT, buff=0.2),
            VGroup(RoundedRectangle(width=0.36, height=0.26, corner_radius=0.05, stroke_color=GREY_A, stroke_width=3),
                   T("z lokalnego zasobu", 22, GREY_A)).arrange(RIGHT, buff=0.2),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.25).move_to([4.9, -1.35, 0])
        self.narr("s6e",
                  ([FadeIn(bat_a), FadeIn(bat_a_l), FadeIn(inv), FadeIn(inv_l), FadeIn(key[0])], 0.8),
                  ([Create(w_a), Create(w_st), Create(w_rt), Create(w_lp)], 1.0),
                  (FadeIn(key[1]), 0.5),
                  ("at", 1),
                  ([FadeIn(bat_c), FadeIn(bat_c_l), FadeIn(chg), FadeIn(chg_l)], 0.8),
                  ([Create(w_c), Create(w_ph)], 0.9))
        self.clear_all()

    def part_statuses(self):
        head = T("uczciwe komunikaty", 44, WHITE, font=SERIF).to_edge(UP, buff=0.7)
        a = T("„wysłane”", 52, WHITE, font=SERIF)
        neq = T("≠", 72, ALERT)
        b = T("„pomoc jedzie”", 52, WHITE, font=SERIF)
        ineq = VGroup(a, neq, b).arrange(RIGHT, buff=0.5).shift(UP * 0.2)
        self.narr("s7a", (FadeIn(head), 1.0), ("at", 1),
                  (FadeIn(a, shift=RIGHT * 0.2), 0.6), (GrowFromCenter(neq), 0.4),
                  (FadeIn(b, shift=LEFT * 0.2), 0.6))

        labels = [("zapisane", "lokalnie"), ("zapisane", "u odbiorcy"), ("przeczytane", "przez dyżurnego"),
                  ("pomoc", "skierowana")]
        who = ["stacja w schronieniu", "odbiorca w służbach", "dyżurny", "decyzja"]
        colors = [ACCENT, RADIO, BLUE_C, OK]
        chips = VGroup()
        for (l1, l2), c in zip(labels, colors):
            box = RoundedRectangle(width=3.05, height=1.3, corner_radius=0.15, stroke_color=GREY_D,
                                   stroke_width=3, fill_color=c, fill_opacity=0)
            txt = VGroup(T(l1, 24, GREY_C), T(l2, 24, GREY_C)).arrange(DOWN, buff=0.08).move_to(box)
            chips.add(VGroup(box, txt))
        chips.arrange(RIGHT, buff=0.42).shift(DOWN * 0.3)
        arrows = VGroup(*[Arrow(chips[i].get_right(), chips[i + 1].get_left(), buff=0.06,
                                stroke_width=3, color=GREY_C, max_tip_length_to_length_ratio=0.35)
                          for i in range(3)])
        nums = VGroup(*[T(str(i + 1), 24, GREY_C).next_to(ch, UP, buff=0.15) for i, ch in enumerate(chips)])
        who_l = VGroup(*[T(w, 20, GREY_B).next_to(ch, DOWN, buff=0.2) for w, ch in zip(who, chips)])

        def light(i):
            box, txt = chips[i]
            c = colors[i]
            return ([box.animate.set_stroke(c).set_fill(c, 0.15), txt.animate.set_color(WHITE),
                     nums[i].animate.set_color(c), FadeIn(who_l[i], shift=UP * 0.1),
                     Create(check(0.26, c).next_to(nums[i], RIGHT, buff=0.15))], 0.6)

        self.narr("s7b",
                  ([FadeOut(ineq, shift=UP * 0.3), FadeIn(chips, lag_ratio=0.1), FadeIn(arrows), FadeIn(nums)], 1.2),
                  ("at", 1), light(0), ("at", 2), light(1), ("at", 3), light(2), ("at", 4), light(3))

        man = person(0.9, OK).next_to(who_l[3], DOWN, buff=0.25)
        human = T("decyduje człowiek", 26, OK).next_to(man, LEFT, buff=0.3)
        VGroup(man, human).next_to(who_l, DOWN, buff=0.5).set_x(0)
        self.narr("s7c",
                  ([LaggedStart(*[Indicate(c, scale_factor=1.05, color=None) for c in chips], lag_ratio=0.25)], 1.6),
                  ("at", 1),
                  ([FadeIn(man, shift=UP * 0.2), FadeIn(human)], 0.8))
        self.clear_all()

    def part_status(self):
        head = T("Gdzie jesteśmy?", 48, WHITE, font=SERIF).to_edge(UP, buff=0.6)
        done = ["koncepcja", "specyfikacja", "płytka do pomiarów radia", "wszystko otwarte:\nschematy, kod, dokumentacja"]
        left = VGroup()
        for s in done:
            left.add(VGroup(check(0.28), T(s, 28, WHITE, line_spacing=0.8)).arrange(RIGHT, buff=0.25, aligned_edge=UP))
        left.arrange(DOWN, aligned_edge=LEFT, buff=0.32).move_to(LEFT * 3.3 + UP * 0.1)
        lh = T("zrobione", 26, OK).next_to(left, UP, buff=0.45).align_to(left, LEFT)
        self.narr("s8a", (FadeIn(head), 0.9), ("at", 1),
                  ([FadeIn(lh), LaggedStart(*[FadeIn(r, shift=RIGHT * 0.2) for r in left[:3]], lag_ratio=0.5)], 2.0),
                  ("at", 2), (FadeIn(left[3], shift=RIGHT * 0.2), 0.7))

        todo = ["1 km wśród budynków?", "dwie doby na bateriach?", "sieć w małym układzie?"]
        right = VGroup(*[VGroup(T("?", 30, ACCENT, weight=HEAVY), T(s, 28, WHITE))
                         .arrange(RIGHT, buff=0.3) for s in todo])
        right.arrange(DOWN, aligned_edge=LEFT, buff=0.32).move_to(RIGHT * 3.4).align_to(left, UP)
        rh = T("niesprawdzone w terenie", 26, ACCENT).align_to(right, LEFT).align_to(lh, UP)
        self.narr("s8b", (FadeIn(rh), 0.7), ("at", 1), (FadeIn(right[0], shift=LEFT * 0.2), 0.6),
                  ("at", 2), (FadeIn(right[1], shift=LEFT * 0.2), 0.6),
                  ("at", 3), (FadeIn(right[2], shift=LEFT * 0.2), 0.6))

        motto = T("zmierzyć, a nie założyć", 40, ACCENT, font=SERIF).move_to(DOWN * 2.1)
        self.narr("s8c", (FadeIn(motto), 1.2))
        self.clear_all()

    def part_call(self):
        center = VGroup(Circle(radius=0.8, stroke_width=0, fill_color=config.background_color, fill_opacity=1),
                        Circle(radius=0.8, stroke_color=ACCENT, stroke_width=4, fill_color=ACCENT, fill_opacity=0.1),
                        logo(1.15))
        roles = [("krótkofalowcy", UP * 2.3 + LEFT * 4.2), ("elektronicy", UP * 2.3 + RIGHT * 4.2),
                 ("programiści", LEFT * 5.0 + DOWN * 0.4), ("służby", RIGHT * 5.0 + DOWN * 0.4)]
        nodes = VGroup()
        for name, p in roles:
            t = T(name, 28, WHITE)
            box = RoundedRectangle(width=t.width + 0.5, height=0.75, corner_radius=0.2, stroke_color=RADIO,
                                   stroke_width=3).move_to(p)
            nodes.add(VGroup(box, t.move_to(p)))
        edges = VGroup(*[Line(center.get_center(), n.get_center(), stroke_color=GREY_D, stroke_width=2,
                              buff=0.0) for n in nodes])
        edges.set_z_index(-1)
        for n in nodes:
            n[0].set_fill(config.background_color, 1)

        def add(i):
            return ([GrowFromCenter(nodes[i]), Create(edges[i])], 0.7)

        self.narr("s9a", (GrowFromCenter(center), 0.7), add(0), add(1), ("at", 1), add(2), ("at", 2), add(3))

        places = [("okno", DOWN * 2.4 + LEFT * 2.4), ("dach", DOWN * 2.4), ("piwnica", DOWN * 2.4 + RIGHT * 2.4)]
        small = VGroup()
        for name, p in places:
            t = T(name, 24, ACCENT)
            box = RoundedRectangle(width=t.width + 0.4, height=0.6, corner_radius=0.18, stroke_color=ACCENT,
                                   stroke_width=2, fill_color=config.background_color, fill_opacity=1).move_to(p)
            small.add(VGroup(box, t.move_to(p)))
        e2 = VGroup(*[Line(center.get_center(), s.get_center(), stroke_color=GREY_D, stroke_width=2)
                      for s in small]).set_z_index(-1)
        tests = T("próby w terenie", 24, GREY_B).next_to(small, DOWN, buff=0.2)
        self.narr("s9b", ([LaggedStart(*[AnimationGroup(GrowFromCenter(s), Create(e)) for s, e in zip(small, e2)],
                                       lag_ratio=0.35), FadeIn(tests)], 1.8))

        allm = VGroup(center, nodes, edges, small, e2, tests)
        url = T("github.com/tmierzwa/WICI", 54, WHITE, weight=SEMIBOLD)
        motto = T("Rozsyłamy wici!", 56, ACCENT, font=SERIF).next_to(url, UP, buff=1.0)
        hint = T("zajrzyj · zadaj pytanie · zgłoś błąd", 28, GREY_A).next_to(url, DOWN, buff=0.6)
        self.narr("s9c",
                  ([allm.animate.scale(0.3).set_opacity(0).move_to(UP * 2)], 1.0),
                  ([FadeIn(url)], 1.2),
                  ("at", 1), (FadeIn(hint, shift=UP * 0.2), 0.7),
                  ("at", 2), (FadeIn(motto), 1.0))
        self.wait(4.0)
        self.play(FadeOut(VGroup(url, motto, hint)), run_time=1.0)
        self.wait(0.5)
