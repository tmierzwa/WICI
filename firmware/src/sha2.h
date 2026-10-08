// SPDX-License-Identifier: MIT
// SHA-256 (FIPS 180-4) i HMAC-SHA-256 (RFC 2104) dla części stacji bez stosu Reticulum:
// skrót dokumentu `configure` (docs/spec/protokol-usb.md, "Transfery dzielone na części"),
// adresy celów z kluczy publicznych z karty odbiorcy (Reticulum: skrót tożsamości = pierwsze
// 16 B SHA-256 klucza, adres celu = pierwsze 16 B SHA-256(skrót nazwy 10 B ‖ skrót tożsamości)),
// odcisk karty stacji i generator HMAC-DRBG (drbg.h). Bez zależności od Arduino; sprawdzany na
// komputerze wobec hashlib.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace sha2 {

constexpr size_t DIGEST = 32;
constexpr size_t BLOCK = 64;

class Hash {
public:
    Hash() { reset(); }
    void reset();
    void update(const uint8_t* data, size_t length);
    void update(const char* text);   // bez kończącego zera
    void finish(uint8_t out[DIGEST]);

private:
    void block(const uint8_t* data);
    uint32_t state_[8];
    uint8_t buffer_[BLOCK];
    size_t used_ = 0;
    uint64_t bytes_ = 0;
};

void digest(const uint8_t* data, size_t length, uint8_t out[DIGEST]);

class Hmac {
public:
    Hmac(const uint8_t* key, size_t keyLength);
    void update(const uint8_t* data, size_t length) { inner_.update(data, length); }
    void finish(uint8_t out[DIGEST]);

private:
    Hash inner_;
    uint8_t outerKey_[BLOCK];
};

// Adres celu Reticulum (16 B) z klucza publicznego tożsamości (64 B) i nazwy "app.aspekt".
void destinationHash(const uint8_t publicKey[64], const char* name, uint8_t out[16]);

}  // namespace sha2
