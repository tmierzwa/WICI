# WICI: zgodność płytki nośnej N1 z oprogramowaniem

Stan: 2026-10-07. Płytka N1 według `tools/design.py` (commit 562d689). Oprogramowanie: pierwsze sprawdzenie wobec `firmware/` w commicie a3b821f (tylko środowisko `bench-a`, plik `src/board_bench_a.h`); ponowne po dodaniu środowiska `bench-n1` z plikiem `src/board_bench_n1.h`.

**Wynik: stanowisko A na N1 ma obraz `bench-n1`, zgodny z płytką w każdym sygnale tabeli niżej.** Obraz się buduje, ale nie był uruchomiony na sprzęcie; ekran pracuje z 1 MHz do próby 2 MHz z analizatorem ([niżej](#do-sprawdzenia-na-sprzęcie)). Obraz `bench-a` zostaje dla okablowania przewodami i nadal nie nadaje się na N1. Stanowisko B (ESP32-S3 z S2-LP) nie ma żadnego oprogramowania. Ustalenia wspólne dla obu wersji (rejestry radia, protokół, ekran) są zgodne.

## Przypisanie pinów nRF52840

| Sygnał | `board_bench_a.h` (przewody) | N1 | `bench-a` zgodne | `board_bench_n1.h` |
|---|---|---|---|---|
| SPI SCK | P1.15 (D13), domyślne `SPI` | P1.04 (D3) | nie | P1.04, własne `SPIClass` na SPIM2, H0H1 |
| SPI MOSI | P1.13 (D11) | P1.13 (D11) | tak | P1.13, H0H1 |
| SPI MISO | P1.14 (D12) | P1.14 (D12) | tak | P1.14 |
| CS radia | P1.12 (D10) | P0.04 (A1) | nie | P0.04 |
| RESET radia | P1.10 (D8) | P1.08 (D7), 10 kΩ do masy | nie | P1.08 |
| GPIO0 radia | P1.03 (D2) | P0.03 (A0) | nie | P0.03 |
| GPIO2 radia | P1.04 (D3) | P0.29 (A3) | nie | P0.29 |
| GPIO3 radia | — | P0.31 (A5) | brak w oprogramowaniu | P0.31, wejście nieużywane |
| CS FRAM | P1.11 (D9) | P1.11 (D9) | tak | P1.11 |
| CS ekranu | P1.05 (D4) | P1.05 (D4) | tak | P1.05 |
| EXTCOMIN | P1.06 (D5) | P1.07 (D6) | nie | P1.07, RTC2 |
| DISP ekranu | nie sterowany (podciągnięcie modułu) | P1.10 (D8), 2,2 kΩ do masy | nie: na N1 ekran jest wyłączony, dopóki program nie poda stanu wysokiego | P1.10: niski do CLEAR, potem wysoki |
| Przyciski GÓRA, DÓŁ, OK, WSTECZ | BUTTON1–4 płytki DK (P0.11, P0.12, P0.24, P0.25) | P1.01, P1.02, P0.26, P0.27 | nie (przyciski DK nadal działają, ale nie są panelem) | P1.01, P1.02, P0.26, P0.27, bez podciągnięcia wewnętrznego |
| CISZA | polecenie `SILENCE` | przełącznik, P1.15 (D13) przez 1 kΩ | brak w oprogramowaniu | P1.15 -> `bench.silence`; `SILENCE` zapasowo |
| Tryb przygotowania | polecenie `PREP` z potwierdzeniem przyciskiem OK | przycisk, P0.02 (AREF) | brak w oprogramowaniu | P0.02, przytrzymanie 3 s; `PREP` zapasowo |
| Dioda alarmu | — (diody DK LED1–4) | P1.12 (D10) | brak w oprogramowaniu | P1.12: do usunięcia przyczyny alarmu i w ciszy |
| Brzęczyk | — (oprogramowanie nie ma brzęczyka) | P1.03 (D2), 2048 Hz | brak w oprogramowaniu | P1.03, `tone()` 2048 Hz |
| VTEST | — | P0.30 (AIN6), VTEST_IN / 6 | brak w oprogramowaniu | P0.30 (AIN6), `VTEST` × 6 |

## Zgodne bez zmian

- Profil P1 ustawia IOCFG1 na wysoką impedancję (`src/p1_registers.h`), więc SO/GPIO1 CC1120 nie walczy z FRAM na wspólnej linii MISO.
- CS ekranu jest aktywny stanem wysokim, a program ustawia go w stan niski przed uruchomieniem SPI. Zgadza się to z R13 na płytce.
- EXTCOMIN z licznika RTC2 przy EMD w stanie wysokim: N1 wiąże EMD z 3,3 V.
- Pozostałe ustawienia: SPI 1 MHz dla radia i FRAM, napięcia 3,0 V z płytki DK, dziennik w FRAM i polecenia pomiarowe nie zależą od przypisania pinów.

## Do sprawdzenia na sprzęcie

- Zegar ekranu. Na N1 SCK idzie przez P1.04, pin „standard drive, low frequency”, przez 33 Ω (R17) i sieć długości około 240 mm, a 2 MHz to górna granica LS027B7DH01. Dlatego `bench-n1` taktuje ekran zegarem 1 MHz (`board::DISPLAY_SPI_HZ`; radio i FRAM też 1 MHz), z napędem H0H1 na SCK i MOSI, który ustawia `SPIClass::begin()` rdzenia. `DISPLAY 2000000` przełącza ekran na 2 MHz do restartu; przejście na 2 MHz na stałe dopiero po obejrzeniu zboczy SCK i MOSI analizatorem na J11 i obrazie bez błędów.
- Kroki A3–A5 [uruchomienia](../uruchomienie.md#stanowisko-a) z poleceniami `BTN`, `LED 5`, `BUZZ`, `VTEST` i `DISPLAY` ([firmware/README.md](../../../firmware/README.md#płytka-nośna-n1-bench-n1)).

## Obraz okablowania przewodami na N1

Uruchomienie `bench-a` na wpiętej płytce N1 jest elektrycznie bezpieczne, ale nie działa. SCK na P1.15 trafia przez R16 (1 kΩ) na przełącznik CISZA; przy ciszy płynie 3 mA. CS radia steruje diodą alarmu, a RESET radia linią DISP. CC1120 zostaje w resecie (R12), a ekran nie dostaje EXTCOMIN. Procedura uruchomienia i tak zakazuje tego obrazu na N1 ([uruchomienie](../uruchomienie.md#oprogramowanie)).

## Potrzebne w oprogramowaniu

Punkty 1–5 wykonane w środowisku `bench-n1` (opis w [firmware/README.md](../../../firmware/README.md#płytka-nośna-n1-bench-n1)); otwarty punkt 6.

1. Plik `src/board_bench_n1.h` i środowisko PlatformIO (na przykład `bench-n1` z `-DWICI_BENCH_N1`), wybierane zamiast `board_bench_a.h`. Przypisania z tabeli wyżej i z [połączeń](../polaczenia.md).
2. Własna instancja `SPIClass` (rdzeń Adafruit: SPIM z pinami MISO P1.14, SCK P1.04, MOSI P1.13) zamiast domyślnego `SPI` z wariantu PCA10056 oraz napęd H0H1 na SCK i MOSI.
3. DISP: stan niski do wyczyszczenia pamięci ekranu, potem wysoki.
4. Wejścia: przełącznik CISZA ustawia `bench.silence`, a przycisk przygotowania wybiera tryb przygotowania zamiast polecenia `PREP`. Polecenia USB mogą zostać jako zapasowe.
5. Dioda alarmu i brzęczyk (2048 Hz z PWM albo z licznika) dla ekranu alarmu oraz polecenia diagnostyczne do kroków A3–A4 uruchomienia (stan wejść, `BUZZ`, `LED`, `VTEST`).
6. Stanowisko B: program na ESP32-S3-DevKitC-1 (SPI na GPIO12/11/13, CS S2-LP GPIO10, SDN GPIO9) co najmniej do odczytu rejestru wersji S2-LP (krok B4).
