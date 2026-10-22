// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// Szyfrowanie do tożsamości (token Reticulum): klucz publiczny efemeryczny X25519 32 B, IV 16 B,
// szyfrogram AES-256-CBC z dopełnieniem PKCS7, HMAC-SHA256 32 B z IV i szyfrogramu. Klucze z HKDF
// wspólnego sekretu ECDH. Bez zapadek (ratchets): firmware/reticulum-core.md, do rozstrzygnięcia.
#pragma once

#include "rnscore.h"

namespace rnscore {

constexpr size_t TOKEN_IV_SIZE = 16;
constexpr size_t TOKEN_BLOCK_SIZE = 16;
// Klucz efemeryczny, IV i HMAC (RNS/Cryptography/Token.py: TOKEN_OVERHEAD to IV i HMAC).
constexpr size_t TOKEN_OVERHEAD = KEY_SIZE / 2 + TOKEN_IV_SIZE + HASH_SIZE;

// Długość tokenu dla tekstu jawnego o długości length (PKCS7 dodaje od 1 do 16 B).
constexpr size_t tokenSize(size_t length) {
    return TOKEN_OVERHEAD + (length / TOKEN_BLOCK_SIZE + 1) * TOKEN_BLOCK_SIZE;
}

// RNS/Identity.py: Identity.encrypt bez zapadki; RNS/Cryptography/Token.py: Token.encrypt. Klucz
// efemeryczny (prywatny, 32 B) i IV podaje wywołujący; w Pythonie to X25519PrivateKey.generate
// i os.urandom, więc muszą być losowe i nowe dla każdego tokenu. out ma tokenSize(length) B i nie
// może zachodzić na plaintext. Fałsz, gdy klucz publiczny celu jest niskiego rzędu (Python zgłasza błąd).
bool encrypt(const uint8_t publicKey[KEY_SIZE], const uint8_t ephemeralKey[KEY_SIZE / 2],
             const uint8_t iv[TOKEN_IV_SIZE], const uint8_t* plaintext, size_t length, uint8_t* out);

// RNS/Identity.py: Identity.decrypt bez zapadek; Token.decrypt; PKCS7.unpad. publicKey musi pochodzić
// z privateKey (sól HKDF to skrót tożsamości). Fałsz tam, gdzie Python zwraca None: zła długość, klucz
// efemeryczny niskiego rzędu, zły HMAC, bajt dopełnienia większy niż 16. Jak w Pythonie bajty
// dopełnienia nie są sprawdzane, a dopełnienie 0 zostawia cały blok. out ma co najmniej
// length - TOKEN_OVERHEAD B (mniej: fałsz) i nie może zachodzić na token; przy fałszu nie zostaje w nim tekst jawny.
bool decrypt(const uint8_t privateKey[KEY_SIZE], const uint8_t publicKey[KEY_SIZE], const uint8_t* token,
             size_t length, uint8_t* out, size_t capacity, size_t* outLength);

}  // namespace rnscore
