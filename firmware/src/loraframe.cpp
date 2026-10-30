// SPDX-License-Identifier: MIT
#include "loraframe.h"

#include <string.h>

namespace loraframe {

static_assert(declaredBitrate() > 4000 && declaredBitrate() < 5000, "przepływność ogłoszenia stacji w LoRa SF7: około 4,8 kb/s");

uint8_t header(uint8_t random, bool split, uint8_t previousNibble) {
    uint8_t nibble = random >> 4;
    if (!split) return static_cast<uint8_t>(nibble << 4);
    if (nibble == previousNibble) nibble = (nibble + 1) & 0x0F;  // inna połówka niż poprzedni datagram dzielony
    return static_cast<uint8_t>((nibble << 4) | FLAG_SPLIT);
}

size_t Splitter::split(const uint8_t* datagram, size_t length, uint8_t random, Frame out[2]) {
    const size_t count = frameCount(length);
    if (count == 0) return 0;
    const bool split = count == 2;
    const uint8_t head = header(random, split, previous_);
    if (split) previous_ = head >> 4;
    for (size_t i = 0; i < count; ++i) {
        const size_t offset = i * FIRST_DATA;
        out[i].length = frameLength(length, i);
        out[i].bytes[0] = head;
        memcpy(out[i].bytes + HEADER_BYTES, datagram + offset, out[i].length - HEADER_BYTES);
    }
    return count;
}

void Assembler::start(const uint8_t* body, size_t count, uint8_t nibble, uint32_t receivedMs) {
    memcpy(data_, body, count);
    length_ = count;
    nibble_ = nibble;
    startedMs_ = receivedMs;
    pending_ = true;
}

void Assembler::expire(uint32_t nowMs) {
    if (pending_ && nowMs - startedMs_ >= ASSEMBLY_TIMEOUT_MS) {
        pending_ = false;
        ++stats_.assembly_timeout;
    }
}

Outcome Assembler::push(const uint8_t* frame, size_t length, uint32_t receivedMs) {
    expire(receivedMs);
    if (length > lora::MAX_PAYLOAD) {
        ++stats_.bad_length;
        return Outcome::IGNORED;
    }
    if (length <= HEADER_BYTES) {
        // RNode zrobiłby z ramki split bez danych pierwszą część, a z ramki bez split pusty datagram.
        ++stats_.header_only;
        return Outcome::IGNORED;
    }
    const uint8_t nibble = frame[0] >> 4;
    const uint8_t* body = frame + HEADER_BYTES;
    const size_t count = length - HEADER_BYTES;
    if (!(frame[0] & FLAG_SPLIT)) {
        // Bez podziału: oczekująca część przepada, ramka idzie sama.
        if (pending_) ++stats_.split_lost;
        pending_ = false;
        memcpy(data_, body, count);
        length_ = count;
        return Outcome::COMPLETE;
    }
    if (pending_ && nibble == nibble_) {
        // Druga część; RNode nie wyjdzie poza swój bufor 508 B (dwie ramki mieszczą się zawsze).
        const size_t room = MAX_DATAGRAM - length_;
        memcpy(data_ + length_, body, count < room ? count : room);
        length_ += count < room ? count : room;
        pending_ = false;
        return Outcome::COMPLETE;
    }
    if (pending_) ++stats_.split_lost;  // inna połówka: poprzednia pierwsza część przepadła
    start(body, count, nibble, receivedMs);
    return Outcome::STORED;
}

}  // namespace loraframe
