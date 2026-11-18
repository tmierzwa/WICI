// SPDX-License-Identifier: MIT
// Wyłączanie stacji przez sterownik wyłącznika LTC2955-2 na płytce v2 (docs/spec/elektronika.md, „sterownik
// wyłącznika”; hardware/r02/zasilanie.md, „Przerwanie i KILL”). Tu są tylko reguły; piny, zapis i ekran obsługuje
// main.cpp.
//
// - Żądanie: INT w stanie niskim przez HOLD_MS (sterownik ściąga INT 19–45 ms po naciśnięciu i trzyma do puszczenia,
//   więc 2 s odmierza program) albo kontrolowane wyłączenie przy wyczerpanych ogniwach (power::Monitor::shutdown).
//   INT liczy się dopiero po pierwszym puszczeniu wyłącznika od startu: przycisk trzymany przy włączaniu nie wyłącza
//   stacji od razu (jak przycisk przygotowania).
// - SAVING: ekran `wylaczanie`; main.cpp zatrzymuje radio i stos, kończy zapis (tablice stosu, zegar dziennika)
//   i woła saved(). Od tej chwili nic już nie pisze do FRAM poza wpisem dziennika o nieudanym KILL.
// - REMOVABLE: ekran `mozna_wyjac` przez SHOW_MS, potem KILL (Q11 ściąga KILL, sterownik zdejmuje zasilanie).
// - KILLED: KILL trzymany. Sterownik ignoruje KILL przez 304–720 ms po włączeniu, a trzymany KILL działa po tym
//   oknie sam, więc start z wyczerpanymi ogniwami też kończy się wyłączeniem.
// - FAILED: zasilanie nie zgasło w FAIL_MS. Stacja zostaje wyłączona programowo (stan zapisany, radio wyłączone),
//   ekran pokazuje `mozna_wyjac` i `kill_nie_zadzialal`, a KILL jest ponawiany co RETRY_MS (puszczony na RELEASE_MS
//   i znowu ściągnięty), z jednym wpisem w dzienniku. Bez restartu: restart włączałby stację wbrew wyłącznikowi,
//   a przy 4,0 V na ogniwach zapętlałby się i dalej rozładowywał ogniwa (decyzja właściciela 2026-11-18).
// Wartości SHOW_MS, FAIL_MS i RETRY_MS przyjął właściciel 2026-11-18; do sprawdzenia na płytce.
// Czas w ms z millis(); różnice odporne na przejście przez zero.
// Bez zależności od Arduino; sprawdzany na komputerze (tests/test_firmware_host.py).
#pragma once

#include <stdint.h>

namespace shutdown {

constexpr uint32_t HOLD_MS = 2000;     // przytrzymanie wyłącznika („WYŁĄCZ: TRZYMAJ 2 s” na folii)
constexpr uint32_t SHOW_MS = 2000;     // `mozna_wyjac` przed KILL
constexpr uint32_t FAIL_MS = 5000;     // KILL bez skutku tyle: FAILED
constexpr uint32_t RETRY_MS = 5000;    // ponowienie KILL
constexpr uint32_t RELEASE_MS = 100;   // KILL puszczony przy ponowieniu

enum class Phase : uint8_t { RUN, SAVING, REMOVABLE, KILLED, FAILED };
enum class Reason : uint8_t { NONE, BUTTON, CELLS };
const char* phaseName(Phase phase);
const char* reasonName(Reason reason);

class Sequence {
public:
    // Wołać w każdym obiegu pętli: intLow — INT w stanie niskim; cellsEmpty — power::Monitor::shutdown().
    // Zwraca true, gdy zmieniła się faza albo poziom KILL (ekran, pin, dziennik).
    bool poll(uint32_t nowMs, bool intLow, bool cellsEmpty);
    void saved(uint32_t nowMs);   // zapis zakończony (po SAVING)

    Phase phase() const { return phase_; }
    Reason reason() const { return reason_; }
    bool active() const { return phase_ != Phase::RUN; }
    bool kill() const { return kill_; }                 // poziom KILL_MCU (wysoki: Q11 ściąga KILL)
    bool failedLog() const { return failedLog_; }        // jednorazowy wpis o nieudanym KILL do zrobienia
    void logged() { failedLog_ = false; }
    uint32_t retries() const { return retries_; }
    // Czas do następnej zmiany [ms] po ostatnim poll() (pętla czuwania); 0xFFFFFFFF, gdy nic nie czeka.
    uint32_t untilMs(uint32_t nowMs) const;

private:
    void enter(Phase phase, uint32_t nowMs);
    Phase phase_ = Phase::RUN;
    Reason reason_ = Reason::NONE;
    bool armed_ = false;        // wyłącznik puszczony od startu
    bool intWas_ = false;
    uint32_t intSinceMs_ = 0;
    uint32_t phaseMs_ = 0;      // wejście w fazę
    bool kill_ = false;
    uint32_t killMs_ = 0;       // ostatnia zmiana KILL w FAILED
    bool failedLog_ = false;
    uint32_t retries_ = 0;
};

}  // namespace shutdown
