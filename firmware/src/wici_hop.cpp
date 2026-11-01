// SPDX-License-Identifier: MIT
#include "wici_hop.h"
#include "wici_record.h"

namespace wici_hop {
namespace {
using wici_record::get16;
using wici_record::id;
}  // namespace

Relay::Relay(journal::Storage& storage, wici_route::Config config, const uint8_t ifac[16],
             bool allowFlood, const uint16_t receiverIds[2], VerifyOrigin verify, const void* verifyContext)
    : config_(config), allowFlood_(allowFlood), queue_(storage), routes_(storage, config),
      sequence_(storage), flood_(storage) {
    if (receiverIds) { receivers_[0] = receiverIds[0]; receivers_[1] = receiverIds[1]; }
    verify_ = verify;
    verifyContext_ = verifyContext;
    keyReady_ = wici_link::deriveKey(ifac, config.network, key_);
}

bool Relay::priority(const wici_link::Frame& frame) const {
    // Floods are K2 whatever their signature.
    if (!verify_ || frame.destination == wici_link::BROADCAST) return false;
    const uint16_t sender = get16(frame.payload + 1), recipient = get16(frame.payload + 3);
    const uint16_t receiver = frame.flags & wici_link::DOWN ? sender : recipient;
    if (receiver != receivers_[0] && receiver != receivers_[1]) return false;
    return verify_(sender, recipient, frame, verifyContext_);
}

bool Relay::begin() {
    active_ = sent_ = everSent_ = false;
    activePriority_ = false;
    outgoingLength_ = 0;
    attempts_ = 0;
    nextSlot_ = owedHacks_ = 0;
    lastRepeatHackS_ = 0;
    repeatHackSent_ = false;
    for (uint32_t& generation : checkedGeneration_) generation = 0;
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
    // Ed25519 takes longer than the HACK deadline on the target MCU. Admit
    // into K2, commit, and verify later in learnPending().
    uint8_t slot = wici_relay::SLOTS;
    wici_relay::Admission stored = queue_.admit(wire, length, nowS, 2, 0, &slot);
    if (stored == wici_relay::Admission::FULL && !broadcast && (frame.flags & wici_link::ACKREQ)) {
        // Only a full queue pays the Ed25519 cost, which can exceed the HACK
        // deadline, so a K1 frame is committed now and HACKed on the sender's
        // retry. Earlier K1 origins are marked first: an unverified claim
        // cannot consume the one durable K1 slot per origin.
        if (!learnPending(nowS)) return Receipt::REJECTED;
        if (priority(frame)) {
            stored = queue_.admit(wire, length, nowS, 0, get16(frame.payload + 1), &slot);
            if (stored == wici_relay::Admission::STORED) {
                owedHacks_ |= static_cast<uint8_t>(1u << slot);
                return Receipt::STORED_NO_HACK;
            }
        }
    }
    if (stored != wici_relay::Admission::STORED && stored != wici_relay::Admission::DUPLICATE &&
        stored != wici_relay::Admission::FORWARDED)
        return Receipt::REJECTED;
    if (stored == wici_relay::Admission::STORED) owedHacks_ &= static_cast<uint8_t>(~(1u << slot));
    if (!(frame.flags & wici_link::ACKREQ))
        return stored == wici_relay::Admission::FORWARDED ? Receipt::IGNORED : Receipt::STORED_NO_HACK;
    const bool owed = stored == wici_relay::Admission::DUPLICATE && (owedHacks_ >> slot & 1);
    if (owed) {
        owedHacks_ &= static_cast<uint8_t>(~(1u << slot));
    } else if (stored != wici_relay::Admission::STORED) {
        // Repeated HACKs cost silence debt; a replayed copy may earn one per 5 s.
        if (repeatHackSent_ && nowS >= lastRepeatHackS_ && nowS - lastRepeatHackS_ < 5)
            return Receipt::IGNORED;
        repeatHackSent_ = true;
        lastRepeatHackS_ = nowS;
    }
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

bool Relay::learnPending(uint32_t nowS) {
    if (!routes_.ready() || !queue_.settle(nowS)) return false;
    uint8_t wire[wici_link::MAX_FRAME];
    for (uint8_t slot = 0; slot < wici_relay::SLOTS; ++slot) {
        size_t length = 0;
        wici_link::Frame frame;
        if (!queue_.read(slot, nowS, wire, sizeof(wire), length) ||
            !wici_link::decode(key_, config_.network, wire, length, frame)) continue;
        uint16_t origin = queue_.verifiedOrigin(slot);
        if (!origin && checkedGeneration_[slot] != queue_.generation(slot)) {
            checkedGeneration_[slot] = queue_.generation(slot);
            if (priority(frame)) {
                origin = get16(frame.payload + 1);
                if (!queue_.markVerified(slot, origin)) return false;
                checkedGeneration_[slot] = queue_.generation(slot);
            }
        }
        // Only a verified origin may move a down route; l_src was checked by
        // the pairwise hop tag when the frame was received.
        if (origin && !(frame.flags & wici_link::DOWN) && origin != config_.own &&
            !routes_.learn(origin, frame.source) && !routes_.ready()) return false;
    }
    return true;
}

bool Relay::prepare(uint32_t nowS) {
    if (active_ || !keyReady_ || !sequence_.ready() || !learnPending(nowS)) return false;
    uint8_t wire[wici_link::MAX_FRAME];
    // First pass: verified K1 frames; second pass: K2. Each pass rotates.
    for (uint8_t order = 0; order < 2 * wici_relay::SLOTS; ++order) {
        const uint8_t slot = static_cast<uint8_t>((nextSlot_ + order) % wici_relay::SLOTS);
        const bool verified = queue_.verifiedOrigin(slot) != 0;
        size_t length = 0;
        wici_link::Frame frame;
        if (verified != (order < wici_relay::SLOTS) ||
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
        activePriority_ = verified && next != wici_link::BROADCAST;
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
        if (slot != slot_ && queue_.verifiedOrigin(slot)) return true;
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
