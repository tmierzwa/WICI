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

// Jedna kopia pętli CRC: rdzeń kompiluje z -Ofast, który rozwijałby funkcję z crc16.h w każdym miejscu.
__attribute__((noinline)) uint16_t crc16(const uint8_t* data, size_t length, uint16_t crc = 0xFFFF) {
    return p1::crc16(data, length, crc);
}

// Układ rekordu 512 B kolejki i skrzynki (część stała): numer 4, czas 4, typ 1, revision 2, event 4,
// adres 16, id 16, długość 2, treść 256, aux 1, kategoria 1 = 307 B; CRC 2 i znacznik 1 -> 310 B.
constexpr size_t MSG_IMMUTABLE = 4 + 4 + 1 + 2 + 4 + HASH + HASH + 2 + sa1::MAX_CONTENT + 2;
// Część zmienna intencji: flagi, próby, następna próba, event, stan, czas, pierwsze nadanie, pokolenie.
// Dwie kopie na zmianę (QUEUE_STATE_B): zanik zasilania w trakcie zapisu zostawia poprzednią.
constexpr size_t QUEUE_STATE = 1 + 2 + 4 + 4 + 1 + 4 + 4 + 1;
constexpr size_t QUEUE_STATE_B = STATE_OFFSET + QUEUE_STATE + 3;
constexpr size_t INBOX_STATE = 1;
constexpr size_t NOTE_IMMUTABLE = 4 + 4 + 1 + 4 + 2 + NOTE_TEXT;
constexpr size_t NOTE_STATE = 1;
constexpr size_t SEEN_IMMUTABLE = 4 + HASH + 2 + 4 + 1;
constexpr size_t CONFIG_IMMUTABLE = 4 + 1 + 1 + 2 + (ADDRESS_MAX + 1) + 2 * HASH + 1 + PHRASES * 3 * (PHRASE_MAX + 1) + HASH +
                                    1 + (ADDRESSES - 1) * (ADDRESS_MAX + 1);
constexpr size_t COUNTERS = 4 + 3 * 4;  // numer zapisu, najwyższe numery kolejki, skrzynki i zdarzeń
static_assert(MSG_IMMUTABLE + 3 <= STATE_OFFSET, "record layout");
static_assert(QUEUE_STATE_B + QUEUE_STATE + 3 <= RECORD, "record layout");
static_assert(NOTE_IMMUTABLE + 3 <= STATE_OFFSET, "note layout");
static_assert(SEEN_IMMUTABLE + 3 <= SEEN_RECORD, "seen layout");
static_assert(CONFIG_IMMUTABLE + 3 <= CONFIG_SLOT, "config layout");

void encodeMessageHeader(uint8_t* b, uint32_t seq, uint32_t timeS, uint8_t type, uint16_t revision, uint32_t event,
                         const uint8_t* address, const uint8_t* id, const char* sa1, uint16_t length, uint8_t aux = 0,
                         uint8_t category = 0) {
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
    b[50 + sa1::MAX_CONTENT] = category;
}

// CRC części zmiennej zaczyna się od numeru rekordu: stan nie pasuje do części stałej innego
// rekordu, który wcześniej zajmował ten slot.
uint16_t stateCrc(uint32_t seq, const uint8_t* state, size_t size) {
    uint8_t b[4];
    putU32(b, seq);
    return crc16(state, size, crc16(b, sizeof(b)));
}

bool stateValid(uint32_t seq, const uint8_t* state, size_t size) {
    return state[size + 2] == COMMITTED && stateCrc(seq, state, size) == getU16(state + size);
}

// Nowsza z dwóch poprawnych kopii stanu intencji (pokolenie w ostatnim bajcie, porównanie modulo 256).
const uint8_t* queueState(uint32_t seq, const uint8_t* record) {
    const uint8_t* a = record + STATE_OFFSET;
    const uint8_t* b = record + QUEUE_STATE_B;
    const bool va = stateValid(seq, a, QUEUE_STATE);
    const bool vb = stateValid(seq, b, QUEUE_STATE);
    if (va && vb) return static_cast<uint8_t>(b[QUEUE_STATE - 1] - a[QUEUE_STATE - 1]) < 128 ? b : a;
    return va ? a : vb ? b : nullptr;
}

