// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include <Crypto.h>
#include <Curve25519.h>
#include <Ed25519.h>

#include "envelope.h"
#include "wici_radio.h"
#include "wici_epoch.h"
#include "wici_beacon.h"

namespace {
struct Memory : journal::Storage {
    uint8_t bytes[0x048000] = {};
    bool read(uint32_t at, uint8_t* out, size_t n) override {
        if (at > sizeof(bytes) || n > sizeof(bytes) - at) return false;
        memcpy(out, bytes + at, n); return true;
    }
    bool write(uint32_t at, const uint8_t* in, size_t n) override {
        if (at > sizeof(bytes) || n > sizeof(bytes) - at) return false;
        memcpy(bytes + at, in, n); return true;
    }
};
struct Air : wici_radio::Air {
    uint8_t data[255] = {}, hack[255] = {};
    size_t dataLength = 0, hackLength = 0;
    unsigned dataCount = 0, hackCount = 0;
    wici_link::TxClass lastClass = wici_link::TxClass::OWN;
    bool hackOk = true, dataOk = true;
    uint32_t receivedMs = 0;
    bool sendData(const uint8_t* p, size_t n, wici_link::TxClass traffic) override {
        lastClass = traffic;
        assert(n <= sizeof(data)); memcpy(data, p, n); dataLength = n; ++dataCount; return dataOk;
    }
    bool sendHack(const uint8_t* p, size_t n, uint32_t ms) override {
        assert(n <= sizeof(hack)); memcpy(hack, p, n); hackLength = n;
        receivedMs = ms; ++hackCount; return hackOk;
    }
};
void publicKey(const uint8_t secret[32], uint8_t out[32]) {
    uint8_t scalar[32]; memcpy(scalar, secret, 32);
    scalar[0] &= 0xf8; scalar[31] = (scalar[31] & 0x7f) | 0x40;
    Curve25519::eval(out, scalar, nullptr); clean(scalar, 32);
}
bool admit(uint16_t net, uint16_t src, uint16_t dst, const uint8_t* p, size_t n, void* ctx) {
    assert(net == 100 && src == 1 && dst == 2 && n == 3 && memcmp(p, "SA1", 3) == 0);
    ++*static_cast<unsigned*>(ctx); return true;
}
uint32_t randomZero(void*) { return 0; }
bool originProof(uint16_t, uint16_t, const wici_link::Frame& frame, const void*) {
    return frame.originSignature[0] == 0xA5;
}
bool beaconProof(uint16_t sender, const uint8_t content[wici_beacon::CONTENT_BYTES],
                 const uint8_t signature[wici_beacon::SIGNATURE_BYTES], const void* context) {
    return wici_beacon::verify(static_cast<const uint8_t*>(context), 100, sender, content, signature);
}
struct Delivery { uint32_t handle = 0; unsigned calls = 0; bool acknowledged = false; };
void delivered(uint32_t handle, bool acknowledged, void* context) {
    Delivery& result = *static_cast<Delivery*>(context);
    result.handle = handle; result.acknowledged = acknowledged; ++result.calls;
}
size_t encode(const uint8_t key[32], const wici_link::Frame& frame, uint8_t wire[255]) {
    const size_t n = wici_link::encode(key, frame, wire, 255); assert(n); return n;
}
}  // namespace

