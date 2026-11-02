// SPDX-License-Identifier: MIT
// Argumenty poleceń portu diagnostyki: liczby z pełną kontrolą (cały tekst, bez znaku tam, gdzie
// nie ma sensu, zakres), żeby „SILENCE X”, „FOFF ABC” albo „KEY BACK -1” nie dawały przypadkowej
// wartości. Bez zależności od Arduino.
#pragma once

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
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

// REQ <n> [<text bytes>] (bench requests, main.cpp): n requests, 1..REQUEST_MAX, and the
// exact length of their text, 0..textMax; without it the text is only the label "REQ <k>".
constexpr uint32_t REQUEST_MAX = 100;
inline bool parseRequest(char* const words[], size_t n, uint32_t textMax, uint32_t& count, int32_t& textBytes) {
    uint32_t bytes = 0;
    if (n < 1 || n > 2 || !parseUint(words[0], 1, REQUEST_MAX, count) || (n == 2 && !parseUint(words[1], 0, textMax, bytes)))
        return false;
    textBytes = n == 2 ? static_cast<int32_t>(bytes) : -1;
    return true;
}

// Text of request k: the label "REQ <k>" padded with '.' or cut to textBytes (-1: the label as is);
// size must exceed textBytes and hold the label.
inline void requestText(uint32_t k, int32_t textBytes, char* out, size_t size) {
    const int label = snprintf(out, size, "REQ %lu", static_cast<unsigned long>(k));
    if (textBytes < 0 || label < 0 || static_cast<size_t>(textBytes) >= size) return;
    for (int32_t i = label; i < textBytes; ++i) out[i] = '.';
    out[textBytes] = '\0';
}

}  // namespace cmdargs
