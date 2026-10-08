# WICI: zgodność płytki nośnej N1 z oprogramowaniem

Stan: 2026-10-07. Płytka N1 według `tools/design.py` (commit 562d689). Oprogramowanie: pierwsze sprawdzenie wobec `firmware/` w commicie a3b821f (tylko środowisko `bench-a`, plik `src/board_bench_a.h`); ponowne po dodaniu środowiska `bench-n1` z plikiem `src/board_bench_n1.h`; trzecie po dodaniu środowiska `bench-b` z plikiem `src/board_bench_b.h`; czwarte po przejściu `bench-b` na wspólny program stacji (`src/main.cpp`) z warstwą ESP32-S3 i sterownikiem łącza S2-LP; piąte po przeglądzie F83 (2026-10-08): zmiany płytki (kolejność pinów J7, położenie JP3, listwy J9/J10) nie dotyczą sygnałów MCU, a test `tests/test_board_netlist.py` sprawdza każdą stałą `board_bench_n1.h` i `board_bench_b.h` od listy połączeń KiCad przez niezależnie przepisane wyprowadzenia złączy DK i DevKitC.

**Wynik: stanowisko A na N1 ma obraz `bench-n1`, a stanowisko B obraz `bench-b`; oba są zgodne z płytką w każdym sygnale tabel niżej.** Obrazy się budują, ale nie były uruchomione na sprzęcie; ekran pracuje z 1 MHz do próby 2 MHz z analizatorem ([niżej](#do-sprawdzenia-na-sprzęcie)). Obraz `bench-a` zostaje dla okablowania przewodami i nadal nie nadaje się na N1. Obraz `bench-b` to ten sam program stacji co na A (polecenia, pomiary, łącze P1, dziennik, magazyn, protokół USB z dwoma CDC, ekran, panel) z S2-LP i ESP32-S3. Ustalenia wspólne dla obu wersji (rejestry radia, protokół, ekran) są zgodne.

## Przypisanie pinów nRF52840

| Sygnał | `board_bench_a.h` (przewody) | N1 | `bench-a` zgodne | `board_bench_n1.h` |
|---|---|---|---|---|
| SPI SCK | P1.15 (D13), domyślne `SPI` | P1.04 (D3) | nie | P1.04, własne `SPIClass` na SPIM2, H0H1 |
| SPI MOSI | P1.13 (D11) | P1.13 (D11) | tak | P1.13, H0H1 |
| SPI MISO | P1.14 (D12) | P1.14 (D12) | tak | P1.14 |
| CS radia | P1.12 (D10) | P0.04 (A1) | nie | P0.04 |
| RESET radia | P1.10 (D8) | P1.08 (D7), 10 kΩ do masy | nie | P1.08 |
| GPIO0 radia | P1.03 (D2) | P0.03 (A0) | nie | P0.03 |
| GPIO2 radia | P1.04 (D3) | P0.29 (A3) | nie | P0.29 |
| GPIO3 radia | — | P0.31 (A5) | brak w oprogramowaniu | P0.31, wejście nieużywane |
| CS FRAM | P1.11 (D9) | P1.11 (D9) | tak | P1.11 |
| CS ekranu | P1.05 (D4) | P1.05 (D4) | tak | P1.05 |
| EXTCOMIN | P1.06 (D5) | P1.07 (D6) | nie | P1.07, RTC2 |
| DISP ekranu | nie sterowany (podciągnięcie modułu) | P1.10 (D8), 2,2 kΩ do masy | nie: na N1 ekran jest wyłączony, dopóki program nie poda stanu wysokiego | P1.10: niski do CLEAR, potem wysoki |
| Przyciski GÓRA, DÓŁ, OK, WSTECZ | BUTTON1–4 płytki DK (P0.11, P0.12, P0.24, P0.25) | P1.01, P1.02, P0.26, P0.27 | nie (przyciski DK nadal działają, ale nie są panelem) | P1.01, P1.02, P0.26, P0.27, bez podciągnięcia wewnętrznego |
| CISZA | polecenie `SILENCE` | przełącznik, P1.15 (D13) przez 1 kΩ | brak w oprogramowaniu | P1.15 -> `bench.silence`; `SILENCE` zapasowo |
| Tryb przygotowania | polecenie `PREP` z potwierdzeniem przyciskiem OK | przycisk, P0.02 (AREF) | brak w oprogramowaniu | P0.02, przytrzymanie 3 s; `PREP` zapasowo |
| Dioda alarmu | — (diody DK LED1–4) | P1.12 (D10) | brak w oprogramowaniu | P1.12: do usunięcia przyczyny alarmu i w ciszy |
| Brzęczyk | — (oprogramowanie nie ma brzęczyka) | P1.03 (D2), 2048 Hz | brak w oprogramowaniu | P1.03, `tone()` 2048 Hz |
| VTEST | — | P0.30 (AIN6), VTEST_IN / 6 | brak w oprogramowaniu | P0.30 (AIN6), `VTEST` × 6 |

## Przypisanie pinów ESP32-S3

Kolumna N1 według [połączeń](../polaczenia.md) (J5/J6 = J1/J3 DevKitC). Test `tests/test_s2lp_p1_registers.py` (`BoardFileTests`) porównuje każdą z 22 sieci tabeli połączeń ze stałą w `board_bench_b.h`.

| Sygnał | N1 (złącze) | `board_bench_b.h` | Zgodne | Uwagi w obrazie |
|---|---|---|---|---|
| SPI SCK | GPIO12 (J5.18), 33 Ω (R18) | `SPI_SCK = 12` | tak | `SPIClass(FSPI)`, napęd `GPIO_DRIVE_CAP_0`, `DRIVE` do prób |
| SPI MOSI | GPIO11 (J5.17) | `SPI_MOSI = 11` | tak | napęd jak SCK |
| SPI MISO | GPIO13 (J5.19) | `SPI_MISO = 13` | tak | |
| CS radia (RF_CS) | GPIO10 (J5.16), 10 kΩ do 3,3 V | `RADIO_CS = 10` | tak | stan wysoki przed `bus.begin()` |
| SDN radia (RF_RESET) | GPIO9 (J5.15), 10 kΩ do masy | `RADIO_SDN = 9` | tak | stan wysoki = wyłączenie; po starcie 1 ms, potem niski i `SRES` |
| GPIO0 radia | GPIO14 (J5.20) | `RADIO_GPIO0 = 14` | tak | wejście; P1: nIRQ (do analizatora; program odpytuje IRQ_STATUS przez SPI) |
| GPIO1 radia | GPIO21 (J6.18) | `RADIO_GPIO1 = 21` | tak | wejście; S2-LP: wyjście masy |
| GPIO2 radia | GPIO4 (J5.4) | `RADIO_GPIO2 = 4` | tak | wejście; P1: wykryte słowo synchronizacji |
| GPIO3 radia | GPIO42 (J6.6) | `RADIO_GPIO3 = 42` | tak | wejście; S2-LP: wyjście masy |
| CS FRAM | GPIO8 (J5.12) | `FRAM_CS = 8` | tak | |
| CS ekranu | GPIO7 (J5.7), 10 kΩ do masy | `DISPLAY_CS = 7` | tak | aktywny stanem wysokim, niski od startu |
| EXTCOMIN | GPIO17 (J5.10) | `DISPLAY_EXTCOMIN = 17` | tak | MCPWM0, 1 Hz |
| DISP ekranu | GPIO16 (J5.9), 2,2 kΩ do masy | `DISPLAY_DISP = 16` | tak | niski do CLEAR, potem wysoki |
| GÓRA | GPIO41 (J6.7) | `BTN_UP = 41` | tak | bez podciągnięcia wewnętrznego |
| DÓŁ | GPIO40 (J6.8) | `BTN_DOWN = 40` | tak | |
| OK | GPIO39 (J6.9) | `BTN_OK = 39` | tak | |
| WSTECZ | GPIO2 (J6.5) | `BTN_BACK = 2` | tak | |
| CISZA | GPIO1 (J6.4) przez 1 kΩ | `SW_SILENCE = 1` | tak | masa = cisza |
| Tryb przygotowania | GPIO6 (J5.6) | `BTN_PREP = 6` | tak | przytrzymanie 3 s |
| Dioda alarmu | GPIO18 (J5.11) | `LED_ALARM = 18` | tak | aktywna stanem wysokim |
| Brzęczyk | GPIO15 (J5.8) | `BUZZER = 15` | tak | `tone()` 2048 Hz |
| VTEST | GPIO5 (J5.5, ADC1_CH4) | `VTEST = 5` | tak | `analogReadMilliVolts` × 6 |

Obraz nie steruje pinami konfiguracyjnymi (GPIO0, 3, 45, 46), USB (19, 20), UART0 (43, 44), diodą RGB ani pinami PSRAM i 1,8 V (35–37, 47, 48); płytka ich nie używa. USB idzie przez USB-OTG (TinyUSB, dwa interfejsy CDC) na złączu „USB” DevKitC; USB-Serial/JTAG jest wyłączony.

## Zgodne bez zmian

- Profil P1 ustawia IOCFG1 na wysoką impedancję (`src/p1_registers.h`), więc SO/GPIO1 CC1120 nie walczy z FRAM na wspólnej linii MISO.
- S2-LP ma osobny pin SDO, który przy CSn w stanie wysokim jest w stanie wysokiej impedancji (DS11896, rozdział 9.1), więc dzieli MISO z FRAM bez ustawień GPIO; jego GPIO0–3 idą na osobne wejścia ESP32-S3.
- CS ekranu jest aktywny stanem wysokim, a program ustawia go w stan niski przed uruchomieniem SPI. Zgadza się to z R13 na płytce.
- EXTCOMIN z licznika RTC2 przy EMD w stanie wysokim: N1 wiąże EMD z 3,3 V.
- Pozostałe ustawienia: SPI 1 MHz dla radia i FRAM, napięcia 3,0 V z płytki DK, dziennik w FRAM i polecenia pomiarowe nie zależą od przypisania pinów.

## Do sprawdzenia na sprzęcie

- Zegar ekranu. Na N1 SCK idzie przez P1.04 (pin, który Nordic zaleca do sygnałów wolnozmiennych ze względu na radio 2,4 GHz, tu nieużywane), przez 33 Ω (R17) i sieć długości około 265 mm, a 2 MHz to górna granica LS027B7DH01. Dlatego `bench-n1` taktuje ekran zegarem 1 MHz (`board::DISPLAY_SPI_HZ`; radio i FRAM też 1 MHz), z napędem H0H1 na SCK i MOSI, który ustawia `SPIClass::begin()` rdzenia. `DISPLAY 2000000` przełącza ekran na 2 MHz do restartu; przejście na 2 MHz na stałe dopiero po obejrzeniu zboczy SCK i MOSI analizatorem na J11 i obrazie bez błędów.
- Kroki A3–A5 [uruchomienia](../uruchomienie.md#stanowisko-a) z poleceniami `BTN`, `LED 5`, `BUZZ`, `VTEST` i `DISPLAY` ([firmware/README.md](../../../firmware/README.md#płytka-nośna-n1-bench-n1)).
- Stanowisko B: zbocza SCK i MOSI ESP32-S3 przy najniższym napędzie (`DRIVE 0`) na J11, przy 1 i 2 MHz; wyższy napęd tylko wtedy, gdy zbocza nie są czyste. Kroki B3–B4 [uruchomienia](../uruchomienie.md#stanowisko-b): `RADIO` z `partnumber: 0x03` i stanem `RX`, `VERIFY` bez niezgodności, dwa porty szeregowe w systemie ([firmware/README.md](../../../firmware/README.md#stanowisko-b-na-płytce-n1-bench-b)).

## Obraz okablowania przewodami na N1

Uruchomienie `bench-a` na wpiętej płytce N1 jest elektrycznie bezpieczne, ale nie działa. SCK na P1.15 trafia przez R16 (1 kΩ) na przełącznik CISZA; przy ciszy płynie 3 mA. CS radia steruje diodą alarmu, a RESET radia linią DISP. CC1120 zostaje w resecie (R12), a ekran nie dostaje EXTCOMIN. Procedura uruchomienia i tak zakazuje tego obrazu na N1 ([uruchomienie](../uruchomienie.md#oprogramowanie)).

## Potrzebne w oprogramowaniu

Punkty 1–5 wykonane w środowisku `bench-n1` (opis w [firmware/README.md](../../../firmware/README.md#płytka-nośna-n1-bench-n1)), punkt 6 w środowisku `bench-b` ([opis](../../../firmware/README.md#stanowisko-b-na-płytce-n1-bench-b)).

1. Plik `src/board_bench_n1.h` i środowisko PlatformIO (na przykład `bench-n1` z `-DWICI_BENCH_N1`), wybierane zamiast `board_bench_a.h`. Przypisania z tabeli wyżej i z [połączeń](../polaczenia.md).
2. Własna instancja `SPIClass` (rdzeń Adafruit: SPIM z pinami MISO P1.14, SCK P1.04, MOSI P1.13) zamiast domyślnego `SPI` z wariantu PCA10056 oraz napęd H0H1 na SCK i MOSI.
3. DISP: stan niski do wyczyszczenia pamięci ekranu, potem wysoki.
4. Wejścia: przełącznik CISZA ustawia `bench.silence`, a przycisk przygotowania wybiera tryb przygotowania zamiast polecenia `PREP`. Polecenia USB mogą zostać jako zapasowe.
5. Dioda alarmu i brzęczyk (2048 Hz z PWM albo z licznika) dla ekranu alarmu oraz polecenia diagnostyczne do kroków A3–A4 uruchomienia (stan wejść, `BUZZ`, `LED`, `VTEST`).
6. Stanowisko B: program na ESP32-S3-DevKitC-1 (SPI na GPIO12/11/13, CS S2-LP GPIO10, SDN GPIO9) co najmniej do odczytu rejestru wersji S2-LP (krok B4). Wykonane: plik `src/board_bench_b.h`, środowisko `bench-b`, sterownik S2-LP z odczytem PARTNUM i VERSION, zapis rejestrów P1 i sterownik łącza P1, polecenia panelu, FRAM, ekran z EXTCOMIN z MCPWM; program stacji wspólny z A.
