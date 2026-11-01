// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include "wici_gateway.h"

namespace {
struct Air : wici_gateway::Air {
    unsigned data = 0, hacks = 0;
    uint32_t stamp = 0;
    bool hackOk = true;
    uint8_t last[255] = {};
    size_t lastLength = 0;
    wici_link::TxClass lastClass = wici_link::TxClass::TRANSIT;
    bool sendData(const uint8_t* wire, size_t n, wici_link::TxClass traffic) override {
        lastClass = traffic;
        assert(n >= 19 && n <= 255); memcpy(last, wire, n); lastLength = n; ++data; return true;
    }
    bool sendHack(const uint8_t*, size_t n, uint32_t ms) override {
        assert(n == 19); ++hacks; stamp = ms; return hackOk;
    }
};
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
size_t encode(const uint8_t key[32], const wici_link::Frame& frame, uint8_t wire[255]) {
    const size_t n = wici_link::encode(key, frame, wire, 255); assert(n); return n;
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
    wici_gateway::Root root(memory, port, air, 100, 5, ifac, identity);
    assert(root.begin(7) && root.ready());
    assert(root.beacon());
    assert(air.lastClass == wici_link::TxClass::BEACON);
    wici_link::Frame observed;
    assert(wici_link::decode(key, 100, air.last, air.lastLength, observed));
    assert(observed.type == wici_link::Type::BEACON && observed.source == 5 &&
           observed.payload[1] == 5 && observed.payload[5] == 7);
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
    assert(root.host(wire, emergencyLength, 901, 1) == wici_gateway::Event::REJECTED);
    n = encode(key, frame, wire);
    wire[n - 1] ^= 1;
    assert(root.radio(wire, n, 1000) == wici_gateway::Event::REJECTED);  // bad MAC
    wire[n - 1] ^= 1;
    assert(root.radio(wire, n, 1000) == wici_gateway::Event::FORWARDED);
    size_t encodedLength = 0;
    const uint8_t* encoded = port.output(encodedLength);
    assert(encodedLength >= n + 3 && encoded[0] == kiss::FEND && encoded[1] == kiss::CMD_DATA);
    port.consume(encodedLength);
    wici_link::Frame hack;
    hack.type = wici_link::Type::HACK; hack.network = 100;
    hack.source = 5; hack.destination = 4; hack.sequence = 42; hack.ttl = 1;
    n = encode(key, hack, wire);
    assert(root.host(wire, n, 1010, 1010 / 1000) == wici_gateway::Event::REJECTED);
    hack.sequence = 41;
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
    assert(root.host(wire, n, 1400, 1400 / 1000) == wici_gateway::Event::QUEUED && air.data == 3);
    assert(port.pendingBytes() == 0);  // scheduler admission is not radio TX
    assert(root.host(wire, n, 1401, 1401 / 1000) == wici_gateway::Event::REJECTED);
    assert(wici_link::decode(key, 100, air.last, air.lastLength, observed));
    assert(observed.source == 5 && observed.destination == 4 && observed.sequence != 77 &&
           observed.hops == 1 && memcmp(observed.payload, frame.payload, frame.length) == 0);
    root.onTxDone(true, 1450);
    assert(port.pendingBytes() > 0);  // only actual TX starts laptop's HACK timer
    port.output(encodedLength);
    port.consume(encodedLength);
    assert(port.pendingBytes() == 0);
    assert(root.host(wire, n, 1401, 1401 / 1000) == wici_gateway::Event::QUEUED);
    root.onTxDone(false, 1470);
    assert(port.pendingBytes() == 0);  // failed TX has no echo
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
}
