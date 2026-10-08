// SPDX-License-Identifier: MIT
#include "sa1.h"

#include <stdio.h>
#include <string.h>

#include "jsonlite.h"
#include "unicode_tables.h"

namespace sa1 {

namespace {

// Dekoduje jeden znak UTF-8 ze ścisłą kontrolą (bez nadmiarowych form i par zastępczych).
bool nextCodepoint(const unsigned char*& p, uint32_t& cp) {
    const unsigned char c = *p;
    size_t n = 0;
    uint32_t minimum = 0;
    if (c < 0x80) { cp = c; ++p; return true; }
    if ((c & 0xE0) == 0xC0) { n = 1; cp = c & 0x1F; minimum = 0x80; }
    else if ((c & 0xF0) == 0xE0) { n = 2; cp = c & 0x0F; minimum = 0x800; }
    else if ((c & 0xF8) == 0xF0) { n = 3; cp = c & 0x07; minimum = 0x10000; }
    else return false;
    ++p;
    for (size_t i = 0; i < n; ++i, ++p) {
        if ((*p & 0xC0) != 0x80) return false;
        cp = (cp << 6) | (*p & 0x3F);
    }
    if (cp < minimum || cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) return false;
    return true;
}

// Kategorie odrzucane przez model: Cc, Cf, Cs, Co, Cn, Zl, Zp (tablice z unicode_tables.h).
bool rejectedCodepoint(uint32_t c) {
    const uint32_t plane = c >> 16;
    if (plane > 16) return true;
    const uint16_t offset = static_cast<uint16_t>(c & 0xFFFF);
    const uint16_t* begin = ucd::REJECTED_TOGGLES + ucd::REJECTED_PLANE_START[plane];
    const uint16_t* end = ucd::REJECTED_TOGGLES + ucd::REJECTED_PLANE_START[plane + 1];
    // Liczba punktów zmiany <= offset (wyszukiwanie binarne).
    size_t low = 0, high = static_cast<size_t>(end - begin);
    while (low < high) {
        const size_t mid = (low + high) / 2;
        if (begin[mid] <= offset) low = mid + 1; else high = mid;
    }
    return (((ucd::REJECTED_PLANE_INITIAL >> plane) & 1) ^ (low & 1)) != 0;
}

// --- NFC (UAX #15): szybka kontrola, a w razie wątpliwości pełna normalizacja i porównanie. ---

constexpr uint32_t S_BASE = 0xAC00, L_BASE = 0x1100, V_BASE = 0x1161, T_BASE = 0x11A7;
constexpr uint32_t L_COUNT = 19, V_COUNT = 21, T_COUNT = 28, N_COUNT = V_COUNT * T_COUNT, S_COUNT = L_COUNT * N_COUNT;

uint8_t combiningClass(uint32_t c) {
    size_t low = 0, high = sizeof(ucd::CCC_RANGES) / sizeof(ucd::CCC_RANGES[0]);
    while (low < high) {  // ostatni przedział o początku <= c
        const size_t mid = (low + high) / 2;
        if ((ucd::CCC_RANGES[mid] >> 8) <= c) low = mid + 1; else high = mid;
    }
    if (low == 0) return 0;
    const uint32_t first = ucd::CCC_RANGES[low - 1] >> 8;
    return c - first <= (ucd::CCC_RANGES[low - 1] & 0xFF) ? ucd::CCC_VALUES[low - 1] : 0;
}

bool nfcNo(uint32_t c) {
    size_t low = 0, high = sizeof(ucd::NFC_NO) / sizeof(ucd::NFC_NO[0]);
    while (low < high) {
        const size_t mid = (low + high) / 2;
        if (ucd::NFC_NO[mid][1] < c) low = mid + 1; else high = mid;
    }
    return low < sizeof(ucd::NFC_NO) / sizeof(ucd::NFC_NO[0]) && ucd::NFC_NO[low][0] <= c;
}

// Numer znaku w NFC_SECOND albo -1.
int secondIndex(uint32_t c) {
    size_t low = 0, high = sizeof(ucd::NFC_SECOND) / sizeof(ucd::NFC_SECOND[0]);
    while (low < high) {
        const size_t mid = (low + high) / 2;
        if (ucd::NFC_SECOND[mid] < c) low = mid + 1; else high = mid;
    }
    return low < sizeof(ucd::NFC_SECOND) / sizeof(ucd::NFC_SECOND[0]) && ucd::NFC_SECOND[low] == c ? static_cast<int>(low) : -1;
}

bool nfcMaybe(uint32_t c) {
    return (c >= V_BASE && c < V_BASE + V_COUNT) || (c > T_BASE && c < T_BASE + T_COUNT) || secondIndex(c) >= 0;
}

// Rozkład kanoniczny jednego poziomu kompozycji pierwotnej: true i (first, second).
bool decomposition(uint32_t c, uint32_t& first, uint32_t& second) {
    if (c >= 0x20000) return false;
    size_t low = c < 0x10000 ? 0 : ucd::DECOMP_PLANE1;
    size_t high = c < 0x10000 ? ucd::DECOMP_PLANE1 : ucd::DECOMP_COUNT;
    const uint16_t key = static_cast<uint16_t>(c & 0xFFFF);
    while (low < high) {
        const size_t mid = (low + high) / 2;
        if (ucd::DECOMP_CP[mid] < key) low = mid + 1; else high = mid;
    }
    if (low == (c < 0x10000 ? ucd::DECOMP_PLANE1 : ucd::DECOMP_COUNT) || ucd::DECOMP_CP[low] != key) return false;
    first = ucd::DECOMP_PAIR[low] >> 8;
    second = ucd::NFC_SECOND[ucd::DECOMP_PAIR[low] & 0xFF];
    return true;
}

// Kompozycja pierwotna pary (z Hangul); 0, gdy brak.
uint32_t compose(uint32_t first, uint32_t second) {
    if (first >= L_BASE && first < L_BASE + L_COUNT && second >= V_BASE && second < V_BASE + V_COUNT)
        return S_BASE + ((first - L_BASE) * V_COUNT + (second - V_BASE)) * T_COUNT;
    if (first >= S_BASE && first < S_BASE + S_COUNT && (first - S_BASE) % T_COUNT == 0 && second > T_BASE && second < T_BASE + T_COUNT)
        return first + (second - T_BASE);
    const int index = secondIndex(second);
    if (index < 0 || first >= (1u << 24)) return 0;
    const uint32_t key = (first << 8) | static_cast<uint32_t>(index);
    size_t low = 0, high = ucd::DECOMP_COUNT;
    while (low < high) {
        const size_t mid = (low + high) / 2;
        if (ucd::DECOMP_PAIR[ucd::COMPOSE_ORDER[mid]] < key) low = mid + 1; else high = mid;
    }
    if (low == ucd::DECOMP_COUNT) return 0;
    const size_t entry = ucd::COMPOSE_ORDER[low];
    if (ucd::DECOMP_PAIR[entry] != key) return 0;
    return (entry < ucd::DECOMP_PLANE1 ? 0u : 0x10000u) | ucd::DECOMP_CP[entry];
}

// Pełny rozkład kanoniczny znaku na koniec bufora; false przy braku miejsca.
bool decomposeInto(uint32_t c, uint32_t* buffer, size_t size, size_t& n) {
    if (c >= S_BASE && c < S_BASE + S_COUNT) {
        const uint32_t s = c - S_BASE;
        if (n + 3 > size) return false;
        buffer[n++] = L_BASE + s / N_COUNT;
        buffer[n++] = V_BASE + (s % N_COUNT) / T_COUNT;
        if (s % T_COUNT) buffer[n++] = T_BASE + s % T_COUNT;
        return true;
    }
    uint32_t first = 0, second = 0;
    if (decomposition(c, first, second)) {
        // Drugi składnik nie ma rozkładu (sprawdza generator); pierwszy rozkładamy dalej.
        return decomposeInto(first, buffer, size, n) && decomposeInto(second, buffer, size, n);
    }
    if (n + 1 > size) return false;
    buffer[n++] = c;
    return true;
}

// Bufor pełnej normalizacji: rozkład daje najwyżej 1,5 znaku na bajt UTF-8 (sprawdza generator).
constexpr size_t NFC_BUFFER = MAX_CONTENT * 3 / 2;

// Dokładna odpowiedź na pytanie unicodedata.normalize("NFC", s) == s dla poprawnego UTF-8.
bool isNfc(const unsigned char* text) {
    bool full = false;
    uint8_t last = 0;
    for (const unsigned char* p = text; *p;) {
        uint32_t c = 0;
        nextCodepoint(p, c);
        if (nfcNo(c)) return false;  // NFC_QC=No: znak nie występuje w żadnym tekście NFC
        const uint8_t ccc = combiningClass(c);
        if ((ccc != 0 && last > ccc) || nfcMaybe(c)) full = true;
        last = ccc;
    }
    if (!full) return true;  // same NFC_QC=Yes w porządku kanonicznym
    uint32_t buffer[NFC_BUFFER];
    size_t n = 0;
    for (const unsigned char* p = text; *p;) {
        uint32_t c = 0;
        nextCodepoint(p, c);
        if (!decomposeInto(c, buffer, NFC_BUFFER, n)) return false;  // nieosiągalne przy limicie 256 B
    }
    // Porządek kanoniczny: stabilne sortowanie ciągów znaków o niezerowej klasie.
    for (size_t i = 1; i < n; ++i) {
        const uint32_t c = buffer[i];
        const uint8_t ccc = combiningClass(c);
        if (ccc == 0) continue;
        size_t j = i;
        while (j > 0) {
            const uint8_t previous = combiningClass(buffer[j - 1]);
            if (previous == 0 || previous <= ccc) break;
            buffer[j] = buffer[j - 1];
            --j;
        }
        buffer[j] = c;
    }
    // Składanie kanoniczne w miejscu.
    // Znak c łączy się z ostatnim znakiem początkowym, gdy nic go nie blokuje: poprzedni
    // pozostawiony znak jest tym początkowym albo ma klasę mniejszą od klasy c.
    size_t starter = 0, target = 1;
    bool haveStarter = combiningClass(buffer[0]) == 0;
    unsigned lastClass = 0;
    for (size_t i = 1; i < n; ++i) {
        const uint32_t c = buffer[i];
        const unsigned ccc = combiningClass(c);
        if (haveStarter && (lastClass < ccc || lastClass == 0)) {
            const uint32_t composite = compose(buffer[starter], c);
            if (composite) {
                buffer[starter] = composite;
                continue;
            }
        }
        if (ccc == 0) {
            starter = target;
            haveStarter = true;
        }
        lastClass = ccc;
        buffer[target++] = c;
    }
    n = target;
    // Porównanie z tekstem wejściowym.
    size_t i = 0;
    for (const unsigned char* p = text; *p; ++i) {
        uint32_t c = 0;
        nextCodepoint(p, c);
        if (i >= n || buffer[i] != c) return false;
    }
    return i == n;
}

bool fieldInteger(const json::Value& array, size_t index, int64_t low, int64_t high, int64_t& out) {
    json::Value v;
    return json::item(array, index, v) && json::integer(v, out) && out >= low && out <= high;
}

const char* fieldText(const json::Value& array, size_t index, char* out, size_t size, size_t maximum, size_t minimum) {
    json::Value v;
    if (!json::item(array, index, v) || v.kind != json::Kind::STRING) return "Invalid UTF-8 text size";
    if (!json::string(v, out, size)) return "Invalid UTF-8 text size";
    return checkText(out, maximum, minimum);
}

// 32 małe cyfry szesnastkowe.
bool isHexId(const char* id) {
    if (strlen(id) != ID_HEX) return false;
    for (size_t i = 0; i < ID_HEX; ++i) {
        const char c = id[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
    }
    return true;
}

}  // namespace

const char* checkText(const char* text, size_t maximum, size_t minimum) {
    // Kolejność kontroli jak w _text() modelu: rozmiar, cudzysłów i ukośnik, kategoria, NFC.
    const size_t bytes = strlen(text);
    if (bytes < minimum || bytes > maximum || bytes > MAX_CONTENT) return "Invalid UTF-8 text size";
    const unsigned char* begin = reinterpret_cast<const unsigned char*>(text);
    uint32_t cp = 0;
    for (const unsigned char* p = begin; *p;) {
        if (!nextCodepoint(p, cp)) return "Invalid UTF-8";
    }
    for (const unsigned char* p = begin; *p; ++p) {
        if (*p == '"' || *p == '\\') return "Quotation mark or backslash";
    }
    for (const unsigned char* p = begin; *p;) {
        nextCodepoint(p, cp);
        if (rejectedCodepoint(cp)) return "Control, format, separator, private or unassigned character";
    }
    if (!isNfc(begin)) return "Text is not NFC";
    return nullptr;
}

const char* decode(const char* wire, size_t length, Message& out) {
    if (length > MAX_CONTENT) return "Content too large";
    char copy[MAX_CONTENT + 1];
    memcpy(copy, wire, length);
    copy[length] = '\0';
    json::Value array;
    if (!json::parse(copy, array) || array.kind != json::Kind::ARRAY) return "Expected message array";
    const size_t n = json::count(array);
    if (n < 4) return "Expected message array";
    int64_t v = 0;
    if (!fieldInteger(array, 0, 1, 1, v)) return "Invalid integer";
    if (!fieldInteger(array, 1, 0, 5, v)) return "Invalid integer";
    out = Message();
    out.type = static_cast<uint8_t>(v);
    json::Value idValue;
    if (!json::item(array, 2, idValue) || !json::string(idValue, out.id, sizeof(out.id)) || !isHexId(out.id)) return "Invalid message id";
    static const size_t lengths[] = {9, 6, 6, 6, 5, 9};
    if (n != lengths[out.type]) return "Invalid message arity";
    const char* error = nullptr;
    if (out.type == BULLETIN) {
        if (!fieldInteger(array, 3, 1, EVENT_MAX, v)) return "Invalid integer";
        out.event = static_cast<uint32_t>(v);
        if ((error = fieldText(array, 4, out.text, sizeof(out.text), BULLETIN_MAX, 0))) return error;
        return nullptr;
    }
    if (!fieldInteger(array, 3, 0, REVISION_MAX, v)) return "Invalid integer";
    out.revision = static_cast<uint16_t>(v);
    if (out.type == REQUEST || out.type == TEST) {
        if (!fieldInteger(array, 4, 0, 9, v)) return "Invalid integer";
        out.category = static_cast<uint8_t>(v);
        if (!fieldInteger(array, 5, 1, 65535, v)) return "Invalid integer";
        out.people = static_cast<uint16_t>(v);
        if ((error = fieldText(array, 6, out.location, sizeof(out.location), LOCATION_MAX, 1))) return error;
        if ((error = fieldText(array, 7, out.text, sizeof(out.text), TEXT_MAX, 0))) return error;
        if (!fieldInteger(array, 8, 0, 2, v)) return "Invalid integer";
        out.urgency = static_cast<uint8_t>(v);
    } else if (out.type == RECEIVED) {
        if (!fieldInteger(array, 4, 1, 1, v) || !fieldInteger(array, 5, 1, 1, v)) return "Invalid integer";
        out.event = 1;
        out.state = 1;
    } else if (out.type == STATUS) {
        if (!fieldInteger(array, 4, 2, EVENT_MAX, v)) return "Invalid integer";
        out.event = static_cast<uint32_t>(v);
        if (!fieldInteger(array, 5, 2, 6, v)) return "Invalid integer";
        out.state = static_cast<uint8_t>(v);
    } else {  // REPLY
        if (!fieldInteger(array, 4, 1, EVENT_MAX, v)) return "Invalid integer";
        out.event = static_cast<uint32_t>(v);
        if ((error = fieldText(array, 5, out.text, sizeof(out.text), TEXT_MAX, 0))) return error;
    }
    return nullptr;
}

size_t encode(const Message& m, char* out, size_t size) {
    char buffer[MAX_CONTENT + 64];
    int n = 0;
    switch (m.type) {
        case REQUEST:
        case TEST:
            n = snprintf(buffer, sizeof(buffer), "[1,%u,\"%s\",%u,%u,%u,\"%s\",\"%s\",%u]", m.type, m.id, m.revision,
                         m.category, m.people, m.location, m.text, m.urgency);
            break;
        case RECEIVED:
            n = snprintf(buffer, sizeof(buffer), "[1,1,\"%s\",%u,1,1]", m.id, m.revision);
            break;
        case STATUS:
            n = snprintf(buffer, sizeof(buffer), "[1,2,\"%s\",%u,%lu,%u]", m.id, m.revision, static_cast<unsigned long>(m.event), m.state);
            break;
        case REPLY:
            n = snprintf(buffer, sizeof(buffer), "[1,3,\"%s\",%u,%lu,\"%s\"]", m.id, m.revision, static_cast<unsigned long>(m.event), m.text);
            break;
        case BULLETIN:
            n = snprintf(buffer, sizeof(buffer), "[1,4,\"%s\",%lu,\"%s\"]", m.id, static_cast<unsigned long>(m.event), m.text);
            break;
        default:
            return 0;
    }
    if (n <= 0 || static_cast<size_t>(n) >= sizeof(buffer) || static_cast<size_t>(n) > MAX_CONTENT || static_cast<size_t>(n) + 1 > size) return 0;
    // Kontrola jak w modelu: koder przyjmuje tylko poprawną wiadomość.
    Message check;
    if (decode(buffer, static_cast<size_t>(n), check)) return 0;
    memcpy(out, buffer, static_cast<size_t>(n) + 1);
    return static_cast<size_t>(n);
}

size_t buttonConfigurationSize(const char* address, const char* const* phrases, size_t count, const char** reason) {
    Message worst;
    worst.type = REQUEST;
    memset(worst.id, 'f', ID_HEX);
    worst.revision = REVISION_MAX;
    worst.category = 9;
    worst.people = 999;
    worst.urgency = 2;
    const char* why = checkText(address, LOCATION_MAX, 1);
    if (why) { if (reason) *reason = why; return 0; }
    strncpy(worst.location, address, LOCATION_MAX);
    char wire[MAX_CONTENT + 1];
    size_t size = encode(worst, wire, sizeof(wire));
    if (!size) { if (reason) *reason = "Content too large"; return 0; }
    for (size_t i = 0; i < count; ++i) {
        why = checkText(phrases[i], TEXT_MAX, 0);
        if (why) { if (reason) *reason = why; return 0; }
        strncpy(worst.text, phrases[i], TEXT_MAX);
        worst.text[TEXT_MAX] = '\0';
        const size_t n = encode(worst, wire, sizeof(wire));
        if (!n) { if (reason) *reason = "Content too large"; return 0; }
        if (n > size) size = n;
    }
    return size;
}

}  // namespace sa1
