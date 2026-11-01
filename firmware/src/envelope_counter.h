// SPDX-License-Identifier: MIT
// Durable nonce reservation for one directed envelope key. The two slots live in the
// otherwise unused FRAM region between the identity and Reticulum file system.
#pragma once

#include <stdint.h>

#include "journal.h"

namespace envelope {

constexpr uint32_t COUNTER_BASE = 0x044100;
constexpr uint32_t COUNTER_SLOT_BYTES = 32;
constexpr uint32_t COUNTER_PEERS = 2;
constexpr uint32_t COUNTER_BLOCK = 64;

class Counter {
public:
    Counter(journal::Storage& storage, uint8_t peerSlot) : storage_(storage), peerSlot_(peerSlot) {}
    // Existing binding must match exactly. Corrupt committed state fails closed.
    bool begin(uint16_t netId, uint16_t ownId, uint16_t peerId);
    // Writes and verifies a new upper bound before handing out a counter.
    bool next(uint32_t& value);
    uint32_t reserved() const { return upper_; }
    bool ready() const { return ready_; }
    bool outgoing(uint16_t netId, uint16_t sender, uint16_t recipient) const {
        return ready_ && netId_ == netId && ownId_ == sender && peerId_ == recipient;
    }

private:
    bool reserve(uint32_t upper);
    journal::Storage& storage_;
    uint8_t peerSlot_;
    uint16_t netId_ = 0, ownId_ = 0, peerId_ = 0;
    uint32_t sequence_ = 0, upper_ = 0, current_ = 0;
    uint8_t slot_ = 1;
    bool ready_ = false;
};

}  // namespace envelope
