// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include "wici_flood.h"

struct Memory : journal::Storage {
    uint8_t bytes[0x048000] = {};
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
    wici_flood::Ring ring(memory);
    assert(ring.begin(100));
    uint8_t header[9] = {0x40, 0, 1, 0, 4, 0, 0, 0, 0};
    for (uint16_t i = 0; i < wici_flood::SLOTS; ++i) {
        header[7] = static_cast<uint8_t>(i >> 8);
        header[8] = static_cast<uint8_t>(i);
        assert(ring.lookup(header, 100) == wici_flood::Lookup::NONE);
        assert(ring.remember(header, 100));
        assert(ring.lookup(header, 100) == wici_flood::Lookup::MATCH);
    }
    header[7] = 1; header[8] = 0;
    assert(!ring.remember(header, 100));  // no eviction inside the two-minute window
    assert(ring.remember(header, 221));  // expired oldest entry is reusable
    wici_flood::Ring restarted(memory);
    assert(restarted.begin(100));
    assert(restarted.lookup(header, 222) == wici_flood::Lookup::MATCH);
    wici_flood::Ring renumbered(memory);
    assert(renumbered.begin(101));  // another network's records neither match nor wedge
    assert(renumbered.lookup(header, 222) == wici_flood::Lookup::NONE);
    assert(renumbered.remember(header, 222));

    static Memory cutMemory;
    wici_flood::Ring beforeCut(cutMemory);
    assert(beforeCut.begin(100));
    cutMemory.writesLeft = 2;
    assert(!beforeCut.remember(header, 100) && !beforeCut.ready());
    cutMemory.writesLeft = -1;
    wici_flood::Ring afterCut(cutMemory);
    assert(afterCut.begin(100));
    assert(afterCut.lookup(header, 100) == wici_flood::Lookup::NONE);
    assert(afterCut.remember(header, 100));
    // A damaged record is not security state: it is tombstoned and counted
    // instead of blocking the link for good.
    cutMemory.bytes[wici_flood::BASE_A + 2] ^= 1;
    wici_flood::Ring corrupt(cutMemory);
    assert(corrupt.begin(100) && corrupt.cleared() == 1);
    assert(corrupt.lookup(header, 100) == wici_flood::Lookup::NONE);
    wici_flood::Ring cleaned(cutMemory);
    assert(cleaned.begin(100) && cleaned.cleared() == 0);
    assert(cleaned.remember(header, 100));
}
