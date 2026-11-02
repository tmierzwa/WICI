// SPDX-License-Identifier: MIT
#include "envelope_replay.h"

#include "fram_record.h"

namespace envelope {
namespace {
using namespace fram_record;

// MAGIC(4) generation(4) fingerprint(8) highest(4) mask(8) CRC(2) version(1) COMMIT
constexpr uint8_t MAGIC[4] = {'W', 'R', 'P', '1'};
constexpr size_t CRC_AT = 28;

uint32_t address(uint8_t peer, uint8_t copy) {
    return REPLAY_BASE + (static_cast<uint32_t>(peer) * 2 + copy) * REPLAY_SLOT_BYTES;
}

}  // namespace

bool ReplayWindow::accept(uint32_t counter, ReplayWindow& next) const {
    next = *this;
    if (!started) {
        next.highest = counter;
        next.mask = 1;
        next.started = true;
        return true;
    }
    if (counter > highest) {
        const uint32_t shift = counter - highest;
        next.highest = counter;
        next.mask = ((shift >= 64 ? 0 : mask << shift) | 1);
        return true;
    }
    const uint32_t distance = highest - counter;
    if (distance >= 64 || (mask & (uint64_t{1} << distance))) return false;
    next.mask |= uint64_t{1} << distance;
    return true;
}

bool DurableReplay::begin(uint16_t network, uint16_t recipient, uint16_t sender, const uint8_t key[32]) {
    ready_ = false;
    window_ = ReplayWindow();
    generation_ = 0;
    copy_ = 1;
    if (peerSlot_ >= REPLAY_PEERS || !key || !id(network) || !id(recipient) ||
        !id(sender) || recipient == sender) return false;
    fingerprint(key, fingerprint_);
    bool found = false;
    for (uint8_t copy = 0; copy < 2; ++copy) {
        uint8_t data[REPLAY_SLOT_BYTES];
        Copy state;
        if (!load(storage_, address(peerSlot_, copy), data, sizeof(data), CRC_AT, MAGIC, state)) return false;
        if (state == Copy::ABSENT) continue;
        if (state == Copy::DAMAGED || data[30] != 1 || !(get64(data + 20) & 1)) return false;
        if (memcmp(data + 8, fingerprint_, FINGERPRINT)) continue;  // window of another key
        const uint32_t generation = get32(data + 4);
        if (!found || newer(generation, generation_)) {
            generation_ = generation;
            copy_ = copy;
            window_.highest = get32(data + 16);
            window_.mask = get64(data + 20);
            window_.started = true;
            found = true;
        }
    }
    ready_ = true;
    return true;
}

bool DurableReplay::propose(uint32_t counter, ReplayWindow& next) const {
    next = ReplayWindow();
    return ready_ && window_.accept(counter, next);
}

bool DurableReplay::accepted(uint32_t counter) const {
    if (!ready_ || !window_.started || counter > window_.highest) return false;
    const uint32_t distance = window_.highest - counter;
    return distance < 64 && (window_.mask & (uint64_t{1} << distance));
}

bool DurableReplay::commit(uint32_t counter) {
    ReplayWindow next;
    if (!propose(counter, next)) return false;
    uint8_t data[REPLAY_SLOT_BYTES] = {};
    memcpy(data, MAGIC, 4);
    put32(data + 4, generation_ + 1);
    memcpy(data + 8, fingerprint_, FINGERPRINT);
    put32(data + 16, next.highest);
    put64(data + 20, next.mask);
    data[30] = 1;
    const uint8_t target = static_cast<uint8_t>(1 - copy_);
    if (!store(storage_, address(peerSlot_, target), data, sizeof(data), CRC_AT)) {
        ready_ = false;
        return false;
    }
    copy_ = target;
    ++generation_;
    window_ = next;
    return true;
}

}  // namespace envelope
