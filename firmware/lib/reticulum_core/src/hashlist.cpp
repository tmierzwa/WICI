// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
#include "hashlist.h"

namespace rnscore {

// Pierwsze 8 B skrótu jako liczba; 0 oznacza wolny wpis, więc skrót z ośmioma zerami dostaje 1.
uint64_t HashList::key(const uint8_t hash[HASH_SIZE]) {
    uint64_t k = 0;
    for (size_t i = 0; i < 8; ++i) k = (k << 8) | hash[i];
    return k ? k : 1;
}

bool HashList::contains(const uint8_t hash[HASH_SIZE]) const {
    const uint64_t k = key(hash);
    for (size_t i = 0; i < count_; ++i) {
        if (keys_[i] == k) return true;
    }
    return false;
}

bool HashList::add(const uint8_t hash[HASH_SIZE]) {
    if (contains(hash)) return false;
    keys_[next_] = key(hash);
    next_ = (next_ + 1) % HASHLIST_MAX;
    if (count_ < HASHLIST_MAX) ++count_;
    return true;
}

void HashList::clear() {
    for (uint64_t& k : keys_) k = 0;
    count_ = 0;
    next_ = 0;
}

}  // namespace rnscore
