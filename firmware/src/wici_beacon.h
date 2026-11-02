// SPDX-License-Identifier: MIT
// Per-node signature for the routed fields and root epoch token in a beacon.
#pragma once

#include <stdint.h>

#include "wici_route.h"

namespace wici_beacon {
constexpr unsigned CONTENT_BYTES = wici_link::BEACON_SIGNED;
constexpr unsigned SIGNATURE_BYTES = 64;
// `identity` is the 64-byte station key (Ed25519 secret in its second half).
bool sign(const uint8_t identity[64], const uint8_t publicKey[32], uint16_t network, uint16_t sender,
          const uint8_t content[CONTENT_BYTES], uint8_t signature[SIGNATURE_BYTES]);
// A complete BEACON frame for `value`, signed by its sender; 0 on failure.
size_t encode(const uint8_t linkKey[32], const uint8_t identity[64], const uint8_t publicKey[32],
              uint16_t network, uint16_t sender, uint16_t sequence, const wici_route::Beacon& value,
              uint8_t* out, size_t capacity);
bool verify(const uint8_t senderEd25519[32], uint16_t network, uint16_t sender,
            const uint8_t content[CONTENT_BYTES], const uint8_t signature[SIGNATURE_BYTES]);

// BEACON schedule. A BEACON follows the previous one by at least MIN_SPACING_MS.
constexpr uint32_t MIN_SPACING_MS = 60000;
constexpr uint32_t JITTER_MS = 4000;
// Earliest time for a BEACON due at `atMs` (a parent/rank change, a retry):
// pushed to MIN_SPACING_MS after the last one, then 0-4 s random, so siblings
// that heard the same parent BEACON do not transmit together.
inline uint32_t jittered(uint32_t atMs, uint32_t lastMs, bool sent, uint32_t random) {
    const uint32_t base = sent && atMs - lastMs < MIN_SPACING_MS ? lastMs + MIN_SPACING_MS : atMs;
    return base + random % (JITTER_MS + 1);
}
// A rank change earns an extra BEACON only from RANK_STEP (one ETX) on, or
// when a rank appears or lapses. The rank carries the HACK average of the link
// to the parent, which moves by small steps under load, and every BEACON
// costs each neighbour an Ed25519 check that blocks its loop. The 30-min
// BEACONs carry the exact rank.
constexpr uint16_t RANK_STEP = 16;
inline bool rankMoved(uint16_t rank, uint16_t advertised) {
    if (rank == 0xFFFF || advertised == 0xFFFF) return rank != advertised;
    return (rank > advertised ? rank - advertised : advertised - rank) >= RANK_STEP;
}
// The root restarts its burst (port opened, durable state recovered) only
// when MIN_SPACING_MS has passed since its last BEACON.
inline bool burstAllowed(uint32_t nowMs, uint32_t lastMs, bool sent) {
    return !sent || nowMs - lastMs >= MIN_SPACING_MS;
}
}  // namespace wici_beacon
