// SPDX-License-Identifier: MIT
// Jawny obszar FRAM stacji (docs/spec/oprogramowanie.md, "Pamięć FRAM", wiersz „licznik czasu,
// dług ciszy, rezerwacja nonce, fram_format, ustawienia ekranu”, oraz "Czas"; radio.md, "Dostęp
// do kanału"): pięć pierścieni małych rekordów i dziennik zdarzeń stacji (diagnostyka).
// - dług ciszy: dług [ms] i czas pracy przy zapisie;
// - licznik czasu pracy: licznik [s], suma przeskoków restartów S [s] i liczba startów; przy
//   starcie licznik i S rosną o 60 s i są zapisywane, zanim stacja nada ramkę albo utworzy rekord
//   (startClock), więc czas po restarcie nigdy nie cofa się wobec czasu sprzed restartu;
//   czas dla obsługi = licznik − S;
// - ustawienia ekranu: język i znaczniki (main.cpp);
// - rezerwacja numerów zapisu rekordów magazynu (store.h): górna granica bloku 1024 numerów,
//   zapisywana przed użyciem pierwszego numeru bloku;
// - wersja formatu FRAM (`fram_format`), stan (zainicjowana albo w trakcie ZNISZCZ DANE) i znacznik
//   zapisanej tożsamości stacji. Brak każdego rekordu przy pustej pamięci to nowa stacja; rekordy
//   niepuste i niepoprawne bez żadnego poprawnego to uszkodzenie, nie nowa stacja (formatState),
//   a pusty rekord tożsamości przy znaczniku to uszkodzenie, nie powód do nowej tożsamości;
// - wejścia w tryb przygotowania (oprogramowanie.md, "Tryb przygotowania i naklejka serwisowa"):
//   licznik wejść, który tylko rośnie, licznik czasu pracy przy wejściu i zmiany wykonane w tym
//   wejściu (nowa konfiguracja i 16 bitów jej SHA-256). Wejście zapisuje się, zanim tryb zacznie
//   działać (enterPrep); każda zmiana dopisuje rekord tego samego wejścia. Pierścień ma 10 rekordów
//   poza dziennikiem zdarzeń, więc zdarzenia diagnostyczne go nie nadpisują.
// Rekordy 24 B mają numer, trzy wartości, CRC-16 i znacznik zatwierdzenia zapisywany po treści,
// więc zanik zasilania w trakcie zapisu zostawia poprzedni rekord. Obszar nie jest szyfrowany.
// ZNISZCZ DANE (erase) kasuje dziennik zdarzeń, zegar i ustawienia; dług ciszy, rezerwacja numerów
// zapisu, rekord formatu i wejścia w tryb przygotowania zostają. Bez zależności od Arduino: sprawdzany na komputerze z pamięcią w RAM.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace journal {

// Układ obszaru (adresy w FRAM). Zajmuje 0x0000..0x8FFF (36 KiB) z 512 KiB.
constexpr uint32_t SMALL_SLOTS = 32;
constexpr size_t SMALL_RECORD = 24;
constexpr uint32_t RING_SPAN = SMALL_SLOTS * SMALL_RECORD;   // 768 B
constexpr uint32_t DEBT_BASE = 0x000000;
constexpr uint32_t CLOCK_BASE = DEBT_BASE + RING_SPAN;
constexpr uint32_t SETTINGS_BASE = CLOCK_BASE + RING_SPAN;
constexpr uint32_t RESERVE_BASE = SETTINGS_BASE + RING_SPAN;
constexpr uint32_t FORMAT_BASE = RESERVE_BASE + RING_SPAN;
constexpr uint32_t PREP_BASE = FORMAT_BASE + RING_SPAN;
constexpr uint32_t PREP_SLOTS = 10;       // 240 B między pierścieniem formatu a dziennikiem zdarzeń
constexpr uint32_t EVENT_BASE = 0x001000;
constexpr uint32_t EVENT_SLOTS = 512;  // 512 x 64 B = 32 KiB (oprogramowanie.md)
constexpr size_t EVENT_RECORD = 64;
constexpr size_t EVENT_TEXT = 53;
constexpr uint8_t COMMITTED = 0xA5;
constexpr uint32_t RESTART_SKIP_S = 60;   // przesunięcie licznika przy starcie (oprogramowanie.md, "Czas")
constexpr uint32_t FRAM_FORMAT = 2;       // wersja formatu rekordów magazynu (fram_format)
constexpr uint32_t FORMAT_IDENTITY = 0x01;   // tożsamość stacji zapisana w FRAM
constexpr uint32_t PREP_CONFIG = 0x0001;   // w wejściu zatwierdzono nową konfigurację (`configure`)
constexpr uint32_t PREP_RESTARTED = 0x8000;  // licznik niepewny po uszkodzonym rekordzie pierścienia (przechodzi dalej)
constexpr uint32_t PREP_CHANGES = 0xFFFF;  // młodsze 16 bitów c: zmiany; starsze: 16 bitów SHA-256 konfiguracji
static_assert(PREP_BASE + PREP_SLOTS * SMALL_RECORD <= EVENT_BASE, "pierścienie przed dziennikiem zdarzeń");

struct Storage {
    virtual ~Storage() = default;
    virtual bool read(uint32_t address, uint8_t* data, size_t count) = 0;
    virtual bool write(uint32_t address, const uint8_t* data, size_t count) = 0;
};

