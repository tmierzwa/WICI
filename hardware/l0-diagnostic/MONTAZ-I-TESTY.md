# WICI L0: montaż, uruchomienie i próby

Dla jednej sztuki: N1 (SMD z JLCPCB) + ESP32-S3-DevKitC-1-N8R8 + Wio SX1262 + Sharp LS027B7DH01A, program diagnostyczny `l0-0.5`. Źródła prawdy: [połączenia MCU](reference/polaczenia-MCU-L0.csv), [połączenia N1](../dev-bench/polaczenia.md), [instrukcja programu](README.md). Przy sprzeczności z [uruchomieniem N1](../dev-bench/uruchomienie.md) (stanowiska A/B) obowiązuje ten dokument.

Kolejność jest tak ułożona, żeby każdy błąd wyszedł na etapie, na którym jest jeszcze tani do poprawienia. Nie przeskakiwać etapów.

## 0. Przed lutowaniem

1. **Oględziny SMD** pod mikroskopem: mostki na J7 (raster 0,5 mm), U2 (SOT-23-6); kropki U1–U4 zgodne z opisem; Q1, D3 (SOT-23), D2 (pasek). U1 powinien być MB85RS4MT (montaż JLC); CY15B104QN też jest dopuszczony.
2. **Szyny bez niczego:** JP1.1 (+3V3) – J11.1 (GND) rośnie (C13 100 µF), bez zwarcia; C9 (+5V_LCD) – GND ≈ 1,3 MΩ (dzielnik R21+R22).
3. **Przymiarka 1:1** na gołej płytce: DevKitC w J5/J6 (pin 1 od strony anteny, USB w stronę napisu USB na płytce), panel w obrysie, taśma FPC sięga J7 bez naprężenia przy krawędzi szkła. Wynik zapisać.
4. **Wgrać DevKitC poza płytką** (rozdział 4, kroki 1–3). Oddziela problemy USB i narzędzi od problemów montażu; fabryczny program nie trafia na N1. Bez peryferiów oczekiwane: `INFO l0-0.5 … 0 …`, `FRAM_ID unknown …`, `ERR radio_begin …`; port, wgranie i odpowiedzi na polecenia muszą działać.

## 1. N1

1. **R12 10 kΩ → 1 kΩ** (0805, 1%) jako pierwsze, zanim THT zasłoni dostęp. Kontrola: J5.15 (RF_RESET) – GND ≈ 1,0 kΩ.
2. **THT** od najniższych: SW1–SW6, D1 (katoda = kwadratowy pad 1, do masy), BZ1 („+” = pad 1), SW5, J11, JP1, JP2, J12, potem J5/J6 (na wpiętym DevKitC albo listwie, żeby stały w osi). J6.22 ma pełne połączenie z polem masy: większy grot.
    - B3F-4055 obrócony o 90° jest trwale zwarty; po wlutowaniu każdy przycisk sprawdzić omomierzem.
    - Nie obsadzać J1–J4, J9/J10, JP3 (złącza stanowisk A/B; J9/J10 leżą na RF_CS, RF_RESET i SPI wspólnych z Wio).
3. **Zworki** JP1 i JP2 założone (JP1: DevKitC 3V3 → +3V3 N1; JP2: 5 V brzęczyka).
4. **Dystanse** M3 × 12 mm w H1–H5. H6–H9 tylko nylon albo nic: pady pustych J1–J4 są na sieciach, H7 jest 3,6 mm od J4.10.

## 2. Adapter Wio

Piny Wio sprawdzone na sprzęcie w R0 (`hardware/radio-pair/src/main.cpp`), po stronie XIAO ESP32S3: SCK GPIO7 (D8), MISO GPIO8 (D9), MOSI GPIO9 (D10), NSS GPIO41, DIO1 GPIO39, NRST GPIO42, BUSY GPIO40, RXEN GPIO38; TCXO 1,8 V z DIO3, DIO2 przełącza TX.

