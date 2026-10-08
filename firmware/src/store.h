// SPDX-License-Identifier: MIT
// Magazyny stacji w FRAM (docs/spec/oprogramowanie.md, "Pamięć FRAM", "Trwałość i potwierdzenia",
// "Zapisy większe niż transakcja", "Cykl życia zgłoszenia"; protokol-usb.md, "Synchronizacja").
//
// Każdy magazyn ma stałe gniazda, bez dziennika dopisywanego i kompaktowania. Rekord gniazda (512 B)
// ma nagłówek 24 B (magazyn 1, gniazdo 2, wersja formatu 1, generacja klucza 4, numer zapisu 8,
// długość 2, zapas 6), treść ≤464 B, miejsce na znacznik AEAD 16 B (zera: generacja klucza 0, rekordy
// jeszcze nie są szyfrowane, F99) i znacznik zatwierdzenia 8 B (CRC-32 bajtów 0..503 i stała).
// Gniazdo puste (same 0x00 albo 0xFF) jest wolne; rekord „wolne” niesie tylko generację gniazda.
// Rekord niepusty z błędnym znacznikiem, magazynem, gniazdem albo wersją to uszkodzenie: gniazdo
// zostaje wyłączone z użycia i liczone w diagnostyce, nigdy nie staje się samo wolnym miejscem.
//
// Każda zmiana gniazd przechodzi przez transakcję (Tx): rekord transakcji (4 KiB, dwa na zmianę)
// dostaje pełne nowe bajty wszystkich zmienianych gniazd i znacznik zatwierdzenia (COMMIT), potem
// bajty trafiają do gniazd, a rekord dostaje znacznik wykonania. Po restarcie zatwierdzona, niewykonana
// transakcja jest wykonywana ponownie tymi samymi bajtami, niezatwierdzona odrzucana. Numer zapisu
// rośnie z każdym rekordem i nie wraca (rezerwacja blokami po 1024 w dzienniku, journal.h).
//
// Rejestr zgłoszeń, skrzynka, pamięć zwolnionych wpisów i pierścień zdarzeń należą do epoki (8 B
// w treści): ZAMKNIJ ZDARZENIE to jedna transakcja nowej epoki w rekordzie meta, po której rekordy
// starej epoki są wolne, a maintain() nadpisuje je kolejnymi transakcjami (także po restarcie).
// Zbiór powtórzeń BULLETIN, konfiguracja i meta przechodzą przez ZAMKNIJ ZDARZENIE.
// Indeksy w RAM (≈15 KB) mają tylko pola potrzebne do kolejki, list ekranu i alarmów; treść SA1
// i pełne `id` czyta się z rekordu. Bez zależności od Arduino; sprawdzany na komputerze z pamięcią w RAM.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "config.h"
#include "journal.h"
#include "sa1.h"

