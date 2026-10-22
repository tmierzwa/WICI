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
        uint8_t low = 0x80, high = 0xBF;   // zakres pierwszego bajtu kontynuacji
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

// umsgpack.py: _unpack_ext_timestamp: 4, 8 albo 12 B, a wynik musi się zmieścić w datetime
// (rok 1–9999; inaczej OverflowError przy _epoch + timedelta). Postaci 4 i 8 B zawsze się mieszczą.
bool validTimestamp(const uint8_t* p, size_t n) {
    if (n == 4 || n == 8) return true;
    if (n != 12) return false;
    constexpr int64_t MIN_S = -62135596800;    // 0001-01-01 00:00:00 UTC względem 1970-01-01
    constexpr int64_t MAX_S = 253402300799;    // 9999-12-31 23:59:59 UTC
    const int64_t seconds = static_cast<int64_t>(bigEndian(p + 4, 8));
    const int64_t micro = static_cast<int64_t>(bigEndian(p, 4) / 1000);   // < 4,3 s
    if (seconds < MIN_S - 5 || seconds > MAX_S) return false;
    const int64_t total = seconds * 1000000 + micro;
    return total >= MIN_S * 1000000 && total <= MAX_S * 1000000 + 999999;
}

// Klucz mapy dopuszczony przez rdzeń (odstępstwo w msgpack.h).
bool allowedKey(const Item& key) {
    switch (key.type) {
        case Type::NIL:
        case Type::BOOL:
        case Type::UINT:
        case Type::INT:
        case Type::STR:
        case Type::BIN:
            return true;
        default:
            return false;
    }
}

// Równość kluczy jak w Pythonie (k in d): True == 1, False == 0, str i bytes różne od siebie.
bool sameKey(const Item& a, const Item& b) {
    auto number = [](const Item& x, bool& negative, uint64_t& magnitude) {
        if (x.type == Type::BOOL) {
            negative = false;
            magnitude = x.boolean ? 1 : 0;
        } else if (x.type == Type::UINT) {
            negative = false;
            magnitude = x.uinteger;
        } else if (x.type == Type::INT) {
            negative = true;
            magnitude = static_cast<uint64_t>(x.integer);   // wartość ujemna, porównywana bitowo
        } else {
            return false;
        }
        return true;
    };
    bool na = false, nb = false;
    uint64_t ma = 0, mb = 0;
    if (number(a, na, ma) && number(b, nb, mb)) return na == nb && ma == mb;
    if (a.type != b.type) return false;
    if (a.type == Type::NIL) return true;
    if (a.type == Type::STR || a.type == Type::BIN) return a.length == b.length && memcmp(a.data, b.data, a.length) == 0;
    return false;
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
    size_t lengthBytes = 0;   // bajty długości po kodzie (str, bin, ext, array, map)
    size_t fixedLength = 0;   // fixext
    if (code <= 0x7F) {
        out.type = Type::UINT;
        out.uinteger = code;
        return true;
    } else if (code >= 0xE0) {
        out.type = Type::INT;
        out.integer = static_cast<int8_t>(code);
        return true;
    } else if ((code & 0xF0) == 0x80 || (code & 0xF0) == 0x90) {
        out.type = (code & 0xF0) == 0x80 ? Type::MAP : Type::ARRAY;
        out.length = code & 0x0F;
    } else if ((code & 0xE0) == 0xA0) {
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
            case 0xC7: case 0xC8: case 0xC9:
                out.type = Type::EXT;
                lengthBytes = size_t(1) << (code - 0xC7);
                break;
            case 0xCA: case 0xCB: {
                const size_t n = code == 0xCA ? 4 : 8;
                if (!take(n, p)) return false;
                const uint64_t bits = bigEndian(p, n);
                if (n == 4) {
                    const uint32_t bits32 = static_cast<uint32_t>(bits);
                    float f;
                    memcpy(&f, &bits32, sizeof(f));
                    out.type = Type::FLOAT32;
                    out.real = f;
                } else {
                    memcpy(&out.real, &bits, sizeof(out.real));
                    out.type = Type::FLOAT64;
                }
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
            case 0xD4: case 0xD5: case 0xD6: case 0xD7: case 0xD8:
                out.type = Type::EXT;
                fixedLength = size_t(1) << (code - 0xD4);
                break;
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
            default:   // 0xC1: ReservedCodeException
                return false;
        }
    }
    if (lengthBytes) {
        if (!take(lengthBytes, p)) return false;
        out.length = static_cast<uint32_t>(bigEndian(p, lengthBytes));
    } else if (fixedLength) {
        out.length = static_cast<uint32_t>(fixedLength);
    }
    switch (out.type) {
        case Type::ARRAY:
        case Type::MAP: {
            // Każdy element ma co najmniej 1 B: przy większej liczbie Python dochodzi do końca danych
            // (InsufficientDataException), więc wynik jest ten sam bez przechodzenia pętli.
            const uint64_t least = uint64_t(out.length) * (out.type == Type::MAP ? 2 : 1);
            return least <= remaining();
        }
        case Type::EXT:
            if (!take(1, p)) return false;
            out.extType = static_cast<int8_t>(p[0]);
            if (!take(out.length, out.data)) return false;
            return out.extType != -1 || validTimestamp(out.data, out.length);
        case Type::STR:
            return take(out.length, out.data) && validUtf8(out.data, out.length);
        default:   // BIN
            return take(out.length, out.data);
    }
}

bool Reader::skip(uint8_t maxDepth) {
    Item item;
    if (!read(item)) return false;
    if (item.type == Type::ARRAY) {
        if (!maxDepth) return false;
        for (uint32_t i = 0; i < item.length; ++i) {
            if (!skip(maxDepth - 1)) return false;
        }
        return true;
    }
    if (item.type == Type::MAP) return maxDepth && skipMap(item.length, maxDepth - 1);
    return true;
}

