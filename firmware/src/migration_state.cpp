// SPDX-License-Identifier: MIT
#include "migration_state.h"

#include "fram_record.h"

namespace migration_state {
namespace {
using namespace fram_record;

constexpr uint8_t MAGIC[4] = {'W', 'M', 'G', '1'};
constexpr size_t DIGEST_AT = 152;

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
    // save() clears the target copy's marker to 0, writes the body, then sets
    // COMMIT. A marker of 0 therefore means "write started": a complete body
    // is a valid record (its digest proves it), a torn body is ignored and the
    // other copy holds the last committed state. Any other marker value or a
    // committed copy with a bad digest is damage and fails closed.
    ready_ = false;
    Record selected = {};
    bool found = false, torn = false;
    uint32_t generation = 0;
    uint8_t chosenCopy = 1;
    for (uint8_t copy = 0; copy < 2; ++copy) {
        uint8_t bytes[COPY_BYTES];
        if (!storage_.read(BASE + copy * COPY_BYTES, bytes, sizeof(bytes))) return false;
        if (blank(bytes, sizeof(bytes))) continue;
        const uint8_t marker = bytes[COPY_BYTES - 1];
        if (marker != COMMIT && marker != 0) return false;
        if (!valid(bytes)) {
            if (marker == COMMIT || torn) return false;
            torn = true;
            chosenCopy = static_cast<uint8_t>(1 - copy);  // the next save overwrites the torn copy
            continue;
        }
        const uint32_t value = get32(bytes + 8);
        if (!found || newer(value, generation)) {
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
    if (!write(storage_, BASE + target * COPY_BYTES, bytes, sizeof(bytes))) {
        ready_ = false;
        return false;
    }
    record_ = next;
    generation_++;
    copy_ = target;
    return true;
}

}  // namespace migration_state
