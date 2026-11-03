// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include <initializer_list>

#include <Crypto.h>
#include <Curve25519.h>
#include <Ed25519.h>

#include "envelope.h"
#include "fram_record.h"
#include "wici_radio.h"
#include "wici_epoch.h"
#include "wici_beacon.h"

namespace {
struct Memory : journal::Storage {
    uint8_t bytes[0x048000] = {};
    int writesLeft = -1;
    bool read(uint32_t at, uint8_t* out, size_t n) override {
        if (at > sizeof(bytes) || n > sizeof(bytes) - at) return false;
        memcpy(out, bytes + at, n); return true;
    }
    bool write(uint32_t at, const uint8_t* in, size_t n) override {
        if (writesLeft == 0 || at > sizeof(bytes) || n > sizeof(bytes) - at) return false;
        if (writesLeft > 0) --writesLeft;
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
    bool acceptOk = true;
    bool accepts(wici_link::TxClass, size_t) override { return acceptOk; }
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
// Every neighbour signs with the root's key in this check.
const uint8_t* beaconProof(uint16_t, const void* context) { return static_cast<const uint8_t*>(context); }
// A BEACON check worker that runs only when the test says so (a slow verifier).
struct Deferred : wici_radio::BeaconCheck {
    void (*check)(void*) = nullptr;
    void* job = nullptr;
    unsigned starts = 0;
    bool free = true;
    bool start(void (*c)(void*), void* j) override {
        if (!free) return false;
        assert(!check);
        check = c; job = j; ++starts; return true;
    }
    void run() { assert(check); void (*c)(void*) = check; check = nullptr; c(job); }
};
uint32_t clockMs = 0;
uint32_t stepClock() { return clockMs += 150; }  // each check reads 150 ms
struct Delivery { uint32_t handle = 0; unsigned calls = 0; bool acknowledged = false; };
void delivered(uint32_t handle, bool acknowledged, void* context) {
    Delivery& result = *static_cast<Delivery*>(context);
    result.handle = handle; result.acknowledged = acknowledged; ++result.calls;
}
size_t encode(const uint8_t key[32], const wici_link::Frame& frame, uint8_t wire[255]) {
    const size_t n = wici_link::encode(key, frame, wire, 255); assert(n); return n;
}
// A HACK repeats the start of the acknowledged bare frame's network MAC.
void setEcho(wici_link::Frame& hack, uint16_t echo) {
    hack.payload[0] = static_cast<uint8_t>(echo >> 8); hack.payload[1] = static_cast<uint8_t>(echo);
    hack.length = wici_link::HACK_ECHO;
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
                               air, randomZero, nullptr, nullptr, 0, rootEd, beaconProof, rootEd);
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
    assert(admitted == 1 && air.hackCount == 1 && air.hackLength == 21 && air.receivedMs == 1234);
    // The sender's first retry (its HACK was lost) is owed a HACK outside the repeat allowance.
    assert(shelter.receive(wire, n, 1235, 10) == wici_radio::Event::HACK_SENT && admitted == 1);
    // A keyless replay of an admitted frame earns one more HACK per 5 s, so it
    // cannot pile silence debt on the destination.
    assert(shelter.receive(wire, n, 1236, 10) == wici_radio::Event::HACK_SENT && air.hackCount == 3);
    assert(shelter.receive(wire, n, 1237, 14) == wici_radio::Event::IGNORED && air.hackCount == 3);
    assert(shelter.receive(wire, n, 1238, 15) == wici_radio::Event::HACK_SENT && air.hackCount == 4);
    wire[n - 1] ^= 1;
    assert(shelter.receive(wire, n, 1239, 15) == wici_radio::Event::REJECTED && air.hackCount == 4);

    // A transit frame is HACKed only after durable queue admission.
    frame.source = 4; frame.sequence = 11; frame.length = 25;
    memset(frame.payload, 0, frame.length);
    frame.payload[0] = 0x40; frame.payload[2] = 4; frame.payload[4] = 1;
    n = encode(key, frame, wire);
    air.hackOk = false;
    assert(shelter.receive(wire, n, 1300, 11) == wici_radio::Event::ADMITTED);
    assert(air.hackCount == 5 && air.receivedMs == 1300);
    // Review D1: the planned parent carries DATA from boot, before any BEACON;
    // without its BEACON the station has no rank and sends no BEACON.
    assert(shelter.routes().parent() == 5 && shelter.routes().rank(11) == 0xFFFF && !shelter.beacon(11));
    air.dataOk = false;
    shelter.poll(1301, 11);
    assert(shelter.routes().down(4) == 4);
    assert(air.dataCount == 1 && air.dataLength == 44);
    assert(air.lastClass == wici_link::TxClass::TRANSIT);
    wici_link::Frame refused;
    assert(wici_link::decode(key, 100, air.data, air.dataLength, refused));

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
    assert(shelter.routes().rank(12) == 21);  // packet SNR contributes five sixteenths
    beacon.payload[4] = 0x7f; beacon.payload[5] = 0xff;
    n = encode(key, beacon, wire);
    // Signature checks are spaced so BEACON floods cannot stall the loop.
    assert(shelter.receive(wire, n, 1401, 12) == wici_radio::Event::IGNORED);
    assert(shelter.receive(wire, n, 2400, 12) == wici_radio::Event::REJECTED);
    assert(shelter.routes().epoch() == 1);  // link-key holder cannot forge a root epoch
    beacon.payload[4] = 0; beacon.payload[5] = 1;
    beacon.payload[2] = 0; beacon.payload[3] = 1;
    beacon.sequence = 1;  // new, so only the signature can refuse it
    n = encode(key, beacon, wire);
    assert(shelter.receive(wire, n, 3400, 12) == wici_radio::Event::REJECTED);
    assert(shelter.routes().rank(12) == 21);  // rank is signed by its sender
    // Finding 4: a replayed BEACON (seq not newer) is refused before the
    // 1 s signature spacing, so recorded copies cannot use up the checks of
    // real BEACONs.
    beacon.payload[2] = 0; beacon.payload[3] = 0;
    assert(wici_beacon::sign(rootSecret, rootEd, 100, 5, beacon.payload,
                             beacon.payload + wici_beacon::CONTENT_BYTES));
    beacon.sequence = 0;
    n = encode(key, beacon, wire);
    assert(shelter.receive(wire, n, 4400, 12, -20) == wici_radio::Event::REJECTED);  // the admitted one, again
    beacon.sequence = 2;
    n = encode(key, beacon, wire);
    assert(shelter.receive(wire, n, 4500, 12, -20) == wici_radio::Event::ADMITTED);
    assert(shelter.routes().rank(12) == 21);
    shelter.poll(1800, 12);
    assert(air.dataCount == 1);
    air.dataOk = true;
    shelter.poll(1801, 12);
    assert(air.dataCount == 2);
    wici_link::Frame sent;
    assert(wici_link::decode(key, 100, air.data, air.dataLength, sent));
    assert(sent.source == 2 && sent.destination == 5 && sent.hops == 1);
    // Review D7, finding 3: the refused transfer was yielded and prepared
    // again for the same next hop; it keeps its seq (a refusal burns none).
    assert(sent.sequence == refused.sequence);
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
    setEcho(reply, wici_link::macEcho(air.data, air.dataLength));
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
    const uint16_t firstEcho = wici_link::macEcho(air.data, air.dataLength);
    assert(first.source == 2 && first.destination == 5 && first.length == 140 && first.ttl == 7);
    const uint16_t firstSeq = first.sequence;
    const uint16_t rankBeforeOwnTimeout = shelter.routes().rank(13);
    shelter.onTxDone(true, 4050, 13);
    shelter.poll(4649, 13);
    assert(air.dataCount == 4);
    shelter.poll(4650, 13);
    assert(shelter.routes().rank(13) > rankBeforeOwnTimeout);
    shelter.poll(5149, 13);
    assert(air.dataCount == 4);
    shelter.poll(5150, 13);
    assert(air.dataCount == 5);
    assert(wici_link::decode(key, 100, air.data, air.dataLength, sent));
    assert(sent.sequence == firstSeq && memcmp(sent.payload, first.payload, first.length) == 0);
    shelter.onTxDone(true, 5200, 13);
    reply.sequence = firstSeq;
    setEcho(reply, firstEcho);  // the retry is the same frame
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
    // A recorded HACK for an older frame with this seq (after the 16-bit seq wrapped) has another echo.
    setEcho(reply, static_cast<uint16_t>(wici_link::macEcho(air.data, air.dataLength) ^ 1));
    n = encode(key, reply, wire);
    assert(shelter.receive(wire, n, 5351, 13) == wici_radio::Event::IGNORED && shelter.ownBusy());
    setEcho(reply, wici_link::macEcho(air.data, air.dataLength));
    n = encode(key, reply, wire);
    assert(shelter.receive(wire, n, 5351, 13) == wici_radio::Event::ADMITTED);
    assert(!shelter.ownBusy() && delivery.calls == 1 && delivery.handle == 88 && delivery.acknowledged);

    // A typical REQUEST (174 B SA1, 199 B envelope) leaves as one DATA frame.
    uint8_t typical[174]; memset(typical, 't', sizeof(typical));
    assert(shelter.queueOwn(1, typical, sizeof(typical), 89));
    shelter.poll(5360, 13);
    assert(air.dataCount == 7 && wici_link::decode(key, 100, air.data, air.dataLength, sent));
    assert(sent.length == 199 && air.dataLength == 218);  // 226 B on air with the hop tag
    shelter.onTxDone(true, 5370, 13);
    reply.sequence = sent.sequence;
    setEcho(reply, wici_link::macEcho(air.data, air.dataLength));
    n = encode(key, reply, wire);
    assert(shelter.receive(wire, n, 5380, 13) == wici_radio::Event::ADMITTED);
    assert(!shelter.ownBusy() && delivery.calls == 2 && delivery.handle == 89 && delivery.acknowledged);

    // Silence exception is an unacknowledged one-shot DATA transmission. The
    // station layer owns the durable three-attempt/60-second limit.
    assert(shelter.queueOwn(1, reinterpret_cast<const uint8_t*>("SA1"), 3, 90, true));
    shelter.poll(5400, 13);
    assert(air.dataCount == 8 && wici_link::decode(key, 100, air.data, air.dataLength, sent));
    assert(sent.flags == 0 && shelter.exceptionTx());
    shelter.onTxDone(true, 5450, 13);
    assert(!shelter.ownBusy() && delivery.calls == 3 && delivery.handle == 90 && delivery.acknowledged);

    // Restart recovers a queued frame and learned down route without another RX.
    frame.sequence = 12; frame.payload[8] = 1;
    n = encode(key, frame, wire);
    assert(shelter.receive(wire, n, 6100, 14) == wici_radio::Event::ADMITTED);
    Air resumedAir;
    wici_radio::Shelter resumed(memory, {100, 2, 5, 5, 0}, 7, receivers, ifac,
                               ownSecret, receiverPublic, admit, &admitted,
                               resumedAir, randomZero, nullptr, nullptr, 0, rootEd, beaconProof, rootEd);
    assert(resumed.begin());
    resumed.poll(1, 15);
    assert(resumed.routes().down(4) == 4);
    // The planned parent survives the restart without its BEACON (D1).
    assert(resumedAir.dataCount == 1 && wici_link::decode(key, 100, resumedAir.data, resumedAir.dataLength, sent));
    assert(sent.destination == 5);
    assert(resumed.receive(wire, n, 4101, 15) == wici_radio::Event::HACK_SENT);

    // The active station image forwards one emergency downlink broadcast once.
    static Memory floodMemory;
    Air floodAir;
    assert(envelope::startCounters(floodMemory));
    wici_radio::Shelter flood(floodMemory, {100, 2, 5, 5, 0}, 7, receivers, ifac,
                             ownSecret, receiverPublic, admit, &admitted,
                             floodAir, randomZero, nullptr, nullptr, 0, rootEd, beaconProof, rootEd);
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
                                 nullptr, nullptr, 0, rootEd, beaconProof, rootEd);
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
    setEcho(reply, wici_link::macEcho(failoverAir.data, failoverAir.dataLength));
    n = encode(key, reply, wire);
    assert(failover.receive(wire, n, at + 100, 30) == wici_radio::Event::ADMITTED);
    assert(failoverDelivery.calls == 1 && failoverDelivery.handle == 77 && failoverDelivery.acknowledged);
    // Review 9: a HACK after the 600 ms still completes the frame until the
    // retry goes to the radio (a replay may have taken the owed one); once
    // the retry is handed over, only a HACK after its TX counts.
    const auto hackOfSent = [&] {
        assert(wici_link::decode(key, 100, failoverAir.data, failoverAir.dataLength, sent));
        reply.source = sent.destination; reply.sequence = sent.sequence;
        setEcho(reply, wici_link::macEcho(failoverAir.data, failoverAir.dataLength));
        return encode(key, reply, wire);
    };
    for (const uint32_t handle : {78u, 79u}) {
        assert(failover.queueOwn(1, reinterpret_cast<const uint8_t*>("SA1"), 3, handle));
        at += 1000; failover.poll(at, 31);
        const unsigned sentCount = failoverAir.dataCount;
        failover.onTxDone(true, at, 31);
        at += 600; failover.poll(at, 31);   // no HACK in time
        n = hackOfSent();
        if (handle == 79) {
            at += 500; failover.poll(at, 31);   // the retry is handed to the radio
            assert(failoverAir.dataCount == sentCount + 1);
            assert(failover.receive(wire, n, at + 1, 31) != wici_radio::Event::ADMITTED);
            failover.onTxDone(true, at + 2, 31);
        }
        assert(failover.receive(wire, n, at + 3, 31) == wici_radio::Event::ADMITTED);
        assert(failoverDelivery.handle == handle && failoverDelivery.acknowledged);
    }
    // Finding 9: a BEACON the radio would refuse (silence, budget, busy)
    // spends neither a seq nor an Ed25519 signature.
    assert(failover.routes().rank(30) != 0xFFFF && failover.beacon(30));
    assert(wici_link::decode(key, 100, failoverAir.data, failoverAir.dataLength, sent) &&
           sent.type == wici_link::Type::BEACON);
    const uint16_t beaconSeq = sent.sequence;
    const unsigned offered = failoverAir.dataCount;
    failoverAir.acceptOk = false;
    for (unsigned i = 0; i < 5; ++i) assert(!failover.beacon(30));
    assert(failoverAir.dataCount == offered);
    failoverAir.acceptOk = true;
    assert(failover.beacon(30) && wici_link::decode(key, 100, failoverAir.data, failoverAir.dataLength, sent));
    assert(sent.sequence == static_cast<uint16_t>(beaconSeq + 1));

