# WICI: zapis odtworzenia płytki nośnej N1

Data: 2026-10-07. Środowisko: macOS 26.6.2, KiCad 10.0.6 (`kicad-cli` i Python KiCad z `pcbnew`), Python 3.14.5 do generatorów schematu, OpenJDK 25.0.4.1 i Freerouting 2.5.0 do trasowania.

Sprawdzenie: dwa razy z rzędu `tools/build.sh`, potem `tools/finalize_board.py` z zachowaną sesją `checks/routing.ses`. Obie płytki porównane przez `tools/compare_boards.py`: footprinty, pady z sieciami, ścieżki, przelotki, strefy i rysunki są identyczne (1170 elementów, 0 różnic). Bajty plików się różnią, bo KiCad nadaje footprintom nowe UUID i według nich porządkuje plik.

Następnie DRC z `--refill-zones --save-board`: 0 naruszeń, 0 brakujących połączeń, 0 różnic PCB–schemat (`drc.json`). Sesja trasowania pochodzi z `tools/route.sh` na tym samym środowisku; Freerouting poprowadził 146 połączeń bez naruszeń.

Ten zapis dotyczy rewizji płytki w tym samym commicie co plik. Zmiana w `tools/` albo w sesji trasowania wymaga powtórzenia sprawdzenia.