int main() {
    static Memory memory;
    Air air;
    uint8_t ifac[16] = {}, key[32], ownSecret[64] = {}, receiverSecret[32] = {};
    for (unsigned i = 0; i < 16; ++i) ifac[i] = static_cast<uint8_t>(i);
    for (unsigned i = 0; i < 32; ++i) {
        ownSecret[i] = static_cast<uint8_t>(i + 32);
        ownSecret[i + 32] = static_cast<uint8_t>(i + 96);
        receiverSecret[i] = static_cast<uint8_t>(i + 64);
    }
    uint8_t ownPublic[32], receiverPublic[2][32], envelopeKey[32];
    publicKey(ownSecret, ownPublic); publicKey(receiverSecret, receiverPublic[0]);
    memcpy(receiverPublic[1], receiverPublic[0], 32);
    assert(envelope::deriveKey(receiverSecret, ownPublic, 100, 1, 2, 1, envelopeKey));
    assert(wici_link::deriveKey(ifac, 100, key));
    const uint16_t receivers[2] = {1, 3};
    uint8_t rootSecret[64] = {}, rootEd[32];
    for (unsigned i = 0; i < 32; ++i) rootSecret[i + 32] = static_cast<uint8_t>(i + 1);
    Ed25519::derivePublicKey(rootEd, rootSecret + 32);
    unsigned admitted = 0;
    assert(envelope::startCounters(memory));  // done when the station identity is first saved
    wici_radio::Shelter shelter(memory, {100, 2, 5, 5, 0}, 7, receivers, ifac,
                               ownSecret, receiverPublic, admit, &admitted,
                               air, randomZero, nullptr, originProof, nullptr, rootEd, beaconProof, rootEd);
    assert(shelter.begin());
    envelope::Frame sealed[2];
    assert(envelope::seal(envelopeKey, 1, 2, 1,
                          reinterpret_cast<const uint8_t*>("SA1"), 3, 236, sealed) == 1);
    wici_link::Frame frame;
    frame.type = wici_link::Type::DATA; frame.flags = wici_link::ACKREQ;
    frame.network = 100; frame.source = 5; frame.destination = 2;
    frame.ttl = 7; frame.sequence = 10; frame.length = sealed[0].length;
    memcpy(frame.payload, sealed[0].bytes, frame.length);
    uint8_t wire[255]; size_t n = encode(key, frame, wire);
    assert(shelter.receive(wire, n, 1234, 10) == wici_radio::Event::HACK_SENT);
    assert(admitted == 1 && air.hackCount == 1 && air.hackLength == 19 && air.receivedMs == 1234);
    assert(shelter.receive(wire, n, 1235, 10) == wici_radio::Event::HACK_SENT && admitted == 1);
    // A keyless replay of an admitted frame earns one HACK per 5 s, so it
    // cannot pile silence debt on the destination.
    assert(shelter.receive(wire, n, 1236, 14) == wici_radio::Event::IGNORED && air.hackCount == 2);
    assert(shelter.receive(wire, n, 1237, 15) == wici_radio::Event::HACK_SENT && air.hackCount == 3);
    wire[n - 1] ^= 1;
    assert(shelter.receive(wire, n, 1238, 15) == wici_radio::Event::REJECTED && air.hackCount == 3);

    // A transit frame is HACKed only after durable queue admission.
    frame.source = 4; frame.sequence = 11; frame.length = 25;
    memset(frame.payload, 0, frame.length);
    frame.payload[0] = 0x40; frame.payload[2] = 4; frame.payload[4] = 1;
    frame.originSignature[0] = 0xA5;
    n = encode(key, frame, wire);
    air.hackOk = false;
    assert(shelter.receive(wire, n, 1300, 11) == wici_radio::Event::ADMITTED);
    assert(air.hackCount == 4 && air.receivedMs == 1300);
    shelter.poll(1301, 11);
    assert(shelter.routes().down(4) == 4);

    wici_link::Frame beacon;
    beacon.type = wici_link::Type::BEACON; beacon.network = 100;
    beacon.source = 5; beacon.destination = wici_link::BROADCAST;
    beacon.ttl = 1; beacon.length = wici_link::BEACON_PAYLOAD;
    beacon.payload[1] = 5; beacon.payload[5] = 1;
    assert(wici_epoch::sign(rootSecret, rootEd, 100, 5, 1, beacon.payload + 9));
    assert(wici_beacon::sign(rootSecret, rootEd, 100, 5, beacon.payload,
                             beacon.payload + wici_beacon::CONTENT_BYTES));
    n = encode(key, beacon, wire);
    assert(shelter.receive(wire, n, 1400, 12, -20) == wici_radio::Event::ADMITTED);
    assert(shelter.routes().rank() == 21);  // packet SNR contributes five sixteenths
    beacon.payload[4] = 0x7f; beacon.payload[5] = 0xff;
    n = encode(key, beacon, wire);
    // Signature checks are spaced so BEACON floods cannot stall the loop.
    assert(shelter.receive(wire, n, 1401, 12) == wici_radio::Event::IGNORED);
    assert(shelter.receive(wire, n, 2400, 12) == wici_radio::Event::REJECTED);
    assert(shelter.routes().epoch() == 1);  // link-key holder cannot forge a root epoch
    beacon.payload[4] = 0; beacon.payload[5] = 1;
    beacon.payload[2] = 0; beacon.payload[3] = 1;
    n = encode(key, beacon, wire);
    assert(shelter.receive(wire, n, 3400, 12) == wici_radio::Event::REJECTED);
    assert(shelter.routes().rank() == 21);  // rank is signed by its sender
    air.dataOk = false;
    shelter.poll(1401, 12);
    assert(air.dataCount == 1 && air.dataLength == 108);
    assert(air.lastClass == wici_link::TxClass::TRANSIT);
    shelter.poll(1900, 12);
    assert(air.dataCount == 1);
    air.dataOk = true;
    shelter.poll(1901, 12);
    assert(air.dataCount == 2);
    wici_link::Frame sent;
    assert(wici_link::decode(key, 100, air.data, air.dataLength, sent));
    assert(sent.source == 2 && sent.destination == 5 && sent.hops == 1);
    const uint16_t outgoingSeq = sent.sequence;
    shelter.onTxDone(true, 1950, 12);
    shelter.poll(2549, 12);
    assert(air.dataCount == 2);
    shelter.poll(2550, 12);
    shelter.poll(3049, 12);
    assert(air.dataCount == 2);
    shelter.poll(3050, 12);
    assert(air.dataCount == 3 && wici_link::decode(key, 100, air.data, air.dataLength, sent));
    assert(sent.sequence == outgoingSeq);
    shelter.onTxDone(true, 3100, 12);
    wici_link::Frame reply;
    reply.type = wici_link::Type::HACK; reply.network = 100;
    reply.source = 5; reply.destination = 2; reply.sequence = outgoingSeq; reply.ttl = 1;
    n = encode(key, reply, wire);
    assert(shelter.receive(wire, n, 2650, 13) == wici_radio::Event::ADMITTED);
    shelter.poll(4000, 13);
    assert(air.dataCount == 3);

    // An own two-part SA1 reserves a nonce and both link sequences before TX.
    Delivery delivery;
    shelter.onDelivery(delivered, &delivery);
    uint8_t ownSa1[230]; memset(ownSa1, 'x', sizeof(ownSa1));
    assert(shelter.queueOwn(1, ownSa1, sizeof(ownSa1), 88));
    assert(!shelter.queueOwn(1, ownSa1, sizeof(ownSa1), 89));
    shelter.poll(4010, 13);
    assert(air.dataCount == 4);
    assert(air.lastClass == wici_link::TxClass::OWN);
    wici_link::Frame first;
    assert(wici_link::decode(key, 100, air.data, air.dataLength, first));
    assert(first.source == 2 && first.destination == 5 && first.length == 140 && first.ttl == 7);
    const uint16_t firstSeq = first.sequence;
    const uint16_t rankBeforeOwnTimeout = shelter.routes().rank();
    shelter.onTxDone(true, 4050, 13);
    shelter.poll(4649, 13);
    assert(air.dataCount == 4);
    shelter.poll(4650, 13);
    assert(shelter.routes().rank() > rankBeforeOwnTimeout);
    shelter.poll(5149, 13);
    assert(air.dataCount == 4);
    shelter.poll(5150, 13);
    assert(air.dataCount == 5);
    assert(wici_link::decode(key, 100, air.data, air.dataLength, sent));
    assert(sent.sequence == firstSeq && memcmp(sent.payload, first.payload, first.length) == 0);
    shelter.onTxDone(true, 5200, 13);
    reply.sequence = firstSeq;
    n = encode(key, reply, wire);
    assert(shelter.receive(wire, n, 5250, 13) == wici_radio::Event::ADMITTED);
    shelter.poll(5260, 13);
    assert(air.dataCount == 6 && wici_link::decode(key, 100, air.data, air.dataLength, sent));
    assert(sent.sequence != firstSeq && sent.length == 140);
    const uint16_t secondSeq = sent.sequence;
    shelter.onTxDone(true, 5300, 13);
    reply.sequence = firstSeq;
    n = encode(key, reply, wire);
    assert(shelter.receive(wire, n, 5350, 13) == wici_radio::Event::IGNORED);
    reply.sequence = secondSeq;
    n = encode(key, reply, wire);
    assert(shelter.receive(wire, n, 5351, 13) == wici_radio::Event::ADMITTED);
    assert(!shelter.ownBusy() && delivery.calls == 1 && delivery.handle == 88 && delivery.acknowledged);

    // Silence exception is an unacknowledged one-shot DATA transmission. The
    // station layer owns the durable three-attempt/60-second limit.
    assert(shelter.queueOwn(1, reinterpret_cast<const uint8_t*>("SA1"), 3, 90, true));
    shelter.poll(5400, 13);
    assert(air.dataCount == 7 && wici_link::decode(key, 100, air.data, air.dataLength, sent));
    assert(sent.flags == 0 && shelter.exceptionTx());
    shelter.onTxDone(true, 5450, 13);
    assert(!shelter.ownBusy() && delivery.calls == 2 && delivery.handle == 90 && delivery.acknowledged);

    // Restart recovers a queued frame and learned down route without another RX.
    frame.sequence = 12; frame.payload[8] = 1;
    n = encode(key, frame, wire);
    assert(shelter.receive(wire, n, 6100, 14) == wici_radio::Event::ADMITTED);
    Air resumedAir;
    wici_radio::Shelter resumed(memory, {100, 2, 5, 5, 0}, 7, receivers, ifac,
                               ownSecret, receiverPublic, admit, &admitted,
                               resumedAir, randomZero, nullptr, originProof, nullptr, rootEd, beaconProof, rootEd);
    assert(resumed.begin());
    resumed.poll(1, 15);
    assert(resumed.routes().down(4) == 4);
    assert(resumedAir.dataCount == 0);  // parent beacon is soft state after restart
    assert(resumed.receive(wire, n, 4101, 15) == wici_radio::Event::HACK_SENT);

    // The active station image forwards one emergency downlink broadcast once.
    static Memory floodMemory;
    Air floodAir;
    assert(envelope::startCounters(floodMemory));
    wici_radio::Shelter flood(floodMemory, {100, 2, 5, 5, 0}, 7, receivers, ifac,
                             ownSecret, receiverPublic, admit, &admitted,
                             floodAir, randomZero, nullptr, originProof, nullptr, rootEd, beaconProof, rootEd);
    assert(flood.begin());
    frame.flags = wici_link::DOWN;
    frame.source = 5; frame.destination = wici_link::BROADCAST;
    frame.sequence = 80; frame.payload[2] = 1; frame.payload[4] = 4;
    n = encode(key, frame, wire);
    assert(flood.receive(wire, n, 8000, 20) == wici_radio::Event::ADMITTED);
    flood.poll(8001, 20);
    assert(floodAir.dataCount == 1);
    assert(floodAir.lastClass == wici_link::TxClass::TRANSIT);
    assert(wici_link::decode(key, 100, floodAir.data, floodAir.dataLength, sent));
    assert(sent.destination == wici_link::BROADCAST && sent.flags == wici_link::DOWN);
    flood.onTxDone(true, 8100, 20);
    assert(flood.receive(wire, n, 8200, 20) == wici_radio::Event::IGNORED);
    // Review finding 8: an own frame that the planned parent never HACKs gets
    // three more attempts at the configured backup before Failed is reported.
    static Memory failoverMemory;
    Air failoverAir;
    assert(envelope::startCounters(failoverMemory));
    wici_radio::Shelter failover(failoverMemory, {100, 2, 5, 5, 6}, 3, receivers, ifac,
                                 ownSecret, receiverPublic, admit, &admitted, failoverAir, randomZero,
                                 nullptr, originProof, nullptr, rootEd, beaconProof, rootEd);
    assert(failover.begin());
    Delivery failoverDelivery;
    failover.onDelivery(delivered, &failoverDelivery);
    wici_link::Frame announce;
    announce.type = wici_link::Type::BEACON; announce.network = 100;
    announce.destination = wici_link::BROADCAST; announce.ttl = 1;
    announce.length = wici_link::BEACON_PAYLOAD;
    announce.payload[1] = 5; announce.payload[5] = 1;
    assert(wici_epoch::sign(rootSecret, rootEd, 100, 5, 1, announce.payload + 9));
    const uint16_t senders[2] = {5, 6};
    for (uint8_t i = 0; i < 2; ++i) {
        announce.source = senders[i];
        announce.payload[3] = static_cast<uint8_t>(i * 16);  // rank 0 for the root, 16 for the backup
        announce.payload[7] = static_cast<uint8_t>(i * 5);   // the backup's parent is the root
        assert(wici_beacon::sign(rootSecret, rootEd, 100, senders[i], announce.payload,
                                 announce.payload + wici_beacon::CONTENT_BYTES));
        n = encode(key, announce, wire);
        assert(failover.receive(wire, n, 10000 + i * 1000, 30) == wici_radio::Event::ADMITTED);
    }
    assert(failover.routes().parent() == 5);
    assert(failover.queueOwn(1, reinterpret_cast<const uint8_t*>("SA1"), 3, 77));
    uint32_t at = 12000;
    failover.poll(at, 30);
    for (unsigned attempt = 0; attempt < 6; ++attempt) {
        assert(failoverAir.dataCount == attempt + 1);
        assert(wici_link::decode(key, 100, failoverAir.data, failoverAir.dataLength, sent));
        assert(sent.destination == (attempt < 3 ? 5 : 6) && sent.ttl == 3);  // network.ttl
        if (attempt == 5) break;
        failover.onTxDone(true, at, 30);
        at += 600; failover.poll(at, 30);   // no HACK
        at += 500; failover.poll(at, 30);   // retry after backoff
    }
    failover.onTxDone(true, at, 30);
    reply.source = 6; reply.sequence = sent.sequence;
    n = encode(key, reply, wire);
    assert(failover.receive(wire, n, at + 100, 30) == wici_radio::Event::ADMITTED);
    assert(failoverDelivery.calls == 1 && failoverDelivery.handle == 77 && failoverDelivery.acknowledged);

    // A replayed first fragment earns one HACK per 5 s, like a replayed whole envelope.
    static Memory partMemory;
    Air partAir;
    assert(envelope::startCounters(partMemory));
    wici_radio::Shelter parted(partMemory, {100, 2, 5, 5, 0}, 7, receivers, ifac,
                               ownSecret, receiverPublic, admit, &admitted,
                               partAir, randomZero, nullptr, originProof, nullptr, rootEd, beaconProof, rootEd);
    assert(parted.begin());
    uint8_t longSa1[200];
    memset(longSa1, 'L', sizeof(longSa1));
    assert(envelope::seal(envelopeKey, 1, 2, 2, longSa1, sizeof(longSa1), envelope::MIN_PAYLOAD, sealed) == 2);
    wici_link::Frame part;
    part.type = wici_link::Type::DATA; part.flags = wici_link::ACKREQ;
    part.network = 100; part.source = 5; part.destination = 2;
    part.ttl = 7; part.sequence = 90; part.length = sealed[0].length;
    memcpy(part.payload, sealed[0].bytes, part.length);
    n = encode(key, part, wire);
    assert(parted.receive(wire, n, 9000, 40) == wici_radio::Event::HACK_SENT);
    assert(parted.receive(wire, n, 9001, 40) == wici_radio::Event::HACK_SENT);
    assert(parted.receive(wire, n, 9002, 44) == wici_radio::Event::IGNORED);
    assert(parted.receive(wire, n, 9003, 45) == wici_radio::Event::HACK_SENT && partAir.hackCount == 3);
}
