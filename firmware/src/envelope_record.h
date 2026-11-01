// SPDX-License-Identifier: MIT
// Shared pieces of the envelope's durable FRAM state (counter, replay window,
// pending fragment): big-endian fields, the key fingerprint, and a record copy
// that starts with a 4-byte magic, has a CRC-16 and ends with a COMMIT byte.
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "crc16.h"
#include "journal.h"
#include "sha2.h"

namespace envelope {

inline bool stationId(uint16_t n) { return n != 0 && n != 0xFFFF; }
inline uint16_t get16(const uint8_t* p) { return static_cast<uint16_t>((p[0] << 8) | p[1]); }
inline uint32_t get32(const uint8_t* p) {
    return (static_cast<uint32_t>(get16(p)) << 16) | get16(p + 2);
}
inline uint64_t get64(const uint8_t* p) { return (static_cast<uint64_t>(get32(p)) << 32) | get32(p + 4); }
inline void put16(uint8_t* p, uint16_t n) { p[0] = static_cast<uint8_t>(n >> 8); p[1] = static_cast<uint8_t>(n); }
inline void put32(uint8_t* p, uint32_t n) { put16(p, static_cast<uint16_t>(n >> 16)); put16(p + 2, static_cast<uint16_t>(n)); }
inline void put64(uint8_t* p, uint64_t n) { put32(p, static_cast<uint32_t>(n >> 32)); put32(p + 4, static_cast<uint32_t>(n)); }

constexpr size_t FINGERPRINT = 8;

// First 8 bytes of SHA-256 over the derived directional envelope key. Durable
// state carrying another fingerprint belongs to another key and nonce space.
inline void fingerprint(const uint8_t key[32], uint8_t out[FINGERPRINT]) {
    uint8_t digest[sha2::DIGEST];
    sha2::digest(key, 32, digest);
    memcpy(out, digest, FINGERPRINT);
    memset(digest, 0, sizeof(digest));
}

namespace record {

constexpr uint8_t COMMIT = 0xA5;

// ABSENT: erased, or a write torn before its COMMIT byte, which never released
// any state. DAMAGED: any other last byte, or a committed copy with a wrong
// magic or CRC. Callers fail closed on DAMAGED instead of using the other copy.
enum class Copy : uint8_t { ABSENT, VALID, DAMAGED };

// Returns false only when the storage read fails.
template <size_t N>
bool load(journal::Storage& storage, uint32_t at, uint8_t (&r)[N], size_t crcAt,
          const uint8_t magic[4], Copy& copy) {
    static_assert(N > 6, "record holds magic, CRC and COMMIT");
    if (!storage.read(at, r, N)) return false;
    bool zero = true, erased = true;
    for (uint8_t byte : r) { zero &= byte == 0; erased &= byte == 0xFF; }
    if (zero || erased || r[N - 1] == 0) copy = Copy::ABSENT;
    else if (r[N - 1] == COMMIT && !memcmp(r, magic, 4) && get16(r + crcAt) == p1::crc16(r, crcAt))
        copy = Copy::VALID;
    else copy = Copy::DAMAGED;
    return true;
}

// Clears COMMIT, writes the body with its CRC, sets COMMIT and reads it back.
template <size_t N>
bool store(journal::Storage& storage, uint32_t at, uint8_t (&r)[N], size_t crcAt) {
    put16(r + crcAt, p1::crc16(r, crcAt));
    r[N - 1] = COMMIT;
    const uint8_t open = 0;
    uint8_t verify[N];
    return storage.write(at + N - 1, &open, 1) && storage.write(at, r, N - 1) &&
           storage.write(at + N - 1, &COMMIT, 1) && storage.read(at, verify, N) && !memcmp(r, verify, N);
}

}  // namespace record
}  // namespace envelope
