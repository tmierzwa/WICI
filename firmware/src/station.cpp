// SPDX-License-Identifier: MIT
#include "station.h"

#include <stdio.h>
#include <string.h>

#include "jsonlite.h"

namespace station {

Station::Station(store::Store& store, Services& services) : store_(store), services_(services) {}

uint32_t Station::retryDelayS(uint16_t attempts, bool delivered, uint32_t ageS, uint32_t random) {
    // ±20% z losowej liczby: współczynnik 0,8..1,2.
    const uint32_t jitter = 80 + random % 41;
    if (delivered) {
        const uint32_t span = RESEND_MAX_S - RESEND_MIN_S;
        return RESEND_MIN_S + (random % (span + 1));
    }
    if (ageS >= FAILED_LATE_S) return FAILED_LATE_INTERVAL_S * jitter / 100;
    static const uint32_t steps[] = {60, 120, 300, 900};  // po 1., 2., 3. i dalszych nieudanych próbach
    const uint16_t index = attempts ? static_cast<uint16_t>(attempts - 1) : 0;
    const uint32_t base = steps[index < 4 ? index : 3];
    return base * jitter / 100;
}

int Station::priority(const store::QueueEntry& e) const {
    // RECEIVED i STATUS, potem REPLY i BULLETIN, potem REQUEST z pilnością 2, pozostałe REQUEST, na końcu TEST.
    switch (e.type) {
        case sa1::RECEIVED: case sa1::STATUS: return 0;
        case sa1::REPLY: case sa1::BULLETIN: return 1;
        case sa1::REQUEST: return e.aux == 2 ? 2 : 3;
        default: return 4;
    }
}

uint32_t Station::nextToSend(uint32_t nowS) const {
    const store::QueueEntry* best = nullptr;
    int bestPriority = 0;
    for (size_t i = 0; i < store_.queueSize(); ++i) {
        const store::QueueEntry* e = store_.queueEntry(i);
        if (!e || !(e->flags & store::ACTIVE) || e->nextTryS > nowS) continue;
        if (testPaused_ && e->type == sa1::TEST) continue;
        const int p = priority(*e);
        if (!best || p < bestPriority || (p == bestPriority && e->createdS < best->createdS)) { best = e; bestPriority = p; }
    }
    return best ? best->seq : 0;
}

bool Station::buildDatagram(const store::QueueRecord& record, char* out, size_t size, size_t& length) {
    uint8_t self[store::HASH];
    services_.address(self);
    char from[2 * store::HASH + 1], to[2 * store::HASH + 1];
    store::bytesToHex(self, from);
    store::bytesToHex(record.to, to);
    const int n = snprintf(out, size, "[\"WICI\",1,\"%s\",\"%s\",%s]", from, to, record.sa1);
    if (n <= 0 || static_cast<size_t>(n) >= size || static_cast<size_t>(n) > DATAGRAM_MAX) return false;
    length = static_cast<size_t>(n);
    return true;
}

void Station::poll(uint32_t nowMs) {
    const uint32_t nowS = services_.uptimeS();
    (void)nowMs;
    // Brak potwierdzenia łącza w czasie: próba nieudana, następna według harmonogramu.
    if (inFlightSeq_ && !awaitingTx_ && nowS - inFlightSentS_ >= ACK_TIMEOUT_S) {
        store::QueueRecord r;
        if (store_.queueRead(inFlightSeq_, r)) {
            ++stats_.failed;
            uint32_t random = 0;
            services_.randomBytes(reinterpret_cast<uint8_t*>(&random), sizeof(random));
            r.nextTryS = nowS + retryDelayS(r.attempts, false, nowS - r.createdS, random);
            r.updatedS = nowS;
            store_.queueUpdate(r);
            services_.changed();
        }
        inFlightSeq_ = 0;
    }
    if (services_.silence() || !services_.radioReady() || services_.busy() || awaitingTx_) return;
    // Zaległe potwierdzenie łącza przed własnym ruchem.
    if (pendingAck_) {
        uint8_t self[store::HASH];
        services_.address(self);
        char from[2 * store::HASH + 1], to[2 * store::HASH + 1], line[160];
        store::bytesToHex(self, from);
        store::bytesToHex(ackTo_, to);
        const int n = snprintf(line, sizeof(line), "[\"WICI\",1,\"%s\",\"%s\",\"ack\",\"%s\",%u,%u,%lu]", from, to, ackId_, ackRevision_,
                               ackType_, static_cast<unsigned long>(ackEvent_));
        pendingAck_ = false;
        if (n > 0 && services_.send(reinterpret_cast<const uint8_t*>(line), static_cast<size_t>(n))) {
            ++stats_.acksSent;
            awaitingTx_ = true;
            return;
        }
    }
    if (inFlightSeq_) return;
    const uint32_t seq = nextToSend(nowS);
    if (!seq) return;
    store::QueueRecord r;
    if (!store_.queueRead(seq, r)) return;
    char datagram[DATAGRAM_MAX + 1];
    size_t length = 0;
    if (!buildDatagram(r, datagram, sizeof(datagram), length)) {
        r.flags = static_cast<uint8_t>(r.flags & ~store::ACTIVE);  // nie da się nadać: intencja zatrzymana
        store_.queueUpdate(r);
        services_.log("intent too large for P1");
        return;
    }
    if (!services_.send(reinterpret_cast<const uint8_t*>(datagram), length)) return;
    ++stats_.sent;
    r.attempts = static_cast<uint16_t>(r.attempts + 1);
    if (!r.sentS) r.sentS = nowS;
    r.nextTryS = nowS + ACK_TIMEOUT_S;  // do czasu wyniku próby nie nadaje się ponownie
    r.updatedS = nowS;
    store_.queueUpdate(r);
    inFlightSeq_ = seq;
    inFlightSentS_ = nowS;
    awaitingTx_ = true;
    services_.changed();
}

void Station::txDone(bool ok) {
    awaitingTx_ = false;
    if (!inFlightSeq_) return;
    if (!ok) {
        // Seria nie wyszła (cisza, odroczenia, dziennik): próba nieudana od razu.
        store::QueueRecord r;
        const uint32_t nowS = services_.uptimeS();
        if (store_.queueRead(inFlightSeq_, r)) {
            ++stats_.failed;
            uint32_t random = 0;
            services_.randomBytes(reinterpret_cast<uint8_t*>(&random), sizeof(random));
            r.nextTryS = nowS + retryDelayS(r.attempts, false, nowS - r.createdS, random);
            r.updatedS = nowS;
            store_.queueUpdate(r);
        }
        inFlightSeq_ = 0;
    } else {
        inFlightSentS_ = services_.uptimeS();  // czas na ack liczy się od końca serii
    }
}

bool Station::trustedSource(const uint8_t from[store::HASH]) const {
    const store::Config& c = store_.config();
    if (c.role == store::OSP) return true;  // bez kart zaufanych: każda stacja (kwarantannę prowadzi laptop)
    uint8_t zero[store::HASH] = {};
    if (!store_.configured() || !memcmp(c.osp[c.activeOsp ? 1 : 0], zero, store::HASH)) return true;  // stanowisko bez karty OSP
    return !memcmp(from, c.osp[c.activeOsp ? 1 : 0], store::HASH);
}

void Station::sendAck(const uint8_t to[store::HASH], const char* id, uint16_t revision, uint8_t type, uint32_t event) {
    memcpy(ackTo_, to, store::HASH);
    ackEvent_ = event;
    strncpy(ackId_, id, sa1::ID_HEX);
    ackId_[sa1::ID_HEX] = '\0';
    ackRevision_ = revision;
    ackType_ = type;
    pendingAck_ = true;
}

void Station::received(const uint8_t* data, size_t length) {
    if (length > DATAGRAM_MAX) { ++stats_.rejected; return; }
    char copy[DATAGRAM_MAX + 1];
    memcpy(copy, data, length);
    copy[length] = '\0';
    json::Value array, v;
    char marker[8], fromHex[2 * store::HASH + 2], toHex[2 * store::HASH + 2];
    uint8_t from[store::HASH], to[store::HASH], self[store::HASH];
    int64_t version = 0;
    if (!json::parse(copy, array) || array.kind != json::Kind::ARRAY || json::count(array) < 5 ||
        !json::item(array, 0, v) || !json::string(v, marker, sizeof(marker)) || strcmp(marker, "WICI") ||
        !json::item(array, 1, v) || !json::integer(v, version) || version != 1 ||
        !json::item(array, 2, v) || !json::string(v, fromHex, sizeof(fromHex)) || !store::hexToBytes(fromHex, from) ||
        !json::item(array, 3, v) || !json::string(v, toHex, sizeof(toHex)) || !store::hexToBytes(toHex, to)) {
        ++stats_.rejected;
        return;
    }
    services_.address(self);
    if (memcmp(to, self, store::HASH)) { ++stats_.rejected; return; }  // nie do nas
    ++stats_.received;
    json::Value payload;
    json::item(array, 4, payload);
    if (payload.kind == json::Kind::STRING) {
        char word[8], id[sa1::ID_HEX + 2];
        int64_t revision = 0, type = 0, event = 0;
        if (!json::string(payload, word, sizeof(word)) || strcmp(word, "ack") || json::count(array) != 9 ||
            !json::item(array, 5, v) || !json::string(v, id, sizeof(id)) || !sa1::isHexId(id) ||
            !json::item(array, 6, v) || !json::integer(v, revision) || revision < 0 || revision > sa1::REVISION_MAX ||
            !json::item(array, 7, v) || !json::integer(v, type) || type < 0 || type > sa1::TEST ||
            !json::item(array, 8, v) || !json::integer(v, event) || event < 0 || event > sa1::EVENT_MAX) {
            ++stats_.rejected;
            return;
        }
        handleAck(from, id, static_cast<uint16_t>(revision), static_cast<uint8_t>(type), static_cast<uint32_t>(event));
        return;
    }
    if (payload.kind != json::Kind::ARRAY || json::count(array) != 5 || payload.length > sa1::MAX_CONTENT) { ++stats_.rejected; return; }
    if (!trustedSource(from)) { ++stats_.rejected; services_.log("datagram from untrusted source"); return; }
    sa1::Message m;
    if (sa1::decode(payload.begin, payload.length, m)) { ++stats_.rejected; return; }
    const bool osp = store_.config().role == store::OSP;
    const bool allowed = osp ? (m.type == sa1::REQUEST || m.type == sa1::TEST) : (m.type >= sa1::RECEIVED && m.type <= sa1::BULLETIN);
    if (!allowed) { ++stats_.rejected; return; }
    char wire[sa1::MAX_CONTENT + 1];
    const size_t wireLength = sa1::encode(m, wire, sizeof(wire));
    if (!wireLength) { ++stats_.rejected; return; }
    handleMessage(from, m, wire, wireLength);
}

void Station::finishIntent(store::QueueRecord& r, uint32_t event, uint8_t state) {
    r.flags = static_cast<uint8_t>((r.flags & ~store::ACTIVE) | store::DONE | store::SENT);
    r.statusEvent = event;
    r.state = state;
    r.updatedS = services_.uptimeS();
    store_.queueUpdate(r);
    if (inFlightSeq_ == r.seq) inFlightSeq_ = 0;
    ++stats_.confirmed;
}

void Station::handleAck(const uint8_t from[store::HASH], const char* id, uint16_t revision, uint8_t type, uint32_t event) {
    uint8_t idBytes[store::HASH];
    if (!store::hexToBytes(id, idBytes)) { ++stats_.rejected; return; }
    const uint32_t nowS = services_.uptimeS();
    // Potwierdzenie łącza dotyczy intencji o pełnym kluczu (odbiorca, typ, id, revision, event).
    const store::QueueEntry* e = store_.queueFind(from, type, idBytes, revision, event);
    if (e) {
        store::QueueRecord r;
        if (!store_.queueRead(e->seq, r)) return;
        if (r.flags & (store::DONE | store::CANCELLED | store::REPLACED)) return;  // spóźnione potwierdzenie zakończonej intencji
        ++stats_.delivered;
        if (inFlightSeq_ == r.seq) inFlightSeq_ = 0;
        if (type == sa1::REQUEST || type == sa1::TEST) {
            // Dostarczone: czeka na RECEIVED 10 min, potem ponawia co 30–60 min.
            uint32_t random = 0;
            services_.randomBytes(reinterpret_cast<uint8_t*>(&random), sizeof(random));
            r.flags |= store::SENT;
            r.nextTryS = nowS + RECEIVED_WAIT_S + (r.attempts > 1 ? retryDelayS(r.attempts, true, nowS - r.createdS, random) : 0);
            r.updatedS = nowS;
            store_.queueUpdate(r);
        } else {
            // RECEIVED, STATUS, REPLY, BULLETIN: dostarczenie kończy intencję.
            finishIntent(r, r.statusEvent, r.state);
        }
        services_.changed();
        return;
    }
}

void Station::handleMessage(const uint8_t from[store::HASH], const sa1::Message& m, const char* wire, size_t wireLength) {
    const uint32_t nowS = services_.uptimeS();
    uint8_t idBytes[store::HASH];
    store::hexToBytes(m.id, idBytes);
    const bool osp = store_.config().role == store::OSP;
    const uint16_t revision = m.type == sa1::BULLETIN ? 0 : m.revision;
    const uint32_t event = (m.type == sa1::STATUS || m.type == sa1::REPLY || m.type == sa1::BULLETIN) ? m.event : 0;
    // Rola stacji: STATUS i RECEIVED dotyczą własnej intencji; STATUS dla nieznanego id jest ignorowany.
    store::QueueRecord intent;
    bool haveIntent = false;
    if (!osp && m.type != sa1::BULLETIN) {
        for (size_t i = 0; i < store_.queueSize(); ++i) {
            const store::QueueEntry* e = store_.queueEntry(i);
            if (e && e->revision == m.revision && !memcmp(e->id, idBytes, store::HASH) && (e->type == sa1::REQUEST || e->type == sa1::TEST) &&
                store_.queueRead(e->seq, intent)) { haveIntent = true; break; }
        }
        if (!haveIntent && (m.type == sa1::STATUS || m.type == sa1::RECEIVED)) {
            uint32_t seenEvent = 0;
            uint8_t seenState = 0;
            if (!store_.seenGet(idBytes, m.revision, seenEvent, seenState)) { ++stats_.rejected; services_.log("status for unknown id"); return; }
        }
    }
    store::InboxRecord record;
    record.receivedS = nowS;
    record.type = m.type;
    record.revision = revision;
    record.event = event;
    memcpy(record.source, from, store::HASH);
    memcpy(record.id, idBytes, store::HASH);
    memcpy(record.sa1, wire, wireLength + 1);
    record.sa1Length = static_cast<uint16_t>(wireLength);
    const store::Put put = store_.inboxPut(record);
    if (put == store::Put::CONFLICT) { ++stats_.conflicts; services_.log("conflicting duplicate"); return; }
    if (put == store::Put::ERROR) { services_.log("inbox write failed"); return; }
    // Potwierdzenie łącza także dla duplikatu: nadawca mógł nie dostać poprzedniego.
    sendAck(from, m.id, revision, m.type, event);
    if (put == store::Put::DUPLICATE) {
        ++stats_.duplicates;
        if (osp) {
            // Powtórzony REQUEST lub TEST o znanym kluczu: zapisany RECEIVED i najnowszy STATUS idą ponownie.
            const store::QueueEntry* receivedEntry = nullptr;
            const store::QueueEntry* statusEntry = nullptr;
            for (size_t i = 0; i < store_.queueSize(); ++i) {
                const store::QueueEntry* e = store_.queueEntry(i);
                if (!e || e->revision != m.revision || memcmp(e->id, idBytes, store::HASH) || memcmp(e->to, from, store::HASH)) continue;
                if (e->type == sa1::RECEIVED) receivedEntry = e;
                else if (e->type == sa1::STATUS && (!statusEntry || e->event > statusEntry->event)) statusEntry = e;
            }
            const store::QueueEntry* again[2] = {receivedEntry, statusEntry};
            for (const store::QueueEntry* e : again) {
                store::QueueRecord r;
                if (!e || !store_.queueRead(e->seq, r)) continue;
                r.flags = static_cast<uint8_t>((r.flags & ~(store::DONE | store::SENT)) | store::ACTIVE);
                r.nextTryS = 0;
                r.updatedS = nowS;
                store_.queueUpdate(r);
            }
        }
        return;
    }
    // Nowa wiadomość: zdarzenie do laptopa i skutki dla intencji.
    char fields[sa1::MAX_CONTENT + 96];
    char sourceHex[2 * store::HASH + 1];
    store::bytesToHex(from, sourceHex);
    snprintf(fields, sizeof(fields), "\"kind\":\"message\",\"source\":\"%s\",\"inbox\":%lu,\"sa1\":%s", sourceHex,
             static_cast<unsigned long>(record.seq), wire);
    services_.notify(osp ? store::NOTE_INCOMING : store::NOTE_MESSAGE, record.seq, fields);
    if (haveIntent) {
        if (m.type == sa1::RECEIVED || m.type == sa1::STATUS) {
            // Pierwsze potwierdzenie ustala (1, 1); kolejne STATUS przechodzą przez status_after modelu.
            uint32_t newEvent = intent.statusEvent ? intent.statusEvent : 1;
            uint8_t newState = intent.statusEvent ? intent.state : 1;
            const char* why = intent.statusEvent ? sa1::statusAfter(intent.statusEvent, intent.state, m.event, m.state, newEvent, newState)
                                                 : sa1::statusAfter(1, 1, m.event, m.state, newEvent, newState);
            if (why) { services_.log(why); }
            else if (newEvent != intent.statusEvent || !(intent.flags & store::DONE)) {
                finishIntent(intent, newEvent, newState);
                store_.seenPut(idBytes, m.revision, newEvent, newState);
            }
        } else if (m.type == sa1::REPLY && (intent.flags & store::ACTIVE)) {
            finishIntent(intent, intent.statusEvent, intent.state);
        }
    }
    services_.changed();
}

Create Station::putIntent(sa1::Message& m, uint8_t type, const uint8_t id[store::HASH], uint32_t delayS, uint32_t& seq) {
    const store::Config& c = store_.config();
    if (!c.address[0]) return Create::NO_ADDRESS;
    m.type = type;
    store::bytesToHex(id, m.id);
    strncpy(m.location, c.address, sa1::LOCATION_MAX);
    m.location[sa1::LOCATION_MAX] = '\0';
    store::QueueRecord record;
    record.sa1Length = static_cast<uint16_t>(sa1::encode(m, record.sa1, sizeof(record.sa1)));
    if (!record.sa1Length) return Create::TOO_LARGE;
    memcpy(record.to, c.osp[c.activeOsp ? 1 : 0], store::HASH);
    memcpy(record.id, id, store::HASH);
    record.type = type;
    record.revision = m.revision;
    record.aux = m.urgency;
    record.category = m.category;
    record.createdS = services_.uptimeS();
    record.updatedS = record.createdS;
    record.nextTryS = delayS ? record.createdS + delayS : 0;
    const store::Put put = store_.queuePut(record, false);
    if (put == store::Put::FULL) return Create::FULL;
    if (put != store::Put::STORED) return Create::ERROR;
    seq = record.seq;
    services_.changed();
    return Create::STORED;
}

Create Station::createRequest(uint8_t category, uint16_t people, uint8_t urgency, const char* text, uint32_t& seq) {
    sa1::Message m;
    m.revision = 0;
    m.category = category;
    m.people = people;
    m.urgency = urgency;
    strncpy(m.text, text ? text : "", sa1::TEXT_MAX);
    m.text[sa1::TEXT_MAX] = '\0';
    // Krótki numer unikalny w stacji: id losowane ponownie, dopóki numer jest zajęty.
    uint8_t id[store::HASH];
    for (int attempt = 0; attempt < 32; ++attempt) {
        services_.randomBytes(id, sizeof(id));
        if (!store_.queueNumberTaken(store::shortNumber(id), id)) break;
    }
    const Create result = putIntent(m, sa1::REQUEST, id, 0, seq);
    if (result == Create::STORED) {
        char line[40];
        snprintf(line, sizeof(line), "request %04u created", store::shortNumber(id));
        services_.log(line);
    }
    return result;
}

Create Station::revise(uint32_t seq, uint16_t people, uint8_t urgency, const char* text, uint32_t& newSeq) {
    store::QueueRecord old;
    if (!store_.queueRead(seq, old) || (old.type != sa1::REQUEST && old.type != sa1::TEST)) return Create::NOT_FOUND;
    sa1::Message m;
    if (sa1::decode(old.sa1, old.sa1Length, m) || m.revision >= sa1::REVISION_MAX) return Create::NOT_FOUND;
    m.revision = static_cast<uint16_t>(m.revision + 1);
    m.people = people;
    m.urgency = urgency;
    if (text) { strncpy(m.text, text, sa1::TEXT_MAX); m.text[sa1::TEXT_MAX] = '\0'; }
    const Create result = putIntent(m, old.type, old.id, 0, newSeq);
    if (result != Create::STORED) return result;
    if ((old.flags & store::ACTIVE) && !(old.flags & store::SENT) && !old.state) {
        // Nienadana starsza rewizja: zastąpiona, nie wychodzi.
        old.flags = static_cast<uint8_t>((old.flags & ~store::ACTIVE) | store::REPLACED);
        old.updatedS = services_.uptimeS();
        store_.queueUpdate(old);
        if (inFlightSeq_ == old.seq) inFlightSeq_ = 0;
    }
    char line[48];
    snprintf(line, sizeof(line), "request %04u revision %u", store::shortNumber(old.id), m.revision);
    services_.log(line);
    return Create::STORED;
}

bool Station::cancel(uint32_t seq) {
    store::QueueRecord r;
    if (!store_.queueRead(seq, r) || r.state || !(r.flags & store::ACTIVE)) return false;
    r.flags = static_cast<uint8_t>((r.flags & ~store::ACTIVE) | store::CANCELLED);
    r.updatedS = services_.uptimeS();
    if (!store_.queueUpdate(r)) return false;
    if (inFlightSeq_ == seq) inFlightSeq_ = 0;
    char line[40];
    snprintf(line, sizeof(line), "request %04u cancelled", store::shortNumber(r.id));
    services_.log(line);
    services_.changed();
    return true;
}

uint32_t Station::pendingTest() const {
    for (size_t i = 0; i < store_.queueSize(); ++i) {
        const store::QueueEntry* e = store_.queueEntry(i);
        if (e && e->type == sa1::TEST && (e->flags & store::ACTIVE) && e->attempts == 0) return e->seq;
    }
    return 0;
}

Create Station::scheduleTest(bool startup, uint32_t& seq) {
    if (const uint32_t pending = pendingTest()) { seq = pending; return Create::STORED; }
    sa1::Message m;
    m.revision = 0;
    m.category = 9;
    m.people = 1;
    m.urgency = 0;
    strncpy(m.text, "test", sizeof(m.text) - 1);
    uint8_t id[store::HASH];
    for (int attempt = 0; attempt < 32; ++attempt) {
        services_.randomBytes(id, sizeof(id));
        if (!store_.queueNumberTaken(store::shortNumber(id), id)) break;
    }
    uint32_t delayS = 0;
    if (startup) {
        const uint16_t stations = store_.config().stations;
        const uint32_t window = stations ? TEST_WINDOW_PER_STATION_S * stations : TEST_WINDOW_S;
        uint32_t random = 0;
        services_.randomBytes(reinterpret_cast<uint8_t*>(&random), sizeof(random));
        delayS = random % window;
    }
    const Create result = putIntent(m, sa1::TEST, id, delayS, seq);
    if (result == Create::STORED) services_.log(startup ? "startup test scheduled" : "test scheduled");
    return result;
}

bool Station::cancelTest() {
    const uint32_t seq = pendingTest();
    if (!seq) return false;
    store::QueueRecord r;
    if (!store_.queueRead(seq, r)) return false;
    r.flags = static_cast<uint8_t>((r.flags & ~store::ACTIVE) | store::CANCELLED);
    r.updatedS = services_.uptimeS();
    if (!store_.queueUpdate(r)) return false;
    services_.log("test cancelled");
    services_.changed();
    return true;
}

void Station::pauseTest(bool paused) {
    if (paused == testPaused_) return;
    testPaused_ = paused;
    if (paused) cancelTest();
    services_.log(paused ? "test paused" : "test resumed");
    services_.changed();
}

bool Station::alarmAcked(size_t slot, AlarmKind kind) const {
    return alarmAcked_[slot] & (kind == AlarmKind::NO_READ ? 2 : 1);
}

bool Station::alarm(uint32_t nowS, Alarm& out, bool withAcked) const {
    // Najstarszy przekroczony próg; alarm potwierdzony przyciskiem OK nie wraca.
    bool found = false;
    uint32_t bestAge = 0;
    for (size_t i = 0; i < store_.queueSize(); ++i) {
        const store::QueueEntry* e = store_.queueEntry(i);
        if (!e || (e->type != sa1::REQUEST && e->type != sa1::TEST) || (e->flags & (store::REPLACED | store::CANCELLED))) continue;
        AlarmKind kind = AlarmKind::NONE;
        uint32_t since = 0;
        if (e->state == 0) {
            if (e->type == sa1::TEST) {
                if (!e->sentS || nowS - e->sentS < TEST_ALARM_S) continue;
                since = e->sentS;
            } else {
                if (nowS - e->createdS < CONFIRM_ALARM_S[e->aux < 3 ? e->aux : 0]) continue;
                since = e->createdS;
            }
            kind = AlarmKind::NO_CONFIRMATION;
        } else if (e->state == 1 && e->type == sa1::REQUEST && e->aux == 2) {
            if (nowS - e->updatedS < READ_ALARM_S) continue;
            since = e->updatedS;
            kind = AlarmKind::NO_READ;
        } else continue;
        if (!withAcked && alarmAcked(i, kind)) continue;
        const uint32_t age = nowS - since;
        if (!found || age > bestAge) {
            found = true;
            bestAge = age;
            out.kind = kind;
            out.seq = e->seq;
            out.number = store::shortNumber(e->id);
            out.minutes = age / 60;
        }
    }
    return found;
}

void Station::ackAlarm(const Alarm& alarm) {
    for (size_t i = 0; i < store_.queueSize(); ++i) {
        const store::QueueEntry* e = store_.queueEntry(i);
        if (e && e->seq == alarm.seq) alarmAcked_[i] |= alarm.kind == AlarmKind::NO_READ ? 2 : 1;
    }
}

}  // namespace station
