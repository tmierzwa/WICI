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
    assert(first.next(sequence) && sequence == 0);  // copy 0 reserves up to 64
    // A restart skips the unused rest of the block. With one copy written so
    // far, the missing copy counts as damaged (finding 8): one more block.
    wici_seq::Counter restarted(memory);
    assert(restarted.begin(100, 2));
    assert(restarted.next(sequence) && sequence == 128);
    memory.writesLeft = 1;
    for (int i = 0; i < 63; ++i) assert(restarted.next(sequence));
    assert(!restarted.next(sequence) && !restarted.ready());
    memory.writesLeft = -1;
    // The failed write left its copy torn (missing): skipped like a damaged one.
    assert(restarted.begin(100, 2));
    assert(restarted.next(sequence) && sequence == 256);
    wici_seq::Counter afterCut(memory);
    assert(afterCut.begin(100, 2));
    assert(afterCut.next(sequence) && sequence == 320);
    // Renumbering continues the reservation instead of wedging the link.
    wici_seq::Counter renumbered(memory);
    assert(renumbered.begin(100, 3));
    assert(renumbered.next(sequence) && sequence == 384);
    // A bad CRC in a copy (here the newer one, up to 448): that block is skipped.
    memory.bytes[wici_seq::BASE + 12] ^= 1;
    wici_seq::Counter corrupt(memory);
    assert(corrupt.begin(100, 3) && corrupt.next(sequence) && sequence == 448);

    // A damaged copy may hold the newer reservation, one block above the
    // other copy: begin skips that block instead of wedging the link, and the
    // skip is written over the damaged copy before any use. With no valid
    // copy left it fails closed.
    static Memory pairMemory;
    wici_seq::Counter writer(pairMemory);
    assert(writer.begin(100, 3));
    for (int i = 0; i <= 64; ++i) assert(writer.next(sequence));
    assert(sequence == 64);  // copy 0: up to 64 (generation 1), copy 1: up to 128 (generation 2)
    pairMemory.bytes[wici_seq::BASE + 2 * wici_seq::SLOT_BYTES - 1] = 0x5A;  // the newer copy damaged
    static Memory refusedMemory;
    memcpy(refusedMemory.bytes, pairMemory.bytes, sizeof(refusedMemory.bytes));
    refusedMemory.writesLeft = 0;
    wici_seq::Counter refusedRepair(refusedMemory);
    assert(!refusedRepair.begin(100, 3));  // the skip must be durable before any use
    static Memory damagedMemory;
    memcpy(damagedMemory.bytes, pairMemory.bytes, sizeof(damagedMemory.bytes));
    wici_seq::Counter damaged(damagedMemory);
    assert(damaged.begin(100, 3));
    assert(damagedMemory.bytes[wici_seq::BASE + 2 * wici_seq::SLOT_BYTES - 1] == 0xA5);  // rewritten
    assert(damaged.next(sequence) && sequence == 128);
    wici_seq::Counter repaired(damagedMemory);
    assert(repaired.begin(100, 3) && repaired.next(sequence) && sequence == 192);
    // Finding 8, double fault: the skip over the damaged copy is torn before
    // its COMMIT, so that copy now reads as missing. The next start must not
    // fall back to the older copy's block (64..127 may have been used).
    static Memory tornMemory;
    memcpy(tornMemory.bytes, pairMemory.bytes, sizeof(tornMemory.bytes));
    tornMemory.writesLeft = 2;  // COMMIT cleared and body written, COMMIT lost
    wici_seq::Counter tornSkip(tornMemory);
    assert(!tornSkip.begin(100, 3));
    assert(tornMemory.bytes[wici_seq::BASE + 2 * wici_seq::SLOT_BYTES - 1] == 0);
    tornMemory.writesLeft = -1;
    wici_seq::Counter afterTear(tornMemory);
    assert(afterTear.begin(100, 3) && afterTear.next(sequence) && sequence == 128);
    damagedMemory.bytes[wici_seq::BASE + wici_seq::SLOT_BYTES - 1] = 0x5A;
    damagedMemory.bytes[wici_seq::BASE + 2 * wici_seq::SLOT_BYTES - 1] = 0x5A;
    wici_seq::Counter blind(damagedMemory);
    assert(!blind.begin(100, 3));
}
