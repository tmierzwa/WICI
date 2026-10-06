# WICI — licencje i zakres

Własne materiały: współtwórcy WICI. Licencja zależy od ścieżki i rodzaju pliku, zgodnie z poniższą mapą. Pliki w paczkach mają te same licencje co ich źródła. Niekomercyjny jest cel projektu; poniższe licencje pozwalają na zastosowania komercyjne.

| Ścieżki | Licencja |
|---|---|
| `**/*.py`, `software/reference/schema.sql`, `.github/workflows/*` | [GPL-3.0-or-later](LICENSES/GPL-3.0-or-later.txt) |
| `docs/spec/*` (w tym `bom-stacji.csv`), `docs/conception/05-projekt-koncepcyjny-komunikacji.html` | [CERN-OHL-P-2.0](LICENSES/CERN-OHL-P-2.0.txt): opisy konstrukcji stacji i jej BOM |
| `hardware/radio-test-r01/cad/radio-usb-controller.*`, tablice bibliotek `cad/*-lib-table`, `cad/footprints/WICI.pretty/USB_B_61400416121.kicad_mod`, `cad/footprints/WICI.pretty/PPTC_1206_1.8x1.8_Gap1.0.kicad_mod` | CERN-OHL-P-2.0: własny projekt i dwa własne footprinty |
| `hardware/radio-test-r01/{bom.csv,assembly-parts.json,connections.*,polaczenia.md,uruchomienie.md,przed-produkcja.md,zmiany-R01-*.md,schemat.pdf,mechanika-1-do-1.pdf}` | CERN-OHL-P-2.0: konstrukcja i pliki do wykonania |
| `hardware/radio-test-r01/fabrication/R01.3/`, poza `README.md`, `NOTICE.md` i `LICENSES/` | CERN-OHL-P-2.0: dane i rysunki wykonawcze |
| `hardware/radio-test-r01/checks/history/*.{kicad_pcb,dsn,ses}`, pozostałe `checks/*.{dsn,ses}`, `checks/schematic.net.xml`, `checks/preview/` | CERN-OHL-P-2.0: historyczne źródła i widoki projektu |
| `hardware/radio-test-r01/cad/symbols/`, footprinty poza dwoma własnymi wskazanymi wyżej; w tym `WICI.pretty/IDC_61201021621.kicad_mod` | [CC-BY-SA-4.0](LICENSES/CC-BY-SA-4.0.txt) z [wyjątkiem KiCad](hardware/radio-test-r01/cad/KICAD-LIBRARY-LICENSE.md) |
| Pozostałe własne Markdown, strony HTML i arkusz CSS koncepcji, raporty JSON/XML/logi, manifesty, konfiguracja repozytorium i lista zależności | [CC-BY-4.0](LICENSES/CC-BY-4.0.txt) |
| `LICENSES/*.txt`, kopie tekstów licencji i `cad/KICAD-LIBRARY-LICENSE.md` | Przytoczone teksty licencji i oryginalne warunki ich autorów; nie są ponownie licencjonowane jako własna dokumentacja |

Reguły szczegółowe w tabeli mają pierwszeństwo przed regułą „pozostałe”. Nawiasy klamrowe i gwiazdki oznaczają wymienione pliki lub wzorce ścieżek. Podprojekty mogą dodawać informacje o pochodzeniu; nie mogą zastępować licencji cudzych materiałów.

Pochodzenie podzbiorów KiCad i modyfikacji IDC: [hardware/radio-test-r01/LICENSES.md](hardware/radio-test-r01/LICENSES.md). Wyjątek KiCad pozwala używać danych biblioteki w projekcie pod licencją projektu; same rozpowszechniane biblioteki i ich pochodne pozostają przy CC-BY-SA-4.0 z wyjątkiem.

Reticulum, LXMF i NomadNet są odrębnymi projektami. Ich kod nie jest częścią tego repozytorium. Ich nazwy i licencje upstream pozostają bez zmian. Materiały producentów w lokalnym `reference-private/` nie są częścią repozytorium ani archiwów WICI i nie otrzymują licencji WICI.

Przed dystrybucją pakietu START z zależnościami trzeba rozstrzygnąć zgodność ich konkretnych licencji z własnym kodem GPL. Reticulum i LXMF w wersjach objętych [przeglądem](docs/review.md) zawierają dodatkowe ograniczenia; samo dołączenie tekstów licencji nie zamyka tej oceny.