    // A replayed first fragment earns one HACK per 5 s, like a replayed whole envelope.
    static Memory partMemory;
    Air partAir;
    assert(envelope::startCounters(partMemory));
    wici_radio::Shelter parted(partMemory, {100, 2, 5, 5, 0}, 7, receivers, ifac,
                               ownSecret, receiverPublic, admit, &admitted,
                               partAir, randomZero, nullptr, nullptr, 0, rootEd, beaconProof, rootEd);
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
    assert(parted.receive(wire, n, 9001, 40) == wici_radio::Event::HACK_SENT);  // owed: the first retry
    assert(parted.receive(wire, n, 9002, 40) == wici_radio::Event::HACK_SENT);  // the repeat allowance
    assert(parted.receive(wire, n, 9003, 44) == wici_radio::Event::IGNORED);
    assert(parted.receive(wire, n, 9004, 45) == wici_radio::Event::HACK_SENT && partAir.hackCount == 4);

    // Review D1/D8: an own SA1 leaves at once to the planned parent (no
    // BEACON yet). A radio TX failure counts like a HACK timeout: three
    // attempts, one more round of three at the parent the table holds now
    // (here the same one: TX failures do not blame the parent), then Failed.
    static Memory txMemory;
    Air txAir;
    assert(envelope::startCounters(txMemory));
    wici_radio::Shelter txFail(txMemory, {100, 2, 5, 5, 6}, 7, receivers, ifac,
                               ownSecret, receiverPublic, admit, &admitted, txAir, randomZero,
                               nullptr, nullptr, 0, rootEd, beaconProof, rootEd);
    assert(txFail.begin());
    Delivery txDelivery;
    txFail.onDelivery(delivered, &txDelivery);
    assert(txFail.queueOwn(1, reinterpret_cast<const uint8_t*>("SA1"), 3, 55));
    at = 20000;
    for (unsigned attempt = 0; attempt < 6; ++attempt) {
        txFail.poll(at, 50);
        assert(txAir.dataCount == attempt + 1 && txDelivery.calls == 0);
        assert(wici_link::decode(key, 100, txAir.data, txAir.dataLength, sent) && sent.destination == 5);
        txFail.onTxDone(false, at, 50);
        at += 500;
    }
    assert(txDelivery.calls == 1 && txDelivery.handle == 55 && !txDelivery.acknowledged && !txFail.ownBusy());
    assert(txFail.routes().parent() == 5);

