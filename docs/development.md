# Narzędzia i tworzenie paczek

## Model i kontrola źródeł

Python 3.12 lub nowszy (CI: 3.12), Git. Model, testy i kontrola repozytorium używają tylko biblioteki standardowej. Uruchom z katalogu głównego:

```sh
python3 -m unittest discover -s software/reference -v
python3 -m unittest discover -s tests -v
python3 tools/verify_repository.py
```

Kontrola porównuje manifest z indeksem Git, wszystkie sumy plików, lokalne odnośniki Markdown i HTML (kotwice tylko w odnośnikach do stron HTML), składnię JSON/Python i wyniki obliczeń. Nie aktualizuje dowodów podczas sprawdzania. CI działa na Linuksie z Pythonem 3.12 i nie uruchamia KiCad.

## Oprogramowanie układowe

Katalog [firmware/](../firmware/README.md) buduje się PlatformIO w osobnym środowisku Pythona (`python3 -m venv .venv-pio && .venv-pio/bin/pip install platformio`, potem `pio run` w `firmware/`). Wersje platformy i rdzenia są przypięte w `platformio.ini`. CI nie buduje obrazu; wynik kompilacji i próby na płytce podaje się w opisie PR. Tablica rejestrów CC1120 dla profilu P1 (`firmware/src/p1_registers.h`) jest generowana: po zmianie parametrów w `firmware/tools/p1_registers.py` uruchomić go z `--write`; test w `tests/` odrzuca nieaktualny nagłówek. Tak samo generowane są teksty ekranu (`firmware/src/ui_texts.h` z tabel w `docs/spec/oprogramowanie.md`, skrypt `firmware/tools/ui_texts.py`; po zmianie tekstów w specyfikacji uruchomić go z `--write`) i bitmapa fontu ekranu (`firmware/src/font_glyphs.h` z `firmware/fonts/DejaVuSansMono-Bold.ttf`, skrypt `firmware/tools/font_bitmap.py`, wymaga Pillow; test regeneracji jest pomijany bez Pillow).

## Strona koncepcji

Koncepcja jest publikowana na [GitHub Pages](https://tmierzwa.github.io/WICI/) przez workflow `pages.yml` po każdej zmianie `docs/concept/` na `main`. `tools/build_pages.py` kopiuje strony i arkusz stylów bez zmiany treści. Linki wychodzące poza koncepcję zamienia na adresy plików w repozytorium dla publikowanego commitu. Lokalnie strony nie wymagają budowania: wystarczy otworzyć `docs/concept/index.html`.

## Narzędzia CAD

Płytkę stacji R02 projektuje się w KiCad 10.0.6; kontrole ERC/DRC uruchamia `kicad-cli` tej samej instalacji, a skrypty geometrii interpreter Pythona KiCad z `pcbnew`. Jest to środowisko odrębne od Pythona narzędzi; nie instaluj pakietu `pcbnew` z PyPI. CI nie uruchamia KiCad. Zasady kontroli, eksportów i dowodów opisuje [projekt R02](../hardware/r02/README.md) z [lekcjami z kontrolera R01.3](../hardware/r02/lekcje.md). Skrypty eksportu Gerberów, porównania eksportów z geometrią (gerbonara) i arkusza 1:1 (ReportLab) poprzedniego kontrolera są w historii Git w commicie `ea32e7c` jako wzór; ich środowisko przypina się ponownie razem z narzędziami R02. Tym samym środowiskiem powstaje [płytka nośna stanowiska deweloperskiego](../hardware/dev-bench/plytka-nosna.md) N1 z generatorami w `hardware/dev-bench/tools/`; trasuje ją Freerouting 2.5.0 (Java 21+), a zakres kontroli, lżejszy niż dla R02, podaje [lista przed zamówieniem](../hardware/dev-bench/przed-produkcja.md#odtworzenie).

## Paczka źródłowa

Po sprawdzeniu repozytorium:

```sh
python3 tools/release.py --source-zip dist/WICI-0.5-source.zip
```

Paczka zawiera źródła, dokumentację i eksporty; nie jest systemem startowym ani aplikacją stacji. Katalog `dist/` nie jest śledzony w Git. Archiwum zawiera wszystkie pliki manifestu i sam manifest, ze stałymi datami i kolejnością wpisów. Kontrola porównuje także bajty każdego wpisu. Zgodność identycznych wejść sprawdzają testy; inne wersje narzędzi lub kompresji mogą dać inny hash ZIP.

Manifest odświeża opiekun po scaleniu zmian i przed wydaniem: przegląda i dodaje pliki do indeksu Git, wykonuje `python3 tools/release.py --refresh`, a następnie pełną kontrolę. Kontrybutor w PR używa `python3 tools/verify_repository.py --pull-request`, które pomija zgodność `manifest.json`; CI robi to samo dla pull requestów, a pełną kontrolę i paczkę źródłową wykonuje dla gałęzi `main` i tagów `v*`; gałęzie robocze sprawdza tylko w pull requeście. Po scaleniu PR, który zmienia pliki, kontrola `main` pozostaje czerwona do odświeżenia manifestu przez opiekuna repozytorium. Nie używaj `--refresh` do ukrycia niewyjaśnionej różnicy.

Oznaczenia licencji sprawdza [REUSE](https://reuse.software/): `pipx run reuse==5.0.2 lint`. Nowy plik bez nagłówka SPDX dostaje licencję z [REUSE.toml](../REUSE.toml).

Eksporty KiCad/PDF mogą zawierać czas utworzenia. Ponowny pełny eksport nie gwarantuje identycznych bajtów, dlatego sprawdza się geometrię względem CAD, a dopiero potem zapisuje nowe sumy aktualnych plików. Główne pliki edytowalne to `cad/*.kicad_*`; wygenerowany ZIP nie zastępuje źródeł.
