// SPDX-License-Identifier: MIT
#include "wici_gateway.h"
#include "wici_beacon.h"
#include "fram_record.h"

#include <Ed25519.h>
#include <string.h>

namespace wici_gateway {
namespace {
using fram_record::get16;
}

Root::Root(journal::Storage& storage, kiss::Port& port, Air& air, uint16_t network,
           uint16_t own, const uint8_t ifac[16], const uint8_t identity[64],
           const config::PriorityKey* peers, uint8_t peerCount,
           const config::Behind* behind, uint16_t behindCount)
    : port_(port), air_(air), network_(network), own_(own),
      routes_(storage, {network, own, own, 0, 0}, peers, peerCount, behind, behindCount),
      flood_(storage), sequence_(storage) {
    port_.acceptCommand(CMD_HACK_ONLY);
    keyReady_ = own && own != wici_link::BROADCAST &&
                wici_link::deriveKey(ifac, network, key_) && identity;
    if (identity) {
        memcpy(signingPrivate_, identity, sizeof(signingPrivate_));
        Ed25519::derivePublicKey(signingPublic_, signingPrivate_ + 32);
    }
}

bool Root::begin(uint16_t epoch) {
    // A downlink already handed to the radio stays pending: the radio may
    // still be sending it, and its TX result (onTxDone, which the radio
    // always reports) gives the laptop the echo or the refusal. Refusing it
    // here would let the laptop send the same envelope twice.
    pending_ = downPending_ = unsentFloodValid_ = false;
    return ready_ = keyReady_ && wici_epoch::sign(signingPrivate_, signingPublic_, network_, own_, epoch, epochSignature_) &&
                    routes_.begin() && flood_.begin(network_) &&
                    sequence_.begin(network_, own_) &&
                    routes_.setRootEpoch(epoch);
}

bool Root::ready() const { return ready_ && routes_.ready() && flood_.ready() && sequence_.ready(); }

bool Root::beacon() {
    if (!ready() || !port_.open() ||
        !air_.accepts(wici_link::TxClass::BEACON, wici_link::BEACON_FRAME)) return false;
    // Receivers take a BEACON only with a newer seq than the last one; a seq
    // burned by a rare refusal after this point only leaves a gap.
    uint16_t sequence;
    if (!sequence_.next(sequence)) return false;
    wici_route::Beacon value;
    value.root = own_;
    value.rank = 0;
    value.epoch = routes_.epoch();
    memcpy(value.epochSignature, epochSignature_, sizeof(epochSignature_));
    uint8_t wire[wici_link::MAX_FRAME];
    const size_t length = wici_beacon::encode(key_, signingPrivate_, signingPublic_, network_, own_, sequence,
                                              value, wire, sizeof(wire));
    return length && air_.sendData(wire, length, wici_link::TxClass::BEACON);
}

void Root::onTxDone(bool success, uint32_t nowMs) {
    if (!outboundPending_) return;
    outboundPending_ = false;
    if (success) {
        if (!outboundBroadcast_) {
            downPending_ = true;
            downSentMs_ = nowMs;
        }
        if (port_.open()) port_.send(outbound_, outboundLength_);
    } else {
        // A failed TX is no attempt: nothing complete went on air. A flood's
        // durable marker stays the root's own, so the laptop may resend it.
        if (outboundBroadcast_) {
            memcpy(unsentFlood_, original_ + wici_link::HEADER, sizeof(unsentFlood_));
            unsentFloodValid_ = true;
        }
        if (port_.open()) port_.send(original_, originalLength_, CMD_REFUSED);  // the laptop retries
    }
    outboundLength_ = originalLength_ = 0;
}

void Root::setUsbOpen(bool open) {
    if (!open) {
        // A downlink already handed to the radio stays pending until its TX
        // result; the laptop hears it only if the port is open again by then.
        pending_ = downPending_ = false;
        routes_.clearDownFailures();
        const uint8_t* ignored = nullptr;
        size_t length = 0;
        while (port_.peek(ignored, length)) port_.pop();
    }
    port_.setOpen(open);
}

Event Root::radio(const uint8_t* wire, size_t length, uint32_t receivedMs) {
    wici_link::Frame frame;
    if (!ready() || !port_.open() || !wici_link::decode(key_, network_, wire, length, frame) ||
        (frame.destination != own_ && frame.destination != wici_link::BROADCAST) ||
        frame.source == own_) return Event::REJECTED;
    // The HACK for the pending downward frame counts even when the KISS
    // buffer is full: it is authenticated, and missing it would count a
    // delivered frame as a failure (and in time forget a working route).
    if (downPending_ && frame.type == wici_link::Type::HACK &&
        frame.source == downNext_ && frame.destination == own_ && frame.sequence == downSequence_) {
        downPending_ = false;
        routes_.downDelivered(downRecipient_, downNext_);
    }
    if (!port_.send(wire, length)) return Event::REJECTED;
    if (frame.type == wici_link::Type::DATA && frame.destination == own_ &&
        (frame.flags & wici_link::ACKREQ)) {
        pending_ = true;
        pendingSource_ = frame.source;
        pendingSequence_ = frame.sequence;
        pendingSender_ = get16(frame.payload + 1);
        pendingVia_ = frame.source;
        receivedMs_ = receivedMs;
    }
    return Event::FORWARDED;
}

Event Root::host(const uint8_t* wire, size_t length, uint32_t nowMs, uint32_t nowS, uint8_t command) {
    wici_link::Frame frame;
    if (!keyReady_ || !port_.open() || (command != kiss::CMD_DATA && command != CMD_HACK_ONLY) ||
        !wici_link::decode(key_, network_, wire, length, frame) ||
        (command == CMD_HACK_ONLY && frame.type != wici_link::Type::HACK))
        return Event::REJECTED;
    if (frame.type == wici_link::Type::HACK) {
        if (!ready() || frame.source != own_ || !pending_ || frame.destination != pendingSource_ ||
            frame.sequence != pendingSequence_ || nowMs - receivedMs_ >= 200)
            return Event::REJECTED;
        if (!air_.sendHack(wire, length, receivedMs_)) return Event::REJECTED;
        pending_ = false;
        // A neighbour is always a route to itself (pairwise tag); this also
        // restores it after `forget`. The envelope sender is learned behind
        // it only on the laptop's "learn" HACK (CMD_DATA): a new envelope part
        // whose sender the envelope MAC authenticated. A recorded copy (a
        // duplicate) or a forged envelope, which a captured neighbour can
        // relay under its own l_src, gets CMD_HACK_ONLY and moves no route.
        // Such evidence is fresh and authenticated, so it may replace an
        // older route (the station moved); a relay may not (Table::learn),
        // and as everywhere only as the plan allows. A failed write takes
        // ready() down.
        routes_.learn(pendingVia_, pendingVia_, true);
        if (command == kiss::CMD_DATA && pendingSender_ != own_ && pendingSender_ != pendingVia_)
            routes_.learn(pendingSender_, pendingVia_, true);
        return Event::HACK_SENT;
    }
    // A malformed frame is a laptop fault, not a transient refusal.
    if (frame.type != wici_link::Type::DATA || frame.destination != own_ ||
        frame.source == own_ || frame.flags != (wici_link::ACKREQ | wici_link::DOWN) ||
        get16(frame.payload + 1) != frame.source) return Event::REJECTED;
    const Event result = transmit(wire, length, frame, nowMs, nowS);
    if (result == Event::QUEUED) return result;
    // Silence, a busy transmitter, a seal or FRAM failure: the laptop learns
    // at once that the item was not sent (bytes unchanged, CMD_REFUSED).
    port_.send(wire, length, CMD_REFUSED);
    return Event::REFUSED;
}

Event Root::transmit(const uint8_t* wire, size_t length, const wici_link::Frame& frame,
                     uint32_t nowMs, uint32_t nowS) {
    if (!ready() || outboundPending_) return Event::REJECTED;
    // The previous downward frame still waits for its HACK: one at a time, so
    // each HACK or timeout is counted for its own station (route `forget`).
    if (downPending_ && nowMs - downSentMs_ < wici_link::HACK_WAIT_MS) return Event::REJECTED;
    if (downPending_) {
        downPending_ = false;
        if (!routes_.downFailed(downRecipient_, downNext_)) return Event::REJECTED;
    }
    const uint16_t recipient = get16(frame.payload + 3);
    const uint16_t next = routes_.down(recipient);
    if (!next) return Event::REJECTED;
    const bool broadcast = next == wici_link::BROADCAST;
    const wici_flood::Lookup flood = broadcast ? flood_.lookup(frame.payload, nowS) : wici_flood::Lookup::NONE;
    // A marker of a flood the radio refused (never on air) stays the root's
    // own; any other one means flooded in the last 120 s.
    const bool ownFlood = unsentFloodValid_ && !memcmp(unsentFlood_, frame.payload, sizeof(unsentFlood_));
    if (flood == wici_flood::Lookup::IO_ERROR || (flood == wici_flood::Lookup::MATCH && !ownFlood))
        return Event::REJECTED;
    // No seq and no flood marker for a frame the radio would refuse.
    if (!air_.accepts(wici_link::TxClass::TRANSIT, length + (broadcast ? 0 : wici_link::HOP_TAG)))
        return Event::REJECTED;
    uint16_t sequence;
    if (!sequence_.next(sequence)) return Event::REJECTED;
    uint8_t forwarded[wici_link::MAX_FRAME];
    const size_t forwardedLength = wici_link::forward(key_, network_, own_, next, sequence,
                                                      wire, length, forwarded, sizeof(forwarded));
    if (!forwardedLength || !port_.canSend(forwarded, forwardedLength) ||
        (flood == wici_flood::Lookup::NONE && broadcast && !flood_.remember(frame.payload, nowS)))
        return Event::REJECTED;
    if (!air_.sendData(forwarded, forwardedLength, wici_link::TxClass::TRANSIT)) {
        if (broadcast) {
            memcpy(unsentFlood_, frame.payload, sizeof(unsentFlood_));
            unsentFloodValid_ = true;
        }
        return Event::REJECTED;
    }
    if (ownFlood) unsentFloodValid_ = false;
    memcpy(outbound_, forwarded, forwardedLength);
    outboundLength_ = forwardedLength;
    memcpy(original_, wire, length);
    originalLength_ = length;
    outboundPending_ = true;
    outboundBroadcast_ = broadcast;
    if (!broadcast) {
        downRecipient_ = recipient;
        downNext_ = next;
        downSequence_ = sequence;
    }
    return Event::QUEUED;
}

}  // namespace wici_gateway
