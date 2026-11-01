// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include "envelope_counter.h"

struct Memory : journal::Storage {
    uint8_t bytes[envelope::COUNTER_BASE + 4 * envelope::COUNTER_SLOT_BYTES] = {};
    int writesLeft = -1;
    bool read(uint32_t at, uint8_t* out, size_t n) override {
        if (at > sizeof(bytes) || n > sizeof(bytes) - at) return false;
        memcpy(out, bytes + at, n);
        return true;
    }
    bool write(uint32_t at, const uint8_t* in, size_t n) override {
        if (writesLeft == 0 || at > sizeof(bytes) || n > sizeof(bytes) - at) return false;
        if (writesLeft > 0) --writesLeft;
        memcpy(bytes + at, in, n);
        return true;
    }
};

int main() {
    Memory memory;
    uint32_t value = 999;
    envelope::Counter first(memory, 0);
    assert(first.begin(100, 4, 2));
    assert(first.next(value) && value == 0 && first.reserved() == 64);
    for (uint32_t i = 1; i < 64; ++i) assert(first.next(value) && value == i);
    // A failed reservation never releases a nonce. After reboot the complete previous
    // block is skipped, including values that might have been used before power loss.
    memory.writesLeft = 1;
    assert(!first.next(value) && !first.ready());
    memory.writesLeft = -1;
    envelope::Counter restarted(memory, 0);
    assert(restarted.begin(100, 4, 2));
    assert(restarted.next(value) && value == 64 && restarted.reserved() == 128);
    envelope::Counter again(memory, 0);
    assert(again.begin(100, 4, 2));
    assert(again.next(value) && value == 128);
    envelope::Counter wrongIdentity(memory, 0);
    assert(!wrongIdentity.begin(100, 5, 2));
    // A committed record with a damaged CRC must never silently fall back to an
    // older reservation, which could repeat a nonce.
    memory.bytes[envelope::COUNTER_BASE + envelope::COUNTER_SLOT_BYTES + 14] ^= 1;
    envelope::Counter corrupt(memory, 0);
    assert(!corrupt.begin(100, 4, 2));
    envelope::Counter secondPeer(memory, 1);
    assert(secondPeer.begin(100, 4, 3));
    assert(secondPeer.next(value) && value == 0);
    assert(secondPeer.begin(100, 4, 3));
    assert(secondPeer.next(value) && value == 64);  // same-object reload skips reserved block
}
