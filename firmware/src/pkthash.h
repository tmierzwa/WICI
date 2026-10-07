// SPDX-License-Identifier: MIT
// Lista skrótów pakietów Reticulum do wykrywania duplikatów (docs/spec/oprogramowanie.md,
// "Pojemności stosu"): 4096 wpisów po pierwsze 8 B skrótu, czyli 32 KiB w RAM zamiast pełnych
// 32 B w kontenerach microReticulum. Pierścień FIFO: po zapełnieniu nowy skrót zastępuje
// najstarszy; sprawdzenie to przegląd liniowy 4096 słów (ok. 0,3 ms przy 64 MHz na pakiet).
// Lista jest lokalna i nie zmienia protokołu; prawdopodobieństwo fałszywego duplikatu przy
// 4096 wpisach jest rzędu 4096 / 2^64. Bez zależności od Arduino i od stosu; ShortHashList
// podstawia ją łata patches/microReticulum/0002 w miejsce Transport::PersistedBytesList.
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <vector>

namespace pkthash {

constexpr size_t CAPACITY = 4096;
constexpr size_t KEY_BYTES = 8;

// Pierwsze 8 B skrótu jako liczba; 0 oznacza wolny wpis, więc skrót z ośmioma zerami dostaje 1.
inline uint64_t key(const uint8_t* hash, size_t length) {
    uint64_t k = 0;
    for (size_t i = 0; i < KEY_BYTES && i < length; ++i) k = (k << 8) | hash[i];
    return k ? k : 1;
}

class List {
public:
    bool contains(uint64_t k) const {
        for (size_t i = 0; i < count_; ++i)
            if (keys_[i] == k) return true;
        return false;
    }
    // Dopisuje skrót, jeśli go nie ma; przy pełnej liście zastępuje najstarszy.
    void add(uint64_t k) {
        if (contains(k)) return;
        keys_[next_] = k;
        next_ = (next_ + 1) % CAPACITY;
        if (count_ < CAPACITY) ++count_;
        else ++evicted_;
    }
    // Usunięcie (Transport usuwa skrót pakietu, którego nie przyjął): wpis dostaje wartość
    // spoza zakresu klucza, więc nie pasuje do żadnego skrótu, a kolejność pierścienia zostaje.
    bool remove(uint64_t k) {
        for (size_t i = 0; i < count_; ++i)
            if (keys_[i] == k) { keys_[i] = 0; ++removed_; return true; }
        return false;
    }
    size_t size() const { return count_; }
    uint32_t evicted() const { return evicted_; }
    uint32_t removed() const { return removed_; }
    void clear() { count_ = 0; next_ = 0; }

private:
    uint64_t keys_[CAPACITY] = {};
    size_t count_ = 0;
    size_t next_ = 0;
    uint32_t evicted_ = 0;
    uint32_t removed_ = 0;
};

// Interfejs zgodny z użyciem Transport::_packet_hashlist w microReticulum (put, exists, remove,
// size); Bytes to RNS::Bytes (data(), size()), Store jest ignorowany, bo lista nie trafia do FRAM:
// po restarcie pusta lista może przyjąć ponownie pakiet sprzed restartu, a powtórzenia wiadomości
// odrzuca warstwa aplikacji po kluczu (id, revision, event).
template <class Bytes, class Store>
class ShortHashList {
public:
    explicit ShortHashList(Store&) {}
    bool put(const Bytes& hash, const std::vector<uint8_t>&, uint32_t) {
        list_.add(key(hash.data(), hash.size()));
        return true;
    }
    bool exists(const Bytes& hash) const { return list_.contains(key(hash.data(), hash.size())); }
    bool remove(const Bytes& hash) { return list_.remove(key(hash.data(), hash.size())); }
    size_t size() const { return list_.size(); }
    const List& list() const { return list_; }

private:
    List list_;
};

}  // namespace pkthash
