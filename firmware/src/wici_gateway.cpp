// SPDX-License-Identifier: MIT
#include "wici_gateway.h"
#include "wici_record.h"
#include "wici_beacon.h"

#include <string.h>

namespace wici_gateway {
namespace {
using wici_record::get16;
}

Root::Root(journal::Storage& storage, kiss::Port& port, Air& air, uint16_t network,
           uint16_t own, const uint8_t ifac[16], const uint8_t identity[64])
    : port_(port), air_(air), network_(network), own_(own),
      routes_(storage, {network, own, own, 0, 0}), flood_(storage), sequence_(storage) {
    keyReady_ = own && own != wici_link::BROADCAST &&
                wici_link::deriveKey(ifac, network, key_) && identity;
    if (identity) memcpy(signingPrivate_, identity, sizeof(signingPrivate_));
}

bool Root::begin(uint16_t epoch) {
    pending_ = outboundPending_ = downPending_ = false;
    downFailures_ = 0;
    return ready_ = keyReady_ && wici_epoch::sign(signingPrivate_, network_, own_, epoch, epochSignature_) &&
                    routes_.begin() && flood_.begin(network_) &&
                    sequence_.begin(network_, own_) &&
                    routes_.setRootEpoch(epoch);
}

bool Root::beacon() {
    if (!ready_) return false;
    uint16_t sequence;
    if (!sequence_.next(sequence)) { ready_ = false; return false; }
    wici_link::Frame frame;
    frame.type = wici_link::Type::BEACON;
    frame.network = network_;
    frame.source = own_;
    frame.destination = wici_link::BROADCAST;
    frame.sequence = sequence;
    frame.ttl = 1;
    frame.length = 9 + wici_epoch::SIGNATURE_BYTES + wici_beacon::SIGNATURE_BYTES;
    frame.payload[0] = static_cast<uint8_t>(own_ >> 8);
    frame.payload[1] = static_cast<uint8_t>(own_);
    frame.payload[4] = static_cast<uint8_t>(routes_.epoch() >> 8);
    frame.payload[5] = static_cast<uint8_t>(routes_.epoch());
    memcpy(frame.payload + 9, epochSignature_, sizeof(epochSignature_));
    if (!wici_beacon::sign(signingPrivate_, network_, own_, frame.payload,
                           frame.payload + wici_beacon::CONTENT_BYTES)) return false;
    uint8_t wire[wici_link::MAX_FRAME];
    const size_t length = wici_link::encode(key_, frame, wire, sizeof(wire));
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
    }
    outboundLength_ = 0;
}

void Root::setUsbOpen(bool open) {
    if (!open) {
        pending_ = outboundPending_ = downPending_ = false;
        downFailures_ = 0;
        outboundLength_ = 0;
        const uint8_t* ignored = nullptr;
        size_t length = 0;
        while (port_.peek(ignored, length)) port_.pop();
    }
    port_.setOpen(open);
}

Event Root::radio(const uint8_t* wire, size_t length, uint32_t receivedMs) {
    wici_link::Frame frame;
    if (!ready_ || !port_.open() || !wici_link::decode(key_, network_, wire, length, frame) ||
        (frame.destination != own_ && frame.destination != wici_link::BROADCAST) ||
        frame.source == own_ || !port_.send(wire, length)) return Event::REJECTED;
    if (downPending_ && frame.type == wici_link::Type::HACK &&
        frame.source == downNext_ && frame.destination == own_ && frame.sequence == downSequence_) {
        downPending_ = false;
        downFailures_ = 0;
    }
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

Event Root::host(const uint8_t* wire, size_t length, uint32_t nowMs, uint32_t nowS) {
    wici_link::Frame frame;
    if (!ready_ || !port_.open() || !wici_link::decode(key_, network_, wire, length, frame))
        return Event::REJECTED;
    if (frame.type == wici_link::Type::HACK) {
        if (frame.source != own_ || !pending_ || frame.destination != pendingSource_ ||
            frame.sequence != pendingSequence_ || nowMs - receivedMs_ >= 200)
            return Event::REJECTED;
        if (!air_.sendHack(wire, length, receivedMs_)) return Event::REJECTED;
        pending_ = false;
        if (pendingSender_ != own_) routes_.learn(pendingSender_, pendingVia_);
        return Event::HACK_SENT;
    }
    if (outboundPending_ || frame.type != wici_link::Type::DATA || frame.destination != own_ ||
        frame.source == own_ || frame.flags != (wici_link::ACKREQ | wici_link::DOWN) ||
        get16(frame.payload + 1) != frame.source) return Event::REJECTED;
    if (downPending_ && nowMs - downSentMs_ >= 600) {
        downPending_ = false;
        if (failureRecipient_ != downRecipient_) {
            failureRecipient_ = downRecipient_;
            downFailures_ = 0;
        }
        if (++downFailures_ >= 3) {
            if (!routes_.forget(downRecipient_, downNext_)) { ready_ = false; return Event::REJECTED; }
            downFailures_ = 0;
        }
    }
    const uint16_t recipient = get16(frame.payload + 3);
    const uint16_t next = routes_.down(recipient);
    if (!next) return Event::REJECTED;
    const bool broadcast = next == wici_link::BROADCAST;
    if (broadcast && flood_.lookup(frame.payload, nowS) != wici_flood::Lookup::NONE)
        return Event::REJECTED;
    uint16_t sequence;
    if (!sequence_.next(sequence)) { ready_ = false; return Event::REJECTED; }
    uint8_t forwarded[wici_link::MAX_FRAME];
    const size_t forwardedLength = wici_link::forward(key_, network_, own_, next, sequence,
                                                      wire, length, forwarded, sizeof(forwarded));
    if (!forwardedLength || !port_.canSend(forwarded, forwardedLength) ||
        (broadcast && !flood_.remember(frame.payload, nowS)) ||
        !air_.sendData(forwarded, forwardedLength, wici_link::TxClass::TRANSIT)) return Event::REJECTED;
    memcpy(outbound_, forwarded, forwardedLength);
    outboundLength_ = forwardedLength;
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
