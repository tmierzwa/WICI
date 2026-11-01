// SPDX-License-Identifier: MIT
// Shared layout rules for WICI-Link FRAM records: big-endian fields, CRC-16
// (CCITT-FALSE) and a final COMMIT byte. A record is written with COMMIT
// cleared, then its body, then COMMIT, and read back, so a torn write is
// never mistaken for a committed record.
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "crc16.h"
#include "journal.h"

namespace wici_record {

constexpr uint8_t COMMIT = 0xA5;

inline uint16_t get16(const uint8_t* p) { return static_cast<uint16_t>((p[0] << 8) | p[1]); }
inline uint32_t get32(const uint8_t* p) {
    return (static_cast<uint32_t>(p[0]) << 24) | (static_cast<uint32_t>(p[1]) << 16) |
           (static_cast<uint32_t>(p[2]) << 8) | p[3];
}
inline void put16(uint8_t* p, uint16_t n) { p[0] = static_cast<uint8_t>(n >> 8); p[1] = static_cast<uint8_t>(n); }
inline void put32(uint8_t* p, uint32_t n) {
    put16(p, static_cast<uint16_t>(n >> 16));
    put16(p + 2, static_cast<uint16_t>(n));
}
inline uint16_t crc(const uint8_t* p, size_t count) { return p1::crc16(p, count); }
// Numbers 0 and 0xFFFF are never station, network or receiver identifiers.
inline bool id(uint16_t n) { return n && n != 0xFFFF; }
// Serial-number comparison of record generations.
inline bool newer(uint32_t candidate, uint32_t current) { return static_cast<int32_t>(candidate - current) > 0; }

// Committed: COMMIT in the last byte and not an all-zero or all-erased area.
inline bool committed(const uint8_t* p, size_t size) {
    bool zero = true, erased = true;
    for (size_t i = 0; i < size; ++i) { zero &= p[i] == 0; erased &= p[i] == 0xFF; }
    return !zero && !erased && p[size - 1] == COMMIT;
}

// Writes data[0..size-2] and then COMMIT at `at + size - 1`, and verifies the
// whole record by reading it back. Any failure leaves the outcome uncertain:
// the caller must stop using its cached state until it reloads FRAM.
inline bool write(journal::Storage& storage, uint32_t at, const uint8_t* data, size_t size) {
    const uint8_t clear = 0;
    if (!storage.write(at + size - 1, &clear, 1) || !storage.write(at, data, size - 1) ||
        !storage.write(at + size - 1, &COMMIT, 1)) return false;
    uint8_t verify[64];
    for (size_t done = 0; done < size;) {
        const size_t n = size - done < sizeof(verify) ? size - done : sizeof(verify);
        if (!storage.read(at + done, verify, n)) return false;
        const size_t body = done + n < size ? n : n - 1;  // the last byte is COMMIT
        if (memcmp(verify, data + done, body) || (body < n && verify[body] != COMMIT)) return false;
        done += n;
    }
    return true;
}

}  // namespace wici_record
