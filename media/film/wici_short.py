"""Pionowa wersja ~60 s (1080×1920) na Reels i TikTok.

Wymaga: python tts.py narracja_short build/short
Render: manim --resolution 1080,1920 --frame_rate 30 --disable_caching --media_dir build/media wici_short.py Short
Grafika zajmuje górne ~60% kadru; napisy (napisy.py) leżą nad interfejsem aplikacji.
"""

import json

from wici_film import *  # ikony, kolory, T(), klasa WICI z narracją i napisami

config.frame_height = 14.222
config.frame_width = 8.0

SHORT = HERE / "build" / "short"


class Short(WICI):
    timing = json.loads((SHORT / "timing.json").read_text())
    audio, out = SHORT / "audio", SHORT
    seg_gap, sub_chunk = 0.2, 54

    def construct(self):
        random.seed(5)
        self.blackout()
        self.shelter()
        self.title()
        self.message()
        self.hops()
        self.station()
        self.call()
        self.write_subs()

    def blackout(self):
        houses = VGroup(*[house(0.75 + 0.2 * random.random(), 0.6 + 0.15 * random.random())
                          for _ in range(5)]).arrange(RIGHT, buff=0.45, aligned_edge=DOWN).move_to(UP * 4.8)
        ground = Line(LEFT * 4.2, RIGHT * 4.2, stroke_color=GREY_D).next_to(houses, DOWN, buff=0)
        glows = VGroup(*[Circle(radius=0.38, stroke_width=0, fill_color=ACCENT, fill_opacity=0.14).move_to(h.window)
                         for h in houses])
        ph = phone(3.4).move_to(UP * 1.2)
        nosig = T("brak\nsieci", 40, ALERT).move_to(ph.screen)
        self.narr("v1",
                  ([FadeIn(houses, lag_ratio=0.1), FadeIn(glows), Create(ground)], 0.8),
                  ([LaggedStart(*[AnimationGroup(h.window.animate.set_fill(GREY_E), FadeOut(g))
                                  for h, g in zip(houses, glows)], lag_ratio=0.2)], 1.2),
                  ("at", 1),
                  ([VGroup(houses, ground).animate.set_opacity(0.25), FadeIn(ph, shift=UP * 0.4)], 0.8),
                  ([LaggedStart(*[FadeOut(b) for b in reversed(ph.bars)], lag_ratio=0.4)], 1.0),
                  (Write(nosig), 0.5))
        self.clear_all(0.3)

    def shelter(self):
        school = building(3.6, 2.0, GREY_A, "schronienie").move_to(UP * 3.6)
        dots = VGroup(*[Dot(radius=0.065, color=WHITE) for _ in range(50)]).arrange_in_grid(5, 10, buff=0.17)
        dots.move_to(school.body)
        need = VGroup(VGroup(drop(), T("woda", 30, WATER)).arrange(RIGHT, buff=0.2),
                      VGroup(pill(), T("leki", 30, ALERT)).arrange(RIGHT, buff=0.2)).arrange(RIGHT, buff=0.8)
        need.next_to(school[1], UP, buff=0.35)
        osp = building(2.2, 1.6, ALERT, "straż", door=True).move_to(DOWN * 0.9)
        link = DashedLine(school.body.get_bottom() + DOWN * 0.75, osp[1].get_top() + UP * 0.2,
                          stroke_color=GREY_B, dash_length=0.12)
        km = T("kilka km", 28, GREY_B).next_to(link, RIGHT, buff=0.35)
        q = T("?", 100, ACCENT, font=SERIF).next_to(link, LEFT, buff=0.4)
        self.narr("v2",
                  ([Create(school, lag_ratio=0.1), LaggedStart(*[GrowFromCenter(d) for d in dots], lag_ratio=0.02)], 1.2),
                  ([FadeIn(need, shift=DOWN * 0.3, lag_ratio=0.4)], 0.8),
                  ("at", 1),
                  ([FadeIn(osp, shift=UP * 0.3), Create(link), FadeIn(km)], 1.0),
                  (Write(q), 0.5))
        self.clear_all(0.3)

    def title(self):
        self.add_sound(str(SFX_TITLE), gain=-11)
        name = T("WICI", 120, WHITE, weight=HEAVY).move_to(UP * 2.6)
        sub = VGroup(T("sieć łączności na czas,", 34, GREY_B), T("gdy nic nie działa", 34, GREY_B))
        sub.arrange(DOWN, buff=0.15).next_to(name, DOWN, buff=0.4)
        self.play(Write(name), run_time=0.9)
        self.play(FadeIn(sub, shift=UP * 0.2), run_time=0.6)
        self.wait(0.4)
        self.play(FadeOut(VGroup(name, sub)), run_time=0.4)

    def message(self):
        card = RoundedRectangle(width=7.4, height=3.3, corner_radius=0.15, stroke_color=GREY_B,
                                fill_color="#171c22", fill_opacity=1).move_to(UP * 3.6)
        head = T("ZGŁOSZENIE", 28, ACCENT, weight=HEAVY).move_to(card.get_top() + DOWN * 0.45)
        rows = VGroup(*[T(f"{k}  {v}", 25, WHITE, t2c={k: GREY_B}) for k, v in
                        [("Gdzie:", "szkoła, ul. Polna 3, wejście od boiska"), ("Ile osób:", "50"),
                         ("Czego brakuje:", "woda, leki"), ("Pilność:", "wysoka")]])
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.26).next_to(head, DOWN, buff=0.35).align_to(card, LEFT).shift(RIGHT * 0.4)
        small = Square(0.5, stroke_width=0, fill_color=ACCENT, fill_opacity=0.95).move_to(UP * 4.4)
        lbl = T("mniej niż 200 bajtów", 34, ACCENT).next_to(small, DOWN, buff=0.35)
        net = crossed("internet", 34).move_to(UP * 2.4)
        ra = radio_module(1.6).move_to(LEFT * 1.6 + DOWN * 0.4)
        ant = Line(ra.get_top(), ra.get_top() + UP * 1.4, stroke_color=GREY_A, stroke_width=5)
        bat = Battery(1.4, 0.65, label="akumulator")
        bat.shift(RIGHT * 1.9 + UP * (ra.get_y() - bat.box.get_y()))
        wire = Line(ra.get_right(), bat.box.get_left(), stroke_color=GREY_B, stroke_width=3)
        waves = VGroup(*[Arc(radius=0.3 * i, start_angle=PI / 4, angle=PI / 2, stroke_color=RADIO, stroke_width=4)
                         .move_arc_center_to(ant.get_end()) for i in (1, 2, 3)])
        self.narr("v3",
                  ([FadeIn(card), Write(head), LaggedStart(*[FadeIn(r) for r in rows], lag_ratio=0.3)], 1.0),
                  ([ReplacementTransform(VGroup(card, head, rows), small)], 0.9),
                  (FadeIn(lbl, shift=UP * 0.2), 0.4),
                  ("at", 1),
                  ([FadeIn(net[0]), Create(net[1])], 0.6),
                  ([FadeIn(ra), Create(ant), FadeIn(bat), Create(wire)], 0.8),
                  ([LaggedStart(*[Create(w) for w in waves], lag_ratio=0.3)], 0.7))
        self.clear_all(0.3)

    def hops(self):
        R = 2.7
        pos = {"A": np.array([-2.5, -1.2, 0]), "B": np.array([-1.0, 0.85, 0]),
               "C": np.array([0.55, 2.9, 0]), "OSP": np.array([2.1, 4.95, 0])}
        blocks = VGroup(*[Rectangle(width=random.uniform(0.15, 0.4), height=random.uniform(0.12, 0.3), stroke_width=0,
                                    fill_color=GREY_D, fill_opacity=0.5)
                          .move_to([random.uniform(-3.9, 3.9), random.uniform(-1.9, 6.0), 0]) for _ in range(110)])

        def node(name, color, label=None, side=RIGHT):
            g = VGroup(Circle(radius=0.3, stroke_color=color, stroke_width=3).move_to(pos[name]),
                       Dot(pos[name], radius=0.16, color=color))
            if label:
                g.add(T(label, 28, color).next_to(g[0], side, buff=0.25))
            return g

        A, OSP = node("A", ACCENT, "schronienie"), node("OSP", ALERT, "straż", LEFT)
        rng = Circle(radius=R, stroke_color=RADIO, stroke_width=2, fill_color=RADIO, fill_opacity=0.07).move_to(pos["A"])
        rng_l = T("około 1 km?", 30, RADIO).move_to(pos["A"] + np.array([0.7, 1.35, 0]))
        mids = {n: node(n, RADIO) for n in ("B", "C")}
        rings = VGroup(*[Circle(radius=R, stroke_color=RADIO, stroke_width=1.2, stroke_opacity=0.35).move_to(pos[n])
                         for n in ("B", "C")])
        chain = ["A", "B", "C", "OSP"]
        links = VGroup(*[Line(pos[a], pos[b], stroke_color=GREY_B, stroke_width=2.5, buff=0.34)
                         for a, b in zip(chain, chain[1:])])
        msg = Square(0.22, stroke_width=0, fill_color=ACCENT, fill_opacity=1).move_to(pos["A"])
        word = T("wici", 72, ACCENT, font=SERIF).move_to([-1.9, 5.0, 0])
        self.narr("v4",
                  ([FadeIn(blocks, lag_ratio=0.01), FadeIn(A), FadeIn(OSP), GrowFromCenter(rng), FadeIn(rng_l)], 1.2),
                  ("at", 1),
                  ([FadeOut(rng_l), rng.animate.set_fill(opacity=0).set_stroke(opacity=0.35, width=1.2),
                    FadeIn(mids["B"]), FadeIn(mids["C"]), Create(rings), Create(links)], 0.9),
                  (FadeIn(msg), 0.15),
                  *[([MoveAlongPath(msg, ArcBetweenPoints(pos[a], pos[b], angle=-PI / 5)),
                      Flash(pos[b], color=RADIO, line_length=0.2, flash_radius=0.4)], 0.6)
                    for a, b in zip(chain, chain[1:])],
                  (Create(check(0.45).next_to(OSP[1], DR, buff=0.2)), 0.3),
                  ("at", 2),
                  (Write(word), 0.7))
        self.clear_all(0.3)

    def station(self):
        rt = router(1.3).move_to([1.5, 5.0, 0])
        rt_l = T("router", 26, GREY_A).next_to(rt[0], RIGHT, buff=0.3)
        ph = phone(2.0).move_to([-2.2, 4.8, 0])
        wf = wifi(rt[1][0].get_end() + UP * 0.05, 0.17, 3, WHITE, angle=PI * 0.85)
        lp = laptop(1.6).move_to([1.5, 2.6, 0])
        lp_l = T("stary laptop", 26, GREY_A).next_to(lp, LEFT, buff=0.6)
        rm = radio_module(1.1).move_to([1.5, 0.45, 0])
        rm_l = T("moduł radiowy", 26, RADIO).next_to(rm, LEFT, buff=0.35)
        ax = 3.3
        cable = VMobject(stroke_color=GREY_B, stroke_width=3).set_points_as_corners(
            [rm.get_right(), [ax, rm.get_y(), 0], [ax, 1.3, 0]])
        ant = Line([ax, 1.3, 0], [ax, 2.1, 0], stroke_color=WHITE, stroke_width=5)
        waves = wifi(ant.get_end(), 0.18, 3, RADIO, angle=PI / 2)
        bat = Battery(1.1, 0.5, label="akumulator 12 V").move_to([-1.6, -0.9, 0])
        eth = Line(rt[0].get_bottom(), lp[0].get_top(), stroke_color=GREY_B, stroke_width=3)
        usb = Line(lp[2].get_bottom(), rm.get_top(), stroke_color=GREY_B, stroke_width=3)
        p1 = VMobject(stroke_color=ACCENT, stroke_width=2).set_points_as_corners(
            [bat.box.get_top(), [bat.box.get_x(), 1.6, 0], [0.95, 1.6, 0], [0.95, lp[2].get_bottom()[1], 0]])
        p2 = VMobject(stroke_color=ACCENT, stroke_width=2).set_points_as_corners(
            [bat.box.get_right(), [rm.get_x(), bat.box.get_y(), 0], rm.get_bottom()])
        p3 = VMobject(stroke_color=ACCENT, stroke_width=2).set_points_as_corners(
            [[0.15, 1.6, 0], [0.15, rt[0].get_y(), 0], rt[0].get_left()])
        form = VGroup(T("WICI", 15, ACCENT, weight=HEAVY),
                      *[Rectangle(width=0.7, height=0.12, stroke_color=GREY_B, stroke_width=1) for _ in range(3)],
                      RoundedRectangle(width=0.5, height=0.16, corner_radius=0.05, stroke_width=0, fill_color=ACCENT,
                                       fill_opacity=1)).arrange(DOWN, buff=0.1)
        form.next_to(ph.bars, DOWN, buff=0.12).set_x(ph.screen.get_x())
        noapp = crossed("aplikacja", 30).next_to(ph, DOWN, buff=0.35)
        self.narr("v5",
                  ([FadeIn(lp, shift=UP * 0.2), FadeIn(lp_l)], 0.6),
                  ([FadeIn(rt, shift=UP * 0.2), FadeIn(rt_l), Create(eth)], 0.6),
                  ([FadeIn(bat), Create(p1), Create(p3)], 0.6),
                  ([FadeIn(rm), FadeIn(rm_l), Create(usb), Create(p2), Create(cable), Create(ant)], 0.8),
                  ([LaggedStart(*[Create(w) for w in waves], lag_ratio=0.3)], 0.5),
                  ("at", 1),
                  ([FadeIn(ph, shift=RIGHT * 0.2), Create(wf)], 0.6),
                  (FadeIn(form, lag_ratio=0.2), 0.6),
                  ([FadeIn(noapp[0]), Create(noapp[1])], 0.6))
        self.clear_all(0.3)

    def call(self):
        ok = VGroup(check(0.4), T("otwarte", 40, WHITE)).arrange(RIGHT, buff=0.3)
        todo = VGroup(T("?", 44, ACCENT, weight=HEAVY), T("niesprawdzone w terenie", 40, WHITE)).arrange(RIGHT, buff=0.3)
        state = VGroup(ok, todo).arrange(DOWN, aligned_edge=LEFT, buff=0.4).move_to(UP * 4.6)
        chips = VGroup()
        for name in ["krótkofalowcy", "elektronicy", "programiści", "straż"]:
            t = T(name, 30, WHITE)
            box = RoundedRectangle(width=3.5, height=0.9, corner_radius=0.22, stroke_color=RADIO, stroke_width=3)
            chips.add(VGroup(box, t.move_to(box)))
        chips.arrange_in_grid(2, 2, buff=(0.35, 0.35)).move_to(UP * 1.3)
        self.narr("v6",
                  ([FadeIn(ok, shift=RIGHT * 0.2)], 0.6),
                  ([FadeIn(todo, shift=RIGHT * 0.2)], 0.6),
                  ("at", 1),
                  ([LaggedStart(*[GrowFromCenter(c) for c in chips], lag_ratio=0.3)], 1.6))
        self.clear_all(0.3)

        motto = T("Rozsyłamy wici.", 60, ACCENT, font=SERIF).move_to(UP * 3.9)
        url = T("github.com/tmierzwa/WICI", 40, WHITE, weight=SEMIBOLD).move_to(UP * 2.3)
        url2 = T("tmierzwa.github.io/WICI", 30, GREY_B).next_to(url, DOWN, buff=0.3)
        self.narr("v7", ([Write(url), FadeIn(url2)], 1.0), ("at", 1), (Write(motto), 0.8))
        self.wait(1.6)
