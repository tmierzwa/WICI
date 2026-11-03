// SPDX-License-Identifier: MIT
// Memory-bearer composition: one relay, a crash after HACK, then uplink and
// downlink. It exercises the durable codecs/state, not the SX1262 driver.
#include <assert.h>
#include <string.h>

#include "wici_relay.h"
#include "wici_route.h"

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
    static Memory relayMemory, rootMemory;
    uint8_t ifac[16] = {}, key[32], incoming[wici_link::MAX_FRAME] = {};
    for (uint8_t i = 0; i < sizeof(ifac); ++i) ifac[i] = i;
    assert(wici_link::deriveKey(ifac, 100, key));
    wici_relay::Queue first(relayMemory);
    wici_route::Table route(relayMemory, {100, 2, 1, 1, 0});
    assert(first.begin(key, 100, 2) && route.begin());

    wici_link::Frame uplink;
    uplink.type = wici_link::Type::DATA;
    uplink.flags = wici_link::ACKREQ;
    uplink.network = 100;
    uplink.source = 4;
    uplink.destination = 2;
    uplink.sequence = 41;
    uplink.ttl = 7;
    uplink.length = 25;
    uplink.payload[0] = 0x40;  // end-to-end envelope header, whole SA1
    uplink.payload[1] = 0; uplink.payload[2] = 4;
    uplink.payload[3] = 0; uplink.payload[4] = 9;
    uplink.payload[8] = 7;
    const size_t receivedLength = wici_link::encode(key, uplink, incoming, sizeof(incoming));
    assert(receivedLength == 44);
    assert(first.admit(incoming, receivedLength, 100) == wici_relay::Admission::STORED);
    assert(route.learn(4, 4));  // down route survives the same crash
    // HACK may be sent only now, after the relay queue and down route commit.
    wici_link::Frame hack;
    hack.type = wici_link::Type::HACK; hack.network = 100;
    hack.source = 2; hack.destination = 4; hack.sequence = 41; hack.ttl = 1;
    const uint16_t echo = wici_link::macEcho(incoming, receivedLength);
    hack.payload[0] = static_cast<uint8_t>(echo >> 8); hack.payload[1] = static_cast<uint8_t>(echo);
    hack.length = wici_link::HACK_ECHO;
    uint8_t hackWire[wici_link::MAX_FRAME] = {};
    const size_t hackLength = wici_link::encode(key, hack, hackWire, sizeof(hackWire));
    wici_link::Frame checked;
    assert(wici_link::decode(key, 100, hackWire, hackLength, checked));

    // Power cut after HACK and before forwarding. Both states are recovered.
    wici_relay::Queue restarted(relayMemory);
    wici_route::Table routeAfter(relayMemory, {100, 2, 1, 1, 0});
    assert(restarted.begin(key, 100, 2) && routeAfter.begin() && restarted.pending(0));
    assert(routeAfter.down(4) == 4);
    assert(routeAfter.beacon(1, {1, 0, 1, 0, 0}, 16, 101));
    assert(routeAfter.parent() == 1);
    uint8_t queued[wici_link::MAX_FRAME] = {};
    size_t queuedLength = 0;
    assert(restarted.read(0, 101, queued, sizeof(queued), queuedLength));
    assert(queuedLength == receivedLength && memcmp(queued, incoming, queuedLength) == 0);
    uint8_t forwardWire[wici_link::MAX_FRAME] = {};
    const size_t forwardLength = wici_link::forward(key, 100, 2, routeAfter.parent(), 42,
                                                   queued, queuedLength, forwardWire, sizeof(forwardWire));
    assert(forwardLength == queuedLength);
    assert(wici_link::decode(key, 100, forwardWire, forwardLength, checked));
    assert(checked.destination == 1 && checked.payload[8] == 7);

    const config::Behind rootPlan[] = {{4, 2}};  // the root's plan: station 4 behind relay 2
    wici_route::Table root(rootMemory, {100, 1, 1, 0, 0}, nullptr, 0, rootPlan, 1);
    assert(root.begin() && root.setRootEpoch(1));
    assert(root.learn(4, 2) && root.down(4) == 2);
    assert(restarted.remove(0, 102));  // root HACK
    wici_relay::Queue afterDelivery(relayMemory);
    assert(afterDelivery.begin(key, 100, 2));
    assert(afterDelivery.admit(incoming, receivedLength, 103) == wici_relay::Admission::FORWARDED);

    wici_link::Frame downlink = uplink;
    downlink.flags = wici_link::ACKREQ | wici_link::DOWN;
    downlink.source = 1; downlink.destination = root.down(4);
    downlink.sequence = 43;
    downlink.payload[1] = 0; downlink.payload[2] = 9;
    downlink.payload[3] = 0; downlink.payload[4] = 4;
    uint8_t downWire[wici_link::MAX_FRAME] = {};
    const size_t downLength = wici_link::encode(key, downlink, downWire, sizeof(downWire));
    assert(wici_link::decode(key, 100, downWire, downLength, checked));
    assert(checked.destination == 2 && routeAfter.down(4) == 4);
}
