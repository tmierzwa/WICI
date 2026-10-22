// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
#include "hkdf.h"

#include <string.h>

#include <Crypto.h>
#include <SHA256.h>

namespace rnscore {

namespace {

void hmac(const uint8_t* key, size_t keyLength, const uint8_t* data, size_t length, uint8_t out[HASH_SIZE]) {
    SHA256 sha;
    sha.resetHMAC(key, keyLength);
    sha.update(data, length);
    sha.finalizeHMAC(key, keyLength, out, HASH_SIZE);
}

}  // namespace

bool hkdf(const uint8_t* ikm, size_t ikmLength, const uint8_t* salt, size_t saltLength, uint8_t* out, size_t length) {
    if (length == 0 || length > HKDF_MAX_SIZE || ikm == nullptr || ikmLength == 0) return false;
    static const uint8_t zeroSalt[HASH_SIZE] = {};
    if (salt == nullptr || saltLength == 0) {
        salt = zeroSalt;
        saltLength = sizeof(zeroSalt);
    }
    // PRK = HMAC(sól, ikm); T(i) = HMAC(PRK, T(i-1) + i), i od 1 (kontekst pusty).
    uint8_t prk[HASH_SIZE];
    hmac(salt, saltLength, ikm, ikmLength, prk);
    uint8_t input[HASH_SIZE + 1];
    uint8_t block[HASH_SIZE];
    size_t used = 0;
    for (size_t i = 0, offset = 0; offset < length; ++i, offset += HASH_SIZE) {
        input[used] = static_cast<uint8_t>(i + 1);
        hmac(prk, sizeof(prk), input, used + 1, block);
        const size_t n = length - offset < HASH_SIZE ? length - offset : HASH_SIZE;
        memcpy(out + offset, block, n);
        memcpy(input, block, HASH_SIZE);
        used = HASH_SIZE;
    }
    clean(prk, sizeof(prk));
    clean(input, sizeof(input));
    clean(block, sizeof(block));
    return true;
}

}  // namespace rnscore
