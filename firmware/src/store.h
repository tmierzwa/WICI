// SPDX-License-Identifier: MIT
// Trwałe struktury stacji w FRAM (docs/spec/oprogramowanie.md, "Trwałość i potwierdzenia",
// "Protokół USB laptop–stacja"): konfiguracja z `configure`, kolejka wychodząca (128 intencji),
// skrzynka odbiorcza (128 wiadomości), zdarzenia do laptopa czekające na `ack` (128) oraz pamięć
// najwyższego event na id po usunięciu treści. Każdy rekord ma numer, CRC-16 i znacznik
// zatwierdzenia zapisywany jako ostatni bajt; część zmienna rekordu (stan intencji, odczyt,
// potwierdzenie) ma własne CRC i znacznik, a jej uszkodzenie cofa stan do wartości domyślnych.
// Rekordy nie są jeszcze szyfrowane (AEAD z kluczem w MCU przyjdzie ze stosem). Bez zależności
// od Arduino; sprawdzany na komputerze z pamięcią w RAM.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "journal.h"
#include "sa1.h"

namespace store {

constexpr uint32_t CONFIG_BASE = 0x009000;
constexpr size_t CONFIG_SLOT = 4096;
constexpr uint32_t CONFIG_SLOTS = 2;
constexpr uint32_t QUEUE_BASE = 0x010000;
constexpr uint32_t QUEUE_SLOTS = 128;
constexpr uint32_t INBOX_BASE = 0x020000;
constexpr uint32_t INBOX_SLOTS = 128;
constexpr uint32_t NOTE_BASE = 0x030000;
constexpr uint32_t NOTE_SLOTS = 128;
constexpr uint32_t SEEN_BASE = 0x040000;
constexpr uint32_t SEEN_SLOTS = 256;
constexpr size_t RECORD = 512;        // kolejka, skrzynka, zdarzenia
constexpr size_t SEEN_RECORD = 32;
constexpr size_t STATE_OFFSET = 448;  // część zmienna rekordu 512 B
constexpr size_t HASH = 16;           // skrót adresu LXMF i identyfikator SA1 w bajtach
constexpr size_t NOTE_TEXT = 400;
constexpr size_t PHRASES = 11;
constexpr size_t PHRASE_MAX = 96;
constexpr size_t ADDRESS_MAX = 64;
constexpr uint8_t COMMITTED = journal::COMMITTED;

enum Role : uint8_t { STATION = 0, OSP = 1 };

struct Config {
    uint32_t seq = 0;
    uint8_t role = STATION;
    uint8_t activeOsp = 0;      // 0 główna, 1 zapasowa
    uint16_t stations = 0;      // liczba stacji w sieci (okno TEST startowego); 0 = nieznana
    char address[ADDRESS_MAX + 1] = {};
    uint8_t osp[2][HASH] = {};  // skróty adresów tożsamości OSP: główna, zapasowa
    uint8_t phraseCount = 0;
    char phrases[PHRASES][3][PHRASE_MAX + 1] = {};  // PL (wysyłana), UK, EN (ekran)
    uint8_t ifac[HASH] = {};    // kod dostępu sieci (IFAC)
};

// Flagi stanu intencji w kolejce.
enum QueueFlag : uint8_t { ACTIVE = 0x01, DONE = 0x02, REPLACED = 0x04, CANCELLED = 0x08, SENT = 0x10 };

struct QueueRecord {
    uint32_t seq = 0;
    uint32_t createdS = 0;
    uint8_t type = 0;
    uint16_t revision = 0;
    uint32_t event = 0;         // STATUS, REPLY, BULLETIN; 0 dla pozostałych
    uint8_t to[HASH] = {};
    uint8_t id[HASH] = {};
    char sa1[sa1::MAX_CONTENT + 1] = {};
    uint16_t sa1Length = 0;
    // część zmienna
    uint8_t flags = ACTIVE;
    uint16_t attempts = 0;
    uint32_t nextTryS = 0;
    uint32_t statusEvent = 0;   // najwyższy event z RECEIVED/STATUS dla tej intencji
    uint8_t state = 0;          // stan 1-6; 0 = brak potwierdzenia
    uint32_t updatedS = 0;
};

struct InboxRecord {
    uint32_t seq = 0;
    uint32_t receivedS = 0;
    uint8_t type = 0;
    uint16_t revision = 0;
    uint32_t event = 0;
    uint8_t source[HASH] = {};
    uint8_t id[HASH] = {};
    char sa1[sa1::MAX_CONTENT + 1] = {};
    uint16_t sa1Length = 0;
    // część zmienna
    uint8_t flags = 0;          // bit 0 = przeczytana
};

enum NoteKind : uint8_t { NOTE_MESSAGE = 1, NOTE_RADIO = 2, NOTE_INCOMING = 3, NOTE_STATION = 4 };

struct NoteRecord {
    uint32_t seq = 0;
    uint32_t createdS = 0;
    uint8_t kind = NOTE_MESSAGE;
    uint32_t ref = 0;           // numer rekordu skrzynki albo 0
    char text[NOTE_TEXT + 1] = {};  // pola JSON zdarzenia (bez nawiasów zewnętrznych)
    // część zmienna
    bool acked = false;
};

struct QueueEntry {
    uint32_t seq = 0;
    uint32_t createdS = 0;
    uint8_t type = 0;
    uint8_t flags = 0;
    uint16_t revision = 0;
    uint32_t event = 0;
    uint32_t nextTryS = 0;
    uint8_t to[HASH] = {};
    uint8_t id[HASH] = {};
};

struct InboxEntry {
    uint32_t seq = 0;
    uint8_t type = 0;
    uint8_t flags = 0;
    uint16_t revision = 0;
    uint32_t event = 0;
    uint8_t source[HASH] = {};
    uint8_t id[HASH] = {};
};

struct NoteEntry {
    uint32_t seq = 0;
    bool acked = false;
};

enum class Put : uint8_t { STORED, DUPLICATE, CONFLICT, FULL, ERROR };
const char* putName(Put result);

class Store {
public:
    explicit Store(journal::Storage& storage);
    bool begin();  // przegląda wszystkie pierścienie; false przy błędzie pamięci
    bool ok() const { return ok_; }

