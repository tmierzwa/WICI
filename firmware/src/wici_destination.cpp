// SPDX-License-Identifier: MIT
#include "wici_destination.h"
#include "fram_record.h"

namespace wici_destination {
namespace {
using fram_record::get16;
using fram_record::id;
}  // namespace

Destination::Destination(journal::Storage& storage, Config config, const uint8_t ifac[16],
                         const uint8_t privateKey[32], const uint8_t peerPublic[2][32],
                         AdmitFn admit, void* context)
    : config_(config), replay_{envelope::DurableReplay(storage, 0), envelope::DurableReplay(storage, 1)},
      parts_{envelope::DurableParts(storage, 0), envelope::DurableParts(storage, 1)},
      admit_(admit), context_(context) {
    if (!ifac || !privateKey || !peerPublic || !admit || !id(config.network) || !id(config.own) ||
        !id(config.receiver[0]) || !id(config.receiver[1]) || config.own == config.receiver[0] ||
        config.own == config.receiver[1] || config.receiver[0] == config.receiver[1]) return;
    keysReady_ = wici_link::deriveKey(ifac, config.network, linkKey_);
    for (uint8_t i = 0; i < 2 && keysReady_; ++i)
        keysReady_ = envelope::deriveKey(privateKey, peerPublic[i], config.network,
                                        config.receiver[i], config.own, config.own, envelopeKeys_[i]);
}

bool Destination::begin() {
    ready_ = false;
    repeatHack_.reset();
    if (!keysReady_) return false;
    for (uint8_t i = 0; i < 2; ++i) {
        if (!replay_[i].begin(config_.network, config_.own, config_.receiver[i], envelopeKeys_[i]) ||
            !parts_[i].begin(config_.network, config_.own, config_.receiver[i], envelopeKeys_[i])) return false;
        // SA1 was durable but the fragment tombstone was interrupted. Replay
        // state proves it can be freed without accepting the content again.
        if (parts_[i].pending() && replay_[i].accepted(parts_[i].pendingCounter()) &&
            !parts_[i].clear()) return false;
    }
    ready_ = true;
    return true;
}

Outcome Destination::receive(const uint8_t* wire, size_t length, uint32_t nowS,
                             uint8_t* hack, size_t capacity, size_t& hackLength, Resolved* resolved) {
    hackLength = 0;
    if (resolved) *resolved = Resolved();
    if (!ready_ || !hack) return Outcome::REJECTED;
    wici_link::Frame frame;
    if (!wici_link::decode(linkKey_, config_.network, wire, length, frame) ||
        frame.type != wici_link::Type::DATA ||
        (frame.destination != config_.own && frame.destination != wici_link::BROADCAST)) return Outcome::IGNORED;
    if (frame.source == config_.own) return Outcome::REJECTED;
    if (frame.destination == wici_link::BROADCAST &&
        (!(frame.flags & wici_link::DOWN) || frame.flags & wici_link::ACKREQ)) return Outcome::REJECTED;
    const uint16_t sender = get16(frame.payload + 1), recipient = get16(frame.payload + 3);
    if (recipient != config_.own) return Outcome::REJECTED;
    uint8_t peer = 2;
    for (uint8_t i = 0; i < 2; ++i) if (sender == config_.receiver[i]) peer = i;
    if (peer == 2) return Outcome::REJECTED;
    envelope::Part part;
    if (!envelope::openPart(envelopeKeys_[peer], frame.payload, frame.length, part) ||
        part.sender != sender || part.recipient != recipient || part.type != 0) return Outcome::REJECTED;
    bool repeat = replay_[peer].accepted(part.counter);
    if (!repeat) {
        envelope::ReplayWindow proposed;
        if (!replay_[peer].propose(part.counter, proposed)) return Outcome::REJECTED;
        if (part.number == 0) {
            if (parts_[peer].pending() && parts_[peer].pendingCounter() == part.counter)
                return Outcome::REJECTED;  // one counter cannot change from fragments to whole
            if (!admit_(config_.network, sender, recipient, part.plaintext, part.length, context_) ||
                !replay_[peer].commit(part.counter)) return Outcome::REJECTED;
            if (resolved) *resolved = Resolved{true, peer, part.counter};
        } else {
            uint8_t full[envelope::MAX_SA1];
            size_t fullLength = 0;
            const envelope::FragmentResult result = parts_[peer].ingest(part, nowS, full, fullLength);
            if (result == envelope::FragmentResult::PARTIAL) {
                // The first part is already in a verified FRAM record.
            } else if (result == envelope::FragmentResult::DUPLICATE) {
                repeat = true;  // a replayed stored part: rate-limited HACK, as a whole duplicate
            } else if (result == envelope::FragmentResult::COMPLETE) {
                if (!admit_(config_.network, sender, recipient, full, fullLength, context_) ||
                    !replay_[peer].commit(part.counter)) return Outcome::REJECTED;
                if (resolved) *resolved = Resolved{true, peer, part.counter};
                // A failed tombstone does not revoke durable SA1/replay state;
                // begin() finishes it when the module is read again.
                if (!parts_[peer].clear()) ready_ = false;
            } else {
                if (result == envelope::FragmentResult::IO_ERROR) ready_ = false;
                return Outcome::REJECTED;
            }
        }
    }
    if (!(frame.flags & wici_link::ACKREQ)) return Outcome::ACCEPTED;
    if (repeat && !repeatHack_.allow(nowS)) return Outcome::IGNORED;
    hackLength = wici_link::encodeHack(linkKey_, frame, wici_link::macEcho(wire, length), hack, capacity);
    return hackLength ? Outcome::HACK_READY : Outcome::REJECTED;
}

}  // namespace wici_destination