    // Review D6: an uncertain FRAM write takes Shelter::ready() down: no
    // admission, no HACK, no own SA1, until begin() reads FRAM again.
    static Memory lostMemory;
    Air lostAir;
    assert(envelope::startCounters(lostMemory));
    wici_radio::Shelter lost(lostMemory, {100, 2, 5, 5, 0}, 7, receivers, ifac,
                             ownSecret, receiverPublic, admit, &admitted, lostAir, randomZero,
                             nullptr, nullptr, 0, rootEd, beaconProof, rootEd);
    assert(lost.begin() && lost.ready());
    frame.flags = wici_link::ACKREQ; frame.source = 4; frame.destination = 2;
    frame.sequence = 300; frame.payload[2] = 4; frame.payload[4] = 1; frame.payload[8] = 9;
    n = encode(key, frame, wire);
    lostMemory.writesLeft = 0;
    assert(lost.receive(wire, n, 30000, 60) == wici_radio::Event::REJECTED);
    assert(!lost.ready() && lostAir.hackCount == 0);
    lostMemory.writesLeft = -1;
    assert(lost.receive(wire, n, 30001, 60) == wici_radio::Event::REJECTED && lostAir.hackCount == 0);
    assert(!lost.queueOwn(1, reinterpret_cast<const uint8_t*>("SA1"), 3, 56));
    assert(lost.begin() && lost.ready());
    assert(lost.receive(wire, n, 30002, 60) == wici_radio::Event::HACK_SENT);

