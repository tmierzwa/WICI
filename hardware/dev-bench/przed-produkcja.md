# WICI: płytka nośna N1 przed zamówieniem

Płytka nośna jest narzędziem stanowiska, nie częścią stacji. Proces kontroli jest więc lżejszy niż dla R02 ([lekcje](../r02/lekcje.md#proces-kontroli-i-dowody)), ale jawny. Obowiązuje:
- ERC i DRC równe 0 z `--severity-all`; kontrola braku obrysu zajętości (`missing_courtyard`) jest włączona, a cztery kontrole wyłączone domyślnie w KiCad zostają wyłączone (lista w `checks/drc.json`, `ignored_checks`);
- zgodność PCB ze schematem;
- odtworzenie z generatorów;
- przymiarka wydruku 1:1;
- przegląd autora z zapisem w [przeglądzie, F81](../../docs/review.md); przegląd przez drugą osobę, wymagany dla R02, tu nie obowiązuje.

Nie obowiązuje kontrola impedancji ani kwalifikacja stosu warstw, bo płytka nie ma toru RF ani USB. Z procesu R02 pomija się też osobny `status.json` i manifest sum w `checks/` (sumy są w `manifest.json` repozytorium), porównanie eksportów z geometrią (gerbonara) i licencje wewnątrz paczki ZIP; zamiast porównania eksporty ogląda się w przeglądarce Gerberów.

## Warunki

| Warunek | Stan |
|---|---|
| ERC 0, DRC 0, brakujących połączeń 0, różnic PCB–schemat 0 (`checks/erc.json`, `checks/drc.json`) | spełniony dla bieżącej rewizji |
| Odtworzenie: `tools/build.sh` i `tools/finalize_board.py` z zachowaną sesją dają tę samą płytkę (`tools/compare_boards.py`, [odtworzenie](#odtworzenie)) | sprawdzone: [zapis odtworzenia](checks/odtworzenie.md) |
| Przegląd elektryczny, mechaniczny i dokumentacji (F81) z poprawkami | wykonany 2026-10-07 przez autora z pomocą AI; nie jest niezależnym audytem |
| Drugi przegląd wobec dokumentów producentów (F83): kolejność pinów modułów, pozycje X-NUCLEO-S2868A2 (UM2638), złącza CC1120EM, DevKitC, DK; poprawki J7, JP3, J9/J10 i paczki dla wykonawcy | wykonany 2026-10-08 z pomocą AI; nie jest niezależnym audytem |
| Pliki produkcyjne obejrzane w przeglądarce Gerberów (warstwy, wycięcie P5, otwory, opisy); zapis w `checks/przymiarka.md` | **otwarte**: kontrola liczbowa eksportów wykonana (F83: zgodność z PCB, obrys zamknięty, ścieżka/odstęp 0,25/0,2 mm, pierścień ≥0,175 mm, otwory się nie nakładają); zostaje obejrzenie w przeglądarce |
| Wydruk 1:1 (`fabrication/N1/mechanika-1-do-1.pdf`, 100%, bez dopasowania do strony, bez odbicia): zmierzona kreska 50 mm; przymiarka rzeczywistego nRF52840-DK (położenie J1–J4 nad gniazdami DK, wycięcie nad P5, pas bez przelotek nad P20), ESP32-S3-DevKitC-1 (J5/J6), CC1120EM (J9/J10, strona SMA), X-NUCLEO-S2868A2 (obrys nad J1–J4, części na spodzie nad J10, C1, C2, C5, R11, R12, R14, R15, R17 i łbami śrub H7–H9; JP3 leży poza obrysem), Adafruit 4694 ekranem do góry (pin VIN nad napisem VIN) i 4719 (gniazda i otwory), przycisków z nasadkami, przełącznika i zacisku | **otwarte**: wynik z osobą i datą zapisuje się w `checks/przymiarka.md` |
| Wysokości części nRF52840-DK pod płytką (P5, P20, SW9, J2 z wtykiem): Nordic ich nie podaje; pomiar suwmiarką przy przymiarce. Wtyk USB w J2 płytki DK leży pod końcówkami gniazda J6 (stanowisko A): sprawdzić z rzeczywistym przewodem; gdy brakuje miejsca, końcówki J5/J6 skraca się po lutowaniu albo stosuje przewód z niskim wtykiem | **otwarte** |
| Listwy J9/J10 współpracują z gniazdami SFM-110-02-S-D-A modułu CC1120EM (BOM TI) | rozstrzygnięte w F83: Samtec TFM-110-01-L-D (przewlekana; karta F-226 podaje SFM jako partnera TFM); FTS-110-01-L-DV z poprzedniego BOM to wersja SMD bez SFM na liście partnerów; przed zakupem sprawdzić rysunek TFM (średnica końcówki wobec otworu 0,65 mm); wysokość po złączeniu 5,97 mm z karty Samtec dotyczy SFM-01, a moduł ma SFM-02, więc wysokość mierzy się przy przymiarce |
| Parametry wykonawcy: dwie warstwy, FR-4 1,6 mm, miedź 35 µm, ścieżka/odstęp ≥0,2 mm, otwór ≥0,4 mm (reguły DRC tak samo), wycięcie z narożnikami frezowanymi (promień frezu), otwory nieplaterowane 1,8, 2,7 i 3,2 mm; opis tylko na górze | zapisane dla wykonawcy w `fabrication/N1/FAB-NOTES.txt` (po angielsku, także w ZIP); potwierdza się przy zamówieniu razem z raportem DFM wykonawcy |
| Zakres montażu: wykonawca montuje tylko 27 elementów SMD (`assembly/bom-assembly.csv`, `assembly/cpl-smd.csv`), resztę lutuje właściciel; obrót elementów SOT-23 i SOD-123 sprawdza się w podglądzie montażu wykonawcy | do potwierdzenia przy zamówieniu |
| Części z [BOM](bom.csv) dostępne u dystrybutora; zamienniki zapisane w zapisie sztuki. Stan 2026-10-08 ([koszt i dostępność](plytka-nosna.md#koszt-i-dostępność)): **Adafruit 4719 niedostępna** (Adafruit brak, DigiKey zapowiada 2027-01-18; zamiennik 4718 ma 2 Mbit, a oprogramowanie i specyfikacja wymagają 4 Mbit; tymczasowo MB85RS4MT na płytce przejściowej w J8); ESP32-S3-DevKitC-1-N8R2 wycofana (kupuje się N8R8 albo N8); CL21A106KAYNNNE brak w DigiKey (zamiennik 10 µF 25 V X5R 0805); E-Switch 100SP1T1B4M2QE w magazynie DigiKey, termin producenta około 12 tygodni; zestaw Adafruit 85 tylko u Adafruit i jej dystrybutorów | do potwierdzenia przy zakupie; FRAM blokuje kompletne stanowiska, nie zamówienie PCB |

Zamówienie zwalniają zamknięte warunki z tabeli, w tym przymiarka 1:1. Płytka jest sprawdzona dopiero po uruchomieniu pierwszej sztuki według [uruchomienia](uruchomienie.md); do tego służą obrazy `bench-n1` (stanowisko A) i `bench-b` (stanowisko B) z poleceniami diagnostycznymi (stan: [zgodność z oprogramowaniem](checks/zgodnosc-firmware.md)). Zielone CI tego nie zastępuje. Zamówienie: 2–5 sztuk (cztery stanowiska do sieci A–B–OSP plus zapas).

## Odtworzenie

Środowisko: KiCad 10.0.6 z jego Pythonem (`pcbnew`) i `kicad-cli`, Python 3.12+ do generatorów schematu, Java 25+ (Freerouting 2.5.0 jest skompilowany dla Javy 25) i Freerouting 2.5.0 do trasowania. Ścieżki KiCad na macOS (na Linuksie `kicad-cli` i `python3` z pakietu KiCad, `KICAD_SHARE=/usr/share/kicad`):

```bash
export KICAD_CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli KICAD_PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 KICAD_SHARE=/Applications/KiCad/KiCad.app/Contents/SharedSupport
```

Z katalogu `hardware/dev-bench/`:

```bash
tools/build.sh
```

```bash
JAVA=/sciezka/do/java FREEROUTING=/sciezka/do/freerouting-2.5.0.jar tools/route.sh
```

```bash
(cd tools && "$KICAD_PY" finalize_board.py ../checks/routing.ses)
```

```bash
tools/drc.sh
```

`build.sh` regeneruje biblioteki, projekt, schemat, ERC, listę połączeń, BOM, `polaczenia.md`, rozmieszczenie i zadanie trasowania `checks/routing.dsn`. `route.sh` nadpisuje `checks/routing.ses` i kończy się błędem, gdy Freerouting zostawi niepoprowadzone połączenia. `drc.sh` uruchamia pełne DRC (`--severity-all`, zgodność ze schematem, wypełnienie stref) do `checks/drc.json`. Aby odtworzyć zapisaną płytkę, pomija się `route.sh` i importuje zachowaną sesję. Freerouting nie gwarantuje identycznej sesji na innej wersji Javy. Nowa sesja wymaga więc ponownego DRC i przeglądu, a nie samego dopisania wyniku. `finalize_board.py` uruchamia się raz, na płytce świeżo wygenerowanej przez `build.sh`. Dwie tak wygenerowane płytki porównuje się bez UUID (bajty plików zawsze się różnią):

```bash
(cd tools && "$KICAD_PY" compare_boards.py /sciezka/do/A.kicad_pcb /sciezka/do/B.kicad_pcb)
```

DRC z `--save-board` zmienia bajty PCB (wypełnienia stref), więc sumy liczy się po nim. Eksport plików produkcyjnych do `fabrication/N1/` i schematu do `schemat.pdf`:

```bash
python3 tools/export_fabrication.py
```

Edytowalnym źródłem jest `tools/design.py`. Plików w `cad/` nie poprawia się ręcznie w KiCad, bo następne uruchomienie generatorów nadpisze takie zmiany.
