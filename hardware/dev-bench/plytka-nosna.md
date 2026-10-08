# WICI: płytka nośna stanowiska N1

**Status: projekt, ERC 0 i DRC 0. Nie zamawiać przed zamknięciem [listy przed zamówieniem](przed-produkcja.md); nie zmontowano żadnej sztuki.**

Płytka nośna zastępuje okablowanie przewodami [stanowiska deweloperskiego](README.md) (opis w README stanowiska i w [firmware/README.md](../../firmware/README.md#okablowanie-stanowiska-a)) jedną dwuwarstwową płytką; przewody zostają tylko do prób przed montażem N1. Na tej płytce montuje się moduły producentów: płytkę MCU, moduł radiowy, FRAM i ekran. Płytka dokłada przyciski, przełącznik CISZA, przycisk trybu przygotowania, diodę alarmu, brzęczyk, wejście pomiaru napięcia i złącze analizatora stanów logicznych. Nie ma własnego toru RF, wzorca częstotliwości ani zasilania. Radio, zegar radia i stabilizatory pochodzą z płytek producentów, więc wnioski ze stanowiska co do toru RF pozostają takie jak w [README](README.md#co-sprawdza-stanowisko-a-co-dopiero-r02). Decyzja i jej granice: [przegląd, F81](../../docs/review.md).

## Jedna płytka, dwa stanowiska

Ta sama płytka służy obu stanowiskom. W danej chwili obsadzone jest tylko jedno z nich.

| | Stanowisko A (TI) | Stanowisko B (ST) |
|---|---|---|
| Ułożenie | nakładka: długie piny złączy Arduino (J1–J4) wchodzą w gniazda Arduino nRF52840-DK | podstawa na dystansach: DevKitC w gniazdach J5/J6, X-NUCLEO-S2868A2 wpięta od góry w gniazda J1–J4 |
| MCU | nRF52840-DK pod płytką | ESP32-S3-DevKitC-1 w J5/J6 |
| Radio | CC1120EM-868-915 w J9/J10 (wewnątrz obrysu Arduino) | X-NUCLEO-S2868A2 nad J1–J4 |
| 3,3 V | z pinu 3V3 złącza Arduino DK (VDD płytki DK, 3,0 V); moduł CC1120EM przez zworkę JP3 | ze stabilizatora DevKitC przez zworkę JP1 |
| 5 V (ekran) | z pinu 5V złącza Arduino DK | z pinu 5V DevKitC przez zworkę JP2 |
| Zworki | JP3 założona, JP1 i JP2 zdjęte | JP1 i JP2 założone, JP3 bez znaczenia (J10 pusty) |
| Puste | J5, J6 (DevKitC) | J9, J10 (EM) |

**Nigdy nie obsadzać obu MCU naraz.** Sieci sygnałowe płytki są wspólne dla obu stanowisk, więc nRF52840 i ESP32-S3 sterowałyby tymi samymi liniami. Tak samo nie wolno obsadzać naraz obu modułów radiowych.

Sygnały radia leżą na tych pozycjach Arduino, których X-NUCLEO-S2868A2 używa z fabrycznie wlutowanymi rezystorami (UM2638, tabele 2–4). Dlatego X-NUCLEO nie wymaga przeróbek, a moduł TI dostaje te same pozycje. Linie, których X-NUCLEO nie używa, obsługują ekran, FRAM i przyciski. Pozycji D5 płytka nie podłącza, bo X-NUCLEO trzyma tam CS swojej pamięci EEPROM z rezystorem podciągającym 100 kΩ.

## Przypisanie sygnałów

Numery GPIO nRF52840 według złączy Arduino nRF52840-DK (instrukcja Nordic, „Arduino signals routing”, i pliki PCA10056 3.0.3); numery GPIO ESP32-S3 według złączy J1/J3 DevKitC-1 (instrukcja Espressif v1.1). Wersje i sumy plików: [źródła](#źródła). Pełna tabela pinów każdego złącza jest w [połączeniach](polaczenia.md), generowanych ze źródła projektu.

| Sygnał | Arduino | nRF52840 (A) | ESP32-S3 (B) | CC1120EM (A) | X-NUCLEO-S2868A2 (B) | Na płytce |
|---|---|---|---|---|---|---|
| SPI_SCK | D3 | P1.04 | GPIO12 | P1.16 SCLK | SCLK (R11) | FRAM, ekran, analizator; 33 Ω szeregowo przy D3 (R17) i przy GPIO12 (R18) |
| SPI_MOSI | D11 | P1.13 | GPIO11 | P1.18 SI | SDI | FRAM, ekran, analizator |
| SPI_MISO | D12 | P1.14 | GPIO13 | P1.20 SO | SDO | FRAM, analizator |
| RF_CS | A1 | P0.04 | GPIO10 | P1.14 CSn | CSn (R13) | 10 kΩ do 3,3 V, analizator |
| RF_RESET | D7 | P1.08 | GPIO9 | P2.15 RESET_N (L = reset) | SDN (H = wyłączenie) | 10 kΩ do masy |
| RF_GPIO0 | A0 | P0.03 | GPIO14 | P1.10 GPIO0 | GPIO0 (R12) | analizator |
| RF_GPIO1 | A2 | P0.28 | GPIO21 | — (GPIO1 to SO) | GPIO1 | |
| RF_GPIO2 | A3 | P0.29 | GPIO4 | P1.12 GPIO2 | GPIO2 | analizator |
| RF_GPIO3 | A5 | P0.31 | GPIO42 | P2.18 GPIO3 | GPIO3 | |
| FRAM_CS | D9 | P1.11 | GPIO8 | | | FRAM (podciągnięcie na module), analizator |
| LCD_CS | D4 | P1.05 | GPIO7 | | | ekran, aktywny stanem wysokim; 10 kΩ do masy; analizator |
| LCD_EXTCOMIN | D6 | P1.07 | GPIO17 | | | ekran; EMD na stałe w stanie wysokim |
| LCD_DISP | D8 | P1.10 | GPIO16 | | | ekran; 10 kΩ do 3,3 V na module i 2,2 kΩ do masy (R19), więc DISP = L do startu MCU |
| LED_ALARM | D10 | P1.12 | GPIO18 | | | dioda przez 1 kΩ |
| BUZZER | D2 | P1.03 | GPIO15 | | | tranzystor i brzęczyk z +5V |
| BTN_UP | D0 | P1.01 | GPIO41 | | | GÓRA do masy, 10 kΩ do 3,3 V |
| BTN_DOWN | D1 | P1.02 | GPIO40 | | | DÓŁ |
| BTN_OK | SDA | P0.26 | GPIO39 | | 2,2 kΩ do 3,3 V na X-NUCLEO | OK |
| BTN_BACK | SCL | P0.27 | GPIO2 | | 2,2 kΩ do 3,3 V na X-NUCLEO | WSTECZ |
| SW_CISZA | D13 | P1.15 | GPIO1 | | | przełącznik przez 1 kΩ (R16): masa = cisza |
| BTN_PREP | AREF | P0.02 | GPIO6 | | | przycisk trybu przygotowania |
| VTEST | A4 | P0.30 (AIN6) | GPIO5 (ADC1_CH4) | | | dzielnik 100 kΩ / 20 kΩ z zacisku VTEST, diody BAT54S do masy i 3,3 V |
| (nie podłączony) | D5 | P1.06 | — | | CS EEPROM, 100 kΩ do 3,3 V | |

Wybór pinów ESP32-S3 omija piny konfiguracyjne GPIO0, GPIO3, GPIO45 i GPIO46, USB GPIO19/20, UART0 GPIO43/44, diodę RGB DevKitC (GPIO38 w v1.1, GPIO48 w v1.0) oraz GPIO35–37, które zajmuje pamięć PSRAM w modułach z PSRAM ośmiobitową (N8R8). Dzięki temu płytka przyjmie DevKitC z modułem N8R2 i N8R8. GPIO47 i GPIO48 też nie są używane, bo w modułach WROOM-2 z 1,8 V (np. N16R8V) mają poziom 1,8 V; płytka przyjęłaby więc i takie moduły, ale obraz `bench-b` zakłada pamięć flash quad SPI (moduły N8, N8R2, N8R8).

Na nRF52840-DK żadna z tych pozycji nie jest współdzielona z funkcjami płytki w ustawieniu fabrycznym. Wyjątkiem jest przełącznik TRACE (SW7) w pozycji „Alt.”, który przenosi przyciski na D6/D7. Rezystory podciągające SDA/SCL płytki DK włącza tylko sygnał SHIELD_DETECT ze złącza P5, którego płytka nie dotyka. RESET złącza Arduino nie jest połączony z nRF52840 (zwora SB44 otwarta); płytka nośna go nie używa.

Zmiana wobec okablowania przewodami: SPI przechodzi z D13 na D3, a radio na pozycje X-NUCLEO, więc oprogramowanie dla płytki nośnej używa własnego pliku opisu płytki. Obraz okablowania przewodami na N1 zwiera wyjście SCK (D13) przez przełącznik CISZA do masy; R16 ogranicza ten prąd do 3 mA, ale obrazu nie należy tak uruchamiać ([uruchomienie](uruchomienie.md#oprogramowanie)).

Wymagania dla pliku opisu płytki N1 wynikające z układu:
- SPI na D3/D11/D12 (nRF52840: P1.04, P1.13, P1.14; Nordic zaleca P1.04 i P1.13 tylko do sygnałów wolnozmiennych ze względu na zakłócenia własnego radia 2,4 GHz, którego stanowisko nie używa; zegar 1 MHz, do 2 MHz po próbie, napęd H0H1 dla SCK i MOSI); ESP32-S3 SCK/MOSI z najniższym napędem, który daje czyste zbocza;
- ekran Sharp: zegar ≤1 MHz (najwyżej 2 MHz), LSB first, CS aktywny stanem wysokim z czasami 3 µs przed i 1 µs po transmisji; DISP w stanie niskim do wyczyszczenia pamięci ekranu;
- CC1120: IOCFG1 zostaje w stanie wysokiej impedancji, bo SO/GPIO1 dzieli linię MISO z FRAM;
- wejścia przycisków, CISZA i przygotowania mają podciągnięcie na płytce, wewnętrzne nie jest potrzebne.

## Mechanika

Obrys 170 × 100 mm. Prawa część płytki ma obrys i otwory Arduino Uno R3. W stanowisku A leży ona nad lewym końcem nRF52840-DK, a reszta płytki wystaje poza płytkę DK w lewo i o około 18 mm poza obie jej krawędzie. Położenia złączy i części DK pochodzą z plików produkcyjnych PCA10056 3.0.3.

- Wycięcie przy prawej krawędzi omija męskie złącze P5 (2 × 3, pozycja ICSP) płytki DK; zapas według rysunku DK wynosi około 0,55 mm od strony J11 i więcej z pozostałych stron. Nad męską listwą P20 (1 × 13) leży pas bez miedzi na warstwie spodniej i bez przelotek, bo końce jej pinów mogą sięgać spodu płytki; ścieżki warstwy wierzchniej oddziela od nich 1,6 mm laminatu. Wysokości części DK nie są podane przez Nordic; przed zamówieniem przymierza się wydruk 1:1 do rzeczywistej płytki.
- Wyprowadzenia elementów przewlekanych w polu Arduino przycina się od spodu do ≤1,5 mm, bo pod nimi leży płytka DK.
- Moduł CC1120EM wpina się złączami SFM (Samtec, 2 × 10, 1,27 mm, na spodzie modułu) w listwy męskie 1,27 mm J9/J10 o rozstawie 30,48 mm. Pin 1 obu złączy leży od strony złącza SMA modułu; położenia padów pochodzą z archiwum CADSTAR referencji TI (swrr091).
- Ekran (Adafruit 4694, 63,5 × 55,9 mm) i FRAM (Adafruit 4719) wpina się listwami w gniazda 1 × 9 i mocuje dystansami M2,5 w otworach płytek Adafruit. Ekran leży szkłem do góry, a szkło jest po stronie płytki modułu przeciwnej do elementów, więc piny J7 od lewej to VIN 3V3 GND CLK DI CS EMD DISP EIN; rysunek montażowy Adafruit pokazuje stronę elementów i odwraca tę kolejność (F83). Moduł jest symetryczny względem złącza i otworów, więc obrócony też wchodzi: nazwy pinów są na warstwie opisu przy J7 i J8 i sprawdza się je przed wpięciem.
- DevKitC leży złączem USB do dolnej krawędzi płytki. Antena modułu ESP32-S3 wystaje nad płytkę nośną; stacja nie używa Wi-Fi ani Bluetooth.
- Stanowisko B stoi na dziewięciu dystansach M3 × 12 mm: w czterech narożnikach (H1–H4), przy dolnej krawędzi (H5) i w czterech otworach Arduino (H6–H9); długie piny J1–J4 wystają wtedy od spodu o około 10 mm. W stanowisku A lewą część płytki podpierają H1, H2 i H5; wysokość, przy której płytka leży poziomo na płytce DK, mierzy się przy przymiarce, bo Nordic nie podaje wysokości DK z gniazdami.
- W otworach Arduino śruby M2,5 albo nylonowe M3 z łbem ≤4,4 mm, bo środek otworu leży 3,56 mm od środka najbliższego padu listwy (J4.10 przy H7). Wokół otworów montażowych nie biegną ścieżki w promieniu 3,3 mm (M3), 3,0 mm (M2,5) i 2,6 mm (otwory Arduino), więc dystans i łeb leżą na masie albo na laminacie. W otworach Arduino ten promień jest mniejszy niż narożnik metalowego dystansu sześciokątnego M3 (5,5 mm pod klucz, około 3,2 mm), a od spodu najbliżej leżą ścieżki RF_CS przy H6 i BTN_BACK przy H7 (2,8 mm od środka otworu): dlatego w H6–H9 stosuje się dystanse nylonowe.
- JP3 (listwa ze zworką, 8,9 mm) leży przy J11, poza obrysem X-NUCLEO-S2868A2, którego spód w stanowisku B jest około 8,5 mm nad płytką; pod nakładką zostają tylko części niskie (J10, C1, C2, C5, R11, R12, R14, R15, R17) i łby śrub H7–H9.
- Moduł CC1120EM i DevKitC wchodzą w gniazda także obrócone o 180°, co zamienia zasilanie z sygnałami albo masą. Obrysy modułów, kółko w miejscu złącza SMA i napis USB są na warstwie opisu; orientację sprawdza się przed każdym wpięciem.
- Przełączniki nRF52840-DK (SW8 zasilanie, SW9 źródło zasilania nRF, SW10) leżą pod płytką nośną; ustawia się je przed nałożeniem płytki.

## Zasilanie

Płytka nie ma stabilizatora. Szyna 3,3 V zasila FRAM i X-NUCLEO, a przez zworkę JP3 moduł CC1120EM (ten moduł nie ma własnego stabilizatora; amperomierz w miejscu JP3 mierzy prąd samego radia). Szyna 5 V zasila moduł ekranu (ma własny stabilizator 3,3 V i pompę ładunku 5 V) i brzęczyk, żeby impulsy 2 kHz brzęczyka nie szły po szynie radia, a cewka dostała napięcie z zakresu karty (3–5 V szczytowo). W stanowisku A szyna 3,3 V to VDD płytki DK, czyli 3,0 V; wszystkie moduły pracują przy tym napięciu (CC1120 2,0–3,6 V, MB85RS4MT 1,8–3,6 V, wejście ekranu 3–5 V). Wydajności prądowej pinów 3V3 i 5V płytek DK i DevKitC producenci nie podają; z szyny 3,3 V stanowisko pobiera najwięcej przy nadawaniu CC1120 (około 45 mA przy +14 dBm według karty układu), z szyny 5 V do około 75 mA przez brzęczyk przy stałym stanie wysokim BUZZER; razem z ekranem i FRAM poniżej 150 mA. Zworki JP1 i JP2 służą też do pomiaru prądu płytki w stanowisku B.

## Rozważone uproszczenia

Przegląd po audycie (2026-10-07; płytka: 65 elementów, 28 pozycji BOM, 4,8 m ścieżek, 51 przelotek, jedna strona montażu; po ponownym trasowaniu w F83 48 przelotek).

| Możliwość | Decyzja | Powód |
|---|---|---|
| Wewnętrzne rezystory podciągające MCU zamiast R5–R10 | nie | zewnętrzne dają ten sam stan na obu MCU i w czasie resetu; sześć rezystorów 0805 to mały koszt |
| Bezpośrednie połączenie zamiast JP1 i JP2 | nie | zworki chronią przed walką stabilizatorów DK i DevKitC przy pomyłce i służą do pomiaru prądu w stanowisku B |
| Złącze analizatora J11 nad J3/J4 zamiast przy dolnej krawędzi | nie | próba trasowania: ścieżki krótsze tylko o 2,5%, trzy przelotki więcej |
| Dzielnik VTEST 10 kΩ / 2,2 kΩ, R4 10 kΩ (bez wartości 100 kΩ i 20 kΩ w BOM) | nie | dwie pozycje BOM mniej, ale zmienia się skala VTEST (1/5,55 zamiast 1/6) w oprogramowaniu i rośnie prąd przy przepięciu na zacisku |
| Rezystory 33 Ω na SCK zastąpić zworą | nie | sieć SCK ma około 265 mm z odgałęzieniami; rezystory łagodzą zbocza ESP32 przy wejściach 74HC4050 bez przerzutnika Schmitta |
| Cztery warstwy albo mniejsza płytka | nie | dwie warstwy mieszczą trasowanie; wymiar wyznaczają ekran, przyciski i obrys Arduino |
| `route.sh` kończy się błędem przy niepoprowadzonych połączeniach; `drc.sh` z pełnym zestawem opcji | tak | Freerouting zwraca kod 0 także z niepoprowadzonymi sieciami; jedna komenda DRC zamiast długiej linii w dokumentacji |

## Koszt i dostępność

Ceny netto w PLN z DigiKey.pl z 2026-10-08, przy zakupie na cztery płytki; koszt PCB to typowa cena wykonawcy, nie oferta. Ceny i stany zmieniają się z tygodnia na tydzień, więc przed zakupem sprawdza się je ponownie.

| Pozycja | Netto na stanowisko | Uwagi |
|---|---:|---|
| Części płytki N1 z [BOM](bom.csv) z dystansami | około 100 | najdroższe: listwy TFM J9/J10 (około 21, tylko A), gniazda J5/J6 (10), przełącznik SW5 (11) |
| PCB N1 (5 sztuk 170 × 100 mm, JLCPCB, z wysyłką) | około 30 | PCBWay około 65; płytka większa niż 100 × 100 mm wypada z najtańszej oferty |
| Montaż 27 elementów SMD u wykonawcy (opcja) | około 60 | przy kilku sztukach taniej lutować ręcznie (0805, SOT-23, SOD-123) |
| Moduły stanowiska A: nRF52840-DK, połowa CC1120EMK-868-915, Adafruit 4694, Adafruit 4719 | około 685 | zestaw CC1120EMK (dwa moduły) kosztuje około 512 |
| Moduły stanowiska B: ESP32-S3-DevKitC-1-N8R8, X-NUCLEO-S2868A2, Adafruit 4694, Adafruit 4719 | około 440 | |
| **Razem stanowisko A / B** z płytką lutowaną ręcznie | **około 815 / 570** | brutto około 1000 / 700; adapter BOOST-CCEMADAPTER (około 160) niepotrzebny przy N1 |

Koszt stanowiska wyznaczają moduły producentów (zestaw CC1120EMK, nRF52840-DK i ekran na każdym stanowisku), a nie płytka nośna. W BOM płytki rozważono jeszcze dwie oszczędności i obu nie przyjęto. Tańsze listwy 1,27 mm innych producentów zamiast Samtec TFM odpadają, bo Samtec podaje TFM jako jedyny partner gniazd SFM modułu, a różnica wynosi kilka złotych. Tańszy przełącznik dźwigienkowy wymaga innego footprintu i ponownego trasowania, a SW5 jest dostępny od ręki.

Dostępność w dniu sprawdzenia:
- **Adafruit 4719 (FRAM 4 Mbit) jest niedostępna**: brak w sklepie Adafruit i w DigiKey (zapowiedź dostawy 2027-01-18). Zamiennik 4718 ma 2 Mbit, a oprogramowanie i specyfikacja wymagają 4 Mbit. Do czasu dostawy można użyć układu MB85RS4MT albo Infineon CY15B104Q (oprogramowanie rozpoznaje oba; ten sam układ wyprowadzeń) w obudowie SOP-8/SOIC-8 208 mil na płytce przejściowej SOP-8/DIP wpiętej przewodami w J8: VIN (J8.1) do VDD układu, GND, SCK, MISO (SO), MOSI (SI), CS z rezystorem 10 kΩ do VIN (płytka N1 nie ma podciągnięcia FRAM_CS) oraz WP i HOLD do VIN. Ta przeróbka nie jest sprawdzona na sprzęcie.
- **ESP32-S3-DevKitC-1-N8R2 jest wycofana**; płytka N1 i obraz `bench-b` przyjmują wersje N8 i N8R8, dostępne u dystrybutorów.
- Ekran Adafruit 4694: brak w sklepie Adafruit, w DigiKey kilkadziesiąt sztuk; zestaw CC1120EMK-868-915: w DigiKey kilka sztuk, potem około 12 tygodni.
- Kondensator 10 µF CL21A106KAYNNNE: brak w DigiKey; wystarczy każdy 10 µF 25 V X5R 0805 ([notatki dla wykonawcy](fabrication/N1/FAB-NOTES.txt) dopuszczają zamienniki).

## Źródła

Geometrię złączy i otworów wzięto z plików producentów pobranych 2026-10-07. Pliki nie są w repozytorium; sumy pozwalają sprawdzić, czy ponownie pobrany plik jest tym samym wydaniem.

| Źródło | Wersja | Użyte do | SHA-256 |
|---|---|---|---|
| [nRF52840 DK, pliki sprzętowe](https://nsscprodmedia.blob.core.windows.net/prod/software-and-other-downloads/dev-kits/nrf52840-dk/nrf52840-development-kit---hardware-files-3_0_3.zip) | PCA10056 3.0.3 | położenie złączy Arduino, P5, P20 i otworów DK; trasy sygnałów Arduino | `3be2fb25452f0fa937501480427e4fe9f23297e032c62ed42f09f97e1e4fb115` |
| [TI swrr091](https://www.ti.com/lit/zip/swrr091) | archiwum CADSTAR CC1120EM | pady złączy P1/P2 modułu CC1120EM i ich rozstaw | `3ea3e14840243610e6a5ca4d91642527b8e070414645da3150aa2cd6951e7ef2` |
| [E-Switch 100SP1T1B4M2QE](https://configured-product-images.s3.amazonaws.com/2D/specs/100SP1T1B4M2QE.pdf) | rysunek T111597 G | footprint przełącznika SW5 | `ba9332d56c244a7daf2a28c2d491322329ecef21b3e136386dd9064561097e3e` |
| [ESP32-S3-DevKitC-1, rysunek](https://dl.espressif.com/dl/schematics/esp_idf/DXF_ESP32-S3-DevKitC-1_V1.1_20220429.pdf) i [instrukcja v1.1](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html) | v1.1, 2022-04-29 | rozstaw złączy J1/J3 i numery GPIO | `9d092400db6f677b491926a07455bec7874054ec65ef6ccbddb6aa7ed3892a17` (rysunek) |
| [ST UM2638](https://www.st.com/resource/en/user_manual/um2638-getting-started-with-the-xnucleos2868a2-sub1-ghz-868-mhz-rf-expansion-board-based-on-s2lp-radio-for-stm32-nucleo-stmicroelectronics.pdf) | wydanie pobrane 2026-10-07 | domyślne pozycje sygnałów X-NUCLEO-S2868A2 (tabele 2–4) | `3d1a722d5723f3eca6f2eee71312bd004d5eea39b49f20b27b2949f571b5dbd1` |

## Pliki

| Plik | Zawartość |
|---|---|
| [połączenia](polaczenia.md) | piny każdego złącza i elementu |
| [schemat](schemat.pdf) | schemat w PDF, eksport z `cad/` |
| `cad/` | projekt KiCad 10.0.6: schemat, PCB, reguły, lokalne biblioteki |
| `tools/` | generatory schematu i PCB, eksport, kontrole |
| `checks/` | raporty ERC/DRC, [zapis odtworzenia](checks/odtworzenie.md), [zgodność z oprogramowaniem](checks/zgodnosc-firmware.md) i dowody |
| [BOM](bom.csv) | części z MPN |
| [pliki produkcyjne](fabrication/N1/README.md) | Gerber, wiercenia, pozycje, rysunek montażowy, wydruk 1:1 |
| [uruchomienie](uruchomienie.md) | montaż, pierwsze włączenie i wzór zapisu sztuki |
| [obsługa](obsluga.md) | konfiguracja A i B, zasady, elementy płytki, pomiar prądu, typowe problemy |
| [przed zamówieniem](przed-produkcja.md) | warunki przed zamówieniem i odtworzenie |
