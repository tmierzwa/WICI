// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include "wici_hop.h"

struct Memory : journal::Storage {
    uint8_t bytes[0x048000] = {};
    bool read(uint32_t at, uint8_t* out, size_t count) override {
        if (at > sizeof(bytes) || count > sizeof(bytes) - at) return false;
        memcpy(out, bytes + at, count); return true;
    }
    bool write(uint32_t at, const uint8_t* in, size_t count) override {
        if (at > sizeof(bytes) || count > sizeof(bytes) - at) return false;
        memcpy(bytes + at, in, count); return true;
    }
};

int main() {
    static Memory memory;
    uint8_t ifac[16] = {}, key[32], wire[255], hack[255];
    for (uint8_t i = 0; i < 16; ++i) ifac[i] = i;
    assert(wici_link::deriveKey(ifac, 100, key));
    wici_link::Frame incoming;
    incoming.type = wici_link::Type::DATA;
    incoming.flags = wici_link::ACKREQ;
    incoming.network = 100; incoming.source = 4; incoming.destination = 2;
    incoming.sequence = 41; incoming.ttl = 7; incoming.length = 25;
    incoming.payload[0] = 0x40;
    incoming.payload[2] = 4; incoming.payload[4] = 1;
    const size_t length = wici_link::encode(key, incoming, wire, sizeof(wire));
    assert(length == 44);
    const uint16_t rootReceiver[2] = {1, 90};
    wici_hop::Relay relay(memory, {100, 2, 1, 1, 0}, ifac, false, rootReceiver);
    assert(relay.begin());
    size_t hackLength = 0;
    assert(relay.receiveData(wire, length, 100, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(hackLength == 19);
    wici_link::Frame parsed;
    assert(wici_link::decode(key, 100, hack, hackLength, parsed));
    assert(parsed.type == wici_link::Type::HACK && parsed.destination == 4 && parsed.sequence == 41);

    // Crash after HACK: the queue remains and a new link sequence is reserved.
    wici_hop::Relay resumed(memory, {100, 2, 1, 1, 0}, ifac, false, rootReceiver);
    assert(resumed.begin());
    resumed.learnPending(101);
    assert(resumed.routes().down(4) == 4);
    wici_link::Frame viaOther = incoming;
    viaOther.source = 5; viaOther.sequence = 45;
    uint8_t duplicate[255];
    assert(wici_link::encode(key, viaOther, duplicate, sizeof(duplicate)) == length);
    assert(resumed.receiveData(duplicate, length, 101, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    resumed.learnPending(101);
    assert(resumed.routes().down(4) == 4);  // duplicate hop header cannot redirect a learned route
    assert(resumed.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 101));
    assert(resumed.prepare(101));
    size_t outLength = 0;
    const uint8_t* out = resumed.outgoing(outLength);
    assert(out && outLength == length && wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.source == 2 && parsed.destination == 1 && parsed.hops == 1 &&
           memcmp(parsed.payload, incoming.payload, incoming.length) == 0);
    const uint16_t seq = parsed.sequence;
    assert(resumed.transmitted(true, 102));
    wici_link::Frame reply;
    reply.type = wici_link::Type::HACK;
    reply.network = 100; reply.source = 4; reply.destination = 2;
    reply.sequence = seq; reply.ttl = 1;
    hackLength = wici_link::encode(key, reply, hack, sizeof(hack));
    assert(!resumed.receiveHack(hack, hackLength, 103));
    assert(resumed.timeout(103));
    assert(resumed.outgoing(outLength) == out && outLength == length);
    assert(resumed.transmitted(true, 104));
    reply.source = 1;
    hackLength = wici_link::encode(key, reply, hack, sizeof(hack));
    assert(resumed.receiveHack(hack, hackLength, 105));
    assert(!resumed.active());
    wici_hop::Relay after(memory, {100, 2, 1, 1, 0}, ifac, false, rootReceiver);
    assert(after.begin());
    assert(after.receiveData(wire, length, 106, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);  // late repeat is HACKed, never queued again
    assert(after.receiveData(duplicate, length, 107, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::IGNORED);  // a re-MACed replay cannot buy a HACK every second
    assert(after.receiveData(duplicate, length, 111, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(!after.prepare(106));

    incoming.sequence = 42;
    incoming.payload[8] = 2;
    const size_t lateLength = wici_link::encode(key, incoming, wire, sizeof(wire));
    assert(after.receiveData(wire, lateLength, 106, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(after.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 106));
    assert(after.prepare(106));
    out = after.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed));
    assert(after.transmitted(true, 106) && after.timeout(107));
    reply.source = 1; reply.sequence = parsed.sequence;
    hackLength = wici_link::encode(key, reply, hack, sizeof(hack));
    assert(after.receiveHack(hack, hackLength, 107));  // HACK after timeout, before retry TX

    wici_link::Frame down = incoming;
    down.flags = wici_link::ACKREQ | wici_link::DOWN;
    down.source = 1; down.destination = 2; down.sequence = 50;
    down.payload[2] = 1; down.payload[4] = 4;
    const size_t downLength = wici_link::encode(key, down, wire, sizeof(wire));
    assert(after.receiveData(wire, downLength, 107, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(after.routes().down(4) == 4 && after.prepare(107));
    out = after.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.destination == 4 && parsed.flags == (wici_link::ACKREQ | wici_link::DOWN));
    assert(after.transmitted(true, 108));
    reply.source = 4; reply.sequence = parsed.sequence;
    hackLength = wici_link::encode(key, reply, hack, sizeof(hack));
    assert(after.receiveHack(hack, hackLength, 109));

    // A silence-exempt unicast report travels through a relay once, with no
    // hop acknowledgment and no false retry responsibility at that relay.
    static Memory exceptionMemory;
    wici_hop::Relay exceptionRelay(exceptionMemory, {100, 2, 1, 1, 0}, ifac);
    assert(exceptionRelay.begin());
    wici_link::Frame exception = incoming;
    exception.flags = 0; exception.sequence = 60; exception.payload[8] = 3;
    const size_t exceptionLength = wici_link::encode(key, exception, wire, sizeof(wire));
    assert(exceptionRelay.receiveData(wire, exceptionLength, 109, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::STORED_NO_HACK && hackLength == 0);
    assert(exceptionRelay.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 109));
    assert(exceptionRelay.prepare(109));
    out = exceptionRelay.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.destination == 1 && parsed.flags == 0);
    assert(exceptionRelay.transmitted(true, 110) && !exceptionRelay.active());
    assert(!exceptionRelay.prepare(110));
    assert(wici_link::encode(key, down, wire, sizeof(wire)) == downLength);

    static Memory defaultMemory;
    wici_hop::Relay defaultSafe(defaultMemory, {100, 2, 1, 1, 0}, ifac);
    assert(defaultSafe.begin());
    assert(defaultSafe.receiveData(wire, downLength, 110, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(!defaultSafe.prepare(110));  // flood requires explicit SA1 retry guarantee

    static Memory noRouteMemory;
    wici_hop::Relay noRoute(noRouteMemory, {100, 2, 1, 1, 0}, ifac, true);
    assert(noRoute.begin());
    assert(noRoute.receiveData(wire, downLength, 110, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(noRoute.prepare(110));
    out = noRoute.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.destination == wici_link::BROADCAST && parsed.flags == wici_link::DOWN);
    assert(noRoute.transmitted(true, 111) && !noRoute.active());
    wici_hop::Relay noRouteAgain(noRouteMemory, {100, 2, 1, 1, 0}, ifac, true);
    assert(noRouteAgain.begin() && !noRouteAgain.prepare(112));

    static Memory noTxMemory;
    wici_hop::Relay noTx(noTxMemory, {100, 2, 1, 1, 0}, ifac, true);
    assert(noTx.begin());
    assert(noTx.receiveData(wire, downLength, 110, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(noTx.prepare(110));  // flood identity durable before radio TX
    wici_hop::Relay cutBeforeTx(noTxMemory, {100, 2, 1, 1, 0}, ifac, true);
    assert(cutBeforeTx.begin());
    assert(!cutBeforeTx.prepare(111));  // at most once; SA1 sender will retry with a new ctr

    static Memory rebroadcastMemory;
    wici_hop::Relay rebroadcast(rebroadcastMemory, {100, 2, 1, 1, 0}, ifac, true);
    assert(rebroadcast.begin());
    down.destination = wici_link::BROADCAST;
    down.flags = wici_link::DOWN;
    const size_t broadcastLength = wici_link::encode(key, down, wire, sizeof(wire));
    assert(rebroadcast.receiveData(wire, broadcastLength, 120, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::STORED_NO_HACK && hackLength == 0);
    assert(rebroadcast.prepare(120));
    out = rebroadcast.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.destination == wici_link::BROADCAST && parsed.hops == 1);
    assert(rebroadcast.transmitted(true, 121));
    assert(rebroadcast.receiveData(wire, broadcastLength, 122, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::IGNORED);
    down.source = 3; down.sequence = 99; down.hops = 2;
    const size_t loopLength = wici_link::encode(key, down, wire, sizeof(wire));
    assert(loopLength == broadcastLength);
    assert(rebroadcast.receiveData(wire, loopLength, 123, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::IGNORED);  // changed hop header cannot restart a flood loop

    // K1 is unicast transit to or from a receiver identity, decided at once
    // and HACKed after durable admission. One K1 slot per neighbour (l_src,
    // authenticated by the hop tag); further frames of that neighbour are K2.
    static Memory priorityMemory;
    const uint16_t receivers[2] = {90, 91};
    wici_hop::Relay priorityRelay(priorityMemory, {100, 2, 1, 1, 0}, ifac, false, receivers);
    assert(priorityRelay.begin());
    wici_link::Frame traffic = incoming;
    traffic.source = 4;
    traffic.flags = wici_link::ACKREQ;
    traffic.payload[2] = 4; traffic.payload[4] = 90;
    size_t n = 0;
    for (uint8_t i = 0; i < 3; ++i) {  // K1, then two K2
        traffic.sequence = static_cast<uint16_t>(70 + i);
        traffic.payload[8] = static_cast<uint8_t>(10 + i);
        n = wici_link::encode(key, traffic, wire, sizeof(wire));
        assert(priorityRelay.receiveData(wire, n, 130, hack, sizeof(hack), hackLength) ==
               wici_hop::Receipt::HACK_READY);
    }
    traffic.sequence = 73; traffic.payload[8] = 13;
    n = wici_link::encode(key, traffic, wire, sizeof(wire));
    assert(priorityRelay.receiveData(wire, n, 130, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::REJECTED);  // a neighbour cannot hold two K1 slots
    traffic.source = 5; traffic.payload[2] = 5; traffic.sequence = 76; traffic.payload[8] = 16;
    n = wici_link::encode(key, traffic, wire, sizeof(wire));
    assert(priorityRelay.receiveData(wire, n, 130, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);  // another neighbour still gets K1
    assert(priorityRelay.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 130));
    uint8_t order[4] = {};
    for (uint8_t i = 0; i < 4; ++i) {  // both K1 frames leave before either K2 frame, rotating
        assert(priorityRelay.prepare(130 + i));
        out = priorityRelay.outgoing(outLength);
        assert(out && wici_link::decode(key, 100, out, outLength, parsed));
        order[i] = parsed.payload[8];
        assert(priorityRelay.transmitted(true, 130 + i));
        reply.source = 1; reply.destination = 2; reply.sequence = parsed.sequence;
        hackLength = wici_link::encode(key, reply, hack, sizeof(hack));
        assert(priorityRelay.receiveHack(hack, hackLength, 130 + i));
    }
    assert(order[0] == 10 && order[1] == 16 && order[2] == 11 && order[3] == 12);

    // A captured station C (7) can only spend its own K1 quota at its parent
    // B (2), and B's quota at the next relay A (3); A still has K1 room for
    // another neighbour D (8), and K2 from B is capped.
    static Memory parentMemory, nextMemory;
    wici_hop::Relay parentB(parentMemory, {100, 2, 1, 3, 0}, ifac, false, receivers);
    wici_hop::Relay nextA(nextMemory, {100, 3, 1, 1, 0}, ifac, false, receivers);
    assert(parentB.begin() && nextA.begin());
    assert(parentB.routes().beacon(3, {1, 1, 1, 1, 0}, 16, 150));
    wici_link::Frame junk = incoming;
    junk.source = 7; junk.destination = 2; junk.flags = wici_link::ACKREQ;
    junk.payload[2] = 7; junk.payload[4] = 90;
    const wici_hop::Receipt atA[4] = {wici_hop::Receipt::HACK_READY, wici_hop::Receipt::HACK_READY,
                                      wici_hop::Receipt::HACK_READY, wici_hop::Receipt::REJECTED};
    for (uint8_t i = 0; i < 4; ++i) {
        junk.sequence = static_cast<uint16_t>(150 + i);
        junk.payload[8] = static_cast<uint8_t>(100 + i);
        n = wici_link::encode(key, junk, wire, sizeof(wire));
        assert(parentB.receiveData(wire, n, 150, hack, sizeof(hack), hackLength) ==
               wici_hop::Receipt::HACK_READY);  // C's K1 slot at B is free again after each hop
        assert(parentB.prepare(150));
        out = parentB.outgoing(outLength);
        assert(out && wici_link::decode(key, 100, out, outLength, parsed) && parsed.destination == 3);
        assert(nextA.receiveData(out, outLength, 150, hack, sizeof(hack), hackLength) == atA[i]);
        assert(parentB.transmitted(true, 150));
        if (atA[i] == wici_hop::Receipt::HACK_READY) assert(parentB.receiveHack(hack, hackLength, 150));
        else assert(parentB.timeout(150));
    }
    wici_link::Frame fromD = incoming;
    fromD.source = 8; fromD.destination = 3; fromD.sequence = 160;
    fromD.payload[2] = 8; fromD.payload[4] = 90; fromD.payload[8] = 120;
    n = wici_link::encode(key, fromD, wire, sizeof(wire));
    assert(nextA.receiveData(wire, n, 150, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(nextA.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 150));
    assert(nextA.prepare(150) && nextA.contendedK2() == false);
    out = nextA.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.payload[8] == 100);  // B's K1 slot first (rotation), D's K1 next
    assert(nextA.transmitted(true, 150));
    reply.source = 1; reply.destination = 3; reply.sequence = parsed.sequence;
    hackLength = wici_link::encode(key, reply, hack, sizeof(hack));
    assert(nextA.receiveHack(hack, hackLength, 150));
    assert(nextA.prepare(151));
    out = nextA.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed) && parsed.payload[8] == 120);

    // Two K2 frames cannot deny the reserved space to K1.
    static Memory starvedMemory;
    wici_hop::Relay guarded(starvedMemory, {100, 2, 1, 1, 0}, ifac, false, receivers);
    assert(guarded.begin());
    traffic.source = 4; traffic.payload[2] = 4; traffic.payload[4] = 50;
    for (uint8_t i = 0; i < 3; ++i) {
        traffic.sequence = static_cast<uint16_t>(90 + i);
        traffic.payload[8] = static_cast<uint8_t>(20 + i);
        n = wici_link::encode(key, traffic, wire, sizeof(wire));
        assert(guarded.receiveData(wire, n, 140, hack, sizeof(hack), hackLength) ==
               (i < 2 ? wici_hop::Receipt::HACK_READY : wici_hop::Receipt::REJECTED));
    }
    traffic.sequence = 93; traffic.payload[4] = 90; traffic.payload[8] = 23;
    n = wici_link::encode(key, traffic, wire, sizeof(wire));
    assert(guarded.receiveData(wire, n, 140, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY && hackLength == 19);
    assert(guarded.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 141));
    assert(guarded.prepare(141));
    out = guarded.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.payload[8] == 23);

    static Memory contentionMemory;
    wici_hop::Relay contentionRelay(contentionMemory, {100, 2, 1, 1, 0}, ifac, false, receivers);
    assert(contentionRelay.begin());
    wici_link::Frame waiting = traffic;
    waiting.flags = wici_link::ACKREQ | wici_link::DOWN;
    waiting.source = 1; waiting.sequence = 80;
    waiting.payload[2] = 90; waiting.payload[4] = 50; waiting.payload[8] = 20;
    n = wici_link::encode(key, waiting, wire, sizeof(wire));
    assert(contentionRelay.receiveData(wire, n, 140, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    waiting.flags = wici_link::ACKREQ;
    waiting.source = 4; waiting.sequence = 81;
    waiting.payload[2] = 4; waiting.payload[4] = 50; waiting.payload[8] = 21;
    n = wici_link::encode(key, waiting, wire, sizeof(wire));
    assert(contentionRelay.receiveData(wire, n, 140, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(contentionRelay.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 140));
    assert(contentionRelay.prepare(140) && contentionRelay.contendedK2());
    out = contentionRelay.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.payload[4] == 50);

    static Memory lateContentionMemory;
    wici_hop::Relay lateContention(lateContentionMemory, {100, 2, 1, 1, 0}, ifac, false, receivers);
    assert(lateContention.begin());
    waiting.flags = wici_link::ACKREQ; waiting.source = 4; waiting.sequence = 82;
    waiting.payload[2] = 4; waiting.payload[4] = 50; waiting.payload[8] = 22;
    n = wici_link::encode(key, waiting, wire, sizeof(wire));
    assert(lateContention.receiveData(wire, n, 141, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(lateContention.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 141));
    assert(lateContention.prepare(141) && !lateContention.contendedK2());
    waiting.flags = wici_link::ACKREQ | wici_link::DOWN;
    waiting.source = 1; waiting.sequence = 83;
    waiting.payload[2] = 90; waiting.payload[4] = 50; waiting.payload[8] = 23;
    n = wici_link::encode(key, waiting, wire, sizeof(wire));
    assert(lateContention.receiveData(wire, n, 141, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(lateContention.contendedK2());  // K1 is known at admission, no deferred check
    // Review finding 2/6: the first retry of a K1 frame gets its HACK even
    // when a replayed copy just used the repeat allowance (the admission
    // HACK may have been lost).
    static Memory owedMemory;
    wici_hop::Relay owed(owedMemory, {100, 2, 1, 1, 0}, ifac, false, receivers);
    assert(owed.begin());
    wici_link::Frame k2 = incoming;
    k2.payload[2] = 4; k2.payload[4] = 50;
    uint8_t k2Wire[255];
    size_t k2Length = 0;
    for (uint8_t i = 0; i < 2; ++i) {
        k2.sequence = static_cast<uint16_t>(200 + i); k2.payload[8] = static_cast<uint8_t>(30 + i);
        k2Length = wici_link::encode(key, k2, k2Wire, sizeof(k2Wire));
        assert(owed.receiveData(k2Wire, k2Length, 200, hack, sizeof(hack), hackLength) ==
               wici_hop::Receipt::HACK_READY);
    }
    assert(owed.receiveData(k2Wire, k2Length, 200, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);  // repeat allowance used at t=200
    wici_link::Frame k1 = k2;
    k1.sequence = 210; k1.payload[4] = 90; k1.payload[8] = 40;
    n = wici_link::encode(key, k1, wire, sizeof(wire));
    assert(owed.receiveData(wire, n, 200, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);  // durable K1 admission, HACK at once
    assert(owed.receiveData(wire, n, 201, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);  // owed HACK is not rate limited
    assert(owed.receiveData(wire, n, 202, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::IGNORED);     // but owed only once

    // Review medium item: floods are K2, even from a receiver.
    static Memory floodK2Memory;
    wici_hop::Relay floodK2(floodK2Memory, {100, 2, 1, 1, 0}, ifac, true, receivers);
    assert(floodK2.begin());
    wici_link::Frame flood = incoming;
    flood.flags = wici_link::DOWN; flood.source = 1; flood.destination = wici_link::BROADCAST;
    flood.sequence = 220; flood.payload[2] = 90; flood.payload[4] = 6; flood.payload[8] = 50;
    const size_t floodLength = wici_link::encode(key, flood, wire, sizeof(wire));
    assert(floodK2.receiveData(wire, floodLength, 220, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::STORED_NO_HACK);
    for (uint8_t i = 0; i < 2; ++i) {
        k2.sequence = static_cast<uint16_t>(221 + i); k2.payload[8] = static_cast<uint8_t>(51 + i);
        k2Length = wici_link::encode(key, k2, k2Wire, sizeof(k2Wire));
        assert(floodK2.receiveData(k2Wire, k2Length, 220, hack, sizeof(hack), hackLength) ==
               (i ? wici_hop::Receipt::REJECTED : wici_hop::Receipt::HACK_READY));
    }
    flood.payload[8] = 53; flood.sequence = 223;
    n = wici_link::encode(key, flood, wire, sizeof(wire));
    assert(floodK2.receiveData(wire, n, 220, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::REJECTED);
    assert(floodK2.learnPending(220));
    assert(floodK2.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 220));
    assert(floodK2.prepare(220) && !floodK2.contendedK2());
    out = floodK2.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.destination == wici_link::BROADCAST);

    // A frame whose only next hop is the neighbor it came from waits without
    // burning a durable link sequence on every loop pass.
    static Memory loopBackMemory;
    wici_hop::Relay loopBack(loopBackMemory, {100, 2, 1, 1, 0}, ifac);
    assert(loopBack.begin());
    wici_link::Frame fromParent = incoming;
    fromParent.source = 1; fromParent.sequence = 230; fromParent.payload[8] = 60;
    n = wici_link::encode(key, fromParent, wire, sizeof(wire));
    assert(loopBack.receiveData(wire, n, 230, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(loopBack.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 230));
    uint16_t seqBefore = 0, seqAfter = 0;
    assert(loopBack.nextSequence(seqBefore));
    for (unsigned i = 0; i < 100; ++i) assert(!loopBack.prepare(230));
    assert(loopBack.nextSequence(seqAfter) && seqAfter == static_cast<uint16_t>(seqBefore + 1));
    // Review finding 7, plan-bound: a down route to station S is learned via
    // neighbour N only if the network plan puts S behind N, or S is N.
    static Memory planMemory;
    const config::Behind plan[] = {{7, 3}};
    wici_hop::Relay planned(planMemory, {100, 2, 1, 1, 0}, ifac, false, rootReceiver, plan, 1);
    assert(planned.begin());
    wici_link::Frame uplink = incoming;
    const uint16_t claims[][2] = {{3, 7}, {3, 8}, {3, 3}, {4, 7}};  // {l_src, envelope src}
    for (uint8_t i = 0; i < 4; ++i) {
        uplink.source = claims[i][0]; uplink.payload[2] = static_cast<uint8_t>(claims[i][1]);
        uplink.sequence = static_cast<uint16_t>(240 + i); uplink.payload[8] = static_cast<uint8_t>(70 + i);
        n = wici_link::encode(key, uplink, wire, sizeof(wire));
        assert(planned.receiveData(wire, n, 240, hack, sizeof(hack), hackLength) ==
               wici_hop::Receipt::HACK_READY);
    }
    assert(planned.learnPending(240));
    assert(planned.routes().down(7) == 3);                    // behind 3 in the plan; 4 cannot move it
    assert(planned.routes().down(8) == wici_link::BROADCAST);  // not behind 3: not learned
    assert(planned.routes().down(3) == 3);                    // a neighbour stands for itself
    static Memory unplannedMemory;
    wici_hop::Relay unplanned(unplannedMemory, {100, 2, 1, 1, 0}, ifac, false, rootReceiver);
    assert(unplanned.begin());
    uplink.source = 4; uplink.payload[2] = 7; uplink.sequence = 250; uplink.payload[8] = 80;
    n = wici_link::encode(key, uplink, wire, sizeof(wire));
    assert(unplanned.receiveData(wire, n, 250, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(unplanned.learnPending(250) && unplanned.routes().down(7) == wici_link::BROADCAST);

    // Review medium item: downlink from one receiver is not serialised; each
    // frame takes a K2 slot and gets its HACK at once.
    static Memory downlinkMemory;
    wici_hop::Relay downlinks(downlinkMemory, {100, 2, 1, 1, 0}, ifac, false, receivers);
    assert(downlinks.begin());
    wici_link::Frame fromReceiver = incoming;
    fromReceiver.flags = wici_link::ACKREQ | wici_link::DOWN; fromReceiver.source = 1;
    fromReceiver.payload[2] = 90; fromReceiver.payload[4] = 4;
    for (uint8_t i = 0; i < 2; ++i) {
        fromReceiver.sequence = static_cast<uint16_t>(250 + i);
        fromReceiver.payload[8] = static_cast<uint8_t>(80 + i);
        n = wici_link::encode(key, fromReceiver, wire, sizeof(wire));
        assert(downlinks.receiveData(wire, n, 250, hack, sizeof(hack), hackLength) ==
               wici_hop::Receipt::HACK_READY);
    }
}
