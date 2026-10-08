// SPDX-License-Identifier: MIT
// CRC-32 znacznika zatwierdzenia rekordów FRAM (docs/spec/oprogramowanie.md, "Trwałość
// i potwierdzenia"): CRC-32/ISO-HDLC (wielomian 0x04C11DB7 odwrócony, wartość początkowa
// i końcowy XOR 0xFFFFFFFF), jak zlib.crc32. Wektor: "123456789" -> 0xCBF43926. Wartość
// pośrednią (bez końcowego XOR) zwraca update(), więc rekord liczy się w częściach.
// Bez zależności od Arduino; sprawdzany na komputerze.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace crc32 {

constexpr uint32_t START = 0xFFFFFFFFu;

// Tablica 16 wpisów (pół bajtu na krok): mała w pamięci programu, kilka razy szybsza od pętli po bitach.
inline uint32_t update(uint32_t crc, const uint8_t* data, size_t length) {
    static const uint32_t table[16] = {0x00000000, 0x1DB71064, 0x3B6E20C8, 0x26D930AC, 0x76DC4190, 0x6B6B51F4,
                                       0x4DB26158, 0x5005713C, 0xEDB88320, 0xF00F9344, 0xD6D6A3E8, 0xCB61B38C,
                                       0x9B64C2B0, 0x86D3D2D4, 0xA00AE278, 0xBDBDF21C};
    for (size_t i = 0; i < length; ++i) {
        crc ^= data[i];
        crc = (crc >> 4) ^ table[crc & 0x0F];
        crc = (crc >> 4) ^ table[crc & 0x0F];
    }
    return crc;
}

inline uint32_t finish(uint32_t crc) { return crc ^ 0xFFFFFFFFu; }

inline uint32_t of(const uint8_t* data, size_t length) { return finish(update(START, data, length)); }

}  // namespace crc32
