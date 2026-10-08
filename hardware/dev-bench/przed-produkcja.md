# WICI: płytka nośna N1 przed zamówieniem

**Wstrzymane do decyzji po pilotażu (przegląd praktyczny 2026-10-08, F99):** pilotaż używa stacji z gotowej płytki MCU z układem LoRa SX1262 ([koncepcja 08](../../docs/concept/08-plan-weryfikacji-i-decyzje.html)). Do pilotażu nie trzeba montować N1; płytka nośna zostaje narzędziem do prób stosu i opcjonalnego porównania P1.

Płytka nośna jest narzędziem stanowiska, nie częścią stacji. Proces kontroli jest więc lżejszy niż dla R02 ([lekcje](../r02/lekcje.md#proces-kontroli-i-dowody)), ale jawny. Obowiązuje:
- ERC i DRC równe 0 z `--severity-all`; kontrola braku obrysu zajętości (`missing_courtyard`) jest włączona, a cztery kontrole wyłączone domyślnie w KiCad zostają wyłączone (lista w `checks/drc.json`, `ignored_checks`); DRC liczy się tylko wtedy, gdy KiCad wczytał reguły projektu z `cad/plytka-nosna.kicad_dru`: `kicad-cli` pomija bez ostrzeżenia cały plik reguł, jeśli jedna reguła się nie parsuje, dlatego `tools/drc.sh` i eksport najpierw sprawdzają regułę-kanarek, która musi zgłosić naruszenie (F103);
- zgodność PCB ze schematem;
- odtworzenie z generatorów, porównane geometrycznie łącznie z padami, wierceniami, grafiką footprintów i wypełnieniem stref (`tools/compare_boards.py`);
- przymiarka wydruku 1:1;
- przegląd autora z zapisem w [przeglądzie, F81](../../docs/review.md); przegląd przez drugą osobę, wymagany dla R02, tu nie obowiązuje.

Nie obowiązuje kontrola impedancji ani kwalifikacja stosu warstw, bo płytka nie ma toru RF ani USB. Z procesu R02 pomija się też osobny `status.json` i manifest sum w `checks/` (sumy są w `manifest.json` repozytorium), porównanie eksportów z geometrią (gerbonara) i licencje wewnątrz paczki ZIP; zamiast porównania eksporty ogląda się w przeglądarce Gerberów. `tools/export_fabrication.py` nie tworzy paczki, dopóki ERC i DRC bieżących plików (ze zgodnością PCB–schemat i kanarkiem reguł) nie dają 0.

## Warunki

| Warunek | Stan |
|---|---|
| ERC 0, DRC 0, brakujących połączeń 0, różnic PCB–schemat 0 (`checks/erc.json`, `checks/drc.json`), reguły projektu wczytane (kanarek) | spełniony dla bieżącej rewizji (audyt N1 wobec F106, ochrona CS pamięci FRAM). Rewizje sprzed F103 miały DRC 0 tylko dlatego, że plik reguł się nie wczytywał; po poprawce składni wyszło 14 ukrytych naruszeń szerokości ścieżek, poprawionych w regułach i opisanych w `FAB-NOTES.txt` |
| Odtworzenie: `tools/build.sh` i `tools/finalize_board.py` z zachowaną sesją dają tę samą płytkę (`tools/compare_boards.py`, [odtworzenie](#odtworzenie)) | sprawdzone: [zapis odtworzenia](checks/odtworzenie.md) |
| Przegląd elektryczny, mechaniczny i dokumentacji (F81) z poprawkami | wykonany 2026-10-07 przez autora z pomocą AI; nie jest niezależnym audytem |
| Drugi przegląd wobec dokumentów producentów (F83): kolejność pinów modułów, pozycje X-NUCLEO-S2868A2 (UM2638), złącza CC1120EM, DevKitC, DK; poprawki J7, JP3, J9/J10 i paczki dla wykonawcy | wykonany 2026-10-08 z pomocą AI; nie jest niezależnym audytem |
| Pliki produkcyjne obejrzane w przeglądarce Gerberów (warstwy, wycięcie P5, otwory, opisy); zapis w `checks/przymiarka.md` | rewizja sprzed F103 obejrzana 2026-10-08 ([zapis](checks/przymiarka.md#przegląd-gerberów-i-wierceń)); dla rewizji F103 wykonana kontrola liczbowa paczki (obrys, warstwy, otwory, liczba otwarć pasty równa liczbie padów SMD), **pełny przegląd z renderem warstw otwarty**. Podgląd wykonawcy ogląda się przy zamówieniu z raportem DFM |
| Wydruk 1:1 (`fabrication/N1/mechanika-1-do-1.pdf`, 100%, bez dopasowania do strony, bez odbicia): zmierzona kreska 50 mm; przymiarka rzeczywistego nRF52840-DK (położenie J1–J4 nad gniazdami DK, wycięcie nad P5, pas bez przelotek nad P20), ESP32-S3-DevKitC-1 (J5/J6), CC1120EM (J9/J10, strona SMA), X-NUCLEO-S2868A2 (obrys nad J1–J4, części na spodzie nad J10, C1, C2, C5, R11, R12, R14, R15, R17 i łbami śrub H7–H9; JP3 leży poza obrysem), panelu Sharp LS027B7DH01A na taśmie 0,8 mm (obrys, taśma FPC wsunięta do oporu w złącze FH12 położone w miejscu J7 na wydruku, bez naprężenia przy krawędzi szkła), przycisków z nasadkami, przełącznika i zacisku | **otwarte**: wynik z osobą i datą zapisuje się w `checks/przymiarka.md` |
| Wysokości części nRF52840-DK pod płytką (P5, P20, SW9, J2 z wtykiem): Nordic ich nie podaje; pomiar suwmiarką przy przymiarce. Wtyk USB w J2 płytki DK leży pod końcówkami gniazda J6 (stanowisko A): sprawdzić z rzeczywistym przewodem; gdy brakuje miejsca, końcówki J5/J6 skraca się po lutowaniu albo stosuje przewód z niskim wtykiem | **otwarte** |
| Listwy J9/J10 współpracują z gniazdami SFM-110-02-S-D-A modułu CC1120EM (BOM TI) | rozstrzygnięte w F83: Samtec TFM-110-01-L-D (przewlekana; karta F-226 podaje SFM jako partnera TFM); FTS-110-01-L-DV z poprzedniego BOM to wersja SMD bez SFM na liście partnerów; rysunek footprintu Samtec zaleca otwór 0,635 mm, więc 0,65 mm pasuje (F85); wysokość po złączeniu 5,97 mm z karty Samtec dotyczy SFM-01, a moduł ma SFM-02, więc wysokość mierzy się przy przymiarce |
| Parametry wykonawcy: dwie warstwy, FR-4 1,6 mm, miedź 35 µm, odstęp ≥0,2 mm, ścieżka nominalnie 0,25 mm, ale **minimum 0,18 mm** w krótkich zwężeniach przy padach o małym rastrze (0,24 mm między padami J7; wykonawca musi przyjąć 0,18 mm, inaczej trzeba poszerzyć zwężenia i powtórzyć trasowanie), otwór ≥0,4 mm (reguły DRC tak samo), wycięcie z narożnikami frezowanymi (promień frezu), otwory nieplaterowane 1,8 i 3,2 mm; opis tylko na górze | zapisane dla wykonawcy w `fabrication/N1/FAB-NOTES.txt` (po angielsku, także w ZIP); potwierdza się przy zamówieniu razem z raportem DFM wykonawcy |
| Zakres montażu: wykonawca montuje tylko 44 elementy SMD (`assembly/bom-assembly.csv`, `assembly/cpl-smd.csv`), w tym FRAM U1, przetwornicę U2 z cewką L1, nadzorcę U3 i bramkę U4 i złącze FPC J7 o rastrze 0,5 mm; resztę lutuje właściciel; obrót elementów SOT-23, SOT-23-5, SOT-23-6, SOD-123, SOIC-8 i J7 sprawdza się w podglądzie montażu wykonawcy | do potwierdzenia przy zamówieniu |
| Części z [BOM](bom.csv) dostępne u dystrybutora; zamienniki zapisane w zapisie sztuki. Stan 2026-10-08 ([koszt i dostępność](plytka-nosna.md#koszt-i-dostępność)): FRAM U1 CY15B104QN-50SXI albo MB85RS4MTPF-G-BCERE1 i panel LS027B7DH01A (nie wersja bez „A”) w magazynach DigiKey; ESP32-S3-DevKitC-1-N8R2 i -N8 wycofane, -N8R8 bez stanu w DigiKey i TME (była w Botland); C1/C4/C8/C9 CL21A106KAYNNNG (wersja -NNNE ma 61 tygodni); zestaw CC1120EMK-868-915 w DigiKey 3 sztuki; FRAM i panel z terminami fabrycznymi 26–30 tygodni, więc kupowane od razu | do potwierdzenia przy zakupie |
| Napięcie panelu: 4,8–5,5 V na VDD/VDDA w obu stanowiskach, także przy brzęczyku i nadawaniu | rozwiązane w projekcie (F103): własna przetwornica U2 (MCP1640) z +3,3 V, wynik obliczony 4,90–5,36 V w najgorszym przypadku ([zasilanie](plytka-nosna.md#zasilanie)); **pomiar przy uruchomieniu** (kroki A2/B2 i pomiar oscyloskopem) |
| Ochrona FRAM przy zaniku zasilania (specyfikacja, [zanik zasilania i zapis](../../docs/spec/elektronika.md#zanik-zasilania-i-zapis), punkt 2) | rozwiązane w projekcie (audyt N1 wobec F106): nadzorca U3 i bramka OR U4 wymuszają CS = H poniżej 2,66–2,74 V niezależnie od MCU, a C13 100 µF podtrzymuje +3V3 przez czas reakcji nadzorcy (≤30 µs; budżet przy 150 mA: spadek z 2,394 V do 2,0 V trwa ≥100 µs; [zasilanie](plytka-nosna.md#zasilanie)); **pomiar przy uruchomieniu** (kroki F1–F3 w [uruchomieniu](uruchomienie.md#ochrona-fram-przy-zaniku-zasilania)): próg, zapas przy 3,0 V stanowiska A, tempo opadania i stan CS przy odłączeniu zasilania pod największym obciążeniem. Serie zapisu ≤256 B zapewnia oprogramowanie, nie płytka |
| Dostępność części (przegląd rynku przy rewizjach F103 i po audycie wobec F106) | zob. [koszt i dostępność](plytka-nosna.md#koszt-i-dostępność); do potwierdzenia przy zakupie |

Zamówienie zwalniają zamknięte warunki z tabeli, w tym przymiarka 1:1. Płytka jest sprawdzona dopiero po uruchomieniu pierwszej sztuki według [uruchomienia](uruchomienie.md); do tego służą obrazy `bench-n1` (stanowisko A) i `bench-b` (stanowisko B) z poleceniami diagnostycznymi (stan: [zgodność z oprogramowaniem](checks/zgodnosc-firmware.md)). Zielone CI tego nie zastępuje. Zamówienie: 2–5 sztuk (cztery stanowiska deweloperskie do sieci A–B–stanowisko odbiorcze plus zapas).

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
