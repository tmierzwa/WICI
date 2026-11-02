// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include "migration_state.h"

struct Memory : journal::Storage {
    uint8_t bytes[0x80000] = {};
    int failCall = -1, partialCall = -1, calls = 0;
    bool read(uint32_t at, uint8_t* out, size_t n) override {
        if (at > sizeof(bytes) || n > sizeof(bytes) - at) return false;
        memcpy(out, bytes + at, n); return true;
    }
    bool write(uint32_t at, const uint8_t* in, size_t n) override {
        const int call = calls++;
        if (at > sizeof(bytes) || n > sizeof(bytes) - at) return false;
        if (call == failCall) return false;
        if (call == partialCall) { memcpy(bytes + at, in, n / 2); return false; }
        memcpy(bytes + at, in, n); return true;
    }
};

int main() {
    static Memory memory;
    memset(memory.bytes + framfs::FS_BASE, 0xC3, framfs::FS_SIZE);
    migration_state::Barrier first(memory);
    assert(first.begin() && first.permitsTransmit());
    migration_state::Record receiving;
    receiving.phase = migration_state::Phase::RECEIVING;
    receiving.mid[0] = 9;
    receiving.privateKey[0] = 37;
    assert(first.save(receiving) && !first.permitsTransmit());
    migration_state::Record forbidden;
    assert(!first.save(forbidden) && !first.permitsTransmit());
    migration_state::Barrier afterRestart(memory);
    assert(afterRestart.begin() && !afterRestart.permitsTransmit());
    assert(afterRestart.record().mid[0] == 9 && afterRestart.record().privateKey[0] == 37);
    migration_state::Record importing = receiving;
    importing.phase = migration_state::Phase::IMPORTING;
    importing.snapshotSize = 4096;
    importing.packageHash[0] = 0xA4;
    memory.partialCall = memory.calls + 1;  // marker clear succeeded, body write is torn
    assert(!afterRestart.save(importing) && !afterRestart.permitsTransmit());
    memory.partialCall = -1;
    // A torn body never published its phase: the other copy is the committed state.
    migration_state::Barrier recovered(memory);
    assert(recovered.begin() && recovered.record().phase == migration_state::Phase::RECEIVING);
    assert(recovered.save(importing) && !recovered.permitsTransmit());
    migration_state::Record imported = importing;
    imported.phase = migration_state::Phase::IMPORTED;
    imported.importedBytes = 4096;
    assert(recovered.save(imported) && !recovered.permitsTransmit());
    migration_state::Barrier importedRestart(memory);
    assert(importedRestart.begin() && importedRestart.record().phase == migration_state::Phase::IMPORTED);
    migration_state::Record invalid = imported;
    invalid.importedBytes++;
    assert(!importedRestart.save(invalid));
    migration_state::Record aborted = imported;
    aborted.phase = migration_state::Phase::ABORTED;
    assert(importedRestart.save(aborted) && !importedRestart.permitsTransmit());
    migration_state::Record clear;
    assert(importedRestart.save(clear) && importedRestart.permitsTransmit());
    for (uint32_t at = framfs::FS_BASE; at < framfs::FS_BASE + framfs::FS_SIZE; ++at)
        assert(memory.bytes[at] == 0xC3);
    // Power lost after the body but before COMMIT: the digest proves the record.
    migration_state::Record next = receiving;
    next.mid[0] = 10;
    memory.failCall = memory.calls + 2;
    assert(!importedRestart.save(next));
    memory.failCall = -1;
    migration_state::Barrier bodyWritten(memory);
    assert(bodyWritten.begin() && bodyWritten.record().phase == migration_state::Phase::RECEIVING &&
           bodyWritten.record().mid[0] == 10);
    // Damage, unlike an interrupted save, fails closed: a foreign marker or a
    // committed copy whose digest no longer matches.
    const uint32_t newest = migration_state::BASE + (memory.bytes[migration_state::BASE + 5] ==
        static_cast<uint8_t>(migration_state::Phase::RECEIVING) ? 0 : migration_state::COPY_BYTES);
    memory.bytes[newest + migration_state::COPY_BYTES - 1] = 0x5A;
    migration_state::Barrier foreign(memory);
    assert(!foreign.begin() && !foreign.permitsTransmit());
    memory.bytes[newest + migration_state::COPY_BYTES - 1] = 0;
    assert(foreign.begin() && foreign.record().phase == migration_state::Phase::RECEIVING);
    memory.bytes[newest + migration_state::COPY_BYTES - 1] = 0xA5;
    memory.bytes[newest + 15] ^= 1;
    migration_state::Barrier corrupt(memory);
    assert(!corrupt.begin() && !corrupt.permitsTransmit());
    // Two torn copies leave no committed state to trust.
    memory.bytes[newest + migration_state::COPY_BYTES - 1] = 0;
    const uint32_t older = newest == migration_state::BASE ? migration_state::BASE + migration_state::COPY_BYTES
                                                           : migration_state::BASE;
    memory.bytes[older + 15] ^= 1;
    memory.bytes[older + migration_state::COPY_BYTES - 1] = 0;
    assert(!corrupt.begin());
    // A first save torn on blank FRAM leaves the blank (transmitting) state.
    memset(memory.bytes + migration_state::BASE, 0, 2 * migration_state::COPY_BYTES);
    migration_state::Barrier fresh(memory);
    assert(fresh.begin());
    memory.partialCall = memory.calls + 1;
    assert(!fresh.save(receiving));
    memory.partialCall = -1;
    migration_state::Barrier freshRestart(memory);
    assert(freshRestart.begin() && freshRestart.permitsTransmit());
    assert(freshRestart.save(receiving) && freshRestart.record().phase == migration_state::Phase::RECEIVING);
}
