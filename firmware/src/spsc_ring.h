// SPDX-License-Identifier: MIT
// Pierścień jednego producenta i jednego konsumenta (SPSC) bez blokady: na stacji L0 producentem jest
// zadanie odbioru (rdzeń 0), konsumentem pętla stacji (rdzeń 1); plan interfejsu LoRa, L6.
// - Indeksy head (pisze tylko producent) i tail (pisze tylko konsument) rosną bez końca w uint32_t;
//   N jest potęgą 2, więc zawinięcie licznika nie psuje pozycji (head - tail = liczba elementów).
// - Producent zapisuje element, potem head z release; konsument czyta head z acquire, więc widzi
//   cały element. Konsument czyta element, potem tail z release; producent czyta tail z acquire, więc
//   nie nadpisze elementu, którego konsument jeszcze nie skopiował.
// - Pełny pierścień: odpada nowy element (najnowszy), licznik overflow() rośnie; elementy w środku
//   zostają w kolejności.
// Bez Arduino: sprawdzany na komputerze (tests/test_radio_link_host.py, RxRingTests).
#pragma once

#include <atomic>
#include <stddef.h>
#include <stdint.h>

template <typename T, size_t N>
class SpscRing {
    static_assert(N > 0 && (N & (N - 1)) == 0, "N musi być potęgą 2 (zawinięcie indeksów)");

public:
    // Producent: false, gdy pierścień pełny (element odpada i liczy się w overflow()).
    bool push(const T& item) {
        const uint32_t head = head_.load(std::memory_order_relaxed);
        if (head - tail_.load(std::memory_order_acquire) == N) {
            overflow_.fetch_add(1, std::memory_order_relaxed);
            return false;
        }
        items_[head % N] = item;
        head_.store(head + 1, std::memory_order_release);
        return true;
    }

    // Konsument: false, gdy pusty.
    bool pop(T& out) {
        const uint32_t tail = tail_.load(std::memory_order_relaxed);
        if (head_.load(std::memory_order_acquire) == tail) return false;
        out = items_[tail % N];
        tail_.store(tail + 1, std::memory_order_release);
        return true;
    }

    size_t size() const { return head_.load(std::memory_order_acquire) - tail_.load(std::memory_order_acquire); }
    uint32_t overflow() const { return overflow_.load(std::memory_order_relaxed); }
    static constexpr size_t capacity() { return N; }

private:
    T items_[N];
    std::atomic<uint32_t> head_{0};
    std::atomic<uint32_t> tail_{0};
    std::atomic<uint32_t> overflow_{0};
};
