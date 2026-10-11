// SPDX-License-Identifier: MIT
// Komputer stanowiska odbiorczego w symulatorze. Docelowo jest to aplikacja w Pythonie z Reticulum
// (docs/spec/stanowisko-osp.md, „Komputer i aplikacja stanowiska”), której jeszcze nie ma; tutaj:
// - stos: ten sam przypięty microReticulum co w stacji (firmware/tools/stack_deps.py), transport
//   jeden interfejs KISS z kontrolą przepływu przez port danych USB węzła stanowiska
//   (stacja w roli `wezel`, prawdziwy obraz bench-b), jak KISSInterface Reticulum na komputerze
//   (różnica: transport włączony, bo microReticulum bez niego nie zapisuje znanych tożsamości);
// - tożsamości: główna i zapasowa, każda z celem "wici.sa1"; aktywna przyjmuje i ogłasza;
//   pliki stosu i klucze w systemie plików framfs (ten sam co w stacji) na „dysku” w pamięci;
// - aplikacja (MODEL): zgłoszenia i TEST od stacji z dowodem od razu (wczesny dowód dopuszcza
//   oprogramowanie.md) i RECEIVED po zapisie; STATUS, REPLY i BULLETIN na polecenie dyżurnego albo
//   automatycznie; każda wiadomość ponawiana do dowodu od stacji. Koperta jak station.cpp.
// Sterowanie poleceniami tekstowymi (sim_command) jak urządzenia; środowisko przenosi bajty KISS.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <Arduino.h>
#include <RNG.h>
#include <microReticulum.h>

#include <deque>
#include <string>
#include <vector>

#include "framfs.h"
#include "hexstr.h"
#include "journal.h"
#include "kiss.h"
#include "rns_framfs.h"
#include "sa1.h"
#include "sha2.h"
#include "store.h"

