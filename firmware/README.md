# WICI: oprogramowanie stacji

Katalog zawiera oprogramowanie układowe stacji. Obecny stan to pierwsze kroki na [stanowisku deweloperskim A](../hardware/dev-bench/README.md): nRF52840-DK z modułem TI CC1120EM-868-915 i pamięcią FRAM na złączu Arduino płytki. Środowisko `bench-a` w `platformio.ini` buduje obraz, który po podłączeniu USB zgłasza się poleceniem `INFO` w formacie ze [specyfikacji radia](../docs/spec/radio.md#usb-do-laptopa), identyfikuje układ radiowy i FRAM przez SPI, zapisuje do CC1120 [rejestry profilu P1](#rejestry-profilu-p1) z weryfikacją odczytu i kalibracją syntezera, wykonuje [polecenia pomiarowe](#polecenia-pomiarowe) `TXCW`, `TXPKT`, `RXPER`, `FOFF` ze specyfikacji, prowadzi [dziennik w FRAM](#dziennik-w-fram) (dług ciszy, zegar czasu pracy z liczbą restartów, zdarzenia), obsługuje [łącze P1](#łącze-p1) (odbiór i składanie datagramów, nadawanie z CCA, odroczeniem i długiem ciszy), podaje zaprogramowaną częstotliwość i RSSI, prowadzi [ekran Sharp i menu stacji](#ekran-i-przyciski) na przyciskach płytki (wybór języka, ekran główny, cisza, STAN; EXTCOMIN z licznika RTC2) obsługuje diody płytki oraz udostępnia drugi interfejs CDC z [protokołem USB laptop–stacja](#protokół-usb-laptopstacja) nad kolejką, skrzynką i konfiguracją w FRAM oraz [warstwę aplikacji](#warstwa-aplikacji-nad-p1) nadającą intencje z kolejki przez P1 i przyjmującą wiadomości do skrzynki. Nie ma jeszcze stosu Reticulum: datagram ma zastępczy format bez podpisu.

Obraz skompilowano (PlatformIO, rdzeń Adafruit nRF52 1.7.0, 51 004 B RAM, 174 592 B flash; podział w [przeglądzie rozmiaru](#rozmiar-i-wydajność)). **Nie uruchomiono go na sprzęcie**: odpowiedzi poleceń, numery pinów, działanie SPI z modułem i przyjęcie rejestrów przez układ wymagają sprawdzenia na płytce według kroków niżej.

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

Ekran ma na płytce przetwornicę 5 V i translację poziomów, więc VIN idzie z VDD płytki (3,0 V). Zworka EXTMODE płytki ekranu musi być w położeniu H (VCOM z pinu EXTCOMIN); nazwy pinów złącza 4694 i położenie zworki sprawdzić na płytce przed lutowaniem, bo nie zostały potwierdzone w dokumentacji Adafruit dostępnej w tym kroku. Gdy zworka jest w położeniu L, `VCOM 1` przełącza odwracanie VCOM na bit w poleceniach ekranu.

Przyciski płytki: BUTTON1 = GÓRA, BUTTON2 = DÓŁ, BUTTON3 = OK, BUTTON4 = WSTECZ (menu stacji, patrz [Ekran i przyciski](#ekran-i-przyciski)). Diody: LED1 bicie serca (0,5 s), LED2 radio rozpoznane, LED3 FRAM rozpoznana i dziennik uruchomiony, LED4 port USB otwarty przez hosta. Przewody do 5 cm; SPI pracuje z 1 MHz.

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

Port USB nRF (J3, nie port J-Link J2) zgłasza się jako urządzenie z dwoma interfejsami CDC ACM z deskryptorami IAD: „WICI diagnostyka” (pierwszy port, polecenia z tej tabeli) i „WICI dane” (drugi port, [protokół laptop–stacja](#protokół-usb-laptopstacja)); identyfikatory VID/PID są testowe z rdzenia Adafruit, do przydziału przed wydaniem. 115200 bit/s (prędkość nie ma znaczenia dla USB). Każda odpowiedź to jeden wiersz JSON. Po otwarciu portu diagnostyki obraz sam wysyła `INFO`, `RADIO` i `FRAM`.

| Polecenie | Odpowiedź |
|---|---|
| `INFO` | pola jak w specyfikacji radia: `contract`, `profile`, `radio`, `mcu`, `fw`, `src`, `mv` (zero, brak pomiaru), `tx_wait_ms` (pozostały dług ciszy), `rx_ok`, `rx_bad`, `tx_drop` z łącza P1, `restarts` i `uptime_s` z dziennika FRAM, oraz `bench`, `prep`, `silence`, `radio_ok`, `p1_ok`, `fram_ok`, `journal_ok`, `journal_resets`, parametry P1, `boot_s`, `screen`, `lang`, `name` (`WICI-xxxxxx` z identyfikatora układu), `reset_reason` (RESETREAS), `store_ok`, `queued`, `inbox`, `pending` (zdarzenia bez `ack`), `usb_data` (port danych otwarty), liczniki wierszy protokołu i `usb_boot` |
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
| `P1RX` | odbiór ramek P1 w tle (zmienna długość, LEN do 102); każda ramka i złożony datagram jako wiersz JSON |
| `P1TX <hex>` | nadanie datagramu 1–600 B zapisanego szesnastkowo: fragmentacja, losowy identyfikator, dług ciszy, CCA, odroczenia; wynik w wierszu `p1tx` po zakończeniu |
| `P1` | liczniki łącza: ramki, datagramy, odrzuty, odroczenia, stan składania |
| `STOP` | przerwanie `TXCW`, `TXPKT`, `P1TX` i odbioru |
| `LOG [<n>]` | ostatnie `n` (domyślnie 16, do 64) zdarzeń z dziennika w FRAM, od najnowszego, z numerem i czasem pracy; bez FRAM 16 wpisów z RAM |
| `JOURNAL` | stan dziennika: rekord długu (numer, dług, czas zapisu, liczba poprawnych rekordów), zegar (numer, czas pracy, restarty), numer ostatniego zdarzenia, największy dług |
| `BENCH` | stan trybu przygotowania, ciszy, zadań i długu |
| `RSSI` | RSSI w dBm z przyjętym przesunięciem −99 dB (`rssi_offset_db`), znaczniki ważności i nośnej; sens tylko w stanie RX |
| `STATE` | stan MARC nazwą i liczbą, bajt stanu, liczba bajtów w kolejkach RX i TX |
| `REG <hex>` | odczyt rejestru, np. `REG 2F73` (MARCSTATE), `REG 2F0C` (FREQ2) |
| `FRAM` | cztery bajty RDID (MB85RS4MT: `047F4903`, MB85RS4MTY: `047F490B`), rejestr stanu, `ok` |
| `BTN` | stan czterech przycisków |
| `LED <1-4> <0/1>` | sterowanie diodą |
| `SCREEN` | treść ekranu: nazwa ekranu, język, pięć wierszy i które są odwrócone, liczba odświeżeń |
| `KEY <UP\|DOWN\|OK\|BACK> [ms]` | naciśnięcie przycisku z portu USB (próby bez dotykania płytki), z czasem przytrzymania w ms; odpowiedź jak `SCREEN` |
| `DISPLAY` | EXTCOMIN: licznik RTC2 i stan pinu, tryb VCOM, liczba odświeżeń, numery pinów |
| `VCOM <0\|1>` | zapasowe odwracanie VCOM bitem w poleceniach ekranu (zworka EXTMODE w położeniu L) |
| `REBOOT` | restart programowy; ekran i język wracają jak po restarcie przez watchdog |
| `STORE` | magazyn FRAM: konfiguracja (rola, adres, OSP, frazy), kolejka, skrzynka, zdarzenia bez `ack`, liczniki protokołu |
| `USB <wiersz JSON>` | wiersz protokołu danych podany przez port diagnostyki (próby z jednym terminalem); odpowiedź idzie na port danych, a gdy jest zamknięty, na diagnostykę |
| `APP` | warstwa aplikacji: intencja w drodze, liczniki nadanych, dostarczonych, nieudanych, odebranych, odrzuconych, duplikatów, potwierdzeń łącza, następna intencja do nadania |
| `LINK <0\|1>` | zatrzymanie i wznowienie nadawania z kolejki (próby ręczne `P1TX` przy zatrzymanym) |

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
- **Stała długość pakietu w tablicy.** Polecenia pomiarowe nadają ramki wzorcowe bez pola LEN, więc tablica ustawia stałą długość z PKT_LEN. Sterownik P1 przełączy układ na zmienną długość (LENGTH_CONFIG = 01, PKT_LEN = 102): od rozstrzygnięcia F79 pole LEN ramki P1 liczy BODY i CRC, czyli dokładnie to, co silnik pakietów odbiera po bajcie długości ([przegląd, F79](../docs/review.md)).
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
| ustawienia ekranu | 0x0400 | 32 × 16 B | numer, język + 1 (0 = niewybrany), ostatni ekran, CRC-16, znacznik zatwierdzenia |
| zdarzenia | 0x1000 | 512 × 64 B (32 KiB) | numer, czas pracy, tekst do 53 znaków, CRC-16 |
| konfiguracja (`src/store.cpp`) | 0x9000 | 2 × 4 KiB | rola, adres, skróty OSP, liczba stacji, 11 fraz × 3 języki, IFAC; nowszy z dwóch slotów |
| kolejka wychodząca | 0x10000 | 128 × 512 B | intencja: typ, klucz (odbiorca, id, revision, event), treść SA1 kanoniczna; część zmienna: stan, próby, następna próba, najwyższy event |
| skrzynka odbiorcza | 0x20000 | 128 × 512 B | wiadomość od OSP albo (rola OSP) `incoming`: źródło, klucz, treść; część zmienna: przeczytana |
| zdarzenia do laptopa | 0x30000 | 128 × 512 B | pola JSON `event`/`incoming`; część zmienna: `ack` |
| najwyższy event na id | 0x40000 | 256 × 32 B | id, revision, event, stan; zostaje po ZAMKNIJ ZDARZENIE |

Zasady:

- **Zapis dwufazowy.** Rekord długu i zegara trafia do najstarszego slotu (numer modulo 32) najpierw z zerowym znacznikiem, potem zapisywany jest sam znacznik zatwierdzenia, a na końcu rekord jest odczytywany i porównywany. Zanik zasilania w trakcie zostawia poprzedni rekord; dziennik ma zawsze co najmniej dwa poprawne rekordy, jeśli były zapisane. Numer 0 i 0xFFFFFFFF są nieważne, więc nowa pamięć (same 0x00 albo 0xFF) nie daje fałszywych rekordów.
- **Dług przed serią.** `TXCW` i `TXPKT` zapisują 12 × zaplanowany czas nadawania przed pierwszą ramką; po odczekaniu obraz zapisuje rekord z długiem 0 i zdarzenie „silence debt cleared”. Po restarcie odczekiwany jest cały ostatni zapisany dług (`INFO` → `tx_wait_ms`).
- **Brak poprawnego rekordu** (nowa FRAM, uszkodzenie): obraz odczekuje największy możliwy dług `MAX_DEBT_MS` = 16 228 ms (12 × czas nadawania datagramu 600 B z założonym narastaniem 2 ms na fragment, liczony jak w modelu i sprawdzany testem), zakłada nowy dziennik i podaje `journal_resets: 1` w `INFO`.
- **Zegar.** Rekord zegara przy starcie (restarty +1) i co 60 s; `uptime_s` w `INFO` liczy się od wartości z dziennika, więc jest monotoniczny między restartami. Nieudany zapis zegara gasi LED3 i `journal_ok`.
- **Zdarzenia.** Każdy wpis `LOG` (start, tryb przygotowania, cisza, serie, potwierdzenia `CONDUCTED`, `FOFF`, kasowanie długu) jest rekordem w FRAM; bufor nadpisuje najstarsze po 512 wpisach. Przy starcie obraz czyta wszystkie 36 KiB obszaru (około 0,3 s przy 1 MHz), żeby znaleźć najnowsze rekordy.

Rekordy kolejki, skrzynki, zdarzeń i konfiguracji nie są szyfrowane (AEAD z kluczem w chronionej pamięci MCU przyjdzie razem ze stosem i tożsamością). Część zmienna rekordu ma własne CRC i znacznik; jej uszkodzenie cofa intencję do stanu „aktywna, 0 prób”, a treść zostaje. Nie ma jeszcze tablicy tras ani kart zaufanych stacji (rola OSP).

## Łącze P1

Kodek i składanie ramek są w `src/p1frame.cpp` (bez zależności od Arduino): fragmentacja datagramu do 600 B na ramki `LEN | BODY | CRC` z LEN liczącym BODY i CRC (F79), rozbiór ramki z pełną kontrolą pól i składanie według [specyfikacji radia](../docs/spec/radio.md#ramka-w-eterze): 8 prób po 120 s, poprawne duplikaty pomijane, sprzeczny duplikat albo zmiana liczby fragmentów lub długości usuwa próbę, przy przepełnieniu odpada próba z najmniejszą liczbą fragmentów, 16 ostatnio złożonych identyfikatorów odrzuca spóźnione duplikaty. Test na komputerze (`tests/test_firmware_host.py`) porównuje ramki z modelem bajt po bajcie dla wszystkich długości 1–600 B i odtwarza przypadki wrogie z testów modelu.

Łącze w `src/measure.cpp`:

- **Odbiór** (`P1RX`): układ w trybie zmiennej długości z PKT_LEN = 102, więc ramki dłuższe odrzuca sam; obraz czyta bajt LEN, czeka na resztę ramki i dwa bajty statusu (RSSI, LQI), rozbiera ramkę i oddaje ją składaniu. Ramki za krótkie, niekompletne w czasie albo z błędem rozbioru liczą się jako `rx_bad`. Każda ramka daje wiersz `p1rx` ze stanem składania, a złożony datagram wiersz z identyfikatorem i danymi szesnastkowo.
- **Nadawanie** (`P1TX`): datagram czeka na koniec długu ciszy, potem 50 ms wolnego kanału (RSSI poniżej progu −100 dBm przy przyjętym przesunięciu RSSI i brak odbioru po słowie synchronizacji na GPIO2). Zajęty kanał odracza nadanie o losowe 100–1000 ms (`deferrals`; łączne czekanie ponad 1 s liczy się jako `long_deferrals`), po 30 odroczeniach datagram jest odrzucany (`tx_drop`; liczba jest wyborem stanowiska, specyfikacja nie podaje limitu). Przed pierwszą ramką do dziennika trafia dług 12 × zarezerwowany czas serii (liczony dla najdłuższych ramek), potem fragmenty idą jedną serią, a odbiór wraca od razu po serii. Cisza radiowa przerywa i odrzuca nadanie. Identyfikator datagramu pochodzi z generatora sprzętowego nRF52840 (RNG z korekcją obciążenia), który daje też ziarno odroczeń.
- **Dwie płytki**: na obu `P1RX`; na jednej `P1TX 48656C6C6F` („Hello”); druga wypisuje `p1rx` z `datagram`. Datagram 600 B to 7 ramek i około 1,4 s nadawania, po nim 16 s długu.

Nie ma jeszcze interfejsu do stosu Reticulum (datagramy trafiają tylko na port USB), rezerwacji 50% budżetu dla ruchu do OSP, osobnych limitów ogłoszeń ani drugiego interfejsu CDC.

## Ekran i przyciski

Wymagania: [ekran i przyciski stacji](../docs/spec/oprogramowanie.md#ekran-i-przyciski-stacji) i tabela tekstów ekranu w tym samym rozdziale. Kod w trzech warstwach:

- **Teksty** (`src/ui_texts.h`, generowany przez `tools/ui_texts.py`): wszystkie tabele rozdziału „Teksty ekranu” (teksty z identyfikatorami, pozycje menu, przyciski, kategorie, gotowe frazy) w trzech językach, jednostki `[czas]` i separator dziesiętny z opisu. Test `tests/test_ui_texts.py` odrzuca nieaktualny nagłówek i sprawdza limity 20 znaków pozycji menu i kategorii.
- **Font** (`src/font_glyphs.h`, generowany przez `tools/font_bitmap.py` z `fonts/DejaVuSansMono-Bold.ttf`): 182 glify po 20 × 40 px (ASCII, alfabet polski i ukraiński, każdy znak tekstów kanonicznych, U+FFFD jako glif zastępczy), 33 px kroju o stałej szerokości, pięć wierszy po 20 znaków z krokiem 48 px na ekranie 400 × 240. Licencja fontu (Bitstream Vera, zmiany DejaVu w domenie publicznej) jest w `fonts/LICENSE.txt` i `LICENSES/`; wygenerowana bitmapa zachowuje tę licencję na kształty liter. Wersaliki mają 24 px, czyli **3,5 mm** na panelu LS027B7DH01 (58,8 mm szerokości): 20 znaków w wierszu i wersaliki ≥4 mm nie dają się pogodzić na tym panelu krojem o stałej szerokości ([przegląd, F80](../docs/review.md)).
- **Model ekranu** (`src/ui.cpp`, bez zależności od Arduino, sprawdzany na komputerze w `tests/test_firmware_host.py`): daje pięć wierszy UTF-8 obciętych do 20 znaków i znacznik wiersza odwróconego; rysowanie i przyciski są poza nim. Ekrany: wybór języka (POLSKI, УКРАЇНСЬКА, ENGLISH; tych nazw nie ma w kanonicznej liście tekstów, F80), ekran główny (`radio_wlaczone`, `kontakt_ponad_krotki` z czasem pracy jako dolnym oszacowaniem, `zasilanie_12v`, `kolejka_krotki` albo pusty wiersz, `nowe_krotki`), cisza (`cisza` w wierszach 1–3, potem zasilanie i kolejka), menu (ZGŁOSZENIE, WIADOMOŚCI, TEST, STAN, JĘZYK/МОВА/LANGUAGE; wybrana pozycja odwrócona, bo znak kursora nie mieści się obok etykiet 20-znakowych), STAN z przewijaniem GÓRA/DÓŁ (radio, liczniki łącza, dług ciszy, `ostatni_kontakt_ponad`, zasilanie, odchyłka częstotliwości z FREQOFF_EST, wersja, nazwa `WICI-xxxxxx`), JĘZYK. W trybie przygotowania wiersz 1 każdego ekranu to `tryb_przygotowania`, a lista zajmuje cztery wiersze. Test sprawdza krótkie formy z największymi wartościami (99 MIN, 128 zgłoszeń, 128 wiadomości) we wszystkich językach, łamanie `cisza` na trzy wiersze, format `[czas]` (99 MIN → 1 H → 47 H → 2 D → 99 D) i pokrycie glifami każdego znaku tekstów.
- **Sterownik ekranu** (`src/sharp.cpp`): bufor 240 × 50 B, zapis tylko zmienionych wierszy poleceniem M0 (bity LSB-first, CS aktywny stanem wysokim, 2 MHz, 8 bitów odstępu po wierszu i 16 na końcu). **EXTCOMIN** generuje licznik RTC2 (preskaler 4095, COMPARE0 = 4, czyli 0,5 s) przez PPI do zadania GPIOTE przełączającego pin i do zerowania licznika: przebieg 1 Hz bez udziału programu i bez HFCLK, jak wymaga specyfikacja; `DISPLAY` pokazuje licznik i stan pinu. Zapasowo `VCOM 1` odwraca VCOM bitem w poleceniu co 500 ms (zworka EXTMODE w położeniu L). Przyciski są odpytywane co 10 ms (zbocze = naciśnięcie), ekran rysowany po zmianie treści, nie częściej niż co 200 ms.

Po włączeniu zasilania pierwszym ekranem jest wybór języka; wybór i każda zmiana ekranu trafiają do pierścienia ustawień w FRAM i do pamięci RAM niezerowanej przy starcie (sekcja `.noinit`), więc po restarcie programowym (`REBOOT`; watchdog działa tak samo, ale nie jest jeszcze włączony) stacja wraca do języka i ekranu sprzed restartu bez pytania. Radio startuje niezależnie od ekranu, jak wymaga specyfikacja.

Przyjęte interpretacje i braki: pasek trybu przygotowania zastępuje wiersz 1 („stale pokazuje”); każdy ekran poza głównym wraca do ekranu głównego po 3 min bezczynności (specyfikacja podaje ten czas tylko dla kreatora); przy niesprawnym radiu wiersz 1 to `RADIO ---`, bo lista tekstów nie ma takiego tekstu (F80); zasilanie to `12 V: 0,0 V`, bo stanowisko nie mierzy napięcia; etykiety liczników w STAN (`RX OK`, `TX`, `DEFER`, `WAIT`, `FOFF`) są jednakowe we wszystkich językach. Nie ma podświetlenia (płytka 4694 go nie ma), sygnału dźwiękowego ani diody NOWA WIADOMOŚĆ / ALARM.

### Ekrany stacji

Przepływy ekranów są w modelu (`src/ui.cpp`), a dane i działania dostarcza mu `src/console.cpp` (interfejs `ui::Host`) nad magazynem FRAM i warstwą aplikacji; `tests/test_firmware_host.py` uruchamia model z magazynem w RAM i sprawdza każdy przepływ na tekstach kanonicznych. Przyciski: GÓRA, DÓŁ i OK działają przy naciśnięciu, WSTECZ przy zwolnieniu, bo przytrzymanie WSTECZ ma inne znaczenie (2 s w kreatorze: `porzucic`; 3 s poza nim: wybór języka).

| Ekran | Działanie |
|---|---|
| start | po wyborze języka `adres_kontrola` z adresem z konfiguracji (WSTECZ = NIE albo brak adresu: `adres_brak`), potem propozycja TEST startowego: OK planuje TEST z losowym opóźnieniem w oknie 50 s × liczba stacji z `configure` (bez niej 15 min) i pokazuje `test_zaplanowany`; WSTECZ pomija |
| ZGŁOSZENIE | kategoria 0–9 → liczba osób z listy 1, 2, 5, 10, 20, 50, 100, INNA (wpis setek, dziesiątek i jednostek; przytrzymanie przycisku powtarza zmianę co 150 ms; domyślnie ostatnio użyta wartość) → pilność bez wartości domyślnej (`pilnosc_2` wymaga `pilnosc_2_potw`) → fraza z konfiguracji albo domyślna lista (kategoria 9 bez pozycji „brak”) → podsumowanie z `podsumowanie_klawisze` → wynik: `zapisane_w_stacji` albo `zapisane_w_ciszy` z `zapisz_numer`, `kolejka_pelna`, `blad_pamieci`, `adres_brak`. WSTECZ cofa o krok; szkic zostaje po powrocie do ekranu głównego. Zgłoszenie dostaje `location` z adresu konfiguracji, id z generatora sprzętowego losowane ponownie, dopóki krótki numer (pierwsze 16 bitów modulo 10 000) jest zajęty w kolejce; `submit` z laptopa o zajętym numerze dostaje `rejected` z `numer_zajety` |
| WIADOMOŚCI | lista najnowszych najpierw: własne zgłoszenia i TEST w najnowszej rewizji (`NNNN` i kategoria), odpowiedzi i komunikaty (`*` przed nieprzeczytaną treścią). Własne: etap (`zapisane_w_stacji`, `wysylanie` z próbą i czasem do następnej, `zapisane_w_ciszy`, `stan_1`…`stan_6`, ANULUJ WYSYŁKĘ po anulowaniu), kategoria, liczba osób i pilność, fraza w wybranym języku, `zapisz_numer`; OK otwiera ZMIEŃ LICZBĘ OSÓB, ZMIEŃ PILNOŚĆ, POTRZEBA USTAŁA (nowa rewizja tego samego id; nienadana starsza rewizja zostaje oznaczona jako zastąpiona) i ANULUJ WYSYŁKĘ (tylko przed `stan_1`; wpis w dzienniku). Odebrane: `odpowiedzi_po_polsku` (UK, EN), treść, czas od odbioru, dla komunikatu `stopka_komunikatu`; otwarcie oznacza jako przeczytane |
| TEST | `test_zaplanowany` (WSTECZ anuluje), `test_wyslany`, stan po RECEIVED/STATUS albo `test_wstrzymany`; OK otwiera menu TEST (nadanie od razu) i WSTRZYMAJ (anuluje czekający TEST i blokuje nadawanie TEST) / WZNÓW |
| STAN | wiersze stanu z kursorem, na końcu PRZEKAZANIE ZMIANY (otwarte zgłoszenia z etapem, nieprzeczytane, cisza, zasilanie) i USŁUGI: ODBIORCA ZAPASOWY (`odbiorca_zapasowy`, przełącza `to` nowych intencji na zapasową tożsamość z konfiguracji) i ZNISZCZ DANE (`zniszcz_ostrzezenie`; usuwa konfigurację, kolejkę, skrzynkę, zdarzenia, klucze odbioru i dziennik zdarzeń, zostawia dług ciszy i zegar); obie wymagają sekwencji GÓRA, DÓŁ, GÓRA, OK, inny przycisk zaczyna od nowa |
| alarm | `brak_potwierdzenia` po 15 min / 1 h / 6 h od zapisu według pilności (TEST: 30 min od nadania) i `brak_odczytu` 30 min po `stan_1` dla pilności 2; zajmuje cały ekran, OK potwierdza (alarm tego zgłoszenia nie wraca), `zapisz_numer` wskazuje zgłoszenie |

Braki tego kroku: ogłoszenie adresu i wyciszenie dźwięku w USŁUGACH (bez stosu i brzęczyka), lista adresów obiektów, powrót ekranu alarmu po wybudzeniu (bez podświetlenia), watchdog.

## Audyt kodu stanowiska

Przegląd całego kodu stacji po kroku ekranów (`store`, `station`, `console`, `usbproto`, `ui`, `sa1`, `jsonlite`, `measure`, `sharp`, `journal`, `main`) dał poprawki:

- **Stos zadania.** Zadanie `loop()` rdzenia Adafruit ma 4 KB stosu, a `configure` przez USB (kopia konfiguracji 3,3 KB) i rysowanie ekranu z odczytem rekordów FRAM potrzebują więcej. Cała praca stacji biegnie teraz w osobnym zadaniu FreeRTOS z 16 KB stosu (`Scheduler.startLoop`), a zadanie rdzenia jest zawieszone; zapis konfiguracji idzie do FRAM kawałkami z narastającym CRC zamiast przez bufor 3,3 KB na stosie.
- **Ponowne użycie slotu.** Nowy rekord w slocie zakończonego rekordu najpierw kasuje stary znacznik zatwierdzenia, potem zapisuje stan i część stałą: zanik zasilania między zapisem stanu a zapisem części stałej nie ożywi starej intencji z nowym stanem.
- **ZNISZCZ DANE** przez USB i z ekranu kasuje również dziennik zdarzeń w FRAM (dług ciszy, zegar i ustawienia zostają, jak w specyfikacji).
- **ODBIORCA ZAPASOWY** odmawia przełączenia, gdy konfiguracja nie ma zapasowej tożsamości OSP.
- Potwierdzenie łącza dla intencji anulowanej albo zastąpionej jest ignorowane; `kolejka_krotki` liczy tylko intencje bez potwierdzenia łącza.

Ograniczenia, które zostają do stosu i kluczy: krótki numer zgłoszenia jest sprawdzany tylko w kolejce (pamięć kluczy odbioru nie ma indeksu numerów); bez karty OSP stacja przyjmuje wiadomości od każdego nadawcy; rekordy FRAM nie są szyfrowane; `Serial`/`SerialData` blokują zapis, gdy host otworzył port, a nie czyta (TinyUSB CDC), więc program laptopa musi czytać port danych na bieżąco; polecenia z potwierdzeniem przyciskiem (`SILENCE`, `destroy`, `conducted`) blokują pętlę stacji do 30 s.

## Protokół USB laptop–stacja

Kontrakt: [specyfikacja oprogramowania](../docs/spec/oprogramowanie.md#protokół-usb-laptopstacja) (`"usb":1`, wiersze JSON do 1024 B z `seq`, `boot` po obu stronach, idempotencja po kluczu wiadomości). Kod w `src/usbproto.cpp` (bez zależności od Arduino; scenariusze w `tests/test_firmware_host.py`), wiadomości SA1 w `src/sa1.cpp` (rozbiór, kontrola i kodowanie kanoniczne jak `reference.py`; stacja nie sprawdza NFC ani znaków nieprzydzielonych poza niecharakterami, bo tablice Unicode nie mieszczą się w zakresie tego kroku, a laptop sprawdza je przed `submit`), skaner JSON w `src/jsonlite.cpp`, magazyn w `src/store.cpp`.

| Wiersz | Działanie |
|---|---|
| `sync` (obie strony) | po otwarciu portu stacja wysyła `sync` z `boot`, `cursor` (numer ostatniego zdarzenia), `pending`, `queued`, `inbox`, `role`, `configured`, `prep`, `silence`, `name`, `fw`; `sync` od laptopa z `cursor` potwierdza zdarzenia do tego numeru, a stacja odpowiada własnym `sync` i wysyła zaległe |
| `submit` z `to`, `id`, `revision`, `sa1` (`"resend":true` uaktywnia zakończoną intencję) | kontrola SA1 jak w modelu, zgodność `id` i `revision` z tablicą, typ według roli (stacja: REQUEST i TEST; OSP: RECEIVED, STATUS, REPLY, BULLETIN), `to` równe aktywnej tożsamości OSP z konfiguracji; `stored` z numerem rekordu dopiero po zapisie w FRAM (ten sam klucz i treść: `stored` z `"duplicate":true`), `rejected` z `reason`: `invalid` (z `detail`), `conflict`, `full` (128 żywych intencji), `memory` |
| `event` / `incoming` (stacja → laptop) | `record`, `at` i pola zdarzenia (`"kind":"radio"` z `silence` i `prep`; wiadomości dojdą z łączem); zapisane w FRAM i ponawiane co 5 s do `ack` |
| `ack` z `cursor` albo `record` | potwierdzenie zdarzeń do numeru albo jednego |
| `test` | TEST z konfiguracji (kategoria 9, 1 osoba, pilność 0, adres stacji, „test”), id z generatora sprzętowego; `stored` |
| `silence` z `on` | potwierdzenie przyciskiem OK w ciągu 30 s, potem `ok`; brak potwierdzenia: `rejected` i wpis w dzienniku |
| `configure` z `address`, `role`, `osp`, `osp_backup`, `stations`, `phrases` (tablica `[PL, UK, EN]`), `ifac` | tylko w trybie przygotowania; kontrola najgorszego zgłoszenia z przycisków jak `check_button_configuration` (`worst_request` w odpowiedzi); zapis do FRAM |
| `close` | ZAMKNIJ ZDARZENIE: usuwa kolejkę, skrzynkę i zdarzenia, zachowuje najwyższy event na id |
| `destroy` | potwierdzenie przyciskiem OK, potem usunięcie konfiguracji i wszystkich rekordów (bez kluczy nie ma jeszcze nic więcej do usunięcia) |
| `announce`, `export`, `import`, `trust`, `revoke` | `rejected` z `"reason":"unsupported"` (`export` i `import` najpierw wymagają trybu przygotowania) do czasu stosu i kluczy |

Każde polecenie trafia do dziennika zdarzeń (`LOG`). Wiersz dłuższy niż 1024 B jest odrzucany w całości, niepełny wiersz sprzed zamknięcia portu również. Bez konfiguracji OSP (`configure` z `osp`) stacja przyjmuje `submit` do dowolnego `to`, bo stanowisko nie ma jeszcze kart.

## Warstwa aplikacji nad P1

Kod w `src/station.cpp` (bez zależności od Arduino; `tests/test_firmware_host.py` łączy dwie stacje w symulowanym eterze ze stratami i sprawdza przebieg REQUEST → RECEIVED → STATUS, regresję stanu, powtórzony REQUEST i źródło spoza zaufania). Po starcie łącze P1 jest w odbiorze (`P1RX`), a kolejka nadaje sama, chyba że `LINK 0`.

- **Datagram zastępczy.** Bez Reticulum i LXMF wiadomość idzie jako `["WICI",1,"<od>","<do>",<SA1>]`, a potwierdzenie łącza jako `["WICI",1,"<od>","<do>","ack","<id>",revision,typ,event]`; adresy to 32 cyfry szesnastkowe (na stanowisku z identyfikatora układu). Nie ma podpisu, szyfrowania ani IFAC: format służy wyłącznie próbom przepływu i czasu na stanowisku i znika w T3 razem ze stosem. Odbiorca potwierdza także duplikat.
- **Kolejność i ponawianie** ([specyfikacja](../docs/spec/oprogramowanie.md#trwałość-i-potwierdzenia)): RECEIVED i STATUS, potem REPLY i BULLETIN, REQUEST z pilnością 2, pozostałe REQUEST według czasu zapisu, na końcu TEST; jedna intencja w drodze. Brak potwierdzenia łącza w 60 s od końca serii = FAILED: kolejne próby po 1, 2, 5 i 15 min ±20%, po 6 h co 60 min. Potwierdzenie łącza = DELIVERED: REQUEST i TEST czekają 10 min na RECEIVED, potem ponawiają co 30–60 min; RECEIVED, STATUS, REPLY i BULLETIN są po dostarczeniu zakończone. RECEIVED, STATUS (przez `status_after`) albo REPLY od OSP kończy ponawianie pary (id, revision) i zapisuje najwyższy event w pamięci kluczy.
- **Odbiór.** Rola stacji przyjmuje RECEIVED, STATUS, REPLY i BULLETIN tylko od aktywnej tożsamości OSP z konfiguracji (bez karty: od każdego, bo stanowisko nie ma jeszcze kluczy), STATUS dla nieznanego id ignoruje; rola OSP przyjmuje REQUEST i TEST. Każda nowa wiadomość trafia do skrzynki i jako `event` (stacja) albo `incoming` (OSP) do laptopa; `nowe_krotki` na ekranie liczy nieprzeczytane. Powtórzony REQUEST lub TEST o znanym kluczu: stacja OSP nadaje ponownie zapisany RECEIVED i najnowszy STATUS.
- **Ekran.** `kolejka_krotki` liczy intencje bez potwierdzenia łącza i wiek najstarszej. Zgłoszenia z kreatora, rewizje, anulowanie, TEST z menu i startowy oraz alarmy są w tej samej warstwie (`createRequest`, `revise`, `cancel`, `scheduleTest`, `alarm`).

## Rozmiar i wydajność

Pomiar obrazu `bench-a` po audycie (`arm-none-eabi-size` i `nm --size-sort`), potem zastosowane i odłożone uproszczenia.

**RAM 51 004 B** (20,5% z 248 832 B; przed przeglądem 53 868 B):

| Obiekt | B | Uwagi |
|---|---|---|
| magazyn FRAM (`store::Store`) | 19 220 | konfiguracja z frazami 3 301 B, indeks kolejki 128 × 68 B, indeks skrzynki 128 × 48 B, indeks zdarzeń 128 × 8 B |
| bufor ekranu (`sharp::Display`) | 12 048 | 240 wierszy × 50 B i mapa zmienionych wierszy |
| stanowisko radiowe (`measure::Bench`) | 7 280 | składanie datagramów: 8 prób × 600 B (specyfikacja), bufory nadawania i złożonego datagramu po 600 B |
| konsola ekranu (`console::Console`) | 2 076 | lista WIADOMOŚCI: 256 × 8 B |
| USB CDC (TinyUSB, 2 interfejsy) | 1 712 | po wyłączeniu klas MSC, HID, MIDI, vendor i video (−3 380 B) |
| bufor poleceń diagnostyki | 1 400 | `P1TX` do 600 B szesnastkowo, `USB <json>` do 1 024 B |
| protokół USB (`usbproto::Protocol`) | 1 124 | wiersz do 1 024 B |
| FreeRTOS (zegar, bezczynność) i stos USB host rdzenia | 2 702 | host MAX3421 włączony przez rdzeń na stałe (`CFG_TUH_ENABLED` bez `#ifndef`) |
| stos zadania stacji | 16 384 | poza powyższą sumą (przydział w czasie pracy) |

**Flash 174 592 B** (21,4% z 815 104 B; przed przeglądem 187 844 B): bitmapa fontu 22 204 B, teksty ekranu w trzech językach około 20 KB i kod modelu ekranu 17 KB (`ui.cpp.o` 37 237 B), `main.cpp` 15,0 KB, `store.cpp` 13,8 KB, `measure.cpp` 12,5 KB, `usbproto.cpp` 8,0 KB, `station.cpp` 6,1 KB, `cc1120.cpp` 4,8 KB, `console.cpp` 3,5 KB, `jsonlite.cpp` 3,3 KB, `sa1.cpp` 2,9 KB, `journal.cpp` 2,8 KB, `sharp.cpp` 1,9 KB, `p1frame.cpp` 1,7 KB; reszta to rdzeń Adafruit, FreeRTOS, TinyUSB i newlib (`_dtoa_r`, `_printf_float` i arytmetyka `double`: około 8 KB, które zostają niezależnie od naszych `%f`, bo platforma dołącza `_printf_float` na stałe; zamiana własnych `%f` na formatowanie całkowite nie zmniejszyła obrazu, więc jej nie ma).

Zastosowane:

- wyłączenie nieużywanych klas TinyUSB flagami w `platformio.ini`: −3 380 B RAM, −13 668 B flash;
- listy ekranu z indeksu w RAM: pozycje WIADOMOŚCI i PRZEKAZANIE ZMIANY biorą numer, kategorię, stan i próby z indeksu kolejki (kategoria dopisana do rekordu i indeksu, +512 B RAM) zamiast czytać rekord 512 B z FRAM dla każdej pozycji przy każdym rysowaniu co 200 ms (128 zgłoszeń: 64 KB SPI, około 80 ms przy 8 MHz); treść komunikatu czyta się tylko dla widocznych wierszy (452 B na pozycję), pełny rekord po otwarciu; test `test_lists_render_from_the_ram_index` liczy bajty odczytu;
- przegląd kolejki nadawczej (`Station::poll`, 128 wpisów) co 100 ms zamiast w każdym obiegu pętli.

Odłożone (z szacunkiem zysku; każde wymaga osobnej zmiany i testów):

| Zmiana | Zysk | Koszt |
|---|---|---|
| frazy z konfiguracji czytane z FRAM na żądanie zamiast w `store::Config` | −3,2 KB RAM | `configure` zapisuje frazy bezpośrednio do FRAM, ekran czyta 97 B na wiersz listy |
| indeks kolejki bez `to` i skrzynki bez `source` (porównanie po odczycie rekordu) | −4,1 KB RAM | dodatkowy odczyt rekordu przy deduplikacji i `queueFind` |
| bufor ekranu jako pas jednego wiersza tekstu (48 × 50 B) zamiast całej ramki | −9,6 KB RAM | panel pamięta obraz; każdy wiersz trzeba rysować i wysyłać od razu, `DISPLAY`/`VCOM` bez zmian |
| lista konsoli jako 4 B na pozycję (numer rekordu z bitem kolejki, czas z indeksu) | −1 KB RAM | sortowanie z odczytem czasu z indeksu |
| CRC-16 z tablicą 512 B | przegląd FRAM przy starcie szybszy o około 25 ms | +512 B flash; `Store::begin()` czyta około 205 KB (0,3 s przy 8 MHz), CRC bitowe 384 rekordów to około 30 ms |
| mniejszy font (16 × 32 px) | −10 KB flash | wersaliki 2,8 mm zamiast 3,5 mm, przeciwnie do wymagania ≥4 mm (F80) |

Czasy, które nie wymagają zmian: alarmy sprawdzane co 1 s w indeksie 128 wpisów; `seenGet` czyta 8 KB tylko dla STATUS o nieznanym id; odświeżanie ekranu wysyła wyłącznie zmienione wiersze (240 × 52 B pełnego obrazu to 50 ms przy 2 MHz); składanie datagramu, deduplikacja i kolejność nadawania pracują na indeksach w RAM.

## Następne kroki

1. Watchdog; audyt kodu i przegląd rozmiaru.
2. microReticulum i LXMF na tym samym projekcie (T3) z pomiarem zapasu RAM; środowisko `bench-b` dla ESP32-S3-DevKitC-1 z S2-LP.
