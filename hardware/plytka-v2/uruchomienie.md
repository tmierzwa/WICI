# Płytka v2: pierwsze uruchomienie krok po kroku

Procedura dla osoby, która nie zna elektroniki. Każdy krok to jedna czynność. Liczby pochodzą z dokumentów w repozytorium; źródło jest w nawiasie kwadratowym. Wartość przyjęta bez źródła jest oznaczona „(założenie)”.

**STOP** znaczy zawsze to samo:
1. Wyłącz wyjście zasilacza (przycisk wyjścia na DPS-150).
2. Odłącz przewody od płytki.
3. Nie rób następnego kroku.
4. Zapisz, co widzisz (odczyty, zdjęcie, numer kroku) i zgłoś to.

**ZAPISZ** znaczy: wynik poza oczekiwanym pasmem, ale płytce nic nie grozi. Zapisz wartość, zaznacz ją na czerwono i rób dalej.

Kolejność kroków jest ważna. Nie przeskakuj do przodu. Próba podłączania pod napięciem (część 7) jest na końcu, bo tylko ona może uszkodzić układ U5 na płytce bez D20.

## Jak orientować płytkę i gdzie mierzyć

**Strona górna** to strona z wieloma drobnymi elementami i z gniazdem USB-C (J4). Na sitodruku nie ma napisów przycisków; są tylko oznaczenia części (np. „D4”, „R78”, „JP3”). Płytka leży gniazdem USB-C do siebie: USB-C jest wtedy na dolnej krawędzi, około jednej czwartej szerokości od lewej. Położenia podaję w milimetrach od lewego górnego narożnika patrząc od góry (x w prawo, y w dół; płytka ma 200 × 120 mm).

**Strona dolna** ma tylko części przewlekane: złącza przewodów J1, J2, J3, gniazda modułów J5, J6, J8, J9, oprawkę bezpiecznika F1 i duży kondensator C50. Na sitodruku spodu są podpisy „J1”, „J2”, „J3”, „J5”, „J6”, „C50”. Po odwróceniu płytki (obrót wokół osi pionowej) lewa i prawa strona się zamieniają: gniazdo J6 jest wtedy na prawo od J5.

**Pin 1 każdego złącza i gniazda ma pad prostokątny**, pozostałe piny mają pady okrągłe lub owalne. Tak jest po obu stronach płytki [plik płytki `cad/plytka-v2.kicad_pcb`].

**Rysunek montażowy.** Małe części w gęstych grupach (np. C38) nie mają nazwy na sitodruku [README, „Poprawki po przeglądzie”, punkt 8]. Wydrukuj dwa rysunki: `rysunek-montazowy-gora.pdf` i `rysunek-montazowy-spod.pdf` (spód jest narysowany w lustrzanym odbiciu, tak jak widać go po odwróceniu płytki). Polecenie, które je tworzy (kicad-cli z KiCad 10, na macOS `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`):

```
kicad-cli pcb export pdf --mode-single --scale 0 --layers F.Fab,F.Silkscreen,Edge.Cuts --sp --black-and-white -o rysunek-montazowy-gora.pdf hardware/plytka-v2/cad/plytka-v2.kicad_pcb
kicad-cli pcb export pdf --mode-single --scale 0 -m --layers B.Fab,B.Silkscreen,Edge.Cuts --sp --black-and-white -o rysunek-montazowy-spod.pdf hardware/plytka-v2/cad/plytka-v2.kicad_pcb
```

### Punkty pomiarowe (sprawdzone w pliku płytki)

| Punkt | Co to jest | Gdzie (patrząc od góry) |
|---|---|---|
| **MASA** | wspólny biegun ujemny | okrągły pad C50 (x 130, y 84). C50 stoi od spodu, ale końce jego nóżek wystają od góry i da się na nich zaczepić krokodylek. Zapasowo: **górny** pad R78 (x 143, y 23,8) |
| **VSYS** | szyna za ogniwami i za wejściem 12 V | prostokątny pad C50 (x 134, y 84) |
| **+3V3** | wyjście przetwornicy 3,3 V (U7) | prostokątny (lewy) pin zworki JP3 (x 171, y 70) |
| **+5V** | wyjście przetwornicy ekranu (U2) | lewy pad R2 (x 159, y 17, obok brzęczyka BZ1) |
| **ON** | szyna „stacja włączona” | **dolny** pad R78 (x 143, y 25,6); górny pad R78 to masa |
| **WEJŚCIE 12 V** | za bezpiecznikiem | prawy pad D4 (x 88, y 108) |
| **C38** | wejście łącznika U5 | lewy pad C38 (x 183,7, y 108,7) to wejście, prawy (x 185,6) to masa; pady 1,9 mm od siebie |

Czarny przewód multimetru zawsze na MASIE (krokodylkiem na nóżce C50), czerwony na punkcie.

## 0. Przygotowanie

### Przyrządy i ich granice

