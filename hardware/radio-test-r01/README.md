# WICI R01.3: prototyp interfejsu radiowego

**Status: HOLD. Nie zamawiać PCB ani montażu całego modemu.**

Przegląd elektryczny wskazał problem USB suspend: Y1 ma stale włączony zegar, więc parametry katalogowe nie gwarantują dotrzymania pełnego budżetu prądu. Przed wykonaniem potrzebne są poprawiona rewizja i odbiór całego modemu. [Warunki przed zamówieniem](przed-produkcja.md).

Repozytorium zawiera edytowalne pliki kontrolera USB w KiCad. Tor radiowy CC1120 jest osobnym modułem opartym na referencji TI. Do testu między dwiema stacjami potrzeba dwóch kontrolerów i dwóch modułów RF.

| Plik | Zawartość |
|---|---|
| [Projekt KiCad](cad/radio-usb-controller.kicad_pro) | Schemat, PCB 70 × 55 mm, cztery warstwy, lokalne biblioteki |
| [Schemat](cad/radio-usb-controller.kicad_sch) | USB, STM32, zegar, EEPROM, programator, interfejs radia |
| [PCB](cad/radio-usb-controller.kicad_pcb) | Rozmieszczenie i poprowadzone połączenia |
| [BOM](bom.csv) | MPN i producenci; 39 pozycji montażowych na jeden kontroler; TP1–TP7 to pola pomiarowe |
| [Połączenia](polaczenia.md) | Numery pinów i przewód do referencji TI |
| [Uruchomienie](uruchomienie.md) | Kolejne pomiary oraz warunki przerwania próby |
| [Otwarte sprawy](przed-produkcja.md) | Przeszkody przed zamówieniem |
| [Zmiany R01.3](zmiany-R01-3.md) | Stos 1,6 mm, rewizja, MPN i zweryfikowane eksporty |
| [Paczka produkcyjna](fabrication/wici-controller-R01.3.zip) | Kandydat: Gerbery, wiercenia i pliki montażowe samego kontrolera |
| [Zmiany R01.2](zmiany-R01-2.md) | Zasilanie 0,5 mm, przelotki, otwory i bezpiecznik |
| [Wydruk 1:1](mechanika-1-do-1.pdf) | Fizyczna kontrola USB-B, SW1 i IDC; druk 100%, bez odbicia |
| [Weryfikacja](checks/status.json) | Wyniki, zakres i ograniczenia kontroli |

Kontroler: ERC 0, DRC 0, brakujących połączeń 0, różnic PCB–schemat 0. Raporty pochodzą z KiCad 10.0.6, z jawnymi regułami w pliku `.kicad_dru` i wypełnionymi polami miedzi. Kontrola zachowuje domyślne pominięcia KiCad wymienione w JSON; nie jest pełnym dowodem poprawności układu.

**Nie ma jeszcze gotowego modemu do użycia.** Nie ma firmware, zaakceptowanego zegara RF, zweryfikowanego pliku produkcyjnego RF ani wyników fizycznych prób. DRC nie sprawdza impedancji USB, dopasowania anteny, jakości lutowania ani zasięgu. Zasięg 1 km jest celem, który wymaga pomiaru.

Wygenerowano i sprawdzono paczkę Gerberów samego kontrolera R01.3. Nie sprawdzono fizycznego dopasowania złączy. Stos producenta jest zapisany w PCB; ocena impedancji USB i kwalifikacja układu pozostają otwarte. Lokalny folder `reference-private` zawiera materiały producenta i niezaakceptowaną konwersję oznaczoną `NOT-FOR-FAB`; folder nie jest częścią repozytorium.

[Odtworzenie kontroli i paczek](odtworzenie.md). [Środowisko narzędzi](../../docs/development.md).

Otwórz plik projektu w KiCad 10.0.6. Nie trzeba instalować dodatkowych bibliotek elementów. [Licencje](LICENSES.md) rozdzielają własny projekt od materiałów producentów.
