// SPDX-License-Identifier: MIT
#include "wici_airtime.h"

#include <string.h>

namespace wici_airtime {
namespace {
constexpr uint8_t MAGIC[4] = {'W', 'A', 'T', '1'};
constexpr uint8_t COMMIT = 0xA5;
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
        for (uint8_t b = 0; b < 8; ++b)
            c = c & 0x8000 ? static_cast<uint16_t>((c << 1) ^ 0x1021) : static_cast<uint16_t>(c << 1);
    }
    return c;
}
bool blank(const uint8_t* p) {
    bool zero = true, erased = true;
    for (size_t i = 0; i < COPY_BYTES; ++i) { zero &= p[i] == 0; erased &= p[i] == 0xFF; }
    return zero || erased;
}
}  // namespace

bool Budget::begin(uint16_t network, uint16_t own) {
    ready_ = false;
    if (!network || network == 0xFFFF || !own || own == 0xFFFF) return false;
    network_ = network; own_ = own; sequence_ = epoch_ = 0; copy_ = 1;
    memset(pool_, 0, sizeof(pool_)); memset(beacon_, 0, sizeof(beacon_));
    bool found = false;
    for (uint8_t i = 0; i < 2; ++i) {
        uint8_t data[COPY_BYTES];
        if (!storage_.read(BASE + i * COPY_BYTES, data, sizeof(data))) return false;
        if (blank(data) || data[63] != COMMIT) continue;
        if (memcmp(data, MAGIC, 4) || u16(data + 4) != network || u16(data + 6) != own ||
            u16(data + 44) != crc(data, 44)) return false;
        const uint32_t sequence = u32(data + 8);
        if (!found || static_cast<int32_t>(sequence - sequence_) > 0) {
            found = true; sequence_ = sequence; epoch_ = u32(data + 12); copy_ = i;
            for (uint8_t b = 0; b < BUCKETS; ++b) {
                pool_[b] = u16(data + 16 + b * 2);
                beacon_[b] = u16(data + 30 + b * 2);
            }
        }
    }
    ready_ = true;
    return true;
}

void Budget::advance(uint32_t epoch) {
    if (epoch <= epoch_) return;  // a clock rollback never restores spent budget
    const uint32_t steps = epoch - epoch_;
    if (steps >= BUCKETS) {
        memset(pool_, 0, sizeof(pool_)); memset(beacon_, 0, sizeof(beacon_));
    } else {
        for (uint32_t n = 1; n <= steps; ++n) {
            const uint8_t slot = static_cast<uint8_t>((epoch_ + n) % BUCKETS);
            pool_[slot] = beacon_[slot] = 0;
        }
    }
    epoch_ = epoch;
}

uint32_t Budget::poolUsed() const {
    uint32_t total = 0;
    for (uint16_t n : pool_) total += n;
    return total * 100;
}
uint32_t Budget::beaconUsed() const {
    uint32_t total = 0;
    for (uint16_t n : beacon_) total += n;
    return total * 100;
}

bool Budget::commit() {
    uint8_t data[COPY_BYTES] = {};
    memcpy(data, MAGIC, 4);
    put16(data + 4, network_); put16(data + 6, own_);
    put32(data + 8, sequence_ + 1); put32(data + 12, epoch_);
    for (uint8_t b = 0; b < BUCKETS; ++b) {
        put16(data + 16 + b * 2, pool_[b]);
        put16(data + 30 + b * 2, beacon_[b]);
    }
    put16(data + 44, crc(data, 44));
    const uint8_t target = static_cast<uint8_t>(1 - copy_);
    const uint32_t at = BASE + target * COPY_BYTES;
    const uint8_t clear = 0;
    if (!storage_.write(at + 63, &clear, 1) || !storage_.write(at, data, 63) ||
        !storage_.write(at + 63, &COMMIT, 1)) { ready_ = false; return false; }
    uint8_t verify[COPY_BYTES];
    if (!storage_.read(at, verify, sizeof(verify)) || memcmp(data, verify, 63) ||
        verify[63] != COMMIT) { ready_ = false; return false; }
    copy_ = target; ++sequence_;
    return true;
}

bool Budget::reserve(bool isBeacon, uint32_t txMs, uint32_t nowS, bool contendedK2) {
    if (!ready_ || !txMs || txMs > 1000 || sequence_ == UINT32_MAX) return false;
    advance(nowS / BUCKET_S);
    const uint32_t cost = (txMs * 13 + 99) / 100;
    const uint32_t beaconCost = (txMs + 99) / 100;
    if (poolUsed() / 100 + cost > POOL_CAP_MS / 100 ||
        (contendedK2 && poolUsed() / 100 + cost > CONTENDED_K2_CAP_MS / 100) ||
        (isBeacon && beaconUsed() / 100 + beaconCost > BEACON_CAP_MS / 100)) return false;
    const uint8_t slot = static_cast<uint8_t>(epoch_ % BUCKETS);
    pool_[slot] = static_cast<uint16_t>(pool_[slot] + cost);
    if (isBeacon) beacon_[slot] = static_cast<uint16_t>(beacon_[slot] + beaconCost);
    return commit();
}

}  // namespace wici_airtime
