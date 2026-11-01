// SPDX-License-Identifier: MIT
#include "migration_package.h"

#include <string.h>

#include <Crypto.h>

#include "sha2.h"

namespace migration_package {

Exporter::~Exporter() { clear(); }

void Exporter::clear() {
    ready_ = false;
    clean(key_, sizeof(key_));
    clean(header_, sizeof(header_));
}

bool Exporter::begin(const migration_state::Record& record) {
    clear();
    if (record.phase != migration_state::Phase::EXPORT || record.snapshotSize != migration_image::SIZE)
        return false;
    uint8_t actual[32], publicKey[32], confirmKey[32];
    if (!migration_image::digest(memory_, actual) || memcmp(actual, record.packageHash, sizeof(actual)) ||
        !migration_crypto::publicKey(record.privateKey, publicKey) ||
        !migration_crypto::derive(record.privateKey, record.peerPublic, record.mid, confirmKey, key_)) {
        clean(key_, sizeof(key_));
        return false;
    }
    migration_crypto::header(record.mid, record.identityDigest, publicKey,
                             record.packageHash, migration_image::SIZE, header_);
    clean(confirmKey, sizeof(confirmKey));
    ready_ = true;
    return true;
}

bool Exporter::read(uint32_t offset, uint8_t* out, size_t length) {
    if (!ready_ || (!out && length) || offset > SIZE || length > SIZE - offset) return false;
    while (length) {
        if (offset < migration_crypto::HEADER) {
            const size_t count = length < migration_crypto::HEADER - offset ? length : migration_crypto::HEADER - offset;
            memcpy(out, header_ + offset, count);
            out += count; offset += static_cast<uint32_t>(count); length -= count;
            continue;
        }
        const uint32_t body = offset - migration_crypto::HEADER;
        const uint32_t chunk = body / (migration_crypto::PART + migration_crypto::TAG);
        const uint32_t within = body % (migration_crypto::PART + migration_crypto::TAG);
        if (chunk >= CHUNKS) return false;
        uint8_t plaintext[migration_crypto::PART], ciphertext[migration_crypto::PART + migration_crypto::TAG];
        if (!migration_image::read(memory_, chunk * migration_crypto::PART, plaintext, sizeof(plaintext)) ||
            !migration_crypto::sealPart(key_, header_, chunk, plaintext, sizeof(plaintext), ciphertext)) {
            clean(plaintext, sizeof(plaintext));
            clean(ciphertext, sizeof(ciphertext));
            return false;
        }
        const size_t available = sizeof(ciphertext) - within;
        const size_t count = length < available ? length : available;
        memcpy(out, ciphertext + within, count);
        clean(plaintext, sizeof(plaintext));
        clean(ciphertext, sizeof(ciphertext));
        out += count; offset += static_cast<uint32_t>(count); length -= count;
    }
    return true;
}

bool Exporter::digest(uint8_t out[32]) {
    if (!ready_ || !out) return false;
    sha2::Hash hash;
    uint8_t block[512];
    for (uint32_t offset = 0; offset < SIZE; offset += sizeof(block)) {
        const size_t count = SIZE - offset < sizeof(block) ? SIZE - offset : sizeof(block);
        if (!read(offset, block, count)) { clean(block, sizeof(block)); return false; }
        hash.update(block, count);
    }
    hash.finish(out);
    clean(block, sizeof(block));
    return true;
}

Importer::~Importer() {
    clean(packageKey_, sizeof(packageKey_));
    clean(confirmKey_, sizeof(confirmKey_));
    clean(chunk_, sizeof(chunk_));
}

bool Importer::begin(const uint8_t mid[16], const uint8_t expectedCipherHash[32]) {
    ready_ = headerReady_ = bound_ = false;
    if (!mid || !expectedCipherHash || !barrier_.ready()) return false;
    record_ = barrier_.record();
    if (record_.phase != migration_state::Phase::IMPORTING ||
        memcmp(record_.mid, mid, 16) || record_.snapshotSize != migration_image::SIZE ||
        record_.importedBytes > migration_image::SIZE || record_.importedBytes % migration_crypto::PART)
        return false;
    memcpy(expectedCipherHash_, expectedCipherHash, 32);
    cipherHash_.reset(); plainHash_.reset();
    next_ = 0; headerUsed_ = chunkUsed_ = 0;
    ready_ = true;
    return true;
}

bool Importer::acceptHeader() {
    if (!migration_crypto::validHeader(header_, record_.mid, migration_image::SIZE)) return false;
    const uint32_t size = (static_cast<uint32_t>(header_[97]) << 24) |
                          (static_cast<uint32_t>(header_[98]) << 16) |
                          (static_cast<uint32_t>(header_[99]) << 8) | header_[100];
    if (size != migration_image::SIZE) return false;
    uint8_t zero[32] = {};
    bound_ = memcmp(record_.peerPublic, zero, 32) != 0;
    if (bound_ && (memcmp(record_.peerPublic, header_ + 33, 32) ||
                   memcmp(record_.packageHash, header_ + 65, 32) ||
                   memcmp(record_.identityDigest, header_ + 17, 16))) return false;
    if (!migration_crypto::derive(record_.privateKey, header_ + 33, record_.mid,
                                  confirmKey_, packageKey_)) return false;
    headerReady_ = true;
    return true;
}

bool Importer::acceptChunk(uint32_t index) {
    if (!headerReady_ || index >= CHUNKS) return false;
    uint8_t plaintext[migration_crypto::PART];
    if (!migration_crypto::openPart(packageKey_, header_, index, chunk_, sizeof(chunk_), plaintext)) {
        clean(plaintext, sizeof(plaintext));
        return false;
    }
    if (!bound_) {
        memcpy(record_.peerPublic, header_ + 33, 32);
        memcpy(record_.packageHash, header_ + 65, 32);
        memcpy(record_.identityDigest, header_ + 17, 16);
        if (!barrier_.save(record_)) { clean(plaintext, sizeof(plaintext)); return false; }
        bound_ = true;
    }
    const uint32_t at = index * migration_crypto::PART;
    if (at < record_.importedBytes) {
        uint8_t stored[migration_crypto::PART];
        const bool equal = migration_image::read(memory_, at, stored, sizeof(stored)) &&
                           !memcmp(stored, plaintext, sizeof(stored));
        clean(stored, sizeof(stored));
        if (!equal) { clean(plaintext, sizeof(plaintext)); return false; }
    } else {
        if (at != record_.importedBytes ||
            !migration_image::write(memory_, at, plaintext, sizeof(plaintext))) {
            clean(plaintext, sizeof(plaintext));
            return false;
        }
        record_.importedBytes += sizeof(plaintext);
        if (!barrier_.save(record_)) { clean(plaintext, sizeof(plaintext)); return false; }
    }
    plainHash_.update(plaintext, sizeof(plaintext));
    clean(plaintext, sizeof(plaintext));
    return true;
}

bool Importer::replayMatches(uint32_t offset, const uint8_t* data, size_t length) {
    while (length) {
        if (offset < migration_crypto::HEADER) {
            const size_t count = length < migration_crypto::HEADER - offset ? length : migration_crypto::HEADER - offset;
            if (memcmp(header_ + offset, data, count)) return false;
            offset += static_cast<uint32_t>(count); data += count; length -= count;
            continue;
        }
        const uint32_t body = offset - migration_crypto::HEADER;
        const uint32_t index = body / sizeof(chunk_);
        const uint32_t within = body % sizeof(chunk_);
        const size_t available = sizeof(chunk_) - within;
        const size_t count = length < available ? length : available;
        if (index == (next_ - migration_crypto::HEADER) / sizeof(chunk_)) {
            if (within + count > chunkUsed_ || memcmp(chunk_ + within, data, count)) return false;
        } else {
            uint8_t plaintext[migration_crypto::PART], ciphertext[sizeof(chunk_)];
            const bool same = migration_image::read(memory_, index * migration_crypto::PART,
                                                     plaintext, sizeof(plaintext)) &&
                              migration_crypto::sealPart(packageKey_, header_, index,
                                                         plaintext, sizeof(plaintext), ciphertext) &&
                              !memcmp(ciphertext + within, data, count);
            clean(plaintext, sizeof(plaintext));
            clean(ciphertext, sizeof(ciphertext));
            if (!same) return false;
        }
        offset += static_cast<uint32_t>(count); data += count; length -= count;
    }
    return true;
}

bool Importer::feed(uint32_t offset, const uint8_t* data, size_t length) {
    if (!ready_ || !data || !length || offset > SIZE || length > SIZE - offset) return false;
    if (offset < next_) return length <= next_ - offset && replayMatches(offset, data, length);
    if (offset != next_) return false;
    while (length) {
        uint8_t* target = headerReady_ ? chunk_ : header_;
        size_t& used = headerReady_ ? chunkUsed_ : headerUsed_;
        const size_t capacity = headerReady_ ? sizeof(chunk_) : sizeof(header_);
        const size_t count = length < capacity - used ? length : capacity - used;
        memcpy(target + used, data, count);
        cipherHash_.update(data, count);
        used += count; data += count; length -= count; next_ += static_cast<uint32_t>(count);
        if (used == capacity) {
            if (headerReady_) {
                const uint32_t index = (next_ - migration_crypto::HEADER) / sizeof(chunk_) - 1;
                if (!acceptChunk(index)) { ready_ = false; return false; }
                chunkUsed_ = 0;
            } else if (!acceptHeader()) { ready_ = false; return false; }
        }
    }
    return true;
}

bool Importer::finish() {
    if (!ready_ || !headerReady_ || next_ != SIZE || chunkUsed_ ||
        record_.importedBytes != migration_image::SIZE) return false;
    uint8_t cipherDigest[32], plainDigest[32];
    cipherHash_.finish(cipherDigest);
    plainHash_.finish(plainDigest);
    ready_ = false;
    return !memcmp(cipherDigest, expectedCipherHash_, 32) &&
           !memcmp(plainDigest, record_.packageHash, 32);
}

}  // namespace migration_package
