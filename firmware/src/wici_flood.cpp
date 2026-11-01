// SPDX-License-Identifier: MIT
#include "wici_flood.h"

#include <string.h>

namespace wici_flood {
namespace {
constexpr uint8_t COMMIT = 0xA5;
uint32_t address(uint16_t slot) {
    return slot < SLOTS_A ? BASE_A + slot * SLOT_BYTES : BASE_B + (slot - SLOTS_A) * SLOT_BYTES;
}
uint16_t u16(const uint8_t* p) { return static_cast<uint16_t>((p[0] << 8) | p[1]); }
uint32_t u32(const uint8_t* p) {
    return (static_cast<uint32_t>(p[0]) << 24) | (static_cast<uint32_t>(p[1]) << 16) |
           (static_cast<uint32_t>(p[2]) << 8) | p[3];
}
void put16(uint8_t* p, uint16_t n) { p[0] = static_cast<uint8_t>(n >> 8); p[1] = static_cast<uint8_t>(n); }
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
    for (uint8_t i = 0; i < SLOT_BYTES; ++i) { zero &= p[i] == 0; erased &= p[i] == 0xFF; }
    return zero || erased;
}
bool id(uint16_t n) { return n && n != 0xFFFF; }
bool header(const uint8_t* p) {
    if (!p || p[0] >> 6 != 1 || (p[0] & 0x0F) > 1 || ((p[0] >> 4) & 3) == 3) return false;
    const uint16_t sender = u16(p + 1), recipient = u16(p + 3);
    return id(sender) && id(recipient) && sender != recipient;
}
bool fresh(uint32_t at, uint32_t now) { return now < at || now - at <= WINDOW_S; }
}  // namespace

bool Ring::begin(uint16_t network) {
    ready_ = false;
    network_ = 0;
    memset(records_, 0, sizeof(records_));
    if (!id(network)) return false;
    for (uint16_t i = 0; i < SLOTS; ++i) {
        uint8_t record[SLOT_BYTES];
        if (!storage_.read(address(i), record, sizeof(record))) return false;
        if (blank(record) || record[SLOT_BYTES - 1] != COMMIT) continue;
        if (u16(record) != network || !header(record + 2) ||
            u16(record + 15) != crc(record, 15)) return false;
        memcpy(records_[i], record, sizeof(record));
    }
    network_ = network;
    ready_ = true;
    return true;
}

Lookup Ring::lookup(const uint8_t envelopeHeader[9], uint32_t nowS) const {
    if (!ready_ || !header(envelopeHeader)) return Lookup::IO_ERROR;
    for (uint16_t i = 0; i < SLOTS; ++i) {
        const uint8_t* record = records_[i];
        if (record[SLOT_BYTES - 1] == COMMIT &&
            fresh(u32(record + 11), nowS) && memcmp(record + 2, envelopeHeader, 9) == 0)
            return Lookup::MATCH;
    }
    return Lookup::NONE;
}

bool Ring::remember(const uint8_t envelopeHeader[9], uint32_t nowS) {
    if (!ready_ || !header(envelopeHeader)) return false;
    const Lookup found = lookup(envelopeHeader, nowS);
    if (found == Lookup::MATCH) return true;
    if (found != Lookup::NONE) return false;
    uint16_t target = SLOTS;
    for (uint16_t i = 0; i < SLOTS; ++i) {
        const uint8_t* record = records_[i];
        if (record[SLOT_BYTES - 1] != COMMIT || !fresh(u32(record + 11), nowS)) {
            target = i;
            break;
        }
    }
    if (target == SLOTS) return false;
    uint8_t record[SLOT_BYTES] = {};
    put16(record, network_);
    memcpy(record + 2, envelopeHeader, 9);
    put32(record + 11, nowS);
    put16(record + 15, crc(record, 15));
    const uint32_t at = address(target);
    const uint8_t clear = 0;
    if (!storage_.write(at + SLOT_BYTES - 1, &clear, 1) ||
        !storage_.write(at, record, SLOT_BYTES - 1) ||
        !storage_.write(at + SLOT_BYTES - 1, &COMMIT, 1)) {
        ready_ = false;
        return false;
    }
    uint8_t verify[SLOT_BYTES];
    if (!storage_.read(at, verify, sizeof(verify)) || memcmp(record, verify, SLOT_BYTES - 1) ||
        verify[SLOT_BYTES - 1] != COMMIT) {
        ready_ = false;
        return false;
    }
    memcpy(records_[target], verify, sizeof(verify));
    return true;
}

}  // namespace wici_flood
