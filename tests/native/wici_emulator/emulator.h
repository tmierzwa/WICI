// SPDX-License-Identifier: MIT
// Emulator wielu węzłów WICI-Link: prawdziwy kod stacji (wici_radio, wici_hop, wici_route, wici_flood,
// wici_relay) i roota (wici_gateway) w wielu instancjach, zegar wirtualny i model kanału.
//
// Co jest prawdziwym kodem: wszystko z firmware/src, łącznie z kryptografią, FRAM w RAM, dziennikiem
// czasu nadawania (wici_airtime) i tagiem pary (wici_hop_auth).
// Co jest modelem (opis założeń w README.md):
//  - Radio: odpowiednik Bench z measure.cpp (dług ciszy 12t, okno 50 ms, CAD, odroczenia, ścieżka HACK).
//  - Channel: kto kogo słyszy, skuteczność łącza, kolizje, ukryte nadajniki.
//  - Laptop: skrót wici_stos.py i wysylka.py (jedno zgłoszenie do roota naraz, 3 próby, ponowienia intencji).
//  - StationApp: skrót Station z station.cpp (kolejka zgłoszeń, 60 s, 10 min, 30-60 min).
// Emulator sprawdza logikę i obciążenie przy przyjętych założeniach. Nie dowodzi niczego o radiu.
#pragma once

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <array>
#include <deque>
#include <map>
#include <memory>
#include <set>
#include <utility>
#include <vector>

#include <ChaChaPoly.h>
#include <Crypto.h>
#include <Curve25519.h>
#include <Ed25519.h>

#include "envelope.h"
#include "envelope_counter.h"
#include "fram_record.h"
#include "kiss.h"
#include "lora_profile.h"
#include "wici_airtime.h"
#include "wici_beacon.h"
#include "wici_epoch.h"
#include "wici_gateway.h"
#include "wici_hop_auth.h"
#include "wici_radio.h"

#ifdef WICI_EMU_VARIANT
#include "wici_variant.h"
#endif

