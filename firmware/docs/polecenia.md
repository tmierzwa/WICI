# WICI: Narzędzia i polecenia diagnostyki

Część opisu oprogramowania stacji; spis części jest w [README](../README.md).

## Narzędzia

PlatformIO Core działa w osobnym środowisku Pythona. Wersje platformy i rdzenia są przypięte w `platformio.ini`: nordicnrf52 11.0.0 i framework-arduinoadafruitnrf52 1.10700.0, czyli rdzeń Adafruit nRF52 1.7.0 z TinyUSB. Dla `bench-b` jest to platforma pioarduino 55.03.312 z Arduino-ESP32 3.3.12 na ESP-IDF 5.5, bo dopiero ta wersja daje dwa interfejsy CDC przez USB-OTG (wersja 2.0.17 z oficjalnej platformy espressif32 daje jeden). Rdzeń Adafruit wybrano, bo używa go microReticulum dla nRF52840 (środowisko `wiscore_rak4631`), więc port wszedł do tego samego projektu; rdzeń Reticulum stacji tego rdzenia nie wymaga.

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

Port USB nRF (J3, nie port J-Link J2) zgłasza się jako urządzenie z dwoma interfejsami CDC ACM z deskryptorami IAD: „WICI diagnostyka” (pierwszy port, polecenia z tej tabeli) i „WICI dane” (drugi port, [protokół laptop–stacja](aplikacja.md#protokół-usb-laptopstacja)); identyfikatory VID/PID są testowe z rdzenia Adafruit, do przydziału przed wydaniem. 115200 bit/s (prędkość nie ma znaczenia dla USB). Każda odpowiedź to jeden wiersz JSON. Po otwarciu portu diagnostyki obraz sam wysyła `INFO`, `RADIO`, `FRAM` i `JOURNAL`. `HELP` (albo pusty wiersz) zwraca listę poleceń tego obrazu.

| Polecenie | Odpowiedź |
|---|---|
| `INFO` | pola jak w specyfikacji radia: `contract`, `profile`, `radio`, `mcu`, `fw`, `src`, `mv` (zero, brak pomiaru), `tx_wait_ms` (pozostały dług ciszy), `rx_ok`, `rx_bad`, `tx_drop` z łącza P1, `restarts` (liczba startów) i `uptime_s` (licznik czasu pracy) z dziennika FRAM, oraz `bench`, `prep`, `silence`, `radio_ok`, `p1_ok`, `fram_ok`, `fram_volatile` (obraz FRAM ginie po odłączeniu zasilania: `true` tylko w `xiao`), `journal_ok`, `journal_resets`, parametry P1, `service_s` (czas dla obsługi = licznik − suma przeskoków restartów), `boot_s`, `screen`, `lang`, `name` (`WICI-xxxxxx`: 6 cyfr skrótu tożsamości Reticulum; bez stosu z identyfikatora układu), `reset_reason` (RESETREAS), `store_ok`, `register`, `inbox`, `head` (ostatnie zdarzenie pierścienia), pola [węzła stanowiska](stos.md#węzeł-stanowiska) (`node`, `usb_open`, `usb_flow`, `usb_buffered`, `usb_pinned`, `usb_rns_in`, `usb_rns_out`, `usb_rx_drop`, `usb_rx_large`, `usb_tx_drop`, `usb_ready`, `usb_cmds`, `computer_s`: sekundy od ostatniego pakietu od komputera, −1 bez pakietu), `usb_data` (port danych otwarty), liczniki wierszy protokołu, `usb_boot`, `wdt_s` (czas watchdoga), `board` (`wires` albo `N1`), `rns_state` (stan stosu: `running`, `not_started`, `unavailable`, `entropy_failed`, `selftest_failed`, `identity_lost`, `start_failed`, `halted`; przyczyna w `LOG`) i `entropy_ok` (odczyt ziarna przeszedł [test zdrowia](stos.md#samotest-rdzenia-na-płytce)) |
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
| `FOFF [<hz>]` | korekta częstotliwości w Hz (do ±50 kHz, krok 30,5 Hz) do restartu, tylko w trybie przygotowania i bez trwającej serii; bez argumentu odczyt |
| `P1RX` | odbiór ramek P1 w tle (zmienna długość, LEN do 102); każda ramka i złożony datagram jako wiersz JSON |
| `P1TX <hex>` | tylko w trybie przygotowania: nadanie datagramu 1–600 B zapisanego szesnastkowo: fragmentacja, losowy identyfikator, dług ciszy, CCA, odroczenia; wynik w wierszu `p1tx` po zakończeniu. Wiersze `p1rx` i `p1tx` wychodzą tylko w całości i tylko wtedy, gdy cały wiersz mieści się w wolnym miejscu bufora portu, więc terminal, który przestał czytać, nie zatrzymuje pętli. Datagram, którego wiersz się nie mieści, dostaje wiersz bez danych z `"data_omitted":true` |
| `P1` | liczniki łącza: ramki, datagramy, odrzuty, odroczenia, stan składania |
| `EMC [<s> <len>\|0]` | tryb pracy do badań EMC ([opis](#tryb-pracy-do-badań-emc)): `EMC <s> <len>` (tryb przygotowania) nadaje ramkę wzorcową `len` B co `s` s i odbiera między ramkami; `EMC 0` kończy; bez argumentu stan: `period_s`, `len`, `min_period_s`, `resumed`, `journal`, `sent`, `failed`, `silenced`, `skipped`, `rx_ok`, `rx_bad`, `missing`, `seconds` |
| `STOP` | przerwanie `TXCW`, `TXPKT`, `P1TX` i odbioru; kończy też tryb EMC |
| `LOG [<n>]` | ostatnie `n` (domyślnie 16, do 64) zdarzeń z dziennika w FRAM, od najnowszego, z numerem i czasem pracy; bez FRAM do 16 ostatnich wpisów z RAM, też od najnowszego |
| `JOURNAL` | stan dziennika: rekord długu (numer, dług, czas zapisu, liczba poprawnych rekordów), licznik czasu pracy (numer, `uptime_s`, `skip_s` = suma przeskoków S, liczba startów), numer ostatniego zdarzenia, największy dług; wejścia w tryb przygotowania: `prep_entries`, `prep_at_s` (licznik czasu przy ostatnim wejściu), `prep_changes` (bit 0: nowa konfiguracja), `prep_config_sha`, `prep_restarted`, `prep_corrupt` |
| `BENCH` | stan trybu przygotowania, ciszy, zadań, długu i trybu EMC (`emc`) |
| `RSSI` | RSSI w dBm z przyjętym przesunięciem −99 dB (`rssi_offset_db`), znaczniki ważności i nośnej; sens tylko w stanie RX |
| `STATE` | stan MARC nazwą i liczbą, bajt stanu, liczba bajtów w kolejkach RX i TX |
| `REG <hex>` | odczyt rejestru z przestrzeni zwykłej (00–2E) albo rozszerzonej (2F00–2FFF), np. `REG 2F73` (MARCSTATE), `REG 2F0C` (FREQ2) |
| `FRAM` | rozpoznany układ (`MB85RS4MT`, `CY15B104Q`, `CY15B104QN`, `emulated-psram` w `xiao` albo `unknown`), `volatile` (`true` tylko w `xiao`, wtedy z `kept` zamiast `spi_hz`, [opis](prototyp-l0-i-xiao.md#zestaw-xiao-xiao)), dziewięć bajtów RDID (MB85RS4MT: `047F4903…`, MB85RS4MTY: `047F490B…`, CY15B104Q: `7F7F7F7F7F7FC22608`, CY15B104QN-50SXI: `7F7F7F7F7F7FC22C00`; wersje 1,8 V CY15V104QN są odrzucane), rejestr stanu, `ok`; `spi_hz` to zegar FRAM (8 MHz na N1, 1 MHz na przewodach) |
| `BTN` | stan czterech przycisków (na N1 także panelu, patrz [N1](stanowiska-a-b.md#płytka-nośna-n1-bench-n1)) |
| `LED <1-4> <0\|1>` | sterowanie diodą |
| `SCREEN` | treść ekranu: nazwa ekranu, język, pięć wierszy i które są odwrócone, liczba odświeżeń |
| `REQ <n> [<bajty>]` | `n` (1–100) zgłoszeń REQUEST tą samą drogą co kreator przycisków (`Station::create`: kodowanie SA1, rejestr, kolejka): kategoria 0, 1 osoba, pilność 0, wybrany adres, tekst „REQ k” albo tekst dokładnie `bajty` (0–96) B; odpowiedź `numbers`, `created`, `sa1_bytes` (SA1 ostatniego) i `error` przy odmowie (np. `full`); do prób W10 i zestawu XIAO bez przycisków |
| `HACK [0]` | potwierdzenia skoku WICI-Link: `hack_sent`, `hack_late` (odmowa z powodu terminu 200 ms), `hack_refused` (stan, zajęty kanał, dług, dziennik), `hack_over_200ms` oraz czas od końca odbioru DATA (znacznik zadania odbioru) do TxDone HACK: `end_ms_last`, `end_ms_max`, `end_ms_mean`; `refused_by` dzieli `hack_refused` według przyczyny: `state` (kształt ramki albo stan zestawu: brak łącza lub dziennika, cisza, przygotowanie, EMC, nadawanie próbne, radio poza odbiorem łącza), `lock` (blokada radia niezdobyta na czas), `rx_pending` (układ odbiera ramkę albo ma nieodczytaną), `prep` (inny błąd przygotowania nadania), `cad` (zajęty kanał), `debt` (limit długu albo nieudany zapis długu w dzienniku), `tx` (nieudane nadanie); na stacji WICI-Link z rodzicem także sprawdzanie podpisów BEACON-ów poza pętlą ([BEACON](../../docs/spec/wici-link.md)): `beacon_checks` (wyniki przyjęte w pętli), `beacon_check_ms_last` i `beacon_check_ms_max` (czas jednego sprawdzenia w zadaniu, ms), `beacon_dropped` (BEACON przy zajętym sprawdzeniu), `beacon_stack_free` (zapas stosu zadania `wici_beacon` na drugim rdzeniu w bajtach, −1 bez zadania) i `proofs_dropped` (dowody doręczenia wyparte z pełnej listy, [dowód doręczenia](../../docs/spec/wici-link.md#dowód-doręczenia)); `HACK 0` zeruje; każdy HACK daje też wiersz `{"hack":"sent","len":29,"end_ms":…}` |
| `KEY <UP\|DOWN\|OK\|BACK> [ms]` | naciśnięcie przycisku z portu USB (próby bez dotykania płytki), z czasem przytrzymania 0–60 000 ms; odpowiedź jak `SCREEN` |
| `DISPLAY` | EXTCOMIN: `extcomin_ok` (licznik ruszył), licznik RTC2 albo MCPWM i stan pinu, tryb VCOM, liczba odświeżeń, numery pinów, zegar SPI ekranu `spi_hz` |
| `VCOM <0\|1>` | odwracanie VCOM bitem w poleceniach ekranu, tylko przy przewodach bez połączenia EMD (`bench-a`); na N1 błąd `VCOM: EXTMODE tied high on N1` |
| `REBOOT` | restart programowy; ekran i język wracają jak po restarcie przez watchdog |
| `STORE` | magazyny FRAM: konfiguracja (`role`, `config_seq`, adres wybranego obiektu, `addresses` i `selected` listy obiektów, aktywna tożsamość odbiorcy `receiver`, frazy, liczba stacji), `identity_saved`, epoka, `head`, `min`, `tomb_floor`, zajęte wpisy rejestru i skrzynki, nieprzeczytane, diagnostyka (`corrupt_slots`, `replayed`, `scrubbed`, `config_corrupt`), liczniki protokołu |
| `USB <wiersz JSON>` | wiersz protokołu danych podany przez port diagnostyki (próby z jednym terminalem); odpowiedź idzie na port danych, a gdy jest zamknięty, na diagnostykę |
| `APP` | warstwa aplikacji: wiadomości w drodze (najwyżej 2), liczniki nadanych, dostarczonych (dowód transportowy), nieudanych, odebranych, odrzuconych, pominiętych, pominiętych BULLETIN, nieprzyjętych z braku miejsca (`inbox_full`), usuniętych nieprzeczytanych BULLETIN (`evicted`), aktywne intencje, niewysłane, gniazdo do nadania |
| `LINK <0\|1>` | zatrzymanie i wznowienie nadawania zgłoszeń przez warstwę aplikacji (próby ręczne `P1TX` przy zatrzymanym); ruch własny stosu (ogłoszenia, dowody, odpowiedzi o trasę) idzie dalej |
| `RNS` | stos Reticulum: adres stacji (`wici.sa1`; na rdzeniu od etapu rdzenia 3 `lxmf.delivery`) i skrót tożsamości, `online` (IFAC skonfigurowany), liczba tras, skrótów pakietów, wpisów tablicy ogłoszeń i potwierdzeń w toku, pula TLSF (`pool`, `pool_used`, `pool_peak`) i system plików FRAM w obrazach z portem, liczniki pakietów, dowodów i ogłoszeń (`announced`), czas do następnego ogłoszenia, przewidywane oczekiwanie w kolejce radiowej (`wait_ms`), przepływność deklarowana (`bitrate`), kolejka interfejsu P1 (`q_len`, `q_held`, `q_full`, `ann_held`, `ann_drop`, `tx_sent`, `tx_failed`, `rx_ok`, `ifac_missing`, `ifac_invalid`, `offline`, `silenced` — pakiety wstrzymane ciszą, `k2_slot`, `k2_pool`, `k2_dest` — odrzucone K2, `pr_limited` — przekazywane zapytania o trasę ponad limit, `pool_ms` i `pr_ms` — czas kanału puli K2 z ogłoszeniami i zapytań o trasę w ostatniej godzinie), `identity_lost`, pola węzła stanowiska jak w `INFO` |
| `RNS SELFTEST` | tylko obrazy z rdzeniem (`bench-a`, `bench-n1`, `bench-b`, `l0`): wszystkie próby [samotestu rdzenia](stos.md#samotest-rdzenia-na-płytce), wiersz `{"selftest":…,"ok":…,"us":…}` na próbę i `{"selftest_ok":…,"entropy_ok":…,"version":…}`; pętla stacji stoi przez kilka sekund |
| `ANNOUNCE` | ogłoszenie adresu na polecenie; wychodzi w najbliższym obiegu poza ciszą radiową i z kodem IFAC, potem `RNS` |

Warunek przejścia kroku 6 z [lekcji R02](../../hardware/r02/lekcje.md#uruchomienie): `RADIO` daje `ready: true`, `partnumber: 0x48` i stan `IDLE`; `FRAM` daje `ok: true`. Bez modułu `partnumber` wynosi `0xFF` albo `0x00`, a `ready` jest `false`. Po starcie obraz sam zapisuje i kalibruje P1; LED2 świeci dopiero, gdy `RADIO` daje `ok: true` i `p1_ok: true`. Po otwarciu portu obraz wysyła też wynik `VERIFY` i `FREQ`.

## Polecenia pomiarowe

Kontrakt jest w [specyfikacji radia](../../docs/spec/radio.md#usb-do-laptopa); kod w `src/measure.cpp`. Polecenia działają tylko w trybie przygotowania (`PREP 1` potwierdzone przyciskiem OK, bo na stacji tryb włącza przycisk pod naklejką serwisową). Każde wejście w ten tryb, także poleceniem, najpierw trafia do pierścienia wejść w FRAM; bez zapisu tryb się nie włącza. W ciszy radiowej (`SILENCE 1`) polecenia są odrzucane, a cisza włączona w trakcie przerywa każdą serię, także przewodową, bo blokuje każde nadawanie. Polecenia wymagają też skonfigurowanego radia (`p1_ok`; inaczej błąd `radio not configured: CONFIG`). Odpowiedzi odmowne mają pole `error`.

Limit nadawania na stanowisku: po każdej serii obowiązuje dług ciszy 12 × czas nadawania (jak w P1), widoczny w `INFO` jako `tx_wait_ms`. Seria bez argumentu `CONDUCTED` nie może przekroczyć 1,4 s czasu nadawania, czyli najdłuższego datagramu P1 (7 ramek po 103 B z narastaniem mocy); na prototypie limit wynosi 838 ms, czyli tyle, ile trwa najdłuższy datagram LoRa ([prototyp](prototyp-l0-i-xiao.md#stacja-l0-l0)). Czas ramki i limit podaje sterownik układu (`radiolink::Driver`). Specyfikacja nie podaje tej liczby wprost; to przyjęta interpretacja. `CONDUCTED` znosi oba ograniczenia, ale wyłącznie do nadawania przewodowego do tłumika lub obciążenia sztucznego. Obraz prosi wtedy o przycisk OK, czeka na niego do 30 s (LED1 miga szybko) i zapisuje potwierdzenie albo jego brak w dzienniku `LOG`. Dług jest zapisywany w [dzienniku FRAM](aplikacja.md#dziennik-i-magazyny-w-fram) przed pierwszą ramką serii; błąd zapisu albo brak FRAM blokuje nadawanie radiowe. Seria `CONDUCTED` (do obciążenia, bez emisji) nie tworzy długu.

- **`TXCW`** przełącza układ na 2-FSK z dewiacją 0, dane z generatora PN9 i pakiet nieskończony, więc wychodzi sama nośna; po czasie albo po `STOP` przywraca rejestry P1. Przerwana wcześniej (`STOP`, cisza) zapisuje dług od nowa z rzeczywistego czasu nadawania. Do pomiaru częstotliwości (potem `FOFF`) i mocy.
- **`TXPKT`** nadaje ramki wzorcowe (`src/testframe.cpp`): numer porządkowy 2 B, wypełnienie PN9 zależne od numeru, na końcu CRC-16 ramki P1; test na komputerze (`tests/test_firmware_host.py`) porównuje CRC i ramkę z modelem. Dla pierwszej ramki obraz mierzy z GPIO2 (PKT_SYNC_RXTX) czas od `STX` do słowa synchronizacji (`lead_ms`: ustalenie syntezera, narastanie, preambuła), czas pakietu w powietrzu (`on_air_ms`, oczekiwane `len` × 8 / 4800) i ogon do IDLE (`tail_ms`); to wejście do parametru `ramp_ms` modelu. Bez przewodu na D3 jest `sync_gpio: false` i odpowiedź podaje tylko `tx_ms` (czas serii ze stanu MARC).
- **`RX <len>`** (tryb przygotowania, bez trwającej serii) ustawia stałą długość pakietu i odbiór ciągły; obraz czyta kolejkę co 5 ms, sprawdza CRC i numer, a `RXPER` zwraca liczniki i je zeruje. `missing` to luki w numeracji, `reordered` numer nie większy od poprzedniego, `overflow` przepełnienia kolejki. `rssi_avg_dbm` używa przyjętego przesunięcia −99 dB.
- **`FOFF`** (tryb przygotowania, bez trwającej serii) przelicza Hz na FREQOFF (równanie 27 instrukcji), zapisuje w IDLE i wraca do odbioru, jeśli trwał; korekta ponad ±50 kHz daje `FOFF outside the subband: max +-50000 Hz`. Kanał LoRa 125 kHz ze środkiem 869,525 MHz wychodzi poza podpasmo 869,4–869,65 MHz już przy 62,5 kHz, a pomyłka o rząd wielkości nie może wyprowadzić nadawania poza podpasmo. Błąd kwarcu modułów (około ±17 kHz) mieści się w tej granicy. Wartość poza zakresem układu daje `FOFF outside the radio range (about +-1 MHz)`. Po `CONFIG` wartość jest zapisywana ponownie, po `RESET` lub restarcie znika.

### Tryb pracy do badań EMC

Badania odporności (EN 301 489-1 i -3) wymagają stacji w pracy z okresowym nadawaniem i odbiorem, a laboratorium ocenia, czy funkcja wraca sama po zakłóceniu (kryterium B). `EMC <s> <len>` działa w trybie przygotowania, przy zapisanym profilu i działającym dzienniku FRAM. Polecenie zapisuje tryb w rekordzie ustawień dziennika i od razu nadaje pierwszą ramkę wzorcową `len` B (jak `TXPKT`, numer od 0), a potem kolejną co `s` s. Między ramkami układ odbiera ramki wzorcowe tej samej długości, np. od drugiej stacji w tym samym trybie albo od `TXPKT` stacji pomocniczej (liczniki jak przy `RX`, odczyt przez `RXPER` albo `EMC`). Po każdej ramce wychodzi wiersz `{"emc":"tx","seq":…,"ok":…,"sent":…,"rx_ok":…,"rx_bad":…,"tx_wait_ms":…}`.

- **Budżet nadawania:** każda ramka zapisuje w dzienniku dług 12 × czas ramki przed nadaniem, jak seria `TXPKT`; okres nie może być krótszy niż 13 × czas ramki (`min_period_s`, w górę do sekundy; na prototypie dla 255 B 6 s), więc dług mija przed następną ramką, a cykl pracy nie przekracza 1/13 (7,7 %, poniżej 10 % w godzinie). Ramka, przed którą dług jeszcze trwa (dług sprzed restartu, ramka dłuższa od rezerwacji), czeka na jego koniec. Ramki idą bez CCA, jak `TXPKT`; tryb służy tylko badaniom w laboratorium. Nie ma wariantu `CONDUCTED`.
- **Cisza radiowa** (CISZA albo `SILENCE 1`) pomija ramki (`silenced`), odbiór trwa; ramka bez zapisanego profilu albo z błędem zapisu długu jest pominięta (`skipped`).
- **Restart:** tryb wraca sam po każdym starcie (`LOG`: „EMC resumed after restart”, `resumed: true`), także bez trybu przygotowania, z numeracją od 0; rekord niepasujący do układu (np. obraz innej stacji na tej samej FRAM) jest kasowany bez nadawania. Wyjście z trybu przygotowania, `CONFIG`, `RESET` i `IDLE` trybu nie kończą: odbiór wraca w ciągu 1 s, a ramki wracają po `CONFIG`.
- **Koniec:** `EMC 0`, `STOP` albo ZNISZCZ DANE kasują rekord. Gdy zapis do dziennika się nie uda, ramki i tak stają, ale rekord zostaje i tryb wróciłby po restarcie: `EMC 0` zwraca wtedy błąd `EMC journal clear failed: mode returns after restart`, a `STOP` pole `emc_error`; następne `EMC 0` próbuje znowu. W trybie EMC `TXCW`, `TXPKT`, `RX`, `FOFF`, `P1RX` i `P1TX` dają `EMC mode on: EMC 0 first`; na stanowiskach A i B odbiór P1 i nadawanie stosu stoją do końca trybu.
- **Alarm:** przez cały tryb, także po restarcie, stacja daje `radio_awaria` (ekran alarmu do OK, wiersz 1 „RADIO: AWARIA”), bo zgłoszenia nie wychodzą; alarm schodzi po `EMC 0`. Stacja, której po badaniach nie wyłączono trybu, nie wygląda na sprawną. LED2 dalej pokazuje zapisany profil.
- Reszta programu (ekran, panel, magazyn, stos) pracuje normalnie; stan trybu podają `EMC` i `BENCH`.

Przebieg pomiaru czułości: na nadajniku `PREP 1`, `TXPKT 2000 103 50 CONDUCTED`; na odbiorniku `PREP 1`, `RX 103`, po serii `RXPER`. PER ≤1% przy 2000 ramek oznacza najwyżej 20 ramek w `rx_bad` plus `missing`.
