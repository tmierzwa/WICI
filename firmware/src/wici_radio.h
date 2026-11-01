// SPDX-License-Identifier: MIT
// Shelter-side WICI-Link radio coordinator. The caller owns the radio scheduler:
// DATA uses ordinary CAD/debt, HACK uses the bounded immediate path in Bench.
#pragma once

#include "wici_destination.h"
#include "wici_hop.h"
#include "envelope_counter.h"

namespace wici_radio {

constexpr uint32_t HACK_WAIT_MS = 600;
constexpr uint32_t RETRY_MIN_MS = 500;
constexpr uint32_t RETRY_SPAN_MS = 1501;

struct Air {
    virtual ~Air() = default;
    // true means the frame was accepted for radio transmission. onTxDone()
    // later reports whether it actually went out.
    virtual bool sendData(const uint8_t* frame, size_t length, wici_link::TxClass traffic) = 0;
    // Synchronous: true only if the authenticated HACK was transmitted.
    virtual bool sendHack(const uint8_t* frame, size_t length, uint32_t receivedMs) = 0;
};

using RandomFn = uint32_t (*)(void* context);
using DeliveryFn = void (*)(uint32_t handle, bool acknowledged, void* context);

enum class Event : uint8_t { IGNORED, REJECTED, ADMITTED, HACK_SENT };

class Shelter {
public:
    Shelter(journal::Storage& storage, wici_route::Config route,
            const uint16_t receiverIds[2], const uint8_t ifac[16],
            const uint8_t privateKey[32], const uint8_t receiverPublic[2][32],
            wici_destination::AdmitFn admit, void* admitContext,
            Air& air, RandomFn random, void* randomContext);
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
    bool beacon();
    void cancelOwn() { if (ownActive_) finishOwn(false); }
    void onDelivery(DeliveryFn callback, void* context) { delivery_ = callback; deliveryContext_ = context; }
    bool ownBusy() const { return ownActive_; }
    bool exceptionTx() const { return ownActive_ && ownException_; }
    bool ready() const { return ready_; }
    wici_route::Table& routes() { return relay_.routes(); }

private:
    uint32_t backoff() const;
    uint16_t network_, own_, root_;
    uint8_t linkKey_[32] = {};
    bool keyReady_ = false, ready_ = false, routePending_ = false;
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
    bool ownException_ = false;
    DeliveryFn delivery_ = nullptr;
    void* deliveryContext_ = nullptr;
    void finishOwn(bool acknowledged);
    wici_destination::Destination destination_;
    wici_hop::Relay relay_;
    Air& air_;
    RandomFn random_;
    void* randomContext_;
};

}  // namespace wici_radio
