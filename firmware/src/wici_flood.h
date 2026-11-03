// SPDX-License-Identifier: MIT
// Durable envelope-identity ring for one-time emergency downlink flooding.
// A caller records an identity before broadcasting. Once the radio reports
// that broadcast sent, the identity is never sent again inside WINDOW_S, even
// after a power cut. A broadcast the radio refused, or whose TX failed, was
// not on air: the caller, holding that fact in RAM, may still send it later
// in the same boot.
// The numbered station bearer reports a flood attempt as undelivered, so SA1
// retry seals a fresh counter.
#pragma once

#include <stdint.h>

#include "journal.h"

namespace wici_flood {

constexpr uint32_t BASE_A = 0x044200;
constexpr uint32_t BASE_B = 0x045A00;
constexpr uint16_t SLOTS = 256;
constexpr uint16_t SLOTS_A = 192;
constexpr uint8_t SLOT_BYTES = 18;
constexpr uint32_t WINDOW_S = 120;
static_assert(BASE_A + SLOTS_A * SLOT_BYTES <= 0x045000, "flood ring before relay queue");
static_assert(BASE_B + (SLOTS - SLOTS_A) * SLOT_BYTES <= 0x046000, "flood ring before routes");

enum class Lookup : uint8_t { NONE, MATCH, IO_ERROR };

class Ring {
public:
    explicit Ring(journal::Storage& storage) : storage_(storage) {}
    // A damaged record is tombstoned and counted (cleared()) instead of
    // blocking the link: at worst one identity could be flooded once more
    // inside WINDOW_S, and its destination refuses the repeat.
    bool begin(uint16_t network);
    uint16_t cleared() const { return cleared_; }
    Lookup lookup(const uint8_t envelopeHeader[9], uint32_t nowS) const;
    // Write and verify the marker before the caller starts a flood TX. A full
    // fresh ring or uncertain write fails closed; no radio frame may be sent.
    bool remember(const uint8_t envelopeHeader[9], uint32_t nowS);
    bool ready() const { return ready_; }

private:
    journal::Storage& storage_;
    uint8_t records_[SLOTS][SLOT_BYTES] = {};
    uint16_t network_ = 0, cleared_ = 0;
    bool ready_ = false;
};

}  // namespace wici_flood
