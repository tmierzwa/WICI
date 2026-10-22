// SPDX-License-Identifier: LicenseRef-Reticulum AND MIT
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2013-2020 vsergeev / Ivan (Vanya) A. Sergeev
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
#include "msgpack.h"

#include <string.h>

namespace rnscore {
namespace msgpack {

static_assert(sizeof(double) == 8 && sizeof(float) == 4, "float64 i float32 wymagają IEEE 754");

namespace {

uint64_t bigEndian(const uint8_t* p, size_t n) {
    uint64_t value = 0;
    for (size_t i = 0; i < n; ++i) value = (value << 8) | p[i];
    return value;
}

// Dekoder UTF-8 Pythona (bytes.decode(data, "utf-8") w _unpack_string): bez form nadmiarowych,
// surogatów (U+D800–U+DFFF) i wartości ponad U+10FFFF.
bool validUtf8(const uint8_t* p, size_t n) {
    size_t i = 0;
    while (i < n) {
        const uint8_t c = p[i];
        size_t follow;
        uint8_t low = 0x80, high = 0xBF;   // dozwolony zakres pierwszego bajtu kontynuacji
        if (c < 0x80) {
            ++i;
            continue;
        } else if (c >= 0xC2 && c <= 0xDF) {
            follow = 1;
        } else if (c >= 0xE0 && c <= 0xEF) {
            follow = 2;
            if (c == 0xE0) low = 0xA0;
            if (c == 0xED) high = 0x9F;
        } else if (c >= 0xF0 && c <= 0xF4) {
            follow = 3;
            if (c == 0xF0) low = 0x90;
            if (c == 0xF4) high = 0x8F;
        } else {
            return false;
        }
        if (follow > n - i - 1) return false;
        if (p[i + 1] < low || p[i + 1] > high) return false;
        for (size_t k = 2; k <= follow; ++k) {
            if ((p[i + k] & 0xC0) != 0x80) return false;
        }
        i += follow + 1;
    }
    return true;
}

// Klucz mapy, który rdzeń przyjmuje (odstępstwo w msgpack.h).
bool allowedKey(const Item& key) {
    return key.type == Type::NIL || key.type == Type::BOOL || key.type == Type::UINT || key.type == Type::INT ||
           key.type == Type::STR || key.type == Type::BIN;
}

// Wartość liczbowa klucza: bool jako 0 albo 1, jak w Pythonie (True == 1, False == 0).
bool keyNumber(const Item& x, bool& negative, uint64_t& bits) {
    negative = x.type == Type::INT;
    if (x.type == Type::BOOL) bits = x.boolean ? 1 : 0;
    else if (x.type == Type::UINT) bits = x.uinteger;
    else if (x.type == Type::INT) bits = static_cast<uint64_t>(x.integer);
    else return false;
    return true;
}

// Równość kluczy jak w Pythonie (k in d); str i bytes o tych samych bajtach są różne.
bool sameKey(const Item& a, const Item& b) {
    bool negativeA = false, negativeB = false;
    uint64_t bitsA = 0, bitsB = 0;
    const bool numberA = keyNumber(a, negativeA, bitsA);
    const bool numberB = keyNumber(b, negativeB, bitsB);
    if (numberA || numberB) return numberA && numberB && negativeA == negativeB && bitsA == bitsB;
    if (a.type != b.type) return false;
    if (a.type == Type::NIL) return true;
    return a.length == b.length && memcmp(a.data, b.data, a.length) == 0;   // STR albo BIN
}

}  // namespace

bool Reader::take(size_t n, const uint8_t*& out) {
    if (n > length_ - position_) return false;
    out = data_ + position_;
    position_ += n;
    return true;
}

bool Reader::read(Item& out) {
    out = Item{};
    const uint8_t* p;
    if (!take(1, p)) return false;
    const uint8_t code = p[0];
    size_t lengthBytes = 0;   // bajty długości po kodzie (str, bin, array, map)
    if (code <= 0x7F) {
        out.type = Type::UINT;
        out.uinteger = code;
        return true;
    } else if (code >= 0xE0) {
        out.type = Type::INT;
        out.integer = static_cast<int8_t>(code);
        return true;
    } else if (code <= 0x9F) {
        out.type = code <= 0x8F ? Type::MAP : Type::ARRAY;
        out.length = code & 0x0F;
    } else if (code <= 0xBF) {
        out.type = Type::STR;
        out.length = code & 0x1F;
    } else {
        switch (code) {
            case 0xC0:
                out.type = Type::NIL;
                return true;
            case 0xC2:
            case 0xC3:
                out.type = Type::BOOL;
                out.boolean = code == 0xC3;
                return true;
            case 0xC4: case 0xC5: case 0xC6:
                out.type = Type::BIN;
                lengthBytes = size_t(1) << (code - 0xC4);
                break;
            case 0xCA: {
                if (!take(4, p)) return false;
                const uint32_t bits = static_cast<uint32_t>(bigEndian(p, 4));
                float value;
                memcpy(&value, &bits, sizeof(value));
                out.type = Type::FLOAT;
                out.real = value;
                return true;
            }
            case 0xCB: {
                if (!take(8, p)) return false;
                const uint64_t bits = bigEndian(p, 8);
                memcpy(&out.real, &bits, sizeof(out.real));
                out.type = Type::FLOAT;
                return true;
            }
            case 0xCC: case 0xCD: case 0xCE: case 0xCF: {
                const size_t n = size_t(1) << (code - 0xCC);
                if (!take(n, p)) return false;
                out.type = Type::UINT;
                out.uinteger = bigEndian(p, n);
                return true;
            }
            case 0xD0: case 0xD1: case 0xD2: case 0xD3: {
                const size_t n = size_t(1) << (code - 0xD0);
                if (!take(n, p)) return false;
                // Rozszerzenie znaku z n bajtów; liczba nieujemna w kodowaniu ze znakiem to zwykły int.
                uint64_t bits = bigEndian(p, n);
                if (n < 8 && (bits >> (8 * n - 1))) bits |= ~uint64_t(0) << (8 * n);
                const int64_t value = static_cast<int64_t>(bits);
                if (value < 0) {
                    out.type = Type::INT;
                    out.integer = value;
                } else {
                    out.type = Type::UINT;
                    out.uinteger = static_cast<uint64_t>(value);
                }
                return true;
            }
            case 0xD9: case 0xDA: case 0xDB:
                out.type = Type::STR;
                lengthBytes = size_t(1) << (code - 0xD9);
                break;
            case 0xDC: case 0xDD:
                out.type = Type::ARRAY;
                lengthBytes = code == 0xDC ? 2 : 4;
                break;
            case 0xDE: case 0xDF:
                out.type = Type::MAP;
                lengthBytes = code == 0xDE ? 2 : 4;
                break;
            default:   // 0xC1 (ReservedCodeException) i ext 0xC7–0xC9, 0xD4–0xD8 (odstępstwo)
                return false;
        }
    }
    if (lengthBytes) {
        if (!take(lengthBytes, p)) return false;
        out.length = static_cast<uint32_t>(bigEndian(p, lengthBytes));
    }
    switch (out.type) {
        case Type::ARRAY:
            // Każdy element ma co najmniej 1 B, więc przy większej liczbie Python dochodzi do końca
            // danych; rdzeń kończy od razu, bez pętli po 2^32 elementach.
            return out.length <= remaining();
        case Type::MAP:
            return out.length <= remaining() / 2;
        case Type::STR:
            return take(out.length, out.data) && validUtf8(out.data, out.length);
        default:   // BIN
            return take(out.length, out.data);
    }
}

// umsgpack.py: _unpack, _unpack_array i _unpack_map bez rekurencji: levels to otwarte tablice i mapy,
// a remaining liczy elementy (w mapie klucze i wartości) do końca każdej z nich.
bool Reader::skip(uint8_t maxDepth) {
    struct Level {
        size_t start;       // pozycja pierwszego klucza mapy
        size_t total;       // elementy: w tablicy wartości, w mapie klucze i wartości
        size_t remaining;
        bool isMap;
    };
    Level levels[MAX_DEPTH];
    if (maxDepth > MAX_DEPTH) maxDepth = MAX_DEPTH;
    uint8_t depth = 0;
    do {
        Level* parent = depth ? &levels[depth - 1] : nullptr;
        const size_t done = parent ? parent->total - parent->remaining : 0;
        const bool isKey = parent && parent->isMap && done % 2 == 0;
        Item item;
        if (!read(item)) return false;
        // _unpack_map: klucz sprawdzony z kluczami już przeczytanymi, zanim przyjdzie wartość.
        if (isKey && (!allowedKey(item) || keySeen(parent->start, done / 2, item))) return false;
        if (parent) --parent->remaining;
        if (item.type == Type::ARRAY || item.type == Type::MAP) {
            if (depth == maxDepth) return false;
            // read zapewnia, że liczba elementów nie przekracza pozostałych bajtów, więc mieści się w size_t.
            const size_t count = item.type == Type::MAP ? size_t(item.length) * 2 : item.length;
            levels[depth++] = Level{position_, count, count, item.type == Type::MAP};
        }
        while (depth && levels[depth - 1].remaining == 0) --depth;
    } while (depth);
    return true;
}

// Czy klucz był już wśród index pierwszych kluczy mapy. Wcześniejszych par nie ma gdzie zapamiętać,
// więc są czytane ponownie od początku mapy; praca rośnie najwyżej z kwadratem długości pakietu.
bool Reader::keySeen(size_t mapStart, size_t index, const Item& key) const {
    Reader earlier(data_, length_);
    earlier.position_ = mapStart;
    for (size_t i = 0; i < index; ++i) {
        Item other;
        if (!earlier.read(other) || sameKey(key, other) || !earlier.skipChecked()) return true;
    }
    return false;
}

// Przejście przez wartość, którą skip już sprawdził: tylko licznik elementów do przeczytania.
bool Reader::skipChecked() {
    size_t pending = 1;
    while (pending) {
        Item item;
        if (!read(item)) return false;
        --pending;
        if (item.type == Type::ARRAY) pending += item.length;
        if (item.type == Type::MAP) pending += size_t(item.length) * 2;
    }
    return true;
}

bool validate(const uint8_t* data, size_t length, uint8_t maxDepth, size_t* consumed) {
    Reader reader(data, length);
    if (!reader.skip(maxDepth)) return false;
    if (consumed) *consumed = reader.position();
    return true;
}

void Writer::put(const uint8_t* data, size_t length) {
    if (!ok_ || length > capacity_ - length_) {
        ok_ = false;
        return;
    }
    if (length) memcpy(out_ + length_, data, length);
    length_ += length;
}

void Writer::header(uint8_t code, uint64_t value, size_t bytes) {
    uint8_t buffer[9];
    buffer[0] = code;
    for (size_t i = 0; i < bytes; ++i) buffer[1 + i] = static_cast<uint8_t>(value >> (8 * (bytes - 1 - i)));
    put(buffer, 1 + bytes);
}

void Writer::array(size_t count) {
    if (count < 16) header(static_cast<uint8_t>(0x90 | count), 0, 0);
    else if (count <= 0xFFFF) header(0xDC, count, 2);
    else ok_ = false;
}

void Writer::map(size_t pairs) {
    if (pairs < 16) header(static_cast<uint8_t>(0x80 | pairs), 0, 0);
    else if (pairs <= 0xFFFF) header(0xDE, pairs, 2);
    else ok_ = false;
}

void Writer::float64(double value) {
    uint64_t bits;
    memcpy(&bits, &value, sizeof(bits));
    header(0xCB, bits, 8);
}

void Writer::bin(const uint8_t* data, size_t length) {
    if (length <= 0xFF) header(0xC4, length, 1);
    else if (length <= 0xFFFF) header(0xC5, length, 2);
    else ok_ = false;
    put(data, length);
}

}  // namespace msgpack
}  // namespace rnscore
