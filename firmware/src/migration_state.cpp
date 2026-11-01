// SPDX-License-Identifier: MIT
#include "migration_state.h"

#include <string.h>

#include "sha2.h"

namespace migration_state {
namespace {

constexpr uint8_t MAGIC[4] = {'W', 'M', 'G', '1'};
constexpr uint8_t COMMIT = 0xA5;
constexpr size_t DIGEST_AT = 152;

void put32(uint8_t* p, uint32_t n) {
    p[0] = static_cast<uint8_t>(n >> 24); p[1] = static_cast<uint8_t>(n >> 16);
    p[2] = static_cast<uint8_t>(n >> 8); p[3] = static_cast<uint8_t>(n);
}
uint32_t get32(const uint8_t* p) {
    return (static_cast<uint32_t>(p[0]) << 24) | (static_cast<uint32_t>(p[1]) << 16) |
           (static_cast<uint32_t>(p[2]) << 8) | p[3];
}
bool blank(const uint8_t* p) {
    bool zero = true, erased = true;
    for (size_t i = 0; i < COPY_BYTES; ++i) { zero &= p[i] == 0; erased &= p[i] == 0xFF; }
    return zero || erased;
}
bool valid(const uint8_t* p) {
    if (memcmp(p, MAGIC, 4) || p[4] != 1 || p[5] > static_cast<uint8_t>(Phase::ABORTED) ||
        p[6] || p[7]) return false;
    uint8_t digest[32];
    sha2::digest(p, DIGEST_AT, digest);
    uint8_t diff = 0;
    for (size_t i = 0; i < sizeof(digest); ++i) diff |= digest[i] ^ p[DIGEST_AT + i];
    for (size_t i = DIGEST_AT + sizeof(digest); i < COPY_BYTES - 1; ++i) diff |= p[i];
    return diff == 0;
}
bool allowed(Phase from, Phase to) {
    if (from == to) return true;  // retry or import progress
    switch (from) {
        case Phase::NONE: return to == Phase::RECEIVING || to == Phase::EXPORT;
        case Phase::RECEIVING: return to == Phase::IMPORTING || to == Phase::ABORTED;
        case Phase::EXPORT: return to == Phase::RETIRED || to == Phase::ABORTED;
        case Phase::IMPORTING: return to == Phase::IMPORTED || to == Phase::ABORTED;
        case Phase::IMPORTED: return to == Phase::NONE || to == Phase::ABORTED;
        case Phase::ABORTED: return to == Phase::NONE;
        case Phase::RETIRED: return false;
    }
    return false;
}
void encode(const Record& record, uint32_t generation, uint8_t out[COPY_BYTES]) {
    memset(out, 0, COPY_BYTES);
    memcpy(out, MAGIC, 4);
    out[4] = 1; out[5] = static_cast<uint8_t>(record.phase);
    put32(out + 8, generation);
    memcpy(out + 12, record.mid, 16);
    memcpy(out + 28, record.privateKey, 32);
    memcpy(out + 60, record.peerPublic, 32);
    memcpy(out + 92, record.packageHash, 32);
    memcpy(out + 124, record.identityDigest, 16);
    put32(out + 140, record.snapshotSize);
    put32(out + 144, record.importedBytes);
    put32(out + 148, record.flags);
    sha2::digest(out, DIGEST_AT, out + DIGEST_AT);
}
void decode(const uint8_t in[COPY_BYTES], Record& record) {
    record.phase = static_cast<Phase>(in[5]);
    memcpy(record.mid, in + 12, 16);
    memcpy(record.privateKey, in + 28, 32);
    memcpy(record.peerPublic, in + 60, 32);
    memcpy(record.packageHash, in + 92, 32);
    memcpy(record.identityDigest, in + 124, 16);
    record.snapshotSize = get32(in + 140);
    record.importedBytes = get32(in + 144);
    record.flags = get32(in + 148);
}

}  // namespace

bool Barrier::begin() {
    ready_ = false;
    Record selected = {};
    bool found = false;
    uint32_t generation = 0;
    uint8_t chosenCopy = 1;
    for (uint8_t copy = 0; copy < 2; ++copy) {
        uint8_t bytes[COPY_BYTES];
        if (!storage_.read(BASE + copy * COPY_BYTES, bytes, sizeof(bytes))) return false;
        if (blank(bytes)) continue;
        // A missing marker could be a torn write or a damaged previously
        // committed lock. Neither is proof that the older state may transmit.
        if (bytes[COPY_BYTES - 1] != COMMIT) return false;
        if (!valid(bytes)) return false;
        const uint32_t value = get32(bytes + 8);
        if (!found || static_cast<int32_t>(value - generation) > 0) {
            decode(bytes, selected);
            generation = value;
            chosenCopy = copy;
            found = true;
        }
    }
    record_ = selected;
    generation_ = generation;
    copy_ = chosenCopy;
    ready_ = true;
    return true;
}

bool Barrier::save(const Record& next) {
    if (!ready_ || static_cast<uint8_t>(next.phase) > static_cast<uint8_t>(Phase::ABORTED) ||
        next.importedBytes > next.snapshotSize || !allowed(record_.phase, next.phase)) return false;
    uint8_t bytes[COPY_BYTES];
    encode(next, generation_ + 1, bytes);
    const uint8_t target = static_cast<uint8_t>(1 - copy_);
    const uint32_t at = BASE + target * COPY_BYTES;
    const uint8_t clear = 0;
    if (!storage_.write(at + COPY_BYTES - 1, &clear, 1) ||
        !storage_.write(at, bytes, COPY_BYTES - 1) ||
        !storage_.write(at + COPY_BYTES - 1, &COMMIT, 1)) {
        ready_ = false;
        return false;
    }
    uint8_t verified[COPY_BYTES];
    if (!storage_.read(at, verified, sizeof(verified)) ||
        memcmp(bytes, verified, COPY_BYTES - 1) || verified[COPY_BYTES - 1] != COMMIT) {
        ready_ = false;
        return false;
    }
    record_ = next;
    generation_++;
    copy_ = target;
    return true;
}

}  // namespace migration_state
