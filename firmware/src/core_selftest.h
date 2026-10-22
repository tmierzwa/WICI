// SPDX-License-Identifier: MIT
// Samotest kryptografii rdzenia Reticulum na płytce (firmware/README.md, „Samotest rdzenia na płytce”):
// wektory z Reticulum w Pythonie przez funkcje rdzenia skompilowane tak jak w obrazie. Sprawdza to, czego
// próby na komputerze nie obejmują: AES-256 sprzętowy na ESP32-S3 (biblioteka Crypto, AESEsp32.cpp),
// arytmetykę Curve25519 i Ed25519 skompilowaną kompilatorem płytki, i podaje czas każdej operacji.
// Tylko w obrazach z rdzeniem (env:bench-a-core, env:l0-core, WICI_RNS_CORE) i w próbach na komputerze.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace coreselftest {

struct Result {
    const char* name;
    bool ok;
    uint32_t us;   // czas próby w µs z zegara podanego do run
};

// Próby przy starcie, przed rnsnode::begin: token (odszyfrowanie i szyfrowanie z kluczem efemerycznym
// i IV z wektora), podpis i weryfikacja podpisu poprawnego. Obejmują wszystkie prymitywy kryptograficzne
// (X25519, Ed25519, AES-256-CBC, SHA-256, SHA-512, HMAC, HKDF); ogłoszenie i IFAC tylko w RNS SELFTEST.
constexpr size_t QUICK = 4;
// Wszystkie próby (polecenie RNS SELFTEST): dodatkowo odrzucenie podpisu zmienionej wiadomości, klucz
// publiczny z prywatnego, przyjęcie i złożenie ogłoszenia, klucz i kod IFAC.
constexpr size_t COUNT = 9;

// Wykonuje pierwsze count prób (najwyżej COUNT) i wpisuje wyniki do out; prawda, gdy wszystkie zgodne.
// Stos: około 2,5 KB (najgłębsza ścieżka rdzenia i bufory wektorów).
bool run(Result* out, size_t count, uint32_t (*micros)());

}  // namespace coreselftest
