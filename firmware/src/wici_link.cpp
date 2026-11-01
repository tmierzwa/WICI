// SPDX-License-Identifier: MIT
#include "wici_link.h"

#include <string.h>

#include "sha2.h"

namespace wici_link {
namespace {

constexpr uint8_t LABEL[] = {'W', 'I', 'C', 'I', ' ', 'l', 'i', 'n', 'k', ' ', 'v', '2'};
bool id(uint16_t value) { return value != 0 && value != BROADCAST; }
void put16(uint8_t* p, uint16_t n) { p[0] = static_cast<uint8_t>(n >> 8); p[1] = static_cast<uint8_t>(n); }
uint16_t get16(const uint8_t* p) { return static_cast<uint16_t>((p[0] << 8) | p[1]); }

bool valid(const Frame& f) {
    if (!id(f.network) || !id(f.source) || (!id(f.destination) && f.destination != BROADCAST) ||
        f.length > MAX_PAYLOAD || f.hops > f.ttl || f.ttl == 0 || f.ttl > 15 || (f.flags & ~3)) return false;
    switch (f.type) {
        case Type::DATA:
            return f.length >= 25 && (f.destination != BROADCAST || !(f.flags & ACKREQ));
        case Type::HACK:
            return id(f.destination) && f.flags == 0 && f.length == 0;
        case Type::BEACON:
            return f.destination == BROADCAST && f.flags == 0 && f.length == 137;
    }
    return false;
}

void mac(const uint8_t key[32], const uint8_t* data, size_t size, uint8_t out[32]) {
    sha2::Hmac h(key, 32);
    h.update(data, size);
    h.finish(out);
}

}  // namespace

bool deriveKey(const uint8_t ifac[16], uint16_t netId, uint8_t out[32]) {
    if (!ifac || !out || !id(netId)) return false;
    uint8_t salt[2], prk[32];
    put16(salt, netId);
    sha2::Hmac extract(salt, sizeof(salt));
    extract.update(ifac, 16);
    extract.finish(prk);
    sha2::Hmac expand(prk, sizeof(prk));
    expand.update(LABEL, sizeof(LABEL));
    const uint8_t block = 1;
    expand.update(&block, 1);
    expand.finish(out);
    memset(prk, 0, sizeof(prk));
    return true;
}

size_t encode(const uint8_t key[32], const Frame& frame, uint8_t* out, size_t capacity) {
    const size_t signature = frame.type == Type::DATA ? ORIGIN_SIGNATURE : 0;
    if (!key || !out || !valid(frame) || capacity < HEADER + frame.length + signature + TAG) return 0;
    uint8_t local[MAX_FRAME] = {};
    local[0] = static_cast<uint8_t>((2 << 6) | (static_cast<uint8_t>(frame.type) << 3) | frame.flags);
    put16(local + 1, frame.network);
    put16(local + 3, frame.source);
    put16(local + 5, frame.destination);
    local[7] = static_cast<uint8_t>((frame.hops << 4) | frame.ttl);
    put16(local + 8, frame.sequence);
    local[10] = 0;
    memcpy(local + HEADER, frame.payload, frame.length);
    if (signature) memcpy(local + HEADER + frame.length, frame.originSignature, signature);
    uint8_t digest[32];
    mac(key, local, HEADER + frame.length + signature, digest);
    memcpy(local + HEADER + frame.length + signature, digest, TAG);
    memcpy(out, local, HEADER + frame.length + signature + TAG);
    memset(digest, 0, sizeof(digest));
    return HEADER + frame.length + signature + TAG;
}

bool decode(const uint8_t key[32], uint16_t netId, const uint8_t* wire, size_t size, Frame& out) {
    out = Frame();
    if (!key || !wire || !id(netId) || size < HEADER + TAG || size > MAX_FRAME) return false;
    uint8_t digest[32], mismatch = 0;
    mac(key, wire, size - TAG, digest);
    for (size_t i = 0; i < TAG; ++i) mismatch |= digest[i] ^ wire[size - TAG + i];
    memset(digest, 0, sizeof(digest));
    if (mismatch) return false;
    Frame proposed;
    const uint8_t first = wire[0];
    if ((first >> 6) != 2 || (first & 4) || wire[10] != 0 || get16(wire + 1) != netId ||
        ((first >> 3) & 7) > static_cast<uint8_t>(Type::BEACON)) return false;
    proposed.type = static_cast<Type>((first >> 3) & 7);
    proposed.flags = first & 3;
    proposed.network = netId;
    proposed.source = get16(wire + 3);
    proposed.destination = get16(wire + 5);
    proposed.hops = wire[7] >> 4;
    proposed.ttl = wire[7] & 15;
    proposed.sequence = get16(wire + 8);
    const size_t signature = proposed.type == Type::DATA ? ORIGIN_SIGNATURE : 0;
    if (size < HEADER + signature + TAG) return false;
    proposed.length = size - HEADER - signature - TAG;
    if (proposed.length > MAX_PAYLOAD) return false;
    memcpy(proposed.payload, wire + HEADER, proposed.length);
    if (signature) memcpy(proposed.originSignature, wire + HEADER + proposed.length, signature);
    if (!valid(proposed)) return false;
    out = proposed;
    return true;
}

size_t forward(const uint8_t key[32], uint16_t netId, uint16_t ownId, uint16_t nextId,
               uint16_t seq, const uint8_t* wire, size_t size, uint8_t* out, size_t capacity) {
    if (!id(ownId) || (!id(nextId) && nextId != BROADCAST) ||
        nextId == ownId || !out || !wire) return 0;
    Frame frame;
    if (!decode(key, netId, wire, size, frame) || frame.type != Type::DATA ||
        (frame.destination != ownId && frame.destination != BROADCAST) ||
        frame.source == ownId || frame.source == nextId || frame.hops >= frame.ttl ||
        (frame.destination == BROADCAST && (!(frame.flags & DOWN) || frame.flags & ACKREQ)) ||
        (nextId == BROADCAST && !(frame.flags & DOWN))) return 0;
    frame.source = ownId;
    frame.destination = nextId;
    frame.sequence = seq;
    ++frame.hops;
    frame.flags = nextId == BROADCAST ? static_cast<uint8_t>(frame.flags & DOWN) : frame.flags;
    return encode(key, frame, out, capacity);
}

}  // namespace wici_link
