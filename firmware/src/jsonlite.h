// SPDX-License-Identifier: MIT
// Mały skaner JSON do wierszy protokołu USB i tablic SA1: wyznacza zakresy wartości w tekście
// bez alokacji, odczytuje pola obiektu i elementy tablicy, dekoduje i koduje napisy.
// Bez zależności od Arduino; sprawdzany na komputerze.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace json {

enum class Kind : uint8_t { NONE, OBJECT, ARRAY, STRING, NUMBER, TRUE_, FALSE_, NULL_ };

struct Value {
    Kind kind = Kind::NONE;
    const char* begin = nullptr;  // pierwszy znak wartości (cudzysłów dla napisu)
    size_t length = 0;            // długość w bajtach łącznie z nawiasami albo cudzysłowami
};

// Skanuje jedną wartość od p (po białych znakach); przesuwa p za nią. false przy błędzie składni.
bool scan(const char*& p, Value& out);
// Cały tekst musi być jedną wartością (plus białe znaki).
bool parse(const char* text, Value& out);
// Pole obiektu o danym kluczu (bez sekwencji ucieczki w kluczu); false, gdy brak.
bool field(const Value& object, const char* key, Value& out);
// Element tablicy o danym indeksie; liczba elementów.
bool item(const Value& array, size_t index, Value& out);
size_t count(const Value& array);  // elementy tablicy albo pola obiektu; 0 dla innych
// Liczba całkowita bez ułamka i wykładnika w zakresie int64.
bool integer(const Value& value, int64_t& out);
// Napis zdekodowany do UTF-8 (sekwencje \", \\, \/, \b, \f, \n, \r, \t, \uXXXX z parami zastępczymi);
// false przy błędnej sekwencji albo braku miejsca. Zwraca długość w bajtach.
bool string(const Value& value, char* out, size_t size, size_t* length = nullptr);
// Napis w JSON z cudzysłowami; znaki spoza ASCII bez zamiany na \u (jak koder modelu). false, gdy brak miejsca.
bool quote(const char* text, char* out, size_t size, size_t* length = nullptr);
// Surowy tekst wartości skopiowany z zerem na końcu; false, gdy brak miejsca.
bool raw(const Value& value, char* out, size_t size);

}  // namespace json
