# WICI — sprzęt i programy do testów

Obecna kolejność prac: **R0 — test pary radiowej, potem L0 — test kompletnego prototypu biurkowego.** R02 czeka na decyzję po pilotażu.

## Katalogi

| Katalog | Zawartość i powód pozostawienia | Wykorzystanie teraz |
|---|---|---|
| [radio-pair](radio-pair/) | Program R0 `pair-0.1`, narzędzie testu komunikacji i testy automatyczne. Narzędzie radiowe jest współdzielone z L0. | Pierwszy test dwóch zamówionych zestawów Seeed 102010611: XIAO ESP32S3 + Wio SX1262. |
| [l0-diagnostic](l0-diagnostic/README.md) | Program L0 `l0-0.2`, instrukcja wgrania i odbioru, narzędzia, testy oraz zapis weryfikacji. | Test zmontowanego prototypu: radio, FRAM, ekran, wejścia, LED, brzęczyk i wspólna magistrala SPI. |
| [dev-bench](dev-bench/README.md) | Projekt CAD, BOM i pliki produkcyjne nośnej N1 oraz dokumentacja stanowisk TI/ST. Zachowujemy źródła sprzętu i powiązania z dokumentacją oraz firmware stanowisk. | Materiały N1; montaż L0 według uzgodnionej paczki wyceny, z połączeniami MCU z [tabeli L0](l0-diagnostic/reference/polaczenia-MCU-L0.csv). Stanowiska TI/ST są wariantem zapasowym. |
| [r02](r02/README.md) | Założenia przyszłej własnej płytki stacji: architektura, zasilanie, radio, obudowa i wnioski z poprzedniego projektu. | Projekt wstrzymany. Nie jest potrzebny do wykonania testów R0/L0; nie zamawiać płytki na jego podstawie. |

Wszystkie cztery katalogi mają odrębną rolę w repozytorium. Do uruchomienia bieżących testów potrzebne są programy R0 i L0 oraz właściwy sprzęt. Zachowanie dokumentacji R02 nie oznacza rozpoczynania jej budowy.

## Właściwy program do właściwej płytki

- **R0:** zestaw Seeed 102010611 → `radio-pair`, środowisko PlatformIO `pair`.
- **L0:** ESP32-S3-DevKitC-1-N8R8 rev.1.1 + N1 + zewnętrzny Wio SX1262 + ekran Sharp LS027B7DH01A + FRAM CY15B104QN-50SXI + panel → `l0-diagnostic`, środowisko PlatformIO `l0`.
- Programy stanowisk TI/ST są w osobnym katalogu [firmware](../firmware/README.md). Nie zastępują programów R0/L0.

Programu L0 nie wgrywa się do zestawu R0. Dokumentacja połączeń stanowisk TI/ST w `dev-bench` nie zastępuje tabeli połączeń MCU dla L0.

## Od czego zacząć

1. Po dostawie zestawów uruchomić R0: podłączyć anteny i przewody USB danych, wykonać kopie fabrycznych pamięci, wgrać program i przeprowadzić test komunikacji. Instrukcja: [R0](l0-diagnostic/reference/R0-INSTRUKCJA.txt).
2. Po montażu L0 wykonać odbiór elektryczny oraz próby podzespołów według [instrukcji L0](l0-diagnostic/README.md). Jeden zestaw R0 jest partnerem radiowym L0.
3. Na podstawie wyników zdecydować o dalszym oprogramowaniu WICI i pilotażu. Projekt R02 pozostaje wstrzymany do decyzji po pilotażu.

R0 i L0 zawierają oprogramowanie diagnostyczne. Poprawna kompilacja i testy automatyczne nie zastępują sprawdzenia rzeczywistych płytek i nie oznaczają gotowości pełnej aplikacji WICI.
