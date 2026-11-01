// SPDX-License-Identifier: MIT
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "sha2.h"
#include "wici_link.h"

void print(const uint8_t* data, size_t size) {
    for (size_t i = 0; i < size; ++i) printf("%02x", data[i]);
    printf("\n");
}

int main() {
    uint8_t ifac[16], key[32], wire[255];
    for (uint8_t i = 0; i < 16; ++i) ifac[i] = i;
    assert(wici_link::deriveKey(ifac, 100, key));
    print(key, sizeof(key));
    wici_link::Frame frame;
    frame.type = wici_link::Type::DATA;
    frame.flags = wici_link::ACKREQ;
    frame.network = 100; frame.source = 4; frame.destination = 1;
    frame.hops = 0; frame.ttl = 7; frame.sequence = 0x1234;
    frame.length = 25;
    for (uint8_t i = 0; i < frame.length; ++i) frame.payload[i] = i;
    const size_t size = wici_link::encode(key, frame, wire, sizeof(wire));
    assert(size == 108);
    print(wire, size);
    wici_link::Frame decoded;
    assert(wici_link::decode(key, 100, wire, size, decoded));
    assert(decoded.source == 4 && decoded.sequence == 0x1234 && decoded.length == 25);
    uint8_t original[255];
    memcpy(original, wire, size);
    auto authenticatedBadHeader = [&](size_t offset, uint8_t changed) {
        uint8_t bad[255];
        memcpy(bad, original, size);
        bad[offset] = changed;
        uint8_t digest[32];
        sha2::Hmac h(key, sizeof(key));
        h.update(bad, size - wici_link::TAG);
        h.finish(digest);
        memcpy(bad + size - wici_link::TAG, digest, wici_link::TAG);
        assert(!wici_link::decode(key, 100, bad, size, decoded));
        assert(decoded.network == 0 && decoded.length == 0);
    };
    authenticatedBadHeader(0, 0x41);  // unknown version
    authenticatedBadHeader(0, 0x85);  // reserved flag
    authenticatedBadHeader(0, 0x89);  // HACK with DATA payload
    authenticatedBadHeader(4, 0);     // reserved link source
    authenticatedBadHeader(7, 0);     // zero TTL
    authenticatedBadHeader(10, 1);    // reserved opts
    wire[12] ^= 1;
    assert(!wici_link::decode(key, 100, wire, size, decoded) && decoded.source == 0);
    wire[12] ^= 1;
    assert(!wici_link::decode(key, 101, wire, size, decoded));
    frame.destination = wici_link::BROADCAST;
    assert(wici_link::encode(key, frame, wire, sizeof(wire)) == 0);  // broadcast never requests HACK
    frame.flags = 0;
    assert(wici_link::encode(key, frame, wire, sizeof(wire)) == size);
    uint8_t forwarded[255];
    assert(!wici_link::forward(key, 100, 2, 1, 9, wire, size, forwarded, sizeof(forwarded)));
    frame.destination = 2;
    frame.flags = wici_link::ACKREQ;
    assert(wici_link::encode(key, frame, wire, sizeof(wire)) == size);
    assert(wici_link::forward(key, 100, 2, 1, 9, wire, size, forwarded, sizeof(forwarded)) == size);
    assert(wici_link::decode(key, 100, forwarded, size, decoded));
    assert(decoded.source == 2 && decoded.destination == 1 && decoded.sequence == 9 &&
           decoded.hops == 1 && decoded.ttl == 7 && decoded.flags == wici_link::ACKREQ &&
           memcmp(decoded.payload, frame.payload, frame.length) == 0 &&
           memcmp(decoded.originSignature, frame.originSignature, wici_link::ORIGIN_SIGNATURE) == 0);
    assert(!wici_link::forward(key, 100, 2, 4, 9, wire, size, forwarded, sizeof(forwarded)));
    assert(!wici_link::forward(key, 100, 2, 1, 9, wire, size, forwarded, size - 1));
    frame.hops = 6; frame.ttl = 6;
    assert(wici_link::encode(key, frame, wire, sizeof(wire)) == size);
    assert(!wici_link::forward(key, 100, 2, 1, 9, wire, size, forwarded, sizeof(forwarded)));
    frame.hops = 0; frame.ttl = 7;
    frame.flags = wici_link::DOWN;
    frame.destination = wici_link::BROADCAST;
    assert(wici_link::encode(key, frame, wire, sizeof(wire)) == size);
    assert(wici_link::forward(key, 100, 2, wici_link::BROADCAST, 10, wire, size,
                              forwarded, sizeof(forwarded)) == size);
    assert(wici_link::decode(key, 100, forwarded, size, decoded));
    assert(decoded.source == 2 && decoded.destination == wici_link::BROADCAST &&
           decoded.flags == wici_link::DOWN && decoded.hops == 1);
}
