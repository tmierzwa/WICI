// SPDX-License-Identifier: MIT
#include "wici_flood.h"

#include "envelope.h"
#include "fram_record.h"

namespace wici_flood {
namespace {
using namespace fram_record;
uint32_t address(uint16_t slot) {
    return slot < SLOTS_A ? BASE_A + slot * SLOT_BYTES : BASE_B + (slot - SLOTS_A) * SLOT_BYTES;
}
bool header(const uint8_t* p) {
    if (!p || p[0] >> 6 != 1 || (p[0] & 0x0F) > envelope::TYPE_PROOF || ((p[0] >> 4) & 3) == 3) return false;
    const uint16_t sender = get16(p + 1), recipient = get16(p + 3);
    return id(sender) && id(recipient) && sender != recipient;
}
bool fresh(uint32_t at, uint32_t now) { return now < at || now - at <= WINDOW_S; }
bool live(const uint8_t* record, uint32_t now) {
    return record[SLOT_BYTES - 1] == COMMIT && fresh(get32(record + 11), now);
}
}  // namespace

bool Ring::begin(uint16_t network) {
    ready_ = false;
    network_ = 0;
    cleared_ = 0;
    memset(records_, 0, sizeof(records_));
    if (!id(network)) return false;
    for (uint16_t i = 0; i < SLOTS; ++i) {
        uint8_t record[SLOT_BYTES];
        Copy copy;
        if (!load(storage_, address(i), record, sizeof(record), 15, nullptr, copy)) return false;
        if (copy == Copy::ABSENT) continue;
        if (copy == Copy::DAMAGED || !id(get16(record)) || !header(record + 2)) {
            // Tombstone: a cleared COMMIT byte reads back as an absent record.
            const uint8_t clear = 0;
            if (!storage_.write(address(i) + SLOT_BYTES - 1, &clear, 1)) return false;
            ++cleared_;
            continue;
        }
        if (get16(record) != network) continue;  // another network's identities; the slot is free
        memcpy(records_[i], record, sizeof(record));
    }
    network_ = network;
    ready_ = true;
    return true;
}

Lookup Ring::lookup(const uint8_t envelopeHeader[9], uint32_t nowS) const {
    if (!ready_ || !header(envelopeHeader)) return Lookup::IO_ERROR;
    for (const uint8_t* record : records_)
        if (live(record, nowS) && memcmp(record + 2, envelopeHeader, 9) == 0) return Lookup::MATCH;
    return Lookup::NONE;
}

bool Ring::remember(const uint8_t envelopeHeader[9], uint32_t nowS) {
    const Lookup found = lookup(envelopeHeader, nowS);
    if (found != Lookup::NONE) return found == Lookup::MATCH;
    uint16_t target = 0;
    while (target < SLOTS && live(records_[target], nowS)) ++target;
    if (target == SLOTS) return false;
    uint8_t record[SLOT_BYTES] = {};
    put16(record, network_);
    memcpy(record + 2, envelopeHeader, 9);
    put32(record + 11, nowS);
    if (!store(storage_, address(target), record, sizeof(record), 15)) {
        ready_ = false;
        return false;
    }
    memcpy(records_[target], record, sizeof(record));
    return true;
}

}  // namespace wici_flood
