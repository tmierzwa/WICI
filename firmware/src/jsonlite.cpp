// SPDX-License-Identifier: MIT
#include "jsonlite.h"

#include <string.h>

namespace json {

namespace {

void skipSpace(const char*& p) {
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') ++p;
}

bool scanString(const char*& p) {
    // p wskazuje cudzysłów otwierający.
    ++p;
    while (*p) {
        const unsigned char c = static_cast<unsigned char>(*p);
        if (c == '"') { ++p; return true; }
        if (c < 0x20) return false;  // znaki sterujące muszą być zakodowane
        if (c == '\\') {
            ++p;
            const char e = *p;
            if (e == 'u') {
                for (int i = 1; i <= 4; ++i) {
                    const char h = p[i];
                    const bool hex = (h >= '0' && h <= '9') || (h >= 'a' && h <= 'f') || (h >= 'A' && h <= 'F');
                    if (!hex) return false;
                }
                p += 5;
                continue;
            }
            if (!e || !strchr("\"\\/bfnrt", e)) return false;
        }
        ++p;
    }
    return false;
}

bool scanNumber(const char*& p) {
    if (*p == '-') ++p;
    if (*p == '0') ++p;
    else if (*p >= '1' && *p <= '9') { while (*p >= '0' && *p <= '9') ++p; }
    else return false;
    if (*p == '.') {
        ++p;
        if (!(*p >= '0' && *p <= '9')) return false;
        while (*p >= '0' && *p <= '9') ++p;
    }
    if (*p == 'e' || *p == 'E') {
        ++p;
        if (*p == '+' || *p == '-') ++p;
        if (!(*p >= '0' && *p <= '9')) return false;
        while (*p >= '0' && *p <= '9') ++p;
    }
    return true;
}

bool scanContainer(const char*& p, char close, int depth) {
    // p wskazuje nawias otwierający.
    if (depth > 16) return false;
    ++p;
    skipSpace(p);
    if (*p == close) { ++p; return true; }
    while (true) {
        skipSpace(p);
        if (close == '}') {
            if (*p != '"' || !scanString(p)) return false;
            skipSpace(p);
            if (*p != ':') return false;
            ++p;
            skipSpace(p);
        }
        Value v;
        if (*p == '{' || *p == '[') {
            v.begin = p;
            if (!scanContainer(p, *p == '{' ? '}' : ']', depth + 1)) return false;
        } else if (!scan(p, v)) return false;
        skipSpace(p);
        if (*p == ',') { ++p; continue; }
        if (*p == close) { ++p; return true; }
        return false;
    }
}

bool literal(const char*& p, const char* word) {
    const size_t n = strlen(word);
    if (strncmp(p, word, n)) return false;
    p += n;
    return true;
}

// Kolejny element kontenera: dla obiektu zwraca klucz (zakres napisu) i wartość.
bool next(const char*& p, char close, Value* key, Value& value) {
    skipSpace(p);
    if (*p == close) return false;
    if (*p == ',') { ++p; skipSpace(p); }
    if (close == '}') {
        if (*p != '"') return false;
        key->kind = Kind::STRING;
        key->begin = p;
        if (!scanString(p)) return false;
        key->length = static_cast<size_t>(p - key->begin);
        skipSpace(p);
        if (*p != ':') return false;
        ++p;
    }
    return scan(p, value);
}

uint32_t hex4(const char* p) {
    uint32_t v = 0;
    for (int i = 0; i < 4; ++i) {
        const char h = p[i];
        v = (v << 4) | static_cast<uint32_t>(h <= '9' ? h - '0' : (h | 0x20) - 'a' + 10);
    }
    return v;
}

bool putUtf8(uint32_t cp, char* out, size_t size, size_t& n) {
    char buf[4];
    size_t len = 0;
    if (cp < 0x80) { buf[0] = static_cast<char>(cp); len = 1; }
    else if (cp < 0x800) { buf[0] = static_cast<char>(0xC0 | (cp >> 6)); buf[1] = static_cast<char>(0x80 | (cp & 0x3F)); len = 2; }
    else if (cp < 0x10000) {
        buf[0] = static_cast<char>(0xE0 | (cp >> 12)); buf[1] = static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
        buf[2] = static_cast<char>(0x80 | (cp & 0x3F)); len = 3;
    } else {
        buf[0] = static_cast<char>(0xF0 | (cp >> 18)); buf[1] = static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
        buf[2] = static_cast<char>(0x80 | ((cp >> 6) & 0x3F)); buf[3] = static_cast<char>(0x80 | (cp & 0x3F)); len = 4;
    }
    if (n + len >= size) return false;
    memcpy(out + n, buf, len);
    n += len;
    return true;
}

}  // namespace

bool scan(const char*& p, Value& out) {
    skipSpace(p);
    out.begin = p;
    switch (*p) {
        case '"': out.kind = Kind::STRING; if (!scanString(p)) return false; break;
        case '{': out.kind = Kind::OBJECT; if (!scanContainer(p, '}', 0)) return false; break;
        case '[': out.kind = Kind::ARRAY; if (!scanContainer(p, ']', 0)) return false; break;
        case 't': out.kind = Kind::TRUE_; if (!literal(p, "true")) return false; break;
        case 'f': out.kind = Kind::FALSE_; if (!literal(p, "false")) return false; break;
        case 'n': out.kind = Kind::NULL_; if (!literal(p, "null")) return false; break;
        default: out.kind = Kind::NUMBER; if (!scanNumber(p)) return false; break;
    }
    out.length = static_cast<size_t>(p - out.begin);
    return true;
}

bool parse(const char* text, Value& out) {
    const char* p = text;
    if (!scan(p, out)) return false;
    skipSpace(p);
    return *p == '\0';
}

bool field(const Value& object, const char* key, Value& out) {
    if (object.kind != Kind::OBJECT) return false;
    const char* p = object.begin + 1;
    const size_t keyLength = strlen(key);
    Value k, v;
    while (next(p, '}', &k, v)) {
        if (k.length == keyLength + 2 && !memcmp(k.begin + 1, key, keyLength)) { out = v; return true; }
    }
    return false;
}

bool item(const Value& array, size_t index, Value& out) {
    if (array.kind != Kind::ARRAY) return false;
    const char* p = array.begin + 1;
    Value v;
    size_t i = 0;
    while (next(p, ']', nullptr, v)) {
        if (i++ == index) { out = v; return true; }
    }
    return false;
}

size_t count(const Value& container) {
    if (container.kind != Kind::ARRAY && container.kind != Kind::OBJECT) return 0;
    const char close = container.kind == Kind::ARRAY ? ']' : '}';
    const char* p = container.begin + 1;
    Value k, v;
    size_t n = 0;
    while (next(p, close, &k, v)) ++n;
    return n;
}

bool integer(const Value& value, int64_t& out) {
    if (value.kind != Kind::NUMBER) return false;
    const char* p = value.begin;
    const char* end = value.begin + value.length;
    bool negative = false;
    if (*p == '-') { negative = true; ++p; }
    if (p == end) return false;
    uint64_t magnitude = 0;
    for (; p < end; ++p) {
        if (*p < '0' || *p > '9') return false;  // ułamek albo wykładnik
        if (magnitude > (UINT64_MAX - 9) / 10) return false;
        magnitude = magnitude * 10 + static_cast<uint64_t>(*p - '0');
    }
    if (magnitude > static_cast<uint64_t>(INT64_MAX)) return false;
    out = negative ? -static_cast<int64_t>(magnitude) : static_cast<int64_t>(magnitude);
    return true;
}

bool string(const Value& value, char* out, size_t size, size_t* length) {
    if (value.kind != Kind::STRING || size == 0) return false;
    const char* p = value.begin + 1;
    const char* end = value.begin + value.length - 1;
    size_t n = 0;
    while (p < end) {
        if (*p != '\\') {
            if (n + 1 >= size) return false;
            out[n++] = *p++;
            continue;
        }
        ++p;
        char c = 0;
        switch (*p) {
            case '"': c = '"'; break;
            case '\\': c = '\\'; break;
            case '/': c = '/'; break;
            case 'b': c = '\b'; break;
            case 'f': c = '\f'; break;
            case 'n': c = '\n'; break;
            case 'r': c = '\r'; break;
            case 't': c = '\t'; break;
            case 'u': {
                uint32_t cp = hex4(p + 1);
                p += 5;
                if (cp >= 0xD800 && cp <= 0xDBFF) {
                    if (p + 6 > end || p[0] != '\\' || p[1] != 'u') return false;
                    const uint32_t low = hex4(p + 2);
                    if (low < 0xDC00 || low > 0xDFFF) return false;
                    cp = 0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00);
                    p += 6;
                } else if (cp >= 0xDC00 && cp <= 0xDFFF) return false;
                if (!putUtf8(cp, out, size, n)) return false;
                continue;
            }
            default: return false;
        }
        if (n + 1 >= size) return false;
        out[n++] = c;
        ++p;
    }
    out[n] = '\0';
    if (length) *length = n;
    return true;
}

bool quote(const char* text, char* out, size_t size, size_t* length) {
    size_t n = 0;
    auto put = [&](char c) { if (n + 1 >= size) return false; out[n++] = c; return true; };
    if (!put('"')) return false;
    for (const char* p = text; *p; ++p) {
        const unsigned char c = static_cast<unsigned char>(*p);
        if (c == '"' || c == '\\') { if (!put('\\') || !put(static_cast<char>(c))) return false; }
        else if (c < 0x20) {
            static const char hex[] = "0123456789abcdef";
            if (!put('\\')) return false;
            if (c == '\n') { if (!put('n')) return false; }
            else if (c == '\r') { if (!put('r')) return false; }
            else if (c == '\t') { if (!put('t')) return false; }
            else if (!put('u') || !put('0') || !put('0') || !put(hex[c >> 4]) || !put(hex[c & 15])) return false;
        } else if (!put(static_cast<char>(c))) return false;
    }
    if (!put('"')) return false;
    out[n] = '\0';
    if (length) *length = n;
    return true;
}

bool raw(const Value& value, char* out, size_t size) {
    if (value.length + 1 > size) return false;
    memcpy(out, value.begin, value.length);
    out[value.length] = '\0';
    return true;
}

}  // namespace json