namespace emu {

using fram_record::get16;
using fram_record::get32;
using fram_record::put32;

constexpr uint16_t NETWORK = 100;
constexpr uint16_t ROOT_ID = 1;
constexpr uint16_t RECEIVER_MAIN = 1000, RECEIVER_BACKUP = 1001;
constexpr uint32_t START_S = 1000;  // licznik sekund stacji na starcie, bo 0 jest wartością specjalną kilku rekordów

// Generator bez zależności od biblioteki standardowej (PCG32): ten sam ciąg na każdym kompilatorze.
class Rng {
public:
    explicit Rng(uint64_t seed = 1) : state_(seed * 2 + 1) { next(); next(); }
    uint32_t next() {
        const uint64_t old = state_;
        state_ = old * 6364136223846793005ULL + 1442695040888963407ULL;
        const uint32_t shifted = static_cast<uint32_t>(((old >> 18) ^ old) >> 27);
        const uint32_t rot = static_cast<uint32_t>(old >> 59);
        return (shifted >> rot) | (shifted << ((32 - rot) & 31));
    }
    uint32_t below(uint32_t n) { return n ? next() % n : 0; }
    uint32_t range(uint32_t low, uint32_t high) { return low + below(high - low + 1); }
    bool chance(uint32_t permille) { return below(1000) < permille; }

private:
    uint64_t state_;
};

// Założenia kanału i czasu, jawnie i w jednym miejscu. Wartości domyślne opisuje README.md.
struct Assumptions {
    uint32_t senseMissPermille = 20;   // CAD albo RSSI nie zauważa ramki w toku
    uint32_t cadMs = 6;                // od decyzji o nadaniu do pierwszego symbolu: obieg CAD z potwierdzeniem
    uint32_t hackProcMs = 25;          // stacja: od końca odbioru do startu HACK (szacunek D21)
    uint32_t rootHackProcMs = 5;       // root: od HACK z laptopa do startu HACK
    uint32_t usbMs = 3;                // KISS w jedną stronę
    uint32_t admissionMs = 40;         // przyjęcie koperty na stanowisku (zapis w SQLite)
    uint32_t beaconCheckMs = 200;      // sprawdzenie podpisów BEACON-u na drugim rdzeniu (0,04-0,4 s)
    uint32_t pollMs = 10;              // obieg pętli stacji
};

// Warianty rozstrzygnięć z 2026-11-05. Wszystkie wyłączone to obecny kod.
struct Variant {
    bool learnRoutes = false;     // przekaźnik uczy się dróg w dół z ruchu w górę, ostatnia wygrywa
    bool alternate = false;       // intencje na przemian: droga, rozsyłanie; ramka rozsyłana zostaje rozsyłana
    uint32_t leaveAfterS = 0;     // bez wiadomości od odbiorcy tyle sekund: zmiana rodzica (około 1800)
    uint32_t holdS = 0;           // opuszczony rodzic nie wraca przez tyle sekund (około 7200)
    uint32_t floodMsPerStation = 0;  // budżet rozsyłania stanowiska: odstęp na stację (około 700)
    uint32_t leaveCount = 0;      // próg w próbach: tyle nadań z HACK bez wiadomości od odbiorcy, następne już przez innego rodzica
    bool perMessage = false;      // próg w próbach: licznik zeruje tylko odpowiedź na tę wiadomość, nie każda od odbiorcy
    uint32_t probeS = 0;          // próbka przekaźnika: tyle sekund bez powrotu dla przekazanego ruchu i własna wiadomość
    uint32_t probeEveryS = 1800;  // próbka przekaźnika: najkrótszy odstęp między próbkami jednej stacji
    uint32_t probeMode = 1;       // 1: powrót to każda ramka w dół; 2: powrót to tylko uwierzytelniona wiadomość do tej stacji
    bool k1Flood = false;         // poprawka bez zmiany bajtów: ramka z gniazda K1 bez drogi zachowuje pierwszeństwo K1
    bool k1Routed = false;        // poprawka bez zmiany bajtów: przy limicie 25% liczą się tylko ramki K1 ze znaną drogą
    bool stickyRoutes = false;    // próba: nauka tylko brakującej drogi zamiast „ostatnia wygrywa”
    bool noPool = false;          // próba przyczyny: bez puli czasu nadawania (nie rozstrzygnięcie, nie do firmware)
};

struct NodeStats {
    uint32_t txUnicast = 0, txFlood = 0, txHack = 0, txBeacon = 0;
    uint64_t airMs = 0;
    uint32_t refusedBudget = 0, deferrals = 0, txDrops = 0;
    uint32_t rxOk = 0, rxCollision = 0, rxLost = 0, rxRejected = 0;
    uint32_t hackRefused = 0;
    uint32_t parentChanges = 0;
    uint32_t leaves = 0;
    uint32_t maxSilentS = 0;   // najdłużej otwarta wiadomość po HACK bez wiadomości od odbiorcy
    uint32_t firstLeaveMs = 0; // pierwsza zmiana rodzica przez stoper albo próg w próbach
    uint32_t probes = 0;       // wysłane próbki
    uint32_t longestMuteS = 0; // najdłużej bez żadnego nadania w chwili odmowy z dziennika czasu nadawania
    // Pomiary ataku na rozsyłanie (k1stats=1).
    uint32_t floodOverCap = 0; // rozsyłania przy puli ponad 25%, gdy czekała inna ramka K1 ze znaną drogą
    uint64_t floodOverCapMs = 0;
    uint32_t unicastRefused = 0; // ramki jednoadresowe odrzucone przez dziennik czasu nadawania
    uint32_t over25S = 0, full60S = 0; // sekundy z pulą ponad 25% i wyczerpaną pulą 60%
    uint32_t floodWindow = 0, floodsInWindow = 0, maxFloods120S = 0;
};

class Net;

struct Fram : journal::Storage {
    std::vector<uint8_t> bytes = std::vector<uint8_t>(0x048000, 0);
    bool read(uint32_t at, uint8_t* out, size_t n) override {
        if (at > bytes.size() || n > bytes.size() - at) return false;
        memcpy(out, bytes.data() + at, n);
        return true;
    }
    bool write(uint32_t at, const uint8_t* in, size_t n) override {
        if (at > bytes.size() || n > bytes.size() - at) return false;
        memcpy(bytes.data() + at, in, n);
        return true;
    }
};

// Odpowiednik Bench i WiciAir (main.cpp, measure.cpp) dla jednego węzła.
class Radio : public wici_link::Air {
public:
    enum class State : uint8_t { IDLE, WAIT_DEBT, BACKOFF, LISTEN, CAD, SENDING };

