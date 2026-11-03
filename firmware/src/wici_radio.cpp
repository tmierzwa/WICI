// SPDX-License-Identifier: MIT
#include "wici_radio.h"
#include "fram_record.h"

#include <string.h>

#include <Ed25519.h>

namespace wici_radio {
namespace {
using fram_record::get16;
using fram_record::put32;
bool reached(uint32_t now, uint32_t deadline) { return static_cast<int32_t>(now - deadline) >= 0; }
}  // namespace

Shelter::Shelter(journal::Storage& storage, wici_route::Config route, uint8_t ttl,
                 const uint16_t receiverIds[2], const uint8_t ifac[16],
                 const uint8_t privateKey[64], const uint8_t receiverPublic[2][32],
                 wici_destination::AdmitFn admit, void* admitContext,
                 Air& air, RandomFn random, void* randomContext,
                 const config::Behind* behind, uint16_t behindCount,
                 const uint8_t rootEd25519[32], BeaconKey beaconKey, const void* beaconContext,
                 const config::PriorityKey* peers, uint8_t peerCount)
    : network_(route.network), own_(route.own), root_(route.root), ttl_(ttl),
      outbound_{envelope::Counter(storage, 0), envelope::Counter(storage, 1)},
      destination_(storage, {route.network, route.own,
                            {static_cast<uint16_t>(receiverIds ? receiverIds[0] : 0),
                             static_cast<uint16_t>(receiverIds ? receiverIds[1] : 0)}, route.root},
                   ifac, privateKey, receiverPublic, admit, admitContext),
      relay_(storage, route, ifac, true, receiverIds, behind, behindCount, peers, peerCount),
      air_(air), random_(random), randomContext_(randomContext) {
    beaconKey_ = beaconKey;
    beaconContext_ = beaconContext;
    if (rootEd25519) {
        memcpy(rootEd25519_, rootEd25519, sizeof(rootEd25519_));
        rootKeyReady_ = true;
    }
    if (privateKey) {
        memcpy(signingPrivate_, privateKey, sizeof(signingPrivate_));
        Ed25519::derivePublicKey(signingPublic_, signingPrivate_ + 32);
    }
    keyReady_ = ifac && random && wici_link::deriveKey(ifac, network_, linkKey_);
    if (receiverIds) {
        receivers_[0] = receiverIds[0];
        receivers_[1] = receiverIds[1];
    }
    outboundKeysReady_ = privateKey && receiverPublic && receiverIds;
    for (uint8_t i = 0; i < 2 && outboundKeysReady_; ++i)
        outboundKeysReady_ = envelope::deriveKey(privateKey, receiverPublic[i], network_,
                                                own_, receivers_[i], own_, outboundKeys_[i]);
}

bool Shelter::begin() {
    ready_ = submitted_ = awaitingHack_ = delayPending_ = false;
    routePending_ = true;  // recover down-route hints from a durable queued frame
    sentAtMs_ = retryAtMs_ = 0;
    ownActive_ = ownSubmitted_ = ownAwaiting_ = ownDelayPending_ = ownException_ = false;
    ownCount_ = ownPart_ = ownAttempts_ = 0;
    beaconChecked_ = false;
    settledS_ = 0;
    return ready_ = keyReady_ && rootKeyReady_ && beaconKey_ && outboundKeysReady_ &&
                    destination_.begin() && relay_.begin() &&
                    outbound_[0].begin(network_, own_, receivers_[0], outboundKeys_[0]) &&
                    outbound_[1].begin(network_, own_, receivers_[1], outboundKeys_[1]);
}

bool Shelter::ready() const {
    return ready_ && destination_.ready() && relay_.ready() && outbound_[0].ready() && outbound_[1].ready();
}

uint32_t Shelter::backoff() const { return RETRY_MIN_MS + random_(randomContext_) % RETRY_SPAN_MS; }

Event Shelter::receive(const uint8_t* wire, size_t length, uint32_t receivedMs, uint32_t nowS,
                       int16_t snrQdb) {
    if (!ready()) return Event::REJECTED;
    wici_link::Frame frame;
    if (!wici_link::decode(linkKey_, network_, wire, length, frame)) return Event::REJECTED;
    if (frame.destination != own_ && frame.destination != wici_link::BROADCAST) return Event::IGNORED;
    if (frame.type == wici_link::Type::HACK) {
        // Also after the 600 ms, until the retry goes to the radio: the retry
        // is the same bytes, so the HACK proves receipt, and a replay may
        // have taken the HACK the parent owed the retry (rule 4).
        if (ownActive_ && (ownAwaiting_ || ownDelayPending_) && frame.source == ownNext_ &&
            frame.destination == own_ && frame.sequence == ownSeq_[ownPart_] &&
            wici_link::hackEcho(frame) == wici_link::macEcho(ownFrames_[ownPart_], ownLengths_[ownPart_])) {
            ownAwaiting_ = ownDelayPending_ = false;
            relay_.heard(ownNext_);
            relay_.routes().hopResult(ownNext_, true, nowS);
            if (++ownPart_ == ownCount_) finishOwn(true);
            else ownAttempts_ = 0;
            return Event::ADMITTED;
        }
        if (!relay_.receiveHack(wire, length, nowS)) return Event::IGNORED;
        if (!relay_.active()) {  // a late HACK of a yielded attempt leaves another transfer running
            submitted_ = awaitingHack_ = false;
            delayPending_ = false;
            retryAtMs_ = 0;
        }
        return Event::ADMITTED;
    }
    if (frame.type == wici_link::Type::BEACON) {
        // BEACONs carry no hop tag, and an Ed25519 check takes 0.04-0.4 s, far
        // beyond the 93 ms a HACK has after RX end. The signatures are checked
        // by the BeaconCheck worker, never here; the route table takes the
        // result in poll(). Checks are spaced (BEACON_CHECK_MS), a second
        // BEACON while one waits is dropped, and a verified epoch token is not
        // rechecked. A replayed or malformed BEACON is refused before the
        // spacing, so a recorded copy cannot use up the checks of real ones.
        wici_route::Beacon beacon;
        wici_route::Table& routes = relay_.routes();
        if (!wici_route::parseBeacon(frame, beacon) || !routes.acceptable(frame.source, beacon, nowS))
            return Event::REJECTED;
        if (beaconChecked_ && receivedMs - beaconCheckedMs_ < BEACON_CHECK_MS) return Event::IGNORED;
        if (pendingState_.load(std::memory_order_acquire) != IDLE) {
            ++beaconStats_.dropped;
            return Event::IGNORED;
        }
        const uint8_t* key = beaconKey_(frame.source, beaconContext_);
        if (!key) return Event::REJECTED;
        beaconChecked_ = true;
        beaconCheckedMs_ = receivedMs;
        PendingBeacon& p = pending_;
        p.beacon = beacon;
        p.sender = frame.source;
        p.cost16 = wici_route::snrCost16(snrQdb);
        p.knownEpoch = routes.epochKnown() && beacon.epoch == routes.epoch() &&
                       !memcmp(beacon.epochSignature, routes.epochSignature(), sizeof(beacon.epochSignature));
        memcpy(p.key, key, sizeof(p.key));
        memcpy(p.content, frame.payload, sizeof(p.content));
        memcpy(p.signature, frame.payload + wici_beacon::CONTENT_BYTES, sizeof(p.signature));
        p.valid = false;
        p.ms = 0;
        pendingState_.store(RUNNING, std::memory_order_release);
        if (!beaconCheck_) checkBeacon(this);
        else if (!beaconCheck_->start(checkBeacon, this)) {
            pendingState_.store(IDLE, std::memory_order_release);
            ++beaconStats_.dropped;
            return Event::IGNORED;
        }
        return pendingState_.load(std::memory_order_acquire) == DONE ? applyBeacon(nowS) : Event::PENDING;
    }
    if (frame.type != wici_link::Type::DATA || frame.length < envelope::OVERHEAD)
        return Event::REJECTED;
    uint8_t hack[wici_link::MAX_FRAME];
    size_t hackLength = 0;
    if (get16(frame.payload + 3) == own_) {
        wici_destination::Resolved resolved;
        const auto result = destination_.receive(wire, length, nowS, hack, sizeof(hack), hackLength, &resolved);
        // A HACK to the root reaches the receiver itself and proves the message;
        // after any other hop, a flood or a HACK the radio refused (silence,
        // deadline), only a proof envelope does.
        const bool hackToRoot = frame.source == root_ && (frame.flags & wici_link::ACKREQ);
        const bool hackReady = result == wici_destination::Outcome::HACK_READY ||
                               result == wici_destination::Outcome::SETTLED;
        const bool hackSent = hackReady && air_.sendHack(hack, hackLength, receivedMs);
        if (resolved.valid && !(hackToRoot && hackSent)) addProof(resolved.peer, resolved.counter);
        if (result == wici_destination::Outcome::SETTLED) return hackSent ? Event::HACK_SENT : Event::REJECTED;
        if (hackReady) return hackSent ? Event::HACK_SENT : Event::ADMITTED;
        return result == wici_destination::Outcome::ACCEPTED ? Event::ADMITTED :
               result == wici_destination::Outcome::IGNORED ? Event::IGNORED : Event::REJECTED;
    }
    const auto result = relay_.receiveData(wire, length, nowS, hack, sizeof(hack), hackLength);
    if (result == wici_hop::Receipt::HACK_READY) {
        routePending_ = true;
        return air_.sendHack(hack, hackLength, receivedMs) ? Event::HACK_SENT : Event::ADMITTED;
    }
    if (result == wici_hop::Receipt::STORED_NO_HACK) { routePending_ = true; return Event::ADMITTED; }
    return result == wici_hop::Receipt::IGNORED ? Event::IGNORED : Event::REJECTED;
}

// Runs in the BeaconCheck worker: reads only the slot and fields fixed at
// construction, and Ed25519 keeps no state between calls.
void Shelter::checkBeacon(void* self) {
    Shelter& shelter = *static_cast<Shelter*>(self);
    PendingBeacon& p = shelter.pending_;
    const uint32_t startMs = shelter.clock_ ? shelter.clock_() : 0;
    p.valid = (p.knownEpoch || wici_epoch::verify(shelter.rootEd25519_, shelter.network_, shelter.root_,
                                                 p.beacon.epoch, p.beacon.epochSignature)) &&
              wici_beacon::verify(p.key, shelter.network_, p.sender, p.content, p.signature);
    p.ms = shelter.clock_ ? shelter.clock_() - startMs : 0;
    shelter.pendingState_.store(DONE, std::memory_order_release);
}

// In the loop, after the check: the table rechecks acceptable() at nowS.
Event Shelter::applyBeacon(uint32_t nowS) {
    const PendingBeacon& p = pending_;
    ++beaconStats_.checks;
    beaconStats_.lastMs = p.ms;
    if (p.ms > beaconStats_.maxMs) beaconStats_.maxMs = p.ms;
    const bool admitted = p.valid && relay_.routes().beacon(p.sender, p.beacon, p.cost16, nowS);
    if (admitted) relay_.heard(p.sender);  // a root back with its laptop ends the hold at once
    pendingState_.store(IDLE, std::memory_order_release);
    return admitted ? Event::ADMITTED : Event::REJECTED;
}

void Shelter::onTxDone(bool success, uint32_t nowMs, uint32_t nowS) {
    if (ownSubmitted_) {
        ownSubmitted_ = false;
        if (!ready()) return;
        if (!success) ownAttemptFailed(nowMs);  // same rule as a HACK timeout, without blaming the parent
        else if (ownException_) {
            if (++ownPart_ == ownCount_) finishOwn(true);
        } else {
            ownAwaiting_ = true;
            ownSentAtMs_ = nowMs;
        }
        return;
    }
    if (!ready() || !submitted_) return;
    submitted_ = false;
    if (!relay_.transmitted(success, nowS)) {
        awaitingHack_ = false;
        retryAtMs_ = nowMs + backoff();
        delayPending_ = true;
        return;
    }
    awaitingHack_ = relay_.active();  // broadcast has no HACK and is retired on TX
    sentAtMs_ = nowMs;
}

void Shelter::ownAttemptFailed(uint32_t nowMs) {
    // Three attempts per parent, then one more round of three at the parent
    // the route table holds now, then Failed to the bearer seam.
    if (ownAttempts_ >= 3 && !failoverOwn()) { finishOwn(false); return; }
    ownRetryAtMs_ = nowMs + backoff();
    ownDelayPending_ = true;
}

void Shelter::poll(uint32_t nowMs, uint32_t nowS) {
    if (!ready()) return;
    if (pendingState_.load(std::memory_order_acquire) == DONE) applyBeacon(nowS);
    // Queue settlement (30-min expiry, crash leftovers) runs once a second,
    // whether or not a transfer is active; the down-route hint of a newly
    // stored frame is learned once, right after its HACK.
    if (routePending_ || nowS != settledS_) {
        relay_.learnPending(nowS);
        routePending_ = false;
        settledS_ = nowS;
    }
    if (awaitingHack_) {
        if (!reached(nowMs, sentAtMs_ + wici_link::HACK_WAIT_MS)) return;
        relay_.timeout(nowS);
        awaitingHack_ = false;
        retryAtMs_ = nowMs + backoff();
        delayPending_ = true;
    }
    if (!ownActive_ && !submitted_ && (proofCount_[0] || proofCount_[1])) startProof();
    if (ownActive_) {
        if (ownAwaiting_) {
            if (!reached(nowMs, ownSentAtMs_ + wici_link::HACK_WAIT_MS)) return;
            ownAwaiting_ = false;
            relay_.routes().hopResult(ownNext_, false, nowS);
            ownAttemptFailed(nowMs);
            if (!ownActive_) return;
        }
        if (submitted_ || ownSubmitted_ ||
            (ownDelayPending_ && !reached(nowMs, ownRetryAtMs_))) return;
        if (air_.sendData(ownFrames_[ownPart_], ownLengths_[ownPart_], wici_link::TxClass::OWN)) {
            ownSubmitted_ = true;
            ownDelayPending_ = false;
            ++ownAttempts_;
        } else {
            ownRetryAtMs_ = nowMs + backoff();
            ownDelayPending_ = true;
        }
        return;
    }
    if (submitted_ || (delayPending_ && !reached(nowMs, retryAtMs_))) return;
    if (!relay_.active() && !relay_.prepare(nowS)) return;
    size_t length = 0;
    const uint8_t* frame = relay_.outgoing(length);
    if (frame && length) {
        const auto traffic = relay_.contendedK2() ? wici_link::TxClass::CONTENDED_K2 :
                                                     wici_link::TxClass::TRANSIT;
        if (air_.sendData(frame, length, traffic)) {
            submitted_ = true;
            delayPending_ = false;
        } else {
            // Refused (silence, budget, no pair key): the item stays queued and
            // the next prepare() ranks the queue and picks the next hop again.
            relay_.yield();
            retryAtMs_ = nowMs + backoff();
            delayPending_ = true;
        }
    }
}

bool Shelter::queueOwn(uint16_t recipient, const uint8_t* sa1, size_t length, uint32_t handle,
                       bool exception) {
    if (!handle || !delivery_) return false;
    uint8_t peer = 2;
    for (uint8_t i = 0; i < 2; ++i) if (recipient == receivers_[i]) peer = i;
    return peer < 2 && startOwn(peer, envelope::TYPE_SA1, sa1, length, handle, exception);
}

void Shelter::addProof(uint8_t peer, uint32_t counter) {
    if (peer > 1) return;
    uint8_t& count = proofCount_[peer];
    if (count == envelope::PROOF_COUNTERS) {  // the oldest goes; its message comes again
        memmove(proofs_[peer], proofs_[peer] + 1, (count - 1) * sizeof(proofs_[peer][0]));
        --count;
        ++proofsDropped_;
    }
    proofs_[peer][count++] = counter;
}

// Not in silence (also not in its exception: that slot belongs to the
// exception's own SA1) and not while the radio refuses own frames.
bool Shelter::startProof() {
    const uint8_t peer = proofCount_[0] ? 0 : 1;
    const size_t length = proofCount_[peer] * 4u;
    if (!air_.accepts(wici_link::TxClass::OWN,
                      wici_link::HEADER + wici_link::TAG + wici_link::HOP_TAG + envelope::OVERHEAD + length))
        return false;
    uint8_t plain[4 * envelope::PROOF_COUNTERS];
    for (uint8_t i = 0; i < proofCount_[peer]; ++i) put32(plain + 4 * i, proofs_[peer][i]);
    // The counters leave the list with the transfer, whatever its end: without
    // a HACK the receiver resends and the station proves the new counter.
    const bool started = startOwn(peer, envelope::TYPE_PROOF, plain, length, 0, false);
    if (started) proofCount_[peer] = 0;
    return started;
}

bool Shelter::startOwn(uint8_t peer, uint8_t type, const uint8_t* data, size_t length, uint32_t handle,
                       bool exception) {
    if (!ready() || ownActive_ || !data || !length || length > envelope::MAX_SA1) return false;
    const uint16_t recipient = receivers_[peer];
    const uint16_t next = relay_.routes().parent();
    if (!next || next == wici_link::BROADCAST || next == own_) return false;
    envelope::Frame parts[2];
    const size_t count = envelope::sealReserved(outbound_[peer], outboundKeys_[peer], network_,
                                                own_, recipient, data, length,
                                                wici_link::MAX_PAYLOAD, parts, type);
    if (!count || count > 2) return false;
    uint8_t frames[2][wici_link::MAX_FRAME] = {};
    size_t lengths[2] = {};
    uint16_t sequences[2] = {};
    for (uint8_t i = 0; i < count; ++i) {
        if (!relay_.nextSequence(sequences[i])) return false;
        wici_link::Frame frame;
        frame.type = wici_link::Type::DATA;
        frame.flags = exception ? 0 : wici_link::ACKREQ;
        frame.network = network_;
        frame.source = own_;
        frame.destination = next;
        frame.ttl = ttl_;
        frame.sequence = sequences[i];
        frame.length = parts[i].length;
        memcpy(frame.payload, parts[i].bytes, frame.length);
        lengths[i] = wici_link::encode(linkKey_, frame, frames[i], sizeof(frames[i]));
        if (!lengths[i]) return false;
    }
    for (uint8_t i = 0; i < count; ++i) {
        memcpy(ownFrames_[i], frames[i], lengths[i]);
        ownLengths_[i] = lengths[i];
        ownSeq_[i] = sequences[i];
    }
    ownCount_ = static_cast<uint8_t>(count);
    ownPart_ = ownAttempts_ = 0;
    ownNext_ = next;
    ownHandle_ = handle;
    ownActive_ = true;
    ownException_ = exception;
    ownSubmitted_ = ownAwaiting_ = ownDelayPending_ = ownFailedOver_ = false;
    return true;
}

bool Shelter::failoverOwn() {
    // After three failures the route table has rotated (planned -> backup ->
    // best dynamic -> planned); the remaining parts get one more round of
    // three attempts at its parent, also when the rotation wrapped to the same one.
    const uint16_t next = relay_.routes().parent();
    if (ownFailedOver_ || !next || next == own_) return false;
    for (uint8_t i = ownPart_; i < ownCount_; ++i) {
        wici_link::Frame frame;
        if (!wici_link::decode(linkKey_, network_, ownFrames_[i], ownLengths_[i], frame)) return false;
        frame.destination = next;
        ownLengths_[i] = wici_link::encode(linkKey_, frame, ownFrames_[i], sizeof(ownFrames_[i]));
        if (!ownLengths_[i]) return false;
    }
    ownNext_ = next;
    ownAttempts_ = 0;
    ownFailedOver_ = true;
    return true;
}

void Shelter::finishOwn(bool acknowledged) {
    const uint32_t handle = ownHandle_;
    ownActive_ = ownSubmitted_ = ownAwaiting_ = ownDelayPending_ = ownException_ = false;
    ownHandle_ = 0;
    ownCount_ = ownPart_ = ownAttempts_ = 0;
    if (handle && delivery_) delivery_(handle, acknowledged, deliveryContext_);  // a proof has no handle
}

bool Shelter::beacon(uint32_t nowS) {
    wici_route::Table& routes = relay_.routes();
    const uint16_t rank = routes.rank(nowS);
    // No rank (no fresh BEACON of the current parent): do not attract
    // children. A BEACON the radio would refuse spends no seq and no signature.
    if (!ready() || submitted_ || ownSubmitted_ || rank == 0xFFFF || !routes.parent() ||
        !air_.accepts(wici_link::TxClass::BEACON, wici_link::BEACON_FRAME)) return false;
    // Receivers take a BEACON only with a newer seq than the last one; a seq
    // burned by a rare refusal after this point only leaves a gap.
    uint16_t sequence;
    if (!relay_.nextSequence(sequence)) return false;
    wici_route::Beacon value;
    value.root = root_;
    value.rank = rank;
    value.epoch = routes.epoch();
    value.parent = routes.parent();
    memcpy(value.epochSignature, routes.epochSignature(), sizeof(value.epochSignature));
    uint8_t wire[wici_link::MAX_FRAME];
    const size_t length = wici_beacon::encode(linkKey_, signingPrivate_, signingPublic_, network_, own_, sequence,
                                              value, wire, sizeof(wire));
    return length && air_.sendData(wire, length, wici_link::TxClass::BEACON);
}

}  // namespace wici_radio
