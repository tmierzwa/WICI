// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// Skrót celu Reticulum z pełnej nazwy (aplikacja i aspekty rozdzielone kropkami) i skrótu tożsamości.
#pragma once

#include "rnscore.h"

namespace rnscore {

// RNS/Destination.py: Destination.hash_from_name_and_identity i Destination.hash: skrót nazwy
// (full_hash pełnej nazwy w UTF-8, pierwsze NAME_HASH_SIZE B), potem truncated_hash skrótu nazwy
// i skrótu tożsamości. identityHash nullptr: cel bez tożsamości (PLAIN), tylko skrót nazwy.
void destinationHash(const char* fullName, const uint8_t identityHash[TRUNCATED_HASH_SIZE], uint8_t out[TRUNCATED_HASH_SIZE]);

}  // namespace rnscore