    Radio(Net& net, int index, Fram& fram, wici_hop_auth::Auth& auth, wici_airtime::Budget& budget)
        : net_(net), index_(index), auth_(auth), budget_(budget) { (void)fram; }

    bool sendData(const uint8_t* wire, size_t length, wici_link::TxClass traffic) override;
    bool accepts(wici_link::TxClass traffic, size_t radioLength) override;
    bool sendHack(const uint8_t* wire, size_t length, uint32_t receivedMs) override;

    // Co milisekundę, gdy nie jest IDLE.
    void poll(uint32_t now);
    bool idle() const { return state_ == State::IDLE; }
    uint32_t debtLeft(uint32_t now) const { return debtUntil_ > now ? debtUntil_ - now : 0; }
    // Koniec nadawania tej ramki: wynik dla koordynatora, dług ciszy.
    void txEnded(uint32_t now);
    void holdForHack(uint32_t now, uint32_t receivedMs);
    bool silent = false;  // cisza radiowa: nic nie nadaje
    // HACK czeka na start albo trwa: pętla stacji stoi jak w Bench::linkSendHack.
    bool blocked(uint32_t now) const { return state_ == State::SENDING || now < hackUntil_; }

private:
    void startListen(uint32_t now, bool first);
    void defer(uint32_t now);
    bool channelBusy(uint32_t now);
    void beginTx(uint32_t now);

    Net& net_;
    int index_;
    wici_hop_auth::Auth& auth_;
    wici_airtime::Budget& budget_;
    State state_ = State::IDLE;
    uint8_t frame_[wici_link::MAX_FRAME] = {};
    size_t length_ = 0;
    uint32_t debtUntil_ = 0, backoffUntil_ = 0, listenStart_ = 0, cadEnd_ = 0, hackHoldUntil_ = 0;
    uint32_t deferrals_ = 0;
    uint32_t lastTxEnd_ = 0, hackUntil_ = 0;
};

// Zgłoszenia stacji: skrót Station::poll, transmit, finishFlight (station.cpp).
struct Report {
    uint32_t id = 0;
    uint32_t createdMs = 0, firstHackMs = 0, closedMs = 0;
    uint32_t nextTryS = 0, attempts = 0, firstSentS = 0;
    uint32_t hacked = 0;  // nadania z HACK od ostatniej wiadomości od odbiorcy (próg w próbach)
    bool probe = false;   // próbka przekaźnika, nie zgłoszenie: poza wynikami i bez wpisu w panelu
    bool delivered = false, closed = false;
    uint16_t station = 0;
    size_t size = 174;
};

struct Node {
    Net* net = nullptr;
    int index = 0;
    uint16_t id = 0, planned = 0, backup = 0;
    bool isRoot = false;
    bool dead = false;        // wyłączona: nie słyszy i nie nadaje
    bool dropper = false;     // daje HACK i porzuca ruch (przejęta albo uszkodzona stacja)
    bool forger = false;      // dodatkowo podaje w górę ramki z cudzym `src` koperty
    bool lowRank = false;     // ogłasza fałszywie niską rangę
    bool selective = false;   // przepuszcza własny ruch bezpośredniego dziecka i ruch w dół, porzuca resztę po HACK
    uint16_t fakeDownTo = 0;  // podsuwa temu dziecku ramki w dół, żeby widziało powrót
    std::vector<uint16_t> fakeTargets; // próba rozsyłania: kolejni sąsiedzi dostają ramki do numerów bez drogi
    uint32_t fakeEveryMs = 0;
    bool fakeNoRoute = false; // ramki w dół co 10 s do numeru bez drogi: gniazda K1 sąsiada zapełniają się rozsyłaniem
    uint32_t nextFakeMs = 0;
    uint32_t nextForgeMs = 0;
    std::vector<uint16_t> forgeRelays;   // komu podaje podrobione ramki
    uint16_t forgeSeq = 1;
    uint32_t forgeCounter = 1;
    std::vector<uint16_t> victims;
    size_t nextVictim = 0;
    uint8_t secret[64] = {};
    uint8_t xPublic[32] = {}, edPublic[32] = {};
    std::unique_ptr<Fram> fram;
    wici_hop_auth::Auth auth;
    std::unique_ptr<wici_airtime::Budget> budget;
    std::unique_ptr<Radio> radio;
    std::unique_ptr<wici_radio::Shelter> shelter;
    std::unique_ptr<kiss::Port> port;
    std::unique_ptr<wici_gateway::Root> root;
    std::vector<config::PriorityKey> peers;
    std::vector<config::Behind> behind;
    Rng rng;

