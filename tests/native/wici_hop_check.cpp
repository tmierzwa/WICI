// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include "wici_airtime.h"
#include "wici_hop.h"

struct Memory : journal::Storage {
    uint8_t bytes[0x048000] = {};
    unsigned writes = 0;
    bool read(uint32_t at, uint8_t* out, size_t count) override {
        if (at > sizeof(bytes) || count > sizeof(bytes) - at) return false;
        memcpy(out, bytes + at, count); return true;
    }
    bool write(uint32_t at, const uint8_t* in, size_t count) override {
        if (at > sizeof(bytes) || count > sizeof(bytes) - at) return false;
        ++writes;
        memcpy(bytes + at, in, count); return true;
    }
};

// A HACK repeats the start of the acknowledged frame's network MAC.
void setEcho(wici_link::Frame& reply, uint16_t echo) {
    reply.payload[0] = static_cast<uint8_t>(echo >> 8);
    reply.payload[1] = static_cast<uint8_t>(echo);
    reply.length = wici_link::HACK_ECHO;
}

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
    assert(hackLength == 21);
    wici_link::Frame parsed;
    assert(wici_link::decode(key, 100, hack, hackLength, parsed));
    assert(parsed.type == wici_link::Type::HACK && parsed.destination == 4 && parsed.sequence == 41 &&
           wici_link::hackEcho(parsed) == wici_link::macEcho(wire, length));

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
    setEcho(reply, wici_link::macEcho(out, outLength));
    hackLength = wici_link::encode(key, reply, hack, sizeof(hack));
    assert(!resumed.receiveHack(hack, hackLength, 103));
    assert(resumed.timeout(103));
    assert(resumed.outgoing(outLength) == out && outLength == length);
    assert(resumed.transmitted(true, 104));
    reply.source = 1;
    // A recorded HACK for an older frame with the same seq (after the 16-bit seq wrapped) has another echo.
    setEcho(reply, static_cast<uint16_t>(wici_link::macEcho(out, outLength) ^ 1));
    hackLength = wici_link::encode(key, reply, hack, sizeof(hack));
    assert(!resumed.receiveHack(hack, hackLength, 105) && resumed.active());
    setEcho(reply, wici_link::macEcho(out, outLength));
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
    setEcho(reply, wici_link::macEcho(out, outLength));
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
    setEcho(reply, wici_link::macEcho(out, outLength));
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
        setEcho(reply, wici_link::macEcho(out, outLength));
        hackLength = wici_link::encode(key, reply, hack, sizeof(hack));
        assert(priorityRelay.receiveHack(hack, hackLength, 130 + i));
    }
    assert(order[0] == 10 && order[1] == 16 && order[2] == 11 && order[3] == 12);

    // E1: a delivery proof (envelope type 1) is K2, so its station's K1 slot
    // stays for its SA1: the REQUEST behind the proof leaves first.
    static Memory proofMemory;
    wici_hop::Relay proofRelay(proofMemory, {100, 2, 1, 1, 0}, ifac, false, receivers);
    assert(proofRelay.begin());
    traffic.source = 4; traffic.payload[2] = 4;
    traffic.payload[0] = 0x41; traffic.sequence = 80; traffic.payload[8] = 20;  // the proof first
    n = wici_link::encode(key, traffic, wire, sizeof(wire));
    assert(proofRelay.receiveData(wire, n, 140, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    traffic.payload[0] = 0x40; traffic.sequence = 81; traffic.payload[8] = 21;  // then its SA1
    n = wici_link::encode(key, traffic, wire, sizeof(wire));
    assert(proofRelay.receiveData(wire, n, 140, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(proofRelay.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 140));
    assert(proofRelay.prepare(140));
    out = proofRelay.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed) && parsed.payload[8] == 21);

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
    assert(nextA.prepare(150) && nextA.contendedK2(150) == false);
    out = nextA.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.payload[8] == 100);  // B's K1 slot first (rotation), D's K1 next
    assert(nextA.transmitted(true, 150));
    reply.source = 1; reply.destination = 3; reply.sequence = parsed.sequence;
    setEcho(reply, wici_link::macEcho(out, outLength));
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
           wici_hop::Receipt::HACK_READY && hackLength == 21);
    assert(guarded.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 141));
    assert(guarded.prepare(141));
    out = guarded.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.payload[8] == 23);

    static Memory contentionMemory;
    wici_hop::Relay contentionRelay(contentionMemory, {100, 2, 1, 1, 0}, ifac, false, receivers);
    assert(contentionRelay.begin());
    assert(contentionRelay.routes().learn(7, 7));  // a route: the flood rule does not apply
    wici_link::Frame waiting = traffic;
    waiting.flags = wici_link::ACKREQ | wici_link::DOWN;
    waiting.source = 7; waiting.sequence = 80;  // its route leads back to its source: it cannot go
    waiting.payload[2] = 90; waiting.payload[4] = 7; waiting.payload[8] = 20;
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
    assert(contentionRelay.prepare(140));
    out = contentionRelay.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.payload[4] == 50);
    // A K1 frame that prepare() would skip is no contention: K2 is not held at
    // the 25% cap for it (review of #187: the same silence as a K1 flood).
    static Memory contentionAirtime;
    wici_airtime::Budget overQuarter(contentionAirtime);
    assert(overQuarter.begin(100, 2));
    while (overQuarter.allows(false, 200, 140, true)) assert(overQuarter.reserve(false, 200, 140));
    assert(overQuarter.allows(false, 200, 140, false));
    assert(!contentionRelay.contendedK2(140) && overQuarter.allows(false, 200, 140, contentionRelay.contendedK2(140)));

    static Memory lateContentionMemory;
    wici_hop::Relay lateContention(lateContentionMemory, {100, 2, 1, 1, 0}, ifac, false, receivers);
    assert(lateContention.begin());
    waiting.flags = wici_link::ACKREQ; waiting.source = 4; waiting.sequence = 82;
    waiting.payload[2] = 4; waiting.payload[4] = 50; waiting.payload[8] = 22;
    n = wici_link::encode(key, waiting, wire, sizeof(wire));
    assert(lateContention.receiveData(wire, n, 141, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(lateContention.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 141));
    assert(lateContention.prepare(141) && !lateContention.contendedK2(141));
    waiting.flags = wici_link::ACKREQ | wici_link::DOWN;
    waiting.source = 1; waiting.sequence = 83;
    waiting.payload[2] = 90; waiting.payload[4] = 7; waiting.payload[8] = 23;
    n = wici_link::encode(key, waiting, wire, sizeof(wire));
    assert(lateContention.receiveData(wire, n, 141, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(!lateContention.contendedK2(141));  // no route yet: it would go out as a flood, K2 itself
    assert(lateContention.routes().learn(7, 7));
    assert(lateContention.contendedK2(141));  // a K1 frame that can go now, known at admission

    // Two K1 frames without a route, pool above 25%: as floods they are K2, and
    // neither may hold the other back. Counted as waiting K1 they both stayed
    // refused until the 30-min expiry and the relay went silent.
    static Memory k1NoRouteMemory, k1NoRouteAirtime;
    // Both from a parent (planned 1, backup 4): only those copies flood.
    wici_hop::Relay k1NoRoute(k1NoRouteMemory, {100, 2, 1, 1, 4}, ifac, true, receivers);
    assert(k1NoRoute.begin());
    assert(k1NoRoute.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 142));
    waiting.flags = wici_link::ACKREQ | wici_link::DOWN;
    waiting.payload[2] = 90;
    const uint16_t k1NoRouteSource[2] = {1, 4};
    for (uint8_t i = 0; i < 2; ++i) {
        waiting.source = k1NoRouteSource[i]; waiting.sequence = static_cast<uint16_t>(84 + i);
        waiting.payload[4] = static_cast<uint8_t>(50 + i); waiting.payload[8] = static_cast<uint8_t>(24 + i);
        n = wici_link::encode(key, waiting, wire, sizeof(wire));
        assert(k1NoRoute.receiveData(wire, n, 142, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    }
    wici_airtime::Budget airtime(k1NoRouteAirtime);
    assert(airtime.begin(100, 2));
    while (airtime.allows(false, 200, 142, true)) assert(airtime.reserve(false, 200, 142));
    assert(airtime.allows(false, 200, 142, false));
    assert(k1NoRoute.prepare(142));
    out = k1NoRoute.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.destination == wici_link::BROADCAST && parsed.payload[4] == 50);
    assert(airtime.allows(false, 200, 142, k1NoRoute.contendedK2(142)));
    // The second frame gets a route: now a real K1 waits and the 25% cap holds.
    assert(k1NoRoute.routes().learn(51, 51));
    assert(!airtime.allows(false, 200, 142, k1NoRoute.contendedK2(142)));
    // A K1 frame to a held next hop: it waits for the hold, so it does not
    // hold K2 back; once the hold ends it can go and the 25% cap applies.
    static Memory heldMemory;
    wici_hop::Relay heldRelay(heldMemory, {100, 2, 1, 1, 0}, ifac, false, receivers);
    assert(heldRelay.begin());
    wici_link::Frame k1Up = traffic;
    k1Up.flags = wici_link::ACKREQ; k1Up.source = 4; k1Up.destination = 2; k1Up.sequence = 86;
    k1Up.payload[2] = 4; k1Up.payload[4] = 90; k1Up.payload[8] = 26;
    n = wici_link::encode(key, k1Up, wire, sizeof(wire));
    assert(heldRelay.receiveData(wire, n, 150, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(heldRelay.prepare(150));
    for (;;) {  // three attempts without HACK: a failed round holds parent 1 for 2 s
        assert(heldRelay.transmitted(true, 150));
        if (!heldRelay.timeout(150)) break;
    }
    wici_link::Frame k2Down = traffic;
    k2Down.flags = wici_link::ACKREQ | wici_link::DOWN; k2Down.source = 1; k2Down.destination = 2; k2Down.sequence = 87;
    k2Down.payload[2] = 60; k2Down.payload[4] = 50; k2Down.payload[8] = 27;
    n = wici_link::encode(key, k2Down, wire, sizeof(wire));
    assert(heldRelay.receiveData(wire, n, 150, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(heldRelay.routes().learn(50, 50));
    assert(heldRelay.prepare(150));
    out = heldRelay.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed) && parsed.destination == 50);
    static Memory heldAirtime;
    wici_airtime::Budget heldBudget(heldAirtime);
    assert(heldBudget.begin(100, 2));
    while (heldBudget.allows(false, 200, 150, true)) assert(heldBudget.reserve(false, 200, 150));
    assert(!heldRelay.contendedK2(150) && heldBudget.allows(false, 200, 150, heldRelay.contendedK2(150)));
    assert(heldRelay.contendedK2(152));  // the hold is over: a K1 frame that can go now

    // A K1 frame on its last allowed hop to a parent that is not the root waits
    // (up to the 30-min expiry) for a next hop that ends there: no contention.
    static Memory ttlMemory, ttlAirtime;
    wici_hop::Relay ttlRelay(ttlMemory, {100, 2, 1, 3, 0}, ifac, false, receivers);
    assert(ttlRelay.begin());
    k1Up.sequence = 88; k1Up.payload[8] = 28; k1Up.hops = 14; k1Up.ttl = 15;
    n = wici_link::encode(key, k1Up, wire, sizeof(wire));
    assert(ttlRelay.receiveData(wire, n, 160, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    k2Down.source = 3; k2Down.sequence = 89; k2Down.payload[8] = 29;
    n = wici_link::encode(key, k2Down, wire, sizeof(wire));
    assert(ttlRelay.receiveData(wire, n, 160, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(ttlRelay.routes().learn(50, 50));
    assert(ttlRelay.prepare(160));
    out = ttlRelay.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed) && parsed.destination == 50);
    wici_airtime::Budget ttlBudget(ttlAirtime);
    assert(ttlBudget.begin(100, 2));
    while (ttlBudget.allows(false, 200, 160, true)) assert(ttlBudget.reserve(false, 200, 160));
    assert(!ttlRelay.contendedK2(160) && ttlBudget.allows(false, 200, 160, ttlRelay.contendedK2(160)));

    // Review finding 2/6, L4/E8: the first retry of any admitted frame gets
    // its HACK even when a replayed copy just used the repeat allowance and
    // after the frame left the queue (the admission HACK may have been lost).
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
           wici_hop::Receipt::HACK_READY);  // the first retry is owed, K2 too
    assert(owed.receiveData(k2Wire, k2Length, 200, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);  // a replay: repeat allowance used at t=200
    assert(owed.receiveData(k2Wire, k2Length, 201, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::IGNORED);
    wici_link::Frame k1 = k2;
    k1.sequence = 210; k1.payload[4] = 90; k1.payload[8] = 40;
    n = wici_link::encode(key, k1, wire, sizeof(wire));
    assert(owed.receiveData(wire, n, 200, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);  // durable K1 admission, HACK at once
    // The frame leaves the queue (K1 first) before the sender's retry arrives.
    assert(owed.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 200) && owed.prepare(200));
    out = owed.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed) && parsed.payload[8] == 40);
    assert(owed.transmitted(true, 200));
    reply.source = 1; reply.destination = 2; reply.sequence = parsed.sequence;
    setEcho(reply, wici_link::macEcho(out, outLength));
    hackLength = wici_link::encode(key, reply, hack, sizeof(hack));
    assert(owed.receiveHack(hack, hackLength, 200));
    assert(owed.receiveData(wire, n, 201, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);  // owed HACK is not rate limited, also after forwarding
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
    assert(floodK2.prepare(220) && !floodK2.contendedK2(220));
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
    // A station relay as configured (`behind` only in the root's document):
    // no plan, so only the neighbour's own frame teaches a route, to itself.
    uplink.payload[2] = 4; uplink.sequence = 251; uplink.payload[8] = 81;
    n = wici_link::encode(key, uplink, wire, sizeof(wire));
    assert(unplanned.receiveData(wire, n, 251, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(unplanned.learnPending(251) && unplanned.routes().down(4) == 4);
    assert(unplanned.routes().down(7) == wici_link::BROADCAST);

    // Review D7, finding 7: an item whose hop limit would end at a relay
    // (that relay refuses hops == ttl) is not sent there and spends no seq;
    // it waits for a next hop that ends the trip, here the root as backup
    // after a detour, bounded by the 30-min expiry. The root may take the
    // last hop.
    static Memory lastHopMemory, rootHopMemory;
    wici_link::Frame lastHop = incoming;
    lastHop.ttl = 2; lastHop.hops = 1; lastHop.sequence = 300; lastHop.payload[8] = 90;
    n = wici_link::encode(key, lastHop, wire, sizeof(wire));
    wici_hop::Relay viaRelay(lastHopMemory, {100, 2, 1, 3, 1}, ifac);
    wici_hop::Relay viaRoot(rootHopMemory, {100, 2, 1, 1, 0}, ifac);
    assert(viaRelay.begin() && viaRoot.begin());
    assert(viaRelay.receiveData(wire, n, 300, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(viaRoot.receiveData(wire, n, 300, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(viaRelay.learnPending(300));  // the down-route hint (4 via 4) is written once, here
    const unsigned writesBeforeWait = lastHopMemory.writes;
    assert(!viaRelay.prepare(300) && !viaRelay.prepare(301));
    assert(lastHopMemory.writes == writesBeforeWait);  // neither retired nor a seq reserved
    viaRelay.routes().loop(302);  // planned 3 -> backup 1, the root
    assert(viaRelay.prepare(302));
    out = viaRelay.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed) && parsed.destination == 1 && parsed.hops == 2);
    assert(viaRoot.prepare(300));
    // Review D7: the 30-min expiry runs while a transfer is active and ends it.
    assert(viaRoot.transmitted(true, 301) && viaRoot.timeout(302) && viaRoot.active());
    assert(viaRoot.learnPending(300 + wici_relay::MAX_HOLD_S - 1) && viaRoot.active());
    assert(viaRoot.learnPending(300 + wici_relay::MAX_HOLD_S) && !viaRoot.active());
    assert(!viaRoot.prepare(300 + wici_relay::MAX_HOLD_S));

    // Review 2c: upward DATA from the current parent is a loop: the parent
    // rotates at once and the frame is still admitted. Final review B1: an
    // envelope that names this station as its sender (`src`) is no signal; a
    // relay cannot check the envelope MAC, so a captured child could forge it.
    static Memory fromParentMemory, ownBackMemory;
    wici_hop::Relay looped(fromParentMemory, {100, 2, 1, 3, 6}, ifac);
    wici_hop::Relay ownBack(ownBackMemory, {100, 2, 1, 3, 6}, ifac);
    assert(looped.begin() && ownBack.begin());
    wici_link::Frame up = incoming;
    up.source = 3; up.sequence = 320; up.payload[8] = 91;
    n = wici_link::encode(key, up, wire, sizeof(wire));
    assert(looped.routes().parent() == 3);
    assert(looped.receiveData(wire, n, 320, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(looped.routes().parent() == 6);
    up.source = 4; up.payload[2] = 2; up.sequence = 321;
    n = wici_link::encode(key, up, wire, sizeof(wire));
    assert(ownBack.receiveData(wire, n, 320, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(ownBack.routes().parent() == 3);
    // Finding 5: only a newly stored envelope is a loop signal. A retry or
    // replayed copy of one already held, even from the current parent, does
    // not rotate the parent again.
    up = incoming; up.source = 6; up.sequence = 322; up.payload[8] = 91;
    n = wici_link::encode(key, up, wire, sizeof(wire));
    assert(looped.receiveData(wire, n, 330, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(looped.routes().parent() == 6);

    // Final review B2: a round of 3 attempts without HACK holds that next hop
    // for 2, 4 ... 256, then 300 s, so a silent root (no laptop) costs a few
    // frames per 5 min instead of the whole transit pool. A HACK echoing an
    // attempt or a checked BEACON from it ends the hold at once; a DATA does
    // not, because a recorded one replays (link frames have no replay window).
    static Memory holdMemory;
    wici_hop::Relay holding(holdMemory, {100, 2, 1, 1, 0}, ifac);
    assert(holding.begin());
    up = incoming; up.sequence = 600; up.payload[8] = 93;
    n = wici_link::encode(key, up, wire, sizeof(wire));
    assert(holding.receiveData(wire, n, 600, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    const auto round = [&](uint32_t at) {
        assert(holding.prepare(at));
        for (unsigned attempt = 0; attempt < 3; ++attempt)
            assert(holding.transmitted(true, at) && holding.timeout(at) == (attempt < 2));
    };
    uint32_t at = 600;
    const uint32_t holds[] = {2, 4, 8, 16, 32, 64, 128, 256, 300, 300};
    for (const uint32_t holdS : holds) {
        round(at);
        assert(!holding.prepare(at + holdS - 1));
        at += holdS;
    }
    round(at);
    assert(!holding.prepare(at + 1));
    wici_link::Frame recorded = incoming;   // root -> relay, down to station 4, from when the root had its laptop
    recorded.flags = wici_link::ACKREQ | wici_link::DOWN; recorded.source = 1; recorded.sequence = 7;
    recorded.payload[2] = 1; recorded.payload[4] = 4; recorded.payload[8] = 94;
    n = wici_link::encode(key, recorded, wire, sizeof(wire));
    // Replayed by a keyless listener: the frame itself goes on to station 4, the hop to the root stays held.
    holding.receiveData(wire, n, at + 1, hack, sizeof(hack), hackLength);
    assert(holding.prepare(at + 1));
    out = holding.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed) && parsed.destination == 4);
    assert(holding.transmitted(true, at + 1));
    reply.source = 4; reply.sequence = parsed.sequence;
    setEcho(reply, wici_link::macEcho(out, outLength));
    hackLength = wici_link::encode(key, reply, hack, sizeof(hack));
    assert(holding.receiveHack(hack, hackLength, at + 1));
    assert(!holding.prepare(at + 1));
    holding.heard(1);  // e.g. the root's BEACON after its laptop came back
    assert(holding.prepare(at + 1));

    // Review 11b, finding 3: a transfer the radio refused, prepared again for
    // the same next hop, keeps its seq, so refusals burn none. After a
    // reroute it gets a new seq, and a HACK for the attempt that was on air
    // before still completes the same item.
    static Memory lateMemory;
    wici_hop::Relay lateHack(lateMemory, {100, 2, 1, 1, 6}, ifac);
    assert(lateHack.begin());
    up = incoming; up.sequence = 330; up.payload[8] = 92;
    n = wici_link::encode(key, up, wire, sizeof(wire));
    assert(lateHack.receiveData(wire, n, 330, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(lateHack.prepare(330));
    out = lateHack.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed));
    const uint16_t firstAttempt = parsed.sequence;
    const uint16_t firstEcho = wici_link::macEcho(out, outLength);
    assert(lateHack.transmitted(true, 331) && lateHack.timeout(332));
    uint16_t seqBeforeRefusals = 0, seqAfterRefusals = 0;
    assert(lateHack.nextSequence(seqBeforeRefusals));
    for (unsigned i = 0; i < 100; ++i) {
        lateHack.yield();  // the radio refused the retry
        assert(!lateHack.active() && lateHack.prepare(333));
        out = lateHack.outgoing(outLength);
        assert(wici_link::decode(key, 100, out, outLength, parsed) && parsed.sequence == firstAttempt);
    }
    assert(lateHack.nextSequence(seqAfterRefusals) &&
           seqAfterRefusals == static_cast<uint16_t>(seqBeforeRefusals + 1));
    lateHack.yield();
    lateHack.routes().loop(333);  // reroute: planned 1 -> backup 6
    assert(lateHack.prepare(333));
    out = lateHack.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed) && parsed.destination == 6 &&
           parsed.sequence != firstAttempt);
    reply.source = 1; reply.destination = 2; reply.sequence = firstAttempt;
    setEcho(reply, firstEcho);
    hackLength = wici_link::encode(key, reply, hack, sizeof(hack));
    assert(lateHack.receiveHack(hack, hackLength, 334) && !lateHack.active());
    assert(!lateHack.prepare(335));                         // the item left the queue
    assert(!lateHack.receiveHack(hack, hackLength, 336));   // and the HACK counts once

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

    // Finding 2 (harness flood_yield): a downward flood the radio refused was
    // never on air. Its durable marker stays this relay's own, so the flood
    // stays queued and goes out at a later prepare() with the same seq, also
    // when another transfer was prepared and refused in between. Only a
    // restart (power loss between marker and TX) can lose it.
    static Memory floodYieldMemory;
    wici_hop::Relay floodYield(floodYieldMemory, {100, 2, 1, 1, 0}, ifac, true, rootReceiver);
    assert(floodYield.begin());
    wici_link::Frame refusedFlood = incoming;
    refusedFlood.flags = wici_link::DOWN; refusedFlood.source = 1; refusedFlood.destination = wici_link::BROADCAST;
    refusedFlood.sequence = 400; refusedFlood.payload[2] = 90; refusedFlood.payload[4] = 6;
    refusedFlood.payload[8] = 50;
    n = wici_link::encode(key, refusedFlood, wire, sizeof(wire));
    assert(floodYield.receiveData(wire, n, 400, hack, sizeof(hack), hackLength) == wici_hop::Receipt::STORED_NO_HACK);
    assert(floodYield.prepare(400));
    out = floodYield.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed) && parsed.destination == wici_link::BROADCAST);
    const uint16_t floodSeq = parsed.sequence;
    floodYield.yield();  // silence, budget or a busy radio: nothing on air
    up = incoming; up.sequence = 401; up.payload[4] = 50; up.payload[8] = 93;  // another (K2) transfer
    n = wici_link::encode(key, up, wire, sizeof(wire));
    assert(floodYield.receiveData(wire, n, 401, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(floodYield.prepare(401));
    out = floodYield.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed) && parsed.destination == 1);
    floodYield.yield();
    assert(floodYield.prepare(402) && floodYield.active());
    out = floodYield.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed) &&
           parsed.destination == wici_link::BROADCAST && parsed.sequence == floodSeq);
    floodYield.yield();
    wici_hop::Relay floodCut(floodYieldMemory, {100, 2, 1, 1, 0}, ifac, true, rootReceiver);
    assert(floodCut.begin() && floodCut.prepare(403));
    out = floodCut.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed) && parsed.destination == 1);  // the uplink
    floodCut.yield();
    assert(floodCut.prepare(404));
    out = floodCut.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed) && parsed.destination == 1);  // never the flood

    // Simplification: a down-route hint is learned once, at admission, and
    // writes no FRAM at later passes. External review: a relay cannot
    // authenticate the envelope sender, so a claim via another planned
    // neighbour does not move a working route (only a missing one is learned).
    static Memory hintMemory;
    const config::Behind both[] = {{7, 3}, {7, 4}};
    wici_hop::Relay hints(hintMemory, {100, 2, 1, 1, 0}, ifac, false, rootReceiver, both, 2);
    assert(hints.begin());
    uplink = incoming; uplink.payload[2] = 7;
    for (uint8_t i = 0; i < 2; ++i) {  // 7 via 4 first (slot 0), then a claim via 3 (slot 1)
        uplink.source = static_cast<uint16_t>(4 - i);
        uplink.sequence = static_cast<uint16_t>(410 + i); uplink.payload[8] = static_cast<uint8_t>(94 + i);
        n = wici_link::encode(key, uplink, wire, sizeof(wire));
        assert(hints.receiveData(wire, n, 410, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
        assert(hints.learnPending(410) && hints.routes().down(7) == 4);
    }
    const unsigned writesAfterHints = hintMemory.writes;
    for (uint32_t t = 411; t < 420; ++t) assert(hints.learnPending(t));
    assert(hints.routes().down(7) == 4 && hintMemory.writes == writesAfterHints);
    wici_hop::Relay hintsAgain(hintMemory, {100, 2, 1, 1, 0}, ifac, false, rootReceiver, both, 2);
    assert(hintsAgain.begin() && hintsAgain.learnPending(420));  // after a restart: each queued hint once
    assert(hintsAgain.routes().down(7) == 4);

    // An honest move: the old route goes after three downward attempts
    // without HACK (forget), and the station's next uplink frame via its new
    // neighbour teaches the new route.
    static Memory movedMemory;
    wici_hop::Relay moved(movedMemory, {100, 2, 1, 1, 0}, ifac, false, rootReceiver, both, 2);
    assert(moved.begin());
    const auto upward = [&](uint16_t via, uint16_t sequence, uint32_t at) {
        wici_link::Frame from = incoming;
        from.source = via; from.payload[2] = 7; from.sequence = sequence; from.payload[8] = static_cast<uint8_t>(sequence);
        n = wici_link::encode(key, from, wire, sizeof(wire));
        assert(moved.receiveData(wire, n, at, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
        assert(moved.prepare(at) && moved.transmitted(true, at));  // up to the parent, HACKed there
        out = moved.outgoing(outLength);
        assert(wici_link::decode(key, 100, out, outLength, parsed) && parsed.destination == 1);
        reply.source = 1; reply.destination = 2; reply.sequence = parsed.sequence;
        setEcho(reply, wici_link::macEcho(out, outLength));
        hackLength = wici_link::encode(key, reply, hack, sizeof(hack));
        assert(moved.receiveHack(hack, hackLength, at));
    };
    upward(4, 440, 440);
    assert(moved.routes().down(7) == 4);
    upward(3, 441, 441);
    assert(moved.routes().down(7) == 4);  // the planned alternate claim moves nothing
    wici_link::Frame toSeven = incoming;
    toSeven.flags = wici_link::ACKREQ | wici_link::DOWN;
    toSeven.source = 1; toSeven.destination = 2; toSeven.sequence = 442;
    toSeven.payload[2] = 1; toSeven.payload[4] = 7; toSeven.payload[8] = 1;
    n = wici_link::encode(key, toSeven, wire, sizeof(wire));
    assert(moved.receiveData(wire, n, 442, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(moved.prepare(442));
    for (unsigned attempt = 0; attempt < 3; ++attempt) {
        if (attempt == 1) {  // the radio refused the retry: the same frame comes back with its count
            moved.yield();
            assert(moved.prepare(443));
        }
        out = moved.outgoing(outLength);
        assert(wici_link::decode(key, 100, out, outLength, parsed) && parsed.destination == 4);
        assert(moved.transmitted(true, 443) && moved.timeout(444) == (attempt < 2));
        assert(moved.routes().down(7) == (attempt < 2 ? 4 : wici_link::BROADCAST));
    }
    assert(!moved.prepare(445));  // no route and no flooding here: the frame waits in the queue
    upward(3, 446, 446);
    assert(moved.routes().down(7) == 3);  // learned again, via the new neighbour

    // Round 3 (3): after a restart the hints are learned in admission order,
    // not slot order: an older frame of station 9 via 4 in slot 1 does not
    // override the newer one via 5 in slot 0.
    static Memory orderMemory;
    const config::Behind nine[] = {{9, 4}, {9, 5}};
    wici_hop::Relay ordered(orderMemory, {100, 2, 1, 1, 0}, ifac, false, rootReceiver, nine, 2);
    assert(ordered.begin());
    uplink = incoming; uplink.source = 4; uplink.payload[2] = 4;  // filler in slot 0 (K1 of 4)
    uplink.sequence = 420; uplink.payload[8] = 96;
    n = wici_link::encode(key, uplink, wire, sizeof(wire));
    assert(ordered.receiveData(wire, n, 490, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    uplink.payload[2] = 9; uplink.sequence = 421; uplink.payload[8] = 97;  // older: 9 via 4, slot 1
    n = wici_link::encode(key, uplink, wire, sizeof(wire));
    assert(ordered.receiveData(wire, n, 500, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(ordered.prepare(500));  // the filler (K1) leaves and frees slot 0
    out = ordered.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed) && parsed.payload[8] == 96);
    assert(ordered.transmitted(true, 501));
    reply.source = 1; reply.destination = 2; reply.sequence = parsed.sequence;
    setEcho(reply, wici_link::macEcho(out, outLength));
    hackLength = wici_link::encode(key, reply, hack, sizeof(hack));
    assert(ordered.receiveHack(hack, hackLength, 502));
    assert(ordered.routes().down(9) == 4 && ordered.routes().forget(9, 4));  // as after 3 downward failures
    uplink.source = 5; uplink.sequence = 422; uplink.payload[8] = 98;  // newer: 9 via 5, slot 0
    n = wici_link::encode(key, uplink, wire, sizeof(wire));
    assert(ordered.receiveData(wire, n, 510, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    // A restart before the hint was learned: newest first, so 9 via 5 is
    // learned and the older 9 via 4 (slot 1) no longer moves it.
    wici_hop::Relay orderedAgain(orderMemory, {100, 2, 1, 1, 0}, ifac, false, rootReceiver, nine, 2);
    assert(orderedAgain.begin() && orderedAgain.learnPending(511) && orderedAgain.routes().down(9) == 5);

    // Round 3 (4): a flood TX the radio accepted but failed put nothing
    // complete on air: the flood stays queued and goes again with its seq.
    static Memory failedFloodMemory;
    wici_hop::Relay failedFlood(failedFloodMemory, {100, 2, 1, 1, 0}, ifac, true, rootReceiver);
    assert(failedFlood.begin());
    refusedFlood.sequence = 430; refusedFlood.payload[8] = 51;
    n = wici_link::encode(key, refusedFlood, wire, sizeof(wire));
    assert(failedFlood.receiveData(wire, n, 430, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::STORED_NO_HACK);
    assert(failedFlood.prepare(430));
    out = failedFlood.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed));
    const uint16_t failedSeq = parsed.sequence;
    assert(!failedFlood.transmitted(false, 431) && !failedFlood.active());
    assert(failedFlood.prepare(432));
    out = failedFlood.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed) &&
           parsed.destination == wici_link::BROADCAST && parsed.sequence == failedSeq);
    assert(failedFlood.transmitted(true, 433) && !failedFlood.prepare(434));

    // Flood rule (wici-link.md, "Rozsyłanie"): a downward frame without a
    // route is passed on only from the planned (1), backup (3) or current
    // parent. A copy from another neighbour is not queued, gets no HACK and
    // is not marked seen, so the parent's later copy still goes out.
    static Memory parentRuleMemory;
    wici_hop::Relay parentRule(parentRuleMemory, {100, 2, 1, 1, 3}, ifac, true, rootReceiver);
    assert(parentRule.begin());
    wici_link::Frame copy = incoming;
    copy.flags = wici_link::DOWN; copy.destination = wici_link::BROADCAST; copy.ttl = 15;
    copy.payload[2] = 90; copy.payload[4] = 40; copy.payload[8] = 60;
    auto offer = [&](uint16_t from, uint16_t sequence) {
        copy.source = from; copy.sequence = sequence;
        n = wici_link::encode(key, copy, wire, sizeof(wire));
        return parentRule.receiveData(wire, n, 600, hack, sizeof(hack), hackLength);
    };
    auto floods = [&]() {
        if (!parentRule.prepare(600)) return false;
        out = parentRule.outgoing(outLength);
        assert(wici_link::decode(key, 100, out, outLength, parsed));
        assert(parsed.destination == wici_link::BROADCAST && parsed.payload[4] == copy.payload[4]);
        return parentRule.transmitted(true, 600);
    };
    // A flood copy from neighbour 5 first, then the same envelope from the planned parent.
    assert(offer(5, 600) == wici_hop::Receipt::IGNORED && hackLength == 0 && !parentRule.prepare(600));
    assert(offer(1, 601) == wici_hop::Receipt::STORED_NO_HACK && floods());
    assert(offer(5, 602) == wici_hop::Receipt::IGNORED);  // seen now, from anyone
    // A unicast frame to this relay without a route: no HACK from neighbour 5,
    // stored and flooded from the backup parent.
    copy.flags = wici_link::DOWN | wici_link::ACKREQ; copy.destination = 2; copy.payload[4] = 41;
    assert(offer(5, 603) == wici_hop::Receipt::IGNORED && hackLength == 0 && !parentRule.prepare(600));
    assert(offer(3, 604) == wici_hop::Receipt::HACK_READY && floods());
    // A dynamic parent counts as soon as it is the current one.
    copy.flags = wici_link::DOWN; copy.destination = wici_link::BROADCAST; copy.payload[4] = 42;
    assert(parentRule.routes().beacon(6, {1, 16, 1, 1, 0}, 16, 600));
    assert(offer(6, 605) == wici_hop::Receipt::IGNORED);
    parentRule.routes().loop(600);
    parentRule.routes().loop(600);
    assert(parentRule.routes().parent() == 6);
    assert(offer(6, 606) == wici_hop::Receipt::STORED_NO_HACK && floods());
    // The rule is decided once, at admission: a frame from the dynamic parent
    // still floods after the parent changes and after a restart (the parent
    // is back to the planned one). Checked again at send time, it sat in a K2
    // slot until the 30-min expiry.
    copy.payload[4] = 44;
    assert(offer(6, 610) == wici_hop::Receipt::STORED_NO_HACK);
    parentRule.routes().loop(600);
    assert(parentRule.routes().parent() != 6 && floods());
    parentRule.routes().loop(600);
    parentRule.routes().loop(600);
    assert(parentRule.routes().parent() == 6);
    copy.payload[4] = 45;
    assert(offer(6, 611) == wici_hop::Receipt::STORED_NO_HACK);
    {
        wici_hop::Relay restarted(parentRuleMemory, {100, 2, 1, 1, 3}, ifac, true, rootReceiver);
        assert(restarted.begin() && restarted.routes().parent() == 1 && restarted.prepare(601));
        out = restarted.outgoing(outLength);
        assert(wici_link::decode(key, 100, out, outLength, parsed));
        assert(parsed.destination == wici_link::BROADCAST && parsed.payload[4] == 45);
        assert(restarted.transmitted(true, 601));
    }
    assert(parentRule.begin() && !parentRule.prepare(602));  // the flood left before the restart above
    copy.payload[4] = 43;
    assert(offer(1, 607) == wici_hop::Receipt::STORED_NO_HACK && floods());  // the planned parent still counts
    // An upward frame and a frame with a known route go on from any neighbour.
    copy.flags = wici_link::ACKREQ; copy.destination = 2; copy.payload[2] = 40; copy.payload[4] = 90;
    assert(offer(5, 608) == wici_hop::Receipt::HACK_READY && parentRule.prepare(600));
    out = parentRule.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed) && parsed.destination == 1);
    parentRule.yield();
    static Memory routedMemory;
    wici_hop::Relay routed(routedMemory, {100, 2, 1, 1, 3}, ifac, true, rootReceiver);
    assert(routed.begin() && routed.routes().learn(7, 7));
    copy.flags = wici_link::DOWN | wici_link::ACKREQ; copy.source = 5; copy.sequence = 609;
    copy.payload[2] = 90; copy.payload[4] = 7;
    n = wici_link::encode(key, copy, wire, sizeof(wire));
    assert(routed.receiveData(wire, n, 600, hack, sizeof(hack), hackLength) == wici_hop::Receipt::HACK_READY);
    assert(routed.prepare(600));
    out = routed.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed) && parsed.destination == 7);
    // A route that goes after admission (three failed rounds) does not turn
    // the frame of neighbour 5 into a flood: it waits for a route or expiry.
    routed.yield();
    assert(routed.routes().forget(7, 7) && !routed.prepare(600) && !routed.contendedK2(600));
    // The mark is durable: after a restart the frame still waits for its route.
    wici_hop::Relay routedAgain(routedMemory, {100, 2, 1, 1, 3}, ifac, true, rootReceiver);
    assert(routedAgain.begin() && routedAgain.routes().down(7) == wici_link::BROADCAST && !routedAgain.prepare(601));
    assert(routedAgain.routes().learn(7, 7) && routedAgain.prepare(601));
    out = routedAgain.outgoing(outLength);
    assert(wici_link::decode(key, 100, out, outLength, parsed) && parsed.destination == 7);
}
