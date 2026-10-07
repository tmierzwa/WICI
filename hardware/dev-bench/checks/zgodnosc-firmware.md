# WICI: zgodność płytki nośnej N1 z oprogramowaniem

Stan: 2026-10-07. Płytka N1 według `tools/design.py` (commit 562d689), oprogramowanie według `firmware/` w commicie a3b821f (środowisko PlatformIO `bench-a`, plik opisu płytki `src/board_bench_a.h`).

**Wynik: oprogramowanie nie obsługuje jeszcze płytki N1.** Jedyny plik opisu płytki dotyczy stanowiska A z okablowaniem przewodami. Stanowisko B (ESP32-S3 z S2-LP) nie ma żadnego oprogramowania. Ustalenia wspólne dla obu wersji (rejestry radia, protokół, ekran) są zgodne.

## Przypisanie pinów nRF52840

| Sygnał | `board_bench_a.h` (przewody) | N1 | Zgodne |
|---|---|---|---|
| SPI SCK | P1.15 (D13), domyślne `SPI` | P1.04 (D3) | nie |
| SPI MOSI | P1.13 (D11) | P1.13 (D11) | tak |
| SPI MISO | P1.14 (D12) | P1.14 (D12) | tak |
| CS radia | P1.12 (D10) | P0.04 (A1) | nie |
| RESET radia | P1.10 (D8) | P1.08 (D7), 10 kΩ do masy | nie |
| GPIO0 radia | P1.03 (D2) | P0.03 (A0) | nie |
| GPIO2 radia | P1.04 (D3) | P0.29 (A3) | nie |
| GPIO3 radia | — | P0.31 (A5) | brak w oprogramowaniu |
| CS FRAM | P1.11 (D9) | P1.11 (D9) | tak |
| CS ekranu | P1.05 (D4) | P1.05 (D4) | tak |
| EXTCOMIN | P1.06 (D5) | P1.07 (D6) | nie |
| DISP ekranu | nie sterowany (podciągnięcie modułu) | P1.10 (D8), 2,2 kΩ do masy | nie: na N1 ekran jest wyłączony, dopóki program nie poda stanu wysokiego |
| Przyciski GÓRA, DÓŁ, OK, WSTECZ | BUTTON1–4 płytki DK (P0.11, P0.12, P0.24, P0.25) | P1.01, P1.02, P0.26, P0.27 | nie (przyciski DK nadal działają, ale nie są panelem) |
| CISZA | polecenie `SILENCE` | przełącznik, P1.15 (D13) przez 1 kΩ | brak w oprogramowaniu |
| Tryb przygotowania | polecenie `PREP` z potwierdzeniem przyciskiem OK | przycisk, P0.02 (AREF) | brak w oprogramowaniu |
| Dioda alarmu | — (diody DK LED1–4) | P1.12 (D10) | brak w oprogramowaniu |
| Brzęczyk | — (oprogramowanie nie ma brzęczyka) | P1.03 (D2), 2048 Hz | brak w oprogramowaniu |
| VTEST | — | P0.30 (AIN6), VTEST_IN / 6 | brak w oprogramowaniu |

## Zgodne bez zmian

- Profil P1 ustawia IOCFG1 na wysoką impedancję (`src/p1_registers.h`), więc SO/GPIO1 CC1120 nie walczy z FRAM na wspólnej linii MISO.
- CS ekranu jest aktywny stanem wysokim, a program ustawia go w stan niski przed `SPI.begin()`. Zgadza się to z R13 na płytce.
- EXTCOMIN z licznika RTC2 przy EMD w stanie wysokim: N1 wiąże EMD z 3,3 V.
- Pozostałe ustawienia: SPI 1 MHz dla radia i FRAM, napięcia 3,0 V z płytki DK, dziennik w FRAM i polecenia pomiarowe nie zależą od przypisania pinów.

## Do sprawdzenia przy pliku N1

- Sterownik ekranu taktuje SPI zegarem 2 MHz (`firmware/README.md`, „Sterownik ekranu”). Na N1 SCK idzie przez P1.04, pin „standard drive, low frequency”, przez 33 Ω (R17) i sieć długości około 240 mm. 2 MHz to górna granica LS027B7DH01. Wymagany napęd H0H1 dla SCK i MOSI i próba z analizatorem na J11; w razie błędów 1 MHz.

## Obraz okablowania przewodami na N1

Uruchomienie `bench-a` na wpiętej płytce N1 jest elektrycznie bezpieczne, ale nie działa. SCK na P1.15 trafia przez R16 (1 kΩ) na przełącznik CISZA; przy ciszy płynie 3 mA. CS radia steruje diodą alarmu, a RESET radia linią DISP. CC1120 zostaje w resecie (R12), a ekran nie dostaje EXTCOMIN. Procedura uruchomienia i tak zakazuje tego obrazu na N1 ([uruchomienie](../uruchomienie.md#oprogramowanie)).

## Potrzebne w oprogramowaniu

1. Plik `src/board_bench_n1.h` i środowisko PlatformIO (na przykład `bench-n1` z `-DWICI_BENCH_N1`), wybierane zamiast `board_bench_a.h`. Przypisania z tabeli wyżej i z [połączeń](../polaczenia.md).
2. Własna instancja `SPIClass` (rdzeń Adafruit: SPIM z pinami MISO P1.14, SCK P1.04, MOSI P1.13) zamiast domyślnego `SPI` z wariantu PCA10056 oraz napęd H0H1 na SCK i MOSI.
3. DISP: stan niski do wyczyszczenia pamięci ekranu, potem wysoki.
4. Wejścia: przełącznik CISZA ustawia `bench.silence`, a przycisk przygotowania wybiera tryb przygotowania zamiast polecenia `PREP`. Polecenia USB mogą zostać jako zapasowe.
5. Dioda alarmu i brzęczyk (2048 Hz z PWM albo z licznika) dla ekranu alarmu oraz polecenia diagnostyczne do kroków A3–A4 uruchomienia (stan wejść, `BUZZ`, `LED`, `VTEST`).
6. Stanowisko B: program na ESP32-S3-DevKitC-1 (SPI na GPIO12/11/13, CS S2-LP GPIO10, SDN GPIO9) co najmniej do odczytu rejestru wersji S2-LP (krok B4).
