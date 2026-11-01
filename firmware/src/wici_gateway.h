// SPDX-License-Identifier: MIT
// Root-node boundary between authenticated WICI radio frames and KISS USB.
// The laptop owns durable envelope admission; the node only permits a HACK
// after it has forwarded the matching DATA to that laptop.
#pragma once

#include "kiss.h"
#include "wici_flood.h"
#include "wici_link.h"
#include "wici_route.h"
#include "wici_seq.h"

namespace wici_gateway {

using Air = wici_link::Air;

enum class Event : uint8_t { REJECTED, FORWARDED, QUEUED, HACK_SENT };

class Root {
public:
    Root(journal::Storage& storage, kiss::Port& port, Air& air, uint16_t network,
         uint16_t own, const uint8_t ifac[16], const uint8_t identity[64]);
    bool begin(uint16_t epoch);
    bool ready() const { return ready_; }
    bool beacon();
    // The host learns the forwarded link sequence only after the radio has
    // actually transmitted. Scheduler admission can precede TX by airtime debt.
    void onTxDone(bool success, uint32_t nowMs);
    uint16_t down(uint16_t station) const { return routes_.down(station); }
    void setUsbOpen(bool open);
    // Called with the radio's receive-end timestamp. A failed KISS enqueue
    // cannot create a pending HACK authorization.
    Event radio(const uint8_t* wire, size_t length, uint32_t receivedMs);
    // Called for a decoded KISS data packet from the laptop. A HACK must match
    // the last forwarded unicast DATA and fit the 200 ms radio deadline.
    Event host(const uint8_t* wire, size_t length, uint32_t nowMs, uint32_t nowS);

private:
    kiss::Port& port_;
    Air& air_;
    uint16_t network_, own_;
    wici_route::Table routes_;
    wici_flood::Ring flood_;
    wici_seq::Counter sequence_;
    uint8_t key_[32] = {};
    uint8_t signingPrivate_[64] = {}, signingPublic_[32] = {}, epochSignature_[64] = {};
    bool keyReady_ = false, ready_ = false, pending_ = false, outboundPending_ = false;
    uint8_t outbound_[wici_link::MAX_FRAME] = {};
    size_t outboundLength_ = 0;
    bool outboundBroadcast_ = false, downPending_ = false;
    uint16_t downRecipient_ = 0, downNext_ = 0, downSequence_ = 0;
    uint16_t failureRecipient_ = 0;
    uint8_t downFailures_ = 0;
    uint32_t downSentMs_ = 0;
    uint16_t pendingSource_ = 0, pendingSequence_ = 0;
    uint16_t pendingSender_ = 0, pendingVia_ = 0;
    uint32_t receivedMs_ = 0;
};

}  // namespace wici_gateway
