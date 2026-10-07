"""Nakłada napisy z build/subs.json na film (libass) i zapisuje plik .srt.

Użycie: python napisy.py WEJŚCIE.mp4 WYJŚCIE.mp4 [plik.srt] [subs.json]
Kadr pionowy dostaje większe napisy, wyżej, nad interfejsem Reels/TikTok.
Wymaga ffmpeg z libass (Homebrew: ffmpeg-full).
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).parent
BUILD = HERE / "build"
FFMPEG = os.environ.get("FFMPEG", "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")

ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Avenir Next Medium,{size},&H00FFFFFF,&H00FFFFFF,&H5A000000,&H00000000,0,0,0,0,100,100,0,0,3,12,0,2,60,60,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ts(t, sep):
    ms = round(t * 1000)
    h, m, s = ms // 3600000, ms // 60000 % 60, ms // 1000 % 60
    if sep == ".":
        return f"{h}:{m:02}:{s:02}.{ms % 1000 // 10:02}"
    return f"{h:02}:{m:02}:{s:02},{ms % 1000:03}"


def main():
    src, dst = sys.argv[1], sys.argv[2]
    subs_json = Path(sys.argv[4]) if len(sys.argv) > 4 else BUILD / "subs.json"
    subs = json.loads(subs_json.read_text())["subs"]
    w, h = map(int, subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=width,height", "-of", "csv=p=0", src],
                                   capture_output=True, text=True, check=True).stdout.split(","))
    vertical = h > w
    head = ASS_HEAD.format(w=1080 if vertical else 1920, h=1920 if vertical else 1080, size=58 if vertical else 46, margin=540 if vertical else 46)
    ass = subs_json.parent / "napisy.ass"
    nl = r"\N"
    lines = [f"Dialogue: 0,{ts(a, '.')},{ts(b - 0.02, '.')},Default,,0,0,0,,"
             f"{nl.join(textwrap.wrap(t, 28 if vertical else 50))}" for a, b, t in subs]
    ass.write_text(head + "\n".join(lines) + "\n")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", src, "-vf", f"subtitles={ass}",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", dst], check=True)
    if len(sys.argv) > 3:
        with open(sys.argv[3], "w") as fh:
            for i, (a, b, t) in enumerate(subs, 1):
                fh.write(f"{i}\n{ts(a, ',')} --> {ts(b, ',')}\n{t}\n\n")
    print("gotowe:", dst)


if __name__ == "__main__":
    main()
