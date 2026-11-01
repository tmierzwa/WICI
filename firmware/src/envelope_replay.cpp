// SPDX-License-Identifier: MIT
#include "envelope_replay.h"

#include <string.h>
#include "sha2.h"

namespace envelope {
namespace {
constexpr uint8_t MAGIC[4] = {'W', 'R', 'P', '1'}, COMMIT = 0xA5;
uint32_t u32(const uint8_t* p) {
    return (static_cast<uint32_t>(p[0]) << 24) | (static_cast<uint32_t>(p[1]) << 16) |
           (static_cast<uint32_t>(p[2]) << 8) | p[3];
}
uint64_t u64(const uint8_t* p) {
    uint64_t n = 0;
    for (uint8_t i = 0; i < 8; ++i) n = (n << 8) | p[i];
    return n;
}
void put16(uint8_t* p, uint16_t n) { p[0] = static_cast<uint8_t>(n >> 8); p[1] = static_cast<uint8_t>(n); }
uint16_t u16(const uint8_t* p) { return static_cast<uint16_t>((p[0] << 8) | p[1]); }
void put32(uint8_t* p, uint32_t n) {
    p[0] = static_cast<uint8_t>(n >> 24); p[1] = static_cast<uint8_t>(n >> 16);
    p[2] = static_cast<uint8_t>(n >> 8); p[3] = static_cast<uint8_t>(n);
}
void put64(uint8_t* p, uint64_t n) {
    for (int i = 7; i >= 0; --i) { p[i] = static_cast<uint8_t>(n); n >>= 8; }
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
    for (uint8_t i = 0; i < REPLAY_SLOT_BYTES; ++i) {
        zero &= p[i] == 0; erased &= p[i] == 0xFF;
    }
    return zero || erased;
}
bool id(uint16_t n) { return n && n != 0xFFFF; }
uint32_t address(uint8_t peer, uint8_t copy) {
    return REPLAY_BASE + (static_cast<uint32_t>(peer) * 2 + copy) * REPLAY_SLOT_BYTES;
}
}  // namespace

bool DurableReplay::begin(uint16_t network, uint16_t recipient, uint16_t sender, const uint8_t key[32]) {
    ready_ = false;
    window_ = ReplayWindow();
    generation_ = 0;
    copy_ = 1;
    if (peerSlot_ >= REPLAY_PEERS || !key || !id(network) || !id(recipient) || !id(sender) ||
        recipient == sender) return false;
    uint8_t digest[sha2::DIGEST];
    sha2::digest(key, 32, digest);
    memcpy(fingerprint_, digest, sizeof(fingerprint_));
    memset(digest, 0, sizeof(digest));
    network_ = network; recipient_ = recipient; sender_ = sender;
    bool found = false;
    for (uint8_t copy = 0; copy < 2; ++copy) {
        uint8_t record[REPLAY_SLOT_BYTES];
        if (!storage_.read(address(peerSlot_, copy), record, sizeof(record))) return false;
        if (blank(record) || record[31] != COMMIT) continue;
        if (memcmp(record, MAGIC, 4) || record[30] != 1 ||
            u16(record + 28) != crc(record, 28) || !(u64(record + 20) & 1)) return false;
        if (memcmp(record + 8, fingerprint_, sizeof(fingerprint_))) continue;
        const uint32_t generation = u32(record + 4);
        if (!found || static_cast<int32_t>(generation - generation_) > 0) {
            generation_ = generation;
            copy_ = copy;
            window_.highest = u32(record + 16);
            window_.mask = u64(record + 20);
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
    uint8_t record[REPLAY_SLOT_BYTES] = {};
    memcpy(record, MAGIC, 4);
    put32(record + 4, generation_ + 1);
    memcpy(record + 8, fingerprint_, sizeof(fingerprint_));
    put32(record + 16, next.highest);
    put64(record + 20, next.mask);
    record[30] = 1;
    put16(record + 28, crc(record, 28));
    const uint8_t target = static_cast<uint8_t>(1 - copy_);
    const uint32_t at = address(peerSlot_, target);
    const uint8_t clear = 0;
    if (!storage_.write(at + 31, &clear, 1) || !storage_.write(at, record, 31) ||
        !storage_.write(at + 31, &COMMIT, 1)) {
        ready_ = false;
        return false;
    }
    uint8_t verify[REPLAY_SLOT_BYTES];
    if (!storage_.read(at, verify, sizeof(verify)) || memcmp(record, verify, 31) || verify[31] != COMMIT) {
        ready_ = false;
        return false;
    }
    copy_ = target;
    ++generation_;
    window_ = next;
    return true;
}

}  // namespace envelope
