// SPDX-License-Identifier: MIT
// Lekkie uśpienie MCU: opis linii budzenia i wybór poziomów, przy których linia budzi (docs/spec/oprogramowanie.md,
// „Czuwanie”). Uśpienie wykonuje platform::sleep (platform_esp32.cpp) z listami z pliku opisu płytki:
// board::SLEEP_HOLD (wyjścia trzymane w uśpieniu) i board::SLEEP_WAKE (linie budzenia).
//
// Lekkie uśpienie ESP32-S3 budzi poziomem, nie zboczem. Linia, której stan trwa (laptop podłączony, wyłącznik
// albo przycisk wciśnięty), budziłaby więc procesor w kółko. Dlatego:
// - linia ANY_CHANGE budzi przy poziomie przeciwnym do obecnego, czyli przy każdej zmianie stanu: wciśnięcie budzi,
//   trzymanie już nie, puszczenie budzi znowu;
// - linia ACTIVE_HIGH (DIO1 radia) budzi stanem wysokim, a gdy już jest wysoka, uśpienia nie ma: przerwanie
//   radia czeka na obsłużenie (ramka w buforze).
// Bez zależności od Arduino; sprawdzany na komputerze (tests/test_mcu_sleep.py).
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace mcu_sleep {

enum class Wake : uint8_t { ANY_CHANGE, ACTIVE_HIGH };

struct Line {
    uint8_t pin;
    Wake wake;
    const char* name;  // pole "line" w odpowiedzi NAP
};

constexpr size_t MAX_LINES = 16;

// Przyczyna wybudzenia: zegar (koniec maxMs), linia z listy, inna (np. przyczyna, której ESP-IDF nie
// rozpoznał), uśpienie odrzucone (ESP-IDF odmówił, najczęściej bo linia zmieniła stan między odczytem poziomów
// a wejściem w uśpienie: wołający sprawdza linie od nowa) albo bez uśpienia (BUSY): linia ACTIVE_HIGH już
// aktywna, blokada radia zajęta, trwający dźwięk brzęczyka albo pusta lista linii przy maxMs = 0.
enum class Cause : uint8_t { TIMER, LINE, OTHER, REJECTED, BUSY };

struct Result {
    Cause cause;
    int8_t line;      // indeks w liście linii (LINE, BUSY z linią) albo -1
    uint32_t sleptMs; // czas od wejścia w uśpienie do powrotu
};

inline const char* causeName(Cause c) {
    switch (c) {
    case Cause::TIMER: return "timer";
    case Cause::LINE: return "line";
    case Cause::OTHER: return "other";
    case Cause::REJECTED: return "rejected";
    case Cause::BUSY: return "busy";
    }
    return "other";
}

// Poziomy budzenia z obecnych poziomów linii (levels: 0 albo 1). Zwraca indeks linii ACTIVE_HIGH, która już
// jest aktywna (wtedy bez uśpienia), albo -1, gdy armed[] jest gotowe.
inline int arm(const Line* lines, size_t n, const uint8_t* levels, uint8_t* armed) {
    for (size_t i = 0; i < n; ++i) {
        if (lines[i].wake == Wake::ACTIVE_HIGH) {
            if (levels[i]) return static_cast<int>(i);
            armed[i] = 1;
        } else {
            armed[i] = levels[i] ? 0 : 1;
        }
    }
    return -1;
}

// Linia, która obudziła: pierwsza, której obecny poziom równa się uzbrojonemu; -1, gdy żadna (impuls
// krótszy niż powrót z uśpienia, np. drganie styku).
inline int woke(size_t n, const uint8_t* levels, const uint8_t* armed) {
    for (size_t i = 0; i < n; ++i)
        if (levels[i] == armed[i]) return static_cast<int>(i);
    return -1;
}

}  // namespace mcu_sleep