// umsgpack.py: _unpack_map: klucz, sprawdzenie z kluczami już przeczytanymi, wartość. Wcześniejsze pary
// są czytane ponownie od początku mapy, bo nie ma gdzie ich zapamiętać; liczba par jest ograniczona
// długością danych (read), więc praca rośnie najwyżej z kwadratem długości pakietu.
bool Reader::skipMap(uint32_t pairs, uint8_t maxDepth) {
    const size_t first = position_;
    for (uint32_t i = 0; i < pairs; ++i) {
        Item key;
        if (!read(key) || !allowedKey(key)) return false;
        Reader earlier(data_, length_);
        earlier.position_ = first;
        for (uint32_t j = 0; j < i; ++j) {
            Item other;
            if (!earlier.read(other) || sameKey(key, other) || !earlier.skipTrusted()) return false;
        }
        if (!skip(maxDepth)) return false;
    }
    return true;
}

// Przejście przez wartość, którą skip już sprawdził (bez ponownego sprawdzania kluczy map).
bool Reader::skipTrusted() {
    Item item;
    if (!read(item)) return false;
    const uint64_t count = item.type == Type::ARRAY ? item.length : item.type == Type::MAP ? uint64_t(item.length) * 2 : 0;
    for (uint64_t i = 0; i < count; ++i) {
        if (!skipTrusted()) return false;
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

void Writer::nil() { header(0xC0, 0, 0); }

void Writer::boolean(bool value) { header(value ? 0xC3 : 0xC2, 0, 0); }

// umsgpack.py: _pack_integer.
void Writer::uinteger(uint64_t value) {
    if (value < 0x80) {
        header(static_cast<uint8_t>(value), 0, 0);
    } else if (value <= 0xFF) {
        header(0xCC, value, 1);
    } else if (value <= 0xFFFF) {
        header(0xCD, value, 2);
    } else if (value <= 0xFFFFFFFF) {
        header(0xCE, value, 4);
    } else {
        header(0xCF, value, 8);
    }
}

void Writer::integer(int64_t value) {
    const uint64_t bits = static_cast<uint64_t>(value);
    if (value >= 0) {
        uinteger(bits);
    } else if (value >= -32) {
        header(static_cast<uint8_t>(bits), 0, 0);
    } else if (value >= INT8_MIN) {
        header(0xD0, bits, 1);
    } else if (value >= INT16_MIN) {
        header(0xD1, bits, 2);
    } else if (value >= INT32_MIN) {
        header(0xD2, bits, 4);
    } else {
        header(0xD3, bits, 8);
    }
}

// umsgpack.py: _pack_float z precyzją "double".
void Writer::float64(double value) {
    uint64_t bits;
    memcpy(&bits, &value, sizeof(bits));
    header(0xCB, bits, 8);
}

// umsgpack.py: _pack_string (bez trybu zgodności ze starą specyfikacją).
void Writer::str(const uint8_t* data, size_t length) {
    if (length < 32) {
        header(static_cast<uint8_t>(0xA0 | length), 0, 0);
    } else if (length <= 0xFF) {
        header(0xD9, length, 1);
    } else if (length <= 0xFFFF) {
        header(0xDA, length, 2);
    } else if (uint64_t(length) <= 0xFFFFFFFF) {
        header(0xDB, length, 4);
    } else {
        ok_ = false;
    }
    put(data, length);
}

// umsgpack.py: _pack_binary.
void Writer::bin(const uint8_t* data, size_t length) {
    if (length <= 0xFF) {
        header(0xC4, length, 1);
    } else if (length <= 0xFFFF) {
        header(0xC5, length, 2);
    } else if (uint64_t(length) <= 0xFFFFFFFF) {
        header(0xC6, length, 4);
    } else {
        ok_ = false;
    }
    put(data, length);
}

// umsgpack.py: _pack_array.
void Writer::array(uint32_t count) {
    if (count < 16) {
        header(static_cast<uint8_t>(0x90 | count), 0, 0);
    } else if (count <= 0xFFFF) {
        header(0xDC, count, 2);
    } else {
        header(0xDD, count, 4);
    }
}

// umsgpack.py: _pack_map.
void Writer::map(uint32_t pairs) {
    if (pairs < 16) {
        header(static_cast<uint8_t>(0x80 | pairs), 0, 0);
    } else if (pairs <= 0xFFFF) {
        header(0xDE, pairs, 2);
    } else {
        header(0xDF, pairs, 4);
    }
}

// umsgpack.py: _pack_ext: fixext dla 1, 2, 4, 8 i 16 B, inaczej ext 8, 16 albo 32.
void Writer::ext(int8_t type, const uint8_t* data, size_t length) {
    const uint8_t t = static_cast<uint8_t>(type);
    switch (length) {
        case 1: header(0xD4, t, 1); break;
        case 2: header(0xD5, t, 1); break;
        case 4: header(0xD6, t, 1); break;
        case 8: header(0xD7, t, 1); break;
        case 16: header(0xD8, t, 1); break;
        default:
            if (length <= 0xFF) {
                header(0xC7, (uint64_t(length) << 8) | t, 2);
            } else if (length <= 0xFFFF) {
                header(0xC8, (uint64_t(length) << 8) | t, 3);
            } else if (uint64_t(length) <= 0xFFFFFFFF) {
                header(0xC9, (uint64_t(length) << 8) | t, 5);
            } else {
                ok_ = false;
            }
    }
    put(data, length);
}

}  // namespace msgpack
}  // namespace rnscore
