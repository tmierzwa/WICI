// SPDX-License-Identifier: MIT
#include "wici_airtime.h"

#include "wici_record.h"

namespace wici_airtime {
namespace {
using namespace wici_record;
constexpr uint8_t MAGIC[4] = {'W', 'A', 'T', '1'};
}  // namespace

bool Budget::begin(uint16_t network, uint16_t own) {
    ready_ = false;
    if (!id(network) || !id(own)) return false;
    network_ = network; own_ = own; sequence_ = epoch_ = 0; copy_ = 1;
    memset(pool_, 0, sizeof(pool_)); memset(beacon_, 0, sizeof(beacon_));
    bool found = false;
    for (uint8_t i = 0; i < 2; ++i) {
        uint8_t data[COPY_BYTES];
        if (!storage_.read(BASE + i * COPY_BYTES, data, sizeof(data))) return false;
        if (!committed(data, sizeof(data))) continue;
        if (memcmp(data, MAGIC, 4) || get16(data + 4) != network || get16(data + 6) != own ||
            get16(data + 44) != crc(data, 44)) return false;
        const uint32_t sequence = get32(data + 8);
        if (!found || newer(sequence, sequence_)) {
            found = true; sequence_ = sequence; epoch_ = get32(data + 12); copy_ = i;
            for (uint8_t b = 0; b < BUCKETS; ++b) {
                pool_[b] = get16(data + 16 + b * 2);
                beacon_[b] = get16(data + 30 + b * 2);
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
    if (!write(storage_, BASE + target * COPY_BYTES, data, sizeof(data))) { ready_ = false; return false; }
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
