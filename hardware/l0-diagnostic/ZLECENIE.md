# WICI L0: zlecenie montażu i uruchomienia prototypu

Brief dla wykonawcy. WICI to otwarty projekt stacji łączności awaryjnej LoRa 868 MHz (https://github.com/tmierzwa/WICI). L0 to biurkowy prototyp zasilany z USB, którym sprawdzamy współpracę procesora, radia, ekranu, pamięci i panelu. Zlecenie obejmuje jedną sztukę; drugą (komplet części jest) proszę wycenić jako opcję.

## Co dostarczam

- Płytka nośna N1 (170 × 100 mm) z fabrycznie zmontowanymi 44 elementami SMD (JLCPCB).
- Elementy przewlekane według [BOM](../dev-bench/bom.csv), bez J1–J4, J9/J10 i JP3 (wyjaśnienie w punkcie 1).
- ESP32-S3-DevKitC-1-N8R8, panel Sharp LS027B7DH01A (szkło, taśma FPC) i taśma 3M 4032.
- Dwa nowe zestawy Seeed 102010611 (XIAO ESP32S3 + Wio SX1262 z anteną): Wio z jednego idzie do L0, drugi zestaw z programem R0 `pair-0.4` jest partnerem radiowym do prób. Przed rozebraniem oba sprawdza się wzajemnie próbą 100 pakietów (instrukcja, rozdział 2).
- Program diagnostyczny L0 `l0-0.5` z narzędziami i instrukcją prób ([README](README.md)); oprogramowanie jest gotowe, jego tworzenie jest poza zakresem.

Drobne materiały (R12 1 kΩ 0805, 10 kΩ, 100 nF, 10 µF, listwy goldpin, przewody, płytka uniwersalna) zapewnia wykonawca w ramach wyceny, chyba że ustalimy inaczej.

## Zakres prac

Szczegóły montażu, diagnozy i prób: [instrukcja montażu i prób](MONTAZ-I-TESTY.md).

1. **Montaż przewlekany** na N1 (instrukcja, rozdziały 0 i 1):
    - przed lutowaniem przymiarka DevKitC w J5/J6 i panelu w obrysie na opisie płytki;
    - gniazda DevKitC J5/J6, przyciski SW1–SW6, przełącznik CISZA, LED, brzęczyk, J11, J12, JP1 i JP2; JP1 i JP2 zwarte;
    - **nie obsadzać J1–J4, J9/J10 i JP3.** N1 służy też dwóm innym stanowiskom: J1–J4 to gniazda Arduino pod nRF52840-DK i nakładkę X-NUCLEO, J9/J10 i JP3 przyjmują i zasilają moduł CC1120EM. L0 ich nie używa, a J9/J10 leżą na tych samych sieciach co Wio (RF_CS, RF_RESET, SPI), więc wpięty tam moduł kłóciłby się z Wio na magistrali;
    - podstawa: dystanse M3 × 12 mm z gwintem od spodu przez płytkę i nakrętką od góry. W otworach H6–H9 tylko nakrętki nylonowe albo bez dystansu: pady nieobsadzonych J1–J4 są połączone z sieciami, a środek H7 leży 3,6 mm od padu J4.10;
    - DevKitC bez przeróbek.
2. **R12: wymiana 10 kΩ na 1 kΩ** (1%, 0805). Bez tego reset radia przy starcie nie schodzi do stanu niskiego.
3. **Adapter Wio** (moduł obok N1, krótkie przewody albo mała płytka uniwersalna):
    - XIAO odłączony od Wio (złącze B2B); Wio J2.1 (VIN) niepodłączone;
    - zasilanie Wio J2.3 (+3V3) z JP1 pad 1 przez rozłączany punkt pomiaru prądu (zworka albo listwa na amperomierz), Wio J2.2 (GND) z J11.1;
    - przy Wio 100 nF i 10 µF na 3,3 V oraz 10 kΩ z RXEN (Wio J1.5) do masy;
    - sygnały według tabeli niżej i [polaczenia-MCU-L0.csv](reference/polaczenia-MCU-L0.csv); bez długich odgałęzień SPI, bo magistrala jest wspólna z ekranem i FRAM;
    - antena założona przed pierwszym uruchomieniem radia.
4. **Ekran:** taśma FPC w J7, panel ekranem do góry. Panel przykleić taśmą 3M 4032 dopiero po poprawnym teście ekranu, a nie od razu jak w kroku 7 uruchomienia N1; klej nie pozwala go potem zdjąć bez ryzyka pęknięcia szkła. Punkty pomiarowe muszą zostać dostępne.
5. **Kontrola przed zasilaniem** (instrukcja, rozdział 3): oględziny pod lupą (zwłaszcza mostki na J7, raster 0,5 mm), zwarcia szyn, ciągłość połączeń Wio.
6. **Wgranie programu i próby**, zasilanie wyłącznie z portu USB/OTG DevKitC, E1–E6, R1–R3 (instrukcja, rozdziały 4 i 5; polecenia w [instrukcji programu L0](README.md#kolejność-prób-po-montażu)): start i zasilanie, pełny test FRAM z retencją, ochrona FRAM przy zaniku zasilania (oscyloskop), ekran i panel, 15 minut wspólnego SPI, 100 pakietów radiowych w obie strony, blokada CISZA.
7. **Raport:** wynik każdej próby, zmierzone napięcia i prądy (spoczynek, RX, TX), zrzuty oscyloskopu (ochrona FRAM, EXTCOMIN), logi USB i pliki JSON z `results/`, zdjęcia montażu, lista rzeczy nieukończonych.

### Połączenia Wio

| Sygnał | Wio | GPIO DevKitC | Sieć N1 (pin) |
|---|---|---:|---|
| SCK | J2.6 | 12 | SPI_SCK_DEVKIT (J5.18) |
| MOSI | J2.4 | 11 | SPI_MOSI (J5.17) |
| MISO | J2.5 | 13 | SPI_MISO (J5.19) |
| NSS | J1.4 | 10 | RF_CS (J5.16) |
| RESET | J1.3 | 9 | RF_RESET (J5.15) |
| BUSY | J1.2 | 14 | RF_GPIO0 (J5.20) |
| DIO1 | J1.1 | 21 | RF_GPIO1 (J6.18) |
| RXEN | J1.5 | 42 | RF_GPIO3 (J6.6), 10 kΩ do masy przy Wio |
| 3,3 V | J2.3 | | JP1 pad 1 przez punkt pomiaru prądu |
| masa | J2.2 | | J11.1 |
| VIN | J2.1 | | nie podłączać |

## Wymagany sprzęt wykonawcy

- Stacja lutownicza z cienkim grotem i grotem o większej pojemności cieplnej (pady masy), topnik, plecionka.
- Lupa ≥10× albo mikroskop do oględzin J7.
- Multimetr, amperomierz z zakresem ≥200 mA i miernik prądu USB.
- Oscyloskop ≥3 kanały, ≥50 MHz, sondy x10 (próba zaniku zasilania: 3,3 V, CS FRAM za bramką na U1.1, GUARD).
- Komputer z Pythonem 3 i dwoma portami USB (program L0 i partner R0 na jednym hoście; instrukcja podaje nazwy portów macOS, na Linuksie działa analogicznie), przewód micro-USB z transmisją danych.

## Poza zakresem

Zasilanie AA/12 V, kalibracja VTEST, obudowa docelowa, próby terenowe, aplikacja WICI, zmiany w oprogramowaniu i certyfikacja.

## Prośba o wycenę

Proszę osobno podać montaż (punkty 1–5) oraz uruchomienie z próbami i raportem (6–7), termin realizacji i warunki przekazania sprzętu (osobiście albo wysyłka). Druga sztuka jako opcja. Pytania techniczne przed wyceną są mile widziane. Pełny zakres prób: [zakres prototypu L0](../../output/pdf/WICI-L0-zakres-prototypu.pdf).