void decodeQueueState(const uint8_t* s, QueueRecord& r) {
    r.flags = s[0];
    r.attempts = getU16(s + 1);
    r.nextTryS = getU32(s + 3);
    r.statusEvent = getU32(s + 7);
    r.state = s[11];
    r.updatedS = getU32(s + 12);
    r.sentS = getU32(s + 16);
}

// Część stała wiadomości kolejki albo skrzynki; adres to odbiorca (kolejka) albo źródło (skrzynka).
bool decodeMessageHeader(const uint8_t* b, uint32_t& timeS, uint8_t& type, uint16_t& revision, uint32_t& event, uint8_t* address,
                         uint8_t* id, char* sa1, uint16_t& length) {
    timeS = getU32(b + 4);
    type = b[8];
    revision = getU16(b + 9);
    event = getU32(b + 11);
    memcpy(address, b + 15, HASH);
    memcpy(id, b + 31, HASH);
    length = getU16(b + 47);
    if (length > sa1::MAX_CONTENT) return false;
    memcpy(sa1, b + 49, length);
    sa1[length] = '\0';
    return true;
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

bool Store::readRecord(uint32_t address, uint8_t* buffer, size_t immutable, size_t span) {
    // Czyta span bajtów; true, gdy część stała jest poprawna i zatwierdzona (stan sprawdza wołający).
    if (!storage_.read(address, buffer, span)) return false;
    if (buffer[immutable + 2] != COMMITTED) return false;
    if (crc16(buffer, immutable) != getU16(buffer + immutable)) return false;
    return seqUsable(getU32(buffer));
}

bool Store::writeImmutable(uint32_t address, uint8_t* buffer, size_t immutable) {
    putU16(buffer + immutable, crc16(buffer, immutable));
    buffer[immutable + 2] = 0;
    if (!storage_.write(address, buffer, immutable + 3)) return false;
    const uint8_t committed = COMMITTED;
    return storage_.write(address + immutable + 2, &committed, 1);
}

bool Store::invalidate(uint32_t address, size_t immutable) {
    // Ponowne użycie slotu: stary rekord traci znacznik, zanim powstanie nowy (zanik zasilania
    // między zapisem stanu a zapisem części stałej nie ożywi starego rekordu z nowym stanem).
    const uint8_t zero = 0;
    return storage_.write(address + immutable + 2, &zero, 1);
}

bool Store::writeState(uint32_t address, uint32_t seq, uint8_t* state, size_t stateSize) {
    putU16(state + stateSize, stateCrc(seq, state, stateSize));
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
    // Konfiguracja: nowszy z dwóch slotów. CRC liczone kawałkami i pola czytane wprost do config_,
    // bez kopii rekordu 3,3 KB na stosie.
    config_ = Config();
    selected_ = 0;
    uint32_t bestSeq = 0;
    uint32_t bestSlot = 0;
    for (uint32_t slot = 0; slot < CONFIG_SLOTS; ++slot) {
        const uint32_t base = CONFIG_BASE + slot * CONFIG_SLOT;
        uint8_t tail[3];
        if (!storage_.read(base + CONFIG_IMMUTABLE, tail, sizeof(tail))) return false;
        if (tail[2] != COMMITTED) continue;
        uint16_t crc = 0xFFFF;
        uint32_t seq = 0;
        for (size_t offset = 0; offset < CONFIG_IMMUTABLE; offset += sizeof(buffer)) {
            const size_t chunk = CONFIG_IMMUTABLE - offset < sizeof(buffer) ? CONFIG_IMMUTABLE - offset : sizeof(buffer);
            if (!storage_.read(base + static_cast<uint32_t>(offset), buffer, chunk)) return false;
            if (!offset) seq = getU32(buffer);
            crc = crc16(buffer, chunk, crc);
        }
        if (crc != getU16(tail) || !seqUsable(seq) || seq <= bestSeq) continue;
        bestSeq = seq;
        bestSlot = slot;
    }
    if (bestSeq) {
        uint32_t at = CONFIG_BASE + bestSlot * CONFIG_SLOT;
        uint8_t head[8];
        const bool read = storage_.read(at, head, sizeof(head)) && storage_.read(at += sizeof(head), reinterpret_cast<uint8_t*>(config_.address), ADDRESS_MAX + 1) &&
                          storage_.read(at += ADDRESS_MAX + 1, &config_.osp[0][0], 2 * HASH) && storage_.read(at += 2 * HASH, &config_.phraseCount, 1) &&
                          storage_.read(at += 1, reinterpret_cast<uint8_t*>(config_.phrases), sizeof(config_.phrases)) &&
                          storage_.read(at += sizeof(config_.phrases), config_.ifac, HASH) &&
                          storage_.read(at += HASH, &config_.objectCount, 1) &&
                          storage_.read(at += 1, reinterpret_cast<uint8_t*>(config_.objects), sizeof(config_.objects));
        if (!read) return false;
        config_.seq = bestSeq;
        config_.role = head[4];
        config_.activeOsp = head[5];
        config_.stations = getU16(head + 6);
        config_.address[ADDRESS_MAX] = '\0';
        if (config_.phraseCount > PHRASES) config_.phraseCount = PHRASES;
        if (config_.objectCount > ADDRESSES - 1) config_.objectCount = ADDRESSES - 1;
        for (auto& object : config_.objects) object[ADDRESS_MAX] = '\0';
        for (auto& phrase : config_.phrases) for (auto& text : phrase) text[PHRASE_MAX] = '\0';
    }
    // Najwyższe numery sprzed ostatniego ZAMKNIJ ZDARZENIE: numeracja rośnie dalej, a kursor
    // laptopa i numery rekordów nie wskazują nowych rekordów.
    queueSeq_ = inboxSeq_ = noteSeq_ = 0;
    countersSeq_ = 0;
    for (uint32_t slot = 0; slot < 2; ++slot) {
        if (!readRecord(COUNTERS_BASE + slot * 32, buffer, COUNTERS, COUNTERS + 3)) continue;
        const uint32_t seq = getU32(buffer);
        if (seq <= countersSeq_) continue;
        countersSeq_ = seq;
        queueSeq_ = getU32(buffer + 4);
        inboxSeq_ = getU32(buffer + 8);
        noteSeq_ = getU32(buffer + 12);
    }
    // Kolejka.
    for (uint32_t slot = 0; slot < QUEUE_SLOTS; ++slot) {
        queue_[slot] = QueueEntry();
        if (!storage_.read(QUEUE_BASE + slot * RECORD, buffer, RECORD)) return false;
        if (buffer[MSG_IMMUTABLE + 2] != COMMITTED || crc16(buffer, MSG_IMMUTABLE) != getU16(buffer + MSG_IMMUTABLE)) continue;
        const uint32_t seq = getU32(buffer);
        if (!seqUsable(seq)) continue;
        QueueEntry& e = queue_[slot];
        e.seq = seq;
        fillQueueEntry(e, buffer);
        if (seq > queueSeq_) queueSeq_ = seq;
    }
    // Skrzynka.
    for (uint32_t slot = 0; slot < INBOX_SLOTS; ++slot) {
        inbox_[slot] = InboxEntry();
        if (!readRecord(INBOX_BASE + slot * RECORD, buffer, MSG_IMMUTABLE, STATE_OFFSET + INBOX_STATE + 3)) continue;
        InboxEntry& e = inbox_[slot];
        e.seq = getU32(buffer);
        e.type = buffer[8];
        e.receivedS = getU32(buffer + 4);
        e.revision = getU16(buffer + 9);
        e.event = getU32(buffer + 11);
        memcpy(e.source, buffer + 15, HASH);
        memcpy(e.id, buffer + 31, HASH);
        e.flags = stateValid(e.seq, buffer + STATE_OFFSET, INBOX_STATE) ? buffer[STATE_OFFSET] : 0;
        if (e.seq > inboxSeq_) inboxSeq_ = e.seq;
    }
    // Zdarzenia.
    for (uint32_t slot = 0; slot < NOTE_SLOTS; ++slot) {
        notes_[slot] = NoteEntry();
        if (!readRecord(NOTE_BASE + slot * RECORD, buffer, NOTE_IMMUTABLE, STATE_OFFSET + NOTE_STATE + 3)) continue;
        notes_[slot].seq = getU32(buffer);
        notes_[slot].acked = stateValid(notes_[slot].seq, buffer + STATE_OFFSET, NOTE_STATE) && buffer[STATE_OFFSET] != 0;
        if (notes_[slot].seq > noteSeq_) noteSeq_ = notes_[slot].seq;
    }
    // Pamięć event: tylko najwyższy numer.
    seenSeq_ = 0;
    for (uint32_t slot = 0; slot < SEEN_SLOTS; ++slot) {
        if (!readRecord(SEEN_BASE + slot * SEEN_RECORD, buffer, SEEN_IMMUTABLE, SEEN_IMMUTABLE + 3)) continue;
        const uint32_t seq = getU32(buffer);
        if (seq > seenSeq_) seenSeq_ = seq;
    }
    ok_ = true;
    return true;
}

void Store::fillQueueEntry(QueueEntry& e, const uint8_t* buffer) {
    // Indeks w RAM z rekordu przeczytanego w całości (część stała już sprawdzona).
    e.createdS = getU32(buffer + 4);
    e.type = buffer[8];
    e.revision = getU16(buffer + 9);
    e.event = getU32(buffer + 11);
    memcpy(e.to, buffer + 15, HASH);
    memcpy(e.id, buffer + 31, HASH);
    e.aux = buffer[49 + sa1::MAX_CONTENT];
    e.category = buffer[50 + sa1::MAX_CONTENT];
    QueueRecord r;
    if (const uint8_t* s = queueState(e.seq, buffer)) {
        decodeQueueState(s, r);
        e.stateGen = s[QUEUE_STATE - 1];
    } else {
        r.flags = ACTIVE;  // obie kopie stanu nieczytelne (nie powinno się zdarzyć): intencja aktywna od nowa
        e.stateGen = 0;
    }
    e.flags = r.flags;
    e.attempts = r.attempts;
    e.nextTryS = r.nextTryS;
    e.state = r.state;
    e.updatedS = r.updatedS;
    e.sentS = r.sentS;
}

bool Store::writeCounters() {
    // Dwa sloty po 32 B na zmianę, jak rekordy dziennika: stary slot traci znacznik dopiero przy zapisie.
    uint32_t seq = countersSeq_ + 1;
    if (!seqUsable(seq)) seq = 1;
    uint8_t buffer[COUNTERS + 3];
    putU32(buffer, seq);
    putU32(buffer + 4, queueSeq_);
    putU32(buffer + 8, inboxSeq_);
    putU32(buffer + 12, noteSeq_);
    const uint32_t address = COUNTERS_BASE + (seq % 2) * 32;
    if (!invalidate(address, COUNTERS) || !writeImmutable(address, buffer, COUNTERS)) return false;
    countersSeq_ = seq;
    return true;
}

const char* Store::addressAt(size_t index) const {
    if (index >= addressCount()) return "";
    return index ? config_.objects[index - 1] : config_.address;
}

bool Store::writeConfig(const Config& config) {
    if (!ok_) return false;
    uint32_t seq = config_.seq + 1;
    if (!seqUsable(seq)) seq = 1;
    // Rekord konfiguracji (3,3 KB) idzie do FRAM kawałkami z narastającym CRC, bez kopii na stosie.
    uint8_t head[8];
    putU32(head, seq);
    head[4] = config.role;
    head[5] = config.activeOsp;
    putU16(head + 6, config.stations);
    const uint8_t count = config.phraseCount;
    const uint8_t objects = config.objectCount;
    struct Piece { const uint8_t* data; size_t length; };
    const Piece pieces[] = {
        {head, sizeof(head)},
        {reinterpret_cast<const uint8_t*>(config.address), ADDRESS_MAX + 1},
        {&config.osp[0][0], 2 * HASH},
        {&count, 1},
        {reinterpret_cast<const uint8_t*>(config.phrases), sizeof(config.phrases)},
        {config.ifac, HASH},
        {&objects, 1},
        {reinterpret_cast<const uint8_t*>(config.objects), sizeof(config.objects)},
    };
    const uint32_t address = CONFIG_BASE + (seq % CONFIG_SLOTS) * CONFIG_SLOT;
    if (!invalidate(address, CONFIG_IMMUTABLE)) return false;
    uint16_t crc = 0xFFFF;
    uint32_t offset = 0;
    for (const Piece& piece : pieces) {
        if (!storage_.write(address + offset, piece.data, piece.length)) return false;
        crc = crc16(piece.data, piece.length, crc);
        offset += static_cast<uint32_t>(piece.length);
    }
    uint8_t tail[3];
    putU16(tail, crc);
    tail[2] = 0;
    if (!storage_.write(address + offset, tail, sizeof(tail))) return false;
    const uint8_t committed = COMMITTED;
    if (!storage_.write(address + offset + 2, &committed, 1)) return false;
    config_ = config;
    config_.seq = seq;
    if (selected_ >= addressCount()) selected_ = 0;
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
                        record.sa1, record.sa1Length, record.aux, record.category);
    const uint32_t address = QUEUE_BASE + static_cast<uint32_t>(slot) * RECORD;
    // Stary rekord traci znacznik, potem stan (nowa intencja aktywna), potem część stała ze znacznikiem:
    // rekord staje się ważny na końcu.
    if (seqs[slot] && !invalidate(address, MSG_IMMUTABLE)) return Put::ERROR;
    record.seq = seq;
    record.flags = ACTIVE;
    record.attempts = 0;
    record.statusEvent = 0;
    record.state = 0;
    record.sentS = 0;
    // Pierwsza kopia stanu, pokolenie 0 (nextTryS: zaplanowane nadanie TEST startowego); druga kopia
    // starego rekordu nie przejdzie CRC z nowym numerem.
    uint8_t* state = buffer + STATE_OFFSET;
    encodeQueueState(state, record, 0);
    if (!writeState(address + STATE_OFFSET, seq, state, QUEUE_STATE)) return Put::ERROR;
    if (!writeImmutable(address, buffer, MSG_IMMUTABLE)) return Put::ERROR;
    queueSeq_ = seq;  // numer zużyty także przy błędzie odczytu kontrolnego
    // Odczyt kontrolny całego rekordu; przy niezgodności rekord traci znacznik, a slot zostaje pusty.
    uint8_t back[RECORD];
    queue_[slot] = QueueEntry();
    if (!readRecord(address, back, MSG_IMMUTABLE, RECORD) || memcmp(back, buffer, MSG_IMMUTABLE) || queueState(seq, back) != back + STATE_OFFSET) {
        invalidate(address, MSG_IMMUTABLE);
        return Put::ERROR;
    }
    queue_[slot].seq = seq;
    fillQueueEntry(queue_[slot], back);
    return Put::STORED;
}