namespace store {

// Układ FRAM (512 KiB): dziennik 0x00000–0x08FFF (journal.h), magazyny 0x09000–0x43FFF,
// tożsamość i system plików stosu 0x44000–0x7FFFF (framfs.h).
constexpr uint32_t TX_BASE = 0x009000;
constexpr uint32_t TX_AREA = 4096;
constexpr uint32_t CONFIG_BASE = 0x00B000;            // kopie A i B
constexpr uint32_t CONFIG_COPY = 8192;
constexpr uint32_t META_BASE = 0x00F000;
constexpr uint32_t BULLETIN_BASE = 0x00F200;
constexpr uint32_t BULLETIN_BLOCKS = 4;
constexpr uint32_t REGISTER_BASE = 0x010000;
constexpr uint32_t REGISTER_SLOTS = 256;
constexpr uint32_t INBOX_BASE = 0x030000;
constexpr uint32_t INBOX_SLOTS = 128;
constexpr uint32_t RELEASED_BASE = 0x040000;
constexpr uint32_t RELEASED_BLOCKS = 16;
constexpr uint32_t RING_BASE = 0x042000;
constexpr uint32_t RING_BLOCKS = 16;
constexpr uint32_t STORE_END = 0x044000;
constexpr uint32_t FRAM_END = 0x080000;               // ZNISZCZ DANE kasuje TX_BASE..FRAM_END
constexpr size_t SLOT = 512;
constexpr size_t RECORD_HEADER = 24;
constexpr size_t TAG = 16;                             // znacznik AEAD (zera do czasu szyfrowania)
constexpr size_t MARKER = 8;                           // CRC-32 i stała
constexpr size_t BODY_MAX = SLOT - RECORD_HEADER - TAG - MARKER;   // 464 B
constexpr size_t BLOCK_ENTRIES = 16;                   // wpisy 24 B w bloku 512 B
constexpr size_t ENTRY = 24;
constexpr size_t RELEASED_ENTRIES = RELEASED_BLOCKS * BLOCK_ENTRIES;   // 256
constexpr size_t RING_ENTRIES = RING_BLOCKS * BLOCK_ENTRIES;           // 256
constexpr size_t BULLETIN_ENTRIES = BULLETIN_BLOCKS * BLOCK_ENTRIES;   // 64
constexpr uint32_t BULLETIN_WINDOW = 86400;            // okno event komunikatów
constexpr size_t HASH = 16;
constexpr size_t EPOCH = 8;
constexpr size_t NONCE = 8;                            // `nonce` polecenia `test`
constexpr size_t TEST_NONCES = 8;
constexpr size_t REVISION_TIMES = 8;                   // COMMIT niepotwierdzonych rewizji (alarm)
constexpr uint32_t WRITE_BLOCK = 1024;                 // rezerwacja numerów zapisu
static_assert(RING_BASE + RING_BLOCKS * SLOT == STORE_END, "pierścień zdarzeń kończy magazyny");
static_assert(BULLETIN_BASE + BULLETIN_BLOCKS * SLOT <= REGISTER_BASE, "zbiór powtórzeń przed rejestrem");
static_assert(CONFIG_BASE + 2 * CONFIG_COPY <= META_BASE, "kopie konfiguracji przed meta");
static_assert(TX_BASE + 2 * TX_AREA <= CONFIG_BASE, "rekordy transakcji przed konfiguracją");

// Magazyn w nagłówku rekordu (rekordu nie da się przenieść do innego magazynu ani gniazda).
enum Kind : uint8_t { CONFIG = 1, META = 2, REGISTER = 3, INBOX = 4, RELEASED = 5, BULLETIN = 6, RING = 7 };

// Etap wysyłki najnowszej rewizji (oprogramowanie.md, "Cykl życia zgłoszenia").
enum class Stage : uint8_t { SAVED, SENDING, DELIVERED, RECEIVED, CANCELLED };

enum Origin : uint8_t { BUTTONS = 0, USB = 1 };
// SENT_ONCE: `nadane` (zapis jednokrotny przed pierwszym przekazaniem do stosu); READ_MAX: STATUS
// rewizji r_max przyjęty (alarm brak_odczytu); BACKUP: liczniki i wysyłka dotyczą tożsamości zapasowej.
enum RequestFlag : uint8_t { SENT_ONCE = 0x01, READ_MAX = 0x02, BACKUP = 0x04 };

struct RevisionTime {
    uint16_t revision = 0;
    uint32_t commitS = 0;
};

// Wpis rejestru: najnowsza rewizja z treścią, wysyłka i decyzja odbiorcy.
struct Request {
    uint16_t gen = 0;            // generacja gniazda (zdarzenia `lost`); nadaje magazyn
    uint8_t type = sa1::REQUEST; // REQUEST albo TEST
    uint8_t origin = BUTTONS;
    uint8_t id[HASH] = {};
    uint16_t rMax = 0;
    int32_t rRcv = -1;
    Stage stage = Stage::SAVED;
    uint8_t flags = 0;
    uint8_t decision = 0;        // 0 albo stan 2–6
    uint16_t decisionRev = 0;
    uint8_t urgency = 0;
    uint8_t category = 0;
    uint16_t people = 0;
    uint16_t attempts = 0;       // próby nadania r_max
    uint32_t statusHi = 0;
    uint32_t replyHi = 0;
    uint32_t createdS = 0;       // czasy dla obsługi (journal.h)
    uint32_t changedS = 0;
    uint32_t receivedS = 0;      // RECEIVED r_max
    uint32_t nextTryS = 0;
    uint32_t firstSentS = 0;     // pierwsze przekazanie r_max (TEST: test_wyslany)
    // COMMIT rewizji nowszych niż r_rcv, rosnąco; przy więcej niż 8 wypada druga najstarsza
    // (najstarsza wyznacza alarm), więc alarm nigdy nie przychodzi później, niż wynika z COMMIT.
    uint8_t revisionCount = 0;
    RevisionTime revisions[REVISION_TIMES];
    uint8_t nonce[NONCE] = {};   // TEST z polecenia `test`
    uint16_t sa1Length = 0;
    char sa1[sa1::MAX_CONTENT + 1] = {};
};

enum class SlotState : uint8_t { FREE, USED, CORRUPT, STALE };   // STALE: rekord starej epoki do nadpisania

// Indeks wpisu w RAM; pełny wpis czyta readRequest.
struct RequestIndex {
    SlotState state = SlotState::FREE;
    uint8_t type = 0;
    Stage stage = Stage::SAVED;
    uint8_t flags = 0;
    uint8_t decision = 0;
    uint8_t urgency = 0;
    uint8_t category = 0;
    uint16_t gen = 0;
    uint16_t rMax = 0;
    uint16_t decisionRev = 0;
    uint16_t attempts = 0;
    uint32_t idPrefix = 0;
    uint32_t commitS = 0;        // COMMIT r_max (kolejność w kolejce)
    uint32_t changedS = 0;
    // Początek alarmu: przed RECEIVED COMMIT najstarszej niepotwierdzonej rewizji (TEST: pierwsze
    // nadanie, ważne ze znacznikiem SENT_ONCE), po RECEIVED czas RECEIVED r_max.
    uint32_t alarmS = 0;
    uint32_t nextTryS = 0;
    bool used() const { return state == SlotState::USED; }
    uint16_t number() const;     // krótki numer
};

// Wiadomość skrzynki (REPLY, BULLETIN).
struct Message {
    uint16_t gen = 0;
    uint8_t type = sa1::REPLY;
    uint8_t source = config::MAIN;   // tożsamość odbiorcy, od której przyszła
    bool read = false;
    uint8_t id[HASH] = {};
    uint16_t revision = 0;
    uint32_t event = 0;
    uint32_t number = 0;         // `msg`: numer zdarzenia `msg` w epoce
    uint32_t receivedS = 0;
    uint16_t sa1Length = 0;
    char sa1[sa1::MAX_CONTENT + 1] = {};
};

struct MessageIndex {
    SlotState state = SlotState::FREE;
    uint8_t type = 0;
    uint8_t source = 0;
    bool read = false;
    uint16_t gen = 0;
    uint32_t idPrefix = 0;
    uint32_t number = 0;
    uint32_t receivedS = 0;
    bool used() const { return state == SlotState::USED; }
};

// Zwolniony wpis rejestru (protokol-usb.md, "Niepewny wynik polecenia").
struct Released {
    uint8_t id[HASH] = {};
    uint16_t revision = 0;
    uint32_t ev = 0;             // numer zdarzenia `released`; 0 = wpis pusty
    uint16_t number = 0;
    bool cancelled = false;
};

// Zdarzenie dla laptopa: wpis 24 B pierścienia bez treści SA1 (protokol-usb.md, "Synchronizacja").
enum class EventKind : uint8_t { OWN = 1, STAGE = 2, MSG = 3, RADIO = 4, STATION = 6 };
// Pierwsze wartości są równe etapom (Stage), więc zmiana etapu daje kod wprost.
enum class StageCode : uint8_t { STORED, SENDING, DELIVERED, RECEIVED, CANCELLED, SUPERSEDED, RELEASED };
const char* stageCodeName(StageCode code);   // także nazwa etapu w wierszu `snap`
enum StationWhat : uint8_t { RESTART = 0, CONFIGURED = 1, RECEIVER_BACKUP = 2, PREP = 3 };
enum RadioBits : uint8_t { RADIO_SILENCE = 0x01, RADIO_SWITCH = 0x02, RADIO_EXCEPTION = 0x04 };
struct Event {
    uint32_t ev = 0;
    uint32_t at = 0;             // czas dla obsługi
    EventKind kind = EventKind::STATION;
    // OWN: pochodzenie; STAGE: StageCode; MSG: źródło; RADIO: RadioBits; STATION: StationWhat.
    uint8_t a = 0;
    bool decisionChanged = false;   // STAGE: nowa decyzja (blokuje `close`)
    uint16_t slot = 0;           // gniazdo rejestru albo skrzynki; RELEASED: indeks pamięci zwolnionych
    uint16_t gen = 0;
    uint16_t revision = 0;
    uint8_t decision = 0;        // STAGE
    uint8_t attempt = 0;         // STAGE: próba (nasycona)
    uint16_t decisionRev = 0;
    uint32_t value = 0;          // STAGE: status_event; STATION: szczegół
};

struct TestNonce {
    uint8_t nonce[NONCE] = {};
    uint8_t id[HASH] = {};
};

// Stan stacji poza magazynami (jedno gniazdo, zawsze przez transakcję).
struct Meta {
    // Epoka pierścienia zdarzeń i protokołu USB (`epoch`). Nowa po ZAMKNIJ ZDARZENIE, ZNISZCZ DANE i po
    // odtworzeniu uszkodzonego pierścienia; numeracja tej epoki zaczyna się od ringBase + 1.
    uint8_t epoch[EPOCH] = {};
    uint32_t ringBase = 0;
    // Epoka danych: rejestr, skrzynka i pamięć zwolnionych wpisów (nowa tylko po ZAMKNIJ ZDARZENIE
    // i ZNISZCZ DANE), więc odtworzenie pierścienia ich nie usuwa.
    uint8_t dataEpoch[EPOCH] = {};
    uint32_t tombFloor = 1;          // od tego zdarzenia pamięć zwolnionych jest kompletna
    int8_t configCopy = -1;          // aktywna kopia konfiguracji (0 A, 1 B), -1 brak
    uint32_t configSeq = 0;
    uint8_t receiver = config::MAIN; // aktywna tożsamość odbiorcy (KLUCZ ZAPASOWY nieodwracalny)
    bool silence = false;            // cisza ustawiona z panelu (USB); przełącznik CISZA osobno
    bool exceptionSet = false;
    uint8_t exception[HASH] = {};    // wyjątek ciszy dla jednej pary (id, revision)
    uint16_t exceptionRev = 0;       // r_max zgłoszenia przy ustawieniu wyjątku
    bool testPaused = false;
    bool contactKnown = false;
    uint32_t contactS = 0;           // ostatnia przyjęta wiadomość od aktywnej tożsamości odbiorcy
    bool closedSet = false;          // ostatnie ZAMKNIJ ZDARZENIE (powtórzenie `close`)
    uint8_t closedEpoch[EPOCH] = {};
    uint32_t closedHead = 0;
    uint32_t bulletinFloor = 0;      // aktywnej tożsamości odbiorcy
    uint32_t bulletinMax = 0;
    uint8_t nonceNext = 0;
    TestNonce nonces[TEST_NONCES];
};

// Cisza wynikowa (oprogramowanie.md, "Tryby kryzysowe"): przełącznik CISZA ma pierwszeństwo i wyklucza
// wyjątek; wyjątek tylko przy ciszy ustawionej z panelu. Jedna reguła dla łącza, stosu, wysyłki i USB.
enum class Silence : uint8_t { OFF, FULL, EXCEPTION };
inline Silence silenceMode(const Meta& m, bool switchOn) {
    return switchOn ? Silence::FULL : !m.silence ? Silence::OFF : m.exceptionSet ? Silence::EXCEPTION : Silence::FULL;
}
inline uint8_t radioBits(const Meta& m, bool switchOn) {   // RadioBits zdarzenia `radio`
    const Silence s = silenceMode(m, switchOn);
    return static_cast<uint8_t>((s != Silence::OFF ? RADIO_SILENCE : 0) | (switchOn ? RADIO_SWITCH : 0) | (s == Silence::EXCEPTION ? RADIO_EXCEPTION : 0));
}

enum class Begin : uint8_t { OK, NEW, MEMORY, FORMAT, CORRUPT };
const char* beginName(Begin result);

struct Diagnostics {
    uint32_t corruptSlots = 0;       // gniazda wyłączone z użycia
    uint32_t replayed = 0;           // transakcje wykonane ponownie przy starcie
    uint32_t scrubbed = 0;           // gniazda starej epoki nadpisane po ZAMKNIJ ZDARZENIE
    bool configCorrupt = false;      // aktywna kopia konfiguracji nieczytelna: stacja bez konfiguracji
};

class Store;

// Transakcja: zmiany gniazd i zdarzenia, zapisane razem albo wcale. Indeksy w RAM zmieniają się
// dopiero po zatwierdzeniu i wykonaniu. Najwyżej 7 rekordów 512 B w jednym rekordzie transakcji.
class Tx {
public:
    explicit Tx(Store& store);
    // Treść gniazda; fresh: nowy wpis w gnieździe (generacja + 1), inaczej zmiana tego samego wpisu.
    void request(uint16_t slot, const Request& r, bool fresh);
    void message(uint16_t slot, const Message& m, bool fresh);
    void free(Kind kind, uint16_t slot);             // rekord „wolne” (z generacją gniazda)
    // Dopisanie do pamięci zwolnionych wpisów (ev = numer zdarzenia `released` z tej transakcji).
    void released(const Released& r);
    void bulletin(const uint8_t id[HASH], uint32_t event);   // zbiór powtórzeń aktywnej tożsamości
    Meta& meta();                                    // kopia meta do zmiany
    uint32_t event(const Event& e);                  // nadaje kolejne `ev` epoki i `at`
    uint16_t gen(Kind kind, uint16_t slot) const;    // generacja gniazda po tej transakcji
    bool commit();

private:
    friend class Store;
    static constexpr size_t MAX_CHANGES = 3;
    static constexpr size_t MAX_EVENTS = 3;
    struct Change {
        Kind kind;
        uint16_t slot;
        uint16_t length;             // 0 = rekord „wolne”
        uint8_t body[BODY_MAX];
    };
    Change* change(Kind kind, uint16_t slot);
    Store& store_;
    Change changes_[MAX_CHANGES];
    size_t count_ = 0;
    Event events_[MAX_EVENTS];
    size_t eventCount_ = 0;
    bool releasedSet_ = false;
    Released released_;
    bool bulletinSet_ = false;
    size_t bulletinIndex_ = 0;
    uint8_t bulletinId_[HASH] = {};
    uint32_t bulletinEvent_ = 0;
    bool metaSet_ = false;
    Meta meta_;
    bool overflow_ = false;
};

class Store {
public:
    // random: generator stacji (epoka); profile: profil radiowy układu (config::parse).
    Store(journal::Storage& memory, journal::Journal& journal, void (*random)(uint8_t* out, size_t count), const char* profile);
    // Przegląd: ponowne wykonanie zatwierdzonej transakcji, meta, konfiguracja, indeksy, wznowienie
    // ZNISZCZ DANE. NEW: pusta pamięć sformatowana teraz. MEMORY (błąd odczytu), FORMAT (inna wersja
    // formatu albo rekord formatu nieczytelny) i CORRUPT (meta uszkodzone albo dane bez rekordu
    // formatu): stacja bez magazynu (blad_pamieci), naprawa przez ZNISZCZ DANE.
    Begin begin();
    bool ok() const { return ok_; }
    const Diagnostics& diagnostics() const { return diag_; }
    // Czas dla obsługi do czasów rekordów i `at` zdarzeń (main.cpp ustawia go w każdym obiegu).
    void now(uint32_t nowS) { nowS_ = nowS; }
    uint32_t now() const { return nowS_; }

