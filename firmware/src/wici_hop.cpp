// SPDX-License-Identifier: MIT
#include "wici_hop.h"
#include "fram_record.h"

namespace wici_hop {
namespace {
using fram_record::get16;
using fram_record::id;
}  // namespace

Relay::Relay(journal::Storage& storage, wici_route::Config config, const uint8_t ifac[16],
             bool allowFlood, const uint16_t receiverIds[2], const config::Behind* behind, uint16_t behindCount)
    : config_(config), allowFlood_(allowFlood), behind_(behind), behindCount_(behind ? behindCount : 0),
      queue_(storage), routes_(storage, config), sequence_(storage), flood_(storage) {
    if (receiverIds) { receivers_[0] = receiverIds[0]; receivers_[1] = receiverIds[1]; }
    keyReady_ = wici_link::deriveKey(ifac, config.network, key_);
}

bool Relay::priority(const wici_link::Frame& frame) const {
    // Floods are K2.
    if (frame.destination != config_.own) return false;
    const uint16_t receiver = get16(frame.payload + (frame.flags & wici_link::DOWN ? 1 : 3));
    return receiver == receivers_[0] || receiver == receivers_[1];
}

bool Relay::planned(uint16_t station, uint16_t via) const {
    if (station == via) return true;
    for (uint16_t i = 0; i < behindCount_; ++i)
        if (behind_[i].station == station && behind_[i].via == via) return true;
    return false;
}

bool Relay::begin() {
    active_ = sent_ = everSent_ = false;
    activePriority_ = false;
    outgoingLength_ = 0;
    attempts_ = 0;
    nextSlot_ = owedHacks_ = 0;
    repeatHack_.reset();
    return keyReady_ && queue_.begin(key_, config_.network, config_.own) && routes_.begin() &&
           sequence_.begin(config_.network, config_.own) && flood_.begin(config_.network);
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
    if (get16(frame.payload + 3) == config_.own || !id(get16(frame.payload + 1)) ||
        !id(get16(frame.payload + 3))) return Receipt::REJECTED;
    const bool broadcast = frame.destination == wici_link::BROADCAST;
    if (broadcast && !allowFlood_) return Receipt::IGNORED;
    if (broadcast && (!(frame.flags & wici_link::DOWN) || frame.flags & wici_link::ACKREQ))
        return Receipt::REJECTED;
    if (broadcast && flood_.lookup(frame.payload, nowS) != wici_flood::Lookup::NONE)
        return Receipt::IGNORED;
    // A neighbour that already holds its K1 slot competes for K2 space.
    uint8_t slot = wici_relay::SLOTS;
    const bool k1 = priority(frame);
    wici_relay::Admission stored = k1 ? queue_.admit(wire, length, nowS, frame.source, &slot) :
                                        wici_relay::Admission::FULL;
    if (stored == wici_relay::Admission::FULL) stored = queue_.admit(wire, length, nowS, 0, &slot);
    if (stored != wici_relay::Admission::STORED && stored != wici_relay::Admission::DUPLICATE &&
        stored != wici_relay::Admission::FORWARDED)
        return Receipt::REJECTED;
    if (!(frame.flags & wici_link::ACKREQ))
        return stored == wici_relay::Admission::FORWARDED ? Receipt::IGNORED : Receipt::STORED_NO_HACK;
    const uint8_t bit = static_cast<uint8_t>(slot < wici_relay::SLOTS ? 1u << slot : 0);
    if (stored == wici_relay::Admission::STORED) {
        // The HACK of a K1 admission can be lost. The sender's first retry
        // then gets its HACK even if a replayed copy just used the repeat
        // allowance, so a replay cannot push K1 traffic into SA1 retries.
        if (queue_.k1Neighbor(slot)) owedHacks_ |= bit;
        else owedHacks_ &= static_cast<uint8_t>(~bit);
    } else if (stored == wici_relay::Admission::DUPLICATE && (owedHacks_ & bit)) {
        owedHacks_ &= static_cast<uint8_t>(~bit);
    } else if (!repeatHack_.allow(nowS)) {
        return Receipt::IGNORED;
    }
    hackLength = wici_link::encodeHack(key_, frame, hack, capacity);
    return hackLength ? Receipt::HACK_READY : Receipt::REJECTED;
}

bool Relay::learnPending(uint32_t nowS) {
    if (!routes_.ready() || !queue_.settle(nowS)) return false;
    uint8_t wire[wici_link::MAX_FRAME];
    for (uint8_t slot = 0; slot < wici_relay::SLOTS; ++slot) {
        size_t length = 0;
        wici_link::Frame frame;
        if (!queue_.read(slot, nowS, wire, sizeof(wire), length) ||
            !wici_link::decode(key_, config_.network, wire, length, frame)) continue;
        // l_src of a queued uplink frame was checked by the pairwise hop tag;
        // the plan decides which envelope senders it may stand for.
        const uint16_t station = get16(frame.payload + 1);
        if (!(frame.flags & wici_link::DOWN) && station != config_.own && planned(station, frame.source) &&
            !routes_.learn(station, frame.source) && !routes_.ready()) return false;
    }
    return true;
}

bool Relay::prepare(uint32_t nowS) {
    if (active_ || !keyReady_ || !sequence_.ready() || !learnPending(nowS)) return false;
    uint8_t wire[wici_link::MAX_FRAME];
    // First pass: K1 frames; second pass: K2. Each pass rotates.
    for (uint8_t order = 0; order < 2 * wici_relay::SLOTS; ++order) {
        const uint8_t slot = static_cast<uint8_t>((nextSlot_ + order) % wici_relay::SLOTS);
        const bool k1 = queue_.k1Neighbor(slot) != 0;
        size_t length = 0;
        wici_link::Frame frame;
        if (k1 != (order < wici_relay::SLOTS) ||
            !queue_.read(slot, nowS, wire, sizeof(wire), length) ||
            !wici_link::decode(key_, config_.network, wire, length, frame)) continue;
        const uint16_t next = frame.flags & wici_link::DOWN ?
                              routes_.down(get16(frame.payload + 3)) : routes_.parent();
        // Never hand a frame back to the neighbor it came from.
        if ((!id(next) && next != wici_link::BROADCAST) || next == frame.source) continue;
        if (next == wici_link::BROADCAST) {
            if (!allowFlood_) continue;
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
        nextSlot_ = static_cast<uint8_t>((slot + 1) % wici_relay::SLOTS);
        noAck_ = next == wici_link::BROADCAST || !(frame.flags & wici_link::ACKREQ);
        activePriority_ = k1 && next != wici_link::BROADCAST;
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

bool Relay::contendedK2() const {
    if (!active_ || activePriority_) return false;
    for (uint8_t slot = 0; slot < wici_relay::SLOTS; ++slot)
        if (slot != slot_ && queue_.k1Neighbor(slot)) return true;
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
