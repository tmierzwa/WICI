// SPDX-License-Identifier: MIT
#include "p1frame.h"

#include <string.h>

#include "crc16.h"

namespace p1frame {

const char* parseName(Parse result) {
    switch (result) {
        case Parse::OK: return "ok";
        case Parse::BAD_LENGTH: return "length";
        case Parse::BAD_CRC: return "crc";
        case Parse::BAD_VERSION: return "version";
        case Parse::BAD_COUNT: return "count";
        case Parse::BAD_CHUNK: return "chunk";
    }
    return "?";
}

const char* outcomeName(Outcome outcome) {
    switch (outcome) {
        case Outcome::STORED: return "stored";
        case Outcome::COMPLETE: return "complete";
        case Outcome::DUPLICATE: return "duplicate";
        case Outcome::CONFLICT: return "conflict";
        case Outcome::LATE_DUPLICATE: return "late";
    }
    return "?";
}

uint8_t fragmentCount(size_t length) {
    if (length < 1 || length > MAX_DATAGRAM) return 0;
    return static_cast<uint8_t>((length + CHUNK - 1) / CHUNK);
}

size_t buildFrame(const uint8_t* data, size_t length, const uint8_t id[ID_BYTES], uint8_t index, uint8_t out[MAX_FRAME]) {
    const uint8_t count = fragmentCount(length);
    if (count == 0 || index >= count) return 0;
    const size_t offset = static_cast<size_t>(index) * CHUNK;
    const size_t chunk = length - offset < CHUNK ? length - offset : CHUNK;
    const size_t body = HEADER_BYTES + chunk;
    out[0] = static_cast<uint8_t>(body + 2);  // LEN: BODY i CRC (F79)
    out[1] = 1;                                // wersja ramki
    out[2] = 0;                                // znaczniki
    memcpy(out + 3, id, ID_BYTES);
    out[11] = index;
    out[12] = count;
    out[13] = static_cast<uint8_t>(length >> 8);
    out[14] = static_cast<uint8_t>(length & 0xFF);
    memcpy(out + 15, data + offset, chunk);
    const uint16_t crc = p1::crc16(out, 1 + body);  // LEN i BODY
    out[1 + body] = static_cast<uint8_t>(crc >> 8);
    out[2 + body] = static_cast<uint8_t>(crc & 0xFF);
    return body + 3;
}

Parse parseFrame(const uint8_t* frame, size_t length, Fragment& fragment) {
    if (length < MIN_LEN + 1 || length > MAX_FRAME) return Parse::BAD_LENGTH;
    const uint8_t len = frame[0];
    if (len < MIN_LEN || len > MAX_LEN || length != static_cast<size_t>(len) + 1) return Parse::BAD_LENGTH;
    const uint16_t crc = static_cast<uint16_t>((frame[length - 2] << 8) | frame[length - 1]);
    if (p1::crc16(frame, length - 2) != crc) return Parse::BAD_CRC;
    if (frame[1] != 1 || frame[2] != 0) return Parse::BAD_VERSION;
    memcpy(fragment.id, frame + 3, ID_BYTES);
    fragment.index = frame[11];
    fragment.count = frame[12];
    fragment.total = static_cast<uint16_t>((frame[13] << 8) | frame[14]);
    if (fragment.total < 1 || fragment.total > MAX_DATAGRAM) return Parse::BAD_VERSION;
    if (fragment.count != fragmentCount(fragment.total) || fragment.index >= fragment.count) return Parse::BAD_COUNT;
    fragment.chunk = frame + 1 + HEADER_BYTES;
    fragment.chunkLength = static_cast<uint8_t>(length - 3 - HEADER_BYTES);
    const size_t remaining = fragment.total - static_cast<size_t>(fragment.index) * CHUNK;
    const size_t expected = remaining < CHUNK ? remaining : CHUNK;
    if (fragment.chunkLength != expected) return Parse::BAD_CHUNK;
    return Parse::OK;
}

Assembler::Attempt* Assembler::find(const uint8_t id[ID_BYTES]) {
    for (Attempt& a : attempts_) {
        if (a.used && !memcmp(a.id, id, ID_BYTES)) return &a;
    }
    return nullptr;
}

Assembler::Attempt* Assembler::allocate(uint32_t nowMs) {
    Attempt* victim = nullptr;
    for (Attempt& a : attempts_) {
        if (!a.used) {
            a = Attempt();
            a.used = true;
            a.startedMs = nowMs;
            return &a;
        }
        // Przepełnienie: odpada próba z najmniejszą liczbą fragmentów, przy równej najstarsza.
        if (!victim || a.received < victim->received ||
            (a.received == victim->received && static_cast<int32_t>(a.startedMs - victim->startedMs) < 0)) {
            victim = &a;
        }
    }
    ++stats_.evicted;
    *victim = Attempt();
    victim->used = true;
    victim->startedMs = nowMs;
    return victim;
}

bool Assembler::recent(const uint8_t id[ID_BYTES]) const {
    for (size_t i = 0; i < RECENT_IDS; ++i) {
        if (recentUsed_[i] && !memcmp(recentIds_[i], id, ID_BYTES)) return true;
    }
    return false;
}

void Assembler::remember(const uint8_t id[ID_BYTES]) {
    memcpy(recentIds_[recentNext_], id, ID_BYTES);
    recentUsed_[recentNext_] = true;
    recentNext_ = (recentNext_ + 1) % RECENT_IDS;
}

size_t Assembler::active() const {
    size_t n = 0;
    for (const Attempt& a : attempts_) n += a.used ? 1 : 0;
    return n;
}

void Assembler::expire(uint32_t nowMs) {
    for (Attempt& a : attempts_) {
        if (a.used && nowMs - a.startedMs >= ATTEMPT_MS) {
            a.used = false;
            ++stats_.expired;
        }
    }
}

Outcome Assembler::push(const Fragment& f, uint32_t nowMs) {
    if (recent(f.id)) {
        ++stats_.late;
        return Outcome::LATE_DUPLICATE;
    }
    Attempt* a = find(f.id);
    if (a && (a->count != f.count || a->total != f.total)) {
        a->used = false;  // zmiana liczby fragmentów albo długości usuwa próbę
        ++stats_.conflicts;
        return Outcome::CONFLICT;
    }
    const size_t offset = static_cast<size_t>(f.index) * CHUNK;
    if (a && (a->mask & (1u << f.index))) {
        if (!memcmp(a->data + offset, f.chunk, f.chunkLength)) {
            ++stats_.duplicates;
            return Outcome::DUPLICATE;
        }
        a->used = false;  // inna treść tego samego fragmentu
        ++stats_.conflicts;
        return Outcome::CONFLICT;
    }
    if (!a) {
        a = allocate(nowMs);
        memcpy(a->id, f.id, ID_BYTES);
        a->count = f.count;
        a->total = f.total;
    }
    memcpy(a->data + offset, f.chunk, f.chunkLength);
    a->mask |= static_cast<uint8_t>(1u << f.index);
    ++a->received;
    ++stats_.stored;
    if (a->received < a->count) return Outcome::STORED;
    memcpy(completed_, a->data, a->total);
    completedLength_ = a->total;
    memcpy(completedId_, a->id, ID_BYTES);
    remember(a->id);
    a->used = false;
    ++stats_.completed;
    return Outcome::COMPLETE;
}

}  // namespace p1frame
