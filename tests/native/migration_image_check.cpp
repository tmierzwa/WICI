// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include "migration_image.h"

struct Memory : journal::Storage {
    uint8_t bytes[0x80000] = {};
    bool fail = false;
    bool read(uint32_t at, uint8_t* out, size_t n) override {
        if (fail || at > sizeof(bytes) || n > sizeof(bytes) - at) return false;
        memcpy(out, bytes + at, n); return true;
    }
    bool write(uint32_t at, const uint8_t* in, size_t n) override {
        if (fail || at > sizeof(bytes) || n > sizeof(bytes) - at) return false;
        memcpy(bytes + at, in, n); return true;
    }
};

int main() {
    static Memory memory;
    memset(memory.bytes + migration_image::DATA_BASE, 0xA5, migration_image::DATA_END - migration_image::DATA_BASE);
    memset(memory.bytes + migration_image::CACHE_BASE, 0x5A, migration_image::CACHE_END - migration_image::CACHE_BASE);
    memset(memory.bytes + migration_image::CACHE_END, 0xC3, 0x80000 - migration_image::CACHE_END);
    uint8_t input[513], output[513];
    for (size_t i = 0; i < sizeof(input); ++i) input[i] = static_cast<uint8_t>(i);
    assert(migration_image::write(memory, migration_image::JOURNAL_BYTES - 1, input, sizeof(input)));
    assert(memory.bytes[migration_image::JOURNAL_BYTES - 1] == input[0]);
    assert(memory.bytes[migration_image::DATA_BASE] == input[1]);
    assert(migration_image::read(memory, migration_image::JOURNAL_BYTES - 1, output, sizeof(output)));
    assert(!memcmp(input, output, sizeof(input)));
    assert(!migration_image::read(memory, migration_image::SIZE - 1, output, 2));
    assert(!migration_image::write(memory, migration_image::SIZE + 1, input, 0));
    uint8_t first[32], second[32];
    assert(migration_image::digest(memory, first));
    assert(migration_image::write(memory, migration_image::SIZE - 1, input, 1));
    assert(migration_image::digest(memory, second) && memcmp(first, second, 32));
    memory.fail = true;
    assert(!migration_image::digest(memory, second));
    memory.fail = false;
    assert(migration_image::clearLocalCaches(memory));
    for (uint32_t i = migration_image::JOURNAL_BYTES; i < migration_image::DATA_BASE; ++i) assert(memory.bytes[i] == 0);
    for (uint32_t i = migration_image::CACHE_BASE; i < migration_image::CACHE_END; ++i) assert(memory.bytes[i] == 0);
    for (uint32_t i = migration_image::CACHE_END; i < 0x80000; ++i) assert(memory.bytes[i] == 0xC3);
    assert(migration_image::eraseTarget(memory));
    for (uint32_t i = 0; i < migration_image::CACHE_END; ++i) assert(memory.bytes[i] == 0);
    for (uint32_t i = migration_image::CACHE_END; i < 0x80000; ++i) assert(memory.bytes[i] == 0xC3);
}
