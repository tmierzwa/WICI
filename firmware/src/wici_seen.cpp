// SPDX-License-Identifier: MIT
#include "wici_seen.h"

#include "wici_link.h"
#include "fram_record.h"
#include "sha2.h"

namespace wici_seen {
namespace {
using namespace fram_record;
// Record: network, envelope version/sender/recipient/counter (9 B), payload
// digest (6 B), time (4 B), CRC, COMMIT.
constexpr size_t DIGEST_AT = 11, TIME_AT = 17, CRC_AT = 21;
bool valid(const uint8_t* p) {
    return id(get16(p)) && id(get16(p + 3)) && id(get16(p + 5));
}
bool wireValid(const uint8_t* wire, size_t length) {
    return wire && length >= wici_link::HEADER + wici_link::TAG + 25 && length <= wici_link::MAX_FRAME;
}
bool live(const uint8_t* record, uint32_t now) {
    const uint32_t at = get32(record + TIME_AT);
    return record[SLOT_BYTES - 1] == COMMIT && (now < at || now - at <= WINDOW_S);
}
bool sameKey(const uint8_t* record, const uint8_t* wire) {
    return memcmp(record, wire + 1, 2) == 0 &&
           memcmp(record + 2, wire + wici_link::HEADER, 9) == 0;
}
void payloadDigest(const uint8_t* wire, size_t length, uint8_t out[6]) {
    uint8_t digest[sha2::DIGEST];
    sha2::digest(wire + wici_link::HEADER, length - wici_link::HEADER - wici_link::TAG, digest);
    memcpy(out, digest, 6);
}
}  // namespace

bool Ring::begin() {
    ready_ = false;
    cleared_ = 0;
    memset(records_, 0, sizeof(records_));
    for (uint16_t i = 0; i < SLOTS; ++i) {
        uint8_t data[SLOT_BYTES];
        Copy copy;
        if (!load(storage_, BASE + i * SLOT_BYTES, data, sizeof(data), CRC_AT, nullptr, copy)) return false;
        if (copy == Copy::ABSENT) continue;
        if (copy == Copy::DAMAGED || !valid(data)) {
            // Tombstone: a cleared COMMIT byte reads back as an absent record.
            const uint8_t clear = 0;
            if (!storage_.write(BASE + i * SLOT_BYTES + SLOT_BYTES - 1, &clear, 1)) return false;
            ++cleared_;
            continue;
        }
        memcpy(records_[i], data, sizeof(data));
    }
    ready_ = true;
    return true;
}

Lookup Ring::lookup(const uint8_t* wire, size_t length, uint32_t nowS) {
    if (!ready_ || !wireValid(wire, length)) return Lookup::IO_ERROR;
    uint8_t digest[6];
    payloadDigest(wire, length, digest);
    for (const uint8_t* data : records_) {
        if (!live(data, nowS) || !sameKey(data, wire)) continue;
        return memcmp(data + DIGEST_AT, digest, sizeof(digest)) == 0 ? Lookup::MATCH : Lookup::CONFLICT;
    }
    return Lookup::NONE;
}

bool Ring::remember(const uint8_t* wire, size_t length, uint32_t nowS) {
    const Lookup existing = lookup(wire, length, nowS);
    if (existing != Lookup::NONE) return existing == Lookup::MATCH;
    // A free or expired slot first, otherwise the oldest record.
    uint16_t target = SLOTS;
    uint32_t oldest = 0;
    for (uint16_t i = 0; i < SLOTS; ++i) {
        const uint8_t* data = records_[i];
        if (!live(data, nowS)) { target = i; break; }
        const uint32_t at = get32(data + TIME_AT);
        const uint32_t age = nowS < at ? 0 : nowS - at;
        if (target == SLOTS || age > oldest) { oldest = age; target = i; }
    }
    uint8_t data[SLOT_BYTES] = {};
    memcpy(data, wire + 1, 2);                      // network
    memcpy(data + 2, wire + wici_link::HEADER, 9);  // envelope identity
    payloadDigest(wire, length, data + DIGEST_AT);
    put32(data + TIME_AT, nowS);
    if (!store(storage_, BASE + target * SLOT_BYTES, data, sizeof(data), CRC_AT)) {
        ready_ = false;
        return false;
    }
    memcpy(records_[target], data, sizeof(data));
    return true;
}
}  // namespace wici_seen
