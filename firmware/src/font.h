// SPDX-License-Identifier: MIT
// Font ekranu: wyszukiwanie glifów w tablicy z font_glyphs.h i dekodowanie UTF-8.
// Bez zależności od Arduino; sprawdzany na komputerze.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "font_glyphs.h"

namespace font {

// Glif znaku albo glif zastępczy U+FFFD, gdy znaku nie ma w tablicy.
const Glyph& glyph(uint32_t codepoint);
bool has(uint32_t codepoint);

// Kolejny znak UTF-8 z tekstu; przesuwa wskaźnik. Błędne bajty dają U+FFFD.
uint32_t next(const char*& text);
// Liczba znaków (nie bajtów) tekstu UTF-8.
size_t length(const char* text);

}  // namespace font
