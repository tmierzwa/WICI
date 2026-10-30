# WICI: obudowa stacji (szkielet)

**Status 2026-10-11: szkielet bez geometrii. Nie drukować, nie zamawiać.** Katalog zbiera założenia obudowy w jednym miejscu i odmawia wygenerowania części, dopóki nie ma pomiarów z przymiarki. Wygląd stacji pokazuje tylko render koncepcyjny.

![Koncepcja stacji, widok z przodu](render/stacja-front.png)

![Koncepcja stacji, złącza na dolnej ściance](render/stacja-zlacza.png)

Do materiałów: [render/stacja-materialy.png](render/stacja-materialy.png), 3600 × 2400 px (na stronę i README: [stacja-materialy-web.jpg](render/stacja-materialy-web.jpg), 1800 × 1200 px, około 125 KB), z krótkim podpisem „wizualizacja koncepcyjna”: stacji jeszcze nie zbudowano, wygląd zmieni się po próbach i pilotażu.

Render pokazuje założenia z [projektu obudowy płytki R02](../r02/obudowa.md) (dawnej własnej płytki stacji, dziś materiału do v2 i wydania) z 2026-10-08: Hammond 1599KBAT (220 × 140 × 40 mm), ekran Sharp LS027B7DH01A w oknie 61,5 × 38 mm, cztery przyciski PV6 w rozstawie 32 mm, kolumna ALARM, CISZA z osłoną i wyłącznik główny, przycisk przygotowania za otworem Ø4 mm pod numerowaną naklejką VOID (zamiast plombowanej pokrywy serwisowej, [F113](../../docs/review.md)) oraz USB-C, 12 V (EN3) i SMA na dolnej ściance. Na ekranie jest ekran główny z [oprogramowania](../../docs/spec/oprogramowanie.md#ekran-i-przyciski-stacji), a na folii panelu nazwy przycisków z [karty](../../docs/obsluga/karta-stacji.html) i jej wersji UK i EN. Umowne są: wnętrze, słupki, śruby pokrywy, linia podziału, wysokość osi złączy, kształt osłony CISZY i kolor wyłącznika.

## Dwa etapy

1. **Obudowa prototypu:** obudowa drukowana 3D (PETG albo ASA) dla prototypu na płytce v1 (dawniej N1) z DevKitC, Wio i panelem, do prób czytelności i obsługi (T8) w kroku 4. Otwory liczy się z plików płytki (`positions.csv`, `plytka-nosna.kicad_pcb`), a nie z ich przepisanej kopii. Ograniczenie: płytka v1 ma przyciski 12 mm w rozstawie 16 mm, więc obsługi w rękawicach na prototypie nie da się sprawdzić.
2. **Obudowa pilotażowa:** kupiona skrzynka V-0 (propozycja: Hammond 1599KBAT) z obrobionym frontem, folią panelu i drukowanym wkładem tylko w środku, dla 8 stacji pilotażowych na płytce v2 w kroku 6 ([stacja pilotażowa](../../docs/spec/elektronika.md#stacja-pilotażowa)). Obrys i otwory płytki v2 dopasowuje się do obudowy, a wkład do płytki v2.

## Co jest znane, a co trzeba zmierzyć

Znane wartości mają źródło w repozytorium: obrys płytki v1 (170 × 100 mm), 9 otworów montażowych, położenia części, wymiary panelu Sharp i układ panelu z projektu R02. Pomiary są w `zalozenia.py` (`MEASUREMENTS`) i mają wartość `None`, dopóki ktoś ich nie wykona:

| Pomiar | Skąd |
|---|---|
| wysokość DevKitC w gniazdach J5/J6 nad płytką v1 | suwmiarka po wpięciu DevKitC |
| wysokość nasadki przycisku nad płytką v1 | zmontowany prototyp |
| wysokość szkła panelu nad płytką v1 | po teście ekranu i przyklejeniu |
| długość wolnej taśmy FPC | przymiarka z panelem |
| położenie i wysokość Wio z adapterem, wyjście u.FL | po montażu prototypu |
| położenie gniazda USB/OTG DevKitC | po wpięciu DevKitC |
| słupki i śruby pokrywy Hammond 1599KBAT | model STEP albo próbka |
| płytka v2 stacji pilotażowej | projekt v2 po kroku 4 |
| obrys i wysokość osłony GT-4R | karta i próbka |

Największe ryzyko obudowy prototypu to różnica wysokości: panel leży około 2,5 mm nad płytką v1, a DevKitC w gniazdach 8,5 mm sięga znacznie wyżej. Pokrywa potrzebuje więc wgłębionego, fazowanego okna albo garbu nad DevKitC. Wybór zapadnie dopiero po pomiarze.

## Następne kroki

Stan 2026-10-11: przed testami i pomiarami nic więcej w obudowie się nie projektuje. Każdy krok zaczyna się po warunku z kolumny „Kiedy”.

| Kiedy | Krok |
|---|---|
| teraz, decyzja opiekuna projektu | jeden komplet próbek do przymiarki (około 100–150 USD): Hammond 1599KBAT, cztery przyciski PV6, osłona GT-4R z przełącznikiem GTS, gniazdo EN3 z wtykiem, koszyk BH4AAW; sprawdza obsługę w rękawicach przy rozstawie 32 mm, wysokość osłony CISZY, słupki i śruby pokrywy oraz miejsce na koszyk; nie zależy od projektu płytki v2 ([obudowa R02](../r02/obudowa.md) ma status „nie zamawiać”, więc zakup wymaga decyzji) |
| po dostawie prototypów, przed lutowaniem | przymiarka 1:1 ([przed produkcją](../dev-bench/przed-produkcja.md#zamówienie-2026-10-10-l0)) i wpisanie pomiarów do `MEASUREMENTS` w `zalozenia.py`: wysokości DevKitC, nasadki przycisku i szkła panelu, długość taśmy FPC, położenie Wio z u.FL i gniazda USB/OTG |
| po komplecie pomiarów prototypu | generator `build.py` (build123d): drukowana obudowa prototypu z PETG albo ASA, szablon wiercenia 1:1, test zgodności otworów z płytką v1; wybór między wgłębionym oknem a garbem nad DevKitC |
| przy projekcie płytki v2 (krok 6; w `zalozenia.py` pozycja `pilot_board`) | obrys i otwory v2 pod skrzynkę, wkład montażowy, obróbka frontu (szablon albo CNC), folia panelu PL/UK/EN; jedna sztuka, próba montażu i T8, potem 8 sztuk |
| po pilotażu (krok 8) | obudowa wyrobu: model STEP Hammonda, obrys płyty bazowej, klasa palności, ESD, próba klimatyczna; ocena pokrywy z plombą wobec naklejki ([F113](../../docs/review.md)) |

## Pliki

| Plik | Rola |
|---|---|
| `zalozenia.py` | jedno źródło założeń: koncepcja panelu, geometria płytki v1 z jej plików, lista pomiarów; `--json` odświeża `render/uklad.json` |
| `build.py` | punkt wejścia generatora; bez kompletu pomiarów wypisuje braki i kończy się kodem 2 |
| `render/stacja.html`, `render/render.js` | scena three.js i zapis PNG przez Playwright |
| `render/uklad.json` | dane sceny z `zalozenia.py`; test sprawdza, czy są aktualne |
| [tests/test_obudowa.py](../../tests/test_obudowa.py) | zgodność z plikami płytki v1, reguły układu panelu z dokumentu R02, odmowa generowania |

```sh
python3 hardware/obudowa/zalozenia.py --json   # po zmianie założeń
python3 hardware/obudowa/build.py              # dziś: lista brakujących pomiarów, kod 2
cd hardware/obudowa/render && npm install --no-save three@0.160.0 playwright && node render.js
```

`render.js` podaje three.js z lokalnego `node_modules`, a bez niego pobiera bibliotekę z jsDelivr. Generator geometrii (build123d: STEP, STL, szablon wiercenia 1:1) powstanie dopiero po przymiarce. Licencje: skrypty MIT, dokumentacja i rendery CC-BY-4.0, przyszłe pliki konstrukcyjne CERN-OHL-P-2.0 ([LICENSE.md](../../LICENSE.md)).
