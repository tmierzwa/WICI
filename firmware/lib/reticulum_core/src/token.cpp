// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
#include "token.h"

#include <string.h>

#include <AES.h>
#include <Crypto.h>
#include <SHA256.h>

#include "identity.h"

namespace rnscore {

namespace {

constexpr size_t HALF = KEY_SIZE / 2;
constexpr size_t BLOCK = TOKEN_BLOCK_SIZE;

void hmac(const uint8_t* key, size_t keyLength, const uint8_t* data, size_t length, uint8_t out[HASH_SIZE]) {
    SHA256 sha;
    sha.resetHMAC(key, keyLength);
    sha.update(data, length);
    sha.finalizeHMAC(key, keyLength, out, HASH_SIZE);
}

// RNS/Identity.py: Identity.encrypt i __decrypt: hkdf(DERIVED_KEY_LENGTH, wspólny sekret,
// salt=get_salt() czyli skrót tożsamości, context=get_context() czyli None, w hkdf pusty ciąg).
// RNS/Cryptography/HKDF.py: hkdf (RFC 5869): PRK = HMAC(sól, sekret), T(i) = HMAC(PRK, T(i-1) + kontekst + i).
void deriveKey(const uint8_t shared[HALF], const uint8_t publicKey[KEY_SIZE], uint8_t out[DERIVED_KEY_SIZE]) {
    static_assert(DERIVED_KEY_SIZE % HASH_SIZE == 0, "HKDF w całych blokach");
    uint8_t salt[TRUNCATED_HASH_SIZE];
    identityHash(publicKey, salt);
    uint8_t prk[HASH_SIZE];
    hmac(salt, sizeof(salt), shared, HALF, prk);
    uint8_t input[HASH_SIZE + 1];
    size_t used = 0;
    for (uint8_t i = 1; i <= DERIVED_KEY_SIZE / HASH_SIZE; ++i) {
        input[used] = i;
        hmac(prk, sizeof(prk), input, used + 1, out + (i - 1) * HASH_SIZE);
        memcpy(input, out + (i - 1) * HASH_SIZE, HASH_SIZE);
        used = HASH_SIZE;
    }
    clean(prk, sizeof(prk));
    clean(input, sizeof(input));
}

}  // namespace

bool encrypt(const uint8_t publicKey[KEY_SIZE], const uint8_t* ratchet, const uint8_t ephemeralKey[HALF],
             const uint8_t iv[TOKEN_IV_SIZE], const uint8_t* plaintext, size_t length, uint8_t* out) {
    uint8_t shared[HALF];
    if (!exchange(ephemeralKey, ratchet ? ratchet : publicKey, shared)) {
        clean(shared, sizeof(shared));
        return false;
    }
    uint8_t derived[DERIVED_KEY_SIZE];
    deriveKey(shared, publicKey, derived);
    clean(shared, sizeof(shared));

    exchange(ephemeralKey, nullptr, out);   // klucz publiczny efemeryczny
    uint8_t* body = out + HALF;             // IV i szyfrogram, z nich HMAC
    uint8_t* ciphertext = body + TOKEN_IV_SIZE;
    memcpy(body, iv, TOKEN_IV_SIZE);

    // RNS/Cryptography/PKCS7.py: pad; RNS/Cryptography/AES.py: AES_256_CBC.encrypt (klucz: ostatnie 32 B).
    const size_t padded = (length / BLOCK + 1) * BLOCK;
    const uint8_t pad = static_cast<uint8_t>(padded - length);
    AES256 aes;
    aes.setKey(derived + HALF, HALF);
    uint8_t block[BLOCK];
    const uint8_t* previous = iv;
    for (size_t offset = 0; offset < padded; offset += BLOCK) {
        for (size_t i = 0; i < BLOCK; ++i) {
            block[i] = (offset + i < length ? plaintext[offset + i] : pad) ^ previous[i];
        }
        aes.encryptBlock(ciphertext + offset, block);
        previous = ciphertext + offset;
    }
    clean(block, sizeof(block));

    // RNS/Cryptography/Token.py: HMAC.new(signing_key, iv + szyfrogram); klucz HMAC to pierwsze 32 B.
    hmac(derived, HALF, body, TOKEN_IV_SIZE + padded, ciphertext + padded);
    clean(derived, sizeof(derived));
    return true;
}

bool decrypt(const uint8_t privateKey[KEY_SIZE], const uint8_t publicKey[KEY_SIZE], const uint8_t* token,
             size_t length, uint8_t* out, size_t capacity, size_t* outLength) {
    // Python odrzuca każdy z tych przypadków później (HMAC, AES lub unpad), wynik jest ten sam: None.
    if (length < TOKEN_OVERHEAD + BLOCK || (length - TOKEN_OVERHEAD) % BLOCK != 0) return false;
    const size_t size = length - TOKEN_OVERHEAD;
    if (capacity < size) return false;

    uint8_t shared[HALF];
    if (!exchange(privateKey, token, shared)) {
        clean(shared, sizeof(shared));
        return false;
    }
    uint8_t derived[DERIVED_KEY_SIZE];
    deriveKey(shared, publicKey, derived);
    clean(shared, sizeof(shared));

    // RNS/Cryptography/Token.py: verify_hmac przed odszyfrowaniem, porównanie w stałym czasie.
    const uint8_t* body = token + HALF;
    const uint8_t* ciphertext = body + TOKEN_IV_SIZE;
    uint8_t mac[HASH_SIZE];
    hmac(derived, HALF, body, TOKEN_IV_SIZE + size, mac);
    if (!secure_compare(mac, ciphertext + size, HASH_SIZE)) {
        clean(derived, sizeof(derived));
        return false;
    }

    AES256 aes;
    aes.setKey(derived + HALF, HALF);
    clean(derived, sizeof(derived));
    const uint8_t* previous = body;   // IV
    for (size_t offset = 0; offset < size; offset += BLOCK) {
        aes.decryptBlock(out + offset, ciphertext + offset);
        for (size_t i = 0; i < BLOCK; ++i) out[offset + i] ^= previous[i];
        previous = ciphertext + offset;
    }

    // RNS/Cryptography/PKCS7.py: unpad sprawdza tylko, czy ostatni bajt nie przekracza bloku.
    const uint8_t pad = out[size - 1];
    if (pad > BLOCK) {
        clean(out, size);
        return false;
    }
    *outLength = size - pad;
    return true;
}

}  // namespace rnscore
