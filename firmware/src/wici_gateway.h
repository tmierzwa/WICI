// SPDX-License-Identifier: MIT
// Root-node boundary between authenticated WICI radio frames and KISS USB.
// The laptop owns durable envelope admission; the node only permits a HACK
// after it has forwarded the matching DATA to that laptop. A downward frame
// the root cannot send goes straight back to the laptop as KISS command 0x01.
#pragma once

#include "config.h"
#include "kiss.h"
#include "wici_flood.h"
#include "wici_link.h"
#include "wici_route.h"
#include "wici_seq.h"

namespace wici_gateway {

using Air = wici_link::Air;

enum class Event : uint8_t { REJECTED, FORWARDED, QUEUED, HACK_SENT, REFUSED };

constexpr uint8_t CMD_REFUSED = 0x01;  // KISS command: downward frame not sent, bytes unchanged

class Root {
public:
    // `peers` (priority_keys, must outlive the root) are the pairwise
    // neighbours; `behind` (the network plan, must outlive the root) bounds
    // the down routes, as on every relay (wici_route::Table::learn).
    Root(journal::Storage& storage, kiss::Port& port, Air& air, uint16_t network,
         uint16_t own, const uint8_t ifac[16], const uint8_t identity[64],
         const config::PriorityKey* peers = nullptr, uint8_t peerCount = 0,
         const config::Behind* behind = nullptr, uint16_t behindCount = 0);
    // Reads durable state from FRAM; also the recovery after ready() fell. A
    // downward frame still waiting for its TX result stays pending: onTxDone()
    // reports it to the laptop.
    bool begin(uint16_t epoch);
    // False after an uncertain FRAM write (routes, flood ring, link sequence).
    bool ready() const;
    uint16_t clearedRecords() const { return flood_.cleared(); }
    // Only while the laptop's KISS port is open: a closed port cannot HACK.
    // Neither a seq nor a signature is spent when the radio would refuse.
    bool beacon();
    // The host learns the forwarded link sequence only after the radio has
    // actually transmitted. Scheduler admission can precede TX by airtime debt.
    void onTxDone(bool success, uint32_t nowMs);
    uint16_t down(uint16_t station) const { return routes_.down(station); }
    void setUsbOpen(bool open);
    // Called with the radio's receive-end timestamp, after the pairwise tag
    // check. A failed KISS enqueue cannot create a pending HACK authorization.
    Event radio(const uint8_t* wire, size_t length, uint32_t receivedMs);
    // Called for a decoded KISS data packet from the laptop. A HACK must match
    // the last forwarded unicast DATA and fit the 200 ms radio deadline. The
    // laptop HACK means only that the frame is durable at the stanowisko (new,
    // a duplicate, or set aside as never admissible); after it the root learns
    // the routes to the neighbour itself and, as the plan allows, to the
    // envelope sender behind it. A well-formed downward DATA that cannot be
    // sent (also while the previous one waits for its HACK) is REFUSED: its
    // bytes go back to the laptop at once with CMD_REFUSED.
    Event host(const uint8_t* wire, size_t length, uint32_t nowMs, uint32_t nowS);

private:
    Event transmit(const uint8_t* wire, size_t length, const wici_link::Frame& frame,
                   uint32_t nowMs, uint32_t nowS);
    kiss::Port& port_;
    Air& air_;
    uint16_t network_, own_;
    wici_route::Table routes_;
    wici_flood::Ring flood_;
    wici_seq::Counter sequence_;
    uint8_t key_[32] = {};
    uint8_t signingPrivate_[64] = {}, signingPublic_[32] = {}, epochSignature_[64] = {};
    bool keyReady_ = false, ready_ = false, pending_ = false, outboundPending_ = false;
    uint8_t outbound_[wici_link::MAX_FRAME] = {}, original_[wici_link::MAX_FRAME] = {};
    size_t outboundLength_ = 0, originalLength_ = 0;
    bool outboundBroadcast_ = false, downPending_ = false;
    uint16_t downRecipient_ = 0, downNext_ = 0, downSequence_ = 0;
    uint16_t failureRecipient_ = 0;
    uint8_t downFailures_ = 0;
    uint32_t downSentMs_ = 0;
    uint16_t pendingSource_ = 0, pendingSequence_ = 0;
    uint16_t pendingSender_ = 0, pendingVia_ = 0;
    uint32_t receivedMs_ = 0;
    // A flood whose durable marker was written but which the radio then
    // refused: never on air, so the laptop's next attempt of that envelope
    // may still go out (RAM only: after a restart the marker blocks it).
    uint8_t unsentFlood_[9] = {};
    bool unsentFloodValid_ = false;
};

}  // namespace wici_gateway
