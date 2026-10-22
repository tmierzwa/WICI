// SPDX-License-Identifier: MIT
#include "drbg.h"

#include <string.h>

namespace drbg {

void wipe(void* data, size_t length) {
    volatile uint8_t* p = static_cast<volatile uint8_t*>(data);
    while (length--) *p++ = 0;
}

bool healthy(const uint8_t* entropy, size_t length) {
    // Progi z SP 800-90B, 4.4.1 i 4.4.2 dla H = 4 b na bajt i alfa = 2^-20: test powtórzeń
    // C = 1 + ceil(20 / H) = 6; test proporcji: najmniejsze C z P(X + 1 >= C) <= 2^-20 dla
    // X ~ Binom(47, 2^-4), czyli 15 dla okna 48 B (zamiast 512 B z normy, bo tyle ma odczyt; stacja podaje
    // dokładnie SEED_ENTROPY B, dłuższy odczyt ma okno całej długości).
    constexpr size_t REPETITION_CUTOFF = 6;
    constexpr size_t PROPORTION_CUTOFF = 15;
    if (length < SEED_ENTROPY) return false;
    size_t run = 1, same = 1;
    for (size_t i = 1; i < length; ++i) {
        run = entropy[i] == entropy[i - 1] ? run + 1 : 1;
        if (run >= REPETITION_CUTOFF) return false;
        if (entropy[i] == entropy[0]) ++same;
    }
    return same < PROPORTION_CUTOFF;
}

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
