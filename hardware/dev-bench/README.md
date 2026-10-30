# WICI: płytka v1 prototypu

Płytka v1 (dawniej płytka nośna N1) łączy kupione moduły w prototyp stacji na biurku: ESP32-S3-DevKitC-1 w gniazdach, moduł Seeed Wio SX1262 na przewodach obok płytki, panel Sharp LS027B7DH01A, pamięć FRAM z ochroną przy zaniku zasilania, przyciski, przełącznik CISZA, diodę alarmu i brzęczyk. Własnego toru RF ani zasilania z ogniw i 12 V nie ma; zasila ją USB. Prototyp jest sprzętem kroku 4 planu ([koncepcja, rozdział 08](../../docs/concept/08-plan-weryfikacji-i-decyzje.html#kolejnosc-prac)), a jego wnioski przechodzą do płytki v2 stacji pilotażowej ([elektronika](../../docs/spec/elektronika.md#stacja-pilotażowa)). Katalog i pliki zachowują dawne nazwy (`dev-bench`, `fabrication/N1`), bo wykonawca prototypu pracuje na tych ścieżkach.

## Wersje

| Wersja | Stan |
|---|---|
| v1 | 5 płytek z JLCPCB zamówionych 2026-10-10, w tym 2 z montażem SMD ([zamówienie](przed-produkcja.md#zamówienie-2026-10-10-l0)). Dwie zmontowane płytki są w montażu u wykonawcy jako prototypy ([zlecenie](../l0-diagnostic/ZLECENIE.md)); trzy są gołe. Panel nie mieści się na v1 w obrysie z opisu płytki (F118); sposób ułożenia podaje krok 7 [uruchomienia](uruchomienie.md#montaż). R12 wymienia się przy montażu na 1 kΩ |
| v1.1 | projekt na `main`: złącze panelu J7 odsunięte na zmierzoną długość taśmy FPC ([F118](../../docs/review.md)). Nie do zamówienia; jest bazą płytki v2. Wycenę pełnego montażu SMD i THT w JLCPCB sprawdzono w zamkniętym [PR #129](https://github.com/tmierzwa/WICI/pull/129) |

Pliki produkcyjne w `fabrication/N1/` są rewizji v1.1; pliki v1 są w historii Git.

## Prototyp

Odbiór zmontowanego prototypu (radio, FRAM, ekran, wejścia, dioda, brzęczyk, wspólna magistrala SPI) robi program diagnostyczny ([l0-diagnostic](../l0-diagnostic/README.md)) według [instrukcji montażu i testów](../l0-diagnostic/MONTAZ-I-TESTY.md). Połączenia MCU prototypu są w [tabeli prototypu](../l0-diagnostic/reference/polaczenia-MCU-L0.csv). Po odbiorze na prototyp wgrywa się program stacji, środowisko `l0` w [firmware](../../firmware/README.md).

Płytka ma też gniazda na moduły TI, ST i Nordic (J1–J4, J9, J10, JP3) z czasów stanowisk deweloperskich A/B. Prototyp ich nie używa, a v2 ich nie dostanie. Opis stanowisk jest w [archiwum](../archiwum/stanowiska-a-b.md); obrazy `bench-*` w `firmware/` dotyczą tylko stanowisk.

## Pliki

| Plik | Zawartość |
|---|---|
| [płytka v1](plytka-nosna.md) | opis płytki: przypisanie sygnałów, mechanika, zasilanie, koszt i dostępność, źródła |
| [połączenia](polaczenia.md) | piny każdego złącza i elementu (z generatora) |
| [schemat](schemat.pdf) | schemat w PDF, eksport z `cad/` |
| `cad/` | projekt KiCad 10.0.6: schemat, PCB, reguły, lokalne biblioteki |
| `tools/` | generatory schematu i PCB, eksport, kontrole; edytowalnym źródłem jest `tools/design.py` |
| `checks/` | raporty ERC/DRC, [zapis odtworzenia](checks/odtworzenie.md), [przymiarka](checks/przymiarka.md), [zgodność z oprogramowaniem stanowisk](checks/zgodnosc-firmware.md) |
| [BOM](bom.csv) | części z MPN |
| [pliki produkcyjne](fabrication/N1/README.md) | Gerber, wiercenia, pozycje, rysunek montażowy, wydruk 1:1 |
| [uruchomienie](uruchomienie.md) | montaż, kontrola przed zasilaniem, kalibracja VTEST, ochrona FRAM, pomiar oscyloskopem, wzór zapisu sztuki |
| [obsługa](obsluga.md) | obsługa stanowisk A/B (archiwalna; zasady dla panelu, VTEST i pomiaru prądu dotyczą też prototypu) |
| [przed zamówieniem](przed-produkcja.md) | zamówienie v1, stan v1.1, warunki zamówienia i odtworzenie z generatorów |

Licencje według [LICENSE.md](../../LICENSE.md): projekt płytki i pliki produkcyjne CERN-OHL-P-2.0, skrypty MIT, dokumentacja CC-BY-4.0.