1. **Zasilacz FNIRSI DPS-150.** Wyjście 0–30 V, 0–5 A; nastawa i wyświetlacz prądu co 1 mA, ale dokładność odczytu prądu to ±5 mA [producent: fnirsi.com/products/dps-150; Elektor, recenzja DPS-150]. Zasilacz tylko obniża napięcie: wyjście jest zawsze niższe niż napięcie, które go zasila. Z ładowarką USB-PD (najwyżej 20 V) da najwyżej około 19 V. Do 24 V i 28,8 V w części 7 potrzebne jest zasilanie wejścia 32 V. **33 V ten zasilacz nie da w ogóle.**
2. Odczyt prądu DPS-150 poniżej około 10 mA nic nie znaczy. Prądy w µA mierzy PPK2.
3. **Nordic PPK2.** Jako źródło: 0,8–5,0 V, do 1 A (do 1 A potrzebne są dwa przewody USB). Jako amperomierz: tylko na przewodzie o napięciu 0,8–5,0 V [nordicsemi.com/ppk2, instrukcja PPK2]. Nigdy nie podłączaj go do J2 ani do VSYS.
4. **FNIRSI 2D15P.** Zasilany z własnego akumulatora. Z sondą 10X przyjmuje do 800 V [producent: fnirsi.com/products/2d15p]. Nie wiadomo, czy wejście multimetru jest odizolowane od masy oscyloskopu. Dlatego: **multimetr w tym urządzeniu tylko do napięć i oporności, nigdy jako amperomierz w obwodzie**, i nigdy nie mierz multimetrem, gdy sonda oscyloskopu jest podłączona gdziekolwiek poza MASĄ płytki.
5. Sonda 10X z krótką sprężynką masy.

### Do kupienia lub przygotowania

6. Bezpiecznik T1A 5 × 20 mm (Schurter 0001.2504 albo Littelfuse 0477001); JLC montuje tylko zaciski [design.py, EXTRAS, F1].
7. Dwie wtyczki JST XH 2-pinowe z przewodami (do J1 i J2), zakończone krokodylkami albo wtykami do zasilacza.
8. Wiązka z przyciskiem do J3 (wygodniejsza niż pęseta, bo przy przytrzymaniu przez 10–20 s trzeba jeszcze patrzeć na miernik).
9. Przewód połączeniowy męski–męski 2,54 mm (Dupont), około 10 cm (do części 4).
10. Cztery tulejki dystansowe M3 o wysokości co najmniej 25 mm z wkrętami do otworów H1, H2, H3 i H6 (Ø3,5 mm). Moduły od spodu sięgają około 16 mm pod płytkę [README, „Rozmieszczenie wstępne”, wysokości].
11. Antena 868 MHz albo obciążenie 50 Ω na u.FL (część 5).
12. Koszyk 4 × AA z ogniwami (część 6).
13. Do części 7: kondensator elektrolityczny co najmniej 1000 µF na co najmniej 63 V (założenie: wyraźnie powyżej 33 V), źródło 24–33 V (punkt 1) i **dwa krótkie druty przylutowane do padów C38** (punkt 7.3). Lutowanie zleć temu, kto dolutowuje D20.
14. Kartka na wyniki: numer płytki, data, kto, przyrządy.

### Stanowisko

15. Przykręć płytkę na tulejkach, stroną górną do góry. Płytka nie może leżeć na stole: od spodu są złącza, C50 i bezpiecznik.
16. Pod płytką ma być pusto: żadnych narzędzi, ścinków drutu, pęsety. Podkładka nieprzewodząca (np. karton).
17. Zanim dotkniesz modułów (część 5), dotknij uziemionego metalu albo obudowy zasilacza.

### Zasady na cały czas

18. Do części 5 płytka jest **bez modułów**: bez DevKitC w J5/J6, bez Wio w J8/J9, bez taśmy ekranu w J7.
19. Najpierw napięcie i ograniczenie prądu na zasilaczu przy wyłączonym wyjściu, potem przewody, na końcu wyjście.
20. Nigdy więcej niż 33,0 V na J2. Od 36,7 V przewodzi dioda D4 [README, „Dobór części”, D4].
21. Nigdy nie wkładaj żadnego przewodu do żadnego z dwóch gniazd USB na samej płytce DevKitC, gdy jest w płytce. DevKitC dopuszcza tylko jedno źródło zasilania, a drugie gniazdo DevKitC jest połączone z tymi samymi liniami USB co J4 [elektronika.md, „Gniazdo USB do laptopa”; design.py, komentarz przy DEVKIT].
22. Od części 5: nie włączaj stacji z Wio bez anteny albo obciążenia 50 Ω na u.FL (założenie: program może nadawać sam).
23. Masa sondy oscyloskopu tylko na MASĘ płytki.

Pomyłka biegunowości nie powinna uszkodzić płytki: odwrotne 12 V do 33 V i odwrotnie włożone ogniwa są w wymaganiach odbioru [odbior.md, „Zasilanie stacji – progi”, „Tor zasilania stacji pilotażowej”]. Mimo to sprawdzaj biegunowość, bo te próby jeszcze się nie odbyły.

## 1. Oględziny bez zasilania (lupa albo zdjęcie telefonem w powiększeniu)

1. Obejrzyj nóżki układów, czy nie ma mostka cyny między sąsiednimi nóżkami:
   - U5 (łącznik 12 V, x 168, y 108; nóżki co 0,5 mm),
   - U6 (sterownik przycisku, x 152, y 36),
   - U7 (przetwornica 3,3 V, x 129, y 57),
   - U2 (przetwornica 5 V, x 63, y 66),
   - złącze ekranu J7 (x 42, y 67; nóżki co 0,5 mm),
   - gniazdo USB-C J4 i układ U8 obok niego.
