// SPDX-License-Identifier: MIT
// Komputer stanowiska odbiorczego w symulatorze. Docelowo jest to aplikacja w Pythonie z Reticulum i LXMF
// (docs/spec/stanowisko-osp.md, „Komputer i aplikacja stanowiska”), której jeszcze nie ma; tutaj:
// - stos: rdzeń Reticulum stacji (firmware/lib/reticulum_core, od etapu R6-4 jak w stacji), transport
//   z jednym interfejsem KISS z kontrolą przepływu przez port danych USB węzła stanowiska (stacja w roli
//   `wezel`, prawdziwy obraz bench-b), jak KISSInterface Reticulum na komputerze. Rdzeń ma zawsze
//   włączony transport, a Reticulum na komputerze pracuje bez niego: retransmisje cudzych ogłoszeń
//   (HEADER_2) nie wychodzą do węzła;
// - tożsamości: główna i zapasowa, każda z celem "lxmf.delivery" jak LXMRouter; aktywna przyjmuje
//   i ogłasza (transport rdzenia z kluczem aktywnej). Klucze w rekordach tożsamości framfs (jak w stacji),
//   tablica znanych celów rdzenia w miejscu systemu plików stacji, oba na „dysku” w pamięci;
// - wiadomości: SA1 w LXMF jednym pakietem okazjonalnym (rnscore::lxmfPackSa1, lxmfReceiveSa1), z podpisem
//   aktywnej tożsamości i weryfikacją podpisu stacji kluczem z jej ogłoszenia;
// - aplikacja (MODEL): zgłoszenia i TEST od stacji z dowodem od razu (wczesny dowód dopuszcza
//   oprogramowanie.md; LXMRouter dowodzi każdego pakietu, PROVE_ALL) i RECEIVED po zapisie; STATUS, REPLY
//   i BULLETIN na polecenie dyżurnego albo automatycznie; każda wiadomość ponawiana do dowodu od stacji.
// Sterowanie poleceniami tekstowymi (sim_command) jak urządzenia; środowisko przenosi bajty KISS.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <Arduino.h>

#include <deque>
#include <string>
#include <vector>

#include "destination.h"
#include "drbg.h"
#include "framfs.h"
#include "hexstr.h"
#include "identity.h"
#include "journal.h"
#include "kiss.h"
#include "lxmf.h"
#include "packet.h"
#include "sa1.h"
#include "store.h"
#include "table.h"
#include "transport.h"

