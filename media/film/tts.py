"""Generuje narrację ElevenLabs: zdania -> segmenty WAV + timing.json.

Klucz: zmienna ELEVENLABS_API_KEY albo plik wskazany w ELEVENLABS_ENV.
Zdania są buforowane w build/tts/<hash>.mp3, więc ponowne uruchomienie
generuje tylko zmienione zdania.
"""

import array
import base64
import hashlib
import json
import os
import subprocess
import urllib.request
import wave
from pathlib import Path

import importlib
import sys

HERE = Path(__file__).parent
BUILD = HERE / "build"
CACHE = BUILD / "tts"
# python tts.py [moduł_narracji] [katalog_wyjściowy]; domyślnie film główny
NARRATION = sys.argv[1] if len(sys.argv) > 1 else "narracja"
OUT = HERE / (sys.argv[2] if len(sys.argv) > 2 else "build")
AUDIO = OUT / "audio"
SEGMENTS = importlib.import_module(NARRATION).SEGMENTS

VOICE_ID = os.environ.get("WICI_VOICE", "JBFqnCBsd6RMkjVDRZzb")  # George
MODEL = "eleven_multilingual_v2"
SETTINGS = {"stability": 0.55, "similarity_boost": 0.75, "style": 0.1, "speed": 1.05}
RATE = 44100
GAP_SENTENCE = 0.4
LEAD_IN = 0.15
TAIL = 0.12  # oddech po ostatniej literze zdania


def api_key():
    key = os.environ.get("ELEVENLABS_API_KEY")
    if key:
        return key
    env = os.environ.get("ELEVENLABS_ENV")
    for line in Path(env).read_text().splitlines():
        if line.startswith("ELEVENLABS_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("brak ELEVENLABS_API_KEY")


def synth(text, prev, key):
    """Zwraca PCM zdania przycięty do końca ostatniej litery (znaczniki czasu ElevenLabs)."""
    payload = {"text": text, "model_id": MODEL, "language_code": "pl",
               "voice_settings": SETTINGS, "previous_text": prev}
    h = hashlib.sha1(json.dumps([VOICE_ID, payload], ensure_ascii=False).encode()).hexdigest()[:16]
    cached = CACHE / f"{h}.json"
    if not cached.exists():
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/with-timestamps?output_format=mp3_44100_128",
            data=json.dumps(payload).encode(),
            headers={"xi-api-key": key, "Content-Type": "application/json"})
        cached.write_bytes(urllib.request.urlopen(req, timeout=120).read())
        print("  tts:", text[:60])
    d = json.loads(cached.read_text())
    mp3 = CACHE / f"{h}.mp3"
    if not mp3.exists():
        mp3.write_bytes(base64.b64decode(d["audio_base64"]))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "s16le", "-ac", "1",
                          "-ar", str(RATE), "-"], capture_output=True, check=True).stdout
    al = d["alignment"]
    letters = [i for i, c in enumerate(al["characters"]) if c.isalnum()]
    start = max(0.0, al["character_start_times_seconds"][letters[0]] - 0.04)
    end = al["character_end_times_seconds"][letters[-1]] + TAIL
    return cut(raw, start, end)


def cut(raw, start, end, fade=0.04):
    a = array.array("h", raw)
    i, j = int(start * RATE), min(len(a), int(end * RATE))
    a = a[i:j]
    n = int(fade * RATE)
    for k in range(min(n, len(a))):
        a[k] = int(a[k] * k / n)
        a[-1 - k] = int(a[-1 - k] * k / n)
    return a.tobytes()


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    AUDIO.mkdir(parents=True, exist_ok=True)
    key = api_key()
    flat = [(s if isinstance(s, str) else s[1]) for _, ss in SEGMENTS for s in ss]
    timing, n = {}, 0
    for seg, sentences in SEGMENTS:
        pcm = bytearray(b"\0\0" * int(LEAD_IN * RATE))
        items = []
        for k, s in enumerate(sentences):
            shown, spoken = (s, s) if isinstance(s, str) else s
            prev = " ".join(flat[max(0, n - 2):n])
            n += 1
            data = synth(spoken, prev, key)
            start = len(pcm) / 2 / RATE
            pcm += data
            items.append({"text": shown, "start": round(start, 3), "end": round(len(pcm) / 2 / RATE, 3)})
            if k < len(sentences) - 1:
                pcm += b"\0\0" * int(GAP_SENTENCE * RATE)
        with wave.open(str(AUDIO / f"{seg}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(bytes(pcm))
        timing[seg] = {"duration": round(len(pcm) / 2 / RATE, 3), "sentences": items}
    (OUT / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=1))
    total = sum(t["duration"] for t in timing.values())
    print(f"segmentów: {len(timing)}, mowa: {total:.1f} s")


if __name__ == "__main__":
    main()
