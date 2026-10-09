// SPDX-License-Identifier: MIT
#include "usbproto.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "hexstr.h"
#include "sha2.h"

namespace usbproto {

namespace {

// Dopisanie do wiersza; false, gdy wiersz przekroczyłby bufor.
bool appendf(char* out, size_t size, size_t& n, const char* format, ...) {
    va_list args;
    va_start(args, format);
    const int written = n < size ? vsnprintf(out + n, size - n, format, args) : -1;
    va_end(args);
    if (written < 0 || n + static_cast<size_t>(written) >= size) return false;
    n += static_cast<size_t>(written);
    return true;
}

const char* boolName(bool value) { return value ? "true" : "false"; }

// Pola poleceń: nazwa, rodzaj, wymagane. Pole spoza listy albo złego rodzaju: `invalid` z nazwą.
enum class F : uint8_t { STR, INT, BOOL, ARRAY };
struct FieldSpec {
    const char* name;
    F kind;
    bool required;
};
struct Command {
    const char* type;
    uint8_t mode;              // MODE_*
    FieldSpec fields[4];
    uint8_t count;
};
enum : uint8_t { ANY = 0, STATION = 1, PREP = 2 };   // STATION: nie w konfiguracji węzła

const Command COMMANDS[] = {
    {"sync", ANY, {{"boot", F::STR, true}, {"epoch", F::STR, true}, {"cursor", F::INT, true}}, 3},
    {"ack", ANY, {{"epoch", F::STR, true}, {"cursor", F::INT, true}}, 2},
    {"snapshot", ANY, {{"epoch", F::STR, true}}, 1},
    {"submit", STATION, {{"id", F::STR, true}, {"revision", F::INT, true}, {"sa1", F::ARRAY, true}}, 3},
    {"cancel", STATION, {{"id", F::STR, true}}, 1},
    {"test", STATION, {{"nonce", F::STR, true}}, 1},
    {"announce", STATION, {}, 0},
    {"silence", ANY, {{"on", F::BOOL, true}, {"exception_id", F::STR, false}}, 2},
    {"mark_read", STATION, {{"msg", F::INT, true}}, 1},
    {"status", ANY, {}, 0},
    {"close", STATION, {{"epoch", F::STR, true}, {"head", F::INT, true}}, 2},
    {"destroy", ANY, {}, 0},
    {"card", PREP, {}, 0},
    {"xfer_begin", PREP, {{"op", F::STR, true}, {"size", F::INT, false}, {"sha256", F::STR, false}}, 3},
    {"xfer_part", PREP, {{"xfer", F::STR, true}, {"offset", F::INT, true}, {"data", F::STR, true}}, 3},
    {"xfer_read", PREP, {{"xfer", F::STR, true}, {"offset", F::INT, true}, {"length", F::INT, true}}, 3},
    {"xfer_commit", PREP, {{"xfer", F::STR, true}}, 1},
    {"xfer_abort", PREP, {{"xfer", F::STR, true}}, 1},
    {"migrate", PREP, {}, 0},
};

bool kindMatches(const json::Value& v, F kind) {
    switch (kind) {
        case F::STR: return v.kind == json::Kind::STRING;
        case F::INT: {
            int64_t n = 0;
            return json::integer(v, n) && n >= 0 && n <= 0xFFFFFFFFLL;
        }
        case F::BOOL: return v.kind == json::Kind::TRUE_ || v.kind == json::Kind::FALSE_;
        case F::ARRAY: return v.kind == json::Kind::ARRAY;
    }
    return false;
}

// Kontrola pól polecenia; nazwa złego pola w bad (drukowalne ASCII).
bool checkFields(const json::Value& msg, const Command& c, char* bad, size_t size) {
    json::Value key, value;
    for (size_t i = 0; json::member(msg, i, key, value); ++i) {
        char name[24];
        if (!json::string(key, name, sizeof(name))) { snprintf(bad, size, "field"); return false; }
        if (!strcmp(name, "usb") || !strcmp(name, "seq") || !strcmp(name, "type")) continue;
        bool known = false;
        for (uint8_t f = 0; f < c.count && !known; ++f) {
            if (strcmp(name, c.fields[f].name)) continue;
            known = true;
            if (!kindMatches(value, c.fields[f].kind)) { snprintf(bad, size, "%s", name); return false; }
        }
        if (!known) {
            for (char* p = name; *p; ++p) if (*p < 0x21 || *p > 0x7E || *p == '"' || *p == '\\') *p = '?';
            snprintf(bad, size, "%s", name);
            return false;
        }
    }
    for (uint8_t f = 0; f < c.count; ++f) {
        if (c.fields[f].required && !json::field(msg, c.fields[f].name, value)) { snprintf(bad, size, "%s", c.fields[f].name); return false; }
    }
    return true;
}

uint32_t intField(const json::Value& msg, const char* key) {
    json::Value v;
    int64_t n = 0;
    json::field(msg, key, v);
    json::integer(v, n);
    return static_cast<uint32_t>(n);
}

void numberText(uint16_t number, char out[5]) { snprintf(out, 5, "%04u", number % 10000u); }

const char* const STATION_WHAT[] = {"restart", "config", "receiver_backup", "prep"};

const char BASE64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

int base64Value(char c) {
    const char* p = c ? strchr(BASE64, c) : nullptr;
    return p ? static_cast<int>(p - BASE64) : -1;
}

}  // namespace

int base64Decode(const char* text, uint8_t* out, size_t size) {
    const size_t length = strlen(text);
    if (length % 4) return -1;
    size_t n = 0;
    for (size_t i = 0; i < length; i += 4) {
        int v[4];
        size_t pad = 0;
        for (size_t k = 0; k < 4; ++k) {
            const char c = text[i + k];
            if (c == '=' && i + 4 == length && k >= 2) { v[k] = 0; ++pad; continue; }
            if (pad || (v[k] = base64Value(c)) < 0) return -1;   // znak po dopełnieniu albo spoza alfabetu
        }
        const uint32_t word = (static_cast<uint32_t>(v[0]) << 18) | (v[1] << 12) | (v[2] << 6) | v[3];
        const size_t bytes = 3 - pad;
        if (n + bytes > size) return -1;
        for (size_t k = 0; k < bytes; ++k) out[n++] = static_cast<uint8_t>(word >> (16 - 8 * k));
    }
    return static_cast<int>(n);
}

size_t base64Encode(const uint8_t* data, size_t length, char* out) {
    size_t n = 0;
    for (size_t i = 0; i < length; i += 3) {
        const size_t take = length - i < 3 ? length - i : 3;
        uint32_t word = static_cast<uint32_t>(data[i]) << 16;
        if (take > 1) word |= static_cast<uint32_t>(data[i + 1]) << 8;
        if (take > 2) word |= data[i + 2];
        for (size_t k = 0; k < 4; ++k) out[n++] = k <= take ? BASE64[(word >> (18 - 6 * k)) & 0x3F] : '=';
    }
    out[n] = '\0';
    return n;
}

Protocol::Protocol(store::Store& store, station::Station& station, Host& host) : store_(store), station_(station), host_(host) {}

void Protocol::begin() {
    uint8_t bytes[BOOT_HEX / 2];
    host_.randomBytes(bytes, sizeof(bytes));
    hexstr::encode(bytes, sizeof(bytes), boot_);
}

void Protocol::connected(uint32_t nowMs) {
    connected_ = true;
    synced_ = false;
    lostSync_ = nullptr;
    snap_ = Snap();
    outStart_ = outCount_ = 0;   // wiersze poprzedniej sesji nie trafią do nowej
    seqOut_ = 0;
    seqIn_ = 0;
    lineLength_ = 0;
    overflow_ = false;
    lastSentMs_ = nowMs;
    hello();
}

void Protocol::disconnected() {
    connected_ = false;
    synced_ = false;
    lostSync_ = nullptr;
    snap_ = Snap();
    outStart_ = outCount_ = 0;
    lineLength_ = 0;
    overflow_ = false;
    xfer_ = Xfer();
    if (pending()) { host_.confirmEnd(); pending_ = Pending(); }   // pytanie bez odbiorcy odpowiedzi
}

void Protocol::feed(const char* bytes, size_t count, uint32_t nowMs) {
    for (size_t i = 0; i < count; ++i) {
        const char c = bytes[i];
        if (c == '\n') {
            if (lineLength_ && line_[lineLength_ - 1] == '\r') --lineLength_;   // CR przed LF pomijany
            if (overflow_) { ++stats_.overflow; rejected(-1, "too_long"); }
            else if (lineLength_) { line_[lineLength_] = '\0'; handleLine(line_, nowMs); }
            lineLength_ = 0;
            overflow_ = false;
        } else if (overflow_) {
            continue;
        } else if (c == '\0' || lineLength_ == MAX_LINE) {
            overflow_ = true;   // bajt NUL albo wiersz ponad 1024 B: cały wiersz odrzucony
            lineLength_ = 0;
        } else {
            line_[lineLength_++] = c;
        }
    }
}

void Protocol::send(const char* type, int64_t re, const char* fields) { push(type, re, fields, OUT_BYTES); }

bool Protocol::push(const char* type, int64_t re, const char* fields, size_t reserve) {
    // reserve = OUT_BYTES: odpowiedź, dla której wejście zostawiło miejsce (brak miejsca to błąd programu);
    // inaczej wiersz z inicjatywy stacji (zdarzenie, migawka): tylko gdy zostanie reserve wolnych bajtów.
    char line[LINE_ROOM + 1];   // wiersz, LF i NUL
    size_t n = 0;
    bool ok = appendf(line, sizeof(line), n, "{\"usb\":%u,\"seq\":%lu,\"type\":\"%s\"", static_cast<unsigned>(CONTRACT),
                      static_cast<unsigned long>(seqOut_ + 1), type);
    if (re >= 0) ok = ok && appendf(line, sizeof(line), n, ",\"re\":%lld", static_cast<long long>(re));
    if (fields && *fields) ok = ok && appendf(line, sizeof(line), n, ",%s", fields);
    ok = ok && appendf(line, sizeof(line), n, "}\n");
    if (!ok) { host_.log("usb: reply too long"); return true; }
    const bool reply = reserve == OUT_BYTES;
    if (n > room() || (!reply && n + reserve > room())) {
        if (reply) { ++stats_.dropped; host_.log("usb: output queue full"); }
        return false;
    }
    ++seqOut_;
    ++stats_.linesOut;
    for (size_t i = 0; i < n; ++i) out_[(outStart_ + outCount_ + i) % OUT_BYTES] = line[i];
    outCount_ += n;
    return true;
}

const char* Protocol::output(size_t& length) const {
    length = outStart_ + outCount_ <= OUT_BYTES ? outCount_ : OUT_BYTES - outStart_;
    return out_ + outStart_;
}

void Protocol::consume(size_t length) {
    if (length > outCount_) length = outCount_;
    outStart_ = (outStart_ + length) % OUT_BYTES;
    outCount_ -= length;
    if (!outCount_) outStart_ = 0;
}

void Protocol::rejected(int64_t re, const char* reason, const char* detail) {
    char fields[96];
    if (detail) snprintf(fields, sizeof(fields), "\"reason\":\"%s\",\"detail\":\"%s\"", reason, detail);
    else snprintf(fields, sizeof(fields), "\"reason\":\"%s\"", reason);
    ++stats_.rejected;
    send("rejected", re, fields);
}

void Protocol::hello() {
    uint8_t key[64], lxmf[store::HASH];
    char lxmfHex[2 * store::HASH + 1] = "", epoch[2 * store::EPOCH + 1];
    if (store_.station() && host_.identity(key, lxmf)) hexstr::encode(lxmf, store::HASH, lxmfHex);
    hexstr::encode(store_.meta().epoch, store::EPOCH, epoch);
    char fields[400];
    snprintf(fields, sizeof(fields),
             "\"boot\":\"%s\",\"contracts\":[%u],\"name\":\"%s\",\"lxmf\":\"%s\",\"fw\":\"%s\",\"role\":\"%s\",\"prep\":%s,"
             "\"configured\":%s,\"epoch\":\"%s\",\"head\":%lu,\"min\":%lu,\"migration\":\"none\"",
             boot_, static_cast<unsigned>(CONTRACT), host_.stationName(), lxmfHex, host_.version(),
             store_.configured() && !store_.station() ? "wezel" : "stacja", boolName(host_.prep()), boolName(store_.configured()), epoch,
             static_cast<unsigned long>(store_.head()), static_cast<unsigned long>(store_.minEvent()));
    send("hello", -1, fields);
}

void Protocol::handleLine(const char* line, uint32_t nowMs) {
    ++stats_.linesIn;
    json::Value msg, v;
    int64_t usb = 0, seq = -1;
    char type[24] = "";
    if (!json::parse(line, msg) || msg.kind != json::Kind::OBJECT) { rejected(-1, "invalid", "json"); return; }
    if (!json::field(msg, "seq", v) || !json::integer(v, seq) || seq < 1 || seq > 0xFFFFFFFFLL) { rejected(-1, "seq"); return; }
    // `seq` rośnie o 1 w sesji; każdy wiersz z poprawnym `seq` go zużywa (także odmowa `contract`),
    // a po odmowie `seq` stacja liczy dalej od numeru laptopa.
    const bool inOrder = seq == seqIn_ + 1;
    seqIn_ = seq;
    if (!json::field(msg, "usb", v) || !json::integer(v, usb) || usb != CONTRACT) {
        rejected(seq, "contract");
        hello();
        return;
    }
    if (!inOrder) { rejected(seq, "seq"); return; }
    if (!json::field(msg, "type", v) || !json::string(v, type, sizeof(type))) { rejected(seq, "invalid", "type"); return; }
    for (char* c = type; *c; ++c) if (*c < 0x21 || *c > 0x7E) *c = '?';   // do dziennika tylko drukowalne ASCII
    if (strcmp(type, "ack")) {   // każde polecenie w dzienniku; ack nie jest poleceniem
        char text[40];
        snprintf(text, sizeof(text), "usb %s", type);
        host_.log(text);
    }
    dispatch(type, msg, seq, nowMs);
}

void Protocol::dispatch(const char* type, const json::Value& msg, int64_t seq, uint32_t nowMs) {
    const Command* c = nullptr;
    for (const Command& command : COMMANDS) if (!strcmp(type, command.type)) c = &command;
    if (!c) { rejected(seq, "unknown_type"); return; }
    char bad[24];
    if (strcmp(type, "migrate") && strcmp(type, "xfer_begin") && !checkFields(msg, *c, bad, sizeof(bad))) { rejected(seq, "invalid", bad); return; }
    if (pending() && strcmp(type, "ack") && strcmp(type, "status")) { rejected(seq, "busy"); return; }
    if (c->mode == PREP && !host_.prep()) { rejected(seq, "prep_required"); return; }
    if (c->mode == STATION && store_.configured() && !store_.station()) { rejected(seq, "role"); return; }
    if (!strcmp(type, "sync")) doSync(msg, seq, nowMs);
    else if (!strcmp(type, "ack")) doAck(msg, nowMs);
    else if (!strcmp(type, "snapshot")) doSnapshot(msg, seq);
    else if (!strcmp(type, "submit")) doSubmit(msg, seq);
    else if (!strcmp(type, "cancel")) doCancel(msg, seq);
    else if (!strcmp(type, "test")) doTest(msg, seq);
    else if (!strcmp(type, "announce")) {
        // Polecenia w ciągu 30 s łączone w jedno ogłoszenie.
        if (announced_ && nowMs - announceMs_ < ANNOUNCE_MERGE_MS) { send("ok", seq, ""); return; }
        if (!host_.announce()) { rejected(seq, "busy"); return; }
        announced_ = true;
        announceMs_ = nowMs;
        send("ok", seq, "");
    } else if (!strcmp(type, "silence")) doSilence(msg, seq, nowMs);
    else if (!strcmp(type, "mark_read")) {
        // Numer wiadomości to numer zdarzenia; wiadomość, która wypadła już ze skrzynki, daje `ok` (ponowienie).
        const uint32_t number = intField(msg, "msg");
        if (!number || number > store_.head()) rejected(seq, "invalid", "msg");
        else if (store_.findMessage(number) >= 0 && !station_.markRead(number)) rejected(seq, "memory");
        else send("ok", seq, "");
    } else if (!strcmp(type, "status")) doStatus(seq);
    else if (!strcmp(type, "close")) doClose(msg, seq, nowMs);
    else if (!strcmp(type, "destroy")) {
        pending_ = Pending();
        pending_.type = Pending::DESTROY;
        pending_.seq = seq;
        pending_.sinceMs = nowMs;
        host_.confirmBegin(Question::DESTROY, "");
        send("pending", seq, "\"confirm_s\":30");
    } else if (!strcmp(type, "card")) doCard(seq);
    else if (!strcmp(type, "xfer_begin")) doXferBegin(msg, seq, nowMs);
    else if (!strcmp(type, "xfer_part")) doXferPart(msg, seq, nowMs);
    else if (!strcmp(type, "xfer_read")) doXferRead(msg, seq, nowMs);
    else if (!strcmp(type, "xfer_commit")) doXferCommit(msg, seq);
    else if (!strcmp(type, "xfer_abort")) { xfer_ = Xfer(); send("ok", seq, ""); }
    else rejected(seq, "migration", "unsupported");   // PRZENIEŚ STACJĘ jeszcze nie ma (F107)
}

// --- Synchronizacja --------------------------------------------------------------------------

void Protocol::doSync(const json::Value& msg, int64_t seq, uint32_t nowMs) {
    json::Value v;
    char epochText[2 * store::EPOCH + 2];
    uint8_t epoch[store::EPOCH] = {};
    json::field(msg, "epoch", v);
    if (!json::string(v, epochText, sizeof(epochText)) || (epochText[0] && !hexstr::decode(epochText, epoch, store::EPOCH))) {
        rejected(seq, "invalid", "epoch");
        return;
    }
    const uint32_t cursor = intField(msg, "cursor");
    const uint32_t head = store_.head(), min = store_.minEvent();
    char current[2 * store::EPOCH + 1], fields[160];
    hexstr::encode(store_.meta().epoch, store::EPOCH, current);
    const char* reason = !epochText[0] || memcmp(epoch, store_.meta().epoch, store::EPOCH) ? "epoch"
                         : cursor > head                                                     ? "ahead"
                         : cursor + 1 < min                                                  ? "gap"
                                                                                             : nullptr;
    synced_ = false;
    lostSync_ = nullptr;
    if (reason) {
        sendSnapRequired(seq, reason, OUT_BYTES);
        return;
    }
    snprintf(fields, sizeof(fields), "\"epoch\":\"%s\",\"from\":%lu,\"head\":%lu", current, static_cast<unsigned long>(cursor + 1),
             static_cast<unsigned long>(head));
    send("sync_ok", seq, fields);
    synced_ = true;
    memcpy(syncedEpoch_, store_.meta().epoch, store::EPOCH);
    cursor_ = cursor;
    nextEv_ = cursor + 1;
    lastSentMs_ = nowMs - RESEND_MS;
}

void Protocol::doAck(const json::Value& msg, uint32_t nowMs) {
    uint8_t epoch[store::EPOCH];
    const uint32_t cursor = intField(msg, "cursor");
    if (!synced_ || !json::hexField(msg, "epoch", epoch, store::EPOCH) || memcmp(epoch, syncedEpoch_, store::EPOCH) || cursor > store_.head()) return;
    if (cursor > cursor_) {
        cursor_ = cursor;
        // `ack` spóźniony wobec ponowienia potwierdza zdarzenia przed nextEv_: wysyłka idzie dalej od cursor + 1.
        if (nextEv_ <= cursor_) nextEv_ = cursor_ + 1;
        if (cursor_ + 1 >= nextEv_) lastSentMs_ = nowMs;   // wszystko potwierdzone: następne bez czekania na ponowienie
    }
}

bool Protocol::sendSnapRequired(int64_t re, const char* reason, size_t reserve) {
    char current[2 * store::EPOCH + 1], fields[160];
    hexstr::encode(store_.meta().epoch, store::EPOCH, current);
    snprintf(fields, sizeof(fields), "\"epoch\":\"%s\",\"head\":%lu,\"min\":%lu,\"reason\":\"%s\"", current,
             static_cast<unsigned long>(store_.head()), static_cast<unsigned long>(store_.minEvent()), reason);
    return push("snap_required", re, fields, reserve);
}

// Strumień zdarzeń nie może iść dalej (nowa epoka, zdarzenie nadpisane albo nieczytelne): laptop dostaje
// `snap_required` bez `re` i robi migawkę; bez tego czekałby na zdarzenia, które nie przyjdą.
void Protocol::loseSync(const char* reason) {
    synced_ = false;
    lostSync_ = reason;
}

bool Protocol::sendEvent(const store::Event& e) {
    char fields[MAX_LINE - 64], hex[2 * store::HASH + 1];
    size_t n = 0;
    hexstr::encode(store_.meta().epoch, store::EPOCH, hex);
    appendf(fields, sizeof(fields), n, "\"epoch\":\"%s\",\"ev\":%lu,\"at\":%lu,", hex, static_cast<unsigned long>(e.ev),
            static_cast<unsigned long>(e.at));
    switch (e.kind) {
        case store::EventKind::OWN: {
            const store::RequestIndex& x = store_.request(e.slot);
            store::Request r;
            if (!x.used() || x.gen != e.gen || !store_.readRequest(e.slot, r)) {
                appendf(fields, sizeof(fields), n, "\"kind\":\"own\",\"revision\":%u,\"lost\":true", e.revision);
                break;
            }
            hexstr::encode(r.id, store::HASH, hex);
            appendf(fields, sizeof(fields), n, "\"kind\":\"own\",\"id\":\"%s\",\"revision\":%u,\"origin\":\"%s\"", hex, e.revision,
                    e.a == store::USB ? "usb" : "buttons");
            if (e.revision == r.rMax) appendf(fields, sizeof(fields), n, ",\"sa1\":%s", r.sa1);
            else appendf(fields, sizeof(fields), n, ",\"superseded\":true");
            if (r.type == sa1::TEST) {
                char nonce[2 * store::NONCE + 1];
                hexstr::encode(r.nonce, store::NONCE, nonce);
                appendf(fields, sizeof(fields), n, ",\"nonce\":\"%s\"", nonce);
            }
            break;
        }
        case store::EventKind::STAGE: {
            const store::StageCode code = static_cast<store::StageCode>(e.a);
            appendf(fields, sizeof(fields), n, "\"kind\":\"stage\",\"revision\":%u,\"stage\":\"%s\"", e.revision, store::stageCodeName(code));
            if (code == store::StageCode::RELEASED) {
                store::Released rel;
                if (store_.releasedAt(e.slot, rel) && rel.ev == e.ev) {   // wpis mógł zostać zajęty od nowa po odtworzeniu
                    hexstr::encode(rel.id, store::HASH, hex);
                    appendf(fields, sizeof(fields), n, ",\"id\":\"%s\"", hex);
                } else appendf(fields, sizeof(fields), n, ",\"lost\":true");
                break;
            }
            const store::RequestIndex& x = store_.request(e.slot);
            store::Request r;
            if (x.used() && x.gen == e.gen && store_.readRequest(e.slot, r)) {
                hexstr::encode(r.id, store::HASH, hex);
                const uint32_t now = store_.now();
                const uint32_t next = r.rMax == e.revision && r.stage <= store::Stage::DELIVERED && r.nextTryS > now ? r.nextTryS - now : 0;
                appendf(fields, sizeof(fields), n, ",\"id\":\"%s\",\"next_s\":%lu", hex, static_cast<unsigned long>(next));
            } else appendf(fields, sizeof(fields), n, ",\"lost\":true");
            appendf(fields, sizeof(fields), n, ",\"attempt\":%u,\"decision\":%u,\"decision_rev\":%u,\"status_event\":%lu", e.attempt, e.decision,
                    e.decisionRev, static_cast<unsigned long>(e.value));
            break;
        }
        case store::EventKind::MSG: {
            appendf(fields, sizeof(fields), n, "\"kind\":\"msg\",\"msg\":%lu,\"from\":\"%s\"", static_cast<unsigned long>(e.ev),
                    e.a == config::BACKUP ? "backup" : "main");
            const store::MessageIndex& x = store_.message(e.slot);
            store::Message m;
            if (x.used() && x.gen == e.gen && x.number == e.ev && store_.readMessage(e.slot, m)) appendf(fields, sizeof(fields), n, ",\"sa1\":%s", m.sa1);
            else appendf(fields, sizeof(fields), n, ",\"lost\":true");
            break;
        }
        case store::EventKind::RADIO: {
            // Wyjątek z chwili zdarzenia (odwołanie w zdarzeniu), nie z bieżącego meta.
            uint8_t id[store::HASH];
            const bool known = store_.exceptionId(e, id);
            appendf(fields, sizeof(fields), n, "\"kind\":\"radio\",");
            n += radioFields(fields + n, sizeof(fields) - n, e.a, known ? id : nullptr, e.revision, (e.a & store::RADIO_EXCEPTION) && !known);
            break;
        }
        case store::EventKind::STATION:
            appendf(fields, sizeof(fields), n, "\"kind\":\"station\",\"what\":\"%s\",\"detail\":%lu", e.a < 4 ? STATION_WHAT[e.a] : "?",
                    static_cast<unsigned long>(e.value));
            break;
    }
    // Zdarzenie tylko z miejscem w kolejce; przy pytaniu przyciskiem miejsce na jego odpowiedź zostaje.
    return push("event", -1, fields, pending() ? PENDING_RESERVE : 0);
}

size_t Protocol::requestFields(const store::Request& r, char* out, size_t size) {
    char id[2 * store::HASH + 1], number[5];
    hexstr::encode(r.id, store::HASH, id);
    numberText(store::shortNumber(r.id), number);
    size_t n = 0;
    appendf(out, size, n,
            "\"item\":\"request\",\"id\":\"%s\",\"revision\":%u,\"sa1\":%s,\"stage\":\"%s\",\"decision\":%u,\"decision_rev\":%u,"
            "\"status_event\":%lu,\"reply_event\":%lu,\"number\":\"%s\"",
            id, r.rMax, r.sa1, store::stageCodeName(static_cast<store::StageCode>(r.stage)), r.decision, r.decisionRev,
            static_cast<unsigned long>(r.statusHi), static_cast<unsigned long>(r.replyHi), number);
    if (r.type == sa1::TEST) {
        char nonce[2 * store::NONCE + 1];
        hexstr::encode(r.nonce, store::NONCE, nonce);
        appendf(out, size, n, ",\"nonce\":\"%s\"", nonce);
    }
    return n;
}

void Protocol::doSnapshot(const json::Value& msg, int64_t seq) {
    uint8_t epoch[store::EPOCH];
    if (!json::hexField(msg, "epoch", epoch, store::EPOCH) || memcmp(epoch, store_.meta().epoch, store::EPOCH)) { rejected(seq, "invalid", "epoch"); return; }
    size_t count = store_.requestCount() + store_.messageCount();
    for (size_t i = 0; i < store::RELEASED_ENTRIES; ++i) count += store_.releasedUsed(i);
    char hex[2 * store::EPOCH + 1], fields[160];
    hexstr::encode(epoch, store::EPOCH, hex);
    snprintf(fields, sizeof(fields), "\"epoch\":\"%s\",\"head\":%lu,\"count\":%u,\"tomb_floor\":%lu", hex, static_cast<unsigned long>(store_.head()),
             static_cast<unsigned>(count), static_cast<unsigned long>(store_.meta().tombFloor));
    send("snap_begin", seq, fields);
    snap_ = Snap();
    snap_.active = true;
    snap_.seq = seq;
    snap_.head = store_.head();
    snap_.changes = store_.changes();
    memcpy(snap_.epoch, epoch, store::EPOCH);
    continueSnapshot();
}

void Protocol::continueSnapshot() {
    // Wiersze w miarę miejsca w kolejce. Migawka opisuje jeden stan: każda zatwierdzona zmiana danych
    // w jej trakcie (ze zdarzeniem albo bez, np. odczyt wiadomości na ekranie, także nowa epoka) kończy
    // ją odmową `stale` (laptop powtarza `snapshot`).
    char fields[MAX_LINE - 64];
    while (snap_.active) {
        if (store_.changes() != snap_.changes) {
            if (room() < LINE_ROOM) return;   // odpowiedź końcowa przy pustej kolejce
            snap_.active = false;
            rejected(snap_.seq, "stale");
            return;
        }
        const Snap before = snap_;
        if (snapItem(fields, sizeof(fields))) {
            if (!push("snap", snap_.seq, fields, 0)) { snap_ = before; return; }   // wiersz czeka na miejsce
            continue;
        }
        if (room() < LINE_ROOM) return;
        char hex[2 * store::EPOCH + 1];
        hexstr::encode(snap_.epoch, store::EPOCH, hex);
        snprintf(fields, sizeof(fields), "\"epoch\":\"%s\",\"head\":%lu", hex, static_cast<unsigned long>(snap_.head));
        snap_.active = false;
        send("snap_end", snap_.seq, fields);
        // Laptop stosuje migawkę z kursorem (epoch, head); dalsze zdarzenia idą od head + 1.
        synced_ = true;
        memcpy(syncedEpoch_, snap_.epoch, store::EPOCH);
        cursor_ = snap_.head;
        nextEv_ = cursor_ + 1;
        return;
    }
}

bool Protocol::snapItem(char* fields, size_t size) {
    // Następny wpis migawki: rejestr (faza 0), pamięć zwolnionych wpisów (1), skrzynka (2); false na końcu.
    for (; snap_.phase == 0 && snap_.index < store::REGISTER_SLOTS; ++snap_.index) {
        store::Request r;
        if (store_.request(snap_.index).used() && store_.readRequest(snap_.index, r) && requestFields(r, fields, size)) { ++snap_.index; return true; }
    }
    if (snap_.phase == 0) { snap_.phase = 1; snap_.index = 0; }
    for (; snap_.phase == 1 && snap_.index < store::RELEASED_ENTRIES; ++snap_.index) {
        store::Released rel;
        if (!store_.releasedAt(snap_.index, rel)) continue;
        char id[2 * store::HASH + 1], number[5];
        hexstr::encode(rel.id, store::HASH, id);
        numberText(rel.number, number);
        snprintf(fields, size, "\"item\":\"released\",\"id\":\"%s\",\"revision\":%u,\"ev\":%lu,\"number\":\"%s\"", id, rel.revision,
                 static_cast<unsigned long>(rel.ev), number);
        ++snap_.index;
        return true;
    }
    if (snap_.phase == 1) { snap_.phase = 2; snap_.index = 0; }
    for (; snap_.index < store::INBOX_SLOTS; ++snap_.index) {
        store::Message m;
        if (!store_.message(snap_.index).used() || !store_.readMessage(snap_.index, m)) continue;
        snprintf(fields, size, "\"item\":\"msg\",\"msg\":%lu,\"from\":\"%s\",\"received_at\":%lu,\"read\":%s,\"sa1\":%s",
                 static_cast<unsigned long>(m.number), m.source == config::BACKUP ? "backup" : "main", static_cast<unsigned long>(m.receivedS),
                 boolName(m.read), m.sa1);
        ++snap_.index;
        return true;
    }
    return false;
}

// --- Polecenia -------------------------------------------------------------------------------

void Protocol::stored(int64_t seq, const station::Stored& s) {
    char fields[160], id[2 * store::HASH + 1], number[5];
    hexstr::encode(s.id, store::HASH, id);
    numberText(s.number, number);
    snprintf(fields, sizeof(fields), "\"id\":\"%s\",\"revision\":%u,\"number\":\"%s\",\"duplicate\":%s%s", id, s.revision, number,
             boolName(s.duplicate), s.released ? ",\"released\":true" : "");
    ++stats_.stored;
    send("stored", seq, fields);
}

void Protocol::doSubmit(const json::Value& msg, int64_t seq) {
    json::Value array, v;
    sa1::Message m;
    json::field(msg, "sa1", array);
    if (array.length > sa1::MAX_CONTENT) { rejected(seq, "invalid", "sa1"); return; }
    const char* why = sa1::decode(array.begin, array.length, m);
    if (why || (m.type != sa1::REQUEST && m.type != sa1::TEST)) { rejected(seq, "invalid", "sa1"); return; }
    char id[sa1::ID_HEX + 2];
    json::field(msg, "id", v);
    if (!json::string(v, id, sizeof(id)) || strcmp(id, m.id)) { rejected(seq, "invalid", "id"); return; }
    if (intField(msg, "revision") != m.revision) { rejected(seq, "invalid", "revision"); return; }
    station::Stored s;
    const station::Result result = station_.submit(m, s);
    if (result == station::Result::STORED || result == station::Result::DUPLICATE) stored(seq, s);
    else rejected(seq, station::resultName(result));
}

void Protocol::doCancel(const json::Value& msg, int64_t seq) {
    uint8_t id[store::HASH];
    if (!json::hexField(msg, "id", id, store::HASH)) { rejected(seq, "invalid", "id"); return; }
    bool released = false;
    const station::Result result = station_.cancel(id, released);
    if (result == station::Result::STORED) send("ok", seq, released ? "\"released\":true" : "");
    else rejected(seq, station::resultName(result), result == station::Result::NOT_FOUND ? "id" : nullptr);
}

void Protocol::doTest(const json::Value& msg, int64_t seq) {
    uint8_t nonce[store::NONCE];
    if (!json::hexField(msg, "nonce", nonce, store::NONCE)) { rejected(seq, "invalid", "nonce"); return; }
    station::Stored s;
    const station::Result result = station_.test(nonce, s);
    if (result == station::Result::STORED) stored(seq, s);
    else if (result == station::Result::INVALID) rejected(seq, "invalid", "paused");   // TEST wstrzymany (WSTRZYMAJ)
    else rejected(seq, station::resultName(result));
}

void Protocol::doSilence(const json::Value& msg, int64_t seq, uint32_t nowMs) {
    json::Value v;
    json::field(msg, "on", v);
    Pending p;
    p.type = Pending::SILENCE;
    p.on = v.kind == json::Kind::TRUE_;
    p.exceptionSet = json::field(msg, "exception_id", v);
    // Wyjątek tylko przy włączaniu ciszy z panelu; przełącznik CISZA ma pierwszeństwo i go wyklucza.
    // Wyjątek obejmuje wpis rejestru (para id, r_max z chwili potwierdzenia); id spoza rejestru: `invalid`.
    if (p.exceptionSet && (!p.on || !json::hexField(msg, "exception_id", p.exception, store::HASH) || store_.findRequest(p.exception) < 0)) {
        rejected(seq, "invalid", "exception_id");
        return;
    }
    if (host_.silenceSwitch() && (!p.on || p.exceptionSet)) { rejected(seq, "silence_switch"); return; }
    // Klucz powtórzenia to stan docelowy: stan już osiągnięty daje `ok` bez pytania i bez zdarzenia.
    const store::Meta& m = store_.meta();
    const int slot = p.exceptionSet ? store_.findRequest(p.exception) : -1;
    if (m.silence == p.on && m.exceptionSet == p.exceptionSet &&
        (!p.exceptionSet || (!memcmp(m.exception, p.exception, store::HASH) && m.exceptionRev == store_.request(static_cast<size_t>(slot)).rMax))) {
        char fields[160];
        currentRadioFields(fields, sizeof(fields));
        send("ok", seq, fields);
        return;
    }
    p.seq = seq;
    p.sinceMs = nowMs;
    pending_ = p;
    char number[5] = "";
    if (p.exceptionSet) numberText(store::shortNumber(p.exception), number);
    host_.confirmBegin(p.exceptionSet ? Question::SILENCE_EXCEPTION : p.on ? Question::SILENCE_ON : Question::SILENCE_OFF, number);
    send("pending", seq, "\"confirm_s\":30");
}

void Protocol::doClose(const json::Value& msg, int64_t seq, uint32_t nowMs) {
    Pending p;
    p.type = Pending::CLOSE;
    if (!json::hexField(msg, "epoch", p.epoch, store::EPOCH)) { rejected(seq, "invalid", "epoch"); return; }
    p.head = intField(msg, "head");
    // Powtórzone `close` z zapamiętaną parą: ten sam wynik bez drugiego usunięcia i bez pytania.
    const store::Meta& m = store_.meta();
    if (m.closedSet && !memcmp(m.closedEpoch, p.epoch, store::EPOCH) && m.closedHead == p.head) {
        char fields[64], hex[2 * store::EPOCH + 1];
        hexstr::encode(m.epoch, store::EPOCH, hex);
        snprintf(fields, sizeof(fields), "\"epoch\":\"%s\",\"duplicate\":true", hex);
        send("ok", seq, fields);
        return;
    }
    p.seq = seq;
    p.sinceMs = nowMs;
    pending_ = p;
    host_.confirmBegin(Question::CLOSE, "");
    send("pending", seq, "\"confirm_s\":30");
}

size_t Protocol::radioFields(char* out, size_t size, uint8_t bits, const uint8_t* exception, uint16_t revision, bool lost) {
    // Pola ciszy z bitów store::radioBits i wyjątku (id, rewizja); exception = nullptr: id nieznane
    // (`lost`: wpis zdarzenia opuścił rejestr i pamięć zwolnionych wpisów).
    const bool silence = bits & store::RADIO_SILENCE, excepted = bits & store::RADIO_EXCEPTION;
    char hex[2 * store::HASH + 1] = "";
    if (excepted && exception) hexstr::encode(exception, store::HASH, hex);
    size_t n = 0;
    appendf(out, size, n, "\"silence\":%s,\"silence_source\":%s,\"exception_id\":%s%s%s", boolName(silence),
            !silence ? "null" : (bits & store::RADIO_SWITCH) ? "\"switch\"" : "\"panel\"", hex[0] ? "\"" : "null", hex, hex[0] ? "\"" : "");
    if (excepted) appendf(out, size, n, ",\"exception_revision\":%u", static_cast<unsigned>(revision));
    else appendf(out, size, n, ",\"exception_revision\":null");
    if (lost) appendf(out, size, n, ",\"lost\":true");
    return n;
}

size_t Protocol::currentRadioFields(char* out, size_t size) {
    const store::Meta& m = store_.meta();
    return radioFields(out, size, store::radioBits(m, host_.silenceSwitch()), m.exception, m.exceptionRev);
}

void Protocol::finishPending(bool confirmed) {
    const Pending p = pending_;
    pending_ = Pending();
    host_.confirmEnd();
    if (!confirmed) { host_.log("usb command not confirmed"); rejected(p.seq, "not_confirmed"); return; }
    char fields[160];
    switch (p.type) {
        case Pending::SILENCE:
            if (!p.on && host_.silenceSwitch()) { rejected(p.seq, "silence_switch"); return; }
            if (!station_.setSilence(p.on, p.exceptionSet ? p.exception : nullptr, host_.silenceSwitch())) { rejected(p.seq, "memory"); return; }
            currentRadioFields(fields, sizeof(fields));
            send("ok", p.seq, fields);
            return;
        case Pending::CLOSE: {
            // Warunek sprawdzany po potwierdzeniu, przed jedną transakcją nowej epoki.
            if (memcmp(p.epoch, store_.meta().epoch, store::EPOCH) || !store_.quietSince(p.head)) { rejected(p.seq, "stale"); return; }
            if (!store_.close(p.head)) { rejected(p.seq, "memory"); return; }
            synced_ = false;
            char hex[2 * store::EPOCH + 1];
            hexstr::encode(store_.meta().epoch, store::EPOCH, hex);
            snprintf(fields, sizeof(fields), "\"epoch\":\"%s\",\"duplicate\":false", hex);
            send("ok", p.seq, fields);
            return;
        }
        case Pending::DESTROY:
            if (!host_.destroy()) { rejected(p.seq, "memory"); return; }
            synced_ = false;
            send("ok", p.seq, "");
            return;
        case Pending::NONE: return;
    }
}

void Protocol::doStatus(int64_t seq) {
    const store::Meta& m = store_.meta();
    char fields[MAX_LINE - 64], radio[160], power[160], diag[200];
    currentRadioFields(radio, sizeof(radio));
    host_.power(power, sizeof(power));
    host_.diag(diag, sizeof(diag));
    uint32_t oldest = 0;
    (void)store_.unsent(oldest);
    const uint32_t now = store_.now();
    char contact[16] = "null";
    if (m.contactKnown) snprintf(contact, sizeof(contact), "%lu", static_cast<unsigned long>(now > m.contactS ? now - m.contactS : 0));
    snprintf(fields, sizeof(fields),
             "\"role\":\"%s\",\"prep\":%s,\"configured\":%s,\"config_seq\":%lu,\"fw\":\"%s\",\"secure_version\":0,\"fram_format\":%lu,"
             "\"uptime\":%lu,\"register\":%u,\"intents\":%u,\"inbox\":%u,\"unread\":%u,\"receiver\":\"%s\",\"last_contact\":%s,"
             "\"last_contact_lower\":%s,%s,\"power\":{%s},\"migration\":\"none\",\"mid\":\"\",\"diag\":{%s}",
             store_.configured() && !store_.station() ? "wezel" : "stacja", boolName(host_.prep()), boolName(store_.configured()),
             static_cast<unsigned long>(store_.config().seq), host_.version(), static_cast<unsigned long>(journal::FRAM_FORMAT),
             static_cast<unsigned long>(host_.counterS()), static_cast<unsigned>(store_.requestCount()), static_cast<unsigned>(store_.activeIntents()),
             static_cast<unsigned>(store_.messageCount()), static_cast<unsigned>(store_.unread()), m.receiver == config::BACKUP ? "backup" : "main",
             contact, boolName(m.contactKnown && host_.contactBeforeStart()), radio, power, diag);
    send("status", seq, fields);
}

void Protocol::doCard(int64_t seq) {
    uint8_t key[64], lxmf[store::HASH], digest[32];
    if (!store_.station() || !host_.identity(key, lxmf)) { rejected(seq, "not_configured"); return; }
    char keyHex[129], lxmfHex[2 * store::HASH + 1], fingerprint[24];
    hexstr::encode(key, sizeof(key), keyHex);
    hexstr::encode(lxmf, store::HASH, lxmfHex);
    sha2::digest(key, sizeof(key), digest);
    // Odcisk: pierwsze 8 B SHA-256 klucza w grupach po 4 cyfry; ekran pokazuje go jednocześnie.
    char hex[17];
    hexstr::encode(digest, 8, hex);
    snprintf(fingerprint, sizeof(fingerprint), "%.4s %.4s %.4s %.4s", hex, hex + 4, hex + 8, hex + 12);
    char fields[MAX_LINE - 64];
    size_t n = 0;
    appendf(fields, sizeof(fields), n, "\"name\":\"%s\",\"lxmf\":\"%s\",\"key\":\"%s\",\"address\":[", host_.stationName(), lxmfHex, keyHex);
    for (size_t i = 0; i < store_.addressCount(); ++i) appendf(fields, sizeof(fields), n, "%s\"%s\"", i ? "," : "", store_.addressAt(i));
    if (!appendf(fields, sizeof(fields), n, "],\"fingerprint\":\"%s\"", fingerprint)) { rejected(seq, "size"); return; }
    host_.showCard(fingerprint);
    send("card", seq, fields);
}

// --- Transfery -------------------------------------------------------------------------------

bool Protocol::xferOpen(const json::Value& msg, int64_t seq, uint32_t nowMs) {
    json::Value v;
    char text[12];
    uint32_t id = 0;
    if (!json::field(msg, "xfer", v) || !json::string(v, text, sizeof(text)) || strlen(text) != 8 ||
        !hexstr::decode(text, reinterpret_cast<uint8_t*>(&id), sizeof(id)) || xfer_.op == Xfer::NONE || id != xfer_.id) {
        rejected(seq, "invalid", "xfer");
        return false;
    }
    xfer_.lastMs = nowMs;
    return true;
}

void Protocol::doXferBegin(const json::Value& msg, int64_t seq, uint32_t nowMs) {
    json::Value v;
    char op[16] = "";
    json::field(msg, "op", v);
    if (!json::string(v, op, sizeof(op))) { rejected(seq, "invalid", "op"); return; }
    static const Command configure = {"xfer_begin", PREP, {{"op", F::STR, true}, {"size", F::INT, true}, {"sha256", F::STR, true}}, 3};
    static const Command configGet = {"xfer_begin", PREP, {{"op", F::STR, true}}, 1};
    const bool put = !strcmp(op, "configure");
    if (!put && strcmp(op, "config_get")) {
        // import, export, firmware: PRZENIEŚ STACJĘ i aktualizacja jeszcze nie ma (F107).
        rejected(seq, !strcmp(op, "import") || !strcmp(op, "export") ? "migration" : "invalid", "op");
        return;
    }
    char bad[24];
    if (!checkFields(msg, put ? configure : configGet, bad, sizeof(bad))) { rejected(seq, "invalid", bad); return; }
    xfer_ = Xfer();   // nowy transfer porzuca poprzedni
    if (put) {
        xfer_.size = intField(msg, "size");
        if (xfer_.size == 0 || xfer_.size > config::DOC_MAX) { rejected(seq, "size"); return; }
        if (!json::hexField(msg, "sha256", xfer_.sha, sizeof(xfer_.sha))) { rejected(seq, "invalid", "sha256"); return; }
        if (!store_.configBegin()) { rejected(seq, "memory"); return; }
        xfer_.op = Xfer::CONFIGURE;
    } else {
        if (!store_.configured()) { rejected(seq, "not_configured"); return; }
        xfer_.op = Xfer::CONFIG_GET;
        xfer_.size = store_.configSize();
        memcpy(xfer_.sha, store_.configSha(), sizeof(xfer_.sha));
    }
    host_.randomBytes(reinterpret_cast<uint8_t*>(&xfer_.id), sizeof(xfer_.id));
    xfer_.lastMs = nowMs;
    char id[9], sha[65], fields[160];
    hexstr::encode(reinterpret_cast<const uint8_t*>(&xfer_.id), sizeof(xfer_.id), id);
    hexstr::encode(xfer_.sha, sizeof(xfer_.sha), sha);
    if (put) snprintf(fields, sizeof(fields), "\"xfer\":\"%s\",\"max_part\":%u", id, static_cast<unsigned>(PART_MAX));
    else snprintf(fields, sizeof(fields), "\"xfer\":\"%s\",\"size\":%lu,\"sha256\":\"%s\"", id, static_cast<unsigned long>(xfer_.size), sha);
    send("ok", seq, fields);
}

void Protocol::doXferPart(const json::Value& msg, int64_t seq, uint32_t nowMs) {
    if (!xferOpen(msg, seq, nowMs)) return;
    if (xfer_.op != Xfer::CONFIGURE) { rejected(seq, "invalid", "xfer"); return; }
    json::Value v;
    char text[4 * PART_MAX / 3 + 8];
    uint8_t data[PART_MAX];
    json::field(msg, "data", v);
    const int length = json::string(v, text, sizeof(text)) ? base64Decode(text, data, sizeof(data)) : -1;
    const uint32_t offset = intField(msg, "offset");
    if (length <= 0) { rejected(seq, "invalid", "data"); return; }
    if (offset + static_cast<uint32_t>(length) > xfer_.size) { rejected(seq, "size"); return; }
    if (offset > xfer_.next) { rejected(seq, "invalid", "offset"); return; }
    if (offset < xfer_.next) {
        // Część powtórzona (zgubione `ok`): cała w zapisanym zakresie i z tą samą treścią.
        uint8_t written[PART_MAX];
        if (offset + static_cast<uint32_t>(length) > xfer_.next) { rejected(seq, "invalid", "offset"); return; }
        if (!store_.configStaged(offset, written, static_cast<size_t>(length))) { rejected(seq, "memory"); return; }
        if (memcmp(written, data, static_cast<size_t>(length))) { rejected(seq, "invalid", "data"); return; }
    } else {
        if (!store_.configWrite(offset, data, static_cast<size_t>(length))) { rejected(seq, "memory"); return; }
        xfer_.next = offset + static_cast<uint32_t>(length);
    }
    char fields[32];
    snprintf(fields, sizeof(fields), "\"next\":%lu", static_cast<unsigned long>(xfer_.next));
    send("ok", seq, fields);
}

void Protocol::doXferRead(const json::Value& msg, int64_t seq, uint32_t nowMs) {
    if (!xferOpen(msg, seq, nowMs)) return;
    const uint32_t offset = intField(msg, "offset"), length = intField(msg, "length");
    if (xfer_.op != Xfer::CONFIG_GET) { rejected(seq, "invalid", "xfer"); return; }
    if (length == 0 || length > PART_MAX || offset > xfer_.size || length > xfer_.size - offset) { rejected(seq, "size"); return; }
    uint8_t data[PART_MAX];
    if (!store_.configRead(offset, data, length)) { rejected(seq, "memory"); return; }
    char fields[4 * PART_MAX / 3 + 48];
    const int n = snprintf(fields, sizeof(fields), "\"offset\":%lu,\"data\":\"", static_cast<unsigned long>(offset));
    const size_t encoded = base64Encode(data, length, fields + n);
    snprintf(fields + n + encoded, sizeof(fields) - n - encoded, "\"");
    send("data", seq, fields);
}

void Protocol::doXferCommit(const json::Value& msg, int64_t seq) {
    if (!xferOpen(msg, seq, xfer_.lastMs)) return;
    if (xfer_.op == Xfer::CONFIG_GET) { xfer_ = Xfer(); send("ok", seq, ""); return; }
    if (xfer_.next != xfer_.size) { rejected(seq, "size"); return; }
    const bool wasNode = store_.configured() && !store_.station();
    const char* detail = nullptr;
    size_t worst = 0;
    const store::Store::ConfigResult result = store_.configCommit(xfer_.size, xfer_.sha, detail, worst);
    xfer_ = Xfer();
    switch (result) {
        case store::Store::ConfigResult::HASH: rejected(seq, "hash"); return;
        case store::Store::ConfigResult::INVALID: rejected(seq, "invalid", detail); return;
        case store::Store::ConfigResult::MEMORY: rejected(seq, "memory"); return;
        case store::Store::ConfigResult::OK: break;
    }
    char fields[64];
    snprintf(fields, sizeof(fields), "\"worst_request\":%u,\"config_seq\":%lu", static_cast<unsigned>(worst),
             static_cast<unsigned long>(store_.config().seq));
    send("ok", seq, fields);
    host_.configChanged(wasNode != !store_.station());
}

void Protocol::poll(uint32_t nowMs) {
    if (snap_.active) { continueSnapshot(); return; }   // migawka przed zdarzeniami; polecenia czekają
    // Odpowiedź na pytanie przyciskiem z miejscem w kolejce (`status` w czasie pytania mógł ją zająć).
    if (pending() && room() >= PENDING_RESERVE) {
        const Confirm c = host_.confirmPoll();
        if (c != Confirm::WAITING) finishPending(c == Confirm::YES);
        else if (nowMs - pending_.sinceMs >= CONFIRM_MS) finishPending(false);
    }
    if (xfer_.op != Xfer::NONE && nowMs - xfer_.lastMs >= XFER_IDLE_MS) xfer_ = Xfer();
    if (connected_ && lostSync_ && sendSnapRequired(-1, lostSync_, pending() ? PENDING_RESERVE : 0)) lostSync_ = nullptr;
    if (!connected_ || !synced_) return;
    if (memcmp(syncedEpoch_, store_.meta().epoch, store::EPOCH)) { loseSync("epoch"); return; }
    if (nextEv_ > cursor_ + 1 && nowMs - lastSentMs_ >= RESEND_MS) {
        nextEv_ = cursor_ + 1;   // bez `ack` przez 5 s: od cursor + 1
        ++stats_.resends;
    }
    while (nextEv_ <= store_.head() && nextEv_ <= cursor_ + WINDOW) {
        if (nextEv_ < store_.minEvent()) { loseSync("gap"); return; }   // nadpisane przed wysłaniem
        store::Event e;
        if (!store_.readEvent(nextEv_, e)) { loseSync("gap"); return; }
        if (!sendEvent(e)) return;
        ++nextEv_;
        lastSentMs_ = nowMs;
    }
}

}  // namespace usbproto
