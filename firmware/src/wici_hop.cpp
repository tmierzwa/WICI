// SPDX-License-Identifier: MIT
#include "wici_hop.h"

namespace wici_hop {
namespace {
uint16_t u16(const uint8_t* p) { return static_cast<uint16_t>((p[0] << 8) | p[1]); }
bool id(uint16_t n) { return n && n != wici_link::BROADCAST; }
}  // namespace

Relay::Relay(journal::Storage& storage, wici_route::Config config, const uint8_t ifac[16],
             bool allowFlood, const uint16_t receiverIds[2])
    : config_(config), allowFlood_(allowFlood), queue_(storage), routes_(storage, config),
      sequence_(storage), flood_(storage) {
    if (receiverIds) { receivers_[0] = receiverIds[0]; receivers_[1] = receiverIds[1]; }
    keyReady_ = wici_link::deriveKey(ifac, config.network, key_);
}

bool Relay::priority(const wici_link::Frame& frame) const {
    const uint16_t sender = u16(frame.payload + 1), recipient = u16(frame.payload + 3);
    return (receivers_[0] && (sender == receivers_[0] || recipient == receivers_[0])) ||
           (receivers_[1] && (sender == receivers_[1] || recipient == receivers_[1]));
}

bool Relay::begin() {
    active_ = sent_ = everSent_ = false;
    activePriority_ = contendedK2_ = false;
    outgoingLength_ = 0;
    attempts_ = 0;
    nextHint_ = 0;
    for (RouteHint& hint : hints_) hint = RouteHint();
    return keyReady_ && queue_.begin() && routes_.begin() && sequence_.begin(config_.network, config_.own) &&
           flood_.begin(config_.network);
}

Receipt Relay::receiveData(const uint8_t* wire, size_t length, uint32_t nowS,
                           uint8_t* hack, size_t capacity, size_t& hackLength) {
    hackLength = 0;
    if (!keyReady_ || !hack) return Receipt::REJECTED;
    wici_link::Frame frame;
    if (!wici_link::decode(key_, config_.network, wire, length, frame) ||
        frame.type != wici_link::Type::DATA ||
        (frame.destination != config_.own && frame.destination != wici_link::BROADCAST)) return Receipt::IGNORED;
    // This component is for transit traffic. A final recipient must durably
    // admit the decrypted envelope in its own inbox before answering HACK.
    if (u16(frame.payload + 3) == config_.own || !id(u16(frame.payload + 1)) ||
        !id(u16(frame.payload + 3))) return Receipt::REJECTED;
    const bool broadcast = frame.destination == wici_link::BROADCAST;
    if (broadcast && !allowFlood_) return Receipt::IGNORED;
    if (broadcast && (!(frame.flags & wici_link::DOWN) || frame.flags & wici_link::ACKREQ))
        return Receipt::REJECTED;
    if (broadcast && flood_.lookup(frame.payload, nowS) != wici_flood::Lookup::NONE)
        return Receipt::IGNORED;
    const wici_relay::Admission stored = queue_.admit(key_, config_.network, config_.own,
        wire, length, nowS, priority(frame) ? 0 : 1);
    if (stored != wici_relay::Admission::STORED && stored != wici_relay::Admission::DUPLICATE)
        return Receipt::REJECTED;
    if (!(frame.flags & wici_link::DOWN)) {
        const uint16_t sender = u16(frame.payload + 1);
        RouteHint* chosen = nullptr;
        for (RouteHint& hint : hints_) {
            if (hint.sender == sender) { chosen = &hint; break; }
            if (!hint.sender && !chosen) chosen = &hint;
        }
        if (!chosen) chosen = &hints_[nextHint_++ % wici_relay::SLOTS];
        *chosen = {sender, frame.source};
    }
    if (!(frame.flags & wici_link::ACKREQ)) return Receipt::STORED_NO_HACK;
    wici_link::Frame reply;
    reply.type = wici_link::Type::HACK;
    reply.network = config_.network;
    reply.source = config_.own;
    reply.destination = frame.source;
    reply.sequence = frame.sequence;
    reply.ttl = 1;
    hackLength = wici_link::encode(key_, reply, hack, capacity);
    return hackLength ? Receipt::HACK_READY : Receipt::REJECTED;
}

void Relay::learnPending(uint32_t nowS) {
    if (!routes_.ready() || !queue_.finishForwarded(key_, config_.network, config_.own, nowS)) return;
    uint8_t wire[wici_link::MAX_FRAME];
    for (uint8_t slot = 0; slot < wici_relay::SLOTS; ++slot) {
        size_t length = 0;
        if (!queue_.read(key_, config_.network, config_.own, slot, nowS, wire, sizeof(wire), length)) continue;
        wici_link::Frame frame;
        if (wici_link::decode(key_, config_.network, wire, length, frame) &&
            !(frame.flags & wici_link::DOWN)) {
            const uint16_t sender = u16(frame.payload + 1);
            if (sender != config_.own) routes_.learn(sender, frame.source);
        }
    }
    // A duplicate may arrive through a new neighbor while the durable queue
    // still contains the older copy. Apply the newest RAM hints last.
    for (RouteHint& hint : hints_) {
        if (!hint.sender || !routes_.ready()) continue;
        if (routes_.learn(hint.sender, hint.via)) hint = RouteHint();
    }
}

bool Relay::prepare(uint32_t nowS) {
    if (active_ || !keyReady_ || !routes_.ready() || !sequence_.ready()) return false;
    if (!queue_.finishForwarded(key_, config_.network, config_.own, nowS)) return false;
    uint8_t wire[wici_link::MAX_FRAME];
    bool priorityWaiting = false;
    for (uint8_t order = 0; order < 2 * wici_relay::SLOTS; ++order) {
        const uint8_t slot = order % wici_relay::SLOTS;
        size_t length = 0;
        if (!queue_.read(key_, config_.network, config_.own, slot, nowS, wire, sizeof(wire), length)) continue;
        wici_link::Frame frame;
        if (!wici_link::decode(key_, config_.network, wire, length, frame)) continue;
        if (order < wici_relay::SLOTS && priority(frame)) priorityWaiting = true;
        if (priority(frame) != (order < wici_relay::SLOTS)) continue;
        const uint16_t next = frame.flags & wici_link::DOWN ?
                              routes_.down(u16(frame.payload + 3)) : routes_.parent();
        if (!id(next) && next != wici_link::BROADCAST) continue;
        if (next == wici_link::BROADCAST && !allowFlood_) continue;
        if (next == wici_link::BROADCAST) {
            const wici_flood::Lookup state = flood_.lookup(frame.payload, nowS);
            if (state == wici_flood::Lookup::IO_ERROR) return false;
            if (state == wici_flood::Lookup::MATCH) {
                if (!queue_.remove(slot, nowS)) return false;
                continue;  // committed before a crash; never broadcast twice
            }
        }
        uint16_t sequence;
        if (!sequence_.next(sequence)) return false;
        const size_t n = wici_link::forward(key_, config_.network, config_.own, next, sequence,
                                            wire, length, outgoing_, sizeof(outgoing_));
        if (!n) continue;  // The reserved sequence is burned on an invalid route.
        if (next == wici_link::BROADCAST && !flood_.remember(frame.payload, nowS)) return false;
        next_ = next; outgoingSeq_ = sequence; slot_ = slot;
        noAck_ = next == wici_link::BROADCAST || !(frame.flags & wici_link::ACKREQ);
        activePriority_ = priority(frame);
        contendedK2_ = priorityWaiting && !activePriority_;
        outgoingLength_ = n; attempts_ = 1;
        sent_ = everSent_ = false; active_ = true;
        return true;
    }
    return false;
}

const uint8_t* Relay::outgoing(size_t& length) const {
    length = active_ ? outgoingLength_ : 0;
    return active_ ? outgoing_ : nullptr;
}

bool Relay::contendedK2(uint32_t nowS) {
    if (!active_ || activePriority_) return false;
    if (contendedK2_) return true;
    uint8_t wire[wici_link::MAX_FRAME];
    for (uint8_t slot = 0; slot < wici_relay::SLOTS; ++slot) {
        if (!queue_.pending(slot)) continue;
        size_t length = 0;
        if (!queue_.read(key_, config_.network, config_.own, slot, nowS, wire, sizeof(wire), length)) {
            contendedK2_ = true;  // uncertain queue state cannot loosen the K2 budget
            return true;
        }
        wici_link::Frame frame;
        if (wici_link::decode(key_, config_.network, wire, length, frame) && priority(frame)) {
            contendedK2_ = true;  // a later K1 remains relevant through this transfer's retries
            return true;
        }
    }
    return false;
}

bool Relay::transmitted(bool success, uint32_t nowS) {
    if (!active_) return false;
    if (noAck_) {
        const bool removed = queue_.remove(slot_, nowS);
        active_ = false;  // one attempt only, even after a failed TX
        return removed && success;
    }
    if (!success) { active_ = false; return false; }  // Queue remains durable.
    sent_ = everSent_ = true;
    return true;
}

bool Relay::receiveHack(const uint8_t* wire, size_t length, uint32_t nowS) {
    if (!active_ || !everSent_ || next_ == wici_link::BROADCAST) return false;
    wici_link::Frame frame;
    if (!wici_link::decode(key_, config_.network, wire, length, frame) ||
        frame.type != wici_link::Type::HACK || frame.source != next_ ||
        frame.destination != config_.own || frame.sequence != outgoingSeq_) return false;
    if (!queue_.remove(slot_, nowS)) return false;
    routes_.hopResult(next_, true, nowS);
    active_ = false;
    return true;
}

bool Relay::timeout(uint32_t nowS) {
    if (!active_ || !sent_ || next_ == wici_link::BROADCAST) return false;
    routes_.hopResult(next_, false, nowS);
    if (attempts_ < 3) {
        ++attempts_;
        sent_ = false;
        return true;
    }
    active_ = false;  // No HACK: keep the durable queue item for another route.
    return false;
}

}  // namespace wici_hop
