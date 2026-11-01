// SPDX-License-Identifier: MIT
#include "wici_seq.h"

#include <string.h>

namespace wici_seq {
namespace {
constexpr uint8_t MAGIC[4] = {'W', 'S', 'Q', '1'}, COMMIT = 0xA5;
uint16_t u16(const uint8_t* p) { return static_cast<uint16_t>((p[0] << 8) | p[1]); }
uint32_t u32(const uint8_t* p) {
    return (static_cast<uint32_t>(p[0]) << 24) | (static_cast<uint32_t>(p[1]) << 16) |
           (static_cast<uint32_t>(p[2]) << 8) | p[3];
}
void put16(uint8_t* p, uint16_t n) { p[0] = static_cast<uint8_t>(n >> 8); p[1] = static_cast<uint8_t>(n); }
void put32(uint8_t* p, uint32_t n) {
    p[0] = static_cast<uint8_t>(n >> 24); p[1] = static_cast<uint8_t>(n >> 16);
    p[2] = static_cast<uint8_t>(n >> 8); p[3] = static_cast<uint8_t>(n);
}
uint16_t crc(const uint8_t* p, size_t count) {
    uint16_t c = 0xFFFF;
    for (size_t i = 0; i < count; ++i) {
        c ^= static_cast<uint16_t>(p[i]) << 8;
        for (uint8_t j = 0; j < 8; ++j)
            c = c & 0x8000 ? static_cast<uint16_t>((c << 1) ^ 0x1021) : static_cast<uint16_t>(c << 1);
    }
    return c;
}
bool blank(const uint8_t* p) {
    bool zero = true, erased = true;
    for (size_t i = 0; i < SLOT_BYTES; ++i) { zero &= p[i] == 0; erased &= p[i] == 0xFF; }
    return zero || erased;
}
}  // namespace

bool Counter::begin(uint16_t network, uint16_t own) {
    ready_ = false;
    generation_ = upper_ = current_ = 0;
    copy_ = 1;
    if (!network || network == 0xFFFF || !own || own == 0xFFFF) return false;
    network_ = network; own_ = own;
    bool found = false;
    for (uint8_t copy = 0; copy < 2; ++copy) {
        uint8_t data[SLOT_BYTES];
        if (!storage_.read(BASE + copy * SLOT_BYTES, data, sizeof(data))) return false;
        if (blank(data) || data[31] != COMMIT) continue;
        if (memcmp(data, MAGIC, 4) || u16(data + 4) != network || u16(data + 6) != own ||
            u16(data + 16) != crc(data, 16) || !u32(data + 12) || u32(data + 12) % BLOCK) return false;
        const uint32_t generation = u32(data + 8);
        if (!found || static_cast<int32_t>(generation - generation_) > 0) {
            generation_ = generation; upper_ = u32(data + 12); copy_ = copy; found = true;
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
    put16(data + 16, crc(data, 16));
    const uint8_t target = static_cast<uint8_t>(1 - copy_);
    const uint32_t at = BASE + target * SLOT_BYTES;
    const uint8_t clear = 0;
    if (!storage_.write(at + 31, &clear, 1) || !storage_.write(at, data, 31) ||
        !storage_.write(at + 31, &COMMIT, 1)) return false;
    uint8_t verify[SLOT_BYTES];
    if (!storage_.read(at, verify, sizeof(verify)) || memcmp(data, verify, 31) || verify[31] != COMMIT) return false;
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
