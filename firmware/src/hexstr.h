// SPDX-License-Identifier: MIT
// Skróty i identyfikatory jako małe cyfry szesnastkowe (docs/spec/protokol-usb.md, "Warstwa
// przesyłu": `id` 32 znaki, klucz 128 znaków, SHA-256 64 znaki, `boot` i `epoch` 16 znaków).
// Jedna para funkcji dla magazynu, warstwy aplikacji, protokołu USB i diagnostyki.
// Bez zależności od Arduino.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace hexstr {

// out ma 2 × length + 1 B.
inline void encode(const uint8_t* data, size_t length, char* out) {
    static const char digits[] = "0123456789abcdef";
    for (size_t i = 0; i < length; ++i) {
        out[2 * i] = digits[data[i] >> 4];
        out[2 * i + 1] = digits[data[i] & 15];
    }
    out[2 * length] = '\0';
}

// Dokładnie 2 × length małych cyfr szesnastkowych i koniec napisu; false bez zmiany sensu out przy błędzie.
inline bool decode(const char* text, uint8_t* out, size_t length) {
    for (size_t i = 0; i < 2 * length; ++i) {
        const char c = text[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
    }
    if (text[2 * length] != '\0') return false;
    for (size_t i = 0; i < length; ++i) {
        const char hi = text[2 * i], lo = text[2 * i + 1];
        out[i] = static_cast<uint8_t>(((hi <= '9' ? hi - '0' : hi - 'a' + 10) << 4) | (lo <= '9' ? lo - '0' : lo - 'a' + 10));
    }
    return true;
}

}  // namespace hexstr
