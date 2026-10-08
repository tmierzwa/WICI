# WICI R02: architektura płytki stacji

**Wstrzymane do decyzji po pilotażu (przegląd praktyczny 2026-10-08, F99):** pilotaż używa stacji z gotowej płytki MCU z układem LoRa SX1262 ([koncepcja 08](../../docs/concept/08-plan-weryfikacji-i-decyzje.html)).

**Status: 2026-10-08, przed schematem. Nie zamawiać.** Dokument opisuje bloki R02, sygnały między nimi i budżet pinów obu wykonań. Porównuje też dwa możliwe podziały na płytki (krok 1 [kolejności prac](README.md#kolejność-prac)). Wszystko tutaj wynika z wymagań, a nie z wyników prób, więc nie czeka na T3–T5. Rzeczy zależne od prób są wymienione na końcu.

Źródła: [elektronika](../../docs/spec/elektronika.md) (zasilanie i wymagania R02), [radio](../../docs/spec/radio.md#dwa-wykonania), [oprogramowanie](../../docs/spec/oprogramowanie.md#ekran-i-przyciski-stacji), przypisanie sygnałów stanowiska N1 ([płytka nośna](../dev-bench/plytka-nosna.md), `firmware/src/board_bench_n1.h` i `board_bench_b.h`). Projekt bloku zasilania jest w [zasilaniu](zasilanie.md), obudowa w [obudowie](obudowa.md), a tor RF i stos warstw w [torze RF](tor-rf.md).

## Bloki

```text
                 ┌──────────────── zasilanie (wspólne dla A i B) ────────────────┐
 4 × AA ─────────┤ 1 Ω, Schottky ─┐                                              │
 12 V (IP67) ────┤ bezpiecznik, TVS, S12 (OVP, zatrzask UV) ─┴─ VSYS ─ przetwornica 3V3 ─┼─ 3V3
 przycisk zasil. ┤ sterownik wyłącznika (soft-latch) ── ON, INT, KILL                    │
                 │ komparator VSYS 3,4 V ── VSYS_FAIL; dzielniki ADC z kluczami          │
                 └───────────────────────────────────────────────────────────────┘
 3V3 ─┬─ MCU (A: nRF52840, B: ESP32-S3FN8) ─── USB-C (ESD; VBUS: A do PHY, B tylko wykrycie)
      ├─ radio (A: CC1120, B: S2-LP) + TCXO ─ dopasowanie, filtr ─ (SAW, przełącznik: D10) ─ ESD ─ SMA
      ├─ FRAM 4 Mbit SPI
      ├─ przetwornica 5 V z odłączeniem wyjścia ─ panel Sharp (FPC) i podświetlenie
      ├─ przyciski GÓRA, DÓŁ, OK, WSTECZ, CISZA, przygotowanie; dioda alarmu; brzęczyk
      └─ opcja: RTC z podtrzymaniem; pola programowania (SWD albo UART)
```

Wspólne dla obu wykonań są zasilanie, FRAM, ekran z szyną 5 V, przyciski, dioda, brzęczyk, USB-C, złącza zewnętrzne i obudowa. Różnią się MCU z jego zegarami i programowaniem oraz radio z TCXO i torem RF.

## Sygnały MCU

Liczby dotyczą pinów GPIO MCU. USB D+/D−, SWD i piny kwarców mają osobne wyprowadzenia. Kolumna „N1” wskazuje, czy sygnał jest już sprawdzany na stanowisku.

| Grupa | Sygnały | Liczba | Wymaganie na pin | N1 |
|---|---|---|---|---|
| SPI wspólne | SCK, MOSI, MISO | 3 | piny sprzętowego SPI; SCK przez rezystor szeregowy przy MCU | tak |
| Radio | CS, RESET (A) albo SDN (B), GPIO0, GPIO2 (przerwanie), GPIO3 | 4–5 | przerwanie na pinie z obsługą zdarzeń; GPIO3 opcjonalnie | tak |
| FRAM | CS | 1 | podciągnięcie 10 kΩ do 3V3, więc FRAM jest odłączona w czasie startu | tak |
| Ekran | CS, DISP, EXTCOMIN | 3 | EXTCOMIN z licznika sprzętowego (A: RTC2 przez PPI i GPIOTE, B: MCPWM), nie z programu | tak |
| Szyna 5 V i podświetlenie | 5V_EN, FL_PWM | 2 | 5V_EN z rezystorem do masy (szyna wyłączona do startu programu); FL_PWM sprzętowy PWM | nie |
| Przyciski | GÓRA, DÓŁ, OK, WSTECZ, CISZA, PRZYGOTOWANIE | 6 | wejścia z wybudzaniem z uśpienia; CISZA przez 1 kΩ | tak |
| Sygnalizacja | LED_ALARM, BUZZER | 2 | BUZZER sprzętowy PWM 2 kHz | tak |
| Wyłącznik główny | INT (wejście), KILL (wyjście) | 2 | KILL z podciągnięciem do 3V3, MCU ściąga go otwartym drenem; KILL musi być wysoki 400 ms po włączeniu ([zasilanie](zasilanie.md#suma-diodowa-i-sterownik-wyłącznika)); 2 s przytrzymania odmierza program z INT | nie |
| Zanik zasilania | VSYS_FAIL | 1 | przerwanie o najwyższym priorytecie, z wybudzaniem | nie |
| Przetwornica 3V3 | PWM/SYNC | 1 | stan wysoki na czas nadawania (Burst Mode obsługuje zwykle poniżej 50 mA) | nie |
| Pomiar | V_AA, V_12 (analogowe), DIV_EN (1–2) | 3–4 | wejścia ADC: A tylko P0.02–P0.05 i P0.28–P0.31 (AIN0–AIN7); B ADC1, GPIO1–GPIO10 | częściowo (VTEST) |
| Zatrzask UV 12 V | UV_STAN (wejście), UV_KASUJ (wyjście przez izolację poziomów) | 2 | `odlaczone_12v` na ekranie, kasowanie przyciskiem OK tylko przy V12 ≥12,4 V | nie |
| USB | VBUS_DET | 0 (A), 1 (B) | B: przez ≥100 kΩ albo bufor z Ioff ([elektronika](../../docs/spec/elektronika.md#zasilanie-stacji)) | nie |
| RTC (opcja) | SDA, SCL, INT | 3 | I²C | nie |
| Razem | | 34–37 | | |

**Wykonanie A (nRF52840, aQFN73):** 48 GPIO. Odpadają P0.00 i P0.01 (kwarc 32,768 kHz) oraz P0.18 (reset). Zostaje 45 pinów, czyli około 10 pinów zapasu. P0.09 i P0.10 są domyślnie pinami NFC i wymagają przełączenia w UICR. Sygnały szybkie (SCK, MOSI) prowadzi się z pinów, których Nordic nie ogranicza do sygnałów wolnozmiennych. Na N1 SCK leży na P1.04, a to pin zalecany tylko do sygnałów wolnozmiennych ([firmware](../../firmware/README.md)); w R02 SCK przenosi się na pin bez tego ograniczenia według specyfikacji produktu nRF52840 (rozdział o pinach blisko radia), a przypisanie sprawdza się przy schemacie.

**Wykonanie B (ESP32-S3FN8, QFN56):** 45 GPIO (GPIO0–21 i GPIO26–48). Odpadają:
- GPIO26–32: flash w obudowie; GPIO33–37 zostają wolne (zajęłaby je dopiero PSRAM octal w ESP32-S3R8/R16V);
- GPIO19 i GPIO20: USB;
- GPIO43 i GPIO44: UART0 do programowania i konsoli serwisowej.

Zostaje 34 pinów, w tym cztery piny konfiguracji startu (GPIO0, GPIO3, GPIO45, GPIO46), które wolno użyć tylko z ustalonym stanem w czasie resetu. Przy RTC i 37 sygnałach brakuje jednego pinu. Dlatego w B RTC (opcja) albo GPIO3 radia odpada, albo wolne sygnały (DIV_EN, UV_STAN, 5V_EN) idą na ekspander I²C; decyduje schemat. Wykonanie B nie ma pinów zapasowych, A ma około 8.

## Stany zasilania

| Stan | Co jest zasilane | Kto przełącza |
|---|---|---|
| Wyłączona | tylko sterownik wyłącznika z sumy diodowej oraz prądy upływu: dzielniki odłączone, S12 i przetwornica 3V3 wyłączone; cel ≤20 µA z każdego źródła | przycisk zasilania |
| Start | 3V3; 5 V wyłączone do chwili, gdy program wyczyści pamięć ekranu (DISP niski) | sterownik wyłącznika (ON), potem MCU |
| Praca | 3V3, 5 V, radio w RX; podświetlenie tylko po naciśnięciu przycisku i do upływu czasu | MCU |
| Zanik | przerwanie VSYS_FAIL: MCU gasi podświetlenie, diodę i brzęczyk, kończy transakcję FRAM i nadawanie w ≥2 ms podtrzymania | komparator VSYS |
| Wyłączanie | INT po 2 s naciśnięcia: `wylaczanie`, koniec zapisu i TX, `mozna_wyjac`, KILL; bez odpowiedzi MCU sterownik wyłącza po ≥5 s | sterownik wyłącznika i MCU |
| Odłączone 12 V | zatrzask UV otwiera S12 przy 11,5 V; stacja pracuje z ogniw i pokazuje `odlaczone_12v` | komparator z zatrzaskiem |

Każdy pin sterujący (EN, SDN, RESET, KILL, 5V_EN, DIV_EN) ma rezystor ustalający stan bezpieczny, zanim MCU skonfiguruje piny. To lekcja F01 z R01.3 ([lekcje](lekcje.md#zasilanie-i-usb)). Bilans prądu dla każdego stanu z tej tabeli liczy się przed layoutem.

## Podział na płytki

Krok 1 kolejności prac wymaga wyboru jednego z dwóch podziałów.

| Kryterium | 1: dwie płytki A i B ze wspólnymi arkuszami schematu | 2: płyta bazowa i moduł MCU+RF dla każdego wykonania |
|---|---|---|
| Stos warstw | cała płytka 4 warstwy w stosie referencji RF; dwie płytki, bo stosy referencji TI i ST mogą się różnić ([tor RF](tor-rf.md)) | 4 warstwy tylko na małym module; płyta bazowa 2 warstwy |
| Zmiana MCU po T3 (D14) | nowy projekt całej płytki A | nowy tylko moduł A; płyta bazowa, obudowa i zasilanie bez zmian |
| Zmiana toru RF po T4 (D10: SAW, przełącznik) | nowa rewizja całej płytki | nowa rewizja modułu |
| Dwóch dostawców (W14) | dwie pełne płytki do kwalifikacji | jedna płyta bazowa, dwa moduły na jednym złączu; w T7 wymienia się moduł |
| Złącze między płytkami | brak | 25–40 styków: SPI, CS, przerwania, przyciski, zasilanie 3V3 i VSYS; dodatkowa część, przejście ESD i miejsce na wysokość |
| Ścieżki SPI do ekranu i FRAM | krótkie, na jednej płytce | przez złącze; FRAM można zostawić na module, przy MCU |
| Koszt prototypu | dwie płytki 4-warstwowe w pełnym rozmiarze panelu (około 200 × 120 mm, [obudowa](obudowa.md#płyta-bazowa-obrys-i-ograniczenia)) | płyta 2-warstwowa 200 × 120 mm i dwa małe moduły 4-warstwowe; niższy |
| Ryzyko | mniej części, mniej połączeń | złącze w torze zasilania i sygnałów; więcej plików do utrzymania |

**Decyzja: podział 2** (autor, 2026-10-08). Dwie z trzech otwartych decyzji (D14 i D10) zmieniają tylko MCU i tor RF. W podziale 2 ich wynik nie przerabia zasilania, panelu, złączy ani obudowy, więc te części mogą powstać teraz. Kwalifikacja drugiego dostawcy sprowadza się do wymiany modułu w tej samej płycie. Panel dla dłoni w rękawicach wymaga płytki około 200 × 120 mm, a tak duża płytka jest tania tylko jako dwuwarstwowa. Złącze płyta–moduł to typowe złącze płytka–płytka o rastrze 1,27 mm albo dwie listwy 2,54 mm. Zasilanie idzie przez kilka styków równolegle, a linie od przycisków przez filtr RC i ESD na płycie bazowej, przy przyciskach. Dokumenty [zasilania](zasilanie.md) i [obudowy](obudowa.md) traktują płytę bazową jako osobny blok.

## Ustalone teraz

- **FRAM:** CY15B104QN-50SXI albo MB85RS4MTPF-G-BCERE1 w SOIC-8 208 mil, na wspólnym footprincie. Oba są w sprzedaży, oprogramowanie rozpoznaje oba, a N1 je montuje ([F86](../../docs/review.md)). Pin 7 (HOLD albo RESET) i WP podłącza się na stałe do 3V3, CS ma podciągnięcie 10 kΩ.
- **Złącze ekranu Sharp:** Hirose FH12-10S-0.5SH ze stykami od dołu, na taśmę panelu LS027B7DH01A, jak na N1. Kondensatory przy złączu według karty Sharp. Wybór samego ekranu (D15) czeka na próbę czytelności w −20 °C.
- **Wykonanie B:** ESP32-S3FN8 (8 MB flash w obudowie na dwa gniazda obrazu po 3 MiB, bez PSRAM i bez zewnętrznej pamięci QSPI; wcześniej ESP32-S3FH4R2 z 4 MB, za małą na gniazda, F105). Gdyby D14 wymagało PSRAM: ESP32-S3R2 z zewnętrzną flash QSPI 8 MiB. USB przez USB-OTG z TinyUSB, VBUS tylko do wykrycia hosta.
- **Programowanie:** A przez SWD (pola Tag-Connect TC2030). B przez UART0 (GPIO43/44) z polami testowymi oraz przez USB w trybie pobierania z ROM. Oba złącza są niedostępne bez otwarcia obudowy.
- **Sygnały i ich stan przy starcie:** według tabel powyżej.

## Czeka na próby

| Co | Próba albo decyzja | Wpływ na R02 |
|---|---|---|
| MCU wykonania A (nRF52840 albo większy) | T3, D14 | moduł A albo cała płytka A (podział 1) |
| Filtr SAW, przełącznik RF, filtr harmonicznych | T4, D10 | tor RF obu wykonań |
| Ekran (Sharp albo zamiennik) i podświetlenie | D15, T6 (czytelność w −20 °C) | złącze ekranu, okno obudowy |
| Pobór w lekkim uśpieniu ESP32-S3 z włączonym odbiornikiem | T3 i pomiar na N1 | wybór B, budżet energii W23 |
| Wynik N1: napięcie panelu, zbocza SPI, rozpoznanie FRAM | uruchomienie N1 | przypisanie sygnałów i rezystory szeregowe |
