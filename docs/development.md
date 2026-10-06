# Narzędzia i tworzenie paczek

## Model i kontrola źródeł

Python 3.12, Git. Model, testy i kontrola repozytorium używają tylko biblioteki standardowej. Uruchom z katalogu głównego:

```sh
python3 -m unittest discover -s software/reference -v
python3 -m unittest discover -s tests -v
python3 tools/verify_repository.py
```

Kontrola porównuje manifest z indeksem Git, wszystkie sumy plików, lokalne odnośniki Markdown, składnię JSON/Python, wyniki obliczeń i paczkę kontrolera. Nie aktualizuje dowodów podczas sprawdzania. CI działa na Linuxie z Pythonem 3.12 i nie uruchamia KiCad.

## Narzędzia CAD

Zapisany projekt można otworzyć bez generowania. Do odtwarzania kontroli używamy KiCad 10.0.6, jego `kicad-cli` i interpretera z `pcbnew`. To osobne środowisko od Pythona narzędzi. Nie instaluj losowego pakietu `pcbnew` z PyPI.

Dodatkowe biblioteki służą wyłącznie do PDF i analizy eksportów. Przygotuj środowisko Python 3.12:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-tools.txt
```

Na Windows użyj `py -3.12 -m venv .venv` i `.venv\Scripts\python.exe`. Główne narzędzia to ReportLab 5.0.1 i gerbonara 1.6.3; plik wymagań przypina także ich zależności z przetestowanego środowiska. Wektory Gerberów analizujemy z plików, bez serwera sieciowego gerbonara.

Pełny przebieg CAD i eksportu sprawdzono na macOS z KiCad 10.0.6 i Pythonem 3.12. Otwieranie źródeł jest niezależne od systemu; procedura dla innych instalacji wymaga wskazania właściwego interpretera KiCad. [Polecenia i kolejność](../hardware/radio-test-r01/odtworzenie.md).

Freerouting 2.5.0 jest potrzebny tylko do nowego trasowania. Odtworzenie R01.3 używa zapisanej sesji SES, bez Java i bez sieci. Podglądy PNG/SVG w `checks/preview/` służą do przeglądu. Do produkcji używa się zweryfikowanych eksportów. Bieżące PDF montażu i schematu tworzy KiCad, a PDF mechaniki ReportLab; nie potrzeba Inkscape ani konwertera SVG.

## Paczka źródłowa

Po sprawdzeniu repozytorium:

```sh
python3 tools/release.py --source-zip dist/WICI-0.4-source.zip
```

To źródła, dokumentacja i eksporty. Nie jest to system startowy ani aplikacja stacji. Plik `dist/` nie jest śledzony w Git. Archiwum ma wszystkie pliki manifestu oraz sam manifest, stałe daty i kolejność wpisów. Kontrola porównuje także bajty każdego wpisu. Zgodność identycznych wejść sprawdzają testy; inne wersje narzędzi lub kompresji mogą dać inny hash ZIP.

Po świadomej zmianie źródeł: przejrzyj i dodaj pliki do indeksu Git, wykonaj `python3 tools/release.py --refresh`, następnie pełną kontrolę. Nie używaj `--refresh` do ukrycia niewyjaśnionej różnicy.

Eksporty KiCad/PDF mogą zawierać czas utworzenia. Pełny ponowny eksport nie obiecuje identycznych bajtów. Sprawdza się geometrię względem CAD, a następnie zapisuje nowe sumy aktualnych plików. Główne pliki edytowalne to `cad/*.kicad_*`; wygenerowany ZIP nie zastępuje źródeł.
