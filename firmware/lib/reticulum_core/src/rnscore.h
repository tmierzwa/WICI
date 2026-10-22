// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// Rdzeń Reticulum stacji: wspólne stałe i typy. Utwór zależny od implementacji referencyjnej
// Reticulum (e40191b, 1.5.5); zakres i zasady: firmware/reticulum-core.md. Przestrzeń nazw rnscore,
// żeby rdzeń i port (RNS) mogły być w jednym programie prób. C++17 bez wyjątków i RTTI, bez sterty.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace rnscore {

// Długości w bajtach. Odpowiedniki w RNS/Identity.py (Identity.KEYSIZE, HASHLENGTH, SIGLENGTH,
// NAME_HASH_LENGTH, RATCHETSIZE, DERIVED_KEY_LENGTH) i RNS/Reticulum.py (TRUNCATED_HASHLENGTH).
constexpr size_t KEY_SIZE = 512 / 8;            // klucz publiczny tożsamości: X25519 32 B + Ed25519 32 B
constexpr size_t HASH_SIZE = 256 / 8;           // pełny skrót SHA-256
constexpr size_t TRUNCATED_HASH_SIZE = 128 / 8; // skrót tożsamości i celu
constexpr size_t SIGNATURE_SIZE = 512 / 8;      // podpis Ed25519
constexpr size_t NAME_HASH_SIZE = 80 / 8;
constexpr size_t RATCHET_SIZE = 256 / 8;
constexpr size_t DERIVED_KEY_SIZE = 512 / 8;    // HKDF dla tokenu: klucz HMAC 32 B + klucz AES-256 32 B

}  // namespace rnscore
