"""Znak WICI: Avenir Next Heavy, kropki nad I połączone sygnałem z impulsem.

Zapisuje znak w krzywych (SVG) na ciemne i jasne tło, ikonę oraz ich PNG.
Wymaga: macOS z fontem Avenir Next, pip install fonttools cairosvg.
"""

from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTCollection

HERE = Path(__file__).parent
FONT = TTCollection("/System/Library/Fonts/Avenir Next.ttc").fonts[8]  # Avenir Next Heavy
CAP = 708
LINE = 52  # grubość sygnału w jednostkach fontu (1000/em); czytelna jeszcze przy 24 px wysokości znaku
DOT = 1.06  # średnica kropki względem pnia I: koło wygląda na mniejsze od prostokąta tej samej szerokości
GAP = 70  # światło między górą I a kropką, zbliżone do światła między literami
KERN = {("I", "C"): -24, ("C", "I"): -14}  # optyczne odstępy: krągłe C bliżej pnia, otwarcie C daje światło
BG, WHITE, YELLOW = "#0f1216", "#ffffff", "#f4d345"  # tło, napis i akcent z filmu
INK_LIGHT, YELLOW_LIGHT = "#0f1216", "#c99a00"  # żółty przyciemniony, by nie znikał na jasnym tle


def contours(gs, name):
    rec = DecomposingRecordingPen(gs)
    gs[name].draw(rec)
    out, cur = [], []
    for op, args in rec.value:
        cur.append((op, args))
        if op in ("closePath", "endPath"):
            out.append(cur)
            cur = []
    return out


def replay(pen, ops):
    for op, args in ops:
        getattr(pen, op)(*args)


def pulse(a, b, yc, r, line):
    """Linia od a do b na wysokości yc z impulsem pośrodku; skala zależy od promienia kropki r.

    Szczyt impulsu (z grubością linii) kończy się równo z górą kropek.
    """
    u, d, w = r - line / 2, r * 0.32, r * 0.62
    m = (a + b) / 2 + 0.4 * w  # środek obrysu impulsu w połowie odcinka między kropkami
    return (f"M{a:.0f} {yc:.0f}H{m - 1.9 * w:.0f}L{m - 1.1 * w:.0f} {yc - u:.0f}L{m:.0f} {yc + d:.0f}"
            f"L{m + 0.7 * w:.0f} {yc - u * 0.4:.0f}L{m + 1.1 * w:.0f} {yc:.0f}H{b:.0f}")


def mark():
    gs, cmap, hmtx = FONT.getGlyphSet(), FONT.getBestCmap(), FONT["hmtx"]
    glyf = FONT["glyf"]
    ink, stems, x, prev = [], [], 0, None
    for ch in "WICI":
        name = cmap[ord(ch)]
        x += KERN.get((prev, ch), 0)
        prev = ch
        for ops in contours(gs, name):
            svg = SVGPathPen(gs)
            replay(TransformPen(svg, (1, 0, 0, -1, x, 0)), ops)  # oś y w dół, linia bazowa = 0
            ink.append(svg.getCommands())
        if ch == "I":
            stems.append((x + glyf[name].xMin, x + glyf[name].xMax))
        x += hmtx[name][0]
    stem = stems[0][1] - stems[0][0]
    r = stem * DOT / 2
    yc = -(CAP + GAP + r)
    centers = [(s0 + s1) / 2 for s0, s1 in stems]
    dots = "".join(f'<circle cx="{c:.0f}" cy="{yc:.0f}" r="{r:.0f}"/>' for c in centers)
    top = yc - r
    right = x - hmtx[cmap[ord("I")]][1]
    view = f"-40 {top - 40:.0f} {right + 80:.0f} {-top + 80:.0f}"
    sig = pulse(centers[0] + r, centers[1] - r, yc, r, LINE)
    line = f"M{centers[0]:.0f} {yc:.0f}H{centers[0] + r:.0f}M{centers[1] - r:.0f} {yc:.0f}H{centers[1]:.0f}"
    return view, " ".join(ink), dots, sig + line


def logo_svg(view, ink, dots, sig, fg, accent):
    # sygnał pod kropkami, wchodzi do ich środków: bez płaskich końców na krągłej krawędzi
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" role="img" aria-label="WICI">'
            f'<path fill="none" stroke="{accent}" stroke-width="{LINE}" stroke-linejoin="round" d="{sig}"/>'
            f'<path fill="{fg}" d="{ink}"/><g fill="{fg}">{dots}</g></svg>\n')


def icon_svg():
    # te same kropki i sygnał co w znaku; linia grubsza względem kropki, by została widoczna przy 32 px
    r, line, y, a, b = 56, 32, 256, 92, 420
    sig = pulse(a + r, b - r, y, r, line) + f"M{a} {y}H{a + r}M{b - r} {y}H{b}"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="WICI">'
            f'<rect width="512" height="512" rx="104" fill="{BG}"/>'
            f'<path fill="none" stroke="{YELLOW}" stroke-width="{line}" stroke-linejoin="round" d="{sig}"/>'
            f'<circle cx="{a}" cy="{y}" r="{r}" fill="{WHITE}"/><circle cx="{b}" cy="{y}" r="{r}" fill="{WHITE}"/></svg>\n')


def main():
    import cairosvg

    view, ink, dots, sig = mark()
    files = {
        "WICI-na-ciemnym.svg": logo_svg(view, ink, dots, sig, WHITE, YELLOW),
        "WICI-na-jasnym.svg": logo_svg(view, ink, dots, sig, INK_LIGHT, YELLOW_LIGHT),
        "ikona.svg": icon_svg(),
    }
    for name, svg in files.items():
        (HERE / name).write_text(svg, encoding="utf-8")
    for name in ("WICI-na-ciemnym", "WICI-na-jasnym"):
        cairosvg.svg2png(url=str(HERE / f"{name}.svg"), write_to=str(HERE / f"{name}.png"), output_width=2400)
    for size in (512, 180, 32):
        cairosvg.svg2png(url=str(HERE / "ikona.svg"), write_to=str(HERE / f"ikona-{size}.png"),
                         output_width=size, output_height=size)


if __name__ == "__main__":
    main()
