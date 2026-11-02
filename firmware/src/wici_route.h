// SPDX-License-Identifier: MIT
// WICI-Link tree routing state. The caller verifies the root epoch token and
// the beacon sender's signature before calling beacon().
// Down routes are double-buffered in FRAM; beacons and link quality are soft state.
// A station always has a parent: the planned one is the floor, usable from
// boot without any BEACON. Three hop failures rotate planned -> backup ->
// best dynamic neighbour -> planned.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "config.h"
#include "journal.h"
#include "wici_link.h"
#include "wici_epoch.h"

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
    uint8_t epochSignature[wici_epoch::SIGNATURE_BYTES] = {};
    uint16_t sequence = 0;  // link seq of the frame (under the network MAC), not signed content
};

bool parseBeacon(const wici_link::Frame& frame, Beacon& out);

// Convert packet SNR (quarter dB) to a nonzero link cost in 1/16 units.
uint16_t snrCost16(int16_t snrQdb);

class Table {
public:
    // `peers` (priority_keys, must outlive the table) are the neighbours with a
    // pairwise key; without them every neighbour counts as paired. `behind`
    // (the network plan, must outlive the table) lists the stations behind
    // each neighbour, on their planned path or only on a backup one; a
    // neighbour always stands for itself on its planned path.
    Table(journal::Storage& storage, Config config,
          const config::PriorityKey* peers = nullptr, uint8_t peerCount = 0,
          const config::Behind* behind = nullptr, uint16_t behindCount = 0)
        : storage_(storage), config_(config), peers_(peers), peerCount_(peers ? peerCount : 0),
          behind_(behind), behindCount_(behind ? behindCount : 0) {}
    // A committed record with a bad binding/CRC fails closed. A torn newer copy
    // falls back to the previous committed one. Routes via a neighbour without
    // a pairwise key (removed by a reconfiguration) or outside the current
    // plan (`behind`) are dropped.
    bool begin();
    bool ready() const { return ready_; }
    // Only after authenticated uplink DATA was durably admitted at this hop,
    // and only as the network plan allows: `destination` is `via` itself or
    // stands behind it (`behind`). Anything else is refused (false, ready()
    // unchanged); relays and the root share this one check. An existing
    // route to another station is replaced with `replace` (the root, on the
    // laptop's "learn" HACK for a fresh authenticated envelope). A relay
    // cannot authenticate the claimed envelope sender: it learns a missing
    // route (none yet, or forgotten after 3 downward failures) and replaces
    // only a route via a backup-only neighbour by one via the neighbour on
    // the planned path; equal classes never replace each other. The route
    // of a neighbour to itself (pairwise tag) always replaces.
    bool learn(uint16_t destination, uint16_t via, bool replace = false);
    // Plan class of `destination` via `via`; ordered, a higher one wins.
    enum class Plan : uint8_t { NONE, BACKUP, PLANNED };
    Plan plan(uint16_t destination, uint16_t via) const;
    bool planned(uint16_t destination, uint16_t via) const { return plan(destination, via) != Plan::NONE; }
    bool forget(uint16_t destination, uint16_t via);
    uint16_t down(uint16_t destination) const;  // BROADCAST when no route
    // Every check of beacon() that needs no signature: fields, epoch age and
    // replay (`seq` not newer than the last BEACON of a fresh entry). The
    // caller runs it before spending its signature budget, so a replayed or
    // malformed BEACON costs no Ed25519 check.
    bool acceptable(uint16_t neighbor, const Beacon& value, uint32_t nowS) const;
    // Beacons are soft state; caller supplies measured ETX/SNR cost in 1/16 units.
    bool beacon(uint16_t neighbor, const Beacon& value, uint16_t linkCost16, uint32_t nowS);
    void hopResult(uint16_t neighbor, bool acknowledged, uint32_t nowS);
    // Loop signal from the data plane (upward DATA from the current parent, or
    // this station's own envelope coming back up): rotate the parent at once,
    // as at the failure threshold.
    void loop(uint32_t nowS);
    // Never 0 on a station (the planned parent is the floor); 0 on the root.
    uint16_t parent() const { return parent_; }
    // The parent's rank plus the link cost to it, from the parent's BEACON
    // while it is fresh at nowS (rule 4); 0 on the root. 0xFFFF without such a
    // BEACON: the station then sends and relays DATA upward but does not BEACON.
    uint16_t rank(uint32_t nowS) const;
    uint16_t epoch() const { return epoch_; }
    bool epochKnown() const { return epochKnown_; }
    const uint8_t* epochSignature() const { return epochSignature_; }
    bool setRootEpoch(uint16_t epoch);

private:
    struct Route { uint16_t destination = 0, via = 0; };
    struct Neighbor {
        uint16_t id = 0, rank = 0, cost = 0, epoch = 0, parent = 0;
        uint32_t lastSeenS = 0;
        uint16_t snrCost = 16;
        uint8_t delivery16 = 16;
        uint16_t sequence = 0;  // last accepted BEACON seq: while fresh, an older or equal one is a replay
    };
    bool commit();
    bool paired(uint16_t id) const;
    const Neighbor* find(uint16_t id) const;
    bool fresh(const Neighbor& n, uint32_t nowS) const;
    bool usable(uint16_t id, uint32_t nowS) const;
    uint16_t bestDynamic(uint32_t nowS) const;
    uint16_t rotation(uint8_t step, uint32_t nowS) const;
    uint8_t step(uint16_t id) const;
    void setParent(uint16_t id, uint32_t nowS);
    void lowerCeiling(uint32_t nowS);
    void reconsider(uint16_t neighbor, bool heard, uint32_t nowS);
    journal::Storage& storage_;
    Config config_;
    const config::PriorityKey* peers_ = nullptr;
    uint8_t peerCount_ = 0;
    const config::Behind* behind_ = nullptr;
    uint16_t behindCount_ = 0;
    Route routes_[ROUTES] = {};
    Neighbor neighbors_[NEIGHBORS] = {};
    uint32_t generation_ = 0;
    uint16_t epoch_ = 0, rankCeiling_ = 0xFFFF;  // lowest rank held in this epoch
    uint8_t epochSignature_[wici_epoch::SIGNATURE_BYTES] = {};
    uint16_t parent_ = 0;
    uint8_t currentCopy_ = 1, failures_ = 0;  // consecutive hop failures of parent_
    uint16_t nextRoute_ = 0;
    uint32_t epochHeardS_ = 0;  // new epoch adopted or current parent's last BEACON
    bool ready_ = false, epochKnown_ = false;
};

}  // namespace wici_route
