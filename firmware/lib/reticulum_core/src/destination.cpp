// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
#include "destination.h"

#include <string.h>

#include "hash.h"

namespace rnscore {

void nameHash(const char* fullName, uint8_t out[NAME_HASH_SIZE]) {
    uint8_t full[HASH_SIZE];
    fullHash(reinterpret_cast<const uint8_t*>(fullName), strlen(fullName), full);
    memcpy(out, full, NAME_HASH_SIZE);
}

void destinationHashFrom(const uint8_t nameHash[NAME_HASH_SIZE], const uint8_t identityHash[TRUNCATED_HASH_SIZE],
                         uint8_t out[TRUNCATED_HASH_SIZE]) {
    uint8_t material[NAME_HASH_SIZE + TRUNCATED_HASH_SIZE];
    memcpy(material, nameHash, NAME_HASH_SIZE);
    size_t length = NAME_HASH_SIZE;
    if (identityHash) {
        memcpy(material + NAME_HASH_SIZE, identityHash, TRUNCATED_HASH_SIZE);
        length += TRUNCATED_HASH_SIZE;
    }
    truncatedHash(material, length, out);
}

void destinationHash(const char* fullName, const uint8_t identityHash[TRUNCATED_HASH_SIZE], uint8_t out[TRUNCATED_HASH_SIZE]) {
    uint8_t name[NAME_HASH_SIZE];
    nameHash(fullName, name);
    destinationHashFrom(name, identityHash, out);
}

}  // namespace rnscore
