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

uint32_t reservedTxMs(size_t length) {
    return p1frame::fragmentCount(length) * airtimeMs(p1frame::CHUNK);
}

uint32_t reservedDebtMs(size_t length) {
    return reservedTxMs(length) * DEBT_FACTOR;
}

uint32_t channelMs(size_t length) {
    return reservedTxMs(length) * (1 + DEBT_FACTOR);
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

const uint8_t* pathRequestTarget(const uint8_t* raw, size_t length) {
    if (length < 2 || (raw[0] & 0x0F) != 0x08) return nullptr;   // DATA do PLAIN
    const size_t at = (raw[0] & 0x40) ? 2 + 16 + 16 + 1 : 2 + 16 + 1;
    return length >= at + 16 ? raw + at : nullptr;
}

const char* laneName(Lane lane) {
    switch (lane) {
        case Lane::CONTROL: return "control";
        case Lane::K0: return "k0";
        case Lane::K1: return "k1";
        case Lane::K2: return "k2";
        case Lane::ANNOUNCE: return "announce";
    }
    return "?";
}

const char* admitName(Admit admit) {
    switch (admit) {
        case Admit::QUEUED: return "queued";
        case Admit::HELD: return "held";
        case Admit::FULL: return "full";
        case Admit::ANNOUNCE_LIMIT: return "announce_limit";
        case Admit::TOO_LARGE: return "too_large";
        case Admit::K2_SLOT: return "k2_slot";
        case Admit::K2_POOL: return "k2_pool";
        case Admit::K2_DEST: return "k2_dest";
        case Admit::PATH_REQUEST_LIMIT: return "path_request_limit";
    }
    return "?";
}

namespace {

// Pierwszeństwo w kolejce: K0 i K1 razem.
uint8_t rank(Lane lane) {
    switch (lane) {
        case Lane::CONTROL: return 0;
        case Lane::K0:
        case Lane::K1: return 1;
        case Lane::K2: return 2;
        case Lane::ANNOUNCE: return 3;
    }
    return 3;
}

uint32_t percentOfWindow(uint32_t percent) { return WINDOW_MS / 100 * percent; }

}  // namespace

void Queue::Window::advance(uint32_t nowMs) {
    const uint32_t now = nowMs / 60000;
    const uint32_t elapsed = now - minute;   // także po zawinięciu millis(): całe okno od nowa
    for (uint32_t k = 1; k <= elapsed && k <= WINDOW_MIN; ++k) ms[(minute + k) % WINDOW_MIN] = 0;
    minute = now;
}

uint32_t Queue::Window::used(uint32_t nowMs) {
    advance(nowMs);
    uint32_t total = 0;
    for (uint32_t v : ms) total += v;
    return total;
}

void Queue::Window::add(uint32_t nowMs, uint32_t cost) {
    advance(nowMs);
    ms[minute % WINDOW_MIN] += cost;
}

Lane Queue::lane(const uint8_t* raw, size_t length, Hint hint) const {
    if (length < 2) return Lane::K0;
    const Kind kind = classify(raw, length);
    if (kind == Kind::CONTROL) return Lane::CONTROL;
    if (kind == Kind::ANNOUNCE) return pathResponse(raw, length) ? Lane::CONTROL : Lane::ANNOUNCE;
    if (hint == Hint::OWN || raw[1] == 0) return Lane::K0;
    if (hint == Hint::RECEIVER) return Lane::K1;
    const uint8_t* dest = destination(raw, length);
    if (receiverSet_ && dest && !memcmp(dest, receiver_, 16)) return Lane::K1;
    return Lane::K2;
}

bool Queue::push(Lane lane, const uint8_t* wire, size_t length) {
    for (Slot& s : slots_) {
        if (s.used) continue;
        s.used = true;
        s.lane = lane;
        s.order = order_++;
        s.length = static_cast<uint16_t>(length);
        memcpy(s.data, wire, length);
        ++count_;
        ++counters_.queued;
        return true;
    }
    return false;
}

Admit Queue::offer(const uint8_t* raw, size_t rawLength, const uint8_t* wire, size_t wireLength, uint32_t nowMs, Hint hint) {
    if (rawLength < 2 || wireLength == 0 || wireLength > MAX_WIRE || wireLength > p1frame::MAX_DATAGRAM) {
        ++counters_.tooLarge;
        return Admit::TOO_LARGE;
    }
    const Lane l = lane(raw, rawLength, hint);
    if (l == Lane::ANNOUNCE) return offerAnnounce(raw[1], destination(raw, rawLength), wire, wireLength, nowMs);
    if (full()) { ++counters_.full; return Admit::FULL; }
    // Zapytanie o trasę bez wskazania stosu: przekazywane (Reticulum nadaje je od nowa z hops = 0).
    if (hint == Hint::NONE && (raw[0] & 0x0F) == 0x08)
        return offerPathRequest(pathRequestTarget(raw, rawLength), wire, wireLength, nowMs);
    if (l == Lane::K2) return offerK2(destination(raw, rawLength), wire, wireLength, nowMs);
    push(l, wire, wireLength);
    return Admit::QUEUED;
}

bool Queue::poolAllows(uint32_t nowMs, size_t length) {
    return pool_.used(nowMs) + channelMs(length) <= percentOfWindow(POOL_PERCENT);
}

bool Queue::k0k1Waiting() const {
    for (size_t i = 0; i < QUEUE; ++i) {
        const Slot& s = slots_[i];
        if (s.used && (int)i != current_ && rank(s.lane) <= rank(Lane::K1)) return true;
    }
    return false;
}

Queue::DestWindow* Queue::findDest(const uint8_t* dest) {
    for (DestWindow& d : dests_)
        if (d.used && !memcmp(d.dest, dest, 16)) return &d;
    return nullptr;
}

Admit Queue::offerK2(const uint8_t* dest, const uint8_t* wire, size_t length, uint32_t nowMs) {
    if (count_ + 1 >= QUEUE) { ++counters_.k2Slot; return Admit::K2_SLOT; }
    if (!poolAllows(nowMs, length)) { ++counters_.k2Pool; return Admit::K2_POOL; }
    const uint32_t cost = channelMs(length);
    DestWindow* d = dest ? findDest(dest) : nullptr;
    if (d && k0k1Waiting() && d->window.used(nowMs) + cost > percentOfWindow(DEST_PERCENT)) {
        ++counters_.k2Dest;
        return Admit::K2_DEST;
    }
    if (dest && !d) {
        // Nowy cel: wolne miejsce albo cel najmniej używany w oknie.
        for (DestWindow& e : dests_) {
            if (!e.used) { d = &e; break; }
            if (!d || e.window.used(nowMs) < d->window.used(nowMs)) d = &e;
        }
        d->used = true;
        memcpy(d->dest, dest, 16);
        d->window = Window();
    }
    if (d) d->window.add(nowMs, cost);
    pool_.add(nowMs, cost);
    push(Lane::K2, wire, length);
    return Admit::QUEUED;
}

Admit Queue::offerPathRequest(const uint8_t* target, const uint8_t* wire, size_t length, uint32_t nowMs) {
    PathRequest* slot = nullptr;
    if (target) {
        for (PathRequest& r : recentRequests_) {
            if (!r.used || memcmp(r.target, target, 16)) continue;
            if (nowMs - r.atMs < PATH_REQUEST_GAP_MS) { ++counters_.pathRequestLimited; return Admit::PATH_REQUEST_LIMIT; }
            slot = &r;
        }
    }
    const uint32_t cost = channelMs(length);
    if (pathRequests_.used(nowMs) + cost > percentOfWindow(PATH_REQUEST_PERCENT)) {
        ++counters_.pathRequestLimited;
        return Admit::PATH_REQUEST_LIMIT;
    }
    if (target) {
        // Nowy cel: wolne miejsce albo najstarszy wpis.
        for (PathRequest& r : recentRequests_) {
            if (slot) break;
            if (!r.used) { slot = &r; break; }
        }
        if (!slot) {
            slot = &recentRequests_[0];
            for (PathRequest& r : recentRequests_)
                if (static_cast<int32_t>(r.atMs - slot->atMs) < 0) slot = &r;
        }
        slot->used = true;
        memcpy(slot->target, target, 16);
        slot->atMs = nowMs;
    }
    pathRequests_.add(nowMs, cost);
    push(Lane::CONTROL, wire, length);
    return Admit::QUEUED;
}

void Queue::releaseAnnounce(const uint8_t* wire, size_t length, uint32_t nowMs) {
    push(Lane::ANNOUNCE, wire, length);
    pool_.add(nowMs, channelMs(length));
    // Limit 2%: następne ogłoszenie po czasie TX tego ogłoszenia x 100 / 2.
    announceAllowedAt_ = nowMs + reservedTxMs(length) * 100 / ANNOUNCE_CAP_PERCENT;
    announceGate_ = true;
}

Admit Queue::offerAnnounce(uint8_t hops, const uint8_t* dest, const uint8_t* wire, size_t length, uint32_t nowMs) {
    // Od razu tylko bez oczekujących, po upływie limitu 2% i w puli 60%.
    if (held() == 0 && !full() && announceOpen(nowMs) && poolAllows(nowMs, length)) {
        releaseAnnounce(wire, length, nowMs);
        return Admit::QUEUED;
    }
    Held* slot = nullptr;
    for (Held& h : held_)
        if (h.used && dest && !memcmp(h.dest, dest, 16)) slot = &h;   // nowsze ogłoszenie tego samego celu
    for (Held& h : held_)
        if (!slot && !h.used) slot = &h;
    if (!slot) {
        // Pełna lista: ogłoszenie z mniejszą liczbą skoków zastępuje to z największą (najstarsze z nich).
        Held* worst = nullptr;
        for (Held& h : held_)
            if (!worst || h.hops > worst->hops || (h.hops == worst->hops && static_cast<int32_t>(h.sinceMs - worst->sinceMs) < 0)) worst = &h;
        ++counters_.announcesDropped;
        if (worst->hops <= hops) return Admit::ANNOUNCE_LIMIT;
        slot = worst;
    }
    slot->used = true;
    slot->hops = hops;
    if (dest) memcpy(slot->dest, dest, 16);
    else memset(slot->dest, 0, 16);
    slot->sinceMs = nowMs;
    slot->length = static_cast<uint16_t>(length);
    memcpy(slot->data, wire, length);
    ++counters_.announcesHeld;
    return Admit::HELD;
}

void Queue::setReceiver(const uint8_t dest[16]) {
    receiverSet_ = false;
    if (!dest) return;
    for (int i = 0; i < 16; ++i) receiverSet_ |= dest[i] != 0;
    memcpy(receiver_, dest, 16);
}

uint32_t Queue::poolUsedMs(uint32_t nowMs) { return pool_.used(nowMs); }

uint32_t Queue::pathRequestUsedMs(uint32_t nowMs) { return pathRequests_.used(nowMs); }

uint32_t Queue::destUsedMs(const uint8_t dest[16], uint32_t nowMs) {
    DestWindow* d = dest ? findDest(dest) : nullptr;
    return d ? d->window.used(nowMs) : 0;
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
    if (!poolAllows(nowMs, best->length)) return;
    releaseAnnounce(best->data, best->length, nowMs);
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
        if (rank(s.lane) < rank(b.lane) || (rank(s.lane) == rank(b.lane) && static_cast<int32_t>(s.order - b.order) < 0)) best = (int)i;
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

void Queue::drop() {
    for (size_t i = 0; i < QUEUE; ++i) {
        if (!slots_[i].used || static_cast<int>(i) == current_) continue;
        slots_[i].used = false;
        --count_;
        ++counters_.silenced;
    }
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
