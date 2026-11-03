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
    uint16_t root = 0;  // the receiver's radio node: a HACK to it proves delivery
};

using AdmitFn = bool (*)(uint16_t network, uint16_t sender, uint16_t recipient,
                         const uint8_t* content, size_t length, void* context);

// SETTLED: a frame this station can never admit, from a relay; the HACK only
// ends that relay's retries and resolves nothing (no delivery proof).
enum class Outcome : uint8_t { IGNORED, ACCEPTED, HACK_READY, SETTLED, REJECTED };

// A whole SA1 message this frame resolved (admitted, or settled as a duplicate,
// late or skipped message): the station owes its sender a delivery proof.
struct Resolved {
    bool valid = false;
    uint8_t peer = 0;  // receiver slot of the envelope sender
    uint32_t counter = 0;
};

class Destination {
public:
    Destination(journal::Storage& storage, Config config, const uint8_t ifac[16],
                const uint8_t privateKey[32], const uint8_t peerPublic[2][32],
                AdmitFn admit, void* context);
    // Re-reads replay windows and parts; also the recovery after ready() fell.
    bool begin();
    // False after an uncertain FRAM write of a replay window or part.
    bool ready() const { return ready_ && replay_[0].ready() && replay_[1].ready(); }
    // HACK_READY only after part storage or the SA1 effect and replay window
    // are durable. Broadcast frames are accepted without a HACK. A repeat or a
    // first part alone resolves nothing.
    Outcome receive(const uint8_t* wire, size_t length, uint32_t nowS,
                    uint8_t* hack, size_t capacity, size_t& hackLength, Resolved* resolved = nullptr);

private:
    Config config_;
    uint8_t linkKey_[32] = {};
    uint8_t envelopeKeys_[2][32] = {};
    bool keysReady_ = false, ready_ = false;
    envelope::DurableReplay replay_[2];
    envelope::DurableParts parts_[2];
    AdmitFn admit_;
    void* context_;
    wici_link::RepeatHack repeatHack_;
    wici_link::OwedHacks owedHacks_;
};

}  // namespace wici_destination
