// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include "wici_relay.h"

struct Memory : journal::Storage {
    uint8_t bytes[wici_seen::BASE + wici_seen::SLOTS * wici_seen::SLOT_BYTES] = {};
    int writesLeft = -1;
    bool read(uint32_t at, uint8_t* out, size_t count) override {
        if (at > sizeof(bytes) || count > sizeof(bytes) - at) return false;
        memcpy(out, bytes + at, count);
        return true;
    }
    bool write(uint32_t at, const uint8_t* in, size_t count) override {
        if (writesLeft == 0 || at > sizeof(bytes) || count > sizeof(bytes) - at) return false;
        if (writesLeft > 0) --writesLeft;
        memcpy(bytes + at, in, count);
        return true;
    }
};

int main() {
    static Memory memory;
    uint8_t ifac[16] = {}, key[32];
    for (uint8_t i = 0; i < sizeof(ifac); ++i) ifac[i] = i;
    assert(wici_link::deriveKey(ifac, 100, key));
    wici_link::Frame frame;
    frame.type = wici_link::Type::DATA;
    frame.flags = wici_link::ACKREQ;
    frame.network = 100;
    frame.source = 4;
    frame.destination = 2;
    frame.ttl = 7;
    frame.length = 25;
    frame.payload[0] = 0x40;  // WICI envelope v1, whole SA1
    frame.payload[1] = 0; frame.payload[2] = 4;
    frame.payload[3] = 0; frame.payload[4] = 1;
    uint8_t wire[wici_link::MAX_FRAME], saved[wici_link::MAX_FRAME];
    size_t n = wici_link::encode(key, frame, wire, sizeof(wire)), length = 0;
    assert(n == 44);
    wici_relay::Queue queue(memory);
    assert(queue.begin());
    assert(queue.admit(key, 100, 2, wire, n, 100) == wici_relay::Admission::STORED);
    assert(queue.admit(key, 100, 2, wire, n, 100) == wici_relay::Admission::DUPLICATE);
    uint8_t otherIfac[16], otherKey[32], otherWire[wici_link::MAX_FRAME];
    memset(otherIfac, 0xA5, sizeof(otherIfac));
    assert(wici_link::deriveKey(otherIfac, 100, otherKey));
    frame.sequence = 8;
    assert(wici_link::encode(otherKey, frame, otherWire, sizeof(otherWire)) == n);
    assert(queue.admit(otherKey, 100, 2, otherWire, n, 100) == wici_relay::Admission::REJECTED);
    frame.sequence = 0;
    assert(queue.read(key, 100, 2, 0, 100, saved, sizeof(saved), length) && length == n && memcmp(saved, wire, n) == 0);
    const size_t savedLength = length;
    assert(!queue.read(key, 101, 2, 0, 100, saved, sizeof(saved), length));
    frame.sequence = 9;
    n = wici_link::encode(key, frame, wire, sizeof(wire));
    assert(queue.admit(key, 100, 2, wire, n, 100) == wici_relay::Admission::DUPLICATE);
    frame.payload[24] ^= 1;
    n = wici_link::encode(key, frame, wire, sizeof(wire));
    assert(queue.admit(key, 100, 2, wire, n, 100) == wici_relay::Admission::REJECTED);
    frame.payload[24] ^= 1;
    n = wici_link::encode(key, frame, wire, sizeof(wire));
    wire[n - 1] ^= 1;
    assert(queue.admit(key, 100, 2, wire, n, 100) == wici_relay::Admission::REJECTED);
    wire[n - 1] ^= 1;

    wici_relay::Queue restarted(memory);
    assert(restarted.begin() && restarted.pending(0));
    assert(restarted.admit(key, 100, 2, wire, n, 100) == wici_relay::Admission::DUPLICATE);
    for (uint8_t i = 1; i < 4; ++i) {
        frame.sequence = i;
        frame.payload[8] = i;
        n = wici_link::encode(key, frame, wire, sizeof(wire));
        assert(restarted.admit(key, 100, 2, wire, n, 100) == wici_relay::Admission::STORED);
    }
    frame.sequence = 4;
    frame.payload[8] = 4;
    n = wici_link::encode(key, frame, wire, sizeof(wire));
    assert(restarted.admit(key, 100, 2, wire, n, 100) == wici_relay::Admission::FULL);
    memory.writesLeft = 1;
    assert(!restarted.remove(0, 101));
    assert(!restarted.pending(0));  // No more admissions until the FRAM copies are reloaded.
    assert(restarted.admit(key, 100, 2, wire, n, 101) == wici_relay::Admission::REJECTED);
    memory.writesLeft = -1;
    wici_relay::Queue afterCut(memory);
    assert(afterCut.begin() && afterCut.pending(0));
    memory.writesLeft = 3;
    assert(!afterCut.remove(0, 102));  // seen committed, tombstone interrupted
    memory.writesLeft = -1;
    wici_relay::Queue afterSeen(memory);
    assert(afterSeen.begin() && afterSeen.pending(0));
    assert(!afterSeen.read(key, 100, 2, 0, 103, wire, sizeof(wire), length));
    assert(afterSeen.finishForwarded(key, 100, 2, 103));
    assert(!afterSeen.pending(0));
    wici_relay::Queue afterRemove(memory);
    assert(afterRemove.begin() && !afterRemove.pending(0));
    assert(afterRemove.admit(key, 100, 2, saved, savedLength, 103) == wici_relay::Admission::DUPLICATE);
    assert(afterRemove.admit(key, 100, 2, wire, n, 103) == wici_relay::Admission::STORED);
    assert(afterRemove.remove(0, 104));
    assert(afterRemove.admit(key, 100, 2, saved, savedLength, 223) == wici_relay::Admission::STORED);
    // A committed record with a damaged CRC must not be accepted after restart.
    memory.bytes[wici_relay::BASE + 0 * wici_relay::COPY_BYTES + 25] ^= 1;
    wici_relay::Queue corrupt(memory);
    assert(!corrupt.begin());
}
