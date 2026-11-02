// SPDX-License-Identifier: MIT
// Relay-side WICI-Link admission and one outstanding next-hop transfer.
// The radio caller owns CAD, silence, airtime debt and the 600 ms HACK timer.
#pragma once

#include "config.h"
#include "wici_relay.h"
#include "wici_route.h"
#include "wici_seq.h"
#include "wici_flood.h"

namespace wici_hop {

enum class Receipt : uint8_t { IGNORED, HACK_READY, STORED_NO_HACK, REJECTED };

// Every unicast DATA reaching receiveData() has passed the pairwise hop tag,
// so its link source is an authenticated neighbour. K1 is unicast transit to
// or from an active receiver identity, at most one queue slot per neighbour.
// A down route to a station is learned via a neighbour only when the network
// plan puts the station behind it (`behind`, from priority_keys) or the
// station is that neighbour.
class Relay {
public:
    // Flooding requires SA1 retries independent of local TX success (a flood
    // is one attempt); the station coordinator enables it. `behind` must
    // outlive the relay.
    Relay(journal::Storage& storage, wici_route::Config config, const uint8_t ifac[16],
          bool allowFlood = false, const uint16_t receiverIds[2] = nullptr,
          const config::Behind* behind = nullptr, uint16_t behindCount = 0);
    bool begin();
    // HACK_READY only after the incoming frame is durably held or was already
    // forwarded. `hack` is a complete radio frame; the caller applies silence.
    Receipt receiveData(const uint8_t* wire, size_t length, uint32_t nowS,
                        uint8_t* hack, size_t capacity, size_t& hackLength);
    // Called outside the HACK deadline: settles the queue and learns down
    // routes allowed by the plan. False on a storage failure.
    bool learnPending(uint32_t nowS);
    // Start one queued transfer. The same bytes are returned by outgoing() for
    // each retry; on reboot a new reserved seq is used for the old queue item.
    bool prepare(uint32_t nowS);
    const uint8_t* outgoing(size_t& length) const;
    // The active transfer is K2 while a K1 frame waits in the queue.
    bool contendedK2() const;
    // Call only after a real TX attempt. A broadcast is retired after success;
    // unicast waits for a matching authenticated HACK.
    bool transmitted(bool success, uint32_t nowS);
    bool receiveHack(const uint8_t* wire, size_t length, uint32_t nowS);
    // After 600 ms without HACK: true means retry the identical frame after
    // silence debt and randomized backoff; false leaves it queued for reroute.
    bool timeout(uint32_t nowS);
    // Origin traffic uses the same durable link sequence space as relay traffic.
    bool nextSequence(uint16_t& sequence) { return sequence_.next(sequence); }
    bool active() const { return active_; }
    wici_route::Table& routes() { return routes_; }

private:
    wici_route::Config config_;
    bool allowFlood_ = false;
    uint16_t receivers_[2] = {};
    const config::Behind* behind_ = nullptr;
    uint16_t behindCount_ = 0;
    bool priority(const wici_link::Frame& frame) const;
    bool planned(uint16_t station, uint16_t via) const;
    uint8_t key_[32] = {};
    bool keyReady_ = false;
    wici_relay::Queue queue_;
    wici_route::Table routes_;
    wici_seq::Counter sequence_;
    wici_flood::Ring flood_;
    uint8_t outgoing_[wici_link::MAX_FRAME] = {};
    size_t outgoingLength_ = 0;
    uint16_t next_ = 0, outgoingSeq_ = 0;
    uint8_t slot_ = 0, attempts_ = 0;
    bool active_ = false, sent_ = false, everSent_ = false, noAck_ = false;
    bool activePriority_ = false;
    wici_link::RepeatHack repeatHack_;
    uint8_t nextSlot_ = 0;
    uint8_t owedHacks_ = 0;  // K1 slots whose first sender retry gets a HACK regardless of RepeatHack
};

}  // namespace wici_hop
