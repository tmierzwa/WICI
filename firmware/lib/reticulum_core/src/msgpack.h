// SPDX-License-Identifier: LicenseRef-Reticulum AND MIT
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2013-2020 vsergeev / Ivan (Vanya) A. Sergeev
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// MessagePack w podzbiorze, którego używa LXMF, bez sterty i bez rekurencji. Wzorcem jest
// u-msgpack-python 2.7.1 dołączony do Reticulum e40191b (RNS/vendor/umsgpack.py, licencja MIT), którego
// używa LXMF c3ff2d6 (LXMessage.pack, LXMessage.unpack_from_bytes).
// - Koder ma tylko to, co składa LXMessage.pack: tablicę, mapę, float64 i bin; bajty są te same co z packb.
// - Dekoder sprawdza wartość z wrogiego pakietu tak jak unpackb i przyjmuje podzbiór tego, co przyjmuje
//   Python. Odstępstwa są wyłącznie odrzuceniami wejścia, którego LXMessage.pack nie składa
//   (firmware/reticulum-core.md, tabela różnic): zagnieżdżenie głębsze niż MAX_DEPTH, typ ext (także
//   znacznik czasu) i klucz mapy inny niż nil, bool, liczba całkowita, str i bin.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace rnscore {
namespace msgpack {

// Najwięcej poziomów tablic i map jednej wartości; LXMessage.pack składa 2 (wiadomość i mapa pól).
constexpr uint8_t MAX_DEPTH = 8;

// Typ wartości po rozbiorze. Liczba całkowita ≥ 0 to UINT, ujemna to INT, bez względu na kodowanie
// (umsgpack.py: _unpack_integer daje int Pythona); float32 i float64 to FLOAT.
enum class Type : uint8_t { NIL, BOOL, UINT, INT, FLOAT, STR, BIN, ARRAY, MAP };

struct Item {
    Type type;
    bool boolean;          // BOOL
    uint64_t uinteger;     // UINT
    int64_t integer;       // INT (< 0)
    double real;           // FLOAT
    const uint8_t* data;   // STR, BIN: bajty wewnątrz bufora wejścia
    uint32_t length;       // STR, BIN: liczba bajtów; ARRAY: elementów; MAP: par
};

// Czytnik kolejnych wartości z bufora, który musi żyć dłużej niż wyniki.
class Reader {
public:
    Reader(const uint8_t* data, size_t length) : data_(data), length_(length) {}

    // umsgpack.py: _unpack bez elementów: nagłówek i dane wartości prostej; dla ARRAY i MAP tylko nagłówek.
    // Fałsz: koniec danych (InsufficientDataException), kod 0xC1 (ReservedCodeException), napis bez
    // poprawnego UTF-8 (InvalidStringException), ext (odstępstwo) albo tablica lub mapa z większą liczbą
    // elementów niż pozostałe bajty (Python dochodzi wtedy do końca danych). Przy fałszu pozycja jest
    // nieokreślona.
    bool read(Item& out);

    // umsgpack.py: _unpack całej wartości z elementami: błędy jak w read, a w mapach także klucz
    // powtórzony (DuplicateKeyException) albo niedozwolony (odstępstwo). maxDepth: ile poziomów tablic
    // i map wolno otworzyć, najwyżej MAX_DEPTH (0: tylko wartość prosta). Bez rekurencji: stos poziomów
    // ma stały rozmiar. Przesuwa pozycję za wartość.
    bool skip(uint8_t maxDepth);

    size_t position() const { return position_; }
    size_t remaining() const { return length_ - position_; }

private:
    bool take(size_t n, const uint8_t*& out);
    bool keySeen(size_t mapStart, size_t index, const Item& key) const;
    bool skipChecked();

    const uint8_t* data_;
    size_t length_;
    size_t position_ = 0;
};

// umsgpack.py: unpackb: jedna pełna wartość od początku bufora; bajty za nią są pomijane jak w Pythonie
// (unpackb czyta z io.BytesIO tylko pierwszą wartość). consumed: długość wartości (może być nullptr).
bool validate(const uint8_t* data, size_t length, uint8_t maxDepth, size_t* consumed);

// Pisarz do stałego bufora; po przepełnieniu albo przy długości ponad 65 535 (więcej niż pakiet) nic
// więcej nie zapisuje, a ok() zwraca fałsz. Kodowanie najkrótsze, jak umsgpack.py.
class Writer {
public:
    Writer(uint8_t* out, size_t capacity) : out_(out), capacity_(capacity) {}

    void array(size_t count);   // _pack_array; elementy zapisuje się dalej
    void map(size_t pairs);     // _pack_map; klucz i wartość na przemian
    void float64(double value);   // _pack_float z precyzją "double" (53-bitowa mantysa)
    void bin(const uint8_t* data, size_t length);   // _pack_binary

    bool ok() const { return ok_; }
    size_t length() const { return length_; }

private:
    void header(uint8_t code, uint64_t value, size_t bytes);
    void put(const uint8_t* data, size_t length);

    uint8_t* out_;
    size_t capacity_;
    size_t length_ = 0;
    bool ok_ = true;
};

}  // namespace msgpack
}  // namespace rnscore
