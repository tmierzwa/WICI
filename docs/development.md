# Narzędzia i tworzenie paczek

## Model i kontrola źródeł

Python 3.12 lub nowszy (CI: 3.12), Git. Model, testy i kontrola repozytorium używają tylko biblioteki standardowej. Uruchom z katalogu głównego:

```sh
python3 -m unittest discover -s software/reference -v
python3 -m unittest discover -s tests -v
python3 tools/verify_repository.py
```

Kontrola porównuje manifest z indeksem Git i sprawdza sumy wszystkich plików, lokalne odnośniki Markdown i HTML (kotwice tylko w odnośnikach do stron HTML), składnię JSON/Python i wyniki obliczeń. Nie aktualizuje dowodów podczas sprawdzania. CI działa na Linuksie z Pythonem 3.12 i nie uruchamia KiCad.

## Oprogramowanie układowe

Katalog [firmware/](../firmware/README.md) buduje się PlatformIO w osobnym środowisku Pythona (`python3 -m venv .venv-pio && .venv-pio/bin/pip install platformio`, potem `pio run` w `firmware/`). Wersje platformy i rdzenia są przypięte w `platformio.ini`. CI buduje w workflow `Firmware` ([.github/workflows/firmware.yml](../.github/workflows/firmware.yml)) przy każdej zmianie w `firmware/` dziesięć środowisk: `bench-a`, `bench-n1`, `bench-b`, `l0` (program stacji prototypu) i `host` na rdzeniu Reticulum stacji oraz `bench-a-port`, `bench-n1-port`, `bench-b-port`, `l0-port` i `host-port` z portem microReticulum (wyjście awaryjne do etapu rdzenia 6-5). Dla obrazów z rdzeniem, które nie są `host`, workflow uruchamia też `tools/core_boards.py` (rdzeń z kompilatorem danej płytki). Osobne zadania: próby wrogiego ruchu na rdzeniu i na porcie oraz fuzzing rdzenia. Wybór stosu opisuje [firmware/README](../firmware/README.md#wybór-stosu-port-albo-rdzeń). Wynik prób na płytce podaje się w opisie PR. Samo `pio run` buduje domyślne środowisko `bench-a`; pozostałe wybiera się przez `-e`, np. `-e l0`. Program diagnostyczny prototypu (`hardware/l0-diagnostic`) ma własne środowisko `l0`, poza tą listą. Część nagłówków jest generowana. Tablicę rejestrów CC1120 dla profilu P1 (`firmware/src/p1_registers.h`) tworzy `firmware/tools/p1_registers.py`, a tablicę S2-LP (`firmware/src/s2lp_p1_registers.h`) skrypt `firmware/tools/s2lp_p1_registers.py`. Po zmianie parametrów w skrypcie trzeba go uruchomić z `--write`; testy w `tests/` odrzucają nieaktualny nagłówek. Tak samo powstają teksty ekranu (`firmware/src/ui_texts.h` z tabel w `docs/spec/oprogramowanie.md`, skrypt `firmware/tools/ui_texts.py`; po zmianie tekstów w specyfikacji uruchomić go z `--write`) i bitmapa fontu ekranu (`firmware/src/font_glyphs.h` z `firmware/fonts/DejaVuSansMono-Bold.ttf`, skrypt `firmware/tools/font_bitmap.py`, wymaga Pillow; test regeneracji jest pomijany bez Pillow).

## Symulator stacji

[Symulator](../software/simulator/README.md) uruchamia obraz bench-b oprogramowania stacji (pliki `firmware/src` wybrane przez `build_src_filter`, flagi z `platformio.ini`, stos z `firmware/tools/stack_deps.py`) na wirtualnej płytce w przeglądarce. Zbudowane `software/simulator/web/wici-station.mjs` i `wici-post.mjs` są w repozytorium. Po każdej zmianie `firmware/src`, `platformio.ini`, pinów lub łat stosu trzeba je zbudować od nowa poleceniem `python3 software/simulator/build.py` (Emscripten 3.1.74: `emsdk install 3.1.74 && emsdk activate 3.1.74`), bo `tests/test_simulator.py` odrzuca obraz niezgodny ze źródłami. Workflow `pages.yml` publikuje stronę pod `wici.net.pl/symulator/`.

## Strona koncepcji

Koncepcja jest publikowana na [GitHub Pages](https://docs.github.com/pages) pod adresem [wici.net.pl](https://wici.net.pl/) przez workflow `pages.yml` po każdej zmianie `docs/concept/` na `main`. `tools/build_pages.py` kopiuje strony i arkusz stylów bez zmiany treści. Linki wychodzące poza koncepcję zamienia na adresy plików w repozytorium dla publikowanego commitu. Lokalnie strony nie wymagają budowania: wystarczy otworzyć `docs/concept/index.html`.

## Domena i poczta

Domenę `wici.net.pl` zarejestrowano w home.pl 10 października 2026 r. (odnowienie do 10 października 2027 r.). Strefę DNS obsługują serwery `dns.home.pl`, `dns2.home.pl` i `dns3.home.pl`. Strona działa na GitHub Pages, a poczta na serwerze Hosting Biznes w home.pl. Domena jest przypisana do serwera w trybie „Brak obsługi WWW”, żeby panel nie nadpisał rekordów strony.

| Rekord | Host | Wartość | Cel |
|---|---|---|---|
| A (4) | `wici.net.pl` | `185.199.108.153`, `.109.153`, `.110.153`, `.111.153` | GitHub Pages |
| AAAA (4) | `wici.net.pl` | `2606:50c0:8000::153` … `8003::153` | GitHub Pages |
| CNAME | `www` | `tmierzwa.github.io.` | GitHub Pages; GitHub przekierowuje `www` na domenę główną |
| TXT | `_github-pages-challenge-tmierzwa` | kod weryfikacji z ustawień konta GitHub | zabezpieczenie przed przejęciem domeny; nie usuwać |
| MX | `wici.net.pl` | `10 serwer2617177.hosting-home.pl.` | poczta |
| SRV (6) | `_imap`, `_imaps`, `_pop3`, `_pop3s`, `_smtps`, `_submission` | `serwer2617177.hosting-home.pl.`, porty 143, 993, 110, 995, 465, 587 | autokonfiguracja programów pocztowych |
| TXT | `wici.net.pl` | `v=spf1 mx ~all` | SPF |
| TXT | `dkim._domainkey` | klucz publiczny z panelu home.pl | DKIM |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:kontakt@wici.net.pl` | DMARC w trybie raportowania |

Ustawienia repozytorium (Settings → Pages): źródło GitHub Actions, Custom domain `wici.net.pl`, Enforce HTTPS. Przy publikacji przez Actions plik `CNAME` w repozytorium nie jest potrzebny. Adres `tmierzwa.github.io/WICI` przekierowuje na domenę. Przy przypisywaniu domeny do serwera w home.pl nie wybierać „Główny katalog na serwerze” ani innej opcji WWW, bo panel podmieni rekordy A. SRV muszą wskazywać nazwę serwera pocztowego, a nie `wici.net.pl`, bo ta nazwa prowadzi do GitHub Pages. Adres projektu: `kontakt@wici.net.pl`; hasła i dane logowania nie należą do repozytorium.

## Narzędzia CAD

Płytki stacji projektuje się w KiCad 10.0.6: v1 (dawniej płytka nośna N1, płytka prototypu) jest wykonana, v1.1 jest projektem na `main`, v2 jest do zaprojektowania, a projekt R02 (wstrzymany) zostaje materiałem do v2 i do wydania. Kontrole ERC/DRC uruchamia `kicad-cli` tej samej instalacji, a skrypty geometrii interpreter Pythona KiCad z `pcbnew`. To środowisko jest odrębne od Pythona używanego przez narzędzia; nie instaluj pakietu `pcbnew` z PyPI. CI nie uruchamia KiCad. Zasady kontroli, eksportów i dowodów opisuje [materiał r02](../hardware/r02/README.md) z [lekcjami z kontrolera R01.3](../hardware/r02/lekcje.md). Skrypty eksportu Gerberów, porównania eksportów z geometrią (gerbonara) i arkusza 1:1 (ReportLab) poprzedniego kontrolera są w historii Git w commicie `53a075a` jako wzór; ich środowisko przypina się ponownie razem z narzędziami płytki v2. Tym samym środowiskiem powstała [płytka v1](../hardware/dev-bench/plytka-nosna.md) z generatorami w `hardware/dev-bench/tools/`. Trasuje ją Freerouting 2.5.0 (Java 25+). Zakres kontroli płytki v1 jest lżejszy niż dla R02; podaje go [lista przed zamówieniem](../hardware/dev-bench/przed-produkcja.md#odtworzenie).

## Paczka źródłowa

Po sprawdzeniu repozytorium:

```sh
python3 tools/release.py --source-zip dist/WICI-0.5-source.zip
```

Paczka zawiera źródła, dokumentację i eksporty; nie jest systemem startowym ani aplikacją stacji. Katalog `dist/` nie jest śledzony w Git. Archiwum zawiera wszystkie pliki manifestu i sam manifest, ze stałymi datami i kolejnością wpisów. Kontrola porównuje także bajty każdego wpisu. Zgodność identycznych wejść sprawdzają testy; inne wersje narzędzi lub kompresji mogą dać inną sumę kontrolną ZIP.

Manifest odświeża opiekun po scaleniu zmian i przed wydaniem, osobnym PR (na `main` nie można wysyłać zmian bezpośrednio). Przegląda i dodaje pliki do indeksu Git, wykonuje `python3 tools/release.py --refresh`, a następnie pełną kontrolę. Kontrybutor w PR używa `python3 tools/verify_repository.py --pull-request`, które pomija zgodność `manifest.json`. CI robi to samo dla pull requestów i gałęzi `main`, a pełną kontrolę z manifestem i paczkę źródłową wykonuje tylko dla tagów `v*`; gałęzie robocze sprawdza tylko w pull requeście. Po scaleniu PR, który zmienia pliki, manifest pozostaje nieaktualny, dopóki opiekun go nie odświeży. Kontrola `main` go pomija, ale tag `v*` z nieaktualnym manifestem nie przejdzie. Nie używaj `--refresh` do ukrycia niewyjaśnionej różnicy.

Oznaczenia licencji sprawdza [REUSE](https://reuse.software/): `pipx run reuse==5.0.2 lint`. Nowy plik bez nagłówka SPDX dostaje licencję z [REUSE.toml](../REUSE.toml).

Eksporty KiCad/PDF mogą zawierać czas utworzenia. Ponowny pełny eksport nie gwarantuje identycznych bajtów, dlatego sprawdza się geometrię względem CAD, a dopiero potem zapisuje nowe sumy aktualnych plików. Główne pliki edytowalne to `cad/*.kicad_*`; wygenerowany ZIP nie zastępuje źródeł.
