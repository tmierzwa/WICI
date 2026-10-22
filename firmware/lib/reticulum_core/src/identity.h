// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// Tożsamość Reticulum: klucz prywatny 64 B (X25519 32 B, potem ziarno Ed25519 32 B), klucz publiczny
// 64 B w tej samej kolejności, skrót tożsamości, podpis i weryfikacja Ed25519.
#pragma once

#include "rnscore.h"

namespace rnscore {

// RNS/Identity.py: Identity.load_private_key i get_public_key. Klucz X25519 jest przycinany jak w
// RFC 7748 (decodeScalar25519), tak jak robi to biblioteka kryptograficzna Pythona.
void publicKey(const uint8_t privateKey[KEY_SIZE], uint8_t out[KEY_SIZE]);

// RNS/Identity.py: Identity.update_hashes (truncated_hash klucza publicznego).
void identityHash(const uint8_t publicKey[KEY_SIZE], uint8_t out[TRUNCATED_HASH_SIZE]);

// RNS/Identity.py: Identity.sign (Ed25519, RFC 8032). publicKey musi pochodzić z privateKey.
void sign(const uint8_t privateKey[KEY_SIZE], const uint8_t publicKey[KEY_SIZE], const uint8_t* message, size_t length,
          uint8_t out[SIGNATURE_SIZE]);

// RNS/Identity.py: Identity.validate. Fałsz dla podpisu o złej długości, niekanonicznego (S ≥ L, jak
// odrzuca go Python) i niepoprawnego; nie zgłasza błędu.
bool validate(const uint8_t publicKey[KEY_SIZE], const uint8_t* signature, size_t signatureLength,
              const uint8_t* message, size_t length);

}  // namespace rnscore
