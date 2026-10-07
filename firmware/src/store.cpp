// SPDX-License-Identifier: MIT
#include "store.h"

#include <string.h>

#include "crc16.h"

namespace store {

namespace {

void putU16(uint8_t* out, uint16_t v) { out[0] = static_cast<uint8_t>(v); out[1] = static_cast<uint8_t>(v >> 8); }
void putU32(uint8_t* out, uint32_t v) { putU16(out, static_cast<uint16_t>(v)); putU16(out + 2, static_cast<uint16_t>(v >> 16)); }
uint16_t getU16(const uint8_t* in) { return static_cast<uint16_t>(in[0] | (in[1] << 8)); }
uint32_t getU32(const uint8_t* in) { return static_cast<uint32_t>(getU16(in)) | (static_cast<uint32_t>(getU16(in + 2)) << 16); }
bool seqUsable(uint32_t seq) { return seq != 0 && seq != 0xFFFFFFFF; }

// Układ rekordu 512 B kolejki i skrzynki (część stała): numer 4, czas 4, typ 1, revision 2, event 4,
// adres 16, id 16, długość 2, treść 256 = 305 B; CRC 2 i znacznik 1 -> 308 B.
constexpr size_t MSG_IMMUTABLE = 4 + 4 + 1 + 2 + 4 + HASH + HASH + 2 + sa1::MAX_CONTENT + 1;  // + bajt aux
constexpr size_t QUEUE_STATE = 1 + 2 + 4 + 4 + 1 + 4 + 4;  // flagi, próby, następna próba, event, stan, czas, pierwsze nadanie
constexpr size_t INBOX_STATE = 1;
constexpr size_t NOTE_IMMUTABLE = 4 + 4 + 1 + 4 + 2 + NOTE_TEXT;
constexpr size_t NOTE_STATE = 1;
constexpr size_t SEEN_IMMUTABLE = 4 + HASH + 2 + 4 + 1;
constexpr size_t CONFIG_IMMUTABLE = 4 + 1 + 1 + 2 + (ADDRESS_MAX + 1) + 2 * HASH + 1 + PHRASES * 3 * (PHRASE_MAX + 1) + HASH;
static_assert(MSG_IMMUTABLE + 3 <= STATE_OFFSET, "record layout");
static_assert(STATE_OFFSET + QUEUE_STATE + 3 <= RECORD, "record layout");
static_assert(NOTE_IMMUTABLE + 3 <= STATE_OFFSET, "note layout");
static_assert(SEEN_IMMUTABLE + 3 <= SEEN_RECORD, "seen layout");
static_assert(CONFIG_IMMUTABLE + 3 <= CONFIG_SLOT, "config layout");

void encodeMessageHeader(uint8_t* b, uint32_t seq, uint32_t timeS, uint8_t type, uint16_t revision, uint32_t event,
                         const uint8_t* address, const uint8_t* id, const char* sa1, uint16_t length, uint8_t aux = 0) {
    memset(b, 0, MSG_IMMUTABLE);
    putU32(b, seq);
    putU32(b + 4, timeS);
    b[8] = type;
    putU16(b + 9, revision);
    putU32(b + 11, event);
    memcpy(b + 15, address, HASH);
    memcpy(b + 31, id, HASH);
    putU16(b + 47, length);
    memcpy(b + 49, sa1, length);
    b[49 + sa1::MAX_CONTENT] = aux;
}

}  // namespace

const char* putName(Put result) {
    switch (result) {
        case Put::STORED: return "stored";
        case Put::DUPLICATE: return "duplicate";
        case Put::CONFLICT: return "conflict";
        case Put::FULL: return "full";
        case Put::ERROR: return "error";
    }
    return "?";
}

bool hexToBytes(const char* hex, uint8_t out[HASH]) {
    if (strlen(hex) != 2 * HASH) return false;
    for (size_t i = 0; i < HASH; ++i) {
        uint8_t v = 0;
        for (int k = 0; k < 2; ++k) {
            const char c = hex[2 * i + k];
            v = static_cast<uint8_t>(v << 4);
            if (c >= '0' && c <= '9') v |= static_cast<uint8_t>(c - '0');
            else if (c >= 'a' && c <= 'f') v |= static_cast<uint8_t>(c - 'a' + 10);
            else return false;
        }
        out[i] = v;
    }
    return true;
}

void bytesToHex(const uint8_t in[HASH], char out[2 * HASH + 1]) {
    static const char digits[] = "0123456789abcdef";
    for (size_t i = 0; i < HASH; ++i) {
        out[2 * i] = digits[in[i] >> 4];
        out[2 * i + 1] = digits[in[i] & 15];
    }
    out[2 * HASH] = '\0';
}

Store::Store(journal::Storage& storage) : storage_(storage) {}

bool Store::readRecord(uint32_t address, uint8_t* buffer, size_t immutable, size_t stateOffset, size_t stateSize, bool& stateValid) {
    // Zwraca true, gdy część stała jest poprawna i zatwierdzona; stateValid osobno.
    stateValid = false;
    const size_t span = stateSize ? stateOffset + stateSize + 3 : immutable + 3;
    if (!storage_.read(address, buffer, span)) return false;
    if (buffer[immutable + 2] != COMMITTED) return false;
    if (p1::crc16(buffer, immutable) != getU16(buffer + immutable)) return false;
    if (!seqUsable(getU32(buffer))) return false;
    if (stateSize) {
        const uint8_t* s = buffer + stateOffset;
        stateValid = s[stateSize + 2] == COMMITTED && p1::crc16(s, stateSize) == getU16(s + stateSize);
    }
    return true;
}

bool Store::writeImmutable(uint32_t address, uint8_t* buffer, size_t immutable) {
    putU16(buffer + immutable, p1::crc16(buffer, immutable));
    buffer[immutable + 2] = 0;
    if (!storage_.write(address, buffer, immutable + 3)) return false;
    const uint8_t committed = COMMITTED;
    return storage_.write(address + immutable + 2, &committed, 1);
}

bool Store::writeState(uint32_t address, uint8_t* state, size_t stateSize) {
    putU16(state + stateSize, p1::crc16(state, stateSize));
    state[stateSize + 2] = 0;
    if (!storage_.write(address, state, stateSize + 3)) return false;
    const uint8_t committed = COMMITTED;
    return storage_.write(address + stateSize + 2, &committed, 1);
}

bool Store::erase(uint32_t base, size_t count, size_t size) {
    uint8_t zeros[RECORD];
    memset(zeros, 0, sizeof(zeros));
    for (size_t i = 0; i < count; ++i) {
        for (size_t offset = 0; offset < size; offset += sizeof(zeros)) {
            const size_t chunk = size - offset < sizeof(zeros) ? size - offset : sizeof(zeros);
            if (!storage_.write(base + static_cast<uint32_t>(i * size + offset), zeros, chunk)) return false;
        }
    }
    return true;
}

bool Store::begin() {
    ok_ = false;
    uint8_t buffer[RECORD];
    bool stateValid = false;
    // Konfiguracja: nowszy z dwóch slotów.
    config_ = Config();
    for (uint32_t slot = 0; slot < CONFIG_SLOTS; ++slot) {
        uint8_t big[CONFIG_IMMUTABLE + 3];
        if (!storage_.read(CONFIG_BASE + slot * CONFIG_SLOT, big, sizeof(big))) return false;
        if (big[CONFIG_IMMUTABLE + 2] != COMMITTED || p1::crc16(big, CONFIG_IMMUTABLE) != getU16(big + CONFIG_IMMUTABLE)) continue;
        const uint32_t seq = getU32(big);
        if (!seqUsable(seq) || seq <= config_.seq) continue;
        Config c;
        const uint8_t* p = big;
        c.seq = seq; p += 4;
        c.role = *p++;
        c.activeOsp = *p++;
        c.stations = getU16(p); p += 2;
        memcpy(c.address, p, ADDRESS_MAX + 1); p += ADDRESS_MAX + 1;
        memcpy(c.osp, p, 2 * HASH); p += 2 * HASH;
        c.phraseCount = *p++;
        memcpy(c.phrases, p, sizeof(c.phrases)); p += sizeof(c.phrases);
        memcpy(c.ifac, p, HASH);
        c.address[ADDRESS_MAX] = '\0';
        if (c.phraseCount > PHRASES) c.phraseCount = PHRASES;
        config_ = c;
    }
    // Kolejka.
    queueSeq_ = 0;
    for (uint32_t slot = 0; slot < QUEUE_SLOTS; ++slot) {
        queue_[slot] = QueueEntry();
        if (!storage_.read(QUEUE_BASE + slot * RECORD, buffer, RECORD)) return false;
        if (buffer[MSG_IMMUTABLE + 2] != COMMITTED || p1::crc16(buffer, MSG_IMMUTABLE) != getU16(buffer + MSG_IMMUTABLE)) continue;
        const uint32_t seq = getU32(buffer);
        if (!seqUsable(seq)) continue;
        QueueEntry& e = queue_[slot];
        e.seq = seq;
        e.createdS = getU32(buffer + 4);
        e.type = buffer[8];
        e.aux = buffer[49 + sa1::MAX_CONTENT];
        e.revision = getU16(buffer + 9);
        e.event = getU32(buffer + 11);
        memcpy(e.to, buffer + 15, HASH);
        memcpy(e.id, buffer + 31, HASH);
        const uint8_t* s = buffer + STATE_OFFSET;
        if (s[QUEUE_STATE + 2] == COMMITTED && p1::crc16(s, QUEUE_STATE) == getU16(s + QUEUE_STATE)) {
            e.flags = s[0];
            e.attempts = getU16(s + 1);
            e.nextTryS = getU32(s + 3);
            e.state = s[11];
            e.updatedS = getU32(s + 12);
            e.sentS = getU32(s + 16);
        } else {
            e.flags = ACTIVE;  // stan nieczytelny: intencja aktywna od nowa
            e.nextTryS = 0;
        }
        if (seq > queueSeq_) queueSeq_ = seq;
    }
    // Skrzynka.
    inboxSeq_ = 0;
    for (uint32_t slot = 0; slot < INBOX_SLOTS; ++slot) {
        inbox_[slot] = InboxEntry();
        if (!readRecord(INBOX_BASE + slot * RECORD, buffer, MSG_IMMUTABLE, STATE_OFFSET, INBOX_STATE, stateValid)) continue;
        InboxEntry& e = inbox_[slot];
        e.seq = getU32(buffer);
        e.type = buffer[8];
        e.receivedS = getU32(buffer + 4);
        e.revision = getU16(buffer + 9);
        e.event = getU32(buffer + 11);
        memcpy(e.source, buffer + 15, HASH);
        memcpy(e.id, buffer + 31, HASH);
        e.flags = stateValid ? buffer[STATE_OFFSET] : 0;
        if (e.seq > inboxSeq_) inboxSeq_ = e.seq;
    }
    // Zdarzenia.
    noteSeq_ = 0;
    for (uint32_t slot = 0; slot < NOTE_SLOTS; ++slot) {
        notes_[slot] = NoteEntry();
        if (!readRecord(NOTE_BASE + slot * RECORD, buffer, NOTE_IMMUTABLE, STATE_OFFSET, NOTE_STATE, stateValid)) continue;
        notes_[slot].seq = getU32(buffer);
        notes_[slot].acked = stateValid && buffer[STATE_OFFSET] != 0;
        if (notes_[slot].seq > noteSeq_) noteSeq_ = notes_[slot].seq;
    }
    // Pamięć event: tylko najwyższy numer.
    seenSeq_ = 0;
    for (uint32_t slot = 0; slot < SEEN_SLOTS; ++slot) {
        if (!readRecord(SEEN_BASE + slot * SEEN_RECORD, buffer, SEEN_IMMUTABLE, 0, 0, stateValid)) continue;
        const uint32_t seq = getU32(buffer);
        if (seq > seenSeq_) seenSeq_ = seq;
    }
    ok_ = true;
    return true;
}

bool Store::writeConfig(const Config& config) {
    if (!ok_) return false;
    Config c = config;
    c.seq = config_.seq + 1;
    if (!seqUsable(c.seq)) c.seq = 1;
    uint8_t big[CONFIG_IMMUTABLE + 3];
    memset(big, 0, sizeof(big));
    uint8_t* p = big;
    putU32(p, c.seq); p += 4;
    *p++ = c.role;
    *p++ = c.activeOsp;
    putU16(p, c.stations); p += 2;
    memcpy(p, c.address, ADDRESS_MAX + 1); p += ADDRESS_MAX + 1;
    memcpy(p, c.osp, 2 * HASH); p += 2 * HASH;
    *p++ = c.phraseCount;
    memcpy(p, c.phrases, sizeof(c.phrases)); p += sizeof(c.phrases);
    memcpy(p, c.ifac, HASH);
    const uint32_t address = CONFIG_BASE + (c.seq % CONFIG_SLOTS) * CONFIG_SLOT;
    if (!writeImmutable(address, big, CONFIG_IMMUTABLE)) return false;
    config_ = c;
    return true;
}

int Store::freeSlot(const uint32_t* seqs, const uint8_t* live, size_t slots) const {
    // Wolny slot: pusty, a gdy brak, zakończony rekord z najmniejszym numerem.
    int best = -1;
    for (size_t i = 0; i < slots; ++i) {
        if (seqs[i] == 0) return static_cast<int>(i);
        if (!live[i] && (best < 0 || seqs[i] < seqs[best])) best = static_cast<int>(i);
    }
    return best;
}

const QueueEntry* Store::queueFind(const uint8_t to[HASH], uint8_t type, const uint8_t id[HASH], uint16_t revision, uint32_t event) const {
    for (const QueueEntry& e : queue_) {
        if (e.seq && e.type == type && e.revision == revision && e.event == event && !memcmp(e.to, to, HASH) && !memcmp(e.id, id, HASH)) return &e;
    }
    return nullptr;
}

bool Store::queueNumberTaken(uint16_t number, const uint8_t id[HASH]) const {
    for (const QueueEntry& e : queue_) {
        if (e.seq && (e.type == sa1::REQUEST || e.type == sa1::TEST) && memcmp(e.id, id, HASH) && shortNumber(e.id) == number) return true;
    }
    return false;
}

size_t Store::queueLive() const {
    size_t n = 0;
    for (const QueueEntry& e : queue_) n += (e.seq && !(e.flags & (DONE | REPLACED | CANCELLED))) ? 1 : 0;
    return n;
}

size_t Store::queueUnsent() const {
    size_t n = 0;
    for (const QueueEntry& e : queue_) n += (e.seq && (e.flags & ACTIVE) && !(e.flags & SENT)) ? 1 : 0;
    return n;
}

uint32_t Store::queueOldestUnsentS(bool& found) const {
    found = false;
    uint32_t oldest = 0;
    for (const QueueEntry& e : queue_) {
        if (!e.seq || !(e.flags & ACTIVE) || (e.flags & SENT)) continue;
        if (!found || e.createdS < oldest) oldest = e.createdS;
        found = true;
    }
    return oldest;
}

uint32_t Store::queueOldestActiveS(bool& found) const {
    found = false;
    uint32_t oldest = 0;
    for (const QueueEntry& e : queue_) {
        if (!e.seq || (e.flags & (DONE | REPLACED | CANCELLED))) continue;
        if (!found || e.createdS < oldest) oldest = e.createdS;
        found = true;
    }
    return oldest;
}

Put Store::queuePut(QueueRecord& record, bool resend) {
    if (!ok_ || record.sa1Length > sa1::MAX_CONTENT) return Put::ERROR;
    const QueueEntry* existing = queueFind(record.to, record.type, record.id, record.revision, record.event);
    if (existing) {
        QueueRecord old;
        if (!queueRead(existing->seq, old)) return Put::ERROR;
        if (old.sa1Length != record.sa1Length || memcmp(old.sa1, record.sa1, record.sa1Length)) return Put::CONFLICT;
        record = old;
        if (resend && (old.flags & (DONE | CANCELLED))) {
            record.flags = ACTIVE;
            record.attempts = 0;
            record.nextTryS = 0;
            if (!queueUpdate(record)) return Put::ERROR;
            return Put::STORED;
        }
        return Put::DUPLICATE;
    }
    uint32_t seqs[QUEUE_SLOTS];
    uint8_t live[QUEUE_SLOTS];
    for (size_t i = 0; i < QUEUE_SLOTS; ++i) {
        seqs[i] = queue_[i].seq;
        live[i] = queue_[i].seq && !(queue_[i].flags & (DONE | REPLACED | CANCELLED));
    }
    const int slot = freeSlot(seqs, live, QUEUE_SLOTS);
    if (slot < 0) return Put::FULL;
    uint32_t seq = queueSeq_ + 1;
    if (!seqUsable(seq)) seq = 1;
    uint8_t buffer[RECORD];
    memset(buffer, 0, sizeof(buffer));
    encodeMessageHeader(buffer, seq, record.createdS, record.type, record.revision, record.event, record.to, record.id,
                        record.sa1, record.sa1Length, record.aux);
    const uint32_t address = QUEUE_BASE + static_cast<uint32_t>(slot) * RECORD;
    // Najpierw stan (nowa intencja aktywna), potem część stała ze znacznikiem: rekord staje się ważny na końcu.
    record.seq = seq;
    record.flags = ACTIVE;
    record.attempts = 0;
    record.statusEvent = 0;
    record.state = 0;
    record.sentS = 0;
    uint8_t state[QUEUE_STATE + 3];
    memset(state, 0, sizeof(state));
    state[0] = record.flags;
    putU32(state + 3, record.nextTryS);  // zaplanowane nadanie (TEST startowy)
    putU32(state + 7, record.statusEvent);
    putU32(state + 12, record.updatedS);
    if (!writeState(address + STATE_OFFSET, state, QUEUE_STATE)) return Put::ERROR;
    if (!writeImmutable(address, buffer, MSG_IMMUTABLE)) return Put::ERROR;
    QueueRecord back;
    queue_[slot] = QueueEntry();
    queue_[slot].seq = seq;  // tymczasowo, aby queueRead znalazł slot
    if (!queueRead(seq, back) || back.sa1Length != record.sa1Length || memcmp(back.sa1, record.sa1, record.sa1Length)) {
        queue_[slot] = QueueEntry();
        return Put::ERROR;
    }
    QueueEntry& e = queue_[slot];
    e.createdS = record.createdS;
    e.type = record.type;
    e.aux = record.aux;
    e.flags = ACTIVE;
    e.revision = record.revision;
    e.event = record.event;
    e.nextTryS = record.nextTryS;
    e.updatedS = record.updatedS;
    memcpy(e.to, record.to, HASH);
    memcpy(e.id, record.id, HASH);
    queueSeq_ = seq;
    return Put::STORED;
}

bool Store::queueRead(uint32_t seq, QueueRecord& record) {
    for (size_t slot = 0; slot < QUEUE_SLOTS; ++slot) {
        if (queue_[slot].seq != seq) continue;
        uint8_t buffer[RECORD];
        bool stateValid = false;
        if (!readRecord(QUEUE_BASE + slot * RECORD, buffer, MSG_IMMUTABLE, STATE_OFFSET, QUEUE_STATE, stateValid)) return false;
        record = QueueRecord();
        record.seq = seq;
        record.createdS = getU32(buffer + 4);
        record.type = buffer[8];
        record.revision = getU16(buffer + 9);
        record.event = getU32(buffer + 11);
        memcpy(record.to, buffer + 15, HASH);
        memcpy(record.id, buffer + 31, HASH);
        record.sa1Length = getU16(buffer + 47);
        if (record.sa1Length > sa1::MAX_CONTENT) return false;
        memcpy(record.sa1, buffer + 49, record.sa1Length);
        record.sa1[record.sa1Length] = '\0';
        record.aux = buffer[49 + sa1::MAX_CONTENT];
        if (stateValid) {
            const uint8_t* s = buffer + STATE_OFFSET;
            record.flags = s[0];
            record.attempts = getU16(s + 1);
            record.nextTryS = getU32(s + 3);
            record.statusEvent = getU32(s + 7);
            record.state = s[11];
            record.updatedS = getU32(s + 12);
            record.sentS = getU32(s + 16);
        }
        return true;
    }
    return false;
}

bool Store::queueUpdate(const QueueRecord& record) {
    for (size_t slot = 0; slot < QUEUE_SLOTS; ++slot) {
        if (queue_[slot].seq != record.seq) continue;
        uint8_t state[QUEUE_STATE + 3];
        memset(state, 0, sizeof(state));
        state[0] = record.flags;
        putU16(state + 1, record.attempts);
        putU32(state + 3, record.nextTryS);
        putU32(state + 7, record.statusEvent);
        state[11] = record.state;
        putU32(state + 12, record.updatedS);
        putU32(state + 16, record.sentS);
        if (!writeState(QUEUE_BASE + slot * RECORD + STATE_OFFSET, state, QUEUE_STATE)) return false;
        QueueEntry& e = queue_[slot];
        e.flags = record.flags;
        e.attempts = record.attempts;
        e.nextTryS = record.nextTryS;
        e.state = record.state;
        e.updatedS = record.updatedS;
        e.sentS = record.sentS;
        return true;
    }
    return false;
}

const InboxEntry* Store::inboxFind(const uint8_t source[HASH], uint8_t type, const uint8_t id[HASH], uint16_t revision, uint32_t event) const {
    for (const InboxEntry& e : inbox_) {
        if (e.seq && e.type == type && e.revision == revision && e.event == event && !memcmp(e.source, source, HASH) && !memcmp(e.id, id, HASH)) return &e;
    }
    return nullptr;
}

size_t Store::inboxCount() const {
    size_t n = 0;
    for (const InboxEntry& e : inbox_) n += e.seq ? 1 : 0;
    return n;
}

size_t Store::inboxUnread() const {
    size_t n = 0;
    for (const InboxEntry& e : inbox_) n += (e.seq && !(e.flags & 1)) ? 1 : 0;
    return n;
}

Put Store::inboxPut(InboxRecord& record) {
    if (!ok_ || record.sa1Length > sa1::MAX_CONTENT) return Put::ERROR;
    const InboxEntry* existing = inboxFind(record.source, record.type, record.id, record.revision, record.event);
    if (existing) {
        InboxRecord old;
        if (!inboxRead(existing->seq, old)) return Put::ERROR;
        if (old.sa1Length != record.sa1Length || memcmp(old.sa1, record.sa1, record.sa1Length)) return Put::CONFLICT;
        record = old;
        return Put::DUPLICATE;
    }
    // Pełna skrzynka: odpada najstarsza przeczytana (najpierw BULLETIN), potem najstarsza w ogóle.
    uint32_t seqs[INBOX_SLOTS];
    uint8_t live[INBOX_SLOTS];
    for (size_t i = 0; i < INBOX_SLOTS; ++i) { seqs[i] = inbox_[i].seq; live[i] = 1; }
    int slot = freeSlot(seqs, live, INBOX_SLOTS);
    if (slot < 0) {
        for (int pass = 0; pass < 3 && slot < 0; ++pass) {
            for (size_t i = 0; i < INBOX_SLOTS; ++i) {
                const InboxEntry& e = inbox_[i];
                const bool candidate = pass == 0 ? ((e.flags & 1) && e.type == sa1::BULLETIN) : pass == 1 ? (e.flags & 1) != 0 : true;
                if (candidate && (slot < 0 || e.seq < inbox_[slot].seq)) slot = static_cast<int>(i);
            }
        }
    }
    uint32_t seq = inboxSeq_ + 1;
    if (!seqUsable(seq)) seq = 1;
    uint8_t buffer[RECORD];
    memset(buffer, 0, sizeof(buffer));
    encodeMessageHeader(buffer, seq, record.receivedS, record.type, record.revision, record.event, record.source, record.id,
                        record.sa1, record.sa1Length);
    const uint32_t address = INBOX_BASE + static_cast<uint32_t>(slot) * RECORD;
    uint8_t state[INBOX_STATE + 3] = {};
    if (!writeState(address + STATE_OFFSET, state, INBOX_STATE)) return Put::ERROR;
    if (!writeImmutable(address, buffer, MSG_IMMUTABLE)) return Put::ERROR;
    InboxEntry& e = inbox_[slot];
    e = InboxEntry();
    e.seq = seq;
    e.receivedS = record.receivedS;
    e.type = record.type;
    e.revision = record.revision;
    e.event = record.event;
    memcpy(e.source, record.source, HASH);
    memcpy(e.id, record.id, HASH);
    record.seq = seq;
    record.flags = 0;
    inboxSeq_ = seq;
    return Put::STORED;
}

bool Store::inboxRead(uint32_t seq, InboxRecord& record) {
    for (size_t slot = 0; slot < INBOX_SLOTS; ++slot) {
        if (inbox_[slot].seq != seq) continue;
        uint8_t buffer[RECORD];
        bool stateValid = false;
        if (!readRecord(INBOX_BASE + slot * RECORD, buffer, MSG_IMMUTABLE, STATE_OFFSET, INBOX_STATE, stateValid)) return false;
        record = InboxRecord();
        record.seq = seq;
        record.receivedS = getU32(buffer + 4);
        record.type = buffer[8];
        record.revision = getU16(buffer + 9);
        record.event = getU32(buffer + 11);
        memcpy(record.source, buffer + 15, HASH);
        memcpy(record.id, buffer + 31, HASH);
        record.sa1Length = getU16(buffer + 47);
        if (record.sa1Length > sa1::MAX_CONTENT) return false;
        memcpy(record.sa1, buffer + 49, record.sa1Length);
        record.sa1[record.sa1Length] = '\0';
        record.flags = stateValid ? buffer[STATE_OFFSET] : 0;
        return true;
    }
    return false;
}

bool Store::inboxMarkRead(uint32_t seq) {
    for (size_t slot = 0; slot < INBOX_SLOTS; ++slot) {
        if (inbox_[slot].seq != seq) continue;
        uint8_t state[INBOX_STATE + 3] = {1};
        if (!writeState(INBOX_BASE + slot * RECORD + STATE_OFFSET, state, INBOX_STATE)) return false;
        inbox_[slot].flags |= 1;
        return true;
    }
    return false;
}

bool Store::notePut(NoteRecord& record) {
    if (!ok_) return false;
    const size_t length = strlen(record.text);
    if (length > NOTE_TEXT) return false;
    uint32_t seqs[NOTE_SLOTS];
    uint8_t live[NOTE_SLOTS];
    for (size_t i = 0; i < NOTE_SLOTS; ++i) { seqs[i] = notes_[i].seq; live[i] = notes_[i].seq && !notes_[i].acked; }
    int slot = freeSlot(seqs, live, NOTE_SLOTS);
    if (slot < 0) {
        // Wszystkie niepotwierdzone: odpada najstarsze (laptop odtworzy stan z kursora i skrzynki).
        for (size_t i = 0; i < NOTE_SLOTS; ++i) if (slot < 0 || notes_[i].seq < notes_[slot].seq) slot = static_cast<int>(i);
    }
    uint32_t seq = noteSeq_ + 1;
    if (!seqUsable(seq)) seq = 1;
    uint8_t buffer[RECORD];
    memset(buffer, 0, sizeof(buffer));
    putU32(buffer, seq);
    putU32(buffer + 4, record.createdS);
    buffer[8] = record.kind;
    putU32(buffer + 9, record.ref);
    putU16(buffer + 13, static_cast<uint16_t>(length));
    memcpy(buffer + 15, record.text, length);
    const uint32_t address = NOTE_BASE + static_cast<uint32_t>(slot) * RECORD;
    uint8_t state[NOTE_STATE + 3] = {};
    if (!writeState(address + STATE_OFFSET, state, NOTE_STATE)) return false;
    if (!writeImmutable(address, buffer, NOTE_IMMUTABLE)) return false;
    notes_[slot].seq = seq;
    notes_[slot].acked = false;
    record.seq = seq;
    record.acked = false;
    noteSeq_ = seq;
    return true;
}

bool Store::noteRead(uint32_t seq, NoteRecord& record) {
    for (size_t slot = 0; slot < NOTE_SLOTS; ++slot) {
        if (notes_[slot].seq != seq) continue;
        uint8_t buffer[RECORD];
        bool stateValid = false;
        if (!readRecord(NOTE_BASE + slot * RECORD, buffer, NOTE_IMMUTABLE, STATE_OFFSET, NOTE_STATE, stateValid)) return false;
        record = NoteRecord();
        record.seq = seq;
        record.createdS = getU32(buffer + 4);
        record.kind = buffer[8];
        record.ref = getU32(buffer + 9);
        const uint16_t length = getU16(buffer + 13);
        if (length > NOTE_TEXT) return false;
        memcpy(record.text, buffer + 15, length);
        record.text[length] = '\0';
        record.acked = stateValid && buffer[STATE_OFFSET] != 0;
        return true;
    }
    return false;
}

bool Store::noteAck(uint32_t seq) {
    for (size_t slot = 0; slot < NOTE_SLOTS; ++slot) {
        if (notes_[slot].seq != seq) continue;
        if (notes_[slot].acked) return true;
        uint8_t state[NOTE_STATE + 3] = {1};
        if (!writeState(NOTE_BASE + slot * RECORD + STATE_OFFSET, state, NOTE_STATE)) return false;
        notes_[slot].acked = true;
        return true;
    }
    return false;
}

bool Store::noteAckUpTo(uint32_t cursor) {
    for (size_t slot = 0; slot < NOTE_SLOTS; ++slot) {
        if (notes_[slot].seq && notes_[slot].seq <= cursor && !notes_[slot].acked && !noteAck(notes_[slot].seq)) return false;
    }
    return true;
}

size_t Store::notesPending() const {
    size_t n = 0;
    for (const NoteEntry& e : notes_) n += (e.seq && !e.acked) ? 1 : 0;
    return n;
}

uint32_t Store::notePendingAfter(uint32_t cursor) const {
    uint32_t best = 0;
    for (const NoteEntry& e : notes_) {
        if (e.seq > cursor && !e.acked && (best == 0 || e.seq < best)) best = e.seq;
    }
    return best;
}

bool Store::seenGet(const uint8_t id[HASH], uint16_t revision, uint32_t& event, uint8_t& state) {
    uint8_t buffer[SEEN_RECORD];
    bool stateValid = false;
    uint32_t bestSeq = 0;
    for (uint32_t slot = 0; slot < SEEN_SLOTS; ++slot) {
        if (!readRecord(SEEN_BASE + slot * SEEN_RECORD, buffer, SEEN_IMMUTABLE, 0, 0, stateValid)) continue;
        if (memcmp(buffer + 4, id, HASH) || getU16(buffer + 20) != revision) continue;
        const uint32_t seq = getU32(buffer);
        if (seq > bestSeq) {
            bestSeq = seq;
            event = getU32(buffer + 22);
            state = buffer[26];
        }
    }
    return bestSeq != 0;
}

bool Store::seenPut(const uint8_t id[HASH], uint16_t revision, uint32_t event, uint8_t state) {
    if (!ok_) return false;
    uint32_t seq = seenSeq_ + 1;
    if (!seqUsable(seq)) seq = 1;
    uint8_t buffer[SEEN_RECORD];
    memset(buffer, 0, sizeof(buffer));
    putU32(buffer, seq);
    memcpy(buffer + 4, id, HASH);
    putU16(buffer + 20, revision);
    putU32(buffer + 22, event);
    buffer[26] = state;
    if (!writeImmutable(SEEN_BASE + (seq % SEEN_SLOTS) * SEEN_RECORD, buffer, SEEN_IMMUTABLE)) return false;
    seenSeq_ = seq;
    return true;
}

bool Store::close() {
    if (!ok_) return false;
    // Najwyższy event każdej intencji do pamięci kluczy, potem usunięcie treści.
    for (const QueueEntry& e : queue_) {
        if (!e.seq) continue;
        QueueRecord r;
        if (queueRead(e.seq, r) && r.statusEvent && !seenPut(r.id, r.revision, r.statusEvent, r.state)) return false;
    }
    if (!erase(QUEUE_BASE, QUEUE_SLOTS, RECORD) || !erase(INBOX_BASE, INBOX_SLOTS, RECORD) || !erase(NOTE_BASE, NOTE_SLOTS, RECORD)) return false;
    for (QueueEntry& e : queue_) e = QueueEntry();
    for (InboxEntry& e : inbox_) e = InboxEntry();
    for (NoteEntry& e : notes_) e = NoteEntry();
    queueSeq_ = inboxSeq_ = noteSeq_ = 0;
    return true;
}

bool Store::destroy() {
    if (!ok_) return false;
    if (!erase(CONFIG_BASE, CONFIG_SLOTS, CONFIG_SLOT) || !erase(QUEUE_BASE, QUEUE_SLOTS, RECORD) || !erase(INBOX_BASE, INBOX_SLOTS, RECORD) ||
        !erase(NOTE_BASE, NOTE_SLOTS, RECORD) || !erase(SEEN_BASE, SEEN_SLOTS, SEEN_RECORD)) return false;
    return begin();
}

uint16_t shortNumber(const uint8_t id[HASH]) {
    return static_cast<uint16_t>(((static_cast<uint16_t>(id[0]) << 8) | id[1]) % 10000);
}

}  // namespace store
