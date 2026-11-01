// SPDX-License-Identifier: MIT
#include "wici_seq.h"

#include "fram_record.h"

namespace wici_seq {
namespace {
using namespace fram_record;
constexpr uint8_t MAGIC[4] = {'W', 'S', 'Q', '1'};
}  // namespace

bool Counter::begin(uint16_t network, uint16_t own) {
    ready_ = false;
    generation_ = upper_ = current_ = 0;
    copy_ = 1;
    if (!id(network) || !id(own)) return false;
    network_ = network; own_ = own;
    bool found = false;
    for (uint8_t copy = 0; copy < 2; ++copy) {
        uint8_t data[SLOT_BYTES];
        Copy state;
        if (!load(storage_, BASE + copy * SLOT_BYTES, data, sizeof(data), 16, MAGIC, state)) return false;
        if (state == Copy::ABSENT) continue;
        // The reservation stays monotonic across renumbering; the record
        // takes the new binding with its next block.
        if (state == Copy::DAMAGED || !get32(data + 12) || get32(data + 12) % BLOCK) return false;
        const uint32_t generation = get32(data + 8);
        if (!found || newer(generation, generation_)) {
            generation_ = generation; upper_ = get32(data + 12); copy_ = copy; found = true;
        }
    }
    current_ = upper_;
    ready_ = true;
    return true;
}

bool Counter::reserve(uint32_t upper) {
    uint8_t data[SLOT_BYTES] = {};
    memcpy(data, MAGIC, 4);
    put16(data + 4, network_); put16(data + 6, own_);
    put32(data + 8, generation_ + 1); put32(data + 12, upper);
    const uint8_t target = static_cast<uint8_t>(1 - copy_);
    if (!store(storage_, BASE + target * SLOT_BYTES, data, sizeof(data), 16)) return false;
    upper_ = upper; ++generation_; copy_ = target;
    return true;
}

bool Counter::next(uint16_t& sequence) {
    if (!ready_) return false;
    if (current_ == upper_) {
        if (upper_ > UINT32_MAX - BLOCK || !reserve(upper_ + BLOCK)) {
            ready_ = false;
            return false;
        }
    }
    sequence = static_cast<uint16_t>(current_++);
    return true;
}
}  // namespace wici_seq