    // Konfiguracja: dokument zapisywany w nieaktywnej kopii, potem configCommit.
    const config::Config& config() const { return config_; }
    bool configured() const { return config_.seq != 0; }
    bool station() const { return configured() && config_.role == config::Role::STATION; }
    bool configBegin();                                                // nieaktywna kopia bez znacznika
    bool configWrite(uint32_t offset, const uint8_t* data, size_t length);
    bool configStaged(uint32_t offset, uint8_t* out, size_t length);   // odczyt zapisanej części nieaktywnej kopii
    enum class ConfigResult : uint8_t { OK, HASH, INVALID, MEMORY };
    // Kontrola SHA-256 i treści, znacznik kopii, transakcja wskaźnika ze zdarzeniem `station`.
    ConfigResult configCommit(uint32_t size, const uint8_t sha[32], const char*& detail, size_t& worst);
    uint32_t configSize() const { return configSize_; }
    bool configRead(uint32_t offset, uint8_t* out, size_t length);
    const uint8_t* configSha() const { return configSha_; }
    // Adres dołączany do zgłoszeń z przycisków: obiekt wybrany na ekranie (RAM; zapis w ustawieniach).
    size_t addressCount() const { return config_.addressCount; }
    const char* addressAt(size_t index) const { return index < config_.addressCount ? config_.addresses[index] : ""; }
    const char* address() const { return addressAt(selected_); }
    size_t selectedAddress() const { return selected_; }
    void selectAddress(size_t index) { selected_ = index < addressCount() ? static_cast<uint8_t>(index) : 0; }
    // Cel "wici.sa1" aktywnej tożsamości odbiorcy albo nullptr (bez konfiguracji stacji).
    const uint8_t* recipient() const;

