// SPDX-License-Identifier: MIT
// Final shelter recipient of authenticated WICI-Link frames. Admission callback
// must make the SA1 effect durable and idempotent before returning true.
#pragma once

#include "envelope_parts.h"
#include "envelope_replay.h"
#include "wici_link.h"

namespace wici_destination {

struct Config {
    uint16_t network = 0, own = 0;
    uint16_t receiver[2] = {};
};

using AdmitFn = bool (*)(uint16_t network, uint16_t sender, uint16_t recipient,
                         const uint8_t* content, size_t length, void* context);

enum class Outcome : uint8_t { IGNORED, ACCEPTED, HACK_READY, REJECTED };

class Destination {
public:
    Destination(journal::Storage& storage, Config config, const uint8_t ifac[16],
                const uint8_t privateKey[32], const uint8_t peerPublic[2][32],
                AdmitFn admit, void* context);
    bool begin();
    // HACK_READY only after part storage or the SA1 effect and replay window
    // are durable. Broadcast frames are accepted without a HACK.
    Outcome receive(const uint8_t* wire, size_t length, uint32_t nowS,
                    uint8_t* hack, size_t capacity, size_t& hackLength);

private:
    Config config_;
    uint8_t linkKey_[32] = {};
    uint8_t envelopeKeys_[2][32] = {};
    bool keysReady_ = false, ready_ = false;
    envelope::DurableReplay replay_[2];
    envelope::DurableParts parts_[2];
    AdmitFn admit_;
    void* context_;
};

}  // namespace wici_destination
