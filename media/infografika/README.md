# Infografika WICI

Infografika do mediów społecznościowych w dwóch formatach, eksport 2×: post 4:5 (1080 × 1350 px) i Stories 9:16 (1080 × 1920 px). Treść: jak działa WICI, czego nie zastępuje (112) i kogo szukamy. Odsyła do [strony koncepcji](https://tmierzwa.github.io/WICI/).

| Plik | Zawartość |
|---|---|
| [WICI-infografika-pl.png](WICI-infografika-pl.png) | wersja polska |
| [WICI-infografika-en.png](WICI-infografika-en.png) | wersja angielska |
| [WICI-stories-pl.png](WICI-stories-pl.png), [WICI-stories-en.png](WICI-stories-en.png) | Stories: ta sama treść; górne 250 px i dolne 300 px zostają wolne pod przyciski aplikacji |
| [infografika.html](infografika.html) | szablon; teksty obu wersji są w tabeli `T` na końcu pliku, format wybiera parametr `?format=story` |
| [render.js](render.js) | eksport PNG przez Playwright |

Treść opiera się na [README](../../README.md), [koncepcji](../../docs/concept/index.html) i tekstach ekranu z [oprogramowania](../../docs/spec/oprogramowanie.md#teksty-ekranu). Zasięg ~1 km i 48 h pracy są oznaczone jako cele do sprawdzenia. Znak, kolory i font pochodzą z [media/logo](../logo/README.md).

## Odtworzenie

Wymagania: Node.js i pakiet `playwright` z przeglądarką Chromium.

```sh
node media/infografika/render.js
```

Skrypt wstawia znak z `media/logo/WICI-na-ciemnym.svg` i ostrzega, gdy treść nie mieści się w kadrze.