    // Harmonogram BEACON-ów, jak w main.cpp.
    uint32_t nextBeaconMs = 0, lastBeaconMs = 0;
    uint16_t advertisedParent = 0, advertisedRank = 0xFFFF, scheduledParent = 0, scheduledRank = 0xFFFF;
    uint8_t beacons = 0;
    uint16_t lastParent = 0;

    // Sprawdzenie BEACON-u w tle: wirtualny drugi rdzeń.
    struct Check : wici_radio::BeaconCheck {
        Net* net = nullptr;
        void (*job)(void*) = nullptr;
        void* argument = nullptr;
        uint32_t dueMs = 0;
        bool start(void (*check)(void*), void* context) override;
        void poll(uint32_t now) {
            if (job && now >= dueMs) {
                void (*run)(void*) = job;
                job = nullptr;
                run(argument);
            }
        }
    } check;

    // Zgłoszenia.
    std::vector<Report*> reports;
    uint32_t lastHandle = 0;
    struct Flight { Report* report = nullptr; uint32_t handle = 0, sentS = 0; } flights[2];
    uint32_t lastReceiverMsgS = 0;  // ostatnia uwierzytelniona wiadomość od odbiorcy
    uint32_t leaveTimerS = 0;       // wariant: początek czasu bez odpowiedzi przy otwartej wiadomości
    uint32_t upWaitS = 0;           // próbka: przekazany ruch w górę czeka na powrót od tej chwili
    uint32_t lastProbeS = 0;
    uint32_t lastTxMs = 0;
    NodeStats stats;
};

// Skrót stanowiska: WiciStos i Wysylka (software/laptop/wici/stanowisko).
class Laptop {
public:
    struct Intent {
        uint16_t dest = 0;
        uint32_t reportId = 0;
        std::vector<uint8_t> plain;
        uint32_t attempts = 0, firstTryS = 0, nextTryS = 0, forwarded = 0;
        bool done = false, flying = false, hasFirstTry = false;
    };
    struct Delivery {
        size_t intent = 0;
        std::vector<std::vector<uint8_t>> frames;
        uint16_t destination = 0;
        size_t part = 0;
        bool hasSequence = false;
        uint16_t sequence = 0;
        std::vector<uint8_t> onAir;
        uint32_t submissions = 0, attempts = 0, sentMs = 0, retryMs = 0;
        bool relayed = false, flooded = false, lastOwn = false;
        bool flood = false;   // wariant: ta próba idzie rozsyłaniem
        int result = -1;      // -1 w toku, 0 porażka, 1 doręczone, 2 przekazane, 3 rozesłane
    };

    Laptop(Net& net, Node& rootNode);
    void tick(uint32_t now);
    void setOpen(bool open);
    bool open() const { return open_; }
    size_t openIntents() const;
    uint32_t floods = 0, routed = 0, refused = 0, deliveredIntents = 0, duplicates = 0, rejected = 0;
    uint32_t floodsDeferred = 0;
    // Wiadomość do stacji poza łańcuchem zgłoszeń (S7: rozsyłanie przy pustych drogach).
    void enqueue(uint16_t dest, uint32_t reportId, size_t size);

private:
    enum Outcome { PARTIAL, COMPLETE, DUPLICATE, PROOF, SETTLED };
    void readPort(uint32_t now);
    void handle(uint8_t command, const std::vector<uint8_t>& wire, uint32_t now);
    void receive(const std::vector<uint8_t>& wire, uint32_t now);
    Outcome admit(const wici_link::Frame& frame, uint32_t now);
    bool hackAllowed(const std::vector<uint8_t>& wire, Outcome outcome, uint32_t now);
    void portTick(uint32_t now);
    void submit(Delivery& item, uint32_t now);
    void nextPart(Delivery& item);
    void finish(Delivery& item, int result);
    void wysylkaTick(uint32_t now);
    void failed(Intent& intent, uint32_t nowS);
    void forwardedIntent(Intent& intent, uint32_t nowS, bool custody);
    uint32_t retryDelay(uint32_t attempts, uint32_t ageS);
    Delivery* sentItem(const uint8_t* payload, size_t length);
    bool answers(const Delivery& item, const wici_link::Frame& hack);
    bool wantsFlood(const Delivery& item) const;

