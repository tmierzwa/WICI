# WICI: płytka nośna stanowiska N1

**Status: projekt. Nie zamówiono ani nie zmontowano żadnej sztuki.**

Płytka nośna zastępuje przewody [stanowiska deweloperskiego](README.md) jedną dwuwarstwową płytką. Na tej płytce montuje się moduły producentów: płytkę MCU, moduł radiowy, FRAM i ekran. Płytka dokłada przyciski, przełącznik CISZA, przycisk trybu przygotowania, diodę alarmu, brzęczyk, wejście pomiaru napięcia i złącze analizatora stanów logicznych. Nie ma własnego toru RF, wzorca częstotliwości ani zasilania. Radio, zegar radia i stabilizatory pochodzą z płytek producentów, więc wnioski ze stanowiska co do toru RF pozostają takie jak w [README](README.md#co-sprawdza-stanowisko-a-co-dopiero-r02). Decyzja i jej granice: [przegląd, F81](../../docs/review.md).

## Jedna płytka, dwa stanowiska

Ta sama płytka służy obu stanowiskom. W danej chwili obsadzone jest tylko jedno z nich.

| | Stanowisko A (TI) | Stanowisko B (ST) |
|---|---|---|
| Ułożenie | nakładka: długie piny złączy Arduino (J1–J4) wchodzą w gniazda Arduino nRF52840-DK | podstawa na dystansach: DevKitC w gniazdach J5/J6, X-NUCLEO-S2868A2 wpięta od góry w gniazda J1–J4 |
| MCU | nRF52840-DK pod płytką | ESP32-S3-DevKitC-1 w J5/J6 |
| Radio | CC1120EM-868-915 w J9/J10 (wewnątrz obrysu Arduino) | X-NUCLEO-S2868A2 nad J1–J4 |
| 3,3 V | z pinu 3V3 złącza Arduino DK (VDD płytki DK, 3,0 V) | ze stabilizatora DevKitC przez zworkę JP1 |
| 5 V (ekran) | z pinu 5V złącza Arduino DK | z pinu 5V DevKitC przez zworkę JP2 |
| Zworki | JP1 i JP2 zdjęte | JP1 i JP2 założone |
| Puste | J5, J6 (DevKitC) | J9, J10 (EM) |

**Nigdy nie obsadzać obu MCU naraz.** Przewody sygnałowe płytki są wspólne dla obu wykonań, więc nRF52840 i ESP32-S3 sterowałyby tymi samymi liniami. To samo dotyczy obu modułów radiowych naraz.

Sygnały radia leżą na tych pozycjach Arduino, których X-NUCLEO-S2868A2 używa z fabrycznie wlutowanymi rezystorami (UM2638, tabele 2–4). Dlatego X-NUCLEO nie wymaga przeróbek, a moduł TI dostaje te same pozycje. Linie, których X-NUCLEO nie używa, obsługują ekran, FRAM i przyciski. Pozycji D5 płytka nie podłącza, bo X-NUCLEO trzyma tam CS swojej pamięci EEPROM z rezystorem podciągającym 100 kΩ.

## Przypisanie sygnałów

Numery GPIO nRF52840 według złączy Arduino nRF52840-DK (instrukcja Nordic, „Arduino signals routing”, i pliki PCA10056 3.0.3); numery GPIO ESP32-S3 według złączy J1/J3 DevKitC-1 (instrukcja Espressif v1.1). Pełna tabela pinów każdego złącza powstanie w `polaczenia.md`, generowanym ze źródła projektu.

| Sygnał | Arduino | nRF52840 (A) | ESP32-S3 (B) | CC1120EM (A) | X-NUCLEO-S2868A2 (B) | Na płytce |
|---|---|---|---|---|---|---|
| SPI_SCK | D3 | P1.04 | GPIO12 | P1.16 SCLK | SCLK (R11) | FRAM, ekran, analizator |
| SPI_MOSI | D11 | P1.13 | GPIO11 | P1.18 SI | SDI | FRAM, ekran, analizator |
| SPI_MISO | D12 | P1.14 | GPIO13 | P1.20 SO | SDO | FRAM, analizator |
| RF_CS | A1 | P0.04 | GPIO10 | P1.14 CSn | CSn (R13) | 10 kΩ do 3,3 V |
| RF_RESET | D7 | P1.08 | GPIO9 | P2.15 RESET_N (L = reset) | SDN (H = wyłączenie) | 100 kΩ do masy |
| RF_GPIO0 | A0 | P0.03 | GPIO14 | P1.10 GPIO0 | GPIO0 (R12) | analizator |
| RF_GPIO1 | A2 | P0.28 | GPIO21 | — (GPIO1 to SO) | GPIO1 | |
| RF_GPIO2 | A3 | P0.29 | GPIO47 | P1.12 GPIO2 | GPIO2 | analizator |
| RF_GPIO3 | A5 | P0.31 | GPIO42 | P2.18 GPIO3 | GPIO3 | |
| FRAM_CS | D9 | P1.11 | GPIO8 | | | FRAM (podciągnięcie na module) |
| LCD_CS | D4 | P1.05 | GPIO7 | | | ekran, aktywny stanem wysokim; 10 kΩ do masy |
| LCD_EXTCOMIN | D6 | P1.07 | GPIO17 | | | ekran; EMD na stałe w stanie wysokim |
| LCD_DISP | D8 | P1.10 | GPIO16 | | | ekran (podciągnięcie na module) |
| LED_ALARM | D10 | P1.12 | GPIO18 | | | dioda przez 1 kΩ |
| BUZZER | D2 | P1.03 | GPIO15 | | | tranzystor i brzęczyk |
| BTN_UP | D0 | P1.01 | GPIO41 | | | GÓRA do masy, 10 kΩ do 3,3 V |
| BTN_DOWN | D1 | P1.02 | GPIO40 | | | DÓŁ |
| BTN_OK | SDA | P0.26 | GPIO39 | | 2,2 kΩ do 3,3 V na X-NUCLEO | OK |
| BTN_BACK | SCL | P0.27 | GPIO2 | | 2,2 kΩ do 3,3 V na X-NUCLEO | WSTECZ |
| SW_CISZA | D13 | P1.15 | GPIO1 | | | przełącznik: masa = cisza |
| BTN_PREP | AREF | P0.02 | GPIO6 | | | przycisk trybu przygotowania |
| VTEST | A4 | P0.30 (AIN6) | GPIO5 (ADC1_CH4) | | | dzielnik 100 kΩ / 20 kΩ z zacisku VTEST |
| (nie podłączony) | D5 | P1.06 | — | | CS EEPROM, 100 kΩ do 3,3 V | |

Wybór pinów ESP32-S3 omija piny konfiguracyjne GPIO0, GPIO3, GPIO45 i GPIO46, USB GPIO19/20, UART0 GPIO43/44, diodę RGB DevKitC (GPIO38 w v1.1, GPIO48 w v1.0) oraz GPIO35–37, które zajmuje pamięć PSRAM w modułach z PSRAM ośmiobitową (N8R8). Dzięki temu płytka przyjmie DevKitC z modułem N8R2 i N8R8.

Na nRF52840-DK żadna z tych pozycji nie jest współdzielona z funkcjami płytki w ustawieniu fabrycznym. Wyjątkiem jest przełącznik TRACE (SW7) w pozycji „Alt.”, który przenosi przyciski na D6/D7. Rezystory podciągające SDA/SCL płytki DK włącza tylko sygnał SHIELD_DETECT ze złącza P5, którego płytka nie dotyka. RESET złącza Arduino nie jest połączony z nRF52840 (zwora SB44 otwarta); płytka nośna go nie używa.

Zmiana wobec okablowania przewodami: SPI przechodzi z D13 na D3, a radio na pozycje X-NUCLEO, więc oprogramowanie dla płytki nośnej używa własnego pliku opisu płytki.

## Mechanika

Obrys 170 × 100 mm. Prawa część płytki ma obrys i otwory Arduino Uno R3. W stanowisku A leży ona nad lewym końcem nRF52840-DK, a reszta płytki wystaje poza płytkę DK w lewo i o około 18 mm poza obie jej krawędzie. Położenia złączy i części DK pochodzą z plików produkcyjnych PCA10056 3.0.3.

- Wycięcie przy prawej krawędzi omija męskie złącze P5 (2 × 3, pozycja ICSP) płytki DK; szczelina w polu Arduino omija męską listwę P20 (1 × 13). Wysokości części DK nie są podane przez Nordic; przed zamówieniem przymierza się wydruk 1:1 do rzeczywistej płytki.
- Wyprowadzenia elementów przewlekanych w polu Arduino przycina się od spodu do ≤1,5 mm, bo pod nimi leży płytka DK.
- Moduł CC1120EM wpina się złączami SFM (Samtec, 2 × 10, 1,27 mm, na spodzie modułu) w listwy męskie 1,27 mm J9/J10 o rozstawie 30,48 mm. Pin 1 obu złączy leży od strony złącza SMA modułu; położenia padów pochodzą z archiwum CADSTAR referencji TI (swrr091).
- Ekran (Adafruit 4694, 63,5 × 55,9 mm) i FRAM (Adafruit 4719) wpina się listwami w gniazda 1 × 9 i mocuje dystansami M2,5 w otworach płytek Adafruit.
- DevKitC leży złączem USB do dolnej krawędzi płytki. Antena modułu ESP32-S3 wystaje nad płytkę nośną; stacja nie używa Wi-Fi ani Bluetooth.
- Stanowisko B stoi na dystansach M3 w czterech narożnikach i czterech otworach Arduino; długie piny J1–J4 wystają wtedy od spodu o około 10 mm.

## Zasilanie

Płytka nie ma stabilizatora. Szyna 3,3 V zasila moduł CC1120EM, FRAM i X-NUCLEO, a szyna 5 V moduł ekranu (ma własny stabilizator 3,3 V i pompę ładunku 5 V). W stanowisku A szyna 3,3 V to VDD płytki DK, czyli 3,0 V; wszystkie moduły pracują przy tym napięciu (CC1120 2,0–3,6 V, MB85RS4MT 1,8–3,6 V, wejście ekranu 3–5 V). Wydajności prądowej pinów 3V3 i 5V płytek DK i DevKitC producenci nie podają; stanowisko pobiera najwięcej przy nadawaniu CC1120 (około 45 mA przy +14 dBm według karty układu). Zworki JP1 i JP2 służą też do pomiaru prądu płytki w stanowisku B.

## Pliki

| Plik | Zawartość |
|---|---|
| `polaczenia.md` | piny każdego złącza i elementu |
| `cad/` | projekt KiCad 10.0.6: schemat, PCB, reguły, lokalne biblioteki |
| `tools/` | generatory schematu i PCB, eksport, kontrole |
| `checks/` | raporty ERC/DRC i dowody |
| `bom.csv` | części z MPN |
| `uruchomienie.md` | montaż i pierwsze włączenie |
| `przed-produkcja.md` | warunki przed zamówieniem |