namespace post {

namespace {

constexpr size_t HASH = 16;
constexpr uint32_t RETRY_MS[] = {30000, 60000, 120000, 300000};
constexpr uint32_t READY_TIMEOUT_MS = 5000;   // Reticulum zwalnia blokadę przepływu sam po 5 s

// „Dysk” komputera: pliki stosu i klucze (framfs na 512 KiB), przetrwa restart programu.
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

class KissInterface : public RNS::InterfaceImpl {
public:
    KissInterface() : RNS::InterfaceImpl("KISS") {
        _IN = true;
        _OUT = true;
        _HW_MTU = kiss::MTU;
        _bitrate = 115200;
        _mode = RNS::Type::Interface::MODE_FULL;
    }
    void deliver(const std::string& packet) {
        char b[64];
        snprintf(b, sizeof(b), "KISS: pakiet %u B od węzła", static_cast<unsigned>(packet.size()));
        event("kiss", b);
        std::shared_ptr<RNS::InterfaceImpl> self = shared_from_this();
        RNS::Interface(self).handle_incoming(RNS::Bytes(reinterpret_cast<const uint8_t*>(packet.data()), packet.size()));
    }

protected:
    bool send_outgoing(const RNS::Bytes& raw) override {
        std::string frame;
        kissEncode(kiss::CMD_DATA, raw.data(), raw.size(), frame);
        kissQueue.push_back(frame);
        handle_outgoing(raw);
        return true;
    }
};

KissInterface* kissImpl = nullptr;   // własność przejmuje RNS::Interface (jak P1Interface w rns_node.cpp)

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
                else if (command == kiss::CMD_DATA && kissImpl) {
                    ++framesIn;
                    kissImpl->deliver(kissFrame.substr(1));
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
    uint8_t state = 0;
    std::string station;     // cel "wici.sa1" stacji (hex)
    std::string sa1, label;
    uint8_t identity = 0;
    uint64_t nextMs = 0;
    uint16_t attempts = 0;
    bool inFlight = false;
    bool done = false;
};

struct Station {
    std::string address;     // hex celu "wici.sa1"
    uint64_t heardMs = 0;
};

Disk disk;
framfs::Fs* fs = nullptr;
alignas(framfs::Fs) uint8_t fsMemory[sizeof(framfs::Fs)];
RNS::Reticulum reticulum(RNS::Type::NONE);
RNS::Identity identities[2] = {RNS::Identity(RNS::Type::NONE), RNS::Identity(RNS::Type::NONE)};
RNS::Destination destinations[2] = {RNS::Destination(RNS::Type::NONE), RNS::Destination(RNS::Type::NONE)};
RNS::Interface iface(RNS::Type::NONE);
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

void event(const char* kind, const std::string& text) {
    std::string e = "{\"t\":" + std::to_string(millis()) + ",\"kind\":\"" + kind + "\",\"text\":\"";
    for (char c : text) e += (c == '"' || c == '\\') ? '\'' : c;
    events.push_back(e + "\"}");
    if (events.size() > 2000) events.erase(events.begin(), events.begin() + 1000);
}

std::string hexOf(const RNS::Bytes& b) {
    char out[2 * 64 + 1];
    hexstr::encode(b.data(), b.size() < 64 ? b.size() : 64, out);
    return out;
}

// Klucz tożsamości w obszarze tożsamości framfs: główna w gnieździe stacji, zapasowa 128 B dalej.
bool loadIdentity(int k) {
    journal::Storage& s = disk;
    uint8_t key[framfs::KEY_BYTES];
    struct Shifted : journal::Storage {
        journal::Storage& base;
        uint32_t offset;
        Shifted(journal::Storage& b, uint32_t o) : base(b), offset(o) {}
        bool read(uint32_t a, uint8_t* d, size_t n) override { return base.read(a + offset, d, n); }
        bool write(uint32_t a, const uint8_t* d, size_t n) override { return base.write(a + offset, d, n); }
    } slot(s, k ? 2 * framfs::IDENTITY_SLOT : 0);
    if (framfs::loadKey(slot, key)) {
        identities[k] = RNS::Identity(false);
        if (identities[k].load_private_key(RNS::Bytes(key, sizeof(key)))) return true;
    }
    identities[k] = RNS::Identity();
    const RNS::Bytes prv = identities[k].get_private_key();
    return framfs::saveKey(slot, prv.data());
}

void onPacket(const RNS::Bytes& data, const RNS::Packet& packet);

class Announces final : public RNS::AnnounceHandler {
public:
    Announces() : RNS::AnnounceHandler("wici.sa1") {}
    void received_announce(const RNS::Bytes& hash, const RNS::Identity&, const RNS::Bytes&) override {
        const std::string h = hexOf(hash);
        for (int k = 0; k < 2; ++k) if (destinations[k] && hexOf(destinations[k].hash()) == h) return;
        for (Station& s : stations) if (s.address == h) { s.heardMs = millis(); return; }
        stations.push_back({h, millis()});
        event("announce", "ogłoszenie stacji " + h.substr(0, 8));
    }
};
RNS::HAnnounceHandler announces;

void announce() {
    if (!started) return;
    destinations[active].announce(RNS::Bytes(), false);   // zwykłe ogłoszenie (drugi argument: odpowiedź na zapytanie o trasę)
    lastAnnounceMs = millis();
    announced = true;
    event("announce", std::string("ogłoszenie stanowiska (") + (active ? "zapasowa" : "główna") + ")");
}

void begin() {
    if (started) return;
    try {
        RNS::set_log_callback([](const char* msg, RNS::LogLevel) { event("rns", msg); });
        fs = new (fsMemory) framfs::Fs(disk);
        if (!fs->mount()) { event("error", "dysk"); return; }
        microStore::FileSystem filesystem{new rnsfs::FramFileSystem(*fs)};
        RNS::Utilities::OS::register_filesystem(filesystem);
        uint8_t seed[32];
        vb::entropy(seed, sizeof(seed));
        RNG.begin("WICI-post");
        RNG.stir(seed, 32, 256);
        if (!loadIdentity(0) || !loadIdentity(1)) { event("error", "tożsamość"); return; }
        kissImpl = new KissInterface();
        iface = kissImpl;
        RNS::Transport::register_interface(iface);
        iface.start();
        reticulum = RNS::Reticulum();
        // Reticulum w Pythonie na komputerze pracuje bez transportu; microReticulum zakłada magazyny znanych
        // tożsamości i tras tylko w trybie transportu (Transport.cpp, start), więc tu transport jest
        // włączony. Z jednym interfejsem (KISS) węzeł transportowy nie ma czego przekazywać dalej.
        reticulum.transport_enabled(true);
        RNS::Transport::identity(identities[0]);
        // Jak rns_node.cpp: limity tablic przed startem (magazyny microStore na framfs).
        RNS::Transport::path_table_maxsize(RNS_PATH_TABLE_MAX);
        RNS::Identity::known_destinations_maxsize(RNS_KNOWN_DESTINATIONS_MAX);
        reticulum.start();
        RNS::Utilities::OS::setTimeOffset(0);
        microStore::set_time_offset(0);
        for (int k = 0; k < 2; ++k) {
            destinations[k] = RNS::Destination(identities[k], RNS::Type::Destination::IN, RNS::Type::Destination::SINGLE, "wici", "sa1");
            destinations[k].set_packet_callback(onPacket);
            destinations[k].set_proof_strategy(RNS::Type::Destination::PROVE_ALL);
        }
        announces = RNS::HAnnounceHandler(new Announces());
        RNS::Transport::register_announce_handler(announces);
        started = true;
        event("start", "stanowisko gotowe, cel " + hexOf(destinations[0].hash()).substr(0, 8));
    } catch (const std::exception& e) {
        event("error", e.what());
    }
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

void onPacket(const RNS::Bytes& data, const RNS::Packet& packet) {
    const std::string text(reinterpret_cast<const char*>(data.data()), data.size());
    // Koperta ["WICI",1,"<od>","<do>",<SA1>] (station.cpp).
    if (text.size() < 82 || text.compare(0, 11, "[\"WICI\",1,\"") != 0) { event("rx", "pakiet bez koperty WICI"); return; }
    const std::string from = text.substr(11, 32), to = text.substr(46, 32);
    uint8_t identity = 0;
    for (int k = 0; k < 2; ++k) if (destinations[k] && hexOf(destinations[k].hash()) == to) identity = static_cast<uint8_t>(k);
    if (identity != active) { event("rx", "pakiet do nieaktywnej tożsamości"); return; }
    sa1::Message m;
    if (sa1::decode(text.data() + 80, text.size() - 81, m) || (m.type != sa1::REQUEST && m.type != sa1::TEST)) {
        event("rx", "wiadomość odrzucona (format)");
        return;
    }
    bool known = false;
    for (Station& s : stations) if (s.address == from) { known = true; s.heardMs = millis(); }
    if (!known) stations.push_back({from, millis()});
    (void)packet;
    handleRequest(m, from, identity);
}

void sendDue() {
    const uint64_t now = millis();
    for (Outgoing& o : outbox) {
        if (o.done || o.inFlight || now < o.nextMs) continue;
        if (o.identity != active) { o.done = true; continue; }
        ++o.attempts;
        o.nextMs = now + RETRY_MS[o.attempts - 1 < 3 ? o.attempts - 1 : 3];
        try {
            uint8_t dest[HASH];
            hexstr::decode(o.station.c_str(), dest, HASH);
            const RNS::Bytes hash(dest, HASH);
            const RNS::Identity remote = RNS::Identity::recall(hash);
            if (!remote) {
                RNS::Transport::request_path(hash);
                event("tx", o.label + ": stacja nieznana, zapytanie o trasę");
                continue;
            }
            RNS::Destination out(remote, RNS::Type::Destination::OUT, RNS::Type::Destination::SINGLE, "wici", "sa1");
            const std::string packet = "[\"WICI\",1,\"" + hexOf(destinations[active].hash()) + "\",\"" + o.station + "\"," + o.sa1 + "]";
            RNS::Packet p(out, RNS::Bytes(reinterpret_cast<const uint8_t*>(packet.data()), packet.size()));
            RNS::PacketReceipt receipt = p.receipt_send();
            if (!receipt) { event("tx", o.label + ": stos odmówił"); continue; }
            o.inFlight = true;
            const uint32_t serial = o.serial;
            receipt.set_timeout(60);
            receipt.set_delivery_handler([serial](const RNS::PacketReceipt&) {
                for (Outgoing& q : outbox) {
                    if (q.serial != serial) continue;
                    q.done = true;
                    q.inFlight = false;
                    event("ack", "stacja potwierdziła: " + q.label);
                    for (Request& r : requests) {
                        if (r.id != q.id) continue;
                        if (q.type == sa1::RECEIVED && (r.receivedAcked == 0xFFFF || q.revision > r.receivedAcked)) r.receivedAcked = q.revision;
                        if (q.type == sa1::STATUS) r.stateAcked = q.state;
                        if (q.type == sa1::REPLY) r.replyAcked = true;
                    }
                }
            });
            receipt.set_timeout_handler([serial](const RNS::PacketReceipt&) {
                for (Outgoing& q : outbox) if (q.serial == serial) { q.inFlight = false; event("timeout", "brak dowodu: " + q.label); }
            });
            event("tx", o.label + " (próba " + std::to_string(o.attempts) + ")");
        } catch (const std::exception& e) {
            event("error", e.what());
        }
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
    const RNS::Bytes key = identities[k].get_public_key();
    uint8_t lxmf[HASH];
    sha2::destinationHash(key.data(), "lxmf.delivery", lxmf);
    char lx[2 * HASH + 1];
    hexstr::encode(lxmf, HASH, lx);
    return std::string("{\"lxmf\":\"") + lx + "\",\"key\":\"" + hexOf(key) + "\"}";
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
        active = strcmp(a1, "backup") ? 0 : 1;
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
        if (result == "ok") { r->replyEvent = m.event; r->reply = rest2; }
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
        try {
            reticulum.loop();
        } catch (const std::exception& e) {
            event("error", e.what());
        }
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

// Łata microStore 0001 (firmware/patches): wpisy chronione przed usunięciem; komputer stanowiska
// (Reticulum w Pythonie) takiej ochrony nie ma.
namespace microStore {
bool pinned_key(const uint8_t*, size_t) { return false; }
}  // namespace microStore
