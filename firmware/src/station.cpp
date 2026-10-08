// SPDX-License-Identifier: MIT
#include "station.h"

#include <stdio.h>
#include <string.h>

#include "hexstr.h"
#include "jsonlite.h"

namespace station {

using store::Request;
using store::RequestIndex;
using store::Stage;
using store::StageCode;

namespace {

void addRevision(Request& r, uint16_t revision, uint32_t commitS) {
    // Pełna lista: wypada druga najstarsza (najstarsza wyznacza alarm).
    if (r.revisionCount == store::REVISION_TIMES) {
        memmove(&r.revisions[1], &r.revisions[2], (store::REVISION_TIMES - 2) * sizeof(r.revisions[0]));
        --r.revisionCount;
    }
    r.revisions[r.revisionCount].revision = revision;
    r.revisions[r.revisionCount].commitS = commitS;
    ++r.revisionCount;
}

// Potwierdzenie rewizji (RECEIVED albo przyjęty STATUS/REPLY): r_rcv rośnie, starsze czasy COMMIT
// odpadają. true, gdy r_max dostał potwierdzenie po raz pierwszy.
bool confirm(Request& r, uint16_t revision, uint32_t nowS) {
    if (static_cast<int32_t>(revision) > r.rRcv) r.rRcv = revision;
    uint8_t kept = 0;
    for (uint8_t i = 0; i < r.revisionCount; ++i) {
        if (static_cast<int32_t>(r.revisions[i].revision) > r.rRcv) r.revisions[kept++] = r.revisions[i];
    }
    r.revisionCount = kept;
    if (revision != r.rMax || r.stage == Stage::RECEIVED) return false;
    r.stage = Stage::RECEIVED;
    r.receivedS = nowS;
    return true;
}

bool backupFlag(const Request& r) { return (r.flags & store::BACKUP) != 0; }

}  // namespace

const char* resultName(Result result) {
    switch (result) {
        case Result::STORED:
        case Result::DUPLICATE: return "ok";
        case Result::NO_CONFIG:
        case Result::NO_ADDRESS: return "not_configured";
        case Result::FULL: return "full";
        case Result::NUMBER_TAKEN: return "numer_zajety";
        case Result::CONFLICT: return "conflict";
        case Result::STALE: return "stale";
        case Result::CLOSED: return "closed";
        case Result::TOO_LATE: return "too_late";
        case Result::MEMORY: return "memory";
        case Result::INVALID:
        case Result::NOT_FOUND: break;
    }
    return "invalid";
}

Station::Station(store::Store& store, Services& services) : store_(store), services_(services) {}

uint32_t Station::random32() {
    uint32_t value = 0;
    services_.randomBytes(reinterpret_cast<uint8_t*>(&value), sizeof(value));
    return value;
}

uint32_t Station::retryDelayS(uint16_t attempts, bool delivered, uint32_t ageS, uint32_t random) {
    if (delivered) return RESEND_MIN_S + random % (RESEND_MAX_S - RESEND_MIN_S + 1);
    const uint32_t jitter = 80 + random % 41;   // ±20%: współczynnik 0,8..1,2
    if (ageS >= FAILED_LATE_S) return FAILED_LATE_INTERVAL_S * jitter / 100;
    static const uint32_t steps[] = {60, 120, 300, 900};   // po 1., 2., 3. i dalszych nieudanych próbach
    const uint16_t index = attempts ? static_cast<uint16_t>(attempts - 1) : 0;
    return steps[index < 4 ? index : 3] * jitter / 100;
}

size_t Station::inFlight() const {
    size_t n = 0;
    for (const Flight& f : flights_) n += f.slot >= 0;
    return n;
}

void Station::stageEvent(store::Tx& tx, uint16_t slot, uint16_t gen, const Request& r, StageCode code, bool decisionChanged) {
    store::Event e;
    e.kind = store::EventKind::STAGE;
    e.a = static_cast<uint8_t>(code);
    e.decisionChanged = decisionChanged;
    e.slot = slot;
    e.gen = gen;
    e.revision = r.rMax;
    e.decision = r.decision;
    e.attempt = r.attempts > 255 ? 255 : static_cast<uint8_t>(r.attempts);
    e.decisionRev = r.decisionRev;
    e.value = r.statusHi;
    tx.event(e);
}

void Station::markCancelled(store::Tx& tx, uint16_t slot, Request& r) {
    r.stage = Stage::CANCELLED;
    r.changedS = store_.now();
    tx.request(slot, r, false);
    stageEvent(tx, slot, store_.request(slot).gen, r, StageCode::CANCELLED, false);
}

void Station::touchContact(store::Tx& tx) {
    store::Meta& m = tx.meta();
    m.contactS = store_.now();
    m.contactKnown = true;
}

// --- Wysyłka ---------------------------------------------------------------------------------

const RequestIndex* Station::exceptionEntry() const {
    const store::Meta& m = store_.meta();
    if (store::silenceMode(m, services_.silenceSwitch()) != store::Silence::EXCEPTION) return nullptr;
    const bool cached = exceptionSlot_ >= 0 && !memcmp(exceptionId_, m.exception, store::HASH) &&
                        store_.request(static_cast<size_t>(exceptionSlot_)).used() && store_.request(static_cast<size_t>(exceptionSlot_)).gen == exceptionGen_;
    if (!cached) {
        memcpy(exceptionId_, m.exception, store::HASH);
        exceptionSlot_ = store_.findRequest(m.exception);
        if (exceptionSlot_ >= 0) exceptionGen_ = store_.request(static_cast<size_t>(exceptionSlot_)).gen;
    }
    return exceptionSlot_ >= 0 ? &store_.request(static_cast<size_t>(exceptionSlot_)) : nullptr;
}

bool Station::silencedFor(const RequestIndex& r) const {
    // Cisza radiowa wstrzymuje wysyłkę; wyjątek z panelu obejmuje tylko parę (id, revision) z chwili
    // ustawienia: nowa rewizja tego zgłoszenia czeka jak każda inna wiadomość.
    if (!services_.silence()) return false;
    return exceptionEntry() != &r || r.rMax != store_.meta().exceptionRev;
}

bool Station::due(const RequestIndex& r) const {
    if (!r.used() || r.stage > Stage::DELIVERED) return false;
    if (r.type == sa1::TEST && testPaused()) return false;
    // Po KLUCZ ZAPASOWY niepotwierdzone rewizje idą od razu do tożsamości zapasowej.
    const bool retarget = ((r.flags & store::BACKUP) != 0) != (store_.meta().receiver == config::BACKUP) && (r.flags & store::SENT_ONCE);
    return (retarget || static_cast<int32_t>(store_.now() - r.nextTryS) >= 0) && !silencedFor(r);
}

int Station::nextToSend() const {
    // REQUEST z pilnością 2, potem pozostałe REQUEST według COMMIT, na końcu TEST.
    int best = -1, bestRank = 0;
    for (size_t i = 0; i < store::REGISTER_SLOTS; ++i) {
        const RequestIndex& r = store_.request(i);
        if (!due(r)) continue;
        bool flying = false;
        for (const Flight& f : flights_) flying |= f.slot == static_cast<int>(i);
        if (flying) continue;
        const int rank = r.type == sa1::TEST ? 2 : r.urgency == 2 ? 0 : 1;
        if (best < 0 || rank < bestRank || (rank == bestRank && r.commitS < store_.request(best).commitS)) {
            best = static_cast<int>(i);
            bestRank = rank;
        }
    }
    return best;
}

bool Station::transmit(uint16_t slot) {
    Request r;
    const uint8_t* to = store_.recipient();
    if (!to || !store_.readRequest(slot, r)) return false;
    uint8_t self[store::HASH];
    char from[2 * store::HASH + 1], target[2 * store::HASH + 1], packet[PACKET_MAX + 1];
    services_.address(self);
    hexstr::encode(self, store::HASH, from);
    hexstr::encode(to, store::HASH, target);
    const int n = snprintf(packet, sizeof(packet), "[\"WICI\",1,\"%s\",\"%s\",%s]", from, target, r.sa1);
    if (n <= 0 || static_cast<size_t>(n) > PACKET_MAX) return false;   // SA1 ≤256 B: nie zdarza się
    // `nadane` i etap zatwierdzone przed przekazaniem do stosu; po restarcie w trakcie próba wraca po 60 s.
    const uint32_t nowS = store_.now();
    const bool backup = store_.meta().receiver == config::BACKUP;
    const bool retarget = backupFlag(r) != backup;
    StageCode code = StageCode::SENDING;
    const bool stageChange = r.stage == Stage::SAVED || (retarget && r.stage == Stage::DELIVERED);
    r.flags = static_cast<uint8_t>((r.flags | store::SENT_ONCE) & ~store::BACKUP) | (backup ? store::BACKUP : 0);
    if (retarget) r.statusHi = r.replyHi = 0;   // liczniki należą do aktywnej tożsamości odbiorcy
    if (stageChange) r.stage = Stage::SENDING;
    r.attempts = static_cast<uint16_t>(r.attempts + 1);
    if (!r.firstSentS) r.firstSentS = nowS;
    r.nextTryS = nowS + ACK_TIMEOUT_S;
    r.changedS = nowS;
    store::Tx tx(store_);
    tx.request(slot, r, false);
    const uint16_t gen = store_.request(slot).gen;
    if (stageChange) stageEvent(tx, slot, gen, r, code, false);
    if (!tx.commit()) { services_.log("send: store write failed"); return false; }
    const uint32_t handle = services_.send(to, reinterpret_cast<const uint8_t*>(packet), static_cast<size_t>(n), ACK_TIMEOUT_S);
    if (!handle) {
        // Stos odmówił (cel bez trasy, pełna kolejka, brak IFAC): próba nieudana.
        ++stats_.failed;
        r.nextTryS = nowS + retryDelayS(r.attempts, false, nowS - r.firstSentS, random32());
        store::Tx retry(store_);
        retry.request(slot, r, false);
        retry.commit();
        services_.changed();
        return false;
    }
    ++stats_.sent;
    for (Flight& f : flights_) {
        if (f.slot >= 0) continue;
        f.slot = static_cast<int16_t>(slot);
        f.gen = gen;
        f.revision = r.rMax;
        f.handle = handle;
        f.sentS = nowS;
        break;
    }
    services_.changed();
    return true;
}

void Station::finishFlight(Flight& f, bool delivered) {
    const Flight done = f;
    const uint16_t slot = static_cast<uint16_t>(f.slot);
    f = Flight();
    Request r;
    // Wynik próby rewizji już zastąpionej, wpisu zwolnionego albo potwierdzonego: bez skutku.
    if (!store_.readRequest(slot, r) || r.gen != done.gen || r.rMax != done.revision || r.stage > Stage::DELIVERED) return;
    const uint32_t nowS = store_.now();
    store::Tx tx(store_);
    if (delivered) {
        ++stats_.delivered;
        // DELIVERED: 10 min na RECEIVED, potem ponowienia co 30–60 min.
        const bool first = r.stage == Stage::SENDING;
        r.nextTryS = nowS + (first ? RECEIVED_WAIT_S : retryDelayS(r.attempts, true, 0, random32()));
        if (first) {
            r.stage = Stage::DELIVERED;
            stageEvent(tx, slot, r.gen, r, StageCode::DELIVERED, false);
        }
    } else {
        ++stats_.failed;
        r.nextTryS = nowS + retryDelayS(r.attempts, false, nowS - r.firstSentS, random32());
    }
    r.changedS = nowS;
    tx.request(slot, r, false);
    if (!tx.commit()) services_.log("receipt: store write failed");
    services_.changed();
}

void Station::receipt(uint32_t handle, bool delivered) {
    for (Flight& f : flights_) {
        if (f.slot >= 0 && handle && f.handle == handle) { finishFlight(f, delivered); return; }
    }
}

void Station::poll() {
    if (!store_.ok()) return;
    // Stos nie podał wyniku potwierdzenia (restart stosu, utracony uchwyt): próba nieudana.
    for (Flight& f : flights_) {
        if (f.slot >= 0 && store_.now() - f.sentS >= RECEIPT_GUARD_S) finishFlight(f, false);
    }
    if (!services_.radioReady() || services_.busy()) return;
    while (inFlight() < IN_FLIGHT) {
        const int slot = nextToSend();
        if (slot < 0 || !transmit(static_cast<uint16_t>(slot))) break;
    }
}

// --- Czynności lokalne -----------------------------------------------------------------------

bool Station::releaseOne() {
    // Osobna transakcja przed nowym wpisem: gniazdo wolne, (id, r_max) do pamięci zwolnionych, `released`.
    const int slot = store_.closedRequest();
    Request r;
    if (slot < 0 || !store_.readRequest(static_cast<size_t>(slot), r)) return false;
    store::Released released;
    memcpy(released.id, r.id, store::HASH);
    released.revision = r.rMax;
    released.number = store::shortNumber(r.id);
    released.cancelled = r.stage == Stage::CANCELLED;
    store::Tx tx(store_);
    tx.free(store::REGISTER, static_cast<uint16_t>(slot));
    store::Event e;
    e.kind = store::EventKind::STAGE;
    e.a = static_cast<uint8_t>(StageCode::RELEASED);
    e.slot = static_cast<uint16_t>(store_.releasedNext());
    e.revision = r.rMax;
    released.ev = tx.event(e);
    tx.released(released);
    return tx.commit();
}

Result Station::save(Request& r, int slot, uint8_t origin, uint16_t& gen, const uint8_t* nonce) {
    const bool fresh = slot < 0;
    if (fresh) {
        slot = store_.freeRequestSlot();
        if (slot < 0) {
            if (!releaseOne()) return store_.ok() ? Result::FULL : Result::MEMORY;
            slot = store_.freeRequestSlot();
            if (slot < 0) return Result::MEMORY;
        }
    }
    store::Tx tx(store_);
    tx.request(static_cast<uint16_t>(slot), r, fresh);
    gen = tx.gen(store::REGISTER, static_cast<uint16_t>(slot));
    store::Event e;
    e.kind = store::EventKind::OWN;
    e.a = origin;
    e.slot = static_cast<uint16_t>(slot);
    e.gen = gen;
    e.revision = r.rMax;
    tx.event(e);
    if (nonce) {
        store::Meta& m = tx.meta();
        memcpy(m.nonces[m.nonceNext].nonce, nonce, store::NONCE);
        memcpy(m.nonces[m.nonceNext].id, r.id, store::HASH);
        m.nonceNext = static_cast<uint8_t>((m.nonceNext + 1) % store::TEST_NONCES);
    }
    if (!tx.commit()) return Result::MEMORY;
    services_.changed();
    return Result::STORED;
}

Result Station::createWith(uint8_t type, uint8_t category, uint16_t people, uint8_t urgency, const char* location, const char* text,
                           uint32_t delayS, uint8_t origin, const uint8_t* nonce, uint8_t id[store::HASH], uint16_t& number) {
    if (!store_.station()) return Result::NO_CONFIG;
    if (!location[0]) return Result::NO_ADDRESS;
    sa1::Message m;
    m.type = type;
    m.category = category;
    m.people = people;
    m.urgency = urgency;
    strncpy(m.location, location, sa1::LOCATION_MAX);
    strncpy(m.text, text ? text : "", sa1::TEXT_MAX);
    // Krótki numer unikalny w stacji: id losowane ponownie, dopóki numer jest zajęty.
    for (int attempt = 0; attempt < 32; ++attempt) {
        services_.randomBytes(id, store::HASH);
        if (!store_.numberTaken(store::shortNumber(id), id)) break;
    }
    hexstr::encode(id, store::HASH, m.id);
    Request r;
    r.sa1Length = static_cast<uint16_t>(sa1::encode(m, r.sa1, sizeof(r.sa1)));
    if (!r.sa1Length) return Result::INVALID;
    const uint32_t nowS = store_.now();
    r.type = type;
    r.origin = origin;
    memcpy(r.id, id, store::HASH);
    r.urgency = urgency;
    r.category = category;
    r.people = people;
    r.createdS = r.changedS = nowS;
    r.nextTryS = nowS + delayS;
    addRevision(r, 0, nowS);
    if (nonce) memcpy(r.nonce, nonce, store::NONCE);
    uint16_t gen = 0;
    const Result result = save(r, -1, origin, gen, nonce);
    if (result == Result::STORED) {
        number = store::shortNumber(id);
        char line[48];
        snprintf(line, sizeof(line), "%s %04u created", type == sa1::TEST ? "test" : "request", number);
        services_.log(line);
    }
    return result;
}

Result Station::create(uint8_t category, uint16_t people, uint8_t urgency, const char* text, uint16_t& number) {
    uint8_t id[store::HASH];
    return createWith(sa1::REQUEST, category, people, urgency, store_.address(), text, 0, store::BUTTONS, nullptr, id, number);
}

Result Station::revise(uint16_t slot, uint16_t people, uint8_t urgency, const char* text) {
    Request r;
    sa1::Message m;
    if (!store_.readRequest(slot, r) || r.type != sa1::REQUEST || sa1::decode(r.sa1, r.sa1Length, m)) return Result::NOT_FOUND;
    if (r.stage == Stage::CANCELLED) return Result::CLOSED;
    if (r.rMax >= sa1::REVISION_MAX) return Result::INVALID;
    m.revision = static_cast<uint16_t>(r.rMax + 1);
    m.people = people;
    m.urgency = urgency;
    if (text) { strncpy(m.text, text, sa1::TEXT_MAX); m.text[sa1::TEXT_MAX] = '\0'; }   // rewizja zachowuje lokalizację
    char wire[sa1::MAX_CONTENT + 1];
    const size_t length = sa1::encode(m, wire, sizeof(wire));
    if (!length) return Result::INVALID;
    return revision(slot, r, m, wire, length, store::BUTTONS);
}

Result Station::revision(uint16_t slot, Request& r, const sa1::Message& m, const char* wire, size_t length, uint8_t origin) {
    // Nowa rewizja: etap `zapisane`, intencja poprzedniej kończy się (nadawana: po bieżącej próbie),
    // decyzja zostaje i jest pokazywana pod etapem nowej rewizji.
    const uint32_t nowS = store_.now();
    const bool superseded = r.stage <= Stage::DELIVERED;
    const Request old = r;
    r.rMax = m.revision;
    r.stage = Stage::SAVED;
    r.flags = static_cast<uint8_t>(r.flags & ~store::READ_MAX);
    r.urgency = m.urgency;
    r.category = m.category;
    r.people = m.people;
    r.attempts = 0;
    r.firstSentS = 0;
    r.nextTryS = nowS;
    r.changedS = nowS;
    r.origin = origin;
    addRevision(r, m.revision, nowS);
    memcpy(r.sa1, wire, length + 1);
    r.sa1Length = static_cast<uint16_t>(length);
    store::Tx tx(store_);
    tx.request(slot, r, false);
    const uint16_t gen = store_.request(slot).gen;
    store::Event e;
    e.kind = store::EventKind::OWN;
    e.a = origin;
    e.slot = slot;
    e.gen = gen;
    e.revision = r.rMax;
    if (superseded) stageEvent(tx, slot, gen, old, StageCode::SUPERSEDED, false);
    tx.event(e);
    if (!tx.commit()) return Result::MEMORY;
    char line[48];
    snprintf(line, sizeof(line), "request %04u revision %u", store::shortNumber(r.id), r.rMax);
    services_.log(line);
    services_.changed();
    return Result::STORED;
}

Result Station::submit(const sa1::Message& m, Stored& out) {
    // Reguły `submit` (protokol-usb.md): nowe id, nowa rewizja, duplikat albo konflikt, stale, closed,
    // id zwolnione (bez kontroli treści).
    if (!store_.station()) return Result::NO_CONFIG;
    if (m.type != sa1::REQUEST && m.type != sa1::TEST) return Result::INVALID;
    if (!hexstr::decode(m.id, out.id, store::HASH)) return Result::INVALID;
    out.revision = m.revision;
    out.number = store::shortNumber(out.id);
    char wire[sa1::MAX_CONTENT + 1];
    const size_t length = sa1::encode(m, wire, sizeof(wire));
    if (!length) return Result::INVALID;
    const int slot = store_.findRequest(out.id);
    if (slot >= 0) {
        Request r;
        if (!store_.readRequest(static_cast<size_t>(slot), r)) return Result::MEMORY;
        if (r.stage == Stage::CANCELLED) return Result::CLOSED;
        if (m.revision < r.rMax) return Result::STALE;
        if (m.revision == r.rMax) {
            out.duplicate = length == r.sa1Length && !memcmp(wire, r.sa1, length);
            return out.duplicate ? Result::DUPLICATE : Result::CONFLICT;
        }
        if (m.type != r.type) return Result::CONFLICT;
        return revision(static_cast<uint16_t>(slot), r, m, wire, length, store::USB);
    }
    store::Released released;
    if (store_.releasedFind(out.id, released)) {
        if (m.revision < released.revision) return Result::STALE;
        if (m.revision > released.revision) return Result::CLOSED;
        out.duplicate = out.released = true;
        return Result::DUPLICATE;
    }
    if (store_.numberTaken(out.number, out.id)) return Result::NUMBER_TAKEN;
    const uint32_t nowS = store_.now();
    Request r;
    r.type = m.type;
    r.origin = store::USB;
    memcpy(r.id, out.id, store::HASH);
    r.rMax = m.revision;
    r.urgency = m.urgency;
    r.category = m.category;
    r.people = m.people;
    r.createdS = r.changedS = r.nextTryS = nowS;
    addRevision(r, m.revision, nowS);
    memcpy(r.sa1, wire, length + 1);
    r.sa1Length = static_cast<uint16_t>(length);
    uint16_t gen = 0;
    return save(r, -1, store::USB, gen, nullptr);
}

Result Station::cancel(const uint8_t id[store::HASH], bool& released) {
    released = false;
    const int slot = store_.findRequest(id);
    if (slot < 0) {
        store::Released r;
        if (!store_.releasedFind(id, r)) return Result::NOT_FOUND;
        if (!r.cancelled) return Result::TOO_LATE;
        released = true;
        return Result::STORED;
    }
    Request r;
    if (!store_.readRequest(static_cast<size_t>(slot), r)) return Result::MEMORY;
    if (r.stage == Stage::CANCELLED) return Result::STORED;
    // Po pierwszym przekazaniu do stosu odbiorca mógł zgłoszenie dostać: tylko POTRZEBA USTAŁA.
    if (r.flags & store::SENT_ONCE) return Result::TOO_LATE;
    store::Tx tx(store_);
    markCancelled(tx, static_cast<uint16_t>(slot), r);
    if (!tx.commit()) return Result::MEMORY;
    char line[40];
    snprintf(line, sizeof(line), "%s %04u cancelled", r.type == sa1::TEST ? "test" : "request", store::shortNumber(r.id));
    services_.log(line);
    services_.changed();
    return Result::STORED;
}

int Station::pendingTest() const {
    for (size_t i = 0; i < store::REGISTER_SLOTS; ++i) {
        const RequestIndex& r = store_.request(i);
        if (r.used() && r.type == sa1::TEST && r.stage == Stage::SAVED && !(r.flags & store::SENT_ONCE)) return static_cast<int>(i);
    }
    return -1;
}

int Station::latestTest() const {
    int best = -1;
    for (size_t i = 0; i < store::REGISTER_SLOTS; ++i) {
        const RequestIndex& r = store_.request(i);
        if (r.used() && r.type == sa1::TEST && r.stage != Stage::CANCELLED && (best < 0 || r.commitS >= store_.request(best).commitS)) {
            best = static_cast<int>(i);
        }
    }
    return best;
}

Result Station::scheduleTest(bool startup) {
    if (pendingTest() >= 0) return Result::STORED;
    if (testPaused()) return Result::INVALID;
    uint32_t delayS = 0;
    if (startup) {
        const uint16_t stations = store_.config().stations;
        delayS = random32() % (stations ? TEST_WINDOW_PER_STATION_S * stations : TEST_WINDOW_S);
    }
    uint8_t id[store::HASH];
    uint16_t number = 0;
    return createWith(sa1::TEST, 9, 1, 0, store_.address(), "test", delayS, store::BUTTONS, nullptr, id, number);
}

Result Station::test(const uint8_t nonce[store::NONCE], Stored& out) {
    // Powtórzone `nonce`: ten sam wynik z wpisu albo z pamięci zwolnionych.
    static const uint8_t none[store::HASH] = {};
    for (const store::TestNonce& t : store_.meta().nonces) {
        if (!memcmp(t.id, none, store::HASH) || memcmp(t.nonce, nonce, store::NONCE)) continue;   // wolny wpis ma zera
        memcpy(out.id, t.id, store::HASH);
        out.number = store::shortNumber(t.id);
        store::Released released;
        out.released = store_.findRequest(t.id) < 0 && store_.releasedFind(t.id, released);
        return Result::STORED;
    }
    out = Stored();
    return createWith(sa1::TEST, 9, 1, 0, store_.address(), "test", 0, store::USB, nonce, out.id, out.number);
}

bool Station::cancelTest() {
    const int slot = pendingTest();
    Request r;
    bool released = false;
    return slot >= 0 && store_.readRequest(static_cast<size_t>(slot), r) && cancel(r.id, released) == Result::STORED;
}

bool Station::pauseTest(bool paused) {
    if (paused == testPaused()) return true;
    // WSTRZYMAJ anuluje TEST czekający na nadanie; obie zmiany w jednej transakcji.
    store::Tx tx(store_);
    tx.meta().testPaused = paused;
    const int slot = paused ? pendingTest() : -1;
    Request r;
    if (slot >= 0 && store_.readRequest(static_cast<size_t>(slot), r)) markCancelled(tx, static_cast<uint16_t>(slot), r);
    if (!tx.commit()) return false;
    services_.log(paused ? "test paused" : "test resumed");
    services_.changed();
    return true;
}

bool Station::switchBackup() {
    // KLUCZ ZAPASOWY: wiadomości tylko od tożsamości zapasowej, liczniki i zbiór powtórzeń od zera,
    // niepotwierdzone rewizje od razu do niej (due()).
    if (!store_.station() || store_.meta().receiver == config::BACKUP) return false;
    store::Tx tx(store_);
    store::Meta& m = tx.meta();
    m.receiver = config::BACKUP;
    m.bulletinFloor = m.bulletinMax = 0;
    m.contactKnown = false;
    store::Event e;
    e.kind = store::EventKind::STATION;
    e.a = store::RECEIVER_BACKUP;
    tx.event(e);
    if (!tx.commit()) return false;
    services_.log("switched to backup receiver");
    services_.changed();
    return true;
}

bool Station::markRead(uint32_t number) {
    const int slot = store_.findMessage(number);
    store::Message m;
    if (slot < 0 || !store_.readMessage(static_cast<size_t>(slot), m)) return false;
    if (m.read) return true;
    m.read = true;
    store::Tx tx(store_);
    tx.message(static_cast<uint16_t>(slot), m, false);
    if (!tx.commit()) return false;
    services_.changed();
    return true;
}

bool Station::note(const store::Event& e) {
    store::Tx tx(store_);
    tx.event(e);
    return tx.commit();
}

bool Station::radioEvent(bool switchOn) { return note(store_.radioEvent(store_.meta(), switchOn)); }

bool Station::stationEvent(store::StationWhat what, uint32_t detail) {
    store::Event e;
    e.kind = store::EventKind::STATION;
    e.a = what;
    e.value = detail;
    return note(e);
}

bool Station::setSilence(bool on, const uint8_t* exception, bool switchOn) {
    store::Tx tx(store_);
    store::Meta& m = tx.meta();
    m.silence = on;
    m.exceptionSet = on && exception;
    memset(m.exception, 0, store::HASH);
    m.exceptionRev = 0;
    if (m.exceptionSet) {
        memcpy(m.exception, exception, store::HASH);
        const int slot = store_.findRequest(exception);
        if (slot >= 0) m.exceptionRev = store_.request(static_cast<size_t>(slot)).rMax;
    }
    tx.event(store_.radioEvent(m, switchOn));
    if (!tx.commit()) return false;
    services_.changed();
    return true;
}

// --- Wiadomości przychodzące -----------------------------------------------------------------

bool Station::received(const uint8_t* data, size_t length) {
    exceptionTraffic_ = false;
    if (length > PACKET_MAX) { ++stats_.rejected; return true; }
    char copy[PACKET_MAX + 1];
    memcpy(copy, data, length);
    copy[length] = '\0';
    json::Value array, v, payload;
    char marker[8], fromHex[2 * store::HASH + 2], toHex[2 * store::HASH + 2];
    uint8_t from[store::HASH], to[store::HASH], self[store::HASH];
    int64_t version = 0;
    if (!json::parse(copy, array) || array.kind != json::Kind::ARRAY || json::count(array) != 5 || !json::item(array, 0, v) ||
        !json::string(v, marker, sizeof(marker)) || strcmp(marker, "WICI") || !json::item(array, 1, v) || !json::integer(v, version) ||
        version != 1 || !json::item(array, 2, v) || !json::string(v, fromHex, sizeof(fromHex)) || !hexstr::decode(fromHex, from, store::HASH) ||
        !json::item(array, 3, v) || !json::string(v, toHex, sizeof(toHex)) || !hexstr::decode(toHex, to, store::HASH) ||
        !json::item(array, 4, payload) || payload.kind != json::Kind::ARRAY || payload.length > sa1::MAX_CONTENT) {
        ++stats_.rejected;
        return true;
    }
    services_.address(self);
    const uint8_t* recipient = store_.recipient();
    // Tylko od aktywnej tożsamości odbiorcy i tylko do tej stacji (trwałe odrzucenie: z dowodem).
    if (memcmp(to, self, store::HASH) || !recipient || memcmp(from, recipient, store::HASH)) {
        ++stats_.rejected;
        services_.log("message from inactive or unknown receiver");
        return true;
    }
    sa1::Message m;
    char wire[sa1::MAX_CONTENT + 1];
    size_t wireLength = 0;
    if (sa1::decode(payload.begin, payload.length, m) || m.type < sa1::RECEIVED || m.type > sa1::BULLETIN ||
        !(wireLength = sa1::encode(m, wire, sizeof(wire)))) {
        ++stats_.rejected;
        return true;
    }
    ++stats_.received;
    uint8_t id[store::HASH];
    hexstr::decode(m.id, id, store::HASH);
    const store::Meta& meta = store_.meta();
    // Dowód wychodzi w ciszy z wyjątkiem tylko dla RECEIVED i STATUS tej pary (id, revision).
    exceptionTraffic_ = (m.type == sa1::RECEIVED || m.type == sa1::STATUS) && store::silenceMode(meta, services_.silenceSwitch()) == store::Silence::EXCEPTION &&
                        !memcmp(id, meta.exception, store::HASH) && m.revision == meta.exceptionRev;
    const bool resolved = m.type == sa1::BULLETIN ? handleBulletin(m, id, wire, wireLength) : handleOwn(m, id, wire, wireLength);
    services_.changed();
    return resolved;
}

int Station::inboxSlot() {
    // Wolne gniazdo, potem kolejno: najstarszy przeczytany BULLETIN, najstarszy przeczytany REPLY
    // zgłoszenia zamkniętego (albo zwolnionego), najstarszy nieprzeczytany BULLETIN. REPLY zgłoszenia
    // otwartego nie odpada nigdy.
    const int free = store_.freeMessageSlot();
    if (free >= 0) return free;
    for (int pass = 0; pass < 3; ++pass) {
        int best = -1;
        for (size_t i = 0; i < store::INBOX_SLOTS; ++i) {
            const store::MessageIndex& x = store_.message(i);
            if (!x.used() || (best >= 0 && x.receivedS >= store_.message(best).receivedS)) continue;
            if (pass == 0 && !(x.type == sa1::BULLETIN && x.read)) continue;
            if (pass == 2 && !(x.type == sa1::BULLETIN && !x.read)) continue;
            if (pass == 1) {
                store::Message m;
                if (x.type != sa1::REPLY || !x.read || !store_.readMessage(i, m)) continue;
                const int request = store_.findRequest(m.id);
                if (request >= 0 && !store_.requestClosed(static_cast<size_t>(request))) continue;
            }
            best = static_cast<int>(i);
        }
        if (best >= 0) {
            if (pass == 2) ++stats_.evicted;
            return best;
        }
    }
    return -1;
}

bool Station::handleOwn(const sa1::Message& m, const uint8_t id[store::HASH], const char* wire, size_t wireLength) {
    const int found = store_.findRequest(id);
    Request r;
    // Spoza rejestru (także zwolnione), r > r_max, zgłoszenie anulowane (nigdy nie nadane): pominięte.
    if (found < 0 || !store_.readRequest(static_cast<size_t>(found), r) || m.revision > r.rMax || r.stage == Stage::CANCELLED) {
        ++stats_.skipped;
        return true;
    }
    const uint16_t slot = static_cast<uint16_t>(found);
    const uint16_t gen = store_.request(slot).gen;
    const bool backup = store_.meta().receiver == config::BACKUP;
    if (backupFlag(r) != backup) {
        // Liczniki STATUS i REPLY należą do aktywnej tożsamości: po KLUCZ ZAPASOWY od zera.
        r.statusHi = r.replyHi = 0;
        r.flags = static_cast<uint8_t>((r.flags & ~store::BACKUP) | (backup ? store::BACKUP : 0));
    }
    bool accepted = m.type == sa1::RECEIVED;
    bool decisionChanged = false;
    if (m.type == sa1::STATUS && m.event > r.statusHi) {
        r.statusHi = m.event;
        decisionChanged = r.decision != m.state || r.decisionRev != m.revision;
        r.decision = m.state;
        r.decisionRev = m.revision;
        if (m.revision == r.rMax) r.flags |= store::READ_MAX;
        accepted = true;
    }
    store::Tx tx(store_);
    if (m.type == sa1::REPLY && m.event > r.replyHi) {
        if (!addMessage(tx, m, id, wire, wireLength)) return false;   // bez dowodu: odbiorca ponowi
        r.replyHi = m.event;
        accepted = true;
    }
    if (!accepted) ++stats_.skipped;   // STATUS albo REPLY z event ≤ licznika: powtórzenie albo spóźniona
    const bool stageChanged = accepted && confirm(r, m.revision, store_.now());
    if (accepted) {
        r.changedS = store_.now();
        tx.request(slot, r, false);
        if (stageChanged || decisionChanged) {
            stageEvent(tx, slot, gen, r, static_cast<StageCode>(r.stage), decisionChanged);
        }
    }
    touchContact(tx);
    return tx.commit();
}

bool Station::addMessage(store::Tx& tx, const sa1::Message& m, const uint8_t id[store::HASH], const char* wire, size_t wireLength) {
    // Nowy wpis skrzynki (REPLY, BULLETIN) ze zdarzeniem `msg`; numer wiadomości = numer zdarzenia.
    const int inbox = inboxSlot();
    if (inbox < 0) { ++stats_.inboxFull; return false; }
    const uint16_t slot = static_cast<uint16_t>(inbox);
    store::Message message;
    message.type = m.type;
    message.source = store_.meta().receiver;
    memcpy(message.id, id, store::HASH);
    message.revision = m.revision;
    message.event = m.event;
    message.receivedS = store_.now();
    memcpy(message.sa1, wire, wireLength + 1);
    message.sa1Length = static_cast<uint16_t>(wireLength);
    tx.message(slot, message, true);
    store::Event e;
    e.kind = store::EventKind::MSG;
    e.a = message.source;
    e.slot = slot;
    e.gen = tx.gen(store::INBOX, slot);
    e.revision = m.revision;
    message.number = tx.event(e);
    tx.message(slot, message, true);
    return true;
}

bool Station::handleBulletin(const sa1::Message& m, const uint8_t id[store::HASH], const char* wire, size_t wireLength) {
    store::Tx tx(store_);
    if (store_.bulletinSeen(id, m.event)) {
        ++stats_.bulletinsSkipped;
    } else {
        if (!addMessage(tx, m, id, wire, wireLength)) return false;
        tx.bulletin(id, m.event);
    }
    touchContact(tx);
    return tx.commit();
}

// --- Alarmy ----------------------------------------------------------------------------------

bool Station::alarm(Alarm& out, bool withAcked) const {
    // Najstarszy przekroczony próg: brak_potwierdzenia (r_max bez RECEIVED; TEST 30 min od nadania),
    // brak_odczytu (pilność 2, 30 min po RECEIVED r_max bez STATUS tej rewizji).
    const uint32_t nowS = store_.now();
    bool found = false;
    uint32_t bestAge = 0;
    for (size_t i = 0; i < store::REGISTER_SLOTS; ++i) {
        const RequestIndex& r = store_.request(i);
        if (!r.used() || r.stage == Stage::CANCELLED || nowS < r.alarmS) continue;
        if (r.type == sa1::TEST && r.stage != Stage::RECEIVED && !(r.flags & store::SENT_ONCE)) continue;   // TEST przed nadaniem
        const uint32_t age = nowS - r.alarmS;
        AlarmKind kind = AlarmKind::NONE;
        if (r.stage != Stage::RECEIVED) {
            if (age >= (r.type == sa1::TEST ? TEST_ALARM_S : CONFIRM_ALARM_S[r.urgency < 3 ? r.urgency : 0])) kind = AlarmKind::NO_CONFIRMATION;
        } else if (r.type == sa1::REQUEST && r.urgency == 2 && !(r.flags & store::READ_MAX) && age >= READ_ALARM_S) {
            kind = AlarmKind::NO_READ;
        }
        if (kind == AlarmKind::NONE) continue;
        const uint8_t bit = kind == AlarmKind::NO_READ ? 2 : 1;
        if (!withAcked && alarmAckedGen_[i] == r.gen && (alarmAcked_[i] & bit)) continue;
        if (!found || age > bestAge) {
            found = true;
            bestAge = age;
            out.kind = kind;
            out.slot = static_cast<uint16_t>(i);
            out.gen = r.gen;
            out.number = r.number();
            out.minutes = age / 60;
        }
    }
    return found;
}

void Station::ackAlarm(const Alarm& alarm) {
    if (alarm.slot >= store::REGISTER_SLOTS) return;
    if (alarmAckedGen_[alarm.slot] != alarm.gen) alarmAcked_[alarm.slot] = 0;   // gniazdo po innym wpisie
    alarmAckedGen_[alarm.slot] = alarm.gen;
    alarmAcked_[alarm.slot] |= alarm.kind == AlarmKind::NO_READ ? 2 : 1;
}

}  // namespace station
