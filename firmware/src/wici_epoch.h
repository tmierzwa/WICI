// SPDX-License-Identifier: MIT
// Root-signed epoch token carried unchanged by every routing beacon.
#pragma once

#include <stdint.h>

namespace wici_epoch {
constexpr uint8_t SIGNATURE_BYTES = 64;
bool sign(const uint8_t privateKey[64], uint16_t network, uint16_t root,
          uint16_t epoch, uint8_t signature[SIGNATURE_BYTES]);
bool verify(const uint8_t rootEd25519[32], uint16_t network, uint16_t root,
            uint16_t epoch, const uint8_t signature[SIGNATURE_BYTES]);
}  // namespace wici_epoch
