// SPDX-License-Identifier: MIT
// Ramka P1 (docs/spec/radio.md, "Ramka P1"): fragmentacja datagramu do 600 B na ramki
// LEN | BODY | CRC (LEN liczy BODY i CRC, F79), rozbiór ramki i składanie datagramów z
// limitami ze specyfikacji: 8 prób, 120 s, poprawne duplikaty pomijane, sprzeczny
// duplikat albo zmiana liczby fragmentów lub długości usuwa próbę, przy przepełnieniu
// odpada próba z najmniejszą liczbą fragmentów, pamięć ostatnio złożonych identyfikatorów
// odrzuca spóźnione duplikaty. Odpowiednik software/reference/reference.py (fragment,
// parse_frame, assemble); bez zależności od Arduino, sprawdzany na komputerze.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace p1frame {

constexpr size_t MAX_DATAGRAM = 600;
constexpr size_t CHUNK = 86;
constexpr size_t MAX_FRAGMENTS = 7;
constexpr size_t HEADER_BYTES = 14;  // wersja, znaczniki, identyfikator 8 B, numer, liczba, długość 2 B
constexpr size_t ID_BYTES = 8;
constexpr uint8_t MIN_LEN = 17;   // nagłówek 14 + 1 B danych + CRC 2
constexpr uint8_t MAX_LEN = 102;  // nagłówek 14 + 86 B danych + CRC 2
constexpr size_t MAX_FRAME = MAX_LEN + 1;  // bajt LEN i LEN bajtów po nim
constexpr size_t ATTEMPTS = 8;
constexpr uint32_t ATTEMPT_MS = 120000;
constexpr size_t RECENT_IDS = 16;

struct Fragment {
    uint8_t id[ID_BYTES];
    uint8_t index;
    uint8_t count;
    uint16_t total;
    const uint8_t* chunk;
    uint8_t chunkLength;
};

enum class Parse : uint8_t { OK, BAD_LENGTH, BAD_CRC, BAD_VERSION, BAD_COUNT, BAD_CHUNK };
const char* parseName(Parse result);

uint8_t fragmentCount(size_t length);  // 0 dla długości spoza 1..600
// Buduje ramkę o numerze index (bajty LEN..CRC); zwraca jej długość albo 0 przy złych danych.
size_t buildFrame(const uint8_t* data, size_t length, const uint8_t id[ID_BYTES], uint8_t index, uint8_t out[MAX_FRAME]);
// Rozbiera ramkę (bajty LEN..CRC, length = LEN + 1); fragment.chunk wskazuje do frame.
Parse parseFrame(const uint8_t* frame, size_t length, Fragment& fragment);

enum class Outcome : uint8_t {
    STORED,          // fragment zapisany, datagram niekompletny
    COMPLETE,        // datagram złożony: completed(), completedLength()
    DUPLICATE,       // poprawny duplikat pominięty
    CONFLICT,        // sprzeczny duplikat albo zmiana liczby/długości: próba usunięta
    LATE_DUPLICATE,  // fragment niedawno złożonego datagramu
};
const char* outcomeName(Outcome outcome);

struct Stats {
    uint32_t stored = 0;
    uint32_t completed = 0;
    uint32_t duplicates = 0;
    uint32_t conflicts = 0;
    uint32_t late = 0;
    uint32_t evicted = 0;   // próby usunięte przy przepełnieniu
    uint32_t expired = 0;   // próby usunięte po 120 s
};

class Assembler {
public:
    Outcome push(const Fragment& fragment, uint32_t nowMs);
    void expire(uint32_t nowMs);
    const uint8_t* completed() const { return completed_; }
    size_t completedLength() const { return completedLength_; }
    const uint8_t* completedId() const { return completedId_; }
    size_t active() const;
    const Stats& stats() const { return stats_; }

private:
    struct Attempt {
        bool used = false;
        uint8_t id[ID_BYTES] = {};
        uint8_t count = 0;
        uint16_t total = 0;
        uint8_t received = 0;
        uint8_t mask = 0;  // bit i = fragment i odebrany
        uint32_t startedMs = 0;
        uint8_t data[MAX_DATAGRAM] = {};
    };
    Attempt* find(const uint8_t id[ID_BYTES]);
    Attempt* allocate(uint32_t nowMs);
    bool recent(const uint8_t id[ID_BYTES]) const;
    void remember(const uint8_t id[ID_BYTES]);

    Attempt attempts_[ATTEMPTS];
    uint8_t recentIds_[RECENT_IDS][ID_BYTES] = {};
    bool recentUsed_[RECENT_IDS] = {};
    size_t recentNext_ = 0;
    uint8_t completed_[MAX_DATAGRAM] = {};
    size_t completedLength_ = 0;
    uint8_t completedId_[ID_BYTES] = {};
    Stats stats_;
};

}  // namespace p1frame
