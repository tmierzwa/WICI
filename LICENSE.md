# WICI: licencje i zakres

Własne materiały: współtwórcy WICI. Licencja zależy od ścieżki i rodzaju pliku, zgodnie z poniższą mapą. Pliki w paczkach mają te same licencje co ich źródła. Cel projektu jest niekomercyjny, ale poniższe licencje pozwalają na zastosowania komercyjne.

| Ścieżki | Licencja |
|---|---|
| `**/*.py`, `software/reference/schema.sql`, `.github/**`, `firmware/**` oraz pliki C/C++ (`*.c`, `*.h`, `*.cpp`, `*.hpp`, `*.ino`), skrypty `*.sh`, `platformio.ini` i `CMakeLists.txt` | [MIT](LICENSES/MIT.txt) |
| `docs/spec/*` (w tym `bom-stacji.csv`), `docs/concept/05-projekt-koncepcyjny-komunikacji.html` | [CERN-OHL-P-2.0](LICENSES/CERN-OHL-P-2.0.txt): opisy konstrukcji stacji i jej BOM |
| `hardware/*/cad/*.kicad_*`, tablice bibliotek `hardware/*/cad/*-lib-table`, własne footprinty `hardware/*/cad/footprints/WICI.pretty/` | CERN-OHL-P-2.0: własny projekt płytki (obecnie R02, w przygotowaniu) |
| `hardware/*/{bom.csv,connections.*,polaczenia.md,uruchomienie.md,przed-produkcja.md,*.pdf}` | CERN-OHL-P-2.0: konstrukcja i pliki do wykonania |
| `hardware/*/fabrication/`, poza `README.md`, `NOTICE.md` i `LICENSES/` danej rewizji | CERN-OHL-P-2.0: dane i rysunki wykonawcze |
| `hardware/*/checks/**/*.{kicad_pcb,dsn,ses}`, `hardware/*/checks/*.xml`, `hardware/*/checks/preview/` | CERN-OHL-P-2.0: historyczne źródła i widoki projektu |
| `hardware/*/cad/symbols/`, `hardware/*/cad/footprints/` poza `WICI.pretty` | CC-BY-SA-4.0 z wyjątkiem KiCad; teksty tej licencji i wyjątku wracają do `LICENSES/` razem z pierwszą biblioteką w CAD R02 (REUSE nie dopuszcza nieużywanych tekstów) |
| `media/logo/`: znak i ikony (litery z kroju Nunito Sans zamienione na krzywe; skrypt `znak.py` na licencji MIT) | CC-BY-4.0 |
| `media/logo/fonts/`: font Nunito Sans, © The Nunito Sans Project Authors | [SIL OFL 1.1](LICENSES/OFL-1.1.txt) |
| `media/film/`: filmy, napisy, plakat i efekt dźwiękowy | CC-BY-4.0; głos lektora i efekt dźwiękowy wygenerowano w ElevenLabs |
| Pozostałe własne Markdown, strony HTML i arkusz CSS koncepcji, raporty JSON/XML/logi, manifesty, konfiguracja repozytorium i lista zależności | [CC-BY-4.0](LICENSES/CC-BY-4.0.txt) |
| `LICENSES/*.txt`, kopie tekstów licencji i `cad/KICAD-LIBRARY-LICENSE.md` | Przytoczone teksty licencji i oryginalne warunki ich autorów; nie są ponownie licencjonowane jako własna dokumentacja |

Tę samą mapę w postaci czytelnej dla narzędzi zawiera [REUSE.toml](REUSE.toml); CI sprawdza ją poleceniem `reuse lint`, a nagłówek `SPDX-License-Identifier` w pliku ma pierwszeństwo. Reguły szczegółowe w tabeli mają pierwszeństwo przed regułą „pozostałe”. Nawiasy klamrowe i gwiazdki oznaczają wymienione pliki lub wzorce ścieżek. Podprojekty mogą dodawać informacje o pochodzeniu; nie mogą zastępować licencji cudzych materiałów.

Każdy projekt płytki zapisuje pochodzenie użytych podzbiorów bibliotek KiCad i własnych modyfikacji w `cad/KICAD-LIBRARY-LICENSE.md`. Wyjątek KiCad pozwala używać danych biblioteki w projekcie pod licencją projektu; same rozpowszechniane biblioteki i ich pochodne pozostają przy CC-BY-SA-4.0 z wyjątkiem.

Reticulum, microReticulum, LXMF i NomadNet są odrębnymi projektami; ich kod nie jest częścią tego repozytorium, a nazwy i licencje upstream pozostają bez zmian. Materiały producentów w lokalnym `reference-private/` nie są częścią repozytorium ani archiwów WICI i nie otrzymują licencji WICI.

Kod WICI jest na licencji MIT, więc można go łączyć i rozpowszechniać z Reticulum i LXMF. Ich licencje zawierają jednak dodatkowe warunki: zakaz użycia w systemach zdolnych celowo szkodzić ludziom i zakaz tworzenia zbiorów do trenowania AI. W 0.5 stos sieciowy działa w oprogramowaniu układowym stacji (port microReticulum, według opisu projektu na licencji Apache-2.0, do potwierdzenia), a laptop nie uruchamia Reticulum ani LXMF. Przed D14 trzeba ustalić, czy warunki licencji Reticulum obejmują port w C++ i implementację LXMF na mikrokontrolerze, oraz sprawdzić licencje SDK producentów (Nordic, Espressif) i bibliotek płytek. Obrazy oprogramowania stacji w `USB/firmware/` dołączają teksty licencji i pliki NOTICE wszystkich składników. Pakiet, którego składnik ma takie dodatkowe warunki, nie jest jako całość oprogramowaniem otwartym w rozumieniu OSI, choć kod WICI jest. [Przegląd, F08](docs/review.md).

Do 2026-10-07 własny kod był na GPL-3.0-or-later. Zmianę na MIT wprowadził jedyny dotychczasowy autor kodu, przed przyjęciem wkładu innych osób.
