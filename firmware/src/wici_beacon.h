// SPDX-License-Identifier: MIT
// Per-node signature for the routed fields and root epoch token in a beacon.
#pragma once

#include <stdint.h>

namespace wici_beacon {
constexpr unsigned CONTENT_BYTES = 73;
constexpr unsigned SIGNATURE_BYTES = 64;
bool sign(const uint8_t identity[64], uint16_t network, uint16_t sender,
          const uint8_t content[CONTENT_BYTES], uint8_t signature[SIGNATURE_BYTES]);
bool verify(const uint8_t senderEd25519[32], uint16_t network, uint16_t sender,
            const uint8_t content[CONTENT_BYTES], const uint8_t signature[SIGNATURE_BYTES]);
}  // namespace wici_beacon
