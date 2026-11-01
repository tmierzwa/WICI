// SPDX-License-Identifier: MIT
// Shared codec of durable FRAM records (envelope and WICI-Link state):
// big-endian fields, CRC-16 (CCITT-FALSE) and a final COMMIT byte. A record
// is written with COMMIT cleared, then its body, then COMMIT, and read back,
// so a torn write is never mistaken for a committed record.
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "crc16.h"
#include "journal.h"
#include "sha2.h"

namespace fram_record {

constexpr uint8_t COMMIT = 0xA5;

inline uint16_t get16(const uint8_t* p) { return static_cast<uint16_t>((p[0] << 8) | p[1]); }
inline uint32_t get32(const uint8_t* p) { return (static_cast<uint32_t>(get16(p)) << 16) | get16(p + 2); }
inline uint64_t get64(const uint8_t* p) { return (static_cast<uint64_t>(get32(p)) << 32) | get32(p + 4); }
inline void put16(uint8_t* p, uint16_t n) { p[0] = static_cast<uint8_t>(n >> 8); p[1] = static_cast<uint8_t>(n); }
inline void put32(uint8_t* p, uint32_t n) { put16(p, static_cast<uint16_t>(n >> 16)); put16(p + 2, static_cast<uint16_t>(n)); }
inline void put64(uint8_t* p, uint64_t n) { put32(p, static_cast<uint32_t>(n >> 32)); put32(p + 4, static_cast<uint32_t>(n)); }
inline uint16_t crc(const uint8_t* p, size_t count) { return p1::crc16(p, count); }
// Numbers 0 and 0xFFFF are never station, network or receiver identifiers.
inline bool id(uint16_t n) { return n && n != 0xFFFF; }
// Serial-number comparison of record generations.
inline bool newer(uint32_t candidate, uint32_t current) { return static_cast<int32_t>(candidate - current) > 0; }
// All-zero or all-erased area: never written.
inline bool blank(const uint8_t* p, size_t size) {
    bool zero = true, erased = true;
    for (size_t i = 0; i < size; ++i) { zero &= p[i] == 0; erased &= p[i] == 0xFF; }
    return zero || erased;
}

constexpr size_t FINGERPRINT = 8;

// First 8 bytes of SHA-256 over a derived key. Records bound to a key carry
// it; durable state with another fingerprint belongs to another key.
inline void fingerprint(const uint8_t key[32], uint8_t out[FINGERPRINT]) {
    uint8_t digest[sha2::DIGEST];
    sha2::digest(key, 32, digest);
    memcpy(out, digest, FINGERPRINT);
    memset(digest, 0, sizeof(digest));
}

// ABSENT: blank, or a write torn before its COMMIT byte, which never released
// any state. DAMAGED: any other last byte, or a committed copy with a wrong
// magic or CRC. Callers fail closed on DAMAGED instead of using another copy.
enum class Copy : uint8_t { ABSENT, VALID, DAMAGED };

// Reads `size` bytes at `at` and classifies them; the CRC covers [0, crcAt)
// and `magic` (4 bytes, or nullptr when the record has none) starts the
// record. Returns false only when the storage read fails.
inline bool load(journal::Storage& storage, uint32_t at, uint8_t* r, size_t size, size_t crcAt,
                 const uint8_t* magic, Copy& copy) {
    if (!storage.read(at, r, size)) return false;
    if (blank(r, size) || r[size - 1] == 0) copy = Copy::ABSENT;
    else if (r[size - 1] == COMMIT && (!magic || !memcmp(r, magic, 4)) && get16(r + crcAt) == crc(r, crcAt))
        copy = Copy::VALID;
    else copy = Copy::DAMAGED;
    return true;
}

// Sets r[size - 1] to COMMIT, writes r[0..size-2] with COMMIT cleared, then
// COMMIT, and verifies the whole record by reading it back. Any failure
// leaves the outcome uncertain: the caller must stop using its cached state
// until it reloads FRAM.
inline bool write(journal::Storage& storage, uint32_t at, uint8_t* r, size_t size) {
    const uint8_t clear = 0;
    r[size - 1] = COMMIT;
    if (!storage.write(at + size - 1, &clear, 1) || !storage.write(at, r, size - 1) ||
        !storage.write(at + size - 1, &COMMIT, 1)) return false;
    uint8_t verify[64];
    for (size_t done = 0; done < size;) {
        const size_t n = size - done < sizeof(verify) ? size - done : sizeof(verify);
        if (!storage.read(at + done, verify, n) || memcmp(verify, r + done, n)) return false;
        done += n;
    }
    return true;
}

// Fills the CRC over [0, crcAt) and writes the record as write() does.
inline bool store(journal::Storage& storage, uint32_t at, uint8_t* r, size_t size, size_t crcAt) {
    put16(r + crcAt, crc(r, crcAt));
    return write(storage, at, r, size);
}

}  // namespace fram_record
