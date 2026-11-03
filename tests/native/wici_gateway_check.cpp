// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include "wici_beacon.h"
#include "wici_gateway.h"

namespace {
struct Air : wici_gateway::Air {
    unsigned data = 0, hacks = 0;
    uint32_t stamp = 0;
    bool hackOk = true, dataOk = true;
    uint8_t last[255] = {};
    size_t lastLength = 0;
    wici_link::TxClass lastClass = wici_link::TxClass::TRANSIT;
    bool sendData(const uint8_t* wire, size_t n, wici_link::TxClass traffic) override {
        lastClass = traffic;
        assert(n >= 19 && n <= 255); memcpy(last, wire, n); lastLength = n; ++data; return dataOk;
    }
    bool sendHack(const uint8_t*, size_t n, uint32_t ms) override {
        assert(n == 21); ++hacks; stamp = ms; return hackOk;
    }
    bool acceptOk = true;
    size_t asked = 0;  // radio length of the last accepts() question
    bool accepts(wici_link::TxClass, size_t radioLength) override { asked = radioLength; return acceptOk; }
};
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
size_t encode(const uint8_t key[32], const wici_link::Frame& frame, uint8_t wire[255]) {
    const size_t n = wici_link::encode(key, frame, wire, 255); assert(n); return n;
}
// A HACK repeats the start of the acknowledged DATA's network MAC (encoding is deterministic).
void setEcho(const uint8_t key[32], wici_link::Frame& hack, const wici_link::Frame& data) {
    uint8_t bare[255];
    const uint16_t echo = wici_link::macEcho(bare, encode(key, data, bare));
    hack.payload[0] = static_cast<uint8_t>(echo >> 8); hack.payload[1] = static_cast<uint8_t>(echo);
    hack.length = wici_link::HACK_ECHO;
}
// The next KISS frame to the laptop: its command byte and unescaped bytes.
size_t take(kiss::Port& port, uint8_t& command, uint8_t out[255]) {
    size_t length = 0, n = 0;
    const uint8_t* bytes = port.output(length);
    assert(length >= 3 && bytes[0] == kiss::FEND);
    command = bytes[1];
    size_t i = 2;
    for (; bytes[i] != kiss::FEND; ++i) {
        uint8_t b = bytes[i];
        if (b == kiss::FESC) b = bytes[++i] == kiss::TFEND ? kiss::FEND : kiss::FESC;
        out[n++] = b;
    }
    port.consume(i + 1);
    return n;
}
}  // namespace

