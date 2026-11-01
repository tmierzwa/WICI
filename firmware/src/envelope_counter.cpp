// SPDX-License-Identifier: MIT
#include "envelope_counter.h"

#include <string.h>
#include "sha2.h"

namespace envelope {
namespace {

constexpr uint8_t COMMIT = 0xA5;
constexpr uint8_t MAGIC[4] = {'W', 'C', 'T', '1'};

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
uint16_t crc(const uint8_t* p, size_t length) {
    uint16_t c = 0xFFFF;
    for (size_t i = 0; i < length; ++i) {
        c ^= static_cast<uint16_t>(p[i]) << 8;
        for (uint8_t b = 0; b < 8; ++b) c = c & 0x8000 ? static_cast<uint16_t>((c << 1) ^ 0x1021) : static_cast<uint16_t>(c << 1);
    }
    return c;
}
uint32_t address(uint8_t peer, uint8_t slot) {
    return COUNTER_BASE + (static_cast<uint32_t>(peer) * 2 + slot) * COUNTER_SLOT_BYTES;
}
bool blank(const uint8_t* p) {
    bool zero = true, erased = true;
    for (size_t i = 0; i < COUNTER_SLOT_BYTES; ++i) {
        zero &= p[i] == 0;
        erased &= p[i] == 0xFF;
    }
    return zero || erased;
}

}  // namespace

bool Counter::begin(uint16_t netId, uint16_t ownId, uint16_t peerId, const uint8_t key[32]) {
    ready_ = false;
    sequence_ = upper_ = current_ = 0;
    slot_ = 1;
    if (peerSlot_ >= COUNTER_PEERS || !key || !netId || netId == 0xFFFF || !ownId || !peerId ||
        ownId == 0xFFFF || peerId == 0xFFFF || ownId == peerId) return false;
    uint8_t digest[sha2::DIGEST];
    sha2::digest(key, 32, digest);
    memcpy(fingerprint_, digest, sizeof(fingerprint_));
    memset(digest, 0, sizeof(digest));
    netId_ = netId; ownId_ = ownId; peerId_ = peerId;
    bool found = false;
    for (uint8_t i = 0; i < 2; ++i) {
        uint8_t data[COUNTER_SLOT_BYTES];
        if (!storage_.read(address(peerSlot_, i), data, sizeof(data))) return false;
        if (blank(data) || data[31] != COMMIT) continue;  // interrupted write cannot have issued counters
        if (memcmp(data, MAGIC, 4) || u16(data + 26) != crc(data, 26) ||
            u32(data + 14) == 0 || (u32(data + 14) % COUNTER_BLOCK) != 0) return false;
        // Reservation space stays monotonic across rekeys. Reusing an older
        // identity later must not restart its nonce counter at zero.
        if (!memcmp(data + 18, fingerprint_, sizeof(fingerprint_)) &&
            (u16(data + 4) != netId || u16(data + 6) != ownId || u16(data + 8) != peerId)) return false;
        uint32_t sequence = u32(data + 10);
        if (!found || static_cast<int32_t>(sequence - sequence_) > 0) {
            sequence_ = sequence; upper_ = u32(data + 14); slot_ = i; found = true;
        }
    }
    current_ = upper_;  // skip every reserved but possibly unused counter after restart
    ready_ = true;
    return true;
}

bool Counter::reserve(uint32_t upper) {
    uint8_t data[COUNTER_SLOT_BYTES] = {};
    memcpy(data, MAGIC, 4);
    put16(data + 4, netId_); put16(data + 6, ownId_); put16(data + 8, peerId_);
    put32(data + 10, sequence_ + 1); put32(data + 14, upper);
    memcpy(data + 18, fingerprint_, sizeof(fingerprint_));
    put16(data + 26, crc(data, 26));
    const uint8_t target = static_cast<uint8_t>(1 - slot_);
    const uint32_t at = address(peerSlot_, target);
    const uint8_t uncommitted = 0;
    if (!storage_.write(at + 31, &uncommitted, 1) || !storage_.write(at, data, 31) ||
        !storage_.write(at + 31, &COMMIT, 1)) return false;
    uint8_t verify[COUNTER_SLOT_BYTES];
    if (!storage_.read(at, verify, sizeof(verify)) || memcmp(data, verify, 31) || verify[31] != COMMIT) return false;
    slot_ = target; ++sequence_; upper_ = upper;
    return true;
}

bool Counter::outgoing(uint16_t netId, uint16_t sender, uint16_t recipient,
                       const uint8_t key[32]) const {
    if (!ready_ || !key || netId_ != netId || ownId_ != sender || peerId_ != recipient) return false;
    uint8_t digest[sha2::DIGEST];
    sha2::digest(key, 32, digest);
    const bool match = memcmp(digest, fingerprint_, sizeof(fingerprint_)) == 0;
    memset(digest, 0, sizeof(digest));
    return match;
}

bool Counter::next(uint32_t& value) {
    if (!ready_) return false;
    if (current_ == upper_) {
        if (upper_ > UINT32_MAX - COUNTER_BLOCK || !reserve(upper_ + COUNTER_BLOCK)) {
            ready_ = false;  // uncertain write: restart and inspect FRAM before any more encryption
            return false;
        }
    }
    value = current_++;
    return true;
}

}  // namespace envelope
