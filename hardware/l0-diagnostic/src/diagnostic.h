// SPDX-License-Identifier: MIT
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace diagnostic {

constexpr const char* VERSION = "l0-0.4";
constexpr uint32_t FRAM_SIZE = 512UL * 1024;
constexpr size_t BLOCK_SIZE = 256;
constexpr size_t MAX_PACKET = 80;
constexpr uint32_t MIX_DURATION_MS = 900000;
constexpr uint32_t MIX_INTERVAL_MS = 200;
constexpr uint32_t MIX_MAX_GAP_MS = 1000;

inline uint8_t pattern(uint32_t address, unsigned pass, uint32_t seed) {
    const uint8_t fixed[] = {0x00, 0xFF, 0xAA, 0x55};
    if (pass < 4) return fixed[pass];
    uint32_t x = address ^ seed;
    x ^= x >> 16;
    x *= 0x7FEB352DU;
    x ^= x >> 15;
    x *= 0x846CA68BU;
    x ^= x >> 16;
    return static_cast<uint8_t>(x);
}

inline uint32_t crc(uint32_t state, uint8_t byte) {
    state ^= byte;
    for (unsigned i = 0; i < 8; ++i)
        state = (state >> 1) ^ ((state & 1) ? 0xEDB88320UL : 0);
    return state;
}

inline bool inRange(uint32_t address, size_t size) {
    return address <= FRAM_SIZE && size <= FRAM_SIZE - address;
}

inline bool cooldownElapsed(uint32_t now, uint32_t started, uint32_t duration) {
    return now - started >= duration;
}

inline bool validPayload(const char* packet) {
    const size_t length = strlen(packet);
    if (length == 0 || length > MAX_PACKET) return false;
    for (size_t i = 0; i < length; ++i)
        if (packet[i] < 33 || packet[i] > 126) return false;
    return true;
}

}  // namespace diagnostic
