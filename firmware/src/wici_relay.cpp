// SPDX-License-Identifier: MIT
#include "wici_relay.h"

#include <string.h>

namespace wici_relay {
namespace {

constexpr uint8_t MAGIC[4] = {'W', 'R', 'Q', '1'};
constexpr uint8_t COMMIT = 0xA5;
constexpr size_t WIRE_AT = 25, CRC_AT = WIRE_AT + wici_link::MAX_FRAME;
static_assert(CRC_AT + 2 < COPY_BYTES, "record fits in relay copy");

uint32_t address(uint8_t slot, uint8_t copy) {
    return BASE + (static_cast<uint32_t>(slot) * 2 + copy) * COPY_BYTES;
}
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
    for (size_t i = 0; i < COPY_BYTES; ++i) { zero &= p[i] == 0; erased &= p[i] == 0xFF; }
    return zero || erased;
}
bool valid(const uint8_t* p) {
    const size_t n = u16(p + 8);
    if (memcmp(p, MAGIC, 4) || (n && (n < wici_link::HEADER + wici_link::TAG || n > wici_link::MAX_FRAME)) ||
        (!n && u16(p + 23)) || u16(p + 23) == wici_link::BROADCAST ||
        u16(p + CRC_AT) != crc(p, CRC_AT)) return false;
    for (size_t i = WIRE_AT + n; i < CRC_AT; ++i) if (p[i]) return false;
    return true;
}
bool transitDestination(const wici_link::Frame& frame, uint16_t ownId) {
    return frame.destination == ownId ||
           (frame.destination == wici_link::BROADCAST &&
            (frame.flags & wici_link::DOWN) && !(frame.flags & wici_link::ACKREQ));
}

}  // namespace

bool Queue::begin() {
    ready_ = false;
    if (!seen_.begin()) return false;
    memset(frames_, 0, sizeof(frames_));
    memset(lengths_, 0, sizeof(lengths_));
    memset(generations_, 0, sizeof(generations_));
    memset(copies_, 0, sizeof(copies_));
    memset(origins_, 0, sizeof(origins_));
    memset(admittedS_, 0, sizeof(admittedS_));
    for (uint8_t slot = 0; slot < SLOTS; ++slot) {
        bool found = false;
        for (uint8_t copy = 0; copy < 2; ++copy) {
            uint8_t data[COPY_BYTES];
            if (!storage_.read(address(slot, copy), data, sizeof(data))) return false;
            if (blank(data) || data[COPY_BYTES - 1] != COMMIT) continue;
            if (!valid(data)) return false;
            uint32_t generation = u32(data + 4);
            if (!found || static_cast<int32_t>(generation - generations_[slot]) > 0) {
                generations_[slot] = generation;
                copies_[slot] = copy;
                lengths_[slot] = u16(data + 8);
                // A provisioned signing key may have changed since this
                // record was written. Reverify the origin after every boot.
                origins_[slot] = 0;
                admittedS_[slot] = u32(data + 19);
                memcpy(frames_[slot], data + WIRE_AT, lengths_[slot]);
                found = true;
            }
        }
    }
    ready_ = true;
    return true;
}

bool Queue::commit(uint8_t slot, const uint8_t* wire, size_t length,
                   uint16_t verifiedOrigin, uint32_t admittedS) {
    uint8_t data[COPY_BYTES] = {};
    memcpy(data, MAGIC, 4);
    put32(data + 4, generations_[slot] + 1);
    put16(data + 8, static_cast<uint16_t>(length));
    if (length) {
        memcpy(data + WIRE_AT, wire, length);
        // Cached addressing fields support on-disk inspection after a crash.
        memcpy(data + 10, wire + 1, 2);  // network
        memcpy(data + 12, wire + 3, 2);  // link source
        memcpy(data + 14, wire + 8, 2);  // link sequence
        memcpy(data + 16, wire + wici_link::HEADER, 3);  // envelope version and source
        put32(data + 19, admittedS);
        put16(data + 23, verifiedOrigin);  // verified origin, covered by CRC and COMMIT
    }
    put16(data + CRC_AT, crc(data, CRC_AT));
    const uint8_t target = static_cast<uint8_t>(1 - copies_[slot]);
    const uint32_t at = address(slot, target);
    const uint8_t clear = 0;
    if (!storage_.write(at + COPY_BYTES - 1, &clear, 1) ||
        !storage_.write(at, data, COPY_BYTES - 1) ||
        !storage_.write(at + COPY_BYTES - 1, &COMMIT, 1)) {
        ready_ = false;  // The target copy may have committed despite the reported error.
        return false;
    }
    uint8_t verify[COPY_BYTES];
    if (!storage_.read(at, verify, sizeof(verify)) || memcmp(data, verify, COPY_BYTES - 1) ||
        verify[COPY_BYTES - 1] != COMMIT) {
        ready_ = false;
        return false;
    }
    ++generations_[slot];
    copies_[slot] = target;
    lengths_[slot] = static_cast<uint16_t>(length);
    origins_[slot] = length ? verifiedOrigin : 0;
    admittedS_[slot] = length ? admittedS : 0;
    memset(frames_[slot], 0, sizeof(frames_[slot]));
    if (length) memcpy(frames_[slot], wire, length);
    return true;
}

