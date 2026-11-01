// SPDX-License-Identifier: MIT
// Exact 256 KiB station snapshot. Excludes diagnostic events and rebuildable
// Reticulum cache, but includes identity, write reservations, envelope counters,
// replay windows, numbered-link state, configuration and all application stores.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "journal.h"

namespace migration_image {

constexpr uint32_t JOURNAL_BYTES = 0x001000;
constexpr uint32_t DATA_BASE = 0x009000;
constexpr uint32_t DATA_END = 0x048000;
constexpr uint32_t SIZE = JOURNAL_BYTES + DATA_END - DATA_BASE;
constexpr uint32_t CACHE_BASE = DATA_END;
constexpr uint32_t CACHE_END = 0x07FE00;
static_assert(SIZE == 256u * 1024u, "migration plaintext is exactly 256 KiB");

// Offset is in the compact snapshot, not a FRAM address. Caller must hold the
// durable migration barrier before write; source must be frozen before read.
bool read(journal::Storage& memory, uint32_t offset, uint8_t* out, size_t length);
bool write(journal::Storage& memory, uint32_t offset, const uint8_t* in, size_t length);
bool digest(journal::Storage& memory, uint8_t out[32]);

// On the target, erase local diagnostic history and route/identity caches after
// the authenticated snapshot is complete, before publishing IMPORTED.
bool clearLocalCaches(journal::Storage& memory);

}  // namespace migration_image
