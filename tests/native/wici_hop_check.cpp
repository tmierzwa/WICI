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

unsigned proofCalls = 0;
bool originProof(uint16_t, uint16_t, const wici_link::Frame& frame, const void*) {
    ++proofCalls;
    return frame.originSignature[0] == 0xA5;  // real Ed25519 verification is tested separately
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
    incoming.originSignature[0] = 0xA5;
    const size_t length = wici_link::encode(key, incoming, wire, sizeof(wire));
    assert(length == 108);
    const uint16_t rootReceiver[2] = {1, 90};
    wici_hop::Relay relay(memory, {100, 2, 1, 1, 0}, ifac, false, rootReceiver, originProof);
    assert(relay.begin());
    size_t hackLength = 0;
    assert(relay.receiveData(wire, length, 100, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(proofCalls == 0);  // signature verification cannot delay HACK
    assert(hackLength == 19);
    wici_link::Frame parsed;
    assert(wici_link::decode(key, 100, hack, hackLength, parsed));
    assert(parsed.type == wici_link::Type::HACK && parsed.destination == 4 && parsed.sequence == 41);

    // Crash after HACK: the queue remains and a new link sequence is reserved.
    wici_hop::Relay resumed(memory, {100, 2, 1, 1, 0}, ifac, false, rootReceiver, originProof);
    assert(resumed.begin());
    resumed.learnPending(101);
    assert(resumed.routes().down(4) == 4);
    assert(proofCalls == 1);
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
    wici_hop::Relay after(memory, {100, 2, 1, 1, 0}, ifac, false, rootReceiver, originProof);
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

    // K2 admission reserves two slots for later work. Signature verification
    // happens only after HACK and its durable result determines send priority.
    static Memory priorityMemory;
    const uint16_t receivers[2] = {90, 91};
    wici_hop::Relay priorityRelay(priorityMemory, {100, 2, 1, 1, 0}, ifac, false, receivers,
                                   originProof);
    assert(priorityRelay.begin());
    wici_link::Frame traffic = incoming;
    traffic.source = 4;
    traffic.flags = wici_link::ACKREQ;
    traffic.payload[4] = 50;
    for (uint8_t i = 0; i < 1; ++i) {
        traffic.sequence = static_cast<uint16_t>(70 + i);
        traffic.payload[8] = static_cast<uint8_t>(10 + i);
        const size_t n = wici_link::encode(key, traffic, wire, sizeof(wire));
        assert(priorityRelay.receiveData(wire, n, 130, hack, sizeof(hack), hackLength) ==
               wici_hop::Receipt::HACK_READY);
    }
    traffic.sequence = 70;
    traffic.payload[8] = 10;
    size_t n = wici_link::encode(key, traffic, wire, sizeof(wire));
    const unsigned beforeProof = proofCalls;
    assert(priorityRelay.receiveData(wire, n, 130, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(proofCalls == beforeProof);  // no extra verification on the HACK path
    traffic.sequence = 74;
    traffic.payload[4] = 90;
    traffic.payload[8] = 14;
    traffic.originSignature[0] = 0xA5;
    n = wici_link::encode(key, traffic, wire, sizeof(wire));
    assert(priorityRelay.receiveData(wire, n, 130, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    traffic.sequence = 75; traffic.payload[8] = 15;
    n = wici_link::encode(key, traffic, wire, sizeof(wire));
    assert(priorityRelay.receiveData(wire, n, 130, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::REJECTED);  // one durable K1 slot per verified origin
    traffic.payload[2] = 5; traffic.source = 5; traffic.sequence = 76; traffic.payload[8] = 16;
    n = wici_link::encode(key, traffic, wire, sizeof(wire));
    assert(priorityRelay.receiveData(wire, n, 130, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::STORED_NO_HACK);
    assert(priorityRelay.receiveData(wire, n, 136, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(priorityRelay.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 130));
    assert(priorityRelay.prepare(130));
    out = priorityRelay.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.payload[4] == 90 && parsed.payload[8] == 14);

    // Two unverified K2 frames cannot deny the reserved space to signed K1.
    static Memory starvedMemory;
    wici_hop::Relay guarded(starvedMemory, {100, 2, 1, 1, 0}, ifac, false, receivers,
                            originProof);
    assert(guarded.begin());
    traffic.payload[4] = 50; traffic.originSignature[0] = 0;
    for (uint8_t i = 0; i < 2; ++i) {
        traffic.sequence = static_cast<uint16_t>(90 + i);
        traffic.payload[8] = static_cast<uint8_t>(20 + i);
        n = wici_link::encode(key, traffic, wire, sizeof(wire));
        assert(guarded.receiveData(wire, n, 140, hack, sizeof(hack), hackLength) ==
               wici_hop::Receipt::HACK_READY);
    }
    traffic.sequence = 92; traffic.payload[4] = 90; traffic.payload[8] = 22;
    n = wici_link::encode(key, traffic, wire, sizeof(wire));
    assert(guarded.receiveData(wire, n, 140, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::REJECTED);  // an unsigned K1 claim gets no reserved slot
    traffic.originSignature[0] = 0xA5;
    n = wici_link::encode(key, traffic, wire, sizeof(wire));
    assert(guarded.receiveData(wire, n, 140, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::STORED_NO_HACK);
    assert(hackLength == 0);
    assert(guarded.receiveData(wire, n, 141, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(guarded.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 141));
    assert(guarded.prepare(141));
    out = guarded.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.payload[8] == 22);

    static Memory contentionMemory;
    wici_hop::Relay contentionRelay(contentionMemory, {100, 2, 1, 1, 0}, ifac, false, receivers,
                                     originProof);
    assert(contentionRelay.begin());
    wici_link::Frame waiting = traffic;
    waiting.flags = wici_link::ACKREQ | wici_link::DOWN;
    waiting.source = 1; waiting.sequence = 80;
    waiting.payload[2] = 90; waiting.payload[4] = 50; waiting.payload[8] = 20;
    waiting.originSignature[0] = 0xA5;
    n = wici_link::encode(key, waiting, wire, sizeof(wire));
    assert(contentionRelay.receiveData(wire, n, 140, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    waiting.flags = wici_link::ACKREQ;
    waiting.source = 4; waiting.sequence = 81;
    waiting.payload[2] = 4; waiting.payload[4] = 50; waiting.payload[8] = 21;
    waiting.originSignature[0] = 0;
    n = wici_link::encode(key, waiting, wire, sizeof(wire));
    assert(contentionRelay.receiveData(wire, n, 140, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    assert(contentionRelay.routes().beacon(1, {1, 0, 1, 0, 0}, 16, 140));
    assert(contentionRelay.prepare(140) && contentionRelay.contendedK2(140));
    out = contentionRelay.outgoing(outLength);
    assert(out && wici_link::decode(key, 100, out, outLength, parsed));
    assert(parsed.payload[4] == 50);

    static Memory lateContentionMemory;
    wici_hop::Relay lateContention(lateContentionMemory, {100, 2, 1, 1, 0}, ifac, false, receivers,
                                    originProof);
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
    waiting.payload[2] = 90; waiting.payload[4] = 50; waiting.payload[8] = 23;
    waiting.originSignature[0] = 0xA5;
    n = wici_link::encode(key, waiting, wire, sizeof(wire));
    assert(lateContention.receiveData(wire, n, 141, hack, sizeof(hack), hackLength) ==
           wici_hop::Receipt::HACK_READY);
    lateContention.learnPending(141);
    assert(lateContention.contendedK2(141));
}