bool Store::queueRead(uint32_t seq, QueueRecord& record) {
    for (size_t slot = 0; slot < QUEUE_SLOTS; ++slot) {
        if (queue_[slot].seq != seq) continue;
        uint8_t buffer[RECORD];
        if (!readRecord(QUEUE_BASE + slot * RECORD, buffer, MSG_IMMUTABLE, RECORD)) return false;
        record = QueueRecord();
        record.seq = seq;
        if (!decodeMessageHeader(buffer, record.createdS, record.type, record.revision, record.event, record.to, record.id, record.sa1,
                                 record.sa1Length)) return false;
        record.aux = buffer[49 + sa1::MAX_CONTENT];
        record.category = buffer[50 + sa1::MAX_CONTENT];
        if (const uint8_t* s = queueState(seq, buffer)) decodeQueueState(s, record);
        return true;
    }
    return false;
}

bool Store::queueUpdate(const QueueRecord& record) {
    for (size_t slot = 0; slot < QUEUE_SLOTS; ++slot) {
        if (queue_[slot].seq != record.seq) continue;
        // Nowe pokolenie do kopii, która nie jest bieżąca: bieżąca zostaje do zatwierdzenia nowej.
        QueueEntry& e = queue_[slot];
        const uint8_t gen = static_cast<uint8_t>(e.stateGen + 1);
        uint8_t state[QUEUE_STATE + 3];
        encodeQueueState(state, record, gen);
        const uint32_t address = QUEUE_BASE + slot * RECORD + ((gen & 1) ? QUEUE_STATE_B : STATE_OFFSET);
        if (!writeState(address, record.seq, state, QUEUE_STATE)) return false;
        e.stateGen = gen;
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

void Store::encodeQueueState(uint8_t* s, const QueueRecord& record, uint8_t gen) {
    memset(s, 0, QUEUE_STATE + 3);
    s[0] = record.flags;
    putU16(s + 1, record.attempts);
    putU32(s + 3, record.nextTryS);
    putU32(s + 7, record.statusEvent);
    s[11] = record.state;
    putU32(s + 12, record.updatedS);
    putU32(s + 16, record.sentS);
    s[QUEUE_STATE - 1] = gen;
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
    for (const InboxEntry& e : inbox_) n += (e.seq && !(e.flags & INBOX_READ)) ? 1 : 0;
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
    // Pełna skrzynka: odpada najstarsza przeczytana (najpierw BULLETIN), potem najstarsza bez
    // zaległego zdarzenia do laptopa, na końcu najstarsza w ogóle.
    uint32_t seqs[INBOX_SLOTS];
    uint8_t live[INBOX_SLOTS];
    for (size_t i = 0; i < INBOX_SLOTS; ++i) { seqs[i] = inbox_[i].seq; live[i] = 1; }
    int slot = freeSlot(seqs, live, INBOX_SLOTS);
    if (slot < 0) {
        for (int pass = 0; pass < 4 && slot < 0; ++pass) {
            for (size_t i = 0; i < INBOX_SLOTS; ++i) {
                const InboxEntry& e = inbox_[i];
                const bool candidate = pass == 0   ? ((e.flags & INBOX_READ) && e.type == sa1::BULLETIN)
                                       : pass == 1 ? (e.flags & INBOX_READ) != 0
                                       : pass == 2 ? !(e.flags & INBOX_NOTIFY)
                                                   : true;
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
    if (inbox_[slot].seq && !invalidate(address, MSG_IMMUTABLE)) return Put::ERROR;
    uint8_t state[INBOX_STATE + 3] = {static_cast<uint8_t>(record.flags & INBOX_NOTIFY)};
    if (!writeState(address + STATE_OFFSET, seq, state, INBOX_STATE)) return Put::ERROR;
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
    e.flags = state[0];
    record.seq = seq;
    record.flags = state[0];
    inboxSeq_ = seq;
    return Put::STORED;
}

bool Store::inboxRead(uint32_t seq, InboxRecord& record) {
    for (size_t slot = 0; slot < INBOX_SLOTS; ++slot) {
        if (inbox_[slot].seq != seq) continue;
        uint8_t buffer[RECORD];
        if (!readRecord(INBOX_BASE + slot * RECORD, buffer, MSG_IMMUTABLE, STATE_OFFSET + INBOX_STATE + 3)) return false;
        record = InboxRecord();
        record.seq = seq;
        if (!decodeMessageHeader(buffer, record.receivedS, record.type, record.revision, record.event, record.source, record.id, record.sa1,
                                 record.sa1Length)) return false;
        record.flags = stateValid(seq, buffer + STATE_OFFSET, INBOX_STATE) ? buffer[STATE_OFFSET] : 0;
        return true;
    }
    return false;
}

bool Store::inboxSetFlags(uint32_t seq, uint8_t flags) {
    for (size_t slot = 0; slot < INBOX_SLOTS; ++slot) {
        if (inbox_[slot].seq != seq) continue;
        if (inbox_[slot].flags == flags) return true;
        uint8_t state[INBOX_STATE + 3] = {flags};
        if (!writeState(INBOX_BASE + slot * RECORD + STATE_OFFSET, seq, state, INBOX_STATE)) return false;
        inbox_[slot].flags = flags;
        return true;
    }
    return false;
}

bool Store::inboxMarkRead(uint32_t seq) {
    for (size_t slot = 0; slot < INBOX_SLOTS; ++slot)
        if (inbox_[slot].seq == seq) return inboxSetFlags(seq, inbox_[slot].flags | INBOX_READ);
    return false;
}

bool Store::notePut(NoteRecord& record) {
    if (!ok_) return false;
    const size_t length = strlen(record.text);
    if (length > NOTE_TEXT) return false;
    uint32_t seqs[NOTE_SLOTS];
    uint8_t live[NOTE_SLOTS];
    for (size_t i = 0; i < NOTE_SLOTS; ++i) { seqs[i] = notes_[i].seq; live[i] = notes_[i].seq && !notes_[i].acked; }
    const int slot = freeSlot(seqs, live, NOTE_SLOTS);
    if (slot < 0) return false;   // wszystkie niepotwierdzone: zdarzenie bez ack zostaje (oprogramowanie.md)
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
    if (notes_[slot].seq && !invalidate(address, NOTE_IMMUTABLE)) return false;
    uint8_t state[NOTE_STATE + 3] = {};
    if (!writeState(address + STATE_OFFSET, seq, state, NOTE_STATE)) return false;
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
        if (!readRecord(NOTE_BASE + slot * RECORD, buffer, NOTE_IMMUTABLE, STATE_OFFSET + NOTE_STATE + 3)) return false;
        record = NoteRecord();
        record.seq = seq;
        record.createdS = getU32(buffer + 4);
        record.kind = buffer[8];
        record.ref = getU32(buffer + 9);
        const uint16_t length = getU16(buffer + 13);
        if (length > NOTE_TEXT) return false;
        memcpy(record.text, buffer + 15, length);
        record.text[length] = '\0';
        record.acked = stateValid(seq, buffer + STATE_OFFSET, NOTE_STATE) && buffer[STATE_OFFSET] != 0;
        return true;
    }
    return false;
}

bool Store::noteAck(uint32_t seq) {
    for (size_t slot = 0; slot < NOTE_SLOTS; ++slot) {
        if (notes_[slot].seq != seq) continue;
        if (notes_[slot].acked) return true;
        uint8_t state[NOTE_STATE + 3] = {1};
        if (!writeState(NOTE_BASE + slot * RECORD + STATE_OFFSET, seq, state, NOTE_STATE)) return false;
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
    uint32_t bestSeq = 0;
    for (uint32_t slot = 0; slot < SEEN_SLOTS; ++slot) {
        if (!readRecord(SEEN_BASE + slot * SEEN_RECORD, buffer, SEEN_IMMUTABLE, SEEN_IMMUTABLE + 3)) continue;
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
    uint32_t known = 0;
    uint8_t knownState = 0;
    if (seenGet(id, revision, known, knownState) && known == event && knownState == state) return true;  // bez zbędnego wpisu
    uint32_t seq = seenSeq_ + 1;
    if (!seqUsable(seq)) seq = 1;
    uint8_t buffer[SEEN_RECORD];
    memset(buffer, 0, sizeof(buffer));
    putU32(buffer, seq);
    memcpy(buffer + 4, id, HASH);
    putU16(buffer + 20, revision);
    putU32(buffer + 22, event);
    buffer[26] = state;
    const uint32_t address = SEEN_BASE + (seq % SEEN_SLOTS) * SEEN_RECORD;
    if (!invalidate(address, SEEN_IMMUTABLE) || !writeImmutable(address, buffer, SEEN_IMMUTABLE)) return false;
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
    // Najwyższe numery przed usunięciem: numeracja rekordów i kursor zdarzeń laptopa rosną dalej
    // (numer rekordu nigdy się nie powtarza; oprogramowanie.md, „Trwałość i potwierdzenia”).
    if (!writeCounters()) return false;
    if (!erase(QUEUE_BASE, QUEUE_SLOTS, RECORD) || !erase(INBOX_BASE, INBOX_SLOTS, RECORD) || !erase(NOTE_BASE, NOTE_SLOTS, RECORD)) return false;
    for (QueueEntry& e : queue_) e = QueueEntry();
    for (InboxEntry& e : inbox_) e = InboxEntry();
    for (NoteEntry& e : notes_) e = NoteEntry();
    return true;
}

bool Store::destroy() {
    if (!ok_) return false;
    if (!erase(CONFIG_BASE, CONFIG_SLOTS, CONFIG_SLOT) || !erase(QUEUE_BASE, QUEUE_SLOTS, RECORD) || !erase(INBOX_BASE, INBOX_SLOTS, RECORD) ||
        !erase(NOTE_BASE, NOTE_SLOTS, RECORD) || !erase(SEEN_BASE, SEEN_SLOTS, SEEN_RECORD) || !erase(COUNTERS_BASE, 1, 64)) return false;
    return begin();
}

uint16_t shortNumber(const uint8_t id[HASH]) {
    return static_cast<uint16_t>(((static_cast<uint16_t>(id[0]) << 8) | id[1]) % 10000);
}

}  // namespace store