    const Meta& meta() const { return meta_; }

    // Rejestr.
    const RequestIndex& request(size_t slot) const { return register_[slot]; }
    bool readRequest(size_t slot, Request& out);
    int findRequest(const uint8_t id[HASH]);           // gniazdo albo -1
    int freeRequestSlot() const;
    int closedRequest() const;                          // wpis zamknięty o najdawniejszej zmianie albo -1
    bool requestClosed(size_t slot) const;
    bool numberTaken(uint16_t number, const uint8_t id[HASH]);   // inne id w rejestrze albo zwolnionych
    size_t requestCount() const;
    size_t activeIntents() const;                       // SAVED, SENDING, DELIVERED
    size_t unsent(uint32_t& oldestS) const;             // SAVED, SENDING; COMMIT najstarszego

    // Skrzynka.
    const MessageIndex& message(size_t slot) const { return inbox_[slot]; }
    bool readMessage(size_t slot, Message& out);
    int findMessage(uint32_t number) const;
    int freeMessageSlot() const;
    size_t messageCount() const;
    size_t unread() const;

    // Pamięć zwolnionych wpisów (indeks pierścienia 0..255).
    bool releasedFind(const uint8_t id[HASH], Released& out);
    bool releasedAt(size_t index, Released& out);
    bool releasedUsed(size_t index) const { return releasedEv_[index] != 0; }
    size_t releasedNext() const { return releasedNext_; }

