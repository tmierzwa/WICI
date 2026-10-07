# WICI: montaż i uruchomienie płytki nośnej N1

Kolejność montażu, pierwsze włączenie i odbiór jednej sztuki płytki nośnej. Opis płytki, przypisanie sygnałów i granice stanowiska: [płytka nośna](plytka-nosna.md). Połączenia pin po pinie: [połączenia](polaczenia.md). Części: [BOM](bom.csv).

Każda sztuka dostaje zapis: numer, rewizja PCB (N1), stanowisko (A albo B), części spoza BOM, wyniki kroków poniżej, osoba i data.

## Montaż

Wszystko lutuje się ręcznie. Elementy SMD to 0805, 1206 (R2), SOT-23 i SOD-123.

1. **SMD najpierw:** R1–R19, C1–C5, Q1 (SOT-23; baza = pad 1), D3 (SOT-23, BAT54S), D2 (SOD-123; katoda, czyli pasek, po stronie oznaczonej na płytce; katoda łączy się z „+” brzęczyka).
2. **Niskie elementy przewlekane:** D1 (katoda, płaski bok i kwadratowy pad 1, do masy), SW6, SW1–SW4, SW5, BZ1 („+” brzęczyka na kwadratowym padzie 1), J12, J11, JP1, JP2, JP3.
3. **Gniazda modułów:** J7 i J8 (1 × 9), J5 i J6 (1 × 22). Gniazda wkłada się na wpiętym module albo na listwie, żeby stały pionowo i w osi.
4. **Złącza modułu radiowego J9/J10:** listwy 2 × 10 o rastrze 1,27 mm, krótszą stroną pinów w płytkę. Moduł CC1120EM wpina się w obie listwy naraz, więc przed lutowaniem trzeba je ustawić na module.
5. **Złącza Arduino J1–J4:** listwy przelotowe z długimi pinami (zestaw Adafruit 85), wkładane od góry. Lutuje się je od spodu z płytką odwróconą, nie na płytce DK, bo grot nie zmieści się między płytkami i stopiłby gniazda DK. Piny ustawia przyrząd: druga płytka nośna albo płytka uniwersalna nasunięta na długie piny. Najpierw jeden pin każdej listwy, przymiarka na DK, potem reszta.
6. **Od spodu w polu Arduino** przycina się wyprowadzenia elementów przewlekanych do ≤1,5 mm. Nie dotyczy to długich pinów J1–J4. Pod polem leży płytka DK.

Przyciski 12 × 12 mm dostają nasadki Omron B32. Pad masy J6.22 ma pełne połączenie z polem masy; lutuje się go grotem o większej pojemności cieplnej. Do płytek ekranu i FRAM lutuje się listwy męskie dołączone do zestawów Adafruit, pinami w dół. Ekran mocuje się czterema dystansami M2,5 (wysokość = gniazdo 8,5 mm + korpus listwy, zmierzyć na płytce), a FRAM dwoma.

## Kontrola przed zasilaniem

| Krok | Czynność | Warunek przejścia |
|---:|---|---|
| 1 | Oględziny: mostki, orientacja D1, D2, Q1, BZ1, SW5; brak opiłków między pinami 1,27 mm | brak usterek |
| 2 | Miernik bez modułów: rezystancja +3V3–GND, +5V–GND, +3V3_DEVKIT–GND, +5V_DEVKIT–GND (piny J1.4, J1.5, J5.1, J5.21 wobec J1.6) | żadnego zwarcia; bez modułów szyny są praktycznie rozwarte (kondensatory się ładują) |
| 3 | Ciągłość: J1.4 – JP3.1 i JP3.2 – J10.7, J10.9 (+3V3, +3V3_RF; między JP3.1 a JP3.2 bez zworki brak połączenia), J1.6 – J9.1, J9.19, J10.2 (GND); J3.4 – J9.16 (SCK przez R17); J2.2 – J9.14 (RF_CS); J3.8 – J10.15 (RF_RESET) | 0 Ω, a J3.4 – J9.16 około 33 Ω (R17); pozostałe piny J9/J10 nie mają połączenia z GND |
| 4 | Orientacja modułu CC1120EM, przed włożeniem: miernikiem na module, między obudową SMA (masa) a stykiem złącza P2 w rzędzie parzystym przy końcu od strony SMA | 0 Ω, bo to P2.2 (masa); ten koniec trafia na pin 2 J10, oznaczony przy złączu |
| 5 | Zworki: stanowisko A z JP3, bez JP1 i JP2; stanowisko B z JP1 i JP2 (bez JP1 ESP32 zasilałby moduły przez podciągnięcia i diody zabezpieczające wejść) | zgodnie ze stanowiskiem |

## Oprogramowanie

