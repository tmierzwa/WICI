// SPDX-License-Identifier: MIT
#include "store.h"

#include <string.h>

#include <initializer_list>

#include "crc32.h"
#include "sha2.h"

namespace store {

namespace {

const uint8_t RECORD_MARK[4] = {'W', 'R', 'E', 'C'};
const uint8_t TX_MAGIC[4] = {'W', 'T', 'X', '1'};
const uint8_t TX_MARK[4] = {'W', 'T', 'X', 'C'};
const uint8_t TX_APPLIED[4] = {'W', 'T', 'X', 'A'};

constexpr size_t TX_HEADER = 24;          // magia 4, numer zapisu 8, liczba rekordów 2, długość 4, zapas 6
constexpr size_t TX_ITEM = 8 + SLOT;      // adres 4, długość 2, zapas 2, rekord
constexpr uint32_t TX_APPLIED_AT = TX_AREA - 16;   // numer zapisu 8, stała 4, zapas 4
constexpr size_t TX_ITEMS_MAX = (TX_APPLIED_AT - TX_HEADER - MARKER) / TX_ITEM;   // 7
constexpr size_t CONFIG_DOC = RECORD_HEADER + 2 + 32;  // dokument w kopii za nagłówkiem, długością i skrótem
constexpr uint32_t CONFIG_MARKER_AT = CONFIG_COPY - MARKER;
static_assert(CONFIG_DOC + config::DOC_MAX <= CONFIG_MARKER_AT - TAG, "dokument mieści się w kopii");
constexpr size_t BLOCK_BODY = EPOCH + BLOCK_ENTRIES * ENTRY;   // 392 B
constexpr size_t CHUNK = 256;             // seria SPI (oprogramowanie.md, "Zapis w FRAM")

void put16(uint8_t* p, uint16_t v) { p[0] = static_cast<uint8_t>(v); p[1] = static_cast<uint8_t>(v >> 8); }
void put32(uint8_t* p, uint32_t v) { put16(p, static_cast<uint16_t>(v)); put16(p + 2, static_cast<uint16_t>(v >> 16)); }
void put64(uint8_t* p, uint64_t v) { put32(p, static_cast<uint32_t>(v)); put32(p + 4, static_cast<uint32_t>(v >> 32)); }
uint16_t get16(const uint8_t* p) { return static_cast<uint16_t>(p[0] | (p[1] << 8)); }
uint32_t get32(const uint8_t* p) { return get16(p) | (static_cast<uint32_t>(get16(p + 2)) << 16); }
uint64_t get64(const uint8_t* p) { return get32(p) | (static_cast<uint64_t>(get32(p + 4)) << 32); }

// Kodowanie treści rekordów polami po kolei (ta sama kolejność w obu kierunkach).
struct Out {
    uint8_t* p;
    size_t n = 0;
    explicit Out(uint8_t* out) : p(out) {}
    void u8(uint8_t v) { p[n++] = v; }
    void u16(uint16_t v) { put16(p + n, v); n += 2; }
    void u32(uint32_t v) { put32(p + n, v); n += 4; }
    void bytes(const void* v, size_t length) { memcpy(p + n, v, length); n += length; }
};

struct In {
    const uint8_t* p;
    size_t length;
    size_t n = 0;
    In(const uint8_t* in, size_t size) : p(in), length(size) {}
    bool ok() const { return n <= length; }
    uint8_t u8() { return n + 1 <= length ? p[n++] : (n = length + 1, 0); }
    uint16_t u16() { if (n + 2 > length) { n = length + 1; return 0; } n += 2; return get16(p + n - 2); }
    uint32_t u32() { if (n + 4 > length) { n = length + 1; return 0; } n += 4; return get32(p + n - 4); }
    void bytes(void* v, size_t size) {
        if (n + size > length) { n = length + 1; memset(v, 0, size); return; }
        memcpy(v, p + n, size);
        n += size;
    }
};

size_t encodeRequest(const uint8_t epoch[EPOCH], const Request& r, uint8_t* body) {
    Out o(body);
    o.bytes(epoch, EPOCH);
    o.u16(r.gen);
    o.u8(r.type);
    o.u8(r.origin);
    o.bytes(r.id, HASH);
    o.u16(r.rMax);
    o.u32(static_cast<uint32_t>(r.rRcv));
    o.u8(static_cast<uint8_t>(r.stage));
    o.u8(r.flags);
    o.u8(r.decision);
    o.u8(r.urgency);
    o.u16(r.decisionRev);
    o.u8(r.category);
    o.u16(r.people);
    o.u16(r.attempts);
    o.u32(r.statusHi);
    o.u32(r.replyHi);
    o.u32(r.createdS);
    o.u32(r.changedS);
    o.u32(r.receivedS);
    o.u32(r.nextTryS);
    o.u32(r.firstSentS);
    o.u8(r.revisionCount);
    for (const RevisionTime& t : r.revisions) { o.u16(t.revision); o.u32(t.commitS); }
    o.bytes(r.nonce, NONCE);
    o.u16(r.sa1Length);
    o.bytes(r.sa1, r.sa1Length);
    return o.n;
}

bool decodeRequest(const uint8_t* body, size_t length, Request& r) {
    In in(body, length);
    uint8_t epoch[EPOCH];
    in.bytes(epoch, EPOCH);
    r.gen = in.u16();
    r.type = in.u8();
    r.origin = in.u8();
    in.bytes(r.id, HASH);
    r.rMax = in.u16();
    r.rRcv = static_cast<int32_t>(in.u32());
    r.stage = static_cast<Stage>(in.u8());
    r.flags = in.u8();
    r.decision = in.u8();
    r.urgency = in.u8();
    r.decisionRev = in.u16();
    r.category = in.u8();
    r.people = in.u16();
    r.attempts = in.u16();
    r.statusHi = in.u32();
    r.replyHi = in.u32();
    r.createdS = in.u32();
    r.changedS = in.u32();
    r.receivedS = in.u32();
    r.nextTryS = in.u32();
    r.firstSentS = in.u32();
    r.revisionCount = in.u8();
    for (RevisionTime& t : r.revisions) { t.revision = in.u16(); t.commitS = in.u32(); }
    in.bytes(r.nonce, NONCE);
    r.sa1Length = in.u16();
    if (r.sa1Length > sa1::MAX_CONTENT || r.revisionCount > REVISION_TIMES || r.stage > Stage::CANCELLED) return false;
    in.bytes(r.sa1, r.sa1Length);
    r.sa1[r.sa1Length] = '\0';
    return in.ok();
}

size_t encodeMessage(const uint8_t epoch[EPOCH], const Message& m, uint8_t* body) {
    Out o(body);
    o.bytes(epoch, EPOCH);
    o.u16(m.gen);
    o.u8(m.type);
    o.u8(m.source);
    o.u8(m.read ? 1 : 0);
    o.bytes(m.id, HASH);
    o.u16(m.revision);
    o.u32(m.event);
    o.u32(m.number);
    o.u32(m.receivedS);
    o.u16(m.sa1Length);
    o.bytes(m.sa1, m.sa1Length);
    return o.n;
}

bool decodeMessage(const uint8_t* body, size_t length, Message& m) {
    In in(body, length);
    uint8_t epoch[EPOCH];
    in.bytes(epoch, EPOCH);
    m.gen = in.u16();
    m.type = in.u8();
    m.source = in.u8();
    m.read = in.u8() != 0;
    in.bytes(m.id, HASH);
    m.revision = in.u16();
    m.event = in.u32();
    m.number = in.u32();
    m.receivedS = in.u32();
    m.sa1Length = in.u16();
    if (m.sa1Length > sa1::MAX_CONTENT) return false;
    in.bytes(m.sa1, m.sa1Length);
    m.sa1[m.sa1Length] = '\0';
    return in.ok();
}

enum MetaFlag : uint8_t { M_SILENCE = 0x01, M_EXCEPTION = 0x02, M_TEST_PAUSED = 0x04, M_CONTACT = 0x08, M_CLOSED = 0x10 };

size_t encodeMeta(const Meta& m, uint8_t* body) {
    Out o(body);
    o.bytes(m.epoch, EPOCH);
    o.u32(m.ringBase);
    o.bytes(m.dataEpoch, EPOCH);
    o.u32(m.tombFloor);
    o.u8(static_cast<uint8_t>(m.configCopy));
    o.u8(m.receiver);
    o.u8(static_cast<uint8_t>((m.silence ? M_SILENCE : 0) | (m.exceptionSet ? M_EXCEPTION : 0) | (m.testPaused ? M_TEST_PAUSED : 0) |
                              (m.contactKnown ? M_CONTACT : 0) | (m.closedSet ? M_CLOSED : 0)));
    o.u8(m.nonceNext);
    o.u32(m.configSeq);
    o.bytes(m.exception, HASH);
    o.u16(m.exceptionRev);
    o.u32(m.contactS);
    o.bytes(m.closedEpoch, EPOCH);
    o.u32(m.closedHead);
    o.u32(m.bulletinFloor);
    o.u32(m.bulletinMax);
    for (const TestNonce& t : m.nonces) { o.bytes(t.nonce, NONCE); o.bytes(t.id, HASH); }
    return o.n;
}

bool decodeMeta(const uint8_t* body, size_t length, Meta& m) {
    In in(body, length);
    in.bytes(m.epoch, EPOCH);
    m.ringBase = in.u32();
    in.bytes(m.dataEpoch, EPOCH);
    m.tombFloor = in.u32();
    m.configCopy = static_cast<int8_t>(in.u8());
    m.receiver = in.u8();
    const uint8_t flags = in.u8();
    m.nonceNext = in.u8();
    m.configSeq = in.u32();
    in.bytes(m.exception, HASH);
    m.exceptionRev = in.u16();
    m.contactS = in.u32();
    in.bytes(m.closedEpoch, EPOCH);
    m.closedHead = in.u32();
    m.bulletinFloor = in.u32();
    m.bulletinMax = in.u32();
    for (TestNonce& t : m.nonces) { in.bytes(t.nonce, NONCE); in.bytes(t.id, HASH); }
    m.silence = flags & M_SILENCE;
    m.exceptionSet = flags & M_EXCEPTION;
    m.testPaused = flags & M_TEST_PAUSED;
    m.contactKnown = flags & M_CONTACT;
    m.closedSet = flags & M_CLOSED;
    return in.ok() && m.configCopy >= -1 && m.configCopy <= 1 && m.receiver <= config::BACKUP && m.nonceNext < TEST_NONCES;
}

// Wpis pierścienia zdarzeń 24 B: ev 4, at 4, rodzaj 1, a 1 (bit 7: nowa decyzja), gniazdo 2,
// generacja 2, rewizja 2, decyzja 1, próba 1, rewizja decyzji 2, wartość 4.
void encodeEvent(const Event& e, uint8_t* p) {
    Out o(p);
    o.u32(e.ev);
    o.u32(e.at);
    o.u8(static_cast<uint8_t>(e.kind));
    o.u8(static_cast<uint8_t>((e.a & 0x7F) | (e.decisionChanged ? 0x80 : 0)));
    o.u16(e.slot);
    o.u16(e.gen);
    o.u16(e.revision);
    o.u8(e.decision);
    o.u8(e.attempt);
    o.u16(e.decisionRev);
    o.u32(e.value);
}

void decodeEvent(const uint8_t* p, Event& e) {
    In in(p, ENTRY);
    e.ev = in.u32();
    e.at = in.u32();
    e.kind = static_cast<EventKind>(in.u8());
    const uint8_t a = in.u8();
    e.a = a & 0x7F;
    e.decisionChanged = a & 0x80;
    e.slot = in.u16();
    e.gen = in.u16();
    e.revision = in.u16();
    e.decision = in.u8();
    e.attempt = in.u8();
    e.decisionRev = in.u16();
    e.value = in.u32();
}

// Wpis pamięci zwolnionych 24 B: id 16, rewizja 2, ev 4, krótki numer 14 b i znacznik anulowania 1 b.
void encodeReleased(const Released& r, uint8_t* p) {
    memcpy(p, r.id, HASH);
    put16(p + 16, r.revision);
    put32(p + 18, r.ev);
    put16(p + 22, static_cast<uint16_t>((r.number & 0x3FFF) | (r.cancelled ? 0x8000 : 0)));
}

void decodeReleased(const uint8_t* p, Released& r) {
    memcpy(r.id, p, HASH);
    r.revision = get16(p + 16);
    r.ev = get32(p + 18);
    r.number = get16(p + 22) & 0x3FFF;
    r.cancelled = get16(p + 22) & 0x8000;
}

// Wpis zbioru powtórzeń BULLETIN 24 B: id 16, event 4, tożsamość odbiorcy 1, zapas 3.
constexpr size_t BULLETIN_EVENT = 16;
constexpr size_t BULLETIN_SOURCE = 20;

uint32_t oldestPending(const Request& r) {
    // COMMIT najstarszej rewizji nowszej niż r_rcv.
    for (uint8_t i = 0; i < r.revisionCount; ++i) {
        if (static_cast<int32_t>(r.revisions[i].revision) > r.rRcv) return r.revisions[i].commitS;
    }
    return r.changedS;
}

}  // namespace

uint16_t prefixNumber(uint32_t prefix) { return static_cast<uint16_t>((prefix >> 16) % 10000); }
uint16_t shortNumber(const uint8_t id[HASH]) { return prefixNumber(idPrefix(id)); }
uint32_t idPrefix(const uint8_t id[HASH]) {
    return (static_cast<uint32_t>(id[0]) << 24) | (static_cast<uint32_t>(id[1]) << 16) | (static_cast<uint32_t>(id[2]) << 8) | id[3];
}
uint16_t RequestIndex::number() const { return prefixNumber(idPrefix); }

const char* stageCodeName(StageCode code) {
    static const char* const names[] = {"stored", "sending", "delivered", "received", "cancelled", "superseded", "released"};
    const size_t i = static_cast<size_t>(code);
    return i < sizeof(names) / sizeof(names[0]) ? names[i] : "?";
}

const char* beginName(Begin result) {
    static const char* const names[] = {"ok", "new", "memory", "format", "corrupt"};
    return names[static_cast<size_t>(result)];
}

// --- Transakcja ----------------------------------------------------------------------------

Tx::Tx(Store& store) : store_(store) {}

Tx::Change* Tx::change(Kind kind, uint16_t slot) {
    for (size_t i = 0; i < count_; ++i) {
        if (changes_[i].kind == kind && changes_[i].slot == slot) return &changes_[i];
    }
    if (count_ == MAX_CHANGES) { overflow_ = true; return nullptr; }
    Change* c = &changes_[count_++];
    c->kind = kind;
    c->slot = slot;
    return c;
}

uint16_t Tx::gen(Kind kind, uint16_t slot) const {
    for (size_t i = 0; i < count_; ++i) {
        if (changes_[i].kind == kind && changes_[i].slot == slot) return get16(changes_[i].body + (changes_[i].length ? EPOCH : 0));
    }
    return kind == REGISTER ? store_.register_[slot].gen : store_.inbox_[slot].gen;
}

void Tx::request(uint16_t slot, const Request& r, bool fresh) {
    Change* c = change(REGISTER, slot);
    if (!c) return;
    // Generacja rośnie przy każdym ponownym zajęciu gniazda.
    Request copy = r;
    copy.gen = static_cast<uint16_t>(store_.register_[slot].gen + (fresh ? 1 : 0));
    c->length = static_cast<uint16_t>(encodeRequest(store_.meta_.dataEpoch, copy, c->body));
}

void Tx::message(uint16_t slot, const Message& m, bool fresh) {
    Change* c = change(INBOX, slot);
    if (!c) return;
    Message copy = m;
    copy.gen = static_cast<uint16_t>(store_.inbox_[slot].gen + (fresh ? 1 : 0));
    c->length = static_cast<uint16_t>(encodeMessage(store_.meta_.dataEpoch, copy, c->body));
}

void Tx::free(Kind kind, uint16_t slot) {
    Change* c = change(kind, slot);
    if (!c) return;
    c->length = 0;   // rekord „wolne”: treść to tylko generacja gniazda
    put16(c->body, kind == REGISTER ? store_.register_[slot].gen : kind == INBOX ? store_.inbox_[slot].gen : 0);
}

void Tx::released(const Released& r) {
    releasedSet_ = true;
    released_ = r;
    // Nadpisanie najstarszego wpisu: pamięć jest kompletna od następnego najstarszego.
    const size_t next = store_.releasedNext_;
    if (store_.releasedEv_[next]) meta().tombFloor = store_.releasedEv_[(next + 1) % RELEASED_ENTRIES];
}

void Tx::bulletin(const uint8_t id[HASH], uint32_t event) {
    // Wolny wpis (także wpis innej tożsamości odbiorcy) albo wpis o najmniejszym event, który
    // staje się bulletin_floor.
    const uint8_t source = store_.meta_.receiver;
    size_t target = BULLETIN_ENTRIES;
    for (size_t i = 0; i < BULLETIN_ENTRIES && target == BULLETIN_ENTRIES; ++i) {
        if (!store_.bulletinEvent_[i] || store_.bulletinSource_[i] != source) target = i;
    }
    if (target == BULLETIN_ENTRIES) {
        target = 0;
        for (size_t i = 1; i < BULLETIN_ENTRIES; ++i) {
            if (store_.bulletinEvent_[i] < store_.bulletinEvent_[target]) target = i;
        }
        Meta& m = meta();
        if (store_.bulletinEvent_[target] > m.bulletinFloor) m.bulletinFloor = store_.bulletinEvent_[target];
    }
    if (event > meta().bulletinMax) meta().bulletinMax = event;
    bulletinSet_ = true;
    bulletinIndex_ = target;
    memcpy(bulletinId_, id, HASH);
    bulletinEvent_ = event;
}

Meta& Tx::meta() {
    if (!metaSet_) { meta_ = store_.meta_; metaSet_ = true; }
    return meta_;
}

uint32_t Tx::event(const Event& e) {
    if (eventCount_ == MAX_EVENTS || store_.head_ + eventCount_ + 1 == 0) { overflow_ = true; return 0; }
    Event& out = events_[eventCount_++];
    out = e;
    out.ev = store_.head_ + static_cast<uint32_t>(eventCount_);
    out.at = store_.nowS_;
    return out.ev;
}

bool Tx::commit() { return !overflow_ && store_.commitTx(*this); }

// --- Magazyn ---------------------------------------------------------------------------------

Store::Store(journal::Storage& memory, journal::Journal& journal, void (*random)(uint8_t*, size_t), const char* profile)
    : memory_(memory), journal_(journal), random_(random), profile_(profile) {}

namespace {

uint32_t addressOf(Kind kind, uint16_t slot) {
    switch (kind) {
        case META: return META_BASE;
        case BULLETIN: return BULLETIN_BASE + slot * SLOT;
        case REGISTER: return REGISTER_BASE + slot * SLOT;
        case INBOX: return INBOX_BASE + slot * SLOT;
        case RELEASED: return RELEASED_BASE + slot * SLOT;
        case RING: return RING_BASE + slot * SLOT;
        default: return 0;
    }
}

uint16_t slotsOf(Kind kind) {
    switch (kind) {
        case META: return 1;
        case BULLETIN: return BULLETIN_BLOCKS;
        case REGISTER: return REGISTER_SLOTS;
        case INBOX: return INBOX_SLOTS;
        case RELEASED: return RELEASED_BLOCKS;
        case RING: return RING_BLOCKS;
        default: return 0;
    }
}

}  // namespace

void Store::encode(Kind kind, uint16_t slot, uint64_t writeNo, const uint8_t* body, size_t length, uint8_t out[SLOT]) const {
    memset(out, 0, SLOT);
    out[0] = kind;
    put16(out + 1, slot);
    out[3] = static_cast<uint8_t>(journal::FRAM_FORMAT);
    put32(out + 4, 0);                    // generacja klucza: rekord jawny
    put64(out + 8, writeNo);
    put16(out + 16, static_cast<uint16_t>(length));
    memcpy(out + RECORD_HEADER, body, length ? length : 2);   // rekord „wolne”: generacja gniazda
    put32(out + SLOT - MARKER, crc32::of(out, SLOT - MARKER));
    memcpy(out + SLOT - 4, RECORD_MARK, 4);
}

SlotState Store::decode(const uint8_t record[SLOT], Kind kind, uint16_t slot, uint8_t* body, size_t& length, uint16_t& gen) const {
    length = 0;
    gen = 0;
    if (journal::blank(record, SLOT)) return SlotState::FREE;
    length = get16(record + 16);
    if (memcmp(record + SLOT - 4, RECORD_MARK, 4) || get32(record + SLOT - MARKER) != crc32::of(record, SLOT - MARKER) ||
        record[0] != kind || get16(record + 1) != slot || record[3] != journal::FRAM_FORMAT || get32(record + 4) != 0 || length > BODY_MAX) {
        length = 0;
        return SlotState::CORRUPT;
    }
    const uint8_t* b = record + RECORD_HEADER;
    if (!length) { gen = get16(b); return SlotState::FREE; }
    memcpy(body, b, length);
    const bool epochTagged = kind == REGISTER || kind == INBOX || kind == RELEASED || kind == RING;
    if (kind == REGISTER || kind == INBOX) gen = get16(b + EPOCH);
    if (epochTagged && (length < EPOCH || memcmp(b, kind == RING ? meta_.epoch : meta_.dataEpoch, EPOCH))) return SlotState::STALE;
    return SlotState::USED;
}

bool Store::readSlot(uint32_t address, Kind kind, uint16_t slot, uint8_t* body, size_t& length, SlotState& state, uint16_t& gen) {
    uint8_t record[SLOT];
    if (!memory_.read(address, record, SLOT)) return false;
    state = decode(record, kind, slot, body, length, gen);
    return true;
}

bool Store::allocate(uint64_t& out) {
    // Numer z bloku zarezerwowanego w dzienniku; nowy blok zapisany przed użyciem pierwszego numeru.
    if (nextWrite_ >= reservedUpper_) {
        if (!journal_.writeReservation(reservedUpper_ + WRITE_BLOCK)) return false;
        reservedUpper_ += WRITE_BLOCK;
    }
    out = nextWrite_++;
    return true;
}

bool Store::readBlock(Kind kind, uint16_t block, uint8_t body[BODY_MAX]) {
    // Blok bieżącej epoki albo pusty blok (wolny, starej epoki). Blok uszkodzony (policzony przy
    // starcie w diag_.corruptSlots) też zaczyna od pustego: jego wpisy przepadły, a zostawiony
    // blokowałby każdą transakcję ze zdarzeniem, zwolnieniem albo BULLETIN.
    size_t length = 0;
    SlotState state;
    uint16_t gen;
    if (!readSlot(addressOf(kind, block), kind, block, body, length, state, gen)) return false;
    if (state != SlotState::USED || length != (kind == BULLETIN ? BLOCK_ENTRIES * ENTRY : BLOCK_BODY)) {
        memset(body, 0, BODY_MAX);
        if (kind != BULLETIN) memcpy(body, kind == RING ? meta_.epoch : meta_.dataEpoch, EPOCH);
    }
    return true;
}

bool Store::commitTx(Tx& tx) {
    if (!ok_) return false;
    // Rekordy transakcji: gniazda, bloki pierścienia, blok pamięci zwolnionych, blok zbioru
    // powtórzeń, meta. Każdy z własnym numerem zapisu.
    struct Item {
        Kind kind;
        uint16_t slot;
        const uint8_t* body;
        size_t length;
    };
    Item items[TX_ITEMS_MAX];
    size_t count = 0;
    for (size_t i = 0; i < tx.count_; ++i) items[count++] = {tx.changes_[i].kind, tx.changes_[i].slot, tx.changes_[i].body, tx.changes_[i].length};
    uint8_t ring[2][BODY_MAX];
    uint16_t ringBlock[2] = {};
    size_t ringCount = 0;
    for (size_t i = 0; i < tx.eventCount_; ++i) {
        const Event& e = tx.events_[i];
        const uint16_t block = static_cast<uint16_t>(((e.ev - 1) % RING_ENTRIES) / BLOCK_ENTRIES);
        size_t b = 0;
        while (b < ringCount && ringBlock[b] != block) ++b;
        if (b == ringCount) {
            if (ringCount == 2 || !readBlock(RING, block, ring[b])) return false;
            ringBlock[ringCount++] = block;
        }
        encodeEvent(e, ring[b] + EPOCH + ((e.ev - 1) % BLOCK_ENTRIES) * ENTRY);
    }
    if (count + ringCount + tx.releasedSet_ + tx.bulletinSet_ + tx.metaSet_ > TX_ITEMS_MAX) return false;   // błąd programu
    for (size_t b = 0; b < ringCount; ++b) items[count++] = {RING, ringBlock[b], ring[b], BLOCK_BODY};
    uint8_t releasedBody[BODY_MAX], bulletinBody[BODY_MAX], metaBody[BODY_MAX];
    if (tx.releasedSet_) {
        const uint16_t block = static_cast<uint16_t>(releasedNext_ / BLOCK_ENTRIES);
        if (!readBlock(RELEASED, block, releasedBody)) return false;
        encodeReleased(tx.released_, releasedBody + EPOCH + (releasedNext_ % BLOCK_ENTRIES) * ENTRY);
        items[count++] = {RELEASED, block, releasedBody, BLOCK_BODY};
    }
    if (tx.bulletinSet_) {
        const uint16_t block = static_cast<uint16_t>(tx.bulletinIndex_ / BLOCK_ENTRIES);
        if (!readBlock(BULLETIN, block, bulletinBody)) return false;
        uint8_t* entry = bulletinBody + (tx.bulletinIndex_ % BLOCK_ENTRIES) * ENTRY;
        memset(entry, 0, ENTRY);
        memcpy(entry, tx.bulletinId_, HASH);
        put32(entry + BULLETIN_EVENT, tx.bulletinEvent_);
        entry[BULLETIN_SOURCE] = meta_.receiver;
        items[count++] = {BULLETIN, block, bulletinBody, BLOCK_ENTRIES * ENTRY};
    }
    if (tx.metaSet_) items[count++] = {META, 0, metaBody, encodeMeta(tx.meta_, metaBody)};
    if (!count) return true;

    // Rekord transakcji: nagłówek, rekordy, znacznik zatwierdzenia (CRC liczone w tej kolejności).
    const uint32_t area = TX_BASE + txArea_ * TX_AREA;
    uint64_t txNo = 0;
    if (!allocate(txNo)) return false;
    uint8_t header[TX_HEADER] = {};
    memcpy(header, TX_MAGIC, 4);
    put64(header + 4, txNo);
    put16(header + 12, static_cast<uint16_t>(count));
    put32(header + 14, static_cast<uint32_t>(count * TX_ITEM));
    uint32_t crc = crc32::update(crc32::START, header, TX_HEADER);
    if (!memory_.write(area, header, TX_HEADER)) return false;
    uint8_t item[TX_ITEM];
    for (size_t i = 0; i < count; ++i) {
        uint64_t writeNo = 0;
        if (!allocate(writeNo)) return false;
        memset(item, 0, 8);
        put32(item, addressOf(items[i].kind, items[i].slot));
        put16(item + 4, static_cast<uint16_t>(SLOT));
        encode(items[i].kind, items[i].slot, writeNo, items[i].body, items[i].length, item + 8);
        crc = crc32::update(crc, item, TX_ITEM);
        if (!memory_.write(area + TX_HEADER + i * TX_ITEM, item, TX_ITEM)) return false;
    }
    uint8_t marker[MARKER];
    put32(marker, crc32::finish(crc));
    memcpy(marker + 4, TX_MARK, 4);
    if (!memory_.write(area + TX_HEADER + count * TX_ITEM, marker, MARKER)) return false;   // COMMIT
    ++changes_;
    txArea_ ^= 1;
    bool found = false;
    if (!applyTx(area, true, found) || !found) {
        // Zatwierdzona transakcja zostanie wykonana przy następnym starcie; do tego czasu magazyn stoi.
        ok_ = false;
        return false;
    }
    return true;   // head_ i indeksy zaktualizował absorb()
}

bool Store::applyTx(uint32_t area, bool absorbRecords, bool& found) {
    // Zatwierdzony rekord transakcji: bajty do gniazd, indeksy, znacznik wykonania.
    uint8_t header[TX_HEADER];
    found = false;
    if (!memory_.read(area, header, TX_HEADER)) return false;
    const size_t count = get16(header + 12);
    const uint32_t length = get32(header + 14);
    if (memcmp(header, TX_MAGIC, 4) || count == 0 || count > TX_ITEMS_MAX || length != count * TX_ITEM) return true;   // brak transakcji
    uint32_t crc = crc32::update(crc32::START, header, TX_HEADER);
    uint8_t item[TX_ITEM];
    for (size_t i = 0; i < count; ++i) {
        if (!memory_.read(area + TX_HEADER + i * TX_ITEM, item, TX_ITEM)) return false;
        crc = crc32::update(crc, item, TX_ITEM);
    }
    uint8_t marker[MARKER];
    if (!memory_.read(area + TX_HEADER + length, marker, MARKER)) return false;
    if (get32(marker) != crc32::finish(crc) || memcmp(marker + 4, TX_MARK, 4)) return true;   // niezatwierdzona: odrzucona
    const uint64_t writeNo = get64(header + 4);
    found = true;
    uint8_t applied[16];
    if (!memory_.read(area + TX_APPLIED_AT, applied, sizeof(applied))) return false;
    if (!absorbRecords && get64(applied) == writeNo && !memcmp(applied + 8, TX_APPLIED, 4)) return true;   // już wykonana
    for (size_t i = 0; i < count; ++i) {
        if (!memory_.read(area + TX_HEADER + i * TX_ITEM, item, TX_ITEM)) return false;
        const uint32_t address = get32(item);
        const uint8_t* record = item + 8;
        const Kind kind = static_cast<Kind>(record[0]);
        const uint16_t slot = get16(record + 1);
        if (slot >= slotsOf(kind) || address != addressOf(kind, slot)) return false;   // nie zdarza się przy poprawnym CRC
        if (!memory_.write(address, record, SLOT)) return false;
        if (absorbRecords) {
            uint8_t body[BODY_MAX];
            size_t bodyLength = 0;
            uint16_t gen = 0;
            const SlotState state = decode(record, kind, slot, body, bodyLength, gen);
            absorb(kind, slot, body, bodyLength, state, gen);
        }
    }
    if (!absorbRecords) ++diag_.replayed;
    memset(applied, 0, sizeof(applied));
    put64(applied, writeNo);
    memcpy(applied + 8, TX_APPLIED, 4);
    return memory_.write(area + TX_APPLIED_AT, applied, sizeof(applied));
}

bool Store::recover() {
    // Zatwierdzone, niewykonane transakcje po kolei numerów zapisu; następna transakcja trafia do
    // rekordu ze starszą transakcją.
    uint64_t numbers[2] = {};
    uint8_t header[TX_HEADER];
    for (uint8_t a = 0; a < 2; ++a) {
        if (!memory_.read(TX_BASE + a * TX_AREA, header, TX_HEADER)) return false;
        if (!memcmp(header, TX_MAGIC, 4)) numbers[a] = get64(header + 4) + 1;
    }
    const uint8_t first = numbers[1] && (!numbers[0] || numbers[1] < numbers[0]) ? 1 : 0;
    for (uint8_t i = 0; i < 2; ++i) {
        const uint8_t a = i ? first ^ 1 : first;
        bool found = false;
        if (numbers[a] && !applyTx(TX_BASE + a * TX_AREA, false, found)) return false;
    }
    txArea_ = numbers[0] <= numbers[1] ? 0 : 1;
    return true;
}

void Store::staleRing() {
    // Nowa epoka pierścienia: bloki starej epoki są wolne, numeracja od ringBase + 1.
    for (SlotState& s : ringState_) if (s == SlotState::USED) s = SlotState::STALE;
    head_ = meta_.ringBase;
}

void Store::staleAll() {
    // Nowa epoka danych: rejestr, skrzynka, pamięć zwolnionych i pierścień starej epoki są wolne.
    for (RequestIndex& r : register_) if (r.state == SlotState::USED) { const uint16_t gen = r.gen; r = RequestIndex(); r.gen = gen; r.state = SlotState::STALE; }
    for (MessageIndex& m : inbox_) if (m.state == SlotState::USED) { const uint16_t gen = m.gen; m = MessageIndex(); m.gen = gen; m.state = SlotState::STALE; }
    for (SlotState& s : releasedState_) if (s == SlotState::USED) s = SlotState::STALE;
    for (SlotState& s : ringState_) if (s == SlotState::USED) s = SlotState::STALE;
    memset(releasedPrefix_, 0, sizeof(releasedPrefix_));
    memset(releasedEv_, 0, sizeof(releasedEv_));
    memset(releasedNumber_, 0, sizeof(releasedNumber_));
    releasedNext_ = 0;
    head_ = 0;
}

void Store::absorb(Kind kind, uint16_t slot, const uint8_t* body, size_t length, SlotState state, uint16_t gen) {
    if (state == SlotState::CORRUPT) {
        ++diag_.corruptSlots;
        corruptBlocks_ |= kind == RING ? 1 : kind == RELEASED ? 2 : kind == BULLETIN ? 4 : 0;
    }
    switch (kind) {
        case META: {
            Meta m;
            if (state != SlotState::USED || !decodeMeta(body, length, m)) break;
            const bool newData = memcmp(m.dataEpoch, meta_.dataEpoch, EPOCH) != 0;
            const bool newRing = memcmp(m.epoch, meta_.epoch, EPOCH) != 0;
            const bool newReceiver = m.receiver != meta_.receiver;
            meta_ = m;
            if (newData) staleAll();
            if (newRing) staleRing();
            if (newReceiver) memset(bulletinEvent_, 0, sizeof(bulletinEvent_));   // zbiór powtórzeń od zera
            break;
        }
        case REGISTER: {
            RequestIndex& x = register_[slot];
            x = RequestIndex();
            x.state = state;
            x.gen = gen;
            Request r;
            if (state != SlotState::USED) break;
            if (!decodeRequest(body, length, r)) { x.state = SlotState::CORRUPT; ++diag_.corruptSlots; break; }
            x.type = r.type;
            x.stage = r.stage;
            x.flags = r.flags;
            x.decision = r.decision;
            x.urgency = r.urgency;
            x.category = r.category;
            x.rMax = r.rMax;
            x.decisionRev = r.decisionRev;
            x.attempts = r.attempts;
            x.idPrefix = idPrefix(r.id);
            x.commitS = r.revisionCount ? r.revisions[r.revisionCount - 1].commitS : r.createdS;
            x.changedS = r.changedS;
            x.nextTryS = r.nextTryS;
            if (r.stage == Stage::RECEIVED) x.alarmS = r.receivedS;
            else if (r.stage != Stage::CANCELLED) x.alarmS = r.type == sa1::TEST ? r.firstSentS : oldestPending(r);
            break;
        }
        case INBOX: {
            MessageIndex& x = inbox_[slot];
            x = MessageIndex();
            x.state = state;
            x.gen = gen;
            Message m;
            if (state != SlotState::USED) break;
            if (!decodeMessage(body, length, m)) { x.state = SlotState::CORRUPT; ++diag_.corruptSlots; break; }
            x.type = m.type;
            x.source = m.source;
            x.read = m.read;
            x.idPrefix = idPrefix(m.id);
            x.number = m.number;
            x.receivedS = m.receivedS;
            break;
        }
        case RELEASED: {
            releasedState_[slot] = state;
            uint32_t newest = 0;
            for (size_t i = 0; i < BLOCK_ENTRIES; ++i) {
                const size_t index = slot * BLOCK_ENTRIES + i;
                Released r;
                if (state == SlotState::USED) decodeReleased(body + EPOCH + i * ENTRY, r);
                releasedPrefix_[index] = idPrefix(r.id);
                releasedEv_[index] = r.ev;
                releasedNumber_[index] = static_cast<uint16_t>(r.number | (r.cancelled ? 0x8000 : 0));
            }
            // Następny wpis: za wpisem o najwyższym ev (pamięć wypełnia się po kolei).
            for (size_t i = 0; i < RELEASED_ENTRIES; ++i) {
                if (releasedEv_[i] > newest) { newest = releasedEv_[i]; releasedNext_ = (i + 1) % RELEASED_ENTRIES; }
            }
            if (!newest) releasedNext_ = 0;
            break;
        }
        case RING: {
            ringState_[slot] = state;
            if (state != SlotState::USED) break;
            for (size_t i = 0; i < BLOCK_ENTRIES; ++i) {
                const uint32_t ev = get32(body + EPOCH + i * ENTRY);
                if (ev > head_) head_ = ev;
            }
            break;
        }
        case BULLETIN: {
            bulletinState_[slot] = state;
            for (size_t i = 0; i < BLOCK_ENTRIES; ++i) {
                const size_t index = slot * BLOCK_ENTRIES + i;
                const uint8_t* entry = body + i * ENTRY;
                const bool used = state == SlotState::USED;
                bulletinPrefix_[index] = used ? idPrefix(entry) : 0;
                bulletinEvent_[index] = used ? get32(entry + BULLETIN_EVENT) : 0;
                bulletinSource_[index] = used ? entry[BULLETIN_SOURCE] : 0;
            }
            break;
        }
        default: break;
    }
}

bool Store::scan() {
    uint8_t body[BODY_MAX];
    size_t length = 0;
    SlotState state;
    uint16_t gen;
    head_ = meta_.ringBase;
    for (Kind kind : {BULLETIN, REGISTER, INBOX, RELEASED, RING}) {
        for (uint16_t slot = 0; slot < slotsOf(kind); ++slot) {
            if (!readSlot(addressOf(kind, slot), kind, slot, body, length, state, gen)) return false;
            absorb(kind, slot, body, length, state, gen);
        }
    }
    return true;
}

bool Store::format(uint32_t flags) {
    // Pusty magazyn: nowa epoka w rekordzie meta, potem rekord formatu w dzienniku.
    meta_ = Meta();
    random_(meta_.epoch, EPOCH);
    random_(meta_.dataEpoch, EPOCH);
    ok_ = true;
    Tx tx(*this);
    tx.meta() = meta_;
    if (!tx.commit()) return false;
    return journal_.writeFormat(journal::FormatState::READY, flags);
}

Begin Store::begin() {
    ok_ = false;
    diag_ = Diagnostics();
    meta_ = Meta();
    config_ = config::Config();
    configSize_ = 0;
    for (RequestIndex& r : register_) r = RequestIndex();
    for (MessageIndex& m : inbox_) m = MessageIndex();
    staleAll();
    memset(bulletinEvent_, 0, sizeof(bulletinEvent_));
    if (!journal_.ok()) return Begin::MEMORY;
    nextWrite_ = reservedUpper_ = journal_.reservation();
    if (!recover()) return Begin::MEMORY;
    uint8_t body[BODY_MAX];
    size_t length = 0;
    SlotState state;
    uint16_t gen;
    if (!readSlot(META_BASE, META, 0, body, length, state, gen)) return Begin::MEMORY;
    Begin result = Begin::OK;
    switch (journal_.formatState()) {
        case journal::FormatState::DESTROYING:
            // ZNISZCZ DANE przerwane zanikiem zasilania: dokończone przed czymkolwiek innym.
            ok_ = true;
            return destroy() ? Begin::NEW : Begin::MEMORY;
        case journal::FormatState::CORRUPT: return Begin::FORMAT;
        case journal::FormatState::BLANK:
            // Nowa pamięć; meta bez rekordu formatu to dane, których stacja nie zna (nie nowa stacja).
            if (state != SlotState::FREE) return Begin::CORRUPT;
            if (!format(0)) return Begin::MEMORY;
            result = Begin::NEW;
            break;
        case journal::FormatState::READY:
            if (journal_.formatVersion() != journal::FRAM_FORMAT) return Begin::FORMAT;
            if (state != SlotState::USED || !decodeMeta(body, length, meta_)) return Begin::CORRUPT;
            break;
    }
    ok_ = true;
    corruptBlocks_ = 0;
    if (!scan() || !loadConfig()) { ok_ = false; return Begin::MEMORY; }
    if (corruptBlocks_ && !recoverBlocks()) { ok_ = false; return Begin::MEMORY; }
    return result;
}

bool Store::copyCrc(uint32_t base, uint32_t& crc) {
    uint8_t chunk[CHUNK];
    crc = crc32::START;
    for (uint32_t offset = 0; offset < CONFIG_MARKER_AT; offset += CHUNK) {
        const size_t n = CONFIG_MARKER_AT - offset < CHUNK ? CONFIG_MARKER_AT - offset : CHUNK;
        if (!memory_.read(base + offset, chunk, n)) return false;
        crc = crc32::update(crc, chunk, n);
    }
    crc = crc32::finish(crc);
    return true;
}

bool Store::hashCopy(int8_t copy, uint32_t size, uint8_t out[32]) {
    sha2::Hash hash;
    uint8_t chunk[CHUNK];
    const uint32_t base = CONFIG_BASE + copy * CONFIG_COPY + CONFIG_DOC;
    for (uint32_t offset = 0; offset < size; offset += CHUNK) {
        const size_t n = size - offset < CHUNK ? size - offset : CHUNK;
        if (!memory_.read(base + offset, chunk, n)) return false;
        hash.update(chunk, n);
    }
    hash.finish(out);
    return true;
}

namespace {

// Dokument konfiguracji czytany wprost z kopii w FRAM.
struct CopySource : config::Source {
    journal::Storage& memory;
    uint32_t base;
    CopySource(journal::Storage& m, uint32_t b) : memory(m), base(b) {}
    bool read(uint32_t offset, char* out, size_t length) override {
        return memory.read(base + offset, reinterpret_cast<uint8_t*>(out), length);
    }
};

}  // namespace

bool Store::loadConfig() {
    // Aktywna kopia: znacznik, nagłówek, SHA-256 dokumentu i pełna kontrola treści; kopia
    // nieczytelna zostawia stację bez konfiguracji (diagnostyka), nigdy z częściową.
    config_ = config::Config();
    configSize_ = 0;
    if (meta_.configCopy < 0) return true;
    const uint32_t base = CONFIG_BASE + meta_.configCopy * CONFIG_COPY;
    uint8_t head[CONFIG_DOC], marker[MARKER];
    uint32_t crc = 0;
    if (!memory_.read(base, head, sizeof(head)) || !memory_.read(base + CONFIG_MARKER_AT, marker, MARKER) || !copyCrc(base, crc)) {
        diag_.configCorrupt = true;   // także po odmowie configure: konfiguracja w RAM pusta do restartu
        return false;
    }
    const uint32_t size = get16(head + RECORD_HEADER);
    uint8_t sha[32];
    size_t worst = 0;
    CopySource source(memory_, base + CONFIG_DOC);
    if (get32(marker) != crc || memcmp(marker + 4, RECORD_MARK, 4) || head[0] != CONFIG || get16(head + 1) != meta_.configCopy ||
        head[3] != journal::FRAM_FORMAT || size > config::DOC_MAX || !hashCopy(meta_.configCopy, size, sha) ||
        memcmp(sha, head + RECORD_HEADER + 2, 32) || config::parse(source, size, profile_, config_, worst)) {
        config_ = config::Config();
        diag_.configCorrupt = true;
        return true;
    }
    config_.seq = meta_.configSeq;
    configSize_ = size;
    memcpy(configSha_, sha, sizeof(sha));
    if (selected_ >= config_.addressCount) selected_ = 0;
    return true;
}

bool Store::configBegin() {
    if (!ok_) return false;
    configNext_ = meta_.configCopy == 0 ? 1 : 0;
    const uint8_t zero[MARKER] = {};
    return memory_.write(CONFIG_BASE + configNext_ * CONFIG_COPY + CONFIG_MARKER_AT, zero, MARKER);
}

bool Store::configWrite(uint32_t offset, const uint8_t* data, size_t length) {
    if (!ok_ || configNext_ < 0 || offset > config::DOC_MAX || length > config::DOC_MAX - offset) return false;
    return memory_.write(CONFIG_BASE + configNext_ * CONFIG_COPY + CONFIG_DOC + offset, data, length);
}

bool Store::configStaged(uint32_t offset, uint8_t* out, size_t length) {
    if (!ok_ || configNext_ < 0 || offset > config::DOC_MAX || length > config::DOC_MAX - offset) return false;
    return memory_.read(CONFIG_BASE + configNext_ * CONFIG_COPY + CONFIG_DOC + offset, out, length);
}

Store::ConfigResult Store::configCommit(uint32_t size, const uint8_t sha[32], const char*& detail, size_t& worst) {
    detail = nullptr;
    if (!ok_ || configNext_ < 0 || size > config::DOC_MAX) return ConfigResult::MEMORY;
    const int8_t copy = configNext_;
    const uint32_t base = CONFIG_BASE + copy * CONFIG_COPY;
    uint8_t digest[32];
    if (!hashCopy(copy, size, digest)) return ConfigResult::MEMORY;
    if (memcmp(digest, sha, sizeof(digest))) return ConfigResult::HASH;
    // Rozbiór wprost do konfiguracji w RAM; przy odmowie wraca aktywna kopia.
    uint8_t mainLxmf[HASH];
    memcpy(mainLxmf, config_.receivers[config::MAIN].lxmf, HASH);
    CopySource source(memory_, base + CONFIG_DOC);
    detail = config::parse(source, size, profile_, config_, worst);
    if (detail) {
        const char* why = detail;
        loadConfig();
        detail = why;
        return ConfigResult::INVALID;
    }
    // Nagłówek kopii, długość i skrót, potem znacznik zatwierdzenia kopii.
    uint8_t head[CONFIG_DOC] = {};
    uint64_t writeNo = 0;
    if (!allocate(writeNo)) { loadConfig(); return ConfigResult::MEMORY; }
    head[0] = CONFIG;
    put16(head + 1, static_cast<uint16_t>(copy));
    head[3] = static_cast<uint8_t>(journal::FRAM_FORMAT);
    put64(head + 8, writeNo);
    put16(head + 16, static_cast<uint16_t>(2 + 32 + size));
    put16(head + RECORD_HEADER, static_cast<uint16_t>(size));
    memcpy(head + RECORD_HEADER + 2, digest, 32);
    const uint8_t zero[CHUNK] = {};
    bool written = memory_.write(base, head, sizeof(head));
    for (uint32_t offset = CONFIG_DOC + size; written && offset < CONFIG_MARKER_AT; offset += CHUNK) {
        const size_t n = CONFIG_MARKER_AT - offset < CHUNK ? CONFIG_MARKER_AT - offset : CHUNK;
        written = memory_.write(base + offset, zero, n);   // dopełnienie i znacznik AEAD: zera
    }
    uint32_t crc = 0;
    uint8_t marker[MARKER];
    if (written && copyCrc(base, crc)) {
        put32(marker, crc);
        memcpy(marker + 4, RECORD_MARK, 4);
        written = memory_.write(base + CONFIG_MARKER_AT, marker, MARKER);
    } else written = false;
    // Publikacja: transakcja wskaźnika kopii (rola odbiorcy wraca do głównej z nowej karty).
    Tx tx(*this);
    Meta& m = tx.meta();
    m.configCopy = copy;
    m.configSeq = meta_.configSeq + 1;
    if (m.receiver != config::MAIN || memcmp(mainLxmf, config_.receivers[config::MAIN].lxmf, HASH)) {
        m.receiver = config::MAIN;
        m.bulletinFloor = m.bulletinMax = 0;
        m.contactKnown = false;
    }
    Event e;
    e.kind = EventKind::STATION;
    e.a = CONFIGURED;
    e.value = m.configSeq;
    tx.event(e);
    if (!written || !tx.commit()) { loadConfig(); return ConfigResult::MEMORY; }
    configNext_ = -1;
    config_.seq = meta_.configSeq;
    configSize_ = size;
    memcpy(configSha_, digest, sizeof(digest));
    if (selected_ >= config_.addressCount) selected_ = 0;
    return ConfigResult::OK;
}

bool Store::configRead(uint32_t offset, uint8_t* out, size_t length) {
    if (!configured() || offset > configSize_ || length > configSize_ - offset) return false;
    return memory_.read(CONFIG_BASE + meta_.configCopy * CONFIG_COPY + CONFIG_DOC + offset, out, length);
}

const uint8_t* Store::recipient() const {
    return station() ? config_.receivers[meta_.receiver].sa1 : nullptr;
}

bool Store::readRequest(size_t slot, Request& out) {
    if (slot >= REGISTER_SLOTS || !register_[slot].used()) return false;
    uint8_t body[BODY_MAX];
    size_t length = 0;
    SlotState state;
    uint16_t gen;
    return readSlot(addressOf(REGISTER, static_cast<uint16_t>(slot)), REGISTER, static_cast<uint16_t>(slot), body, length, state, gen) &&
           state == SlotState::USED && decodeRequest(body, length, out);
}

int Store::findRequest(const uint8_t id[HASH]) {
    const uint32_t prefix = idPrefix(id);
    Request r;
    for (size_t i = 0; i < REGISTER_SLOTS; ++i) {
        if (register_[i].used() && register_[i].idPrefix == prefix && readRequest(i, r) && !memcmp(r.id, id, HASH)) return static_cast<int>(i);
    }
    return -1;
}

int Store::freeRequestSlot() const {
    for (size_t i = 0; i < REGISTER_SLOTS; ++i) {
        if (register_[i].state == SlotState::FREE || register_[i].state == SlotState::STALE) return static_cast<int>(i);
    }
    return -1;
}

bool Store::requestClosed(size_t slot) const {
    // Wpis zamknięty (oprogramowanie.md, "Cykl życia zgłoszenia"): bez aktywnej intencji i (a) decyzja 6
    // z rewizji r_max po RECEIVED r_max, (b) anulowany, (c) TEST po RECEIVED r_max.
    const RequestIndex& r = register_[slot];
    if (!r.used()) return false;
    if (r.stage == Stage::CANCELLED) return true;
    if (r.stage != Stage::RECEIVED) return false;
    return r.type == sa1::TEST || (r.decision == 6 && r.decisionRev == r.rMax);
}

int Store::closedRequest() const {
    int best = -1;
    for (size_t i = 0; i < REGISTER_SLOTS; ++i) {
        if (requestClosed(i) && (best < 0 || register_[i].changedS < register_[best].changedS)) best = static_cast<int>(i);
    }
    return best;
}

bool Store::numberTaken(uint16_t number, const uint8_t id[HASH]) {
    // Krótki numer innego id w rejestrze albo w pamięci zwolnionych wpisów (przedrostek równy:
    // porównanie pełnego id z rekordu).
    const uint32_t prefix = idPrefix(id);
    for (size_t i = 0; i < REGISTER_SLOTS; ++i) {
        const RequestIndex& r = register_[i];
        if (!r.used() || r.number() != number) continue;
        Request full;
        if (r.idPrefix != prefix || !readRequest(i, full) || memcmp(full.id, id, HASH)) return true;
    }
    for (size_t i = 0; i < RELEASED_ENTRIES; ++i) {
        if (!releasedEv_[i] || (releasedNumber_[i] & 0x3FFF) != number) continue;
        Released r;
        if (releasedPrefix_[i] != prefix || !releasedAt(i, r) || memcmp(r.id, id, HASH)) return true;
    }
    return false;
}

size_t Store::requestCount() const {
    size_t n = 0;
    for (const RequestIndex& r : register_) n += r.used();
    return n;
}

size_t Store::activeIntents() const {
    size_t n = 0;
    for (const RequestIndex& r : register_) n += r.used() && r.stage <= Stage::DELIVERED;
    return n;
}

size_t Store::unsent(uint32_t& oldestS) const {
    size_t n = 0;
    for (const RequestIndex& r : register_) {
        if (!r.used() || r.stage > Stage::SENDING) continue;
        if (!n || r.commitS < oldestS) oldestS = r.commitS;
        ++n;
    }
    return n;
}

bool Store::readMessage(size_t slot, Message& out) {
    if (slot >= INBOX_SLOTS || !inbox_[slot].used()) return false;
    uint8_t body[BODY_MAX];
    size_t length = 0;
    SlotState state;
    uint16_t gen;
    return readSlot(addressOf(INBOX, static_cast<uint16_t>(slot)), INBOX, static_cast<uint16_t>(slot), body, length, state, gen) &&
           state == SlotState::USED && decodeMessage(body, length, out);
}

int Store::findMessage(uint32_t number) const {
    for (size_t i = 0; i < INBOX_SLOTS; ++i) {
        if (inbox_[i].used() && inbox_[i].number == number) return static_cast<int>(i);
    }
    return -1;
}

int Store::freeMessageSlot() const {
    for (size_t i = 0; i < INBOX_SLOTS; ++i) {
        if (inbox_[i].state == SlotState::FREE || inbox_[i].state == SlotState::STALE) return static_cast<int>(i);
    }
    return -1;
}

size_t Store::messageCount() const {
    size_t n = 0;
    for (const MessageIndex& m : inbox_) n += m.used();
    return n;
}

size_t Store::unread() const {
    size_t n = 0;
    for (const MessageIndex& m : inbox_) n += m.used() && !m.read;
    return n;
}

bool Store::releasedAt(size_t index, Released& out) {
    if (index >= RELEASED_ENTRIES || !releasedEv_[index]) return false;
    uint8_t body[BODY_MAX];
    size_t length = 0;
    SlotState state;
    uint16_t gen;
    const uint16_t block = static_cast<uint16_t>(index / BLOCK_ENTRIES);
    if (!readSlot(addressOf(RELEASED, block), RELEASED, block, body, length, state, gen) || state != SlotState::USED) return false;
    decodeReleased(body + EPOCH + (index % BLOCK_ENTRIES) * ENTRY, out);
    return out.ev == releasedEv_[index];
}

bool Store::releasedFind(const uint8_t id[HASH], Released& out) {
    const uint32_t prefix = idPrefix(id);
    for (size_t i = 0; i < RELEASED_ENTRIES; ++i) {
        if (releasedEv_[i] && releasedPrefix_[i] == prefix && releasedAt(i, out) && !memcmp(out.id, id, HASH)) return true;
    }
    return false;
}

bool Store::bulletinSeen(const uint8_t id[HASH], uint32_t event) {
    // Pominięty: e ≤ bulletin_floor, starszy o ponad dobę od najnowszego albo para (id, e) w zbiorze.
    if (event <= meta_.bulletinFloor) return true;
    if (meta_.bulletinMax > BULLETIN_WINDOW && event <= meta_.bulletinMax - BULLETIN_WINDOW) return true;
    const uint32_t prefix = idPrefix(id);
    for (size_t i = 0; i < BULLETIN_ENTRIES; ++i) {
        if (bulletinEvent_[i] != event || bulletinPrefix_[i] != prefix || bulletinSource_[i] != meta_.receiver) continue;
        uint8_t body[BODY_MAX];
        if (!readBlock(BULLETIN, static_cast<uint16_t>(i / BLOCK_ENTRIES), body)) return true;   // błąd odczytu: bez przyjęcia
        if (!memcmp(body + (i % BLOCK_ENTRIES) * ENTRY, id, HASH)) return true;
    }
    return false;
}

bool Store::readEvent(uint32_t ev, Event& out) {
    if (ev == 0 || ev > head_ || ev < minEvent()) return false;
    const uint16_t block = static_cast<uint16_t>(((ev - 1) % RING_ENTRIES) / BLOCK_ENTRIES);
    if (ringState_[block] != SlotState::USED) return false;
    uint8_t body[BODY_MAX];
    if (!readBlock(RING, block, body)) return false;
    decodeEvent(body + EPOCH + ((ev - 1) % BLOCK_ENTRIES) * ENTRY, out);
    return out.ev == ev;
}

bool Store::quietSince(uint32_t head) {
    // Zdarzenia po head bez zmiany danych: postęp wysyłki (`sending`, `delivered` bez nowej decyzji),
    // `radio` i `station` nie blokują ZAMKNIJ ZDARZENIE.
    if (head > head_) return false;
    if (head < head_ && head + 1 < minEvent()) return false;
    for (uint32_t ev = head + 1; ev <= head_ && ev; ++ev) {
        Event e;
        if (!readEvent(ev, e)) return false;
        if (e.kind == EventKind::OWN || e.kind == EventKind::MSG) return false;
        if (e.kind == EventKind::STAGE) {
            const StageCode code = static_cast<StageCode>(e.a);
            if (e.decisionChanged || (code != StageCode::SENDING && code != StageCode::DELIVERED)) return false;
        }
    }
    return true;
}

Event Store::radioEvent(const Meta& m, bool switchOn) {
    Event e;
    e.kind = EventKind::RADIO;
    e.a = radioBits(m, switchOn);
    if (!(e.a & RADIO_EXCEPTION)) return e;
    const int slot = findRequest(m.exception);
    e.slot = slot >= 0 ? static_cast<uint16_t>(slot) : 0xFFFF;
    e.gen = slot >= 0 ? register_[slot].gen : 0;
    e.revision = m.exceptionRev;
    e.value = shortNumber(m.exception);
    return e;
}

bool Store::exceptionId(const Event& e, uint8_t id[HASH]) {
    if (e.kind != EventKind::RADIO || !(e.a & RADIO_EXCEPTION)) return false;
    Request r;
    if (e.slot < REGISTER_SLOTS && register_[e.slot].used() && register_[e.slot].gen == e.gen && readRequest(e.slot, r)) {
        memcpy(id, r.id, HASH);
        return true;
    }
    for (size_t i = 0; i < RELEASED_ENTRIES; ++i) {
        Released rel;
        if (!releasedEv_[i] || (releasedNumber_[i] & 0x3FFF) != e.value || !releasedAt(i, rel) || rel.revision < e.revision) continue;
        memcpy(id, rel.id, HASH);
        return true;
    }
    return false;
}

bool Store::close(uint32_t head) {
    // Nowa epoka i para (stara epoka, head z polecenia) do powtórzenia `close` w jednej transakcji;
    // zdarzenia nieblokujące po head nie zmieniają pary, którą laptop ponowi.
    Tx tx(*this);
    Meta& m = tx.meta();
    m.closedSet = true;
    memcpy(m.closedEpoch, meta_.epoch, EPOCH);
    m.closedHead = head;
    random_(m.epoch, EPOCH);
    random_(m.dataEpoch, EPOCH);
    m.ringBase = 0;
    m.tombFloor = 1;
    return tx.commit();
}

bool Store::recoverBlocks() {
    // Uszkodzone bloki małych wpisów (oprogramowanie.md, "Pamięć FRAM"): ich wpisy przepadły, więc
    // stacja nie udaje pełnej wiedzy, a maintain() zapisuje bloki od nowa.
    // - pierścień (protokol-usb.md, "Epoka"): numery z bloku laptop mógł już widzieć; nowa epoka wymusza
    //   migawkę, a numeracja biegnie dalej za najwyższym numerem, jaki mógł zostać nadany, bo numery
    //   zdarzeń wskazują też wiadomości skrzynki (`msg`) i pamięć zwolnionych wpisów (kolejność po `ev`).
    //   Zdarzenia po najwyższym zachowanym numerze leżą w kolejnych blokach za jego blokiem i każdy
    //   z nich jest uszkodzony (zachowany miałby wyższy numer), więc górna granica to zachowany head
    //   + 16 × liczba uszkodzonych bloków (numery skrzynki i pamięci zwolnionych to tylko kontrola);
    // - pamięć zwolnionych: `tomb_floor` za bieżący numer (pamięć niekompletna, laptop nie ponawia);
    // - zbiór BULLETIN: `bulletin_floor` = najwyższy przyjęty `event` (stare komunikaty nie wrócą).
    Tx tx(*this);
    Meta& m = tx.meta();
    uint32_t head = head_;
    if (corruptBlocks_ & 1) {
        uint32_t corrupt = 0;
        for (SlotState s : ringState_) corrupt += s == SlotState::CORRUPT;
        head += corrupt * BLOCK_ENTRIES;
        for (const MessageIndex& x : inbox_) if (x.used() && x.number > head) head = x.number;
        for (uint32_t ev : releasedEv_) if (ev > head) head = ev;
        random_(m.epoch, EPOCH);
        m.ringBase = head;
    }
    if (corruptBlocks_ & 2) m.tombFloor = head + 1;
    if (corruptBlocks_ & 4) m.bulletinFloor = m.bulletinMax;
    if (!tx.commit()) return false;
    corruptBlocks_ = 0;
    return true;
}

bool Store::maintain() {
    // Do trzech gniazd starej epoki w jednej transakcji: rejestr, skrzynka, bloki pamięci zwolnionych
    // i pierścienia. Gniazda STALE są już wolne do użycia; tu znika ich treść.
    if (!ok_) return false;
    Tx tx(*this);
    size_t n = 0;
    for (uint16_t i = 0; i < REGISTER_SLOTS && n < Tx::MAX_CHANGES; ++i) if (register_[i].state == SlotState::STALE) { tx.free(REGISTER, i); ++n; }
    for (uint16_t i = 0; i < INBOX_SLOTS && n < Tx::MAX_CHANGES; ++i) if (inbox_[i].state == SlotState::STALE) { tx.free(INBOX, i); ++n; }
    // Bloki starej epoki i bloki uszkodzone (po recoverBlocks(); inaczej każdy start odtwarzałby je od nowa).
    const auto blocks = [&](Kind kind, const SlotState* states, uint16_t count, bool stale) {
        for (uint16_t i = 0; i < count && n < Tx::MAX_CHANGES; ++i) {
            if ((stale && states[i] == SlotState::STALE) || states[i] == SlotState::CORRUPT) { tx.free(kind, i); ++n; }
        }
    };
    blocks(RELEASED, releasedState_, RELEASED_BLOCKS, true);
    blocks(RING, ringState_, RING_BLOCKS, true);
    blocks(BULLETIN, bulletinState_, BULLETIN_BLOCKS, false);
    if (!n) return false;
    if (!tx.commit()) return false;
    diag_.scrubbed += static_cast<uint32_t>(n);
    return true;
}

bool Store::destroy() {
    // Znacznik w dzienniku najpierw: przerwane kasowanie wznawia begin().
    const uint32_t flags = journal_.formatFlags() & ~journal::FORMAT_IDENTITY;
    if (!journal_.writeFormat(journal::FormatState::DESTROYING, flags)) return false;
    uint8_t zero[CHUNK] = {};
    for (uint32_t address = TX_BASE; address < FRAM_END; address += CHUNK) {
        if (!memory_.write(address, zero, CHUNK)) return false;
    }
    if (!journal_.erase()) return false;
    selected_ = 0;
    nextWrite_ = reservedUpper_ = journal_.reservation();
    txArea_ = 0;
    if (!format(flags)) { ok_ = false; return false; }
    return begin() == Begin::OK;
}

bool Store::identitySaved() const { return journal_.formatFlags() & journal::FORMAT_IDENTITY; }

bool Store::setIdentitySaved() {
    return identitySaved() || journal_.writeFormat(journal::FormatState::READY, journal_.formatFlags() | journal::FORMAT_IDENTITY);
}

}  // namespace store
