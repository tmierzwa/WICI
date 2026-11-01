// SPDX-License-Identifier: MIT
#include "wici_route.h"

#include "wici_record.h"

namespace wici_route {
namespace {
using namespace wici_record;
constexpr uint8_t MAGIC[4] = {'W', 'R', 'T', '1'};
constexpr size_t ROUTES_AT = 24, CRC_AT = ROUTES_AT + ROUTES * 4;
static_assert(CRC_AT + 2 < COPY_BYTES, "route record fits");
}  // namespace

bool parseBeacon(const wici_link::Frame& frame, Beacon& out) {
    out = Beacon();
    if (frame.type != wici_link::Type::BEACON || frame.length != wici_link::BEACON_PAYLOAD) return false;
    out.root = get16(frame.payload);
    out.rank = get16(frame.payload + 2);
    out.epoch = get16(frame.payload + 4);
    out.parent = get16(frame.payload + 6);
    out.flags = frame.payload[8];
    memcpy(out.epochSignature, frame.payload + 9, wici_epoch::SIGNATURE_BYTES);
    return id(out.root) && (out.parent == 0 || id(out.parent)) && !(out.flags & ~1);
}

uint16_t snrCost16(int16_t snrQdb) {
    // A positive SNR keeps the ideal one-transmission cost. Negative SNR
    // adds one sixteenth per dB, capped so malformed radio metadata cannot
    // dominate a route indefinitely.
    if (snrQdb >= 0) return 16;
    const uint16_t penalty = static_cast<uint16_t>((-static_cast<int32_t>(snrQdb) + 3) / 4);
    return static_cast<uint16_t>(16 + (penalty > 32 ? 32 : penalty));
}

namespace {
uint16_t measuredCost(uint16_t snrCost, uint8_t delivery16) {
    // delivery16 is an EWMA success probability in sixteenths. 256/p is
    // ETX in sixteenths; the SNR penalty is added only once.
    return static_cast<uint16_t>(256 / delivery16 + snrCost - 16);
}
}  // namespace

bool Table::begin() {
    ready_ = false;
    generation_ = 0;
    currentCopy_ = 1;
    epoch_ = 0;
    epochKnown_ = false;
    epochHeardS_ = 0;
    memset(epochSignature_, 0, sizeof(epochSignature_));
    rank_ = 0xFFFF;
    rankCeiling_ = 0xFFFF;
    parent_ = failedDynamic_ = 0;
    plannedFailures_ = backupFailures_ = dynamicFailures_ = 0;
    nextRoute_ = 0;
    for (Neighbor& neighbor : neighbors_) neighbor = Neighbor();
    const bool rootNode = config_.own == config_.root;
    if (!id(config_.network) || !id(config_.own) || !id(config_.root) ||
        (config_.planned && !id(config_.planned)) || (config_.backup && !id(config_.backup)) ||
        (rootNode ? (config_.planned || config_.backup) :
                    (!config_.planned || config_.planned == config_.own ||
                     config_.backup == config_.own || config_.backup == config_.planned))) return false;
    for (Route& route : routes_) route = Route();
    bool found = false;
    for (uint8_t copy = 0; copy < 2; ++copy) {
        uint8_t data[COPY_BYTES];
        if (!storage_.read(BASE + copy * COPY_BYTES, data, sizeof(data))) return false;
        if (!committed(data, sizeof(data))) continue;
        if (memcmp(data, MAGIC, 4) || get16(data + CRC_AT) != crc(data, CRC_AT)) return false;
        // Routes learned under other numbers are void; start empty.
        if (get16(data + 8) != config_.network || get16(data + 10) != config_.own ||
            get16(data + 12) != config_.root) continue;
        for (size_t i = 0; i < ROUTES; ++i) {
            const uint16_t dst = get16(data + ROUTES_AT + i * 4);
            const uint16_t via = get16(data + ROUTES_AT + i * 4 + 2);
            if ((dst || via) && (!id(dst) || !id(via) || dst == config_.own || via == config_.own)) return false;
        }
        const uint32_t generation = get32(data + 4);
        if (!found || newer(generation, generation_)) {
            generation_ = generation;
            currentCopy_ = copy;
            for (size_t i = 0; i < ROUTES; ++i) {
                routes_[i].destination = get16(data + ROUTES_AT + i * 4);
                routes_[i].via = get16(data + ROUTES_AT + i * 4 + 2);
            }
            found = true;
        }
    }
    ready_ = true;
    if (rootNode) rank_ = 0;
    return true;
}

bool Table::setRootEpoch(uint16_t epoch) {
    if (!ready_ || config_.own != config_.root) return false;
    epoch_ = epoch;
    epochKnown_ = true;
    return true;
}

bool Table::commit() {
    uint8_t data[COPY_BYTES] = {};
    memcpy(data, MAGIC, 4);
    put32(data + 4, generation_ + 1);
    put16(data + 8, config_.network);
    put16(data + 10, config_.own);
    put16(data + 12, config_.root);
    for (size_t i = 0; i < ROUTES; ++i) {
        put16(data + ROUTES_AT + i * 4, routes_[i].destination);
        put16(data + ROUTES_AT + i * 4 + 2, routes_[i].via);
    }
    put16(data + CRC_AT, crc(data, CRC_AT));
    const uint8_t copy = static_cast<uint8_t>(1 - currentCopy_);
    if (!write(storage_, BASE + copy * COPY_BYTES, data, sizeof(data))) {
        ready_ = false;
        return false;
    }
    ++generation_;
    currentCopy_ = copy;
    return true;
}

bool Table::learn(uint16_t destination, uint16_t via) {
    if (!ready_ || !id(destination) || !id(via) || destination == config_.own ||
        via == config_.own || destination == config_.root) return false;
    size_t empty = ROUTES;
    for (size_t i = 0; i < ROUTES; ++i) {
        if (routes_[i].destination == destination) {
            if (routes_[i].via == via) return true;
            const Route old = routes_[i];
            routes_[i].via = via;
            if (!commit()) { routes_[i] = old; return false; }
            return true;
        }
        if (!routes_[i].destination && empty == ROUTES) empty = i;
    }
    if (empty == ROUTES) empty = nextRoute_++ % ROUTES;
    const Route old = routes_[empty];
    routes_[empty] = {destination, via};
    if (!commit()) { routes_[empty] = old; return false; }
    return true;
}

bool Table::forget(uint16_t destination, uint16_t via) {
    if (!ready_ || !id(destination) || !id(via)) return false;
    for (Route& route : routes_) {
        if (route.destination != destination || route.via != via) continue;
        const Route old = route;
        route = Route();
        if (!commit()) { route = old; return false; }
        return true;
    }
    return true;
}

uint16_t Table::down(uint16_t destination) const {
    if (!ready_ || !id(destination)) return wici_link::BROADCAST;
    for (const Route& route : routes_) if (route.destination == destination) return route.via;
    return wici_link::BROADCAST;
}

const Table::Neighbor* Table::candidate(uint16_t id, uint32_t nowS) const {
    for (const Neighbor& n : neighbors_)
        if (n.id == id && n.epoch == epoch_ && n.parent != config_.own &&
            nowS >= n.lastSeenS && nowS - n.lastSeenS <= BEACON_STALE_S &&
            // A configured backup may have a worse rank than the failed
            // planned route. The ceiling only guards unconfigured neighbors.
            (id == config_.planned || id == config_.backup || n.rank < rankCeiling_) &&
            n.cost && static_cast<uint32_t>(n.rank) + n.cost < 0xFFFF) return &n;
    return nullptr;
}

void Table::selectParent(uint32_t nowS) {
    const Neighbor* chosen = nullptr;
    if (plannedFailures_ < 3) chosen = candidate(config_.planned, nowS);
    if (!chosen && backupFailures_ < 3) chosen = candidate(config_.backup, nowS);
    if (!chosen) {
        for (const Neighbor& neighbor : neighbors_) {
            if ((neighbor.id == config_.planned && plannedFailures_ >= 3) ||
                (neighbor.id == config_.backup && backupFailures_ >= 3) ||
                neighbor.id == failedDynamic_) continue;
            const Neighbor* candidateValue = candidate(neighbor.id, nowS);
            if (candidateValue && (!chosen || static_cast<uint32_t>(candidateValue->rank) + candidateValue->cost <
                                    static_cast<uint32_t>(chosen->rank) + chosen->cost)) chosen = candidateValue;
        }
    }
    if (!chosen) {
        parent_ = 0;
        // Keep the last finite rank as a ceiling within this epoch. Resetting
        // it to infinity here could make a former descendant look eligible and
        // create a multi-node loop after one parent times out.
        return;
    }
    // A dynamic switch needs 1.5 ETX (24/16) improvement; planned/backup
    // failover is exempt because its current link already failed three times.
    if (parent_ && parent_ != chosen->id && parent_ != config_.planned && parent_ != config_.backup) {
        const Neighbor* current = candidate(parent_, nowS);
        if (current && static_cast<uint32_t>(current->rank) + current->cost <=
                       static_cast<uint32_t>(chosen->rank) + chosen->cost + 24) return;
    }
    if (parent_ != chosen->id) dynamicFailures_ = 0;
    parent_ = chosen->id;
    rank_ = static_cast<uint16_t>(chosen->rank + chosen->cost);
    if (rank_ < rankCeiling_) rankCeiling_ = rank_;
}

bool Table::beacon(uint16_t neighbor, const Beacon& value, uint16_t linkCost16, uint32_t nowS) {
    if (!ready_ || config_.own == config_.root || !id(neighbor) || neighbor == config_.own || value.root != config_.root ||
        linkCost16 < 16 || linkCost16 > 48 || value.rank == 0xFFFF || value.parent == config_.own ||
        (value.parent && !id(value.parent)) || (value.flags & ~1) ||
        (value.rank == 0) != (neighbor == config_.root)) return false;
    // An older epoch is a replay, unless the current one has gone silent: a
    // replaced or wiped root restarts its count, and its stations must follow.
    if (epochKnown_ && static_cast<int16_t>(value.epoch - epoch_) < 0 &&
        (nowS < epochHeardS_ || nowS - epochHeardS_ <= BEACON_STALE_S)) return false;
    if (!epochKnown_ || value.epoch != epoch_) {
        epoch_ = value.epoch;
        epochKnown_ = true;
        rank_ = 0xFFFF;
        rankCeiling_ = 0xFFFF;
        parent_ = 0;
        for (Neighbor& neighbor : neighbors_) neighbor = Neighbor();
        plannedFailures_ = backupFailures_ = 0;
        dynamicFailures_ = 0;
        failedDynamic_ = 0;
    }
    memcpy(epochSignature_, value.epochSignature, sizeof(epochSignature_));
    Neighbor* chosen = nullptr;
    for (Neighbor& item : neighbors_) {
        if (item.id == neighbor) { chosen = &item; break; }
        if (!item.id && !chosen) chosen = &item;
    }
    if (!chosen) {
        // The planned links must not be displaced by incidental neighbours.
        // Dynamic entries are soft state and can be evicted when the table is full.
        if (neighbor != config_.planned && neighbor != config_.backup) return false;
        for (Neighbor& item : neighbors_)
            if (item.id != config_.planned && item.id != config_.backup &&
                (!chosen || item.lastSeenS < chosen->lastSeenS)) chosen = &item;
        if (!chosen) return false;
    }
    const uint8_t delivery = chosen->id == neighbor && chosen->epoch == value.epoch ?
                             chosen->delivery16 : 16;
    // A fresh beacon is a new opportunity to probe a configured link. A
    // failed route is reconsidered only after another beacon from that peer.
    if (neighbor == config_.planned && plannedFailures_ >= 3 &&
        chosen->id == neighbor && nowS > chosen->lastSeenS) plannedFailures_ = 0;
    if (neighbor == config_.backup && backupFailures_ >= 3 &&
        chosen->id == neighbor && nowS > chosen->lastSeenS) backupFailures_ = 0;
    *chosen = {neighbor, value.rank, measuredCost(linkCost16, delivery),
               value.epoch, value.parent, nowS, linkCost16, delivery};
    epochHeardS_ = nowS;
    selectParent(nowS);
    return true;
}

void Table::hopResult(uint16_t neighbor, bool acknowledged, uint32_t nowS) {
    if (!ready_) return;
    for (Neighbor& item : neighbors_) {
        if (item.id != neighbor || item.epoch != epoch_) continue;
        // A HACK is one successful attempt; a timeout is one failed attempt.
        // The score remains soft state and resets on a new root epoch.
        item.delivery16 = acknowledged ?
            static_cast<uint8_t>((3u * item.delivery16 + 16u + 3u) / 4u) :
            static_cast<uint8_t>((3u * item.delivery16 + 3u) / 4u);
        if (!item.delivery16) item.delivery16 = 1;
        item.cost = measuredCost(item.snrCost, item.delivery16);
        break;
    }
    // A deliberate probe of the planned parent can restore the planned route.
    if (acknowledged && neighbor == config_.planned && neighbor != parent_) {
        plannedFailures_ = 0;
        selectParent(nowS);
        return;
    }
    if (acknowledged && neighbor == failedDynamic_ && neighbor != parent_) {
        failedDynamic_ = 0;
        dynamicFailures_ = 0;
        selectParent(nowS);
        return;
    }
    if (neighbor != parent_) return;
    uint8_t* failures = neighbor == config_.planned ? &plannedFailures_ :
                        neighbor == config_.backup ? &backupFailures_ : &dynamicFailures_;
    if (failures) *failures = acknowledged ? 0 : static_cast<uint8_t>(*failures < 3 ? *failures + 1 : 3);
    if (!acknowledged && failures == &dynamicFailures_ && dynamicFailures_ >= 3) failedDynamic_ = neighbor;
    selectParent(nowS);
}

}  // namespace wici_route