1. **Zanim odłączysz XIAO:** potwierdź przyporządkowanie padów Wio z tabeli niżej (z paczki RFQ) wobec schematu Seeed Wio-SX1262. Linie SPI dzwoni się omomierzem od padu Wio do D8/D9/D10 XIAO (na krawędzi modułu); NSS, NRST, BUSY, DIO1 i RXEN idą do XIAO tylko przez B2B, więc dla nich schemat. Pomyłka w tej tabeli to najbardziej prawdopodobna przyczyna `radio_begin -2`.
2. XIAO zdjąć z B2B równomiernie, bez podważania jednego końca. Wio VIN nie podłączać.
3. Przy Wio: 100 nF + 10 µF na 3V3 do GND, 10 kΩ z RXEN do GND. 3V3 z JP1.1 przez POWER_BREAK (listwa 1×2 ze zworką), GND z J11.1.
4. Przewody ≤ 6 cm, SPI skręcone z masą albo taśma z masą co drugą żyłą. Bez pętli i odgałęzień: SPI jest wspólne z FRAM (8 MHz) i ekranem.
5. Antena na złącze IPEX przed pierwszym zasileniem, zatrzaśnięta prostopadle; przewód odciążony, żeby nie wyrwać gniazda.

| Sygnał | Wio | Punkt N1 | GPIO DevKitC |
|---|---|---|---:|
| SCK | J2.6 | J5.18 (SPI_SCK_DEVKIT) | 12 |
| MOSI | J2.4 | J5.17 | 11 |
| MISO | J2.5 | J5.19 | 13 |
| NSS | J1.4 | J5.16 (RF_CS, R11 10 kΩ do 3V3) | 10 |
| NRST | J1.3 | J5.15 (R12 1 kΩ do GND) | 9 |
| BUSY | J1.2 | J5.20 | 14 |
| DIO1 | J1.1 | J6.18 | 21 |
| RXEN | J1.5 | J6.6 (10 kΩ do GND przy Wio) | 42 |
| 3V3 | 3V3 | JP1.1 przez POWER_BREAK | |
| GND | GND | J11.1 | |

## 3. Kontrola przed zasilaniem

Bez DevKitC, bez panelu, POWER_BREAK założony.

| Pomiar | Oczekiwane | Inaczej |
|---|---|---|
| Każdy pad Wio – jego punkt N1 | 0 Ω | przewód / pomyłka pinu |
| Linie SPI parami, NSS–NRST, BUSY–DIO1 | brak połączenia | mostek na adapterze |
| J5.15 – GND | ≈ 1 kΩ | ≈ 10 kΩ: R12 niewymieniony |
| J6.6 – GND | ≈ 10 kΩ | brak pull-down RXEN |
| J5.16 – JP1.1 | ≈ 10 kΩ (R11) | |
| JP1.1 – GND, Wio 3V3 – GND | brak zwarcia | |
| J7: pary sąsiednich pinów | zwarte tylko 6–7–8 (+5V_LCD) i 9–10 z uchwytami (GND) | mostek na J7 |
| SW5 w pozycji CISZA: J6.4 – GND | ≈ 1 kΩ (R16) | orientacja SW5 |

## 4. Pierwsze zasilanie i program

Zasilanie wyłącznie przez port **USB** (native USB/OTG) DevKitC, przewodem z danymi, przez miernik prądu USB. Port UART nie ma konsoli tego obrazu. Źródła AA/12 V odłączone.

