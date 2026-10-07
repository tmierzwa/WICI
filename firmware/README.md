# WICI: oprogramowanie stacji

Katalog zawiera oprogramowanie układowe stacji. Obecny stan to pierwsze kroki na [stanowisku deweloperskim A](../hardware/dev-bench/README.md): nRF52840-DK z modułem TI CC1120EM-868-915 i pamięcią FRAM na złączu Arduino płytki. Środowisko `bench-a` w `platformio.ini` buduje obraz, który po podłączeniu USB zgłasza się poleceniem `INFO` w formacie ze [specyfikacji radia](../docs/spec/radio.md#usb-do-laptopa), identyfikuje układ radiowy i FRAM przez SPI, zapisuje do CC1120 [rejestry profilu P1](#rejestry-profilu-p1) z weryfikacją odczytu i kalibracją syntezera, wykonuje [polecenia pomiarowe](#polecenia-pomiarowe) `TXCW`, `TXPKT`, `RXPER`, `FOFF` ze specyfikacji, prowadzi [dziennik w FRAM](#dziennik-w-fram) (dług ciszy, zegar czasu pracy z liczbą restartów, zdarzenia), podaje zaprogramowaną częstotliwość i RSSI oraz obsługuje przyciski i diody płytki. Nie ma jeszcze ramki P1 (F79), stosu Reticulum, ekranu ani drugiego interfejsu CDC.

Obraz skompilowano (PlatformIO, rdzeń Adafruit nRF52 1.7.0, 9900 B RAM, 80 792 B flash). **Nie uruchomiono go na sprzęcie**: odpowiedzi poleceń, numery pinów, działanie SPI z modułem i przyjęcie rejestrów przez układ wymagają sprawdzenia na płytce według kroków niżej.

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

Przyciski płytki: BUTTON1 = GÓRA, BUTTON2 = DÓŁ, BUTTON3 = OK, BUTTON4 = WSTECZ. Diody: LED1 bicie serca (0,5 s), LED2 radio rozpoznane, LED3 FRAM rozpoznana i dziennik uruchomiony, LED4 port USB otwarty przez hosta. Przewody do 5 cm; SPI pracuje z 1 MHz.

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
| `INFO` | pola jak w specyfikacji radia: `contract`, `profile`, `radio`, `mcu`, `fw`, `src`, `mv` (zero, brak pomiaru), `tx_wait_ms` (pozostały dług ciszy), `rx_ok`, `rx_bad`, `restarts` i `uptime_s` z dziennika FRAM, oraz `bench`, `prep`, `silence`, `radio_ok`, `p1_ok`, `fram_ok`, `journal_ok`, `journal_resets`, parametry P1, `boot_s` |
| `RADIO` | `partnumber` (CC1120 = `0x48`), `partversion`, `marcstate`, stan z bajtu statusu, `ok` |
| `RESET` | reset sprzętowy RESET_N i `SRES` (kasuje rejestry P1, `p1_ok: false`), potem `RADIO` |
| `CONFIG` | zapis tablicy P1 w stanie IDLE, odczyt i porównanie 57 rejestrów (`checked`, `mismatches`, pierwszy niezgodny z wartością oczekiwaną i odczytaną), potem kalibracja; `config: true` tylko przy zerze niezgodności i udanej kalibracji |
| `VERIFY` | ponowne porównanie rejestrów z tablicą bez zapisu |
| `CAL` | ręczna kalibracja syntezera; podaje FS_VCO2, FS_VCO4, FS_CHP i FS_CAL2 po kalibracji |
| `FREQ` | słowo FREQ, FREQOFF, częstotliwość nośna w Hz ze wzoru z instrukcji, błąd wobec 869 525 000 Hz, krok FREQOFF oraz FREQOFF_EST z ostatniego odbioru |
| `RX [<len>]` / `IDLE` | odbiór ramek wzorcowych o długości `len` (domyślnie 103) z licznikami dla `RXPER`, albo przerwanie wszystkiego i IDLE; potem `STATE` |
| `PREP <0\|1>` | tryb przygotowania; włączenie wymaga przycisku OK w ciągu 30 s |
| `SILENCE <0\|1>` | cisza radiowa (na stanowisku zamiast przełącznika CISZA) |
| `TXCW <s> [CONDUCTED]` | nośna bez modulacji przez 1–10 s; po zakończeniu `tx_ms` i dług ciszy |
| `TXPKT <n> <len> [<ms>] [CONDUCTED]` | `n` ramek wzorcowych po `len` B (4–103) co `ms`; seria idzie w tle, na końcu `sent`, `failed`, `tx_ms`, czasy pierwszej ramki z GPIO2 |
| `RXPER` | zwraca i zeruje liczniki odbioru: `rx_ok`, `rx_bad`, `missing`, `reordered`, `overflow`, `per_percent`, średnie RSSI i LQI |
| `FOFF [<hz>]` | korekta częstotliwości w Hz (±1 MHz, krok 30,5 Hz) do restartu; bez argumentu odczyt |
| `STOP` | przerwanie `TXCW`, `TXPKT` i odbioru |
| `LOG [<n>]` | ostatnie `n` (domyślnie 16, do 64) zdarzeń z dziennika w FRAM, od najnowszego, z numerem i czasem pracy; bez FRAM 16 wpisów z RAM |
| `JOURNAL` | stan dziennika: rekord długu (numer, dług, czas zapisu, liczba poprawnych rekordów), zegar (numer, czas pracy, restarty), numer ostatniego zdarzenia, największy dług |
| `BENCH` | stan trybu przygotowania, ciszy, zadań i długu |
| `RSSI` | RSSI w dBm z przyjętym przesunięciem −99 dB (`rssi_offset_db`), znaczniki ważności i nośnej; sens tylko w stanie RX |
| `STATE` | stan MARC nazwą i liczbą, bajt stanu, liczba bajtów w kolejkach RX i TX |
| `REG <hex>` | odczyt rejestru, np. `REG 2F73` (MARCSTATE), `REG 2F0C` (FREQ2) |
| `FRAM` | cztery bajty RDID (MB85RS4MT: `047F4903`, MB85RS4MTY: `047F490B`), rejestr stanu, `ok` |
| `BTN` | stan czterech przycisków |
| `LED <1-4> <0/1>` | sterowanie diodą |

Warunek przejścia kroku 6 z [lekcji R02](../hardware/r02/lekcje.md#uruchomienie): `RADIO` daje `ready: true`, `partnumber: 0x48` i stan `IDLE`; `FRAM` daje `fujitsu: true`. Bez modułu `partnumber` wynosi `0xFF` albo `0x00`, a `ready` jest `false`. Po starcie obraz sam zapisuje i kalibruje P1; LED2 świeci dopiero, gdy `RADIO` daje `ok: true` i `p1_ok: true`. Po otwarciu portu obraz wysyła też wynik `VERIFY` i `FREQ`.

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
- **Stała długość pakietu zamiast zmiennej.** W trybie zmiennej długości układ czyta pierwszy bajt po słowie synchronizacji jako liczbę następnych bajtów i kończy odbiór po nich. Pole LEN w P1 liczy tylko BODY, a CRC jest za BODY, więc układ uciąłby CRC. Do rozstrzygnięcia w specyfikacji ([przegląd, F79](../docs/review.md)): LEN liczący BODY i CRC albo odbiór w trybie nieskończonej długości z przełączeniem na stałą po odczycie LEN (SWRU295E, 8.1.5). Do tego czasu polecenia pomiarowe używają stałej długości ustawianej na ramkę.
- **Kalibracja ręczna.** SETTLING_CFG wyłącza kalibrację automatyczną (jak w eksporcie TI); oprogramowanie wykonuje po zapisie rejestrów i po każdym `CAL` procedurę z erraty CC112x (dwa przebiegi `SCAL` z różnym VCDAC_START, zostaje wynik z większym FS_VCO2), przeniesioną z `manualCalibration()` w swrc253e.
- **Weryfikacja odczytem.** Każdy rejestr tablicy jest odczytywany po zapisie i porównywany z maską (XOSC1 ma bit tylko do odczytu). Pierwsza niezgodność trafia do odpowiedzi `CONFIG`/`VERIFY`.
- **GPIO modułu.** GPIO2 (D3) = PKT_SYNC_RXTX (pakiet w powietrzu, do pomiaru czasu TX), GPIO0 (D2) = RXFIFO_THR_PKT (koniec odebranego pakietu); niepodłączone GPIO1 i GPIO3 w trybie analogowym jak w eksporcie TI.
- **Odbiornik z niską IF** 62,5 kHz (wartość domyślna) z kompensacją obrazu, bo warunek IF > 2 × 25 kHz i IF + 12,5 kHz ≤ 100 kHz jest spełniony; zero-IF nasycałoby RSSI przy około −50 dBm.

Czego tablica nie zamyka: błędu częstotliwości kwarcu modułu (mierzy się `FREQ`/`FOFF` na stanowisku), przesunięcia RSSI i progu CCA (T4), dopasowania filtru DC, AGC i progu synchronizacji do 4800 Bd (eksport TI dotyczy 1200 Bd w tym samym paśmie; różnice sprawdza pomiar czułości w T4) oraz wartości z nowszej wersji SmartRF Studio (eksport z pakietu z 2013 r.; przy dostępie do narzędzia porównać tablicę z eksportem dla P1 i wpisać wersję narzędzia do nagłówka).

## Polecenia pomiarowe

Kontrakt jest w [specyfikacji radia](../docs/spec/radio.md#usb-do-laptopa); kod w `src/measure.cpp`. Polecenia działają tylko w trybie przygotowania (`PREP 1`, potwierdzony przyciskiem OK, bo na stacji włącza go przycisk pod plombowaną pokrywą) i są odrzucane w ciszy radiowej (`SILENCE 1`; cisza włączona w trakcie przerywa serię, chyba że była przewodowa). Odpowiedzi odmowne mają pole `error`.

Limit nadawania na stanowisku: po każdej serii obowiązuje dług ciszy 12 × czas nadawania (jak w P1), widoczny w `INFO` jako `tx_wait_ms`, a seria bez argumentu `CONDUCTED` nie może przekroczyć 1,4 s czasu nadawania, czyli najdłuższego datagramu P1 (7 ramek po 103 B z narastaniem mocy). Specyfikacja nie podaje tej liczby wprost; to przyjęta interpretacja. `CONDUCTED` znosi oba ograniczenia wyłącznie do nadawania przewodowego do tłumika lub obciążenia sztucznego: obraz prosi o przycisk OK, czeka na niego do 30 s (LED1 miga szybko) i zapisuje potwierdzenie albo jego brak w dzienniku `LOG`. Dług jest zapisywany w [dzienniku FRAM](#dziennik-w-fram) przed pierwszą ramką serii; błąd zapisu albo brak FRAM blokuje nadawanie radiowe. Seria `CONDUCTED` (do obciążenia, bez emisji) nie tworzy długu.

- **`TXCW`** przełącza układ na 2-FSK z dewiacją 0, dane z generatora PN9 i pakiet nieskończony, więc wychodzi sama nośna; po czasie albo po `STOP` przywraca rejestry P1. Do pomiaru częstotliwości (potem `FOFF`) i mocy.
- **`TXPKT`** nadaje ramki wzorcowe (`src/testframe.cpp`): numer porządkowy 2 B, wypełnienie PN9 zależne od numeru, na końcu CRC-16 ramki P1; test na komputerze (`tests/test_firmware_host.py`) porównuje CRC i ramkę z modelem. Dla pierwszej ramki obraz mierzy z GPIO2 (PKT_SYNC_RXTX) czas od `STX` do słowa synchronizacji (`lead_ms`: ustalenie syntezera, narastanie, preambuła), czas pakietu w powietrzu (`on_air_ms`, oczekiwane `len` × 8 / 4800) i ogon do IDLE (`tail_ms`); to wejście do parametru `ramp_ms` modelu. Bez przewodu na D3 jest `sync_gpio: false`, a czasy liczy się ze stanu MARC.
- **`RX <len>`** ustawia stałą długość pakietu i odbiór ciągły; obraz czyta kolejkę co 5 ms, sprawdza CRC i numer, a `RXPER` zwraca liczniki i je zeruje. `missing` to luki w numeracji, `reordered` numer nie większy od poprzedniego, `overflow` przepełnienia kolejki. `rssi_avg_dbm` używa przyjętego przesunięcia −99 dB.
- **`FOFF`** przelicza Hz na FREQOFF (równanie 27 instrukcji), zapisuje w IDLE i wraca do odbioru, jeśli trwał; po `CONFIG` wartość jest zapisywana ponownie, po `RESET` lub restarcie znika.

Przebieg pomiaru czułości: na nadajniku `PREP 1`, `TXPKT 2000 103 50 CONDUCTED`; na odbiorniku `PREP 1`, `RX 103`, po serii `RXPER`. PER ≤1% przy 2000 ramek oznacza najwyżej 20 ramek w `rx_bad` plus `missing`.

## Dziennik w FRAM

Kod w `src/journal.cpp` (bez zależności od Arduino, sprawdzany na komputerze z pamięcią w RAM w `tests/test_firmware_host.py`) i `src/fram.cpp` (odczyt i zapis MB85RS4MT, adres 3-bajtowy). Wymagania: [dostęp do kanału](../docs/spec/radio.md#dostęp-do-kanału) (dziennik długu ciszy) i [oprogramowanie](../docs/spec/oprogramowanie.md) (licznik czasu pracy co 60 s, dziennik zdarzeń 32 KiB). Obszar nie jest szyfrowany i ma przetrwać ZNISZCZ DANE; ta operacja nie jest jeszcze zaimplementowana.

| Pierścień | Adres w FRAM | Rekordy | Treść rekordu |
|---|---|---|---|
| dług ciszy | 0x0000 | 32 × 16 B | numer, dług [ms], czas pracy przy zapisie, CRC-16, znacznik zatwierdzenia |
| zegar | 0x0200 | 32 × 16 B | numer, czas pracy [s], liczba restartów, CRC-16, znacznik zatwierdzenia |
| zdarzenia | 0x1000 | 512 × 64 B (32 KiB) | numer, czas pracy, tekst do 53 znaków, CRC-16 |

Zasady:

- **Zapis dwufazowy.** Rekord długu i zegara trafia do najstarszego slotu (numer modulo 32) najpierw z zerowym znacznikiem, potem zapisywany jest sam znacznik zatwierdzenia, a na końcu rekord jest odczytywany i porównywany. Zanik zasilania w trakcie zostawia poprzedni rekord; dziennik ma zawsze co najmniej dwa poprawne rekordy, jeśli były zapisane. Numer 0 i 0xFFFFFFFF są nieważne, więc nowa pamięć (same 0x00 albo 0xFF) nie daje fałszywych rekordów.
- **Dług przed serią.** `TXCW` i `TXPKT` zapisują 12 × zaplanowany czas nadawania przed pierwszą ramką; po odczekaniu obraz zapisuje rekord z długiem 0 i zdarzenie „silence debt cleared”. Po restarcie odczekiwany jest cały ostatni zapisany dług (`INFO` → `tx_wait_ms`).
- **Brak poprawnego rekordu** (nowa FRAM, uszkodzenie): obraz odczekuje największy możliwy dług `MAX_DEBT_MS` = 16 228 ms (12 × czas nadawania datagramu 600 B z założonym narastaniem 2 ms na fragment, liczony jak w modelu i sprawdzany testem), zakłada nowy dziennik i podaje `journal_resets: 1` w `INFO`.
- **Zegar.** Rekord zegara przy starcie (restarty +1) i co 60 s; `uptime_s` w `INFO` liczy się od wartości z dziennika, więc jest monotoniczny między restartami. Nieudany zapis zegara gasi LED3 i `journal_ok`.
- **Zdarzenia.** Każdy wpis `LOG` (start, tryb przygotowania, cisza, serie, potwierdzenia `CONDUCTED`, `FOFF`, kasowanie długu) jest rekordem w FRAM; bufor nadpisuje najstarsze po 512 wpisach. Przy starcie obraz czyta wszystkie 36 KiB obszaru (około 0,3 s przy 1 MHz), żeby znaleźć najnowsze rekordy.

Nie ma jeszcze: kolejki zgłoszeń, skrzynki, tablicy tras ani rekordów szyfrowanych ze specyfikacji; układ obszaru dla stacji (role stacji i OSP) zostanie uzgodniony przy tych strukturach, a dziennik tu opisany ma w nim zostać na tych samych adresach.

## Następne kroki

1. Ekran Sharp (Adafruit 4694) z EXTCOMIN z licznika sprzętowego; przyciski jako menu stacji.
2. Ramka P1 w C++ sprawdzona na wektorach z [modelu](../software/reference/README.md) po rozstrzygnięciu F79; dwa interfejsy CDC (dane i diagnostyka).
3. microReticulum i LXMF na tym samym projekcie (T3) z pomiarem zapasu RAM; środowisko `bench-b` dla ESP32-S3-DevKitC-1 z S2-LP.
