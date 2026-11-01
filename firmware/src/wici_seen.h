// SPDX-License-Identifier: MIT
// Durable record of recently forwarded envelope identities across hop rewrites.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "journal.h"

namespace wici_seen {
constexpr uint32_t BASE = 0x046900;
constexpr uint32_t SLOT_BYTES = 24;
constexpr uint16_t SLOTS = 224;
constexpr uint32_t WINDOW_S = 60 * 60;
static_assert(BASE + SLOTS * SLOT_BYTES <= 0x048000, "seen ring before FRAM FS");

enum class Lookup : uint8_t { NONE, MATCH, CONFLICT, IO_ERROR };

class Ring {
public:
    explicit Ring(journal::Storage& storage) : storage_(storage) {}
    bool begin();
    Lookup lookup(const uint8_t* authenticatedWire, size_t length, uint32_t nowS);
    // Call only after the next hop accepted the frame and before freeing its
    // durable relay slot. A failed write leaves the slot pending.
    bool remember(const uint8_t* authenticatedWire, size_t length, uint32_t nowS);

private:
    journal::Storage& storage_;
    uint8_t records_[SLOTS][SLOT_BYTES] = {};
    bool ready_ = false;
};
}  // namespace wici_seen
