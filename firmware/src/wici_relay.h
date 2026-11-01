// SPDX-License-Identifier: MIT
// Four durable WICI-Link frames in the unused FRAM gap before the Reticulum FS.
// A caller may send HACK only for STORED or DUPLICATE. Routing and airtime policy
// are separate; an authenticated frame alone never authorizes HACK.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "journal.h"
#include "wici_link.h"
#include "wici_seen.h"

namespace wici_relay {

constexpr uint32_t BASE = 0x045000;
constexpr uint32_t COPY_BYTES = 320;
constexpr uint8_t SLOTS = 4;
constexpr uint32_t MAX_HOLD_S = 30 * 60;
static_assert(BASE + 2 * SLOTS * COPY_BYTES <= 0x048000, "relay queue before FRAM FS");

enum class Admission : uint8_t { STORED, DUPLICATE, FORWARDED, FULL, REJECTED, IO_ERROR };

class Queue {
public:
    explicit Queue(journal::Storage& storage) : storage_(storage), seen_(storage) {}
    // Corrupt committed records fail closed. Interrupted writes fall back to the
    // other copy; a removed item is a committed tombstone, not erased memory.
    bool begin();
    Admission admit(const uint8_t key[32], uint16_t network, uint16_t ownId,
                    const uint8_t* wire, size_t length, uint32_t nowS,
                    uint8_t freeSlotsReserved = 0, uint16_t verifiedOrigin = 0);
    bool pending(uint8_t slot) const;
    uint16_t verifiedOrigin(uint8_t slot) const { return pending(slot) ? origins_[slot] : 0; }
    uint32_t generation(uint8_t slot) const { return slot < SLOTS ? generations_[slot] : 0; }
    bool markVerified(uint8_t slot, uint16_t origin);
    bool expire(uint32_t nowS);
    // Recheck the current network binding after reboot/configuration changes;
    // an old queue record must not be forwarded under a new link key. A frame
    // already recorded as forwarded is withheld after a crash before tombstone.
    bool read(const uint8_t key[32], uint16_t network, uint16_t ownId, uint8_t slot,
              uint32_t nowS, uint8_t* out, size_t capacity, size_t& length);
    // Finish a tombstone interrupted after the durable forwarded marker.
    // Refuse old-key/configuration records instead of silently clearing them.
    bool finishForwarded(const uint8_t key[32], uint16_t network, uint16_t ownId, uint32_t nowS);
    // Only after the next hop has accepted the frame. Failure keeps it pending.
    bool remove(uint8_t slot, uint32_t nowS);

private:
    bool commit(uint8_t slot, const uint8_t* wire, size_t length,
                uint16_t verifiedOrigin = 0, uint32_t admittedS = 0);
    journal::Storage& storage_;
    wici_seen::Ring seen_;
    uint8_t frames_[SLOTS][wici_link::MAX_FRAME] = {};
    uint16_t lengths_[SLOTS] = {};
    uint32_t generations_[SLOTS] = {};
    uint8_t copies_[SLOTS] = {};
    uint16_t origins_[SLOTS] = {};  // nonzero only after an origin signature was verified
    uint32_t admittedS_[SLOTS] = {};
    bool ready_ = false;
};

}  // namespace wici_relay
