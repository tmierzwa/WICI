# Wycena JLCPCB: pełny montaż L0 (SMD i THT)

**Tylko do wyceny, nie do zamówienia.** Gerbery N1 mają jeszcze złącze J7 w położeniu sprzed [F118](../../../docs/review.md): taśma FPC panelu ma 13,5 mm, a płytka zakłada 6 mm, więc panel nie mieści się w obrysie. Wycena sprawdza dostępność części, montaż przewlekany i cenę. Zamówienie dopiero z płytką z odsuniętym J7. Wtedy zmieniają się pozycje J7, R13, R19, C4, C6, C7, a w razie przesunięcia także R5–R8 i SW1–SW4, a pliki generuje się ponownie.

## Pliki

| Plik | Zawartość |
|---|---|
| [`../../dev-bench/fabrication/N1/wici-plytka-nosna-N1-gerber.zip`](../../dev-bench/fabrication/N1/wici-plytka-nosna-N1-gerber.zip) | Gerbery i wiercenia N1 |
| `bom-jlc-L0.csv` | 44 SMD z montażu N1 (R12 = 1 kΩ, jak wymaga L0) i 14 THT |
| `cpl-jlc-L0.csv` | pozycje: SMD z obrotami JLC (jak w zamówieniu 2026-10-10), THT w środku padów |

Źródło: `python3 hardware/l0-diagnostic/tools/jlc_quote.py`. Skrypt sprawdza, że każdy pad elementu THT leży na otworze z pliku wierceń i że każdy element płytki ma wiersz albo jest na liście nieobsadzonych.

Nieobsadzone (stanowiska A/B): J1–J4, J9, J10, JP3.

## Elementy THT

Części dobrane ze zrzutu biblioteki JLC (jlcparts, 2026-10-28). Stany z tego dnia.

| Element | Część | LCSC | Stan | Uwagi |
|---|---|---|---|---|
| J5, J6 | ZX-PM2.54-1-22PY | C7499337 | ~4000 | zamiennik Sullins PPTC221LFBN-RC: 1×22, 2,54 mm, wysokość 8,5 mm |
| SW1–SW4 | Omron B3F-4055 | C84931 | ~105 000 | oryginał |
| SW6 | Omron B3F-1000 | C93157 | ~7100 | oryginał |
| SW5 | E-Switch 100SP1T1B4M2QE | C273353 | 11 | oryginał, tylko „global sourcing” |
| D1 | Kingbright WP7113ID | C6926004 | 232 | oryginał |
| BZ1 | YS-MBZ12085C05R42 | C409842 | ~6200 | zamiennik CEM-1203(42): 12 mm, 2048 Hz, 5 V, 42 Ω. **Rozstaw nóżek nie jest w bazie; footprint ma 6,5 mm** |
| J11 | A2541WV-9P | C225484 | ~4400 | zamiennik Würth 61300911121 |
| JP1, JP2 | A2541WV-2P | C225477 | ~39 000 | zamiennik Würth 61300211121 |
| J12 | Phoenix 1715721 | C480516 | 197 | oryginał |

## Jak wycenić

1. jlcpcb.com, nowe zamówienie: Gerbery z zip, 2 warstwy, 1,6 mm, HASL bezołowiowy, 5 płytek; parametry jak w `FAB-NOTES.txt`.
2. PCB Assembly: strona Top, 2 sztuki. Wgrać `bom-jlc-L0.csv` i `cpl-jlc-L0.csv`.
3. Na liście części sprawdzić każdą pozycję: dopasowana część, stan, typ montażu (SMT albo THT/„Wave Soldering”) i czy któraś nie jest oznaczona jako niedostępna.
4. W podglądzie ułożenia poprawić obroty, jeśli model wypada obok padów. Szczególnie: D1 (katoda, płaski bok, na kwadratowym padzie 1, do masy), BZ1 („+” na padzie 1), J12 (wejście przewodu w stronę krawędzi płytki), J5/J6 (cały rząd na padach).
5. Zatrzymać się na podsumowaniu kosztu; nie płacić.

## Pytania do JLC (czat)

- Czy zamontują przewlekany SW5 z „global sourcing” (C273353)?
- Rozstaw nóżek BZ1 (C409842): czy 6,5 mm. Jeśli nie, zamiennik INGHAi GMC1209YB-25R2048 (C252921, 2048 Hz, rozstaw 6,5 mm) ma inną cewkę i wymaga sprawdzenia prądu w obwodzie Q1/R2.
- Gniazda J5/J6 muszą stać pionowo i w osi, bo wpina się w nie DevKitC: czy lutują je w przyrządzie.

## Poza montażem JLC

Wpięcie DevKitC, adapter Wio z przewodami, panel z taśmą FPC i jego klejenie, zworki na JP1/JP2, nasadki przycisków (B32-1310), dystanse, antena, program i próby.
