// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
#include "identity.h"

#include <string.h>

#include <Crypto.h>
#include <Curve25519.h>
#include <Ed25519.h>

#include "hash.h"

namespace rnscore {

namespace {

constexpr size_t HALF = KEY_SIZE / 2;

// Rząd grupy Ed25519 L = 2^252 + 27742317777372353535851937790883648493, little-endian (RFC 8032).
constexpr uint8_t ED25519_L[32] = {0xed, 0xd3, 0xf5, 0x5c, 0x1a, 0x63, 0x12, 0x58, 0xd6, 0x9c, 0xf7,
                                   0xa2, 0xde, 0xf9, 0xde, 0x14, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10};

// S < L, porównanie od najstarszego bajtu. Podpis jest jawny, więc stały czas nie jest potrzebny.
bool canonicalScalar(const uint8_t s[32]) {
    for (int i = 31; i >= 0; --i) {
        if (s[i] != ED25519_L[i]) return s[i] < ED25519_L[i];
    }
    return false;
}

}  // namespace

void publicKey(const uint8_t privateKey[KEY_SIZE], uint8_t out[KEY_SIZE]) {
    uint8_t scalar[HALF];
    memcpy(scalar, privateKey, HALF);
    scalar[0] &= 0xF8;
    scalar[31] = (scalar[31] & 0x7F) | 0x40;
    Curve25519::eval(out, scalar, nullptr);   // punkt bazowy 9: zawsze poprawny
    clean(scalar, sizeof(scalar));
    Ed25519::derivePublicKey(out + HALF, privateKey + HALF);
}

void identityHash(const uint8_t publicKey[KEY_SIZE], uint8_t out[TRUNCATED_HASH_SIZE]) {
    truncatedHash(publicKey, KEY_SIZE, out);
}

void sign(const uint8_t privateKey[KEY_SIZE], const uint8_t publicKey[KEY_SIZE], const uint8_t* message, size_t length,
          uint8_t out[SIGNATURE_SIZE]) {
    Ed25519::sign(out, privateKey + HALF, publicKey + HALF, message, length);
}

bool validate(const uint8_t publicKey[KEY_SIZE], const uint8_t* signature, size_t signatureLength,
              const uint8_t* message, size_t length) {
    if (signatureLength != SIGNATURE_SIZE || !canonicalScalar(signature + 32)) return false;
    return Ed25519::verify(signature, publicKey + HALF, message, length);
}

}  // namespace rnscore
