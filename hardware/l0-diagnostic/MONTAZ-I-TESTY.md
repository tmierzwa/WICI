# WICI L0: montaż, uruchomienie i próby

Dotyczy jednej sztuki: N1 (SMD zmontowane w JLCPCB) + ESP32-S3-DevKitC-1-N8R8 + Wio SX1262 + Sharp LS027B7DH01A, program diagnostyczny `l0-0.5`. Dokumenty nadrzędne: [połączenia MCU](reference/polaczenia-MCU-L0.csv), [połączenia N1](../dev-bench/polaczenia.md), [instrukcja programu](README.md). Tam, gdzie [uruchomienie N1](../dev-bench/uruchomienie.md) (stanowiska A/B) mówi co innego, obowiązuje ten dokument.

Etapy są ułożone tak, żeby każdy błąd ujawnił się tam, gdzie jego usunięcie jest najtańsze. Nie przechodzić do następnego etapu przed zaliczeniem poprzedniego.

## 0. Przed lutowaniem

1. **Oględziny SMD pod mikroskopem:** mostki na J7 (raster 0,5 mm) i U2 (SOT-23-6); kropki pinu 1 U1–U4 zgodne z opisem; Q1, D3 (SOT-23), D2 (pasek katody). U1 to MB85RS4MT (montaż JLC); CY15B104QN jest dopuszczonym zamiennikiem. Wady SMD reklamować u producenta przed lutowaniem THT, ze zdjęciami.
2. **Szyny (na padach):** JP1.1 (+3V3) – J11.1 (GND): bez zwarcia, wskazanie rośnie (C13 100 µF); C9 (+5V_LCD) – GND ≈ 1,3 MΩ (dzielnik R21 + R22).
3. **Przymiarka 1:1 na płytce bez SMD:** DevKitC w otworach J5/J6 (pin 1 od strony anteny, gniazdo USB w stronę napisu USB na płytce), panel w obrysie z opisu, taśma FPC sięga J7 bez naprężenia przy krawędzi szkła; przyciski z nasadkami, SW5 i J12 w otworach. Wynik zapisać.
4. **Wgranie DevKitC poza płytką** (rozdział 4, kroki 1–3). Oddziela problemy USB i narzędzi od problemów montażu, a fabryczny program nie steruje wyprowadzeniami na N1. Bez peryferiów oczekiwane: `INFO l0-0.5 … 0 …`, `FRAM_ID unknown …`, `ERR radio_begin …`; odpowiedź na `INFO` może się opóźnić o około 10 s (program szuka radia, zob. diagnoza w rozdziale 4).

## 1. N1

1. **R12: 10 kΩ → 1 kΩ** (0805, 1%), jako pierwsza czynność, dopóki THT nie utrudnia dostępu. Kontrola na padach: J5.15 (RF_RESET) – GND ≈ 1,0 kΩ.
2. **THT**, od najniższych: SW1–SW6, D1 (katoda = płaski bok i kwadratowy pad 1, do masy), BZ1 („+” na padzie 1), SW5, J11, JP1, JP2, J12, na końcu J5/J6 (na wpiętym DevKitC albo na listwie, żeby gniazda stały pionowo i w osi). Pad J6.22 ma pełne połączenie z polem masy: grot o większej pojemności cieplnej.
    - SW5 (SPDT, wyprowadzenia w linii) da się wlutować obrócony o 180°; wtedy położenie CISZA jest odwrócone wobec opisu. Kontrola: w położeniu CISZA J6.4 – GND ≈ 1 kΩ (R16), w położeniu PRACA brak połączenia.
    - Nie obsadzać J1–J4, J9/J10 i JP3. To złącza stanowisk A/B; J9/J10 leżą na RF_CS, RF_RESET i SPI, wspólnych z Wio.
