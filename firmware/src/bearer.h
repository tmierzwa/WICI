// SPDX-License-Identifier: MIT
// Reticulum adapter contract of the station application (station.h). The numbered
// WICI-Link path does not go through it: main.cpp wires wici_radio directly.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace bearer {

constexpr size_t LEGACY_ADDRESS = 16;

struct LegacyBearer {
    virtual ~LegacyBearer() = default;
    // Interface and transport both available for outgoing traffic.
    virtual bool radioReady() = 0;
    virtual bool busy() = 0;
    // May initiate path discovery; call before marking a station intent as sent.
    virtual bool sendReady(const uint8_t to[LEGACY_ADDRESS]) = 0;
    // 0 means no packet was accepted; a nonzero handle gets a later delivery event.
    virtual uint32_t send(const uint8_t to[LEGACY_ADDRESS], const uint8_t* data,
                          size_t length, uint32_t timeoutS) = 0;
    virtual void address(uint8_t out[LEGACY_ADDRESS]) = 0;
};

}  // namespace bearer
