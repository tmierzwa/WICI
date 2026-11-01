// SPDX-License-Identifier: MIT
#include "envelope_parts.h"

#include "envelope_record.h"

namespace envelope {
namespace {

// MAGIC(4) generation(4) net(2) recipient(2) sender(2) counter(4) zero(1) number(1)
// started(4) length(1) data(128) fingerprint(8) CRC(2) zero(29) COMMIT
constexpr uint8_t MAGIC[4] = {'W', 'F', 'P', '1'};
constexpr size_t DATA_AT = 25, FINGERPRINT_AT = DATA_AT + MAX_SA1 / 2;
constexpr size_t CRC_AT = FINGERPRINT_AT + FINGERPRINT;

uint32_t address(uint8_t peer, uint8_t copy) {
    return (peer == 0 ? PARTS_MAIN_BASE : PARTS_BACKUP_BASE) + copy * PARTS_COPY_BYTES;
}

bool zeros(const uint8_t* p, size_t from, size_t to) {
    for (size_t i = from; i < to; ++i)
        if (p[i]) return false;
    return true;
}

// A tombstone has no counter, number, time or data; a pending part has 1..128 bytes.
bool wellFormed(const uint8_t* p) {
    const uint8_t length = p[24];
    if (length > MAX_SA1 / 2 || p[18] || !zeros(p, DATA_AT + length, FINGERPRINT_AT) ||
        !zeros(p, CRC_AT + 2, PARTS_COPY_BYTES - 1)) return false;
    return length ? p[19] == 1 || p[19] == 2 : !p[19] && !get32(p + 14) && !get32(p + 20);
}

}  // namespace

bool DurableParts::begin(uint16_t network, uint16_t recipient, uint16_t sender, const uint8_t key[32]) {
    ready_ = false;
    generation_ = counter_ = startedS_ = 0;
    copy_ = 1; number_ = length_ = 0;
    memset(data_, 0, sizeof(data_));
    if (peerSlot_ >= PARTS_PEERS || !key || !stationId(network) || !stationId(recipient) ||
        !stationId(sender) || recipient == sender) return false;
    fingerprint(key, fingerprint_);
    network_ = network; recipient_ = recipient; sender_ = sender;
    bool found = false;
    for (uint8_t copy = 0; copy < 2; ++copy) {
        uint8_t record[PARTS_COPY_BYTES];
        record::Copy state;
        if (!record::load(storage_, address(peerSlot_, copy), record, CRC_AT, MAGIC, state)) return false;
        if (state == record::Copy::ABSENT) continue;
        if (state == record::Copy::DAMAGED || !wellFormed(record)) return false;
        if (memcmp(record + FINGERPRINT_AT, fingerprint_, FINGERPRINT)) continue;  // another key
        if (get16(record + 8) != network || get16(record + 10) != recipient ||
            get16(record + 12) != sender) return false;
        const uint32_t generation = get32(record + 4);
        if (!found || static_cast<int32_t>(generation - generation_) > 0) {
            generation_ = generation; copy_ = copy;
            counter_ = get32(record + 14); number_ = record[19];
            startedS_ = get32(record + 20); length_ = record[24];
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
        record[19] = part->number;
        put32(record + 20, nowS);
        record[24] = static_cast<uint8_t>(part->length);
        memcpy(record + DATA_AT, part->plaintext, part->length);
    }
    memcpy(record + FINGERPRINT_AT, fingerprint_, FINGERPRINT);
    const uint8_t target = static_cast<uint8_t>(1 - copy_);
    const bool stored = record::store(storage_, address(peerSlot_, target), record, CRC_AT);
    memset(record, 0, sizeof(record));
    if (!stored) {
        ready_ = false;
        return false;
    }
    ++generation_; copy_ = target;
    counter_ = part ? part->counter : 0;
    startedS_ = part ? nowS : 0;
    number_ = part ? part->number : 0;
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
    if (!length_ || (nowS >= startedS_ && nowS - startedS_ > PARTS_TIMEOUT_S))
        return commit(&part, nowS) ? FragmentResult::PARTIAL : FragmentResult::IO_ERROR;
    if (counter_ != part.counter) return FragmentResult::REJECTED;
    if (number_ == part.number)
        return length_ == part.length && memcmp(data_, part.plaintext, length_) == 0 ?
               FragmentResult::PARTIAL : FragmentResult::REJECTED;
    const uint8_t* first = number_ == 1 ? data_ : part.plaintext;
    const uint8_t* second = number_ == 1 ? part.plaintext : data_;
    const size_t firstLength = number_ == 1 ? length_ : part.length;
    const size_t secondLength = number_ == 1 ? part.length : length_;
    memcpy(full, first, firstLength);
    memcpy(full + firstLength, second, secondLength);
    length = firstLength + secondLength;
    return FragmentResult::COMPLETE;
}

bool DurableParts::clear() { return ready_ && commit(nullptr, 0); }

}  // namespace envelope
