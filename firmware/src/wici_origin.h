// SPDX-License-Identifier: MIT
// End-to-end K1 proof for a WICI-Link DATA payload. The signature is copied
// unchanged by every relay; the link MAC is renewed on each hop.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "wici_link.h"

namespace wici_origin {

// Public/private are the existing 64-byte station or receiver identity keys.
// The signed domain includes the network and the exact encrypted envelope.
bool sign(const uint8_t privateKey[64], const uint8_t publicKey[64], uint16_t network,
          const uint8_t* envelope, size_t length, uint8_t out[wici_link::ORIGIN_SIGNATURE]);
bool verify(const uint8_t publicKey[64], uint16_t network, const uint8_t* envelope,
            size_t length, const uint8_t signature[wici_link::ORIGIN_SIGNATURE]);

}  // namespace wici_origin
