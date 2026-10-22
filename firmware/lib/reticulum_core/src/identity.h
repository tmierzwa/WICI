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

// RNS/Cryptography/X25519.py: X25519PrivateKey.exchange (RFC 7748). Klucz prywatny 32 B jest przycinany
// jak wyżej; peer nullptr to punkt bazowy 9 (wtedy out to klucz publiczny). Punkt peer jest brany jak
// w Pythonie: najstarszy bit pominięty, wartość ≥ p zredukowana. Fałsz, gdy wynik jest zerowy (punkt
// niskiego rzędu): Python zgłasza wtedy błąd. Wynik w out także przy fałszu, sprawdzenie w stałym czasie.
bool exchange(const uint8_t privateKey[KEY_SIZE / 2], const uint8_t* peer, uint8_t out[KEY_SIZE / 2]);

// RNS/Identity.py: Identity.update_hashes (truncated_hash klucza publicznego).
void identityHash(const uint8_t publicKey[KEY_SIZE], uint8_t out[TRUNCATED_HASH_SIZE]);

// RNS/Identity.py: Identity.sign (Ed25519, RFC 8032). publicKey musi pochodzić z privateKey.
void sign(const uint8_t privateKey[KEY_SIZE], const uint8_t publicKey[KEY_SIZE], const uint8_t* message, size_t length,
          uint8_t out[SIGNATURE_SIZE]);

// RNS/Identity.py: Identity.validate. Fałsz dla podpisu o złej długości, niekanonicznego (S ≥ L albo R
// w kodowaniu niekanonicznym, jak odrzuca go Python) i niepoprawnego; nie zgłasza błędu. Klucze niskiego
// rzędu przyjmuje jak Python; odstępstwo: klucz z punktem neutralnym zapisanym z bitem znaku (kodowanie,
// którego biblioteka Crypto nie dekoduje) rdzeń odrzuca, Python go przyjmuje (firmware/reticulum-core.md).
bool validate(const uint8_t publicKey[KEY_SIZE], const uint8_t* signature, size_t signatureLength,
              const uint8_t* message, size_t length);

// Bez odpowiednika w Pythonie: liczba operacji asymetrycznych (exchange, sign, weryfikacja w validate)
// od startu programu. Służy próbom ograniczenia pracy na pakiet (najwyżej jedna operacja na obieg pętli
// stacji); zawija się po 2^32.
uint32_t asymmetricOperations();

}  // namespace rnscore
