// SPDX-License-Identifier: MIT
#include "p1iface.h"

#include <string.h>

namespace p1iface {

uint32_t airtimeMs(size_t length) {
    const uint8_t count = p1frame::fragmentCount(length);
    uint32_t total = 0;
    size_t left = length;
    for (uint8_t i = 0; i < count; ++i) {
        const size_t chunk = left < p1frame::CHUNK ? left : p1frame::CHUNK;
        left -= chunk;
        const uint32_t frame = 1 + p1frame::HEADER_BYTES + chunk + 2;   // LEN, nagłówek, dane, CRC
        total += ((FRAME_OVERHEAD + frame) * 8 * 1000 + SYMBOL_RATE - 1) / SYMBOL_RATE + RAMP_MS;
    }
    return total;
}

uint32_t reservedDebtMs(size_t length) {
    return p1frame::fragmentCount(length) * airtimeMs(p1frame::CHUNK) * DEBT_FACTOR;
}

uint32_t declaredBitrate() {
    return p1frame::MAX_DATAGRAM * 8 * 1000 / (airtimeMs(p1frame::MAX_DATAGRAM) * (1 + DEBT_FACTOR));
}

Kind classify(const uint8_t* raw, size_t length) {
    if (length < 2) return Kind::DATA;
    const uint8_t packetType = raw[0] & 0x03;
    const uint8_t destinationType = (raw[0] >> 2) & 0x03;
    if (packetType == 0x03) return Kind::CONTROL;                          // PROOF
    if (packetType == 0x01) return Kind::ANNOUNCE;
    if (packetType == 0x00 && destinationType == 0x02) return Kind::CONTROL;  // DATA do PLAIN (zapytanie o trasę)
    return Kind::DATA;
}

const uint8_t* destination(const uint8_t* raw, size_t length) {
    const size_t at = (raw[0] & 0x40) ? 2 + 16 : 2;
    return length >= at + 16 ? raw + at : nullptr;
}

bool pathResponse(const uint8_t* raw, size_t length) {
    constexpr uint8_t PATH_RESPONSE = 0x0B;
    const size_t at = (raw[0] & 0x40) ? 2 + 16 + 16 : 2 + 16;
    return length > at && (raw[0] & 0x03) == 0x01 && raw[at] == PATH_RESPONSE;
}

const char* admitName(Admit admit) {
    switch (admit) {
        case Admit::QUEUED: return "queued";
        case Admit::HELD: return "held";
        case Admit::FULL: return "full";
        case Admit::ANNOUNCE_LIMIT: return "announce_limit";
        case Admit::TOO_LARGE: return "too_large";
        case Admit::OSP_RESERVE: return "osp_reserve";
    }
    return "?";
}

uint32_t Queue::costMs(size_t length) const {
    // announce_cap: czas TX przy przepływności deklarowanej podzielony przez udział 2%.
    return static_cast<uint32_t>(static_cast<uint64_t>(length) * 8 * 1000 * 100 / ANNOUNCE_CAP_PERCENT / declaredBitrate());
}

bool Queue::push(Kind kind, const uint8_t* wire, size_t length) {
    for (Slot& s : slots_) {
        if (s.used) continue;
        s.used = true;
        s.kind = kind;
        s.order = order_++;
        s.length = static_cast<uint16_t>(length);
        memcpy(s.data, wire, length);
        ++count_;
        ++counters_.queued;
        return true;
    }
    return false;
}

Admit Queue::offer(Kind kind, uint8_t hops, const uint8_t dest[16], const uint8_t* wire, size_t length, uint32_t nowMs) {
    if (length == 0 || length > MAX_WIRE || length > p1frame::MAX_DATAGRAM) { ++counters_.tooLarge; return Admit::TOO_LARGE; }
    if (kind == Kind::ANNOUNCE && hops > 0) {
        // Ogłoszenie przekazywane: od razu tylko bez oczekujących i po upływie limitu.
        if (held() == 0 && announceOpen(nowMs) && !full()) {
            push(kind, wire, length);
            announceAllowedAt_ = nowMs + costMs(length);
            announceGate_ = true;
            return Admit::QUEUED;
        }
        Held* slot = nullptr;
        for (Held& h : held_)
            if (h.used && dest && !memcmp(h.dest, dest, 16)) slot = &h;   // nowsze ogłoszenie tego samego celu
        for (Held& h : held_)
            if (!slot && !h.used) slot = &h;
        if (!slot) { ++counters_.announcesDropped; return Admit::ANNOUNCE_LIMIT; }
        slot->used = true;
        slot->hops = hops;
        if (dest) memcpy(slot->dest, dest, 16);
        slot->sinceMs = nowMs;
        slot->costMs = costMs(length);
        slot->length = static_cast<uint16_t>(length);
        memcpy(slot->data, wire, length);
        ++counters_.announcesHeld;
        return Admit::HELD;
    }
    if (full()) { ++counters_.full; return Admit::FULL; }
    if (kind == Kind::DATA && hops > 0 && ospSet_ && dest && memcmp(dest, osp_, 16) != 0) {
        // Dane przekazywane poza OSP: rezerwa 50% czasu kanału i ostatnie miejsce w kolejce dla OSP.
        const uint32_t cost = airtimeMs(length) + reservedDebtMs(length);
        const uint32_t budget = RESERVE_WINDOW_MIN * 60000 / 100 * OTHER_SHARE_PERCENT;
        if (count_ + 1 >= QUEUE || otherUsedMs(nowMs) + cost > budget) { ++counters_.reserved; return Admit::OSP_RESERVE; }
        window_[windowMinute_ % RESERVE_WINDOW_MIN] += cost;
    }
    push(kind, wire, length);
    return Admit::QUEUED;
}

void Queue::setOsp(const uint8_t dest[16]) {
    ospSet_ = false;
    if (!dest) return;
    for (int i = 0; i < 16; ++i) ospSet_ |= dest[i] != 0;
    memcpy(osp_, dest, 16);
}

void Queue::advanceWindow(uint32_t nowMs) {
    const uint32_t minute = nowMs / 60000;
    const uint32_t elapsed = minute - windowMinute_;   // także po zawinięciu millis(): całe okno od nowa
    for (uint32_t k = 1; k <= elapsed && k <= RESERVE_WINDOW_MIN; ++k) window_[(windowMinute_ + k) % RESERVE_WINDOW_MIN] = 0;
    windowMinute_ = minute;
}

uint32_t Queue::otherUsedMs(uint32_t nowMs) {
    advanceWindow(nowMs);
    uint32_t total = 0;
    for (uint32_t ms : window_) total += ms;
    return total;
}

size_t Queue::held() const {
    size_t n = 0;
    for (const Held& h : held_) n += h.used;
    return n;
}

void Queue::poll(uint32_t nowMs) {
    for (Held& h : held_) {
        if (h.used && nowMs - h.sinceMs > HELD_LIFE_MS) { h.used = false; ++counters_.announcesExpired; }
    }
    const bool open = announceOpen(nowMs);
    if (full() || held() == 0 || !open) return;
    // Najmniej skoków, potem najstarsze (Interface.process_announce_queue w Reticulum).
    Held* best = nullptr;
    for (Held& h : held_) {
        if (!h.used) continue;
        if (!best || h.hops < best->hops || (h.hops == best->hops && static_cast<int32_t>(h.sinceMs - best->sinceMs) < 0)) best = &h;
    }
    push(Kind::ANNOUNCE, best->data, best->length);
    announceAllowedAt_ = nowMs + best->costMs;
    announceGate_ = true;
    best->used = false;
}

bool Queue::announceOpen(uint32_t nowMs) {
    if (announceGate_ && static_cast<int32_t>(nowMs - announceAllowedAt_) >= 0) announceGate_ = false;
    return !announceGate_;
}

int Queue::head() const {
    int best = -1;
    for (size_t i = 0; i < QUEUE; ++i) {
        const Slot& s = slots_[i];
        if (!s.used) continue;
        if (best < 0) { best = (int)i; continue; }
        const Slot& b = slots_[best];
        if (s.kind < b.kind || (s.kind == b.kind && static_cast<int32_t>(s.order - b.order) < 0)) best = (int)i;
    }
    return best;
}

bool Queue::start(const uint8_t*& data, size_t& length) {
    if (current_ >= 0) return false;
    const int i = head();
    if (i < 0) return false;
    current_ = i;
    data = slots_[i].data;
    length = slots_[i].length;
    return true;
}

void Queue::finish(bool sent) {
    if (current_ < 0) return;
    slots_[current_].used = false;
    current_ = -1;
    --count_;
    if (sent) ++counters_.sent;
    else ++counters_.sendFailed;
}

uint32_t Queue::waitMs(uint32_t debtMs) const {
    uint32_t total = debtMs;
    for (const Slot& s : slots_)
        if (s.used) total += airtimeMs(s.length) + reservedDebtMs(s.length);
    return total;
}

uint32_t Queue::announceAllowedInMs(uint32_t nowMs) const {
    if (!announceGate_ || static_cast<int32_t>(nowMs - announceAllowedAt_) >= 0) return 0;
    return announceAllowedAt_ - nowMs;
}

void ifacMask(const uint8_t* raw, size_t length, const uint8_t* tag, size_t tagLength, const uint8_t* mask, uint8_t* wire) {
    wire[0] = static_cast<uint8_t>(((raw[0] | 0x80) ^ mask[0]) | 0x80);
    wire[1] = raw[1] ^ mask[1];
    memcpy(wire + 2, tag, tagLength);
    for (size_t i = 2; i < length; ++i) wire[i + tagLength] = raw[i] ^ mask[i + tagLength];
}

bool ifacPresent(const uint8_t* wire, size_t length, size_t tagLength) {
    return length > 2 + tagLength && (wire[0] & 0x80);
}

void ifacUnmask(const uint8_t* wire, size_t length, size_t tagLength, const uint8_t* mask, uint8_t* raw) {
    raw[0] = static_cast<uint8_t>((wire[0] ^ mask[0]) & 0x7F);
    raw[1] = wire[1] ^ mask[1];
    for (size_t i = 2 + tagLength; i < length; ++i) raw[i - tagLength] = wire[i] ^ mask[i];
}

}  // namespace p1iface