    // External review: BEACON signatures are checked off the HACK path. The
    // route table takes a BEACON only after the worker's result, in poll();
    // DATA arriving meanwhile gets its HACK at once; a second BEACON while
    // one waits is dropped; a replay is refused before the hand-off.
    static Memory asyncMemory;
    Air asyncAir;
    Deferred worker;
    assert(envelope::startCounters(asyncMemory));
    wici_radio::Shelter async(asyncMemory, {100, 2, 5, 5, 0}, 7, receivers, ifac,
                              ownSecret, receiverPublic, admit, &admitted, asyncAir, randomZero,
                              nullptr, nullptr, 0, rootEd, beaconProof, rootEd);
    assert(async.begin());
    async.useBeaconCheck(&worker, stepClock);
    wici_link::Frame signedBeacon;
    signedBeacon.type = wici_link::Type::BEACON; signedBeacon.network = 100;
    signedBeacon.source = 5; signedBeacon.destination = wici_link::BROADCAST;
    signedBeacon.ttl = 1; signedBeacon.length = wici_link::BEACON_PAYLOAD; signedBeacon.sequence = 1;
    signedBeacon.payload[1] = 5; signedBeacon.payload[5] = 1;
    assert(wici_epoch::sign(rootSecret, rootEd, 100, 5, 1, signedBeacon.payload + 9));
    assert(wici_beacon::sign(rootSecret, rootEd, 100, 5, signedBeacon.payload,
                             signedBeacon.payload + wici_beacon::CONTENT_BYTES));
    uint8_t beaconWire[255];
    const size_t beaconLength = encode(key, signedBeacon, beaconWire);
    assert(async.receive(beaconWire, beaconLength, 40000, 70, -20) == wici_radio::Event::PENDING);
    assert(worker.starts == 1 && async.routes().rank(70) == 0xFFFF);
    frame.sequence = 400; frame.payload[8] = 10;
    n = encode(key, frame, wire);
    assert(async.receive(wire, n, 40010, 70) == wici_radio::Event::HACK_SENT && asyncAir.hackCount == 1);
    signedBeacon.sequence = 2;
    n = encode(key, signedBeacon, wire);
    assert(async.receive(wire, n, 41100, 71) == wici_radio::Event::IGNORED);
    assert(worker.starts == 1 && async.beaconStats().dropped == 1);
    async.poll(41200, 71);
    assert(async.routes().rank(71) == 0xFFFF && async.beaconStats().checks == 0);  // still checking
    worker.run();
    assert(async.routes().rank(71) == 0xFFFF);  // the worker never touches the route table
    async.poll(41300, 71);
    assert(async.routes().rank(71) == 21);
    assert(async.beaconStats().checks == 1 && async.beaconStats().lastMs == 150 &&
           async.beaconStats().maxMs == 150);
    assert(async.receive(beaconWire, beaconLength, 43000, 72, -20) == wici_radio::Event::REJECTED);
    assert(worker.starts == 1);  // the replay never reached the worker
    // A forged signature: handed off, refused by the result.
    signedBeacon.sequence = 3; signedBeacon.payload[3] = 0;
    signedBeacon.payload[wici_beacon::CONTENT_BYTES] ^= 1;
    n = encode(key, signedBeacon, wire);
    assert(async.receive(wire, n, 44100, 73) == wici_radio::Event::PENDING && worker.starts == 2);
    worker.run();
    async.poll(44200, 73);
    assert(async.beaconStats().checks == 2 && async.routes().rank(73) == 21);
    // A worker that cannot take the check drops the BEACON, also counted.
    worker.free = false;
    signedBeacon.sequence = 4;
    signedBeacon.payload[wici_beacon::CONTENT_BYTES] ^= 1;
    n = encode(key, signedBeacon, wire);
    assert(async.receive(wire, n, 45200, 74) == wici_radio::Event::IGNORED);
    assert(async.beaconStats().dropped == 2 && worker.starts == 2);
    worker.free = true;
    assert(async.receive(wire, n, 46300, 74) == wici_radio::Event::PENDING && worker.starts == 3);
    worker.run();
    async.poll(46400, 74);
    assert(async.beaconStats().checks == 3 && async.beaconStats().maxMs == 150);

