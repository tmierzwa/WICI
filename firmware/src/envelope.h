// SPDX-License-Identifier: MIT
// WICI envelope v1 codec. Caller reserves ctr in durable storage before seal(); caller commits
// ReplayWindow together with SA1 admission, not when a fragment merely arrives.
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

struct Frame {
    uint8_t bytes[MAX_FRAME] = {};
    size_t length = 0;
};

struct Part {
    uint16_t sender = 0;
    uint16_t recipient = 0;
    uint32_t counter = 0;
    uint8_t type = 0;
    uint8_t number = 0;  // 0 = whole; 1 or 2 = fragment
    uint8_t plaintext[MAX_SA1] = {};
    size_t length = 0;
};

// ownId is sender or recipient in the wire direction; privateKey and peerPublic are raw X25519 keys.
// Returns false for a reserved station number, same endpoint, or weak peer point.
bool deriveKey(const uint8_t privateKey[32], const uint8_t peerPublic[32], uint16_t netId,
               uint16_t sender, uint16_t recipient, uint16_t ownId, uint8_t out[32]);

// Returns 1 or 2 frames; 0 on invalid input/capacity. Frames are independently authenticated.
size_t seal(const uint8_t key[32], uint16_t sender, uint16_t recipient, uint32_t counter,
            const uint8_t* plaintext, size_t length, size_t maxPayload, Frame out[2], uint8_t type = 0);
// Production send path: reserves a counter in FRAM first, then seals. A failed
// encryption may burn a counter but can never reuse it. Rejects a mismatched binding.
size_t sealReserved(Counter& counter, const uint8_t key[32], uint16_t netId, uint16_t sender,
                    uint16_t recipient, const uint8_t* plaintext, size_t length, size_t maxPayload,
                    Frame out[2], uint8_t type = 0);
// Decrypts only after checking the tag. On failure, out is zeroed.
bool openPart(const uint8_t key[32], const uint8_t* frame, size_t length, Part& out);

struct ReplayWindow {
    uint32_t highest = 0;
    uint64_t mask = 0;
    bool started = false;
    // Computes proposed next state without mutating this one; persist next with the SA1 record.
    bool accept(uint32_t counter, ReplayWindow& next) const;
};

}  // namespace envelope
