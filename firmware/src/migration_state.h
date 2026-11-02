// SPDX-License-Identifier: MIT
// Durable migration barrier in the final 512 bytes of FRAM. Boot must load this
// before enabling any radio TX. An interrupted save resolves to the last
// complete record; damaged records fail closed.
#pragma once

#include <stdint.h>

#include "framfs.h"
#include "journal.h"

namespace migration_state {

constexpr uint32_t BASE = framfs::FS_BASE + framfs::FS_SIZE;
constexpr uint32_t COPY_BYTES = 256;
static_assert(BASE + 2 * COPY_BYTES == 0x080000, "migration state ends at FRAM boundary");

enum class Phase : uint8_t {
    NONE = 0, RECEIVING = 1, EXPORT = 2, IMPORTING = 3,
    IMPORTED = 4, RETIRED = 5, ABORTED = 6
};

struct Record {
    Phase phase = Phase::NONE;
    uint8_t mid[16] = {};
    uint8_t privateKey[32] = {};  // target transfer key or source ephemeral key
    uint8_t peerPublic[32] = {};
    uint8_t packageHash[32] = {};
    uint8_t identityDigest[16] = {};
    uint32_t snapshotSize = 0;
    uint32_t importedBytes = 0;
    uint32_t flags = 0;
};

class Barrier {
public:
    explicit Barrier(journal::Storage& storage) : storage_(storage) {}
    bool begin();
    bool save(const Record& next);
    bool ready() const { return ready_; }
    const Record& record() const { return record_; }
    bool permitsTransmit() const { return ready_ && record_.phase == Phase::NONE; }

private:
    journal::Storage& storage_;
    Record record_ = {};
    uint32_t generation_ = 0;
    uint8_t copy_ = 1;
    bool ready_ = false;
};

}  // namespace migration_state
