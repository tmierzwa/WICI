// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// HKDF z HMAC-SHA256 (RFC 5869) bez kontekstu: klucze tokenu, klucz i maska kodu dostępu interfejsu.
#pragma once

#include "rnscore.h"

namespace rnscore {

constexpr size_t HKDF_MAX_SIZE = 255 * HASH_SIZE;   // RFC 5869: najwyżej 255 bloków

// RNS/Cryptography/HKDF.py: hkdf(length, derive_from, salt, context=None). Pusta sól (salt nullptr albo
// długość 0) to 32 B zer, jak w Pythonie. Fałsz tam, gdzie Python zgłasza błąd (length 0, puste ikm),
// i dla length > HKDF_MAX_SIZE (Python zawija wtedy licznik bloków; rdzeń takich długości nie używa).
bool hkdf(const uint8_t* ikm, size_t ikmLength, const uint8_t* salt, size_t saltLength, uint8_t* out, size_t length);

}  // namespace rnscore
