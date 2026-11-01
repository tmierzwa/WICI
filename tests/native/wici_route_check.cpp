// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include "wici_route.h"

struct Memory : journal::Storage {
    uint8_t bytes[wici_route::BASE + 2 * wici_route::COPY_BYTES] = {};
    int writesLeft = -1;
    bool read(uint32_t at, uint8_t* out, size_t count) override {
        if (at > sizeof(bytes) || count > sizeof(bytes) - at) return false;
        memcpy(out, bytes + at, count); return true;
    }
    bool write(uint32_t at, const uint8_t* in, size_t count) override {
        if (writesLeft == 0 || at > sizeof(bytes) || count > sizeof(bytes) - at) return false;
        if (writesLeft > 0) --writesLeft;
        memcpy(bytes + at, in, count); return true;
    }
};

int main() {
    static Memory memory;
    const wici_route::Config config{100, 4, 1, 2, 3};
    wici_route::Table table(memory, config);
    assert(table.begin());
    assert(table.down(10) == wici_link::BROADCAST);
    assert(table.learn(10, 5));
    assert(table.down(10) == 5);
    assert(table.learn(10, 5));
    memory.writesLeft = 1;
    assert(!table.learn(11, 6));  // no route or HACK on a torn write
    assert(!table.ready());
    assert(table.down(10) == wici_link::BROADCAST);  // uncertain media disables even old routes
    assert(table.down(11) == wici_link::BROADCAST);
    memory.writesLeft = -1;
    assert(table.begin() && table.down(10) == 5);
    wici_route::Table restarted(memory, config);
    assert(restarted.begin());
    assert(restarted.down(10) == 5);
    assert(restarted.down(11) == wici_link::BROADCAST);
    assert(restarted.learn(10, 6));
    wici_route::Table updated(memory, config);
    assert(updated.begin() && updated.down(10) == 6);
    wici_route::Table wrong(memory, {101, 4, 1, 2, 3});
    assert(!wrong.begin());
    static Memory rootMemory;
    wici_route::Table root(rootMemory, {100, 1, 1, 0, 0});
    assert(root.begin() && root.rank() == 0 && root.parent() == 0);
    assert(root.setRootEpoch(7) && root.epoch() == 7);
    assert(root.learn(4, 2) && root.down(4) == 2);
    assert(!root.beacon(2, {1, 16, 7, 1, 0}, 16, 100));

    assert(updated.beacon(2, {1, 16, 5, 1, 0}, 16, 100));
    assert(updated.parent() == 2 && updated.rank() == 32);
    assert(updated.beacon(3, {1, 24, 5, 1, 0}, 16, 100));
    assert(updated.parent() == 2);  // planned parent has priority
    updated.hopResult(2, false, 101);
    updated.hopResult(2, false, 102);
    updated.hopResult(2, false, 103);
    assert(updated.parent() == 3 && updated.rank() == 40);
    updated.hopResult(2, true, 104);  // successful probe restores planned parent
    assert(updated.parent() == 2 && updated.rank() > 32);  // ETX still reflects recent failures
    static Memory backupMemory;
    wici_route::Table failover(backupMemory, config);
    assert(failover.begin());
    assert(failover.beacon(2, {1, 16, 5, 1, 0}, 16, 100));
    assert(failover.beacon(3, {1, 40, 5, 1, 0}, 16, 100));
    failover.hopResult(2, false, 101);
    failover.hopResult(2, false, 102);
    failover.hopResult(2, false, 103);
    assert(failover.parent() == 3);  // configured backup may have a higher rank
    assert(failover.beacon(2, {1, 16, 5, 1, 0}, 16, 104));
    assert(failover.parent() == 2);  // a later planned beacon permits recovery

    static Memory fullMemory;
    wici_route::Table crowded(fullMemory, config);
    assert(crowded.begin());
    for (uint16_t peer = 10; peer < 10 + wici_route::NEIGHBORS; ++peer)
        assert(crowded.beacon(peer, {1, 8, 5, 1, 0}, 16, 100));
    assert(crowded.beacon(2, {1, 16, 5, 1, 0}, 16, 101));
    assert(crowded.parent() == 2);  // dynamic peers cannot exclude the planned route
    static Memory routeMemory;
    wici_route::Table bounded(routeMemory, config);
    assert(bounded.begin());
    for (uint16_t i = 0; i < wici_route::ROUTES; ++i)
        assert(bounded.learn(static_cast<uint16_t>(1000 + i), 5));
    assert(bounded.learn(2000, 6));
    assert(bounded.down(2000) == 6 && bounded.down(1000) == wici_link::BROADCAST);
    assert(!updated.beacon(7, {1, 8, 4, 1, 0}, 16, 105));  // old epoch
    assert(!updated.beacon(7, {1, 8, 5, 4, 0}, 16, 105));  // child points back
    assert(updated.beacon(2, {1, 16, 6, 1, 0}, 16, 105));  // new epoch resets soft state
    assert(updated.parent() == 2 && updated.rank() == 32);
    updated.hopResult(2, false, 105 + wici_route::BEACON_STALE_S + 1);
    assert(updated.parent() == 0);  // stale beacon cannot select a parent
    assert(updated.rank() == 32);    // keep loop-prevention ceiling
    assert(updated.beacon(7, {1, 48, 6, 8, 0}, 16, 105 + wici_route::BEACON_STALE_S + 2));
    assert(updated.parent() == 0);  // a descendant cannot become a fallback
    const uint32_t recoveredAt = 105 + wici_route::BEACON_STALE_S + 3;
    assert(updated.beacon(8, {1, 8, 6, 1, 0}, 16, recoveredAt));
    assert(updated.parent() == 8 && updated.rank() == 24);
    updated.hopResult(8, false, recoveredAt + 1);
    updated.hopResult(8, false, recoveredAt + 2);
    updated.hopResult(8, false, recoveredAt + 3);
    assert(updated.parent() == 0);  // failed dynamic parent is withheld
    updated.hopResult(8, true, recoveredAt + 4);
    assert(updated.parent() == 8);  // positive probe restores it

    assert(wici_route::snrCost16(12) == 16);
    assert(wici_route::snrCost16(-20) == 21);
    assert(wici_route::snrCost16(-400) == 48);

    static Memory loopMemory;
    wici_route::Table loopGuard(loopMemory, {100, 4, 1, 2, 0});
    assert(loopGuard.begin());
    assert(loopGuard.beacon(2, {1, 16, 5, 1, 0}, 16, 100));
    assert(loopGuard.rank() == 32);
    // A degraded ETX may increase our advertised rank. A former descendant
    // must still be barred by the lowest rank held in this epoch.
    assert(loopGuard.beacon(7, {1, 35, 5, 8, 0}, 16, 100));
    loopGuard.hopResult(2, false, 101);
    loopGuard.hopResult(2, false, 102);
    loopGuard.hopResult(2, false, 103);
    assert(loopGuard.parent() == 0);

    wici_link::Frame frame;
    frame.type = wici_link::Type::BEACON;
    frame.length = 137;
    frame.payload[1] = 1; frame.payload[3] = 16;
    frame.payload[5] = 6; frame.payload[7] = 1;
    wici_route::Beacon parsed;
    assert(wici_route::parseBeacon(frame, parsed));
    assert(parsed.root == 1 && parsed.rank == 16 && parsed.epoch == 6 && parsed.parent == 1);

    memory.bytes[wici_route::BASE + wici_route::COPY_BYTES + 30] ^= 1;
    wici_route::Table corrupt(memory, config);
    assert(!corrupt.begin());
}
