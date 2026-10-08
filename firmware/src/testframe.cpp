// SPDX-License-Identifier: MIT
#include "testframe.h"

#include "crc16.h"

namespace testframe {

namespace {

// Generator PN9 (x^9 + x^5 + 1) jak w wybielaniu CC1120, zasiany numerem ramki,
// żeby wypełnienie przypominało zaszyfrowany ruch Reticulum, a nie stały wzór.
uint8_t pn9Byte(uint16_t& state) {
    uint8_t out = 0;
    for (int bit = 0; bit < 8; ++bit) {
        const uint8_t lsb = state & 1;
        out |= lsb << bit;
        const uint8_t feedback = ((state >> 5) ^ state) & 1;
        state = static_cast<uint16_t>((state >> 1) | (feedback << 8));
    }
    return out;
}

}  // namespace

bool build(uint8_t* frame, size_t length, uint16_t seq, Fill fill) {
    if (length < MIN_LENGTH || length > MAX_LENGTH) {
        return false;
    }
    frame[0] = static_cast<uint8_t>(seq >> 8);
    frame[1] = static_cast<uint8_t>(seq & 0xFF);
    uint16_t state = static_cast<uint16_t>((seq | 0x100) & 0x1FF);  // stan PN9 nigdy nie jest zerem
    for (size_t i = 2; i + 2 < length; ++i) {
        frame[i] = fill == Fill::ZEROS ? 0x00 : fill == Fill::ONES ? 0xFF : pn9Byte(state);
    }
    const uint16_t crc = p1::crc16(frame, length - 2);
    frame[length - 2] = static_cast<uint8_t>(crc >> 8);
    frame[length - 1] = static_cast<uint8_t>(crc & 0xFF);
    return true;
}

bool check(const uint8_t* frame, size_t length, uint16_t* seq) {
    if (length < MIN_LENGTH || length > MAX_LENGTH) {
        return false;
    }
    const uint16_t expected = static_cast<uint16_t>((frame[length - 2] << 8) | frame[length - 1]);
    if (p1::crc16(frame, length - 2) != expected) {
        return false;
    }
    if (seq) {
        *seq = static_cast<uint16_t>((frame[0] << 8) | frame[1]);
    }
    return true;
}

}  // namespace testframe
