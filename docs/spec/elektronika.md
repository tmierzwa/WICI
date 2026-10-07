# WICI — elektronika

Wartości poniżej służą do wykonania i pomiaru prototypu. Warianty różnych producentów wymagają oddzielnego sprawdzenia tolerancji i nie zawsze mają zgodne wyprowadzenia. Schemat połączeń nie zastępuje projektu płytki drukowanej (PCB) ani odbioru części 230 V.

## Wejścia A/B

```text
A+ ─ FA przy zacisku ─ przewód ─ JA+ ─ [DA: A→K] ─┐
                               │               │
                              TVSA           BUS+
                               │               │
                              GND              │
B+ ─ FB przy zacisku ─ przewód ─ JB+ ─ [DB: A→K] ─┘
                               │
                              TVSB
                               │
                              GND
A−, B−, JA−, JB− i minus Cbus połączone z GND.
BUS+ ─ wyłącznik DC ≥30 A (znamionowany dla prądu stałego) ─ mostek przetwornicy
```

DA i DB: osobne podwójne diody Schottky’ego ze wspólną katodą; obie anody danego elementu są połączone. Katody dołączone do BUS+. Nie wykorzystujemy jednego elementu jako dwóch wejść 20 A. Kandydaci: ST STPS3045CT lub Vishay VS-MBR3045CT-M3, dwa elementy w zestawie. [ST](https://www.st.com/en/diodes-and-rectifiers/stps3045c.html), [Vishay](https://www.vishay.com/doc/?96257=).

| Element | Wymaganie prototypu |
|---|---|
| FA/FB, przewód do gniazda zapalniczki | bezpiecznik 10 A; praca ≤8 A i nie więcej, niż dopuszcza instalacja pojazdu |
| FA/FB, przewód zaciskowy | bezpiecznik 25 A; praca ≤20 A |
| Przewód do gniazda zapalniczki | do 2 m, 2 × 2,5 mm²; styk i dopuszczalna temperatura wtyku dobrane do prądu |
| Przewód zaciskowy | do 2 m, 2 × 6 mm²; złącze uniemożliwiające odwrotne podłączenie, ≥30 A DC |
| TVSA/TVSB | SMCJ18CA, dwukierunkowy, po bezpieczniku, przed diodą |
| DA/DB | ≥45 V, po 20 A dla całego toru w wymaganej temperaturze |
| Radiator DA/DB | punkt wyjścia: ≤3 K/W na tor; mocowanie izolowane elektrycznie |
| Cbus | punkt wyjścia: 8 × 2200 µF/35 V; łączny dopuszczalny prąd tętnień ≥24 A |
| Napięcie wejściowe | 11,5–16 V przy złączu, z uwzględnieniem spadku przewodów |

Kondensatory Cbus należą do stopnia mocy; rozłącznik DC odłącza mostek, nie przewody akumulatorów. Wspólna masa oznacza brak izolacji źródeł. Metalowe obudowy tych diod są połączone z katodą, czyli z BUS+. Wspólny radiator może mieć ten sam potencjał; trzeba go odizolować od dostępnej obudowy i GND. Nie jest to zwarcie między wejściami A/B.

Diody nie zapewniają ograniczenia udaru. Przy 17,6 mF, skoku napięcia 5,5 V i założonej rezystancji pętli 40 mΩ model daje początkowy prąd około 138 A. Jest to założenie do próby, a nie gwarantowana rezystancja znalezionego akumulatora. Trzeba zmierzyć prąd udarowy oraz sprawdzić całkę Joule’a (I²t) bezpieczników i dopuszczalny impuls prądowy diod i styków. Jeśli wynik będzie negatywny, konieczny będzie układ ograniczający prąd udarowy; nie dopuszcza się modułu do pracy wyłącznie przez zwiększenie wartości bezpiecznika.

Lampka wejścia potwierdza wyłącznie obecność napięcia o prawidłowej polaryzacji. Każde wejście A, B i C ma ponadto woltomierz cyfrowy o błędzie ≤1%, mierzący napięcie przed diodą; bez niego opiekun nie zaplanuje wymiany źródeł. Ciągłość zasilania ma zapewniać jednoczesne podłączenie obu źródeł podczas wymiany, a nie energia zgromadzona w Cbus. Ochrona podczas pracy alternatora i rozruchu silnika wymaga osobnych prób motoryzacyjnych; sama dioda TVS nie dowodzi takiej odporności.

Ochrona przed głębokim rozładowaniem: przetwornica wyłącza mostek, gdy napięcie na złączach wejściowych spadnie poniżej 11,5 V (z uwzględnieniem spadku na diodzie), i uruchamia się ponownie dopiero powyżej 12,4 V. Ten sam próg i ta sama histereza dotyczą wejścia C ładowarki. Głęboko rozładowany akumulator kwasowo-ołowiowy traci pojemność, a akumulator rozruchowy — zdolność uruchomienia pojazdu; dla niego opiekun wymienia źródło wcześniej, przy około 12,2 V. Akumulator LiFePO4 ma własny BMS, który nie zastępuje tego progu.

## Jedna sekcja ładowarki

Sekcję powiela się 8 razy. Każda sekcja ma własny regulator, dławik, diodę, bezpieczniki i ogranicznik portu. Obwód C nie ma wspólnej masy z A/B. Wspólny dla wszystkich sekcji jest odłącznik podnapięciowy wejścia C (11,5 V / 12,4 V); sam LM2596 pracuje do około 7 V wejścia i rozładowałby akumulator do zera.

```text
C+ ─ główny F10 A ─ magistrala ─ F1 1,5 A ─ dioda polaryzacji ─ VIN regulatora
VIN ─ Cin ─ GND_C
LM2596 SW ─ L1 68 µH ─ VREG około 5,12 V ─ F2 szybki 3,15 A ─ VSAFE
GND_C ─ anoda D1; katoda D1 ─ SW
VREG ─ Cout ─ GND_C
VREG ─ Rtop 3,16 kΩ ─ FB ─ Rbottom 1,00 kΩ ─ GND_C
VSAFE ─ ogranicznik prądu ─ VUSB ─ USB-A pin 1
GND_C ─ USB-A pin 4; USB-A piny 2 i 3 zwarte
VSAFE ─ niezależny układ przepięciowy ─ GND_C
```

| Element | Wartość początkowa lub wymagana cecha |
|---|---|
| Regulator | LM2596-ADJ, TI lub onsemi; radiator dobrany na podstawie pomiaru strat |
| L1 | 68 µH, Isat ≥6 A, Irms ≥3 A, DCR ≤40 mΩ |
| D1 i ochrona polaryzacji | dioda Schottky’ego ≥3 A/40 V, np. 1N5822 różnych producentów |
| Cin | 470 µF/35 V oraz 100 nF |
| Cout | 470 µF/16 V; kondensator elektrolityczny o ESR zgodnej z kartą katalogową regulatora |
| FB | Rbottom 1,00 kΩ, Rtop początkowo 3,16 kΩ; kontrola napięcia po montażu |
| Ogranicznik portu A | TPS2553, limit początkowo RILIM 15 kΩ, 0,1%; pełny budżet tolerancji nadal do odbioru; temperatura złącza ≤105 °C |
| Ogranicznik portu B | niewybrany; niezależny wariant musi zamknąć gwarantowany budżet prądu i temperatury |
| Prąd roboczy | 1,5 A na złączu, także po nagrzaniu |
| Próg ograniczania prądu | zakwalifikowany przedział 1,6–2,1 A przed ograniczeniem zwrotnym (foldback) lub wyłączeniem termicznym; zwarcie nie wyłącza innych sekcji |
| DCP | D+ i D− zwarte bez dodatkowego układu identyfikacji |

Nominalne 5,12 V nie gwarantuje poprawnego napięcia przy tolerancjach LM2596. W montażu dobiera się stały rezystor FB; nie pozostawiamy dostępnego potencjometru. Odbiór na złączu: 4,75–5,25 V przy 0–1,5 A, 11,5–16 V na wejściu, 0–40 °C w otoczeniu. Nie zamieniamy wymaganych kondensatorów elektrolitycznych na same ceramiczne bez sprawdzenia stabilności. Bez strojenia rezystorem FB tolerancja źródła odniesienia LM2596 daje do 5,27 V, tylko 30 mV poniżej najniższego progu zwieracza; strojenie każdej sekcji jest więc obowiązkowe. Przeskok napięcia po nagłym odłączeniu obciążenia 1,5 A nie może zbliżyć VREG do progu zwieracza, ponieważ jego zadziałanie trwale wyłącza sekcję. [TI LM2596](https://www.ti.com/lit/ds/symlink/lm2596.pdf), [onsemi LM2596](https://www.onsemi.com/download/data-sheet/pdf/lm2596-d.pdf).

TPS2553 dopuszcza 1,5 A prądu ciągłego przy temperaturze złącza do 105 °C. Dla rezystora o wartości dokładnie 15 kΩ karta katalogowa podaje próg 1,610–1,800 A, bez uwzględnienia tolerancji rezystora; rezystor 1% nie zapewnia wystarczającego zapasu powyżej 1,6 A. Dlatego punktem wyjścia jest rezystor 0,1%, z obowiązkową weryfikacją całego budżetu.

Dla MIC2007 nie da się dobrać stałego rezystora w gwarantowanych granicach karty katalogowej: przy warunku IOUT = 2 A i CLF = 210–286 V wymagania 1,6–2,1 A dają jednocześnie RSET ≤131,25 Ω oraz RSET ≥136,19 Ω. Przedział jest pusty jeszcze bez tolerancji rezystora. Nie traktujemy go jako gotowego drugiego wariantu. Inny element albo indywidualna kwalifikacja całego wariantu wymaga odrębnego projektu i dowodu. Nie wolno zwiększać limitu prądu tylko po to, by zaakceptować część. [TPS2553](https://www.ti.com/lit/ds/symlink/tps2553.pdf), [MIC2007](https://www.microchip.com/content/dam/mchp/documents/APID/ProductDocuments/DataSheets/MIC20XX-Fixed-and-Adjustable-Current-Limiting-Power-Distribution-Switches-DS20006486B.pdf).

### Ochrona przed podaniem 12 V na telefon

Kandydat do próby: zwieracz zabezpieczający (crowbar) TL431B + BC327 + tyrystor (SCR), przed ogranicznikiem USB. Anoda TL431 do GND_C, wejście REF przez dzielnik VSAFE–9,31 kΩ–REF–8,20 kΩ–GND_C. Katoda przez 1 kΩ do bazy tranzystora PNP; emiter PNP do VSAFE, rezystor baza–emiter 2,2 kΩ. Kolektor przez 47 Ω do bramki tyrystora; bramka przez 1 kΩ do GND_C. Anoda tyrystora do VSAFE, katoda do GND_C. Tyrystor: TYN612 albo BT151 z dopasowanym prądem bramki i I²t. Różne wykonania wymagają przeliczenia sterowania.

Próg nominalny 5,328 V. Wymagany zakres po tolerancjach i temperaturze 5,30–5,45 V. TL431B i rezystory 0,1% ograniczają rozrzut, lecz nie zastępują próby dynamicznej. F1/F2 mają odłączyć uszkodzoną gałąź z zachowaniem dopuszczalnej wartości I²t tyrystora, przewodów i regulatora. Nie zakładamy, że F2 zadziała przed F1: prądy znamionowe i charakterystyki są różne; koordynację obu oraz głównego F10 A trzeba zmierzyć. Gdy sprawny regulator ogranicza prąd, bezpiecznik może się nie przepalić; tyrystor i jego chłodzenie muszą wtedy wytrzymać ten stan. Przed podłączeniem telefonów należy wymusić zwarcie wejścia z wyjściem przetwornicy obniżającej oraz zmierzyć szczytowe VUSB i energię impulsu. Sama dioda TVS opisana jako „5 V” nie zapewnia ochrony telefonu.

## Przetwornica

Wybrana topologia prototypu: transformator 50 Hz, mostek H po stronie dolnego napięcia, unipolarna modulacja SPWM 20 kHz. Nie budujemy magistrali 350 V DC. Zasada jest znana, ale wartości naszego stopnia są osobnym projektem. [TI SLAA602A](https://www.ti.com/lit/an/slaa602a/slaa602a.pdf).

```text
BUS+ ─ dreny Q1 i Q3
Q1 źródło = LEFT = dren Q2
Q3 źródło = RIGHT = dren Q4
T1 uzwojenie DN między LEFT i RIGHT
Q2/Q4 źródła = BRIDGE_RETURN ─ Rshunt 5 mΩ ─ GND
Cbus między BUS+ i GND; nie między BUS+ i BRIDGE_RETURN
T1 uzwojenie GN ─ filtr LC ─ ochrona AC ─ dwa wyjścia zasilaczy
```

| Część | Dobór do prototypu |
|---|---|
| Q1–Q4 | 4 × ST STP220N6F7 lub Infineon IPP030N06NF2S, ≥60 V, RDS(on) ≤3,1 mΩ przy 10 V |
| Sterowanie mostkiem | dwa UCC27211 albo dwa LTC4444; różne układy zasilania i bootstrapu |
| Napięcie sterowników | stabilizowane, około 10 V; nie bezpośrednio z instalacji pojazdu |
| MCU | STM32F103 z TIM1 albo dsPIC33CK z komplementarnym PWM i wejściem FAULT |
| Czas martwy | początkowo 1 µs; pomiar obu bramek pod obciążeniem |
| Rezystory bramek | 10 Ω, rezystor ściągający 10 kΩ; korekta na podstawie przebiegów |
| Kondensator bootstrap | początkowo 1 µF/25 V na półmostek; dobór na podstawie Qg i prądów upływu |
| Ograniczenie modulacji | m ≤0,9; zapewniony czas doładowania kondensatora bootstrap |
| Bocznik | 5 mΩ, ≥10 W, połączenie Kelvin |
| Szybkie wyłączenie | komparator sprzętowy, próg początkowo 0,375 V, czyli 75 A; zatrzask FAULT |
| Logika blokowania | H AND NOT L, L AND NOT H; następnie AND ENABLE; bez polegania tylko na MCU |
| Komparator | TLV3201 lub MCP6561, z uwzględnieniem błędu i opóźnienia |
| Logika | 74HC04, 74HC08, zatrzask CD4013; dostępne u różnych producentów |
| Temperatura | termistor NTC na radiatorze; zatrzymanie przy 85 °C, ręczny restart po ostygnięciu |
| Profil prądu ciągłego | 8 A lub 20 A, dodatkowy pomiar uśredniony; bezpiecznik chroni przewód |

Masa odniesienia sterownika musi być dołączona przy źródle dolnego tranzystora MOSFET. Podłączenie minusa Cbus do BRIDGE_RETURN, przed bocznikiem, ominęłoby pomiar prądu zwarcia mostka. Jednoczesne wysterowanie obu tranzystorów półmostka ma sprzętowo wyłączyć oba. FAULT zeruje ENABLE i wejście BREAK niezależnie od obsługi przerwania. Podczas startu i resetu MCU bramki pozostają wyłączone.

Uzwojenie DN ma rezystancję około 12 mΩ, więc niesymetria wysterowania mostka rzędu 10 mV daje prąd stały blisko 1 A i podmagnesowanie rdzenia. Regulator mierzy składową stałą prądu uzwojenia DN i ją kompensuje; próba obejmuje prąd magnesowania bez oznak jednostronnego nasycenia, także po skokach obciążenia.

Tranzystory MOSFET firm ST i Infineon mają odpowiednie napięcie i rezystancję katalogową; straty i chłodzenie oblicza się dla nagrzanych tranzystorów, a nie na podstawie prądu z nagłówka karty katalogowej. [ST](https://www.st.com/resource/en/datasheet/stp220n6f7.pdf), [Infineon](https://www.infineon.com/part/IPP030N06NF2S). Sterowniki również nie są zamienne bez zmian w układzie. [TI](https://www.ti.com/lit/ds/symlink/ucc27211.pdf), [ADI](https://www.analog.com/media/en/technical-documentation/data-sheets/4444fb.pdf).

### Transformator i filtr

Moc 150 W dotyczy obciążenia rezystancyjnego; nie jest obietnicą dla dowolnego zestawu zasilaczy impulsowych. Ich współczynnik mocy, szczyty prądu i rozruch wymagają osobnej kwalifikacji. Przy minimalnym napięciu model daje tylko około 0,27 V zapasu po stronie DN, bez prądu magnesowania i strat przełączania. Jeśli próba zawiedzie, należy zmienić transformator lub obniżyć dopuszczalną moc, a nie podnosić próg zwarcia.

Zasilacz impulsowy bez PFC pobiera prąd szczytowy około trzykrotnie większy od wartości skutecznej. Laptop 60 W daje po stronie DN szczyty rzędu 50 A, a prąd ładowania kondensatora wejściowego zasilacza podłączanego pod napięcie wielokrotnie przekracza próg 75 A. Zasilacze podłącza się więc przed zamknięciem wyłącznika DC, a przetwornica rusza z łagodnym startem napięcia. Podłączenie pod napięciem może wyzwolić zatrzask FAULT; wymaga wtedy ręcznego restartu, ale nie może uszkodzić mostka.

T1 do pierwszej próby: rdzeń stalowy 50 Hz, Ae ≥14 cm², pole okna na uzwojenia ≥1200 mm². Uzwojenie dolnego napięcia (DN): 20 zwojów, cztery równoległe druty 1,8 mm; uzwojenie górnego napięcia (GN): 840 zwojów drutem 0,50 mm. Przekładnia: 42. Izolacja i odstępy zapewniające separację od sieci; konstrukcję karkasu oraz barierę izolacyjną zatwierdza wykonawca transformatora. Nie wystarczy nawinąć obu uzwojeń na przypadkowym rdzeniu.

Wymagany odbiór T1: rezystancja uzwojenia DN ≤12 mΩ, uzwojenia GN ≤25 Ω w temperaturze pracy; wytrzymałość izolacji i temperatura potwierdzone według dobranej normy. Same wymiary rdzenia nie gwarantują tych rezystancji. Przy 230 V i 150 W wartość skuteczna prądu uzwojenia DN wynosi w przypadku idealnym 27,4 A; trzeba doliczyć prąd magnesowania i prąd filtru.

Filtr początkowy po stronie 230 V: L = 10 mH, ≥1 A (wartość skuteczna), nienasycający się przy szczytach prądu zasilaczy; C = 1 µF/630 V DC, kondensator foliowy dopuszczony do pracy przy napięciu przemiennym. Równoległa gałąź tłumiąca: 100 Ω/2 W szeregowo z 0,47 µF/630 V. Rezystory rozładowujące: 2 × 150 kΩ/0,5 W połączone szeregowo. L, C i tłumienie wymagają pomiaru bez obciążenia oraz z rzeczywistymi zasilaczami; rezonans LC około 1,59 kHz nie jest dowodem stabilności ani THD.

Sprzężenie zwrotne napięcia: osobny transformator pomiarowy 230/6 V, ≥1 VA, za filtrem. Pomiar wartości skutecznej oraz kalibracja dzielnika ADC na stanowisku. Regulator podaje wstępne m = 230√2/(42×VBUS), z ograniczeniem 0,9 i powolnym startem. Mostek wyłączają: brak danych z ADC, zadziałanie układu nadzorującego (watchdog), przegrzanie, przetężenie, przepięcie po stronie AC i zbyt niskie napięcie BUS. Konkretne stałe regulatora i próg przepięciowy AC wymagają modelu oraz próby; oprogramowanie układowe sterownika jeszcze nie powstało.

### Wyjścia 230 V i PE

Wariant do odbioru elektrycznego: jeden punkt N–PE po stronie źródła, przed osobnymi dwubiegunowymi wyłącznikami RCBO typu A 30 mA dla każdego gniazda. PE obu gniazd i metalowej obudowy na wspólnej szynie; zewnętrzny zacisk do sprawdzonego układu uziemienia. Przewód PE nigdy nie jest przerywany przez wyłącznik. Dobór charakterystyki nadprądowej musi uwzględniać prąd rozruchu zasilaczy i ograniczenie samej przetwornicy. Układ zasila wyłącznie swoje gniazda, bez połączenia z obwodami zasilającymi budynku.

To wymaga sprawdzonego PE lub zaprojektowanego lokalnego uziemienia. Jest dodatkowym warunkiem dla zasilaczy klasy I, którego nie można zagwarantować z założenia „mamy samochód”. Ani samo zwarcie N z PE, ani przycisk testowy wyłącznika różnicowoprądowego nie potwierdzają ochrony w schronieniu. Jeśli nie ma takiej możliwości, wariant dla przypadkowych zasilaczy klasy I nie jest zamknięty. Próby na stanowisku z zasilaczami klasy II nie dowodzą spełnienia całego wymagania. [Wytyczne HSE (nie jest to polska norma)](https://www.hse.gov.uk/pubns/priced/hsg141.pdf).

Do odbioru potrzebne są pomiary izolacji, ciągłości PE, prądu dotykowego, reakcji na uszkodzenie i działania ochrony przy źródle o ograniczonej wydajności prądowej. Przetwornica nie jest obecnie modułem do samodzielnego złożenia przez niewykwalifikowaną osobę. Po ukończeniu tej części otwarty projekt pozwala różnym warsztatom ją wytwarzać; nie usuwa konieczności bezpiecznego wykonania.