1. Paczka programu: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`; obraz z paczki (`images/l0-full.bin` na 0x0) albo `pio run` w `hardware/l0-diagnostic`.
2. Kopia fabryczna: `esptool --chip esp32s3 --port PORT read_flash 0 0x800000 backups/l0-factory-<nr>.bin`, potem `shasum -a 256 -c SHA256SUMS.txt` i `write_flash 0x0 images/l0-full.bin`. Bez `erase_flash`. Port niewidoczny: BOOT + RESET.
3. Konsola `pio device monitor --port PORT --baud 115200`. Komunikaty startu zwykle giną przed otwarciem portu: od razu `INFO`, `STATUS`, `RDID`.
4. DevKitC na N1 (bez panelu; FPC wpina się w kroku 6). Prąd z USB i napięcia według tabeli niżej.
5. `INFO` musi dać `INFO l0-0.5 <MAC> 1 <reset> <boot_id> 869.525 125 7 5 0 1.8`. Trzecie pole `1` = radio, FRAM, timer ekranu i brzęczyka gotowe. `RDID`: `FRAM_ID MB85RS4MT 047F49…` albo `CY15B104QN 7F7F7F7F7F7FC22C…`. MAC zapisać jako identyfikator sztuki.
6. Panel: bez zasilania, FPC stykami w dół do oporu, klapka zamknięta. Panel **nie** przyklejać przed zaliczeniem E5 (klej akrylowy, szkło).

**Pomiary w kroku 4:**

| Punkt | Oczekiwane |
|---|---|
| Prąd całości (USB) | zapisać; skok > 250 mA albo grzanie: odłączyć |
| JP1.1 (+3V3) | 3,2–3,4 V; ≥ 3,0 V przy pracy |
| C9 / J7.7 (+5V_LCD) | 4,90–5,36 V (dopuszczalne 4,8–5,5 V) |
| Prąd Wio (amperomierz w POWER_BREAK, odbiór) | kilka mA (SX1262 Rx Boosted + TCXO); zapisać spoczynek, RX, TX |
| J6.6 (RXEN) w odbiorze | ≈ 3,3 V |

### Diagnoza

| Objaw | Przyczyna / sprawdzenie |
|---|---|
| Brak portu | port UART zamiast USB; przewód tylko do ładowania; BOOT + RESET |
| Port znika cyklicznie, `INFO` pole 4 = `9` | brownout: zwarcie lub spadek +3V3 przy starcie radia; prąd USB, C13, adapter |
| Pole 4 = `4`–`7` | wyjątek / watchdog: zrzut konsoli zaraz po resecie |
| `FRAM_ID unknown FFFF…`, `ERR fram_id_unsupported` | MISO nienapędzane: CS nie dochodzi do U1. U3.1 (wyjście nadzorcy) ma być L przy 3,3 V; U4.4 ma śledzić J5.12 (FRAM_CS). Orientacja U3/U4 |
| `FRAM_ID … 0000…` | MISO zwarte do masy albo U1 bez zasilania (U1.8) |
| `radio_begin -2` | układ nie odpowiada: pomyłka pinu w adapterze, MISO/MOSI zamienione, Wio bez 3V3 (POWER_BREAK), NRST trzymany nisko |
| `radio_begin -705` | BUSY nie schodzi: przewód BUSY, zasilanie Wio, TCXO nie startuje |
| `radio_begin -706` / `-707` | polecenie odrzucone / błąd kalibracji (XOSC): 3V3 na Wio przy starcie, odsprzęganie przy Wio |
| `TX -5` (timeout) | brak DIO1 (RadioLib czeka na TxDone przez DIO1) |
| Nadaje, słabo odbiera / tylko w jedną stronę | RXEN: J6.6 ma być H w odbiorze, L w nadawaniu |
| `ERR cooldown` | odstęp 13 czasów pakietu, nie usterka |
| Ekran pusty przy `ext=1` | FPC odwrócone lub niedociśnięte, mostki J7, J7.5 (DISP) ma być H po starcie, +5V_LCD |
| Obraz blednie, „pływa” | EXTCOMIN: J7.4 ma mieć 1 Hz ~50% (`ext=1` w STATUS to tylko stan timera) |
| Obraz poszarpany, przesunięty | integralność SCK/MOSI: długość przewodów adaptera, masa |
| `inputs` ≠ `00` w spoczynku (CISZA wyłączona) | przycisk obrócony o 90° albo mostek; bity: 0 GÓRA, 1 DÓŁ, 2 OK, 3 WSTECZ, 4 CISZA, 5 PREP |
| Brzęczyk milczy | JP2 zdjęta, Q1/D2, polaryzacja BZ1 |

## 5. Próby

Pełny opis i polecenia: [instrukcja programu L0](README.md#kolejność-prób-po-montażu). **FRAMTEST, GUARD i MIX niszczą zawartość FRAM**, stąd kolejność: retencja (E3) przed E4 i E6. Partner: XIAO z Wio z obrazem R0 `pair-0.4`, anteny założone, 2–3 m. Wszystkie logi i JSON z `results/` zachować; `physical_acceptance=false` w JSON jest celowe (oględziny i oscyloskop ocenia się osobno).

| Próba | Wykonanie | Zalicza |
|---|---|---|
| E1 | 10 restartów (RESET i odłączenie USB), `INFO`/`STATUS` | za każdym razem pole 3 = 1, brak `ERR`, nowy `boot_id` |
| E2 | napięcia i prądy z rozdziału 4 w spoczynku, RX i TX (`TX` z partnerem) | w zakresach, bez resetów i grzania |
| E3 | `diagnose.py --port PORT --fram-write 12345678`; USB odłączone ≥ 60 s; `--fram-verify 12345678` | zapis: 5 × `FRAM_PASS <n> 0 <crc> <crc>` (zero błędów, oba CRC równe) i `FRAM_DONE … WRITE`; po zaniku `FRAM_PASS 4 0 …` i `FRAM_DONE … VERIFY` |
| E4 | `GUARD ERASE`, oscyloskop: CH1 +3V3 (JP1.1), CH2 CS **za bramką** U1.1, CH3 GUARD U3.1; wyzwalanie zboczem opadającym CH1 ≈ 3,0 V, pojedyncze, podstawa czasu obejmująca spadek do < 1,8 V (zacząć od 2 ms/dz); odłączyć USB od strony DevKitC | CH3 rośnie przy ≈ 2,7 V, CH2 idzie w H, zanim CH1 spadnie do 1,8 V; zrzut ekranu do raportu |
| E5 | `LCD 0`…`LCD 4`, `PAUSE 10000` z sondą na J7.4, każde wejście (`INPUT xx`), `LED 1/0`, `BUZZ 1/0` | plansze bez błędów pikseli; EXTCOMIN 1 Hz także w pauzie; 6 wejść, LED, 2048 Hz |
| E6 | `diagnose.py --port PORT_L0 --mixed --peer PORT_R0` (15 min), sondy na SCK i CS-ach | `MIX_DONE` z 0 błędów, ≥ 900 cykli, odstęp ≤ 1000 ms; 100/100 pakietów; ekran poprawny |
| R1/R2 | po restarcie obu: `radio_test.py --a PORT_L0 --b PORT_R0 --version-a l0-0.5 --version-b pair-0.4 --count 100` | 100/100 w obie strony, treść zgodna; RSSI/SNR w raporcie |
| R3 | SW5 na CISZA: `STATUS silence=1`, `TX WICI-SILENCE-01` → `BLOCKED SILENCE`, partner nic; SW5 wyłączony: `TX` z nowym numerem dochodzi; odbiór przy CISZA działa | wszystkie trzy |

Oscyloskop nie może podtrzymywać zasilania płytki (sondy nie na szynach innego źródła); jedno źródło USB naraz.

Po E5 przykleić panel taśmą 3M 4032 (FPC już wpięte, taśma nie zgięta w stronę ekranu).

## 6. Zapis sztuki

Numer sztuki, MAC z `INFO`, typ FRAM z `RDID`, R12 = 1 kΩ (część spoza BOM), zmierzone napięcia i prądy, zrzuty E4 i EXTCOMIN, logi i JSON, zdjęcia płytki i adaptera, odstępstwa.

Następny krok po odbiorze: obraz stacji `l0` ([firmware](../../firmware/README.md#stacja-l0-l0)).
