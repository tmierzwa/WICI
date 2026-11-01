// SPDX-License-Identifier: MIT
#include "envelope_parts.h"

#include <string.h>

namespace envelope {
namespace {
constexpr uint8_t MAGIC[4] = {'W', 'F', 'P', '1'}, COMMIT = 0xA5;
constexpr size_t DATA_AT = 25, CRC_AT = DATA_AT + MAX_SA1 / 2;
uint16_t u16(const uint8_t* p) { return static_cast<uint16_t>((p[0] << 8) | p[1]); }
uint32_t u32(const uint8_t* p) {
    return (static_cast<uint32_t>(p[0]) << 24) | (static_cast<uint32_t>(p[1]) << 16) |
           (static_cast<uint32_t>(p[2]) << 8) | p[3];
}
void put16(uint8_t* p, uint16_t n) { p[0] = static_cast<uint8_t>(n >> 8); p[1] = static_cast<uint8_t>(n); }
void put32(uint8_t* p, uint32_t n) {
    p[0] = static_cast<uint8_t>(n >> 24); p[1] = static_cast<uint8_t>(n >> 16);
    p[2] = static_cast<uint8_t>(n >> 8); p[3] = static_cast<uint8_t>(n);
}
uint16_t crc(const uint8_t* p, size_t count) {
    uint16_t c = 0xFFFF;
    for (size_t i = 0; i < count; ++i) {
        c ^= static_cast<uint16_t>(p[i]) << 8;
        for (uint8_t j = 0; j < 8; ++j)
            c = c & 0x8000 ? static_cast<uint16_t>((c << 1) ^ 0x1021) : static_cast<uint16_t>(c << 1);
    }
    return c;
}
bool blank(const uint8_t* p) {
    bool zero = true, erased = true;
    for (size_t i = 0; i < PARTS_COPY_BYTES; ++i) { zero &= p[i] == 0; erased &= p[i] == 0xFF; }
    return zero || erased;
}
bool id(uint16_t n) { return n && n != 0xFFFF; }
uint32_t address(uint8_t peer, uint8_t copy) {
    return (peer == 0 ? PARTS_MAIN_BASE : PARTS_BACKUP_BASE) + copy * PARTS_COPY_BYTES;
}
bool recordValid(const uint8_t* p, uint16_t network, uint16_t recipient, uint16_t sender) {
    if (memcmp(p, MAGIC, 4) || u16(p + 8) != network || u16(p + 10) != recipient ||
        u16(p + 12) != sender || u16(p + CRC_AT) != crc(p, CRC_AT) ||
        p[24] > MAX_SA1 / 2 || (p[24] && (p[18] != 0 || (p[19] != 1 && p[19] != 2))) ||
        (!p[24] && (p[18] || p[19] || u32(p + 14) || u32(p + 20)))) return false;
    for (size_t i = DATA_AT + p[24]; i < PARTS_COPY_BYTES - 1; ++i)
        if (i != CRC_AT && i != CRC_AT + 1 && p[i]) return false;
    return true;
}
}  // namespace

bool DurableParts::begin(uint16_t network, uint16_t recipient, uint16_t sender) {
    ready_ = false;
    generation_ = counter_ = startedS_ = 0;
    copy_ = 1; number_ = type_ = length_ = 0;
    memset(data_, 0, sizeof(data_));
    if (peerSlot_ >= PARTS_PEERS || !id(network) || !id(recipient) || !id(sender) ||
        recipient == sender) return false;
    network_ = network; recipient_ = recipient; sender_ = sender;
    bool found = false;
    for (uint8_t copy = 0; copy < 2; ++copy) {
        uint8_t record[PARTS_COPY_BYTES];
        if (!storage_.read(address(peerSlot_, copy), record, sizeof(record))) return false;
        if (blank(record) || record[PARTS_COPY_BYTES - 1] != COMMIT) continue;
        if (!recordValid(record, network, recipient, sender)) return false;
        const uint32_t generation = u32(record + 4);
        if (!found || static_cast<int32_t>(generation - generation_) > 0) {
            generation_ = generation; copy_ = copy;
            counter_ = u32(record + 14); type_ = record[18]; number_ = record[19];
            startedS_ = u32(record + 20); length_ = record[24];
            memcpy(data_, record + DATA_AT, sizeof(data_));
            found = true;
        }
    }
    ready_ = true;
    return true;
}

bool DurableParts::commit(const Part* part, uint32_t nowS) {
    uint8_t record[PARTS_COPY_BYTES] = {};
    memcpy(record, MAGIC, 4);
    put32(record + 4, generation_ + 1);
    put16(record + 8, network_);
    put16(record + 10, recipient_);
    put16(record + 12, sender_);
    if (part) {
        put32(record + 14, part->counter);
        record[18] = part->type; record[19] = part->number;
        put32(record + 20, nowS);
        record[24] = static_cast<uint8_t>(part->length);
        memcpy(record + DATA_AT, part->plaintext, part->length);
    }
    put16(record + CRC_AT, crc(record, CRC_AT));
    const uint8_t target = static_cast<uint8_t>(1 - copy_);
    const uint32_t at = address(peerSlot_, target);
    const uint8_t clear = 0;
    if (!storage_.write(at + PARTS_COPY_BYTES - 1, &clear, 1) ||
        !storage_.write(at, record, PARTS_COPY_BYTES - 1) ||
        !storage_.write(at + PARTS_COPY_BYTES - 1, &COMMIT, 1)) {
        ready_ = false;
        return false;
    }
    uint8_t verify[PARTS_COPY_BYTES];
    if (!storage_.read(at, verify, sizeof(verify)) || memcmp(record, verify, PARTS_COPY_BYTES - 1) ||
        verify[PARTS_COPY_BYTES - 1] != COMMIT) {
        ready_ = false;
        return false;
    }
    ++generation_; copy_ = target;
    counter_ = part ? part->counter : 0;
    startedS_ = part ? nowS : 0;
    number_ = part ? part->number : 0;
    type_ = part ? part->type : 0;
    length_ = part ? static_cast<uint8_t>(part->length) : 0;
    memset(data_, 0, sizeof(data_));
    if (part) memcpy(data_, part->plaintext, part->length);
    return true;
}

FragmentResult DurableParts::ingest(const Part& part, uint32_t nowS, uint8_t full[MAX_SA1], size_t& length) {
    length = 0;
    if (!ready_ || !full) return FragmentResult::IO_ERROR;
    if (part.sender != sender_ || part.recipient != recipient_ || part.type != 0 ||
        (part.number != 1 && part.number != 2) || !part.length || part.length > MAX_SA1 / 2)
        return FragmentResult::REJECTED;
    if (!length_ || (nowS >= startedS_ && nowS - startedS_ > PARTS_TIMEOUT_S)) {
        return commit(&part, nowS) ? FragmentResult::PARTIAL : FragmentResult::IO_ERROR;
    }
    if (counter_ != part.counter || type_ != part.type) return FragmentResult::REJECTED;
    if (number_ == part.number)
        return length_ == part.length && memcmp(data_, part.plaintext, length_) == 0 ?
               FragmentResult::PARTIAL : FragmentResult::REJECTED;
    if (length_ + part.length > MAX_SA1) return FragmentResult::REJECTED;
    if (number_ == 1) {
        memcpy(full, data_, length_);
        memcpy(full + length_, part.plaintext, part.length);
    } else {
        memcpy(full, part.plaintext, part.length);
        memcpy(full + part.length, data_, length_);
    }
    length = length_ + part.length;
    return FragmentResult::COMPLETE;
}

bool DurableParts::clear() { return ready_ && commit(nullptr, 0); }

}  // namespace envelope
