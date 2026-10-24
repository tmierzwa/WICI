// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// Lista skrótów pakietów do odrzucania duplikatów (docs/spec/oprogramowanie.md, „Pojemności stosu”):
// 4096 wpisów po pierwsze 8 B skrótu pakietu (32 KiB), pierścień: przy pełnej liście nowy skrót zastępuje
// najstarszy. Prawdopodobieństwo fałszywego duplikatu przy 4096 wpisach jest rzędu 4096 / 2^64.
#pragma once

#include "rnscore.h"

namespace rnscore {

constexpr size_t HASHLIST_MAX = 4096;

// RNS/Transport.py: Transport.packet_hashlist (zbiór pełnych skrótów, obracany po 1 000 000 wpisów).
class HashList {
public:
    bool contains(const uint8_t hash[HASH_SIZE]) const;
    // Jeden przegląd listy: skrót dopisany i prawda albo, gdy już jest, fałsz bez zmian (duplikat).
    bool add(const uint8_t hash[HASH_SIZE]);
    // Skrót zdjęty z listy (odmowa przejściowa po add: ta sama kopia dostanie ponowną szansę). Przegląd od
    // najnowszego wpisu, więc skrót dopisany przed chwilą to jedno porównanie; zwolnione miejsce zostaje puste
    // do następnego obiegu pierścienia (size() bez zmian).
    void remove(const uint8_t hash[HASH_SIZE]);
    size_t size() const { return count_; }
    void clear();

private:
    static uint64_t key(const uint8_t hash[HASH_SIZE]);
    uint64_t keys_[HASHLIST_MAX] = {};
    size_t count_ = 0;
    size_t next_ = 0;
};

}  // namespace rnscore
