// SPDX-License-Identifier: MIT
// Cryptographic primitives for the station transfer protocol. No persistent state or USB parsing.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace migration_crypto {

constexpr size_t MID = 16;
constexpr size_t KEY = 32;
constexpr size_t TAG = 16;
constexpr size_t PART = 512;
constexpr size_t HEADER = 101;

// All buffers have fixed lengths. Private scalars are clamped in a local copy.
bool publicKey(const uint8_t privateKey[KEY], uint8_t publicKey[KEY]);
bool derive(const uint8_t privateKey[KEY], const uint8_t peerPublic[KEY],
            const uint8_t mid[MID], uint8_t confirmKey[KEY], uint8_t packageKey[KEY]);

// Header: version(1), mid(16), identity digest(16), source ephemeral public(32),
// SHA-256 of plaintext snapshot(32), plaintext size big endian(4).
void header(const uint8_t mid[MID], const uint8_t identityDigest[16],
            const uint8_t ephemeralPublic[KEY], const uint8_t packageHash[KEY],
            uint32_t plaintextSize, uint8_t out[HEADER]);
bool validHeader(const uint8_t bytes[HEADER], const uint8_t mid[MID], uint32_t maxSize);

// Each part has a unique nonce from its index; header and index are authenticated.
// Ciphertext is plaintext length + TAG. Rejects invalid lengths and authentication failures.
bool sealPart(const uint8_t packageKey[KEY], const uint8_t hdr[HEADER], uint32_t index,
              const uint8_t* plaintext, size_t length, uint8_t* output);
bool openPart(const uint8_t packageKey[KEY], const uint8_t hdr[HEADER], uint32_t index,
              const uint8_t* ciphertext, size_t length, uint8_t* output);

// kind is exactly "imported", "retired", or "aborted". Aborted omits the package hash.
bool confirmation(const uint8_t confirmKey[KEY], const char* kind, const uint8_t mid[MID],
                  const uint8_t packageHash[KEY], uint8_t out[KEY]);
bool verifyConfirmation(const uint8_t confirmKey[KEY], const char* kind, const uint8_t mid[MID],
                        const uint8_t packageHash[KEY], const uint8_t candidate[KEY]);

}  // namespace migration_crypto