Admission Queue::admit(const uint8_t key[32], uint16_t network, uint16_t ownId,
                       const uint8_t* wire, size_t length, uint32_t nowS,
                       uint8_t freeSlotsReserved, uint16_t verifiedOrigin) {
    if (!ready_ || !key || !wire || !ownId || ownId == wici_link::BROADCAST) return Admission::REJECTED;
    wici_link::Frame frame;
    if (!wici_link::decode(key, network, wire, length, frame) || frame.type != wici_link::Type::DATA ||
        !transitDestination(frame, ownId) || frame.hops >= frame.ttl ||
        freeSlotsReserved > SLOTS ||
        (verifiedOrigin && (verifiedOrigin == wici_link::BROADCAST ||
                            verifiedOrigin != u16(frame.payload + 1)))) return Admission::REJECTED;
    const wici_seen::Lookup prior = seen_.lookup(wire, length, nowS);
    if (prior == wici_seen::Lookup::MATCH) return Admission::FORWARDED;
    if (prior == wici_seen::Lookup::CONFLICT) return Admission::REJECTED;
    if (prior == wici_seen::Lookup::IO_ERROR) return Admission::IO_ERROR;
    for (uint8_t i = 0; i < SLOTS; ++i) {
        if (!lengths_[i]) continue;
        wici_link::Frame oldFrame;
        if (!wici_link::decode(key, network, frames_[i], lengths_[i], oldFrame) ||
            oldFrame.type != wici_link::Type::DATA || !transitDestination(oldFrame, ownId))
            return Admission::REJECTED;  // An old key/configuration cannot authorize a new HACK.
        // Link sender/sequence can change after a parent switch. The end-to-end
        // envelope header identifies the same intent; only identical ciphertext
        // earns another HACK. A conflicting payload cannot overwrite it.
        const uint8_t* old = frames_[i] + wici_link::HEADER;
        const uint8_t* incoming = wire + wici_link::HEADER;
        if (memcmp(old, incoming, 9) == 0) {
            if (lengths_[i] == length &&
                memcmp(old, incoming, length - wici_link::HEADER - wici_link::TAG) == 0)
                return Admission::DUPLICATE;
            return Admission::REJECTED;
        }
    }
    if (verifiedOrigin) {
        for (uint8_t i = 0; i < SLOTS; ++i)
            if (lengths_[i] && origins_[i] == verifiedOrigin) return Admission::FULL;
    }
    uint8_t free = 0, first = SLOTS;
    for (uint8_t i = 0; i < SLOTS; ++i) {
        if (lengths_[i]) continue;
        if (first == SLOTS) first = i;
        ++free;
    }
    if (free > freeSlotsReserved)
        return commit(first, wire, length, verifiedOrigin, nowS) ? Admission::STORED : Admission::IO_ERROR;
    return Admission::FULL;
}

bool Queue::pending(uint8_t slot) const { return ready_ && slot < SLOTS && lengths_[slot]; }

bool Queue::markVerified(uint8_t slot, uint16_t origin) {
    if (!pending(slot) || !origin || origin == wici_link::BROADCAST) return false;
    if (origins_[slot] == origin) return true;
    if (origins_[slot]) return false;
    uint8_t wire[wici_link::MAX_FRAME];
    memcpy(wire, frames_[slot], lengths_[slot]);
    return commit(slot, wire, lengths_[slot], origin, admittedS_[slot]);
}

bool Queue::expire(uint32_t nowS) {
    if (!ready_) return false;
    for (uint8_t slot = 0; slot < SLOTS; ++slot) {
        if (!lengths_[slot] || nowS < admittedS_[slot] ||
            nowS - admittedS_[slot] < MAX_HOLD_S) continue;
        const wici_seen::Lookup state = seen_.lookup(frames_[slot], lengths_[slot], nowS);
        if (state == wici_seen::Lookup::IO_ERROR) return false;
        // A different payload with the same envelope identity may already be
        // in the seen ring. Retire this item without replacing that record.
        if (state == wici_seen::Lookup::CONFLICT) {
            if (!commit(slot, nullptr, 0)) return false;
        } else if (!remove(slot, nowS)) return false;
    }
    return true;
}

bool Queue::read(const uint8_t key[32], uint16_t network, uint16_t ownId, uint8_t slot,
                 uint32_t nowS, uint8_t* out, size_t capacity, size_t& length) {
    length = 0;
    if (!key || !out || !pending(slot) || capacity < lengths_[slot]) return false;
    wici_link::Frame frame;
    if (!wici_link::decode(key, network, frames_[slot], lengths_[slot], frame) ||
        frame.type != wici_link::Type::DATA || !transitDestination(frame, ownId)) return false;
    if (seen_.lookup(frames_[slot], lengths_[slot], nowS) != wici_seen::Lookup::NONE) return false;
    length = lengths_[slot];
    memcpy(out, frames_[slot], length);
    return true;
}

bool Queue::finishForwarded(const uint8_t key[32], uint16_t network, uint16_t ownId, uint32_t nowS) {
    if (!ready_ || !key) return false;
    for (uint8_t slot = 0; slot < SLOTS; ++slot) {
        if (!lengths_[slot]) continue;
        wici_link::Frame frame;
        if (!wici_link::decode(key, network, frames_[slot], lengths_[slot], frame) ||
            frame.type != wici_link::Type::DATA || !transitDestination(frame, ownId)) return false;
        const wici_seen::Lookup state = seen_.lookup(frames_[slot], lengths_[slot], nowS);
        if (state == wici_seen::Lookup::IO_ERROR) return false;
        // A conflicting envelope identity must not freeze unrelated slots.
        if (state == wici_seen::Lookup::CONFLICT) continue;
        if (state == wici_seen::Lookup::MATCH && !commit(slot, nullptr, 0)) return false;
    }
    return true;
}

bool Queue::remove(uint8_t slot, uint32_t nowS) {
    if (!pending(slot)) return false;
    if (!seen_.remember(frames_[slot], lengths_[slot], nowS)) {
        ready_ = false;  // The forwarded marker may have committed; reload before any admission.
        return false;
    }
    return commit(slot, nullptr, 0);
}

}  // namespace wici_relay
