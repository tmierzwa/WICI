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
    assert(queue.begin(key, 100, 2));
    assert(queue.admit(wire, n, 100) == wici_relay::Admission::STORED);
    assert(queue.admit(wire, n, 100) == wici_relay::Admission::DUPLICATE);
    uint8_t otherIfac[16], otherKey[32], otherWire[wici_link::MAX_FRAME];
    memset(otherIfac, 0xA5, sizeof(otherIfac));
    assert(wici_link::deriveKey(otherIfac, 100, otherKey));
    frame.sequence = 8;
    assert(wici_link::encode(otherKey, frame, otherWire, sizeof(otherWire)) == n);
    assert(queue.admit(otherWire, n, 100) == wici_relay::Admission::REJECTED);
    frame.sequence = 0;
    assert(queue.read(0, 100, saved, sizeof(saved), length) && length == n && memcmp(saved, wire, n) == 0);
    const size_t savedLength = length;
        frame.sequence = 9;
    n = wici_link::encode(key, frame, wire, sizeof(wire));
    assert(queue.admit(wire, n, 100) == wici_relay::Admission::DUPLICATE);
    frame.payload[24] ^= 1;
    n = wici_link::encode(key, frame, wire, sizeof(wire));
    assert(queue.admit(wire, n, 100) == wici_relay::Admission::REJECTED);
    frame.payload[24] ^= 1;
    n = wici_link::encode(key, frame, wire, sizeof(wire));
    wire[n - 1] ^= 1;
    assert(queue.admit(wire, n, 100) == wici_relay::Admission::REJECTED);
    wire[n - 1] ^= 1;

    wici_relay::Queue restarted(memory);
    assert(restarted.begin(key, 100, 2) && restarted.pending(0));
    assert(restarted.admit(wire, n, 100) == wici_relay::Admission::DUPLICATE);
    // K2 holds at most two slots; the other two are K1 only, one per neighbour.
    frame.sequence = 1; frame.payload[8] = 1;
    n = wici_link::encode(key, frame, wire, sizeof(wire));
    assert(restarted.admit(wire, n, 100) == wici_relay::Admission::STORED);
    frame.sequence = 2; frame.payload[8] = 2;
    n = wici_link::encode(key, frame, wire, sizeof(wire));
    assert(restarted.admit(wire, n, 100) == wici_relay::Admission::FULL);
    assert(restarted.admit(wire, n, 100, 5) == wici_relay::Admission::REJECTED);  // K1 only for l_src
    assert(restarted.admit(wire, n, 100, 4) == wici_relay::Admission::STORED);
    assert(restarted.k1Neighbor(2) == 4);
    frame.sequence = 3; frame.payload[8] = 3;
    n = wici_link::encode(key, frame, wire, sizeof(wire));
    assert(restarted.admit(wire, n, 100, 4) == wici_relay::Admission::FULL);  // one K1 slot per neighbour
    frame.source = 6;
    n = wici_link::encode(key, frame, wire, sizeof(wire));
    assert(restarted.admit(wire, n, 100, 6) == wici_relay::Admission::STORED);
    frame.source = 4;
    frame.sequence = 4;
    frame.payload[8] = 4;
    n = wici_link::encode(key, frame, wire, sizeof(wire));
    assert(restarted.admit(wire, n, 100) == wici_relay::Admission::FULL);
    memory.writesLeft = 1;
    assert(!restarted.remove(0, 101));
    assert(!restarted.pending(0));  // No more admissions until the FRAM copies are reloaded.
    assert(restarted.admit(wire, n, 101) == wici_relay::Admission::REJECTED);
    memory.writesLeft = -1;
    wici_relay::Queue afterCut(memory);
    assert(afterCut.begin(key, 100, 2) && afterCut.pending(0));
    memory.writesLeft = 3;
    assert(!afterCut.remove(0, 102));  // seen committed, tombstone interrupted
    memory.writesLeft = -1;
    wici_relay::Queue afterSeen(memory);
    assert(afterSeen.begin(key, 100, 2) && afterSeen.pending(0));
    assert(!afterSeen.read(0, 103, wire, sizeof(wire), length));
    assert(afterSeen.settle(103));
    assert(!afterSeen.pending(0));
    wici_relay::Queue afterRemove(memory);
    assert(afterRemove.begin(key, 100, 2) && !afterRemove.pending(0));
    assert(afterRemove.admit(saved, savedLength, 103) == wici_relay::Admission::FORWARDED);
    // Rewriting the hop sequence and MAC cannot make the same envelope new.
    frame.sequence = 200;
    frame.payload[8] = 0;
    size_t replayLength = wici_link::encode(key, frame, wire, sizeof(wire));
    assert(replayLength == savedLength);
    assert(afterRemove.admit(wire, replayLength, 103) == wici_relay::Admission::FORWARDED);
    frame.payload[8] = 4;
    n = wici_link::encode(key, frame, wire, sizeof(wire));
    assert(afterRemove.admit(wire, n, 103) == wici_relay::Admission::STORED);
    assert(afterRemove.remove(0, 104));
    assert(afterRemove.admit(saved, savedLength, 223) == wici_relay::Admission::FORWARDED);
    // A frame without a next-hop HACK must eventually free its durable slot.
    static Memory expiryMemory;
    wici_relay::Queue expiring(expiryMemory);
    assert(expiring.begin(key, 100, 2));
    assert(expiring.admit(saved, savedLength, 100, 4) == wici_relay::Admission::STORED);
    assert(expiring.settle(100 + wici_relay::MAX_HOLD_S - 1) && expiring.pending(0));
    assert(expiring.settle(100 + wici_relay::MAX_HOLD_S) && !expiring.pending(0));
    wici_relay::Queue expiredAfterRestart(expiryMemory);
    assert(expiredAfterRestart.begin(key, 100, 2) && !expiredAfterRestart.pending(0));
    assert(expiredAfterRestart.admit(saved, savedLength, 100 + wici_relay::MAX_HOLD_S) ==
           wici_relay::Admission::FORWARDED);
    // The K1 neighbour is durable: no re-verification after restart.
    static Memory verifiedMemory;
    wici_relay::Queue verified(verifiedMemory);
    assert(verified.begin(key, 100, 2));
    assert(verified.admit(saved, savedLength, 100, 4) == wici_relay::Admission::STORED);
    assert(verified.k1Neighbor(0) == 4);
    wici_relay::Queue afterBoot(verifiedMemory);
    assert(afterBoot.begin(key, 100, 2) && afterBoot.k1Neighbor(0) == 4);
    // Reprovisioning (new link key or station number) drops items that can
    // never be sent again instead of wedging the relay.
    uint8_t newIfac[16], newKey[32];
    memset(newIfac, 0x5A, sizeof(newIfac));
    assert(wici_link::deriveKey(newIfac, 100, newKey));
    wici_relay::Queue renumbered(verifiedMemory);
    assert(renumbered.begin(key, 100, 3) && !renumbered.pending(0));
    static Memory rekeyMemory;
    wici_relay::Queue oldKey(rekeyMemory);
    assert(oldKey.begin(key, 100, 2));
    assert(oldKey.admit(saved, savedLength, 100) == wici_relay::Admission::STORED);
    wici_relay::Queue rekeyed(rekeyMemory);
    assert(rekeyed.begin(newKey, 100, 2) && !rekeyed.pending(0));
    frame.sequence = 300;
    n = wici_link::encode(newKey, frame, wire, sizeof(wire));
    assert(rekeyed.admit(wire, n, 200) == wici_relay::Admission::STORED);
    // A committed record with a damaged CRC must not be accepted after restart.
    memory.bytes[wici_relay::BASE + 0 * wici_relay::COPY_BYTES + 25] ^= 1;
    wici_relay::Queue corrupt(memory);
    assert(!corrupt.begin(key, 100, 2));
}