    // Zbiór powtórzeń BULLETIN aktywnej tożsamości odbiorcy.
    bool bulletinSeen(const uint8_t id[HASH], uint32_t event);

    // Pierścień zdarzeń.
    uint32_t head() const { return head_; }
    uint32_t minEvent() const {
        const uint32_t first = meta_.ringBase + 1;
        return head_ >= first + RING_ENTRIES ? head_ - RING_ENTRIES + 1 : first;
    }
    bool readEvent(uint32_t ev, Event& out);
    // Zdarzenie `radio`: bity ciszy i odwołanie do wyjątku z chwili zdarzenia (gniazdo i generacja wpisu
    // rejestru, rewizja wyjątku, krótki numer w `value`), bo meta zmienia się później.
    Event radioEvent(const Meta& m, bool switchOn);
    // Id wyjątku zdarzenia `radio`: z wpisu rejestru, po jego zwolnieniu z pamięci zwolnionych wpisów
    // (krótki numer jest tam jednoznaczny); false bez wyjątku albo gdy wpisu już nie ma.
    bool exceptionId(const Event& e, uint8_t id[HASH]);
    // Po zdarzeniu head nie ma zdarzeń zmieniających dane (warunek `close`).
    bool quietSince(uint32_t head);

    // ZAMKNIJ ZDARZENIE: nowa epoka w jednej transakcji; dane starej epoki nadpisuje maintain().
    // head: wartość z potwierdzonego `close`, zapamiętana do powtórzenia polecenia.
    bool close(uint32_t head);
    // Nadpisanie gniazd starej epoki (jedna transakcja na wywołanie); false, gdy nic nie zostało.
    bool maintain();
    // ZNISZCZ DANE: znacznik w dzienniku, skasowanie TX_BASE..FRAM_END i dziennika (bez długu ciszy
    // i rezerwacji numerów zapisu), nowy pusty magazyn bez tożsamości stacji.
    bool destroy();
    // Znacznik zapisanej tożsamości stacji w rekordzie formatu (rns_node).
    bool identitySaved() const;
    bool setIdentitySaved();

private:
    friend class Tx;
    bool readSlot(uint32_t address, Kind kind, uint16_t slot, uint8_t* body, size_t& length, SlotState& state, uint16_t& gen);
    void encode(Kind kind, uint16_t slot, uint64_t writeNo, const uint8_t* body, size_t length, uint8_t out[SLOT]) const;
    bool allocate(uint64_t& out);
    SlotState decode(const uint8_t record[SLOT], Kind kind, uint16_t slot, uint8_t* body, size_t& length, uint16_t& gen) const;
    bool applyTx(uint32_t area, bool absorbRecords, bool& found);
    bool recover();
    bool loadConfig();
    bool scan();
    bool format(uint32_t flags);
    void absorb(Kind kind, uint16_t slot, const uint8_t* body, size_t length, SlotState state, uint16_t gen);
    void staleAll();
    void staleRing();
    bool recoverBlocks();   // po uszkodzonych blokach pierścienia, pamięci zwolnionych albo zbioru BULLETIN
    bool readBlock(Kind kind, uint16_t block, uint8_t body[BODY_MAX]);
    bool copyCrc(uint32_t base, uint32_t& crc);
    bool hashCopy(int8_t copy, uint32_t size, uint8_t out[32]);
    bool commitTx(Tx& tx);

