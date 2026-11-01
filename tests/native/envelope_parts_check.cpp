// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include "envelope_parts.h"

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
    envelope::Part first;
    first.sender = 1; first.recipient = 4; first.counter = 7;
    first.number = 1; first.length = 128;
    memset(first.plaintext, 'A', first.length);
    envelope::Part second = first;
    second.number = 2;
    memset(second.plaintext, 'B', second.length);
    uint8_t full[envelope::MAX_SA1] = {};
    size_t length = 0;
    uint8_t key[32] = {};
    envelope::DurableParts parts(memory, 0);
    assert(parts.begin(100, 4, 1, key));
    assert(parts.ingest(first, 1000, full, length) == envelope::FragmentResult::PARTIAL);
    assert(parts.pending() && length == 0);
    envelope::DurableParts restarted(memory, 0);
    assert(restarted.begin(100, 4, 1, key) && restarted.pending());
    assert(restarted.ingest(first, 0, full, length) == envelope::FragmentResult::PARTIAL);
    assert(restarted.ingest(second, 0, full, length) == envelope::FragmentResult::COMPLETE);
    assert(length == 256 && full[0] == 'A' && full[127] == 'A' &&
           full[128] == 'B' && full[255] == 'B');
    assert(restarted.clear());
    envelope::DurableParts cleared(memory, 0);
    assert(cleared.begin(100, 4, 1, key) && !cleared.pending());
    assert(cleared.ingest(second, 1001, full, length) == envelope::FragmentResult::PARTIAL);
    envelope::DurableParts conflict(memory, 0);
    assert(conflict.begin(100, 4, 1, key));
    first.counter = 8;
    assert(conflict.ingest(first, 1002, full, length) == envelope::FragmentResult::REJECTED);
    assert(conflict.ingest(first, 1122, full, length) == envelope::FragmentResult::PARTIAL);
    // A clock that went backwards expires the pending part, as the receiver's SQLite inbox does.
    first.counter = 9;
    assert(conflict.ingest(first, 1000, full, length) == envelope::FragmentResult::PARTIAL);
    first.counter = 8;
    envelope::DurableParts wrong(memory, 0);
    assert(!wrong.begin(100, 4, 2, key));
    uint8_t rotatedKey[32] = {};
    rotatedKey[0] = 1;
    envelope::DurableParts rotated(memory, 0);
    assert(rotated.begin(100, 4, 1, rotatedKey) && !rotated.pending());

    static Memory cutMemory;
    envelope::DurableParts cut(cutMemory, 1);
    assert(cut.begin(100, 4, 1, key));
    cutMemory.writesLeft = 2;
    assert(cut.ingest(first, 1000, full, length) == envelope::FragmentResult::IO_ERROR);
    cutMemory.writesLeft = -1;
    envelope::DurableParts afterCut(cutMemory, 1);
    assert(afterCut.begin(100, 4, 1, key) && !afterCut.pending());
    assert(afterCut.ingest(first, 1000, full, length) == envelope::FragmentResult::PARTIAL);
    uint8_t& commit = cutMemory.bytes[envelope::PARTS_BACKUP_BASE + envelope::PARTS_COPY_BYTES - 1];
    commit = 0x5A;
    envelope::DurableParts damaged(cutMemory, 1);
    assert(!damaged.begin(100, 4, 1, key));
    commit = 0xA5;
    cutMemory.bytes[envelope::PARTS_BACKUP_BASE + 25] ^= 1;
    envelope::DurableParts corrupt(cutMemory, 1);
    assert(!corrupt.begin(100, 4, 1, key));
}
