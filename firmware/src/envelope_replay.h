// SPDX-License-Identifier: MIT
// Two durable receiver-to-station replay windows. The receiver's windows for
// many shelter stations live in SQLite; a shelter has only main/backup peers.
#pragma once

#include "envelope.h"
#include "journal.h"

namespace envelope {

constexpr uint32_t REPLAY_BASE = 0x044F80;
constexpr uint8_t REPLAY_SLOT_BYTES = 32;
constexpr uint8_t REPLAY_PEERS = 2;
static_assert(REPLAY_BASE + REPLAY_PEERS * 2 * REPLAY_SLOT_BYTES <= 0x045000,
              "replay windows before relay queue");

class DurableReplay {
public:
    DurableReplay(journal::Storage& storage, uint8_t peerSlot) : storage_(storage), peerSlot_(peerSlot) {}
    bool begin(uint16_t network, uint16_t recipient, uint16_t sender, const uint8_t key[32]);
    bool propose(uint32_t counter, ReplayWindow& next) const;
    bool accepted(uint32_t counter) const;
    // Call only after the SA1 effect is durable and idempotent in Store. A
    // crash before this commit may replay the callback, so it must deduplicate
    // by its SA1 identity. Failure blocks further admissions until reload.
    bool commit(uint32_t counter);
    bool ready() const { return ready_; }
    const ReplayWindow& current() const { return window_; }

private:
    journal::Storage& storage_;
    uint8_t peerSlot_;
    uint16_t network_ = 0, recipient_ = 0, sender_ = 0;
    uint8_t fingerprint_[8] = {};
    uint32_t generation_ = 0;
    uint8_t copy_ = 1;
    ReplayWindow window_;
    bool ready_ = false;
};

}  // namespace envelope
