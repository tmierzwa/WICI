# WICI: pliki produkcyjne płytki nośnej N1

**Nie zamawiać przed zamknięciem [listy przed zamówieniem](../../przed-produkcja.md).** Pliki eksportuje `tools/export_fabrication.py` z projektu po ERC 0 i DRC 0; ręcznie się ich nie poprawia.

| Plik | Zawartość |
|---|---|
| `wici-plytka-nosna-N1-gerber.zip` | Gerbery i wiercenia do wysłania wykonawcy |
| `gerbers/` | miedź, maska, opis obu stron i obrys (`Edge_Cuts`), RS-274X |
| `drill/` | wiercenia Excellon w mm, otwory platerowane (PTH) i nieplaterowane (NPTH) osobno, mapa wierceń w PDF |
| `assembly/positions.csv` | pozycje części od strony elementów (wszystkie części są na stronie górnej) |
| `assembly/montaz.pdf` | rysunek montażowy w skali 1,5 |
| `assembly/bom.csv` | kopia [BOM](../../bom.csv) |
| `mechanika-1-do-1.pdf` | wydruk do przymiarki w skali 1:1 z kreską kontrolną 50 mm |

Punktem odniesienia Gerberów, wierceń i pozycji jest lewy dolny narożnik płytki.

Parametry dla wykonawcy: dwie warstwy, FR-4 1,6 mm, miedź 35 µm, maska i opis obustronne, ścieżka i odstęp ≥0,2 mm, otwór ≥0,4 mm, wycięcie przy prawej krawędzi z narożnikami w promieniu frezu. Płytka nie ma kontroli impedancji. Licencja plików: CERN-OHL-P-2.0 ([LICENSE.md](../../../../LICENSE.md)).
