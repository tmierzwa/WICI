// SPDX-License-Identifier: MIT
// Durable WICI-Link sequence reservation. Skips unused values after restart.
#pragma once

#include <stdint.h>

#include "journal.h"

namespace wici_seq {
constexpr uint32_t BASE = 0x044180;
constexpr uint32_t SLOT_BYTES = 32;
constexpr uint32_t BLOCK = 64;
static_assert(BASE + 2 * SLOT_BYTES <= 0x044200, "link sequence before relay metadata");

class Counter {
public:
    explicit Counter(journal::Storage& storage) : storage_(storage) {}
    bool begin(uint16_t network, uint16_t own);
    bool next(uint16_t& sequence);
    bool ready() const { return ready_; }

private:
    bool reserve(uint32_t upper);
    journal::Storage& storage_;
    uint16_t network_ = 0, own_ = 0;
    uint32_t generation_ = 0, upper_ = 0, current_ = 0;
    uint8_t copy_ = 1;
    bool ready_ = false;
};
}  // namespace wici_seq