    Net& net_;
    Node& node_;
    uint8_t key_[32] = {};
    bool open_ = false;
    std::vector<uint8_t> stream_;
    bool inFrame_ = false, escape_ = false;
    struct Timed { uint32_t dueMs; uint8_t command; std::vector<uint8_t> wire; };
    std::deque<Timed> usb_, admissions_;
    std::map<uint16_t, std::array<uint8_t, 32>> keysUp_, keysDown_;
    std::map<uint16_t, uint32_t> counters_;
    std::map<uint16_t, std::set<uint32_t>> replay_;
    std::map<std::pair<uint16_t, uint32_t>, std::vector<uint8_t>> partial_;
    std::map<std::pair<uint16_t, uint32_t>, size_t> sent_;  // (stacja, licznik koperty) -> intencja
    std::map<std::pair<uint16_t, uint32_t>, size_t> byReport_;
    std::deque<Intent> intents_;
    std::vector<std::unique_ptr<Delivery>> flight_;   // po jednej na stację
    std::vector<std::unique_ptr<Delivery>> waiting_;  // za inną do tej samej stacji
    Delivery* outstanding_ = nullptr;                 // czeka na echo albo odmowę roota
    uint16_t turn_ = 0;
    std::map<std::vector<uint8_t>, std::pair<uint32_t, bool>> seen_;
    bool repeatSent_ = false;
    uint32_t repeatMs_ = 0;
    uint32_t nextWysylkaMs_ = 0;
    uint32_t nextFloodMs_ = 0;
    Rng rng_;
};

struct LinkInfo {
    uint16_t permille = 0;   // skuteczność ramki bez kolizji; 0: tylko zakłóca, nie da się odebrać
    bool audible = false;    // odbiornik słyszy nadajnik (CAD, RSSI, kolizja)
};

// Ramka w eterze.
struct Air {
    int from = 0;
    uint32_t startMs = 0, endMs = 0;
    std::vector<uint8_t> bytes;
    bool isHack = false;
    bool ended = false;
    uint32_t id = 0;
};

// Stan odbioru jednego węzła.
struct Rx {
    uint32_t locked = 0;    // id ramki, którą odbiera; 0 nic
    bool corrupted = false;
    uint32_t audible = 0;   // ile słyszalnych ramek jest teraz w eterze
    uint32_t lastActivityMs = 0;
    bool transmitting = false;
};

class Net {
public:
    Net(size_t count, uint64_t seed, Assumptions assumptions, Variant variant);
    ~Net();

    // Przed startem: kto kogo słyszy i kto jest czyim rodzicem.
    void link(int a, int b, uint32_t permille);          // dwukierunkowo, odbiór i nasłuch
    void interfere(int a, int b);                        // słychać, ale nie da się odebrać
    void setParents(int station, int planned, int backup);
    void addPeer(int a, int b);                          // para kluczy bez łącza radiowego (np. poza zasięgiem)
    void rootPlan(uint16_t station, uint16_t via);       // `behind` roota
    void start();

    void setLinkPermille(int a, int b, uint32_t permille);
    void setAudible(int a, int b, bool audible);

    void run(uint32_t untilMs);
    template <typename Stop>
    void runUntil(uint32_t untilMs, Stop stop) {
        while (now_ < untilMs) {
            step();
            if (now_ % 1000 == 0 && stop()) return;
        }
    }

