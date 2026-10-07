// SPDX-License-Identifier: MIT
#include "font.h"

namespace font {

const Glyph* find(uint32_t codepoint) {
    size_t low = 0;
    size_t high = GLYPH_COUNT;
    while (low < high) {
        const size_t mid = (low + high) / 2;
        if (GLYPHS[mid].codepoint < codepoint) low = mid + 1;
        else high = mid;
    }
    return low < GLYPH_COUNT && GLYPHS[low].codepoint == codepoint ? &GLYPHS[low] : nullptr;
}

bool has(uint32_t codepoint) { return find(codepoint) != nullptr; }

const Glyph& glyph(uint32_t codepoint) {
    const Glyph* g = find(codepoint);
    return g ? *g : *find(REPLACEMENT);
}

uint32_t next(const char*& text) {
    const uint8_t first = static_cast<uint8_t>(*text);
    if (first == 0) return 0;
    ++text;
    if (first < 0x80) return first;
    size_t extra = 0;
    uint32_t value = 0;
    if ((first & 0xE0) == 0xC0) { extra = 1; value = first & 0x1F; }
    else if ((first & 0xF0) == 0xE0) { extra = 2; value = first & 0x0F; }
    else if ((first & 0xF8) == 0xF0) { extra = 3; value = first & 0x07; }
    else return REPLACEMENT;
    for (size_t i = 0; i < extra; ++i) {
        const uint8_t byte = static_cast<uint8_t>(*text);
        if ((byte & 0xC0) != 0x80) return REPLACEMENT;  // urwana sekwencja: wskaźnik zostaje na tym bajcie
        value = (value << 6) | (byte & 0x3F);
        ++text;
    }
    return value;
}

size_t length(const char* text) {
    size_t n = 0;
    while (next(text)) ++n;
    return n;
}

}  // namespace font
