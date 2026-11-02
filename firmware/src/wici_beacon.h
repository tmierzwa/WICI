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
}  // namespace wici_beacon
