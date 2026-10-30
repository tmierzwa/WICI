// SPDX-License-Identifier: MIT
// Nadzór odbioru w tle (stacja L0, plan interfejsu LoRa: „Zadanie odbioru a watchdog”, L6).
// - TaskSignals: sygnały życia zadania odbioru, które pisze zadanie, a czyta pętla stacji: licznik obiegów
//   (rośnie także wtedy, gdy blokada radia jest zajęta: martwe albo zagłodzone zadanie) i czas ostatniej
//   udanej obsługi układu (każda próbka odbioru, także sama próbka RSSI co 5 ms).
// - Watch: ocena po stronie pętli. Brak postępu jest błędem (radio_awaria) tylko przy uzbrojonym odbiorze
//   stosu (rxArmed), gdy pętla nie nadaje, i gdy jeden z sygnałów stoi STALL_MS. Czas liczy się najwyżej od
//   początku obserwacji (uzbrojenie albo koniec nadawania), więc stary znacznik sprzed uzbrojenia nie daje
//   alarmu od razu. Samoczynny powrót: sygnały znów idą, alarm gaśnie.
// - modeLost: kontrola trybu układu co 10 s (radiocon::check) z tymi samymi warunkami.
// Zadanie nie jest w watchdogu zadań (TWDT pilnuje tylko pętli): restart z powodu radia byłby gorszy od alarmu.
// Bez Arduino: sprawdzany na komputerze (tests/test_radio_link_host.py, RxRingTests).
#pragma once

#include <atomic>
#include <stdint.h>

namespace rxwatch {

constexpr uint32_t STALL_MS = 10000;  // sygnał stoi tyle: radio_awaria (alarm w 15 s z kontrolą co 10 s)

struct TaskSignals {
    std::atomic<uint32_t> ticks{0};          // obiegi zadania (taskTicks)
    std::atomic<uint32_t> lastServiceMs{0};  // millis() ostatniej udanej obsługi układu (lastServiceMs)
    std::atomic<uint32_t> serviceMaxUs{0};   // najdłuższa obsługa pod blokadą radia (rx_service_max_ms)

    void tick() { ticks.fetch_add(1, std::memory_order_relaxed); }
    void serviced(uint32_t nowMs, uint32_t tookUs) {
        lastServiceMs.store(nowMs, std::memory_order_release);
        if (tookUs > serviceMaxUs.load(std::memory_order_relaxed)) serviceMaxUs.store(tookUs, std::memory_order_relaxed);
    }
};

// Układ poza odbiorem jest błędem tylko przy uzbrojonym odbiorze stosu, gdy pętla nie nadaje. Stany
// zwolnione: tryb przygotowania (po IDLE, RESET, REGW), EMC, nośna CW, RX wzorcowy, halt (wszystkie kasują
// rxArmed) i nadawanie.
inline bool modeLost(bool armed, bool transmitting, bool chipInRx) { return armed && !transmitting && !chipInRx; }

class Watch {
public:
    // Wołane w każdym obiegu pętli; true, gdy odbiór stosu stoi (alarm).
    bool stalled(const TaskSignals& s, bool armed, bool transmitting, uint32_t nowMs) {
        if (!armed || transmitting) {
            watching_ = false;
            return false;
        }
        const uint32_t ticks = s.ticks.load(std::memory_order_relaxed);
        if (!watching_ || ticks != ticks_) {
            if (!watching_) sinceMs_ = nowMs;
            watching_ = true;
            ticks_ = ticks;
            ticksMs_ = nowMs;
        }
        return age(ticksMs_, nowMs) >= STALL_MS || age(s.lastServiceMs.load(std::memory_order_acquire), nowMs) >= STALL_MS;
    }

private:
    // Czas od znacznika, najwyżej od początku obserwacji; znacznik zapisany przez zadanie po odczycie
    // nowMs w pętli („w przyszłości”) liczy się jako 0.
    uint32_t age(uint32_t markMs, uint32_t nowMs) const {
        const int32_t sinceMark = static_cast<int32_t>(nowMs - markMs);
        const uint32_t sinceWatch = nowMs - sinceMs_;
        if (sinceMark < 0) return 0;
        return static_cast<uint32_t>(sinceMark) < sinceWatch ? static_cast<uint32_t>(sinceMark) : sinceWatch;
    }

    bool watching_ = false;
    uint32_t sinceMs_ = 0;  // początek obserwacji
    uint32_t ticks_ = 0;    // ostatnio widziany licznik obiegów
    uint32_t ticksMs_ = 0;  // chwila jego ostatniej zmiany
};

}  // namespace rxwatch
