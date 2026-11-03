# WICI: narzędzie surowego LoRa na RAK4631 (`lora-raw`)

Program `lora-raw-0.2` dla RAK4631 (nRF52840 i SX1262 w module RAK4630) na płytce RAK19007. Zamienia zestaw radia RNode w podsłuch kanału i nadajnik dowolnych ramek w profilu LoRa pilotażu do [prób D21 przy stole](../xiao-wici/README.md#podsłuch-i-węzeł-wrogi-lora-raw). Nie ma w nim logiki WICI, RNode ani Reticulum: nie dodaje nagłówka, nie sprawdza kanału, nie ma długu ciszy ani limitu czasu nadawania. Bajty z polecenia `tx` idą w eter bez zmian, a każda odebrana ramka (także z błędem CRC) trafia do USB.

**Na sprzęcie (2026-11-02):** dwa RAK4631 przy −9 dBm, 1 m od siebie: `info` z `"ready":true` i `"begin":0` na obu, 12/12 ramek (po 3 ramki 21 B i 255 B w każdą stronę) z poprawnym CRC, RSSI −50…−54 dBm, SNR 12,25…13,75 dB. Zmierzony `air_us` przewyższa `toa_us` o około 0,23 ms: 73,20 ms wobec 72,96 ms dla 21 B, 416,22 ms wobec 416,00 ms dla 255 B. Podsłuch i węzeł wrogi w próbach D21 nie były jeszcze uruchomione.

## Dlaczego nie RNode

Oficjalny firmware RNode (`markqvist/RNode_Firmware`, commit `56775c51`, sprawdzone 2026-11-02) w zwykłym trybie, którego używa `RNodeInterface` Reticulum, dokłada do każdej ramki LoRa własny nagłówek 1 B i interpretuje go przy odbiorze (`RNode_Firmware.ino`, `transmit()` i `receive_callback()`; `Framing.h`: `FLAG_SPLIT` 0x01; `Utilities.h`: `isSplitPacket()` = bit 0, `packetSequence()` = starsza połówka):

- **Odbiór:** pierwszy bajt ramki jest zawsze zdejmowany jako nagłówek RNode, więc host nie dostaje bajtu `ver/t` ramki WICI-Link v3. Gdy bit 0 tego bajtu jest ustawiony, RNode traktuje ramkę jako pierwszą połowę datagramu dzielonego i jej nie oddaje. W v3 bit 0 to ACKREQ, a starsza połówka bajtu każdej ramki DATA to 0xC, więc jednoadresowa DATA z ACKREQ czeka w buforze: następna DATA z ACKREQ zostaje z nią sklejona w jeden fałszywy pakiet, a następna ramka bez bitu 0 (HACK, BEACON, rozsyłana DATA) kasuje ją bez śladu. Podsłuch na RNode gubiłby więc właśnie DATA z ACKREQ i ich czasy, a pozostałe ramki dostawał o 1 B krótsze.
- **Nadawanie:** RNode dokłada przed treścią bajt z losową starszą połówką (`random(256) & 0xF0`), a treść dłuższą niż 254 B dzieli na dwie ramki. Ramka WICI z hosta wychodzi przesunięta o 1 B, z losowymi bitami wersji; stacja odrzuca ją (MAC liczony jest od bajtu 0).
- **Tryb nasłuchu wszystkiego** (`CMD_PROMISC` 0x0E) przenosi ramki bez nagłówka, ale na nRF52 i ESP32 w tym commicie odebrana ramka trafia tylko do bufora z flagą `packet_ready`, której pętla nie obsługuje (do hosta idą wyłącznie ramki z kolejki `modem_packet_queue`, którą zasila zwykły tryb). Do tego RNode odracza nadanie przy zajętym kanale (CSMA), nie podaje czasu RxDone ani TxDone z zegara urządzenia, nie zgłasza ramek z błędem CRC, a mocy nie da się ustawić poniżej 0 dBm (bajt bez znaku w `CMD_TXPOWER`).

Do pomiarów zasięgu (kroki 2, 3 i 5) zestawy wracają do firmware RNode ([radia RNode](../rnode/README.md)).

## Profil i sprzęt

Profil jak w [specyfikacji radia](../../docs/spec/radio.md#profil-lora-pilotażu) i w `firmware/src/lora_profile.h`: 869,525 MHz, 125 kHz, SF7, CR 4/5, preambuła 24 symbole, nagłówek jawny, CRC, słowo synchronizacji 0x12 (rejestry 0x0740 = 0x14, 0x0741 = 0x24), odbiór ze wzmocnieniem (Rx Boosted gain), regulator DC-DC. Moc po starcie −9 dBm (najmniejsza dla wzmacniacza SX1262 w RadioLib 7.6.0, zakres −9…22 dBm).

| Sygnał SX1262 | Pin nRF52840 (numer Arduino) |
|---|---|
| NSS | P1.10 (42) |
| SCK | P1.11 (43) |
| MOSI | P1.12 (44) |
| MISO | P1.13 (45) |
| BUSY | P1.14 (46) |
| DIO1 | P1.15 (47) |
| NRESET | P1.06 (38) |
| zasilanie przełącznika antenowego | P1.05 (37), stale w stanie wysokim |
| przełącznik nadawanie/odbiór | DIO2 SX1262 |
| TCXO | DIO3 SX1262, 3,3 V |

Źródła (sprawdzone 2026-11-02): RNode_Firmware `56775c51`, `Boards.h` (`BOARD_RAK4631`: `pin_cs` 42, `pin_sclk` 43, `pin_mosi` 44, `pin_miso` 45, `pin_busy` 46, `pin_dio` 47, `pin_reset` 38, `pin_rxen` 37, `DIO2_AS_RF_SWITCH`) i `sx126x.cpp` (`enableTCXO`: 3,3 V dla RAK4631); biblioteka producenta modułu `beegee-tokyo/SX126x-Arduino`, `lora_rak4630_init` (te same piny, `RADIO_RXEN` 37 „power for antenna switch”, `USE_RXEN_ANT_PWR`, DIO2 jako przełącznik, DIO3 dla TCXO z domyślnym `TCXO_CTRL_3_3V`, DC-DC); `meshtastic/firmware`, `variants/nrf52840/rak4631/variant.h` (te same piny, `SX126X_POWER_EN` 37, DIO2 jako przełącznik). Meshtastic ustawia TCXO na 1,8 V; narzędzie idzie za biblioteką producenta i RNode. Zły TCXO objawia się błędem `begin` w `info`.

Płytka w PlatformIO to nRF52840-DK z rdzenia Adafruit (ten sam układ, SoftDevice S140 6.1.1 i układ pamięci co bootloader RAK4631) z własnym wariantem pinów `variants/rak4631_wici` i wgrywaniem przez bootloader (`nrfutil`, dotknięcie 1200 b/s). Zegar urządzenia to TIMER4 1 MHz z kwarcu HFXO, rozszerzony do 64 bitów.

## Budowa i wgranie

```sh
cd hardware/lora-raw
pio run                                   # obraz: Flash 87 648 B (10,8%), RAM 10 760 B (4,3%), 2026-11-02
pio run -t upload --upload-port PORT      # PORT: /dev/ttyACM0 albo /dev/cu.usbmodem…
```

Wgranie zastępuje firmware RNode. Na zestawach z 2026-11-02 dotknięcie 1200 b/s tylko restartuje płytkę do aplikacji (z programem fabrycznym RAK, z RNode i z `lora-raw`), więc `pio … -t upload` się nie udaje, a mimo to kończy się napisem „SUCCESS”; o wyniku świadczy dopiero `info`. Działa wejście ręczne: dwa szybkie naciśnięcia RESET (dioda wolno pulsuje, port zgłasza się jako „WisBlock RAK4631”, nazwa portu się nie zmienia), potem wgranie zbudowanego obrazu bez dotknięcia:

```sh
adafruit-nrfutil dfu serial --package .pio/build/rak4631/firmware.zip -p PORT -b 115200
```

Po wgraniu port zgłasza się jako „WICI lora-raw”. Powrót do RNode: `rnodeconf --autoinstall` według [radiów RNode](../rnode/README.md), potem `rnodeconf --info` i wpis w raporcie. Antena albo tor z tłumikami musi być podłączony przed zasilaniem.

## Protokół USB

Polecenia tekstowe zakończone znakiem nowej linii; odpowiedzi to wiersze JSON.

| Polecenie | Odpowiedź |
|---|---|
| `info` | `{"info":"lora-raw-0.2","board":"rak4631","ready":true,"begin":0,"mhz":869.525,"bw_khz":125,"sf":7,"cr":5,"preamble":24,"sync_word":18,"crc":true,"explicit_header":true,"tcxo_v":3.3,"power_dbm":-9,"rx_stream":true,"tx_count":0,"reset":2,"cut":0,"t_us":…}`; `reset` to rejestr RESETREAS tego startu (2: watchdog, 0: włączenie zasilania), `cut` to wiersze ucięte, bo komputer nie czytał portu |
| `rx on`, `rx off` | `{"rx_stream":true}`; po `rx on` każda ramka: `{"rx":"<hex>","len":N,"rssi":-52.0,"snr":9.25,"crc":true,"t_us":T}`, gdzie `t_us` to przerwanie RxDone (koniec ramki w eterze); po `rx off` radio stoi w gotowości |
| `tx <hex>` | po TxDone: `{"tx":"done","n":K,"len":N,"start_us":S,"done_us":D,"air_us":D−S,"toa_us":…,"power_dbm":P}`; `start_us` to chwila po poleceniu SetTx, `toa_us` czas ze wzoru RadioLib |
| `power <dBm>` | `{"power_dbm":P}`, zakres −9…22 |

Błędy: `{"err":"<co>","code":C}` (`busy` przy nadawaniu w toku, `length`, `hex`, `power_range`, `tx_timeout`, `receive`, `read`, `command`). Czasy są w µs od startu urządzenia. Po starcie odbiór jest włączony. Zapis do USB nigdy nie zatrzymuje programu: wiersz, który nie wyjdzie w 100 ms (komputer trzyma port otwarty, ale nie czyta), jest ucinany i liczony w `cut`. Pętla, która stanie na 4 s z innego powodu, restartuje urządzenie (watchdog); `info` pokazuje wtedy `reset` z bitem DOG (wartość 2), a czasy zaczynają się od zera.

Skrypty prób są w `hardware/xiao-wici/tools`: [`monitor.py`](../xiao-wici/tools/monitor.py) (podsłuch) i [`hostile.py`](../xiao-wici/tools/hostile.py) (węzeł wrogi); testy bez sprzętu: `python3 -m unittest tests.test_bench_tools`.

Licencja tego pliku: CC-BY-4.0 ([LICENSE.md](../../LICENSE.md)); kod MIT.
