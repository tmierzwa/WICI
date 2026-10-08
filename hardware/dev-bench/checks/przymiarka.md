# WICI: przegląd plików produkcyjnych i przymiarka N1

## Przegląd Gerberów i wierceń

**Rewizja F103 (2026-10-08):** kontrola liczbowa paczki z gerbonara 1.6.3: obrys 170 × 100 mm, osiem warstw jak w `FAB-NOTES.txt`, 222 otwory PTH (w tym 62 przelotki 0,4 mm) i 17 NPTH (1,8 i 3,2 mm), 100 otwarć pasty, czyli dokładnie tyle, ile padów SMD ma 39 elementów (34 dwupadowe, D3 i Q1 po 3, U1 8, U2 6, J7 10 + 2). Pełny przegląd z renderem warstw (jak niżej) dla tej rewizji jest **otwarty**.

Poniżej przegląd rewizji sprzed F103 (bez przetwornicy panelu).

Data: 2026-10-08. Wykonał autor z pomocą AI; nie jest niezależnym audytem. Pliki: paczka `fabrication/N1/wici-plytka-nosna-N1-gerber.zip` z commita, w którym leży ten zapis (Gerbery X2 i Excellon z KiCad 10.0.6). Narzędzia: gerbonara 1.6.3 (złożenie warstw obu stron i kontrola geometrii z shapely) i pygerber 2.4.3 (render każdej warstwy osobno). Nie użyto przeglądarki wykonawcy; jej podgląd ogląda się przy zamówieniu razem z raportem DFM.

Obejrzane warstwy: miedź góra i dół, maska góra i dół, pasta, opis góra i dół, obrys, wiercenia PTH i NPTH, złożenie obu stron i powiększenia J7, U1, Q1 i D2, J9 i J10.

| Kontrola | Wynik |
|---|---|
| Obrys | zamknięty, 170 × 100 mm, wycięcie 7,58 × 9,3 mm na prawej krawędzi (x ≥ 162,42 mm, y 46,66–55,96 mm); zgodny z `FAB-NOTES.txt` i plikiem zadania (`gbrjob`: 2 warstwy, 1,6 mm, HASL bezołowiowy) |
| Miedź | najmniejszy odstęp miedzi od krawędzi 0,5 mm na obu warstwach; nic poza obrysem. Najwęższa ścieżka 0,25 mm, z wyjątkiem krótkich odcinków 0,24 mm między padami J7 (raster 0,5 mm), które Freerouting zwęził przy wejściu w pady; wpisane do `FAB-NOTES.txt` |
| Otwory | 219 PTH w siedmiu średnicach i 17 NPTH (1,8 i 3,2 mm), jak w `FAB-NOTES.txt`; najmniejszy mostek między otworami 0,61 mm (dwie przelotki); najmniejszy pierścień 0,175 mm (J9/J10, otwór 0,65 mm w padzie 1,0 mm), jak w uwagach |
| Otwory przy krawędzi | H8 i H9 (3,2 mm, x 167,46 mm) leżą 0,94 mm od prawej krawędzi, górny 1,66 mm od wycięcia. Położenie wynika z otworów Arduino płytki pod spodem; wpisane do `FAB-NOTES.txt`, żeby wykonawca ich nie przesuwał |
| Miedź przy NPTH | co najmniej 0,3 mm od krawędzi każdego otworu, jak w uwagach |
| Maska | każdy pad przewlekany ma otwarcie na obu stronach; 59 przelotek zakrytych (0 otwarć); otwarcia bez miedzi to tylko 17 otworów NPTH |
| Pasta | 82 otwarcia, wszystkie na miedzi górnej i w otwarciach maski, żadne nad otworem; liczba zgadza się z 32 elementami SMD (28 dwupadowych, D3 i Q1 po 3, U1 8, J7 10 + 2 pady mocujące) |
| Opis | linia co najmniej 0,15 mm; nic nie wchodzi na otwarcia maski; polskie znaki czytelne; opis spodu pusty (plik zawiera tylko wycięcia pod pady) |
| Elementy SMD | każda pozycja z `cpl-smd.csv` wypada na padach swojego elementu (dla elementów bez sąsiadów w promieniu 4 mm środek padów pokrywa się z pozycją co do 0,01 mm); znacznik pinu 1 widoczny przy U1 i Q1; pad 1 złącza J7 po prawej, wejście taśmy od strony obrysu panelu |

Uwagi bez wpływu na zamówienie: oznaczenia C4 i C7 stoją między dwoma elementami, a JP1–JP3 mają podwójny opis (oznaczenie i funkcja). C4 i C7 wykonawca umieszcza według pozycji, a nie opisu; przy ręcznym lutowaniu pomaga [rysunek montażowy](../fabrication/N1/assembly/montaz.pdf).

Wynik: pliki są zgodne z płytką i z `FAB-NOTES.txt`; nie znaleziono błędów. Ponowny eksport z poprawionymi uwagami zmienił w Gerberach i wierceniach tylko datę utworzenia.

## Przymiarka 1:1

**Otwarte.** Zakres w [liście przed zamówieniem](../przed-produkcja.md#warunki). Zapisuje się: osobę, datę, zmierzoną kreskę 50 mm z `fabrication/N1/mechanika-1-do-1.pdf` i wynik każdej pozycji (DK, DevKitC, CC1120EM, X-NUCLEO-S2868A2, panel Sharp z taśmą FPC w FH12, przyciski z nasadkami, przełącznik, zacisk, wysokości części DK).
