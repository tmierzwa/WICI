# WICI — elektronika

Wartości poniżej służą do wykonania i pomiaru prototypu. Warianty różnych producentów wymagają oddzielnego sprawdzenia tolerancji i nie zawsze mają zgodne wyprowadzenia. Schemat połączeń nie zastępuje layoutu PCB ani odbioru 230 V.

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
A−, B−, JA−, JB− i minus Cbus połączone do GND.
BUS+ ─ wyłącznik DC ≥30 A ─ mostek przetwornicy
```

DA i DB: osobne podwójne Schottky ze wspólną katodą; obie anody danego elementu połączone. Katody do BUS+. Nie wykorzystujemy jednego elementu jako dwóch wejść 20 A. Kandydaci: ST STPS3045CT lub Vishay VS-MBR3045CT-M3, dwa elementy w zestawie. [ST](https://www.st.com/en/diodes-and-rectifiers/stps3045c.html), [Vishay](https://www.vishay.com/doc/?96257=).

| Element | Wymaganie prototypu |
|---|---|
| FA/FB, przewód zapalniczki | bezpiecznik 10 A; praca ≤8 A i nie więcej niż dopuszcza samochód |
| FA/FB, przewód zaciskowy | bezpiecznik 25 A; praca ≤20 A |
| Przewód zapalniczki | do 2 m, 2 × 2,5 mm², odpowiedni styk i temperatura wtyku |
| Przewód zaciskowy | do 2 m, 2 × 6 mm²; złącze ze stałą polaryzacją ≥30 A DC |
| TVSA/TVSB | SMCJ18CA, dwukierunkowy, po bezpieczniku, przed diodą |
| DA/DB | ≥45 V, po 20 A dla całego toru w wymaganej temperaturze |
| Radiator DA/DB | punkt wyjścia ≤3 K/W na tor, odizolowane elektrycznie mocowanie |
| Cbus | punkt wyjścia 8 × 2200 µF /35 V, łączny dopuszczalny prąd tętnień ≥24 A |
| Napięcie wejściowe | 11,5–16 V przy złączu, z uwzględnieniem spadku przewodów |

Kondensatory Cbus należą do stopnia mocy; rozłącznik DC odłącza mostek, nie przewody akumulatorów. Wspólna masa oznacza brak izolacji źródeł. Metalowe obudowy tych diod są połączone z katodą, czyli BUS+. Wspólny radiator może mieć ten sam potencjał; trzeba go odizolować od dostępnej obudowy i GND. Nie jest to zwarcie między wejściami A/B.

Diody nie zapewniają ograniczenia udaru. Przy 17,6 mF, skoku 5,5 V i założonym oporze pętli 40 mΩ model daje około 138 A początkowo. To założenie do próby, nie gwarantowany opór znalezionego akumulatora. Trzeba zmierzyć udar, sprawdzić I²t bezpieczników, dopuszczalny impuls diod i styków. Jeśli nie przejdą, konieczny będzie tor ograniczający udar; nie dopuszczamy modułu przez samo zwiększenie bezpiecznika.

Lampka wejścia potwierdza wyłącznie obecność prawidłowej polaryzacji. Ciągłość ma zapewniać nakładanie się źródeł, a nie energia Cbus. Ochrona podczas pracy alternatora i rozruchu wymaga osobnych prób automotive; TVS nie jest dowodem takiej odporności.

## Jedna sekcja ładowarki

Powielić 8 razy. Każda sekcja ma własny regulator, dławik, diodę, bezpieczniki i ogranicznik portu. Obwód C nie ma wspólnej masy z A/B.

```text
C+ ─ główny F10 A ─ magistrala ─ F1 1,5 A ─ dioda polaryzacji ─ VIN bucka
VIN ─ Cin ─ GND_C
LM2596 SW ─ L1 68 µH ─ VREG około 5,12 V ─ F2 szybki 3,15 A ─ VSAFE
GND_C ─ anoda D1; katoda D1 ─ SW
VREG ─ Cout ─ GND_C
VREG ─ Rtop 3,16 kΩ ─ FB ─ Rbottom 1,00 kΩ ─ GND_C
VSAFE ─ ogranicznik prądu ─ VUSB ─ USB-A pin 1
GND_C ─ USB-A pin 4; USB-A piny 2 i 3 zwarte
VSAFE ─ niezależny układ nadnapięciowy ─ GND_C
```

| Element | Wartość początkowa lub wymagana cecha |
|---|---|
| Regulator | LM2596-ADJ, TI lub onsemi; radiator zgodnie z pomiarem strat |
| L1 | 68 µH, Isat ≥6 A, Irms ≥3 A, DCR ≤40 mΩ |
| D1 i ochrona polaryzacji | Schottky ≥3 A /40 V; np. 1N5822 różnych producentów |
| Cin | 470 µF /35 V oraz 100 nF |
| Cout | 470 µF /16 V; elektrolit o ESR zgodnym z kartą regulatora |
| FB | Rbottom 1,00 kΩ, Rtop początkowo 3,16 kΩ; kontrola napięcia po montażu |
| Ogranicznik portu A | TPS2553, limit początkowo RILIM 15 kΩ, 0,1%; pełny budżet tolerancji nadal do odbioru; temperatura złącza ≤105°C |
| Ogranicznik portu B | nie wybrany; niezależny wariant musi zamknąć gwarantowany budżet prądu i temperatury |
| Prąd roboczy | 1,5 A na złączu, także po nagrzaniu |
| Próg ograniczania prądu | zakwalifikowany przedział 1,6–2,1 A przed foldback/wyłączeniem termicznym; zwarcie nie wyłącza innych sekcji |
| DCP | D+ i D− zwarte bez dodatkowego układu identyfikacji |

Nominalne 5,12 V nie gwarantuje poprawnego napięcia z tolerancji LM2596. W montażu dobiera się stały rezystor FB; nie pozostawiamy dostępnego potencjometru. Odbiór na złączu: 4,75–5,25 V przy 0–1,5 A, 11,5–16 V wejścia, 0–40°C otoczenia. Nie zamieniamy wymaganych kondensatorów elektrolitycznych na same ceramiczne bez sprawdzenia stabilności. [TI LM2596](https://www.ti.com/lit/ds/symlink/lm2596.pdf), [onsemi LM2596](https://www.onsemi.com/download/data-sheet/pdf/lm2596-d.pdf).

TPS2553 dopuszcza 1,5 A ciągłych przy temperaturze złącza do 105°C. Dla dokładnego 15 kΩ karta podaje próg 1,610–1,800 A, ale bez tolerancji rezystora; 1% nie daje wystarczającego zapasu ponad 1,6 A. Dlatego punktem wyjścia jest 0,1%, z obowiązkową weryfikacją całego budżetu.

MIC2007 nie zamyka doboru stałego rezystora według gwarantowanych granic karty: przy warunku IOUT=2 A, CLF=210–286 V wymagania 1,6–2,1 A dają jednocześnie RSET ≤131,25 Ω oraz ≥136,19 Ω. Przedział jest pusty jeszcze bez tolerancji rezystora. Nie traktujemy go jako gotowego drugiego wariantu. Inny element albo indywidualna kwalifikacja całego wariantu wymaga odrębnego projektu i dowodu. Nie zwiększać limitu prądu w celu zaakceptowania części. [TPS2553](https://www.ti.com/lit/ds/symlink/tps2553.pdf), [MIC2007](https://www.microchip.com/content/dam/mchp/documents/APID/ProductDocuments/DataSheets/MIC20XX-Fixed-and-Adjustable-Current-Limiting-Power-Distribution-Switches-DS20006486B.pdf).

### Ochrona przed podaniem 12 V na telefon

Kandydat do próby: crowbar TL431B + BC327 + SCR, przed ogranicznikiem USB. TL431 anoda do GND_C, REF przez dzielnik VSAFE–9,31 kΩ–REF–8,20 kΩ–GND_C. Katoda przez 1 kΩ do bazy PNP; emiter PNP do VSAFE, rezystor baza–emiter 2,2 kΩ. Kolektor przez 47 Ω do bramki SCR; bramka przez 1 kΩ do GND_C. Anoda SCR do VSAFE, katoda do GND_C. SCR: TYN612 albo BT151 z dopasowanym prądem bramki i I²t. Różne wykonania wymagają przeliczenia sterowania.

Próg nominalny 5,328 V. Wymagany zakres po tolerancjach i temperaturze 5,30–5,45 V. TL431B i oporniki 0,1% ograniczają rozrzut, lecz nie zastępują próby dynamicznej. F1/F2 mają odłączyć uszkodzoną gałąź z zachowaniem dopuszczalnego I²t SCR, przewodów i regulatora. Nie zakładamy, że F2 zadziała przed F1: prądy znamionowe i charakterystyki są różne; koordynację obu oraz głównego F10 A trzeba pomierzyć. Przy ograniczeniu prądu przez sprawny regulator bezpiecznik może nie przepalić się; SCR i chłodzenie muszą wtedy wytrzymać ten stan. Przed podłączeniem telefonów należy wymusić uszkodzenie wejście–wyjście bucka i zmierzyć szczyt VUSB oraz energię impulsu. Sam TVS opisany jako „5 V” nie zapewnia ochrony telefonu.

## Przetwornica

Wybrana topologia prototypu: transformator 50 Hz, mostek H po stronie niskiego napięcia, unipolarne SPWM 20 kHz. Nie budujemy magistrali 350 V DC. Zasada jest znana, ale wartości naszego stopnia są osobnym projektem. [TI SLAA602A](https://www.ti.com/lit/an/slaa602a/slaa602a.pdf).

```text
BUS+ ─ dreny Q1 i Q3
Q1 źródło = LEFT = dren Q2
Q3 źródło = RIGHT = dren Q4
T1 uzwojenie niskie pomiędzy LEFT i RIGHT
Q2/Q4 źródła = BRIDGE_RETURN ─ Rshunt 5 mΩ ─ GND
Cbus pomiędzy BUS+ i GND; nie pomiędzy BUS+ i BRIDGE_RETURN
T1 uzwojenie wysokie ─ filtr LC ─ ochrona AC ─ dwa wyjścia zasilaczy
```

| Część | Dobór do prototypu |
|---|---|
| Q1–Q4 | 4 × STP220N6F7 lub Infineon IPP030N06NF2S, ≥60 V, RDS(on) ≤3,1 mΩ przy 10 V |
| Sterowanie mostkiem | dwa UCC27211 albo dwa LTC4444; inne schematy zasilania i bootstrap |
| Napięcie sterowników | stabilizowane około 10 V; nie surowe napięcie samochodu |
| MCU | STM32F103 z TIM1 albo dsPIC33CK z PWM komplementarnym i wejściem FAULT |
| Martwy czas | początkowo 1 µs; pomiar obu bramek pod obciążeniem |
| Rezystory bramek | 10 Ω, pulldown 10 kΩ; korekta na podstawie przebiegów |
| Bootstrap | początkowo 1 µF /25 V na półmostek, dobór z Qg i upływów |
| Ograniczenie modulacji | m ≤0,9, zapewniony czas odświeżania bootstrap |
| Bocznik | 5 mΩ, ≥10 W, połączenie Kelvin |
| Szybkie wyłączenie | komparator sprzętowy, próg początkowo 0,375 V czyli 75 A; zatrzask FAULT |
| Logika blokowania | H AND NOT L, L AND NOT H; następnie AND ENABLE; bez polegania tylko na MCU |
| Komparator | TLV3201 lub MCP6561, z uwzględnieniem błędu i opóźnienia |
| Logika | 74HC04, 74HC08, zatrzask CD4013; dostępne u różnych producentów |
| Temperatura | NTC na radiatorze; zatrzymanie przy 85°C, ręczny restart po schłodzeniu |
| Profil ciągłego prądu | 8 A lub 20 A, dodatkowy pomiar uśredniony; bezpiecznik chroni przewód |

Źródło odniesienia sterownika musi być przy źródle dolnego MOSFETa. Umieszczenie minusa Cbus nad bocznikiem ominęłoby pomiar prądu zwarcia mostka. Wysterowanie obu tranzystorów półmostka jednocześnie ma sprzętowo wyłączyć oba. FAULT zeruje ENABLE i wejście BREAK, niezależnie od obsługi przerwania. Start i reset MCU utrzymują bramki wyłączone.

MOSFETy ST i Infineon mają odpowiednie napięcie i opór katalogowy; straty i chłodzenie liczy się dla rozgrzanych tranzystorów, a nie prądu z nagłówka katalogu. [ST](https://www.st.com/resource/en/datasheet/stp220n6f7.pdf), [Infineon](https://www.infineon.com/part/IPP030N06NF2S). Sterowniki również nie są zamiennikami bez zmian układu. [TI](https://www.ti.com/lit/ds/symlink/ucc27211.pdf), [ADI](https://www.analog.com/media/en/technical-documentation/data-sheets/4444fb.pdf).

### Transformator i filtr

150 W dotyczy obciążenia rezystancyjnego; nie jest obietnicą dla dowolnego zestawu zasilaczy impulsowych. Ich współczynnik mocy, szczyty prądu i rozruch wymagają osobnej kwalifikacji. Model przy minimalnym napięciu daje tylko około 0,27 V zapasu po stronie niskiej, bez prądu magnesowania i strat przełączania. Jeśli próba zawiedzie, należy zmienić transformator lub obniżyć dopuszczalną moc, a nie podnosić próg zwarcia.

T1 do pierwszej próby: rdzeń stalowy 50 Hz, Ae ≥14 cm², dostępne okno uzwojeń ≥1200 mm². Uzwojenie niskie 20 zwojów, cztery równoległe druty 1,8 mm; wysokie 840 zwojów drutem 0,50 mm. Przekładnia 42. Izolacja i odstępy dla separacji sieciowej; konstrukcję bobiny oraz barierę izolacyjną zatwierdza wykonawca transformatora. Nie wystarczy nawinąć obu uzwojeń na przypadkowym rdzeniu.

Wymagany odbiór T1: R uzwojenia niskiego ≤12 mΩ, wysokiego ≤25 Ω przy temperaturze pracy; wytrzymałość izolacji i temperatura potwierdzone według dobranej normy. Same wymiary rdzenia nie gwarantują tych oporów. Przy 230 V i 150 W prąd niskiego uzwojenia wynosi idealnie 27,4 A RMS; trzeba doliczyć prąd magnesowania i filtr.

Filtr początkowy po stronie 230 V: L = 10 mH, ≥1 A RMS, niesaturujący przy szczytach prądu zasilaczy; C = 1 µF /630 V DC, folia o odpowiednim dopuszczeniu AC. Równoległa gałąź tłumiąca: 100 Ω /2 W szeregowo z 0,47 µF /630 V. Rezystor rozładowania: 2 ×150 kΩ /0,5 W szeregowo. L, C i tłumienie wymagają pomiaru przy braku obciążenia oraz rzeczywistych zasilaczach; rezonans LC około 1,59 kHz nie jest dowodem stabilności ani THD.

Sprzężenie napięcia: osobny transformator pomiarowy 230/6 V, ≥1 VA, za filtrem. Pomiar RMS oraz kalibracja podziału ADC na stanowisku. Regulator podaje wstępne m = 230√2/(42×VBUS), z ograniczeniem 0,9 i powolnym startem. Zabezpieczenia: brak danych ADC, watchdog, przegrzanie, nadprąd, nadnapięcie AC i zbyt niskie BUS wyłączają mostek. Konkretne stałe regulatora i próg nadnapięcia AC wymagają modelu oraz próby; firmware sterownika nie został napisany.

### Wyjścia 230 V i PE

Wariant do odbioru elektrycznego: jeden punkt N–PE po stronie źródła, przed osobnymi dwubiegunowymi RCBO typu A /30 mA dla każdego gniazda. PE obu gniazd i metalowej obudowy na wspólnej szynie; zewnętrzny zacisk do sprawdzonego układu uziemienia. PE nigdy nie przechodzi przez wyłącznik. Dobór charakterystyki nadprądowej musi uwzględniać prąd rozruchu zasilaczy i ograniczenie samej przetwornicy. Układ zasila wyłącznie swoje gniazda, bez połączenia z obwodami zasilającymi budynku.

To wymaga sprawdzonego PE lub zaprojektowanego lokalnego uziemienia. Jest dodatkowym warunkiem dla zasilaczy klasy I, którego nie można zagwarantować z założenia „mamy samochód”. Samo zwarcie N z PE ani przycisk TEST RCD nie potwierdzają ochrony w schronieniu. Jeśli nie ma takiej możliwości, wariant dla przypadkowych zasilaczy klasy I nie jest zamknięty. Próby na stanowisku z zasilaczami klasy II nie dowodzą zgodności całego wymagania. [Zasady zasilania przenośnego HSE, nie norma polska](https://www.hse.gov.uk/pubns/priced/hsg141.pdf).

Do odbioru potrzebne są pomiary izolacji, ciągłości PE, prądu dotykowego, reakcji na uszkodzenie i działania ochrony przy ograniczonym źródle. Przetwornica nie jest obecnie modułem do samodzielnego złożenia przez niewykwalifikowaną osobę. Otwarty projekt pozwala różnym warsztatom ją produkować po zamknięciu tej części; nie usuwa konieczności bezpiecznego wykonania.
