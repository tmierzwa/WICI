# WICI: oprogramowanie stacji

**Następny krok radiowy (przegląd praktyczny 2026-10-08, F99).** Pilotaż używa gotowej płytki ESP32-S3 z układem LoRa SX1262, więc kolejną pracą radiową jest interfejs LoRa (SX1262) w stosie: format w eterze zgodny z RNode, cisza 12t, IFAC ([profil LoRa](../docs/spec/radio.md#profil-lora-pilotażu)). Sterowniki P1 (CC1120, S2-LP) i obrazy stanowisk zostają dla wariantu zapasowego i prób na stanowiskach deweloperskich.

Katalog zawiera oprogramowanie układowe stacji. Poniższy opis zaczyna się od wariantu na [stanowisku deweloperskim A](../hardware/dev-bench/README.md): nRF52840-DK z modułem TI CC1120EM-868-915 i pamięcią FRAM na złączu Arduino płytki. Środowisko `bench-a` w `platformio.ini` buduje obraz, który po podłączeniu USB zgłasza się poleceniem `INFO` w formacie ze [specyfikacji radia](../docs/spec/radio.md#usb-do-laptopa), identyfikuje układ radiowy i FRAM przez SPI, zapisuje do CC1120 [rejestry profilu P1](#rejestry-profilu-p1) z weryfikacją odczytu i kalibracją syntezera, wykonuje [polecenia pomiarowe](#polecenia-pomiarowe) `TXCW`, `TXPKT`, `RXPER`, `FOFF` ze specyfikacji, prowadzi [dziennik i magazyny w FRAM](#dziennik-i-magazyny-w-fram) (dług ciszy, licznik czasu pracy, zdarzenia; rejestr zgłoszeń, skrzynka, pierścień zdarzeń i konfiguracja z transakcjami), obsługuje [łącze P1](#łącze-p1) (odbiór i składanie datagramów, nadawanie z CCA, odroczeniem i długiem ciszy), podaje zaprogramowaną częstotliwość i RSSI, prowadzi [ekran Sharp i menu stacji](#ekran-i-przyciski) na przyciskach płytki (wybór języka, ekran główny, cisza, STAN; EXTCOMIN z licznika RTC2).

Obraz obsługuje diody płytki oraz udostępnia drugi interfejs CDC z [protokołem USB laptop–stacja](#protokół-usb-laptopstacja) (`"usb":2`) oraz [warstwę aplikacji](#warstwa-aplikacji-nad-stosem) z cyklem życia zgłoszenia, wysyłką z rejestru i wiadomościami odbiorcy do skrzynki.

Ruch idzie przez [stos Reticulum](#stos-reticulum) (port microReticulum z interfejsem P1, IFAC, tożsamością i tablicami w FRAM) jako pakiety okazjonalne z potwierdzeniem transportowym; LXMF jeszcze nie ma, więc treść ma zastępczą kopertę z adresem nadawcy bez podpisu.

Stacja ma jedną rolę (D19): w [konfiguracji węzła stanowiska](#węzeł-stanowiska) przekazuje ruch i łączy radio z komputerem stanowiska drugim interfejsem Reticulum przez USB.

Środowisko `bench-n1` buduje ten sam obraz dla stanowiska A na [płytce nośnej N1](#płytka-nośna-n1-bench-n1) zamiast przewodów: inne piny SPI, radia i ekranu oraz panel płytki (przełącznik CISZA, przycisk przygotowania, dioda alarmu, brzęczyk, VTEST).

Środowisko `bench-b` buduje ten sam program stacji dla [stanowiska B na N1](#stanowisko-b-na-płytce-n1-bench-b): ESP32-S3-DevKitC-1 z X-NUCLEO-S2868A2 (ST S2-LP) zamiast nRF52840 i CC1120. Wspólne są polecenia, polecenia pomiarowe, łącze P1, dziennik, magazyn, protokół USB laptop–stacja z dwoma interfejsami CDC, warstwa aplikacji, ekran i panel N1; różnią się warstwa MCU (`src/platform_*.cpp`), sterownik układu radiowego (`src/radio_console_*.cpp`, `src/*_link.cpp`) i [rejestry P1 dla S2-LP](#rejestry-profilu-p1-dla-s2-lp).

Obrazy skompilowano (PlatformIO, ze stosem Reticulum; rdzeń Adafruit nRF52 1.7.0: `bench-a` 99 772 B RAM statycznej, 595 172 B flash, `bench-n1` 100 004 B RAM, 599 856 B flash, podział w [pomiarze RAM stosu](#pamięć-ram) i [przeglądzie rozmiaru](#rozmiar-i-wydajność); Arduino-ESP32 3.3.12: `bench-b` 146 784 B RAM z 327 680 B, 862 277 B flash). **Żadnego nie uruchomiono na sprzęcie**: odpowiedzi poleceń, numery pinów, działanie SPI z modułem, przyjęcie rejestrów przez układ, USB i łącze radiowe wymagają sprawdzenia na płytce według kroków niżej. Na hoście sprawdzone są tylko moduły bez Arduino, sterownik S2-LP i jego sterownik łącza z modelem układu, `measure::Bench` ze sterownikiem zastępczym, tablica rejestrów S2-LP i zgodność pinów `bench-b` z [połączeniami](../hardware/dev-bench/polaczenia.md) (`tests/`), a stos Reticulum z interfejsem P1 w programie na komputerze z emulatorem łącza wobec Reticulum w Pythonie ([próba zgodności](#próba-zgodności-z-reticulum)).

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

Ekran ma na płytce przetwornicę 5 V i translację poziomów, więc VIN idzie z VDD płytki (3,0 V). Płytka 4694 nie ma zworki EXTMODE: pin EMD złącza (EXTMODE ekranu) jest ściągnięty na płytce 10 kΩ do masy, a VCOM z pinu EXTCOMIN (EIN) działa dopiero przy EMD w stanie wysokim, więc EMD łączy się przewodem z VDD (N1 ma goły panel z EXTMODE na stałe w stanie wysokim). Kolejność pinów złącza według projektu Adafruit (JP1.1–JP1.9): VIN, 3V3, GND, CLK, DI, CS, EMD, DISP, EIN. Bez przewodu EMD `VCOM 1` przełącza odwracanie VCOM na bit w poleceniach ekranu.

Przyciski płytki: BUTTON1 = GÓRA, BUTTON2 = DÓŁ, BUTTON3 = OK, BUTTON4 = WSTECZ (menu stacji, patrz [Ekran i przyciski](#ekran-i-przyciski)). Diody: LED1 bicie serca (0,5 s), LED2 radio rozpoznane, LED3 FRAM rozpoznana i dziennik uruchomiony, LED4 port USB otwarty przez hosta. Przewody do 5 cm; SPI pracuje z 1 MHz.

## Płytka nośna N1 (bench-n1)

Opis płytki i przypisanie sygnałów: [płytka nośna](../hardware/dev-bench/plytka-nosna.md#przypisanie-sygnałów), połączenia pin po pinie: [połączenia](../hardware/dev-bench/polaczenia.md). Numery pinów są w `src/board_bench_n1.h`, wybieranym flagą `-DWICI_BENCH_N1` środowiska `bench-n1`; reszta kodu jest wspólna z `bench-a`. **Obrazu `bench-a` nie wgrywa się na DK wpiętą w N1** ([uruchomienie](../hardware/dev-bench/uruchomienie.md#oprogramowanie)): jego SCK na D13 trafia na przełącznik CISZA, a CS i RESET radia na diodę alarmu i DISP ekranu.

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

- **SPI:** SPIM2 z pinami MISO P1.14, SCK P1.04, MOSI P1.13; `SPIClass::begin()` rdzenia ustawia napęd H0H1 na SCK i MOSI. Domyślne `SPI` (SCK na D13) nie jest uruchamiane. Radio 1 MHz jak na przewodach, FRAM **8 MHz** (`board::FRAM_SPI_HZ`; specyfikacja wymaga ≥8 MHz w każdej stacji, a 8 MHz to górna granica SPIM2). Ekran pracuje z **1 MHz**, nie 2 MHz: sieć SCK ma około 300 mm z odgałęzieniami i 33 Ω szeregowo, P1.04 to pin, który Nordic zaleca tylko do sygnałów wolnozmiennych (ochrona radia 2,4 GHz, tu nieużywanego), a 2 MHz to granica LS027B7DH01. `DISPLAY 2000000` przełącza ekran na 2 MHz do restartu i przerysowuje cały obraz, do pomiaru oscyloskopem przy J7 ([uruchomienie N1](../hardware/dev-bench/uruchomienie.md#pomiar-magistrali-oscyloskopem)) (pełny obraz 240 × 52 B trwa 100 ms przy 1 MHz, zwykle zmienia się kilka wierszy).
- **Ekran:** DISP w stanie niskim od startu (2,2 kΩ do masy na płytce), stan wysoki dopiero po poleceniu CLEAR w `display.begin()`.
- **CISZA:** przełącznik działa na zmianę położenia po 50 ms stałego stanu; położenie przy starcie ustawia ciszę od razu. Zmiana trafia do dziennika (`silence on (switch)`) i jako zdarzenie `radio` do laptopa. Przełącznik ma pierwszeństwo ([specyfikacja](../docs/spec/oprogramowanie.md), „Cisza radiowa”): w położeniu „cisza” ani `SILENCE 0`, ani `silence` z laptopa nie wyłącza ciszy (`silence switch on`, `rejected` z `silence switch`). Włączenie ciszy z portu USB przy przełączniku w położeniu „praca” obowiązuje do następnego przełączenia.
- **Tryb przygotowania:** przytrzymanie przycisku przygotowania przez 3 s przełącza tryb (włącza albo wyłącza; wyłączenie przerywa pomiary jak `PREP 0`), z krótkim sygnałem. Przycisk wciśnięty przy starcie nie przełącza trybu. `PREP` z potwierdzeniem OK zostaje jako zapasowe.
- **Dioda alarmu** (według [zasad alarmów](../docs/spec/oprogramowanie.md), `src/annunciator.cpp`): miga krótkimi błyskami (50 ms co 5 s, 1% czasu jak w modelu energii), dopóki są nieprzeczytane wiadomości, trwa przyczyna alarmu (także po potwierdzeniu OK) albo cisza radiowa; błysk trwa co najmniej 50 ms także przy wolnym obiegu pętli. Przyczynę (zgłoszenie po progu bez potwierdzenia od odbiorcy albo pilność 2 bez odczytu, niezależnie od potwierdzenia OK) sprawdza `Station::alarmCause` co sekundę; dioda gaśnie, gdy przyjdzie potwierdzenie albo odczyt, albo zgłoszenie zostanie anulowane lub zastąpione. **Brzęczyk** (2048 Hz z `tone()`, PWM2; stały stan wysoki pobierałby około 75 mA z 5 V): na ekranie alarmu 200 ms co 2 s do potwierdzenia OK; nowa wiadomość (przyrost nieprzeczytanych, bez sygnału za wiadomości sprzed startu) 100 ms, chyba że opiekun wybrał WYCISZ DŹWIĘK, które alarmów nie wycisza. Cisza radiowa nie daje sygnału, także przy włączeniu; zostają tekst ekranu i dioda. Przypomnienie `wymien_ogniwa` co 15 min przyjdzie z pomiarem ogniw (R02).

Polecenia diagnostyczne do kroków A3–A4 [uruchomienia](../hardware/dev-bench/uruchomienie.md#stanowisko-a) (tylko `bench-n1`):

| Polecenie | Odpowiedź |
|---|---|
| `BTN` | cztery przyciski oraz `silence_switch` i `prep_button` (true = linia zwarta do masy), stan `silence` i `prep`, `alarm_led` |
| `LED 5 <0\|1>` | dioda alarmu; obowiązuje (bez migania) do następnej zmiany powodu migania: alarm, cisza, nieprzeczytane |
| `BUZZ [<ms>] [<hz>]` | brzęczyk przez `ms` (domyślnie 500, do 5000; 0 przerywa) z częstotliwością `hz` (100–10 000, domyślnie 2048) |
| `VTEST` | `vtest_mv` (napięcie na zacisku J12 = napięcie pinu × 6), `pin_mv`, `raw`: średnia 16 próbek SAADC, 12 bitów, pełna skala 3,6 V; `ain` i `divider` (6) |
| `DISPLAY <hz>` | zegar SPI ekranu 125 000–2 000 000 Hz do restartu, potem odpowiedź jak `DISPLAY` z polem `spi_hz` |

Przebieg A3: `BTN` bez naciśnięć daje same `false` (przy CISZA w położeniu „cisza” `silence_switch: true`); każde naciśnięcie zmienia tylko swoje pole; `LED 5 1`, `LED 5 0`; `BUZZ` daje słyszalny sygnał 2048 Hz. Przebieg A4: `FRAM` z `ok: true` i nazwą układu, ekran pokazuje wybór języka, a kolejne `DISPLAY` pokazują `counter` RTC2 rosnący od 0 do 4 i `level` (EXTCOMIN) zmieniający się co 0,5 s. `VTEST` przy zacisku J12 zwartym daje około 0 mV, a przy 12 V z zasilacza około 12 000 mV (sprawdzić miernikiem; dokładność zależy od rezystorów 1% i wewnętrznego odniesienia SAADC).

Budowa i wgranie (bootloader jak niżej):

```bash
cd firmware && ../.venv-pio/bin/pio run -e bench-n1
```

```bash
cd firmware && ../.venv-pio/bin/pio run -e bench-n1 -t upload
```

## Stanowisko B na płytce N1 (bench-b)

Opis płytki: [płytka nośna](../hardware/dev-bench/plytka-nosna.md#przypisanie-sygnałów) (kolumna ESP32-S3) i [połączenia](../hardware/dev-bench/polaczenia.md) (J5/J6 to złącza J1/J3 DevKitC). Numery pinów są w `src/board_bench_b.h`. Program to ten sam `src/main.cpp` co na stanowisku A; środowisko `bench-b` pomija sterowniki CC1120 (`cc1120.cpp`, `cc1120_link.cpp`, `radio_console_cc1120.cpp`). Moduł ESP32-S3: N8, N8R2 albo N8R8 (ESP32-S3-WROOM-1, pamięć flash quad SPI); obraz zakłada 8 MB flash w trybie QIO i nie używa PSRAM, więc piny PSRAM ośmiobitowej zostają wolne. Moduły WROOM-2 z pamięcią flash ośmiobitową i 1,8 V (np. N16R8V, N32R8V) wymagają innego trybu pamięci w `platformio.ini` (`opi_opi`) i nie zostały sprawdzone.

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

- **USB.** Złącze „USB” DevKitC (USB-OTG ESP32-S3, GPIO19/20), nie „UART”. Arduino-ESP32 3.3.12 z TinyUSB daje dwa interfejsy CDC ACM z IAD jak na A: pierwszy to diagnostyka (polecenia), drugi dane ([protokół laptop–stacja](#protokół-usb-laptopstacja)). Nazwy interfejsów ustala rdzeń („TinyUSB CDC” i „TinyUSB CDC2”), a urządzenie zgłasza się jako „WICI bench-b” z VID/PID Espressif (testowe, do przydziału przed wydaniem). USB-Serial/JTAG jest wyłączony (`ARDUINO_USB_MODE=0`). Wgrywanie przez ten sam port: PlatformIO otwiera port z prędkością 1200 b/s, program restartuje się do bootloadera ROM i esptool wgrywa obraz; gdy program nie działa, BOOT przytrzymany przy wciśnięciu RESET.
- **Radio.** Sterownik `src/s2lp.cpp` (karta [DS11896](https://www.st.com/resource/en/datasheet/s2-lp.pdf), rozdziały 6 i 9.1): SPI w trybie 0, nagłówek 0x00 zapis, 0x01 odczyt, 0x80 polecenie; w czasie dwóch pierwszych bajtów układ wysyła MC_STATE1 i MC_STATE0 (stan głównego sterownika i XO_ON). Po starcie SDN na 1 ms, `SRES`, odczyt PARTNUM (0xF0) i VERSION (0xF1), zapis tablicy P1 z weryfikacją, potem odbiór P1. Łącze P1 i polecenia pomiarowe idą przez [`src/s2lp_link.cpp`](#sterownik-łącza-s2-lp).
- **SPI i napęd.** SCK i MOSI startują z najniższym napędem ESP32-S3 (`GPIO_DRIVE_CAP_0`, około 5 mA): sieć SCK ma około 300 mm z odgałęzieniami, a 33 Ω (R18) tłumi odbicia na rozgałęzionej sieci; panel Sharp wymaga zboczy SCLK nie dłuższych niż 50 ns, więc zboczy nie wolno nadmiernie spowalniać. `DRIVE <0-3>` zmienia napęd do restartu; wybór na stałe po obejrzeniu zboczy analizatorem na J11 (najniższy napęd, przy którym zbocza są czyste przy 1 i 2 MHz).
- **EXTCOMIN** generuje timer jednostki MCPWM0 (sterownik MCPWM z ESP-IDF 5: licznik 10 kHz, okres 10 000 taktów, stan wysoki do porównania 5000) bez udziału programu, jak RTC2 na nRF52840; gdy sterownik MCPWM zwróci błąd, panel zostaje wyłączony (DISP w stanie niskim), dziennik dostaje wpis `display off: EXTCOMIN timer failed`, a `DISPLAY` podaje `extcomin_ok: false`. Bitu VCOM w poleceniach nie używa się zamiast licznika, bo EXTMODE panelu na N1 jest na stałe w stanie wysokim i panel ten bit pomija (F103). LEDC z kwarcu 40 MHz nie schodzi poniżej około 2,4 Hz (dzielnik do 1024, licznik do 14 bitów), a z wewnętrznego RC_FAST ledwie do 1 Hz i z niedokładnym zegarem, dlatego MCPWM. Kod EXTCOMIN jest w `src/sharp_extcomin_nrf.cpp` (RTC2, PPI, GPIOTE) i `src/sharp_extcomin_esp32.cpp`; reszta `src/sharp.cpp` nie zależy od MCU.
- **Warstwa MCU** (`src/platform_esp32.cpp`): nazwa `WICI-xxxxxx` z adresu MAC w eFuse, gdy stos Reticulum nie wystartował (zwykle, jak na A, nazwa ze skrótu tożsamości i adres celu stacji), `reset_reason` z `esp_reset_reason()`, watchdog zadań (TWDT, 60 s) na zadaniu pętli, pamięć niezerowana `RTC_NOINIT_ATTR` (język i ekran po restarcie programowym), pętla stacji w zadaniu `loop()` rdzenia z 16 KB stosu, identyfikator datagramu z `esp_fill_random` (przy wyłączonym Wi-Fi i Bluetooth źródło szumu jest słabsze; karta ESP32-S3 zaleca wtedy dodatkowe źródło), VTEST z `analogReadMilliVolts` (tłumienie 11 dB, kalibracja z eFuse).
- **Brak diod stanu** LED1–LED4 (DevKitC ma tylko diodę RGB, nieużywaną): `LED 1-4` zwraca błąd, a czekanie na potwierdzenie OK nie miga diodą; dioda alarmu N1 działa jak w `bench-n1`.

Polecenia są jak na [stanowisku A](#polecenia) i [N1](#płytka-nośna-n1-bench-n1) (`LED 5`, `BUZZ`, `VTEST`, `DISPLAY <hz>`), z różnicami układu radiowego i MCU:

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
| `FOFF [<hz>]` | korekta słowem SYNT (krok 23,84 Hz, ±1 MHz); `freqoff` to liczba kroków |
| `DISPLAY [<hz>]` | `extcomin: "MCPWM0"`, licznik 0–9 999 |
| `DRIVE [<0-3>]` | napęd SCK i MOSI (`gpio_drive_cap_t`, około 5/10/20/40 mA) do restartu |
| `REBOOT` | `esp_restart()`; pamięć RTC niezerowana zostaje |

Przebieg B3 (jak A3–A4): `BTN` bez naciśnięć daje same `false`; każde naciśnięcie zmienia tylko swoje pole; `LED 5 1`, `LED 5 0`; `BUZZ` daje sygnał 2048 Hz; `FRAM` z `ok: true` i nazwą układu; ekran pokazuje wybór języka, a kolejne `DISPLAY` pokazują zmieniający się `counter` i `level` zmieniający się co 0,5 s; system operacyjny widzi dwa porty szeregowe. Przebieg B4: po wpięciu X-NUCLEO-S2868A2 `RADIO` daje `partnumber: 0x03`, `xo_on: true` i stan `RX` (odbiór P1 od startu); `VERIFY` daje `mismatches: 0`, `FREQ` około 869 525 003 Hz. Bez modułu (albo z przerwą na MISO) `partnumber` wynosi `0x00` albo `0xFF`, a `ok` jest `false`. Karta DS11896 Rev 5 podaje VERSION `0x91`; biblioteka ST zna też `0x81` i `0xC1`, więc `partversion` nie wpływa na `ok`. Dalej jak na A: `PREP 1`, `TXCW 2` z miernikiem częstotliwości, `FOFF`, `TXPKT`/`RX`/`RXPER` i `P1TX`/`P1RX` między stanowiskami A i B.

Budowa i wgranie (port USB-OTG DevKitC, nie UART):

```bash
cd firmware && ../.venv-pio/bin/pio run -e bench-b
```

```bash
cd firmware && ../.venv-pio/bin/pio run -e bench-b -t upload
```

### Sterownik łącza S2-LP

`measure::Bench` (polecenia pomiarowe i łącze P1) korzysta z interfejsu `radiolink::Driver` (`src/radio_link.h`); CC1120 ma go w `src/cc1120_link.cpp` (kod przeniesiony z `measure.cpp` bez zmian zachowania), S2-LP w `src/s2lp_link.cpp`:

- **Nadawanie** z kolejki TX (128 B) w pakiecie BASIC. Ramka P1 ma zmienną długość: pole LEN wysyła układ z PCKTLEN (LEN liczy BODY i CRC), więc do kolejki idą BODY i CRC bez bajtu LEN. Ramki wzorcowe mają stałą długość z PCKTLEN. Polecenie TX tylko ze stanu READY (odbiór przerywany `SABORT` na czas własnej serii), z przetwornicą SMPS przełączaną na czas nadawania na PM_CONF3 = 0x9C i z powrotem na 0x90 jak w bibliotece ST (`S2LP::send`, `S2LP::read`; także `TXCW`), koniec po przerwaniu TX_DATA_SENT i powrocie do READY; bez przerwania po czasie ramki + 120 ms `SABORT` i opróżnienie kolejki.
- **Odbiór** w trybie stałym (PERS_RX, TIMERS5 = 0: bez limitu czasu RX): po przerwaniu RX_DATA_READY długość z RX_PCKT_LEN, dane z kolejki RX, RSSI z RSSI_LEVEL (zapamiętane przy słowie synchronizacji) − 146 dBm, jakość = SQI. RX_DATA_DISC, długość spoza 17–102 B albo liczba bajtów w kolejce inna niż długość ramki dają `rx_bad` (z PERS_RX następny pakiet pisze do tej samej kolejki, a RX_PCKT_LEN opisuje tylko ostatni, więc nadmiar po dłuższym postoju pętli przesunąłby kolejne odczyty), RX_FIFO_ERROR przepełnienie; po każdym z nich `SABORT`, opróżnienie kolejki i ponowne RX.
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

Czego tablica nie zamyka: mocy wyjściowej (wzór ST jest przybliżeniem; poziom PA i napięcie SMPS do ustawienia pomiarem 13 dBm ±1 dB), błędu częstotliwości kwarcu modułu (`FREQ` podaje tylko wartość zaprogramowaną), przesunięcia RSSI, ustawień AFC, AGC i odtwarzania zegara symboli dla 4800 Bd (zostają wartości domyślne; sprawdza je pomiar czułości w T4) i potwierdzenia kolejności bajtów słowa synchronizacji w eterze.

## Narzędzia

PlatformIO Core w osobnym środowisku Pythona; wersje platformy i rdzenia są przypięte w `platformio.ini` (nordicnrf52 11.0.0, framework-arduinoadafruitnrf52 1.10700.0, czyli rdzeń Adafruit nRF52 1.7.0 z TinyUSB; dla `bench-b` platforma pioarduino 55.03.312 z Arduino-ESP32 3.3.12 na ESP-IDF 5.5, bo dopiero ta wersja daje dwa interfejsy CDC przez USB-OTG; wersja 2.0.17 z oficjalnej platformy espressif32 ma jeden). Rdzeń Adafruit wybrano, bo tego samego używa microReticulum dla nRF52840 (środowisko `wiscore_rak4631`), więc stos sieciowy wejdzie do tego samego projektu.

```bash
python3 -m venv .venv-pio && .venv-pio/bin/pip install platformio
```

```bash
cd firmware && ../.venv-pio/bin/pio run
```

Rdzeń Adafruit zakłada na płytce bootloader Adafruit nRF52 z SoftDevice S140 6.1.1 (obraz aplikacji zaczyna się od 0x26000). Na fabrycznej płytce DK trzeba go wgrać jeden raz przez wbudowany J-Link, plikiem `pca10056_bootloader-<wersja>_s140_6.1.1.hex` z [wydań Adafruit_nRF52_Bootloader](https://github.com/adafruit/Adafruit_nRF52_Bootloader/releases):

```bash
nrfjprog -f nrf52 --program pca10056_bootloader-*_s140_6.1.1.hex --chiperase --verify --reset
```

Potem obraz wgrywa się przez J-Link (`upload_protocol = jlink`, wymaga oprogramowania SEGGER J-Link) albo przez DFU na porcie USB nRF (J3) po zmianie `upload_protocol` na `nrfutil` i wskazaniu portu:

```bash
cd firmware && ../.venv-pio/bin/pio run -t upload
```

Bluetooth nie jest uruchamiany (brak wywołań Bluefruit); SoftDevice tylko zajmuje swój obszar flash. Pomiar zapasu RAM dla T3 musi uwzględnić ten układ pamięci.

## Polecenia

Port USB nRF (J3, nie port J-Link J2) zgłasza się jako urządzenie z dwoma interfejsami CDC ACM z deskryptorami IAD: „WICI diagnostyka” (pierwszy port, polecenia z tej tabeli) i „WICI dane” (drugi port, [protokół laptop–stacja](#protokół-usb-laptopstacja)); identyfikatory VID/PID są testowe z rdzenia Adafruit, do przydziału przed wydaniem. 115200 bit/s (prędkość nie ma znaczenia dla USB). Każda odpowiedź to jeden wiersz JSON. Po otwarciu portu diagnostyki obraz sam wysyła `INFO`, `RADIO`, `FRAM` i `JOURNAL`. `HELP` (albo pusty wiersz) zwraca listę poleceń tego obrazu.

| Polecenie | Odpowiedź |
|---|---|
| `INFO` | pola jak w specyfikacji radia: `contract`, `profile`, `radio`, `mcu`, `fw`, `src`, `mv` (zero, brak pomiaru), `tx_wait_ms` (pozostały dług ciszy), `rx_ok`, `rx_bad`, `tx_drop` z łącza P1, `restarts` (liczba startów) i `uptime_s` (licznik czasu pracy) z dziennika FRAM, oraz `bench`, `prep`, `silence`, `radio_ok`, `p1_ok`, `fram_ok`, `journal_ok`, `journal_resets`, parametry P1, `service_s` (czas dla obsługi = licznik − suma przeskoków restartów), `boot_s`, `screen`, `lang`, `name` (`WICI-xxxxxx`: 6 cyfr skrótu tożsamości Reticulum; bez stosu z identyfikatora układu), `reset_reason` (RESETREAS), `store_ok`, `register`, `inbox`, `head` (ostatnie zdarzenie pierścienia), pola [węzła stanowiska](#węzeł-stanowiska) (`node`, `usb_open`, `usb_flow`, `usb_buffered`, `usb_pinned`, `usb_rns_in`, `usb_rns_out`, `usb_rx_drop`, `usb_rx_large`, `usb_tx_drop`, `usb_ready`, `usb_cmds`, `computer_s`: sekundy od ostatniego pakietu od komputera, −1 bez pakietu), `usb_data` (port danych otwarty), liczniki wierszy protokołu, `usb_boot`, `wdt_s` (czas watchdoga) i `board` (`wires` albo `N1`) |
| `RADIO` | `ready` (układ odpowiada), `partnumber` (CC1120 = `0x48`), `partversion`, `marcstate` i `marc` (nazwa stanu), stan z bajtu statusu, `p1_ok`, `ok` |
| `RESET` | reset sprzętowy RESET_N i `SRES` (kasuje rejestry P1, `p1_ok: false`), potem `RADIO` |
| `CONFIG` | zapis tablicy P1 w stanie IDLE, odczyt i porównanie 58 rejestrów (`checked`, `mismatches`, pierwszy niezgodny z wartością oczekiwaną i odczytaną), potem kalibracja; `config: true` tylko przy zerze niezgodności i udanej kalibracji |
| `VERIFY` | ponowne porównanie rejestrów z tablicą bez zapisu |
| `CAL` | ręczna kalibracja syntezera; podaje FS_VCO2, FS_VCO4, FS_CHP i FS_CAL2 po kalibracji; `p1_ok` zostaje `true` tylko po udanej kalibracji i zgodnej weryfikacji, a nieudana przywraca FS_CAL2 i przechodzi do IDLE |
| `FREQ` | słowo FREQ, FREQOFF, częstotliwość nośna w Hz ze wzoru z instrukcji, błąd wobec 869 525 000 Hz, krok FREQOFF oraz FREQOFF_EST z ostatniego odbioru |
| `RX [<len>]` / `IDLE` | odbiór ramek wzorcowych o długości `len` (4–103, domyślnie 103) z licznikami dla `RXPER`, tylko w trybie przygotowania i bez trwającej serii; albo przerwanie wszystkiego i IDLE; potem `STATE` |
| `PREP <0\|1>` | tryb przygotowania; włączenie wymaga przycisku OK w ciągu 30 s (na N1 zapasowo obok przycisku przygotowania); zmiana daje zdarzenie `station` `prep` |
| `SILENCE <0\|1>` | położenie przełącznika CISZA (na przewodach zamiast przełącznika; na N1 zapasowo do następnego przełączenia); zdarzenie `radio`; ciszę z panelu ustawia tylko polecenie USB `silence` |
| `TXCW <s> [CONDUCTED]` | nośna bez modulacji przez 1–10 s; po zakończeniu `tx_ms` i dług ciszy |
| `TXPKT <n> <len> [<ms>] [ZEROS\|ONES] [CONDUCTED]` | `n` ramek wzorcowych po `len` B (4–103) co `ms`, z wypełnieniem PN9 albo z samych zer (`ZEROS`) lub jedynek (`ONES`) między numerem a CRC; seria idzie w tle, na końcu `sent`, `failed`, `tx_ms`, czasy pierwszej ramki z GPIO2 |
| `RXPER` | zwraca i zeruje liczniki odbioru: `rx_ok`, `rx_bad`, `missing`, `reordered`, `overflow`, `per_percent`, średnie RSSI i LQI |
| `FOFF [<hz>]` | korekta częstotliwości w Hz (około ±1 MHz, krok 30,5 Hz) do restartu, tylko w trybie przygotowania i bez trwającej serii; bez argumentu odczyt |
| `P1RX` | odbiór ramek P1 w tle (zmienna długość, LEN do 102); każda ramka i złożony datagram jako wiersz JSON |
| `P1TX <hex>` | nadanie datagramu 1–600 B zapisanego szesnastkowo: fragmentacja, losowy identyfikator, dług ciszy, CCA, odroczenia; wynik w wierszu `p1tx` po zakończeniu |
| `P1` | liczniki łącza: ramki, datagramy, odrzuty, odroczenia, stan składania |
| `STOP` | przerwanie `TXCW`, `TXPKT`, `P1TX` i odbioru |
| `LOG [<n>]` | ostatnie `n` (domyślnie 16, do 64) zdarzeń z dziennika w FRAM, od najnowszego, z numerem i czasem pracy; bez FRAM do 16 ostatnich wpisów z RAM, też od najnowszego |
| `JOURNAL` | stan dziennika: rekord długu (numer, dług, czas zapisu, liczba poprawnych rekordów), licznik czasu pracy (numer, `uptime_s`, `skip_s` = suma przeskoków S, liczba startów), numer ostatniego zdarzenia, największy dług |
| `BENCH` | stan trybu przygotowania, ciszy, zadań i długu |
| `RSSI` | RSSI w dBm z przyjętym przesunięciem −99 dB (`rssi_offset_db`), znaczniki ważności i nośnej; sens tylko w stanie RX |
| `STATE` | stan MARC nazwą i liczbą, bajt stanu, liczba bajtów w kolejkach RX i TX |
| `REG <hex>` | odczyt rejestru z przestrzeni zwykłej (00–2E) albo rozszerzonej (2F00–2FFF), np. `REG 2F73` (MARCSTATE), `REG 2F0C` (FREQ2) |
| `FRAM` | rozpoznany układ (`MB85RS4MT`, `CY15B104Q`, `CY15B104QN` albo `unknown`), dziewięć bajtów RDID (MB85RS4MT: `047F4903…`, MB85RS4MTY: `047F490B…`, CY15B104Q: `7F7F7F7F7F7FC22608`, CY15B104QN-50SXI: `7F7F7F7F7F7FC22C00`; wersje 1,8 V CY15V104QN są odrzucane), rejestr stanu, `ok`; `spi_hz` to zegar FRAM (8 MHz na N1, 1 MHz na przewodach) |
| `BTN` | stan czterech przycisków (na N1 także panelu, patrz [N1](#płytka-nośna-n1-bench-n1)) |
| `LED <1-4> <0\|1>` | sterowanie diodą |
| `SCREEN` | treść ekranu: nazwa ekranu, język, pięć wierszy i które są odwrócone, liczba odświeżeń |
| `KEY <UP\|DOWN\|OK\|BACK> [ms]` | naciśnięcie przycisku z portu USB (próby bez dotykania płytki), z czasem przytrzymania 0–60 000 ms; odpowiedź jak `SCREEN` |
| `DISPLAY` | EXTCOMIN: `extcomin_ok` (licznik ruszył), licznik RTC2 albo MCPWM i stan pinu, tryb VCOM, liczba odświeżeń, numery pinów, zegar SPI ekranu `spi_hz` |
| `VCOM <0\|1>` | odwracanie VCOM bitem w poleceniach ekranu, tylko przy przewodach bez połączenia EMD (`bench-a`); na N1 błąd `VCOM: EXTMODE tied high on N1` |
| `REBOOT` | restart programowy; ekran i język wracają jak po restarcie przez watchdog |
| `STORE` | magazyny FRAM: konfiguracja (`role`, `config_seq`, adres wybranego obiektu, `addresses` i `selected` listy obiektów, aktywna tożsamość odbiorcy `receiver`, frazy, liczba stacji), `identity_saved`, epoka, `head`, `min`, `tomb_floor`, zajęte wpisy rejestru i skrzynki, nieprzeczytane, diagnostyka (`corrupt_slots`, `replayed`, `scrubbed`, `config_corrupt`), liczniki protokołu |
| `USB <wiersz JSON>` | wiersz protokołu danych podany przez port diagnostyki (próby z jednym terminalem); odpowiedź idzie na port danych, a gdy jest zamknięty, na diagnostykę |
| `APP` | warstwa aplikacji: wiadomości w drodze (najwyżej 2), liczniki nadanych, dostarczonych (dowód transportowy), nieudanych, odebranych, odrzuconych, pominiętych, pominiętych BULLETIN, nieprzyjętych z braku miejsca (`inbox_full`), usuniętych nieprzeczytanych BULLETIN (`evicted`), aktywne intencje, niewysłane, gniazdo do nadania |
| `LINK <0\|1>` | zatrzymanie i wznowienie nadawania zgłoszeń przez warstwę aplikacji (próby ręczne `P1TX` przy zatrzymanym); ruch własny stosu (ogłoszenia, dowody, odpowiedzi o trasę) idzie dalej |
| `RNS` | stos Reticulum: adres `wici.sa1` i skrót tożsamości, `online` (IFAC skonfigurowany), liczba tras, skrótów pakietów, wpisów tablicy ogłoszeń i potwierdzeń w toku, pula TLSF (`pool`, `pool_used`, `pool_peak`), system plików FRAM, liczniki pakietów, dowodów i ogłoszeń (`announced`), czas do następnego ogłoszenia, przewidywane oczekiwanie w kolejce radiowej (`wait_ms`), przepływność deklarowana (`bitrate`), kolejka interfejsu P1 (`q_len`, `q_held`, `q_full`, `ann_held`, `ann_drop`, `tx_sent`, `tx_failed`, `rx_ok`, `ifac_missing`, `ifac_invalid`, `offline`, `silenced` — pakiety wstrzymane ciszą, `k2_slot`, `k2_pool`, `k2_dest` — odrzucone K2, `pr_limited` — przekazywane zapytania o trasę ponad limit, `pool_ms` i `pr_ms` — czas kanału puli K2 z ogłoszeniami i zapytań o trasę w ostatniej godzinie), `identity_lost`, pola węzła stanowiska jak w `INFO` |
| `ANNOUNCE` | ogłoszenie adresu na polecenie; wychodzi w najbliższym obiegu poza ciszą radiową i z kodem IFAC, potem `RNS` |

Warunek przejścia kroku 6 z [lekcji R02](../hardware/r02/lekcje.md#uruchomienie): `RADIO` daje `ready: true`, `partnumber: 0x48` i stan `IDLE`; `FRAM` daje `ok: true`. Bez modułu `partnumber` wynosi `0xFF` albo `0x00`, a `ready` jest `false`. Po starcie obraz sam zapisuje i kalibruje P1; LED2 świeci dopiero, gdy `RADIO` daje `ok: true` i `p1_ok: true`. Po otwarciu portu obraz wysyła też wynik `VERIFY` i `FREQ`.

## Rejestry profilu P1

Tablica rejestrów jest w `src/p1_registers.h`, generowanym przez `tools/p1_registers.py` (test `tests/test_p1_registers.py` sprawdza, że nagłówek jest aktualny, a wartości zgadzają się ze wzorami i z eksportem TI). Wartości pochodzą z dwóch źródeł, oznaczonych w tablicy:

- **P1**: policzone z parametrów [profilu P1](../docs/spec/radio.md#profil-p1-do-prototypu) wzorami instrukcji [CC112x SWRU295E](https://www.ti.com/lit/ug/swru295e/swru295e.pdf): częstotliwość (równania 26–27), szybkość symboli (6–9), dewiacja (1–2), filtr odbiornika (10, tabela 17), moc (21), a także słowo synchronizacji, preambuła i silnik pakietów (rozdział 8 i 11).
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
- **Stała długość pakietu w tablicy.** Polecenia pomiarowe nadają ramki wzorcowe bez pola LEN, więc tablica ustawia stałą długość z PKT_LEN. Sterownik P1 przełączy układ na zmienną długość (LENGTH_CONFIG = 01, PKT_LEN = 102): od rozstrzygnięcia F79 pole LEN ramki P1 liczy BODY i CRC, czyli dokładnie to, co silnik pakietów odbiera po bajcie długości ([przegląd, F79](../docs/review.md)).
- **Kalibracja ręczna.** SETTLING_CFG wyłącza kalibrację automatyczną (jak w eksporcie TI); oprogramowanie wykonuje po zapisie rejestrów i po każdym `CAL` procedurę z erraty CC112x (dwa przebiegi `SCAL` z różnym VCDAC_START, zostaje wynik z większym FS_VCO2), przeniesioną z `manualCalibration()` w swrc253e.
- **Weryfikacja odczytem.** Każdy rejestr tablicy jest odczytywany po zapisie i porównywany z maską (XOSC1 ma bit tylko do odczytu). Pierwsza niezgodność trafia do odpowiedzi `CONFIG`/`VERIFY`.
- **GPIO modułu.** GPIO2 (D3) = PKT_SYNC_RXTX (pakiet w powietrzu, do pomiaru czasu TX), GPIO0 (D2) = RXFIFO_THR_PKT (koniec odebranego pakietu); niepodłączone GPIO1 i GPIO3 w trybie analogowym jak w eksporcie TI.
- **Odbiornik z niską IF** 62,5 kHz (wartość domyślna) z kompensacją obrazu, bo warunek IF > 2 × 25 kHz i IF + 12,5 kHz ≤ 100 kHz jest spełniony; zero-IF nasycałoby RSSI przy około −50 dBm.

Czego tablica nie zamyka: błędu częstotliwości kwarcu modułu (mierzy się `FREQ`/`FOFF` na stanowisku), przesunięcia RSSI i progu CCA (T4), dopasowania filtru DC, AGC i progu synchronizacji do 4800 Bd (eksport TI dotyczy 1200 Bd w tym samym paśmie; różnice sprawdza pomiar czułości w T4) oraz wartości z nowszej wersji SmartRF Studio (eksport z pakietu z 2013 r.; przy dostępie do narzędzia porównać tablicę z eksportem dla P1 i wpisać wersję narzędzia do nagłówka).

## Polecenia pomiarowe

Kontrakt jest w [specyfikacji radia](../docs/spec/radio.md#usb-do-laptopa); kod w `src/measure.cpp`. Polecenia działają tylko w trybie przygotowania (`PREP 1`, potwierdzony przyciskiem OK, bo na stacji włącza go przycisk pod plombowaną pokrywą) i są odrzucane w ciszy radiowej (`SILENCE 1`; cisza włączona w trakcie przerywa każdą serię, także przewodową, bo cisza blokuje każde nadawanie). Wymagają też skonfigurowanego radia (`p1_ok`; inaczej błąd `radio not configured: CONFIG`). Odpowiedzi odmowne mają pole `error`.

Limit nadawania na stanowisku: po każdej serii obowiązuje dług ciszy 12 × czas nadawania (jak w P1), widoczny w `INFO` jako `tx_wait_ms`, a seria bez argumentu `CONDUCTED` nie może przekroczyć 1,4 s czasu nadawania, czyli najdłuższego datagramu P1 (7 ramek po 103 B z narastaniem mocy). Specyfikacja nie podaje tej liczby wprost; to przyjęta interpretacja. `CONDUCTED` znosi oba ograniczenia wyłącznie do nadawania przewodowego do tłumika lub obciążenia sztucznego: obraz prosi o przycisk OK, czeka na niego do 30 s (LED1 miga szybko) i zapisuje potwierdzenie albo jego brak w dzienniku `LOG`. Dług jest zapisywany w [dzienniku FRAM](#dziennik-i-magazyny-w-fram) przed pierwszą ramką serii; błąd zapisu albo brak FRAM blokuje nadawanie radiowe. Seria `CONDUCTED` (do obciążenia, bez emisji) nie tworzy długu.

- **`TXCW`** przełącza układ na 2-FSK z dewiacją 0, dane z generatora PN9 i pakiet nieskończony, więc wychodzi sama nośna; po czasie albo po `STOP` przywraca rejestry P1. Przerwana wcześniej (`STOP`, cisza) zapisuje dług od nowa z rzeczywistego czasu nadawania. Do pomiaru częstotliwości (potem `FOFF`) i mocy.
- **`TXPKT`** nadaje ramki wzorcowe (`src/testframe.cpp`): numer porządkowy 2 B, wypełnienie PN9 zależne od numeru, na końcu CRC-16 ramki P1; test na komputerze (`tests/test_firmware_host.py`) porównuje CRC i ramkę z modelem. Dla pierwszej ramki obraz mierzy z GPIO2 (PKT_SYNC_RXTX) czas od `STX` do słowa synchronizacji (`lead_ms`: ustalenie syntezera, narastanie, preambuła), czas pakietu w powietrzu (`on_air_ms`, oczekiwane `len` × 8 / 4800) i ogon do IDLE (`tail_ms`); to wejście do parametru `ramp_ms` modelu. Bez przewodu na D3 jest `sync_gpio: false` i odpowiedź podaje tylko `tx_ms` (czas serii ze stanu MARC).
- **`RX <len>`** (tryb przygotowania, bez trwającej serii) ustawia stałą długość pakietu i odbiór ciągły; obraz czyta kolejkę co 5 ms, sprawdza CRC i numer, a `RXPER` zwraca liczniki i je zeruje. `missing` to luki w numeracji, `reordered` numer nie większy od poprzedniego, `overflow` przepełnienia kolejki. `rssi_avg_dbm` używa przyjętego przesunięcia −99 dB.
- **`FOFF`** (tryb przygotowania, bez trwającej serii) przelicza Hz na FREQOFF (równanie 27 instrukcji), zapisuje w IDLE i wraca do odbioru, jeśli trwał; wartość spoza zakresu daje `FOFF outside the radio range (about +-1 MHz)`. Po `CONFIG` wartość jest zapisywana ponownie, po `RESET` lub restarcie znika.

Przebieg pomiaru czułości: na nadajniku `PREP 1`, `TXPKT 2000 103 50 CONDUCTED`; na odbiorniku `PREP 1`, `RX 103`, po serii `RXPER`. PER ≤1% przy 2000 ramek oznacza najwyżej 20 ramek w `rx_bad` plus `missing`.

## Dziennik i magazyny w FRAM

Kod w `src/journal.cpp` (jawny obszar: dług ciszy, licznik czasu, ustawienia, rezerwacja numerów zapisu, rekord formatu, dziennik zdarzeń) i `src/store.cpp` (magazyny o stałych gniazdach z transakcjami), oba bez zależności od Arduino i sprawdzane na komputerze z pamięcią w RAM w `tests/test_firmware_host.py`, oraz `src/fram.cpp` (odczyt i zapis FRAM 4 Mbit, adres 3-bajtowy; `src/fram_id.h` rozpoznaje po RDID RAMXEED MB85RS4MT i Infineon CY15B104Q, kandydata A z BOM stacji, a inne układy, także 2 Mbit, odrzuca). Wymagania: [pamięć FRAM](../docs/spec/oprogramowanie.md#pamięć-fram), [trwałość i potwierdzenia](../docs/spec/oprogramowanie.md#trwałość-i-potwierdzenia), [zapisy większe niż transakcja](../docs/spec/oprogramowanie.md#zapisy-większe-niż-transakcja), [czas](../docs/spec/oprogramowanie.md#czas) i [dostęp do kanału](../docs/spec/radio.md#dostęp-do-kanału) (dług ciszy).

| Obszar | Adres w FRAM | Rozmiar | Treść |
|---|---|---|---|
| dług ciszy | 0x00000 | 32 × 24 B | numer, dług [ms], licznik przy zapisie, CRC-16, znacznik zatwierdzenia |
| licznik czasu | 0x00300 | 32 × 24 B | licznik [s], suma przeskoków restartów S [s], liczba startów |
| ustawienia ekranu | 0x00600 | 32 × 24 B | język + 1, znaczniki (wyciszenie, obiekt z listy adresów) |
| rezerwacja numerów zapisu | 0x00900 | 32 × 24 B | górna granica bloku 1024 numerów, zapisywana przed użyciem pierwszego numeru bloku |
| format FRAM | 0x00C00 | 32 × 24 B | `fram_format` (1), stan (zainicjowana, w trakcie ZNISZCZ DANE), znacznik zapisanej tożsamości |
| dziennik zdarzeń | 0x01000 | 512 × 64 B | numer, licznik, tekst do 53 znaków, CRC-16 |
| rekordy transakcji | 0x09000 | 2 × 4 KiB | nagłówek, do 7 par (adres, rekord 512 B), znacznik zatwierdzenia, znacznik wykonania |
| konfiguracja | 0x0B000 | 2 × 8 KiB | kopie A i B: nagłówek, długość i SHA-256 dokumentu `configure`, dokument do 7680 B, znacznik |
| meta | 0x0F000 | 512 B | epoki pierścienia i danych, `ring_base`, `tomb_floor`, aktywna kopia konfiguracji i `config_seq`, aktywna tożsamość odbiorcy, cisza z panelu i wyjątek, WSTRZYMAJ TEST, ostatni kontakt, para ostatniego `close`, granice zbioru powtórzeń BULLETIN, 8 ostatnich `nonce` polecenia `test` |
| zbiór powtórzeń BULLETIN | 0x0F200 | 4 × 512 B | 64 wpisy (przedrostek id, `event`, tożsamość odbiorcy) |
| rejestr zgłoszeń | 0x10000 | 256 × 512 B | wpis: typ, pochodzenie, id, `r_max`, `r_rcv`, etap, `nadane`, decyzja i jej rewizja, liczniki STATUS i REPLY, próby, czasy, COMMIT do 8 niepotwierdzonych rewizji, `nonce`, treść SA1 rewizji `r_max` |
| skrzynka | 0x30000 | 128 × 512 B | REPLY i BULLETIN: źródło, id, `event`, numer `msg`, czas odbioru, przeczytana, treść SA1 |
| pamięć zwolnionych wpisów | 0x40000 | 16 × 512 B | 256 wpisów (id, `r_max`, numer zdarzenia `released`, krótki numer, znacznik anulowania) |
| pierścień zdarzeń | 0x42000 | 16 × 512 B | 256 zdarzeń 24 B dla laptopa (bez treści SA1, którą `event` bierze z rejestru albo skrzynki) |
| tożsamość Reticulum (`src/framfs.cpp`) | 0x44000 | 2 × 128 B | klucz prywatny 64 B, numer, CRC-16; nowszy z dwóch slotów ([stos](#tożsamość-i-tablice-w-fram)) |
| system plików stosu | 0x48000 | 224 KiB | tablica tras, znane tożsamości, buforowane ogłoszenia (magazyny microStore) |

Zasady:

- **Małe rekordy dziennika.** Rekord trafia do najstarszego slotu pierścienia najpierw z zerowym znacznikiem, potem zapisywany jest znacznik zatwierdzenia, a na końcu rekord jest odczytywany i porównywany; zanik zasilania w trakcie zostawia poprzedni. Nowa pamięć (same 0x00 albo 0xFF) nie daje fałszywych rekordów; rekordy niepuste i niepoprawne bez żadnego poprawnego to uszkodzenie, a nie nowa stacja.
- **Dług przed serią.** `TXCW` i `TXPKT` zapisują 12 × zaplanowany czas nadawania przed pierwszą ramką; po odczekaniu obraz zapisuje rekord z długiem 0 („silence debt cleared”). Po restarcie odczekiwany jest cały ostatni zapisany dług (`INFO` → `tx_wait_ms`). Brak poprawnego rekordu długu: obraz odczekuje `MAX_DEBT_MS` = 16 800 ms (12 × 1,4 s; test sprawdza, że nie jest mniejszy od 16 228 ms z modelu dla datagramu 600 B), zakłada nowy dziennik i podaje `journal_resets: 1`.
- **Czas.** Przy starcie licznik i S rosną o 60 s i są zapisane, zanim stacja nada ramkę albo utworzy rekord (`startClock`); potem licznik co 60 s. Czas dla obsługi = licznik − S: tak liczone są czasy w rekordach, `at` zdarzeń, alarmy i ponowienia, więc po restarcie czas nie cofa się wobec żadnego zapisu, a przeskok nie zawyża czasów. Kontakt z odbiorcą sprzed tego startu jest dolnym oszacowaniem (`kontakt_ponad_krotki`, `last_contact_lower`). Nieudany zapis licznika gasi LED3 i `journal_ok`.
- **Gniazdo magazynu** (512 B): nagłówek 24 B (magazyn, gniazdo, wersja formatu, generacja klucza 0, numer zapisu, długość), treść do 464 B, miejsce na znacznik AEAD 16 B (zera, rekordy nie są jeszcze szyfrowane) i znacznik zatwierdzenia (CRC-32 bajtów 0..503 i stała). Gniazdo puste jest wolne, rekord „wolne” niesie generację gniazda (zdarzenia z niezgodną generacją wychodzą do laptopa z `"lost":true`), a rekord niepusty z błędnym znacznikiem, magazynem, gniazdem albo wersją jest uszkodzeniem: gniazdo wypada z użycia (`corrupt_slots`) i nigdy samo nie staje się wolne.
- **Transakcja.** Każda zmiana gniazd (także jednego pola) idzie przez rekord transakcji z pełnymi nowymi bajtami wszystkich zmienianych gniazd, bloków pierścienia zdarzeń, pamięci zwolnionych, zbioru powtórzeń i meta, potem znacznik zatwierdzenia (COMMIT), przepisanie do gniazd i znacznik wykonania. Po restarcie zatwierdzona, niewykonana transakcja jest wykonywana ponownie tymi samymi bajtami (`replayed`), niezatwierdzona odrzucana. Dwa rekordy transakcji na zmianę; numer zapisu rośnie i nie wraca (rezerwacja blokami 1024 w dzienniku). Indeksy w RAM zmieniają się dopiero po wykonaniu.
- **Konfiguracja.** Dokument `configure` trafia częściami do nieaktywnej kopii; `xfer_commit` sprawdza rozmiar i SHA-256, rozbiera dokument wprost z FRAM porcjami po 64 B (bez kopii 7,5 KB w RAM, `src/config.cpp`), zapisuje nagłówek i znacznik kopii, a jedna transakcja meta przełącza wskaźnik kopii i dodaje zdarzenie `station` `config`. Przy starcie aktywna kopia jest sprawdzana tak samo; nieczytelna zostawia stację bez konfiguracji (`config_corrupt`), nigdy z częściową.
- **Epoki.** Meta ma dwie: epokę pierścienia zdarzeń (`epoch` protokołu USB, numeracja od `ring_base` + 1) i epokę danych (rejestr, skrzynka, pamięć zwolnionych). **ZAMKNIJ ZDARZENIE** to jedna transakcja meta z nowymi obiema; rekordy rejestru, skrzynki, pamięci zwolnionych i pierścienia starej epoki są od razu niewidoczne, a `maintain()` w pętli stacji nadpisuje je rekordami „wolne” po 3 gniazda na transakcję, także po restarcie (`scrubbed`). Konfiguracja, meta i zbiór powtórzeń BULLETIN zostają.
- **Rekordy uszkodzone** ([specyfikacja](../docs/spec/oprogramowanie.md#pamięć-fram)): gniazdo rejestru albo skrzynki z błędnym znacznikiem jest wyłączone z użycia; uszkodzony blok przy starcie daje jedną transakcję naprawczą: pierścień zdarzeń dostaje nową epokę z numeracją dalej o 16 (laptop pobiera migawkę), pamięć zwolnionych podnosi `tomb_floor` za bieżący numer, zbiór BULLETIN podnosi `bulletin_floor` do najwyższego przyjętego `event`; `maintain()` zapisuje uszkodzone bloki od nowa. Uszkodzone meta albo rekord formatu zatrzymują magazyny bez formatowania.
- **ZNISZCZ DANE**: stan „w trakcie” w rekordzie formatu, zera w 0x09000–0x7FFFF (magazyny, tożsamość, system plików stosu), skasowanie dziennika zdarzeń, licznika i ustawień, nowy pusty magazyn bez znacznika tożsamości; przerwane kasowanie wznawia start. Dług ciszy, rezerwacja numerów zapisu i rekord formatu zostają.
- **Start.** Inna wersja `fram_format`, nieczytelny rekord formatu albo meta albo dane bez rekordu formatu zostawiają stację bez magazynu (`STORE` → `store_ok: false`, ekran bez kreatora); naprawą jest ZNISZCZ DANE. Stacja nie tworzy sama pustego magazynu w miejsce uszkodzonego.

Indeksy w RAM (rejestr 256 wpisów, skrzynka 128, pamięć zwolnionych i zbiór powtórzeń; razem z konfiguracją 19,3 KB) mają tylko pola potrzebne kolejce, listom ekranu i alarmom; treść SA1 i pełne `id` czyta się z rekordu. Rekordy nie są szyfrowane (AEAD z kluczem w chronionej pamięci MCU przyjdzie razem z ochroną klucza tożsamości, [etap LXMF](#co-zostaje-na-etap-lxmf)).

## Łącze P1

Kodek i składanie ramek są w `src/p1frame.cpp` (bez zależności od Arduino): fragmentacja datagramu do 600 B na ramki `LEN | BODY | CRC` z LEN liczącym BODY i CRC (F79), rozbiór ramki z pełną kontrolą pól i składanie według [specyfikacji radia](../docs/spec/radio.md#ramka-w-eterze): 8 prób po 120 s, poprawne duplikaty pomijane, sprzeczny duplikat albo zmiana liczby fragmentów lub długości usuwa próbę, przy przepełnieniu odpada próba z najmniejszą liczbą fragmentów, 16 ostatnio złożonych identyfikatorów odrzuca spóźnione duplikaty. Test na komputerze (`tests/test_firmware_host.py`) porównuje ramki z modelem bajt po bajcie dla wszystkich długości 1–600 B i odtwarza przypadki wrogie z testów modelu.

Łącze w `src/measure.cpp`, wspólne dla A i B; opis odbioru i CCA dotyczy CC1120, różnice S2-LP są w [sterowniku łącza](#sterownik-łącza-s2-lp):

- **Odbiór** (`P1RX`): układ w trybie zmiennej długości z PKT_LEN = 102, więc ramki dłuższe odrzuca sam; obraz czyta bajt LEN, czeka na resztę ramki i dwa bajty statusu (RSSI, LQI), rozbiera ramkę i oddaje ją składaniu. Ramki za krótkie, niekompletne w czasie albo z błędem rozbioru liczą się jako `rx_bad`. Każda ramka daje wiersz `p1rx` ze stanem składania, a złożony datagram wiersz z identyfikatorem i danymi szesnastkowo.
- **Nadawanie** (`P1TX`): datagram czeka na koniec długu ciszy, potem 50 ms wolnego kanału (RSSI poniżej progu −100 dBm przy przyjętym przesunięciu RSSI, brak odbioru po słowie synchronizacji na GPIO2 i żadna ramka odebrana w tym czasie; przerwa między próbkami ponad 10 ms zaczyna okno od nowa, a ostatnia próbka i nadanie idą w tym samym obiegu). Zajęty kanał odracza nadanie o losowe 100–1000 ms (`deferrals`; łączne czekanie ponad 1 s liczy się jako `long_deferrals`), po 30 odroczeniach datagram jest odrzucany (`tx_drop`; liczba jest wyborem stanowiska, specyfikacja nie podaje limitu). Przed pierwszą ramką do dziennika trafia dług 12 × zarezerwowany czas serii (liczony dla najdłuższych ramek), potem fragmenty idą jedną serią, a odbiór wraca od razu po serii. Cisza radiowa i `STOP` przerywają i odrzucają nadanie (`tx_drop`). Identyfikator datagramu i czas odroczeń pochodzą z generatora stacji (HMAC-DRBG, [stos](#stos-reticulum)).
- **Dwie płytki**: na obu `P1RX`; na jednej `P1TX 48656C6C6F` („Hello”); druga wypisuje `p1rx` z `datagram`. Datagram 600 B to 7 ramek i około 1,4 s nadawania, po nim około 16,4 s długu (rezerwacja: 7 ramek pełnej długości × 12).

Złożone datagramy idą do [interfejsu P1 stosu Reticulum](#interfejs-p1), a koniec serii zwalnia jego kolejkę; `P1RX` i `P1TX` zostają jako polecenia pomiarowe (datagram `P1TX` bez IFAC stos po drugiej stronie odrzuca). Podział czasu kanału na klasy K0–K2 jest w [interfejsie P1](#interfejs-p1).

## Ekran i przyciski

Wymagania: [ekran i przyciski stacji](../docs/spec/oprogramowanie.md#ekran-i-przyciski-stacji) i tabela tekstów ekranu w tym samym rozdziale. Kod w trzech warstwach:

- **Teksty** (`src/ui_texts.h`, generowany przez `tools/ui_texts.py`): wszystkie tabele rozdziału „Teksty ekranu” (teksty z identyfikatorami, pozycje menu, przyciski, kategorie, gotowe frazy) w trzech językach, jednostki `[czas]` i separator dziesiętny z opisu. Test `tests/test_ui_texts.py` odrzuca nieaktualny nagłówek i sprawdza limity 20 znaków pozycji menu i kategorii.
- **Font** (`src/font_glyphs.h`, generowany przez `tools/font_bitmap.py` z `fonts/DejaVuSansMono-Bold.ttf`): 182 glify po 20 × 40 px (ASCII, alfabet polski i ukraiński, każdy znak tekstów kanonicznych, U+FFFD jako glif zastępczy), 33 px kroju o stałej szerokości, pięć wierszy po 20 znaków z krokiem 48 px na ekranie 400 × 240. Licencja fontu (Bitstream Vera, zmiany DejaVu w domenie publicznej) jest w `fonts/LICENSE.txt` i `LICENSES/`; wygenerowana bitmapa zachowuje tę licencję na kształty liter. Wersaliki mają 24 px, czyli **3,5 mm** na panelu LS027B7DH01 (58,8 mm szerokości), jak wymaga specyfikacja (≥3,5 mm, [przegląd, F80 i F101](../docs/review.md)).
- **Model ekranu** (`src/ui.cpp`, bez zależności od Arduino, sprawdzany na komputerze w `tests/test_firmware_host.py`): daje pięć wierszy UTF-8 obciętych do 20 znaków i znacznik wiersza odwróconego; rysowanie i przyciski są poza nim. Ekrany: wybór języka (POLSKI, УКРАЇНСЬКА, ENGLISH; tych nazw nie ma w kanonicznej liście tekstów, F80), ekran główny (`radio_wlaczone`, `kontakt_ponad_krotki` z czasem pracy jako dolnym oszacowaniem, `zasilanie_12v`, `kolejka_krotki` albo pusty wiersz, `nowe_krotki`), cisza (`cisza` w wierszach 1–3, potem zasilanie i kolejka), menu (ZGŁOSZENIE, WIADOMOŚCI, TEST, STAN, JĘZYK/МОВА/LANGUAGE; wybrana pozycja odwrócona, bo znak kursora nie mieści się obok etykiet 20-znakowych), STAN z przewijaniem GÓRA/DÓŁ (radio, liczniki łącza, dług ciszy, `ostatni_kontakt_ponad`, zasilanie, odchyłka częstotliwości z FREQOFF_EST, wersja, nazwa `WICI-xxxxxx`), JĘZYK; w [węźle stanowiska](#węzeł-stanowiska) ekran główny `radio_wlaczone`, `komputer_osp` albo `komputer_brak`, zasilanie, menu tylko STAN i JĘZYK. W trybie przygotowania wiersz 1 każdego ekranu to `tryb_przygotowania`, a lista zajmuje cztery wiersze. Test sprawdza krótkie formy z największymi wartościami (99 MIN, 128 zgłoszeń, 128 wiadomości) we wszystkich językach, łamanie `cisza` na trzy wiersze, format `[czas]` (99 MIN → 1 H → 47 H → 2 D → 99 D) i pokrycie glifami każdego znaku tekstów.
- **Sterownik ekranu** (`src/sharp.cpp`): bufor 240 × 50 B, zapis tylko zmienionych wierszy poleceniem M0 (bity LSB-first, CS aktywny stanem wysokim, 2 MHz, na N1 1 MHz, 8 bitów odstępu po wierszu i 16 na końcu). **EXTCOMIN** generuje licznik RTC2 (preskaler 4095, COMPARE0 = 4, czyli 0,5 s) przez PPI do zadania GPIOTE przełączającego pin i do zerowania licznika: przebieg 1 Hz bez udziału programu i bez HFCLK, jak wymaga specyfikacja; `DISPLAY` pokazuje licznik i stan pinu. `VCOM 1` odwraca VCOM bitem w poleceniu co 500 ms tylko przy przewodach bez połączenia EMD (pin EMD płytki 4694 w stanie niskim); na N1 zwraca błąd. `Display::begin()` zwraca `false`, gdy licznik EXTCOMIN nie ruszył; na N1 program podaje wtedy DISP = L. Przyciski są odpytywane co 10 ms (zbocze = naciśnięcie). Ekran jest przeliczany w najbliższym obiegu pętli po zmianie danych (kilka zmian w jednym obiegu daje jedno przerysowanie) oraz co 200 ms; do panelu idą tylko zmienione wiersze.

Po włączeniu zasilania pierwszym ekranem jest wybór języka; wybór i każda zmiana ekranu trafiają do pamięci RAM niezerowanej przy starcie (sekcja `.noinit`), a zmiana języka także do pierścienia ustawień w FRAM. Po restarcie programowym (`REBOOT`) albo przez watchdog stacja wraca bez pytania do języka sprzed restartu i do menu albo ekranu STAN, jeśli był otwarty; z pozostałych ekranów (kreator, listy, alarm) wraca do ekranu głównego. Na nRF52840 sekcja `.noinit` jest typu NOBITS za `.bss`, więc kod startowy jej nie zeruje; czy bootloader Adafruit nie nadpisuje tego obszaru przy restarcie, trzeba sprawdzić na płytce. Watchdog sprzętowy (60 s, dłużej niż potwierdzenie przyciskiem) jest odświeżany w każdym obiegu pętli stacji i zatrzymuje się, gdy debugger zatrzyma rdzeń; restart przez watchdog trafia do dziennika zdarzeń (`RESETREAS`). Radio startuje niezależnie od ekranu, jak wymaga specyfikacja.

Przyjęte interpretacje i braki: pasek trybu przygotowania zastępuje wiersz 1 („stale pokazuje”); przy niesprawnym radiu wiersz 1 to `radio_awaria`, ale alarm, którego wymaga specyfikacja, jeszcze nie działa; zasilanie to `12 V: 0,0 V`, bo stanowisko nie mierzy napięcia; etykiety liczników w STAN (`RX OK`, `TX`, `DEFER`, `WAIT`, `FOFF`) są jednakowe we wszystkich językach. Nie ma podświetlenia (płytka 4694 go nie ma); sygnał dźwiękowy i dioda alarmu są tylko na N1 (patrz [N1](#płytka-nośna-n1-bench-n1)), sygnału nowej wiadomości nie ma.

### Ekrany stacji

Przepływy ekranów są w modelu (`src/ui.cpp`), a dane i działania dostarcza mu `src/console.cpp` (interfejs `ui::Host`) nad magazynem FRAM i warstwą aplikacji; `tests/test_firmware_host.py` uruchamia model z magazynem w RAM i sprawdza każdy przepływ na tekstach kanonicznych. Przyciski: GÓRA, DÓŁ i OK działają przy naciśnięciu, WSTECZ przy zwolnieniu, bo przytrzymanie WSTECZ ma inne znaczenie (2 s w kreatorze: `porzucic`; 3 s poza nim: wybór języka).

| Ekran | Działanie |
|---|---|
| start | po wyborze języka przy liście obiektów najpierw lista do wyboru (GÓRA, DÓŁ, OK; WSTECZ = żaden: `adres_brak`), potem `adres_kontrola` z adresem wybranego obiektu (WSTECZ = NIE: przy liście powrót do listy, przy jednym adresie albo braku adresu `adres_brak`); wybrany obiekt idzie do nowych zgłoszeń i TEST z przycisków i laptopa, rewizja zachowuje lokalizację zgłoszenia, a wybór przetrwa restart (rekord ustawień); potem propozycja TEST startowego: OK planuje TEST z losowym opóźnieniem w oknie 50 s × liczba stacji z `configure` (bez niej 15 min) i pokazuje `test_zaplanowany`; WSTECZ pomija |
| ZGŁOSZENIE | kategoria 0–9 → liczba osób z listy 1, 2, 5, 10, 20, 50, 100, INNA (wpis setek, dziesiątek i jednostek; przytrzymanie przycisku powtarza zmianę co 150 ms; domyślnie ostatnio użyta wartość) → pilność bez wartości domyślnej (`pilnosc_2` wymaga `pilnosc_2_potw`) → fraza z konfiguracji albo domyślna lista (kategoria 9 bez pozycji „brak”) → podsumowanie z `podsumowanie_klawisze` → wynik: `zapisane_w_stacji` albo `zapisane_w_ciszy` z `zapisz_numer`, `kolejka_pelna`, `blad_pamieci`, `adres_brak`. WSTECZ cofa o krok; szkic zostaje po powrocie do ekranu głównego. Zgłoszenie dostaje `location` z adresu konfiguracji, id z generatora stacji losowane ponownie, dopóki krótki numer (pierwsze 16 bitów modulo 10 000) jest zajęty w rejestrze albo w pamięci zwolnionych wpisów |
| WIADOMOŚCI | lista najnowszych najpierw: własne zgłoszenia i TEST w najnowszej rewizji (`NNNN` i kategoria), odpowiedzi i komunikaty (`*` przed nieprzeczytaną treścią). Własne: etap z rejestru (`zapisane_w_stacji`, w ciszy `zapisane_w_ciszy`; `wysylanie` z próbą i czasem do następnej przy `wysyłanie` i `nadane`; po `odebrane` decyzja odbiorcy `stan_1`…`stan_6`, a gdy przyszła po etapie, dopisana za nim), kategoria, liczba osób i pilność, fraza w wybranym języku, `zapisz_numer`; OK otwiera ZMIEŃ LICZBĘ OSÓB, ZMIEŃ PILNOŚĆ, POTRZEBA USTAŁA (nowa rewizja tego samego id) i ANULUJ WYSYŁKĘ (tylko do pierwszego `nadane` rewizji; anulowane znika z listy). Odebrane: `odpowiedzi_po_polsku` (UK, EN), treść, czas od odbioru, dla komunikatu `stopka_komunikatu`; otwarcie oznacza jako przeczytane |
| TEST | `test_zaplanowany` (WSTECZ anuluje), `test_wyslany`, stan po RECEIVED/STATUS albo `test_wstrzymany`; OK otwiera menu TEST (nadanie od razu) i WSTRZYMAJ (anuluje czekający TEST i blokuje nadawanie TEST) / WZNÓW |
| STAN | wiersze stanu z kursorem, na końcu PRZEKAZANIE ZMIANY (otwarte zgłoszenia z etapem bez zakończonych decyzją 6, nieprzeczytane, cisza, zasilanie) i USŁUGI: OGŁOŚ ADRES (ogłoszenie stosu jak `ANNOUNCE`, wynik `adres_ogloszony`, w ciszy radiowej ogłoszenie czeka na jej koniec; bez działającego stosu `adres_nie_ogloszony`), WYCISZ DŹWIĘK / WŁĄCZ DŹWIĘK (znacznik w pierścieniu ustawień FRAM, przetrwa restart; `dzwiek_wyciszony` w STAN, PRZEKAZANIE ZMIANY i w wierszu 4 ekranu głównego przy pustej kolejce; brzęczyka jeszcze nie ma), KLUCZ ZAPASOWY (`klucz_zapasowy`; nieodwracalne, zdarzenie `station` dla laptopa; wysyłka bez decyzji idzie do zapasowej tożsamości z karty, czekające próby wracają od razu) i ZNISZCZ DANE (`zniszcz_ostrzezenie`; jak `destroy` z laptopa: magazyny, konfiguracja, dziennik zdarzeń, tożsamość i tablice stosu; zostaje tylko dług ciszy; potem restart); dwie ostatnie wymagają sekwencji GÓRA, DÓŁ, GÓRA, OK, inny przycisk zaczyna od nowa |
| węzeł stanowiska | po wyborze języka od razu ekran główny (bez kontroli adresu i TEST): `radio_wlaczone`, `komputer_osp` (czas od ostatniego pakietu od komputera stanowiska) albo `komputer_brak` (żadnego od startu), zasilanie, `dzwiek_wyciszony` po wyciszeniu; w ciszy `cisza` w wierszach 1–3, potem zasilanie i komputer. Menu: STAN i JĘZYK. STAN: liczniki łącza, `USB IN`, `USB OUT`, `USB DROP` (pakiety Reticulum przez USB), kontakt z komputerem, zasilanie, wersja, nazwa i USŁUGI z WYCISZ DŹWIĘK i ZNISZCZ DANE; bez PRZEKAZANIA ZMIANY, OGŁOŚ ADRES i KLUCZ ZAPASOWY |
| potwierdzenie | pytanie polecenia laptopa (`pytanie_cisza_wlacz`, `pytanie_cisza_wyjatek` z krótkim numerem, `pytanie_cisza_wylacz`, `pytanie_zamknij`, `pytanie_zniszcz`) albo odcisk karty (`odcisk_klucza`): OK = TAK, WSTECZ = NIE, po 30 s odmowa; nie przerywa go alarm ani powrót po bezczynności |
| alarm | `brak_potwierdzenia` po 15 min / 1 h / 6 h od zapisu według pilności (TEST: 30 min od nadania) i `brak_odczytu` 30 min po `odebrane` najwyższej rewizji dla pilności 2; zajmuje cały ekran, OK potwierdza (alarm tego zgłoszenia nie wraca), `zapisz_numer` wskazuje zgłoszenie |

Braki tego kroku: przypomnienie `wymien_ogniwa` (bez pomiaru ogniw), powrót ekranu alarmu po wybudzeniu (bez podświetlenia).

## Przeglądy kodu

Wcześniejsze przeglądy (po kroku ekranów i po wejściu stosu, 2026-10) poprawiły stos zadania stacji (osobne zadanie FreeRTOS z 16 KB stosu), sterowniki radia, CCA, limity ogłoszeń i potwierdzeń stosu, kontrolę argumentów portu diagnostyki i ucieczki JSON; ich opis jest w historii repozytorium.

### Dostosowanie do specyfikacji F106 (F107)

Kod stacji przepisano pod obecną specyfikację ([przegląd, F107](../docs/review.md)):

- **Magazyny w FRAM** ([dziennik i magazyny](#dziennik-i-magazyny-w-fram)): gniazda 512 B z nagłówkiem i znacznikiem zatwierdzenia zamiast kolejki intencji, transakcje na dwóch obszarach 4 KiB odtwarzane przy starcie, epoki z ZAMKNIJ ZDARZENIE i sprzątaniem, konfiguracja w dwóch kopiach, pamięć zwolnionych wpisów, pierścień zdarzeń.
- **Cykl życia zgłoszenia** ([warstwa aplikacji](#warstwa-aplikacji-nad-stosem)): rejestr z etapami `zapisane` → `wysyłanie` → `nadane` → `odebrane`, decyzja odbiorcy osobno, 2 własne wiadomości w drodze, ANULUJ WYSYŁKĘ do pierwszego nadania.
- **Protokół USB `"usb":2`** ([protokół](#protokół-usb-laptopstacja)): koperta `seq`/`re`, `hello`, pierścień zdarzeń z epoką i oknem 8, `snapshot`, transfery `xfer_*`, potwierdzenia przyciskiem bez blokowania pętli (ekran pytania).
- **Cisza radiowa z wyjątkiem**: wymiana jednej pary (id, revision) przechodzi przez interfejs P1 (pakiet, zapytanie o trasę, dowody RECEIVED i STATUS), ogłoszenia, ruch przekazywany, pomiary i `P1TX` czekają ([stos](#interfejs-p1)).
- **Karta odbiorcy z kluczami**: tożsamości odbiorcy z kluczy publicznych karty, bez czekania na ogłoszenie; cel K1 kolejki P1 to aktywna tożsamość.
- **Klasy K0–K2** czasu kanału zamiast rezerwy 50%.
- **Generator stacji** (HMAC-DRBG SHA-256, `src/drbg.cpp`) z 48 B ze źródła sprzętowego; na ESP32-S3 źródło przy włączonym `bootloader_random_enable`, bo bez radia Wi-Fi `esp_fill_random` nie ma szumu; generator wmieszany w generator stosu przed utworzeniem tożsamości.
- **Unicode SA1**: NFC i znaki nieprzydzielone z tablic Unicode 16.0 (`src/unicode_tables.h`, `tools/unicode_tables.py`) także dla wiadomości z radia.
- **Tożsamość**: znacznik zapisanej tożsamości w rekordzie formatu (ustawiany po każdym starcie z kluczem bez znacznika); brak klucza przy znaczniku zatrzymuje stos (`identity_lost`) zamiast tworzyć nową tożsamość.
- **Rekordy uszkodzone** według [tabeli specyfikacji](../docs/spec/oprogramowanie.md#pamięć-fram) (F108): osobna epoka pierścienia i danych, odtworzenie bloków pierścienia, pamięci zwolnionych i zbioru BULLETIN ([dziennik i magazyny](#dziennik-i-magazyny-w-fram)).

Usunięto martwy i powielony kod (`statusAfter`, kasowanie klucza w `framfs`, generator sprzętowy w `measure`, dwie kopie odczytu pól szesnastkowych JSON, wstawianie do skrzynki i anulowanie w dwóch miejscach). Odstępstwa i braki: [protokół](#protokół-usb-laptopstacja), [LXMF](#co-zostaje-na-etap-lxmf), [pamięć](#pamięć-ram).

## Protokół USB laptop–stacja

Kontrakt: [protokół USB](../docs/spec/protokol-usb.md) (`"usb":2`). Kod w `src/usbproto.cpp` (bez zależności od Arduino; scenariusze w `tests/test_firmware_host.py`), wiadomości SA1 w `src/sa1.cpp` (rozbiór, kontrola i kodowanie kanoniczne jak `reference.py`, z NFC i znakami nieprzydzielonymi), skaner JSON w `src/jsonlite.cpp`, magazyny w `src/store.cpp`.

- **Koperta i sesja.** Wiersze JSON do 1024 B z `seq` (odpowiedź z `re`), `hello` stacji po otwarciu portu z `boot`, kontraktem, rolą i stanem; tabela pól każdego polecenia: pole nieznane albo złego typu daje `invalid` z nazwą pola. Polecenie spoza roli daje `role`, polecenie trybu przygotowania poza nim `prep_required`.
- **Zdarzenia.** `sync`, `ack` i `snapshot` nad pierścieniem zdarzeń w FRAM z epoką: najwyżej 8 zdarzeń bez `ack`, ponowienie po 5 s od `cursor` + 1; zdarzenia `own`, `stage`, `msg`, `radio` (cisza ze źródłem i wyjątkiem) i `station` (restart, konfiguracja, KLUCZ ZAPASOWY, tryb przygotowania).
- **Polecenia.** `submit`, `cancel`, `test` (z `nonce`), `announce` (bliskie żądania łączone w 30 s), `mark_read`, `status`, `card` (klucz publiczny i adres LXMF stacji z odciskiem, który ekran pokazuje jednocześnie do porównania), transfery `xfer_begin`/`xfer_part`/`xfer_read`/`xfer_commit`/`xfer_abort` dla `configure` i `config_get` (powtórzona część sprawdzana z zapisaną kopią).
- **Potwierdzenie przyciskiem.** `silence`, `close` i `destroy` dostają `pending`, ekran pokazuje pytanie, a wynik idzie do 30 s później; pętla stacji działa dalej, inne polecenia w tym czasie dostają `busy`, a powtórzone `close` od razu odpowiedź.

Numeracja wierszy jak w specyfikacji: wiersz bez `seq` dostaje `rejected` bez `re`, każdy poprawny `seq` jest zużyty (także przy `contract`), a po odmowie `seq` stacja liczy od numeru laptopa. `silence` z `exception_id` wymaga wpisu rejestru i obejmuje jego `r_max` (`exception_revision` w `radio` i `status`); profil `radio.profile` stanowisk to `p1`. Braki: nie ma PRZENIEŚ STACJĘ (`migrate`: `migration` z `unsupported`; operacje `export` i `import` w `xfer_begin`: `migration`) ani aktualizacji oprogramowania (operacja `firmware`: `invalid` z `op`). W konfiguracji węzła stanowiska protokół działa tylko w trybie przygotowania, a poza nim interfejs danych przenosi ramki KISS z pakietami Reticulum ([węzeł stanowiska](#węzeł-stanowiska)). Każde polecenie trafia do dziennika zdarzeń (`LOG`).

## Warstwa aplikacji nad stosem

Kod w `src/station.cpp` (bez zależności od Arduino i od stosu; `tests/test_firmware_host.py` łączy stację z modelem odbiorcy w symulowanym eterze ze stratami i z modelem potwierdzenia transportowego). Po starcie łącze P1 jest w odbiorze (`P1RX`), a rejestr nadaje sam, chyba że `LINK 0`. Poza trybem przygotowania odbiór P1 wraca sam w ciągu sekundy po każdym przerwaniu, bo specyfikacja radia wyłącza odbiór tylko na czas własnego nadawania.

- **Cykl życia** ([specyfikacja](../docs/spec/oprogramowanie.md#cykl-życia-zgłoszenia)): etap `zapisane` → `wysyłanie` → `nadane` (dowód transportowy) → `odebrane` (RECEIVED), decyzja odbiorcy (STATUS, wyższy event wygrywa) osobno; rewizja, ANULUJ WYSYŁKĘ do pierwszego nadania, TEST z WSTRZYMAJ/WZNÓW, zwolnienie wpisu po decyzji 6 do pamięci zwolnionych wpisów. Każda zmiana to jedna transakcja razem ze zdarzeniem dla laptopa.
- **Pakiety Reticulum.** Wiadomość idzie pakietem okazjonalnym do celu SINGLE `wici.sa1` aktywnej tożsamości odbiorcy z karty, szyfrowanym do niej, z potwierdzeniem transportowym. Klucz z karty jest znany stosowi od startu, więc wysyłka nie czeka na ogłoszenie; bez trasy stos wysyła zapytanie o trasę, a próba wraca po 1, 2, 5 i 15 min ±20%.
- **Koperta zastępcza.** Do czasu LXMF treść pakietu to `["WICI",1,"<od>","<do>",<SA1>]` (do 383 B): pakiet okazjonalny nie niesie adresu nadawcy. Adres nadawcy nie jest podpisany; podpis da LXMF.
- **Wysyłka i ponowienia.** Najwyżej 2 własne wiadomości w drodze, kolejność REQUEST pilności 2, pozostałe REQUEST według zapisu, TEST na końcu. Brak dowodu w limicie = FAILED; limit to max(60 s, 2 × liczba skoków × 13 × czas TX datagramu 600 B + dług ciszy + czas opróżnienia kolejki P1); potem próby po 1, 2, 5 i 15 min ±20%, po 6 h co 60 min. Po dowodzie 10 min na RECEIVED, potem co 30–60 min. Bez wyniku od stosu przez 15 min próba liczy się jako nieudana.
- **Odbiór.** RECEIVED, STATUS, REPLY i BULLETIN tylko od aktywnej tożsamości odbiorcy (adres z koperty), REQUEST i TEST odrzucane (jedna rola, D19); powtórzenie BULLETIN rozpoznaje zbiór powtórzeń. Dowód dla wiadomości przychodzącej wychodzi dopiero po zapisie albo trwałym odrzuceniu.
- **Cisza radiowa.** Przełącznik CISZA albo `silence` z laptopa; `silence` z `exception_id` przepuszcza wymianę pary (id, r_max z chwili ustawienia): pakiet i jego ponowienia, zapytanie o trasę, dowody RECEIVED i STATUS tej rewizji; nowa rewizja, REPLY i reszta czekają, a przełącznik zawsze wycisza całkowicie. Reguła wynikowej ciszy jest jedna (`store::silenceMode`) dla łącza, stosu, wysyłki i USB.
- **Ogłoszenia adresu** (`src/rns_announce.h`, [specyfikacja](../docs/spec/oprogramowanie.md#tryby-kryzysowe)): przy starcie po losowych 0–120 s, na polecenie (`ANNOUNCE`, `announce`, OGŁOŚ ADRES), po 2 nieudanych próbach najwyżej raz na 30 min; w ciszy radiowej i bez kodu IFAC żadne; ogłoszenie, którego interfejs P1 nie przyjął, wraca po 60 s.

## Stos Reticulum

Pierwszy etap próby T3 ([odbiór](../docs/spec/odbior.md), wiersz „Stos na MCU”): port microReticulum w obrazach `bench-a`, `bench-n1` i `bench-b`, interfejs P1 jako interfejs Reticulum, tożsamość i tablice w FRAM, warstwa aplikacji na pakietach Reticulum. Bez LXMF (następny etap). Kod: `src/rns_node.cpp` (węzeł: start, interfejs P1, IFAC, tożsamości odbiorcy z karty, cisza z wyjątkiem, wysyłanie z potwierdzeniem, stan), `src/p1iface.cpp` (kolejka radiowa, limity, maskowanie IFAC; bez stosu i Arduino), `src/framfs.cpp` (system plików i rekord tożsamości w FRAM), `src/rns_framfs.h` (adapter do microStore), `src/pkthash.h` (lista skrótów 8 B), `src/rns_announce.h` (kiedy ogłaszać), `src/kiss.cpp` (ramki KISS interfejsu USB węzła stanowiska; bez stosu i Arduino), `src/host/node_host.cpp` (ten sam węzeł na komputerze z emulatorem P1).

Na `bench-b` (ESP32-S3) stos wchodzi do obrazu w tej samej konfiguracji, z dwiema różnicami wynikającymi z portu: pamięć stosu idzie ze sterty ESP-IDF zamiast z puli TLSF o stałym rozmiarze (port na ESP32 nie kompiluje własnego `tlsf.c`, bo ESP-IDF ma TLSF w ROM), więc `RNS` podaje pulę 0, a tablice ogranicza tylko ich pojemność; generator liczb losowych biblioteki Crypto bierze `esp_random()` i zapisuje ziarno w NVS ESP-IDF (na nRF52840 tylko TRNG, bez zapisu ziarna); na obu MCU przed utworzeniem tożsamości stacja wmieszuje w niego 32 B z generatora stacji (HMAC-DRBG z 48 B źródła sprzętowego, na ESP32-S3 przy włączonym `bootloader_random_enable`). Obraz kompiluje się i łączy; RAM stosu na ESP32-S3 nie był mierzony.

### Zależności i licencje

Źródła pobiera `tools/stack_deps.py` (skrypt przed kompilacją w `platformio.ini`) z przypiętych commitów do `.pio/stack`, sprawdza commit i nakłada łaty z `patches/`. Bez rozwiązywania zależności przez PlatformIO, bo menedżer bibliotek dobierał nieprzypięte wersje (Crypto z rejestru, microStore z gałęzi głównej). `python3 tools/stack_deps.py --list` wypisuje tabelę.

| Biblioteka | Wersja, commit | Licencja | Uwagi |
|---|---|---|---|
| [microReticulum](https://github.com/attermann/microReticulum) | 0.5.0, `40fa628` | Apache-2.0 | dołącza TLSF (BSD-3-Clause, Matthew Conte) i heatshrink (ISC, Scott Vokes); bez pliku NOTICE |
| [microStore](https://github.com/attermann/microStore) | 0.1.7, `0f28567` | Apache-2.0 w LICENSE, MIT w `library.json` | niespójność u autora; przyjęto Apache-2.0 jako warunek ostrzejszy |
| [Crypto](https://github.com/attermann/Crypto) (fork rweather/arduinolibs) | `984dc89` | MIT | Southern Storm Software |
| [MsgPack](https://github.com/hideakitai/MsgPack) | 0.4.2, `1f552c3` | MIT | |
| [ArxContainer](https://github.com/hideakitai/ArxContainer), [ArxTypeTraits](https://github.com/hideakitai/ArxTypeTraits), [DebugLog](https://github.com/hideakitai/DebugLog) | 0.7.0 `d6affcd`, 0.3.2 `702de9c`, 0.8.4 `b581f7d` | MIT | |
| [ArduinoJson](https://github.com/bblanchon/ArduinoJson) | 7.4.2, `733bc4e` | MIT | |

Licencje zależności są zgodne z MIT kodu WICI i nie dodają ograniczeń użycia. Obraz z nimi trzeba rozpowszechniać z tekstami licencji i informacją o autorach (Apache-2.0, MIT, BSD-3-Clause, ISC); łaty WICI mają licencję zmienianych plików (Apache-2.0, `REUSE.toml`, `LICENSES/Apache-2.0.txt`) i opis zmian w nagłówku każdej łaty.

**Otwarta kwestia (F26, F08).** microReticulum jest przekładem implementacji referencyjnej Reticulum na C++: zachowuje jej strukturę, nazwy i algorytmy, a w komentarzach ma dosłowne fragmenty kodu Pythona. Reticulum ma licencję MIT z dodatkowymi ograniczeniami (F08). Jeśli port jest utworem zależnym od Reticulum, obraz stacji z portem podlega także tym ograniczeniom, tak jak pakiet START, i nie jest oprogramowaniem otwartym w rozumieniu OSI; sama licencja Apache-2.0 portu tego nie rozstrzyga. Repozytorium nie dołącza kodu portu (tylko łaty i commit), więc źródła WICI pozostają na MIT. Propozycja rozstrzygnięcia (port traktowany ostrożnie jak utwór zależny, tekst licencji Reticulum w obrazach, zapytanie do autora portu) jest w [przeglądzie, F26](../docs/review.md#f26-licencja-portu-microreticulum); decyzja przed D14.

### Łaty

| Łata | Zmiana | Powód |
|---|---|---|
| `0001-pool-without-full-walk` | `pool_malloc` bez `tlsf_walk_pool` i `tlsf_check` przy każdym przydziale (zostają z `-DRNS_DEBUG_HEAP`); liczniki zajętości i szczytu puli (bloki z nagłówkami TLSF i struktura sterująca) | przegląd całej puli przy każdym `new` czynił przetwarzanie ogłoszenia kwadratowym; liczniki do pomiaru RAM |
| `0002-short-packet-hashes` | z `-DRNS_SHORT_PACKET_HASHES` lista skrótów pakietów to `pkthash::ShortHashList` | 4096 × 8 B w RAM (specyfikacja, „Pojemności stosu”) zamiast pełnych skrótów w kontenerach |
| `0003-build-without-neighbor-probing` | licznik sond tylko z `RNS_NEIGHBOR_PROBING` | kompilacja z wyłączonymi sondami sąsiadów |
| microStore `0001-keep-pinned-keys` | limit liczby rekordów (`max_recs`) pomija klucze przypięte przez `microStore::pinned_key` (`src/rns_node.cpp`: skróty celów głównej i zapasowej tożsamości odbiorcy z konfiguracji, w węźle stanowiska cele ogłoszone przez komputer stanowiska) | specyfikacja, „Pojemności stosu”: wpisów odbiorcy nigdy się nie usuwa; wygaśnięcie TTL i jawne usunięcie działają dalej |

Kompilacja: C++17 z wyjątkami i RTTI (wymóg portu); pliki z `.pio/stack` z `-w` (ostrzeżenia zależności nie są ostrzeżeniami WICI; kod WICI kompiluje się z `-Wall` bez ostrzeżeń) i z `-Os`, bo rdzeń Adafruit kompiluje z `-Ofast`, przy którym stos zajmował 254 KB flash więcej (rozwinięte pętle Curve25519 i kontenerów). Wpływu `-Os` na czas podpisu i weryfikacji ogłoszenia na nRF52840 nie zmierzono (lista prób na sprzęcie niżej).

### Interfejs P1

`P1Interface` w `rns_node.cpp` (klasa `RNS::InterfaceImpl`, `HW_MTU` 500, tryb FULL) nad łączem stanowiska (`measure::Bench`: dług ciszy, CCA, odroczenia, fragmentacja). Część bez stosu w `p1iface.cpp`:

- **Kolejka radiowa 4 datagramy.** Pakiet od stosu wchodzi tylko przy wolnym miejscu; przy pełnej kolejce interfejs odmawia (liczniki `q_full`), a `rnsnode::send` od razu zwraca 0, więc warstwa aplikacji wie o zajętości i ponawia według harmonogramu. Kolejność: dowody i pakiety do celów PLAIN (zapytania o trasę) przed danymi, ogłoszenia na końcu ([radio](../docs/spec/radio.md#dostęp-do-kanału), punkt 6; [interfejs P1](../docs/spec/radio.md#interfejs-p1-w-stosie-reticulum)). Datagram w nadawaniu zostaje w kolejce do końca serii, więc pakiet przyjęty w trakcie go nie zastępuje (błąd znaleziony w próbie zgodności, test regresji w `tests/test_rns_units.py`). Cisza całkowita (przełącznik albo `silence` bez wyjątku) odmawia stosowi każdego pakietu i opróżnia kolejkę (`silenced`); datagram, który był już w łączu, odpada razem z serią (`tx_failed`). Cisza z wyjątkiem przepuszcza tylko pakiety wyjęte przez stację: wysłane przez `rnsnode::send` (wiadomość zgłoszenia i zapytanie o trasę) i dowody RECEIVED i STATUS tej pary (id, revision); ogłoszenia czekają na liście. Łącze przyjmuje wtedy tylko datagramy od stosu: `P1TX`, `TXPKT` i `TXCW` milczą przy każdej ciszy. Przy pełnej kolejce interfejs odmawia przed liczeniem podpisu IFAC.
- **Przepływność deklarowana 271 bit/s**: datagram 600 B (1 362 ms nadawania w 7 ramkach) z długiem ciszy 12 × TX. Stos używa jej do limitów czasu i kosztu ogłoszeń.
- **Klasy ruchu K0–K2** ([dostęp do kanału](../docs/spec/radio.md#dostęp-do-kanału), punkt 6; czas kanału = czas TX + dług ciszy, przesuwne okno 60 min w minutowych przedziałach). K0: własne pakiety, dowody, zapytania o trasę i odpowiedzi; przekazywane zapytania o trasę najwyżej 1 na cel na 60 s i łącznie 5% (`pr_limited`). K1: przekazywane dane do aktywnej tożsamości odbiorcy z karty (`rnsnode::setReceivers`), w węźle stanowiska z interfejsu USB i do celów ogłoszonych przez komputer. K2: pozostałe przekazywane dane, razem z ogłoszeniami najwyżej 60% czasu kanału (`k2_pool`), bez ostatniego miejsca w kolejce (`k2_slot`), jeden cel najwyżej 25%, gdy czeka K0 albo K1 (`k2_dest`).
- **Osobny limit ogłoszeń.** Ogłoszenia przekazywane (hops > 0) mają 2% przepływności deklarowanej (`announce_cap` Reticulum): ogłoszenie 202 B co około 5 min. Ponad limit czekają na liście 4 ogłoszeń (jedno na cel, nowsze zastępuje starsze, najmniej skoków najpierw, 3 h życia jak `QUEUED_ANNOUNCE_LIFE`), piąte odpada z licznikiem. Własne ogłoszenia (hops = 0) i odpowiedzi na zapytania o trasę (kontekst PATH_RESPONSE) omijają limit jak w Reticulum, gdzie limit dotyczy tylko ogłoszeń bez przypisanego interfejsu; częstość własnych ustala `rns_announce.h`. microReticulum nie przetwarza kolejki ogłoszeń interfejsu (`process_announce_queue` wyłączone w porcie), dlatego limit jest w interfejsie.
- **IFAC 16 B z `config.ifac`.** Klucz jak `Reticulum._add_interface` z `passphrase` = 32 cyfry szesnastkowe klucza i `ifac_size` = 128 bitów; podpis Ed25519 i maska HKDF jak `Transport.transmit` i `inbound` w e40191b (port nie ma IFAC). Pakiet bez kodu albo z błędnym kodem odpada przed stosem (`ifac_missing`, `ifac_invalid`). Same zera w konfiguracji (stacja przed przygotowaniem) wyłączają interfejs: nie nadaje i odrzuca odbiór (`offline`). Wektor z Reticulum w Pythonie sprawdza test jednostkowy.
- **Dowody.** Cel `wici.sa1` stacji ma `PROVE_APP`: dowód transportowy wychodzi tylko dla pakietu przyjętego przez warstwę aplikacji (zapisany albo duplikat), jak dawny datagram `ack`. Pakiet odrzucony (zły format, obcy adresat, nadawca spoza zaufania) dowodu nie dostaje, więc nadawca liczy próbę jako nieudaną.

### Węzeł stanowiska

Decyzja D19 ([stanowisko odbiorcze](../docs/spec/stanowisko-osp.md#stacja-stanowiska)): tożsamość odbiorcy, Reticulum i LXMF w Pythonie oraz baza zgłoszeń działają na komputerze stanowiska, a stacja stanowiska jest zwykłą stacją w konfiguracji węzła stanowiska (konfiguracja z `"role":"wezel"` przez `xfer_begin` z operacją `configure` w trybie przygotowania). Zmiana tej konfiguracji restartuje stację, bo stos buduje interfejsy przy starcie. W tej konfiguracji:

- **Stos** ma drugi interfejs Reticulum `USB` (`UsbInterface` w `rns_node.cpp`, `HW_MTU` 500, tryb FULL, deklarowane 1 Mbit/s, żeby limit ogłoszeń nie wstrzymywał ogłoszeń sieci do komputera) i nie ma celu `wici.sa1`: adres jest zerowy, stacja się nie ogłasza, `send` i `ANNOUNCE` odmawiają. Tożsamość stacji służy tylko transportowi; nazwa `WICI-xxxxxx` pochodzi z niej jak zwykle. Transport przekazuje ruch także bez komputera.
- **Ramki KISS** (`src/kiss.cpp`, [radio](../docs/spec/radio.md#interfejs-reticulum-przez-usb-węzeł-stanowiska)): ramka danych FEND 0x00 … FEND z FESC, jeden pakiet do 500 B; polecenia TXDELAY, P, SLOTTIME, TXTAIL i inne są pomijane (`usb_cmds`); polecenie 0x0F z wartością 1 od komputera włącza kontrolę przepływu (`usb_flow`). Pakiet od komputera trafia do bufora 8 × 500 B i od razu dostaje ramkę gotowości FEND 0x0F 0x01 FEND (jak RNode, `usb_ready`); przy pełnym buforze gotowość czeka na wolne miejsce, a pakiet ponad bufor odpada (`usb_rx_drop`; za długi: `usb_rx_large`). Niepełna ramka po 100 ms bez bajtu przepada jak w Reticulum. Z bufora pakiet idzie do stosu dopiero, gdy kolejka P1 ma miejsce, więc w czasie długu ciszy czeka w stacji, a komputer na gotowość (Reticulum w Pythonie zwalnia blokadę sam po 5 s).
- **Do komputera** stacja koduje pakiety, które transport kieruje do interfejsu USB, do bufora 1 KiB, a pętla stacji zapisuje do CDC tyle, ile pokazuje `availableForWrite()`, bez blokowania; ramka, która się nie mieści, albo pakiet przy zamkniętym porcie przepada (`usb_tx_drop`), a ponowienie zapewnia LXMF komputera i stacji.
- **Interfejs danych CDC** przenosi ramki KISS poza trybem przygotowania i protokół laptop–stacja w trybie przygotowania (zmiana konfiguracji, oprogramowania); przejście między nimi zamyka i otwiera obie strony. Bufor KISS (około 5 KB) powstaje w puli stosu tylko w węźle stanowiska.
- **Tablice.** Cele ogłoszone przez komputer (ogłoszenie z interfejsu USB, do 8, najnowsze zastępują najstarsze; `usb_pinned`) są chronione w pełnych tablicach tras i znanych tożsamości (`microStore::pinned_key`, łata 0001), jak w specyfikacji „Pojemności stosu”. Lista jest w RAM: po restarcie wpisy wracają z FRAM, a ochronę odnawia ogłoszenie komputera, który ogłasza adres po każdym ponownym połączeniu ze stacją.
- **Klasa K1** to pakiety z interfejsu USB i do celów ogłoszonych przez komputer ([interfejs P1](#interfejs-p1)). IFAC dotyczy tylko P1: pakiet z USB dostaje kod przy nadaniu, pakiet z P1 bez poprawnego kodu odpada przed stosem.
- **Ekran** pokazuje kontakt z komputerem (`komputer_osp`, `komputer_brak`), menu STAN i JĘZYK ([ekrany](#ekrany-stacji)); rejestr, skrzynka i zdarzenia do laptopa są puste (zmiany ciszy i trybu przygotowania idą tylko do dziennika), więc w FRAM pracują tylko tablice stosu, dziennik i konfiguracja.

Program na komputerze z `--node` zastępuje port CDC pseudoterminalem (nazwa w zdarzeniu `ready`), który KISSInterface Reticulum otwiera jak port szeregowy; [próba](#próba-zgodności-z-reticulum) `tools/rns_osp_node.py` łączy go emulowanym P1 ze zwykłą stacją.

### Tożsamość i tablice w FRAM

| Obszar | Adres | Treść |
|---|---|---|
| rekord tożsamości | 0x44000 | 2 sloty × 128 B: znacznik, numer, klucz prywatny 64 B (X25519 + Ed25519), CRC-16; zapis do starszego slotu z odczytem kontrolnym |
| system plików stosu | 0x48000–0x7FFFF | nagłówek, 320 węzłów × 96 B, tablica przydziału 2 B na blok, 1 527 bloków × 128 B (195 456 B danych) |

Tożsamość stacji jest też tożsamością transportu. System plików (`framfs.cpp`) trzyma pliki magazynów microStore (Bitcask): tablicę tras, znane tożsamości i buforowane ogłoszenia; w RAM zostaje kopia tablicy przydziału oraz skrót nazwy, długość i pierwszy blok każdego węzła (6 296 B). Zapis nie jest transakcyjny: montowanie odrzuca węzły z błędnym CRC i zerwanym łańcuchem i zwalnia bloki bez właściciela (testy zaniku zasilania w `tests/test_rns_units.py`); w obszarze jest tylko stan odtwarzalny z ogłoszeń. Zegar stosu to czas pracy z dziennika FRAM (`OS::setTimeOffset`), więc wiek tras liczy się dalej po restarcie.

Lista skrótów pakietów (4096 × 8 B, 32 KiB) jest w RAM i nie trafia do FRAM: po restarcie pusta lista może przyjąć ponownie pakiet sprzed restartu, a powtórzenia wiadomości odrzuca warstwa aplikacji po kluczu (id, revision, event).

Rekord formatu magazynu ma znacznik zapisanej tożsamości: przy starcie bez klucza w FRAM i ze znacznikiem stos nie startuje (`identity_lost` w `RNS`), bo nowa tożsamość po błędzie pamięci zmieniłaby adres stacji znany odbiorcy; bez znacznika stos tworzy tożsamość i ustawia znacznik. ZNISZCZ DANE (`destroy` przez USB albo z menu USŁUGI) zatrzymuje stos bez dalszych zapisów (`rnsnode::halt`), a magazyn kasuje konfigurację, rekordy, znacznik, oba sloty tożsamości i system plików stosu; po 0,5 s stacja restartuje (stan w RAM należał do skasowanych rekordów) i ma nową tożsamość. `REBOOT` zapisuje tablice przed restartem.

### Różnice wobec specyfikacji i Reticulum

| Różnica | Koszt i skutek |
|---|---|
| indeks magazynów microStore (Bitcask) w RAM | pełne wpisy tras, tożsamości i ogłoszeń są w FRAM, ale każdy wpis ma w RAM węzeł mapy z kluczem (wektor 16 B) i położeniem 16 B w dwóch magazynach, plus obiekty kontenerów stosu: 233 B na cel przy 32-bitowych wskaźnikach zamiast około 16 B ze specyfikacji („Pojemności stosu”); dane w RAM rosną liniowo z liczbą celów |
| lista skrótów pakietów nie jest zapisywana | jak wyżej; specyfikacja tego nie wymaga |
| lista ogłoszeń czekających na limit: 4 wpisy (Reticulum: kolejka do 4096) | przy napływie wielu nowych celów większość retransmisji odpada (odtworzenie 256 ogłoszeń: 268 odrzuceń); dalsze stacje poznają trasę zapytaniem o trasę; liczbę wpisów i limit ustala T5 |
| tablica ogłoszeń do retransmisji: 16 wpisów (port: 100, Reticulum: bez limitu) | mniejszy szczyt RAM (−16 KB); przy limicie 2% więcej retransmisji i tak nie wyjdzie |
| sondy sąsiadów portu wyłączone | brak dodatkowego ruchu; funkcja nie istnieje w Reticulum |
| limit ogłoszeń w interfejsie, nie w transporcie | zachowanie jak `announce_cap` dla ogłoszeń przekazywanych; własne ogłoszenia i odpowiedzi o trasę bez limitu jak w Reticulum |
| usuwanie wpisów tras | port ustawiał `RNS_PATH_TABLE_MAX` tylko dla dawnej tablicy w RAM (`cull_path_table`), a magazyn tras w FRAM nie miał limitu; `rns_node.cpp` ustawia go przez `Transport::path_table_maxsize`. Przy pełnej tablicy (256 tras, 256 znanych tożsamości) odpada najstarszy wpis poza celami odbiorcy z konfiguracji, a w węźle stanowiska poza celami ogłoszonymi przez komputer (łata microStore 0001; [próba zgodności](#próba-zgodności-z-reticulum), krok 7) |
| skróty 8 B | fałszywy duplikat z prawdopodobieństwem rzędu 4096 / 2^64 na pakiet |
| zegar stosu | port odrzuca przesunięcie czasu powyżej 2^32 ms (około 49 dni pracy); do sprawdzenia przed pilotażem |

### Próba zgodności z Reticulum

`tools/rns_interop.py` uruchamia Reticulum e40191b w Pythonie z interfejsem UDP (ten sam klucz IFAC) i program `host` (`pio run -e host`): ten sam węzeł, interfejs P1, IFAC i tablice FRAM (plik) co obraz, z emulatorem łącza P1 (ramki P1, czas nadawania z modelu ramki, dług ciszy 12 × TX). `tests/test_rns_stack.py` robi to samo jako test, gdy podano `WICI_PIO` i `WICI_RNS_PYTHON`.

```bash
python3 -m venv .venv-rns && .venv-rns/bin/pip install "git+https://github.com/markqvist/Reticulum@e40191b"
```

```bash
cd firmware && ../.venv-pio/bin/pio run -e host && ../.venv-rns/bin/python tools/rns_interop.py --program .pio/build/host/program --fill 256
```

Wynik (2026-10-08, ostatni przebieg na kodzie z tego commitu, z `--fill 256`): wszystkie 20 sprawdzeń zaliczone.

| Sprawdzenie | Wynik |
|---|---|
| ogłoszenie stacji widoczne w Pythonie (z danymi aplikacji) | tak |
| ogłoszenie z Pythona widoczne w stacji | tak |
| pakiet okazjonalny stacja → Python, dowód transportowy w stacji | tak; od ogłoszenia stacji do pakietu w Pythonie 6,1 s (ogłoszenie i pakiet, każde z długiem 12 × TX) |
| pakiet okazjonalny Python → stacja, dowód w Pythonie | tak; RTT dowodu 4,9 s |
| pakiet odrzucony przez warstwę aplikacji bez dowodu | tak (`PacketReceipt` w Pythonie kończy się `FAILED`) |
| datagram bez IFAC i z błędnym IFAC odrzucony przed stosem | tak, oba policzone |
| 256 dodatkowych ogłoszeń przy celu Pythona przypiętym jako odbiorca: tablica tras pełna (256 celów, limit `RNS_PATH_TABLE_MAX`), lista skrótów 4096 | tak |
| po restarcie programu z tym samym plikiem FRAM: ta sama tożsamość, trasa i tożsamość celu odbiorcy z FRAM, tablica w limicie (256 tras), pakiet bez nowego ogłoszenia, dowód | tak |
| krok 7, nowa pamięć FRAM i tablice po 6 wpisów: cel odbiorcy i 9 dalszych ogłoszeń; odpada najstarszy cel bez ochrony, odbiorca zostaje (trasa i tożsamość) | tak; bez przypięcia odbiorcy odpada (próba kontrolna) |
| krok 8: tożsamość odbiorcy z klucza karty (`receiver`) znana bez ogłoszenia; w ciszy z wyjątkiem ogłoszenie odmówione, a pakiet do odbiorcy z karty wychodzi i dostaje dowód | tak |

Domyślny limit potwierdzenia w Reticulum dla jednego skoku przez szybki interfejs wynosi 12 s; dowód po datagramie 600 B przez P1 może przyjść dopiero po długu ciszy nadawcy i odbiorcy (16,3 s każdy), więc nadawca w Pythonie musi ustawić dłuższy limit (próba: 120 s). Stacja liczy limit według wzoru z [interfejsu P1](../docs/spec/radio.md#interfejs-p1-w-stosie-reticulum) (`rnsnode::send`): co najmniej 60 s, więcej przy wielu skokach, długu i pełnej kolejce. To potwierdza uwagę F02 o limitach czasu po stronie odbiorcy i laptopa.

**Węzeł stanowiska** (`tools/rns_osp_node.py`, druga klasa w `tests/test_rns_stack.py`): dwa programy `host` połączone emulowanym P1 przez UDP, stacja i węzeł stanowiska (`--node`), a w Pythonie Reticulum e40191b jako komputer stanowiska: KISSInterface z `flow_control = Yes` i `bitrate = 24` na pseudoterminalu węzła, bez transportu i interfejsów sieciowych, cel `wici.sa1` w miejscu adresu odbiorcy. Wynik (2026-10-08, kod z tego commitu, dług 12 × TX): wszystkie 12 sprawdzeń zaliczone.

| Sprawdzenie | Wynik |
|---|---|
| węzeł bez adresu (`ready`: same zera) i bez ogłoszenia (`announce` odmawia) | tak |
| komputer włącza kontrolę przepływu (KISS 0x0F 1; cztery polecenia konfiguracji pominięte) | tak |
| ogłoszenie komputera przez węzeł i P1 widoczne w stacji; cel komputera chroniony w tablicach węzła, cel stacji nie | tak; 1,0 s |
| ogłoszenie stacji przez węzeł widoczne w komputerze | tak |
| pakiet okazjonalny stacja → komputer, dowód w stacji | tak |
| pakiet okazjonalny komputer → stacja, dowód w komputerze; limit 184,7 s z samej konfiguracji (`bitrate = 24`: 500 B × 8 / 24 + 6 s + 2 × 6 s), bez `set_timeout` i zmian w kodzie Reticulum; bez opcji `bitrate` limit wynosi 21,3 s ([stanowisko odbiorcze, czasy](../docs/spec/stanowisko-osp.md#komputer-i-aplikacja-stanowiska)) | tak |
| seria 6 pakietów z komputera: kolejka KISS w Pythonie pusta po 0,27 s (bez blokady 5 s), 6 gotowości, bez odrzutów; wszystkie w stacji po 25 s długu ciszy | tak |

Wymagają sprzętu (stanowisko A, dwie płytki albo płytka i Reticulum w Pythonie z modemem P1):

- te same sprawdzenia przez CC1120: ramki P1 w eterze zamiast emulatora, CCA i odroczenia przy ruchu stosu, dług ciszy z dziennika FRAM między pakietami;
- czas podpisu i weryfikacji ogłoszenia, odszyfrowania pakietu i dowodu na nRF52840 przy `-Os` (watchdog 60 s, pętla stacji), czas zapisu tablicy tras do FRAM przy 1 MHz;
- RAM w czasie pracy: wolna sterta po starcie i przy pełnych tablicach (`RNS`: `pool_used`, `pool_peak`), zapas stosów zadań (FreeRTOS `uxTaskGetStackHighWaterMark`), alokacje TinyUSB i newlib poza pulą;
- restart przez watchdog i zanik zasilania w trakcie zapisu tablic (montowanie z naprawą), zimny start trasy po restarcie przekaźnika (`odbior.md`);
- ogłoszenia w ciszy radiowej (żadne nie wychodzi), opóźnienie ogłoszenia startowego, ogłoszenie po 2 nieudanych próbach;
- ograniczenie wierszy stosu w dzienniku zdarzeń (najwyżej 10 na minutę, liczba pominiętych w następnym oknie) przy powtarzającym się błędzie stosu;
- dwie stacje z transportem: przekazywanie ogłoszeń z limitem 2%, trasa A–B–stanowisko;
- węzeł stanowiska: KISS przez interfejs CDC z Reticulum w Pythonie na komputerze (`availableForWrite()` w TinyUSB na nRF52840 i ESP32-S3, odłączenie i ponowne podłączenie komputera, wartość `bitrate` komputera z T3), RAM puli z buforem KISS przy pełnych tablicach.

### Pamięć RAM

Pomiar dla obrazu `bench-a` (nRF52840, 256 KiB RAM) przy pojemnościach ze specyfikacji: 257 celów w tablicy tras i znanych tożsamości (256 ogłoszeń z Reticulum w Pythonie i jego własne; pomiar sprzed limitu 256 wpisów, więc z zapasem jednego celu), 4096 skrótów na liście skrótów pakietów. RAM statyczna z kompilacji (`arm-none-eabi-size`), stosy zadań z rdzenia Adafruit i `main.cpp`, pula stosu z liczników łaty 0001 (bloki z nagłówkami TLSF i struktura sterująca). Pulę zmierzono w programie węzła zbudowanym jako 32-bitowy (i386, te same rozmiary typów co ARM) przez `tools/rns_ram32.py`, który odtwarza datagramy nagrane w próbie zgodności (`rns_interop.py --fill 256 --capture`); program 64-bitowy na komputerze daje tylko górne ograniczenie (166 904 B szczytu, 154 792 B w stanie ustalonym).

| Pozycja | B | Uwagi |
|---|---|---|
| RAM nRF52840 | 262 144 | |
| obszar SoftDevice S140 | 24 576 | 0x20000000–0x20005FFF zarezerwowane przez bootloader i skrypt linkera, choć Bluetooth nie działa |
| RAM aplikacji | 237 568 | PlatformIO podaje 248 832 B z opisu płytki; skrypt linkera daje mniej |
| statyczna (`.data`, `.bss`, `.noinit`) | 99 772 | magazyny stacji 19 288 (indeksy rejestru, skrzynki i zdarzeń, konfiguracja z frazami), bufor ekranu 12 056, łącze 7 288, ekran i konsola 3 300, protokół USB 1 248; stos (z interfejsem USB węzła stanowiska), w tym lista skrótów 4096 × 8 B (32 784), kopia tablicy przydziału i skrótów nazw systemu plików FRAM (6 296), obiekty magazynów (1 456) |
| stos główny (MSP) | 2 048 | skrypt linkera |
| stosy zadań FreeRTOS | 24 784 | stacja 16 384, pętla rdzenia 4 096, wywołania zwrotne 3 072, USB 800, bloki zadań około 430 |
| pula stosu na starcie | 17 176 | puste tablice; w tym struktura sterująca TLSF, kolejka i lista ogłoszeń interfejsu P1 |
| pula stosu, stan ustalony przy pełnych tablicach | 77 164 | 233 B na cel w RAM: indeks magazynów microStore i obiekty kontenerów stosu |
| pula stosu, szczyt przy pełnych tablicach | 100 620 | przetwarzanie 256 ogłoszeń w tempie 3 na sekundę; z tablicą ogłoszeń 100 wpisów (domyślna portu) szczyt wynosił 116 572 B i nie mieścił się w RAM, stąd `RNS_ANNOUNCE_TABLE_MAX=16` |
| pula skonfigurowana (`RNS_HEAP_POOL_BUFFER_SIZE`) | 106 496 | szczyt i 6%; zostaje 4 468 B sterty na inne przydziały (TinyUSB, newlib), do sprawdzenia na płytce |

**Zapas** (RAM niezajęty wobec 256 KiB, obszar SoftDevice liczony jako zajęty): 237 568 − 99 772 − 2 048 − 24 784 = 110 964 B zostaje na pulę i resztę sterty. Przy szczycie puli wolne jest 10 344 B, czyli **4,0%**; w stanie ustalonym 33 800 B, czyli **12,9%**. Próg D14 to 30% (78 643 B). Brakuje 68 299 B w szczycie i 44 843 B w stanie ustalonym, jeszcze bez LXMF. Pula zmierzona przed F107; wiadomości do dwóch własnych naraz i tożsamości odbiorcy z karty dokładają w niej niewiele (dwa wpisy znanych tożsamości), co ma potwierdzić pomiar na płytce.

**Węzeł stanowiska** bierze z puli przy starcie bufor KISS (`kiss::Port`, 5 112 B na ARM: 8 × 500 B od komputera, 1 KiB do komputera, liczniki) i nie ma celu `wici.sa1`. Przy zmierzonym szczycie puli zostałoby w niej około 0,8 KB, więc węzeł stanowiska na nRF52840 zależy od D14 tak samo jak LXMF; szczyt w konfiguracji węzła trzeba zmierzyć na płytce (`RNS`). Stacja w schronieniu bufora nie ma (statycznie dochodzi 200 B: lista celów komputera i stan interfejsu).

**Wniosek dla D14.** Obraz stacji ze stosem w tym kształcie nie spełnia warunku zapasu RAM ≥30% na nRF52840. Podział ze specyfikacji (pełne wpisy w FRAM, w RAM indeks 256 × 16 B) jest spełniony tylko co do wpisów: indeks magazynów portu (mapa haszująca z kluczem jako wektor i położeniem 16 B, dwa magazyny) i obiekty kontenerów stosu dają 233 B na cel zamiast około 16 B, czyli około 60 KB przy 256 celach. Zejście do 30% wymagałoby naraz zwartego indeksu w porcie (tablica posortowanych skrótów i położeń, około 6 KB; zmiana microStore i Transport, czyli głęboka zmiana portu) i odchudzenia obrazu stacji o około 20 KB ([odłożone zmiany](#rozmiar-i-wydajność): pas ekranu −9,6 KB, frazy z FRAM na żądanie −3,2 KB, lista konsoli −1 KB), a LXMF dołoży router, bufor wiadomości i własne tablice. Według [specyfikacji](../docs/spec/oprogramowanie.md#trwałość-i-potwierdzenia) („Pojemności stosu”) taki wynik jest przesłanką do D14: przed projektem wykonania A porównuje się MCU z większą pamięcią (np. nRF5340, RP2350, STM32U5) z głęboką przebudową portu opisaną wyżej. Pomiar na płytce (polecenie `RNS`) ma potwierdzić liczby z odtworzenia.

System plików FRAM przy pełnych tablicach: 135 680 B z 195 456 B (69%), 8 plików.

Flash: 595 172 B z 815 104 B (73,0%); stos dokłada około 324 KB, w tym Curve25519 i Ed25519, kontenery C++17 z wyjątkami (tablice odwijania `.ARM.extab` i `.ARM.exidx` 27 KB), MsgPack i ArduinoJson.

### Co zostaje na etap LXMF

- LXMF na stacji: wiadomość jako jeden pakiet okazjonalny (D01) z podpisem nadawcy i adresem LXMF zamiast koperty `["WICI",1,od,do,…]`; odstęp ponowienia LXMF co najmniej max(60 s, 2 × skoki × 13 × czas TX największego datagramu + dług ciszy + czas opróżnienia kolejki P1) i najwyżej 2 próby LXMF na ponowienie ([interfejs P1](../docs/spec/radio.md#interfejs-p1-w-stosie-reticulum), F02). Adres LXMF w `card` i `hello` jest już liczony z tożsamości stacji.
- Uwierzytelnienie nadawcy: zaufanie do odbiorcy po kluczu z karty zamiast adresu w treści koperty; rozpoznanie ruchu od odbiorcy po nadawcy.
- Szyfrowanie rekordów FRAM (AEAD, generacja klucza w nagłówku gniazda, F99) z kluczem KEK w chronionej pamięci MCU, bezpieczny rozruch; PRZENIEŚ STACJĘ (`migrate`, `export`, `import`) i aktualizacja oprogramowania czekają na te klucze.
- Pamięć: LXMF dokłada router i bufor wiadomości; budżet z tabeli wyżej (D14).
- Energia i ekran zasilania: pomiar ogniw i 12 V (`power` w `status` podaje dziś stałe `12v` bez napięć), przypomnienie `wymien_ogniwa`.

## Rozmiar i wydajność

Obiekty statyczne `bench-a` (`arm-none-eabi-nm --size-sort`, po F107): magazyny stacji 19 288 B (indeksy rejestru 128 wpisów, skrzynki, pamięci zwolnionych wpisów i pierścienia zdarzeń, konfiguracja z frazami i kluczami karty), bufor ekranu 12 056 B (240 wierszy × 50 B i mapa zmian), łącze `measure::Bench` 7 288 B (składanie 8 prób × 600 B), ekran z konsolą 3 300 B, bufor poleceń diagnostyki 1 400 B, protokół USB 1 248 B, warstwa aplikacji 848 B. Listy ekranu biorą numer, kategorię, etap i próby z indeksu w RAM; treść czyta się z FRAM tylko dla otwartej pozycji (z pamięcią podręczną do nowej rewizji). Rejestr jest przeglądany co 100 ms, sprzątanie po ZAMKNIJ ZDARZENIE (`maintain`) idzie w tym samym takcie po jednej transakcji.

Odłożone (z szacunkiem zysku; każde wymaga osobnej zmiany i testów):

| Zmiana | Zysk | Koszt |
|---|---|---|
| frazy z konfiguracji czytane z FRAM na żądanie | −3,2 KB RAM | ekran czyta 97 B na wiersz listy |
| bufor ekranu jako pas jednego wiersza tekstu (48 × 50 B) zamiast całej ramki | −9,6 KB RAM | panel pamięta obraz; każdy wiersz trzeba rysować i wysyłać od razu |
| lista konsoli bez czasu (czas z indeksu przy sortowaniu) | −1 KB RAM | sortowanie z odczytem indeksu |
| mniejszy font (16 × 32 px) | −10 KB flash | wersaliki 2,8 mm, poniżej wymagania ≥3,5 mm |

## Następne kroki

1. Próby na sprzęcie według kroków wyżej (obraz nie był jeszcze uruchomiony na płytce), na N1 także pomiar oscyloskopem przy J7 i U1 (ekran 1 i 2 MHz, FRAM 8 MHz, poziomy i zbocza); węzeł stanowiska z komputerem stanowiska przez USB.
2. T3, etap 2: LXMF na stacji ([co zostaje](#co-zostaje-na-etap-lxmf)); przed nim decyzja o pamięci z [pomiaru RAM](#pamięć-ram) (D14) i rozstrzygnięcie licencji portu (F26).
3. Próby stosu na sprzęcie z [listy](#próba-zgodności-z-reticulum): dwie płytki A przez CC1120 i płytka A z Reticulum w Pythonie, czasy kryptografii przy `-Os`, RAM w czasie pracy, restart w trakcie zapisu tablic; na `bench-b` start stosu i pula TLSF na ESP32-S3.
4. Stanowisko B (`bench-b`), w tej kolejności:
   - kroki B3–B4 na sprzęcie (w tym wyliczenie dwóch portów CDC, wgrywanie przez dotknięcie 1200 b/s i to, czy restart przez watchdog zadań daje `esp_reset_reason()` = TASK_WDT, a nie PANIC, od czego zależy wpis „restart by watchdog”), wybór napędu SCK i MOSI (`DRIVE`) i zegara ekranu analizatorem na J11;
   - łącze między A i B: `TXPKT`/`RX`/`RXPER` w obie strony i `P1TX`/`P1RX` (potwierdzenie kolejności bajtów słowa synchronizacji w eterze; przy braku odbioru zamiana kolejności `REGW 33..36` w trybie przygotowania, `CONFIG` przywraca tablicę), `TXCW` z miernikiem częstotliwości i `FOFF`;
   - odbiór serii ramek bez przerw na B (`TXPKT 50 103 0` z A, `RXPER` na B przy odświeżanym ekranie STAN): sterownik odrzuca ramkę, gdy w kolejce RX jest już początek następnej (pętla stała dłużej niż około 20 ms); przy stratach odczyt tylko długości ramki z pozostawieniem reszty kolejki;
   - przesunięcie RSSI modułu (wpływa na próg CCA −100 dBm i `rssi_avg_dbm`), ustawienia AFC, AGC i odtwarzania zegara symboli przy pomiarze czułości (T4);
   - przegląd tablicy S2-LP w ST STSW-S2LP-DK (S2-LP DK GUI) dla P1, gdy narzędzie będzie dostępne; pomiar mocy i dobór PA_POWER oraz SMPS;
   - własne nazwy interfejsów CDC („WICI diagnostyka”, „WICI dane”) wymagają zmiany w rdzeniu Arduino-ESP32 (nazwy są stałe w `USBCDC.cpp`) albo własnych deskryptorów TinyUSB.
5. Dioda alarmu i brzęczyk na N1: jasność błysku 50 ms przy 1 mA i głośność sygnałów do oceny na płytce; przypomnienie `wymien_ogniwa` z pomiarem ogniw (R02).
