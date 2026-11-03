// SPDX-License-Identifier: MIT
// Próg RSSI dostępu do kanału względem tła szumu (docs/spec/radio.md, „Dostęp do kanału”, punkt 5).
// Próbki RSSI z odbioru poza ramką trafiają do kubełków po BUCKET_MS; kubełek pamięta najmniejszą
// próbkę, więc ramki i krótkie zakłócenia nie podnoszą tła. Tło to mediana minimów z kubełków
// ostatnich BUCKETS × BUCKET_MS, a próg to tło + margines w granicach [lowest, highest]. Bez dość
// świeżych kubełków (start, długie nadawanie, uśpienie) zostaje poprzedni próg; przed pierwszym
// wyznaczeniem jest nim `lowest`. Próbki pisze jeden wątek (zadanie odbioru albo pętla); próg czyta
// pętla bez blokady.
// Bez zależności od Arduino; sprawdzany na komputerze.
#pragma once

#include <atomic>
#include <stddef.h>
#include <stdint.h>

namespace cca {

class NoiseFloor {
public:
    static constexpr uint32_t BUCKET_MS = 2000;
    static constexpr size_t BUCKETS = 8;      // okno 16 s
    static constexpr size_t MIN_BUCKETS = 4;  // tyle świeżych kubełków wyznacza tło

    NoiseFloor(int16_t lowest, int16_t highest, int16_t margin)
        : lowest_(lowest), highest_(highest), margin_(margin), threshold_(lowest) {}

    void sample(int16_t dbm, uint32_t nowMs) {
        const uint32_t epoch = nowMs / BUCKET_MS;
        Bucket& b = buckets_[epoch % BUCKETS];
        if (!b.used || b.epoch != epoch) b = {epoch, dbm, true};
        else if (dbm < b.min) b.min = dbm;
        int16_t minima[BUCKETS];
        size_t n = 0;
        for (const Bucket& x : buckets_)
            if (x.used && epoch - x.epoch < BUCKETS) minima[n++] = x.min;
        if (n < MIN_BUCKETS) return;
        for (size_t i = 1; i < n; ++i)  // sortowanie przez wstawianie: najwyżej 8 wartości
            for (size_t j = i; j > 0 && minima[j - 1] > minima[j]; --j) {
                const int16_t t = minima[j];
                minima[j] = minima[j - 1];
                minima[j - 1] = t;
            }
        floor_.store(minima[n / 2], std::memory_order_relaxed);
        int32_t t = static_cast<int32_t>(minima[n / 2]) + margin_;
        if (t < lowest_) t = lowest_;
        if (t > highest_) t = highest_;
        threshold_.store(static_cast<int16_t>(t), std::memory_order_relaxed);
    }

    int16_t threshold() const { return threshold_.load(std::memory_order_relaxed); }
    // Ostatnio wyznaczone tło; UNKNOWN przed pierwszym wyznaczeniem.
    static constexpr int16_t UNKNOWN = INT16_MIN;
    int16_t floor() const { return floor_.load(std::memory_order_relaxed); }

private:
    struct Bucket {
        uint32_t epoch;
        int16_t min;
        bool used;
    };
    const int16_t lowest_, highest_, margin_;
    Bucket buckets_[BUCKETS] = {};
    std::atomic<int16_t> threshold_;
    std::atomic<int16_t> floor_{UNKNOWN};
};

}  // namespace cca
