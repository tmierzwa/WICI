// SPDX-License-Identifier: MIT
#include "sa1.h"

#include <stdio.h>
#include <string.h>

#include "jsonlite.h"

namespace sa1 {

namespace {

// Kategorie odrzucane przez model: Cc, Cf, Zl, Zp, Co, Cs (Cn tylko niecharaktery).
bool rejectedCodepoint(uint32_t c) {
    if (c < 0x20 || (c >= 0x7F && c <= 0x9F)) return true;                     // Cc
    if (c == 0x2028 || c == 0x2029) return true;                               // Zl, Zp
    if (c == 0xAD || (c >= 0x600 && c <= 0x605) || c == 0x61C || c == 0x6DD || c == 0x70F ||
        c == 0x890 || c == 0x891 || c == 0x8E2 || c == 0x180E || (c >= 0x200B && c <= 0x200F) ||
        (c >= 0x202A && c <= 0x202E) || (c >= 0x2060 && c <= 0x2064) || (c >= 0x2066 && c <= 0x206F) ||
        c == 0xFEFF || (c >= 0xFFF9 && c <= 0xFFFB) || c == 0x110BD || c == 0x110CD ||
        (c >= 0x13430 && c <= 0x1343F) || (c >= 0x1BCA0 && c <= 0x1BCA3) || (c >= 0x1D173 && c <= 0x1D17A) ||
        c == 0xE0001 || (c >= 0xE0020 && c <= 0xE007F)) return true;             // Cf
    if ((c >= 0xE000 && c <= 0xF8FF) || (c >= 0xF0000 && c <= 0xFFFFD) || (c >= 0x100000 && c <= 0x10FFFD)) return true;  // Co
    if ((c >= 0xFDD0 && c <= 0xFDEF) || (c & 0xFFFE) == 0xFFFE) return true;    // niecharaktery (Cn)
    return false;
}

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

}  // namespace

bool isHexId(const char* id) {
    if (strlen(id) != ID_HEX) return false;
    for (size_t i = 0; i < ID_HEX; ++i) {
        const char c = id[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
    }
    return true;
}

const char* checkText(const char* text, size_t maximum, size_t minimum) {
    const size_t bytes = strlen(text);
    if (bytes < minimum || bytes > maximum) return "Invalid UTF-8 text size";
    const unsigned char* p = reinterpret_cast<const unsigned char*>(text);
    while (*p) {
        if (*p == '"' || *p == '\\') return "Quotation mark or backslash";
        uint32_t cp = 0;
        if (!nextCodepoint(p, cp)) return "Invalid UTF-8";
        if (rejectedCodepoint(cp)) return "Control, format, separator, private or unassigned character";
    }
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

const char* statusAfter(uint32_t currentEvent, uint8_t currentState, uint32_t event, uint8_t state,
                        uint32_t& outEvent, uint8_t& outState) {
    if (event < 1 || event > EVENT_MAX || state < 1 || state > 6) return "Invalid integer";
    outEvent = currentEvent;
    outState = currentState;
    if (event < currentEvent) return nullptr;
    if (event == currentEvent && state != currentState) return "Conflicting event";
    if (event > currentEvent && (state == 1 || currentState == 6)) return "Status regression";
    outEvent = event;
    outState = state;
    return nullptr;
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