    Report* report(int station, size_t size = 174);
    void leave(Node& n, uint32_t nowSeconds);
    bool allClosed() const;
    size_t realReports() const;
    uint32_t realArrived() const;
    uint32_t now() const { return now_; }
    uint32_t nowS() const { return now_ / 1000 + START_S; }
    size_t size() const { return nodes_.size(); }
    Laptop& laptop() { return *laptop_; }
    const Assumptions& assumptions() const { return assumptions_; }
    const Variant& variant() const { return variant_; }
    Rng& rng() { return rng_; }
    int indexOf(uint16_t id) const { return id >= 2 && static_cast<size_t>(id - 1) < nodes_.size() ? id - 1 : id == ROOT_ID ? 0 : -1; }

    // Dla Radio.
    void startAir(int from, const uint8_t* bytes, size_t length, bool isHack, uint32_t startMs);
    bool hearsNow(int index) const { return rx_[static_cast<size_t>(index)].audible > 0; }
    bool rxPending(int index) const { return rx_[static_cast<size_t>(index)].locked != 0; }
    uint32_t lastActivity(int index) const { return rx_[static_cast<size_t>(index)].lastActivityMs; }

    // Dla Laptop.
    void reportArrived(uint32_t reportId, uint32_t now);
    void reportClosed(uint32_t reportId, uint32_t now);
    const std::vector<std::unique_ptr<Report>>& reports() const { return reports_; }
    const uint8_t* linkKey() const { return linkKey_; }
    const uint8_t* ifac() const { return ifac_; }
    const uint8_t* receiverSecret() const { return receiverSecret_; }
    const uint8_t* receiverPublic() const { return receiverPublic_; }
    const uint8_t* rootEd() const { return node(0).edPublic; }
    Node& node(int index) const { return *nodes_[static_cast<size_t>(index)]; }

    // Liczniki całej sieci.
    uint32_t hacksOnAir = 0, lastHackMs = 0, longestStallMs = 0;
    bool trackStall = false;
    uint32_t arrivedCount = 0;
    std::map<uint32_t, uint32_t> arrivedMs;  // id zgłoszenia -> pierwsze przyjęcie na stanowisku
    uint32_t channelBusyMs = 0;              // czas, gdy cokolwiek jest w eterze
    std::vector<uint32_t> closedPerBucket;   // domknięte zgłoszenia na 10 min
    std::vector<uint32_t> hacksPerBucket;    // HACK-i na 10 min

    uint16_t ttl = 15;
    uint32_t epochSeed = 1;
    bool k1Stats = false;                        // pomiary ataku na rozsyłanie
    bool trace = false;                          // zapis przebiegu na stderr: ramki, odbiory, zmiany rodzica, migawki dróg
    uint16_t traceStation = 0;                   // czyje drogi pokazują migawki (0: ostatnia stacja łańcucha)
    std::map<uint32_t, uint32_t> downArrivedMs;  // wiadomość w dół -> pierwsze przyjęcie na stacji
    void restartRoot(uint16_t epoch);            // nowa epoka po powrocie stanowiska
    void forgeVictims(int attacker, std::vector<uint16_t> victims);

private:
    void step();
    void stepAir();
    void endAir(Air& air);
    void pollNode(Node& node);
    void pollApp(Node& node);
    void pollBeacon(Node& node);
    void pollHostile(Node& node);
    void pollProbe(Node& node);
    void pollFakeDown(Node& node);
    void noteTraffic(Node& node, const uint8_t* bare, size_t length);
    void deliver(Node& node, const uint8_t* bytes, size_t length, uint32_t now);
    void buildKeys(Node& node);
    void traceAir(const Air& air, char event, int receiver);
    void traceSnapshot();

    Assumptions assumptions_;
    Variant variant_;
    Rng rng_;
    std::vector<std::unique_ptr<Node>> nodes_;
    std::vector<std::vector<LinkInfo>> links_;
    std::vector<Rx> rx_;
    std::deque<Air> pendingStart_;
    std::deque<Air> onAir_;
    std::unique_ptr<Laptop> laptop_;
    std::vector<std::unique_ptr<Report>> reports_;
    uint8_t ifac_[16] = {}, linkKey_[32] = {};
    uint8_t receiverSecret_[32] = {}, receiverPublic_[32] = {};
    uint32_t now_ = 0, nextAirId_ = 1, nextReportId_ = 1;
};

}  // namespace emu
