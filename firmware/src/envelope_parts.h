// SPDX-License-Identifier: MIT
// One durable pending fragment per receiver identity at a shelter station.
// A fragment with another counter is rejected until the pending one expires
// (120 s, or a clock that went backwards); a damaged copy fails closed.
// The second fragment is assembled in RAM; caller commits SA1 and replay state
// before sending HACK, then writes a tombstone with clear().
#pragma once

#include "envelope.h"
#include "journal.h"

namespace envelope {

constexpr uint32_t PARTS_MAIN_BASE = 0x045E80;
constexpr uint32_t PARTS_BACKUP_BASE = 0x047E00;
constexpr uint16_t PARTS_COPY_BYTES = 192;
constexpr uint8_t PARTS_PEERS = 2;
constexpr uint32_t PARTS_TIMEOUT_S = 120;
static_assert(PARTS_MAIN_BASE + 2 * PARTS_COPY_BYTES <= 0x046000, "parts before routes");
static_assert(PARTS_BACKUP_BASE + 2 * PARTS_COPY_BYTES <= 0x048000, "parts before FRAM FS");

enum class FragmentResult : uint8_t { PARTIAL, DUPLICATE, COMPLETE, REJECTED, IO_ERROR };

class DurableParts {
public:
    DurableParts(journal::Storage& storage, uint8_t peerSlot) : storage_(storage), peerSlot_(peerSlot) {}
    bool begin(uint16_t network, uint16_t recipient, uint16_t sender, const uint8_t key[32]);
    // Caller already authenticated `part` with the envelope AEAD. PARTIAL is
    // safe to HACK only after the write/readback performed here. COMPLETE
    // returns plaintext without changing FRAM; caller must commit SA1 first.
    // DUPLICATE: a byte-identical repeat of the stored part, already durable.
    FragmentResult ingest(const Part& part, uint32_t nowS, uint8_t full[MAX_SA1], size_t& length);
    bool clear();
    bool pending() const { return ready_ && length_ != 0; }
    uint32_t pendingCounter() const { return pending() ? counter_ : 0; }

private:
    bool commit(const Part* part, uint32_t nowS);
    journal::Storage& storage_;
    uint8_t peerSlot_;
    uint16_t network_ = 0, recipient_ = 0, sender_ = 0;
    uint32_t generation_ = 0, counter_ = 0, startedS_ = 0;
    uint8_t copy_ = 1, number_ = 0, length_ = 0;
    uint8_t data_[MAX_SA1 / 2] = {};
    uint8_t fingerprint_[8] = {};
    bool ready_ = false;
};

}  // namespace envelope