int main() {
    static Memory memory;
    kiss::Port port;
    Air air;
    uint8_t ifac[16] = {}, key[32], wire[255];
    uint8_t identity[64] = {};
    for (unsigned i = 0; i < 16; ++i) ifac[i] = static_cast<uint8_t>(i);
    for (unsigned i = 0; i < 32; ++i) identity[i + 32] = static_cast<uint8_t>(i + 1);
    assert(wici_link::deriveKey(ifac, 100, key));
    const config::Behind plan[] = {{7, 4}};  // the root's network plan: station 7 behind neighbour 4
    wici_gateway::Root root(memory, port, air, 100, 5, ifac, identity, nullptr, 0, plan, 1);
    assert(root.begin(7) && root.ready());
    // Review D4: no BEACON while the laptop's port is closed (no HACK possible).
    assert(!root.beacon() && air.data == 0);
    root.setUsbOpen(true);
    assert(root.beacon());
    root.setUsbOpen(false);
    assert(air.lastClass == wici_link::TxClass::BEACON);
    wici_link::Frame observed;
    assert(wici_link::decode(key, 100, air.last, air.lastLength, observed));
    assert(observed.type == wici_link::Type::BEACON && observed.source == 5 &&
           observed.payload[1] == 5 && observed.payload[5] == 7);
    // Finding 9: a BEACON the radio would refuse (silence, budget) spends
    // neither a seq nor a signature; the next accepted one follows at once.
    const uint16_t beaconSeq = observed.sequence;
    root.setUsbOpen(true);
    air.acceptOk = false;
    for (unsigned i = 0; i < 5; ++i) assert(!root.beacon());
    assert(air.data == 1 && air.asked == wici_link::BEACON_FRAME);
    air.acceptOk = true;
    assert(root.beacon() && wici_link::decode(key, 100, air.last, air.lastLength, observed));
    assert(observed.sequence == static_cast<uint16_t>(beaconSeq + 1));
    root.setUsbOpen(false);
    uint8_t command = 0, returned[255];
    wici_link::Frame frame;
    frame.type = wici_link::Type::DATA; frame.flags = wici_link::ACKREQ;
    frame.network = 100; frame.source = 4; frame.destination = 5;
    frame.sequence = 41; frame.ttl = 7; frame.length = 25;
    frame.payload[0] = 0x40; frame.payload[2] = 4; frame.payload[4] = 1;
    size_t n = encode(key, frame, wire);
    assert(root.radio(wire, n, 1000) == wici_gateway::Event::REJECTED);  // no USB
    root.setUsbOpen(true);
    wici_link::Frame emergency = frame;
    emergency.source = 1; emergency.flags = wici_link::ACKREQ | wici_link::DOWN;
    emergency.payload[2] = 1; emergency.payload[4] = 9;
    emergency.sequence = 39;
    size_t emergencyLength = encode(key, emergency, wire);
    assert(root.host(wire, emergencyLength, 900, 1) == wici_gateway::Event::QUEUED);
    assert(air.lastClass == wici_link::TxClass::TRANSIT);
    assert(wici_link::decode(key, 100, air.last, air.lastLength, observed));
    assert(observed.destination == wici_link::BROADCAST && observed.flags == wici_link::DOWN);
    assert(port.pendingBytes() == 0);
    root.onTxDone(true, 950);
    size_t sentLength = 0;
    port.output(sentLength);
    port.consume(sentLength);
    // Review D11: a downward frame the root cannot send (here: flooded inside
    // 120 s) goes back to the laptop at once, bytes unchanged, command 0x01.
    assert(root.host(wire, emergencyLength, 901, 1) == wici_gateway::Event::REFUSED);
    assert(take(port, command, returned) == emergencyLength && command == wici_gateway::CMD_REFUSED &&
           memcmp(returned, wire, emergencyLength) == 0);
    n = encode(key, frame, wire);
    wire[n - 1] ^= 1;
    assert(root.radio(wire, n, 1000) == wici_gateway::Event::REJECTED);  // bad MAC
    wire[n - 1] ^= 1;
    assert(root.radio(wire, n, 1000) == wici_gateway::Event::FORWARDED);
    const uint16_t dataEcho = wici_link::macEcho(wire, n);
    size_t encodedLength = 0;
    const uint8_t* encoded = port.output(encodedLength);
    assert(encodedLength >= n + 3 && encoded[0] == kiss::FEND && encoded[1] == kiss::CMD_DATA);
    port.consume(encodedLength);
    wici_link::Frame hack;
    hack.type = wici_link::Type::HACK; hack.network = 100;
    hack.source = 5; hack.destination = 4; hack.sequence = 42; hack.ttl = 1;
    hack.payload[0] = static_cast<uint8_t>(dataEcho >> 8); hack.payload[1] = static_cast<uint8_t>(dataEcho);
    hack.length = wici_link::HACK_ECHO;
    n = encode(key, hack, wire);
    assert(root.host(wire, n, 1010, 1010 / 1000) == wici_gateway::Event::REJECTED);
    hack.sequence = 41;
    hack.payload[1] ^= 1;  // the echo of another frame with this seq
    n = encode(key, hack, wire);
    assert(root.host(wire, n, 1010, 1010 / 1000) == wici_gateway::Event::REJECTED && air.hacks == 0);
    hack.payload[1] ^= 1;
    n = encode(key, hack, wire);
    assert(root.host(wire, n, 1200, 1200 / 1000) == wici_gateway::Event::REJECTED);  // expired
    air.hackOk = false;
    assert(root.host(wire, n, 1100, 1100 / 1000) == wici_gateway::Event::REJECTED && air.hacks == 1);
    air.hackOk = true;
    assert(root.host(wire, n, 1101, 1101 / 1000) == wici_gateway::Event::HACK_SENT);
    assert(air.hacks == 2 && air.stamp == 1000);
    assert(root.down(4) == 4);
    assert(root.host(wire, n, 1102, 1102 / 1000) == wici_gateway::Event::REJECTED);
    hack.source = 4; hack.destination = 5;
    n = encode(key, hack, wire);
    assert(root.radio(wire, n, 1300) == wici_gateway::Event::FORWARDED);  // radio HACK has no pending admission
    assert(root.host(wire, n, 1301, 1301 / 1000) == wici_gateway::Event::REJECTED);
    port.output(encodedLength);
    port.consume(encodedLength);

    frame.source = 1; frame.destination = 5; frame.flags = wici_link::ACKREQ | wici_link::DOWN;
    frame.payload[2] = 1; frame.payload[4] = 4; frame.sequence = 77;
    n = encode(key, frame, wire);
    assert(root.host(wire, n, 1400, 1400 / 1000) == wici_gateway::Event::QUEUED && air.data == 4);
    assert(port.pendingBytes() == 0);  // scheduler admission is not radio TX
    assert(root.host(wire, n, 1401, 1401 / 1000) == wici_gateway::Event::REFUSED);  // transmitter busy
    assert(take(port, command, returned) == n && command == wici_gateway::CMD_REFUSED);
    assert(wici_link::decode(key, 100, air.last, air.lastLength, observed));
    assert(observed.source == 5 && observed.destination == 4 && observed.sequence != 77 &&
           observed.hops == 1 && memcmp(observed.payload, frame.payload, frame.length) == 0);
    root.onTxDone(true, 1450);
    assert(port.pendingBytes() > 0);  // only actual TX starts laptop's HACK timer
    port.output(encodedLength);
    port.consume(encodedLength);
    assert(port.pendingBytes() == 0);
    assert(root.host(wire, n, 1401, 1401 / 1000) == wici_gateway::Event::QUEUED);
    root.onTxDone(false, 1470);  // failed TX: no echo, the original bytes are refused
    assert(take(port, command, returned) == n && command == wici_gateway::CMD_REFUSED &&
           memcmp(returned, wire, n) == 0 && port.pendingBytes() == 0);
    air.dataOk = false;  // silence or a missing pair key
    assert(root.host(wire, n, 1480, 1) == wici_gateway::Event::REFUSED);
    assert(take(port, command, returned) == n && command == wici_gateway::CMD_REFUSED);
    air.dataOk = true;
    const uint8_t queued[] = {kiss::FEND, kiss::CMD_DATA, 1, kiss::FEND};
    port.feed(queued, sizeof(queued), 1400);
    assert(port.buffered() == 1);
    root.setUsbOpen(false);
    assert(port.buffered() == 0);
    root.setUsbOpen(true);
    frame.source = 4; frame.destination = 5; frame.flags = wici_link::ACKREQ;
    n = encode(key, frame, wire);
    assert(root.host(wire, n, 1401, 1401 / 1000) == wici_gateway::Event::REJECTED);
    assert(root.radio(wire, n, 1500) == wici_gateway::Event::FORWARDED);
    root.setUsbOpen(false);
    root.setUsbOpen(true);
    hack.source = 5; hack.destination = 4; hack.sequence = 77;
    setEcho(key, hack, frame);
    n = encode(key, hack, wire);
    assert(root.host(wire, n, 1501, 1501 / 1000) == wici_gateway::Event::REJECTED);
    frame.source = 1; frame.destination = 5;
    frame.flags = wici_link::ACKREQ | wici_link::DOWN;
    n = encode(key, frame, wire);
    for (uint32_t attempt = 0; attempt < 3; ++attempt) {
        const uint32_t at = 2000 + attempt * 1000;
        assert(root.host(wire, n, at, at / 1000) == wici_gateway::Event::QUEUED);
        assert(wici_link::decode(key, 100, air.last, air.lastLength, observed));
        assert(observed.destination == 4 && observed.flags == (wici_link::ACKREQ | wici_link::DOWN));
        root.onTxDone(true, at + 50);
    }
    assert(root.host(wire, n, 5000, 5) == wici_gateway::Event::QUEUED);
    assert(root.down(4) == wici_link::BROADCAST);
    assert(wici_link::decode(key, 100, air.last, air.lastLength, observed));
    assert(observed.destination == wici_link::BROADCAST && observed.flags == wici_link::DOWN);
    root.onTxDone(true, 5050);
    // Review 3/4: the radio frame alone proves nothing (it may be replayed);
    // after `forget`, the laptop HACK of a frame relayed by neighbour 4
    // restores the route to 4 itself, here for another envelope sender (7).
    while (port.pendingBytes()) take(port, command, returned);
    frame.source = 4; frame.destination = 5; frame.flags = wici_link::ACKREQ;
    frame.payload[2] = 7; frame.payload[4] = 1; frame.sequence = 60;
    n = encode(key, frame, wire);
    assert(root.radio(wire, n, 5100) == wici_gateway::Event::FORWARDED);
    assert(root.down(4) == wici_link::BROADCAST);
    hack.source = 5; hack.destination = 4; hack.sequence = 60;
    setEcho(key, hack, frame);
    n = encode(key, hack, wire);
    assert(root.host(wire, n, 5150, 5) == wici_gateway::Event::HACK_SENT);
    assert(root.down(4) == 4 && root.down(7) == 4);
    // Finding 1: the laptop HACK also comes for a recorded copy of an old
    // envelope (a duplicate), which a captured neighbour can relay under its
    // own l_src. The root learns the sender behind that neighbour only as the
    // plan allows, like every relay: station 8 is not behind 4.
    frame.payload[2] = 8; frame.sequence = 64;
    n = encode(key, frame, wire);
    assert(root.radio(wire, n, 5160) == wici_gateway::Event::FORWARDED);
    hack.sequence = 64;
    setEcho(key, hack, frame);
    n = encode(key, hack, wire);
    assert(root.host(wire, n, 5170, 5) == wici_gateway::Event::HACK_SENT);
    assert(root.down(8) == wici_link::BROADCAST && root.down(4) == 4 && root.ready());

    // Review 10, round 3 (6): a downlink already handed to the radio stays
    // pending through begin() (the radio may still be sending it) and
    // through closing the port; only its TX result reaches the laptop, so the
    // laptop never resends a frame that went on air.
    while (port.pendingBytes()) take(port, command, returned);
    frame.source = 1; frame.destination = 5; frame.flags = wici_link::ACKREQ | wici_link::DOWN;
    frame.payload[2] = 1; frame.payload[4] = 4; frame.sequence = 61;
    n = encode(key, frame, wire);
    assert(root.host(wire, n, 5200, 5) == wici_gateway::Event::QUEUED);
    assert(root.begin(7) && port.pendingBytes() == 0);
    assert(root.host(wire, n, 5201, 5) == wici_gateway::Event::REFUSED);  // the transmitter is still busy
    take(port, command, returned);
    root.onTxDone(true, 5250);
    assert(take(port, command, returned) > 0 && command == kiss::CMD_DATA);  // the echo
    frame.sequence = 69; frame.payload[8] = 6;
    n = encode(key, frame, wire);
    assert(root.host(wire, n, 5900, 5) == wici_gateway::Event::QUEUED);
    root.setUsbOpen(false);
    root.setUsbOpen(true);
    root.onTxDone(false, 5950);
    assert(take(port, command, returned) == n && command == wici_gateway::CMD_REFUSED);

    // Review D6: an uncertain FRAM write takes ready() down (no forwarding,
    // no BEACON, downlink refused) until begin() reads FRAM again.
    frame.source = 6; frame.destination = 5; frame.flags = wici_link::ACKREQ;
    frame.payload[2] = 6; frame.payload[4] = 1; frame.sequence = 62;
    n = encode(key, frame, wire);
    assert(root.radio(wire, n, 6000) == wici_gateway::Event::FORWARDED);
    take(port, command, returned);
    hack.destination = 6; hack.sequence = 62;
    setEcho(key, hack, frame);
    n = encode(key, hack, wire);
    memory.writesLeft = 0;
    assert(root.host(wire, n, 6050, 6) == wici_gateway::Event::HACK_SENT);  // route write fails after the HACK
    assert(!root.ready() && !root.beacon());
    assert(root.radio(wire, n, 6060) == wici_gateway::Event::REJECTED);
    frame.source = 1; frame.flags = wici_link::ACKREQ | wici_link::DOWN;
    frame.payload[2] = 1; frame.payload[4] = 4; frame.sequence = 63;
    n = encode(key, frame, wire);
    assert(root.host(wire, n, 6100, 6) == wici_gateway::Event::REFUSED);
    assert(take(port, command, returned) == n && command == wici_gateway::CMD_REFUSED);
    memory.writesLeft = -1;
    assert(root.begin(7) && root.ready() && root.down(4) == 4);
    assert(root.host(wire, n, 6200, 6) == wici_gateway::Event::QUEUED);

    // Finding 11: while the previous downward frame waits for its HACK (600 ms
    // from its TX), the next one is refused to the laptop; then it goes.
    root.onTxDone(true, 6250);
    while (port.pendingBytes()) take(port, command, returned);
    frame.sequence = 65; frame.payload[8] = 5;
    n = encode(key, frame, wire);
    assert(root.host(wire, n, 6849, 6) == wici_gateway::Event::REFUSED);
    assert(take(port, command, returned) == n && command == wici_gateway::CMD_REFUSED);
    assert(root.host(wire, n, 6850, 6) == wici_gateway::Event::QUEUED);
    root.onTxDone(true, 6900);
    while (port.pendingBytes()) take(port, command, returned);

    // Finding 2: a flood refused by the radio after its durable marker was
    // never on air, so the laptop's next attempt of that envelope goes out.
    // A radio that would refuse at once (accepts) costs no marker and no seq.
    frame.payload[4] = 30; frame.sequence = 66;  // no route to 30: flood
    n = encode(key, frame, wire);
    air.acceptOk = false;
    assert(root.host(wire, n, 8000, 8) == wici_gateway::Event::REFUSED);
    assert(air.asked == n);  // a flood carries no pairwise tag
    take(port, command, returned);
    air.acceptOk = true; air.dataOk = false;
    assert(root.host(wire, n, 8001, 8) == wici_gateway::Event::REFUSED);
    take(port, command, returned);
    air.dataOk = true;
    assert(root.host(wire, n, 8002, 8) == wici_gateway::Event::QUEUED);
    assert(wici_link::decode(key, 100, air.last, air.lastLength, observed) &&
           observed.destination == wici_link::BROADCAST);
    root.onTxDone(true, 8050);
    take(port, command, returned);
    assert(root.host(wire, n, 8100, 8) == wici_gateway::Event::REFUSED);  // flooded: once in 120 s
    take(port, command, returned);
    // Round 3 (4): a flood TX the radio accepted but failed put nothing
    // complete on air; the laptop's next attempt of it goes out.
    frame.payload[4] = 32; frame.sequence = 68;
    n = encode(key, frame, wire);
    assert(root.host(wire, n, 8150, 8) == wici_gateway::Event::QUEUED);
    root.onTxDone(false, 8160);
    assert(take(port, command, returned) == n && command == wici_gateway::CMD_REFUSED);
    assert(root.host(wire, n, 8170, 8) == wici_gateway::Event::QUEUED);
    root.onTxDone(true, 8180);
    take(port, command, returned);
    // After a restart a marker is never the root's own: power loss between
    // the marker and TX may lose a flood, never send it twice.
    frame.payload[4] = 31; frame.sequence = 67;
    n = encode(key, frame, wire);
    air.dataOk = false;
    assert(root.host(wire, n, 8200, 8) == wici_gateway::Event::REFUSED);
    take(port, command, returned);
    air.dataOk = true;
    assert(root.begin(7));
    assert(root.host(wire, n, 8201, 8) == wici_gateway::Event::REFUSED);
    take(port, command, returned);

    // External review: the laptop HACK alone proves neither freshness nor the
    // envelope sender. The root learns the route to the sender only on the
    // "learn" HACK (KISS 0x00: a new envelope part the envelope MAC
    // authenticated), which may replace an older route (the station moved);
    // KISS 0x02 HACKs without learning (duplicate, set aside, unauthenticated).
    // The neighbour's route to itself (pairwise tag) is learned on both.
    static Memory learnMemory;
    kiss::Port learnPort;
    Air learnAir;
    const config::Behind both[] = {{7, 4}, {7, 3}};  // station 7 may stand behind 4 or 3
    wici_gateway::Root learner(learnMemory, learnPort, learnAir, 100, 5, ifac, identity, nullptr, 0, both, 2);
    assert(learner.begin(7));
    learner.setUsbOpen(true);
    const auto relayed = [&](uint16_t via, uint16_t sequence, uint32_t at, uint8_t hackCommand) {
        wici_link::Frame up = frame;
        up.source = via; up.destination = 5; up.flags = wici_link::ACKREQ;
        up.payload[2] = 7; up.payload[4] = 1; up.sequence = sequence;
        size_t length = encode(key, up, wire);
        assert(learner.radio(wire, length, at) == wici_gateway::Event::FORWARDED);
        while (learnPort.pendingBytes()) take(learnPort, command, returned);
        wici_link::Frame reply = hack;
        reply.source = 5; reply.destination = via; reply.sequence = sequence;
        setEcho(key, reply, up);
        length = encode(key, reply, wire);
        return learner.host(wire, length, at + 50, at / 1000, hackCommand);
    };
    assert(relayed(4, 100, 10000, wici_gateway::CMD_HACK_ONLY) == wici_gateway::Event::HACK_SENT);
    assert(learnAir.hacks == 1 && learner.down(4) == 4 && learner.down(7) == wici_link::BROADCAST);
    assert(relayed(4, 101, 11000, kiss::CMD_DATA) == wici_gateway::Event::HACK_SENT);
    assert(learner.down(7) == 4);
    assert(relayed(3, 102, 12000, wici_gateway::CMD_HACK_ONLY) == wici_gateway::Event::HACK_SENT);
    assert(learner.down(7) == 4 && learner.down(3) == 3);  // a duplicate via 3 moves nothing
    assert(relayed(3, 103, 13000, kiss::CMD_DATA) == wici_gateway::Event::HACK_SENT);
    assert(learner.down(7) == 3 && learnAir.hacks == 4);   // fresh and authenticated: the station moved
    // Any other command, and 0x02 with anything but a HACK, is rejected
    // without a refusal; on the port, unknown commands stay ignored.
    assert(relayed(4, 104, 14000, 0x05) == wici_gateway::Event::REJECTED && learnAir.hacks == 4);
    wici_link::Frame downlink = frame;
    downlink.source = 1; downlink.destination = 5; downlink.flags = wici_link::ACKREQ | wici_link::DOWN;
    downlink.payload[2] = 1; downlink.payload[4] = 7; downlink.sequence = 105;
    n = encode(key, downlink, wire);
    assert(learner.host(wire, n, 15000, 15, wici_gateway::CMD_HACK_ONLY) == wici_gateway::Event::REJECTED);
    assert(learnPort.pendingBytes() == 0 && learnAir.data == 0);
    const uint8_t kissFrames[] = {kiss::FEND, 0x05, 0x11, kiss::FEND, 0x02, 0x22, 0x23, kiss::FEND};
    learnPort.feed(kissFrames, sizeof(kissFrames), 16000);
    const uint8_t* packet = nullptr;
    size_t packetLength = 0;
    assert(learnPort.buffered() == 1 && learnPort.counters().commands == 1);
    assert(learnPort.peek(packet, packetLength, command) && command == wici_gateway::CMD_HACK_ONLY &&
           packetLength == 2 && packet[0] == 0x22);
    kiss::Port plain;  // a port without acceptCommand (Reticulum node) ignores 0x02 as before
    plain.setOpen(true);
    plain.feed(kissFrames, sizeof(kissFrames), 16000);
    assert(plain.buffered() == 0 && plain.counters().commands == 2);

    // Final review L5: the root forgets a route after 3 downward frames to
    // that station in a row without HACK, counted per route. A delivered
    // frame to another station in between restarts nothing (routes: 4 via 4,
    // 3 via 3).
    // Drained whole (output() and consume()): after the full buffer below the
    // ring wraps, and take() reads one contiguous frame.
    const auto drain = [&] {
        size_t length = 0;
        while (learnPort.pendingBytes()) { learnPort.output(length); learnPort.consume(length); }
    };
    const auto sendDown = [&](uint16_t recipient, uint16_t sequence, uint32_t at) {
        wici_link::Frame d = downlink;
        d.payload[4] = static_cast<uint8_t>(recipient); d.sequence = sequence;
        const size_t length = encode(key, d, wire);
        assert(learner.host(wire, length, at, at / 1000) == wici_gateway::Event::QUEUED);
        learner.onTxDone(true, at + 50);
        drain();
        wici_link::Frame sent;
        assert(wici_link::decode(key, 100, learnAir.last, learnAir.lastLength, sent));
        return sent;
    };
    const auto hackFor = [&](const wici_link::Frame& sent, uint16_t sequence) {
        wici_link::Frame reply = hack;
        reply.source = sent.destination; reply.destination = 5; reply.sequence = sequence;
        setEcho(key, reply, sent);
        const size_t length = encode(key, reply, wire);
        return learner.radio(wire, length, 0);
    };
    assert(learner.down(4) == 4 && learner.down(3) == 3);
    sendDown(4, 110, 20000);
    sendDown(4, 111, 21000);                       // failure 1 of the route to 4
    wici_link::Frame toThree = sendDown(3, 112, 22000);  // failure 2
    assert(hackFor(toThree, toThree.sequence) == wici_gateway::Event::FORWARDED);
    drain();
    sendDown(4, 113, 23000);
    sendDown(3, 114, 24000);                       // failure 3: the route to 4 is gone
    assert(learner.down(4) == wici_link::BROADCAST && learner.down(3) == 3);
    // L9: the HACK of the pending downward frame counts even when the KISS
    // buffer to the laptop is full (the frame itself is not passed on).
    sendDown(3, 115, 25000);                       // failure 1 of the route to 3
    toThree = sendDown(3, 116, 26000);             // failure 2
    unsigned filled = 0;
    while (hackFor(toThree, static_cast<uint16_t>(toThree.sequence + 1000)) == wici_gateway::Event::FORWARDED)
        assert(++filled < 1000);
    assert(hackFor(toThree, toThree.sequence) == wici_gateway::Event::REJECTED);
    drain();
    sendDown(3, 117, 27000);                       // the previous frame was delivered
    sendDown(3, 118, 28000);                       // failure 1 again
    assert(learner.down(3) == 3 && learner.ready());

    // Review 8: the laptop retries with the root's echo of the attempt. To
    // the same next hop the root sends those bytes again (same seq and MAC,
    // so the hop owes them its HACK even after replays used up its repeat
    // limit) and burns no seq; once the route is gone the part floods.
    wici_link::Frame previous;
    assert(wici_link::decode(key, 100, learnAir.last, learnAir.lastLength, previous));
    assert(hackFor(previous, previous.sequence) == wici_gateway::Event::FORWARDED);
    drain();
    const wici_link::Frame attempt = sendDown(3, 119, 30000);
    uint8_t echo[255];
    const size_t echoLength = learnAir.lastLength;
    memcpy(echo, learnAir.last, echoLength);
    const uint32_t retries[] = {30700, 31400};
    for (const uint32_t at : retries) {   // no HACK: failures 1 and 2 of the route to 3
        assert(learner.host(echo, echoLength, at, at / 1000) == wici_gateway::Event::QUEUED);
        assert(learnAir.lastLength == echoLength && !memcmp(learnAir.last, echo, echoLength));
        learner.onTxDone(true, at + 50);
        drain();
    }
    assert(learner.host(echo, echoLength, 32100, 32) == wici_gateway::Event::QUEUED);  // failure 3
    assert(learner.down(3) == wici_link::BROADCAST);
    assert(wici_link::decode(key, 100, learnAir.last, learnAir.lastLength, observed));
    assert(observed.destination == wici_link::BROADCAST && observed.flags == wici_link::DOWN &&
           observed.source == 5 && observed.hops == 1 && observed.sequence == attempt.sequence + 1 &&
           observed.length == attempt.length && !memcmp(observed.payload, attempt.payload, attempt.length));
    learner.onTxDone(true, 32150);
    drain();
    // Flooded in the last 120 s: refused, with the laptop's bytes unchanged.
    assert(learner.host(echo, echoLength, 32200, 32) == wici_gateway::Event::REFUSED);
    assert(take(learnPort, command, returned) == echoLength && command == wici_gateway::CMD_REFUSED &&
           !memcmp(returned, echo, echoLength));
    // An echo to the root itself or one that never left it (no hop) is a laptop fault.
    wici_link::Frame bad = attempt;
    bad.destination = 5;
    n = encode(key, bad, wire);
    assert(learner.host(wire, n, 32300, 32) == wici_gateway::Event::REJECTED && !learnPort.pendingBytes());
    bad = attempt;
    bad.hops = 0;
    n = encode(key, bad, wire);
    assert(learner.host(wire, n, 32300, 32) == wici_gateway::Event::REJECTED && !learnPort.pendingBytes());

    // Review 1/11a: BEACON schedule. A change or retry is pushed to 60 s
    // after the last BEACON only when that is later, then jittered 0-4 s;
    // a long-silent station is not scheduled in the past.
    assert(wici_beacon::jittered(500000, 0, false, 4000) == 504000);
    assert(wici_beacon::jittered(500000, 100000, true, 4001) == 500000);   // 400 s after the last one
    assert(wici_beacon::jittered(500000, 470000, true, 1234) == 531234);   // within 60 s
    assert(wici_beacon::jittered(505000, 470000, true, 7) == 530007);      // a retry 5 s later
    assert(wici_beacon::burstAllowed(1000, 0, false));
    assert(!wici_beacon::burstAllowed(100000, 50000, true));
    assert(wici_beacon::burstAllowed(110000, 50000, true));
    // Finding 10: a rank change earns an extra BEACON only from one ETX on,
    // or when the rank appears or lapses.
    assert(!wici_beacon::rankMoved(40, 32) && !wici_beacon::rankMoved(32, 47));
    assert(wici_beacon::rankMoved(48, 32) && wici_beacon::rankMoved(32, 48));
    assert(wici_beacon::rankMoved(0xFFFF, 32) && wici_beacon::rankMoved(32, 0xFFFF));
    assert(!wici_beacon::rankMoved(0xFFFF, 0xFFFF));
}
