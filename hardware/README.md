# WICI: sprzęt i programy do prób

Katalog zawiera sprzęt i programy do kroków planu z [rozdziału 08 koncepcji](../docs/concept/08-plan-weryfikacji-i-decyzje.html#kolejnosc-prac). Nazwy katalogów, środowisk PlatformIO i obrazów są dawne (np. `l0-diagnostic`, `dev-bench`, env `l0`) i się nie zmieniają, bo wykonawca prototypu ma dokumenty z tymi ścieżkami. Dawne kody (R0, L0, N1, R02) objaśnia [słownik](../docs/concept/slownik.html).

## Kroki planu i sprzęt

| Krok | Sprzęt | Stan |
|---|---|---|
| 1. Radia testowe | 2 zestawy Seeed XIAO ESP32-S3 + Wio SX1262 z programem radiowym `pair-0.4` ([radio-pair](radio-pair/README.md)) | wykonany 2026-10-10: 100/100 w obie strony przy stole ([wyniki](radio-pair/evidence/bench-r0-2026-10-10.txt)), próby w budynku przy 0 dBm ([wyniki](radio-pair/evidence/range-r0-2026-10-10.txt)). 2026-10-31 sprawdzone jako radia RNode: oficjalne RNode 1.86 nie steruje przełącznikiem anteny RF_SW1 i odbiera o około 25 dB słabiej, z łatką z `radio-pair` działa ([wyniki](radio-pair/evidence/rnode-xiao-2026-10-31.txt), [radia RNode](../docs/spec/radio.md#radia-rnode)). Zestawy są wolne; nie są narzędziem dalszych kroków |
| 2. Radia RNode przy stole | 2 zestawy RAK19007 + RAK4631 z firmware RNode, laptopy z Reticulum w Pythonie ([rnode](rnode/README.md)) | zestawy zamówione 2026-10-29 |
| 3. Pomiar ogólny | radia RNode | po kroku 2 |
| 4. Prototyp na płytce v1 | stacja na płytce v1 ([dev-bench](dev-bench/README.md)), odbiór programem diagnostycznym ([l0-diagnostic](l0-diagnostic/README.md)), program stacji z [firmware](../firmware/README.md) | 2 prototypy w montażu u wykonawcy |
| 5. Pomiar w gminie | radia RNode | wymaga gminy pilotażowej i kroku 3 |
| 6. Stacje pilotażowe na płytce v2 | płytka v2 ([elektronika](../docs/spec/elektronika.md#stacja-pilotażowa)), obudowa ([obudowa](obudowa/README.md)), zasilanie z ogniw i 12 V (materiał w [r02](r02/README.md)) | projekt v2 po kroku 4 |
| 7. Pilotaż | 8 stacji pilotażowych | po kroku 6 |
| 8. Wyrób | stacja WICI; materiał do wydania w [r02](r02/README.md) | decyzja po pilotażu |

Procedury i warunki zaliczenia kroków są w [odbiorze](../docs/spec/odbior.md#próby-według-kroków).

## Katalogi

| Katalog | Zawartość |
|---|---|
| [radio-pair](radio-pair/README.md) | program radiowy `pair-0.4` radiów testowych, narzędzia prób i wyniki kroku 1; narzędzie testu pary jest współdzielone z programem diagnostycznym; [sonda RF_SW1](radio-pair/rfsw-probe/README.md) i łatka RNode dla tych zestawów |
| [rnode](rnode/README.md) | radia RNode: wgranie firmware, konfiguracja Reticulum, próba przy stole (krok 2) |
| [dev-bench](dev-bench/README.md) | płytka v1 prototypu: projekt CAD, generatory, BOM, pliki produkcyjne, uruchomienie; projekt v1.1 jako baza płytki v2 |
| [l0-diagnostic](l0-diagnostic/README.md) | program diagnostyczny prototypu `l0-0.5`, zlecenie i instrukcja dla wykonawcy, narzędzia, testy i zapis weryfikacji |
| [obudowa](obudowa/README.md) | założenia obudowy, lista pomiarów z przymiarki, generator odmawiający pracy bez pomiarów i render koncepcyjny |
| [przetwornica-3v3](przetwornica-3v3/README.md) | płytka testowa przetwornicy 3,3 V (LTC3115-1) do pomiaru sprawności przed schematem v2: generator, pliki dla JLC, procedura pomiaru |
| [r02](r02/README.md) | materiał do projektu płytki v2 (zasilanie z ogniw i 12 V, panel) i do wydania; części o P1 i dwóch wykonaniach są archiwalne |
| [archiwum](archiwum/README.md) | stanowiska deweloperskie A/B (TI, ST, Nordic) wstrzymane po F99 |

## Właściwy program do właściwej płytki

- **Radia testowe:** zestaw Seeed 102010611 → `radio-pair`, środowisko PlatformIO `pair`.
- **Radia RNode:** RAK4631 → oficjalny firmware RNode z `rnodeconf` ([rnode](rnode/README.md)); własnego programu WICI na nich nie ma.
- **Prototyp, odbiór:** ESP32-S3-DevKitC-1-N8R8 rev. 1.1 + płytka v1 + zewnętrzny Wio SX1262 + ekran Sharp LS027B7DH01A + FRAM CY15B104QN-50SXI albo MB85RS4MTPF-G-BCERE1 → program diagnostyczny, środowisko `l0` w `hardware/l0-diagnostic` (nie w `firmware/`).
- **Prototyp, praca:** ten sam sprzęt → program stacji, środowisko `l0` w [firmware](../firmware/README.md).

Programu diagnostycznego ani programu stacji nie wgrywa się do radiów testowych. Obrazy `bench-*` w `firmware/` dotyczą archiwalnych stanowisk A/B i nie pasują do prototypu.

Poprawna kompilacja i testy automatyczne nie zastępują prób na rzeczywistych płytkach.
