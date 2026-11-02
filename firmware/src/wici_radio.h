// SPDX-License-Identifier: MIT
// Shelter-side WICI-Link radio coordinator. The caller owns the radio scheduler:
// DATA uses ordinary CAD/debt, HACK uses the bounded immediate path in Bench.
#pragma once

#include "wici_destination.h"
#include "wici_hop.h"
#include "envelope_counter.h"
#include "wici_beacon.h"

namespace wici_radio {

constexpr uint32_t RETRY_MIN_MS = 500;
constexpr uint32_t RETRY_SPAN_MS = 1501;
constexpr uint32_t BEACON_CHECK_MS = 1000;  // minimum spacing of BEACON signature checks

using Air = wici_link::Air;

using RandomFn = uint32_t (*)(void* context);
using DeliveryFn = void (*)(uint32_t handle, bool acknowledged, void* context);
using VerifyBeacon = bool (*)(uint16_t sender, const uint8_t content[wici_beacon::CONTENT_BYTES],
                              const uint8_t signature[wici_beacon::SIGNATURE_BYTES], const void* context);

enum class Event : uint8_t { IGNORED, REJECTED, ADMITTED, HACK_SENT };

class Shelter {
public:
    // ttl: hop limit of own DATA frames (network plan, 1-15).
    Shelter(journal::Storage& storage, wici_route::Config route, uint8_t ttl,
            const uint16_t receiverIds[2], const uint8_t ifac[16],
            const uint8_t privateKey[64], const uint8_t receiverPublic[2][32],
            wici_destination::AdmitFn admit, void* admitContext,
            Air& air, RandomFn random, void* randomContext,
            const config::Behind* behind = nullptr, uint16_t behindCount = 0,
            const uint8_t rootEd25519[32] = nullptr,
            VerifyBeacon verifyBeacon = nullptr, const void* beaconContext = nullptr,
            const config::PriorityKey* peers = nullptr, uint8_t peerCount = 0);
    // Reads all durable state from FRAM. Also the recovery after ready() fell:
    // the caller cancels the own transfer first (cancelOwn).
    bool begin();
    // Called from Bench's raw callback. No route learning or outbound DATA is
    // performed before the HACK attempt; all timestamps come from the radio.
    Event receive(const uint8_t* frame, size_t length, uint32_t receivedMs, uint32_t nowS,
                  int16_t snrQdb = 0);
    // Called after the radio's DATA completion callback, never for HACK.
    void onTxDone(bool success, uint32_t nowMs, uint32_t nowS);
    void poll(uint32_t nowMs, uint32_t nowS);
    // One own SA1 intent at a time. Its nonce and link sequences are reserved
    // durably before any frame is offered to the radio. Completion means that
    // every fragment received a next-hop HACK; SA1 confirmation is separate.
    bool queueOwn(uint16_t recipient, const uint8_t* sa1, size_t length, uint32_t handle,
                  bool exception = false);
    // Signs and offers one BEACON with the rank at nowS (wici_route::Table::rank).
    bool beacon(uint32_t nowS);
    void cancelOwn() { if (ownActive_) finishOwn(false); }
    void onDelivery(DeliveryFn callback, void* context) { delivery_ = callback; deliveryContext_ = context; }
    bool ownBusy() const { return ownActive_; }
    bool exceptionTx() const { return ownActive_ && ownException_; }
    // False after any uncertain FRAM write in a durable part (queue, rings,
    // routes, link sequence, envelope counters, replay windows) until begin().
    bool ready() const;
    uint16_t clearedRecords() const { return relay_.clearedRecords(); }
    wici_route::Table& routes() { return relay_.routes(); }

private:
    uint32_t backoff() const;
    uint16_t network_, own_, root_;
    uint8_t ttl_;
    uint8_t linkKey_[32] = {};
    uint8_t signingPrivate_[64] = {}, signingPublic_[32] = {};
    uint8_t rootEd25519_[32] = {};
    VerifyBeacon verifyBeacon_ = nullptr;
    const void* beaconContext_ = nullptr;
    bool keyReady_ = false, rootKeyReady_ = false, ready_ = false, routePending_ = false;
    bool submitted_ = false, awaitingHack_ = false, delayPending_ = false;
    uint32_t sentAtMs_ = 0, retryAtMs_ = 0;
    envelope::Counter outbound_[2];
    uint8_t outboundKeys_[2][32] = {};
    uint16_t receivers_[2] = {};
    bool outboundKeysReady_ = false;
    uint8_t ownFrames_[2][wici_link::MAX_FRAME] = {};
    size_t ownLengths_[2] = {};
    uint8_t ownCount_ = 0, ownPart_ = 0, ownAttempts_ = 0;
    uint16_t ownNext_ = 0, ownSeq_[2] = {};
    uint32_t ownHandle_ = 0, ownSentAtMs_ = 0, ownRetryAtMs_ = 0;
    bool ownActive_ = false, ownSubmitted_ = false, ownAwaiting_ = false, ownDelayPending_ = false;
    bool ownException_ = false, ownFailedOver_ = false;
    bool beaconChecked_ = false;
    uint32_t beaconCheckedMs_ = 0, settledS_ = 0;
    DeliveryFn delivery_ = nullptr;
    void* deliveryContext_ = nullptr;
    void finishOwn(bool acknowledged);
    void ownAttemptFailed(uint32_t nowMs);
    bool failoverOwn();
    wici_destination::Destination destination_;
    wici_hop::Relay relay_;
    Air& air_;
    RandomFn random_;
    void* randomContext_;
};

}  // namespace wici_radio