3. **Zworki** JP1 i JP2 założone (JP1: 3V3 DevKitC → +3V3 N1; JP2: 5 V dla brzęczyka).
4. **Dystanse** M3 × 12 mm w H1–H5. W H6–H9 tylko nakrętki nylonowe albo nic: pady nieobsadzonych J1–J4 są połączone z sieciami, a środek H7 leży 3,6 mm od padu J4.10.

## 2. Adapter Wio

Przyporządkowanie sygnałów Wio do GPIO XIAO ESP32S3 potwierdzone na sprzęcie programem R0 (`hardware/radio-pair/src/main.cpp`): SCK GPIO7 (D8), MISO GPIO8 (D9), MOSI GPIO9 (D10), NSS GPIO41, DIO1 GPIO39, NRST GPIO42, BUSY GPIO40, RXEN GPIO38. TCXO 1,8 V zasila DIO3, tor nadawania przełącza DIO2.

1. Tabela niżej jest zgodna ze schematem Seeed „Wio-SX1262 for XIAO V1.0” (KiCad 8): J1 i J2 to listwy 1 × 7, raster 2,54 mm; J1.6, J1.7 i J2.7 niepodłączone. Na module R1 10 kΩ podciąga RST do +3V3; RF_SW1 (RXEN) nie ma rezystora do masy. Płytka w innej wersji: porównać z jej schematem przed lutowaniem. Kontrola bez schematu: ciągłość J2.6, J2.5, J2.4 do D8, D9, D10 na krawędzi XIAO (przy połączonym B2B).
2. XIAO zdjąć ze złącza B2B (J3 na Wio) równomiernie, bez podważania jednego końca; XIAO zachować. J2.1 (VIN) nie podłączać. Dioda i przycisk na Wio są połączone tylko z J3, po odłączeniu XIAO nie działają.
3. Przy Wio: 100 nF i 10 µF między 3V3 a GND, 10 kΩ z RXEN do GND. J2.3 (+3V3) z JP1.1 przez POWER_BREAK (listwa 1 × 2 ze zworką), J2.2 (GND) z J11.1.
4. Przyłączenie do N1 od spodu płytki, na wyprowadzeniach gniazd J5/J6 i listwy JP1. Przewody ≤ 6 cm, linie SPI skręcone z przewodem masy albo taśma z masą co drugą żyłą; bez pętli i odgałęzień. SCK i MOSI biegną także do FRAM (8 MHz) i ekranu, więc długość przewodów adaptera wpływa na całą magistralę.
5. Antena w gnieździe u.FL (IPEX) przed pierwszym zasileniem, zatrzaśnięta prostopadle, przewód odciążony.
6. **Nie zasilać płytki ze zdjętą zworką POWER_BREAK.** Wyjścia MCU (NSS i NRST w stanie wysokim) zasilałyby wtedy Wio przez diody zabezpieczające wejść. Prąd Wio mierzy się amperomierzem wpiętym w miejsce zworki.

| Sygnał | Wio | Punkt N1 | GPIO DevKitC |
|---|---|---|---:|
| SCK | J2.6 | J5.18 (SPI_SCK_DEVKIT, przed R18) | 12 |
| MOSI | J2.4 | J5.17 | 11 |
| MISO | J2.5 | J5.19 | 13 |
| NSS | J1.4 | J5.16 (RF_CS, R11 10 kΩ do +3V3) | 10 |
| NRST | J1.3 | J5.15 (R12 1 kΩ do GND) | 9 |
| BUSY | J1.2 | J5.20 | 14 |
| DIO1 | J1.1 | J6.18 | 21 |
| RXEN | J1.5 | J6.6 (10 kΩ do GND przy Wio) | 42 |
| +3V3 | J2.3 | JP1.1 przez POWER_BREAK | |
| GND | J2.2 | J11.1 | |
| VIN | J2.1 | nie podłączać | |

## 3. Kontrola przed zasilaniem

Bez DevKitC i panelu, POWER_BREAK założony.

