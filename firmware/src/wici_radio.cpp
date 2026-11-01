// SPDX-License-Identifier: MIT
#include "wici_radio.h"

#include <string.h>

namespace wici_radio {
namespace {
uint16_t u16(const uint8_t* p) { return static_cast<uint16_t>((p[0] << 8) | p[1]); }
bool reached(uint32_t now, uint32_t deadline) { return static_cast<int32_t>(now - deadline) >= 0; }
}  // namespace

Shelter::Shelter(journal::Storage& storage, wici_route::Config route,
                 const uint16_t receiverIds[2], const uint8_t ifac[16],
                 const uint8_t privateKey[32], const uint8_t receiverPublic[2][32],
                 wici_destination::AdmitFn admit, void* admitContext,
                 Air& air, RandomFn random, void* randomContext)
    : network_(route.network), own_(route.own), root_(route.root),
      outbound_{envelope::Counter(storage, 0), envelope::Counter(storage, 1)},
      destination_(storage, {route.network, route.own,
                            {static_cast<uint16_t>(receiverIds ? receiverIds[0] : 0),
                             static_cast<uint16_t>(receiverIds ? receiverIds[1] : 0)}},
                   ifac, privateKey, receiverPublic, admit, admitContext),
      relay_(storage, route, ifac, true, receiverIds), air_(air), random_(random), randomContext_(randomContext) {
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
    return ready_ = keyReady_ && outboundKeysReady_ && destination_.begin() && relay_.begin() &&
                    outbound_[0].begin(network_, own_, receivers_[0]) &&
                    outbound_[1].begin(network_, own_, receivers_[1]);
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
        wici_route::Beacon beacon;
        return wici_route::parseBeacon(frame, beacon) &&
                       relay_.routes().beacon(frame.source, beacon,
                                              wici_route::snrCost16(snrQdb), nowS) ?
               Event::ADMITTED : Event::REJECTED;
    }
    if (frame.type != wici_link::Type::DATA || frame.length < envelope::OVERHEAD)
        return Event::REJECTED;
    uint8_t hack[wici_link::MAX_FRAME];
    size_t hackLength = 0;
    if (u16(frame.payload + 3) == own_) {
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
            if (ownAttempts_ >= 3) { finishOwn(false); return; }
            ownRetryAtMs_ = nowMs + backoff();
            ownDelayPending_ = true;
        }
        if (submitted_ || ownSubmitted_ ||
            (ownDelayPending_ && !reached(nowMs, ownRetryAtMs_))) return;
        if (air_.sendData(ownFrames_[ownPart_], ownLengths_[ownPart_])) {
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
        if (air_.sendData(frame, length)) {
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
        frame.ttl = 7;
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
    ownSubmitted_ = ownAwaiting_ = ownDelayPending_ = false;
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
    if (!ready_ || submitted_ || ownSubmitted_ || relay_.routes().rank() == 0xFFFF ||
        !relay_.routes().parent()) return false;
    uint16_t sequence;
    if (!relay_.nextSequence(sequence)) { ready_ = false; return false; }
    wici_link::Frame frame;
    frame.type = wici_link::Type::BEACON;
    frame.network = network_;
    frame.source = own_;
    frame.destination = wici_link::BROADCAST;
    frame.sequence = sequence;
    frame.ttl = 1;
    frame.length = 9;
    const uint16_t rank = relay_.routes().rank();
    const uint16_t epoch = relay_.routes().epoch();
    const uint16_t parent = relay_.routes().parent();
    frame.payload[0] = static_cast<uint8_t>(root_ >> 8);
    frame.payload[1] = static_cast<uint8_t>(root_);
    frame.payload[2] = static_cast<uint8_t>(rank >> 8);
    frame.payload[3] = static_cast<uint8_t>(rank);
    frame.payload[4] = static_cast<uint8_t>(epoch >> 8);
    frame.payload[5] = static_cast<uint8_t>(epoch);
    frame.payload[6] = static_cast<uint8_t>(parent >> 8);
    frame.payload[7] = static_cast<uint8_t>(parent);
    uint8_t wire[wici_link::MAX_FRAME];
    const size_t length = wici_link::encode(linkKey_, frame, wire, sizeof(wire));
    return length && air_.sendData(wire, length);
}

}  // namespace wici_radio