2. Od spodu obejrzyj luty wszystkich części przewlekanych: J1, J2, J3, J5, J6, J8, J9, F1, C50. Każda nóżka ma mieć błyszczący stożek lutu.
3. C50 od spodu: pasek „−” na korpusie leży po stronie przeciwnej do znaku „+” na płytce [README, „Sprawdzenie w podglądzie JLC”].
4. Diody (małe prostokąty z paskiem): pasek po tej samej stronie co pasek na sitodruku [tamże].
5. Dioda alarmu D1: ścięcie obudowy po stronie ścięcia na sitodruku. Brzęczyk BZ1: „+” przy „+” [tamże].
6. Zaciski bezpiecznika F1 od spodu: płytka ogranicznika każdego zacisku po stronie zewnętrznej, przy białej kresce [README, „Pliki produkcyjne”, zaciski F1].
7. Włóż bezpiecznik T1A w zaciski. **STOP, jeśli trzeba go wciskać:** luz to tylko 0,2–0,55 mm na stronę [README, „Pliki produkcyjne”, rozstaw zacisków].
8. Od spodu: cztery nóżki obudowy gniazda USB-C. Jeśli któraś nie ma lutu, zapisz; dolutowanie przed częścią 5 (wkładanie wtyku) [README, „Pliki produkcyjne”].
9. Płytka z D20: D20 (prostokąt SMB, x 181, y 114, pod C38) przylutowana obiema stronami. Kierunek nie ma znaczenia (dioda dwukierunkowa) [design.py, D20]. Płytka bez D20: pole puste.
10. Oznacz płytki naklejkami: „z D20” i „bez D20”.
11. **STOP, jeśli** widzisz mostek cyny, brak części, część obróconą wbrew rysunkowi albo ślady przegrzania.

## 2. Oporność do masy bez zasilania

Multimetr w trybie oporności. Płytka bez modułów, bez zasilania. Na szynach z dużymi kondensatorami odczyt rośnie przez kilka sekund; zapisz wartość po około 10 s.

1. Pin 2 J1 (pad okrągły) do MASY: poniżej 1 Ω.
2. Pin 2 J2 (pad okrągły) do MASY: poniżej 1 Ω.
3. Włóż wtyczkę do J1. Zmierz od każdego z jej przewodów do MASY. Przewód z wynikiem poniżej 1 Ω to minus; oznacz go taśmą. Drugi to plus.
4. To samo z wtyczką do J2.
5. Bezpiecznik: pin 1 J2 (pad prostokątny) do WEJŚCIA 12 V (prawy pad D4): poniżej 1 Ω.

Szyny do masy. Projekt nie ma na żadnej szynie oporu do masy mniejszego niż setki kΩ [design.py: R70/R71, R61/R62, R21/R22; brak rezystora do masy na VSYS i wejściu ogniw]. Liczy się „nie zwarcie” i porównanie dwóch płytek.

| Krok | Punkt (czerwony przewód) | Oczekiwane |
|---|---|---|
| 6 | pin 1 J2 | setki kΩ (dzielnik R70 280 kΩ + R71 30,1 kΩ przez diodę D13) |
| 7 | pin 1 J1 | rośnie, kończy na setkach kΩ albo poza zakresem |
| 8 | VSYS | rośnie powoli, kończy na setkach kΩ albo więcej |
| 9 | +3V3 | rośnie powoli, kończy na setkach kΩ albo MΩ (dzielnik R61 + R62 = 1,43 MΩ) |
| 10 | +5V | setki kΩ albo MΩ (dzielnik R21 + R22 = 1,31 MΩ) |

11. Zmierz między VSYS a +3V3: nie może być zwarcia.
12. Zapisz odczyty obu płytek obok siebie.
13. **STOP, jeśli** którakolwiek szyna ma do masy mniej niż 100 Ω albo VSYS i +3V3 mają między sobą mniej niż 100 Ω.
14. **STOP i zapytaj, jeśli** odczyt leży między 100 Ω a 10 kΩ albo ta sama szyna na dwóch płytkach różni się więcej niż dziesięciokrotnie (progi: założenie).

## 3. Zasilanie bez modułów

### 3a. Z wejścia ogniw (J1), stacja wyłączona

1. Przy wyłączonym wyjściu ustaw 6,0 V.
2. Ustaw ograniczenie prądu 0,10 A [przetwornica-3v3/README.md, „Pomiar”: pierwsze włączenie 100–200 mA].
3. Wtyczka J1: plus zasilacza na przewód „plus”, minus na przewód z taśmą. Włóż wtyczkę do J1.
4. Włącz wyjście.
5. Odczytaj prąd. Oczekiwane: 0,000–0,005 A (stacja wyłączona bierze około 13 µA, czego ten zasilacz nie pokaże) [README, „Na pierwszych sztukach v2”, prąd w stanie wyłączonym].
6. **STOP, jeśli** zasilacz zostaje w ograniczeniu prądu (wskaźnik CC) dłużej niż 1 s albo pokazuje ponad 0,010 A.
7. Zmierz VSYS: 5,5–6,0 V (dioda D7 traci przy małym prądzie mniej niż 0,43 V) [README, „Dobór części”, D7].
8. Zmierz +3V3: poniżej 0,1 V.
9. Zmierz ON: poniżej 0,1 V [README, „Dobór części”, R78].
10. **STOP, jeśli** +3V3 albo ON ma ponad 0,3 V (stacja nie może włączyć się sama z ogniw [README, „Tor zasilania”, włączenie z ogniw]).

### 3b. Prąd w stanie wyłączonym (PPK2)

11. Wyłącz wyjście zasilacza, odłącz wtyczkę J1 od zasilacza.
12. Podłącz wtyczkę J1 do PPK2 w trybie źródła (Source meter), 5,0 V.
13. Włącz zasilanie w programie PPK2, odczekaj 1 minutę, zapisz średni prąd. Oczekiwane: typowo około 13 µA, najwyżej 0,1 mA [README, „Na pierwszych sztukach v2”; elektronika.md, „pobór”].
14. **ZAPISZ, jeśli** ponad 20 µA (wpływa na wybór C50 [README, „Kondensator szyny C50”]). **STOP, jeśli** ponad 0,1 mA.
15. Wyłącz PPK2, podłącz wtyczkę J1 z powrotem do zasilacza (6,0 V, 0,10 A), włącz wyjście.

