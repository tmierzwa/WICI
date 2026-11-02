// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include "wici_airtime.h"

struct Memory : journal::Storage {
    uint8_t bytes[0x048000] = {};
    bool failWrite = false;
    bool read(uint32_t at, uint8_t* out, size_t count) override {
        if (at > sizeof(bytes) || count > sizeof(bytes) - at) return false;
        memcpy(out, bytes + at, count); return true;
    }
    bool write(uint32_t at, const uint8_t* in, size_t count) override {
        if (failWrite || at > sizeof(bytes) || count > sizeof(bytes) - at) return false;
        memcpy(bytes + at, in, count); return true;
    }
};

int main() {
    static Memory memory;
    memset(memory.bytes + framfs::IDENTITY_BASE, 0x5A, 2 * framfs::IDENTITY_SLOT);
    memset(memory.bytes + envelope::PARTS_BACKUP_BASE, 0x3C, 2 * envelope::PARTS_COPY_BYTES);
    wici_airtime::Budget first(memory);
    assert(first.begin(100, 2));
    unsigned admitted = 0;
    while (first.reserve(false, 800, 100)) ++admitted;
    assert(admitted == 207);
    assert(first.poolUsed() == admitted * 800u * 13u);
    for (uint32_t at = framfs::IDENTITY_BASE; at < framfs::IDENTITY_BASE + 2 * framfs::IDENTITY_SLOT; ++at)
        assert(memory.bytes[at] == 0x5A);
    for (uint32_t at = envelope::PARTS_BACKUP_BASE;
         at < envelope::PARTS_BACKUP_BASE + 2 * envelope::PARTS_COPY_BYTES; ++at)
        assert(memory.bytes[at] == 0x3C);
    wici_airtime::Budget resumed(memory);
    assert(resumed.begin(100, 2));
    assert(resumed.poolUsed() == first.poolUsed());
    assert(!resumed.reserve(false, 800, 200));
    assert(!resumed.reserve(false, 800, 3600));  // old bucket retained conservatively
    assert(resumed.reserve(false, 800, 4200));
    assert(resumed.poolUsed() == 10400);
    assert(resumed.reserve(true, 800, 4200));
    assert(resumed.beaconUsed() == 800);
    memory.failWrite = true;
    assert(!resumed.reserve(true, 800, 4200) && !resumed.ready());
    memory.failWrite = false;
    wici_airtime::Budget afterFailure(memory);
    assert(afterFailure.begin(100, 2) && afterFailure.beaconUsed() == 800);
    wici_airtime::Budget renumbered(memory);  // spent airtime survives renumbering
    assert(renumbered.begin(100, 3) && renumbered.beaconUsed() == 800);

    static Memory beaconMemory;
    wici_airtime::Budget beacons(beaconMemory);
    assert(beacons.begin(100, 2));
    for (unsigned i = 0; i < 90; ++i) assert(beacons.reserve(true, 800, 100));
    assert(beacons.beaconUsed() == wici_airtime::BEACON_CAP_MS);
    assert(!beacons.reserve(true, 800, 100));
    assert(beacons.poolUsed() == 90u * 800u * 13u);

    static Memory contentionMemory;
    wici_airtime::Budget contention(contentionMemory);
    assert(contention.begin(100, 2));
    for (unsigned i = 0; i < 86; ++i) assert(contention.reserve(false, 800, 100, true));
    assert(!contention.reserve(false, 800, 100, true));
    assert(contention.reserve(false, 800, 100));  // no K1 waiting: the 60% pool still applies
    wici_airtime::Budget contentionRestart(contentionMemory);
    assert(contentionRestart.begin(100, 2));
    assert(!contentionRestart.reserve(false, 800, 100, true));

    static Memory corruptMemory;
    wici_airtime::Budget corrupt(corruptMemory);
    assert(corrupt.begin(100, 2) && corrupt.reserve(false, 800, 100));
    corruptMemory.bytes[wici_airtime::BASE + 16] ^= 1;
    wici_airtime::Budget checked(corruptMemory);
    assert(!checked.begin(100, 2));  // committed corruption cannot reset the quota
}
