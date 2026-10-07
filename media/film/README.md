# Film „WICI: sieć łączności na czas, gdy nic nie działa”

| Plik | Format |
|---|---|
| [WICI-film.mp4](WICI-film.mp4), [WICI-film.srt](WICI-film.srt) | 4:45, 1920×1080, 30 kl./s, napisy wypalone w obrazie i osobno |
| [WICI-short.mp4](WICI-short.mp4), [WICI-short.srt](WICI-short.srt) | 60 s, 1080×1920 na Reels i TikTok; napisy nad interfejsem aplikacji |
| [plakat.jpg](plakat.jpg) | kadr tytułowy, plakat odtwarzacza na stronie koncepcji |

Animacje: [Manim Community](https://www.manim.community/), font Avenir Next, znak z [media/logo](../logo/README.md). Lektor: ElevenLabs (`eleven_multilingual_v2`, głos „George”). Efekt planszy tytułowej [sfx/title.mp3](sfx/title.mp3): ElevenLabs sound-generation.

| Plik | Rola |
|---|---|
| `narracja.py`, `narracja_short.py` | tekst lektora i napisów, podzielony na segmenty |
| `tts.py` | synteza mowy ze znacznikami czasu; każde zdanie cięte 0,12 s po ostatniej literze → `build/…/audio/*.wav`, `timing.json` |
| `wici_film.py` | animacje filmu i wspólne ikony; zapisuje `build/subs.json` |
| `wici_short.py` | układ pionowy na tych samych ikonach; zapisuje `build/short/subs.json` |
| `napisy.py` | wypala napisy (libass) i zapisuje `.srt`; rozmiar i położenie zależą od orientacji kadru |

## Odtworzenie

Wymagania: Python 3.12, `pip install manim`, Homebrew `ffmpeg-full` (libass), font Avenir Next (macOS), klucz ElevenLabs.

```sh
export ELEVENLABS_ENV=/ścieżka/do/.env.elevenlabs
python3 tts.py
manim --resolution 1920,1080 --frame_rate 30 --disable_caching --media_dir build/media wici_film.py WICI
python3 napisy.py build/media/videos/wici_film/1080p30/WICI.mp4 WICI-film.mp4 WICI-film.srt

python3 tts.py narracja_short build/short
manim --resolution 1080,1920 --frame_rate 30 --disable_caching --media_dir build/media wici_short.py Short
python3 napisy.py build/media/videos/wici_short/1920p30/Short.mp4 WICI-short.mp4 WICI-short.srt build/short/subs.json
```

Na koniec normalizacja głośności: `ffmpeg -i IN.mp4 -c:v copy -af loudnorm=I=-16:TP=-1.5:LRA=11 OUT.mp4` (dla wersji pionowej `I=-14`).
`tts.py` buforuje zdania w `build/tts`; po zmianie tekstu generuje tylko zmienione. Inny głos: zmienna `WICI_VOICE`.
