// SPDX-License-Identifier: MIT
// Napis w odpowiedzi JSON portu diagnostyki: cudzysłów, ukośnik wsteczny i znaki sterujące jako
// sekwencje ucieczki, więc tekst z laptopa, dziennika albo stosu nie psuje wiersza ani nie dzieli
// go na dwa. Znaki spoza ASCII bez zmian (UTF-8).
#pragma once

#include <Arduino.h>

namespace jsonprint {

inline void text(Print& out, const char* s) {
    static const char hex[] = "0123456789abcdef";
    for (; *s; ++s) {
        const unsigned char c = static_cast<unsigned char>(*s);
        if (c == '"' || c == '\\') {
            out.write('\\');
            out.write(c);
        } else if (c < 0x20) {
            const char escape[] = {'\\', 'u', '0', '0', hex[c >> 4], hex[c & 15]};
            out.write(reinterpret_cast<const uint8_t*>(escape), sizeof(escape));
        } else {
            out.write(c);
        }
    }
}

// Pole "klucz":"napis" bez przecinka.
inline void field(Print& out, const char* key, const char* value) {
    out.write('"');
    out.print(key);
    out.print("\":\"");
    text(out, value);
    out.write('"');
}

}  // namespace jsonprint