### 3c. Włączenie przyciskiem

16. Naciśnij przycisk na wiązce J3 na około pół sekundy. Sterownik reaguje po 19–45 ms [karta LTC2955, tDB(ON)].
17. Odczytaj prąd. Oczekiwane: kilka mA albo mniej (wyświetlacz może pokazać 0,000–0,010 A).
18. **STOP, jeśli** prąd przekracza 0,050 A albo zasilacz zostaje w ograniczeniu (założenie: bez modułów nic nie bierze dziesiątek mA).
19. Zmierz +3V3: około 3,31 V; z tolerancją części 3,22–3,39 V [design.py, R61/R62; karta LTC3115-1, napięcie FB 0,977–1,017 V].
20. **STOP, jeśli** +3V3 jest poza 3,2–3,4 V (3,6 V to maksimum FRAM [design.py, U1]).
21. Zmierz +5V: około 5,13 V; z tolerancją 4,90–5,36 V [elektronika.md, „ekran”; karta MCP1640, VFB 1,175–1,245 V].
22. **STOP, jeśli** +5V jest poza 4,8–5,5 V (zakres zasilania panelu Sharp [elektronika.md, „ekran”]).
23. Zmierz ON: około 5–5,5 V przy 6,0 V na wejściu [README, „Tor zasilania”, klucze przy końcu ogniw: przy 4 V ON około 3,3 V].
24. Po minucie dotknij palcem U7, U2, U6. **STOP, jeśli** któryś jest wyraźnie ciepły (założenie).
25. Ustaw 7,3 V. Zmierz +3V3: 3,22–3,39 V.
26. Ustaw 4,4 V. Zmierz +3V3: 3,22–3,39 V.
27. Ustaw 4,0 V. Zmierz +3V3: 3,22–3,39 V [elektronika.md, napięcia ogniw].
28. **STOP, jeśli** przy którymkolwiek +3V3 jest poza 3,2–3,4 V.
29. Wróć do 6,0 V.

### 3d. Wyłączenie przytrzymaniem (bez programu)

30. Czerwony przewód multimetru na +3V3 (krokodylkiem albo haczykiem, żeby mieć wolne ręce).
31. Naciśnij i trzymaj przycisk J3, w tej samej chwili włącz stoper.
32. Puść, gdy +3V3 spadnie poniżej 0,5 V. Zapisz czas. Oczekiwane: 5,2–19 s, nominalnie około 11,5 s [design.py, C37; karta LTC2955: 5,2 s/µF].
33. **STOP, jeśli** stacja nie wyłącza się po 25 s (założenie).
34. Zmierz ON: poniżej 0,1 V.
35. Wyłącz wyjście, odłącz J1.

### 3e. Z wejścia 12 V (J2), bez ogniw

Przy podłączeniu 12 V stacja **włącza się sama**, bez przycisku. To zamierzone [README, „Tor zasilania”, samoczynne włączenie; „Decyzje”, 4].

36. Przy wyłączonym wyjściu ustaw 12,6 V i ograniczenie 0,30 A (założenie: powyżej prądu włączania około 250 mA [design.py, C32]).
37. Wtyczka J2: plus na przewód „plus”, minus na przewód z taśmą. Włóż do J2.
38. Włącz wyjście.
39. Po 2 s odczytaj prąd: kilka mA. **STOP, jeśli** ponad 0,050 A albo zasilacz zostaje w ograniczeniu.
40. Zmierz +3V3 (bez naciskania przycisku): 3,22–3,39 V. To potwierdza samoczynne włączenie.
41. Zmierz VSYS: 12,5–12,6 V [README, „Dobór części”, Q2, Q3: 23 mΩ].
42. Zmierz +5V: 4,90–5,36 V. Warunki STOP jak w krokach 20 i 22.
43. Zmierz WEJŚCIE 12 V (prawy pad D4) i porównaj z wyświetlaczem zasilacza. Różnica ma być poniżej 0,05 V. Jeśli jest, w 3f i 3g napięcie wejścia odczytujesz z wyświetlacza zasilacza (jeden multimetr mierzy wtedy +3V3 albo ON).

### 3f. Progi wejścia 12 V (co 0,1 V, kilka sekund na krok)

44. Multimetr na +3V3. Zmniejszaj napięcie od 12,6 V co 0,1 V.
45. Zapisz napięcie, przy którym +3V3 znika. Oczekiwane: 10,98 V (10,58–11,24 V) [README, „Decyzje”, 1]. Odbiór: nie wcześniej niż przy 11,3 V, najpóźniej przy 10,5 V [odbior.md, „Zasilanie stacji – progi”].
46. Zatrzymaj się na 10,0 V. Zapisz +3V3: około 0,5 V jest normalne (zasilanie od tyłu przez dzielnik pomiaru 12 V) [README, „Na pierwszych sztukach v2”].
47. Przełóż czerwony przewód na ON: dalej wysokie (sterownik czeka) [README, „Tor zasilania”, podtrzymanie bez 3,3 V].
48. Przełóż na +3V3. Zwiększaj co 0,1 V.
49. Zapisz napięcie, przy którym +3V3 wraca. Oczekiwane: 11,94 V (11,59–12,29 V); odbiór: najpóźniej 12,4 V [tamże].
50. Zwiększaj do 16,0 V. +3V3 ma zostać [odbior.md: OVP nie zadziała przy 16 V].
51. Zwiększaj co 0,1 V do 18,0 V (jeśli zasilacz nie daje 18,0 V, do najwyższego, jakie daje, i zapisz je). Zapisz napięcie, przy którym +3V3 znika. Oczekiwane: 16,81 V (16,32–17,30 V) [design.py, R30/R31; karta LM74800, 1,195–1,267 V].
52. **STOP, jeśli** +3V3 nie znika do 17,4 V.
53. Zmniejszaj. Zapisz napięcie, przy którym +3V3 wraca. Oczekiwane: około 15,4 V (14,9–15,8 V) [karta LM74800, próg opadający 1,091–1,159 V × 13,66].
54. **ZAPISZ** każdy próg poza pasmem. **STOP** tylko, jeśli +3V3 nie wraca samo.
55. Wróć do 12,6 V.

