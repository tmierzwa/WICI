// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
#include "hash.h"

#include <string.h>

#include <SHA256.h>

namespace rnscore {

void fullHash(const uint8_t* data, size_t length, uint8_t out[HASH_SIZE]) {
    SHA256 sha;
    sha.update(data, length);
    sha.finalize(out, HASH_SIZE);
}

void truncatedHash(const uint8_t* data, size_t length, uint8_t out[TRUNCATED_HASH_SIZE]) {
    uint8_t full[HASH_SIZE];
    fullHash(data, length, full);
    memcpy(out, full, TRUNCATED_HASH_SIZE);
}

}  // namespace rnscore
