// SPDX-License-Identifier: MIT
#include "config.h"

#include <string.h>

#include <initializer_list>

#include "hexstr.h"
#include "jsonlite.h"
#include "sa1.h"
#include "sha2.h"

namespace config {

namespace {

constexpr size_t VALUE_MAX = 640;   // pole albo element listy w RAM (karta odbiorcy ≈ 400 B, trójka fraz ≈ 300 B)

struct Range {
    uint32_t start = 0;
    uint32_t end = 0;
    bool set = false;
};

// Odczyt dokumentu kawałkami po 64 B.
class Reader {
public:
    Reader(Source& source, uint32_t size) : source_(source), size_(size) {}
    bool failed() const { return failed_; }
    bool escaped() const { return escaped_; }
    void seek(uint32_t pos) { pos_ = pos; }
    bool atEnd() { space(); return pos_ >= size_; }

    int peek() {
        if (pos_ >= size_ || failed_) return -1;
        if (pos_ < base_ || pos_ >= base_ + length_) {
            base_ = pos_;
            length_ = size_ - pos_ < sizeof(buffer_) ? size_ - pos_ : sizeof(buffer_);
            if (!source_.read(base_, buffer_, length_)) { failed_ = true; return -1; }
        }
        return static_cast<unsigned char>(buffer_[pos_ - base_]);
    }
    int get() {
        const int c = peek();
        if (c >= 0) ++pos_;
        return c;
    }
    void space() {
        for (int c = peek(); c == ' ' || c == '\t' || c == '\n' || c == '\r'; c = peek()) ++pos_;
    }
    bool expect(char wanted) {
        space();
        if (peek() != wanted) return false;
        ++pos_;
        return true;
    }
    // Zakres jednej wartości JSON (bez kontroli wnętrza: robi ją rozbiór pola).
    bool skip(Range& out) {
        space();
        out.start = pos_;
        int c = peek();
        if (c == '"') {
            if (!string()) return false;
        } else if (c == '{' || c == '[') {
            int depth = 0;
            do {
                c = peek();
                if (c == '"') { if (!string()) return false; continue; }
                if (get() < 0) return false;
                if (c == '{' || c == '[') ++depth;
                else if (c == '}' || c == ']') --depth;
            } while (depth > 0);
        } else {
            while ((c = peek()) >= 0 && ((c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || c == '-' || c == '+' || c == '.' || c == 'E')) ++pos_;
            if (pos_ == out.start) return false;
        }
        out.end = pos_;
        out.set = true;
        return true;
    }
    bool copy(const Range& range, char* out, size_t size) {
        const uint32_t length = range.end - range.start;
        if (length >= size) return false;
        if (!source_.read(range.start, out, length)) { failed_ = true; return false; }
        out[length] = '\0';
        return true;
    }

private:
    // Napis bez sekwencji ucieczki (dokument nie ma ich wcale) i bez znaków sterujących.
    bool string() {
        get();
        for (;;) {
            const int c = get();
            if (c < 0 || c < 0x20) return false;
            if (c == '\\') { escaped_ = true; return false; }
            if (c == '"') return true;
        }
    }

    Source& source_;
    uint32_t size_;
    uint32_t pos_ = 0;
    uint32_t base_ = 0;
    size_t length_ = 0;
    char buffer_[64];
    bool failed_ = false;
    bool escaped_ = false;
};

// Elementy tablicy JSON jako zakresy; count > max, gdy elementów jest więcej.
bool elements(Reader& in, const Range& array, Range* out, size_t max, size_t& count) {
    count = 0;
    in.seek(array.start);
    if (!in.expect('[')) return false;
    in.space();
    if (in.peek() == ']') { in.get(); return true; }
    for (;;) {
        Range item;
        if (!in.skip(item)) return false;
        if (count < max) out[count] = item;
        ++count;
        if (in.expect(']')) return true;
        if (!in.expect(',')) return false;
    }
}

enum Field : uint8_t { ROLE, ADDRESSES_F, RECEIVER, STATIONS, PHRASES_F, IFAC, RADIO, FIELDS };
const char* const NAMES[FIELDS] = {"role", "addresses", "receiver", "stations", "phrases", "ifac", "radio"};

bool parseValue(Reader& r, const Range& range, char* buffer, json::Value& out) {
    return r.copy(range, buffer, VALUE_MAX) && json::parse(buffer, out);
}

// Obiekt z dokładnie podanymi polami (nieznane pole = odmowa).
bool onlyFields(const json::Value& object, const char* const* keys, size_t count) {
    if (object.kind != json::Kind::OBJECT || json::count(object) != count) return false;
    json::Value v;
    for (size_t i = 0; i < count; ++i) {
        if (!json::field(object, keys[i], v)) return false;
    }
    return true;
}

bool text(const json::Value& value, char* out, size_t maximum, size_t minimum) {
    return json::string(value, out, maximum + 1) && !sa1::checkText(out, maximum, minimum);
}

bool receiver(const json::Value& card, Receiver& out) {
    static const char* const keys[] = {"lxmf", "key"};
    if (!onlyFields(card, keys, 2) || !json::hexField(card, "lxmf", out.lxmf, HASH) || !json::hexField(card, "key", out.key, KEY)) return false;
    uint8_t expected[HASH];
    sha2::destinationHash(out.key, LXMF_NAME, expected);
    if (memcmp(expected, out.lxmf, HASH)) return false;   // adres LXMF nie należy do klucza z karty
    sha2::destinationHash(out.key, SA1_NAME, out.sa1);
    return true;
}

}  // namespace

const char* parse(Source& source, uint32_t size, const char* profile, Config& out, size_t& worst) {
    out = Config();
    worst = 0;
    if (size == 0 || size > DOC_MAX) return "json";
    Reader r(source, size);
    Range fields[FIELDS];
    if (!r.expect('{')) return r.failed() ? "memory" : "json";
    r.space();
    if (r.peek() == '}') r.get();
    else {
        for (;;) {
            Range keyRange, value;
            char key[16];
            if (!r.skip(keyRange) || !r.copy(keyRange, key, sizeof(key)) || key[0] != '"' || !r.expect(':')) {
                return r.failed() ? "memory" : "json";
            }
            key[strlen(key) - 1] = '\0';
            size_t f = 0;
            while (f < FIELDS && strcmp(key + 1, NAMES[f])) ++f;
            if (f == FIELDS) {
                // Pole nieznane: jego nazwa w odpowiedzi, tylko drukowalne ASCII (bez wstrzykiwania w wiersz).
                static char unknown[sizeof(key)];
                for (size_t i = 0; key[i + 1]; ++i) unknown[i] = key[i + 1] > 0x20 && key[i + 1] < 0x7F ? key[i + 1] : '?';
                unknown[strlen(key) - 1] = '\0';
                return unknown;
            }
            if (fields[f].set || !r.skip(value)) return r.failed() ? "memory" : r.escaped() ? NAMES[f] : "json";
            fields[f] = value;
            if (r.expect('}')) break;
            if (!r.expect(',')) return r.failed() ? "memory" : "json";
        }
    }
    if (!r.atEnd()) return r.failed() ? "memory" : "json";

    char buffer[VALUE_MAX];
    json::Value v;
    // Rola wyznacza pola wymagane i zabronione.
    if (!fields[ROLE].set) return NAMES[ROLE];
    char role[8];
    if (!parseValue(r, fields[ROLE], buffer, v) || !json::string(v, role, sizeof(role))) return NAMES[ROLE];
    if (!strcmp(role, "stacja")) out.role = Role::STATION;
    else if (!strcmp(role, "wezel")) out.role = Role::NODE;
    else return NAMES[ROLE];
    for (size_t f : {ADDRESSES_F, RECEIVER, STATIONS, PHRASES_F}) {
        if (fields[f].set != (out.role == Role::STATION)) return NAMES[f];
    }
    if (!fields[IFAC].set || !fields[RADIO].set) return !fields[IFAC].set ? NAMES[IFAC] : NAMES[RADIO];

    char hex[2 * HASH + 2];
    if (!parseValue(r, fields[IFAC], buffer, v) || !json::string(v, hex, sizeof(hex)) || !hexstr::decode(hex, out.ifac, HASH)) return NAMES[IFAC];
    static const char* const radioKeys[] = {"profile"};
    json::Value p;
    if (!parseValue(r, fields[RADIO], buffer, v) || !onlyFields(v, radioKeys, 1) || !json::field(v, "profile", p) ||
        !json::string(p, out.profile, sizeof(out.profile)) || strcmp(out.profile, profile)) {
        return NAMES[RADIO];   // profil, którego układ radiowy stacji nie obsługuje, też jest odmową
    }
    if (out.role == Role::NODE) return nullptr;

    int64_t stations = 0;
    if (!parseValue(r, fields[STATIONS], buffer, v) || !json::integer(v, stations) || stations < 1 || stations > STATIONS_MAX) return NAMES[STATIONS];
    out.stations = static_cast<uint16_t>(stations);

    static const char* const cardKeys[] = {"main", "backup"};
    json::Value card;
    if (!parseValue(r, fields[RECEIVER], buffer, v) || !onlyFields(v, cardKeys, 2) || !json::field(v, "main", card) ||
        !receiver(card, out.receivers[MAIN]) || !json::field(v, "backup", card) || !receiver(card, out.receivers[BACKUP]) ||
        !memcmp(out.receivers[MAIN].lxmf, out.receivers[BACKUP].lxmf, HASH)) {
        return NAMES[RECEIVER];
    }

    Range items[PHRASES];
    size_t count = 0;
    if (!elements(r, fields[ADDRESSES_F], items, ADDRESSES, count) || count < 1 || count > ADDRESSES) return NAMES[ADDRESSES_F];
    out.addressCount = static_cast<uint8_t>(count);
    for (size_t i = 0; i < count; ++i) {
        if (!parseValue(r, items[i], buffer, v) || !text(v, out.addresses[i], ADDRESS_MAX, 1)) return NAMES[ADDRESSES_F];
    }
    if (!elements(r, fields[PHRASES_F], items, PHRASES, count) || count > PHRASES) return NAMES[PHRASES_F];
    out.phraseCount = static_cast<uint8_t>(count);
    const char* polish[PHRASES];
    for (size_t i = 0; i < count; ++i) {
        if (!parseValue(r, items[i], buffer, v) || v.kind != json::Kind::ARRAY || json::count(v) != LANGS) return NAMES[PHRASES_F];
        for (size_t l = 0; l < LANGS; ++l) {
            json::Value s;
            // Do SA1 trafia fraza polska (niepusta); brak tłumaczenia: ekran pokazuje polską.
            if (!json::item(v, l, s) || !text(s, out.phrases[i][l], PHRASE_MAX, l == 0 ? 1 : 0)) return NAMES[PHRASES_F];
        }
        polish[i] = out.phrases[i][0];
    }
    for (size_t i = 0; i < out.addressCount; ++i) {
        const size_t n = sa1::buttonConfigurationSize(out.addresses[i], polish, out.phraseCount);
        if (!n) return "worst_request";
        if (n > worst) worst = n;
    }
    return nullptr;
}

}  // namespace config
