// SPDX-License-Identifier: MIT
#include "usbproto.h"

#include <stdio.h>
#include <string.h>

#include "jsonlite.h"
#include "sa1.h"

namespace usbproto {

namespace {

bool fieldHex(const json::Value& msg, const char* key, uint8_t out[store::HASH]) {
    json::Value v;
    char hex[2 * store::HASH + 2];
    return json::field(msg, key, v) && json::string(v, hex, sizeof(hex)) && store::hexToBytes(hex, out);
}

bool fieldInt(const json::Value& msg, const char* key, int64_t& out) {
    json::Value v;
    return json::field(msg, key, v) && json::integer(v, out);
}

bool fieldBool(const json::Value& msg, const char* key, bool& out) {
    json::Value v;
    if (!json::field(msg, key, v)) return false;
    if (v.kind == json::Kind::TRUE_) { out = true; return true; }
    if (v.kind == json::Kind::FALSE_) { out = false; return true; }
    return false;
}

const char* typeName(const json::Value& msg, char* out, size_t size) {
    json::Value v;
    if (!json::field(msg, "type", v) || !json::string(v, out, size)) return nullptr;
    return out;
}

}  // namespace

Protocol::Protocol(store::Store& store, Host& host) : store_(store), host_(host) {}

void Protocol::begin() {
    uint8_t bytes[BOOT_HEX / 2];
    host_.randomBytes(bytes, sizeof(bytes));
    for (size_t i = 0; i < sizeof(bytes); ++i) snprintf(boot_ + 2 * i, 3, "%02x", bytes[i]);
}

void Protocol::connected(uint32_t nowMs) {
    connected_ = true;
    synced_ = false;
    lineLength_ = 0;
    overflow_ = false;
    lastSentMs_ = nowMs;
    sendSync(-1);
}

void Protocol::disconnected() {
    connected_ = false;
    synced_ = false;
    lineLength_ = 0;
    overflow_ = false;
}

void Protocol::feed(const char* bytes, size_t count, uint32_t nowMs) {
    for (size_t i = 0; i < count; ++i) {
        const char c = bytes[i];
        if (c == '\n' || c == '\r') {
            if (overflow_) {
                overflow_ = false;
                ++stats_.overflow;
                rejected(-1, "line too long");
            } else if (lineLength_) {
                line_[lineLength_] = '\0';
                handleLine(line_, nowMs);
            }
            lineLength_ = 0;
        } else if (overflow_) {
            continue;
        } else if (c == '\0') {
            // NUL ucina wiersz w C: cały wiersz odrzucony (jak przy przepełnieniu, z tym samym licznikiem)
            overflow_ = true;
            lineLength_ = 0;
        } else if (lineLength_ < MAX_LINE) {
            line_[lineLength_++] = c;
        } else {
            overflow_ = true;
            lineLength_ = 0;
        }
    }
}

void Protocol::send(const char* type, int64_t re, const char* fields) {
    char line[MAX_LINE + 1];
    const uint32_t seq = ++seq_;
    int n;
    if (re >= 0) n = snprintf(line, sizeof(line), "{\"usb\":%lu,\"seq\":%lu,\"type\":\"%s\",\"re\":%lld%s%s}", static_cast<unsigned long>(CONTRACT),
                              static_cast<unsigned long>(seq), type, static_cast<long long>(re), fields && *fields ? "," : "", fields ? fields : "");
    else n = snprintf(line, sizeof(line), "{\"usb\":%lu,\"seq\":%lu,\"type\":\"%s\"%s%s}", static_cast<unsigned long>(CONTRACT),
                      static_cast<unsigned long>(seq), type, fields && *fields ? "," : "", fields ? fields : "");
    if (n <= 0 || static_cast<size_t>(n) >= sizeof(line)) return;
    ++stats_.linesOut;
    host_.emit(line);
}

void Protocol::rejected(int64_t re, const char* reason, const char* detail) {
    char fields[160];
    if (detail) snprintf(fields, sizeof(fields), "\"reason\":\"%s\",\"detail\":\"%s\"", reason, detail);
    else snprintf(fields, sizeof(fields), "\"reason\":\"%s\"", reason);
    ++stats_.rejected;
    send("rejected", re, fields);
}

void Protocol::sendSync(int64_t re) {
    const store::Config& c = store_.config();
    char fields[320];
    snprintf(fields, sizeof(fields),
             "\"boot\":\"%s\",\"cursor\":%lu,\"pending\":%u,\"queued\":%u,\"inbox\":%u,\"role\":\"%s\",\"configured\":%s,\"prep\":%s,"
             "\"silence\":%s,\"name\":\"%s\",\"fw\":\"%s\"",
             boot_, static_cast<unsigned long>(store_.noteLatest()), static_cast<unsigned>(store_.notesPending()),
             static_cast<unsigned>(store_.queueLive()), static_cast<unsigned>(store_.inboxCount()), c.role == store::OSP ? "osp" : "station",
             store_.configured() ? "true" : "false", host_.prep() ? "true" : "false", host_.silence() ? "true" : "false",
             host_.stationName(), host_.version());
    send("sync", re, fields);
}

bool Protocol::sendNote(uint32_t seq) {
    store::NoteRecord note;
    if (!store_.noteRead(seq, note)) return false;
    char fields[store::NOTE_TEXT + 64];
    snprintf(fields, sizeof(fields), "\"record\":%lu,\"at\":%lu,%s", static_cast<unsigned long>(note.seq),
             static_cast<unsigned long>(note.createdS), note.text);
    send(note.kind == store::NOTE_INCOMING ? "incoming" : "event", -1, fields);
    return true;
}

void Protocol::handleLine(const char* line, uint32_t nowMs) {
    ++stats_.linesIn;
    json::Value msg;
    int64_t usb = 0;
    int64_t seq = -1;
    char type[24];
    if (!json::parse(line, msg) || msg.kind != json::Kind::OBJECT) { rejected(-1, "not json"); return; }
    if (!fieldInt(msg, "usb", usb) || usb != CONTRACT) { rejected(-1, "contract"); return; }
    if (!fieldInt(msg, "seq", seq) || seq < 0) { rejected(-1, "seq"); return; }
    if (!typeName(msg, type, sizeof(type))) { rejected(seq, "type"); return; }
    // Typ z laptopa trafia do dziennika tylko jako znaki drukowalne ASCII (bez wstrzykiwania wierszy LOG).
    for (char* c = type; *c; ++c) if (*c < 0x21 || *c > 0x7E) *c = '?';
    char text[64];
    snprintf(text, sizeof(text), "usb %s", type);
    if (strcmp(type, "ack")) host_.log(text);  // każde polecenie w dzienniku; ack nie jest poleceniem
    if (!strcmp(type, "sync")) {
        int64_t cursor = 0;
        if (fieldInt(msg, "cursor", cursor) && cursor >= 0 && cursor <= UINT32_MAX) {
            cursor_ = static_cast<uint32_t>(cursor);
            store_.noteAckUpTo(cursor_);
        }
        synced_ = true;
        lastSentSeq_ = 0;
        lastSentMs_ = nowMs - RESEND_MS;  // zaległe zdarzenia od razu
        sendSync(seq);
    } else if (!strcmp(type, "ack")) doAck(msg, nowMs);
    else if (!strcmp(type, "submit")) doSubmit(msg, seq);
    else if (!strcmp(type, "test")) doTest(seq);
    else if (!strcmp(type, "silence")) doSilence(msg, seq);
    else if (!strcmp(type, "configure")) doConfigure(msg, seq);
    else if (!strcmp(type, "close")) {
        if (!store_.close()) { rejected(seq, "memory"); return; }
        host_.queueChanged();
        send("ok", seq, "\"closed\":true");
    } else if (!strcmp(type, "destroy")) {
        if (!host_.confirm()) { host_.log("usb destroy not confirmed"); rejected(seq, "not confirmed"); return; }
        const bool journal = host_.eraseJournal();
        if (!store_.destroy() || !journal) { rejected(seq, "memory"); return; }
        host_.destroyed();
        host_.configChanged();
        host_.queueChanged();
        send("ok", seq, "\"destroyed\":true");
    } else if (!strcmp(type, "export") || !strcmp(type, "import")) {
        if (!host_.prep()) rejected(seq, "preparation mode required");
        else rejected(seq, "unsupported");
    } else if (!strcmp(type, "announce")) {
        if (host_.announce()) send("ok", seq, "\"announce\":true");
        else rejected(seq, "unsupported");
    } else if (!strcmp(type, "trust") || !strcmp(type, "revoke")) rejected(seq, "unsupported");
    else rejected(seq, "unknown type");
}

void Protocol::doAck(const json::Value& msg, uint32_t nowMs) {
    int64_t value = 0;
    bool last = false;
    if (fieldInt(msg, "cursor", value) && value >= 0 && value <= UINT32_MAX) {
        cursor_ = static_cast<uint32_t>(value);
        store_.noteAckUpTo(cursor_);
        last = cursor_ >= lastSentSeq_;
    } else if (fieldInt(msg, "record", value) && value > 0 && value <= UINT32_MAX) {
        store_.noteAck(static_cast<uint32_t>(value));
        last = static_cast<uint32_t>(value) == lastSentSeq_;
    }
    // Potwierdzone ostatnio wysłane: następne zaległe zdarzenie od razu, nie po 5 s.
    if (last) lastSentMs_ = nowMs - RESEND_MS;
}

void Protocol::recipient(uint8_t out[store::HASH]) const {
    const store::Config& c = store_.config();
    memcpy(out, c.osp[c.activeOsp ? 1 : 0], store::HASH);
}

void Protocol::doSubmit(const json::Value& msg, int64_t seq) {
    store::QueueRecord record;
    json::Value array;
    if (!fieldHex(msg, "to", record.to)) { rejected(seq, "invalid", "to"); return; }
    if (!json::field(msg, "sa1", array) || array.kind != json::Kind::ARRAY || array.length > sa1::MAX_CONTENT) { rejected(seq, "invalid", "sa1"); return; }
    sa1::Message m;
    const char* why = sa1::decode(array.begin, array.length, m);
    if (why) { rejected(seq, "invalid", why); return; }
    // Kanoniczna postać treści (ta sama, którą koduje model).
    record.sa1Length = static_cast<uint16_t>(sa1::encode(m, record.sa1, sizeof(record.sa1)));
    if (!record.sa1Length) { rejected(seq, "invalid", "Content too large"); return; }
    char id[sa1::ID_HEX + 2];
    json::Value v;
    int64_t revision = -1;
    if (!json::field(msg, "id", v) || !json::string(v, id, sizeof(id)) || strcmp(id, m.id)) { rejected(seq, "invalid", "id"); return; }
    if (m.type != sa1::BULLETIN) {
        if (!fieldInt(msg, "revision", revision) || revision != m.revision) { rejected(seq, "invalid", "revision"); return; }
    }
    const store::Config& c = store_.config();
    const bool station = c.role == store::STATION;
    const bool allowed = station ? (m.type == sa1::REQUEST || m.type == sa1::TEST) : (m.type >= sa1::RECEIVED && m.type <= sa1::BULLETIN);
    if (!allowed) { rejected(seq, "invalid", "type not allowed for this role"); return; }
    if (station && store_.configured()) {
        uint8_t osp[store::HASH];
        recipient(osp);
        if (memcmp(osp, record.to, store::HASH)) { rejected(seq, "invalid", "recipient is not the active OSP"); return; }
    }
    store::hexToBytes(m.id, record.id);
    if ((m.type == sa1::REQUEST || m.type == sa1::TEST) && store_.queueNumberTaken(store::shortNumber(record.id), record.id)) {
        rejected(seq, "numer_zajety");  // krótki numer zajęty przez inne zgłoszenie: laptop losuje nowe id
        return;
    }
    record.type = m.type;
    record.revision = m.type == sa1::BULLETIN ? 0 : m.revision;
    record.event = (m.type == sa1::STATUS || m.type == sa1::REPLY || m.type == sa1::BULLETIN) ? m.event : 0;
    record.aux = (m.type == sa1::REQUEST || m.type == sa1::TEST) ? m.urgency : 0;
    record.category = (m.type == sa1::REQUEST || m.type == sa1::TEST) ? m.category : 0;
    record.createdS = host_.uptimeS();
    bool resend = false;
    fieldBool(msg, "resend", resend);
    const store::Put put = store_.queuePut(record, resend);
    char fields[160];
    switch (put) {
        case store::Put::STORED:
        case store::Put::DUPLICATE:
            ++stats_.stored;
            snprintf(fields, sizeof(fields), "\"id\":\"%s\",\"revision\":%u,\"record\":%lu,\"duplicate\":%s", m.id, record.revision,
                     static_cast<unsigned long>(record.seq), put == store::Put::DUPLICATE ? "true" : "false");
            send("stored", seq, fields);
            host_.queueChanged();
            break;
        case store::Put::CONFLICT: rejected(seq, "conflict"); break;
        case store::Put::FULL: rejected(seq, "full"); break;
        case store::Put::ERROR: rejected(seq, "memory"); break;
    }
}

void Protocol::doTest(int64_t seq) {
    const store::Config& c = store_.config();
    if (!store_.configured() || !c.address[0]) { rejected(seq, "not configured"); return; }
    if (c.role != store::STATION) { rejected(seq, "invalid", "type not allowed for this role"); return; }
    sa1::Message m;
    m.type = sa1::TEST;
    uint8_t id[store::HASH];
    for (int attempt = 0; attempt < 32; ++attempt) {
        host_.randomBytes(id, sizeof(id));
        if (!store_.queueNumberTaken(store::shortNumber(id), id)) break;
    }
    store::bytesToHex(id, m.id);
    m.revision = 0;
    m.category = 9;
    m.people = 1;
    strncpy(m.location, c.address, sa1::LOCATION_MAX);
    strncpy(m.text, "test", sizeof(m.text) - 1);
    m.urgency = 0;
    store::QueueRecord record;
    record.sa1Length = static_cast<uint16_t>(sa1::encode(m, record.sa1, sizeof(record.sa1)));
    if (!record.sa1Length) { rejected(seq, "invalid", "Content too large"); return; }
    recipient(record.to);
    memcpy(record.id, id, store::HASH);
    record.type = sa1::TEST;
    record.category = 9;
    record.createdS = host_.uptimeS();
    const store::Put put = store_.queuePut(record, false);
    if (put != store::Put::STORED) { rejected(seq, store::putName(put)); return; }
    ++stats_.stored;
    char fields[120];
    snprintf(fields, sizeof(fields), "\"id\":\"%s\",\"revision\":0,\"record\":%lu,\"duplicate\":false", m.id, static_cast<unsigned long>(record.seq));
    send("stored", seq, fields);
    host_.queueChanged();
}

void Protocol::doSilence(const json::Value& msg, int64_t seq) {
    bool on = false;
    if (!fieldBool(msg, "on", on)) { rejected(seq, "invalid", "on"); return; }
    // Przełącznik na stacji ma pierwszeństwo przed panelem (oprogramowanie.md, „Cisza radiowa”).
    if (!on && host_.silenceSwitch()) { rejected(seq, "silence switch"); return; }
    if (!host_.confirm()) { host_.log("usb silence not confirmed"); rejected(seq, "not confirmed"); return; }
    host_.setSilence(on);
    send("ok", seq, on ? "\"silence\":true" : "\"silence\":false");
}

void Protocol::doConfigure(const json::Value& msg, int64_t seq) {
    if (!host_.prep()) { rejected(seq, "preparation mode required"); return; }
    store::Config c = store_.config();
    json::Value v;
    if (json::field(msg, "address", v) && !json::string(v, c.address, sizeof(c.address))) { rejected(seq, "invalid", "address"); return; }
    char role[12];
    if (json::field(msg, "role", v)) {
        if (!json::string(v, role, sizeof(role))) { rejected(seq, "invalid", "role"); return; }
        if (!strcmp(role, "station")) c.role = store::STATION;
        else if (!strcmp(role, "osp")) c.role = store::OSP;
        else { rejected(seq, "invalid", "role"); return; }
    }
    if (json::field(msg, "osp", v) && !fieldHex(msg, "osp", c.osp[0])) { rejected(seq, "invalid", "osp"); return; }
    if (json::field(msg, "osp_backup", v) && !fieldHex(msg, "osp_backup", c.osp[1])) { rejected(seq, "invalid", "osp_backup"); return; }
    if (json::field(msg, "ifac", v) && !fieldHex(msg, "ifac", c.ifac)) { rejected(seq, "invalid", "ifac"); return; }
    int64_t stations = 0;
    if (json::field(msg, "stations", v)) {
        if (!json::integer(v, stations) || stations < 0 || stations > 65535) { rejected(seq, "invalid", "stations"); return; }
        c.stations = static_cast<uint16_t>(stations);
    }
    if (json::field(msg, "phrases", v)) {
        if (v.kind != json::Kind::ARRAY || json::count(v) > store::PHRASES) { rejected(seq, "invalid", "phrases"); return; }
        memset(c.phrases, 0, sizeof(c.phrases));
        c.phraseCount = static_cast<uint8_t>(json::count(v));
        for (size_t i = 0; i < c.phraseCount; ++i) {
            json::Value entry;
            if (!json::item(v, i, entry) || entry.kind != json::Kind::ARRAY || json::count(entry) != 3) { rejected(seq, "invalid", "phrases"); return; }
            for (size_t l = 0; l < 3; ++l) {
                json::Value s;
                if (!json::item(entry, l, s) || !json::string(s, c.phrases[i][l], sizeof(c.phrases[i][l]))) { rejected(seq, "invalid", "phrases"); return; }
                if (sa1::checkText(c.phrases[i][l], store::PHRASE_MAX)) { rejected(seq, "invalid", "phrase text"); return; }
            }
        }
    }
    const char* phrases[store::PHRASES];
    for (size_t i = 0; i < c.phraseCount; ++i) phrases[i] = c.phrases[i][0];
    const char* why = nullptr;
    size_t size = 0;
    if (c.address[0]) {
        size = sa1::buttonConfigurationSize(c.address, phrases, c.phraseCount, &why);
        if (!size) { rejected(seq, "invalid", why); return; }
    }
    if (!store_.writeConfig(c)) { rejected(seq, "memory"); return; }
    host_.configChanged();
    char fields[80];
    snprintf(fields, sizeof(fields), "\"configured\":true,\"worst_request\":%u,\"config_seq\":%lu", static_cast<unsigned>(size),
             static_cast<unsigned long>(store_.config().seq));
    send("ok", seq, fields);
}

bool Protocol::event(uint8_t kind, uint32_t ref, const char* fields, uint32_t nowMs) {
    store::NoteRecord note;
    note.kind = kind;
    note.ref = ref;
    note.createdS = host_.uptimeS();
    strncpy(note.text, fields, store::NOTE_TEXT);
    note.text[store::NOTE_TEXT] = '\0';
    if (!store_.notePut(note)) return false;
    if (connected_ && synced_) {
        sendNote(note.seq);
        lastSentSeq_ = note.seq;
        lastSentMs_ = nowMs;
    }
    return true;
}

void Protocol::poll(uint32_t nowMs) {
    if (!connected_ || !synced_) return;
    if (nowMs - lastSentMs_ < RESEND_MS) return;
    const uint32_t pending = store_.notePendingAfter(cursor_);
    if (!pending) return;
    if (pending == lastSentSeq_) ++stats_.resends;
    sendNote(pending);
    lastSentSeq_ = pending;
    lastSentMs_ = nowMs;
}

}  // namespace usbproto
