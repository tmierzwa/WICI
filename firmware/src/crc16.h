// SPDX-License-Identifier: MIT
// CRC-16 ramki P1 (docs/spec/radio.md): wielomian 0x1021, wartość początkowa 0xFFFF,
// bez odwracania bitów, końcowy XOR 0 (CRC-16/CCITT-FALSE). Wektor: "123456789" -> 0x29B1.
// Bez zależności od Arduino, żeby dało się sprawdzić na komputerze (tests/test_firmware_host.py).
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace p1 {

inline uint16_t crc16(const uint8_t* data, size_t length, uint16_t crc = 0xFFFF) {
    for (size_t i = 0; i < length; ++i) {
        crc ^= static_cast<uint16_t>(data[i]) << 8;
        for (int bit = 0; bit < 8; ++bit) {
            crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021) : static_cast<uint16_t>(crc << 1);
        }
    }
    return crc;
}

}  // namespace p1
