# WICI: Prototyp L0, płytka v2 i zestaw XIAO

Część opisu oprogramowania stacji; spis części jest w [README](../README.md).

## Stacja L0 (l0)

Środowisko `l0` buduje program stacji dla prototypu na płytce v1 (dawniej płytka nośna N1): ESP32-S3-DevKitC-1-N8R8 z modułem Seeed Wio-SX1262 (SX1262, TCXO 1,8 V) w miejscu X-NUCLEO-S2868A2. Piny są w `src/board_l0.h` według [`polaczenia-MCU-L0.csv`](../../hardware/l0-diagnostic/reference/polaczenia-MCU-L0.csv), tych samych co w [programie diagnostycznym](../../hardware/l0-diagnostic/README.md). Program, warstwa MCU, ekran, panel płytki v1, dziennik i magazyn są te same co w `bench-b`; obraz pomija sterowniki CC1120 i S2-LP i ma sterownik SX1262 w [profilu LoRa pilotażu](../../docs/spec/radio.md#profil-lora-pilotażu). Obraz się kompiluje (rozmiar w [pomiarze RAM](stos.md#pamięć-ram)). **Nie uruchomiono go na sprzęcie**; kroki niżej są niewykonane.

| Sygnał | GPIO ESP32-S3 | Uwagi |
|---|---|---|
| SPI SCK / MOSI / MISO | 12 / 11 / 13 | jak w `bench-b`; radio 1 MHz, FRAM 8 MHz |
| NSS / NRESET SX1262 | 10 / 9 | NRESET napędzany stanem wysokim po resecie (N1 R12 = 1 kΩ do masy, Wio 10 kΩ do 3,3 V) |
| BUSY / DIO1 | 14 / 21 | wejścia; sterownik czeka na BUSY niski przed każdą transakcją, przerwania czyta przez SPI, DIO1 tylko w `RADIO` |
| RXEN | 42 | stan wysoki tylko w odbiorze, niski w nadawaniu i spoczynku; nadawanie przełącza DIO2 układu |
| FRAM, ekran, panel, VTEST | jak w `bench-b` | |

Sterownik (`src/sx1262.cpp`: polecenia, rejestry, bufor, BUSY; `src/sx1262_link.cpp`: profil i `radiolink::Driver`; `src/lora_profile.h`: parametry i czas ramki) jest własny, jak dla CC1120 i S2-LP. Sekwencję startu przeniesiono z programu diagnostycznego (RadioLib 7.6.0, `SX1262::begin`, `setRfSwitchPins(RXEN)`, `setDio2AsRfSwitch`, `setRxBoostedGainMode`). Sam obraz nie łączy RadioLib, dzięki czemu test na komputerze sprawdza ten sam kod z modelem układu, bez PlatformIO:

- **Start:**
  - NRESET niski na 1 ms,
  - tekst wersji z rejestru 0x0320 (`ok`, gdy zaczyna się od „SX126”; SX1262 podaje „SX1261 V2D 2D02”),
  - STDBY_RC, TCXO 1,8 V z DIO3 (start 5 ms), skasowanie błędów,
  - kalibracja wszystkich bloków (kalibracja po włączeniu zasilania bez TCXO kończy się błędem XOSC_START),
  - przetwornica DC-DC, DIO2 jako przełącznik RF, typ pakietu LoRa, tryb powrotu STDBY_XOSC (TCXO pracuje między ramkami),
  - kalibracja obrazu 863–870 MHz, częstotliwość,
  - PA jak w programie diagnostycznym (RadioLib, tabela dla 13 dBm: 0x01, 0x04, SX1262, wartość 19 w SetTxParams) z rampą 200 µs,
  - limit prądu 60 mA (zapis po SetPaConfig, który ustawia 140 mA),
  - modulacja SF7, 125 kHz, CR 4/5, bez LDRO, pakiet z jawnym nagłówkiem i CRC,
  - poprawki z rozdziału 15 karty (0x0889, 0x08D8, 0x0736), słowo synchronizacji,
  - Rx Boosted (0x08AC = 0x96) dopisany do listy rejestrów zachowywanych w uśpieniu (0x029F = 1, 0x02A0..0x02A1 = 0x08AC),
  - na końcu weryfikacja odczytem: typ pakietu, 10 rejestrów i brak błędów układu.
- **Stałe z RNode:** preambuła 24 symbole (reguła RNode max(18, ceil(24 ms / czas symbolu)), `Config.h`/`Utilities.h` w commicie 56775c51) i słowo synchronizacji 0x12 (rejestry 0x0740 = 0x14 i 0x0741 = 0x24 jak w RNode, `sx126x.cpp`) są stałymi w `src/lora_profile.h`. Obie wartości pochodzą ze źródła RNode; radiem potwierdza je [krok 4](#krok-4-interfejs-lora-z-radiem-rnode). Program diagnostyczny nadaje z preambułą 8 symboli i mocą 0 dBm.
- **Nadawanie:** ramka z bufora od adresu 0, długość w parametrach pakietu, RXEN niski, `SetTx` bez limitu czasu układu; koniec po TxDone (układ wraca sam do STDBY_XOSC), bez niego po czasie ramki + 100 ms przejście do STDBY_XOSC i błąd.
- **Odbiór** ciągły (`SetRx 0xFFFFFF`) z RXEN wysokim: ramka po RxDone, długość i początek z `GetRxBufferStatus`, RSSI pakietu (−RssiPkt/2) i SNR (SnrPkt/4) z `GetPacketStatus`; błąd CRC lub nagłówka albo inna długość niż w `RX <len>` dają `rx_bad`, a układ zostaje w odbiorze.
- **TXCW:** `SetTxContinuousWave`; **FOFF:** słowo RF ± kroki 32 MHz / 2²⁵ (0,954 Hz), do ±50 kHz (granica podpasma), zapis w STDBY_XOSC i powrót do odbioru.
- **Czas ramki** z wzoru karty (rozdz. 6.1.4; ten sam co `lora_frame_seconds` w `software/reference/obliczenia.py`) plus 3 ms na narastanie (założenie jak w P1, do pomiaru): 255 B w SF7 to 416,0 ms w powietrzu i 419 ms rezerwacji.

Polecenia pomiarowe działają jak na A i B (ten sam `src/measure.cpp`, [opis](polecenia.md#polecenia-pomiarowe)), z czasem ramki, najdłuższą ramką i limitem serii z profilu LoRa:

- `TXPKT <n> <len>` i `RX [<len>]` przyjmują ramki wzorcowe 4–255 B; dług 12 × `n` × czas ramki trafia do dziennika FRAM przed pierwszą ramką, a seria bez `CONDUCTED` nie może przekroczyć 838 ms, czyli najdłuższego datagramu LoRa (dwie ramki 255 B z narastaniem). Przykład: `TXPKT 2 255` planuje 838 ms i zapisuje 10056 ms długu; `TXPKT 3 255` wymaga `CONDUCTED`. `expected_on_air_ms` to cała ramka LoRa od preambuły; `sync_gpio` jest `false` (bez wyjścia „pakiet w powietrzu”).
- `TXCW` trwa co najmniej 1 s, więc w profilu LoRa wymaga zawsze `CONDUCTED` (pomiar mocy i częstotliwości przewodowo do tłumika).
- `RXPER` podaje dodatkowo wiersz `{"snr_avg_db":…,"rx_ok":…}`; `lqi_avg` wynosi 0.
- Łącza P1 nie ma: `P1RX` i `P1TX` zwracają `no P1 link on this radio`. Łącze stosu idzie w ramkach RNode (`src/measure.cpp`, [profil LoRa](../../docs/spec/radio.md#profil-lora-pilotażu)): odbiór wraca sam poza trybem przygotowania i po rekonfiguracji układu, a nadanie idzie kolejno przez dług z dziennika, 50 ms bez aktywności, CAD, zapis długu 12 × czas ramek i dwie ramki. Opis i liczniki: [interfejs LoRa stosu](#interfejs-lora-stosu).
- Tryb pracy do badań EMC ([opis](polecenia.md#tryb-pracy-do-badań-emc)): na przykład `EMC 10 255` nadaje ramkę 255 B (419 ms rezerwacji, 5028 ms długu) co 10 s i odbiera ramki 255 B między nimi; najkrótszy okres dla 255 B to 6 s, dla 20 B 1 s.
- `INFO` podaje `profile: "LoRa"`, `radio: "SX1262"`, `bench: "L0"` i pola profilu `carrier_hz`, `bw_hz`, `sf`, `cr`, `preamble`, `sync_word` zamiast `symbol_rate`, `deviation_hz`, `rx_filter_hz`; `p1_ok` oznacza tu zapisany i zweryfikowany profil LoRa. Konfiguracja stacji (`configure`) wymaga `radio.profile` = `lora-sf7`.

| Polecenie | Odpowiedź na L0 |
|---|---|
| `RADIO` | `version` (tekst z 0x0320), `status` i `state` z bajtu statusu (`STBY_RC`, `STBY_XOSC`, `FS`, `RX`, `TX`, `UNKNOWN`), `device_errors`, `busy`, `dio1`, `rxen`, `irq_seen`, `busy_timeouts`, `p1_ok`, `ok` |
| `RESET` | NRESET na 1 ms; rejestry wracają do wartości po resecie (0x08AC = 0x94), `p1_ok: false` |
| `CONFIG` / `VERIFY` | reset i zapis profilu LoRa z weryfikacją / sama weryfikacja (`first`, `reg`, `expected`, `actual` przy różnicy) |
| `FREQ` | słowo RF, częstotliwość, błąd wobec 869 525 000 Hz, krok, `rf_offset` (kroki `FOFF`) |
| `STATE`, `IDLE`, `RSSI` | tryb układu, RXEN i BUSY; `IDLE` przechodzi do STDBY_RC; `RSSI` z `GetRssiInst` (tylko w RX) |
| `REG <hex>` / `REGW <hex> <hex>` | odczyt / zapis rejestru 0000–FFFF; zapis tylko w trybie przygotowania, `CONFIG` go cofa (np. próba słowa synchronizacji 0x0740/0x0741 wobec RNode) |
| `SLEEP` | uśpienie z ciepłym startem i wybudzenie przez NSS; `rx_gain` i `boosted` pokazują, czy Rx Boosted przetrwał (lista rejestrów zachowywanych) |

Test `tests/test_radio_link_host.py` (`Sx1262LinkTests`) sprawdza sterownik z modelem układu na poziomie poleceń: bajt statusu, BUSY, rejestry, bufor, przerwania kasowane poleceniem, tryb powrotu po TxDone, odbiór ciągły i uśpienie z listą zachowywanych rejestrów (bez wpisu 0x08AC wraca do 0x94). Sprawdza też `measure::Bench` nad nim: kolejność startu, parametry profilu, Rx Boosted po uśpieniu, CW, nadanie i brak TxDone, odbiór z RSSI i SNR, błędy CRC i nagłówka, FOFF, BUSY bez zejścia, odmowę P1, limit serii 838 ms, dług w dzienniku i jego skasowanie, ciszę, `RXPER` z SNR i tryb EMC. W trybie EMC sprawdza okres (najmniej 13 × czas ramki), dług przed każdą ramką, odbiór między ramkami, ciszę, wznowienie z dziennika po restarcie bez trybu przygotowania i koniec z kasowaniem rekordu. Model nie zastępuje karty: zachowanie układu w rzeczywistości sprawdzają kroki niżej.

Budowa i wgranie (port USB-OTG DevKitC, jak `bench-b`):

```bash
cd firmware && ../.venv-pio/bin/pio run -e l0
```

```bash
cd firmware && ../.venv-pio/bin/pio run -e l0 -t upload
```

Próba zmontowanego prototypu (**niewykonana**; raport z próby w Issue z etykietą `próba`):

1. `INFO` (`radio_ok`, `p1_ok`, `fram_ok`, `journal_ok` = `true`, `profile: "LoRa"`), `RADIO` (`version` „SX1261 V2D 2D02”, `device_errors` 0x0000, `busy: false`, `busy_timeouts: 0`, `rxen: false` w spoczynku), `VERIFY` (`mismatches: 0`), `FREQ`, `SLEEP` (`boosted: true`), `RESET` i `CONFIG`. Odpowiedzi programu diagnostycznego (`hardware/l0-diagnostic`) są punktem odniesienia dla SPI, FRAM, ekranu i panelu.
2. Obraz stacji na dwóch prototypach (drugi egzemplarz po udanym uruchomieniu pierwszego): `PREP 1`, na odbiorniku `RX 20`, na nadajniku serie `TXPKT 11 20` (836 ms) do 100 ramek, z odczekaniem długu (`INFO` `tx_wait_ms`) między seriami, albo jedną serią `TXPKT 100 20 50 CONDUCTED` przez tłumik; `RXPER` z `rssi_avg_dbm` i `snr_avg_db`; potem w drugą stronę. Odbiór ramek programu diagnostycznego przez obraz stacji nie jest próbą z punktu 2 (inna preambuła i treść ramek).
3. Cisza: przełącznik CISZA (SW5) albo `SILENCE 1`: `TXPKT` i `TXCW` dają `radio silence`, cisza włączona w trakcie serii ją przerywa (`LOG`: „silence during TXPKT”); partner nie odbiera ramek; po wyłączeniu nadawanie wraca.
4. Moc i częstotliwość na złączu modułu przewodowo do tłumika: `TXCW 2 CONDUCTED` z miernikiem mocy i częstotliwości (cel 13 dBm, 869,525 MHz), potem `FOFF` i ponowny pomiar; od wyniku zależy wybór ustawień PA (RadioLib albo tabela 13-21 karty).
5. Cykl pracy ≤10% w oknie godzinnym (wiersz „Limit czasu nadawania” w [odbiorze](../../docs/spec/odbior.md#próby)): seria `TXPKT 2 255` powtarzana zaraz po zejściu długu przez godzinę, z pomiarem czasu nadawania w eterze (analizator widma albo odbiornik SDR) wobec rezerwacji 419 ms na ramkę; także restart w trakcie długu (dług odczekany po starcie) i odczekanie `MAX_DEBT_MS` bez poprawnego rekordu.
6. Czasy: rzeczywisty czas ramki i narastania (pole `tx_ms` wobec `expected_on_air_ms`), start TCXO, prąd odbioru w trybie Rx Boosted.
7. Brak emisji 2,4 GHz w wybranym sposobie wyłączenia Wi-Fi i Bluetooth (D14; obraz nie uruchamia Wi-Fi ani Bluetooth, ale wybór sposobu wyłączenia jest warunkiem wstępnym etapu).
8. Tryb EMC przed badaniami: `EMC 10 255` na dwóch prototypach przez godzinę (`sent`, `rx_ok`, `missing` po obu stronach, cykl pracy w eterze), restart zasilania i przyciskiem RESET w trakcie (`resumed: true`, pierwsza ramka po odczekaniu długu), CISZA w trakcie (`silenced`), „RADIO: AWARIA” na ekranie przez cały tryb, `EMC 0` (alarm schodzi).

### Interfejs LoRa stosu

Obrazy `l0` (rdzeń, wersja `l0-0.6`) i `l0-port` (port, `l0-0.7`) mają pod stosem łącze LoRa w ramkach RNode ([ramka w eterze](../../docs/spec/radio.md#profil-lora-pilotażu)); ten sam kod łącza i ramkowania ma program `host` z `--link lora` ([próba zgodności](stos.md#próba-zgodności-z-reticulum)).

- **Ramki** (`src/loraframe.h/.cpp`): datagram to pakiet Reticulum z IFAC 16 B, 1–508 B. Do 254 B idzie w jednej ramce, dłuższy w dwóch: nagłówek 1 B i bajty 0–253, potem ten sam nagłówek i reszta. Starsza połówka nagłówka pochodzi z generatora stacji, a w datagramie dzielonym jest inna niż w poprzednim dzielonym. Pakiet ponad 492 B (508 B z IFAC) odpada przed nadaniem i liczy się w `too_large` (`RNS`). Składanie idzie według reguł RNode z trzema zaostrzeniami: ramka z samym nagłówkiem (trzecia ramka RNode przy 508 B) jest pomijana (`header_only`), pierwsza część przepada po 1 s od odbioru jej ramki (`assembly_timeout`), a inna połówka albo ramka bez podziału kasuje oczekującą część (`split_lost`).
- **Czas łącza** (`p1iface::loraTiming`): czas datagramu z czasu jego ramek (508 B: 838 ms z narastaniem 3 ms na ramkę), dług ciszy 12 × ten czas (508 B: 10 056 ms; tyle stacja odczekuje po starcie bez poprawnego rekordu długu), przepływność deklarowana stosowi 4846 b/s (ogłoszenie stacji z IFAC, 221 B).
- **Nadanie** (`measure::Bench::sendLora`): dług z dziennika, potem okno 50 ms bez aktywności kanału ze znaczników odbioru (preambuła, nagłówek, ramka, RSSI ponad progiem) i RSSI w chwili decyzji; próg to tło szumu z próbek odbioru + 10 dB w granicach −100…−60 dBm (`src/cca_floor.h`, `cca_threshold_dbm` w `P1`), ramka 1 do bufora układu (nieodczytana albo odbierana ramka odracza nadanie), CAD (wykryta preambuła odracza bez zapisu długu), zapis długu 12 × czas ramek w dzienniku FRAM, ramka 1 i od razu ramka 2, jak w RNode bez sprawdzania kanału między nimi, powrót do odbioru. Odroczenie trwa losowo 100–1000 ms, po 30 odroczeniach datagram odpada (`tx_drop`). Od decyzji do powrotu do odbioru pętla trzyma blokadę radia (do około 0,9 s).
- **Zadanie odbioru** (`platform_esp32.cpp`, `sx1262::LinkDriver::taskCycle`): ESP32-S3, rdzeń 0, priorytet tuż pod zadaniem TinyUSB, obieg co takt FreeRTOS (1 ms), stos 4 KiB w pamięci statycznej. Obsługuje układ zawsze, gdy sterownik jest w odbiorze (stos i polecenia pomiarowe `RX` i `EMC`). Przy wysokim DIO1 (RxDone, CrcErr, HeaderErr; w MCU podciągnięcie w dół) albo co 5 ms próbuje wziąć blokadę radia bez czekania; zajęta oznacza pominięty obieg. Pod blokadą czyta przerwania, odświeża znaczniki aktywności, co 5 ms bierze próbkę RSSI i przenosi ramkę z czasem odbioru do pierścienia 8 ramek (`src/spsc_ring.h`, jeden producent i jeden konsument). Pełny pierścień gubi najnowszą ramkę (`rx_ring_overflow`). Pętla czyta ramki z pierścienia (`pollRx`). Przekroczenie czasu BUSY przerywa obieg bez zapisu, a następna próba jest po 100 ms.
- **Spóźniona ramka** (`rx_late`): układ w odbiorze ciągłym pisze kolejną ramkę w buforze za poprzednią, więc druga ramka 255 B nadpisuje pierwszą. Ramka, przy której jest już HeaderValid następnej ramki, jest odrzucana i liczona w `rx_late` oraz `rx_bad`.
- **Blokada radia** (`platform::RadioLock`, `src/radio_lock.h`): rekurencyjny mutex FreeRTOS z dziedziczeniem priorytetu; zawsze najpierw blokada radia, potem magistrala SPI. `Bench` dostaje sterownik przez `radiolink::LockedDriver`, więc każda jego operacja na układzie idzie pod blokadą; pętla czeka na nią najwyżej 500 ms. Przekroczenie (`lock_timeouts`) daje `radio_awaria` do następnej kontroli radia, a polecenie układu dostaje `radio lock timeout`. `WICI_RADIO_LOCK_CHECK` sprawdza blokadę przed każdą transakcją z SX1262 (`lock_misses`, oczekiwane 0). Ekran idzie w kawałkach po 9 wierszy pikseli, jeden na obieg pętli.
- **Nadzór i alarm** (`src/rx_watch.h`, `radiocon::check`): odbiór stosu jest uzbrojony (`rx_armed`), gdy stos działa, a łącze jest w odbiorze poza trybem przygotowania i EMC. Polecenia `IDLE`, `RESET`, `REGW`, `TXCW`, `TXPKT`, `RX` i `EMC` rozbrajają go bez alarmu. `radio_awaria` pojawia się, gdy radio nie służy stacji, gdy przy uzbrojonym odbiorze licznik obiegów zadania stoi 10 s (także w czasie nadawania) albo czas ostatniej udanej obsługi układu stoi 10 s poza nadawaniem (`rx_stalled`), albo gdy pętla nie dostała blokady. Kontrola co 10 s (pod blokadą) przywraca profil utracony przez reset układu i od razu uzbraja odbiór. Układ poza RX przy uzbrojonym odbiorze wraca do odbioru (`rx_mode_lost`). Alarm schodzi sam, gdy zadanie znów obsługuje układ.
- **Gotowość:** odbiór stosu startuje przed ekranem; `rx_ready_ms` to czas od startu do uzbrojenia (kryterium ≤60 s).

Liczniki:

- `INFO`: `link` (`"lora"`), `rx_task`, `rx_armed`, `rx_ready_ms`, `loop_max_ms` (najdłuższy obieg pętli od startu), `rx_task_loops`, `rx_service_max_ms` (najdłuższa obsługa układu przez zadanie), `rx_stalled`, `rx_mode_lost`, `lock_timeouts`, `lock_misses`;
- `P1`: `{"lora":…}` z `rx_ok`, `rx_bad`, `rx_datagrams`, `tx_datagrams`, `tx_fragments` (ramki), `tx_drop`, `deferrals`, `long_deferrals`, powodami odroczeń (`cad_busy`, `rssi_busy`, `rx_busy`; `rx_busy` liczy też czekanie na HACK po usłyszanej DATA z ACKREQ, [WICI-Link](../../docs/spec/wici-link.md#potwierdzenie-na-każdym-skoku)), wykryciami CAD bez potwierdzenia drugim CAD (`cad_unconfirmed`, także przed HACK), datagramami nadanymi mimo obcej energii ponad progiem RSSI (`rssi_ignored`, [radio](../../docs/spec/radio.md#dostęp-do-kanału)), składaniem (`split_lost`, `header_only`, `assembly_timeout`), `rx_late`, `rx_ring_overflow`, `cca_threshold_dbm`, `tx_wait_ms`;
- `RNS`: `link`, `too_large`, `bitrate`, `rx_stack_free` (zapas stosu zadania odbioru w bajtach), `heap_size`, `heap_free` i `heap_min` (sterta ESP-IDF: cała, wolna i najmniejsza wolna od startu; −1 na nRF52840). Pola `pool*` (pula TLSF) wypełniają tylko obrazy z portem; na ESP32 są zerowe w `l0` i `l0-port`;
- wiersze `lorarx` (złożony datagram: `len`, `frames`, `rssi_dbm`, dane) i `loratx` (wynik, `len`, `frames`, `deferrals`, `wait_ms`, `tx_wait_ms`);
- program `host --link lora` podaje w stanie `lora_split_lost`, `lora_header_only`, `lora_assembly_timeout` i `lora_bad_length` (ramka ponad 255 B, możliwa tylko w emulatorze; obraz na układzie tego licznika nie podaje).

Testy na komputerze: `tests/test_loraframe.py` (ramki bajt po bajcie wobec wzorca z firmware RNode, składanie, czasy), `tests/test_radio_link_host.py` (`Sx1262LinkTests`, `LoraBenchTests`, `RxRingTests`, `DisplayChunkTests`: CAD, przygotowanie nadania, spóźniona ramka, pierścień, nadzór, ekran w kawałkach), `tests/test_rns_units.py` (czas łącza), próby wrogie na łączu LoRa (`LoraHostileStackTests`, `CoreLoraHostileStackTests`) i [próba zgodności](stos.md#próba-zgodności-z-reticulum) z `RNodeInterface`.

### Krok 4: interfejs LoRa z radiem RNode

Procedura (**niewykonana**; raport w Issue z etykietą `próba`). Sprzęt: prototyp z `l0` (potem z `l0-port`), RAK4631 z oficjalnym firmware RNode ([hardware/rnode](../../hardware/rnode/README.md)), dwa komputery z Reticulum w Pythonie `e40191b`, drugi prototyp do CAD. Najpierw punkty 1–3 [próby prototypu](#stacja-l0-l0). Po stronie RNode interfejs jak w `tools/rns_interop.py` i `tools/rnode_trial.py` (oba biorą go z `rnode_framing.rnode_interface`):

```ini
  [[LoRa RNode]]
    type = RNodeInterface
    port = /dev/…
    frequency = 869525000
    bandwidth = 125000
    txpower = 13
    spreadingfactor = 7
    codingrate = 5
    passphrase = <klucz sieci stacji, 32 cyfry szesnastkowe>
    ifac_size = 128
```

`ifac_size` podaje się w bitach; 128 daje IFAC 16 B jak w stacji (domyślne 8 B stacja odrzuci jako `ifac_invalid`).

1. **Wymiana:** ogłoszenia i pakiety z dowodem w obie strony (stacja w zwykłej konfiguracji, `RNS`: przyrost `paths`, `rx_ok`, `ifac_invalid` 0).
2. **100 datagramów 508 B w każdą stronę przy obciążeniu kryptografią.** Z RNode do stacji: 100 ogłoszeń nowych celów z danymi aplikacji 325 B (pakiet 492 B, jak krok B `rns_interop.py`); każde stacja weryfikuje podpisem Ed25519. Ze stacji do RNode: stacja jako węzeł stanowiska, a komputer za USB ogłasza cele z danymi 309 B. Stacja retransmituje je z identyfikatorem transportu (16 B), więc w eterze idzie 492 B z IFAC 16 B; wiersze `loratx` z `"len":508,"frames":2`. Tempo wyznacza limit ogłoszeń stacji (`ann_held`), więc ta strona trwa dłużej. Ogłoszenia wysyła i liczy `tools/rnode_trial.py` (Python z Reticulum `e40191b` i pyserial, jak `rns_interop.py`); każde ogłoszenie niesie znacznik, identyfikator przebiegu i numer, a wynik idzie do pliku JSON (`--out`) do raportu. Laptop A ma RAK4631 z RNode, laptop B stację (pierwszy port USB to konsola diagnostyczna, drugi port danych węzła stanowiska); klucz sieci stacji w pliku `klucz.txt` (32 cyfry szesnastkowe):

   ```bash
   # Z RNode do stacji. B: liczniki przed
   .venv-rns/bin/python firmware/tools/rnode_trial.py station-counters --station-diag /dev/cu.usbmodem1101 --out przed.json
   # A: 100 ogłoszeń co 3 s (około 5 min)
   .venv-rns/bin/python firmware/tools/rnode_trial.py rnode-announce --port /dev/cu.usbmodem2101 --key-file klucz.txt --out rnode-announce.json
   # B: liczniki po i kryteria z przyrostów
   .venv-rns/bin/python firmware/tools/rnode_trial.py station-counters --station-diag /dev/cu.usbmodem1101 --before przed.json --direction rnode --out po.json
   # Ze stacji do RNode (stacja jako węzeł stanowiska). A: nasłuch do 100 ogłoszeń
   .venv-rns/bin/python firmware/tools/rnode_trial.py rnode-listen --port /dev/cu.usbmodem2101 --key-file klucz.txt --out rnode-listen.json
   # B: 100 ogłoszeń przez USB co 90 s (około 2,5 h), liczniki i wiersze loratx z konsoli przez całą próbę
   .venv-rns/bin/python firmware/tools/rnode_trial.py usb-announce --port /dev/cu.usbmodem1103 --station-diag /dev/cu.usbmodem1101 --out usb-announce.json
   ```

   Gdy RNode i stacja są przy jednym laptopie, `rnode-announce` też przyjmuje `--station-diag` i zapisuje liczniki sam. Odstępy domyślne wynikają ze stacji: z RNode żeton weryfikacji ogłoszenia co 1 s (`ann_limited`), przez USB limit ogłoszeń 2% (około 42 s na 508 B) razy dwa nadania każdego ogłoszenia (ponowienie, bo słuchacz bez transportu go nie powtarza). Na komputerze narzędzie przechodzi próbę z emulatorem RNode i programem `host` (`RnodeTrialToolTests` w `tests/test_rns_stack_lora.py`, po 3 ogłoszenia w każdą stronę); to sprawdza narzędzie, nie radio. Zapisać przed i po (`P1`, `INFO`, `RNS`; narzędzie robi to samo i oznacza każde kryterium jako spełnione, niespełnione albo brakujące):
   - po stronie stacji: przyrost `rx_datagrams` (≥99 ze 100), przyrost `header_only` (trzecia ramka RNode, jedna na datagram), `rx_late` = 0, `rx_ring_overflow`, `assembly_timeout`, `split_lost`, `loop_max_ms`, `rx_service_max_ms`, `rx_stack_free`;
   - po stronie Pythona: liczba przyjętych ogłoszeń ze stacji (≥99 ze 100);
   - odstęp między nadaniami stacji wobec długu (`tx_wait_ms` w `loratx`, około 10 s po 508 B).
3. **CAD z sąsiednią stacją:** drugi prototyp w trybie przygotowania nadaje serie `TXPKT 2 255` (po każdej czeka na dług), a pierwsza ma w tym czasie datagramy w kolejce. Oczekiwane: przyrost `cad_busy`, `rx_busy` albo `rssi_busy` i `deferrals`, `deferrals` > 0 w wierszach `loratx`, brak nakładania się nadań (odbiornik SDR albo `RXPER` trzeciej stacji). Potem to samo z tłumikiem albo odległością, przy której RSSI sąsiada jest poniżej progu CCA (−100 dBm): wtedy odroczenia daje sam CAD i odbiór ramki w toku, więc `cad_busy` i `rx_busy` muszą rosnąć, a nadania nadal się nie nakładają.
4. **Gotowość i nadzór:** `rx_ready_ms` ≤60 s po starcie; przez cały krok `rx_stalled` false, `lock_timeouts` 0, `lock_misses` 0, `rx_mode_lost` 0.
5. **Port:** punkty 1–2 na `l0-port`.

### Próby rdzenia na prototypie

Próby 1–8 z [przejścia na rdzeń](stos.md#przejście-na-rdzeń-i-powrót-do-portu) dla pilotażu idą na prototypie z łączem LoRa:

1. Samotest rdzenia na `l0` (`board_selftest.py -e l0`).
2. RAM w czasie pracy przy pełnej tablicy tras (256 celów) i liście 4096 skrótów pakietów, w `l0` i `l0-port`: stacja jako węzeł stanowiska, ogłoszenia i pakiety z Reticulum w Pythonie przez USB (bez długu ciszy radia). `RNS` podaje `paths`, `hashes`, `rx_stack_free` oraz stertę ESP-IDF: `heap_size`, `heap_free` i `heap_min` (pola `pool*` są zerowe w obu obrazach: rdzeń ich nie wypełnia, a port na ESP32 bierze pamięć ze sterty bez puli TLSF); RAM statyczną daje kompilacja. Próg: `heap_min` ≥30% `heap_size`.
3. Dwa prototypy przez LoRa: ogłoszenia, pakiet, dowód, zgłoszenie z RECEIVED, dług ciszy z dziennika między pakietami.
4. Prototyp jako węzeł stanowiska z Reticulum i LXMF w Pythonie na komputerze (`bitrate = 41`): SA1 w obie strony, kontrola przepływu KISS, odłączenie i ponowne podłączenie USB.
5. Przejście i powrót między `l0` a `l0-port`: stacja po pracy na porcie z wypełnioną tablicą, potem `l0`: ta sama nazwa i tożsamość, `table_corrupt`, pierwsze zgłoszenie dostarczone; potem `l0-port` i znów `l0`.
6. Zanik zasilania i restart przez watchdog w trakcie zapisu tablicy: stacja startuje, wpis odbiorcy zostaje.
7. Przekaźnik A–B–stanowisko przez LoRa (trzy prototypy, B jako przekaźnik) przez 24 h z okresowymi zgłoszeniami: bez restartów, RAM i liczniki stabilne (`RNS`, `INFO`: `loop_max_ms`, `rx_late`, `rx_ring_overflow`, `lock_timeouts`).
8. Rola węzła stanowiska na ESP32-S3 z SX1262 (start stosu, interfejs USB i LoRa).

## Prototyp płytki v2 (v2)

Środowisko `v2` buduje ten sam program stacji co `l0` dla prototypu na [płytce v2](../../hardware/plytka-v2/README.md): ten sam DevKitC, Wio-SX1262, FRAM, ekran i panel, do tego tor zasilania z ogniw AA i z 12 V, wyłącznik i wykrywanie laptopa. Plik opisu płytki to `src/board_v2.h`. Piny pochodzą z tabeli „Sygnały MCU” w [polaczenia.md](../../hardware/plytka-v2/polaczenia.md), a test `tests/test_board_netlist.py` sprawdza każdy z nich z listą połączeń `hardware/plytka-v2/checks/netlist.xml`. Radio, FRAM, ekran i panel mają te same piny co w `l0`.

| Sygnał | GPIO ESP32-S3 | Co robi program |
|---|---|---|
| pomiar 12 V (V_12_ADC) | 5 (ADC1_CH4) | polecenie `VTEST`: `vtest_mv` to napięcie 12 V, `divider` wynosi 16 |
| pomiar ogniw (V_AA_ADC) i klucz dzielnika (DIV_EN) | 4 (ADC1_CH3) i 46 | jeszcze nic; DIV_EN niesterowany (R43 do masy), w uśpieniu zatrzaśnięty |
| PWM przetwornicy (PWM_SYNC) | 45 | jeszcze nic; niesterowany (R63 do masy: Burst Mode), w uśpieniu zatrzaśnięty |
| INT wyłącznika (PWR_INT) | 48 | budzi z uśpienia (`NAP` i [pętla czuwania](#pętla-czuwania-v2)); wyłączenia z programu jeszcze nie ma |
| wyłączenie stacji (KILL_MCU) | 47 | jeszcze nic; pin nie jest sterowany, R72 trzyma go w stanie niskim (stacja zostaje włączona), a w uśpieniu jest zatrzaśnięty |
| laptop podłączony (USB_LAPTOP) | 3 | budzi z uśpienia; w [pętli czuwania](#pętla-czuwania-v2) zasada 10 s i odłączanie od magistrali USB |

**Przelicznik 12 V.** Pomiar korzysta z dzielnika UV sterownika U5: R37 221 kΩ, R38 10,0 kΩ i R39 15,4 kΩ, wszystkie 0,1%. Napięcie na pinie to 12 V × 15,4 / 246,4, czyli dokładnie 1/16 (na L0 dzielnik VTEST dawał 1/6). R76 10 kΩ i C33 100 nF to filtr przed pinem, a nie część dzielnika. Napięcie jest tylko przy włączonej stacji, bo dzielnik podłącza Q4 z szyny ON. 36 V daje 2,25 V, czyli mieści się w zakresie tłumienia 11 dB.

Czego nie da się sprawdzić bez płytki v2: odczytu `VTEST` wobec woltomierza (upływ BAV199 i pinu EN/UVLO zmienia go do około 0,06 V, [README płytki](../../hardware/plytka-v2/README.md)), poziomu INT przy krótkim i długim naciśnięciu wyłącznika i poziomu USB_LAPTOP z laptopem i ładowarką.

## Lekkie uśpienie (NAP)

Stacja pilotażowa śpi między zdarzeniami w lekkim uśpieniu ESP32-S3 ([czuwanie](../../docs/spec/oprogramowanie.md#czuwanie)). Wspólna dla `l0` i `v2` część to `platform::sleep(maxMs)` w `src/platform_esp32.cpp`; woła ją polecenie `NAP` (oba obrazy) i [pętla czuwania](#pętla-czuwania-v2) (tylko `v2`). Funkcja usypia MCU do terminu albo do zdarzenia i zwraca przyczynę wybudzenia. Listy pinów są w pliku opisu płytki (`board::SLEEP_HOLD`, `board::SLEEP_WAKE`), a logika poziomów budzenia w `src/mcu_sleep.h`.

- **Wyjścia trzymane w uśpieniu.** W lekkim uśpieniu domena cyfrowa ma zasilanie, więc przy obecnych ustawieniach Arduino-ESP32 piny i tak zostają w swoim stanie (`CONFIG_PM_SLP_DISABLE_GPIO` jest wyłączone). Program nie polega jednak na tym ustawieniu. Przed uśpieniem woła `gpio_sleep_sel_dis` (pin zostaje przy zwykłej konfiguracji) i `gpio_hold_en` (stan zatrzaśnięty) dla każdego wyjścia z listy. Po wybudzeniu zwalnia je przez `gpio_hold_dis`. Bez tego rezystory płytki ściągnęłyby NRESET radia do masy (R12 1 kΩ: reset radia), RXEN do masy (koniec odbioru) i DISP do masy (wygaszony ekran). Lista: CS radia, NRESET, RXEN, CS FRAM, CS ekranu, EXTCOMIN, DISP, dioda alarmu i brzęczyk, a na `v2` także DIV_EN, PWM_SYNC i KILL_MCU.
- **Brzęczyk.** LEDC w uśpieniu stoi, więc przebieg z `tone()` mógłby zatrzymać się w stanie wysokim i brzęczyk pobierałby prąd. Przed uśpieniem program woła `noTone()` i czeka najwyżej 50 ms, aż zadanie `tone()` odłączy LEDC od pinu; potem ustawia pin w stan niski i trzyma go tak razem z innymi wyjściami. W czasie trwającego dźwięku nie zasypia (`busy`).
- **Budzenie.** Lekkie uśpienie budzi poziomem, nie zboczem. Wyłącznik trzyma INT w stanie niskim, dopóki jest wciśnięty (do 5–19 s przy wymuszonym wyłączeniu), a laptop trzyma USB_LAPTOP w stanie niskim, dopóki jest podłączony. Budzenie stałym poziomem obudziłoby więc MCU w kółko. Dlatego przyciski, CISZA, INT i USB_LAPTOP budzą przy poziomie przeciwnym do obecnego, czyli przy każdej zmianie stanu: podłączenie laptopa budzi, laptop podłączony już nie, odłączenie budzi znowu. DIO1 radia budzi stanem wysokim (koniec odbieranej ramki); gdy już jest wysoki, uśpienia nie ma, bo ramka czeka na odczyt. Test `tests/test_mcu_sleep.py` sprawdza te poziomy i listy obu płytek.
- **Radio.** Przed uśpieniem funkcja bierze blokadę operacji radia, więc zadanie odbioru nie jest w środku transakcji SPI, gdy rdzenie stają. SX1262 zostaje w odbiorze ciągłym.

Polecenie `NAP <ms>` (1–30 000 ms) robi jedno takie uśpienie do pomiaru prądu w czuwaniu. Działa tylko w trybie przygotowania i bez trwającej serii radiowej. Przed uśpieniem odpowiada `{"nap_ms":…}`, a po wybudzeniu `{"slept_ms":…,"cause":…,"line":…}`. `cause` to `timer`, `line` (wtedy `line` podaje linię: `dio1`, `up`, `down`, `ok`, `back`, `silence`, `prep`, na `v2` także `power_int` i `laptop`), `busy` (DIO1 wysoki, blokada radia zajęta albo trwa dźwięk brzęczyka), `rejected` (ESP-IDF odmówił uśpienia, zwykle bo linia zmieniła stan tuż przed uśpieniem; pętla czuwania sprawdza wtedy linie od nowa w następnym obiegu) albo `other`. Śpiący MCU nie obsługuje USB, więc laptop może zgłosić błąd portu albo połączyć go od nowa. EXTCOMIN ekranu (MCPWM) w uśpieniu stoi, dlatego `NAP` zawsze ma zegar i limit 30 s.

Czego nie da się sprawdzić bez płytki: prądu w uśpieniu, tego, czy Wio-SX1262 zostaje w odbiorze i czy ekran nie gaśnie przy zatrzaśniętych pinach, zachowania portu USB w czasie `NAP` i budzenia przez INT i USB_LAPTOP (te linie ma tylko `v2`). Na `l0` da się sprawdzić budzenie przyciskami, CISZĄ i DIO1, gdy prototyp wróci od wykonawcy.

## Pętla czuwania (v2)

Na `v2` stacja śpi także w zwykłej pracy. Po każdym obiegu pętli stacji, zamiast `delay(1)`, `standbyStep()` w `src/main.cpp` decyduje, czy uśpić MCU i na jak długo, a uśpienie wykonuje `platform::sleep`. Reguły są w `src/standby.h`, bez zależności od Arduino; sprawdza je `tests/test_standby.py`. Pętla jest tylko na `v2`, bo zasada 10 s wymaga wykrywania napięcia na VBUS (USB_LAPTOP). `l0` i `xiao` tej linii nie mają, więc śpią wyłącznie w `NAP`.

**Kiedy stacja nie śpi.** Pierwszy pasujący powód wygrywa; jego nazwę podaje polecenie `STANDBY` w polu `standby`.

| Powód | Warunek | Czuwanie |
|---|---|---|
| `prep` | tryb przygotowania | kończy się |
| `node` | stacja węzła stanowiska | kończy się |
| `usb` | laptop połączony (host wyliczył urządzenie) albo okno 10 s po pojawieniu się napięcia na VBUS, po zakończeniu połączenia przez host przy napięciu na VBUS i po starcie programu | kończy się |
| `radio` | łącze w oknie CCA albo w nadawaniu, nośna, seria pomiarowa, EMC; do 2 s po odebranej albo nadanej ramce; ramka czeka w pierścieniu zadania odbioru (wtedy `platform::sleep` zwraca `busy`) | przerwa |
| `panel` | przycisk wciśnięty (także przycisk przygotowania); do 1 s po wybudzeniu przyciskiem, CISZĄ, wyłącznikiem albo laptopem | przerwa |
| `screen` | ekran ma wiersze do wysłania; sterownik odmówił wymuszenia EXTCOMIN; bit VCOM z programu (EMD niski, przewody przy stole) | przerwa |
| `work` | porządkowanie magazynu po ZAMKNIJ ZDARZENIE, restart zaplanowany | przerwa |
| `short` | najbliższy termin za mniej niż 10 ms | przerwa |

Gdy czuwanie się kończy (`prep`, `node`, `usb`), EXTCOMIN wraca do licznika MCPWM, a stacja wraca na magistralę USB. Przerwa w czuwaniu niczego nie zmienia: po niej stacja zasypia dalej.

**Jak długo śpi.** Do najbliższego terminu, najwyżej 1 s. Terminy w planie to: koniec długu ciszy albo odroczenia datagramu czekającego na nadanie, koniec błysku diody, następny błysk i następny sygnał ekranu alarmu, następny BEACON, koniec okna 10 s i następna zmiana EXTCOMIN (co 0,5 s, więc w praktyce uśpienie trwa najwyżej 0,5 s). Terminy modułów stosu Reticulum, WICI-Link i aplikacji (ogłoszenia, ponowienia, wygasanie tras, przegląd rejestru, zapis zegara co 60 s, kontrola radia co 10 s) nie mają osobnego odczytu. Wszystkie są w sekundach, a obieg po każdym wybudzeniu je obsługuje, więc spóźniają się najwyżej o 0,5 s. Krótkie terminy po zdarzeniu radiowym (HACK w 200 ms, czekanie na HACK 600 ms, składanie dwóch ramek do 1 s, losowe opóźnienie przekazania ogłoszenia) pokrywa 2 s pracy po każdej ramce.

**USB i zasada 10 s.** Napięcie na VBUS (USB_LAPTOP w stanie niskim) otwiera okno 10 s, w którym stacja nie śpi i jest na magistrali. Gdy host wyliczy urządzenie, stacja nie śpi, dopóki połączenie trwa. PHY ESP32-S3 nie mierzy VBUS, więc wyjęty przewód wygląda dla TinyUSB jak zawieszenie magistrali, a urządzenie zostaje wyliczone. Dlatego połączenie trwa przy wyliczeniu bez zawieszenia albo przy wyliczeniu z napięciem na VBUS gniazda płytki (laptop uśpiony z przewodem w gnieździe dalej jest połączony). Wyjęcie przewodu z gniazda płytki zdejmuje napięcie, a przy stole na złączu DevKitC (bez napięcia na VBUS płytki) zawieszenie wystarcza. Bez połączenia w ciągu 10 s (np. ładowarka w gnieździe) napięcie nie wstrzymuje uśpienia. Przed uśpieniem stacja odłącza się od magistrali (`tud_disconnect`, bez podciągnięcia D+), więc laptop nie zaczyna połączenia ze śpiącym MCU, a wraca na nią (`tud_connect`) przy następnym oknie. Okno 10 s jest też po starcie programu. Laptop przy stole podłączony do złącza USB modułu DevKitC ma te same linie danych, ale nie daje napięcia na VBUS gniazda płytki, więc bez tego okna nie zdążyłby wyliczyć stacji ani wgrać programu (dotknięcie 1200 b/s). Gdy okno minęło, stacja wraca na magistralę w trybie przygotowania (przycisk przygotowania przez 3 s); program można też wgrać przez złącze UART modułu.

**EXTCOMIN.** Licznik MCPWM w lekkim uśpieniu stoi, a pin jest zatrzaśnięty, więc długie uśpienie dałoby panelowi składową stałą. W czuwaniu pętla przejmuje pin: wymusza stan na generatorze MCPWM (`mcpwm_generator_set_force_level`, `Display::forceExtcomin`) i odwraca go co 500 ms czasu rzeczywistego, także w przerwach czuwania. Uśpienie kończy się najpóźniej na następnej zmianie. Odmowa sterownika zostawia pin licznikowi, a stacja z włączonym ekranem przestaje zasypiać (`screen`).

**Radio.** SX1262 zostaje w odbiorze ciągłym. DIO1 budzi MCU na koniec odbieranej ramki. Ramka odebrana przez zadanie odbioru, a jeszcze nie przeczytana przez pętlę, wstrzymuje uśpienie: `platform::sleep` sprawdza pierścień ramek pod blokadą radia (`mcu_sleep::Hooks::pending`), więc ramka nie czeka całego uśpienia (HACK ma 200 ms). Sterownik SX1262 uznaje ramkę za spóźnioną (`rx_late`), gdy przy RxDone zastaje HeaderValid, a od poprzedniej próbki minęło ponad 25 ms, bo nie wie wtedy, czyj to nagłówek. Po uśpieniu ta przerwa jest zawsze dłuższa, więc po wybudzeniu, jeszcze pod blokadą radia, sterownik przyjmuje wybudzenie za chwilę ostatniej próbki (`LinkDriver::resumed`). To poprawne, bo DIO1 budzi MCU tuż po RxDone, a nagłówek następnej ramki przychodzi najwcześniej po jej preambule i nagłówku. Po każdym wybudzeniu pętla czeka 2 ms, bo takt FreeRTOS w uśpieniu stoi: zadanie odbioru (obieg co takt) czyta ramkę i próbkę RSSI, zanim MCU znowu uśnie, a nadzór zadania odbioru (`rx_watch.h`, 10 s bez obiegu to alarm `radio_awaria`) widzi jego obiegi. W uśpieniu zadanie odbioru nie zbiera znaczników aktywności kanału, więc po wybudzeniu okno CCA 50 ms liczy się od nowa (`Bench::resumed`): decyzja o kanale zapada dopiero po 50 ms pracy. MCU nie śpi w czasie samego nadawania. Nadanie LoRa trwa w obiegu pętli pod blokadą radia, a zysk byłby mały przy prądzie nadawania.

**Polecenie `STANDBY`** (tylko `v2`, port diagnostyki) podaje stan i liczniki od startu. Uśpiona stacja nie ma USB, więc liczniki czyta się po podłączeniu laptopa (od tej chwili powód `usb`):

```
{"standby":"usb","usb":"attached","vbus":true,"mounted":true,"vcom":"timer","sleeps":171223,"slept_ms":85107430,
 "uptime_ms":86421005,"wake":{"timer":169870,"radio":1201,"input":152,"other":0},"rejected":3,"busy":41}
```

`slept_ms` / `uptime_ms` to udział uśpienia w czasie pracy, potrzebny do oceny prądu czuwania. `wake` dzieli wybudzenia na zegar, DIO1, inne linie z listy i przyczyny nierozpoznane; `rejected` i `busy` to próby bez uśpienia (odmowa ESP-IDF; DIO1 wysokie, blokada radia albo dźwięk brzęczyka). `vcom` mówi, czy EXTCOMIN prowadzi pętla (`loop`), czy licznik (`timer`).

**Co wymaga pomiaru na płytce v2.**

1. Prąd czuwania: średni pobór z szyny 3,3 V w czuwaniu bez ruchu radiowego (model: lekkie uśpienie z SX1262 w odbiorze ciągłym) i z ruchem na granicy długu ciszy (cel z modelu: około 14 mA), razem z udziałem uśpienia z `STANDBY`. Stąd czas czuwania na ogniwach: **8 dni czuwania jest celem pomiarowym**, a wymaganiem pozostaje W23 (≥48 h na ogniwach).
2. Koszt jednego wybudzenia: czas pracy po wybudzeniu przez zegar (obieg pętli i 2 ms dla zadania odbioru) i prąd w tym czasie. Przy dwóch wybudzeniach na sekundę od tego zależy, czy warto obniżyć zegar CPU albo budzić rzadziej (EXTCOMIN z licznika działającego w uśpieniu).
3. Ekran przy EXTCOMIN prowadzonym przez pętlę: obraz bez zmian po wielu godzinach czuwania, przebieg 1 Hz na pinie oscyloskopem, brak zakłóceń przy przejściu między licznikiem a pętlą.
4. Odbiór bez strat: seria ramek od sąsiedniej stacji w czuwaniu (liczniki `rx_ok` i `rx_late` przy odbiorcy wobec nadanych), także dwie ramki jednego datagramu tuż po sobie, oraz brak alarmu `radio_awaria` po dobie czuwania.
5. USB: laptop podłączony do gniazda płytki w czuwaniu (wybudzenie, okno 10 s, wyliczenie), wyjęcie przewodu (stacja znowu śpi), laptop uśpiony z przewodem (stacja nie śpi), stan `tud_suspended` po wyjęciu przewodu ze złącza DevKitC, ładowarka w gnieździe (po 10 s stacja śpi i jest odłączona), zamiana ładowarki na laptopa, wgranie programu przez złącze DevKitC w oknie po starcie, ponowne połączenie po `tud_disconnect`/`tud_connect`.
6. Wybudzenia przyciskami, CISZĄ i wyłącznikiem: reakcja ekranu bez opóźnienia, przytrzymanie przycisku przygotowania przez 3 s w czuwaniu, długie naciśnięcie wyłącznika (INT w stanie niskim przez 5–19 s).
7. Zadanie odbioru i takt FreeRTOS po wybudzeniu: `rx_task_loops` w `INFO` rośnie w czuwaniu, a `loop_max_ms` nie rośnie.

## Zestaw XIAO (xiao)

Środowisko `xiao` buduje ten sam program stacji co `l0` (WICI-Link v3 przy konfiguracji numerowanej, Reticulum bez niej) dla dwóch zestawów Seeed 102010611 z [hardware/radio-pair](../../hardware/radio-pair/README.md): XIAO ESP32-S3 (ESP32-S3R8, 8 MB flash, 8 MB PSRAM ośmiobitowej) z płytką Wio-SX1262. Zestawy służą jako dodatkowe stacje w próbach D21 przy stole ([procedura](../../hardware/xiao-wici/README.md)). Nie zastępują prototypu w próbach energii (W23), zaniku zasilania, zapasu RAM (D14) ani czułości: nie mają FRAM, toru zasilania ani obudowy stacji, a PSRAM zmienia rozkład sterty. Wersja w `INFO`: `xiao-0.1`, `bench: "XIAO"`, `board: "XIAO"`. Obraz się kompiluje (RAM statycznie 182 052 B z 327 680 B, 55,6%; flash 607 059 B). Na obu zestawach (2026-11-02) startuje i przechodzi `INFO`, `RADIO`, `FRAM` i `RNS SELFTEST`; próby z [procedury](../../hardware/xiao-wici/README.md) nie były wykonane. Pierwsze uruchomienie kończyło się pętlą restartów: `config_ = config::Config()` w `Store::loadConfig` budowało kopię 7,8 KB na stosie pętli (16 KiB) w głębi `setup()`, a zrzut awarii z partycji `coredump` pokazał przekroczenie stosu w tym wierszu. Konfigurację zeruje teraz w miejscu `config::clear`; ten sam błąd dotyczył obrazu `l0`.

| Sygnał | GPIO ESP32-S3 | Uwagi |
|---|---|---|
| SPI SCK / MISO / MOSI | 7 / 8 / 9 (D8 / D9 / D10) | radio 1 MHz, napęd domyślny ESP-IDF |
| NSS / NRESET SX1262 | 41 / 42 | złącze B2B płytki Wio |
| BUSY / DIO1 | 40 / 39 | jak w `l0`: przerwania przez SPI, DIO1 tylko w `RADIO` |
| RXEN (RF_SW1) | 38 | stan wysoki tylko w odbiorze; nadawanie przełącza DIO2 układu; TCXO 1,8 V z DIO3 |
| OK | 0 (przycisk BOOT) | potwierdza `PREP 1` i `CONDUCTED`; innych przycisków nie ma |
| dioda | 21 (żółta USER, aktywna stanem niskim) | `LED 1`: rytm pracy co 0,5 s, szybkie miganie przy czekaniu na BOOT |

Piny pochodzą z programu `pair-0.4` i jego źródeł ([ZRODLA-I-WERYFIKACJA.txt](../../hardware/radio-pair/ZRODLA-I-WERYFIKACJA.txt): strona Seeed zestawu i wariant `seeed_xiao_s3` Meshtastic); na tych pinach para przeszła 100/100 wymian i próbę surowych ramek WICI-Link ([dowód](../../hardware/radio-pair/evidence/wici-raw-2026-11-01.md)). Plik płytki definiuje dwa przełączniki: `WICI_HEADLESS` (bez ekranu Sharp; model ekranu działa dalej, więc `SCREEN` pokazuje treść, a `KEY` i `REQ` zastępują przyciski) i `WICI_FRAM_PSRAM`. Brak przycisków, diod i panelu wyraża się jak w innych płytkach pinem −1; `BTN`, `LED 2–4`, `DISPLAY`, `VCOM`, `VTEST` i `BUZZ` nie mają tu sensu.

**FRAM w PSRAM.** Zestaw nie ma FRAM. `src/fram_ram.h` (`fram::RamMemory`) trzyma obraz 512 KiB w PSRAM pod tą samą mapą co FRAM (dziennik, magazyn, tablice Reticulum, stan WICI-Link), z 16-bajtowym znacznikiem przed obrazem i zapisem pamięci podręcznej PSRAM po każdym zapisie. Obraz przetrwa restart programowy (`REBOOT`, zmiana roli po `configure`, ZNISZCZ DANE, watchdog), ale **ginie po odłączeniu zasilania** (także po przycisku RESET, jeśli odcina on zasilanie PSRAM: niesprawdzone). Bez znacznika (po włączeniu zasilania albo gdy sterta dała inny blok) obraz jest zerowany i stacja startuje jak nowa: nowa tożsamość, bez konfiguracji, dziennik od zera i największy dług ciszy (10 s). Obraz nie jest kopiowany do flash: sam dług ciszy i zegar dają do około 133 tys. zapisów na dobę, które zużyłyby pamięć flash. `INFO` podaje `fram_volatile: true`, a `FRAM` `{"fram":"emulated-psram",…,"volatile":true,"kept":…}`; `kept: false` po restarcie programowym oznacza utratę obrazu. Wpis „FRAM image in PSRAM cleared” w `LOG` znaczy nową stację.

**Ponowne przygotowanie po zaniku zasilania.** Klucze stacji powstają w trybie przygotowania i istnieją tylko w PSRAM. Po odłączeniu zasilania zestaw ma nową tożsamość, więc karty i plan sieci z jego starymi kluczami są nieważne: odczytać nową kartę (`card`), wpisać nowe klucze `ed25519`/`x25519` w `priority_keys` wszystkich sąsiadów i skonfigurować ich ponownie, a zestawowi wgrać konfigurację. Rejestr stanowiska nie wiąże ponownie tego samego numeru z innym kluczem ([usb-protocol.md](../../docs/spec/usb-protocol.md#transfery-dzielone-na-części)), więc zestaw dostaje nowy numer stacji albo próba zaczyna się od nowego nośnika stanowiska. Zestawy zasila się więc z USB komputera bez przerw przez całą serię prób.

**Przygotowanie i obsługa tylko przez USB.** Port „diagnostyka” i port „dane” jak w `l0`. Przygotowanie: `PREP 1` i przycisk BOOT w ciągu 30 s (dioda miga), potem aplikacja laptopa na porcie danych (`configure`, `card`) albo `USB <wiersz JSON>` z portu diagnostyki; pytania z potwierdzeniem (`silence`, `close`, `destroy`, karta) zamyka `KEY OK`, a `SCREEN` pokazuje pytanie. Zgłoszenia: `REQ <n> [<bajty tekstu>]` albo `submit` protokołu USB; TEST: `test` protokołu albo menu przez `KEY`. Stan: `INFO`, `APP` (`intents` = zgłoszenia przed RECEIVED), `STORE`, `RNS`, `HACK`, `LOG`, `JOURNAL`.

**Role.** Stacja schronienia z rodzicem (`network.parent`) jest przekaźnikiem dla stacji, które plan sieci stawia za nią, i źródłem własnych zgłoszeń; root (`role: "wezel"`, `network.station` = `network.root`, rodzice 0) przenosi ramki WICI-Link w KISS na porcie danych do aplikacji stanowiska (`python -m wici.stanowisko start --port PORT_DANYCH`); zmiana roli restartuje zestaw, a obraz w PSRAM to przeżywa. Bez `network` zestaw pracuje w Reticulum jak `l0`. Root uczy się dróg w dół tylko według planu sieci (`priority_keys[].behind` w swojej konfiguracji; sąsiad jest zawsze drogą do siebie), więc plan stanowiska podaje stacje stojące za jego sąsiadami. Dokument stacji schronienia nie może mieć `behind`: przekaźnik zna drogi w dół tylko do swoich sąsiadów, a ramkę do dalszej stacji rozsyła. Drogi do nadawcy koperty root uczy się tylko po HACK od aplikacji w ramce KISS z poleceniem 0x00 (nowa część koperty uwierzytelniona MAC koperty); HACK z poleceniem 0x02 (powtórzenie, ramka odłożona, koperta nieuwierzytelniona) root nadaje bez nauki tej drogi. Przekaźnik usuwa drogę w dół po 3 próbach ramki w dół bez HACK ([w dół](../../docs/spec/wici-link.md#ruch-w-górę-i-w-dół)). Root nadaje BEACON-y tylko przy otwartym porcie danych, a ramkę w dół, której nie może nadać, od razu odsyła aplikacji stanowiska w ramce KISS z poleceniem 0x01 ([odmowa roota](../../docs/spec/wici-link.md#implementacja)). Niepewny zapis FRAM wyłącza łącze WICI-Link bez restartu: `LOG` ma wtedy „wici durable state uncertain: link silent, FRAM re-read every 10 s”, a po udanym ponownym odczycie „wici durable state recovered”; skasowane uszkodzone wpisy pierścieni podaje „wici: N damaged ring records cleared”.

```bash
cd firmware && ../.venv-pio/bin/pio run -e xiao            # budowa
cd firmware && ../.venv-pio/bin/pio run -e xiao -t upload  # wgranie: port USB-C XIAO; bez odpowiedzi BOOT przy RESET
```

Nie wgrywać obrazu `xiao` do DevKitC ani `l0` do XIAO (inne piny radia). Kopię fabrycznej pamięci robi się według [radio-pair](../../hardware/radio-pair/ZRODLA-I-WERYFIKACJA.txt).