    const Config& config() const { return config_; }
    bool configured() const { return config_.seq != 0; }
    bool writeConfig(const Config& config);

    // Kolejka: klucz (to, typ, id, revision, event); ta sama treść = DUPLICATE (seq rekordu w record.seq),
    // inna treść = CONFLICT; 128 żywych intencji = FULL. Zakończona intencja o tym samym kluczu
    // jest ponownie uaktywniana, gdy resend = true (w przeciwnym razie DUPLICATE).
    Put queuePut(QueueRecord& record, bool resend);
    bool queueRead(uint32_t seq, QueueRecord& record);
    bool queueUpdate(const QueueRecord& record);  // zapis części zmiennej
    size_t queueLive() const;                      // intencje bez DONE/REPLACED/CANCELLED
    uint32_t queueOldestActiveS(bool& found) const;  // czas utworzenia najstarszej żywej intencji
    size_t queueSize() const { return QUEUE_SLOTS; }
    const QueueEntry* queueEntry(size_t slot) const { return queue_[slot].seq ? &queue_[slot] : nullptr; }
    const QueueEntry* queueFind(const uint8_t to[HASH], uint8_t type, const uint8_t id[HASH], uint16_t revision, uint32_t event) const;

    // Skrzynka: klucz (źródło, typ, id, revision, event); deduplikacja jak w kolejce.
    Put inboxPut(InboxRecord& record);
    bool inboxRead(uint32_t seq, InboxRecord& record);
    bool inboxMarkRead(uint32_t seq);
    size_t inboxCount() const;
    size_t inboxUnread() const;
    const InboxEntry* inboxEntry(size_t slot) const { return inbox_[slot].seq ? &inbox_[slot] : nullptr; }
    const InboxEntry* inboxFind(const uint8_t source[HASH], uint8_t type, const uint8_t id[HASH], uint16_t revision, uint32_t event) const;

    // Zdarzenia do laptopa: dopisanie, odczyt, potwierdzenie do kursora, pierwsze niepotwierdzone po kursorze.
    bool notePut(NoteRecord& record);
    bool noteRead(uint32_t seq, NoteRecord& record);
    bool noteAck(uint32_t seq);
    bool noteAckUpTo(uint32_t cursor);
    uint32_t noteLatest() const { return noteSeq_; }
    size_t notesPending() const;
    uint32_t notePendingAfter(uint32_t cursor) const;  // 0, gdy brak

    // Najwyższy event na id (również po usunięciu treści).
    bool seenGet(const uint8_t id[HASH], uint16_t revision, uint32_t& event, uint8_t& state);
    bool seenPut(const uint8_t id[HASH], uint16_t revision, uint32_t event, uint8_t state);

    bool close();    // ZAMKNIJ ZDARZENIE: usuwa kolejkę, skrzynkę i zdarzenia; klucze odbioru zostają
    bool destroy();  // ZNISZCZ DANE: usuwa wszystko łącznie z konfiguracją i pamięcią event

private:
    bool erase(uint32_t base, size_t count, size_t size);
    bool readRecord(uint32_t address, uint8_t* buffer, size_t immutable, size_t stateOffset, size_t stateSize, bool& stateValid);
    bool writeImmutable(uint32_t address, uint8_t* buffer, size_t immutable);
    bool writeState(uint32_t address, uint8_t* state, size_t stateSize);
    int freeSlot(const uint32_t* seqs, const uint8_t* live, size_t slots) const;

    journal::Storage& storage_;
    bool ok_ = false;
    Config config_;
    QueueEntry queue_[QUEUE_SLOTS];
    uint32_t queueSeq_ = 0;
    InboxEntry inbox_[INBOX_SLOTS];
    uint32_t inboxSeq_ = 0;
    NoteEntry notes_[NOTE_SLOTS];
    uint32_t noteSeq_ = 0;
    uint32_t seenSeq_ = 0;
};

// Pomocnicze: skrót szesnastkowy 32 znaków <-> 16 bajtów.
bool hexToBytes(const char* hex, uint8_t out[HASH]);
void bytesToHex(const uint8_t in[HASH], char out[2 * HASH + 1]);

}  // namespace store
