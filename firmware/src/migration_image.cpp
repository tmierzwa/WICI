// SPDX-License-Identifier: MIT
#include "migration_image.h"

#include <string.h>

#include "sha2.h"

namespace migration_image {
namespace {

bool range(uint32_t offset, size_t length) {
    return offset <= SIZE && length <= SIZE - offset;
}

size_t span(uint32_t offset, size_t length, uint32_t& address) {
    const bool journal = offset < JOURNAL_BYTES;
    const uint32_t remaining = journal ? JOURNAL_BYTES - offset : SIZE - offset;
    address = journal ? offset : DATA_BASE + offset - JOURNAL_BYTES;
    return length < remaining ? length : remaining;
}

}  // namespace

bool read(journal::Storage& memory, uint32_t offset, uint8_t* out, size_t length) {
    if ((!out && length) || !range(offset, length)) return false;
    while (length) {
        uint32_t address;
        const size_t count = span(offset, length, address);
        if (!memory.read(address, out, count)) return false;
        out += count; offset += static_cast<uint32_t>(count); length -= count;
    }
    return true;
}

bool write(journal::Storage& memory, uint32_t offset, const uint8_t* in, size_t length) {
    if ((!in && length) || !range(offset, length)) return false;
    while (length) {
        uint32_t address;
        const size_t count = span(offset, length, address);
        if (!memory.write(address, in, count)) return false;
        in += count; offset += static_cast<uint32_t>(count); length -= count;
    }
    return true;
}

bool digest(journal::Storage& memory, uint8_t out[32]) {
    if (!out) return false;
    sha2::Hash hash;
    uint8_t part[512];
    for (uint32_t offset = 0; offset < SIZE; offset += sizeof(part)) {
        if (!read(memory, offset, part, sizeof(part))) {
            memset(part, 0, sizeof(part));
            return false;
        }
        hash.update(part, sizeof(part));
    }
    hash.finish(out);
    memset(part, 0, sizeof(part));
    return true;
}

bool clearLocalCaches(journal::Storage& memory) {
    uint8_t zero[256] = {};
    for (uint32_t at = JOURNAL_BYTES; at < DATA_BASE; at += sizeof(zero))
        if (!memory.write(at, zero, sizeof(zero))) return false;
    for (uint32_t at = CACHE_BASE; at < CACHE_END; at += sizeof(zero))
        if (!memory.write(at, zero, sizeof(zero))) return false;
    return true;
}

}  // namespace migration_image
