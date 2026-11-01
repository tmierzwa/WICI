// SPDX-License-Identifier: MIT
#include "wici_seen.h"

#include <string.h>

#include "wici_link.h"
#include "sha2.h"

namespace wici_seen {
namespace {
constexpr uint8_t COMMIT = 0xA5;
uint16_t u16(const uint8_t* p) { return static_cast<uint16_t>((p[0] << 8) | p[1]); }
uint32_t u32(const uint8_t* p) {
    return (static_cast<uint32_t>(p[0]) << 24) | (static_cast<uint32_t>(p[1]) << 16) |
           (static_cast<uint32_t>(p[2]) << 8) | p[3];
}
void put32(uint8_t* p, uint32_t n) {
    p[0] = static_cast<uint8_t>(n >> 24); p[1] = static_cast<uint8_t>(n >> 16);
    p[2] = static_cast<uint8_t>(n >> 8); p[3] = static_cast<uint8_t>(n);
}
uint16_t crc(const uint8_t* p, size_t count) {
    uint16_t c = 0xFFFF;
    for (size_t i = 0; i < count; ++i) {
        c ^= static_cast<uint16_t>(p[i]) << 8;
        for (uint8_t j = 0; j < 8; ++j)
            c = c & 0x8000 ? static_cast<uint16_t>((c << 1) ^ 0x1021) : static_cast<uint16_t>(c << 1);
    }
    return c;
}
bool blank(const uint8_t* p) {
    bool zero = true, erased = true;
    for (size_t i = 0; i < SLOT_BYTES; ++i) { zero &= p[i] == 0; erased &= p[i] == 0xFF; }
    return zero || erased;
}
bool valid(const uint8_t* p) {
    return p[23] == COMMIT && u16(p) && u16(p) != 0xFFFF &&
           u16(p + 3) && u16(p + 3) != 0xFFFF &&
           u16(p + 5) && u16(p + 5) != 0xFFFF &&
           u16(p + 21) == crc(p, 21);
}
bool wireValid(const uint8_t* wire, size_t length) {
    return wire && length >= wici_link::HEADER + wici_link::TAG + 25 && length <= wici_link::MAX_FRAME;
}
bool fresh(uint32_t at, uint32_t now) { return now < at || now - at <= WINDOW_S; }
bool sameKey(const uint8_t* record, const uint8_t* wire) {
    return memcmp(record, wire + 1, 2) == 0 &&
           memcmp(record + 2, wire + wici_link::HEADER, 9) == 0;
}
void payloadDigest(const uint8_t* wire, size_t length, uint8_t out[6]) {
    uint8_t digest[sha2::DIGEST];
    sha2::digest(wire + wici_link::HEADER, length - wici_link::HEADER - wici_link::TAG, digest);
    memcpy(out, digest, 6);
    memset(digest, 0, sizeof(digest));
}
}  // namespace

bool Ring::begin() {
    ready_ = false;
    memset(records_, 0, sizeof(records_));
    for (uint16_t i = 0; i < SLOTS; ++i) {
        uint8_t data[SLOT_BYTES];
        if (!storage_.read(BASE + i * SLOT_BYTES, data, sizeof(data))) return false;
        if (!blank(data) && data[23] == COMMIT && !valid(data)) return false;
        if (data[23] == COMMIT) memcpy(records_[i], data, sizeof(data));
    }
    ready_ = true;
    return true;
}

Lookup Ring::lookup(const uint8_t* wire, size_t length, uint32_t nowS) {
    if (!ready_ || !wireValid(wire, length)) return Lookup::IO_ERROR;
    uint8_t digest[6];
    payloadDigest(wire, length, digest);
    for (uint16_t i = 0; i < SLOTS; ++i) {
        const uint8_t* data = records_[i];
        if (data[23] != COMMIT) continue;
        if (!fresh(u32(data + 17), nowS) || !sameKey(data, wire)) continue;
        return memcmp(data + 11, digest, sizeof(digest)) == 0 ?
               Lookup::MATCH : Lookup::CONFLICT;
    }
    return Lookup::NONE;
}

bool Ring::remember(const uint8_t* wire, size_t length, uint32_t nowS) {
    if (!ready_ || !wireValid(wire, length)) return false;
    const Lookup existing = lookup(wire, length, nowS);
    if (existing == Lookup::MATCH) return true;
    if (existing != Lookup::NONE) return false;
    uint16_t target = SLOTS;
    uint32_t oldest = 0;
    for (uint16_t i = 0; i < SLOTS; ++i) {
        const uint8_t* data = records_[i];
        if (data[23] != COMMIT || !fresh(u32(data + 17), nowS)) { target = i; break; }
        const uint32_t age = nowS < u32(data + 17) ? 0 : nowS - u32(data + 17);
        if (target == SLOTS || age > oldest) { oldest = age; target = i; }
    }
    if (target == SLOTS) return false;
    uint8_t data[SLOT_BYTES] = {};
    memcpy(data, wire + 1, 2);       // network
    memcpy(data + 2, wire + wici_link::HEADER, 9);  // envelope version, sender, recipient, counter
    payloadDigest(wire, length, data + 11);
    put32(data + 17, nowS);
    const uint16_t check = crc(data, 21);
    data[21] = static_cast<uint8_t>(check >> 8); data[22] = static_cast<uint8_t>(check);
    const uint32_t at = BASE + target * SLOT_BYTES;
    const uint8_t clear = 0;
    if (!storage_.write(at + 23, &clear, 1) || !storage_.write(at, data, 23) ||
        !storage_.write(at + 23, &COMMIT, 1)) { ready_ = false; return false; }
    uint8_t verify[SLOT_BYTES];
    if (!storage_.read(at, verify, sizeof(verify)) || memcmp(data, verify, 23) || verify[23] != COMMIT) {
        ready_ = false;
        return false;
    }
    memcpy(records_[target], verify, sizeof(verify));
    return true;
}
}  // namespace wici_seen
