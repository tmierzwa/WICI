// SPDX-License-Identifier: MIT
#include "wici_route.h"

#include "fram_record.h"

namespace wici_route {
namespace {
using namespace fram_record;
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
    out.sequence = frame.sequence;
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

bool Table::paired(uint16_t id) const {
    if (!peers_) return true;
    for (uint8_t i = 0; i < peerCount_; ++i) if (peers_[i].station == id) return true;
    return false;
}

bool Table::begin() {
    ready_ = false;
    generation_ = 0;
    currentCopy_ = 1;
    epoch_ = 0;
    epochKnown_ = false;
    epochHeardS_ = 0;
    memset(epochSignature_, 0, sizeof(epochSignature_));
    rankCeiling_ = 0xFFFF;
    parent_ = 0;
    failures_ = 0;
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
        Copy state;
        if (!load(storage_, BASE + copy * COPY_BYTES, data, sizeof(data), CRC_AT, MAGIC, state)) return false;
        if (state == Copy::ABSENT) continue;
        if (state == Copy::DAMAGED) return false;
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
    // A neighbour without a pairwise key can never receive a unicast frame,
    // and a route outside the current plan (learned under an older `behind`)
    // may not be used. Both are dropped here; FRAM sheds them with the next commit.
    for (Route& route : routes_)
        if (route.via && (!paired(route.via) || !planned(route.destination, route.via))) route = Route();
    ready_ = true;
    if (!rootNode) parent_ = config_.planned;  // the floor: usable without any BEACON
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
    const uint8_t copy = static_cast<uint8_t>(1 - currentCopy_);
    if (!store(storage_, BASE + copy * COPY_BYTES, data, sizeof(data), CRC_AT)) {
        ready_ = false;
        return false;
    }
    ++generation_;
    currentCopy_ = copy;
    return true;
}

bool Table::planned(uint16_t destination, uint16_t via) const {
    if (destination == via) return true;
    for (uint16_t i = 0; i < behindCount_; ++i)
        if (behind_[i].station == destination && behind_[i].via == via) return true;
    return false;
}

bool Table::learn(uint16_t destination, uint16_t via) {
    if (!ready_ || !id(destination) || !id(via) || destination == config_.own ||
        via == config_.own || destination == config_.root || !paired(via) ||
        !planned(destination, via)) return false;
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

const Table::Neighbor* Table::find(uint16_t id) const {
    for (const Neighbor& n : neighbors_) if (id && n.id == id) return &n;
    return nullptr;
}

bool Table::fresh(const Neighbor& n, uint32_t nowS) const {
    return n.epoch == epoch_ && nowS >= n.lastSeenS && nowS - n.lastSeenS <= BEACON_STALE_S;
}

bool Table::usable(uint16_t id, uint32_t nowS) const {
    if (!id) return false;
    const Neighbor* n = find(id);
    // The planned and backup parents need no BEACON; a fresh one that names
    // this station as its parent excludes them (a loop) until it goes stale.
    if (id == config_.planned || id == config_.backup)
        return !n || !fresh(*n, nowS) || n->parent != config_.own;
    // A dynamic neighbour needs a fresh BEACON, may not point back at this
    // station and must rank below the lowest rank this station held in the
    // epoch, so a former descendant is never chosen.
    return n && fresh(*n, nowS) && n->parent != config_.own && n->rank < rankCeiling_ &&
           n->cost && static_cast<uint32_t>(n->rank) + n->cost < 0xFFFF;
}

uint16_t Table::bestDynamic(uint32_t nowS) const {
    const Neighbor* best = nullptr;
    for (const Neighbor& n : neighbors_) {
        if (n.id == config_.planned || n.id == config_.backup || !usable(n.id, nowS)) continue;
        if (!best || static_cast<uint32_t>(n.rank) + n.cost < static_cast<uint32_t>(best->rank) + best->cost)
            best = &n;
    }
    return best ? best->id : 0;
}

// Rotation steps: 0 planned, 1 backup, 2 best dynamic neighbour.
uint8_t Table::step(uint16_t id) const {
    return id == config_.planned ? 0 : id == config_.backup ? 1 : 2;
}

uint16_t Table::rotation(uint8_t from, uint32_t nowS) const {
    for (uint8_t i = 0; i < 3; ++i) {
        const uint8_t at = static_cast<uint8_t>((from + i) % 3);
        const uint16_t id = at == 0 ? config_.planned : at == 1 ? config_.backup : bestDynamic(nowS);
        if (usable(id, nowS)) return id;
    }
    return config_.planned;  // no candidate: the planned parent stays the floor
}

void Table::setParent(uint16_t id, uint32_t nowS) {
    if (id != parent_) failures_ = 0;
    parent_ = id;
    lowerCeiling(nowS);
}

uint16_t Table::rank(uint32_t nowS) const {
    if (!ready_) return 0xFFFF;
    if (config_.own == config_.root) return 0;
    // The rank follows only from a fresh BEACON of the current parent, so it
    // lapses by itself 90 min after that BEACON, without any other event.
    const Neighbor* n = find(parent_);
    if (!n || !fresh(*n, nowS) || n->parent == config_.own ||
        static_cast<uint32_t>(n->rank) + n->cost >= 0xFFFF) return 0xFFFF;
    return static_cast<uint16_t>(n->rank + n->cost);
}

void Table::lowerCeiling(uint32_t nowS) {
    const uint16_t now = rank(nowS);
    if (now < rankCeiling_) rankCeiling_ = now;
}

void Table::reconsider(uint16_t neighbor, bool heard, uint32_t nowS) {
    // A parent that became unusable (loop, stale, new epoch) is replaced as
    // after three failures.
    if (!usable(parent_, nowS)) {
        setParent(rotation(static_cast<uint8_t>(step(parent_) + 1), nowS), nowS);
        return;
    }
    // A HACK or new BEACON from the planned or backup parent brings it back
    // at once, without hysteresis.
    if (heard && neighbor == config_.planned && parent_ != config_.planned && usable(neighbor, nowS)) {
        setParent(neighbor, nowS);
        return;
    }
    if (heard && neighbor && neighbor == config_.backup && step(parent_) == 2 && usable(neighbor, nowS)) {
        setParent(neighbor, nowS);
        return;
    }
    // Between dynamic neighbours a switch needs 1.5 ETX (24/16) improvement.
    if (step(parent_) == 2) {
        const Neighbor* current = find(parent_);
        const Neighbor* best = find(bestDynamic(nowS));
        if (current && best && best != current &&
            static_cast<uint32_t>(current->rank) + current->cost >
            static_cast<uint32_t>(best->rank) + best->cost + 24) {
            setParent(best->id, nowS);
            return;
        }
    }
    lowerCeiling(nowS);
}

bool Table::acceptable(uint16_t neighbor, const Beacon& value, uint32_t nowS) const {
    if (!ready_ || config_.own == config_.root || !id(neighbor) || neighbor == config_.own ||
        value.root != config_.root || value.rank == 0xFFFF ||
        (value.parent && !id(value.parent)) || (value.flags & ~1) ||
        (value.rank == 0) != (neighbor == config_.root)) return false;
    // An older epoch is a replay, unless the current one has gone silent: a
    // replaced or wiped root restarts its count, and its stations must follow.
    // Only BEACONs of the current parent keep the epoch alive, so siblings
    // still repeating the old epoch cannot hold off a restarted root.
    if (epochKnown_ && static_cast<int16_t>(value.epoch - epoch_) < 0 &&
        (nowS < epochHeardS_ || nowS - epochHeardS_ <= BEACON_STALE_S)) return false;
    // A BEACON is new only if its link seq (under the network MAC) is newer
    // than the last one from this neighbour: a recorded copy can neither keep
    // a dead neighbour fresh nor pull this station back to it. The stored seq
    // counts only while the entry is fresh (90 min): a neighbour cannot move
    // its seq by half the u16 space in that time, but after hours of silence
    // a newer seq could look older, so a stale entry's seq is forgotten, as
    // that of an evicted entry is.
    if (epochKnown_ && value.epoch == epoch_) {
        const Neighbor* known = find(neighbor);
        if (known && fresh(*known, nowS) && static_cast<int16_t>(value.sequence - known->sequence) <= 0)
            return false;
    }
    return true;
}

bool Table::beacon(uint16_t neighbor, const Beacon& value, uint16_t linkCost16, uint32_t nowS) {
    if (linkCost16 < 16 || linkCost16 > 48 || !acceptable(neighbor, value, nowS)) return false;
    if (!epochKnown_ || value.epoch != epoch_) {
        epoch_ = value.epoch;
        epochKnown_ = true;
        epochHeardS_ = nowS;
        rankCeiling_ = 0xFFFF;
        for (Neighbor& entry : neighbors_) entry = Neighbor();
    }
    memcpy(epochSignature_, value.epochSignature, sizeof(epochSignature_));
    const bool configured = neighbor == config_.planned || neighbor == config_.backup;
    Neighbor* chosen = nullptr;
    for (Neighbor& item : neighbors_) {
        if (item.id == neighbor) { chosen = &item; break; }
        if (!item.id && !chosen) chosen = &item;
    }
    // Only a configured parent pointing back is kept (it must stay excluded
    // without a BEACON); any other such neighbour is simply no candidate.
    if (value.parent == config_.own && !configured) {
        if (chosen && chosen->id == neighbor) *chosen = Neighbor();
        if (neighbor == parent_) reconsider(neighbor, false, nowS);
        return true;
    }
    if (!chosen) {
        // A full table gives up its oldest stale dynamic entry. The planned
        // links are never evicted, and they may also evict the oldest live
        // dynamic entry; other neighbours may not.
        for (Neighbor& item : neighbors_)
            if (item.id != config_.planned && item.id != config_.backup && !fresh(item, nowS) &&
                (!chosen || item.lastSeenS < chosen->lastSeenS)) chosen = &item;
        if (!chosen && configured)
            for (Neighbor& item : neighbors_)
                if (item.id != config_.planned && item.id != config_.backup &&
                    (!chosen || item.lastSeenS < chosen->lastSeenS)) chosen = &item;
        if (!chosen) return false;
    }
    const uint8_t delivery = chosen->id == neighbor && chosen->epoch == value.epoch ?
                             chosen->delivery16 : 16;
    *chosen = {neighbor, value.rank, measuredCost(linkCost16, delivery),
               value.epoch, value.parent, nowS, linkCost16, delivery, value.sequence};
    reconsider(neighbor, true, nowS);
    if (neighbor == parent_) epochHeardS_ = nowS;
    return true;
}

void Table::hopResult(uint16_t neighbor, bool acknowledged, uint32_t nowS) {
    if (!ready_ || config_.own == config_.root) return;
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
    if (neighbor == parent_ && !acknowledged && ++failures_ >= 3) {
        // planned -> backup -> best dynamic -> planned; the counter restarts
        // with every parent, also when the rotation wraps to the same one.
        loop(nowS);
        return;
    }
    if (neighbor == parent_ && acknowledged) failures_ = 0;
    reconsider(neighbor, acknowledged, nowS);
}

void Table::loop(uint32_t nowS) {
    if (!ready_ || config_.own == config_.root) return;
    failures_ = 0;
    setParent(rotation(static_cast<uint8_t>(step(parent_) + 1), nowS), nowS);
}

}  // namespace wici_route
