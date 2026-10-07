# WICI: warunki przed zamówieniem

Status pozostaje **HOLD**, dopóki wszystkie pozycje nie mają potwierdzonego wyniku. W wersji 0.5 lista dotyczy stanowiska laboratoryjnego P1; wymagania płytki stacji R02 są w [specyfikacji elektroniki](../../docs/spec/elektronika.md).

| Obszar | Obecny wynik | Co trzeba zakończyć |
|---|---|---|
| Kontroler: schemat i połączenia PCB | ERC/DRC/parity: 0 | Przegląd elektryczny względem kart katalogowych, poza samą kontrolą programu |
| Mechanika | Wymiary USB z rysunku; otwory M3 i PDF 1:1 gotowe | Dopasowanie rzeczywistego USB, przycisku SW1 6 mm, IDC i wtyków TI. MPN są już podane: USB-B 61400416121, SW1 B3F-1000, IDC 61201021621 |
| Zasilanie kontrolera | Ścieżki 0,5 mm; własne przelotki kondensatorów; F1 PPTC | Pomiar prądu, spadku na F1, temperatury i stabilności przy RX/TX; sprawdzenie obu części PPTC |
| Stos warstw kontrolera | Zapisany JLC04161H-7628, nominalnie 1,6 mm; jawne grubości warstw | Potwierdzić stos u wybranego wykonawcy; policzyć i w razie potrzeby poprawić impedancję/geometrię USB dla tego stosu |
| Pliki produkcyjne kontrolera | Gerbery, PTH/NPTH, BOM z MPN i pozycje wygenerowane; eksporty sprawdzone | Fizyczne dopasowanie i kwalifikacja nadal otwarte; eksport nie zmienia HOLD |
| Referencja RF | Wspólne połączenia CSA/CPA zgodne | Poprawny, przejrzany projekt/wykonanie RF; nie zamawiać z importu KiCad |
| Import RF | DRC: 204 naruszenia, połączeń brakujących 0 | Wyjaśnić reguły wierceń, stosy padów i utracone dane importu. Zero brakujących połączeń nie oznacza poprawnego toru RF |
| Zegar RF | Zwykły kwarc referencji nie spełnia P1 | Wybrać dostępny TCXO 32 MHz i zgodny footprint, zasilanie, sprzężenie wejścia oraz pełny budżet błędu ≤ ±2,5 ppm; przygotować kalibrację |
| USB suspend i udar | Y1.1 połączone stale z V3; brak sterowanego zatrzymania zegara | Dotyczy stanowiska zasilanego z VBUS; stacja R02 jest samozasilana. ASE przy 8 MHz: do 7 mA, a cały modem w suspend ma budżet 2,5 mA. Potrzebna zmiana toru zegara/zasilania i firmware oraz pomiar całego modemu. Sprawdzić udar z pojemnościami za LDO i modułem RF; C1=1 µF sam nie zamyka bilansu USB |
| Filtr harmonicznych | Brak w wykonaniu | Filtr dolnoprzepustowy tłumiący 1739 i 2609 MHz do poziomu EN 300 220; pomiar widma z rzeczywistym filtrem |
| Ochrona wyjścia RF | Brak w wykonaniu | Ochrona ESD o małej pojemności przed złączem 50 Ω; wpływ na dopasowanie i moc zmierzony |
| Filtr SAW 868 MHz | Do oceny | Pomiar blokowania przez nadajniki LTE 800 i GSM 900 z filtrem i bez niego; strata wtrąceniowa wobec celu czułości |
| Firmware | Brak | Działający obraz, mapowanie pinów, USB CDC, SPI CC1120, profil P1 i trwały limit czasu nadawania |
| Różni dostawcy | Interfejs radia wydzielony; alternatywa LDO | Zweryfikować drugie wykonanie radia/kontrolera. S2-LP nie jest zamiennikiem CC1120 na tej samej płytce |
| Próby fizyczne | Nie wykonano | Zasilanie, USB, temperatura, widmo TX, czułość RX, odporność na restart, dwie sztuki i pomiar w terenie |

Wniosek USB wynika z połączenia Y1.1→V3 w `connections.csv` i parametrów [ASE](https://abracon.com/Oscillators/ASEseries.pdf). Odłączenie pull-up D+ nie wyłącza Y1. Zmiana projektu wymaga nowej rewizji CAD i ponownych eksportów; R01.3 nie zawiera tej poprawki. [Pełne ustalenia przeglądu](../../docs/review.md).

## RF: sprawdzone fakty

Referencja TI 868/915 ma cztery warstwy i stos o grubości około 1,24 mm: cztery warstwy miedzi po 35 µm i dielektryki 0,4 / 0,3 / 0,4 mm. Jej toru RF nie należy przenosić na dwie warstwy ani na dowolny stos FR-4. Parametry materiału i tolerancje wymagają uzgodnienia z wykonawcą.

Porównanie oryginalnych archiwów CSA i CPA obejmuje 156 wspólnych, połączonych pinów. Nie znaleziono różnic ich połączeń. PCB zawiera dodatkowo 13 pól U1.34–U1.46 należących do masy pod układem. Jest to kontrola połączeń logicznych, bez analizy impedancji i bez potwierdzenia parametrów RF.

Konwersja CADSTAR → KiCad zgłosiła utratę części reguł, obszarów ograniczeń i problem priorytetów pól miedzi. Początkowe awarie DRC wynikały z inicjalizacji aplikacji macOS w ograniczonym środowisku. DRC uruchomiony poza tym ograniczeniem zakończył się raportem: 172 naruszenia wierceń, 4 naruszenia stosów padów i inne. Trzeba odróżnić różnice reguł od rzeczywistych błędów konwersji. Importu nie można obecnie dopuścić do produkcji.

TI przewiduje opcjonalny TCXO X2 w obudowie 2,5 × 2,0 mm. Wariant referencyjny: X2, R322 = 0 Ω, C321 = 100 nF, C322 = 22 pF; nie montować X1, C311, R12 ani R321; C301 = 0 Ω zwiera XOSC_Q1, XOSC_Q2 pozostaje niepodłączone. Te wartości nie kwalifikują dowolnego nowego TCXO. Poziom i kształt sygnału na EXT_XOSC oraz pojemność sprzęgająca wymagają sprawdzenia z wybranym układem.

Przykładowy ATX-14-F-32.000MHZ-E05-T nie jest zatwierdzony. Ma inną obudowę, a jego ±0,5 ppm dotyczy temperatury. Po dodaniu tolerancji początkowej po lutowaniu, starzenia oraz wpływu zasilania i obciążenia budżet wynosi do ±3,9 ppm. Sama etykieta „TCXO ±0,5 ppm” nie spełnia tego warunku. [Karta ATX-14](https://abracon.com/datasheets/ATX-14.pdf).

Materiały TI pozostają w `reference-private`. Licencja własnego projektu nie obejmuje ich automatycznie. Przed publiczną dystrybucją trzeba rozwiązać uprawnienia do referencji RF albo przygotować własny projekt CAD z zachowaniem dozwolonego użycia dokumentacji.
