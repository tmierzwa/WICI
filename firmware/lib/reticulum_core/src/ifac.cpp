// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
#include "ifac.h"

#include <string.h>

#include <Crypto.h>

#include "hash.h"
#include "hkdf.h"
#include "identity.h"

namespace rnscore {

namespace {

// RNS/Reticulum.py: Reticulum.IFAC_SALT.
constexpr uint8_t IFAC_SALT[32] = {0xad, 0xf5, 0x4d, 0x88, 0x2c, 0x9a, 0x9b, 0x80, 0x77, 0x1e, 0xb4,
                                   0x99, 0x5d, 0x70, 0x2d, 0x4a, 0x3e, 0x73, 0x33, 0x91, 0xb2, 0xa0,
                                   0xf5, 0x3f, 0x41, 0x6d, 0x9f, 0x90, 0x7e, 0x55, 0xcf, 0xf8};

constexpr size_t WIRE_MAX = MTU + IFAC_MAX_SIZE;

// Kod: ostatnie size B podpisu pakietu bez IFAC (ifac_identity.sign(raw)[-ifac_size:]).
void tag(const Ifac& ifac, const uint8_t* raw, size_t length, uint8_t out[IFAC_MAX_SIZE]) {
    uint8_t signature[SIGNATURE_SIZE];
    sign(ifac.key, ifac.publicKey, raw, length, signature);
    memcpy(out, signature + SIGNATURE_SIZE - ifac.size, ifac.size);
}

}  // namespace

bool ifacSetup(const char* networkName, const char* passphrase, size_t size, Ifac& out) {
    if ((!networkName && !passphrase) || size < IFAC_MIN_SIZE || size > IFAC_MAX_SIZE) return false;
    uint8_t origin[2 * HASH_SIZE];
    size_t used = 0;
    const char* const parts[2] = {networkName, passphrase};
    for (const char* text : parts) {
        if (!text) continue;
        fullHash(reinterpret_cast<const uint8_t*>(text), strlen(text), origin + used);
        used += HASH_SIZE;
    }
    uint8_t originHash[HASH_SIZE];
    fullHash(origin, used, originHash);
    hkdf(originHash, sizeof(originHash), IFAC_SALT, sizeof(IFAC_SALT), out.key, KEY_SIZE);
    publicKey(out.key, out.publicKey);
    out.size = size;
    clean(origin, sizeof(origin));
    clean(originHash, sizeof(originHash));
    return true;
}

size_t ifacApply(const Ifac& ifac, const uint8_t* raw, size_t length, uint8_t* wire, size_t capacity) {
    const size_t total = length + ifac.size;
    if (length < 2 || length > MTU || total > capacity) return 0;
    uint8_t code[IFAC_MAX_SIZE];
    tag(ifac, raw, length, code);
    // Maska: hkdf(len(raw) + ifac_size, kod, sól = ifac_key); kod zostaje jawny.
    uint8_t mask[WIRE_MAX];
    hkdf(code, ifac.size, ifac.key, KEY_SIZE, mask, total);
    wire[0] = static_cast<uint8_t>(((raw[0] | 0x80) ^ mask[0]) | 0x80);
    wire[1] = static_cast<uint8_t>(raw[1] ^ mask[1]);
    memcpy(wire + 2, code, ifac.size);
    for (size_t i = 2; i < length; ++i) wire[i + ifac.size] = static_cast<uint8_t>(raw[i] ^ mask[i + ifac.size]);
    return total;
}

size_t ifacCheck(const Ifac& ifac, const uint8_t* wire, size_t length, uint8_t* raw, size_t capacity) {
    if (length <= 2 + ifac.size || length > MTU + ifac.size || !(wire[0] & 0x80) || length - ifac.size > capacity) return 0;
    const uint8_t* code = wire + 2;
    uint8_t mask[WIRE_MAX];
    hkdf(code, ifac.size, ifac.key, KEY_SIZE, mask, length);
    const size_t rawLength = length - ifac.size;
    raw[0] = static_cast<uint8_t>((wire[0] ^ mask[0]) & 0x7F);
    raw[1] = static_cast<uint8_t>(wire[1] ^ mask[1]);
    for (size_t i = 2; i < rawLength; ++i) raw[i] = static_cast<uint8_t>(wire[i + ifac.size] ^ mask[i + ifac.size]);
    uint8_t expected[IFAC_MAX_SIZE];
    tag(ifac, raw, rawLength, expected);
    return secure_compare(expected, code, ifac.size) ? rawLength : 0;
}

}  // namespace rnscore