// Rekord 24 B: numer, trzy wartości, CRC, znacznik zatwierdzenia.
struct SmallRecord {
    uint32_t seq = 0;
    uint32_t a = 0;  // dług: dług [ms]; zegar: licznik [s]; ustawienia: język + 1; rezerwacja: młodsze słowo;
                     // format: wersja
    uint32_t b = 0;  // dług: czas pracy przy zapisie [s]; zegar: suma przeskoków S [s]; ustawienia: znaczniki;
                     // rezerwacja: starsze słowo; format: stan (FormatState)
    uint32_t c = 0;  // zegar: liczba startów; format: znaczniki (FORMAT_IDENTITY);
                     // wejścia: zmiany (PREP_CHANGES) i SHA-256 konfiguracji << 16
    // Wejścia w tryb przygotowania: a = numer wejścia (licznik), b = licznik czasu pracy przy wejściu [s].
};

struct EventRecord {
    uint32_t seq = 0;
    uint32_t uptimeS = 0;
    char text[EVENT_TEXT + 1] = {};
};

enum class FormatState : uint8_t { BLANK, READY, DESTROYING, CORRUPT };

// Kodowanie rekordów (również do testów na komputerze).
void encodeSmall(const SmallRecord& record, uint8_t out[SMALL_RECORD]);  // znacznik = 0
bool decodeSmall(const uint8_t in[SMALL_RECORD], SmallRecord& record);   // true tylko dla zatwierdzonych
void encodeEvent(const EventRecord& record, uint8_t out[EVENT_RECORD]);
bool decodeEvent(const uint8_t in[EVENT_RECORD], EventRecord& record);
bool blank(const uint8_t* data, size_t length);   // same 0x00 albo same 0xFF (nowa albo skasowana pamięć)

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

    // Start zegara: licznik + 60 s, S + 60 s, liczba startów + 1, zapisane od razu (przed pierwszą
    // ramką i pierwszym rekordem). false blokuje pracę z dziennikiem.
    bool startClock();
    uint32_t counterAtStart() const { return clock_.a; }
    uint32_t skipS() const { return clock_.b; }
    uint32_t starts() const { return clock_.c; }

    // Zapis treści, potem znacznika, potem odczyt kontrolny; false blokuje nadawanie.
    bool writeDebt(uint32_t debtMs, uint32_t uptimeS);
    bool writeClock(uint32_t counterS);   // co 60 s; S i liczba startów bez zmian
    bool writeSettings(uint32_t language, uint32_t flags);  // język + 1, znaczniki ekranu (main.cpp)
    bool writeEvent(uint32_t uptimeS, const char* text);
    // Zdarzenie sprzed `back` wpisów (0 = najnowsze); false, gdy brak albo uszkodzone.
    bool readEvent(uint32_t back, EventRecord& record);

    // Rezerwacja numerów zapisu (górna granica bloku, wyłącznie rosnąca).
    uint64_t reservation() const { return (static_cast<uint64_t>(reserve_.b) << 32) | reserve_.a; }
    bool writeReservation(uint64_t upper);

    // Wersja i stan formatu FRAM: BLANK (nowa pamięć), READY, DESTROYING albo CORRUPT.
    FormatState formatState() const { return formatState_; }
    uint32_t formatVersion() const { return format_.a; }
    uint32_t formatFlags() const { return format_.c; }
    bool writeFormat(FormatState state, uint32_t flags);

    // Wejścia w tryb przygotowania. enterPrep: numer wejścia + 1 przy liczniku czasu counterS,
    // zapisany przed włączeniem trybu (false: tryb się nie włącza). notePrep: zmiana w bieżącym wejściu
    // (PREP_CONFIG i 16 bitów SHA-256 konfiguracji). prepCorrupt: pierścień ma zatwierdzony rekord
    // z błędnym CRC, który mógł być najnowszym wejściem, więc licznik jest niepewny; następne wejście
    // dostaje numer po najnowszym poprawnym (albo 1), znacznik PREP_RESTARTED i czyści uszkodzone gniazda.
    bool enterPrep(uint32_t counterS);
    bool notePrep(uint32_t change, uint16_t configSha);
    uint32_t prepEntries() const { return prep_.a; }
    uint32_t prepAtS() const { return prep_.b; }
    uint32_t prepChanges() const { return prep_.c & PREP_CHANGES & ~PREP_RESTARTED; }
    bool prepRestarted() const { return prep_.c & PREP_RESTARTED; }
    uint16_t prepConfigSha() const { return static_cast<uint16_t>(prep_.c >> 16); }
    bool prepCorrupt() const { return prepCorrupt_; }
    const SmallRecord& prep() const { return prep_; }

    // ZNISZCZ DANE: dziennik zdarzeń, zegar i ustawienia; dług ciszy, rezerwacja, format i wejścia
    // w tryb przygotowania zostają.
    bool erase();

private:
    bool scanSmall(uint32_t base, SmallRecord& latest, uint32_t& validCount, uint32_t& corruptCount, uint32_t slots = SMALL_SLOTS);
    bool writeSmall(uint32_t base, SmallRecord& current, uint32_t a, uint32_t b, uint32_t c, uint32_t slots = SMALL_SLOTS);
    bool eraseRing(uint32_t base, SmallRecord& current);

    Storage& storage_;
    bool ok_ = false;
    SmallRecord debt_;
    uint32_t debtValid_ = 0;
    SmallRecord clock_;
    SmallRecord settings_;
    SmallRecord reserve_;
    SmallRecord format_;
    SmallRecord prep_;
    bool prepCorrupt_ = false;
    uint32_t prepCorruptSlots_ = 0;   // bity gniazd pierścienia wejść z rekordem uszkodzonym
    FormatState formatState_ = FormatState::BLANK;
    EventRecord event_;
};

}  // namespace journal
