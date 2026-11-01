// SPDX-License-Identifier: MIT
// Deterministic encrypted export of a frozen 256 KiB station image.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "journal.h"
#include "migration_crypto.h"
#include "migration_image.h"
#include "migration_state.h"
#include "sha2.h"

namespace migration_package {

constexpr uint32_t CHUNKS = migration_image::SIZE / migration_crypto::PART;
constexpr uint32_t SIZE = migration_crypto::HEADER + migration_image::SIZE + CHUNKS * migration_crypto::TAG;
static_assert(migration_image::SIZE % migration_crypto::PART == 0, "whole snapshot chunks");

class Exporter {
public:
    explicit Exporter(journal::Storage& memory) : memory_(memory) {}
    ~Exporter();
    // The source is already locked and has stored its snapshot hash in record.
    // Rehash the source on every restart; any mutation refuses export.
    bool begin(const migration_state::Record& record);
    bool read(uint32_t offset, uint8_t* out, size_t length);
    bool digest(uint8_t out[32]);
    void clear();
    bool ready() const { return ready_; }

private:
    journal::Storage& memory_;
    uint8_t key_[32] = {};
    uint8_t header_[migration_crypto::HEADER] = {};
    bool ready_ = false;
};

class Importer {
public:
    Importer(journal::Storage& memory, migration_state::Barrier& barrier)
        : memory_(memory), barrier_(barrier) {}
    ~Importer();
    // Every resumed upload starts at offset zero. Previously committed chunks
    // are authenticated again and compared with FRAM before new chunks write.
    bool begin(const uint8_t mid[16], const uint8_t expectedCipherHash[32]);
    bool feed(uint32_t offset, const uint8_t* data, size_t length);
    bool finish();
    uint32_t next() const { return next_; }
    bool ready() const { return ready_; }

private:
    bool acceptHeader();
    bool acceptChunk(uint32_t index);
    bool replayMatches(uint32_t offset, const uint8_t* data, size_t length);
    journal::Storage& memory_;
    migration_state::Barrier& barrier_;
    migration_state::Record record_ = {};
    sha2::Hash cipherHash_;
    sha2::Hash plainHash_;
    uint8_t expectedCipherHash_[32] = {};
    uint8_t header_[migration_crypto::HEADER] = {};
    uint8_t chunk_[migration_crypto::PART + migration_crypto::TAG] = {};
    uint8_t packageKey_[32] = {};
    uint8_t confirmKey_[32] = {};
    uint32_t next_ = 0;
    size_t headerUsed_ = 0, chunkUsed_ = 0;
    bool headerReady_ = false, bound_ = false, ready_ = false;
};

}  // namespace migration_package
