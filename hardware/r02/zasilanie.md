# WICI R02: blok zasilania

**Wstrzymane do decyzji po pilotażu (przegląd praktyczny 2026-10-08, F99):** pilotaż używa stacji z gotowej płytki MCU z układem LoRa SX1262 ([koncepcja 08](../../docs/concept/08-plan-weryfikacji-i-decyzje.html)).

**Status: 2026-10-08, projekt przed schematem. Nie zamawiać.** Blok jest wspólny dla obu wykonań i nie zależy od prób T3–T5. Dokument dobiera części i wartości elementów do wymagań z [elektroniki](../../docs/spec/elektronika.md#zasilanie-stacji) i [BOM stacji](../../docs/spec/bom-stacji.csv), liczy prąd w stanie wyłączonym i opisuje próby, które da się zrobić teraz na płytkach ewaluacyjnych.

Liczby pochodzą z kart producentów odczytanych 2026-10-08 (lista w [źródłach](#źródła)). Ceny i stany są z DigiKey z tego dnia. Oznaczenie „do sprawdzenia” dotyczy danych, których nie potwierdzono w karcie albo które wymagają pomiaru.

## Ustalenia, które zmieniają specyfikację

Przegląd kart wykazał błędy i sprzeczności w obecnych wymaganiach ([F87](../../docs/review.md)). Decyzje autora z 2026-10-08, przeniesione do [elektroniki](../../docs/spec/elektronika.md#zasilanie-stacji), [BOM](../../docs/spec/bom-stacji.csv) i modelu energii:
- tor ogniw z diodą Schottky’ego zamiast idealnej diody (Z7);
- kondensator podtrzymania ≥680 µF o małym upływie (Z4, Z5);
- tłumik RC na wejściu 12 V (Z8);
- OVP jako reguła 0,9 × maksimum zamiast ±2% (Z6);
- jeden próg załączenia 12 V: 12,4 V (Z9);
- podział na płytę bazową i moduł MCU+RF ([architektura](architektura.md#podział-na-płytki)).

| # | Ustalenie | Źródło | Skutek |
|---|---|---|---|
| Z1 | **TPS610995 to wersja 3,6 V, nie 5 V.** Wersja 5 V to TPS610997, dostępna tylko w WCSP 1,23 × 0,88 mm. W obudowie WSON 2 × 2 mm jest regulowany TPS61099DRV z dzielnikiem | TI SLVSD88M, tabela porównania wersji i 6.5 | poprawione w elektronice i BOM: TPS61099 (DRV) ustawiony na 5 V |
| Z2 | **LTC2954 nie ma licznika czasu wyłączenia bez naciśniętego przycisku.** Przy braku odpowiedzi MCU wyłączenie wymusza tylko przycisk przytrzymany przez t_PDT. Sam sterownik nie wyłączy się po puszczeniu przycisku. INT idzie w stan niski 32 ms po naciśnięciu i trwa, dopóki przycisk jest wciśnięty, więc 2 s odmierza program. LTC2955, wybrany zamiast LTC2954, działa tak samo: INT po 32 ms, trwa najmniej 32 ms i do puszczenia przycisku albo końca licznika TMR | ADI LTC2954 rew. B, s. 6 i 9; LTC2955 rew. A, s. 9–10 | poprawione w elektronice: wymuszenie przytrzymaniem przycisku ≥5 s |
| Z3 | **KILL musi być w stanie wysokim najpóźniej 304 ms po włączeniu EN** (LTC2955; dla LTC2954 400 ms), inaczej sterownik znowu wyłącza zasilanie | LTC2955, t_KILL(ON BLANK) 304/512/720 ms | rezystor podciągający KILL do 3V3, a MCU ściąga KILL otwartym drenem; zasilanie trzyma się od chwili, gdy jest 3V3 |
| Z4 | **Polimerowy kondensator podtrzymania przekracza budżet stanu wyłączonego.** VSYS jest stale połączone z ogniwami (tor ogniw nie ma łącznika). Nichicon PCR 470 µF/25 V ma gwarantowany upływ ≤352 µA przy napięciu znamionowym, a budżet to ≤20 µA | Nichicon PCR, CAT.8100N | zdecydowane: aluminiowy elektrolit o małym upływie (Nichicon UKL, 0,002 CV) i ceramika; upływ przy 6 V do zmierzenia |
| Z5 | **Pojemność podtrzymania przy najgorszym progu:** komparator może zadziałać już przy 3,325 V, więc C ≥450 µF; po tolerancji −20% i spadku w −20 °C potrzeba nominalnie 680 µF, a nie 470 µF | §[podtrzymanie](#kondensator-podtrzymania-vsys) | zdecydowane: ≥680 µF |
| Z6 | **LM74800-Q1 nie da progu OVP 17 V ±2%.** Sam komparator OV ma ±2,9%: przy rezystorach 0,1% próg wynosi 16,40–17,45 V. Reguła 0,9 × 40 V dla LTC3115-1 i tak jest spełniona z dużym zapasem. ADI LTC4368-2 daje 16,71–17,29 V | TI SNOSD95C s. 5; ADI LTC4368 rew. C s. 4 | zdecydowane: reguła 0,9 × maksimum i dolna granica progu powyżej 16 V zamiast ±2% |
| Z7 | **Prąd z ogniw w stanie wyłączonym:** typowo około 24 µA, najgorzej około 49 µA przy cel ≤20 µA. Składniki: LTC4412 (11/19 µA), LTC2954 (6/12 µA), LTC3115-1 w wyłączeniu (3/10 µA), LM74800 zasilany wstecznie z VSYS przez diodę podłożową (2,9/5 µA) | §[bilans](#bilans-prądu-w-stanie-wyłączonym) | zdecydowane: dioda Schottky’ego zamiast idealnej diody i LTC2955 zamiast LTC2954, około 7/19 µA ([bilans](#bilans-prądu-w-stanie-wyłączonym)) |
| Z8 | **Bipolarny kondensator tłumiący 47 µF/35 V ma gwarantowany upływ 49–52 µA**, ponad budżet 12 V | Nichicon UES, Panasonic SU-A | zdecydowane: tłumik RC (ceramika 10–22 µF/50 V z rezystorem 0,5–1 Ω) |
| Z9 | **Sprzeczność progów 12 V:** elektronika mówi „pierwsze załączenie przy ≥12,0 V”, a gdzie indziej „ponowne załączenie zawsze tylko przy V12 ≥12,4 V” | elektronika, wiersze „Wejście 12 V” i „Odłączenie 12 V” | zdecydowane: 12,4 V w obu przypadkach |
| Z10 | **Komparator VSYS:** TPS3710 ma sam próg opadający −1,9%/+1,4%, więc ±2% wychodzi tylko typowo (najgorzej −2,2%/+2,0%). Wejście SENSE wytrzymuje 7 V, więc dzielnika nie odłącza się od dołu | TI SBVS271A, 5.1 i 5.5 | odłączanie dzielnika od góry (PMOS); wymaganie ±2,5% albo pojemność liczona przy 3,32 V (Z5) |
| Z11 | **Nominalne Iq LTC3115-1 w Burst Mode to 50 µA typowo, bez wartości maksymalnej**, a sprawność ≥85% przy 6 V wychodzi z wykresów tylko na granicy (około 82–85% dla 3,3 V, oszacowanie) | ADI LTC3115-1 rew. C, s. 3 i 6 | pomiar na płytce ewaluacyjnej przed schematem |
| Z12 | **Tranzystor PMOS toru ogniw wg wymagania (≤50 mΩ przy −2,5 V, ≥30 V) ma tylko jednego producenta (Vishay).** W pracy ogniwa mają ≥4,0 V, a LTC4412 ściąga bramkę do około 0 V | Vishay, Diodes, Nexperia | nieaktualne po decyzji Z7 (tor ogniw bez PMOS) |
| Z13 | **LTC4412 nie ogranicza udaru przy wkładaniu ogniw**, bo prąd płynie najpierw przez diodę podłożową. Szacunkowo 7–15 A do około 600 µF; opór ogniw do sprawdzenia | LTC4412 rew. C | rezystor 1 Ω impulsowy w torze ogniw: ≤5 A, spadek 0,08–0,12 V; dotyczy też diody Schottky’ego |
| Z14 | **LTC2954 widzi przez sumę diodową impuls 29 V** z TVS, a pracuje do 26,4 V | LTC2954 s. 2–3; LTC2955 s. 2, 3 i 6 | LTC2955 pracuje do 36 V (maksimum 40 V), więc reguła 0,9 jest spełniona bez filtra; karta zaleca dla VIN >20 V rezystor 1 kΩ i kondensator ≥10 nF, więc filtr 1 kΩ / 1 µF za diodą od strony 12 V zostaje |
| Z15 | **Diody sumy zasilania:** diody Schottky’ego mają w 45 °C upływ rzędu µA i ten prąd płynie do pierwotnych ogniw litowych. Krzemowa dioda o małym upływie (Nexperia BAS116H, ≤5 nA) jest lepsza, a spadek nie ma znaczenia | Nexperia BAS116H, BAT46WJ | dioda krzemowa o małym upływie zamiast Schottky’ego; od strony 12 V ≥40 V |

LM74800-Q1 obsługuje oba połączenia tranzystorów: ze wspólnym drenem (przykład aplikacji TI) i ze wspólnym źródłem (jak w obecnym opisie). Wspólny dren pozwala użyć punktu środkowego do sumy diodowej. Wybór należy do schematu.

## Projekt bloków

### Wejście 12 V

| Element | Wybór | Uwagi |
|---|---|---|
| Bezpiecznik zwłoczny T1A przy wtyku | Schurter SPT 0001.2504 (300 V DC; DigiKey 4714 szt., 1,13 USD) | drugi: Littelfuse 0477001 (400 V DC). Większość bezpieczników T 5×20 mm ma parametry tylko dla prądu przemiennego (Bel 5TT, Eaton GDC) |
| TVS | SMBJ18CA (Vishay albo Littelfuse): ograniczenie 29,2 V przy 20,5 A | 29,2 V przyjmuje się jako najgorszy przypadek przed S12 |
| Tłumienie | ceramika 10–22 µF/50 V X7R z rezystorem 0,5–1 Ω (impulsowy, 1206) | zamiast bipolarnego elektrolitu (Z8); indukcyjność 3 m przewodu (2–3 µH) do sprawdzenia |
| Odwrotne podłączenie 16 V przez 60 s | prąd TVS i LM74800 poniżej 0,2 mA | bezpiecznik nie przepala się |

### Łącznik S12

**Kandydat 1: TI LM74800-Q1** (LM74800QDRRRQ1; DigiKey 7537 szt., 3,18 USD) z dwoma N-MOSFET.

| Parametr | Wartość |
|---|---|
| Zakres pracy / odwrotna polaryzacja | 3–65 V / do −65 V |
| Wyłączenie (EN <0,3 V) | 2,87 µA typowo, 5 µA najwyżej |
| Dzielnik OVP (SW → OV) | 255 kΩ / 20,0 kΩ: 16,93 V nominalnie, 16,40–17,45 V przy 0,1%; dzielnik wisi na SW, więc w stanie wyłączonym nie pobiera prądu |
| Narastanie | C_dVdT 68 nF: 0,34–0,66 A do około 600 µF, rampa do 16 V w około 19 ms |
| Tranzystory | Nexperia BUK7Y12-40E (40 V, 12 mΩ, SOA około 3 A przy 16 V przez 10–100 ms); drugi producent z opublikowanym SOA dla 10 ms i DC do znalezienia. Infineon BSZ063N04LS6 odpada (około 0,3 A przy 16 V przez 10 ms) |

**Kandydat 2 (inny producent): ADI LTC4368-2**: 2,5–60 V, do −40 V, progi UV/OV 500 mV ±1,5%.
- OVP 330 kΩ / 10,0 kΩ daje 17,00 V nominalnie i 16,71–17,29 V przy rezystorach 0,1%.
- Wada: w stanie wyłączonym pobiera prąd z obu stron, z wejścia 12 V 5/25 µA i z VSYS, czyli z ogniw, 3/20 µA.
- Po UV sam ponawia start po 32 ms, więc zatrzask UV i tak jest zewnętrzny.

### Zatrzask podnapięciowy 12 V

Zatrzask musi działać bez 3V3, na przykład przy samym 12 V i bez ogniw.
- **Szyna zatrzasku:** V12 za TVS, a przed S12, przechodzi przez PMOS ≥40 V (Nexperia BSS84AK) do lokalnej szyny V12L. Bramką PMOS steruje wyjście ON sterownika wyłącznika. Wyłączenie stacji albo odłączenie 12 V gasi V12L i tym samym kasuje zatrzask.
- **Komparator:** TI TPS3701 (komparator okienkowy, 1,8–36 V, 8/11 µA, progi 400 mV ±0,75%; DigiKey 11 372 szt., 3,02 USD).
- **Zasilanie logiki:** LDO TPS70933 (2,7–30 V, 1,4/2,25 µA). Przy impulsie 29,2 V pracuje na granicy reguły 0,9, więc dostaje rezystor szeregowy 1 kΩ i diodę Zenera 24 V.
- **Logika:** zatrzask SR na 74LVC2G00 (ustawiany przy ≥12,4 V, kasowany przy <11,5 V) i pamięć zadziałania na 74LVC1G74, kasowana przez reset przy włączeniu albo przez MCU.
- **Dzielnik (0,1%):** 3,88 MΩ / 10,2 kΩ / 130 kΩ daje próg wyłączenia 11,38–11,60 V i ponownego załączenia 12,27–12,51 V. Pobór całego zatrzasku przy włączonej stacji wynosi około 13 µA typowo i 17 µA najwyżej, plus prąd logiki 74LVC (do sprawdzenia).
- **S12 EN:** wyjście zatrzasku (logika 3,3 V wystarcza dla LM74800 i LTC4368).
- **Kasowanie przyciskiem OK:** NMOS (2N7002) sterowany z GPIO MCU zwiera wejście kasowania pamięci zadziałania. Bramka izoluje domenę 3V3 od 12 V. Załączenie i tak wymaga V12 ≥12,4 V.

Drugi producent: ADI LTC2965 (3,5–100 V, 3/7/15 µA) z osobnymi progami w górę i w dół. Zastępuje TPS3701, LDO i zatrzask SR; zostaje tylko pamięć zadziałania. Dokładność z rezystorami 1% wynosi około ±2,6%. TI TPS3762 odpada, bo jego regulowana wersja z zatrzaskiem jest tylko nadnapięciowa.

### Tor ogniw

- **Ogniwa:** 4 × AA → rezystor 1 Ω impulsowy (2512) → dioda Schottky’ego → VSYS (decyzja Z7).
  - Rezystor ogranicza udar do ≤5 A (Z13).
  - Napięcie ogniw mierzy się przed rezystorem, więc progi 4,4 i 4,0 V się nie przesuwają.
- **Dioda:** VR ≥30 V (VSYS ogranicza OVP łącznika S12 do ≤18,3 V), spadek ≤0,4 V przy 120 mA, impuls ≥5 A.
  - Gdy stacja pracuje z 12 V, VSYS jest wyższe od ogniw, a prąd wsteczny diody płynie do pierwotnych ogniw litowych. Diodę wybiera się więc o małym upływie przy 16 V i 45 °C, a dopuszczalny prąd bierze z karty ogniw (Energizer L91, do sprawdzenia).
  - Konkretne części dwóch producentów do wyboru po tym sprawdzeniu.
- **Koszt w energii:** spadek 0,35 V przy 6 V zwiększa moc pobieraną z ogniw o około 6%. Model energii liczy go jawnie:
  - nRF52840: 91 h na komplecie ogniw;
  - ESP32-S3 z MCU 30 mA: 49 h, czyli nadal ≥48 h;
  - W23 dopuszcza średnio najwyżej około 61 mA z szyny 3V3, wcześniej 64 mA.
- **Zapas do komparatora VSYS:** przy wyłączeniu przez ogniwa (4,0 V) VSYS wynosi około 3,65 V zamiast 4,0 V. Do progu zaniku (3,4 V, najwyżej 3,47 V) zostaje około 0,2 V. Impuls TX przy zimnych, wyczerpanych ogniwach może więc wywołać fałszywe przerwanie VSYS_FAIL. T6 sprawdza to w −10 °C przy końcu pracy ogniw. W razie potrzeby obniża się próg komparatora (z przeliczeniem pojemności) albo podnosi próg wyłączenia ogniw.

### Suma diodowa i sterownik wyłącznika

- **Suma diodowa:** dwie diody Nexperia BAS116H (75 V, ≤5 nA).
  - Od strony 12 V za diodą jest filtr 1 kΩ / 1 µF (Z14, zalecenie karty LTC2955 dla VIN >20 V).
  - Drugi producent diody o małym upływie do znalezienia.
- **Sterownik: ADI LTC2955ITS8-2** (TSOT-23-8, −40–85 °C; 1,5–36 V, 0,5/1,2/3 µA w pełnym zakresie temperatur). Zastępuje LTC2954-2 (6/12 µA), bo obniża najgorszy prąd z ogniw w stanie wyłączonym poniżej 20 µA ([bilans](#bilans-prądu-w-stanie-wyłączonym)).
  - EN̄ (wersja -2) jest wyjściem wysokonapięciowym do bramki PMOS, który z sumy diodowej tworzy szynę ON. W stanie wyłączonym wewnętrzny rezystor 0,45–1,35 MΩ podciąga EN̄ do VIN, więc bramka nie pobiera prądu.
  - Karta gwarantuje w stanie wysokim tylko VIN − 1,5 V przy −0,5 µA. Dlatego bramkę PMOS podciąga do źródła zewnętrzny rezystor 100 kΩ, na co karta pozwala, a od EN̄ idzie rezystor 100 kΩ. Ten dzielnik trzyma też |VGS| ≤15 V przy impulsie 29 V i pobiera prąd tylko przy włączonej stacji (około 60 µA przy 12 V).
  - Szyna ON zasila zatrzask UV (V12L przez swój PMOS), steruje EN łącznika S12 i podciągnięciem RUN przetwornicy.
  - ON (wejście samoczynnego włączenia) jest zwarte do GND, bo stacja włącza się tylko przyciskiem. W obudowie TSOT-23 SEL jest wewnętrznie zwarty do GND, a wyjścia PGD nie ma.
- **Czasy:**
  - Włączenie po 19–45 ms naciśnięcia (stałe, bez kondensatora). Stacja nie ma więc ochrony przed przypadkowym włączeniem krótkim dotknięciem, którą w LTC2954 dawał C_ONT; przycisk jest zagłębiony w panelu ([obudowa](obudowa.md)).
  - C_TMR = 2,2 µF X7R: wymuszone wyłączenie po 64 ms + t_TMR, przy czym t_TMR = C_TMR / 0,19 µF/s, czyli około 11,6 s nominalnie. Karta podaje rozrzut t_TMR tylko dla 2,2 nF (5,8/11,5/17,2 ms, ±50%). Po przeniesieniu na 2,2 µF i z tolerancją kondensatora ±10% wychodzi około 5,2–19 s, więc ≥5 s jest spełnione. Rozrzut mierzy się na próbce.
  - Po wyłączeniu sterownik przez 0,6–1,4 s ignoruje przycisk.
- **Przerwanie i KILL:** INT (otwarty dren, do 6 V) z podciągnięciem do 3V3 idzie do MCU. Przy wyłączaniu INT idzie w stan niski po 19–45 ms naciśnięcia i trwa, dopóki przycisk jest wciśnięty. Puszczenie przycisku przed końcem t_TMR przerywa wyłączanie i zwalnia INT, więc 2 s przytrzymania odmierza program, jak przy LTC2954.
  - KILL (do 6 V, próg 0,8 V) ma podciągnięcie do 3V3, a MCU ściąga go otwartym drenem. Po włączeniu EN̄ KILL musi być w stanie wysokim najpóźniej po 304 ms (Z3); narastanie S12 (około 19 ms) i rozruch przetwornicy mieszczą się w tym czasie z zapasem, do potwierdzenia pomiarem.
- **Drugi producent:** nie znaleziono sterownika spoza ADI z INT i KILL na 2,7–26 V. TI na swoim forum podaje, że nie ma odpowiednika LTC2954.
  - Droga zastępcza: stale włączony LDO TPS70930 z sumy diodowej (1,3/2,05 µA) zasila ST STM6601CA2BDM6F (1,6–5,5 V, 0,6 µA w spoczynku, INT, PSHOLD w roli KILL, blokada podnapięciowa 2,6 V, C_SRD 1 µF daje około 10 s wymuszonego wyłączenia; kartę czytano z kopii u dystrybutora). Razem około 1,9 µA typowo i 3,1 µA najwyżej, czyli podobnie jak LTC2955 (1,2/3 µA). Wyjścia mają poziom 3,3 V, więc szynę ON nadal tworzy PMOS.

### Przetwornica 3V3

**ADI LTC3115-1** (2,7–40 V, wyłączenie 3/10 µA):

| Element | Wartość |
|---|---|
| Częstotliwość | 750 kHz, R_T = 47,5 kΩ |
| Dławik | 15 µH, I_SAT ≥2 A: Würth 74437368150 (10 × 10 mm, 40/45 mΩ, 5,55 A) albo Bourns SRP1038A-150M (40/45 mΩ, 10 A) |
| Wejście | 2 × 10 µF/50 V X7R 1210 + 100 nF; pojemność skuteczna przy 12,8 V do sprawdzenia w krzywej producenta |
| Wyjście | 2 × 22 µF X5R 1210 |
| Sprzężenie zwrotne | 1 MΩ / 432 kΩ: 3,31 V, 2,3 µA |
| Kompensacja (typ III, procedura z karty s. 23–28) | C_FB 3,9 nF, R_FB 20 kΩ, C_POLE 82 pF, C_FF 82 pF, R_FF 20 kΩ; do sprawdzenia w LTspice, jak zaleca karta |
| RUN | podciągnięcie 1 MΩ do VSYS i NMOS z otwartym drenem sterowany z ON. RUN nie może przekroczyć VIN + 0,3 V, więc nie podłącza się go do szyny ON z sumy diodowej |
| PWM/SYNC | stan niski to Burst Mode (domyślnie). MCU podaje stan wysoki na czas nadawania, bo Burst Mode obsługuje zwykle poniżej 50 mA. To dodatkowy pin MCU ([architektura](architektura.md#sygnały-mcu)) |

Sprawność ≥85% przy 6 V i ≥80% przy 12,8 V (30–60 mA) wynika z wykresów dla 5 V wyjścia tylko na granicy (Z11). Iq 50 µA jest typowe, bez maksimum. Oba warunki mierzy się na płytce ewaluacyjnej, zanim przetwornica wejdzie do schematu.

TI TPS63070 odpada jako pierwszy wybór: Iq do 103 µA (wymaganie ≤50 µA) i zalecane wejście tylko do 16 V (maksimum bezwzględne 20 V, SLVSC58B), więc praca z 12 V wymaga zawężenia do 15 V i progu OVP z przerzutem ≤16 V ([elektronika](../../docs/spec/elektronika.md#zasilanie-stacji)). U TI, MPS i ST nie znaleziono przetwornicy podwyższająco-obniżającej z wejściem ≥20 V, Iq ≤50 µA i wyjściem 3,3 V (TPS552892, TPS55289 i LM5176 mają Iq rzędu 0,8–2 mA, TPS5516x nie ma wyjścia 3,3 V). Drugi producent wymaga więc innej architektury: przetwornica obniżająca o małym Iq z pracą przy 100% wypełnienia, np. TI TPS629210 (3–17 V, 4 µA). Przy ogniwach 4,0 V wystarcza dla nRF52840, ale dla ESP32-S3 jest na granicy w czasie podtrzymania (VSYS spada do 2,7 V), więc decyzja zależy od D14.

### Komparator VSYS

**TI TPS3710**, zasilany z 3V3: dzielnik z VSYS 390 kΩ / 51,1 kΩ (0,1%) daje 3,405 V nominalnie i 3,325–3,469 V najgorzej (Z10).
- **Odłączanie dzielnika:** PMOS od strony VSYS sterowany z 3V3, bo stale podłączony dzielnik pobierałby 13,6 µA z ogniw.
- **Pobór przy włączonej stacji:** TPS3710 ≤13 µA z 3V3 i dzielnik 14–36 µA.
- **Drugi producent:** ADI ADCMP361 (±2,5% na zboczu opadającym). Microchip MCP65R41 i ADI LTC1540 odpadają z powodu dokładności.

### Kondensator podtrzymania VSYS

C ≥ 2·P·t/(V₁² − V₂²) = 2 · 0,42 W · 2 ms / (3,4² − 2,7²) = 393 µF. Przy progu 3,325 V (najgorszy przypadek komparatora) wychodzi ≥450 µF. Po tolerancji −20% i około −10% w −20 °C potrzeba nominalnie 680 µF.

| Kandydat | Pojemność / napięcie | Upływ (napięcie znamionowe) | Uwagi |
|---|---|---|---|
| Nichicon UKL1E681MHD (elektrolit o małym upływie) | 680 µF / 25 V, Ø12,5 × 25 mm | ≤34 µA (0,002 CV) | część pozycji serii ma status „do wycofania”; ten numer do sprawdzenia. ESR wyższa niż polimeru, więc równolegle ceramika |
| Nichicon PCR1E471MCL1GS (polimer) | 470 µF / 25 V | ≤352 µA | odpada ze względu na budżet (Z4) |

Upływ elektrolitu przy 6 V (około 25% napięcia znamionowego) jest zwykle dużo niższy od wartości katalogowej, ale karta go nie podaje, więc się go mierzy. Drugi producent elektrolitu o małym upływie (Panasonic albo Kemet) do znalezienia.

### Szyna 5 V ekranu i podświetlenie

- **TI TPS61099DRV** (regulowany, WSON 2 × 2 mm) z dzielnikiem 4,02 MΩ / 1 MΩ → 5,02 V.
  - Prawdziwe odłączenie wyjścia w wyłączeniu; Iq około 1 µA.
  - Sprawność 3,3 → 5 V przy 15 mA około 93–94%.
- **Drugi producent:** Microchip MCP1640 (wersja z odłączeniem obciążenia; wersje C i D w wyłączeniu przepuszczają wejście na wyjście).
- **Obciążenie:** panel Sharp (do 350 µW, około 70 µA przy 5 V) i podświetlenie 15 mA, razem około 25 mA z 3V3.
- **Panel pamięciowy** trzyma obraz tylko pod napięciem, więc szyna 5 V pracuje przez cały czas działania stacji.
- **Sterownik podświetlenia:** Diodes AL5802, liniowe źródło prądowe: 15 mA przy R = 43 Ω, wejście EN do PWM. AL5809 odpada, bo potrzebuje 2,5 V zapasu. Drugi producent do znalezienia.

### Pomiar napięć

- **Dzielnik 12 V:** 100 kΩ / 10,2 kΩ (0,1%) z kluczem górnym PMOS BSS84AK (−50 V), sterowanym przez 2N7002 z GPIO.
  - Napięcie na wejściu ADC: 1,06 V przy 11,5 V, 1,48 V przy 16 V i 2,70 V przy impulsie 29,2 V, czyli poniżej VDD.
  - Upływ klucza w stanie wyłączonym ≤1 µA.
- **nRF52840 (A):** błąd wzmocnienia SAADC wynosi ±3%. Wymaganie 2% wymaga więc kalibracji jednopunktowej przy produkcji; po kalibracji błąd to około 0,8%.
- **ESP32-S3 (B):** zakres ATTEN2 (0–1,6 V) z kalibracją eFuse daje ±10 mV, czyli 0,7–0,9%.

## Bilans prądu w stanie wyłączonym

25 °C, wartości typowe / najwyższe.

| Źródło i stan | Składniki | Razem |
|---|---|---|
| Ogniwa, bez 12 V (dioda Schottky’ego i LTC2955) | LTC2955 1,2/3 µA, LTC3115-1 3/10 µA, LM74800 przez diodę podłożową 2,9/5 µA, klucze dzielników 0/1 µA, dioda sumy od strony 12 V (BAS116H) ≈0 | **około 7/19 µA** (cel ≤20 µA) |
| Dla porównania: z LTC2954 | LTC2954 6/12 µA zamiast LTC2955 | około 12/28 µA |
| Dla porównania: z LTC4412 i LTC2954 | LTC4412 dokładał 12/21 µA | około 24/49 µA |
| 12 V, z ogniwami | LTC2955 1,2/3 µA, LM74800 2,9/5 µA, TVS ≈0/1 µA, dzielnik i PMOS zatrzasku ≈0/2 µA | **około 4/11 µA**, bez bipolarnego elektrolitu |
| Ogniwa przy obecnym 12 V | LTC3115-1 nie pobiera z ogniw (VSYS z 12 V); prąd wsteczny diody Schottky’ego płynie do ogniw (do sprawdzenia w karcie diody) | prąd wsteczny diody |

Do tego dochodzi upływ kondensatora podtrzymania VSYS, którego karta nie podaje dla 6 V (Z4). Dlatego bilans potwierdza się pomiarem.

Z LTC2955 cel ≤20 µA jest spełniony także w najgorszym przypadku, ale z zapasem tylko około 1 µA. Największy składnik to LTC3115-1 w wyłączeniu (10 µA najwyżej), a upływ kondensatora podtrzymania dochodzi osobno. Bez pomiaru wynik nie jest więc rozstrzygnięty.

## Reguła OVP

| Układ | Maksimum pracy | 0,9 × maksimum | Najgorsze napięcie | Wynik |
|---|---|---|---|---|
| LTC3115-1 (VIN) | 40 V | 36 V | OVP 17,75 V + 0,5 V przerzutu = 18,3 V | spełniona |
| TPS3710 zasilany z 3V3 | 18 V | 16,2 V | 3,3 V | spełniona |
| Dioda Schottky’ego toru ogniw (VR) | ≥30 V | 27 V | 18,3 V | spełniona |
| LTC2955 (przed S12) | 36 V | 32,4 V | impuls około 28,5 V | spełniona; filtr RC 1 kΩ / 1 µF według zalecenia karty dla VIN >20 V (Z14) |
| TPS3701 | 36 V | 32,4 V | 29,2 V | spełniona |
| TPS70933 | 30 V | 27 V | 29,2 V | spełniona dopiero z rezystorem i diodą Zenera |

Przerzut liczono tak: OV wyłącza bramkę w ≤5,4 µs, a w tym czasie nawet 50 A podnosi 600 µF o około 0,5 V.

## Próby teraz, na płytkach ewaluacyjnych

Wyniki tych prób są potrzebne do schematu zasilania, a nie wymagają T3–T5.

| Próba | Płytka | Cena (DigiKey, 2026-10-08) | Co mierzyć |
|---|---|---|---|
| Przetwornica 3V3 | ADI DC1687B (LTC3115-1; zmienić dzielnik na 3,3 V i R_T na 750 kHz) | około 230 USD (element14) | sprawność przy 30–60 mA z 6 V i 12,8 V w Burst Mode, Iq bez obciążenia, prąd w wyłączeniu, granica Burst Mode, przejście PWM/SYNC przy impulsie TX |
| Sterownik wyłącznika | ADI DC1836A-B (LTC2955IDDB-2; ta sama struktura w obudowie DFN, ON zwarty do GND, SEL do GND) | do sprawdzenia | INT przy krótkim i długim naciśnięciu, przerwanie wyłączania po puszczeniu przycisku, KILL i okno 304 ms, wymuszone wyłączenie z C_TMR 2,2 µF, stan EN̄ z dzielnikiem bramki 100 kΩ / 100 kΩ, prąd w stanie wyłączonym przy 4,0–6,6 V i 16 V |
| Łącznik S12 | TI LM74800EVM-CD i ADI DC2418A-B (LTC4368-2) | 126,22 i 118,28 USD | próg OVP, narastanie przy 600 µF, odwrotne podłączenie 16 V, impuls 30 V, prąd w wyłączeniu z obu stron |
| Tor ogniw | płytka uniwersalna z diodą Schottky’ego i rezystorem 1 Ω | części kilka USD | spadek przy 40–120 mA, prąd wsteczny przy 16 V w 25 °C i 45 °C, udar przy wkładaniu ogniw Li-FeS2, przełączanie ogniwa ↔ 12 V bez spadku 3V3, VSYS przy impulsie TX na zimnych ogniwach |
| Szyna 5 V | TI TPS61099EVM-023 albo -768 (sklep TI: 20 i 53 szt.; która wersja układu jest na płytce, do sprawdzenia) | do sprawdzenia | zasilanie panelu Sharp z N1, prąd w wyłączeniu |
| Zatrzask UV | płytka uniwersalna z TPS3701 i 74LVC | części około 10 USD | progi 11,5 i 12,4 V, kasowanie przy wyłączeniu i odłączeniu 12 V, pobór |
| Kondensator podtrzymania | próbki UKL i PCR | | upływ przy 6 V w 25 °C i 45 °C |

Pomiary zapisuje się w `hardware/r02/checks/` (osoba, data, przyrządy), a wyniki wpisuje do tego dokumentu i do [elektroniki](../../docs/spec/elektronika.md).

## Otwarte

- Prąd z ogniw w stanie wyłączonym: najgorszy przypadek z LTC2955 wynosi około 19 µA przy celu ≤20 µA, więc rozstrzyga pomiar razem z upływem kondensatora podtrzymania.
- Rozrzut t_TMR przy 2,2 µF (karta podaje go tylko dla 2,2 nF).
- Dioda Schottky’ego toru ogniw: dopuszczalny prąd wsteczny ogniw Li-FeS2 i części dwóch producentów.
- Zapas VSYS do progu komparatora przy zimnych ogniwach (T6).
- Drugi producent dla:
  - sterownika wyłącznika (propozycja: STM6601 z LDO TPS70930, do próby);
  - przetwornicy 3V3 (propozycja: przetwornica obniżająca TPS629210, zależna od D14);
  - N-MOSFET z SOA dla 10 ms;
  - diody o małym upływie;
  - elektrolitu o małym upływie;
  - sterownika podświetlenia.
- Opór wewnętrzny ogniw Li-FeS2 (Energizer L91) do obliczenia udaru.
- Upływ kondensatora podtrzymania przy 6 V.
- Pobór 74LVC w zatrzasku w pełnym zakresie temperatur.

## Źródła

- ADI LTC2955 rew. A (s. 2–4, 6, 8–10, 13–14): https://www.analog.com/media/en/technical-documentation/data-sheets/2955fa.pdf; LTC2954 rew. B (poprzedni wybór): https://www.analog.com/media/en/technical-documentation/data-sheets/2954fb.pdf
- ADI LTC3115-1 rew. C: https://www.analog.com/media/en/technical-documentation/data-sheets/LTC3115-1.pdf
- ADI LTC4412 rew. C: https://www.analog.com/media/en/technical-documentation/data-sheets/LTC4412.pdf; LTC4368 rew. C: https://www.analog.com/media/en/technical-documentation/data-sheets/LTC4368.pdf; LTC2965 rew. C: https://www.analog.com/media/en/technical-documentation/data-sheets/2965fc.pdf; ADCMP361 rew. B
- TI LM7480-Q1 SNOSD95C: https://www.ti.com/lit/ds/symlink/lm7480-q1.pdf; TPS3701 SBVS240C; TPS3710 SBVS271A: https://www.ti.com/lit/ds/symlink/tps3710.pdf; TPS709 SBVS186H; TPS61099 SLVSD88M: https://www.ti.com/lit/ds/symlink/tps61099.pdf; TPS63070 SLVSC58B
- Microchip MCP1640 DS20002234D; Diodes AL5802 DS35516
- Nichicon UES (CAT.8100N), PCR (CAT.8100N), UKL (CAT.8100M); Panasonic SU-A
- Nexperia BUK7Y12-40E, BSS84AK, BAS116H, BAT46WJ, BUK6Y19-30P; Vishay SQ3495EV (77077), SMBJ18CA (88392); Diodes DMP3018SFV (DS40134); Infineon BSZ063N04LS6 rew. 2.1
- Schurter SPT 5×20: https://www.schurter.com/en/datasheet/typ_SPT_5x20.pdf; Littelfuse 477
- Nordic nRF52840 PS, SAADC: https://docs.nordicsemi.com/bundle/ps_nrf52840/page/saadc.html; Espressif ESP32-S3 datasheet v2.2, tabele 5-5 i 5-6
