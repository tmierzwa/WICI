# WICI: Obrazy stanowisk deweloperskich A i B (wstrzymane)

Część opisu oprogramowania stacji; spis części jest w [README](../README.md).

Katalog zawiera oprogramowanie układowe stacji. Opisy stanowisk A i B oraz profilu P1 niżej dotyczą obrazów `bench-*`: to obrazy wstrzymanego wariantu (własny profil P1, stanowiska deweloperskie; F99, 2026-10-08), zostają w repozytorium bez zmian i nie są ścieżką pilotażu ([archiwum](../../docs/archiwum/README.md)). Opis zaczyna się od wariantu na [stanowisku deweloperskim A](../../hardware/dev-bench/README.md): nRF52840-DK z modułem TI CC1120EM-868-915 i pamięcią FRAM na złączu Arduino płytki. Środowisko `bench-a` w `platformio.ini` buduje obraz, który po podłączeniu USB zgłasza się na polecenie `INFO` w formacie ze [specyfikacji radia](../../docs/spec/radio.md#usb-do-laptopa) i rozpoznaje przez SPI układ radiowy i FRAM. Obraz zapisuje do CC1120 [rejestry profilu P1](#rejestry-profilu-p1) z weryfikacją odczytu i kalibracją syntezera oraz wykonuje [polecenia pomiarowe](polecenia.md#polecenia-pomiarowe) `TXCW`, `TXPKT`, `RXPER`, `FOFF` ze specyfikacji. Prowadzi [dziennik i magazyny w FRAM](aplikacja.md#dziennik-i-magazyny-w-fram): dług ciszy, licznik czasu pracy i zdarzenia, a także rejestr zgłoszeń, skrzynkę, pierścień zdarzeń i konfigurację z transakcjami. Obsługuje [łącze P1](#łącze-p1) (odbiór i składanie datagramów, nadawanie z CCA, odroczeniem i długiem ciszy) i podaje zaprogramowaną częstotliwość oraz RSSI. Na przyciskach płytki działa [ekran Sharp i menu stacji](aplikacja.md#ekran-i-przyciski): wybór języka, ekran główny, cisza, STAN; EXTCOMIN pochodzi z licznika RTC2.

Obraz obsługuje diody płytki i udostępnia drugi interfejs CDC z [protokołem USB laptop–stacja](aplikacja.md#protokół-usb-laptopstacja) (`"usb":2`) oraz [warstwę aplikacji](aplikacja.md#warstwa-aplikacji-nad-stosem) z cyklem życia zgłoszenia, wysyłką z rejestru i wiadomościami odbiorcy do skrzynki.

Środowisko `bench-n1` buduje ten sam obraz dla stanowiska A na [płytce nośnej N1](#płytka-nośna-n1-bench-n1) zamiast przewodów: inne piny SPI, radia i ekranu oraz panel płytki (przełącznik CISZA, przycisk przygotowania, dioda alarmu, brzęczyk, VTEST).

Środowisko `bench-b` buduje ten sam program stacji dla [stanowiska B na N1](#stanowisko-b-na-płytce-n1-bench-b): ESP32-S3-DevKitC-1 z X-NUCLEO-S2868A2 (ST S2-LP) zamiast nRF52840 i CC1120. Wspólne są polecenia, polecenia pomiarowe, łącze P1, dziennik, magazyn, protokół USB laptop–stacja z dwoma interfejsami CDC, warstwa aplikacji, ekran i panel N1; różnią się warstwa MCU (`src/platform_*.cpp`), sterownik układu radiowego (`src/radio_console_*.cpp`, `src/*_link.cpp`) i [rejestry P1 dla S2-LP](#rejestry-profilu-p1-dla-s2-lp).

## Okablowanie stanowiska A

Numery pinów są w `src/board_bench_a.h`. Płytka DK pracuje domyślnie z VDD = 3,0 V, co mieści się w zakresie CC1120 (2,0–3,6 V) i FRAM; moduł zasila się z pinu VDD płytki, nie z 5 V. Złącza EM są na spodzie modułu, a widok od spodu odwraca obraz: przed włączeniem sprawdzić każdą żyłę miernikiem.

| Sygnał | Złącze Arduino DK | GPIO nRF52840 | Moduł CC1120EM | FRAM Adafruit 4719 | Ekran Adafruit 4694 |
|---|---|---|---|---|---|
| SCK | D13 | P1.15 | P1.16 | SCK | CLK |
| MOSI | D11 | P1.13 | P1.18 | MOSI | DI |
| MISO | D12 | P1.14 | P1.20 | MISO | |
| CSn radia | D10 | P1.12 | P1.14 | | |
| RESET_N radia | D8 | P1.10 | P2.15 | | |
| GPIO0 radia | D2 | P1.03 | P1.10 | | |
| GPIO2 radia | D3 | P1.04 | P1.12 | | |
| CS FRAM | D9 | P1.11 | | CS | |
| CS ekranu (aktywny stanem wysokim) | D4 | P1.05 | | | CS |
| EXTCOMIN ekranu (1 Hz z RTC2) | D5 | P1.06 | | | EXTCOMIN |
| 3,0 V | VDD | | P2.7 (P2.9 to ten sam węzeł) | VIN | VIN |
| GND | GND | | P1.1, P1.19, P2.2 | GND | GND |
| EMD ekranu (EXTMODE, stan wysoki) | VDD | | | | EMD |

Ekran ma na płytce przetwornicę 5 V i translację poziomów, więc VIN idzie z VDD płytki (3,0 V). Płytka 4694 nie ma zworki EXTMODE: pin EMD złącza (EXTMODE ekranu) jest ściągnięty na płytce 10 kΩ do masy, a VCOM z pinu EXTCOMIN (EIN) działa dopiero przy EMD w stanie wysokim. Dlatego EMD łączy się przewodem z VDD (N1 ma goły panel z EXTMODE na stałe w stanie wysokim). Kolejność pinów złącza według projektu Adafruit (JP1.1–JP1.9): VIN, 3V3, GND, CLK, DI, CS, EMD, DISP, EIN. Bez przewodu EMD `VCOM 1` przełącza odwracanie VCOM na bit w poleceniach ekranu.

Przyciski płytki: BUTTON1 = GÓRA, BUTTON2 = DÓŁ, BUTTON3 = OK, BUTTON4 = WSTECZ (menu stacji, patrz [Ekran i przyciski](aplikacja.md#ekran-i-przyciski)). Diody: LED1 bicie serca (0,5 s), LED2 radio rozpoznane, LED3 FRAM rozpoznana i dziennik uruchomiony, LED4 port USB otwarty przez hosta. Przewody do 5 cm; SPI pracuje z 1 MHz.

## Płytka nośna N1 (bench-n1)

Opis płytki i przypisanie sygnałów: [płytka nośna](../../hardware/dev-bench/plytka-nosna.md#przypisanie-sygnałów), połączenia pin po pinie: [połączenia](../../hardware/dev-bench/polaczenia.md). Numery pinów są w `src/board_bench_n1.h`, wybieranym flagą `-DWICI_BENCH_N1` środowiska `bench-n1`; reszta kodu jest wspólna z `bench-a`. **Obrazu `bench-a` nie wgrywa się na DK wpiętą w N1** ([uruchomienie](../../hardware/dev-bench/uruchomienie.md#oprogramowanie)): jego SCK na D13 trafia na przełącznik CISZA, a CS i RESET radia na diodę alarmu i DISP ekranu.

| Sygnał | Przewody (`bench-a`) | N1 (`bench-n1`) |
|---|---|---|
| SPI SCK / MOSI / MISO | P1.15 / P1.13 / P1.14, domyślne `SPI` (SPIM3) | P1.04 (D3) / P1.13 / P1.14, własne `SPIClass` na SPIM2 |
| CS / RESET_N radia | P1.12 / P1.10 | P0.04 (A1), 10 kΩ do 3,3 V / P1.08 (D7), 10 kΩ do masy |
| GPIO0 / GPIO2 / GPIO3 radia | P1.03 / P1.04 / — | P0.03 (A0) / P0.29 (A3) / P0.31 (A5, wejście nieużywane) |
| CS FRAM, CS ekranu | P1.11, P1.05 | bez zmian |
| EXTCOMIN / DISP ekranu | P1.06 / nie sterowany | P1.07 (D6) / P1.10 (D8) |
| GÓRA, DÓŁ, OK, WSTECZ | BUTTON1–4 płytki DK, podciągnięcie wewnętrzne | P1.01, P1.02, P0.26, P0.27, podciągnięcie na płytce |
| CISZA / przygotowanie | polecenia `SILENCE` / `PREP` | przełącznik P1.15 (D13) / przycisk P0.02 (AREF); polecenia zostają jako zapasowe |
| Dioda alarmu / brzęczyk / VTEST | — | P1.12 (D10) / P1.03 (D2), 2048 Hz / P0.30 (AIN6) |

Diody LED1–4 płytki DK zachowują swoje role. Ustalenia dla N1:

- **SPI:** SPIM2 z pinami MISO P1.14, SCK P1.04, MOSI P1.13. `SPIClass::begin()` rdzenia ustawia napęd H0H1 na SCK i MOSI. Domyślne `SPI` (SCK na D13) nie jest uruchamiane. Radio pracuje z 1 MHz jak na przewodach, FRAM z **8 MHz** (`board::FRAM_SPI_HZ`). Specyfikacja wymaga ≥8 MHz w każdej stacji, a 8 MHz to górna granica SPIM2. Ekran pracuje z **1 MHz**, a nie z 2 MHz, z trzech powodów:
  - sieć SCK ma około 300 mm z odgałęzieniami i 33 Ω szeregowo,
  - Nordic zaleca pin P1.04 tylko do sygnałów wolnozmiennych (ochrona radia 2,4 GHz, tu nieużywanego),
  - 2 MHz to granica LS027B7DH01.

  Do pomiaru oscyloskopem przy J7 ([uruchomienie N1](../../hardware/dev-bench/uruchomienie.md#pomiar-magistrali-oscyloskopem)) `DISPLAY 2000000` przełącza ekran na 2 MHz do restartu i przerysowuje cały obraz. Przesłanie pełnego obrazu (240 wierszy po 52 B: adres, 50 B danych i odstęp) trwa przy 1 MHz 100 ms, a zwykle zmienia się tylko kilka wierszy.
- **Ekran:** DISP w stanie niskim od startu (2,2 kΩ do masy na płytce), stan wysoki dopiero po poleceniu CLEAR w `display.begin()`.
- **CISZA:** przełącznik działa na zmianę położenia po 50 ms stałego stanu; położenie przy starcie ustawia ciszę od razu. Zmiana trafia do dziennika (`silence on (switch)`) i jako zdarzenie `radio` do laptopa. Przełącznik ma pierwszeństwo ([specyfikacja](../../docs/spec/oprogramowanie.md), „Cisza radiowa”): w położeniu „cisza” ani `SILENCE 0`, ani `silence` z laptopa nie wyłącza ciszy (`silence switch on`, `rejected` z `silence switch`). Włączenie ciszy z portu USB przy przełączniku w położeniu „praca” obowiązuje do następnego przełączenia.
- **Tryb przygotowania:** przytrzymanie przycisku przygotowania przez 3 s przełącza tryb (włącza albo wyłącza; wyłączenie przerywa pomiary jak `PREP 0`), z krótkim sygnałem. Przycisk wciśnięty przy starcie nie przełącza trybu. `PREP` z potwierdzeniem OK zostaje jako zapasowe.
- **Dioda alarmu** (według [zasad alarmów](../../docs/spec/oprogramowanie.md), `src/annunciator.cpp`): miga krótkimi błyskami (50 ms co 5 s, 1% czasu jak w modelu energii), dopóki są nieprzeczytane wiadomości, trwa przyczyna alarmu (także po potwierdzeniu OK) albo cisza radiowa. Błysk trwa co najmniej 50 ms także przy wolnym obiegu pętli. Przyczyną alarmu jest zgłoszenie po progu bez potwierdzenia od odbiorcy albo pilność 2 bez odczytu, niezależnie od potwierdzenia OK. `Station::alarmCause` sprawdza ją co sekundę. Dioda gaśnie, gdy przyjdzie potwierdzenie albo odczyt albo gdy zgłoszenie zostanie anulowane lub zastąpione.
- **Brzęczyk** gra 2048 Hz z `tone()` na PWM2 (stały stan wysoki pobierałby około 75 mA z 5 V). Na ekranie alarmu daje 200 ms co 2 s aż do potwierdzenia OK. Nowa wiadomość (przyrost nieprzeczytanych) daje 100 ms, chyba że gospodarz wybrał WYCISZ DŹWIĘK. Ta opcja nie wycisza alarmów. Za wiadomości sprzed startu nie ma sygnału. Cisza radiowa nie daje sygnału, także przy włączeniu. Zostają tekst na ekranie i dioda. Przypomnienie `wymien_ogniwa` co 15 min przyjdzie z pomiarem ogniw (tor zasilania z ogniw ma dopiero płytka v2).

Polecenia diagnostyczne do kroków A3–A4 [uruchomienia](../../hardware/dev-bench/uruchomienie.md#stanowisko-a) (tylko `bench-n1`):

| Polecenie | Odpowiedź |
|---|---|
| `BTN` | cztery przyciski oraz `silence_switch` i `prep_button` (true = linia zwarta do masy), stan `silence` i `prep`, `alarm_led` |
| `LED 5 <0\|1>` | dioda alarmu; obowiązuje (bez migania) do następnej zmiany powodu migania: alarm, cisza, nieprzeczytane |
| `BUZZ [<ms>] [<hz>]` | brzęczyk przez `ms` (domyślnie 500, do 5000; 0 przerywa) z częstotliwością `hz` (100–10 000, domyślnie 2048) |
| `VTEST` | `vtest_mv` (napięcie na zacisku J12 = napięcie pinu × 6), `pin_mv`, `raw`: średnia 16 próbek SAADC, 12 bitów, pełna skala 3,6 V; `ain` i `divider` (6) |
| `DISPLAY <hz>` | zegar SPI ekranu 125 000–2 000 000 Hz do restartu, potem odpowiedź jak `DISPLAY` z polem `spi_hz` |

Przebieg A3:

- `BTN` bez naciśnięć daje same `false` (przy CISZA w położeniu „cisza” `silence_switch: true`), a każde naciśnięcie zmienia tylko swoje pole.
- `LED 5 1`, `LED 5 0`.
- `BUZZ` daje słyszalny sygnał 2048 Hz.

Przebieg A4: `FRAM` z `ok: true` i nazwą układu. Ekran pokazuje wybór języka, a kolejne `DISPLAY` pokazują `counter` RTC2 rosnący od 0 do 4 i `level` (EXTCOMIN) zmieniający się co 0,5 s. `VTEST` przy zacisku J12 zwartym daje około 0 mV, a przy 12 V z zasilacza około 12 000 mV. Wynik sprawdzić miernikiem. Dokładność zależy od rezystorów 1% i wewnętrznego odniesienia SAADC.

Budowa i wgranie (bootloader jak niżej):

```bash
cd firmware && ../.venv-pio/bin/pio run -e bench-n1
```

```bash
cd firmware && ../.venv-pio/bin/pio run -e bench-n1 -t upload
```

## Stanowisko B na płytce N1 (bench-b)

Opis płytki: [płytka nośna](../../hardware/dev-bench/plytka-nosna.md#przypisanie-sygnałów) (kolumna ESP32-S3) i [połączenia](../../hardware/dev-bench/polaczenia.md) (J5/J6 to złącza J1/J3 DevKitC). Numery pinów są w `src/board_bench_b.h`. Program to ten sam `src/main.cpp` co na stanowisku A; środowisko `bench-b` pomija sterowniki CC1120 (`cc1120.cpp`, `cc1120_link.cpp`, `radio_console_cc1120.cpp`). Moduł ESP32-S3: N8, N8R2 albo N8R8 (ESP32-S3-WROOM-1, pamięć flash quad SPI); obraz zakłada 8 MB flash w trybie QIO i nie używa PSRAM, więc piny PSRAM ośmiobitowej zostają wolne. Moduły WROOM-2 z pamięcią flash ośmiobitową i 1,8 V (np. N16R8V, N32R8V) wymagają innego trybu pamięci w `platformio.ini` (`opi_opi`) i nie zostały sprawdzone.

| Sygnał | GPIO ESP32-S3 | Uwagi |
|---|---|---|
| SPI SCK / MOSI / MISO | 12 / 11 / 13 | piny IO_MUX FSPI, kontroler SPI2 (`SPIClass(FSPI)`); SCK przez 33 Ω (R18); 1 MHz dla radia i ekranu, 8 MHz dla FRAM |
| CSn / SDN S2-LP | 10 / 9 | SDN: stan wysoki wyłącza układ (10 kΩ do masy na płytce) |
| GPIO0 / GPIO1 / GPIO2 / GPIO3 S2-LP | 14 / 21 / 4 / 42 | wejścia; GPIO0 = nIRQ, GPIO2 = słowo synchronizacji (oba na J11), stan w odpowiedzi `RADIO` |
| CS FRAM | 8 | |
| CS / EXTCOMIN / DISP ekranu | 7 / 17 / 16 | CS aktywny stanem wysokim; EXTCOMIN 1 Hz z MCPWM0; DISP niski do CLEAR, potem wysoki |
| GÓRA, DÓŁ, OK, WSTECZ | 41, 40, 39, 2 | podciągnięcie na płytce (OK i WSTECZ także 2,2 kΩ na X-NUCLEO) |
| CISZA / przygotowanie | 1 / 6 | jak w `bench-n1` |
| Dioda alarmu / brzęczyk | 18 / 15 | brzęczyk 2048 Hz z `tone()` (LEDC) |
| VTEST | 5 (ADC1_CH4) | VTEST_IN / 6; `VTEST` podaje `adc` (`ADC1_CH4`) zamiast `raw` i `ain` |

Różnice wobec stanowiska A:

- **USB.** Złącze „USB” DevKitC (USB-OTG ESP32-S3, GPIO19/20), nie „UART”. Arduino-ESP32 3.3.12 z TinyUSB daje dwa interfejsy CDC ACM z IAD jak na A: pierwszy to diagnostyka (polecenia), drugi dane ([protokół laptop–stacja](aplikacja.md#protokół-usb-laptopstacja)). Nazwy interfejsów ustala rdzeń („TinyUSB CDC” i „TinyUSB CDC2”), a urządzenie zgłasza się jako „WICI bench-b” z VID/PID Espressif (testowe, do przydziału przed wydaniem). USB-Serial/JTAG jest wyłączony (`ARDUINO_USB_MODE=0`). Wgrywanie przez ten sam port: PlatformIO otwiera port z prędkością 1200 b/s, program restartuje się do bootloadera ROM i esptool wgrywa obraz; gdy program nie działa, BOOT przytrzymany przy wciśnięciu RESET.
- **Radio.** Sterownik `src/s2lp.cpp` (karta [DS11896](https://www.st.com/resource/en/datasheet/s2-lp.pdf), rozdziały 6 i 9.1): SPI w trybie 0, nagłówek 0x00 zapis, 0x01 odczyt, 0x80 polecenie; w czasie dwóch pierwszych bajtów układ wysyła MC_STATE1 i MC_STATE0 (stan głównego sterownika i XO_ON). Po starcie SDN na 1 ms, `SRES`, odczyt PARTNUM (0xF0) i VERSION (0xF1), zapis tablicy P1 z weryfikacją, potem odbiór P1. Łącze P1 i polecenia pomiarowe idą przez [`src/s2lp_link.cpp`](#sterownik-łącza-s2-lp).
- **SPI i napęd.** SCK i MOSI startują z najniższym napędem ESP32-S3 (`GPIO_DRIVE_CAP_0`, około 5 mA): sieć SCK ma około 300 mm z odgałęzieniami, a 33 Ω (R18) tłumi odbicia na rozgałęzionej sieci; panel Sharp wymaga zboczy SCLK nie dłuższych niż 50 ns, więc zboczy nie wolno nadmiernie spowalniać. `DRIVE <0-3>` zmienia napęd do restartu; wybór na stałe po obejrzeniu zboczy analizatorem na J11 (najniższy napęd, przy którym zbocza są czyste przy 1 i 2 MHz).
- **EXTCOMIN** generuje timer jednostki MCPWM0 (sterownik MCPWM z ESP-IDF 5: licznik 10 kHz, okres 10 000 taktów, stan wysoki do porównania 5000) bez udziału programu, jak RTC2 na nRF52840; gdy sterownik MCPWM zwróci błąd, panel zostaje wyłączony (DISP w stanie niskim), dziennik dostaje wpis `display off: EXTCOMIN timer failed`, a `DISPLAY` podaje `extcomin_ok: false`. Bitu VCOM w poleceniach nie używa się zamiast licznika, bo EXTMODE panelu na N1 jest na stałe w stanie wysokim i panel ten bit pomija (F103). LEDC z kwarcu 40 MHz nie schodzi poniżej około 2,4 Hz (dzielnik do 1024, licznik do 14 bitów), a z wewnętrznego RC_FAST ledwie do 1 Hz i z niedokładnym zegarem, dlatego MCPWM. Kod EXTCOMIN jest w `src/sharp_extcomin_nrf.cpp` (RTC2, PPI, GPIOTE) i `src/sharp_extcomin_esp32.cpp`; reszta `src/sharp.cpp` nie zależy od MCU.
- **Warstwa MCU** (`src/platform_esp32.cpp`):
  - nazwa `WICI-xxxxxx` z adresu MAC w eFuse, gdy stos Reticulum nie wystartował (zwykle, jak na A, nazwa ze skrótu tożsamości i adres celu stacji),
  - `reset_reason` z `esp_reset_reason()`,
  - watchdog zadań (TWDT, 60 s) na zadaniu pętli,
  - pamięć niezerowana `RTC_NOINIT_ATTR` (język i ekran po restarcie programowym),
  - pętla stacji w zadaniu `loop()` rdzenia z 16 KB stosu,
  - identyfikator datagramu z `esp_fill_random`; przy wyłączonym Wi-Fi i Bluetooth źródło szumu jest słabsze i karta ESP32-S3 zaleca wtedy dodatkowe źródło,
  - VTEST z `analogReadMilliVolts` (tłumienie 11 dB, kalibracja z eFuse).
- **Brak diod stanu** LED1–LED4 (DevKitC ma tylko diodę RGB, nieużywaną): `LED 1-4` zwraca błąd, a czekanie na potwierdzenie OK nie miga diodą; dioda alarmu N1 działa jak w `bench-n1`.

Polecenia są jak na [stanowisku A](polecenia.md#polecenia) i [N1](#płytka-nośna-n1-bench-n1) (`LED 5`, `BUZZ`, `VTEST`, `DISPLAY <hz>`), z różnicami układu radiowego i MCU:

| Polecenie | Odpowiedź na B |
|---|---|
| `INFO` | jak na A, z `radio: "S2LP"`, `mcu: "ESP32-S3"`, `bench: "B"`, `board: "N1"`, `rx_filter_hz` S2-LP (25 481) i `reset_reason` jako kod `esp_reset_reason()` |
| `RADIO` | `partnumber` (S2-LP = `0x03`), `partversion` i `cut` (`0x81` = 2.0, `0x91` = 2.1, `0xC1` = 3.0), `mc_state1`, `mc_state0`, `state` (`READY`, `STANDBY`, `SLEEP_A/B`, `LOCK`, `RX`, `TX`, `SYNTH_SETUP` albo `INVALID`), `xo_on`, `sdn`, stany GPIO0–3, `irq_seen` (wszystkie przerwania od startu), `p1_ok`, `ok` (= `partnumber` 0x03) |
| `RESET` | SDN na 1 ms i `SRES` (rejestry wracają do wartości domyślnych, `p1_ok: false`), potem `RADIO` |
| `SDN <0\|1>` | wyłączenie (1) i włączenie (0) S2-LP pinem SDN; wyłączenie kasuje rejestry |
| `CONFIG` / `VERIFY` | zapis tablicy P1 w stanie READY i porównanie odczytem / samo porównanie; `CONFIG` zapisuje potem `FOFF`; bez `CAL` (S2-LP kalibruje VCO sam przy każdym przejściu do LOCK) |
| `FREQ` | słowo SYNT, dzielnik pasma, częstotliwość z równania 7 karty (z korektą `FOFF`), błąd wobec 869 525 000 Hz, krok 23,84 Hz i `synt_offset` (kroki `FOFF`) |
| `STATE`, `IDLE` | stan głównego sterownika i liczba bajtów w kolejkach TX i RX; `IDLE` przechodzi do READY |
| `RSSI` | `rssi_dbm` z RSSI_LEVEL_RUN − 146 (tylko w RX) |
| `REG <hex>` | odczyt rejestru 00–FE z bajtami statusu, np. `REG F0` (PARTNUM), `REG 8E` (MC_STATE0) |
| `REGW <hex> <hex>` | zapis rejestru 00–FE w READY, tylko w trybie przygotowania (np. kolejność bajtów SYNC0..3 do próby w eterze); `VERIFY` pokazuje różnicę wobec tablicy P1, `CONFIG` ją cofa. Po wyjściu z trybu przygotowania zmieniona tablica daje `p1_ok: false` (stacja nie nadaje P1) do `CONFIG` |
| `TXCW` | MOD_TYPE = CW i dane PN9; pole `marc` podaje stan S2-LP (`TX`) |
| `TXPKT` | ramki wzorcowe o stałej długości; S2-LP nie wyprowadza „pakiet w powietrzu” dla nadawania, więc `sync_gpio: false`, a czas serii liczy się do przerwania TX_DATA_SENT i powrotu do READY |
| `FOFF [<hz>]` | korekta słowem SYNT (krok 23,84 Hz; do ±50 kHz, jak na A); `freqoff` to liczba kroków |
| `DISPLAY [<hz>]` | `extcomin: "MCPWM0"`, licznik 0–9 999 |
| `DRIVE [<0-3>]` | napęd SCK i MOSI (`gpio_drive_cap_t`, około 5/10/20/40 mA) do restartu |
| `REBOOT` | `esp_restart()`; pamięć RTC niezerowana zostaje |

Przebieg B3 (jak A3–A4):

- `BTN` bez naciśnięć daje same `false`, a każde naciśnięcie zmienia tylko swoje pole.
- `LED 5 1`, `LED 5 0`.
- `BUZZ` daje sygnał 2048 Hz.
- `FRAM` z `ok: true` i nazwą układu.
- Ekran pokazuje wybór języka, a kolejne `DISPLAY` pokazują zmieniający się `counter` i `level` zmieniający się co 0,5 s.
- System operacyjny widzi dwa porty szeregowe.

Przebieg B4: po wpięciu X-NUCLEO-S2868A2 `RADIO` daje `partnumber: 0x03`, `xo_on: true` i stan `RX` (odbiór P1 od startu). `VERIFY` daje `mismatches: 0`, a `FREQ` około 869 525 003 Hz. Bez modułu (albo z przerwą na MISO) `partnumber` wynosi `0x00` albo `0xFF`, a `ok` jest `false`. Karta DS11896 Rev 5 podaje VERSION `0x91`. Biblioteka ST zna też `0x81` i `0xC1`, więc `partversion` nie wpływa na `ok`. Dalej jak na A: `PREP 1`, `TXCW 2` z miernikiem częstotliwości, `FOFF`, `TXPKT`/`RX`/`RXPER` i `P1TX`/`P1RX` między stanowiskami A i B.

Budowa i wgranie (port USB-OTG DevKitC, nie UART):

```bash
cd firmware && ../.venv-pio/bin/pio run -e bench-b
```

```bash
cd firmware && ../.venv-pio/bin/pio run -e bench-b -t upload
```

### Sterownik łącza S2-LP

`measure::Bench` (polecenia pomiarowe i łącze P1) korzysta z interfejsu `radiolink::Driver` (`src/radio_link.h`); CC1120 ma go w `src/cc1120_link.cpp` (kod przeniesiony z `measure.cpp` bez zmian zachowania), S2-LP w `src/s2lp_link.cpp`:

- **Nadawanie** z kolejki TX (128 B) w pakiecie BASIC. Ramka P1 ma zmienną długość: pole LEN wysyła układ z PCKTLEN (LEN liczy BODY i CRC), więc do kolejki idą BODY i CRC bez bajtu LEN. Ramki wzorcowe mają stałą długość z PCKTLEN. Polecenie TX idzie tylko ze stanu READY; na czas własnej serii odbiór przerywa `SABORT`. Przetwornica SMPS na czas nadawania przechodzi na PM_CONF3 = 0x9C, a potem wraca na 0x90, jak w bibliotece ST (`S2LP::send`, `S2LP::read`; dotyczy też `TXCW`). Nadawanie kończy się po przerwaniu TX_DATA_SENT i powrocie do READY. Gdy przerwanie nie przyjdzie, po czasie ramki + 120 ms sterownik wysyła `SABORT` i opróżnia kolejkę.
- **Odbiór** w trybie stałym (PERS_RX, TIMERS5 = 0: bez limitu czasu RX): po przerwaniu RX_DATA_READY długość pochodzi z RX_PCKT_LEN, dane z kolejki RX, RSSI z RSSI_LEVEL (zapamiętanego przy słowie synchronizacji) − 146 dBm, a jakość to SQI. RX_DATA_DISC, długość spoza 17–102 B albo liczba bajtów w kolejce inna niż długość ramki dają `rx_bad`. Przy PERS_RX następny pakiet trafia do tej samej kolejki, a RX_PCKT_LEN opisuje tylko ostatni, więc nadmiar po dłuższym postoju pętli przesunąłby kolejne odczyty. RX_FIFO_ERROR oznacza przepełnienie. Po każdym z tych zdarzeń sterownik wysyła `SABORT`, opróżnia kolejkę i wraca do RX.
- **Przerwania** czytane z IRQ_STATUS3..0 (odczyt kasuje) przez SPI przy każdym odpytaniu i zbierane w programie, bez linii nIRQ; maska: RX_DATA_READY, RX_DATA_DISC, TX_DATA_SENT, TX_FIFO_ERROR, RX_FIFO_ERROR, VALID_SYNC.
- **CCA:** kanał zajęty, gdy przyszło VALID_SYNC bez końca ramki (najwyżej 300 ms) albo RSSI_LEVEL_RUN − 146 przekracza próg −100 dBm.
- **TXCW:** MOD_TYPE = 7 (CW) i TXSOURCE = PN9; `STOP` przywraca MOD2 i PCKTCTRL1 z tablicy.
- **FOFF:** słowo SYNT ± liczba kroków f_xo / 2^19 / 4 (23,84 Hz) wobec tablicy, zapis w READY i powrót do RX; po `CONFIG` zapisywany ponownie.
- **Oszacowanie błędu częstotliwości** z odebranych ramek (pole `foff` ekranu STAN na A z FREQOFF_EST) na B nie jest podawane: karta nie podaje jednostki AFC_CORR.

Test `tests/test_radio_link_host.py` sprawdza sterownik łącza S2-LP z modelem układu (bajty statusu, stany po poleceniach, kolejki FIFO, IRQ_STATUS kasowane odczytem) oraz `measure::Bench` ze sterownikiem zastępczym (seria wzorcowa z długiem, nadanie P1 z CCA i odroczeniem, odbiór i składanie, `FOFF`, `TXCW`).

### Rejestry profilu P1 dla S2-LP

Tablica jest w `src/s2lp_p1_registers.h`, generowanym przez `tools/s2lp_p1_registers.py` (test `tests/test_s2lp_p1_registers.py` sprawdza wzory, pola pakietu i aktualność nagłówka). X-NUCLEO-S2868A2 ma kwarc 50 MHz, więc zegar części cyfrowej to 25 MHz (PD_CLKDIV = 0), a dzielnik odniesienia jest wyłączony (D = 1). Wartości oznaczone w tablicy:

- **P1**: policzone z parametrów profilu wzorami karty DS11896 (Rev 5): częstotliwość bazowa (równanie 7), prąd pompy ładunku (tabela 37), szybkość (14), dewiacja (10), filtr (tabela 44), IF (15), pola pakietu BASIC (rozdział 7). Wyszukiwanie mantysy i wykładnika odtwarza kod biblioteki ST ([stm32duino/S2-LP](https://github.com/stm32duino/S2-LP), `S2LP_Radio.cpp`, BSD-3-Clause), więc zaokrąglenia są takie jak w sterowniku ST.
- **ST**: ustawienia, które biblioteka ST zapisuje w `S2LPRadioInit` i `S2LP::begin` bez parametru profilu: filtr Bessela PA dla < 16 kbit/s, FIR wyłączony dla FSK, częstotliwość przełączania SMPS (PM_CONF3), poziom PA ze wzoru 29 − 2 × dBm.
- **reset**: wartości domyślne z tabeli 62 zapisane jawnie, żeby weryfikacja je obejmowała.

| Parametr P1 | Rejestry | Wartość | Wynik |
|---|---|---|---|
| 869,525 MHz, pasmo wysokie (B = 4) | SYNT3..0, SYNTH_CONFIG2 | `62 2C 7E FA`, `0xD0` | 869 525 003 Hz, krok 23,8 Hz; VCO 3478 MHz < 3600 MHz: PLL_CP_ISEL = 3, bez PFD split |
| IF 300 kHz | IF_OFFSET_ANA, IF_OFFSET_DIG | `0x2F`, `0xC2` | wartości domyślne (`0x2A`, `0xB8`) dotyczą kwarcu 26 MHz |
| 4800 Bd, 2-GFSK BT 0,5 | MOD4..2 | `92 A7 A4` | 4800,0 Bd |
| dewiacja ±4 kHz | MOD1, MOD0 | `0x01`, `0x50` | 4005,4 Hz (krok około 6 Hz; 3993,5 Hz przy M = 79) |
| filtr 24–32 kHz | CHFLT | `0x15` | 25,5 kHz (26,5 kHz z tabeli × 25/26) |
| próg CCA −100 dBm | RSSI_TH | `0x2E` | RSSI_TH − 146; przesunięcie RSSI modułu wyznacza T4 |
| 8 × 0xAA, D3 91 D3 91 | PCKTCTRL6, PCKTCTRL5, PCKTCTRL3, SYNC3..0 | `0x80`, `0x20`, `0x01`, `91 D3 91 D3` | 32 pary bitów wzoru 1010, słowo 32-bitowe (SYNC0 nadawany pierwszy, patrz niżej) |
| LEN = BODY + CRC, CRC programowe | PCKTCTRL4, PCKTCTRL2, PCKTCTRL1 | `0x00`, `0x01`, `0x00` | pakiet BASIC, zmienna długość z 1-bajtowym LEN, bez adresu, bez CRC układu, bez wybielania, MSB pierwszy |
| 13 dBm | PA_POWER8, PA_POWER0 | `0x03`, `0x07` | poziom 3 w gnieździe o indeksie 7 (PA_POWER8 = 0x5A; biblioteka ST pisze indeks i do PA_POWER8 + 7 − i), bez PA_MAXDBM i bez narastania; wzór biblioteki ST, moc do pomiaru |

Decyzje i otwarte punkty:

- **Kolejność bajtów słowa synchronizacji.** S2-LP nadaje najpierw SYNC0 (adres 0x36), a SYNC3 (0x33) na końcu; tak zapisuje słowo biblioteka ST (`S2LPSetSyncWords`: najmłodszy bajt do SYNC3) i tak potwierdził pracownik ST na forum ST (wątek „Make S2-LP talk to nRF905”). Słowo P1 `D3 91 D3 91` w kolejności nadawania daje więc SYNC0 = `D3`, SYNC1 = `91`, SYNC2 = `D3`, SYNC3 = `91`. Ostatecznie potwierdza to próba ramki P1 między stanowiskami A i B.
- **Zmienna długość w tablicy** (na CC1120 tablica ma stałą długość dla ramek wzorcowych): LEN ramki P1 liczy BODY i CRC, czyli dokładnie to, co silnik pakietów BASIC odbiera po polu długości; ramki wzorcowe przełączają bit FIX_VAR_LEN na czas `TXPKT` i `RX`. Sterownik łącza ustawia PCKTLEN przy każdym pakiecie: przy nadawaniu długość BODY i CRC ramki, przy odbiorze P1 największą (102).
- **Odbiór stały i przerwania:** PERS_RX (PROTOCOL0 = `0x0A`, z ustawieniem ST) i TIMERS5 = 0 (bez limitu czasu RX) trzymają odbiornik w RX po każdej ramce; IRQ_MASK odblokowuje zdarzenia [sterownika łącza](#sterownik-łącza-s2-lp).
- **GPIO modułu:** GPIO0 (GPIO14 ESP32-S3, J11) = nIRQ (sterownik odpytuje IRQ_STATUS, linia tylko do analizatora), GPIO2 (GPIO4, J11) = wykryte słowo synchronizacji, jak GPIO2 CC1120 na stanowisku A; GPIO1 i GPIO3 zostają wyjściem masy (wartość domyślna).
- **Bez kalibracji ręcznej:** S2-LP kalibruje VCO sam przy każdym przejściu do LOCK (wartość domyślna VCO_CONFIG).

Tablica nie rozstrzyga:

- mocy wyjściowej: wzór ST jest przybliżeniem, poziom PA i napięcie SMPS trzeba ustawić pomiarem na 13 dBm ±1 dB;
- błędu częstotliwości kwarcu modułu (`FREQ` podaje tylko wartość zaprogramowaną);
- przesunięcia RSSI;
- ustawień AFC, AGC i odtwarzania zegara symboli dla 4800 Bd (zostają wartości domyślne, sprawdza je pomiar czułości w T4);
- kolejności bajtów słowa synchronizacji, dopóki nie potwierdzi jej próba w eterze.

## Rejestry profilu P1

Tablica rejestrów jest w `src/p1_registers.h`, generowanym przez `tools/p1_registers.py` (test `tests/test_p1_registers.py` sprawdza, że nagłówek jest aktualny, a wartości zgadzają się ze wzorami i z eksportem TI). Wartości pochodzą z dwóch źródeł, oznaczonych w tablicy:

- **P1**: policzone z parametrów [profilu P1](../../docs/archiwum/p1-radio.md#profil-p1-do-prototypu) wzorami instrukcji [CC112x SWRU295E](https://www.ti.com/lit/ug/swru295e/swru295e.pdf): częstotliwość (równania 26–27), szybkość symboli (6–9), dewiacja (1–2), filtr odbiornika (10, tabela 17), moc (21), a także słowo synchronizacji, preambuła i silnik pakietów (rozdział 8 i 11).
- **TI**: rejestry opisane w instrukcji „use values from SmartRF Studio” (syntezer FS_*, XOSC, mieszacz IF, filtr DC, AGC). SmartRF Studio to program TI tylko na Windows, nieuruchamiany w tym kroku; wartości wzięto z eksportu SmartRF Studio, który TI dołącza do pakietu przykładów [swrc253e](https://www.ti.com/tool/download/SWRC253) (`cc112x_easy_link_reg_config.h`, BSD-3-Clause): 868 MHz, 2-FSK, dewiacja 3,998 kHz, filtr 25 kHz, czyli ten sam tor odbiorczy co w P1. Pozycje zależne od szybkości (PA_CFG0, TOC_CFG) pochodzą z bloku 4,8 kbit/s pliku `cc112x_serial_mode_reg_config.h` tego pakietu.

| Parametr P1 | Rejestry | Wartość | Wynik ze wzoru |
|---|---|---|---|
| 869,525 MHz, pasmo 820–960 MHz (dzielnik LO 4) | FREQ2..0, FS_CFG | `6C B0 CD`, `0x12` | 869 525 024 Hz, krok 122 Hz; FREQOFF daje krok 30,5 Hz |
| 4800 Bd | SYMBOL_RATE2..0 | `63 A9 2A` | 4800,0 Bd (ta sama mantysa co domyślne 1200 Bd, wykładnik 6 zamiast 4) |
| dewiacja ±4 kHz, 2-GFSK | DEVIATION_M, MODCFG_DEV_E | `0x06`, `0x0B` | 3997,8 Hz, jak w eksporcie TI |
| filtr 24–32 kHz | CHAN_BW | `0x08` | 25,0 kHz (decymacja 20 × 8); inne nastawy w przedziale: 28,6 kHz (`0x07`), 31,25 kHz (`0x44`) |
| 13 dBm | PA_CFG2 | `0x7D` | PA_POWER_RAMP 61 → 13,0 dBm na wyjściu układu, przed torem modułu |
| 8 × 0xAA, D3 91 D3 91 | PREAMBLE_CFG1, SYNC3..0, SYNC_CFG0 | `0x28`, `D3 91 D3 91`, `0x17` | słowo 32-bitowe bez kwalifikatora błędów bitów |
| próg CCA −100 dBm | AGC_CS_THR | `0xFF` | −100 dBm przy przyjętym przesunięciu RSSI −99 dB; obie wartości wyznacza T4 |
| ramka do 103 B, CRC w ramce | PKT_CFG0, PKT_CFG1, PKT_LEN | `0x00`, `0x01`, `0x67` | stała długość z PKT_LEN, CRC układu wyłączone, status (RSSI, LQI) dopisany do FIFO |

Decyzje przy tworzeniu tablicy:

- **CRC układu wyłączone.** CC1120 liczy CRC-16 z wielomianem 0x1021 tylko z wartością początkową 0x0000, a P1 wymaga 0xFFFF (CRC-16/CCITT-FALSE), więc CRC liczy oprogramowanie.
- **Stała długość pakietu w tablicy.** Polecenia pomiarowe nadają ramki wzorcowe bez pola LEN, więc tablica ustawia stałą długość z PKT_LEN. Sterownik P1 przełączy układ na zmienną długość (LENGTH_CONFIG = 01, PKT_LEN = 102): od rozstrzygnięcia F79 pole LEN ramki P1 liczy BODY i CRC, czyli dokładnie to, co silnik pakietów odbiera po bajcie długości ([przegląd, F79](../../docs/review.md)).
- **Kalibracja ręczna.** SETTLING_CFG wyłącza kalibrację automatyczną (jak w eksporcie TI); oprogramowanie wykonuje po zapisie rejestrów i po każdym `CAL` procedurę z erraty CC112x (dwa przebiegi `SCAL` z różnym VCDAC_START, zostaje wynik z większym FS_VCO2), przeniesioną z `manualCalibration()` w swrc253e.
- **Weryfikacja odczytem.** Każdy rejestr tablicy jest odczytywany po zapisie i porównywany z maską (XOSC1 ma bit tylko do odczytu). Pierwsza niezgodność trafia do odpowiedzi `CONFIG`/`VERIFY`.
- **GPIO modułu.** GPIO2 (D3) = PKT_SYNC_RXTX (pakiet w powietrzu, do pomiaru czasu TX), GPIO0 (D2) = RXFIFO_THR_PKT (koniec odebranego pakietu); niepodłączone GPIO1 i GPIO3 w trybie analogowym jak w eksporcie TI.
- **Odbiornik z niską IF** 62,5 kHz (wartość domyślna) z kompensacją obrazu, bo warunek IF > 2 × 25 kHz i IF + 12,5 kHz ≤ 100 kHz jest spełniony; zero-IF nasycałoby RSSI przy około −50 dBm.

Tablica nie rozstrzyga:

- błędu częstotliwości kwarcu modułu (mierzy się go `FREQ`/`FOFF` na stanowisku);
- przesunięcia RSSI i progu CCA (T4);
- dopasowania filtru DC, AGC i progu synchronizacji do 4800 Bd (eksport TI dotyczy 1200 Bd w tym samym paśmie; różnice sprawdza pomiar czułości w T4);
- wartości z nowszej wersji SmartRF Studio. Eksport pochodzi z pakietu z 2013 r.; przy dostępie do narzędzia trzeba porównać tablicę z eksportem dla P1 i wpisać wersję narzędzia do nagłówka.

## Łącze P1

Kodek i składanie ramek są w `src/p1frame.cpp` (bez zależności od Arduino). Kod dzieli datagram do 600 B na ramki `LEN | BODY | CRC`, w których LEN liczy BODY i CRC (F79), rozbiera ramkę z pełną kontrolą pól i składa datagramy według [specyfikacji radia](../../docs/archiwum/p1-radio.md#ramka-w-eterze). Składanie ma 8 prób po 120 s. Poprawne duplikaty są pomijane; sprzeczny duplikat albo zmiana liczby fragmentów lub długości usuwa próbę. Przy przepełnieniu odpada próba z najmniejszą liczbą fragmentów, a lista 16 ostatnio złożonych identyfikatorów odrzuca spóźnione duplikaty. Test na komputerze (`tests/test_firmware_host.py`) porównuje ramki z modelem bajt po bajcie dla wszystkich długości 1–600 B i odtwarza przypadki wrogie z testów modelu.

Łącze w `src/measure.cpp`, wspólne dla A i B; opis odbioru i CCA dotyczy CC1120, różnice S2-LP są w [sterowniku łącza](#sterownik-łącza-s2-lp):

- **Odbiór** (`P1RX`): układ w trybie zmiennej długości z PKT_LEN = 102, więc ramki dłuższe odrzuca sam; obraz czyta bajt LEN, czeka na resztę ramki i dwa bajty statusu (RSSI, LQI), rozbiera ramkę i oddaje ją składaniu. Ramki za krótkie, niekompletne w czasie albo z błędem rozbioru liczą się jako `rx_bad`. Każda ramka daje wiersz `p1rx` ze stanem składania, a złożony datagram wiersz z identyfikatorem i danymi szesnastkowo (bufor CDC na nRF52840 ma 256 B, więc dane mają tylko datagramy do około 80 B; dłuższe dają wiersz z `"data_omitted":true`, a do stosu trafiają bez zmian).
- **Nadawanie** (`P1TX`): datagram czeka na koniec długu ciszy, a potem na 50 ms wolnego kanału. Kanał jest wolny, gdy RSSI jest poniżej progu −100 dBm przy przyjętym przesunięciu RSSI, na GPIO2 nie trwa odbiór po słowie synchronizacji i w tym czasie nie przyszła żadna ramka. Przerwa między próbkami ponad 10 ms zaczyna okno od nowa, a ostatnia próbka i nadanie idą w tym samym obiegu. Zajęty kanał odracza nadanie o losowe 100–1000 ms (`deferrals`; łączne czekanie ponad 1 s liczy się jako `long_deferrals`). Po 30 odroczeniach datagram jest odrzucany (`tx_drop`); tę liczbę wybrano dla stanowiska, specyfikacja nie podaje limitu. Przed pierwszą ramką do dziennika trafia dług 12 × zarezerwowany czas serii (liczony dla najdłuższych ramek), potem fragmenty idą jedną serią, a odbiór wraca od razu po serii. Cisza radiowa i `STOP` przerywają i odrzucają nadanie (`tx_drop`). Identyfikator datagramu i czas odroczeń pochodzą z generatora stacji (HMAC-DRBG, [stos](stos.md#stos-reticulum)).
- **Dwie płytki**: na obu `P1RX`; na jednej `P1TX 48656C6C6F` („Hello”); druga wypisuje `p1rx` z `datagram`. Datagram 600 B to 7 ramek i około 1,4 s nadawania, po nim około 16,4 s długu (rezerwacja: 7 ramek pełnej długości × 12).

Złożone datagramy idą do [interfejsu P1 stosu Reticulum](stos.md#interfejs-p1), a koniec serii zwalnia jego kolejkę; `P1RX` i `P1TX` zostają jako polecenia pomiarowe (datagram `P1TX` bez IFAC stos po drugiej stronie odrzuca). Podział czasu kanału na klasy K0–K2 jest w [interfejsie P1](stos.md#interfejs-p1).
