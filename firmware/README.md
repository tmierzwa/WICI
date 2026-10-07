# WICI: oprogramowanie stacji

Katalog zawiera oprogramowanie układowe stacji. Obecny stan to pierwsze kroki na [stanowisku deweloperskim A](../hardware/dev-bench/README.md): nRF52840-DK z modułem TI CC1120EM-868-915 i pamięcią FRAM na złączu Arduino płytki. Środowisko `bench-a` w `platformio.ini` buduje obraz, który po podłączeniu USB zgłasza się poleceniem `INFO` w formacie ze [specyfikacji radia](../docs/spec/radio.md#usb-do-laptopa), identyfikuje układ radiowy i FRAM przez SPI oraz obsługuje przyciski i diody płytki. Nie ma jeszcze profilu P1, stosu Reticulum, ekranu ani drugiego interfejsu CDC.

Obraz skompilowano (PlatformIO, rdzeń Adafruit nRF52 1.7.0, 8928 B RAM, 60 080 B flash). **Nie uruchomiono go na sprzęcie**: odpowiedzi poleceń, numery pinów i działanie SPI z modułem wymagają sprawdzenia na płytce według kroków niżej.

## Okablowanie stanowiska A

Numery pinów są w `src/board_bench_a.h`. Płytka DK pracuje domyślnie z VDD = 3,0 V, co mieści się w zakresie CC1120 (2,0–3,6 V) i FRAM; moduł zasila się z pinu VDD płytki, nie z 5 V. Złącza EM są na spodzie modułu, a widok od spodu odwraca obraz: przed włączeniem sprawdzić każdą żyłę miernikiem.

| Sygnał | Złącze Arduino DK | GPIO nRF52840 | Moduł CC1120EM | FRAM Adafruit 4719 |
|---|---|---|---|---|
| SCK | D13 | P1.15 | P1.16 | SCK |
| MOSI | D11 | P1.13 | P1.18 | MOSI |
| MISO | D12 | P1.14 | P1.20 | MISO |
| CSn radia | D10 | P1.12 | P1.14 | |
| RESET_N radia | D8 | P1.10 | P2.15 | |
| GPIO0 radia | D2 | P1.03 | P1.10 | |
| GPIO2 radia | D3 | P1.04 | P1.12 | |
| CS FRAM | D9 | P1.11 | | CS |
| 3,0 V | VDD | | P2.7 (P2.9 to ten sam węzeł) | VIN |
| GND | GND | | P1.1, P1.19, P2.2 | GND |

Przyciski płytki: BUTTON1 = GÓRA, BUTTON2 = DÓŁ, BUTTON3 = OK, BUTTON4 = WSTECZ. Diody: LED1 bicie serca (0,5 s), LED2 radio rozpoznane, LED3 FRAM rozpoznana, LED4 port USB otwarty przez hosta. Przewody do 5 cm; SPI pracuje z 1 MHz.

## Narzędzia

PlatformIO Core w osobnym środowisku Pythona; wersje platformy i rdzenia są przypięte w `platformio.ini` (nordicnrf52 11.0.0, framework-arduinoadafruitnrf52 1.10700.0, czyli rdzeń Adafruit nRF52 1.7.0 z TinyUSB). Rdzeń Adafruit wybrano, bo tego samego używa microReticulum dla nRF52840 (środowisko `wiscore_rak4631`), więc stos sieciowy wejdzie do tego samego projektu.

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

Port USB nRF (J3, nie port J-Link J2) zgłasza się jako CDC ACM, 115200 bit/s (prędkość nie ma znaczenia dla USB). Każda odpowiedź to jeden wiersz JSON. Po otwarciu portu obraz sam wysyła `INFO`, `RADIO` i `FRAM`.

| Polecenie | Odpowiedź |
|---|---|
| `INFO` | pola jak w specyfikacji radia: `contract`, `profile`, `radio`, `mcu`, `fw`, `src`, `mv`, liczniki ruchu (na razie zera), `restarts`, oraz `bench`, `radio_ok`, `fram_ok`, `uptime_s` |
| `RADIO` | `partnumber` (CC1120 = `0x48`), `partversion`, `marcstate`, stan z bajtu statusu, `ok` |
| `RESET` | reset sprzętowy RESET_N i `SRES`, potem `RADIO` |
| `REG <hex>` | odczyt rejestru, np. `REG 2F73` (MARCSTATE), `REG 2F0C` (FREQ2) |
| `FRAM` | cztery bajty RDID (MB85RS4MT: `047F4903`, MB85RS4MTY: `047F490B`), rejestr stanu, `ok` |
| `BTN` | stan czterech przycisków |
| `LED <1-4> <0/1>` | sterowanie diodą |

Warunek przejścia kroku 6 z [lekcji R02](../hardware/r02/lekcje.md#uruchomienie): `RADIO` daje `ready: true`, `partnumber: 0x48` i stan `IDLE`; `FRAM` daje `fujitsu: true`. Bez modułu `partnumber` wynosi `0xFF` albo `0x00`, a `ready` jest `false`.

## Następne kroki

1. Konfiguracja rejestrów P1 (869,525 MHz, 2-GFSK 4800 bit/s, dewiacja ±4 kHz, filtr 24–32 kHz, preambuła i słowo synchronizacji) z eksportu SmartRF Studio, zapisana jako tablica w kodzie z odnośnikiem do wersji narzędzia.
2. Polecenia pomiarowe `TXCW`, `TXPKT`, `RXPER`, `FOFF` ze [specyfikacji radia](../docs/spec/radio.md#usb-do-laptopa), z limitem czasu nadawania i potwierdzeniem przyciskiem dla serii przewodowych.
3. Dziennik długu ciszy i licznik restartów w FRAM; ekran Sharp (Adafruit 4694) z EXTCOMIN z licznika sprzętowego.
4. Ramka P1 w C++ sprawdzona na wektorach z [modelu](../software/reference/README.md); dwa interfejsy CDC (dane i diagnostyka).
5. microReticulum i LXMF na tym samym projekcie (T3) z pomiarem zapasu RAM; środowisko `bench-b` dla ESP32-S3-DevKitC-1 z S2-LP.
