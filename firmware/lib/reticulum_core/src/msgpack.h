// SPDX-License-Identifier: LicenseRef-Reticulum AND MIT
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2013-2020 vsergeev / Ivan (Vanya) A. Sergeev
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// MessagePack w podzbiorze, którego potrzebuje LXMF, bez sterty: koder do stałego bufora i dekoder
// wskazujący do bufora wejścia. Wzorcem jest u-msgpack-python 2.7.1 dołączony do Reticulum e40191b
// (RNS/vendor/umsgpack.py, licencja MIT), którego używa LXMF c3ff2d6 (LXMessage.pack,
// LXMessage.unpack_from_bytes). Koder składa te same bajty co packb dla typów, które ma. Dekoder
// przyjmuje podzbiór tego, co przyjmuje unpackb; każde odstępstwo jest odrzuceniem wejścia, którego
// LXMessage.pack nie składa (firmware/reticulum-core.md, tabela różnic):
// - zagnieżdżenie tablic i map głębsze niż maxDepth (Python: do granicy rekurencji interpretera);
// - klucz mapy inny niż nil, bool, liczba całkowita, str i bin (Python: także float, ext, znacznik
//   czasu i tablica zamieniana na krotkę).
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace rnscore {
namespace msgpack {

// Typ wartości po rozbiorze. Liczba całkowita ≥ 0 jest UINT, ujemna INT, bez względu na kodowanie
// (umsgpack.py: _unpack_integer daje int Pythona). EXT obejmuje znacznik czasu (typ -1).
enum class Type : uint8_t { NIL, BOOL, UINT, INT, FLOAT32, FLOAT64, STR, BIN, ARRAY, MAP, EXT };

struct Item {
    Type type;
    bool boolean;          // BOOL
    uint64_t uinteger;     // UINT
    int64_t integer;       // INT (< 0)
    double real;           // FLOAT32 i FLOAT64
    const uint8_t* data;   // STR, BIN, EXT: bajty wewnątrz bufora wejścia
    uint32_t length;       // STR, BIN, EXT: liczba bajtów; ARRAY: elementów; MAP: par
    int8_t extType;        // EXT
};

// Czytnik jednej wartości po drugiej z bufora, który musi żyć dłużej niż wyniki.
class Reader {
public:
    Reader(const uint8_t* data, size_t length) : data_(data), length_(length) {}

    // umsgpack.py: _unpack bez zagnieżdżonych elementów: nagłówek i dane wartości prostej; dla ARRAY i MAP
    // tylko nagłówek (elementy czyta się dalej). Fałsz: koniec danych (InsufficientDataException), kod
    // 0xC1 (ReservedCodeException), napis bez poprawnego UTF-8 (InvalidStringException), znacznik czasu
    // o złej długości (UnsupportedTimestampException) albo spoza zakresu datetime (OverflowError).
    // Przy fałszu pozycja jest nieokreślona.
    bool read(Item& out);

    // umsgpack.py: _unpack całej wartości z elementami, z tymi samymi błędami co read, a w mapach także
    // z kluczem powtórzonym (DuplicateKeyException) i niedozwolonym (odstępstwo w opisie pliku).
    // maxDepth: ile poziomów tablic i map wolno otworzyć (0: tylko wartość prosta). Przesuwa pozycję za
    // wartość; przy fałszu pozycja jest nieokreślona.
    bool skip(uint8_t maxDepth);

    size_t position() const { return position_; }
    size_t remaining() const { return length_ - position_; }

private:
    bool take(size_t n, const uint8_t*& out);
    bool skipMap(uint32_t pairs, uint8_t maxDepth);
    bool skipTrusted();

    const uint8_t* data_;
    size_t length_;
    size_t position_ = 0;
};

// umsgpack.py: unpackb: jedna pełna wartość od początku bufora; bajty za nią są pomijane, jak w Pythonie
// (unpackb czyta z io.BytesIO tylko pierwszą wartość). consumed: długość wartości (może być nullptr).
bool validate(const uint8_t* data, size_t length, uint8_t maxDepth, size_t* consumed);

// Pisarz do stałego bufora; po przepełnieniu nic więcej nie zapisuje, a ok() zwraca fałsz.
// Kodowanie najkrótsze, jak w umsgpack.py (_pack_integer, _pack_string, _pack_binary, _pack_array,
// _pack_map, _pack_ext); liczba zmiennoprzecinkowa zawsze jako float64 (_pack_float, precyzja
// "double" na każdej platformie z 53-bitową mantysą).
class Writer {
public:
    Writer(uint8_t* out, size_t capacity) : out_(out), capacity_(capacity) {}

    void nil();
    void boolean(bool value);
    void uinteger(uint64_t value);
    void integer(int64_t value);   // ≥ 0 jak uinteger
    void float64(double value);
    void str(const uint8_t* data, size_t length);   // bajty UTF-8; poprawność sprawdza wywołujący
    void bin(const uint8_t* data, size_t length);
    void array(uint32_t count);   // elementy zapisuje się dalej
    void map(uint32_t pairs);     // klucz i wartość na przemian
    void ext(int8_t type, const uint8_t* data, size_t length);

    bool ok() const { return ok_; }
    size_t length() const { return length_; }

private:
    void put(const uint8_t* data, size_t length);
    void header(uint8_t code, uint64_t value, size_t bytes);

    uint8_t* out_;
    size_t capacity_;
    size_t length_ = 0;
    bool ok_ = true;
};

}  // namespace msgpack
}  // namespace rnscore
