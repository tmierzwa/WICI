// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// Tablica znanych celów i tras w pamięci trwałej (etap R2, firmware/reticulum-core.md; specyfikacja:
// docs/spec/oprogramowanie.md, „Pojemności stosu”). Odpowiada w Pythonie RNS/Identity.py:
// known_destinations i known_ratchets oraz RNS/Transport.py: path_table z ogłoszeniem w pamięci
// podręcznej (Transport.cache, get_cached_packet), zapisywanym przez save_path_table.
//
// Pełne wpisy leżą w gniazdach o stałym rozmiarze (TABLE_SLOT_SIZE) w obszarze pamięci trwałej, który
// podaje wywołujący (TableStorage); w RAM jest tylko indeks: skrót celu, czas ostatniego użycia wpisu
// i trasy oraz znacznik trasy dla każdego gniazda. Gniazd jest o jedno więcej niż wpisów, więc zmiana
// wpisu zawsze trafia do wolnego gniazda, a stare gniazdo jest unieważniane dopiero po zatwierdzeniu
// nowego: zanik zasilania w dowolnym zapisie zostawia poprzednią albo nową treść zmienianego wpisu. Wpis
// wypierany dla nowego celu jest unieważniany przed zapisem nowego, więc zanik w tym zapisie go gubi.
//
// Gniazdo (little-endian): 0 znacznik zatwierdzenia (0xA5), 1 wersja formatu, 2 numer gniazda (2 B),
// 4 numer zapisu (4 B), 8 znaczniki (bit 0 trasa, 1 ratchet, 2 flaga kontekstu, 3 interfejs trasy: 1 bit,
// więc najwyżej 2 interfejsy; gniazdo sprzed etapu R4 ma 0, czyli interfejs 0, P1), 9 skoki, 10 długość
// ogłoszenia (2 B), 12 ostatnie użycie [s], 16 cel, 32 wygaśnięcie trasy [s], 36 ostatnie użycie trasy [s], 40 czas przyjęcia ratchetu [s], 44 czas
// emisji ogłoszenia z ratchetem [s], 48 następny skok, 64 ratchet, 96 dane ogłoszenia (do
// ANNOUNCE_FORWARDABLE_SIZE), 561 CRC-32 bajtów 1..560. Dane ogłoszenia zaczynają się kluczem publicznym
// (64 B) i mają skrót losowy od bajtu 74, więc gniazdo nie trzyma ich osobno: bez ogłoszenia w pamięci
// podręcznej (np. cel z karty) te same miejsca trzymają sam klucz i skrót losowy. Zapis: znacznik 0, bajty
// 1..567, znacznik 0xA5; unieważnienie: znacznik 0. Montowanie czyta tylko nagłówek (40 B na gniazdo:
// znacznik, wersja, numer gniazda, bez CRC); CRC sprawdza każdy pełny odczyt wpisu, a wpis z błędną
// treścią wypada z indeksu (gniazdo wolne, licznik corrupt()). Błąd samego odczytu nie usuwa wpisu.
#pragma once

#include "announce.h"
#include "rnscore.h"