### 3g. Samoczynne włączenie z 12 V

56. Wyłącz stację przytrzymaniem J3 (jak 31–32).
57. Odczekaj 30 s przy 12,6 V. Stacja ma zostać wyłączona [odbior.md: „po wyłączeniu ręcznym przy stałym 12,6 V nie włącza się sama”].
58. **STOP, jeśli** włączyła się sama.
59. Wyłącz wyjście, wyjmij wtyczkę z J2, odczekaj 2 minuty (założenie: sterownik musi stracić zasilanie).
60. Ustaw 7,5 V, włóż wtyczkę, włącz wyjście. Multimetr na ON: poniżej 0,1 V.
61. Zwiększaj co 0,1 V, kilka sekund na krok.
62. Zapisz napięcie z wyświetlacza, przy którym ON skacze z około 0 V na kilka woltów. Oczekiwane: około 8,2–9,6 V; odbiór: nie poniżej 8,0 V i najpóźniej przy 9,8 V [README, „Tor zasilania”; odbior.md].
63. Jeśli ON nie skoczyło do 12,6 V: powtórz 59–62 z 10 minutami czekania. Jeśli dalej nie: **ZAPISZ** (to wynik dla README, nie uszkodzenie).
64. Zwiększaj dalej. Zapisz, przy jakim napięciu pojawia się +3V3: około 11,94 V, najpóźniej 12,4 V.
65. Przy 12,6 V wyłącz wyjście.

## 4. Wyłączenie przez KILL bez DevKitC (opcjonalnie: sprawdza tranzystor Q11)

1. Bez zasilania. Odwróć płytkę na tulejkach albo zajrzyj od spodu.
2. Znajdź gniazdo podpisane „J6”. Pin 1 ma pad prostokątny przy podpisie. Policz od pinu 1 do pinu 17.
3. Sprawdź, czy to dobry otwór: multimetr na oporności, czarny na MASIE, czerwony (cienka końcówka) w ten otwór. Oczekiwane: około 100 kΩ (R72 do masy) [design.py, R72]. Sąsiednie otwory dają co innego, a pin 21 i 22 dają 0 Ω (masa). **Nie idź dalej, jeśli nie masz 100 kΩ.**
4. Znajdź gniazdo podpisane „J5”. Pin 1 to pad prostokątny przy podpisie.
5. Sprawdź: czerwony w otwór pinu 1 J5, czarny na +3V3 (lewy pin JP3): poniżej 1 Ω.
6. Włóż jeden koniec przewodu Dupont w J6 pin 17. Drugi koniec zostaw wolny, z dala od płytki.
7. Zasilanie z J1: 6,0 V, 0,10 A. Włącz stację przyciskiem J3. Odczekaj 2 s (sterownik ignoruje KILL przez 0,3–0,7 s po włączeniu [karta LTC2955, tKILL(ON BLANK)]).
8. Włóż wolny koniec w J5 pin 1.
9. Oczekiwane: stacja wyłącza się od razu, +3V3 spada do 0 V [README, „Tor zasilania”, wyłączenie].
10. Wyjmij przewód. Wyłącz wyjście zasilacza.

Pomyłka o jeden pin w J6 jest bezpieczna (pin 16 to INT z podciągnięciem do +3V3, pin 18 to wolna linia radia [polaczenia.md]); pomyłka o cztery piny (21, 22: masa) zwarłaby +3V3, dlatego krok 3.

## 5. Moduły: DevKitC i Wio, start i wgranie programu

### DevKitC

1. Stacja wyłączona, wszystkie źródła odłączone. +3V3 poniżej 0,1 V.
2. Sprawdź napis na module: ESP32-S3-DevKitC-1 **N8R8**, wersja 1.1 (dioda RGB) [README, „Przydział pinów”].
3. Zdejmij zworkę z JP3.
4. Włóż DevKitC od spodu w J5 i J6. Pin modułu podpisany „3V3” (przy antenie) idzie w otwór pinu 1 J5 (prostokątny pad, przy podpisie „J5”); antena modułu wskazuje górną krawędź płytki. Moduł widziany od spodu stoi jak na płytce v1.1 [README, „Rozmieszczenie wstępne”, moduły od spodu]. Każda nóżka w otworze, żaden otwór na końcach rzędu pusty.
5. Zasilacz na J1: 6,0 V, ograniczenie 0,30 A (założenie: odwrotnie włożony moduł zwiera +3V3 do masy i zasilacz wejdzie w ograniczenie).
6. Oscyloskop na +3V3 (lewy pin JP3), masa sondy na MASIE: 0,5 V/działkę, zbocze opadające na 3,15 V, tryb pojedynczy, 2 ms/działkę.
7. Włącz stację przyciskiem.
8. **STOP, jeśli** zasilacz siedzi w ograniczeniu albo +3V3 (multimetr) jest poniżej 3,0 V.
9. Jeśli stacja wyłącza się sama około pół sekundy po włączeniu: program w DevKitC ustawia GPIO47 (KILL). Nie jest to uszkodzenie: przejdź do wgrania programu i włączaj stację z przytrzymanym przyciskiem BOOT na DevKitC (moduł nie uruchamia wtedy programu).
10. Odczytaj najniższe +3V3 z oscyloskopu (jeśli się wyzwolił). **STOP, jeśli** 2,74 V albo niżej (próg nadzorcy FRAM U3, 2,66–2,74 V [elektronika.md, „Zanik zasilania i zapis”, punkt 2]). Wynik liczy się tylko, gdy zasilacz ani razu nie wszedł w ograniczenie prądu.
11. Wyłącz stację przytrzymaniem. Ustaw 4,0 V i ograniczenie 1,0 A. Powtórz 7–10 [README, „Przed zamówieniem”: start ESP32-S3 przy 4 V]. Przy spadku nie poprawiaj niczego sam; README podaje kolejne poprawki [tamże].

