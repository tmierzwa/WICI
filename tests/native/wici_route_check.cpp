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

// BEACONs with a rising link seq: each one is new to its receiver.
uint16_t beaconSeq = 0;
wici_route::Beacon B(uint16_t root, uint16_t rank, uint16_t epoch, uint16_t parent) {
    wici_route::Beacon value;
    value.root = root; value.rank = rank; value.epoch = epoch; value.parent = parent;
    value.sequence = ++beaconSeq;
    return value;
}

// The network plan of these checks: stations behind neighbours.
const config::Behind plan[] = {{10, 5}, {10, 6}, {10, 7}, {11, 6}, {12, 5}, {4, 2}};
constexpr uint16_t PLANNED = sizeof(plan) / sizeof(plan[0]);

int main() {
    static Memory memory;
    const wici_route::Config config{100, 4, 1, 2, 3};
    wici_route::Table table(memory, config, nullptr, 0, plan, PLANNED);
    assert(table.begin());
    // Finding 1: a route outside the plan is refused without a write.
    memory.writesLeft = 0;
    assert(!table.learn(13, 5) && !table.learn(11, 5) && table.ready());
    assert(table.planned(5, 5) && table.planned(10, 5) && !table.planned(11, 5));
    memory.writesLeft = -1;
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
    wici_route::Table restarted(memory, config, nullptr, 0, plan, PLANNED);
    assert(restarted.begin());
    assert(restarted.down(10) == 5);
    assert(restarted.down(11) == wici_link::BROADCAST);
    // External review: a claimed envelope sender does not move a working
    // route (a relay cannot authenticate it); only `replace` (the root, on a
    // fresh authenticated admission) does, without a write when refused.
    memory.writesLeft = 0;
    assert(!restarted.learn(10, 6) && restarted.ready() && restarted.down(10) == 5);
    memory.writesLeft = -1;
    assert(restarted.learn(10, 6, true));
    wici_route::Table updated(memory, config, nullptr, 0, plan, PLANNED);
    assert(updated.begin() && updated.down(10) == 6);
    static Memory renumberMemory;
    memcpy(renumberMemory.bytes, memory.bytes, sizeof(memory.bytes));
    wici_route::Table renumbered(renumberMemory, {101, 4, 1, 2, 3}, nullptr, 0, plan, PLANNED);
    assert(renumbered.begin() && renumbered.down(10) == wici_link::BROADCAST);  // old routes void
    assert(renumbered.learn(10, 7));
    wici_route::Table renumberedAgain(renumberMemory, {101, 4, 1, 2, 3}, nullptr, 0, plan, PLANNED);
    assert(renumberedAgain.begin() && renumberedAgain.down(10) == 7);
    static Memory rootMemory;
    wici_route::Table root(rootMemory, {100, 1, 1, 0, 0}, nullptr, 0, plan, PLANNED);
    assert(root.begin() && root.rank(0) == 0 && root.parent() == 0);
    assert(root.setRootEpoch(7) && root.epoch() == 7);
    assert(root.learn(4, 2) && root.down(4) == 2);
    assert(!root.beacon(2, B(1, 16, 7, 1), 16, 100));

    // Review D1: the planned parent is the floor, usable right after boot
    // without any BEACON; the rank (and so BEACONing) waits for its BEACON.
    assert(updated.parent() == 2 && updated.rank(100) == 0xFFFF);
    assert(updated.beacon(2, B(1, 16, 5, 1), 16, 100));
    assert(updated.parent() == 2 && updated.rank(100) == 32);
    assert(updated.beacon(3, B(1, 24, 5, 1), 16, 100));
    assert(updated.parent() == 2);  // planned parent has priority
    updated.hopResult(2, false, 101);
    updated.hopResult(2, false, 102);
    updated.hopResult(2, false, 103);
    assert(updated.parent() == 3 && updated.rank(103) == 40);
    updated.hopResult(2, true, 104);  // successful probe restores planned parent
    assert(updated.parent() == 2 && updated.rank(104) > 32);  // ETX still reflects recent failures
    static Memory backupMemory;
    wici_route::Table failover(backupMemory, config);
    assert(failover.begin());
    assert(failover.beacon(2, B(1, 16, 5, 1), 16, 100));
    assert(failover.beacon(3, B(1, 40, 5, 1), 16, 100));
    failover.hopResult(2, false, 101);
    failover.hopResult(2, false, 102);
    failover.hopResult(2, false, 103);
    assert(failover.parent() == 3);  // configured backup may have a higher rank
    assert(failover.beacon(2, B(1, 16, 5, 1), 16, 104));
    assert(failover.parent() == 2);  // a later planned beacon permits recovery

    static Memory fullMemory;
    wici_route::Table crowded(fullMemory, config);
    assert(crowded.begin());
    for (uint16_t peer = 10; peer < 10 + wici_route::NEIGHBORS; ++peer)
        assert(crowded.beacon(peer, B(1, 8, 5, 1), 16, 100));
    assert(crowded.beacon(2, B(1, 16, 5, 1), 16, 101));
    assert(crowded.parent() == 2);  // dynamic peers cannot exclude the planned route
    static Memory routeMemory;
    wici_route::Table bounded(routeMemory, config);
    assert(bounded.begin());
    for (uint16_t i = 0; i < wici_route::ROUTES; ++i)  // each neighbour stands for itself
        assert(bounded.learn(static_cast<uint16_t>(1000 + i), static_cast<uint16_t>(1000 + i)));
    assert(bounded.learn(2000, 2000));
    assert(bounded.down(2000) == 2000 && bounded.down(1000) == wici_link::BROADCAST);
    assert(!updated.beacon(7, B(1, 8, 4, 1), 16, 105));  // old epoch
    assert(updated.beacon(2, B(1, 16, 6, 1), 16, 105));  // new epoch resets soft state
    assert(updated.parent() == 2 && updated.rank(105) == 32);
    updated.hopResult(2, false, 105 + wici_route::BEACON_STALE_S + 1);
    assert(updated.parent() == 2);      // a stale BEACON never removes the floor
    assert(updated.rank(105 + wici_route::BEACON_STALE_S + 1) == 0xFFFF);  // but it no longer gives a rank to advertise

    // D1 rotation without any BEACON: planned -> backup -> (no dynamic) ->
    // planned; the parent is never 0.
    static Memory floorMemory;
    wici_route::Table floor(floorMemory, config);
    assert(floor.begin() && floor.parent() == 2);
    for (uint8_t round = 0; round < 4; ++round) {
        for (uint8_t i = 0; i < 3; ++i) floor.hopResult(floor.parent(), false, 100 + round);
        assert(floor.parent() == (round % 2 ? 2 : 3) && floor.rank(100 + round) == 0xFFFF);
    }

    // D1 rotation with a dynamic neighbour and immediate return to the
    // configured parents after their BEACON.
    static Memory rotationMemory;
    wici_route::Table rotation(rotationMemory, config);
    assert(rotation.begin());
    assert(rotation.beacon(8, B(1, 8, 5, 1), 16, 100));
    assert(rotation.parent() == 2 && rotation.rank(100) == 0xFFFF);  // rank only from the parent's BEACON
    for (uint8_t i = 0; i < 3; ++i) rotation.hopResult(2, false, 101);
    assert(rotation.parent() == 3);  // backup needs no BEACON either
    for (uint8_t i = 0; i < 3; ++i) rotation.hopResult(3, false, 102);
    assert(rotation.parent() == 8 && rotation.rank(102) == 24);
    for (uint8_t i = 0; i < 3; ++i) rotation.hopResult(8, false, 103);
    assert(rotation.parent() == 2 && rotation.rank(103) == 0xFFFF);  // the rotation wraps
    for (uint8_t i = 0; i < 2; ++i) rotation.hopResult(2, false, 104);
    assert(rotation.parent() == 2);  // the counter restarted at the wrap
    rotation.hopResult(2, false, 104);
    assert(rotation.parent() == 3);
    for (uint8_t i = 0; i < 3; ++i) rotation.hopResult(3, false, 105);
    assert(rotation.parent() == 8);
    assert(rotation.beacon(3, B(1, 30, 5, 1), 16, 106));
    assert(rotation.parent() == 3 && rotation.rank(106) == 46);  // backup back at once, no hysteresis
    assert(rotation.beacon(2, B(1, 40, 5, 1), 16, 107));
    assert(rotation.parent() == 2 && rotation.rank(107) == 56);  // planned back at once

    // Hysteresis applies only between dynamic neighbours.
    static Memory dynamicMemory;
    wici_route::Table dynamic(dynamicMemory, {100, 4, 1, 2, 0});
    assert(dynamic.begin());
    assert(dynamic.beacon(8, B(1, 8, 5, 1), 48, 100));
    for (uint8_t i = 0; i < 3; ++i) dynamic.hopResult(2, false, 100);
    assert(dynamic.parent() == 8 && dynamic.rank(100) == 56);
    assert(dynamic.beacon(10, B(1, 30, 5, 1), 16, 101));
    assert(dynamic.parent() == 8);   // 46 is not 1.5 ETX better than 56
    assert(dynamic.beacon(9, B(1, 4, 5, 1), 16, 102));
    assert(dynamic.parent() == 9 && dynamic.rank(102) == 20);

    // D2: a BEACON naming this station as parent is recorded, not dropped.
    // That neighbour is then no candidate; if it was the parent, the
    // rotation moves on, and its next clean BEACON brings it back.
    static Memory loopMemory2;
    wici_route::Table loop(loopMemory2, config);
    assert(loop.begin());
    assert(loop.beacon(2, B(1, 16, 5, 1), 16, 100) && loop.parent() == 2);
    assert(loop.beacon(7, B(1, 8, 5, 4), 16, 101));   // a child points back: recorded
    assert(loop.beacon(2, B(1, 16, 5, 4), 16, 102));  // the parent now points back
    assert(loop.parent() == 3 && loop.rank(102) == 0xFFFF);
    for (uint8_t i = 0; i < 3; ++i) loop.hopResult(3, false, 103);
    assert(loop.parent() == 3);  // 7 points back and 2 loops: the rotation finds only the backup
    assert(loop.beacon(2, B(1, 16, 5, 1), 16, 104));
    assert(loop.parent() == 2 && loop.rank(104) == 32);

    // D5: a table full of stale dynamic entries takes a new dynamic neighbour
    // in place of the oldest stale one; a full table of live ones does not.
    static Memory staleMemory;
    wici_route::Table stale(staleMemory, config);
    assert(stale.begin());
    for (uint16_t peer = 10; peer < 10 + wici_route::NEIGHBORS; ++peer)
        assert(stale.beacon(peer, B(1, 8, 5, 1), 16, 100 + peer));
    assert(!stale.beacon(50, B(1, 8, 5, 1), 16, 200));
    assert(stale.beacon(50, B(1, 8, 5, 1), 16, 111 + wici_route::BEACON_STALE_S));
    assert(!stale.beacon(51, B(1, 8, 5, 1), 16, 111 + wici_route::BEACON_STALE_S));  // 11+ still live

    assert(wici_route::snrCost16(12) == 16);
    assert(wici_route::snrCost16(-20) == 21);
    assert(wici_route::snrCost16(-400) == 48);

    static Memory loopMemory;
    wici_route::Table loopGuard(loopMemory, {100, 4, 1, 2, 0});
    assert(loopGuard.begin());
    assert(loopGuard.beacon(2, B(1, 16, 5, 1), 16, 100));
    assert(loopGuard.rank(100) == 32);
    // A degraded ETX may increase our advertised rank. A former descendant
    // must still be barred by the lowest rank held in this epoch: with no
    // other candidate the rotation stays on the planned floor.
    assert(loopGuard.beacon(7, B(1, 35, 5, 8), 16, 100));
    loopGuard.hopResult(2, false, 101);
    loopGuard.hopResult(2, false, 102);
    loopGuard.hopResult(2, false, 103);
    assert(loopGuard.parent() == 2);

    wici_link::Frame frame;
    frame.type = wici_link::Type::BEACON;
    frame.length = wici_link::BEACON_PAYLOAD;
    frame.payload[1] = 1; frame.payload[3] = 16;
    frame.payload[5] = 6; frame.payload[7] = 1;
    wici_route::Beacon parsed;
    assert(wici_route::parseBeacon(frame, parsed));
    assert(parsed.root == 1 && parsed.rank == 16 && parsed.epoch == 6 && parsed.parent == 1);

    memory.bytes[wici_route::BASE + wici_route::COPY_BYTES + 30] ^= 1;
    wici_route::Table corrupt(memory, config);
    assert(!corrupt.begin());
    // Review finding 7: a replaced root restarts its epoch count. An older
    // epoch is refused while the current one is heard and accepted after the
    // current epoch has been silent for BEACON_STALE_S.
    static Memory epochMemory;
    wici_route::Table rootReplaced(epochMemory, config);
    assert(rootReplaced.begin());
    assert(rootReplaced.beacon(2, B(1, 16, 500, 1), 16, 1000));
    // D3: siblings still repeating the old epoch do not keep it alive; only
    // BEACONs of the current parent do.
    assert(rootReplaced.beacon(7, B(1, 20, 500, 1), 16, 1000 + wici_route::BEACON_STALE_S));
    assert(!rootReplaced.beacon(2, B(1, 16, 1, 1), 16, 1000 + wici_route::BEACON_STALE_S));
    assert(rootReplaced.epoch() == 500);
    assert(rootReplaced.beacon(2, B(1, 16, 1, 1), 16, 1001 + wici_route::BEACON_STALE_S));
    assert(rootReplaced.epoch() == 1 && rootReplaced.parent() == 2);

    // D7: a down route via a neighbour that lost its pairwise key (removed by
    // a reconfiguration) is dropped at begin and never learned again.
    static Memory pairMemory;
    wici_route::Table pairedBefore(pairMemory, config, nullptr, 0, plan, PLANNED);
    assert(pairedBefore.begin() && pairedBefore.learn(10, 5) && pairedBefore.learn(11, 6));
    static config::PriorityKey peers[3];
    peers[0].station = 2; peers[1].station = 3; peers[2].station = 6;
    wici_route::Table pairedAfter(pairMemory, config, peers, 3, plan, PLANNED);
    assert(pairedAfter.begin());
    assert(pairedAfter.down(10) == wici_link::BROADCAST && pairedAfter.down(11) == 6);
    assert(!pairedAfter.learn(12, 5));
    // Round 3 (7): a route outside the current plan (learned under an older
    // `behind`) is dropped at begin, like one via an unpaired neighbour; a
    // neighbour's route to itself always stays.
    static Memory replanMemory;
    wici_route::Table oldPlan(replanMemory, config, nullptr, 0, plan, PLANNED);
    assert(oldPlan.begin() && oldPlan.learn(10, 5) && oldPlan.learn(5, 5));
    const config::Behind newPlan[] = {{10, 6}};
    wici_route::Table replanned(replanMemory, config, nullptr, 0, newPlan, 1);
    assert(replanned.begin() && replanned.down(10) == wici_link::BROADCAST && replanned.down(5) == 5);

    // Review 5: a replayed BEACON (same or older seq) is refused: it can
    // neither pull the station back to a dead planned parent nor keep it fresh.
    static Memory replayMemory;
    wici_route::Table replay(replayMemory, config);
    assert(replay.begin());
    const wici_route::Beacon recorded = B(1, 16, 5, 1);
    assert(replay.beacon(2, recorded, 16, 100) && replay.parent() == 2);
    for (uint8_t i = 0; i < 3; ++i) replay.hopResult(2, false, 101);
    assert(replay.parent() == 3);
    assert(!replay.beacon(2, recorded, 16, 102) && replay.parent() == 3);
    wici_route::Beacon older = recorded;
    older.sequence = static_cast<uint16_t>(recorded.sequence - 1);
    assert(!replay.beacon(2, older, 16, 103) && replay.parent() == 3);
    wici_route::Beacon later = recorded;
    later.sequence = static_cast<uint16_t>(recorded.sequence + 40000);  // more than half the space ahead
    assert(!replay.beacon(2, later, 16, 104));
    assert(replay.beacon(2, B(1, 16, 5, 1), 16, 105) && replay.parent() == 2);

    // Review 6: a dynamic neighbour naming this station as parent is not
    // kept; if it was the parent, the rotation moves on.
    static Memory eraseMemory;
    wici_route::Table erase(eraseMemory, {100, 4, 1, 2, 0});
    assert(erase.begin());
    assert(erase.beacon(8, B(1, 8, 5, 1), 16, 100));
    for (uint8_t i = 0; i < 3; ++i) erase.hopResult(2, false, 100);
    assert(erase.parent() == 8);
    assert(erase.beacon(8, B(1, 8, 5, 4), 16, 101) && erase.parent() == 2);
    assert(erase.beacon(8, B(1, 8, 5, 1), 16, 102) && erase.parent() == 2);  // the erased entry is new again
    for (uint8_t i = 0; i < 3; ++i) erase.hopResult(2, false, 103);
    assert(erase.parent() == 8);

    // Review 2c: a loop signal from the data plane rotates at once.
    static Memory signalMemory;
    wici_route::Table signal(signalMemory, config);
    assert(signal.begin() && signal.parent() == 2);
    signal.loop(100);
    assert(signal.parent() == 3);
    signal.loop(101);
    assert(signal.parent() == 2);

    // Finding 3: the stored BEACON seq counts only while the entry is fresh.
    // After hours of silence a neighbour's seq may have moved by more than
    // half the u16 space; its next BEACON is new all the same.
    static Memory wrapMemory;
    wici_route::Table wrap(wrapMemory, {100, 5, 1, 3, 0});
    assert(wrap.begin());
    wici_route::Beacon heard = B(1, 16, 1, 1);
    heard.sequence = 10;
    assert(wrap.beacon(3, heard, 16, 100) && wrap.rank(100) == 32);
    heard.sequence = 10 + 40000;
    assert(!wrap.acceptable(3, heard, 160) && !wrap.beacon(3, heard, 16, 160));  // fresh: looks older
    const uint32_t afterHours = 100 + 6 * 3600;
    assert(wrap.acceptable(3, heard, afterHours) && wrap.beacon(3, heard, 16, afterHours));
    assert(wrap.rank(afterHours) == 32);
    heard.sequence = static_cast<uint16_t>(heard.sequence + 50);
    assert(wrap.beacon(3, heard, 16, afterHours + 60));
    // Finding 4: acceptable() holds every check of beacon() that needs no
    // signature (replay, fields, epoch age), so the caller can refuse such a
    // BEACON before spending its signature budget.
    assert(!wrap.acceptable(3, heard, afterHours + 61));  // the same seq again: a replay
    wici_route::Beacon next = heard;
    next.sequence = static_cast<uint16_t>(heard.sequence + 1);
    assert(wrap.acceptable(3, next, afterHours + 61));
    wici_route::Beacon foreign = next;
    foreign.root = 2;
    assert(!wrap.acceptable(3, foreign, afterHours + 61));
    wici_route::Beacon oldEpoch = next;
    oldEpoch.epoch = 0;
    assert(!wrap.acceptable(3, oldEpoch, afterHours + 61));  // older epoch while the parent is heard
    // Finding 6: the rank lapses 90 min after the parent's last BEACON, with
    // no other event; the parent itself (the planned floor) stays.
    assert(wrap.rank(afterHours + 60 + wici_route::BEACON_STALE_S) == 32);
    assert(wrap.rank(afterHours + 61 + wici_route::BEACON_STALE_S) == 0xFFFF && wrap.parent() == 3);
}
