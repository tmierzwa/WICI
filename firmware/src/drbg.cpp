// SPDX-License-Identifier: MIT
#include "drbg.h"

#include <string.h>

namespace drbg {

void Drbg::update(const uint8_t* a, size_t aLength, const uint8_t* b, size_t bLength) {
    // HMAC_DRBG_Update (SP 800-90A, 10.1.2.2) z danymi dostarczonymi a ‖ b.
    const bool provided = aLength || bLength;
    for (uint8_t round = 0; round < (provided ? 2 : 1); ++round) {
        sha2::Hmac mac(key_, sizeof(key_));
        mac.update(value_, sizeof(value_));
        mac.update(&round, 1);   // 0x00, potem 0x01
        if (aLength) mac.update(a, aLength);
        if (bLength) mac.update(b, bLength);
        mac.finish(key_);
        sha2::Hmac next(key_, sizeof(key_));
        next.update(value_, sizeof(value_));
        next.finish(value_);
    }
}

void Drbg::seed(const uint8_t* entropy, size_t entropyLength, const uint8_t* nonce, size_t nonceLength) {
    memset(key_, 0x00, sizeof(key_));
    memset(value_, 0x01, sizeof(value_));
    update(entropy, entropyLength, nonce, nonceLength);
    seeded_ = entropyLength >= sha2::DIGEST;
}

bool Drbg::generate(uint8_t* out, size_t length) {
    if (!seeded_ || length > 65536) return false;
    while (length) {
        sha2::Hmac mac(key_, sizeof(key_));
        mac.update(value_, sizeof(value_));
        mac.finish(value_);
        const size_t take = length < sizeof(value_) ? length : sizeof(value_);
        memcpy(out, value_, take);
        out += take;
        length -= take;
    }
    update(nullptr, 0);
    return true;
}

}  // namespace drbg