### Wio

12. Wyłącz stację, odłącz zasilanie.
13. **Zwrot Wio nie jest jeszcze potwierdzony przymiarką** [README, „Przed zamówieniem”, zwrot Wio]. Według README: moduł wisi elementami w dół (listwy wychodzą od strony bez elementów), złącze u.FL przy pinie 7 gniazda J9 (koniec J9 dalej od górnej krawędzi płytki). Przed włożeniem porównaj z obrazkiem pinów Seeed: pin „3V3” Wio musi trafić w J9 pin 3, a „GND” w J9 pin 2 [design.py, J9]. Jeśli się nie zgadza, nie wkładaj i zgłoś.
14. Podłącz antenę albo obciążenie 50 Ω do u.FL.
15. PPK2 w trybie **amperomierza (Ampere meter)**, nie źródła: VIN na lewy pin JP3 (+3V3), VOUT na prawy pin JP3, GND PPK2 na MASĘ. Zworka JP3 zdjęta.
16. Zasilacz na J1: 6,0 V, 0,50 A (założenie). Oscyloskop jak w kroku 6.
17. Włącz stację. Odczytaj prąd radia w PPK2.
18. **STOP, jeśli** prąd radia bez nadawania przekracza 20 mA albo rośnie (założenie: SX1262 w odbiorze bierze kilka mA; dużo więcej oznacza źle włożony moduł).
19. Wyłącz stację, odłącz PPK2, załóż zworkę JP3.

### Wgranie programu

Płytka v2 nie ma jeszcze pliku opisu płytki w programie. Pasuje obraz `l0` prototypu v1.1: piny ekranu, radia, FRAM i przycisków są te same [README, „Przydział pinów”; firmware/src/board_l0.h]. Obraz `l0` sprawdzi USB, ekran, radio i FRAM. Nie obsługuje pomiaru ogniw, KILL, INT, PWM przetwornicy i wykrywania laptopa; odczyt „12 V” będzie błędny (czyta GPIO5 z dzielnikiem 1/6, a v2 ma 0,0625 [board_l0.h, VTEST; design.py, R38/R39]). Obraz `l0` nie rusza GPIO3, GPIO4 ani GPIO45–48, więc nie koliduje z nowymi obwodami v2 [board_l0.h]. Gdyby obraz `l0` nie ruszył, zapasowo wgrywa się program diagnostyczny L0 (`hardware/l0-diagnostic`, te same piny, USB natywne).

Laptop nie zasila stacji przez USB-C (VBUS idzie tylko do wykrywania laptopa), więc stacja musi być zasilana z J1 albo J2 [elektronika.md, „Gniazdo USB do laptopa”].

20. Zainstaluj PlatformIO według firmware/README.md.
21. Zasilacz na J1: 6,0 V, 0,50 A. Antena na Wio. Włącz stację.
22. Podłącz laptop do USB-C stacji (J4).
23. Uruchom: `cd firmware && ../.venv-pio/bin/pio run -e l0 -t upload` [firmware/README.md].
24. Jeśli wgrywanie nie znajduje portu: przytrzymaj BOOT na DevKitC, naciśnij i puść RST, puść BOOT, powtórz 23. Kolejne wgrania idą bez przycisków (wgrywanie przez esptool z „dotknięciem 1200 b/s” [platformio.ini, `[env:bench-b-port]`, przez `bench-b`]).
25. Po wgraniu naciśnij RST na DevKitC.
26. Laptop ma widzieć urządzenie „WICI L0” z dwoma portami szeregowymi [platformio.ini, `[env:l0]`, `[lora]`].
27. Otwórz pierwszy port. Obraz sam wysyła `INFO`, `RADIO`, `FRAM`, `JOURNAL`; `INFO` ma pokazać `l0-0.6` [firmware/docs/polecenia.md; platformio.ini].
28. **STOP, jeśli** laptop nie widzi urządzenia albo nie ma `INFO`: zapisz komunikat esptool.
29. Wyłącz stację przytrzymaniem J3 (laptop zostaje podłączony). Zmierz +3V3: poniżej 0,3 V. Laptop nie może zasilać wyłączonej stacji [README, „Tor zasilania”, wykrywanie laptopa]. **STOP, jeśli** wyżej.

## 6. Przełączanie 12 V ↔ ogniwa pod obciążeniem

Ta próba ma sens tylko z pracującym DevKitC; bez modułów +3V3 nie ma obciążenia i nie spadnie [README, „Na pierwszych sztukach v2”, C50].

