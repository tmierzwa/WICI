// SPDX-License-Identifier: MIT
// WICI-Link tree routing state. Link authentication is done before these methods.
// Down routes are double-buffered in FRAM; beacons and link quality are soft state.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "journal.h"
#include "wici_link.h"

namespace wici_route {

constexpr uint32_t BASE = 0x046000;
constexpr uint32_t COPY_BYTES = 1152;
constexpr size_t ROUTES = 256;
constexpr size_t NEIGHBORS = 16;
constexpr uint32_t BEACON_STALE_S = 90 * 60;
static_assert(BASE + 2 * COPY_BYTES <= 0x048000, "route table before FRAM FS");

struct Config {
    uint16_t network = 0, own = 0, root = 0, planned = 0, backup = 0;
};

struct Beacon {
    uint16_t root = 0, rank = 0, epoch = 0, parent = 0;
    uint8_t flags = 0;
};

bool parseBeacon(const wici_link::Frame& frame, Beacon& out);
// Convert packet SNR (quarter dB) to a nonzero link cost in 1/16 units.
uint16_t snrCost16(int16_t snrQdb);

class Table {
public:
    Table(journal::Storage& storage, Config config) : storage_(storage), config_(config) {}
    // A committed record with a bad binding/CRC fails closed. A torn newer copy
    // falls back to the previous committed one.
    bool begin();
    bool ready() const { return ready_; }
    // Only after authenticated uplink DATA was durably admitted at this hop.
    bool learn(uint16_t destination, uint16_t via);
    bool forget(uint16_t destination, uint16_t via);
    uint16_t down(uint16_t destination) const;  // BROADCAST when no route
    // Beacons are soft state; caller supplies measured ETX/SNR cost in 1/16 units.
    bool beacon(uint16_t neighbor, const Beacon& value, uint16_t linkCost16, uint32_t nowS);
    void hopResult(uint16_t neighbor, bool acknowledged, uint32_t nowS);
    uint16_t parent() const { return parent_; }
    uint16_t rank() const { return rank_; }
    uint16_t epoch() const { return epoch_; }
    bool setRootEpoch(uint16_t epoch);

private:
    struct Route { uint16_t destination = 0, via = 0; };
    struct Neighbor {
        uint16_t id = 0, rank = 0, cost = 0, epoch = 0, parent = 0;
        uint32_t lastSeenS = 0;
        uint16_t snrCost = 16;
        uint8_t delivery16 = 16;
    };
    bool commit();
    void selectParent(uint32_t nowS);
    const Neighbor* candidate(uint16_t id, uint32_t nowS) const;
    journal::Storage& storage_;
    Config config_;
    Route routes_[ROUTES] = {};
    Neighbor neighbors_[NEIGHBORS] = {};
    uint32_t generation_ = 0;
    uint16_t epoch_ = 0, rank_ = 0xFFFF, rankCeiling_ = 0xFFFF;
    uint16_t parent_ = 0, failedDynamic_ = 0;
    uint8_t currentCopy_ = 1, plannedFailures_ = 0, backupFailures_ = 0, dynamicFailures_ = 0;
    bool ready_ = false, epochKnown_ = false;
};

}  // namespace wici_route
