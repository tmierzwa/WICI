// SPDX-License-Identifier: MIT
#include "wici_radio.h"
#include "fram_record.h"

#include <string.h>

#include <Ed25519.h>
#include "wici_origin.h"

namespace wici_radio {
namespace {
using fram_record::get16;
bool reached(uint32_t now, uint32_t deadline) { return static_cast<int32_t>(now - deadline) >= 0; }
}  // namespace

Shelter::Shelter(journal::Storage& storage, wici_route::Config route, uint8_t ttl,
                 const uint16_t receiverIds[2], const uint8_t ifac[16],
                 const uint8_t privateKey[64], const uint8_t receiverPublic[2][32],
                 wici_destination::AdmitFn admit, void* admitContext,
                 Air& air, RandomFn random, void* randomContext,
                 wici_hop::VerifyOrigin verifyOrigin, const void* verifyContext,
                 const uint8_t rootEd25519[32], VerifyBeacon verifyBeacon, const void* beaconContext)
    : network_(route.network), own_(route.own), root_(route.root), ttl_(ttl),
      outbound_{envelope::Counter(storage, 0), envelope::Counter(storage, 1)},
      destination_(storage, {route.network, route.own,
                            {static_cast<uint16_t>(receiverIds ? receiverIds[0] : 0),
                             static_cast<uint16_t>(receiverIds ? receiverIds[1] : 0)}},
                   ifac, privateKey, receiverPublic, admit, admitContext),
      relay_(storage, route, ifac, true, receiverIds, verifyOrigin, verifyContext),
      air_(air), random_(random), randomContext_(randomContext) {
    verifyBeacon_ = verifyBeacon;
    beaconContext_ = beaconContext;
    if (rootEd25519) {
        memcpy(rootEd25519_, rootEd25519, sizeof(rootEd25519_));
        rootKeyReady_ = true;
    }
    if (privateKey) {
        memcpy(signingPrivate_, privateKey, sizeof(signingPrivate_));
        Ed25519::derivePublicKey(signingPublic_ + 32, signingPrivate_ + 32);
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
    return ready_ = keyReady_ && rootKeyReady_ && verifyBeacon_ && outboundKeysReady_ &&
                    destination_.begin() && relay_.begin() &&
                    outbound_[0].begin(network_, own_, receivers_[0], outboundKeys_[0]) &&
                    outbound_[1].begin(network_, own_, receivers_[1], outboundKeys_[1]);
}

uint32_t Shelter::backoff() const { return RETRY_MIN_MS + random_(randomContext_) % RETRY_SPAN_MS; }

Event Shelter::receive(const uint8_t* wire, size_t length, uint32_t receivedMs, uint32_t nowS,
                       int16_t snrQdb) {
    if (!ready_) return Event::REJECTED;
    wici_link::Frame frame;
    if (!wici_link::decode(linkKey_, network_, wire, length, frame)) return Event::REJECTED;
    if (frame.destination != own_ && frame.destination != wici_link::BROADCAST) return Event::IGNORED;
    if (frame.type == wici_link::Type::HACK) {
        if (ownActive_ && ownAwaiting_ && frame.source == ownNext_ &&
            frame.destination == own_ && frame.sequence == ownSeq_[ownPart_]) {
            ownAwaiting_ = ownDelayPending_ = false;
            relay_.routes().hopResult(ownNext_, true, nowS);
            if (++ownPart_ == ownCount_) finishOwn(true);
            else ownAttempts_ = 0;
            return Event::ADMITTED;
        }
        if (!relay_.receiveHack(wire, length, nowS)) return Event::IGNORED;
        submitted_ = awaitingHack_ = false;
        delayPending_ = false;
        retryAtMs_ = 0;
        return Event::ADMITTED;
    }
    if (frame.type == wici_link::Type::BEACON) {
        // BEACONs carry no hop tag, and each Ed25519 check blocks the loop,
        // and so every HACK deadline, for about 0.2-0.4 s on nRF52840. Checks
        // are therefore spaced, and a verified epoch token is not rechecked.
        wici_route::Beacon beacon;
        wici_route::Table& routes = relay_.routes();
        if (!wici_route::parseBeacon(frame, beacon)) return Event::REJECTED;
        if (beaconChecked_ && receivedMs - beaconCheckedMs_ < BEACON_CHECK_MS) return Event::IGNORED;
        beaconChecked_ = true;
        beaconCheckedMs_ = receivedMs;
        const bool knownEpoch = routes.epochKnown() && beacon.epoch == routes.epoch() &&
                                !memcmp(beacon.epochSignature, routes.epochSignature(), sizeof(beacon.epochSignature));
        return (knownEpoch ||
                wici_epoch::verify(rootEd25519_, network_, root_, beacon.epoch, beacon.epochSignature)) &&
                       verifyBeacon_(frame.source, frame.payload, frame.payload + wici_beacon::CONTENT_BYTES,
                                     beaconContext_) &&
                       routes.beacon(frame.source, beacon, wici_route::snrCost16(snrQdb), nowS) ?
               Event::ADMITTED : Event::REJECTED;
    }
    if (frame.type != wici_link::Type::DATA || frame.length < envelope::OVERHEAD)
        return Event::REJECTED;
    uint8_t hack[wici_link::MAX_FRAME];
    size_t hackLength = 0;
    if (get16(frame.payload + 3) == own_) {
        const auto result = destination_.receive(wire, length, nowS, hack, sizeof(hack), hackLength);
        if (result == wici_destination::Outcome::HACK_READY)
            return air_.sendHack(hack, hackLength, receivedMs) ? Event::HACK_SENT : Event::ADMITTED;
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

void Shelter::onTxDone(bool success, uint32_t nowMs, uint32_t nowS) {
    if (ready_ && ownSubmitted_) {
        ownSubmitted_ = false;
        if (success) {
            if (ownException_) {
                if (++ownPart_ == ownCount_) finishOwn(true);
            } else {
                ownAwaiting_ = true;
                ownSentAtMs_ = nowMs;
            }
        } else if (ownAttempts_ >= 3) finishOwn(false);
        else {
            ownRetryAtMs_ = nowMs + backoff();
            ownDelayPending_ = true;
        }
        return;
    }
    if (!ready_ || !submitted_) return;
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

void Shelter::poll(uint32_t nowMs, uint32_t nowS) {
    if (!ready_) return;
    if (routePending_) { relay_.learnPending(nowS); routePending_ = false; }
    if (awaitingHack_) {
        if (!reached(nowMs, sentAtMs_ + HACK_WAIT_MS)) return;
        relay_.timeout(nowS);
        awaitingHack_ = false;
        retryAtMs_ = nowMs + backoff();
        delayPending_ = true;
    }
    if (ownActive_) {
        if (ownAwaiting_) {
            if (!reached(nowMs, ownSentAtMs_ + HACK_WAIT_MS)) return;
            ownAwaiting_ = false;
            relay_.routes().hopResult(ownNext_, false, nowS);
            if (ownAttempts_ >= 3 && !failoverOwn()) { finishOwn(false); return; }
            ownRetryAtMs_ = nowMs + backoff();
            ownDelayPending_ = true;
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
            retryAtMs_ = nowMs + backoff();
            delayPending_ = true;
        }
    }
}

bool Shelter::queueOwn(uint16_t recipient, const uint8_t* sa1, size_t length, uint32_t handle,
                       bool exception) {
    if (!ready_ || ownActive_ || !sa1 || !length || length > envelope::MAX_SA1 || !handle ||
        !delivery_) return false;
    uint8_t peer = 2;
    for (uint8_t i = 0; i < 2; ++i) if (recipient == receivers_[i]) peer = i;
    const uint16_t next = relay_.routes().parent();
    if (peer == 2 || !next || next == wici_link::BROADCAST || next == own_) return false;
    envelope::Frame parts[2];
    const size_t count = envelope::sealReserved(outbound_[peer], outboundKeys_[peer], network_,
                                                own_, recipient, sa1, length,
                                                wici_link::MAX_PAYLOAD, parts);
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
        if (!wici_origin::sign(signingPrivate_, signingPublic_, network_, frame.payload,
                               frame.length, frame.originSignature)) return false;
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
    // After three failures the route table has moved to the backup or another
    // parent; the remaining parts get one more round of three attempts there.
    const uint16_t next = relay_.routes().parent();
    if (ownFailedOver_ || !next || next == ownNext_) return false;
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
    if (delivery_) delivery_(handle, acknowledged, deliveryContext_);
}

bool Shelter::beacon() {
    wici_route::Table& routes = relay_.routes();
    if (!ready_ || submitted_ || ownSubmitted_ || routes.rank() == 0xFFFF || !routes.parent()) return false;
    uint16_t sequence;
    if (!relay_.nextSequence(sequence)) { ready_ = false; return false; }
    wici_route::Beacon value;
    value.root = root_;
    value.rank = routes.rank();
    value.epoch = routes.epoch();
    value.parent = routes.parent();
    memcpy(value.epochSignature, routes.epochSignature(), sizeof(value.epochSignature));
    uint8_t wire[wici_link::MAX_FRAME];
    const size_t length = wici_beacon::encode(linkKey_, signingPrivate_, signingPublic_ + 32, network_, own_, sequence,
                                              value, wire, sizeof(wire));
    return length && air_.sendData(wire, length, wici_link::TxClass::BEACON);
}

}  // namespace wici_radio
