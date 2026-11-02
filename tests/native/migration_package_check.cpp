// SPDX-License-Identifier: MIT
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "hexstr.h"
#include "migration_package.h"

struct Memory : journal::Storage {
    uint8_t bytes[0x80000] = {};
    bool read(uint32_t at, uint8_t* out, size_t n) override {
        if (at > sizeof(bytes) || n > sizeof(bytes) - at) return false;
        memcpy(out, bytes + at, n); return true;
    }
    bool write(uint32_t at, const uint8_t* in, size_t n) override {
        if (at > sizeof(bytes) || n > sizeof(bytes) - at) return false;
        memcpy(bytes + at, in, n); return true;
    }
};

void line(const char* name, const uint8_t* value, size_t length) {
    char hex[2 * (migration_crypto::PART + migration_crypto::TAG) + 1];
    hexstr::encode(value, length, hex);
    printf("%s=%s\n", name, hex);
}

int main() {
    static Memory memory;
    uint8_t block[512];
    for (uint32_t offset = 0; offset < migration_image::SIZE; offset += sizeof(block)) {
        for (size_t i = 0; i < sizeof(block); ++i) block[i] = static_cast<uint8_t>((offset + i) >> 7);
        assert(migration_image::write(memory, offset, block, sizeof(block)));
    }
    migration_state::Record record;
    record.phase = migration_state::Phase::EXPORT;
    record.snapshotSize = migration_image::SIZE;
    for (size_t i = 0; i < 32; ++i) {
        record.privateKey[i] = static_cast<uint8_t>(i);
        if (i < 16) { record.mid[i] = static_cast<uint8_t>(i + 96); record.identityDigest[i] = static_cast<uint8_t>(i + 112); }
    }
    uint8_t target[32];
    for (size_t i = 0; i < 32; ++i) target[i] = static_cast<uint8_t>(i + 32);
    assert(migration_crypto::publicKey(target, record.peerPublic));
    assert(migration_image::digest(memory, record.packageHash));
    migration_package::Exporter exporter(memory);
    assert(exporter.begin(record));
    uint8_t header[migration_crypto::HEADER], first[528], last[528], sha[32], joined[500];
    assert(exporter.read(0, header, sizeof(header)));
    assert(exporter.read(migration_crypto::HEADER, first, sizeof(first)));
    assert(exporter.read(migration_package::SIZE - sizeof(last), last, sizeof(last)));
    assert(exporter.read(80, joined, sizeof(joined)));
    assert(!memcmp(joined, header + 80, sizeof(header) - 80));
    assert(!memcmp(joined + sizeof(header) - 80, first, sizeof(joined) - (sizeof(header) - 80)));
    assert(exporter.digest(sha));
    line("header", header, sizeof(header));
    line("first", first, sizeof(first));
    line("last", last, sizeof(last));
    line("sha", sha, sizeof(sha));
    static Memory targetMemory;
    migration_state::Barrier barrier(targetMemory);
    assert(barrier.begin());
    migration_state::Record receiving;
    receiving.phase = migration_state::Phase::RECEIVING;
    memcpy(receiving.mid, record.mid, 16);
    memcpy(receiving.privateKey, target, 32);
    assert(barrier.save(receiving));
    migration_state::Record importing = receiving;
    importing.phase = migration_state::Phase::IMPORTING;
    importing.snapshotSize = migration_image::SIZE;
    assert(barrier.save(importing));
    {
        migration_package::Importer half(targetMemory, barrier);
        assert(half.begin(record.mid, sha));
        for (uint32_t offset = 0; offset < migration_package::SIZE / 2; offset += 512) {
            const size_t count = migration_package::SIZE / 2 - offset < 512 ?
                                 migration_package::SIZE / 2 - offset : 512;
            assert(exporter.read(offset, block, count));
            assert(half.feed(offset, block, count));
        }
        assert(barrier.record().importedBytes > 0);
    }
    migration_state::Barrier restarted(targetMemory);
    assert(restarted.begin());
    migration_package::Importer importer(targetMemory, restarted);
    assert(importer.begin(record.mid, sha));
    assert(exporter.read(0, block, 512));
    assert(importer.feed(0, block, 512));
    assert(importer.feed(0, block, 512));
    block[10] ^= 1;
    assert(!importer.feed(0, block, 512));
    for (uint32_t offset = 0; offset < migration_package::SIZE; offset += 512) {
        const size_t count = migration_package::SIZE - offset < 512 ? migration_package::SIZE - offset : 512;
        assert(exporter.read(offset, block, count));
        assert(importer.feed(offset, block, count));
    }
    assert(importer.finish());
    assert(restarted.record().importedBytes == migration_image::SIZE);
    uint8_t copied[512], original[512];
    for (uint32_t offset = 0; offset < migration_image::SIZE; offset += 512) {
        assert(migration_image::read(memory, offset, original, sizeof(original)));
        assert(migration_image::read(targetMemory, offset, copied, sizeof(copied)));
        assert(!memcmp(original, copied, sizeof(original)));
    }
    static Memory corruptTarget;
    migration_state::Barrier corruptBarrier(corruptTarget);
    assert(corruptBarrier.begin() && corruptBarrier.save(receiving));
    assert(corruptBarrier.save(importing));
    migration_package::Importer corruptImporter(corruptTarget, corruptBarrier);
    assert(corruptImporter.begin(record.mid, sha));
    assert(exporter.read(0, block, sizeof(block)));
    block[migration_crypto::HEADER + 10] ^= 1;
    assert(corruptImporter.feed(0, block, sizeof(block)));
    assert(exporter.read(512, block, 117));
    assert(!corruptImporter.feed(512, block, 117));
    assert(corruptBarrier.record().importedBytes == 0);
    // A changed frozen snapshot is rejected on restart.
    memory.bytes[migration_image::DATA_BASE] ^= 1;
    migration_package::Exporter changed(memory);
    assert(!changed.begin(record));
}