namespace post {

namespace {

constexpr size_t HASH = 16;
constexpr uint32_t RETRY_MS[] = {30000, 60000, 120000, 300000};
constexpr uint32_t READY_TIMEOUT_MS = 5000;   // Reticulum zwalnia blokadę przepływu sam po 5 s

// „Dysk” komputera: klucze i tablica znanych celów (512 KiB jak FRAM stacji), przetrwa restart programu.
struct Disk : journal::Storage {
    std::vector<uint8_t> bytes = std::vector<uint8_t>(512 * 1024, 0xFF);
    bool read(uint32_t a, uint8_t* d, size_t n) override {
        if (a + n > bytes.size()) return false;
        memcpy(d, bytes.data() + a, n);
        return true;
    }
    bool write(uint32_t a, const uint8_t* d, size_t n) override {
        if (a + n > bytes.size()) return false;
        memcpy(bytes.data() + a, d, n);
        return true;
    }
};

void event(const char* kind, const std::string& text);

// ---- łącze KISS do węzła (strona komputera) ----
std::string kissOut;                 // bajty do węzła (środowisko pisze je do portu danych)
std::deque<std::string> kissQueue;   // ramki czekające na gotowość węzła
bool kissReady = true;
bool portOpen = false;               // port danych węzła otwarty przez komputer (przed otwarciem nic nie wychodzi)
uint32_t kissSentMs = 0;
std::string kissFrame;
bool kissIn = false, kissEsc = false;
uint32_t framesIn = 0, framesOut = 0;

void kissEncode(uint8_t command, const uint8_t* data, size_t n, std::string& out) {
    out += static_cast<char>(kiss::FEND);
    out += static_cast<char>(command);
    for (size_t i = 0; i < n; ++i) {
        if (data[i] == kiss::FEND) { out += static_cast<char>(kiss::FESC); out += static_cast<char>(kiss::TFEND); }
        else if (data[i] == kiss::FESC) { out += static_cast<char>(kiss::FESC); out += static_cast<char>(kiss::TFESC); }
        else out += static_cast<char>(data[i]);
    }
    out += static_cast<char>(kiss::FEND);
}

// Pakiet od węzła do transportu (interfejs 0).
void deliver(const std::string& packet);

void kissPump() {
    const uint32_t now = millis();
    if (!portOpen) { kissQueue.clear(); return; }
    if (!kissReady && now - kissSentMs > READY_TIMEOUT_MS) kissReady = true;
    if (kissReady && !kissQueue.empty()) {
        kissOut += kissQueue.front();
        {
            char b[80];
            snprintf(b, sizeof(b), "KISS: ramka %u B do węzła", static_cast<unsigned>(kissQueue.front().size()));
            event("kiss", b);
        }
        kissQueue.pop_front();
        kissReady = false;
        kissSentMs = now;
        ++framesOut;
    }
}

void kissFeed(const std::vector<uint8_t>& bytes) {
    if (!portOpen) return;   // aplikacja zamknęła port węzła: nic z niego nie czyta
    for (uint8_t c : bytes) {
        if (c == kiss::FEND) {
            if (kissIn && !kissFrame.empty()) {
                const uint8_t command = static_cast<uint8_t>(kissFrame[0]) & 0x0F;
                if (command == kiss::CMD_READY) kissReady = true;
                else if (command == kiss::CMD_DATA) {
                    ++framesIn;
                    deliver(kissFrame.substr(1));
                }
            }
            kissFrame.clear();
            kissIn = true;
            kissEsc = false;
            continue;
        }
        if (!kissIn) continue;
        if (kissEsc) {
            kissFrame += static_cast<char>(c == kiss::TFEND ? kiss::FEND : c == kiss::TFESC ? kiss::FESC : c);
            kissEsc = false;
        } else if (c == kiss::FESC) kissEsc = true;
        else kissFrame += static_cast<char>(c);
    }
}

// ---- stan aplikacji ----

struct Request {
    std::string id;
    uint16_t number = 0;
    uint8_t type = sa1::REQUEST;
    uint16_t revision = 0;
    uint8_t category = 0;
    uint16_t people = 0;
    uint8_t urgency = 0;
    std::string location, text, station;
    uint64_t firstMs = 0, lastMs = 0;
    uint8_t state = 1;
    uint32_t statusEvent = 1;
    uint32_t replyEvent = 0;
    std::string reply;
    uint32_t copies = 0;
    bool changed = false;
    uint8_t identity = 0;
    uint64_t autoReadAt = 0, autoDecideAt = 0;
    uint16_t receivedAcked = 0xFFFF;   // rewizja, której RECEIVED stacja potwierdziła dowodem (0xFFFF: żadna)
    uint8_t stateAcked = 0;            // stan, którego STATUS stacja potwierdziła
    bool replyAcked = false;
};

struct Outgoing {
    uint32_t serial = 0;
    std::string id;          // zgłoszenie (pusty: komunikat)
    uint8_t type = 0;
    uint16_t revision = 0;
    uint32_t event = 0;
    uint8_t state = 0;
    std::string station;     // cel "lxmf.delivery" stacji (hex)
    std::string sa1, label;
    uint8_t identity = 0;
    uint64_t nextMs = 0;
    uint16_t attempts = 0;
    bool inFlight = false;
    bool done = false;
    uint32_t handle = 0;     // potwierdzenie transportu rdzenia
};

struct Station {
    std::string address;     // hex celu "lxmf.delivery" stacji
    uint64_t heardMs = 0;
};

Disk disk;
// Obszar tablicy znanych celów rdzenia na dysku: miejsce systemu plików stacji (jak rns_node_core.cpp).
struct DiskTable : rnscore::TableStorage {
    bool read(uint32_t offset, uint8_t* data, size_t count) override {
        return offset + count <= rnscore::TABLE_AREA && disk.read(framfs::FS_BASE + offset, data, count);
    }
    bool write(uint32_t offset, const uint8_t* data, size_t count) override {
        return offset + count <= rnscore::TABLE_AREA && disk.write(framfs::FS_BASE + offset, data, count);
    }
};
DiskTable table;
rnscore::Transport transport;
drbg::Drbg generator;   // klucze tożsamości, skróty losowe ogłoszeń, klucze efemeryczne i IV (RNS: os.urandom)
struct Identity {
    uint8_t privateKey[rnscore::KEY_SIZE];
    uint8_t publicKey[rnscore::KEY_SIZE];
    uint8_t hash[HASH];
    uint8_t address[HASH];   // cel "lxmf.delivery"
};
Identity identities[2];
uint8_t lxmfName[rnscore::NAME_HASH_SIZE];
uint8_t active = 0;
bool started = false;
bool autoRead = true, announced = false;
uint32_t readMin = 2, decideMin = 5;
uint8_t autoDecision = 0;
std::vector<Request> requests;
std::vector<Outgoing> outbox;
std::vector<Station> stations;
uint32_t serials = 0, bulletinEvent = 0;
std::vector<std::string> events;
std::string reply;
uint64_t lastAnnounceMs = 0;
uint32_t nextHandle = 0;
uint32_t rebroadcastsHeld = 0;   // retransmisje cudzych ogłoszeń, których komputer bez transportu nie nadaje

void event(const char* kind, const std::string& text) {
    std::string e = "{\"t\":" + std::to_string(millis()) + ",\"kind\":\"" + kind + "\",\"text\":\"";
    for (char c : text) e += (c == '"' || c == '\\') ? '\'' : c;
    events.push_back(e + "\"}");
    if (events.size() > 2000) events.erase(events.begin(), events.begin() + 1000);
}

std::string hexOf(const uint8_t* b, size_t n) {
    char out[2 * 64 + 1];
    hexstr::encode(b, n < 64 ? n : 64, out);
    return out;
}

// Klucz tożsamości w obszarze tożsamości framfs: główna w gnieździe stacji, zapasowa 128 B dalej. Nowy klucz
// z generatora, X25519 przycięty jak w rns_node_core.cpp (RNS/Identity.py: Identity.create_keys).
bool loadIdentity(int k) {
    struct Shifted : journal::Storage {
        journal::Storage& base;
        uint32_t offset;
        Shifted(journal::Storage& b, uint32_t o) : base(b), offset(o) {}
        bool read(uint32_t a, uint8_t* d, size_t n) override { return base.read(a + offset, d, n); }
        bool write(uint32_t a, const uint8_t* d, size_t n) override { return base.write(a + offset, d, n); }
    } slot(disk, k ? 2 * framfs::IDENTITY_SLOT : 0);
    Identity& id = identities[k];
    if (!framfs::loadKey(slot, id.privateKey)) {
        if (!generator.generate(id.privateKey, sizeof(id.privateKey))) return false;
        id.privateKey[0] &= 0xF8;
        id.privateKey[31] = (id.privateKey[31] & 0x7F) | 0x40;
        if (!framfs::saveKey(slot, id.privateKey)) return false;
    }
    rnscore::publicKey(id.privateKey, id.publicKey);
    rnscore::identityHash(id.publicKey, id.hash);
    rnscore::destinationHashFrom(lxmfName, id.hash, id.address);
    return true;
}

void onPacket(const uint8_t* data, size_t length);
void onReceipt(uint32_t handle, bool delivered);

// Wywołania z transportu rdzenia (jeden interfejs: KISS do węzła).
bool transmitHook(const uint8_t* raw, size_t length, uint8_t, void*) {
    if (length > 1 && (raw[0] & 0x40) && (raw[0] & 0x03) == rnscore::ANNOUNCE) {
        ++rebroadcastsHeld;   // HEADER_2: retransmisja cudzego ogłoszenia albo odpowiedź za inny cel
        return false;
    }
    std::string frame;
    kissEncode(kiss::CMD_DATA, raw, length, frame);
    kissQueue.push_back(frame);
    return true;
}

void announceHook(const uint8_t destination[HASH], const uint8_t*, size_t, void*) {
    const std::string h = hexOf(destination, HASH);
    for (const Identity& id : identities) if (memcmp(id.address, destination, HASH) == 0) return;
    for (Station& s : stations) if (s.address == h) { s.heardMs = millis(); return; }
    stations.push_back({h, millis()});
    event("announce", "ogłoszenie stacji " + h.substr(0, 8));
}

bool packetHook(const uint8_t* data, size_t length, void*) {
    onPacket(data, length);
    return true;   // PROVE_ALL jak LXMRouter: dowód każdego pakietu do celu
}

void receiptHook(uint32_t handle, bool delivered, void*) { onReceipt(handle, delivered); }
bool randomHook(uint8_t* out, size_t length, void*) { return generator.generate(out, length); }
bool yesHook(uint8_t, void*) { return true; }

// Transport z kluczem aktywnej tożsamości; tablica znanych celów zostaje (montowana od nowa).
void beginTransport() {
    rnscore::TransportHooks h;
    h.transmit = transmitHook;
    h.announce = announceHook;
    h.packet = packetHook;
    h.receipt = receiptHook;
    h.random = randomHook;
    h.mayVerify = yesHook;
    const Identity& id = identities[active];
    transport.begin(id.privateKey, id.publicKey, id.hash, id.address, lxmfName, h, table, millis(), 1);
    transport.setBitrate(115200);
}

void deliver(const std::string& packet) {
    char b[64];
    snprintf(b, sizeof(b), "KISS: pakiet %u B od węzła", static_cast<unsigned>(packet.size()));
    event("kiss", b);
    if (!transport.inbound(reinterpret_cast<const uint8_t*>(packet.data()), packet.size(), millis())) event("rx", "pakiet nieczytelny");
}

void announce() {
    if (!started) return;
    uint8_t random[5];   // ogłoszenie bez danych aplikacji, jak przed etapem R6-4
    if (!generator.generate(random, sizeof(random)) || !transport.announce(random, nullptr, 0, millis())) {
        event("error", "ogłoszenie odrzucone");
        return;
    }
    lastAnnounceMs = millis();
    announced = true;
    event("announce", std::string("ogłoszenie stanowiska (") + (active ? "zapasowa" : "główna") + ")");
}

void begin() {
    if (started) return;
    uint8_t seed[32];
    vb::entropy(seed, sizeof(seed));
    static const char nonce[] = "WICI-post";
    generator.seed(seed, sizeof(seed), reinterpret_cast<const uint8_t*>(nonce), sizeof(nonce) - 1);
    rnscore::nameHash("lxmf.delivery", lxmfName);
    if (!loadIdentity(0) || !loadIdentity(1)) { event("error", "tożsamość"); return; }
    beginTransport();
    started = true;
    event("start", "stanowisko gotowe, cel " + hexOf(identities[0].address, HASH).substr(0, 8));
}

Request* find(uint16_t number) {
    for (Request& r : requests) if (r.number == number) return &r;
    return nullptr;
}

std::string queue(const sa1::Message& m, const std::string& label, const std::string& station, uint8_t identity) {
    char wire[sa1::MAX_CONTENT + 1];
    if (!sa1::encode(m, wire, sizeof(wire))) return "err tekst niezgodny z SA1 (znaki, NFC albo długość)";
    Outgoing o;
    o.serial = ++serials;
    o.id = m.type == sa1::BULLETIN ? "" : m.id;
    o.type = m.type;
    o.revision = m.revision;
    o.event = m.event;
    o.state = m.state;
    o.station = station;
    o.sa1 = wire;
    o.label = label;
    o.identity = identity;
    o.nextMs = millis();
    outbox.push_back(o);
    if (outbox.size() > 400) outbox.erase(outbox.begin(), outbox.begin() + 100);
    return "ok";
}

std::string decide(Request& r, uint8_t state, const char* who) {
    if (state < 2 || state > 6) return "err stan 2-6";
    if (state == 5 && (r.reply.find_first_not_of(" \t\r\n") == std::string::npos || !r.replyAcked))
        return "err najpierw wyślij instrukcję i poczekaj na potwierdzenie jej odbioru";
    r.state = state;
    r.changed = false;
    r.statusEvent = r.statusEvent + 1 < 2 ? 2 : r.statusEvent + 1;
    sa1::Message m;
    m.type = sa1::STATUS;
    snprintf(m.id, sizeof(m.id), "%s", r.id.c_str());
    m.revision = r.revision;
    m.event = r.statusEvent;
    m.state = state;
    char b[80];
    snprintf(b, sizeof(b), "STATUS %u dla %04u (%s)", state, r.number, who);
    return queue(m, b, r.station, r.identity);
}

void handleRequest(const sa1::Message& m, const std::string& station, uint8_t identity) {
    uint8_t id[HASH];
    hexstr::decode(m.id, id, HASH);
    Request* r = nullptr;
    for (Request& q : requests) if (q.id == m.id) r = &q;
    const bool fresh = !r;
    if (fresh) {
        requests.push_back(Request());
        r = &requests.back();
        r->id = m.id;
        r->number = store::shortNumber(id);
        r->firstMs = millis();
        if (autoRead) r->autoReadAt = millis() + readMin * 60000ull;
        if (autoDecision) r->autoDecideAt = millis() + decideMin * 60000ull;
    }
    ++r->copies;
    r->lastMs = millis();
    r->station = station;
    r->identity = identity;
    const bool newer = fresh || m.revision > r->revision;
    if (newer) {
        r->type = m.type;
        r->revision = m.revision;
        r->reply.clear();
        r->replyAcked = false;
        r->stateAcked = 0;
        // Odmowa wymaga instrukcji tej wersji; nie powtarzamy jej dla korekty.
        if (r->state == 5) r->state = 1;
        r->category = m.category;
        r->people = m.people;
        r->urgency = m.urgency;
        r->location = m.location;
        r->text = m.text;
        if (!fresh) r->changed = true;
    }
    char b[120];
    snprintf(b, sizeof(b), "zapisane %s %04u rew. %u%s", m.type == sa1::TEST ? "TEST" : "zgłoszenie", r->number, m.revision, newer ? "" : " (powtórzenie)");
    event("rx", b);
    sa1::Message out;
    out.type = sa1::RECEIVED;
    snprintf(out.id, sizeof(out.id), "%s", m.id);
    out.revision = m.revision;
    out.event = 1;
    out.state = 1;
    snprintf(b, sizeof(b), "ODEBRANE %04u rew. %u", r->number, m.revision);
    queue(out, b, station, identity);
    if (r->state >= 2 && r->revision == m.revision) {
        sa1::Message st;
        st.type = sa1::STATUS;
        snprintf(st.id, sizeof(st.id), "%s", m.id);
        st.revision = r->revision;
        st.event = r->statusEvent;
        st.state = r->state;
        snprintf(b, sizeof(b), "STATUS %u dla %04u (powtórzenie)", r->state, r->number);
        queue(st, b, station, identity);
    }
}

// Wiadomość SA1 w LXMF od stacji (LXMRouter.delivery_packet): klucz nadawcy z jego ogłoszenia w tablicy.
void onPacket(const uint8_t* data, size_t length) {
    const Identity& id = identities[active];
    rnscore::KnownDestination sender;
    rnscore::LxmfSa1 lx;
    if (length < rnscore::LXMF_SOURCE_OFFSET + HASH || !transport.lookup(data + rnscore::LXMF_SOURCE_OFFSET, sender, millis()) ||
        !rnscore::lxmfReceiveSa1(id.address, data, length, sender.publicKey, lx)) {
        event("rx", "wiadomość odrzucona (nadawca nieznany, podpis albo nie SA1)");
        return;
    }
    const std::string from = hexOf(lx.sourceHash, HASH);
    sa1::Message m;
    if (sa1::decode(reinterpret_cast<const char*>(lx.content), lx.contentLength, m) || (m.type != sa1::REQUEST && m.type != sa1::TEST)) {
        event("rx", "wiadomość odrzucona (format)");
        return;
    }
    bool known = false;
    for (Station& s : stations) if (s.address == from) { known = true; s.heardMs = millis(); }
    if (!known) stations.push_back({from, millis()});
    handleRequest(m, from, active);
}

void onReceipt(uint32_t handle, bool delivered) {
    for (Outgoing& q : outbox) {
        if (q.handle != handle || !q.inFlight) continue;
        q.inFlight = false;
        if (!delivered) { event("timeout", "brak dowodu: " + q.label); return; }
        q.done = true;
        event("ack", "stacja potwierdziła: " + q.label);
        for (Request& r : requests) {
            if (r.id != q.id) continue;
            if (q.type == sa1::RECEIVED && (r.receivedAcked == 0xFFFF || q.revision > r.receivedAcked)) r.receivedAcked = q.revision;
            if (q.type == sa1::STATUS && q.revision == r.revision && q.event == r.statusEvent) r.stateAcked = q.state;
            if (q.type == sa1::REPLY && q.revision == r.revision && q.event == r.replyEvent) r.replyAcked = true;
        }
        return;
    }
}

void sendDue() {
    const uint64_t now = millis();
    const Identity& id = identities[active];
    for (Outgoing& o : outbox) {
        if (o.done || o.inFlight || now < o.nextMs) continue;
        if (o.identity != active) { o.done = true; continue; }
        ++o.attempts;
        o.nextMs = now + RETRY_MS[o.attempts - 1 < 3 ? o.attempts - 1 : 3];
        uint8_t dest[HASH];
        hexstr::decode(o.station.c_str(), dest, HASH);
        if (!transport.knows(dest)) {
            uint8_t tag[HASH];
            if (generator.generate(tag, sizeof(tag))) transport.requestPath(dest, tag, now);
            event("tx", o.label + ": stacja nieznana, zapytanie o trasę");
            continue;
        }
        // LXMessage.pack (OPPORTUNISTIC), znacznik czasu w s od startu programu (stacja go nie używa).
        uint8_t data[rnscore::LXMF_SA1_MAX_DATA], hash[rnscore::HASH_SIZE];
        const size_t length = rnscore::lxmfPackSa1(id.privateKey, id.publicKey, dest, id.address, static_cast<double>(now / 1000),
                                                   reinterpret_cast<const uint8_t*>(o.sa1.data()), o.sa1.size(), data, sizeof(data), hash);
        uint8_t random[32 + 16];
        const uint32_t handle = ++nextHandle ? nextHandle : ++nextHandle;
        if (!length || !generator.generate(random, sizeof(random)) ||
            transport.send(dest, data, length, random, random + 32, handle, 60000, now) != rnscore::SendResult::SENT) {
            event("tx", o.label + ": stos odmówił");
            continue;
        }
        o.inFlight = true;
        o.handle = handle;
        event("tx", o.label + " (próba " + std::to_string(o.attempts) + ")");
    }
}

void autoOperator() {
    const uint64_t now = millis();
    for (Request& r : requests) {
        if (r.autoReadAt && now >= r.autoReadAt) { r.autoReadAt = 0; if (r.state < 2) decide(r, 2, "auto"); }
        if (r.autoDecideAt && now >= r.autoDecideAt) {
            r.autoDecideAt = 0;
            // TEST kończy się na odczycie (state 2), bez decyzji o pomocy.
            if (r.state < 3 && r.type != sa1::TEST && autoDecision) decide(r, autoDecision, "auto");
        }
    }
}

std::string jsonText(const std::string& s) {
    std::string out = "\"";
    for (char c : s) { if (c == '"' || c == '\\') out += '\\'; out += c; }
    return out + "\"";
}

std::string state() {
    std::string o = "{\"started\":" + std::string(started ? "true" : "false") + ",\"identity\":" + std::to_string(active);
    o += ",\"auto\":{\"read\":" + std::string(autoRead ? "true" : "false") + ",\"read_min\":" + std::to_string(readMin) +
         ",\"decision\":" + std::to_string(autoDecision) + ",\"decide_min\":" + std::to_string(decideMin) + "}";
    size_t waiting = 0;
    for (const Outgoing& q : outbox) waiting += !q.done;
    o += ",\"outbox\":" + std::to_string(waiting) + ",\"kiss_in\":" + std::to_string(framesIn) + ",\"kiss_out\":" + std::to_string(framesOut);
    o += ",\"stations\":[";
    for (const Station& s : stations) o += jsonText(s.address) + ",";
    if (o.back() == ',') o.pop_back();
    o += "],\"requests\":[";
    for (const Request& r : requests) {
        o += "{\"number\":" + std::to_string(r.number) + ",\"type\":\"" + (r.type == sa1::TEST ? "test" : "request") + "\",\"revision\":" +
             std::to_string(r.revision) + ",\"category\":" + std::to_string(r.category) + ",\"people\":" + std::to_string(r.people) +
             ",\"urgency\":" + std::to_string(r.urgency) + ",\"location\":" + jsonText(r.location) + ",\"text\":" + jsonText(r.text) +
             ",\"state\":" + std::to_string(r.state) + ",\"changed\":" + (r.changed ? "true" : "false") + ",\"copies\":" + std::to_string(r.copies) +
             ",\"first_ms\":" + std::to_string(r.firstMs) + ",\"reply\":" + jsonText(r.reply) + ",\"station\":" + jsonText(r.station) +
             ",\"identity\":" + std::to_string(r.identity) + ",\"received_acked\":" + (r.receivedAcked == 0xFFFF ? "-1" : std::to_string(r.receivedAcked)) +
             ",\"state_acked\":" + std::to_string(r.stateAcked) + ",\"reply_acked\":" + (r.replyAcked ? "true" : "false") + "},";
    }
    if (o.back() == ',') o.pop_back();
    return o + "]}";
}

std::string card(int k) {
    // Karta odbiorcy do konfiguracji stacji (protokol-usb.md, `configure`): adres LXMF i klucz publiczny.
    return std::string("{\"lxmf\":\"") + hexOf(identities[k].address, HASH) + "\",\"key\":\"" +
           hexOf(identities[k].publicKey, rnscore::KEY_SIZE) + "\"}";
}

std::string run(const char* line) {
    char cmd[16] = "", a1[64] = "";
    sscanf(line, "%15s %63s", cmd, a1);
    const char* rest = strchr(line, ' ') ? strchr(line, ' ') + 1 : "";
    const char* rest2 = strchr(rest, ' ') ? strchr(rest, ' ') + 1 : "";
    if (!strcmp(cmd, "kissin")) {
        std::vector<uint8_t> bytes;
        for (const char* p = rest; p[0] && p[1]; p += 2) {
            auto v = [](char c) { return c <= '9' ? c - '0' : (c | 32) - 'a' + 10; };
            bytes.push_back(static_cast<uint8_t>(v(p[0]) << 4 | v(p[1])));
        }
        kissFeed(bytes);
        return "ok";
    }
    if (!strcmp(cmd, "kissout")) {
        std::string out(2 * kissOut.size(), '0');
        hexstr::encode(reinterpret_cast<const uint8_t*>(kissOut.data()), kissOut.size(), &out[0]);
        out.resize(2 * kissOut.size());
        kissOut.clear();
        return out;
    }
    if (!strcmp(cmd, "card")) return started ? "{\"main\":" + card(0) + ",\"backup\":" + card(1) + "}" : "err stanowisko nie wystartowało";
    if (!strcmp(cmd, "state")) return state();
    if (!strcmp(cmd, "log")) {
        std::string o = "[";
        for (const std::string& e : events) o += e + ",";
        if (o.back() == ',') o.pop_back();
        events.clear();
        return o + "]";
    }
    if (!strcmp(cmd, "announce")) { announce(); return "ok"; }
    if (!strcmp(cmd, "port")) {
        // Otwarcie portu węzła: kontrola przepływu KISS (KISSInterface z flow_control, firmware/src/kiss.h),
        // potem ogłoszenie celu, jak aplikacja stanowiska po starcie interfejsu.
        portOpen = !strcmp(a1, "open");
        kissOut.clear();
        kissQueue.clear();
        kissReady = true;
        if (portOpen) {
            static const uint8_t on = 0x01;
            kissEncode(kiss::CMD_READY, &on, 1, kissOut);
            announce();
        }
        return "ok";
    }
    if (!strcmp(cmd, "station")) {
        // Stacja z wykazu stanowiska (karta przygotowania), znana przed pierwszym ogłoszeniem.
        std::string h = a1;
        if (h.size() != 2 * HASH) return "err adres stacji";
        for (const Station& s : stations) if (s.address == h) return "ok";
        stations.push_back({h, 0});
        return "ok";
    }
    if (!strcmp(cmd, "identity")) {
        const uint8_t next = strcmp(a1, "backup") ? 0 : 1;
        if (next != active) {
            active = next;
            if (started) beginTransport();
        }
        announce();
        return "ok";
    }
    if (!strcmp(cmd, "auto")) {
        unsigned read = 1, rm = 2, dec = 0, dm = 5;
        sscanf(rest, "%u %u %u %u", &read, &rm, &dec, &dm);
        autoRead = read != 0;
        readMin = rm;
        if (dec != 0 && (dec < 3 || dec > 6)) return "err decyzja automatyczna 0 albo 3-6";
        autoDecision = static_cast<uint8_t>(dec);
        decideMin = dm;
        return "ok";
    }
    if (!strcmp(cmd, "bulletin")) {
        sa1::Message m;
        m.type = sa1::BULLETIN;
        uint8_t id[HASH];
        vb::entropy(id, HASH);
        hexstr::encode(id, HASH, m.id);
        m.event = bulletinEvent + 1;
        snprintf(m.text, sizeof(m.text), "%s", rest);
        std::string result = "ok";
        for (const Station& s : stations) {
            result = queue(m, "KOMUNIKAT do " + s.address.substr(0, 6), s.address, active);
            if (result != "ok") return result;
        }
        if (stations.empty()) return "err brak znanych stacji";
        bulletinEvent = m.event;
        return result;
    }
    Request* r = find(static_cast<uint16_t>(strtoul(a1, nullptr, 10)));
    if (!strcmp(cmd, "decide") || !strcmp(cmd, "read") || !strcmp(cmd, "reply")) {
        if (!r) return "err brak zgłoszenia o tym numerze";
        if (!strcmp(cmd, "read")) return decide(*r, 2, "dyżurny");
        if (!strcmp(cmd, "decide")) return decide(*r, static_cast<uint8_t>(atoi(rest2)), "dyżurny");
        sa1::Message m;
        m.type = sa1::REPLY;
        snprintf(m.id, sizeof(m.id), "%s", r->id.c_str());
        m.revision = r->revision;
        m.event = r->replyEvent + 1;
        snprintf(m.text, sizeof(m.text), "%s", rest2);
        char b[64];
        snprintf(b, sizeof(b), "ODPOWIEDŹ dla %04u", r->number);
        const std::string result = queue(m, b, r->station, r->identity);
        if (result == "ok") { r->replyEvent = m.event; r->reply = rest2; r->replyAcked = false; }
        return result;
    }
    return "err nieznane polecenie";
}

}  // namespace
}  // namespace post

// Program komputera na wirtualnej płytce (setup/loop wołane przez sim_run, hal/vboard.cpp).
void setup() { post::begin(); }

void loop() {
    using namespace post;
    if (started) {
        transport.poll(millis());
        kissPump();
        autoOperator();
        sendDue();
        if (portOpen && millis() - lastAnnounceMs > 30 * 60 * 1000UL) announce();
    }
    delay(10);
}

extern "C" const char* post_command(const char* line) {
    post::reply = post::run(line);
    return post::reply.c_str();
}

extern "C" uint8_t* post_disk() { return post::disk.bytes.data(); }
extern "C" uint32_t post_disk_size() { return static_cast<uint32_t>(post::disk.bytes.size()); }
