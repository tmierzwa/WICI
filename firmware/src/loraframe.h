// SPDX-License-Identifier: MIT
// Ramka LoRa zgodna w eterze z firmware RNode (docs/spec/radio.md, "Ramka w eterze"): 1 B nagłówka
// i dane. Nagłówek: starsza połówka losowa, bit 0 = FLAG_SPLIT (datagram w dwóch ramkach), reszta 0.
// Datagram (pakiet Reticulum z IFAC) do 508 B; ponad 254 B idzie w dwóch ramkach po nagłówku:
// bajty 0-253 i reszta. Składanie według reguł RNode (RNode_Firmware.ino:365-440, commit 56775c51)
// z trzema różnicami, które zaostrzają odbiór: ramka z samym nagłówkiem (trzecia ramka RNode przy
// 508 B) jest pomijana, oczekująca pierwsza część przepada po 1 s od odbioru jej ramki, a nagłówek
// kolejnych datagramów dzielonych ma inną połówkę (po zgubionej drugiej ramce RNode nie skleiłby
// dwóch datagramów). Plus czas datagramu w eterze i przepływność deklarowana stosowi.
// Bez zależności od Arduino, sprawdzany na komputerze (tests/test_loraframe.py).
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "lora_profile.h"

namespace loraframe {

constexpr size_t HEADER_BYTES = 1;
constexpr uint8_t FLAG_SPLIT = 0x01;
constexpr size_t IFAC_BYTES = 16;
constexpr size_t MAX_DATAGRAM = 508;                     // HW_MTU RNodeInterface: dwie ramki po 254 B danych
constexpr size_t MAX_RAW = MAX_DATAGRAM - IFAC_BYTES;    // pakiet bez IFAC: 492 B
constexpr size_t FIRST_DATA = lora::MAX_PAYLOAD - HEADER_BYTES;  // 254 B danych w pierwszej ramce
constexpr uint32_t ASSEMBLY_TIMEOUT_MS = 1000;           // jak długo czeka pierwsza część
constexpr uint8_t NO_NIBBLE = 0xFF;                      // brak poprzedniego datagramu dzielonego

static_assert(MAX_DATAGRAM == 2 * FIRST_DATA, "508 B to dokładnie dwie pełne ramki");

// --- Czas datagramu w eterze ------------------------------------------------

// Liczba ramek datagramu: 1 albo 2, 0 poza 1..508 B. 508 B to dwie ramki (RNode dodaje trzecią, my nie).
constexpr size_t frameCount(size_t length) {
    return length < 1 || length > MAX_DATAGRAM ? 0 : (length > FIRST_DATA ? 2 : 1);
}
// Długość ramki o numerze index (z nagłówkiem), 0 poza zakresem.
constexpr size_t frameLength(size_t length, size_t index) {
    return index >= frameCount(length) ? 0 : HEADER_BYTES + (index == 0 ? (length < FIRST_DATA ? length : FIRST_DATA) : length - FIRST_DATA);
}
// Czas datagramu w eterze w µs, bez narastania mocy (wzór karty; jak lora_tx_seconds w modelu), 0 poza 1..508 B.
constexpr uint32_t airtimeUs(size_t length) {
    return frameCount(length) == 0 ? 0 : lora::frameAirUs(frameLength(length, 0)) +
           (frameCount(length) == 2 ? lora::frameAirUs(frameLength(length, 1)) : 0);
}
// Czas datagramu w ms: suma rezerwacji ramek (lora::frameAirMs, z narastaniem mocy), 0 poza 1..508 B.
constexpr uint32_t airtimeMs(size_t length) {
    return frameCount(length) == 0 ? 0 : lora::frameAirMs(frameLength(length, 0)) +
           (frameCount(length) == 2 ? lora::frameAirMs(frameLength(length, 1)) : 0);
}
// Rezerwacja czasu nadawania datagramu do długu ciszy: dokładny czas jego ramek (nazwa z LinkTiming).
constexpr uint32_t reservedTxMs(size_t length) { return airtimeMs(length); }

// Przepływność deklarowana stosowi (b/s): 8 x L / czas nadawania(L) dla ogłoszenia stacji z IFAC.
// L = 19 B nagłówka + 170 B ogłoszenia + 16 B identyfikatora transportu + 16 B IFAC = 221 B
// (cold_start_announces.announce_bytes w software/reference/wyniki.json). Zmiana modelu zmienia L tutaj.
constexpr size_t ANNOUNCE_DATAGRAM_BYTES = 221;
constexpr uint32_t declaredBitrate() {
    return static_cast<uint32_t>(8ull * ANNOUNCE_DATAGRAM_BYTES * 1000000ull / airtimeUs(ANNOUNCE_DATAGRAM_BYTES));
}

// --- Nadawanie --------------------------------------------------------------

// Bajt nagłówka: starsza połówka z random, dla datagramu dzielonego inna niż previousNibble
// (poprzedni datagram dzielony, albo NO_NIBBLE).
uint8_t header(uint8_t random, bool split, uint8_t previousNibble);

struct Frame {
    uint8_t bytes[lora::MAX_PAYLOAD];
    size_t length = 0;
};

// Dzieli datagramy na ramki i pamięta połówkę ostatniego dzielonego.
class Splitter {
public:
    // Zapisuje frameCount(length) ramek do out[0..1] i zwraca ich liczbę (0 poza 1..508 B).
    // random: bajt z generatora stacji (starsza połówka trafia do nagłówka).
    size_t split(const uint8_t* datagram, size_t length, uint8_t random, Frame out[2]);

private:
    uint8_t previous_ = NO_NIBBLE;
};

// --- Odbiór -----------------------------------------------------------------

enum class Outcome : uint8_t {
    STORED,    // pierwsza część zapisana, czeka na drugą
    COMPLETE,  // datagram gotowy: datagram(), length()
    IGNORED,   // ramka pominięta (bez danych albo za długa); stan składania bez zmian
};

struct Stats {
    uint32_t split_lost = 0;        // pierwsza część przepadła: nadeszła inna połówka albo ramka bez podziału
    uint32_t header_only = 0;       // ramki bez danych (sam nagłówek, także trzecia ramka RNode, albo 0 B)
    uint32_t assembly_timeout = 0;  // pierwsza część przepadła po 1 s
    uint32_t bad_length = 0;        // ramki dłuższe niż 255 B
};

class Assembler {
public:
    // Ramka z odbioru: bajty od nagłówka, czas jej odbioru (ms, z zadania odbioru, nie z chwili obsługi).
    Outcome push(const uint8_t* frame, size_t length, uint32_t receivedMs);
    // Usuwa oczekującą pierwszą część po 1 s od jej odbioru (wołane z pętli, gdy nie ma ramek).
    void expire(uint32_t nowMs);
    // Kasuje oczekującą część (rekonfiguracja i IDLE układu); liczniki zostają.
    void reset() { pending_ = false; }
    bool pending() const { return pending_; }
    // Ostatni złożony datagram, ważny do następnego push().
    const uint8_t* datagram() const { return data_; }
    size_t length() const { return length_; }
    const Stats& stats() const { return stats_; }

private:
    void start(const uint8_t* body, size_t count, uint8_t nibble, uint32_t receivedMs);

    uint8_t data_[MAX_DATAGRAM] = {};
    size_t length_ = 0;
    bool pending_ = false;
    uint8_t nibble_ = 0;
    uint32_t startedMs_ = 0;
    Stats stats_;
};

}  // namespace loraframe
