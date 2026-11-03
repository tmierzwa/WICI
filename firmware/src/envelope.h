// SPDX-License-Identifier: MIT
// WICI envelope v1 codec (docs/spec/transport.md). The production send path reserves ctr in
// FRAM first (sealReserved); the receive path commits the replay window (envelope_replay.h)
// together with SA1 admission, not when a fragment merely arrives.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace envelope {

class Counter;

constexpr size_t HEADER = 9;
constexpr size_t TAG = 16;
constexpr size_t OVERHEAD = HEADER + TAG;
constexpr size_t MAX_SA1 = 256;
constexpr size_t MAX_FRAME = MAX_SA1 + OVERHEAD;
constexpr size_t MIN_PAYLOAD = 153;
static_assert(MIN_PAYLOAD == MAX_SA1 / 2 + OVERHEAD, "two parts fit every bearer");
constexpr uint8_t TYPE_SA1 = 0;
// A station's delivery proof to the receiver (transport.md); a station never opens one. 2..15 are reserved.
constexpr uint8_t TYPE_PROOF = 1;
constexpr size_t PROOF_COUNTERS = 16;  // u32 counters of resolved SA1 messages, 1..16 per proof

struct Frame {
    uint8_t bytes[MAX_FRAME] = {};
    size_t length = 0;
};

struct Part {
    uint16_t sender = 0;
    uint16_t recipient = 0;
    uint32_t counter = 0;
    uint8_t type = TYPE_SA1;  // openPart() accepts no other type
    uint8_t number = 0;  // 0 = whole; 1 or 2 = fragment
    uint8_t plaintext[MAX_SA1] = {};
    size_t length = 0;
};

// X25519 with a raw private key (clamped here): the own public key and the shared secret with
// peerPublic. Returns false, with both outputs wiped, for an all-zero (weak peer point) secret.
bool agree(const uint8_t privateKey[32], const uint8_t peerPublic[32], uint8_t ownPublic[32],
           uint8_t shared[32]);

// ownId is sender or recipient in the wire direction; privateKey and peerPublic are raw X25519 keys.
// Returns false for a reserved station number, same endpoint, or weak peer point.
bool deriveKey(const uint8_t privateKey[32], const uint8_t peerPublic[32], uint16_t netId,
               uint16_t sender, uint16_t recipient, uint16_t ownId, uint8_t out[32]);

// Returns 1 or 2 frames; 0 on invalid input/capacity. Frames are independently authenticated.
size_t seal(const uint8_t key[32], uint16_t sender, uint16_t recipient, uint32_t counter,
            const uint8_t* plaintext, size_t length, size_t maxPayload, Frame out[2],
            uint8_t type = TYPE_SA1);
// Production send path: reserves a counter in FRAM first, then seals. A failed
// encryption may burn a counter but can never reuse it. Rejects a mismatched binding.
size_t sealReserved(Counter& counter, const uint8_t key[32], uint16_t netId, uint16_t sender,
                    uint16_t recipient, const uint8_t* plaintext, size_t length, size_t maxPayload,
                    Frame out[2], uint8_t type = TYPE_SA1);
// Releases plaintext only after the tag verifies; SA1 only. On failure, out is zeroed.
bool openPart(const uint8_t key[32], const uint8_t* frame, size_t length, Part& out);

}  // namespace envelope
