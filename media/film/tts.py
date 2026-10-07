"""Generuje narrację ElevenLabs: zdania -> segmenty WAV + timing.json.

Każde zdanie powstaje w TAKES podejściach (stałe ziarna, więc wynik jest powtarzalny);
wybierane jest to, którego koniec opada (zdanie oznajmujące) albo rośnie (pytanie).

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
import time
import urllib.error
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import importlib
import sys

import numpy as np

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
QUESTION = {"stability": 0.3, "style": 0.5}  # pytania: więcej ekspresji, żeby intonacja się podniosła
TAKES = 3  # podejść na zdanie; wybór po intonacji końca
RATE = 44100
GAP_SENTENCE = 0.4
LEAD_IN = 0.15
TAIL = 0.12  # cisza po wybrzmieniu głosu


def api_key():
    key = os.environ.get("ELEVENLABS_API_KEY")
    if key:
        return key
    env = os.environ.get("ELEVENLABS_ENV")
    for line in Path(env).read_text().splitlines():
        if line.startswith("ELEVENLABS_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("brak ELEVENLABS_API_KEY")


def fetch(payload, key):
    """Nagranie z bufora albo z API: (PCM 16 bit mono, znaczniki czasu liter)."""
    h = hashlib.sha1(json.dumps([VOICE_ID, payload], ensure_ascii=False).encode()).hexdigest()[:16]
    cached = CACHE / f"{h}.json"
    if not cached.exists():
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/with-timestamps?output_format=mp3_44100_128",
            data=json.dumps(payload).encode(),
            headers={"xi-api-key": key, "Content-Type": "application/json"})
        for attempt in range(6):  # limit równoczesnych zapytań: 429 -> odczekaj i ponów
            try:
                body = urllib.request.urlopen(req, timeout=120).read()
                break
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == 5:
                    raise
                time.sleep(2 * (attempt + 1))
        cached.write_bytes(body)
        print("  tts:", payload["text"][:60], payload.get("seed", ""))
    d = json.loads(cached.read_text())
    mp3 = CACHE / f"{h}.mp3"
    if not mp3.exists():
        mp3.write_bytes(base64.b64decode(d["audio_base64"]))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "s16le", "-ac", "1",
                          "-ar", str(RATE), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float64), d["alignment"]


def speech_bounds(x, al):
    """Początek i koniec mowy: od znaczników liter, a koniec przedłużony do wybrzmienia głosu.

    Znacznik ostatniej litery często wypada przed końcem opadającej sylaby; cięcie w tym miejscu
    brzmi, jakby lektor chciał mówić dalej. Dlatego koniec szukamy po energii sygnału.
    """
    letters = [i for i, c in enumerate(al["characters"]) if c.isalnum()]
    start = max(0.0, al["character_start_times_seconds"][letters[0]] - 0.04)
    end = al["character_end_times_seconds"][letters[-1]]
    hop = int(0.01 * RATE)
    rms = np.sqrt(np.convolve(x ** 2, np.ones(hop) / hop, mode="same"))
    floor = rms.max() * 10 ** (-45 / 20)
    k, stop = int(end * RATE), min(len(x), int((end + 0.6) * RATE))
    while k < stop and rms[k] > floor:
        k += hop
    return start, k / RATE + TAIL


def final_rise(x, t0, t1):
    """O ile półtonów głos kończy się wyżej (+) albo niżej (−) niż chwilę wcześniej.

    Wysokość z autokorelacji w ramkach 40 ms (70–250 Hz, głos męski); ramki odbiegające od mediany
    o ponad 7 półtonów (błędy oktawy) są pomijane. Porównanie: ostatnie 0,15 s mowy z 0,45–0,15 s.
    """
    win, hop = int(0.04 * RATE), int(0.01 * RATE)
    lo, hi = int(RATE / 250), int(RATE / 70)
    ts, st = [], []
    for a in range(int(max(t0, t1 - 0.6) * RATE), int(t1 * RATE) - win, hop):
        f = x[a:a + win] - x[a:a + win].mean()
        ac = np.correlate(f, f, mode="full")[win - 1:]
        if ac[0] <= 0:
            continue
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] / ac[0] > 0.5:
            ts.append(a / RATE + 0.02)
            st.append(12 * np.log2(RATE / lag))
    ts, st = np.array(ts), np.array(st)
    if len(st) < 6:
        return 0.0
    keep = np.abs(st - np.median(st)) < 7
    ts, st = ts[keep], st[keep]
    end = ts.max()
    last, before = st[ts > end - 0.15], st[(ts <= end - 0.15) & (ts > end - 0.45)]
    if len(last) < 2 or len(before) < 2:
        return 0.0
    return float(np.median(last) - np.median(before))


def synth(text, prev, key, opts=None):
    """PCM zdania. Bez opts: TAKES podejść i wybór po intonacji końca, z pytaniem rosnącym,
    a w zdaniu oznajmującym opadającym. opts (wybrane ręcznie zdanie): "settings" nadpisuje
    ustawienia głosu, "next_text" podpowiada intonację; jedno podejście, jak odsłuchano."""
    question = text.rstrip().endswith("?")
    settings = {**SETTINGS, **(QUESTION if question else {}), **(opts or {}).get("settings", {})}
    payload = {"text": text, "model_id": MODEL, "language_code": "pl",
               "voice_settings": settings, "previous_text": prev}
    if opts and "next_text" in opts:
        payload["next_text"] = opts["next_text"]
    takes = [payload] if opts else [{**payload, "seed": s} for s in range(1, (2 * TAKES if question else TAKES) + 1)]
    best = None
    for pl in takes:
        x, al = fetch(pl, key)
        t0, t1 = speech_bounds(x, al)
        rise = final_rise(x, t0, t1 - TAIL)
        score = rise if question else -rise
        if best is None or score > best[0]:
            best = (score, x, t0, t1, pl.get("seed"))
    _, x, t0, t1, seed = best
    return cut(x.astype(np.int16).tobytes(), t0, t1), seed


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
    flat = [(s if isinstance(s, str) else s[1]) for _, ss in SEGMENTS for s in ss]  # (napis, lektor[, opcje])
    jobs = []
    for _, sentences in SEGMENTS:
        for s in sentences:
            shown, spoken, opts = (s, s, None) if isinstance(s, str) else (s + (None,))[:3]
            n = len(jobs)
            jobs.append((shown, spoken, " ".join(flat[max(0, n - 2):n]), opts))
    with ThreadPoolExecutor(2) as pool:  # zdania są niezależne; pobieramy równolegle
        done = list(pool.map(lambda j: synth(j[1], j[2], key, j[3]), jobs))
    timing, n = {}, 0
    for seg, sentences in SEGMENTS:
        pcm = bytearray(b"\0\0" * int(LEAD_IN * RATE))
        items = []
        for k in range(len(sentences)):
            shown = jobs[n][0]
            data, seed = done[n]
            n += 1
            start = len(pcm) / 2 / RATE
            pcm += data
            items.append({"text": shown, "start": round(start, 3), "end": round(len(pcm) / 2 / RATE, 3), "seed": seed})
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
