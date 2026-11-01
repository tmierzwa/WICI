// SPDX-License-Identifier: MIT
// Per-neighbor authentication for unicast WICI radio frames.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "config.h"
#include "wici_link.h"

namespace wici_hop_auth {

constexpr size_t TAG = 8;
constexpr size_t MAX_BARE = wici_link::MAX_FRAME - TAG;

class Auth {
public:
    bool begin(uint16_t network, uint16_t own, const uint8_t privateKey[32],
               const config::PriorityKey* peers, uint8_t count);
    // Broadcast frames carry only the existing group MAC and signed content.
    // Unicast frames get a pairwise tag covering every byte of the bare frame.
    size_t seal(const uint8_t* bare, size_t length, uint8_t* out, size_t capacity) const;
    bool open(const uint8_t* radio, size_t length, uint8_t* bare,
              size_t capacity, size_t& bareLength) const;

private:
    const uint8_t* key(uint16_t peer) const;
    uint16_t network_ = 0, own_ = 0;
    uint16_t ids_[config::PRIORITY_KEYS_MAX] = {};
    uint8_t keys_[config::PRIORITY_KEYS_MAX][32] = {};
    uint8_t count_ = 0;
};

}  // namespace wici_hop_auth