1. DevKitC i Wio w gniazdach, program `l0`, antena, zworka JP3.
2. Koszyk z ogniwami AA w J1 (albo PPK2 jako źródło 5,0 V na J1).
3. Włącz stację przyciskiem.
4. Zasilacz: 12,6 V, 0,50 A, wtyczka w J2, wyjście włączone.
5. Oscyloskop na +3V3, masa na MASIE: 0,5 V/działkę, zbocze opadające na 3,15 V, tryb pojedynczy, 1 ms/działkę.
6. Wyjmij wtyczkę z J2 (przejście na ogniwa). Odczytaj, czy oscyloskop się wyzwolił i najniższe +3V3.
7. Uzbrój oscyloskop, włóż wtyczkę do J2 (powrót na 12 V). Odczytaj.
8. Powtórz 6–7 dziesięć razy (razem 20 przełączeń) [odbior.md, „Tor zasilania stacji pilotażowej”: 20 przełączeń bez restartu].
9. Po próbie sprawdź w `INFO`, że liczba startów (`restarts`) się nie zmieniła [firmware/docs/polecenia.md].
10. **ZAPISZ** każdy spadek poniżej 3,2 V. **STOP, jeśli** +3V3 spadło do 2,74 V albo stacja się zrestartowała: to decyduje o C50 [README, „Na pierwszych sztukach v2”, C50].
11. Wyłącz stację, odłącz oba źródła, laptop.

## 7. Podłączanie 12 V pod napięciem (na końcu)

Ta próba rozstrzyga, czy drugi TVS (D20) wchodzi do serii [README, „Ochrona wejścia przy łączniku”]. Przy podłączeniu wtyku do włączonego źródła napięcie przy C38 może dojść do dwukrotności napięcia źródła: szacunkowo 57,6 V przy 28,8 V i 66 V przy 33 V, wobec granicy 70 V układu U5 [tamże]. Dlatego najpierw płytka **bez D20**, napięcie stopniowo, a próba jest ostatnia.

### Przygotowanie

1. Wyjmij DevKitC i Wio (założenie: przy uszkodzeniu U5 moduły nie ucierpią).
2. Źródło 24–33 V: DPS-150 zasilany napięciem 32 V daje do 30 V, więc 24 V i 28,8 V. **33 V wymaga innego źródła** (punkt 0.1). Do 33 V potrzebny jest zasilacz laboratoryjny do co najmniej 35 V; bez niego decyzji z README dla płytki bez D20 nie da się podjąć.
3. Na obu płytkach do padów C38 mają być przylutowane dwa krótkie druty (do 5 mm). Nie trzymaj sondy ręką na gołych padach 0805: ześlizgnięta sprężynka zwiera wejście do masy przy naładowanym kondensatorze 1000 µF.
4. Kompensacja sondy: sonda 10X na wyjściu prostokąta 1 kHz w 2D15P (generator), wkrętakiem na sondzie ustaw płaskie górne krawędzie bez szpilek. Źle skompensowana sonda zawyża albo zaniża szczyty.
5. Przełącznik na sondzie 10X i w menu oscyloskopu 10X.
6. Końcówka sondy na drucie od lewego padu C38, sprężynka masy na drucie od prawego padu.
7. Sprzężenie DC, 10 V/działkę. **Przesuń linię zera na najniższą linię siatki** i sprawdź, że górna krawędź ekranu to co najmniej 80 V. Jeśli nie, 20 V/działkę. (Przy zerze na środku ekranu szczyt powyżej 40 V zostałby obcięty i wynik wyglądałby na dobry.)
8. Podstawa czasu 50 µs/działkę, największa pamięć (1M), zmierz Vmax. Próbkowanie co najmniej 100 MS/s (drgania mają 0,5–1,6 MHz: szacunek z 0,5–1 µH lub 0,1 µH i 100 nF [README, „Ile napięcia może przybyć”]). Dłuższe okno łapie też drganie styków po pierwszym dotknięciu.
9. Wyzwalanie: zbocze narastające na połowie napięcia źródła (np. 12 V przy 24 V), tryb pojedynczy.
10. Kondensator 1000 µF / 63 V na zaciski zasilacza: plus kondensatora (bez paska) na plus. Odwrotnie podłączony elektrolit może wybuchnąć.
11. Ograniczenie prądu 0,50 A (założenie; prąd udaru daje kondensator) [README, „Ochrona wejścia przy łączniku”, pomiar 2].
12. Dwa przewody od zasilacza do wtyczki J2: docelowy (README przyjmuje około 1 m) i krótki, około 0,3 m [tamże].
13. J1 bez ogniw (założenie).

### Płytka bez D20

14. Rozgrzewka: 12,6 V, 5 podłączeń wtyku przy włączonym źródle. Zapisz szczyty (założenie: sprawdzenie ustawień).
15. Ustaw 24,0 V.
16. Uzbrój oscyloskop.
17. Włóż wtyk do J2 jednym ruchem.
18. Zapisz Vmax.
19. Wyjmij wtyk, odczekaj kilka sekund.
20. Powtórz 16–19: 20 razy z przewodem docelowym i 20 razy z krótkim [README, pomiar 2–3].
21. Przy 24 V zmierz +3V3 (multimetr, sonda odłożona): około 1,3–1,8 V [README, „Na pierwszych sztukach v2”, zasilanie od tyłu]. Zapisz.
22. **Jeśli którykolwiek szczyt przekroczył 60 V:** nie idź wyżej na tej płytce. D20 wchodzi do serii [README, pomiar 3 i 6]. Przejdź do 27.
23. Ustaw 28,8 V, powtórz 16–20.
24. **Jeśli którykolwiek szczyt przekroczył 60 V:** nie rób 33 V. D20 wchodzi do serii. Przejdź do 27.
25. 33,0 V (nie więcej), powtórz 16–20. Przy 33 V dioda D10 może przewodzić do około 2 mA, to normalne [README, „Decyzje”, 2].
26. **Jeśli którykolwiek szczyt przy 33 V przekroczył 65 V: przerwij próby 33 V od razu.** D20 wchodzi do serii [README, pomiar 6]; dalsze podłączenia tylko zbliżają U5 do granicy 70 V.
27. Sprawdź płytkę: kroki 36–42 z części 3 (12,6 V, +3V3, +5V). **STOP, jeśli** działa inaczej niż wcześniej.