Kroki A3–A5 i B3–B4 wymagają obrazu z plikiem opisu płytki N1 (na przykład `board_bench_n1.h`) z poleceniami diagnostycznymi: stan wejść (przyciski, CISZA, przygotowanie), dioda, brzęczyk i odczyt VTEST. Dla stanowiska A jest to obraz środowiska `bench-n1` z plikiem `board_bench_n1.h`; polecenia diagnostyczne (`BTN`, `LED 5`, `BUZZ`, `VTEST`, `DISPLAY`) i przebieg kroków A3–A4 opisuje [firmware/README.md](../../firmware/README.md#płytka-nośna-n1-bench-n1). Dla stanowiska B jest to obraz środowiska `bench-b` z plikiem `board_bench_b.h`: ten sam program stacji z tymi samymi poleceniami panelu (`BTN`, `LED 5`, `BUZZ`, `VTEST`, `DISPLAY`) oraz `RADIO` z odczytem PARTNUM i VERSION S2-LP ([firmware/README.md](../../firmware/README.md#stanowisko-b-na-płytce-n1-bench-b)). Różnice między oprogramowaniem a płytką i lista potrzebnych zmian: [zgodność z oprogramowaniem](checks/zgodnosc-firmware.md).

**Nie wgrywać obrazu okablowania przewodami (`board_bench_a.h`) przy wpiętej płytce N1.** W tym obrazie D13 jest wyjściem SCK, a na N1 jest wejściem przełącznika CISZA, które przełącznik zwiera do masy. Do tego D10 i D8 sterują tam radiem, a na N1 diodą i linią DISP ekranu. Przed wpięciem DK w N1 wgrywa się obraz N1 albo pusty program.

## Stanowisko A

| Krok | Czynność | Warunek przejścia |
|---:|---|---|
| A1 | nRF52840-DK z wgranym obrazem N1 (instrukcja w [firmware](../../firmware/README.md#płytka-nośna-n1-bench-n1), środowisko `bench-n1`), zasilanie DK w ustawieniu fabrycznym (VDD z przetwornicy płytki, 3,0 V), wyłącznik SW8 włączony, przełącznik TRACE (SW7) w pozycji „Default”; przełączniki DK ustawia się przed nałożeniem płytki, bo potem są pod nią. Płytka nośna bez modułów na DK; lewa część płytki na dystansach M3 (H1, H2, H5) tak, by leżała poziomo | płytka nie naciska na części DK |
| A2 | Zasilanie z USB DK (J2 albo J3) przez miernik USB; pomiar J1.4 i J1.5 wobec masy | około 3,0 V i około 5 V; prąd bez modułów zgodny z samą płytką DK (wzrost < 20 mA) |
| A3 | Przyciski, CISZA, przycisk przygotowania, dioda i brzęczyk poleceniem diagnostycznym obrazu | każdy przycisk zmienia stan tylko swojej linii; brzęczyk słychać przy 2048 Hz |
| A4 | Wpięte FRAM i ekran | `FRAM` rozpoznaje układ; ekran pokazuje obraz, EXTCOMIN z MCU (EMD w stanie wysokim) |
| A5 | Wpięty CC1120EM (orientacja z kroku 4, złącze SMA nad kółkiem na opisie), amperomierz w miejscu JP3 przy pierwszym włączeniu | `RADIO` daje `partnumber: 0x48`; dalej kroki z [lekcji R02](../r02/lekcje.md#uruchomienie) i pomiary z README stanowiska |

## Stanowisko B

| Krok | Czynność | Warunek przejścia |
|---:|---|---|
| B1 | Płytka nośna na ośmiu dystansach M3. JP1 i JP2 założone, bez modułów | płytka stoi stabilnie; długie piny J1–J4 nie dotykają podłoża; śruby w otworach Arduino nie dotykają listew |
| B2 | ESP32-S3-DevKitC-1 (moduł N8, N8R2 albo N8R8), USB w stronę napisu USB na płytce, do komputera, amperomierz w miejscu JP1; pomiar J1.4 i J1.5 | około 3,3 V i około 4,7 V; prąd przez JP1 bez modułów < 5 mA (podciągnięcia) |
| B3 | Jak A3 i A4 | jak w A |
| B4 | X-NUCLEO-S2868A2 z fabrycznymi rezystorami, zworka JP1 na X-NUCLEO założona, wpięta w J1–J4 | `RADIO` obrazu `bench-b` daje `partnumber: 0x03`, `partversion` (rejestr wersji S2-LP) i stan `RX` (odbiór P1 od startu); `VERIFY` bez niezgodności |

## Czego płytka nie sprawdza

Płytka nośna nie zmienia toru RF, wzorca częstotliwości ani zasilania modułów producentów. Granice pomiarów stanowiska są w [README stanowiska](README.md#co-sprawdza-stanowisko-a-co-dopiero-r02).
