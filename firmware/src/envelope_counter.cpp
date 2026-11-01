// SPDX-License-Identifier: MIT
#include "envelope_counter.h"

#include "envelope_record.h"

namespace envelope {
namespace {

// MAGIC(4) net(2) own(2) peer(2) sequence(4) upper(4) fingerprint(8) CRC(2) zero(3) COMMIT
constexpr uint8_t MAGIC[4] = {'W', 'C', 'T', '1'};
constexpr size_t CRC_AT = 26;

uint32_t address(uint8_t peer, uint8_t slot) {
    return COUNTER_BASE + (static_cast<uint32_t>(peer) * 2 + slot) * COUNTER_SLOT_BYTES;
}

}  // namespace

bool Counter::begin(uint16_t netId, uint16_t ownId, uint16_t peerId, const uint8_t key[32]) {
    ready_ = false;
    sequence_ = upper_ = current_ = 0;
    slot_ = 1;
    if (peerSlot_ >= COUNTER_PEERS || !key || !stationId(netId) || !stationId(ownId) ||
        !stationId(peerId) || ownId == peerId) return false;
    fingerprint(key, fingerprint_);
    netId_ = netId; ownId_ = ownId; peerId_ = peerId;
    bool found = false;
    for (uint8_t i = 0; i < 2; ++i) {
        uint8_t data[COUNTER_SLOT_BYTES];
        record::Copy copy;
        if (!record::load(storage_, address(peerSlot_, i), data, CRC_AT, MAGIC, copy)) return false;
        if (copy == record::Copy::ABSENT) continue;  // a torn write cannot have issued counters
        if (copy == record::Copy::DAMAGED || get32(data + 14) == 0 || get32(data + 14) % COUNTER_BLOCK)
            return false;
        // Reservation space stays monotonic across rekeys. Reusing an older
        // identity later must not restart its nonce counter at zero.
        if (!memcmp(data + 18, fingerprint_, FINGERPRINT) &&
            (get16(data + 4) != netId || get16(data + 6) != ownId || get16(data + 8) != peerId)) return false;
        const uint32_t sequence = get32(data + 10);
        if (!found || static_cast<int32_t>(sequence - sequence_) > 0) {
            sequence_ = sequence; upper_ = get32(data + 14); slot_ = i; found = true;
        }
    }
    current_ = upper_;  // skip every reserved but possibly unused counter after restart
    ready_ = true;
    return true;
}

bool Counter::reserve(uint32_t upper) {
    uint8_t data[COUNTER_SLOT_BYTES] = {};
    memcpy(data, MAGIC, 4);
    put16(data + 4, netId_); put16(data + 6, ownId_); put16(data + 8, peerId_);
    put32(data + 10, sequence_ + 1); put32(data + 14, upper);
    memcpy(data + 18, fingerprint_, FINGERPRINT);
    const uint8_t target = static_cast<uint8_t>(1 - slot_);
    if (!record::store(storage_, address(peerSlot_, target), data, CRC_AT)) return false;
    slot_ = target; ++sequence_; upper_ = upper;
    return true;
}

bool Counter::outgoing(uint16_t netId, uint16_t sender, uint16_t recipient,
                       const uint8_t key[32]) const {
    if (!ready_ || !key || netId_ != netId || ownId_ != sender || peerId_ != recipient) return false;
    uint8_t actual[FINGERPRINT];
    fingerprint(key, actual);
    return memcmp(actual, fingerprint_, FINGERPRINT) == 0;
}

bool Counter::next(uint32_t& value) {
    if (!ready_) return false;
    if (current_ == upper_) {
        if (upper_ > UINT32_MAX - COUNTER_BLOCK || !reserve(upper_ + COUNTER_BLOCK)) {
            ready_ = false;  // uncertain write: restart and inspect FRAM before any more encryption
            return false;
        }
    }
    value = current_++;
    return true;
}

}  // namespace envelope