    journal::Storage& memory_;
    journal::Journal& journal_;
    void (*random_)(uint8_t*, size_t);
    const char* profile_;
    bool ok_ = false;
    uint32_t nowS_ = 0;
    Diagnostics diag_;
    config::Config config_;
    uint32_t configSize_ = 0;
    uint8_t configSha_[32] = {};
    int8_t configNext_ = -1;           // kopia w zapisie (configBegin)
    uint8_t selected_ = 0;
    Meta meta_;
    RequestIndex register_[REGISTER_SLOTS];
    MessageIndex inbox_[INBOX_SLOTS];
    uint32_t releasedPrefix_[RELEASED_ENTRIES] = {};
    uint32_t releasedEv_[RELEASED_ENTRIES] = {};
    uint16_t releasedNumber_[RELEASED_ENTRIES] = {};   // krótki numer, bit 15: anulowany
    SlotState releasedState_[RELEASED_BLOCKS] = {};
    size_t releasedNext_ = 0;
    uint32_t bulletinPrefix_[BULLETIN_ENTRIES] = {};
    uint32_t bulletinEvent_[BULLETIN_ENTRIES] = {};    // 0 = wpis pusty
    uint8_t bulletinSource_[BULLETIN_ENTRIES] = {};    // tożsamość odbiorcy wpisu
    SlotState bulletinState_[BULLETIN_BLOCKS] = {};
    SlotState ringState_[RING_BLOCKS] = {};
    uint32_t head_ = 0;
    // Uszkodzone bloki przy starcie (bity: 1 pierścień, 2 pamięć zwolnionych, 4 zbiór BULLETIN).
    uint8_t corruptBlocks_ = 0;
    uint64_t nextWrite_ = 0;
    uint64_t reservedUpper_ = 0;
    uint8_t txArea_ = 0;               // rekord transakcji następnej transakcji
};

// Krótki numer = pierwsze 16 bitów id modulo 10 000; przedrostek = pierwsze 4 B id.
uint16_t shortNumber(const uint8_t id[HASH]);
uint32_t idPrefix(const uint8_t id[HASH]);
uint16_t prefixNumber(uint32_t prefix);   // krótki numer z przedrostka

}  // namespace store