    // E1: delivery proof. A HACK to the root reaches the receiver and proves
    // the message; after a relay or a flood only a proof envelope does.
    static Memory proofMemory;
    Air proofAir;
    assert(envelope::startCounters(proofMemory));
    wici_radio::Shelter prover(proofMemory, {100, 2, 5, 5, 0}, 7, receivers, ifac,
                               ownSecret, receiverPublic, admit, &admitted,
                               proofAir, randomZero, nullptr, nullptr, 0, rootEd, beaconProof, rootEd);
    assert(prover.begin());
    Delivery proofDelivery;
    prover.onDelivery(delivered, &proofDelivery);
    uint8_t backKey[32];  // station 2 -> receiver 1
    assert(envelope::deriveKey(receiverSecret, ownPublic, 100, 2, 1, 1, backKey));
    uint32_t ms = 50000;
    auto arrive = [&](uint32_t counter, uint16_t from, uint8_t flags) {
        envelope::Frame message[2];
        assert(envelope::seal(envelopeKey, 1, 2, counter, reinterpret_cast<const uint8_t*>("SA1"), 3, 236,
                              message) == 1);
        wici_link::Frame data;
        data.type = wici_link::Type::DATA; data.flags = flags; data.network = 100; data.source = from;
        data.destination = flags & wici_link::ACKREQ ? 2 : wici_link::BROADCAST;
        data.ttl = 7; data.sequence = static_cast<uint16_t>(counter); data.length = message[0].length;
        memcpy(data.payload, message[0].bytes, data.length);
        uint8_t raw[255];
        const size_t length = encode(key, data, raw);
        return prover.receive(raw, length, ms, ms / 1000);
    };
    // The proof the station must send for these counters, under its own counter `own`.
    auto expectProof = [&](uint32_t own, std::initializer_list<uint32_t> counters) {
        uint8_t plain[64]; size_t length = 0;
        for (uint32_t c : counters) { fram_record::put32(plain + length, c); length += 4; }
        envelope::Frame expected[2];
        assert(envelope::seal(backKey, 2, 1, own, plain, length, 236, expected, envelope::TYPE_PROOF) == 1);
        wici_link::Frame out;
        assert(wici_link::decode(key, 100, proofAir.data, proofAir.dataLength, out));
        assert(out.source == 2 && out.destination == 5 && out.flags == wici_link::ACKREQ);
        assert(out.length == expected[0].length && !memcmp(out.payload, expected[0].bytes, out.length));
        assert(out.payload[0] == 0x41 && proofAir.lastClass == wici_link::TxClass::OWN);
        return out.sequence;
    };
    auto hackFrom5 = [&](uint16_t sequence) {
        wici_link::Frame hackFrame;
        hackFrame.type = wici_link::Type::HACK; hackFrame.network = 100; hackFrame.source = 5;
        hackFrame.destination = 2; hackFrame.sequence = sequence; hackFrame.ttl = 1;
        setEcho(hackFrame, wici_link::macEcho(proofAir.data, proofAir.dataLength));
        uint8_t raw[255];
        const size_t length = encode(key, hackFrame, raw);
        assert(prover.receive(raw, length, ms, ms / 1000) == wici_radio::Event::ADMITTED);
    };
    auto step = [&]() { ms += 10; prover.poll(ms, ms / 1000); };
    auto sentOk = [&]() { ms += 10; prover.onTxDone(true, ms, ms / 1000); };
    // From the root with ACKREQ: its HACK is the proof, no envelope follows.
    assert(arrive(5, 5, wici_link::ACKREQ) == wici_radio::Event::HACK_SENT);
    step();
    assert(proofAir.dataCount == 0 && !prover.ownBusy());
    // From the root, but the radio refused the HACK (silence, deadline): the root never saw it, so a proof follows.
    proofAir.hackOk = false;
    assert(arrive(4, 5, wici_link::ACKREQ) == wici_radio::Event::ADMITTED);
    proofAir.hackOk = true;
    step();
    assert(proofAir.dataCount == 1);
    uint16_t refusedSeq = expectProof(0, {4});
    sentOk();
    hackFrom5(refusedSeq);
    // Through relay 7: the station proves counter 6 to the receiver, via its parent.
    assert(arrive(6, 7, wici_link::ACKREQ) == wici_radio::Event::HACK_SENT);
    step();
    assert(proofAir.dataCount == 2 && prover.ownBusy());
    uint16_t proofSeq = expectProof(1, {6});
    // A REQUEST waits behind the proof (a busy link is no failed try), and
    // the proof's end reports nothing to the station application.
    assert(!prover.queueOwn(1, reinterpret_cast<const uint8_t*>("SA1"), 3, 91));
    sentOk();
    hackFrom5(proofSeq);
    assert(!prover.ownBusy() && proofDelivery.calls == 0);
    // A repeat resolves nothing new: no second proof.
    assert(arrive(6, 7, wici_link::ACKREQ) == wici_radio::Event::HACK_SENT);
    step();
    assert(proofAir.dataCount == 2);
    // A flood (no HACK at all) and a relay: one proof names both counters.
    assert(arrive(7, 5, wici_link::DOWN) == wici_radio::Event::ADMITTED);
    assert(arrive(8, 7, wici_link::ACKREQ) == wici_radio::Event::HACK_SENT);
    step();
    assert(proofAir.dataCount == 3);
    proofSeq = expectProof(2, {7, 8});
    sentOk();
    hackFrom5(proofSeq);
    // The own SA1 goes first; no proof starts in silence; a full list drops its oldest.
    assert(prover.queueOwn(1, reinterpret_cast<const uint8_t*>("SA1"), 3, 92));
    for (uint32_t c = 10; c < 27; ++c) assert(arrive(c, 7, wici_link::ACKREQ) == wici_radio::Event::HACK_SENT);
    assert(prover.proofsDropped() == 1);
    step();
    wici_link::Frame own;
    assert(proofAir.dataCount == 4 && wici_link::decode(key, 100, proofAir.data, proofAir.dataLength, own));
    assert(own.payload[0] == 0x40);  // the station's SA1, not the proof
    sentOk();
    hackFrom5(own.sequence);
    assert(proofDelivery.calls == 1 && proofDelivery.handle == 92);
    proofAir.acceptOk = false;
    step();
    assert(proofAir.dataCount == 4 && !prover.ownBusy());
    proofAir.acceptOk = true;
    step();
    assert(proofAir.dataCount == 5);
    expectProof(4, {11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26});
}
