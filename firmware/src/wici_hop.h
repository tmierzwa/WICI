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
// station is that neighbour, and never replaces a working route
// (wici_route::Table::learn): 3 downward attempts without HACK forget it.
class Relay {
public:
    // Flooding requires SA1 retries independent of local TX success (a flood
    // is one attempt); the station coordinator enables it. `behind` must
    // outlive the relay.
    Relay(journal::Storage& storage, wici_route::Config config, const uint8_t ifac[16],
          bool allowFlood = false, const uint16_t receiverIds[2] = nullptr,
          const config::Behind* behind = nullptr, uint16_t behindCount = 0,
          const config::PriorityKey* peers = nullptr, uint8_t peerCount = 0);
    // Re-reads every durable part from FRAM; also the recovery after ready() fell.
    bool begin();
    // False after any uncertain FRAM write in the queue, seen ring, routes,
    // link sequence or flood ring, until begin() succeeds again.
    bool ready() const;
    // Damaged non-security records (seen and flood rings) cleared by begin().
    uint16_t clearedRecords() const { return queue_.clearedRecords() + flood_.cleared(); }
    // HACK_READY only after the incoming frame is durably held or was already
    // forwarded. `hack` is a complete radio frame; the caller applies silence.
    Receipt receiveData(const uint8_t* wire, size_t length, uint32_t nowS,
                        uint8_t* hack, size_t capacity, size_t& hackLength);
    // Called outside the HACK deadline, also while a transfer is active:
    // settles the queue (30-min expiry) on every call and learns the down
    // route hint of each newly stored uplink frame once (after begin(): of
    // every queued frame once). An older queued frame never moves a route
    // back. A retired active item ends the transfer. False on a storage failure.
    bool learnPending(uint32_t nowS);
    // Start one queued transfer. The same bytes are returned by outgoing() for
    // each retry. The same queue item prepared again for the same next hop
    // (after yield() or three timeouts) keeps its seq, so radio refusals burn
    // none; on reboot a new reserved seq is used for the old queue item. An
    // item whose hop limit would end at a relay waits for another next hop
    // (bounded by the 30-min expiry).
    bool prepare(uint32_t nowS);
    // The radio refused the active transfer: it stays queued, and the next
    // prepare() ranks the queue (K1 before K2) and picks the next hop again.
    // A refused flood was never on air: its durable marker stays this relay's
    // own, and the flood goes out at a later prepare(). A HACK for an attempt
    // already on air still completes the same item while it stays in the
    // queue (receiveHack).
    void yield();
    const uint8_t* outgoing(size_t& length) const;
    // The active transfer is K2 while a K1 frame waits in the queue.
    bool contendedK2() const;
    // Call only after a real TX attempt. A frame without HACK (flood, silence
    // exception) is retired after a successful TX; unicast waits for a
    // matching authenticated HACK. After a failed TX the item stays queued.
    bool transmitted(bool success, uint32_t nowS);
    // Completes the item of any attempt that was on air (the active one or one
    // yielded earlier); active() tells whether a different transfer is still running.
    bool receiveHack(const uint8_t* wire, size_t length, uint32_t nowS);
    // After 600 ms without HACK: true means retry the identical frame after
    // silence debt and randomized backoff; false leaves it queued for reroute.
    // The third failed attempt of a downward frame forgets its down route.
    bool timeout(uint32_t nowS);
    // Origin traffic uses the same durable link sequence space as relay traffic.
    bool nextSequence(uint16_t& sequence) { return sequence_.next(sequence); }
    bool active() const { return active_; }
    wici_route::Table& routes() { return routes_; }

private:
    // The last transfer prepared for one queue item (RAM only). `generation`
    // binds it to that item; `late` keeps an attempt that was on air before
    // the item was prepared again for another next hop.
    struct Attempt {
        uint32_t generation = 0;
        uint16_t next = 0, sequence = 0, lateNext = 0, lateSequence = 0;
        bool valid = false, onAir = false, late = false;
    };
    wici_route::Config config_;
    bool allowFlood_ = false;
    uint16_t receivers_[2] = {};
    bool priority(const wici_link::Frame& frame) const;
    uint8_t key_[32] = {};
    bool keyReady_ = false;
    wici_relay::Queue queue_;
    wici_route::Table routes_;
    wici_seq::Counter sequence_;
    wici_flood::Ring flood_;
    uint8_t outgoing_[wici_link::MAX_FRAME] = {};
    size_t outgoingLength_ = 0;
    uint16_t next_ = 0, downTo_ = 0;  // downTo_: envelope destination of an active downward frame
    uint8_t slot_ = 0, attempts_ = 0;
    bool active_ = false, sent_ = false, noAck_ = false;
    bool activePriority_ = false;
    Attempt prepared_[wici_relay::SLOTS];
    uint8_t learn_ = 0;  // queue slots whose down-route hint is not learned yet
    wici_link::RepeatHack repeatHack_;
    uint8_t nextSlot_ = 0;
    uint8_t owedHacks_ = 0;  // K1 slots whose first sender retry gets a HACK regardless of RepeatHack
};

}  // namespace wici_hop
