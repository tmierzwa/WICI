# WICI — odtworzenie kontrolera R01.3

Główne źródła to schemat, PCB, projekt i reguły w `cad/`. Zapisane biblioteki są kompletne. Wystarczy otworzyć `cad/radio-usb-controller.kicad_pro` w KiCad 10.0.6. Fizyczne dopasowanie i próby układu pozostają osobnymi warunkami.

## Środowisko

[Instalacja Pythona narzędzi i zależności](../../docs/development.md). Do CAD używamy KiCad **10.0.6** wraz z jego `pcbnew`, nie pakietu o tej nazwie z PyPI. Przebieg poniżej sprawdzono na macOS. Z katalogu głównego WICI wskaż swoją instalację:

```sh
export KICAD_CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
export KICAD_PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3
export TOOLS_PY="$PWD/.venv/bin/python"
"$KICAD_CLI" version
"$KICAD_PY" -c 'import pcbnew; print(pcbnew.GetBuildVersion())'
```

Obie wersje mają być 10.0.6. Na innych systemach zmień ścieżki na interpreter i CLI tej samej instalacji. Nie uruchamiaj dwóch procesów KiCad równocześnie. Odtwarzanie wykonuj w osobnej kopii roboczej, aby nie nadpisać kandydata.

## Kontrola zapisanych źródeł

Z `hardware/radio-test-r01/`:

```sh
"$KICAD_CLI" sch erc --format json --severity-all --exit-code-violations --output checks/erc-controller.json cad/radio-usb-controller.kicad_sch
"$KICAD_CLI" pcb drc --format json --all-track-errors --severity-all --schematic-parity --exit-code-violations --refill-zones --save-board --output checks/drc-controller.json cad/radio-usb-controller.kicad_pcb
```

Oba polecenia muszą zwrócić 0. DRC ma puste `violations`, `unconnected_items` i `schematic_parity`. Domyślne pominięcia KiCad są wymienione w raportach. Nie dodano wyjątków dla naruszeń. Zapis po DRC może zmienić bajty PCB; dalsza kontrola ma odnosić się do tego zapisu.

## Odtworzenie R01.3 z zachowanej sesji

Skopiuj repozytorium do osobnego katalogu. Z katalogu kontrolera w tej kopii uruchom kolejno:

```sh
"$TOOLS_PY" tools/make_schematic.py
"$KICAD_PY" tools/improve_controller_power.py
"$KICAD_PY" tools/import_routing.py checks/controller-power.ses
"$KICAD_PY" tools/finalize_power_routing.py
"$KICAD_PY" tools/apply_fabrication_revision.py
```

Następnie uruchom ERC i DRC z sekcji wyżej. `finalize_power_routing.py` uruchamiaj jeden raz na świeżym imporcie. `improve_controller_power.py` czyta wcześniejszy PCB `checks/history/controller-power-input.kicad_pcb`. Sesja SES jest właściwa tylko dla tego rozmieszczenia; nie używaj `controller-final.ses`.

Z katalogu kontrolera **kandydata**, Pythonem KiCad porównaj osobną kopię:

```sh
"$KICAD_PY" tools/verify_replay.py /sciezka/do/kopii/hardware/radio-test-r01
```

Narzędzie zapisuje `checks/replay-verification.json` przy kandydacie. Porównuje położenia, pady, ścieżki, przelotki, obrysy pól, otwory, schemat, BOM i połączenia. Pomija UUID i pamięć wypełnienia pól. Zmieniona geometria wymaga przeglądu i nowej rewizji, nie dopisania „PASS”.

## PDF, eksporty i ZIP

Z katalogu kontrolera, po przejściu kontroli CAD:

```sh
"$KICAD_PY" tools/audit_controller_revision.py
"$TOOLS_PY" tools/make_mechanical_sheet.py
"$TOOLS_PY" tools/export_fabrication.py --kicad-cli "$KICAD_CLI"
"$KICAD_PY" tools/export_fabrication_geometry.py
"$TOOLS_PY" tools/verify_fabrication.py
```

Eksporter tworzy dziewięć Gerberów, osobne PTH/NPTH z mapami PDF, pozycje wszystkich i SMT, BOM, pastę, PDF montażowy i `schemat.pdf`. Kopiuje PDF mechaniki i stos warstw. Dołącza NOTICE, pełne licencje i tworzy `fabrication/wici-controller-R01.3.zip`. PDF montażu ma skalę 2:1; mechanika osobny wydruk 1:1.

Analiza `verify_fabrication.py` porównuje eksporty z rzeczywistą geometrią PCB i wiąże wszystkie pliki paczki z sumami. Jeśli zawiedzie, nie wysyłaj ZIP do wykonawcy. Sprawdź wizualnie rysunki, Gerbery i PDF mechaniki. Wydrukuj mechanikę w 100%, bez dopasowania i odbicia, sprawdź odcinek 50 mm i przymierz rzeczywiste USB-B, SW1 i IDC.

Po przeglądzie poprawnych raportów:

```sh
"$TOOLS_PY" tools/check_bundle.py
"$TOOLS_PY" tools/check_bundle.py --check
```

Pierwsza komenda zapisuje status i manifest sprzętu. Druga tylko sprawdza: kompletność, bajty ZIP, sumy i raporty. HOLD pozostaje. Samodzielne przepakowanie istniejących eksportów: `"$TOOLS_PY" tools/pack_fabrication.py`; potem ponów analizę eksportów i kontrolę paczki.

Po zmianie publicznych plików wróć do katalogu głównego, przejrzyj i dodaj je do indeksu, odśwież główny manifest i wykonaj [kontrole repozytorium](../../docs/development.md). Wygenerowane PDF/Gerbery zawierają czas eksportu, więc porównanie geometrii i bieżących sum zastępuje obietnicę identycznych bajtów po ponownym eksporcie.

## Trasowanie i wcześniejsze narzędzia

Dla nowego trasowania `export_power_routing.py` tworzy DSN z nieaktywnymi In1/In2. Freerouting 2.5.0: lokalnie, analityka wyłączona (`-da`). Sekcja ustawień musi poprzedzać pola miedzi w DSN. Raport autoroutera zawiera nieukończone połączenia zachowanych tras/płaszczyzn; odbiór wynika z końcowego KiCad DRC, nie statusu autoroutera.

`make_board.py`, `finalize_routing.py`, `controller.dsn` i `controller-final.ses` opisują R01. Nie służą do odtworzenia R01.3. `prepare_footprints.py` jest potrzebny tylko do ponownego pobrania bibliotek. Symbole pochodzą z podzbiorów KiCad 9.0.0/10.0.6, footprinty z 10.0.6; pochodzenie i licencje są w `sources.json` oraz `cad/KICAD-LIBRARY-LICENSE.md`.
