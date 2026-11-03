// SPDX-License-Identifier: MIT
#include "wici_hop.h"
#include "envelope.h"
#include "fram_record.h"

namespace wici_hop {
namespace {
using fram_record::get16;
using fram_record::id;
}  // namespace

Relay::Relay(journal::Storage& storage, wici_route::Config config, const uint8_t ifac[16],
             bool allowFlood, const uint16_t receiverIds[2], const config::Behind* behind, uint16_t behindCount,
             const config::PriorityKey* peers, uint8_t peerCount)
    : config_(config), allowFlood_(allowFlood),
      queue_(storage), routes_(storage, config, peers, peerCount, behind, behindCount),
      sequence_(storage), flood_(storage) {
    if (receiverIds) { receivers_[0] = receiverIds[0]; receivers_[1] = receiverIds[1]; }
    keyReady_ = wici_link::deriveKey(ifac, config.network, key_);
}

bool Relay::priority(const wici_link::Frame& frame) const {
    // Floods are K2. So is a delivery proof: K1 of its station stays for its
    // SA1 (the type is plaintext, but marking it only demotes the own frame).
    if (frame.destination != config_.own || (frame.payload[0] & 0x0F) == envelope::TYPE_PROOF) return false;
    const uint16_t receiver = get16(frame.payload + (frame.flags & wici_link::DOWN ? 1 : 3));
    return receiver == receivers_[0] || receiver == receivers_[1];
}

bool Relay::begin() {
    active_ = sent_ = false;
    activePriority_ = false;
    outgoingLength_ = 0;
    nextSlot_ = owedHacks_ = 0;
    for (Attempt& attempt : prepared_) attempt = Attempt();
    for (Hold& hold : holds_) hold = Hold();
    learn_ = (1u << wici_relay::SLOTS) - 1;  // recover hints of frames queued before a restart
    repeatHack_.reset();
    return keyReady_ && queue_.begin(key_, config_.network, config_.own) && routes_.begin() &&
           sequence_.begin(config_.network, config_.own) && flood_.begin(config_.network);
}

bool Relay::ready() const {
    return keyReady_ && queue_.ready() && routes_.ready() && sequence_.ready() && flood_.ready();
}

Receipt Relay::receiveData(const uint8_t* wire, size_t length, uint32_t nowS,
                           uint8_t* hack, size_t capacity, size_t& hackLength) {
    hackLength = 0;
    if (!keyReady_ || !hack) return Receipt::REJECTED;
    wici_link::Frame frame;
    if (!wici_link::decode(key_, config_.network, wire, length, frame) ||
        frame.type != wici_link::Type::DATA ||
        (frame.destination != config_.own && frame.destination != wici_link::BROADCAST)) return Receipt::IGNORED;
    if (frame.destination == config_.own) heard(frame.source);  // unicast: the pairwise tag names it
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
    const uint8_t bit = static_cast<uint8_t>(slot < wici_relay::SLOTS ? 1u << slot : 0);
    if (stored == wici_relay::Admission::STORED && !(frame.flags & wici_link::DOWN)) {
        // Its down-route hint is learned once, after the HACK (learnPending).
        learn_ |= bit;
        // Loop signal: a new upward envelope from this station's own parent
        // (l_src, checked by the pairwise tag). The parent rotates at once;
        // the frame leaves through the new parent. A retry or replayed copy
        // of an envelope already held is no second signal. The envelope's
        // `src` is no signal: a relay cannot check the envelope MAC, so a
        // captured child could name this station there and move its parent
        // (wici-link.md, rule 2).
        if (frame.source == routes_.parent()) routes_.loop(nowS);
    }
    if (!(frame.flags & wici_link::ACKREQ))
        return stored == wici_relay::Admission::FORWARDED ? Receipt::IGNORED : Receipt::STORED_NO_HACK;
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
    if (active_ && !queue_.pending(slot_)) active_ = false;  // expired or forwarded before a crash
    uint8_t wire[wici_link::MAX_FRAME];
    // Hints newest first, by admission time (slot order says nothing): a
    // route is learned only where none exists (Table::learn), so after a
    // restart the newest frame of a station sets it and older ones do not
    // move it. Frames admitted in the same second keep slot order.
    while (learn_) {
        uint8_t slot = wici_relay::SLOTS;
        for (uint8_t i = 0; i < wici_relay::SLOTS; ++i)
            if ((learn_ & (1u << i)) && (slot == wici_relay::SLOTS || queue_.admittedS(i) > queue_.admittedS(slot)))
                slot = i;
        learn_ &= static_cast<uint8_t>(~(1u << slot));
        size_t length = 0;
        wici_link::Frame frame;
        if (!queue_.read(slot, nowS, wire, sizeof(wire), length) ||
            !wici_link::decode(key_, config_.network, wire, length, frame) ||
            (frame.flags & wici_link::DOWN)) continue;
        // l_src of a queued uplink frame was checked by the pairwise hop tag;
        // the plan decides which envelope senders it may stand for (learn()
        // refuses the others without a write).
        if (!routes_.learn(get16(frame.payload + 1), frame.source) && !routes_.ready()) return false;
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
        // A next hop that stopped answering is held; frames to others still go.
        if (next != wici_link::BROADCAST && held(next, nowS)) continue;
        // The last allowed hop must end at the root (up) or at the envelope
        // destination (down): a relay there refuses it. The frame waits for a
        // next hop that ends there (e.g. the planned parent back after a
        // detour to the backup); the 30-min expiry bounds the wait.
        if (next != wici_link::BROADCAST && frame.hops + 1 >= frame.ttl &&
            next != (frame.flags & wici_link::DOWN ? get16(frame.payload + 3) : config_.root)) continue;
        Attempt& last = prepared_[slot];
        // The same item for the same next hop is the same frame: it keeps its
        // seq, so a radio refusal burns none.
        const bool again = last.valid && last.generation == queue_.generation(slot) && last.next == next;
        wici_flood::Lookup flood = wici_flood::Lookup::NONE;
        if (next == wici_link::BROADCAST) {
            if (!allowFlood_) continue;
            flood = flood_.lookup(frame.payload, nowS);
            if (flood == wici_flood::Lookup::IO_ERROR) return false;
            // A marker this relay wrote for a flood the radio then refused
            // stays its own (`again`): that flood was never on air. Any other
            // marker was committed before a crash: never broadcast twice.
            if (flood == wici_flood::Lookup::MATCH && !again) {
                if (!queue_.remove(slot, nowS)) return false;
                continue;
            }
        }
        uint16_t sequence = last.sequence;
        if (!again && !sequence_.next(sequence)) return false;
        const size_t n = wici_link::forward(key_, config_.network, config_.own, next, sequence,
                                            wire, length, outgoing_, sizeof(outgoing_));
        if (!n) continue;  // A newly reserved sequence is burned on an invalid route.
        // The marker is durable before the radio may start (flood_ contract).
        if (next == wici_link::BROADCAST && flood == wici_flood::Lookup::NONE &&
            !flood_.remember(frame.payload, nowS)) return false;
        if (!again) {
            Attempt fresh;
            fresh.generation = queue_.generation(slot);
            fresh.next = next; fresh.sequence = sequence; fresh.valid = true;
            // An attempt on air for another next hop still completes the item.
            const bool sameItem = last.valid && last.generation == fresh.generation;
            if (sameItem && last.onAir) {
                fresh.late = true; fresh.lateNext = last.next; fresh.lateSequence = last.sequence;
            } else if (sameItem && last.late) {
                fresh.late = true; fresh.lateNext = last.lateNext; fresh.lateSequence = last.lateSequence;
            }
            last = fresh;
        }
        next_ = next; slot_ = slot;
        downTo_ = frame.flags & wici_link::DOWN ? get16(frame.payload + 3) : 0;
        nextSlot_ = static_cast<uint8_t>((slot + 1) % wici_relay::SLOTS);
        noAck_ = next == wici_link::BROADCAST || !(frame.flags & wici_link::ACKREQ);
        activePriority_ = k1 && next != wici_link::BROADCAST;
        outgoingLength_ = n;
        sent_ = false; active_ = true;
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
    // A failed TX put nothing complete on air: the item stays queued (a
    // flood keeps its own marker, `again` in prepare()) and goes again.
    if (!success) { active_ = false; return false; }  // Queue remains durable.
    if (noAck_) {
        active_ = false;  // one attempt on air, no HACK to wait for
        return queue_.remove(slot_, nowS);
    }
    sent_ = true;
    prepared_[slot_].onAir = true;
    return true;
}

void Relay::yield() {
    // The item and its attempt record stay; prepare() decides again.
    active_ = sent_ = false;
}

bool Relay::receiveHack(const uint8_t* wire, size_t length, uint32_t nowS) {
    wici_link::Frame frame;
    if (!wici_link::decode(key_, config_.network, wire, length, frame) ||
        frame.type != wici_link::Type::HACK || frame.destination != config_.own) return false;
    // Any attempt that was on air for a queued item counts: the active one,
    // also after its timeout, or one given up by yield() or a reroute.
    for (uint8_t slot = 0; slot < wici_relay::SLOTS; ++slot) {
        const Attempt& attempt = prepared_[slot];
        if (!attempt.valid || attempt.generation != queue_.generation(slot) || !queue_.pending(slot)) continue;
        uint16_t next;
        if (attempt.onAir && frame.source == attempt.next && frame.sequence == attempt.sequence) next = attempt.next;
        else if (attempt.late && frame.source == attempt.lateNext && frame.sequence == attempt.lateSequence)
            next = attempt.lateNext;
        else continue;
        if (!queue_.remove(slot, nowS)) return false;  // a new generation voids the record
        if (active_ && slot_ == slot) active_ = false;
        heard(next);
        routes_.hopResult(next, true, nowS);
        return true;
    }
    return false;
}

bool Relay::timeout(uint32_t nowS) {
    if (!active_ || !sent_ || next_ == wici_link::BROADCAST) return false;
    routes_.hopResult(next_, false, nowS);
    Attempt& attempt = prepared_[slot_];
    if (attempt.attempts < 3) {
        ++attempt.attempts;
        sent_ = false;
        return true;
    }
    active_ = false;  // No HACK: keep the durable queue item for another route.
    attempt.attempts = 1;  // the next round (after the hold or via another next hop) has 3 attempts again
    failedRound(next_, nowS);
    // A relay learns no route over a working one (Table::learn), so a station
    // that moved is found again only after the old route goes: the next
    // frame floods, and the station's next uplink frame teaches the new
    // route. A failed write takes ready() down.
    if (downTo_) routes_.forget(downTo_, next_);
    return false;
}

bool Relay::held(uint16_t next, uint32_t nowS) const {
    for (const Hold& hold : holds_)
        if (hold.id == next) return nowS < hold.untilS;
    return false;
}

void Relay::failedRound(uint16_t next, uint32_t nowS) {
    // Without the hold a silent next hop (a root without its laptop) would
    // get a round every 0.5-2 s until the 60% pool ran out, and transit would
    // stay blocked for up to an hour after it came back.
    Hold* slot = nullptr;
    for (Hold& hold : holds_) {
        if (hold.id == next) { slot = &hold; break; }
        if (!slot || hold.untilS < slot->untilS) slot = &hold;  // free or the earliest to end
    }
    if (slot->id != next) *slot = Hold{next, 0, 0};
    if (slot->rounds < 9) ++slot->rounds;
    slot->untilS = nowS + (slot->rounds < 9 ? 1u << slot->rounds : HOLD_MAX_S);  // 2, 4 ... 256, then 300 s
}

void Relay::heard(uint16_t neighbor) {
    for (Hold& hold : holds_)
        if (hold.id == neighbor) hold = Hold();
}

}  // namespace wici_hop
