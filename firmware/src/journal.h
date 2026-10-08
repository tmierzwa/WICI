// SPDX-License-Identifier: MIT
// Dziennik stacji w FRAM (docs/spec/radio.md "Dostęp do kanału", oprogramowanie.md "Czas"
// i "Pamięć FRAM według roli"): dług ciszy, licznik czasu pracy z liczbą restartów oraz
// dziennik zdarzeń oraz ustawienia ekranu (język, wyciszenie dźwięku). Cztery pierścienie rekordów
// o stałej długości; każdy rekord ma numer i CRC-16, a rekordy długu, zegara i ustawień także
// znacznik zatwierdzenia zapisywany po treści, więc zanik zasilania w trakcie zapisu zostawia
// poprzedni rekord. Obszar nie jest szyfrowany. ZNISZCZ DANE kasuje tylko dziennik zdarzeń;
// dług ciszy, zegar i ustawienia zostają. Bez zależności od Arduino: sprawdzany na komputerze
// z pamięcią w RAM.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace journal {

// Układ obszaru (adresy w FRAM). Zajmuje 0x0000..0x8FFF (36 KiB) z 512 KiB.
constexpr uint32_t DEBT_BASE = 0x000000;
constexpr uint32_t DEBT_SLOTS = 32;
constexpr uint32_t CLOCK_BASE = 0x000200;
constexpr uint32_t CLOCK_SLOTS = 32;
constexpr uint32_t SETTINGS_BASE = 0x000400;
constexpr uint32_t SETTINGS_SLOTS = 32;
constexpr uint32_t EVENT_BASE = 0x001000;
constexpr uint32_t EVENT_SLOTS = 512;  // 512 x 64 B = 32 KiB (oprogramowanie.md)
constexpr size_t SMALL_RECORD = 16;
constexpr size_t EVENT_RECORD = 64;
constexpr size_t EVENT_TEXT = 53;
constexpr uint8_t COMMITTED = 0xA5;

struct Storage {
    virtual ~Storage() = default;
    virtual bool read(uint32_t address, uint8_t* data, size_t count) = 0;
    virtual bool write(uint32_t address, const uint8_t* data, size_t count) = 0;
};

// Rekord 16 B długu ciszy albo zegara: numer, dwie wartości, CRC, znacznik zatwierdzenia.
struct SmallRecord {
    uint32_t seq = 0;
    uint32_t a = 0;  // dług: dług [ms]; zegar: czas pracy [s]
    uint32_t b = 0;  // dług: czas pracy przy zapisie [s]; zegar: liczba restartów
                     // ustawienia: a = język + 1 (0 = niewybrany), b = znaczniki (0x100 | wyciszenie)
};

struct EventRecord {
    uint32_t seq = 0;
    uint32_t uptimeS = 0;
    char text[EVENT_TEXT + 1] = {};
};

// Kodowanie rekordów (również do testów na komputerze).
void encodeSmall(const SmallRecord& record, uint8_t out[SMALL_RECORD]);  // znacznik = 0
bool decodeSmall(const uint8_t in[SMALL_RECORD], SmallRecord& record);   // true tylko dla zatwierdzonych
void encodeEvent(const EventRecord& record, uint8_t out[EVENT_RECORD]);
bool decodeEvent(const uint8_t in[EVENT_RECORD], EventRecord& record);

class Journal {
public:
    explicit Journal(Storage& storage);

    // Przegląda pierścienie; zwraca false przy błędzie pamięci.
    bool begin();
    bool ok() const { return ok_; }
    bool debtFresh() const { return debtValid_ == 0; }  // brak poprawnego rekordu długu
    uint32_t debtValid() const { return debtValid_; }
    const SmallRecord& debt() const { return debt_; }
    const SmallRecord& clock() const { return clock_; }
    const SmallRecord& settings() const { return settings_; }
    uint32_t eventSeq() const { return event_.seq; }

    // Zapis treści, potem znacznika, potem odczyt kontrolny; false blokuje nadawanie.
    bool writeDebt(uint32_t debtMs, uint32_t uptimeS);
    bool writeClock(uint32_t uptimeS, uint32_t restarts);
    bool writeSettings(uint32_t language, uint32_t flags);  // język + 1, znaczniki ekranu (main.cpp)
    bool writeEvent(uint32_t uptimeS, const char* text);
    // Zdarzenie sprzed `back` wpisów (0 = najnowsze); false, gdy brak albo uszkodzone.
    bool readEvent(uint32_t back, EventRecord& record);
    // ZNISZCZ DANE: kasuje dziennik zdarzeń (dług ciszy, zegar i ustawienia zostają).
    bool eraseEvents();

private:
    bool scanSmall(uint32_t base, uint32_t slots, SmallRecord& latest, uint32_t& validCount);
    bool writeSmall(uint32_t base, uint32_t slots, SmallRecord& current, uint32_t a, uint32_t b);

    Storage& storage_;
    bool ok_ = false;
    SmallRecord debt_;
    uint32_t debtValid_ = 0;
    SmallRecord clock_;
    SmallRecord settings_;
    EventRecord event_;
};

}  // namespace journal
