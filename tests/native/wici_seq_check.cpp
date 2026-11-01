// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include "wici_seq.h"

struct Memory : journal::Storage {
    uint8_t bytes[wici_seq::BASE + 2 * wici_seq::SLOT_BYTES] = {};
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
    wici_seq::Counter first(memory);
    uint16_t sequence = 0;
    assert(first.begin(100, 2));
    assert(first.next(sequence) && sequence == 0);
    wici_seq::Counter restarted(memory);
    assert(restarted.begin(100, 2));
    assert(restarted.next(sequence) && sequence == 64);
    memory.writesLeft = 1;
    for (int i = 0; i < 63; ++i) assert(restarted.next(sequence));
    assert(!restarted.next(sequence) && !restarted.ready());
    memory.writesLeft = -1;
    assert(restarted.begin(100, 2));
    assert(restarted.next(sequence) && sequence == 128);
    wici_seq::Counter afterCut(memory);
    assert(afterCut.begin(100, 2));
    assert(afterCut.next(sequence) && sequence == 192);
    wici_seq::Counter wrong(memory);
    assert(!wrong.begin(100, 3));
    memory.bytes[wici_seq::BASE + wici_seq::SLOT_BYTES + 12] ^= 1;
    wici_seq::Counter corrupt(memory);
    assert(!corrupt.begin(100, 2));
}
