// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// Skróty Reticulum: pełny SHA-256 i skrót ucięty do 16 B (tożsamości, cele, pakiety).
#pragma once

#include "rnscore.h"

namespace rnscore {

// RNS/Identity.py: Identity.full_hash (RNS.Cryptography.sha256).
void fullHash(const uint8_t* data, size_t length, uint8_t out[HASH_SIZE]);

// RNS/Identity.py: Identity.truncated_hash (pierwsze TRUNCATED_HASHLENGTH bitów pełnego skrótu).
void truncatedHash(const uint8_t* data, size_t length, uint8_t out[TRUNCATED_HASH_SIZE]);

}  // namespace rnscore