| Pomiar | Oczekiwane | Odchylenie oznacza |
|---|---|---|
| Każdy pad Wio – jego punkt N1 | 0 Ω | przerwę albo pomyłkę pinu |
| Linie SPI parami; NSS–NRST; BUSY–DIO1 | brak połączenia | mostek na adapterze |
| J5.15 – GND | ≈ 1 kΩ | ≈ 10 kΩ: R12 niewymieniony |
| J6.6 – GND | ≈ 10 kΩ | brak rezystora RXEN |
| J5.16 – JP1.1 | ≤ 10 kΩ (R11) | |
| Wio J2.3 – JP1.1 | 0 Ω | POWER_BREAK |
| JP1.1 – GND | bez zwarcia | |
| Wio J2.1 (VIN) – cokolwiek na N1 | brak połączenia | |
| J7, sąsiednie piny parami | połączone tylko 6–7–8 (+5V_LCD) oraz 9–10 z uchwytami (GND) | mostek na J7 |

## 4. Pierwsze zasilanie i program

Zasilanie wyłącznie przez gniazdo **USB** DevKitC (natywne USB/OTG, nie UART), przewodem z liniami danych, przez miernik prądu USB. Port UART nie ma konsoli tego obrazu. Jedno źródło zasilania naraz; źródła AA i 12 V odłączone.