namespace rnscore {

constexpr size_t KNOWN_MAX = 256;                       // docs/spec/oprogramowanie.md, „Pojemności stosu”
constexpr size_t TABLE_SLOTS = KNOWN_MAX + 1;           // jedno gniazdo zapasowe do zapisu z kopią
constexpr size_t TABLE_SLOT_SIZE = 568;
constexpr uint32_t TABLE_AREA = TABLE_SLOTS * TABLE_SLOT_SIZE;   // 145 976 B
constexpr uint32_t RATCHET_EXPIRY_S = 60UL * 60 * 24 * 30;      // RNS/Identity.py: RATCHET_EXPIRY
constexpr uint32_t DESTINATION_TIMEOUT_S = 60UL * 60 * 24 * 7;   // RNS/Transport.py: DESTINATION_TIMEOUT

// Obszar gniazd w pamięci trwałej; adresy od 0 do TABLE_AREA - 1.
struct TableStorage {
    virtual ~TableStorage() = default;
    virtual bool read(uint32_t offset, uint8_t* data, size_t count) = 0;
    virtual bool write(uint32_t offset, const uint8_t* data, size_t count) = 0;
};

// Wpis znanego celu: RNS/Identity.py: known_destinations i known_ratchets, RNS/Transport.py: path_table.
// Z listy skrótów losowych ogłoszeń (Python: do 64) wpis trzyma tylko ostatni (tabela różnic).
struct KnownDestination {
    uint8_t destination[TRUNCATED_HASH_SIZE];
    uint8_t publicKey[KEY_SIZE];
    uint8_t ratchet[RATCHET_SIZE];
    uint8_t randomHash[RANDOM_HASH_SIZE];       // ostatni skrót losowy ogłoszenia przyjętego do trasy
    uint8_t nextHop[TRUNCATED_HASH_SIZE];       // identyfikator transportu albo sam cel (sąsiad)
    uint32_t pathExpiresS;                      // IDX_PT_EXPIRES: should_add
    uint32_t pathUsedS;                         // IDX_PT_TIMESTAMP: trasa nieużywana DESTINATION_TIMEOUT wygasa
    uint32_t usedS;                             // ostatnie użycie: do wypierania
    uint32_t ratchetS;                          // przyjęcie ratchetu (Identity._remember_ratchet: "received")
    uint32_t ratchetEmittedS;                   // czas emisji ogłoszenia z zapisanym ratchetem (nasycony)
    uint16_t announceLength;                    // ogłoszenie w pamięci podręcznej (0: brak, np. cel z karty)
    uint8_t hops;
    bool hasRatchet;
    bool hasPath;
    bool contextFlag;                           // flaga kontekstu ogłoszenia w pamięci podręcznej (ratchet)
    uint8_t interface;                          // IDX_PT_RVCD_IF: interfejs ogłoszenia trasy (0 albo 1)
};

class Table {
public:
    // Montowanie: indeks z nagłówków gniazd; z dwóch zatwierdzonych gniazd jednego celu (zanik zasilania
    // między zapisem nowego a unieważnieniem starego) zostaje to z większym numerem zapisu, a drugie jest
    // unieważniane (1 B), żeby nie wróciło po wyparciu zwycięskiego. Poza tym bez zapisów.
    // nowS: czas pracy przy starcie (ratchety sprzed startu wygasają jak przy wczytaniu w Pythonie);
    // interfaces: liczba interfejsów transportu. Trasa przez interfejs spoza tej liczby (gniazdo zapisane
    // przy innej konfiguracji) to brak trasy, jak w Pythonie przy wczytaniu path_table bez interfejsu.
    void begin(TableStorage& storage, uint32_t nowS, uint8_t interfaces = 1);
    int find(const uint8_t destination[TRUNCATED_HASH_SIZE]) const;   // gniazdo albo -1
    // Odczyt wpisu z gniazda ze sprawdzeniem znacznika, numeru gniazda, celu i CRC; przy błędnej treści
    // wpis wypada z indeksu (corrupt()), przy błędzie odczytu zostaje (false, ponowny odczyt później).
    // Trasa nieużywana dłużej niż DESTINATION_TIMEOUT_S (Transport.jobs: usuwana z path_table) wraca bez
    // trasy; ratchet zapamiętany przed startem i starszy niż RATCHET_EXPIRY_S (Identity.get_ratchet) bez
    // ratchetu.
    bool read(int slot, KnownDestination& out, uint32_t nowS);
    // Sam klucz publiczny z gniazda (64 B, bez CRC): tanie sprawdzenie kolizji przed weryfikacją podpisu.
    bool readKey(int slot, uint8_t out[KEY_SIZE]);
    // Dane ogłoszenia z ostatniego udanego read() (announceLength bajtów); ważne do następnej operacji.
    const uint8_t* announce() const;
    // Ogłoszenie w pamięci podręcznej przy zapisie: KEEP zostawia ogłoszenie z gniazda slot (z ostatniego
    // read() tego gniazda), SET zapisuje nowe (length ≤ ANNOUNCE_FORWARDABLE_SIZE; 0: bez ogłoszenia).
    enum class Cached : uint8_t { KEEP, SET };
    // Zapis wpisu: slot = gniazdo z find() (zmiana) albo -1 (nowy cel). Ogłoszenie musi zaczynać się
    // kluczem wpisu i mieć jego skrót losowy; inne nie trafia do pamięci podręcznej. Nowy cel przy pełnej
    // tablicy wypiera najdawniej używany cel bez ochrony (pinned). Zwraca nowe gniazdo albo -1 (wszystkie
    // wpisy chronione, błąd zapisu).
    int write(int slot, const KnownDestination& entry, Cached cached, const uint8_t* announce, size_t length,
              bool (*pinned)(const uint8_t destination[TRUNCATED_HASH_SIZE], void* context), void* context);
    // Ostatnie użycie wpisu (path: także trasy) tylko w RAM; do FRAM trafia z następną zmianą wpisu.
    void touch(int slot, uint32_t nowS, bool path);
    // Transport.jobs: znacznik trasy nieużywanej DESTINATION_TIMEOUT_S skasowany; ponowienie unieważnień,
    // które się nie udały (błąd zapisu).
    void expire(uint32_t nowS);
    bool hasPath(int slot) const;
    // Interfejs trasy z indeksu (bez odczytu gniazda); bez trasy: -1.
    int pathInterface(int slot) const;
    // Do max celów z trasą przez interfejs iface, najpierw ostatnio używane trasy (indeks); hops ≠ 0: tylko
    // trasy o tej liczbie skoków (bajt gniazda w FRAM, bez CRC). Węzeł stanowiska odtwarza z tego po starcie
    // cele komputera (interfejs USB, 1 skok).
    size_t routes(uint8_t iface, uint8_t hops, uint8_t (*out)[TRUNCATED_HASH_SIZE], size_t max) const;
    size_t size() const { return count_; }
    size_t paths() const;
    uint32_t writes() const { return writes_; }    // zapisy gniazd od startu (diagnostyka)
    uint32_t corrupt() const { return corrupt_; }  // gniazda z błędną treścią od startu (diagnostyka)
    void setLimit(size_t limit);   // próby: mniejsza tablica (1..KNOWN_MAX)
    void clear();                  // halt: indeks i bufor skasowane, bez zapisów

private:
    struct Index {
        uint8_t destination[TRUNCATED_HASH_SIZE];
        uint32_t usedS;
        uint32_t pathUsedS;
    };
    bool live(size_t slot) const { return live_[slot / 8] & (1u << (slot % 8)); }
    void setBit(uint8_t* bits, size_t slot, bool on);
    void drop(size_t slot);
    bool load(size_t slot);   // gniazdo do bufora: znacznik, numer, cel, CRC; przy błędnej treści drop
    bool invalidate(size_t slot);   // przy błędzie gniazdo czeka w stale_ na ponowienie
    int victim(int keep, bool (*pinned)(const uint8_t*, void*), void* context) const;
    bool routeMatches(size_t slot, uint8_t iface, uint8_t hops) const;   // routes()
    bool readHeader(size_t slot, uint8_t* header);   // begin(): nagłówek gniazda (40 B)
    void mount(size_t slot, const uint8_t* header, uint32_t nowS);   // begin(): gniazdo z nagłówka do indeksu

    TableStorage* storage_ = nullptr;
    Index index_[TABLE_SLOTS] = {};
    uint8_t live_[(TABLE_SLOTS + 7) / 8] = {};
    uint8_t path_[(TABLE_SLOTS + 7) / 8] = {};
    uint8_t second_[(TABLE_SLOTS + 7) / 8] = {};   // trasa przez interfejs 1 (flaga gniazda, INTERFACES_MAX = 2)
    uint8_t stale_[(TABLE_SLOTS + 7) / 8] = {};   // gniazda poza indeksem do unieważnienia w FRAM
    uint8_t buffer_[TABLE_SLOT_SIZE] = {};   // obraz gniazda (odczyt i zapis), poza stosem
    // Same zera na starcie (obiekt w .bss, nie kopiowany z flash): gniazdo obrazu w buforze + 1 (0: brak)
    // i limit (0: KNOWN_MAX).
    size_t bufferSlot_ = 0;
    size_t count_ = 0;
    size_t limit_ = 0;
    uint32_t sequence_ = 0;
    uint32_t bootS_ = 0;
    uint32_t writes_ = 0;
    uint32_t corrupt_ = 0;
    uint8_t interfaces_ = 0;   // z begin()
};

}  // namespace rnscore
