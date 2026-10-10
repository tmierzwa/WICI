# WICI: pliki produkcyjne płytki nośnej N1

**Nie zamawiać przed zamknięciem [listy przed zamówieniem](../../przed-produkcja.md).** Pliki eksportuje `tools/export_fabrication.py` z projektu po ERC 0 i DRC 0; ręcznie się ich nie poprawia.

| Plik | Zawartość |
|---|---|
| `wici-plytka-nosna-N1-gerber.zip` | Gerbery, wiercenia i `FAB-NOTES.txt` do wysłania wykonawcy |
| `FAB-NOTES.txt` | parametry płytki i zakres montażu dla wykonawcy, po angielsku |
| `gerbers/` | miedź, maska, opis obu stron (spód pusty), pasta na górze (`F_Paste`, do szablonu montażu SMD), obrys (`Edge_Cuts`) i plik zadania z rewizją N1, RS-274X X2 |
| `drill/` | wiercenia Excellon w mm, otwory platerowane (PTH) i nieplaterowane (NPTH) osobno, mapa wierceń w PDF |
| `assembly/positions.csv` | pozycje części od strony elementów (wszystkie części są na stronie górnej) |
| `assembly/montaz.pdf` | rysunek montażowy w skali 1,5 z tabliczką (rewizja N1) |
| `assembly/bom.csv` | kopia [BOM](../../bom.csv) |
| `assembly/bom-assembly.csv` | BOM dla montażowni po angielsku, tylko 32 elementy SMD: oznaczenia, ilość na płytkę, MPN; resztę lutuje właściciel według [BOM](../../bom.csv) |
| `assembly/jlc-bom.csv` | BOM w formacie JLCPCB z numerami LCSC (stany z 2026-10-10), razem z `jlc-cpl.csv` (pozycje z obrotami JLC: SOT-23, SOT-23-5 i SOT-23-6 o 180°, SOIC-8 o 270°, sprawdzone w podglądzie JLC); w miejsce części bez stanu U1 to MB85RS4MTPF-G-BCERE1, a U2 to MCP1640CT-I/CHY (wariant C tej samej przetwornicy, EN na stałe do VIN) |
| `assembly/cpl-smd.csv` | pozycje 32 elementów SMD w kolumnach Designator, Mid X, Mid Y, Layer, Rotation |
| `mechanika-1-do-1.pdf` | wydruk do przymiarki w skali 1:1 z kreską kontrolną 50 mm |

Punktem odniesienia Gerberów, wierceń i pozycji jest lewy dolny narożnik płytki.

Parametry dla wykonawcy (pełna lista w `FAB-NOTES.txt`): dwie warstwy, FR-4 1,6 mm, miedź 35 µm, HASL bezołowiowy, maska obustronna, opis tylko na górze (plik opisu spodu jest pusty), ścieżka i odstęp ≥0,2 mm, otwór ≥0,4 mm, wycięcie przy prawej krawędzi z narożnikami w promieniu frezu. Płytka nie ma kontroli impedancji. Licencja plików: CERN-OHL-P-2.0 ([LICENSE.md](../../../../LICENSE.md)).