1. Narzędzia: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`. Obraz z paczki (`images/l0-full.bin` pod adres 0x0) albo kompilacja `pio run` w `hardware/l0-diagnostic`.
2. Kopia fabryczna i wgranie: `.venv/bin/python -m esptool --chip esp32s3 --port PORT read_flash 0 0x800000 backups/l0-factory-<nr>.bin`, następnie `shasum -a 256 -c SHA256SUMS.txt` i `write_flash 0x0 images/l0-full.bin`. Bez `erase_flash`. Brak portu: przytrzymać BOOT, nacisnąć RESET. Nazwa portu (`/dev/cu.usbmodem…`, na Linuksie `/dev/ttyACM…`) może się zmienić po każdym resecie.
3. Konsola: `.venv/bin/pio device monitor --port PORT --baud 115200`. Komunikaty startowe zwykle giną przed otwarciem portu: od razu `INFO`, `STATUS`, `RDID`. Konsolę zamknąć przed uruchomieniem skryptów.
4. DevKitC na N1, bez panelu. Pomiary według tabeli niżej.
5. `INFO` ma zwrócić `INFO l0-0.5 <MAC> 1 <reset> <boot_id> 869.525 125 7 5 0 1.8`. Pole 3 = `1`: radio, FRAM, timer ekranu i timer brzęczyka gotowe. Pole 4 (przyczyna resetu): `1` po zasileniu i po RESET; inne wartości zaraz po wgraniu programu przez USB są normalne. `RDID`: `FRAM_ID MB85RS4MT 047F49…` albo `FRAM_ID CY15B104QN 7F7F7F7F7F7FC22C…`. MAC zapisać jako identyfikator sztuki.
6. Panel, przy odłączonym zasilaniu: FPC stykami w dół do oporu, klapka zamknięta. Panelu **nie** przyklejać przed zaliczeniem E5 (klej akrylowy; zdjęcie grozi pęknięciem szkła).

**Pomiary w kroku 4:**

| Punkt | Oczekiwane |
|---|---|
| Prąd z USB | zapisać; ciągle > 300 mA albo nagrzewanie się elementu: odłączyć |
| JP1.1 (+3V3) | 3,2–3,4 V; ≥ 3,0 V w każdym stanie pracy |
| C9 (+5V_LCD) | 4,90–5,36 V (dopuszczalne 4,8–5,5 V) |
| Prąd Wio (amperomierz w POWER_BREAK), odbiór | kilka mA (Rx Boosted + TCXO); zapisać |
| J6.6 (RXEN) w odbiorze | ≈ 3,3 V |

Prąd nadawania trwa tyle co pakiet (dziesiątki ms) i multimetr go nie uchwyci: rezystor 1 Ω w miejscu POWER_BREAK i oscyloskop.

### Diagnoza

| Objaw | Przyczyna, co sprawdzić |
|---|---|
| Brak portu | gniazdo UART zamiast USB; przewód bez linii danych; BOOT + RESET |
| Port pojawia się i znika cyklicznie; pole 4 = `9` | brownout: zwarcie albo spadek +3V3 przy starcie radia; prąd z USB, C13, adapter |
| Pole 4 = `4`–`7` | wyjątek albo watchdog: zapis konsoli zaraz po resecie |
| Odpowiedzi dopiero po około 10 s, potem `ERR radio_begin -2` | RadioLib dziesięć razy resetuje układ i nie odczytuje tekstu wersji: przerwa lub pomyłka pinu w adapterze, MISO/MOSI zamienione, Wio bez 3V3, NRST trzymany nisko, BUSY stale w stanie wysokim |
| `radio_begin -705` | BUSY nie opada po poleceniu: przewód BUSY, zasilanie Wio, oscylator TCXO |
| `radio_begin -706` / `-707` | układ odrzucił polecenie albo nie wykonał go (najczęściej kalibracja przy niestartującym TCXO): napięcie 3V3 na Wio przy starcie, odsprzęganie |
| `FRAM_ID unknown FFFF…`, `ERR fram_id_unsupported` | CS nie dochodzi do U1: U3.1 (wyjście nadzorcy) ma być w stanie niskim przy 3,3 V, U4.4 ma odwzorowywać J5.12 (FRAM_CS); orientacja U3/U4 |
| `FRAM_ID … 0000…` | MISO zwarte do masy albo U1 bez zasilania (U1.8) |
| `FRAM_ID` zmienny między kolejnymi `RDID` | dwa układy sterują MISO: J5.16 (NSS radia) ma być w stanie wysokim poza transakcją radia |
| `TX -5` | brak DIO1: RadioLib czeka na TxDone, odpytując DIO1 |
| Nadawanie działa, odbiór słaby albo tylko w jedną stronę | RXEN: J6.6 w stanie wysokim w odbiorze, niskim w nadawaniu |
| `ERR cooldown` | wymagany odstęp 13 czasów pakietu; to nie usterka |
| Ekran pusty przy `ext=1` | FPC odwrócona albo niedociśnięta, mostki na J7, J7.5 (DISP) ma być w stanie wysokim po starcie, +5V_LCD |
| Obraz blednie albo „pływa” | EXTCOMIN: na J7.4 ma być 1 Hz, wypełnienie około 50% (`ext=1` w `STATUS` to tylko stan timera) |
| Obraz poszarpany albo przesunięty | integralność SCK/MOSI: długość przewodów adaptera, masa |
| `inputs` ≠ `00` w spoczynku (SW5 w położeniu PRACA) | mostek albo uszkodzony przycisk; bity: 0 GÓRA, 1 DÓŁ, 2 OK, 3 WSTECZ, 4 CISZA, 5 PREP |
| Brzęczyk milczy | zworka JP2, Q1 i D2, biegunowość BZ1 |

Podejrzenie modułu: najpierw zamiana na moduł z drugiego kompletu (Wio sprawdzone wcześniej w R0, drugi DevKitC). Zapasowy panel tylko w ostateczności (termin dostawy 26–30 tygodni).

## 5. Próby

Pełny opis poleceń: [instrukcja programu L0](README.md#kolejność-prób-po-montażu). **FRAMTEST, GUARD i MIX niszczą zawartość FRAM**, dlatego retencję (E3) wykonuje się przed E4 i E6. Partner: XIAO z Wio z obrazem R0 `pair-0.4`, wcześniej sprawdzony z drugim zestawem R0; anteny założone, odległość 2–3 m. Zachować wszystkie logi i pliki JSON z `results/`. Pole `physical_acceptance=false` w JSON jest zamierzone: oględziny i przebiegi z oscyloskopu ocenia się osobno.

| Próba | Wykonanie | Warunek zaliczenia |
|---|---|---|
| E1 | 10 restartów (RESET i odłączenie USB), za każdym razem `INFO` i `STATUS` | pole 3 = `1`, brak `ERR`, nowy `boot_id`, pole 4 ≠ `9` |
| E2 | napięcia i prądy z rozdziału 4 w spoczynku, w odbiorze i przy nadawaniu (`TX` do partnera) | wartości w zakresach, bez resetów i nagrzewania |
| E3 | `tools/diagnose.py --port PORT --fram-write 12345678`; zasilanie odłączone ≥ 60 s; `--fram-verify 12345678` | zapis: 5 × `FRAM_PASS <n> 0 <crc> <crc>` (zero błędów, sumy CRC równe) i `FRAM_DONE … WRITE`; po zaniku zasilania `FRAM_PASS 4 0 …` i `FRAM_DONE … VERIFY` |
| E4 | `GUARD ERASE`; oscyloskop: CH1 +3V3 (JP1.1), CH2 CS **za bramką** (U1.1), CH3 wyjście nadzorcy (U3.1); wyzwalanie zboczem opadającym CH1 przy ≈ 3,0 V, tryb pojedynczy, podstawa czasu obejmująca spadek poniżej 1,8 V (zacząć od 2 ms/dz.); odłączyć USB po stronie DevKitC | CH3 przechodzi w stan wysoki przy ≈ 2,7 V, a CH2 w stan wysoki, zanim CH1 spadnie do 1,8 V; zrzut ekranu do raportu |
| E5 | `LCD 0` … `LCD 4`; `PAUSE 10000` z sondą na J7.4; każde wejście (`INPUT xx`, bez eliminacji drgań styków, kilka wpisów na naciśnięcie jest normalne); `LED 1/0`, `BUZZ 1/0` | plansze bez błędów pikseli; EXTCOMIN 1 Hz także w pauzie; 6 wejść, LED, brzęczyk 2048 Hz |
| E6 | `tools/diagnose.py --port PORT_L0 --mixed --peer PORT_R0` (15 min); sondy na SCK i liniach CS | `MIX_DONE` z 0 błędów, ≥ 900 cykli, liczba plansz równa liczbie cykli, największy odstęp ≤ 1000 ms; 100/100 pakietów; ekran poprawny |
| R1/R2 | po restarcie obu urządzeń: `tools/radio_test.py --a PORT_L0 --b PORT_R0 --version-a l0-0.5 --version-b pair-0.4 --count 100` | 100/100 w obie strony, treść zgodna; RSSI i SNR w raporcie |
| R3 | SW5 w położeniu CISZA: `STATUS` pokazuje `silence=1`, `TX WICI-SILENCE-01` zwraca `BLOCKED SILENCE`, partner nic nie odbiera; SW5 w położeniu PRACA: `TX` z nowym numerem dociera; odbiór przy CISZA działa | wszystkie trzy warunki |

Oscyloskop nie może podtrzymywać zasilania płytki: sondy nie na szynach innego źródła, masa tylko przez sondy.

Po E5 przykleić panel taśmą 3M 4032 (FPC już wpięta; taśmy FPC nie zginać w stronę ekranu).

## 6. Zapis sztuki

Numer sztuki, MAC z `INFO`, typ FRAM z `RDID`, R12 = 1 kΩ (część spoza BOM), zmierzone napięcia i prądy, zrzuty E4 i EXTCOMIN, logi i JSON, zdjęcia płytki i adaptera, rozbieżności z tą instrukcją.

Następny krok po odbiorze: obraz stacji `l0` ([firmware](../../firmware/README.md#stacja-l0-l0)).
