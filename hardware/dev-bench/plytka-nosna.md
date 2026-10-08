# WICI: płytka nośna stanowiska N1

**Status: projekt, ERC 0 i DRC 0 (z działającymi regułami projektu, F103). Nie zamawiać przed zamknięciem [listy przed zamówieniem](przed-produkcja.md); nie zmontowano żadnej sztuki.**

**Rola po przeglądzie praktycznym (F99) i rewizja po audycie (F103).** Pilotaż nie wymaga N1: sprzętem pilotażu jest gotowa płytka ESP32-S3 z SX1262 ([stacja pilotażowa](../../docs/spec/elektronika.md#stacja-pilotażowa)). N1 zostaje narzędziem prób stosu, kolejki FRAM, ekranu i obsługi (T1–T3, T8) oraz opcjonalnego porównania z P1. Z tego powodu N1 spełnia te wymagania specyfikacji, które dotyczą każdej stacji i dają się sprawdzić na stanowisku: FRAM taktowana zegarem ≥8 MHz ([zanik zasilania i zapis](../../docs/spec/elektronika.md#zanik-zasilania-i-zapis)), panel zasilany napięciem z zakresu karty (własna przetwornica 5 V, jak w R02) i EXTCOMIN wyłącznie z licznika MCU, z panelem wyłączonym przy jego awarii.

Płytka nośna zastępuje okablowanie przewodami [stanowiska deweloperskiego](README.md) (opis w README stanowiska i w [firmware/README.md](../../firmware/README.md#okablowanie-stanowiska-a)) jedną dwuwarstwową płytką; przewody zostają tylko do prób przed montażem N1. Na tej płytce montuje się moduły producentów: płytkę MCU i moduł radiowy. Pamięć FRAM (U1) i panel ekranu Sharp (w złączu FPC J7) są na samej płytce jako te same układy, które przewiduje [BOM stacji](../../docs/spec/bom-stacji.csv), bez płytek pośrednich dostępnych tylko u jednego sprzedawcy ([F86](../../docs/review.md)). Płytka dokłada przyciski, przełącznik CISZA, przycisk trybu przygotowania, diodę alarmu, brzęczyk, wejście pomiaru napięcia, złącze analizatora stanów logicznych i małą przetwornicę 5 V zasilającą sam panel (U2). Nie ma własnego toru RF, wzorca częstotliwości ani zasilania modułów. Radio, zegar radia i stabilizatory pochodzą z płytek producentów, więc wnioski ze stanowiska co do toru RF pozostają takie jak w [README](README.md#co-sprawdza-stanowisko-a-co-dopiero-r02). Decyzja i jej granice: [przegląd, F81](../../docs/review.md).

## Jedna płytka, dwa stanowiska

Ta sama płytka służy obu stanowiskom. W danej chwili obsadzone jest tylko jedno z nich.

| | Stanowisko A (TI) | Stanowisko B (ST) |
|---|---|---|
| Ułożenie | nakładka: długie piny złączy Arduino (J1–J4) wchodzą w gniazda Arduino nRF52840-DK | podstawa na dystansach: DevKitC w gniazdach J5/J6, X-NUCLEO-S2868A2 wpięta od góry w gniazda J1–J4 |
| MCU | nRF52840-DK pod płytką | ESP32-S3-DevKitC-1 w J5/J6 |
| Radio | CC1120EM-868-915 w J9/J10 (wewnątrz obrysu Arduino) | X-NUCLEO-S2868A2 nad J1–J4 |
| 3,3 V | z pinu 3V3 złącza Arduino DK (VDD płytki DK, 3,0 V); moduł CC1120EM przez zworkę JP3 | ze stabilizatora DevKitC przez zworkę JP1 |
| 5 V (panel ekranu, brzęczyk) | z pinu 5V złącza Arduino DK | z pinu 5V DevKitC przez zworkę JP2 |
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
| FRAM_CS | D9 | P1.11 | GPIO8 | | | FRAM U1, 10 kΩ do 3,3 V (R20), analizator |
| LCD_CS | D4 | P1.05 | GPIO7 | | | SCS panelu, aktywny stanem wysokim; 10 kΩ do masy (R13); analizator |
| LCD_EXTCOMIN | D6 | P1.07 | GPIO17 | | | EXTCOMIN panelu; EXTMODE panelu na stałe do +5V_LCD (VDD panelu) |
| LCD_DISP | D8 | P1.10 | GPIO16 | | | DISP panelu; 10 kΩ do masy (R19) i 100 nF (C7, zalecenie Sharp), więc DISP = L (ekran biały) do startu MCU |
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
- SPI na D3/D11/D12 (nRF52840: P1.04, P1.13, P1.14; Nordic zaleca P1.04 i P1.13 tylko do sygnałów wolnozmiennych ze względu na zakłócenia własnego radia 2,4 GHz, którego stanowisko nie używa; napęd H0H1 dla SCK i MOSI); ESP32-S3 SCK/MOSI z najniższym napędem, który daje czyste zbocza; zegar osobno dla każdego układu: radio 1 MHz, ekran 1 MHz (do 2 MHz po pomiarze), FRAM 8 MHz;
- ekran Sharp: zegar ≤1 MHz (najwyżej 2 MHz: SCLK ≥200 ns w stanie wysokim i niskim), LSB first, CS aktywny stanem wysokim z czasami 3 µs przed i 1 µs po transmisji; DISP w stanie niskim do wyczyszczenia pamięci ekranu; wejścia panelu wymagają VIH ≥2,7 V i VIL ≤VSS + 0,15 V, a zbocza SCLK, SI, SCS i EXTCOMIN ≤50 ns (Sharp LCP-1112041, tabele 7-1 i 6-3-2), więc w stanowisku A logika 3,0 V płytki DK ma tylko 0,3 V zapasu VIH; poziomy i zbocza przy J7 sprawdza oscyloskop przy [uruchomieniu](uruchomienie.md#pomiar-magistrali-oscyloskopem); zbocze DISP wyznacza kondensator 100 nF zalecany przez Sharp (C7), więc nie podlega granicy 50 ns;
- EXTCOMIN tylko z licznika MCU: EXTMODE jest na stałe w stanie wysokim, więc bit VCOM w poleceniach nic nie zmienia; gdy licznik nie ruszy, program zostawia DISP w stanie niskim i zgłasza usterkę;
- FRAM: CY15B104QN albo MB85RS4MT na tym samym footprincie; oprogramowanie rozpoznaje oba po RDID (`src/fram_id.h`); zegar 8 MHz, bo specyfikacja wymaga ≥8 MHz w każdej stacji (seria 256 B ≤0,3 ms);
- CC1120: IOCFG1 zostaje w stanie wysokiej impedancji, bo SO/GPIO1 dzieli linię MISO z FRAM;
- wejścia przycisków, CISZA i przygotowania mają podciągnięcie na płytce, wewnętrzne nie jest potrzebne.

## Mechanika

Obrys 170 × 100 mm. Prawa część płytki ma obrys i otwory Arduino Uno R3. W stanowisku A leży ona nad lewym końcem nRF52840-DK, a reszta płytki wystaje poza płytkę DK w lewo i o około 18 mm poza obie jej krawędzie. Położenia złączy i części DK pochodzą z plików produkcyjnych PCA10056 3.0.3.

- Wycięcie przy prawej krawędzi omija męskie złącze P5 (2 × 3, pozycja ICSP) płytki DK; zapas według rysunku DK wynosi około 0,55 mm od strony J11 i więcej z pozostałych stron. Nad męską listwą P20 (1 × 13) leży pas bez miedzi na warstwie spodniej i bez przelotek, bo końce jej pinów mogą sięgać spodu płytki; ścieżki warstwy wierzchniej oddziela od nich 1,6 mm laminatu. Wysokości części DK nie są podane przez Nordic; przed zamówieniem przymierza się wydruk 1:1 do rzeczywistej płytki.
- Wyprowadzenia elementów przewlekanych w polu Arduino przycina się od spodu do ≤1,5 mm, bo pod nimi leży płytka DK.
- Moduł CC1120EM wpina się złączami SFM (Samtec, 2 × 10, 1,27 mm, na spodzie modułu) w listwy męskie 1,27 mm J9/J10 o rozstawie 30,48 mm. Pin 1 obu złączy leży od strony złącza SMA modułu; położenia padów pochodzą z archiwum CADSTAR referencji TI (swrr091).
- Panel Sharp LS027B7DH01A (62,8 × 42,82 × 1,64 mm, Sharp LCP-1112041) leży ekranem do góry na taśmie piankowej 0,8 mm (3M 4032) w obrysie na warstwie opisu; pod nim nie ma żadnych elementów (generator płytki to sprawdza). Taśma FPC panelu (6,06 mm od krawędzi szkła, styki od spodu) wchodzi płasko w złącze Hirose FH12 J7 ze stykami od dołu; czoło złącza leży 2,3 mm od krawędzi szkła, więc w złączu jest około 3,8 mm taśmy. Według rysunku Sharp (LCP-1112041, rysunek 8-1, widok od tyłu) styk 1 (SCLK) jest od strony ekranu po prawej, dlatego footprint J7 jest obrócony o 180°, a pad 1 leży po prawej. Taśmy nie wolno zginać w stronę polaryzatora ani częściej niż trzy razy; zgięcie tylko 0,8–6 mm od szkła, promień ≥0,45 mm. Położenie złącza wobec długości taśmy sprawdza się przy przymiarce z rzeczywistym panelem.
- FRAM U1 (SOIC-8, 208 mil) jest elementem SMD montowanym razem z pozostałymi; na tym samym footprincie pasuje CY15B104QN-50SXI i MB85RS4MTPF-G-BCERE1, bo oba mają ten sam układ wyprowadzeń (pin 7: HOLD w MB85RS4MT, RESET w CY15B104QN; oba na stałe do 3,3 V).
- DevKitC leży złączem USB do dolnej krawędzi płytki. Antena modułu ESP32-S3 wystaje nad płytkę nośną; stacja nie używa Wi-Fi ani Bluetooth.
- Stanowisko B stoi na dziewięciu dystansach M3 × 12 mm: w czterech narożnikach (H1–H4), przy dolnej krawędzi (H5) i w czterech otworach Arduino (H6–H9); długie piny J1–J4 wystają wtedy od spodu o około 10 mm. W stanowisku A lewą część płytki podpierają H1, H2 i H5; wysokość, przy której płytka leży poziomo na płytce DK, mierzy się przy przymiarce, bo Nordic nie podaje wysokości DK z gniazdami.
- W otworach Arduino śruby M2,5 albo nylonowe M3 z łbem ≤4,4 mm, bo środek otworu leży 3,56 mm od środka najbliższego padu listwy (J4.10 przy H7). Wokół otworów montażowych nie biegną ścieżki w promieniu 3,3 mm (M3) i 2,6 mm (otwory Arduino), więc dystans i łeb leżą na masie albo na laminacie. W otworach Arduino ten promień jest mniejszy niż narożnik metalowego dystansu sześciokątnego M3 (5,5 mm pod klucz, około 3,2 mm), a od spodu najbliżej leżą ścieżki RF_CS przy H6 (3,0 mm od środka otworu) oraz BTN_BACK i LED_ALARM przy H7 (2,8 mm): metalowy dystans mógłby przez uszkodzoną maskę zewrzeć dwie sieci, dlatego w H6–H9 stosuje się dystanse nylonowe.
- JP3 (listwa ze zworką, 8,9 mm) leży przy J11, poza obrysem X-NUCLEO-S2868A2, którego spód w stanowisku B jest około 8,5 mm nad płytką; pod nakładką zostają tylko części niskie (J10, C1, C2, C5, R11, R12, R14, R15, R17) i łby śrub H7–H9.
- Moduł CC1120EM i DevKitC wchodzą w gniazda także obrócone o 180°, co zamienia zasilanie z sygnałami albo masą. Obrysy modułów, kółko w miejscu złącza SMA i napis USB są na warstwie opisu; orientację sprawdza się przed każdym wpięciem.
- Przełączniki nRF52840-DK (SW8 zasilanie, SW9 źródło zasilania nRF, SW10) leżą pod płytką nośną; ustawia się je przed nałożeniem płytki.

## Zasilanie

Płytka nie ma stabilizatora modułów. Szyna 3,3 V zasila FRAM U1, X-NUCLEO i przetwornicę panelu U2, a przez zworkę JP3 moduł CC1120EM (ten moduł nie ma własnego stabilizatora; amperomierz w miejscu JP3 mierzy prąd samego radia). Szyna 5 V z płytki MCU zasila już tylko brzęczyk, żeby impulsy 2 kHz brzęczyka nie szły po szynie radia, a cewka dostała napięcie z zakresu karty (3–5 V szczytowo). W stanowisku A szyna 3,3 V to VDD płytki DK, czyli 3,0 V; układy pracują przy tym napięciu (CC1120 2,0–3,6 V, CY15B104QN i MB85RS4MT 1,8–3,6 V, MCP1640 od 0,65 V po starcie, wejścia logiczne panelu od 2,7 V).

**Zasilanie panelu (+5V_LCD).** Panel wymaga 4,8–5,5 V na VDD i VDDA (LCP-1112041, tabela 7-1). Pin 5V płytki DevKitC jest za diodą Schottky'ego (1N5819HW) i daje około 4,6–4,8 V, a pin 5V płytki DK zależy od portu USB; żadne z nich nie gwarantuje zakresu panelu, także przy prądzie brzęczyka. Dlatego panel ma własną przetwornicę z +3,3 V, jak R02 ([elektronika](../../docs/spec/elektronika.md#zasilanie-stacji), wiersz „Szyna 5 V ekranu”): Microchip MCP1640 (U2, synchroniczna, PFM przy małym obciążeniu, prąd spoczynkowy 19 µA, karta DS20002234D) z cewką 4,7 µH Würth WE-TPC 3816 (L1, z tabeli 5-2 karty), C8 10 µF na wejściu (karta: ≥4,7 µF), C9 10 µF na wyjściu i C4 10 µF przy panelu (karta: ≥10 µF; dwa kondensatory, bo X5R przy 5 V traci część pojemności). Dzielnik R21 1,00 MΩ / R22 309 kΩ: VOUT = VFB · (1 + R21/R22) = 1,21 V · 4,236 = 5,13 V nominalnie; przy VFB 1,175–1,245 V i rezystorach 1% wynik mieści się w 4,90–5,36 V, czyli w zakresie panelu bez strojenia. C10 100 pF równolegle do R21 tłumi szpilki w trybie PFM (karta, 5.4). EN jest na stałe połączony z VIN, więc panel dostaje 5 V około 0,75 ms (miękki start) po pojawieniu się 3,3 V, zanim MCU skończy start; do tego czasu DISP i SCS są ściągnięte do masy, a pozostałe wejścia panelu niesterowane, co odpowiada kolejności włączania z karty Sharp. VDD i VDDA rosną razem (ta sama sieć), jak wymaga karta. EXTMODE łączy się z tą samą siecią. Napięcie J7.7 i tętnienia mierzy się przy uruchomieniu, także przy pracy brzęczyka i nadawaniu.

Wydajności prądowej pinów 3V3 i 5V płytek DK i DevKitC producenci nie podają; z szyny 3,3 V stanowisko pobiera najwięcej przy nadawaniu CC1120 (około 45 mA przy +14 dBm według karty układu), a panel z przetwornicą poniżej 1 mA; z szyny 5 V do około 75 mA przez brzęczyk przy stałym stanie wysokim BUZZER. Razem poniżej 150 mA. Zworki JP1 i JP2 służą też do pomiaru prądu płytki w stanowisku B.

## Rozważone uproszczenia

Przegląd po audycie (2026-10-07; płytka miała wtedy 65 elementów, 28 pozycji BOM, 4,8 m ścieżek i 51 przelotek). Po przejściu na części produkcyjne (F86, 2026-10-08): 62 elementy, 31 pozycji BOM, 4,6 m ścieżek, 59 przelotek, jedna strona montażu, 32 elementy SMD. Po przetwornicy panelu i dzielniku VTEST 0,1% (F103): 69 elementów (w tym 9 otworów), 37 pozycji BOM, 4,7 m ścieżek, 62 przelotki, jedna strona montażu, 39 elementów SMD.

| Możliwość | Decyzja | Powód |
|---|---|---|
| Wewnętrzne rezystory podciągające MCU zamiast R5–R10 | nie | zewnętrzne dają ten sam stan na obu MCU i w czasie resetu; sześć rezystorów 0805 to mały koszt |
| Bezpośrednie połączenie zamiast JP1 i JP2 | nie | zworki chronią przed walką stabilizatorów DK i DevKitC przy pomyłce i służą do pomiaru prądu w stanowisku B |
| Złącze analizatora J11 nad J3/J4 zamiast przy dolnej krawędzi | nie | próba trasowania: ścieżki krótsze tylko o 2,5%, trzy przelotki więcej |
| Dzielnik VTEST 10 kΩ / 2,2 kΩ, R4 10 kΩ (bez wartości 100 kΩ i 20 kΩ w BOM) | nie | dwie pozycje BOM mniej, ale zmienia się skala VTEST (1/5,55 zamiast 1/6) w oprogramowaniu i rośnie prąd przy przepięciu na zacisku |
| Rezystory 33 Ω na SCK zastąpić zworą | nie | sieć SCK ma około 300 mm z odgałęzieniami; rezystory tłumią odbicia przy wejściach panelu, FRAM i radia |
| Płytki Adafruit z ekranem (4694) i FRAM (4719) zamiast gołych układów | nie (F86) | obie płytki są dostępne tylko u Adafruit i jej dystrybutorów, a 4719 nie ma w sprzedaży; stanowisko sprawdza dzięki temu te same układy co stacja, z dwoma źródłami FRAM |
| Przetwornica 5 V panelu na płytce, jak w stacji | tak (F103; wcześniej nie) | pin 5V DevKitC (4,6–4,8 V za diodą) nie gwarantuje 4,8 V panelu; koncentrator „5,1 V” nie zamykał sprawy bez pomiaru pod obciążeniem; MCP1640 z sześcioma elementami biernymi kosztuje około 8 zł |
| Panel na płytce Adafruit 4694 zamiast przetwornicy | nie | płytka 4694 była niedostępna (F86); stanowisko i R02 mają goły panel |
| Dzielnik VTEST z rezystorów 0,1% zamiast 1% | tak (F103) | rezystory 1% dawały do ±1,7% błędu skali przed błędem ADC; 0,1% daje ±0,17%, resztę usuwa kalibracja każdej sztuki |
| Cztery warstwy albo mniejsza płytka | nie | dwie warstwy mieszczą trasowanie; wymiar wyznaczają ekran, przyciski i obrys Arduino |
| `route.sh` kończy się błędem przy niepoprowadzonych połączeniach; `drc.sh` z pełnym zestawem opcji | tak | Freerouting zwraca kod 0 także z niepoprowadzonymi sieciami; jedna komenda DRC zamiast długiej linii w dokumentacji |

## Koszt i dostępność

Ceny netto z DigiKey z 2026-10-08, przy zakupie na cztery stanowiska; ceny w dolarach przeliczone po około 3,65 zł/USD. Koszt PCB to typowa cena wykonawcy, nie oferta. Ceny i stany zmieniają się z tygodnia na tydzień, więc przed zakupem sprawdza się je ponownie.

| Pozycja | Netto na stanowisko | Uwagi |
|---|---:|---|
| Części płytki N1 z [BOM](bom.csv) bez FRAM, z dystansami i taśmą | około 115 zł | najdroższe: listwy TFM J9/J10 (około 21 zł, tylko A), listwy Samtec SSQ J1–J4 (około 14 zł), przełącznik SW5 (11 zł) |
| FRAM U1 CY15B104QN-50SXI (albo MB85RS4MTPF) | około 70 zł (19 USD) | DigiKey ponad 1700 i 1400 sztuk |
| PCB N1 (5 sztuk 170 × 100 mm, JLCPCB, z wysyłką) | około 30 zł | PCBWay około 65 zł; płytka większa niż 100 × 100 mm wypada z najtańszej oferty |
| Montaż 39 elementów SMD u wykonawcy (opcja) | około 65–75 zł | ręcznie da się polutować wszystko poza złączem J7 (raster 0,5 mm), które wymaga wprawy |
| Panel Sharp LS027B7DH01A | około 86 zł (23,6 USD) | DigiKey ponad 2700 sztuk |
| Moduły stanowiska A: nRF52840-DK, połowa zestawu CC1120EMK-868-915 | około 440 zł | zestaw (dwa moduły) kosztuje około 512 zł |
| Moduły stanowiska B: ESP32-S3-DevKitC-1-N8R8, X-NUCLEO-S2868A2 | około 196 zł | |
| **Razem stanowisko A / B** z płytką lutowaną ręcznie | **około 740 / 500 zł** | brutto około 910 / 615 zł; przy płytkach Adafruit było około 815 / 570 zł; przetwornica panelu i rezystory 0,1% dodały około 10 zł |

Koszt stanowiska wyznaczają płytki rozwojowe producentów (zestaw CC1120EMK i nRF52840-DK), a nie płytka nośna. Przejście z płytek Adafruit na gołe układy obniżyło koszt o około 80 zł na stanowisko. Rozważono jeszcze dwie oszczędności i obu nie przyjęto. Tańsze listwy 1,27 mm innych producentów zamiast Samtec TFM odpadają, bo Samtec podaje TFM jako jedyny partner gniazd SFM modułu, a różnica wynosi kilka złotych. Tańszy przełącznik dźwigienkowy wymaga innego footprintu, a SW5 jest dostępny od ręki.

Dostępność w dniu sprawdzenia:
- Części płytki są w magazynach dystrybutorów; FRAM ma dwóch producentów na jednym footprincie, a panel, złącze FH12 i listwy SSQ są aktywne u producentów (terminy fabryczne 2–28 tygodni).
- **ESP32-S3-DevKitC-1-N8R2 i -N8 są wycofane** (DigiKey: „no longer manufactured”); kupuje się -N8R8 (płytka N1 i obraz `bench-b` omijają GPIO35–37 zajęte przez PSRAM). DigiKey i TME mają 0 sztuk, DigiKey spodziewa się dostawy w czerwcu 2027; dostępna od ręki była w Botland. Płytki DevKitC kupuje się od razu na wszystkie stanowiska B.
- Zestaw CC1120EMK-868-915: w DigiKey 3 sztuki, sklep TI pokazuje stan dopiero po zalogowaniu; dwa stanowiska A potrzebują jednego zestawu (dwa moduły), ale zapasu u dystrybutorów prawie nie ma. Kupuje się go z wyprzedzeniem.
- FRAM: oba warianty w magazynie, ale z terminami fabrycznymi 26–30 tygodni; kupuje się od razu na wszystkie płytki.
- Panel LS027B7DH01A ma jednego producenta (Sharp), termin fabryczny 28 tygodni; DigiKey ma ponad 2700 sztuk. Płytka Adafruit 4694 z tym panelem jest prawie niedostępna (Adafruit, Pimoroni i The Pi Hut bez stanu, DigiKey 26 sztuk), dlatego N1 używa gołego panelu.
- Taśma 3M 4032 w małych rolkach nie jest w ofercie typowych dystrybutorów elektroniki (DigiKey: rolka 2" × 5 yd za około 76 USD); wystarczy dowolna dwustronna taśma piankowa 0,8 mm.
- Kondensator 10 µF: CL21A106KAYNNNE (61 tygodni) zastąpiono tą samą częścią w innym opakowaniu, CL21A106KAYNNNG (DigiKey ponad 5000 sztuk); zamiennik GRM21BR61E106MA73L. Większość innych 10 µF 25 V X5R 0805 też ma zerowy stan ([notatki dla wykonawcy](fabrication/N1/FAB-NOTES.txt) dopuszczają zamienniki o tych parametrach).
- Przyciski Omron B3F i B32 sprzedaje się teraz pod marką Aratas, z tymi samymi numerami części.
- Listwy Samtec SSQ z wyprowadzeniami 10 mm mają jednego producenta; innego o tej długości wyprowadzeń nie znaleziono. To narzędzie stanowiska A, nie część stacji.

## Źródła

Geometrię złączy i otworów wzięto z plików producentów pobranych 2026-10-07, dane FRAM z kart pobranych 2026-10-08, a dane panelu i przetwornicy z kart pobranych 2026-10-08 przy rewizji F103. Pliki nie są w repozytorium; sumy pozwalają sprawdzić, czy ponownie pobrany plik jest tym samym wydaniem.

| Źródło | Wersja | Użyte do | SHA-256 |
|---|---|---|---|
| [nRF52840 DK, pliki sprzętowe](https://nsscprodmedia.blob.core.windows.net/prod/software-and-other-downloads/dev-kits/nrf52840-dk/nrf52840-development-kit---hardware-files-3_0_3.zip) | PCA10056 3.0.3 | położenie złączy Arduino, P5, P20 i otworów DK; trasy sygnałów Arduino | `3be2fb25452f0fa937501480427e4fe9f23297e032c62ed42f09f97e1e4fb115` |
| [TI swrr091](https://www.ti.com/lit/zip/swrr091) | archiwum CADSTAR CC1120EM | pady złączy P1/P2 modułu CC1120EM i ich rozstaw | `3ea3e14840243610e6a5ca4d91642527b8e070414645da3150aa2cd6951e7ef2` |
| [E-Switch 100SP1T1B4M2QE](https://configured-product-images.s3.amazonaws.com/2D/specs/100SP1T1B4M2QE.pdf) | rysunek T111597 G | footprint przełącznika SW5 | `ba9332d56c244a7daf2a28c2d491322329ecef21b3e136386dd9064561097e3e` |
| [ESP32-S3-DevKitC-1, rysunek](https://dl.espressif.com/dl/schematics/esp_idf/DXF_ESP32-S3-DevKitC-1_V1.1_20220429.pdf) i [instrukcja v1.1](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html) | v1.1, 2022-04-29 | rozstaw złączy J1/J3 i numery GPIO | `9d092400db6f677b491926a07455bec7874054ec65ef6ccbddb6aa7ed3892a17` (rysunek) |
| [Sharp LCP-1112041 (karta LS027B7DH01A)](https://d7rh5s3nxmpy4.cloudfront.net/CMP7377/files/LS027B7DH01A_06Aug12_Spec_LCP-1112041.pdf) | pierwsze wydanie 2012-08-06 | karta dokładnego MPN z BOM: wyprowadzenia (tabela 4-1), zasilanie i poziomy wejść (tabela 7-1), czasy i zbocza (tabela 6-3-2), kolejność włączania, kondensatory (rysunek 9-1), obrys panelu i taśmy FPC (rysunek 8-1), zalecane złącze; wcześniej używana karta LS027B7DH01 bez „A” (LCP-2110015A) podaje te same wartości użyte w projekcie | `ec5b7f8f0a85a69a9b4fa495a7c6adb3ec794dd686afffc03df3dd22539f01ac` |
| [Microchip DS20002234D (karta MCP1640)](https://ww1.microchip.com/downloads/en/DeviceDoc/20002234D.pdf) | D, 2010–2015 | wyprowadzenia SOT-23-6, VFB 1,175–1,245 V, dzielnik (równanie 5-1), kondensatory (tabela 5-1), cewki (tabela 5-2), kondensator 100 pF przy RTOP | `9bc12658806b9639e6b32419f0ac103e08b2170449fa7da4402be427c7abc7db` |
| Infineon 002-20526 (karta CY15B104QN) | Rev. *D, 2023-10-27 | wyprowadzenia, RDID, wersje napięciowe | `68fc2f1d81df21b228cc917860437f5900d24409a87a7db3ec385682fad729b8` |
| RAMXEED DS501-00053-3v1-E (karta MB85RS4MT) | 3v1 | wyprowadzenia, RDID | `d5ab01acbc711b15978e6a6003ded1b7452135b9fa369f361e21e130f81526fd` |
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
