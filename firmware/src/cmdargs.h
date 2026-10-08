// SPDX-License-Identifier: MIT
// Argumenty poleceń portu diagnostyki: liczby z pełną kontrolą (cały tekst, bez znaku tam, gdzie
// nie ma sensu, zakres), żeby „SILENCE X”, „FOFF ABC” albo „KEY BACK -1” nie dawały przypadkowej
// wartości. Bez zależności od Arduino.
#pragma once

#include <errno.h>
#include <stdint.h>
#include <stdlib.h>

namespace cmdargs {

inline const char* boolName(bool value) { return value ? "true" : "false"; }

// Liczba bez znaku w podstawie base (10 albo 16) z zakresu [minimum, maximum].
inline bool parseUint(const char* text, uint32_t minimum, uint32_t maximum, uint32_t& out, int base = 10) {
    if (!text || !*text || *text == '-' || *text == '+' || *text == ' ') return false;
    char* end = nullptr;
    errno = 0;
    const unsigned long value = strtoul(text, &end, base);
    if (errno || *end || value < minimum || value > maximum) return false;
    out = static_cast<uint32_t>(value);
    return true;
}

// Liczba ze znakiem z zakresu [minimum, maximum].
inline bool parseInt(const char* text, int32_t minimum, int32_t maximum, int32_t& out) {
    if (!text || !*text || *text == ' ') return false;
    char* end = nullptr;
    errno = 0;
    const long value = strtol(text, &end, 10);
    if (errno || *end || value < minimum || value > maximum) return false;
    out = static_cast<int32_t>(value);
    return true;
}

// 0 albo 1.
inline bool parseFlag(const char* text, bool& out) {
    uint32_t value = 0;
    if (!parseUint(text, 0, 1, value)) return false;
    out = value != 0;
    return true;
}

}  // namespace cmdargs