### Co znaczy wynik (płytka bez D20)

| Wynik | Decyzja [README, „Ochrona wejścia przy łączniku”, pomiar 6] |
|---|---|
| 24 V i 28,8 V do 60 V, 33 V do 65 V | seria bez D20 |
| ponad 60 V przy 24 V albo 28,8 V (33 V nie robione) | D20 w serii |
| ponad 65 V przy 33 V | D20 w serii |
| 33 V nie dało się zrobić z braku źródła | decyzji nie ma; zgłoś |
| ponad 70 V gdziekolwiek | granica U5 przekroczona: STOP, zgłoś, płytka mogła ucierpieć |

### Płytka z D20

28. Powtórz 14–27 na płytce z D20, także przy 33 V [README, pomiar 4].
29. Porównaj szczyty obu płytek: różnica pokazuje, o ile D20 obniża napięcie.
30. Impuls do ograniczenia TVS (T6) wymaga generatora udarów i nie należy do tej procedury [README, pomiar 5].

## 8. Pomiary na później

Tych pomiarów nie robi się przy pierwszym uruchomieniu. Wymagają programu z plikiem opisu płytki v2, amperomierza µA albo grzania do 60 °C. Wyniki decydują o poprawkach przed serią [README, „Na pierwszych sztukach v2”]. Prądów w µA przy napięciu powyżej 5 V nie zmierzy ani PPK2, ani DPS-150, więc do nich potrzebny jest osobny amperomierz z zakresem µA.

| Co | Oczekiwane | Źródło | Przyrząd |
|---|---|---|---|
| prąd stanu wyłączonego z ogniw, 25 i 60 °C | typowo około 13 µA; najgorszy przypadek ponad 20 µA (cel projektu zasilania); granica 0,1 mA | README, „Na pierwszych sztukach v2”; elektronika.md, „pobór” | PPK2 jako źródło 4,4–5,0 V na J1; dla 6–7,3 V amperomierz µA w przewodzie J1 (PPK2 daje najwyżej 5 V) |
| udział C50 w prądzie wyłączonym | na prototypach SamYoung PXB; upływ według karty producenta, przy 6 V mniejszy niż przy 25 V | README, „Kondensator szyny C50” | jak wyżej; wynik wpływa na wybór serii C50 przed serią pilotażową |
| prąd stanu wyłączonego z 12 V | dzielnik ON około 37 µA i R48 około 15 µA plus wyłączony łącznik 2,87 µA; granica 0,1 mA | README, „Tor zasilania”, stan wyłączony i samoczynne włączenie; elektronika.md, „pobór” | amperomierz µA w przewodzie J2 (DPS-150 ma dokładność ±5 mA, PPK2 najwyżej 5 V) |
| prąd wsteczny diody D7 do ogniw przy 12 V i 16 V, 45 i 60 °C | ≤1 µA (odbiór) | odbior.md, „Tor zasilania stacji pilotażowej” i „Zasilanie stacji – progi”; README, „Na pierwszych sztukach v2” | amperomierz µA w przewodzie ogniw |
| napięcie EN/UVLO łącznika przy pracy z ogniw bez 12 V, 25 i 60 °C | ma zostać wyraźnie poniżej 0,3 V | README, „Na pierwszych sztukach v2” | multimetr |
| KILL przy VCTL 3,6 V na ciepło | KILL powyżej około 2 V; wyłączenie przy około 0,84 V | README, „Tor zasilania”, podtrzymanie; „Na pierwszych sztukach v2” | multimetr |
| RUN przetwornicy w stanie wyłączonym, 60 °C | poniżej około 0,3 V | README, „Na pierwszych sztukach v2” | multimetr |
| +3V3 przy stacji czekającej bez ogniw: 11 V i 24 V; 10 włożeń ogniw przy 24 V | około 0,5 V i 1,3–1,8 V; czysty start | README, „Na pierwszych sztukach v2”; odbior.md, „Tor zasilania stacji pilotażowej” | multimetr, program |
| pobór w RX, TX, czuwaniu | średni prąd wobec ≤35/≤60 mA | odbior.md, „Zasilanie stacji – progi”; „Tor zasilania stacji pilotażowej” | PPK2 / zasilacz |
| +3V3 przy nadawaniu z ogniw 4,4 V | ≥3,2 V | odbior.md, „Tor zasilania stacji pilotażowej” | oscyloskop |
| przetwornica 3,3 V na v2: tętnienia, sprawność, zakłócenia | do zmierzenia od nowa (układ różni się od płytki testowej) | README, „Miedź ręczna”, „Na pierwszych sztukach v2” | oscyloskop, PPK2 |
| tętnienia +5V przy pracy brzęczyka | do oceny oscyloskopem | README, „Decyzje”, 3 | oscyloskop |
| udar przy wkładaniu ogniw przez R40 | do potwierdzenia | README, „Do następnej wersji”, R40 | oscyloskop |

## Wyniki

Wyniki zapisuje się w `hardware/plytka-v2/pomiary/`, jeden plik na płytkę i dzień: osoba, data, przyrządy, numer płytki („z D20” albo „bez D20”), numer kroku i odczyt. Katalog `checks/` zostaje dla plików, które tworzy generator. Wnioski trafiają do punktów w [README](README.md#na-pierwszych-sztukach-v2), „Na pierwszych sztukach v2”.
