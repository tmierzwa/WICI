// SPDX-License-Identifier: MIT
// Próba odporności stosu Reticulum stacji na komputerze (tests/test_rns_hostile.py): ruch od
// węzła z kodem IFAC (ważne ogłoszenia, zapytania o trasę, pakiety do stacji i przez stację,
// dowody, żądania łącza, powtórki) z mutacjami, przez warstwę rnsnode jak na stacji, z zegarem
// symulowanym (dni i tygodnie w sekundach) i z FRAM w pliku, w której zapis może się urwać
// w dowolnym miejscu (zanik zasilania). Jeden proces to jeden start stacji; FRAM, zegar
// i skrót tożsamości przechodzą do następnego startu w plikach obok FRAM.
//
// Generator ruchu buduje pakiety prymitywami rdzenia (lib/reticulum_core: tożsamość, ogłoszenie, pack, token,
// dowód; sprawdzone wektorami Reticulum w Pythonie), a klucze, skróty losowe i IV biorą się tylko z --seed
// (rnd()). Ten sam generator działa dla stacji na porcie i na rdzeniu; stos stacji widzi ruch wyłącznie jako
// datagramy z IFAC w rnsnode::received() (toStation()).
// Wynik: wiersz JSON na stdout; kod 3 = złamany niezmiennik, 75 = zanik zasilania w zapisie.
//
// rns_stress <fram> [--seed N] [--events N] [--mutate PERCENT] [--start S] [--gap S]
//            [--long-jumps] [--cut-after-writes N] [--defect token48|short-announce|held-announce|link-mtu|flood|station-flood|damaged-receiver|forward-flood|rebroadcast-load|own-path-requests|path-flood]
//            [--hostile-days N [--window-s S] [--stop-after-s S]] [--receiver-foreign-key] [--dump PLIK]
//
// --dump: datagramy generatora z feed() (rodzaj, czy mutowany, pakiet przed IFAC i datagram na łączu) po wierszu
// JSON, na początku klucze generatora i klucz prywatny stacji z FRAM (tylko w próbie); tools/rns_differential.py
// --stress-dump sprawdza nimi w Reticulum w Pythonie, że niezmutowany ruch jest poprawny (tests/test_rns_differential.py). Pole "generated" wyniku: datagramy
// generatora według rodzaju (feed() i powtórki).
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/time.h>
#include <unistd.h>

// Hak przydziałów sterty jest tylko w budowie z ASan (tests/test_rns_hostile.py buduje zawsze z nim);
// bez niego przebieg 60 dni podaje przydziały jako niezmierzone (null).
#if defined(__has_feature)
#if __has_feature(address_sanitizer)
#define WICI_ALLOCATION_HOOK 1
#endif
#endif
#if defined(__SANITIZE_ADDRESS__)
#define WICI_ALLOCATION_HOOK 1
#endif
#if defined(WICI_RNS_CORE) && defined(WICI_ALLOCATION_HOOK)
#include <sanitizer/allocator_interface.h>
#endif

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include <RNG.h>
#include <SHA256.h>   // HMAC w --defect token48 (biblioteka Crypto, jak w rdzeniu)

#include "announce.h"
#include "destination.h"
#include "hkdf.h"
#include "identity.h"
#include "lxmf.h"
#include "packet.h"
#include "proof.h"
#include "token.h"
#include "transport.h"

#include "framfs.h"
#include "p1iface.h"
#include "rns_node.h"

namespace {

// ---- zegar symulowany: rns_node (debugClock) i stos przez gettimeofday ----
uint64_t simMs = 0;
uint64_t simClock() { return simMs; }

}  // namespace

// Zegar stosu stacji na porcie i microStore (rns_stress_port.cpp, tylko w budowie z portem): opis błędu albo
// nullptr. Rdzeń bierze czas wyłącznie z rnsnode::debugClock.
#ifdef WICI_RNS_CORE
static const char* stackClockError(uint64_t) { return nullptr; }
#else
const char* stackClockError(uint64_t ms);
#endif

extern "C" int gettimeofday(struct timeval* __restrict tv, void* __restrict) {
    tv->tv_sec = static_cast<time_t>(simMs / 1000);   // glibc deklaruje tv jako nonnull
    tv->tv_usec = static_cast<suseconds_t>((simMs % 1000) * 1000);
    return 0;
}

// steady_clock też z zegara symulowanego: na hoście microStore::millis() (odstęp ponownej kompaktacji
// FileStore, USTORE_COMPACT_RETRY_MS) i Stream biorą z niego czas, a definicja w programie ma
// pierwszeństwo przed biblioteką standardową (dynamiczną). Bez tego stan FRAM portu zależał od czasu
// rzeczywistego.
std::chrono::steady_clock::time_point std::chrono::steady_clock::now() noexcept {
    return time_point(std::chrono::duration_cast<duration>(std::chrono::milliseconds(simMs)));
}

namespace {

// Nazwa celów stacji i węzłów generatora: port "wici.sa1", rdzeń od etapu R3 "lxmf.delivery".
#ifdef WICI_RNS_CORE
constexpr const char* DEST_APP = "lxmf";
constexpr const char* DEST_ASPECT = "delivery";
#else
constexpr const char* DEST_APP = rnsnode::APP_NAME;
constexpr const char* DEST_ASPECT = rnsnode::ASPECT;
#endif
const std::string DEST_NAME = std::string(DEST_APP) + "." + DEST_ASPECT;
constexpr int EXIT_INVARIANT = 3;
constexpr int EXIT_POWER_CUT = 75;
constexpr size_t FRAM_BYTES = 512 * 1024;

uint32_t rngState = 1;
uint32_t rnd() {
    rngState = rngState * 1103515245u + 12345u;
    return (rngState >> 16) & 0x7fff;
}
uint32_t rnd32() { return (rnd() << 15) ^ rnd(); }

using Bytes = std::vector<uint8_t>;

Bytes randomBytes(size_t n) {
    Bytes b(n);
    for (uint8_t& x : b) x = static_cast<uint8_t>(rnd());
    return b;
}

Bytes& operator<<(Bytes& to, const Bytes& more) {
    to.insert(to.end(), more.begin(), more.end());
    return to;
}

Bytes left(const Bytes& b, size_t n) { return Bytes(b.begin(), b.begin() + static_cast<long>(n < b.size() ? n : b.size())); }

std::string hex(const uint8_t* d, size_t n) {
    static const char* digits = "0123456789abcdef";
    std::string s;
    for (size_t i = 0; i < n; ++i) { s += digits[d[i] >> 4]; s += digits[d[i] & 15]; }
    return s;
}

// Tożsamość Reticulum (identity.h): klucz prywatny 64 B, publiczny i skrót tożsamości; stacja ma tu tylko
// klucz publiczny i skrót.
struct Identity {
    uint8_t prv[rnscore::KEY_SIZE] = {};
    uint8_t pub[rnscore::KEY_SIZE] = {};
    uint8_t hash[rnscore::TRUNCATED_HASH_SIZE] = {};
};

Identity fromPrivate(const uint8_t prv[rnscore::KEY_SIZE]) {
    Identity id;
    memcpy(id.prv, prv, sizeof(id.prv));
    rnscore::publicKey(id.prv, id.pub);
    rnscore::identityHash(id.pub, id.hash);
    return id;
}

// Nowa tożsamość z rnd() (w Pythonie Identity() z os.urandom).
Identity newIdentity() {
    uint8_t prv[rnscore::KEY_SIZE];
    for (uint8_t& b : prv) b = static_cast<uint8_t>(rnd());
    return fromPrivate(prv);
}

}  // namespace

#ifdef WICI_COVERAGE
// Pomiar pokrycia wierszy (clang -fprofile-instr-generate): _exit() pomija zapis profilu przy wyjściu.
extern "C" int __llvm_profile_write_file(void);
#endif

namespace {

// Koniec procesu bez destruktorów statycznych portu (kolejność niszczenia nie jest częścią próby).
[[noreturn]] void quit(int code) {
#ifdef WICI_COVERAGE
    __llvm_profile_write_file();
#endif
    _exit(code);
}

[[noreturn]] void fail(const char* what) {
    printf("{\"result\":\"invariant\",\"what\":\"%s\"}\n", what);
    fflush(stdout);
    quit(EXIT_INVARIANT);
}

// ---- FRAM w pliku (mmap), z zanikiem zasilania po N zapisach ----
struct FileFram : journal::Storage {
    uint8_t* bytes = nullptr;
    long cutAfter = -1;      // numer zapisu, w którym znika zasilanie (-1: bez zaniku)
    long writes = 0;
    std::string clockPath;

    bool open(const std::string& path) {
        const int fd = ::open(path.c_str(), O_RDWR | O_CREAT, 0644);
        if (fd < 0) return false;
        off_t size = lseek(fd, 0, SEEK_END);
        if (size != static_cast<off_t>(FRAM_BYTES)) {
            if (ftruncate(fd, FRAM_BYTES) != 0) return false;
            size = 0;
        }
        void* m = mmap(nullptr, FRAM_BYTES, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        ::close(fd);
        if (m == MAP_FAILED) return false;
        bytes = static_cast<uint8_t*>(m);
        if (size == 0) memset(bytes, 0xFF, FRAM_BYTES);   // nowy układ: same 0xFF
        return true;
    }
    bool read(uint32_t address, uint8_t* data, size_t count) override {
        if (address + count > FRAM_BYTES) return false;
        memcpy(data, bytes + address, count);
        return true;
    }
    bool write(uint32_t address, const uint8_t* data, size_t count) override;
};

FileFram fram;

void saveClock() {
    if (FILE* f = fopen(fram.clockPath.c_str(), "w")) {
        fprintf(f, "%llu\n", static_cast<unsigned long long>(simMs));
        fclose(f);
    }
}

bool FileFram::write(uint32_t address, const uint8_t* data, size_t count) {
    if (address + count > FRAM_BYTES) return false;
    if (writes++ == cutAfter) {
        // Zanik w trakcie zapisu: dochodzi tylko początek danych (FRAM zapisuje bajt po bajcie).
        const size_t part = count ? rnd() % count : 0;
        memcpy(bytes + address, data, part);
        msync(bytes, FRAM_BYTES, MS_SYNC);
        saveClock();
        printf("{\"result\":\"power_cut\",\"write\":%ld,\"address\":%u,\"count\":%u,\"written\":%u}\n", writes - 1, address,
               static_cast<unsigned>(count), static_cast<unsigned>(part));
        fflush(stdout);
        quit(EXIT_POWER_CUT);
    }
    memcpy(bytes + address, data, count);
    return true;
}

// Skrót całego ruchu przebiegu (FNV-1a 64): datagramy do stacji i od stacji w kolejności. Te same --seed
// i zegar symulowany dają ten sam skrót (test_same_seed_same_traffic; generator z rnd(), RNG portu z ziarna: rng_seeded.cpp).
uint64_t trafficHash = 0xcbf29ce484222325ull;
void hashTraffic(uint8_t direction, const uint8_t* data, size_t length) {
    trafficHash = (trafficHash ^ direction) * 0x100000001b3ull;
    for (size_t i = 0; i < length; ++i) trafficHash = (trafficHash ^ data[i]) * 0x100000001b3ull;
}

// Datagram z IFAC do stacji (wszystkie wejścia ruchu przechodzą tędy).
void toStation(const uint8_t* wire, size_t length) {
    hashTraffic(0, wire, length);
    rnsnode::received(wire, length);
}

// Wywołanie stosu stacji w toku (liczenie przydziałów sterty w hostileDays; radio próby się nie liczy).
bool inStation = false;

// Hak packet stacji rozstrzyga losowo trzy z czterech pakietów (rnd()); settleAll: każdy, gdy scenariusz
// wymaga dowodu dla swojej wiadomości.
bool settleAll = false;
uint32_t appPackets = 0;   // wiadomości przekazane hakowi packet stacji (warstwie aplikacji)

// ---- łącze radiowe: datagramy stacji trafiają do generatora (powtórki, dowody) ----
struct Radio : rnsnode::Radio {
    bool busy = false;
    uint64_t txEnd = 0;
    uint32_t sent = 0;
    std::vector<std::vector<uint8_t>> recent;   // ostatnie datagramy stacji (z IFAC)
    bool ready() override { return !busy; }
    uint32_t debtMs() override { return 0; }
    bool transmit(const uint8_t* data, size_t length) override {
        ++sent;
        hashTraffic(1, data, length);
        const bool counted = inStation;
        inStation = false;
        if (recent.size() >= 32) recent.erase(recent.begin());
        recent.emplace_back(data, data + length);
        inStation = counted;
        busy = true;
        txEnd = simMs + 50 + length;   // czas nadawania nie gra roli w tej próbie
        return true;
    }
    void poll() {
        if (busy && simMs >= txEnd) {
            busy = false;
            rnsnode::txDone(true);
        }
    }
};

Radio radio;

// ---- IFAC: klucz sieci stacji; kod liczy ta sama funkcja interfejsu P1 co przy nadawaniu ----
const uint8_t IFAC_KEY[16] = {0x57, 0x49, 0x43, 0x49, 0x2d, 0x73, 0x74, 0x72, 0x65, 0x73, 0x73, 0x2d, 0x69, 0x66, 0x61, 0x63};

std::vector<uint8_t> ifacWrap(const Bytes& raw) {
    std::vector<uint8_t> wire(p1iface::MAX_WIRE);
    wire.resize(rnsnode::debugIfacWrap(raw.data(), raw.size(), wire.data()));
    return wire;
}

Bytes ifacUnwrap(const std::vector<uint8_t>& wire) {
    uint8_t raw[p1iface::MAX_WIRE];
    const size_t n = rnsnode::debugIfacUnwrap(wire.data(), wire.size(), raw);
    return Bytes(raw, raw + n);
}

// Pakiet ponad HW_MTU: datagram z flagą IFAC i dowolnym kodem, dłuższy niż MAX_WIRE (stacja go odrzuca).
std::vector<uint8_t> oversize(const std::vector<uint8_t>& v) {
    std::vector<uint8_t> wire{static_cast<uint8_t>(v[0] | 0x80), v[1]};
    for (size_t i = 0; i < p1iface::IFAC_SIZE; ++i) wire.push_back(static_cast<uint8_t>(rnd()));
    wire.insert(wire.end(), v.begin() + 2, v.end());
    return wire;
}

// ---- węzły generatora: tożsamości wymyślonych stacji (pierwsza jest odbiorcą stacji) ----
constexpr size_t PEERS = 24;
std::vector<Identity> peers;
std::vector<Bytes> peerDest;     // cele DEST_NAME węzłów
Identity station;                // tylko klucz publiczny i skrót tożsamości
Bytes stationDest, stationTransport;
std::vector<Bytes> recentHashes, linkIds;
std::vector<std::vector<uint8_t>> recentWire;
uint32_t mutatePercent = 0;
uint32_t fed = 0, mutated = 0;

// Datagramy generatora według rodzaju (pole "generated"); rodzaje w kolejności pierwszego użycia.
std::vector<std::pair<std::string, uint32_t>> generated;
void countGenerated(const char* kind) {
    for (auto& g : generated) {
        if (g.first == kind) { ++g.second; return; }
    }
    generated.emplace_back(kind, 1);
}

std::string generatedJson() {
    std::string out;
    for (const auto& g : generated) out += (out.empty() ? "\"" : ",\"") + g.first + "\":" + std::to_string(g.second);
    return out;
}

FILE* dump = nullptr;   // --dump

void remember(std::vector<Bytes>& v, const Bytes& b) {
    if (v.size() < 64) v.push_back(b);
    else v[rnd() % v.size()] = b;
}

Bytes headerTwo(const Bytes& raw, const Bytes& transportId) {
    if (raw.size() < 2) return raw;
    Bytes out{static_cast<uint8_t>(raw[0] | 0x40 | 0x10), raw[1]};
    out << transportId;
    out.insert(out.end(), raw.begin() + 2, raw.end());
    return out;
}

Bytes withHops(Bytes raw, uint8_t hops) {
    if (raw.size() >= 2) raw[1] = hops;
    return raw;
}

// ---- pakiety prymitywami rdzenia ----
Bytes destinationOf(const char* name, const uint8_t* identityHash) {
    Bytes d(rnscore::TRUNCATED_HASH_SIZE);
    rnscore::destinationHash(name, identityHash, d.data());
    return d;
}

// Pakiet HEADER_1 bez transportu (Packet.pack); pusty, gdy pack go nie przyjmie (puste dane, ponad MTU).
Bytes packet(rnscore::PacketType type, rnscore::DestinationType destinationType, const Bytes& destination, const Bytes& data,
             uint8_t context = 0) {
    rnscore::Packet p{};
    p.headerType = rnscore::HEADER_1;
    p.transportType = rnscore::BROADCAST;
    p.destinationType = destinationType;
    p.packetType = type;
    memcpy(p.destinationHash, destination.data(), rnscore::TRUNCATED_HASH_SIZE);
    p.context = context;
    p.data = data.data();
    p.dataLength = data.size();
    Bytes raw(rnscore::MTU);
    raw.resize(rnscore::pack(p, raw.data(), raw.size()));
    return raw;
}

// Pakiet DATA do celu SINGLE tożsamości to: token (Identity.encrypt bez ratchetu) z kluczem efemerycznym
// i IV z rnd().
Bytes dataTo(const Identity& to, const Bytes& destination, const Bytes& plaintext) {
    uint8_t ephemeral[rnscore::KEY_SIZE / 2], iv[rnscore::TOKEN_IV_SIZE];
    for (uint8_t& b : ephemeral) b = static_cast<uint8_t>(rnd());
    for (uint8_t& b : iv) b = static_cast<uint8_t>(rnd());
    Bytes token(rnscore::tokenSize(plaintext.size()));
    if (!rnscore::encrypt(to.pub, nullptr, ephemeral, iv, plaintext.data(), plaintext.size(), token.data(), token.size())) token.clear();
    return packet(rnscore::DATA, rnscore::SINGLE, destination, token);
}

// Ogłoszenie celu name tożsamości id (Destination.announce): skrót losowy z rnd() i czasu symulowanego;
// pathResponse: kontekst PATH_RESPONSE.
Bytes announce(const Identity& id, const char* name, const Bytes& appData, bool pathResponse) {
    uint8_t nameHash[rnscore::NAME_HASH_SIZE], random[5], randomHash[rnscore::RANDOM_HASH_SIZE];
    rnscore::nameHash(name, nameHash);
    const Bytes destination = destinationOf(name, id.hash);
    for (uint8_t& b : random) b = static_cast<uint8_t>(rnd());
    rnscore::announceRandomHash(random, simMs / 1000, randomHash);
    Bytes data(rnscore::ANNOUNCE_FORWARDABLE_SIZE);
    data.resize(rnscore::buildAnnounce(id.prv, id.pub, destination.data(), nameHash, randomHash, nullptr, appData.data(),
                                       appData.size(), data.data(), data.size()));
    return packet(rnscore::ANNOUNCE, rnscore::SINGLE, destination, data, pathResponse ? rnscore::CONTEXT_PATH_RESPONSE : 0);
}

// Zapytanie o trasę (Transport.request_path): DATA do celu PLAIN "rnstransport.path.request".
Bytes pathRequestOf(const Bytes& data) {
    static const Bytes destination = destinationOf("rnstransport.path.request", nullptr);
    return packet(rnscore::DATA, rnscore::PLAIN, destination, data);
}

// Pełny skrót pakietu (Packet.get_hash); pusty, gdy unpack go nie przyjmie.
Bytes packetHash(const Bytes& raw) {
    rnscore::Packet p;
    if (!rnscore::unpack(raw.data(), raw.size(), p)) return {};
    Bytes h(rnscore::HASH_SIZE);
    rnscore::packetHash(raw.data(), raw.size(), h.data());
    return h;
}

// Identyfikator łącza z żądania (Link.link_id_from_lr_packet): ucięty skrót pakietu bez bajtów ponad klucze
// (sygnalizacja MTU); pusty, gdy unpack go nie przyjmie.
Bytes linkIdOf(const Bytes& raw) {
    rnscore::Packet p;
    if (!rnscore::unpack(raw.data(), raw.size(), p) || p.dataLength < rnscore::KEY_SIZE) return {};
    uint8_t h[rnscore::HASH_SIZE];
    rnscore::packetHash(raw.data(), raw.size() - (p.dataLength - rnscore::KEY_SIZE), h);
    return Bytes(h, h + rnscore::TRUNCATED_HASH_SIZE);
}

// Jawny dowód tożsamości id dla pakietu raw (Identity.prove, implicit False): PROOF do celu równego uciętemu
// skrótowi pakietu.
Bytes proofOf(const Bytes& raw, const Identity& id) {
    uint8_t h[rnscore::HASH_SIZE], proof[rnscore::PROOF_EXPLICIT_SIZE];
    rnscore::packetHash(raw.data(), raw.size(), h);
    const size_t n = rnscore::prove(id.prv, id.pub, h, false, proof);
    return packet(rnscore::PROOF, rnscore::SINGLE, Bytes(h, h + rnscore::TRUNCATED_HASH_SIZE), Bytes(proof, proof + n));
}

uint8_t randomHops() {
    const uint32_t r = rnd() % 10;
    return r < 6 ? rnd() % 8 : r < 9 ? rnd() % 128 : 120 + rnd() % 136;
}

void mutate(std::vector<uint8_t>& v, size_t keep) {
    const int ops = 1 + rnd() % 6;
    for (int k = 0; k < ops; ++k) {
        if (v.size() <= keep + 1) { v.push_back(static_cast<uint8_t>(rnd())); continue; }
        const size_t at = keep + rnd() % (v.size() - keep);
        switch (rnd() % 8) {
            case 0: v[at] ^= static_cast<uint8_t>(1u << (rnd() % 8)); break;
            case 1: v[at] = static_cast<uint8_t>(rnd()); break;
            case 2: v.erase(v.begin() + at); break;
            case 3: v.insert(v.begin() + at, static_cast<uint8_t>(rnd())); break;
            case 4: v[at] = (rnd() & 1) ? 0x00 : 0xFF; break;
            case 5: v.resize(at + 1); break;
            case 6: v[0] ^= static_cast<uint8_t>(1u << (rnd() % 7)); break;   // bez bitu IFAC
            case 7: for (uint32_t n = 50 + rnd() % 250; n && v.size() < 700; --n) v.push_back(static_cast<uint8_t>(rnd())); break;
        }
    }
}

// Pakiet Reticulum (bez IFAC) do stacji: mutacja przed kodem IFAC (węzeł z kluczem sieci) albo,
// rzadziej, po nim (węzeł bez klucza).
void feed(const Bytes& raw, const char* kind) {
    std::vector<uint8_t> v(raw.data(), raw.data() + raw.size());
    const bool m = mutatePercent && rnd() % 100 < mutatePercent;
    const bool afterIfac = m && rnd() % 7 == 0;
    if (m && !afterIfac) mutate(v, 0);
    std::vector<uint8_t> wire = v.size() > p1iface::HW_MTU ? oversize(v) : v.size() >= 2 ? ifacWrap(v) : v;
    if (afterIfac) mutate(wire, 1);
    if (m) ++mutated;
    ++fed;
    countGenerated(kind);
    if (dump) {
        fprintf(dump, "{\"kind\":\"%s\",\"mutated\":%s,\"raw\":\"%s\",\"wire\":\"%s\"}\n", kind, m ? "true" : "false",
                hex(v.data(), v.size()).c_str(), hex(wire.data(), wire.size()).c_str());
    }
    if (wire.empty()) return;
    if (recentWire.size() < 32) recentWire.push_back(wire);
    else recentWire[rnd() % recentWire.size()] = wire;
    toStation(wire.data(), wire.size());
}

void announceFromPeer() {
    const size_t i = rnd() % PEERS;
    const Bytes appData = randomBytes(rnd() % 40);
    Bytes raw = announce(peers[i], DEST_NAME.c_str(), appData, rnd() % 4 == 0);
    if (rnd() % 2) raw = headerTwo(raw, rnd() % 3 ? randomBytes(16) : stationTransport);
    feed(withHops(raw, randomHops()), "announce");
}

Bytes someDestination() {
    switch (rnd() % 4) {
        case 0: return randomBytes(16);
        case 1: return stationDest;
        default: return peerDest[rnd() % PEERS];
    }
}

void pathRequest() {
    Bytes data = someDestination();
    if (rnd() % 2) data << randomBytes(16);
    data << randomBytes(rnd() % 3 ? 16 : rnd() % 20);
    feed(withHops(pathRequestOf(data), randomHops()), "path-request");
}

void dataThroughStation() {
    const size_t i = rnd() % PEERS;
    const Bytes raw = headerTwo(dataTo(peers[i], peerDest[i], randomBytes(1 + rnd() % 300)), rnd() % 4 ? stationTransport : randomBytes(16));
    remember(recentHashes, packetHash(raw));
    feed(withHops(raw, randomHops()), "transit");
}

void dataToStation() {
    Bytes raw = dataTo(station, stationDest, randomBytes(1 + rnd() % 300));
    if (rnd() % 2) raw = headerTwo(raw, stationTransport);
    remember(recentHashes, packetHash(raw));
    feed(withHops(raw, randomHops()), "local");
}

void linkRequest() {
    const Identity ephemeral = newIdentity();
    Bytes data(ephemeral.pub, ephemeral.pub + rnscore::KEY_SIZE);
    if (rnd() % 2) data << randomBytes(3);
    const bool local = rnd() % 3 == 0;
    const Bytes& destination = local ? stationDest : peerDest[rnd() % PEERS];
    const Bytes lr = packet(rnscore::LINKREQUEST, rnscore::SINGLE, destination, data);
    const Bytes raw = local ? lr : headerTwo(lr, stationTransport);
    const Bytes id = linkIdOf(raw);
    if (!id.empty()) remember(linkIds, id);
    feed(withHops(raw, randomHops()), "link-request");
}

void proofOrLinkTraffic() {
    Bytes raw;
    const uint32_t r = rnd() % 3;
    if (r == 0 && !linkIds.empty()) {   // LRPROOF do łącza
        raw.push_back(0x0F);
        raw.push_back(randomHops());
        raw << linkIds[rnd() % linkIds.size()];
        raw.push_back(0xFF);
        raw << randomBytes(rnd() % 2 ? 99 : rnd() % 140);
    } else if (r == 1 && !linkIds.empty()) {   // dane albo dowód w łączu
        raw.push_back(static_cast<uint8_t>(0x0C | (rnd() % 2 ? 0x03 : 0x00)));
        raw.push_back(randomHops());
        raw << linkIds[rnd() % linkIds.size()];
        raw.push_back(static_cast<uint8_t>(rnd()));
        raw << randomBytes(rnd() % 200);
    } else {   // dowód pakietu (jawny albo skrócony) do niedawnego pakietu
        const Bytes h = recentHashes.empty() ? randomBytes(32) : recentHashes[rnd() % recentHashes.size()];
        if (h.size() < 16) return;
        raw.push_back(0x03);
        raw.push_back(randomHops());
        raw << left(h, 16);
        raw.push_back(0x00);
        if (rnd() % 2) raw << h;
        raw << randomBytes(64);
    }
    feed(raw, "proof");
}

// Ważny dowód od węzła dla pakietu, który wysłała stacja (potwierdzenie doręczenia).
void proofForStationPacket() {
    if (radio.recent.empty()) return;
    const Bytes raw = ifacUnwrap(radio.recent[rnd() % radio.recent.size()]);
    rnscore::Packet p;
    if (raw.empty() || !rnscore::unpack(raw.data(), raw.size(), p) || p.packetType != rnscore::DATA) return;
    for (size_t i = 0; i < PEERS; ++i) {
        if (memcmp(p.destinationHash, peerDest[i].data(), rnscore::TRUNCATED_HASH_SIZE) != 0) continue;
        feed(withHops(proofOf(raw, peers[i]), static_cast<uint8_t>(rnd() % 3)), "station-proof");
        return;
    }
}

void replay() {
    if (rnd() % 2 && !radio.recent.empty()) {   // datagram stacji wraca od innego przekaźnika
        const std::vector<uint8_t>& w = radio.recent[rnd() % radio.recent.size()];
        countGenerated("station-replay");
        toStation(w.data(), w.size());
    } else if (!recentWire.empty()) {
        const std::vector<uint8_t>& w = recentWire[rnd() % recentWire.size()];
        countGenerated("replay");
        toStation(w.data(), w.size());
    }
}

void stationActs() {
    switch (rnd() % 3) {
        case 0: rnsnode::announce(nullptr, 0); break;
        case 1: {   // w kopercie warstwy aplikacji (station.cpp), którą rdzeń tłumaczy na LXMF
            const Bytes& d = peerDest[rnd() % PEERS];
            const std::string head = "[\"WICI\",1,\"" + hex(rnsnode::address(), 16) + "\",\"" + hex(d.data(), 16) + "\",";
            Bytes data(head.begin(), head.end());
            data << randomBytes(1 + rnd() % 200);
            data.push_back(']');
            rnsnode::send(d.data(), data.data(), data.size(), rnsnode::RECEIPT_MIN_S);
            break;
        }
        default: rnsnode::requestPath(peerDest[rnd() % PEERS].data());
    }
}

bool longJumps = false;

void advanceClock() {
    const uint32_t r = rnd() % 1000;
    uint64_t ms;
    if (r < 900) ms = rnd() % 2000;
    else if (r < 990 || !longJumps) ms = static_cast<uint64_t>(rnd() % 600) * 1000;
    else ms = static_cast<uint64_t>(3600 + rnd32() % (8 * 86400)) * 1000;   // godzina do 8 dni
    simMs += ms;
}

void service() {
    radio.poll();
    rnsnode::loop(static_cast<uint32_t>(simMs));
}

// Port i microStore mają widzieć zegar symulowany; inaczej próby czasu niczego nie sprawdzają.
void checkClock() {
    if (const char* what = stackClockError(simMs)) fail(what);
}

// Zalew wrogimi datagramami (stacja na rdzeniu): bez flagi IFAC, z kodem IFAC spoza sieci, z ważnym
// IFAC ogłoszenia z błędnym podpisem (także z celem odbiorcy z karty), dowody do nieznanych pakietów,
// pakiety do stacji bez ważnego tokenu, powtórzone nagranie jednego poprawnego ogłoszenia (IFAC przechodzi
// bez klucza sieci) i ogłoszenia z celem odbiorcy i obcym kluczem (kolizja). Dwa datagramy na obieg
// loop(), czyli szybciej, niż stacja je przetwarza. W każdym obiegu najwyżej jedna operacja asymetryczna
// (audyt rdzenia, U2). W trakcie zalewu: ogłoszenia odbiorcy z karty, pakiet stacji do odbiorcy i jego
// dowód (wynik w polu "flood", także gdy ruch ginie w pełnej kolejce). Pakiet do stacji z dowodem
// kosztuje w jednym obiegu do trzech operacji (odszyfrowanie, podpis dowodu, IFAC dowodu), a wiadomość
// SA1 znanego nadawcy cztery (z weryfikacją podpisu LXMF; reticulum-core.md, tabela różnic).
std::string floodResult;

// Pakiet stacji (bez IFAC) typu DATA do celu destination.
bool stationDataTo(const Bytes& raw, const Bytes& destination) {
    rnscore::Packet p;
    return rnscore::unpack(raw.data(), raw.size(), p) && p.packetType == rnscore::DATA &&
           memcmp(p.destinationHash, destination.data(), rnscore::TRUNCATED_HASH_SIZE) == 0;
}

void receive(const Bytes& raw) {
    const std::vector<uint8_t> wire = ifacWrap(raw);
    if (!wire.empty()) toStation(wire.data(), wire.size());
}

Bytes announceOf(size_t peer) { return announce(peers[peer], DEST_NAME.c_str(), Bytes(), false); }

uint32_t interfaceCounter(const char* name) {
    char iface[rnsnode::INTERFACE_JSON_SIZE];
    rnsnode::interfaceJson(iface, sizeof(iface));
    const std::string key = std::string("\"") + name + "\":";
    const char* at = strstr(iface, key.c_str());
    return at ? static_cast<uint32_t>(strtoul(at + key.size(), nullptr, 10)) : 0;
}

// Jawny dowód odbiorcy dla ostatniego pakietu stacji do niego; pusty, gdy stacja go jeszcze nie nadała.
Bytes receiverProof() {
    for (auto w = radio.recent.rbegin(); w != radio.recent.rend(); ++w) {
        const Bytes raw = ifacUnwrap(*w);
        if (stationDataTo(raw, peerDest[0])) return proofOf(raw, peers[0]);
    }
    return Bytes();
}

#ifdef WICI_RNS_CORE
std::vector<uint8_t> replayWire;   // nagrane poprawne ogłoszenie węzła 1 z IFAC

// Operacje asymetryczne stacji w obiegach loop() (bez IFAC, który generator nakłada na datagramy kodem rdzenia).
uint32_t stationOperations = 0;

void serviceCounted(uint32_t limit = 1) {
    radio.poll();
    const uint32_t before = rnscore::asymmetricOperations();
    rnsnode::loop(static_cast<uint32_t>(simMs));
    const uint32_t ops = rnscore::asymmetricOperations() - before;
    if (ops > limit) fail("too many asymmetric operations in one loop pass");
    stationOperations += ops;
}

void hostileDatagram(bool replayOnly) {
    std::vector<uint8_t> v;
    switch (replayOnly ? 5 + rnd() % 2 : rnd() % 7) {
        case 0:   // bez flagi IFAC
            v = {static_cast<uint8_t>(rnd() & 0x7F), static_cast<uint8_t>(rnd())};
            for (uint32_t n = 18 + rnd() % 300; n; --n) v.push_back(static_cast<uint8_t>(rnd()));
            toStation(v.data(), v.size());
            return;
        case 1:   // flaga IFAC, kod spoza sieci
            v = {static_cast<uint8_t>(rnd() | 0x80), static_cast<uint8_t>(rnd())};
            for (uint32_t n = 40 + rnd() % 450; n; --n) v.push_back(static_cast<uint8_t>(rnd()));
            toStation(v.data(), v.size());
            return;
        case 2: {   // ogłoszenie z błędnym podpisem (bez danych aplikacji podpis to ostatnie 64 B)
            Bytes raw = announceOf(rnd() % 2 ? 0 : 1 + rnd() % (PEERS - 1));
            std::vector<uint8_t> a(raw.data(), raw.data() + raw.size());
            a[a.size() - 1 - rnd() % 64] ^= static_cast<uint8_t>(1u << (rnd() % 8));
            receive(a);
            return;
        }
        case 3: {   // dowód niejawny do nieznanego pakietu
            Bytes raw;
            raw.push_back(static_cast<uint8_t>(0x03));
            raw.push_back(static_cast<uint8_t>(0x00));
            raw << randomBytes(16);
            raw.push_back(static_cast<uint8_t>(0x00));
            raw << randomBytes(64);
            receive(raw);
            return;
        }
        case 4: {   // pakiet do stacji z przypadkowym tokenem (ECDH, potem zły HMAC)
            Bytes raw;
            raw.push_back(static_cast<uint8_t>(0x00));
            raw.push_back(static_cast<uint8_t>(0x00));
            raw << stationDest;
            raw.push_back(static_cast<uint8_t>(0x00));
            raw << randomBytes(32 + 16 + 32 + 16 * (1 + rnd() % 4));
            receive(raw);
            return;
        }
        case 5:   // to samo nagranie poprawnego ogłoszenia (bez klucza sieci: kod IFAC jest deterministyczny)
            toStation(replayWire.data(), replayWire.size());
            return;
        default: {   // cel odbiorcy z karty z kluczem innego węzła (kolizja z wpisem odbiorcy)
            Bytes raw = announceOf(1 + rnd() % (PEERS - 1));
            std::vector<uint8_t> a(raw.data(), raw.data() + raw.size());
            memcpy(a.data() + 2, peerDest[0].data(), 16);
            receive(a);
            return;
        }
    }
}

// Datagramy jednego obiegu: dwa wrogie i, gdy jest, jeden prawdziwy w przypadkowym miejscu między nimi.
void floodPass(bool replayOnly, const Bytes& genuine) {
    const uint32_t at = genuine.empty() ? 3 : rnd() % 3;
    for (uint32_t k = 0; k < 3; ++k) {
        if (k == at) receive(genuine);
        if (k < 2) hostileDatagram(replayOnly);
    }
    serviceCounted();
}

void flood() {
    replayWire = ifacWrap(announceOf(1));
    const uint32_t delivered0 = rnsnode::status().delivered;
    // Koperta warstwy aplikacji (station.cpp) z treścią SA1; rdzeń wysyła treść w LXMF.
    const std::string message = "[\"WICI\",1,\"" + hex(rnsnode::address(), 16) + "\",\"" + hex(peerDest[0].data(), 16) +
                                "\",[1,\"report during the flood\"]]";
    uint32_t handle = 0, announceTries = 0, proofTries = 0;
    int pathRound = -1, deliveredRound = -1;
    for (int round = 0; round < 1200; ++round) {
        Bytes genuine;
        if (round == 100) handle = rnsnode::send(peerDest[0].data(), reinterpret_cast<const uint8_t*>(message.data()), message.size(),
                                                 rnsnode::RECEIPT_MIN_S);
        if (round >= 100 && pathRound < 0 && round % 100 == 0) {   // odbiorca ogłasza się co sekundę
            genuine = withHops(announceOf(0), 1);
            ++announceTries;
        } else if (handle && deliveredRound < 0 && round % 50 == 25) {   // dowód odbiorcy co pół sekundy
            genuine = receiverProof();
            if (!genuine.empty()) ++proofTries;
        }
        floodPass(false, genuine);
        if (round % 10 == 0) simMs += 100;
        const bool path = rnsnode::hasPath(peerDest[0].data());
        if (path && round < 100) fail("receiver path from a forged announce");
        if (path && pathRound < 0) pathRound = round;
        if (deliveredRound < 0 && rnsnode::status().delivered > delivered0) deliveredRound = round;
    }
    if (!handle) fail("station could not send during the flood");

    // Same powtórki poprawnego ogłoszenia i kolizje: odpadają przed weryfikacją, więc nie zabierają
    // żetonów; ogłoszenia odbiorcy z nowym skrótem losowym przechodzą weryfikację.
    for (int i = 0; i < 5; ++i) { simMs += 1000; serviceCounted(); }
    const uint32_t limited0 = interfaceCounter("ann_limited"), accepted0 = rnsnode::status().announcesSeen;
    uint32_t replayAnnounces = 0;
    for (int round = 0; round < 400; ++round) {
        Bytes genuine;
        if (round % 100 == 0) { genuine = withHops(announceOf(0), 1); ++replayAnnounces; }
        floodPass(true, genuine);
        simMs += 10;
    }
    for (int i = 0; i < 8; ++i) serviceCounted();
    const uint32_t replayLimited = interfaceCounter("ann_limited") - limited0;
    const uint32_t replayAccepted = rnsnode::status().announcesSeen - accepted0;
    if (replayLimited) fail("replayed announces took verification tokens");

    // Po zalewie: ogłoszenie odbiorcy i pakiet do stacji przechodzą.
    for (int i = 0; i < 20; ++i) { simMs += 1000; serviceCounted(); }
    receive(withHops(announceOf(0), 1));
    for (int i = 0; i < 4; ++i) serviceCounted();
    if (!rnsnode::hasPath(peerDest[0].data())) fail("receiver announce lost after the flood");
    const uint32_t before = rnsnode::status().packetsReceived;
    const std::string report = "report after the flood";
    receive(dataTo(station, stationDest, Bytes(report.begin(), report.end())));
    for (int i = 0; i < 4; ++i) serviceCounted(3);
    if (rnsnode::status().packetsReceived != before + 1) fail("packet to the station lost after the flood");
    // Wiadomość SA1 odbiorcy z karty: w jednym obiegu ECDH, weryfikacja podpisu LXMF, podpis dowodu i IFAC dowodu.
    const char sa1[] = "[1,\"after the flood\"]";
    uint8_t lxmf[400], messageHash[32];
    const size_t n = rnscore::lxmfPackSa1(peers[0].prv, peers[0].pub, stationDest.data(), peerDest[0].data(), 0,
                                          reinterpret_cast<const uint8_t*>(sa1), sizeof(sa1) - 1, lxmf, sizeof(lxmf), messageHash);
    const uint32_t rejected = interfaceCounter("lxmf_rejected");
    receive(dataTo(station, stationDest, Bytes(lxmf, lxmf + n)));
    for (int i = 0; i < 4; ++i) serviceCounted(4);
    if (rnsnode::status().packetsReceived != before + 2) fail("SA1 message from the receiver lost after the flood");
    if (interfaceCounter("lxmf_rejected") != rejected) fail("SA1 message from the receiver rejected");
    // Ten sam kształt od odbiorcy ze złym podpisem: też najwyżej cztery operacje, odrzucenie z powodem.
    lxmf[16] ^= 0x01;
    const uint32_t badSignature = interfaceCounter("lxmf_rej_signature");
    receive(dataTo(station, stationDest, Bytes(lxmf, lxmf + n)));
    for (int i = 0; i < 4; ++i) serviceCounted(4);
    if (interfaceCounter("lxmf_rej_signature") != badSignature + 1) fail("forged SA1 message from the receiver not rejected");

    char text[256];
    snprintf(text, sizeof(text),
             "\"path_round\":%d,\"announce_tries\":%u,\"delivered_round\":%d,\"proof_tries\":%u,"
             "\"replay_announces\":%u,\"replay_accepted\":%u,\"replay_limited\":%u",
             pathRound, announceTries, deliveredRound, proofTries, replayAnnounces, replayAccepted, replayLimited);
    floodResult = text;
}

// Pakiet z wiadomością SA1 (treść sa1) w LXMF od odbiorcy z karty do celu stacji.
Bytes receiverMessage(const char* sa1) {
    uint8_t lxmf[400], messageHash[32];
    const size_t n = rnscore::lxmfPackSa1(peers[0].prv, peers[0].pub, stationDest.data(), peerDest[0].data(), 0,
                                          reinterpret_cast<const uint8_t*>(sa1), strlen(sa1), lxmf, sizeof(lxmf), messageHash);
    return dataTo(station, stationDest, Bytes(lxmf, lxmf + n));
}

// Zalew pakietami do celu stacji (stacja na rdzeniu): przez 60 s dwa datagramy na obieg loop() z poprawnie
// zaszyfrowanymi pakietami do stacji o przypadkowej treści. Każdy przetworzony kosztuje trzy operacje
// (odszyfrowanie, podpis dowodu trwałego odrzucenia, IFAC dowodu), więc limit pracy (wiadro w
// rns_node_core.cpp, żeton co sekundę, 4 naraz) ogranicza je do około jednego na sekundę; reszta odpada
// przed odszyfrowaniem ("rx_limited"). Po zalewie wiadomość SA1 odbiorcy z karty: kopia przy pustym wiadrze
// odpada, ta sama kopia po uzupełnieniu przechodzi z dowodem.
// Wynik w polu "flood": datagramy, przetworzone, odrzucone limitem, operacje asymetryczne.
void stationFlood() {
    receive(withHops(announceOf(0), 1));
    for (int k = 0; k < 110; ++k) { simMs += 10; serviceCounted(); }
    if (!rnsnode::hasPath(peerDest[0].data())) fail("station-flood: receiver announce not accepted");
    const uint32_t received0 = rnsnode::status().packetsReceived, limited0 = interfaceCounter("rx_limited");
    const uint32_t ops0 = stationOperations;
    uint32_t datagrams = 0;
    for (int pass = 0; pass < 3000; ++pass) {   // 60 s po 20 ms
        for (int k = 0; k < 2; ++k) {
            receive(dataTo(station, stationDest, randomBytes(1 + rnd() % 300)));
            ++datagrams;
        }
        simMs += 20;
        serviceCounted(3);
    }
    for (int k = 0; k < 8; ++k) { simMs += 20; serviceCounted(3); }
    const uint32_t processed = rnsnode::status().packetsReceived - received0;
    const uint32_t limited = interfaceCounter("rx_limited") - limited0;
    const uint32_t ops = stationOperations - ops0;   // każdy datagram: IFAC; przetworzony pakiet: jeszcze trzy

    // Wiadomość SA1 odbiorcy z karty tuż po zalewie (wiadro puste): odpada bez zapisu skrótu, więc ta sama
    // kopia po uzupełnieniu wiadra (inną drogą, od przekaźnika) przechodzi z dowodem.
    const Bytes m = receiverMessage("[1,\"after the station flood\"]");
    const uint32_t before = rnsnode::status().packetsReceived, rejected = interfaceCounter("lxmf_rejected");
    const uint32_t limitedBefore = interfaceCounter("rx_limited");
    receive(m);
    for (int k = 0; k < 4; ++k) { simMs += 20; serviceCounted(4); }
    if (interfaceCounter("rx_limited") != limitedBefore + 1) fail("station-flood: SA1 copy with an empty bucket not limited");
    for (int k = 0; k < 5; ++k) { simMs += 1000; serviceCounted(); }
    const uint32_t sent = radio.sent;
    settleAll = true;
    receive(m);
    for (int k = 0; k < 4; ++k) { simMs += 20; serviceCounted(4); }
    settleAll = false;
    if (rnsnode::status().packetsReceived != before + 1) fail("station-flood: SA1 message from the receiver lost");
    if (interfaceCounter("lxmf_rejected") != rejected) fail("station-flood: SA1 message from the receiver rejected");
    if (radio.sent == sent) fail("station-flood: no proof for the SA1 message");

    char text[192];
    snprintf(text, sizeof(text), "\"datagrams\":%u,\"processed\":%u,\"limited\":%u,\"operations\":%u", datagrams, processed,
             limited, ops);
    floodResult = text;
}

// Ruch tranzytowy szybszy niż przetwarzanie (stacja na rdzeniu): najpierw trasy o skok dalej do węzłów
// generatora, potem dwa datagramy na obieg loop(): pakiety ze stacją jako następnym skokiem (forward,
// każde przekazanie to podpis IFAC) albo (load) nowe ogłoszenia węzłów (każde przyjęte planuje dwie
// retransmisje) i zapytania o znane cele (odpowiedzi z pamięci podręcznej). W każdym obiegu najwyżej
// jedna operacja asymetryczna; wynik w polu "flood": liczba obiegów i czas.
void transitLoad(bool announces) {
    for (size_t i = 1; i < PEERS; ++i) {   // trasy: weryfikacja ogłoszeń najwyżej raz na sekundę
        receive(withHops(announceOf(i), 1));
        for (int k = 0; k < 110; ++k) { simMs += 10; serviceCounted(); }
    }
    const uint32_t routes = static_cast<uint32_t>(rnsnode::status().paths);
    for (int round = 0; round < 1500; ++round) {
        for (int k = 0; k < 2; ++k) {
            const size_t i = 1 + rnd() % (PEERS - 1);
            if (!announces) {
                receive(withHops(headerTwo(dataTo(peers[i], peerDest[i], randomBytes(1 + rnd() % 200)), stationTransport), 0));
            } else if (rnd() % 2) {
                receive(withHops(announceOf(i), 1 + rnd() % 3));
            } else {
                Bytes data = peerDest[i];
                data << randomBytes(16);
                receive(pathRequestOf(data));
            }
        }
        simMs += 10;
        serviceCounted();
    }
    for (int i = 0; i < 2000; ++i) { simMs += 10; serviceCounted(); }   // zaległe retransmisje po jednej
    char out[96];
    snprintf(out, sizeof(out), "\"routes\":%u,\"rounds\":1500", routes);
    floodResult = out;
}

// Zapytania o trasę do celu stacji z nowymi znacznikami, dwa datagramy na obieg loop() przez 70 s.
// Odpowiedź z nowym podpisem ogłoszenia (podpis i IFAC: dwie operacje asymetryczne w jednym obiegu,
// wyjątek z tabeli różnic) najwyżej raz na 30 s, w pozostałych obiegach najwyżej jedna operacja; wynik
// w polu "flood": obiegi z dwiema operacjami.
void ownPathRequests() {
    uint32_t doubles = 0;
    for (int round = 0; round < 7000; ++round) {
        for (int k = 0; k < 2; ++k) {
            Bytes data = stationDest;
            data << randomBytes(16);
            receive(pathRequestOf(data));
        }
        simMs += 10;
        radio.poll();
        const uint32_t before = rnscore::asymmetricOperations();
        rnsnode::loop(static_cast<uint32_t>(simMs));
        const uint32_t ops = rnscore::asymmetricOperations() - before;
        if (ops > 2) fail("own path requests: more than two asymmetric operations in one loop pass");
        doubles += ops == 2;
    }
    if (doubles > 3) fail("own path requests: new announce signature more often than once per 30 s");
    char out[96];
    snprintf(out, sizeof(out), "\"double_passes\":%u,\"rounds\":7000", doubles);
    floodResult = out;
}


// Praca przez dni z wrogim ruchem (reticulum-core.md, kryterium odbioru 5; odbior.md, wiersz „Wrogi węzeł”,
// przebieg 2): każdego dnia okno windowS sekund, w każdej sekundzie ogłoszenie nowego celu, zapytanie
// o trasę do przypadkowego celu, pakiet przez stację do przypadkowego celu i pakiet przez stację do
// jednego celu (ogłaszającego się na początku okna); potem skok zegara do następnego dnia. Na początku
// okna odbiorca z karty ogłasza się, a stacja wysyła mu zgłoszenie, które musi zostać potwierdzone
// w tym samym oknie. Wpis odbiorcy sprawdzany co dzień. Po starcie stacja nie przydziela pamięci: przydziały sterty w wywołaniach
// rnsnode liczy hak sanitizera (generator ruchu korzysta ze sterty przez std::vector, więc liczony jest tylko stos
// stacji). stopAfterS: koniec procesu w ostatnim dniu po tylu sekundach okna (restart w trakcie ruchu).
uint32_t stationAllocations = 0;
#ifdef WICI_ALLOCATION_HOOK
void onMalloc(const volatile void*, size_t) { stationAllocations += inStation; }
void onFree(const volatile void*) {}
#endif

template <typename F>
void inStationCall(F f) {
    inStation = true;
    f();
    inStation = false;
}

// Datagram i obiegi pętli przez 200 ms (kolejka odbioru ma 4 miejsca: ruch z jednej sekundy nie trafia
// do niej naraz).
void hostileReceive(const Bytes& raw) {
    const std::vector<uint8_t> wire = ifacWrap(raw);
    if (!wire.empty()) inStationCall([&] { toStation(wire.data(), wire.size()); });
    for (int k = 0; k < 10; ++k) {
        simMs += 20;
        radio.poll();
        inStationCall([] { rnsnode::loop(static_cast<uint32_t>(simMs)); });
    }
}

Bytes dataVia(const Bytes& destination) {
    Bytes raw;
    raw.push_back(static_cast<uint8_t>(0x00));
    raw.push_back(static_cast<uint8_t>(0x00));
    raw << destination;
    raw.push_back(static_cast<uint8_t>(0x00));
    raw << randomBytes(16 + rnd() % 160);
    return headerTwo(raw, stationTransport);
}

void hostileDays(long days, long windowS, long stopAfterS) {
#ifdef WICI_ALLOCATION_HOOK
    __sanitizer_install_malloc_and_free_hooks(onMalloc, onFree);
#endif
    uint32_t datagrams = 0, reports = 0, daysDone = 0;
    const auto passes = [](int n) {
        for (int k = 0; k < n; ++k) {
            simMs += 20;
            radio.poll();
            inStationCall([] { rnsnode::loop(static_cast<uint32_t>(simMs)); });
        }
    };
    for (long day = 0; day < days; ++day) {
        const bool last = day == days - 1;
        hostileReceive(withHops(announceOf(0), 1));
        hostileReceive(withHops(announceOf(2), 2));   // cel ruchu przez stację „do jednego celu”
        passes(100);
        if (!rnsnode::hasPath(peerDest[0].data())) fail("hostile days: receiver announce not accepted");
        const uint32_t delivered0 = rnsnode::status().delivered;
        // Koperta warstwy aplikacji (station.cpp) z treścią SA1; rdzeń wysyła treść w LXMF.
        const std::string report = "[\"WICI\",1,\"" + hex(rnsnode::address(), 16) + "\",\"" + hex(peerDest[0].data(), 16) +
                                   "\",[1,\"daily report under hostile traffic\"]]";
        uint32_t handle = 0;
        inStationCall([&] {
            handle = rnsnode::send(peerDest[0].data(), reinterpret_cast<const uint8_t*>(report.data()), report.size(),
                                   rnsnode::RECEIPT_MIN_S);
        });
        if (!handle) fail("hostile days: report not accepted");
        bool stopped = false;
        for (long second = 0; second < windowS; ++second) {
            if (last && stopAfterS >= 0 && second == stopAfterS) { stopped = true; break; }
            const Identity& node = peers[1 + rnd() % (PEERS - 1)];
            const std::string name = std::string(DEST_APP) + "." + hex(randomBytes(4).data(), 4);
            hostileReceive(withHops(announce(node, name.c_str(), Bytes(), false), 1 + rnd() % 4));
            Bytes query = rnd() % 2 ? randomBytes(16) : peerDest[rnd() % PEERS];
            query << randomBytes(16);
            hostileReceive(pathRequestOf(query));
            hostileReceive(dataVia(randomBytes(16)));
            hostileReceive(dataVia(peerDest[2]));
            datagrams += 4;
            if (rnsnode::status().delivered == delivered0 && second % 2 == 1) {
                const Bytes proof = receiverProof();
                if (!proof.empty()) hostileReceive(proof);
            }
        }
        if (!rnsnode::knows(peerDest[0].data())) fail("hostile days: receiver identity lost");
        if (stopped) break;
        if (rnsnode::status().delivered == delivered0) fail("hostile days: daily report not delivered");
        ++reports;
        ++daysDone;
        simMs += static_cast<uint64_t>(86400 - windowS) * 1000;
        passes(10);
    }
    if (stationAllocations) fail("hostile days: station allocated memory after start");
    char allocations[16] = "null";
#ifdef WICI_ALLOCATION_HOOK
    snprintf(allocations, sizeof(allocations), "%u", stationAllocations);
#endif
    char out[192];
    snprintf(out, sizeof(out), "\"days\":%u,\"window_s\":%ld,\"datagrams\":%u,\"reports\":%u,\"allocations\":%s",
             daysDone, windowS, datagrams, reports, allocations);
    floodResult = out;
}

// Uszkodzone gniazdo odbiorcy z karty w tablicy znanych celów rdzenia (FRAM od framfs::FS_BASE, gniazda
// 568 B, cel od bajtu 16; lib/reticulum_core/src/table.h): wiadomość SA1 odbiorcy do stacji przechodzi do
// warstwy aplikacji (podpis sprawdzany kluczem z karty, nie z tablicy), pakiet stacji do odbiorcy wychodzi
// mimo to (wpis z kluczy karty od nowa), a gniazdo liczy "table_corrupt".
void damagedReceiver() {
    constexpr size_t SLOT = 568, SLOTS = 257;
    bool damaged = false;
    for (size_t slot = 0; slot < SLOTS; ++slot) {
        uint8_t* b = fram.bytes + framfs::FS_BASE + slot * SLOT;
        if (b[0] != 0xA5 || memcmp(b + 16, peerDest[0].data(), 16) != 0) continue;
        b[300] ^= 0xFF;   // poza nagłówkiem: indeks bez zmian, błędne CRC przy odczycie
        damaged = true;
    }
    if (!damaged) fail("damaged-receiver: no receiver slot");
    const uint32_t before = appPackets, rejected = interfaceCounter("lxmf_rejected");
    settleAll = true;
    receive(receiverMessage("[1,\"reply after a damaged slot\"]"));
    for (int k = 0; k < 4; ++k) { simMs += 20; service(); }
    settleAll = false;
    if (interfaceCounter("lxmf_rejected") != rejected) fail("damaged-receiver: SA1 message from the receiver rejected");
    if (appPackets != before + 1) fail("damaged-receiver: SA1 message from the receiver lost");
    // Koperta warstwy aplikacji (station.cpp) z treścią SA1; rdzeń wysyła treść w LXMF.
    const std::string message = "[\"WICI\",1,\"" + hex(rnsnode::address(), 16) + "\",\"" + hex(peerDest[0].data(), 16) +
                                "\",[1,\"report after a damaged slot\"]]";
    if (!rnsnode::send(peerDest[0].data(), reinterpret_cast<const uint8_t*>(message.data()), message.size(),
                       rnsnode::RECEIPT_MIN_S)) {
        fail("damaged-receiver: report not sent");
    }
}
// Gniazdo odbiorcy z karty z kluczem innego węzła i poprawnym CRC (celowe uszkodzenie FRAM przed startem;
// tablica sprawdza CRC, a nie zgodność klucza z celem): przy starcie klucz z karty zastępuje wpis
// (rnsnode rememberReceivers), więc zgłoszenie do odbiorcy odszyfruje odbiorca, nie obcy węzeł.
uint32_t slotCrc(const uint8_t* b, size_t n) {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < n; ++i) {
        crc ^= b[i];
        for (int k = 0; k < 8; ++k) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

void receiverForeignKey() {
    constexpr size_t SLOT = 568, SLOTS = 257, AT_KEY = 96, AT_CRC = 561;
    bool damaged = false;
    for (size_t slot = 0; slot < SLOTS; ++slot) {
        uint8_t* b = fram.bytes + framfs::FS_BASE + slot * SLOT;
        if (b[0] != 0xA5 || memcmp(b + 16, peerDest[0].data(), 16) != 0) continue;
        memcpy(b + AT_KEY, peers[1].pub, 64);
        const uint32_t crc = slotCrc(b + 1, AT_CRC - 1);
        for (int k = 0; k < 4; ++k) b[AT_CRC + k] = static_cast<uint8_t>(crc >> (8 * k));
        damaged = true;
    }
    if (!damaged) fail("receiver-foreign-key: no receiver slot");
}

void receiverReadsReport() {
    receive(withHops(announceOf(0), 1));
    for (int i = 0; i < 100; ++i) { simMs += 20; service(); }
    // Koperta warstwy aplikacji (station.cpp); na antenie wiadomość LXMF z tą treścią SA1.
    const std::string text = "report after a foreign key in FRAM";
    const std::string message = "[\"WICI\",1,\"" + hex(rnsnode::address(), 16) + "\",\"" + hex(peerDest[0].data(), 16) +
                                "\",[1,\"" + text + "\"]]";
    if (!rnsnode::send(peerDest[0].data(), reinterpret_cast<const uint8_t*>(message.data()), message.size(), rnsnode::RECEIPT_MIN_S)) {
        fail("receiver-foreign-key: not sent");
    }
    for (int i = 0; i < 100; ++i) { simMs += 20; service(); }
    for (auto w = radio.recent.rbegin(); w != radio.recent.rend(); ++w) {
        const Bytes raw = ifacUnwrap(*w);
        if (!stationDataTo(raw, peerDest[0])) continue;
        rnscore::Packet p;
        rnscore::unpack(raw.data(), raw.size(), p);
        uint8_t plain[rnscore::MTU];
        size_t length = 0;
        if (!rnscore::decrypt(peers[0].prv, peers[0].pub, p.data, p.dataLength, plain, sizeof(plain), &length)) length = 0;
        const std::string body(reinterpret_cast<const char*>(plain), length);
        if (body.find(text) == std::string::npos) {
            fail("receiver-foreign-key: receiver cannot read the report");
        }
        floodResult = "\"receiver_reads\":true";
        return;
    }
    fail("receiver-foreign-key: no report on air");
}
#else
void flood() { fail("flood: station core only"); }
void stationFlood() { fail("station-flood: station core only"); }
void damagedReceiver() { fail("damaged-receiver: station core only"); }
void transitLoad(bool) { fail("transit load: station core only"); }
void ownPathRequests() { fail("own path requests: station core only"); }
void hostileDays(long, long, long) { fail("hostile days: station core only"); }
void receiverForeignKey() { fail("receiver-foreign-key: station core only"); }
void receiverReadsReport() {}
#endif

// Zalew zapytaniami o trasę (port i rdzeń, R5-4b): węzeł z kluczem sieci przez godzinę co 100 ms pyta
// z nowym znacznikiem o kolejny znany cel, co czwarte zapytanie o cel stacji. Odpowiedzi (ogłoszenia
// z kontekstem PATH_RESPONSE, klasa K0) mają w kolejce P1 własny budżet czasu kanału (5%, p1iface.h), więc
// zalew nie zajmie kanału przed K1. W połowie zalewu stacja wysyła zgłoszenie do odbiorcy z karty, które
// musi wyjść i zostać potwierdzone. Na rdzeniu w każdym obiegu najwyżej jedna operacja asymetryczna, poza
// nowym podpisem odpowiedzi o cel stacji (podpis i IFAC, najwyżej raz na 30 s; tabela różnic), a podpisów
// IFAC stacji (operacje poza sprawdzeniem IFAC odbioru, górne oszacowanie) jest najwyżej tyle, ile nadań,
// miejsc na liście oczekujących i przyjętych zapytań. Wynik w polu "flood": zapytania, odpowiedzi na łączu,
// ich czas kanału w pierwszych 59 min (okno budżetu przesuwa się co minutę, więc odpowiedzi z pierwszej
// minuty wypadają z niego przed upływem godziny) i ten budżet.
void pathFlood() {
    for (size_t i = 0; i < PEERS; ++i) {   // trasy: na rdzeniu weryfikacja ogłoszeń najwyżej raz na sekundę
        receive(withHops(announceOf(i), 1));
        for (int k = 0; k < 110; ++k) { simMs += 10; service(); }
    }
    if (!rnsnode::hasPath(peerDest[0].data())) fail("path-flood: receiver announce not accepted");
    const std::string report = "[\"WICI\",1,\"" + hex(rnsnode::address(), 16) + "\",\"" + hex(peerDest[0].data(), 16) +
                               "\",[1,\"report during the path flood\"]]";
    const uint32_t sent0 = interfaceCounter("tx_sent"), limited0 = interfaceCounter("pr_resp_limited");
    const uint32_t delivered0 = rnsnode::status().delivered;
#ifdef WICI_RNS_CORE
    const uint32_t ops0 = stationOperations, requests0 = interfaceCounter("pr_in");
    const uint32_t checked0 = interfaceCounter("rx_ok") + interfaceCounter("ifac_invalid");
    uint32_t doubles = 0;
#endif
    constexpr int TICKS = 36000, BUDGET_TICKS = 35400;   // 3600 s i 59 min po 100 ms
    uint32_t requests = 0, responses = 0, responseMs = 0, handle = 0, seen = radio.sent;
    int reportAt = -1, deliveredAt = -1;
    for (int tick = 0; tick < TICKS; ++tick) {
        Bytes data = tick % 4 == 0 ? stationDest : peerDest[1 + (tick / 4) % (PEERS - 1)];
        data << randomBytes(16);
        receive(pathRequestOf(data));
        ++requests;
        if (tick == TICKS / 2) handle = rnsnode::send(peerDest[0].data(), reinterpret_cast<const uint8_t*>(report.data()),
                                                      report.size(), rnsnode::RECEIPT_MIN_S);
        for (int k = 0; k < 2; ++k) {
            simMs += 50;
#ifdef WICI_RNS_CORE
            const uint32_t before = stationOperations;
            serviceCounted(2);
            doubles += stationOperations - before == 2;
#else
            service();
#endif
        }
        // Nowe datagramy stacji (najnowsze na końcu radio.recent); nagłówek na łączu jest zamaskowany kodem IFAC.
        const uint32_t fresh = radio.sent - seen;
        seen = radio.sent;
        const size_t from = radio.recent.size() - (fresh < radio.recent.size() ? fresh : radio.recent.size());
        for (size_t j = from; j < radio.recent.size(); ++j) {
            const Bytes raw = ifacUnwrap(radio.recent[j]);
            if (raw.empty() || !p1iface::pathResponse(raw.data(), raw.size())) continue;
            ++responses;
            if (tick < BUDGET_TICKS) responseMs += p1iface::channelMs(radio.recent[j].size());
        }
        if (handle && reportAt < 0) {
            const Bytes proof = receiverProof();
            if (!proof.empty()) {
                reportAt = tick;
                receive(proof);
            }
        }
        if (reportAt >= 0 && deliveredAt < 0 && rnsnode::status().delivered > delivered0) deliveredAt = tick;
    }
    if (!handle) fail("path-flood: station could not send the report");
    if (reportAt < 0) fail("path-flood: report not sent during the flood");
    if (deliveredAt < 0) fail("path-flood: report not delivered during the flood");
    const uint32_t budget = p1iface::WINDOW_MS / 100 * p1iface::PATH_RESPONSE_PERCENT;
    if (responseMs > budget) fail("path-flood: path responses above their channel budget");
    const uint32_t sent = interfaceCounter("tx_sent") - sent0;
    char text[320];
    int n = snprintf(text, sizeof(text),
                     "\"requests\":%u,\"responses\":%u,\"response_ms\":%u,\"budget_ms\":%u,\"limited\":%u,\"sent\":%u,"
                     "\"report_s\":%d,\"delivered_s\":%d",
                     requests, responses, responseMs, budget, interfaceCounter("pr_resp_limited") - limited0, sent,
                     (reportAt - TICKS / 2) / 10, (deliveredAt - TICKS / 2) / 10);
#ifdef WICI_RNS_CORE
    const uint32_t accepted = interfaceCounter("pr_in") - requests0;
    const uint32_t checked = interfaceCounter("rx_ok") + interfaceCounter("ifac_invalid") - checked0;
    const uint32_t signatures = stationOperations - ops0 - checked;
    if (signatures > sent + p1iface::HELD_ANNOUNCES + accepted) fail("path-flood: more IFAC signatures than sends, held and requests");
    if (doubles > TICKS / 300 + 1) fail("path-flood: new announce signature more often than once per 30 s");
    if (n > 0 && static_cast<size_t>(n) < sizeof(text)) {
        snprintf(text + n, sizeof(text) - n, ",\"accepted\":%u,\"signatures\":%u,\"double_passes\":%u", accepted, signatures,
                 doubles);
    }
#endif
    (void)n;
    floodResult = text;
}

const char* floodJson() { return floodResult.c_str(); }

// Awarie portu z przeglądu 2026-10-21 (poprawione łatami 0005-0007) jako próby regresji.
void defect(const std::string& name) {
    if (name == "token48") {
        // Token z poprawnym HMAC (klucz z ECDH z kluczem publicznym stacji), ale bez szyfrogramu.
        // Klucz HMAC to pierwsze 32 B z HKDF (Token.py); HMAC obejmuje IV i pusty szyfrogram.
        uint8_t ephemeral[rnscore::KEY_SIZE / 2], ephemeralPublic[rnscore::KEY_SIZE / 2], shared[rnscore::KEY_SIZE / 2];
        uint8_t derived[rnscore::DERIVED_KEY_SIZE], mac[rnscore::HASH_SIZE];
        for (uint8_t& b : ephemeral) b = static_cast<uint8_t>(rnd());
        rnscore::exchange(ephemeral, nullptr, ephemeralPublic);
        rnscore::exchange(ephemeral, station.pub, shared);
        rnscore::hkdf(shared, sizeof(shared), station.hash, sizeof(station.hash), derived, sizeof(derived));
        const Bytes iv = randomBytes(rnscore::TOKEN_IV_SIZE);
        SHA256 sha;
        sha.resetHMAC(derived, 32);
        sha.update(iv.data(), iv.size());
        sha.finalizeHMAC(derived, 32, mac, sizeof(mac));
        Bytes raw{0x00, 0x00};   // HEADER_1, SINGLE, DATA
        raw << stationDest;
        raw.push_back(0x00);
        raw.insert(raw.end(), ephemeralPublic, ephemeralPublic + sizeof(ephemeralPublic));
        raw << iv;
        raw.insert(raw.end(), mac, mac + sizeof(mac));
        feed(raw, "defect");
    } else if (name == "short-announce") {
        Bytes raw;
        raw.push_back(static_cast<uint8_t>(0x01));   // HEADER_1, SINGLE, ANNOUNCE
        raw.push_back(static_cast<uint8_t>(0x00));
        raw << randomBytes(16);
        raw.push_back(static_cast<uint8_t>(0x00));
        raw << randomBytes(40);                   // urwane w kluczu Ed25519: odczyt poza buforem
        feed(raw, "defect");
    } else if (name == "held-announce") {
        // Ogłoszenie sąsiada i zaraz zapytanie o trasę do tego celu: odpowiedź odkłada ogłoszenie do
        // _held_announces, a Transport::jobs wstawia je z powrotem do _announce_table w pętli po niej.
        for (int round = 0; round < 8; ++round) {
            const size_t i = 1 + rnd() % (PEERS - 1);
            const Bytes appData = randomBytes(8);
            feed(withHops(announce(peers[i], DEST_NAME.c_str(), appData, false), 1), "announce");
            Bytes data = peerDest[i];
            data << randomBytes(16) << randomBytes(16);
            feed(withHops(pathRequestOf(data), 0), "path-request");
            for (int k = 0; k < 30; ++k) { simMs += 1000; service(); }
        }
    } else if (name == "link-mtu") {
        // Żądania łącza do stacji z sygnalizacją MTU tak małego, że MDU łącza wyszłoby <= 0 (dawniej
        // konwersja ujemnej wartości na uint16_t w Link::update_mdu; wykryte ziarnem 2027 po cięciu
        // zasilania), oraz graniczne: 83 B ostatnie bez MDU, 84 B pierwsze z MDU > 0. Tryb łącza 1.
        for (const uint32_t mtu : {1u, 64u, 67u, 68u, 83u, 84u}) {
            const Identity ephemeral = newIdentity();
            Bytes data(ephemeral.pub, ephemeral.pub + rnscore::KEY_SIZE);
            data.push_back(static_cast<uint8_t>((1u << 5) | ((mtu >> 16) & 0x1F)));
            data.push_back(static_cast<uint8_t>(mtu >> 8));
            data.push_back(static_cast<uint8_t>(mtu));
            feed(withHops(packet(rnscore::LINKREQUEST, rnscore::SINGLE, stationDest, data), 0), "link-request");
            for (int k = 0; k < 10; ++k) { simMs += 100; service(); }
        }
    } else if (name == "station-flood") {
        stationFlood();
    } else if (name == "flood") {
        flood();
    } else if (name == "forward-flood" || name == "rebroadcast-load") {
        transitLoad(name == "rebroadcast-load");
    } else if (name == "own-path-requests") {
        ownPathRequests();
    } else if (name == "path-flood") {
        pathFlood();
    } else if (name == "damaged-receiver") {
        damagedReceiver();
    } else {
        fail("unknown defect");
    }
}

std::string readFile(const std::string& path) {
    std::string s;
    if (FILE* f = fopen(path.c_str(), "r")) {
        char b[256];
        while (fgets(b, sizeof(b), f)) s += b;
        fclose(f);
    }
    while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
    return s;
}

void writeFile(const std::string& path, const std::string& text) {
    if (FILE* f = fopen(path.c_str(), "w")) {
        fprintf(f, "%s\n", text.c_str());
        fclose(f);
    }
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) { fprintf(stderr, "usage: rns_stress <fram> [options]\n"); return 2; }
    const std::string framPath = argv[1];
    long events = 2000;
    uint64_t startS = 1767225600;   // 2026-01-01
    uint64_t gapS = 0, setClockS = 0;
    std::string defectName;
    long hostileDayCount = 0, windowS = 120, stopAfterS = -1;
    bool foreignKey = false;
    std::string dumpPath;
    rngState = 1;
    for (int i = 2; i < argc; ++i) {
        const std::string a = argv[i];
        const char* v = i + 1 < argc ? argv[i + 1] : "0";
        if (a == "--seed") { rngState = static_cast<uint32_t>(strtoul(v, nullptr, 10)); ++i; }
        else if (a == "--events") { events = atol(v); ++i; }
        else if (a == "--mutate") { mutatePercent = static_cast<uint32_t>(atoi(v)); ++i; }
        else if (a == "--start") { startS = strtoull(v, nullptr, 10); ++i; }
        else if (a == "--gap") { gapS = strtoull(v, nullptr, 10); ++i; }
        else if (a == "--set-clock") { setClockS = strtoull(v, nullptr, 10); ++i; }   // zegar cofnięty albo przestawiony
        else if (a == "--cut-after-writes") { fram.cutAfter = atol(v); ++i; }
        else if (a == "--long-jumps") longJumps = true;
        else if (a == "--defect") { defectName = v; ++i; }
        else if (a == "--hostile-days") { hostileDayCount = atol(v); ++i; }
        else if (a == "--window-s") { windowS = atol(v); ++i; }
        else if (a == "--stop-after-s") { stopAfterS = atol(v); ++i; }
        else if (a == "--receiver-foreign-key") foreignKey = true;
        else if (a == "--dump") { dumpPath = v; ++i; }
        else { fprintf(stderr, "unknown option %s\n", a.c_str()); return 2; }
    }

    // Ziarno do RNG stacji na porcie (rng_seeded.cpp); generator bierze bajty tylko z rnd().
    RNG.stir(reinterpret_cast<const uint8_t*>(&rngState), sizeof(rngState));
    fram.clockPath = framPath + ".clock";
    const std::string idPath = framPath + ".id";
    const std::string savedClock = readFile(fram.clockPath);
    simMs = savedClock.empty() ? startS * 1000 : strtoull(savedClock.c_str(), nullptr, 10) + gapS * 1000;
    if (setClockS) simMs = setClockS * 1000;
    if (!fram.open(framPath)) { fprintf(stderr, "fram %s\n", framPath.c_str()); return 2; }
    rnsnode::debugClock(simClock);

    // Węzły generatora i odbiorca stacji (pierwszy węzeł) przed startem stosu. Klucz odbiorcy przechodzi do
    // następnego startu w pliku obok FRAM, jak odbiorca z karty stacji.
    const std::string receiverPath = framPath + ".receiver";
    const std::string savedReceiver = readFile(receiverPath);
    for (size_t i = 0; i < PEERS; ++i) {
        if (i == 0 && savedReceiver.size() == 128) {
            uint8_t prv[64];
            for (size_t k = 0; k < 64; ++k) prv[k] = static_cast<uint8_t>(strtoul(savedReceiver.substr(2 * k, 2).c_str(), nullptr, 16));
            peers.push_back(fromPrivate(prv));
        } else {
            peers.push_back(newIdentity());
        }
        if (i == 0 && savedReceiver.empty()) writeFile(receiverPath, hex(peers.back().prv, sizeof(peers.back().prv)));
        peerDest.push_back(destinationOf(DEST_NAME.c_str(), peers.back().hash));
    }
    uint8_t keys[2][64] = {}, sa1[2][16] = {};
    memcpy(keys[0], peers[0].pub, 64);
    memcpy(sa1[0], peerDest[0].data(), 16);
    rnsnode::setReceivers(keys, sa1, 0);

    if (foreignKey) receiverForeignKey();
    const std::string savedId = readFile(idPath);
    uint8_t seed[32];
    for (uint8_t& b : seed) b = static_cast<uint8_t>(rnd());
    rnsnode::Hooks hooks;
    hooks.packet = [](const uint8_t*, size_t, bool& exception, void*) {
        ++appPackets;
        exception = false;
        return settleAll || rnd() % 4 != 0;
    };
    if (!rnsnode::begin(fram, radio, IFAC_KEY, simMs, !savedId.empty(), seed, hooks)) {
        const rnsnode::Status s = rnsnode::status();
        printf("{\"result\":\"%s\"}\n", s.identityLost ? "identity_lost" : "begin_failed");
        return 0;
    }
    const std::string id = hex(rnsnode::identityHash(), 16);
    if (savedId.empty()) writeFile(idPath, id);
    else if (savedId != id) fail("identity changed across restart");

    if (!rnsnode::publicKey(station.pub)) fail("no station key");
    rnscore::identityHash(station.pub, station.hash);
    stationDest = Bytes(rnsnode::address(), rnsnode::address() + 16);
    stationTransport = Bytes(rnsnode::identityHash(), rnsnode::identityHash() + 16);
    checkClock();
    if (!dumpPath.empty()) {
        dump = fopen(dumpPath.c_str(), "w");
        if (!dump) { fprintf(stderr, "dump %s\n", dumpPath.c_str()); return 2; }
        // Hasło sieci to 32 cyfry szesnastkowe klucza IFAC, bez nazwy sieci (rnsnode::begin; ifac_netkey w Pythonie).
        // Klucz stacji z rekordu klucza w FRAM (ten sam dla portu i rdzenia): Python odszyfrowuje nim pakiety do stacji.
        uint8_t prv[framfs::KEY_BYTES];
        if (!framfs::loadKey(fram, prv)) fail("dump: no station key in FRAM");
        fprintf(dump, "{\"ifac_netkey\":\"%s\",\"ifac_size\":%u,\"app\":\"%s.%s\",\"station_private_key\":\"%s\",\"peers\":[",
                hex(IFAC_KEY, sizeof(IFAC_KEY)).c_str(), static_cast<unsigned>(p1iface::IFAC_SIZE), DEST_APP, DEST_ASPECT,
                hex(prv, sizeof(prv)).c_str());
        for (size_t i = 0; i < PEERS; ++i) {
            fprintf(dump, "%s\"%s\"", i ? "," : "", hex(peers[i].prv, sizeof(peers[i].prv)).c_str());
        }
        fprintf(dump, "]}\n");
    }

    if (!defectName.empty()) {
        defect(defectName);
        for (int i = 0; i < 20; ++i) { simMs += 1000; service(); }
    }
    if (hostileDayCount) hostileDays(hostileDayCount, windowS, stopAfterS);
    if (foreignKey) receiverReadsReport();
    for (long n = 0; n < events; ++n) {
        const uint32_t e = rnd() % 100;
        if (e < 20) announceFromPeer();
        else if (e < 30) pathRequest();
        else if (e < 45) dataThroughStation();
        else if (e < 55) dataToStation();
        else if (e < 61) linkRequest();
        else if (e < 70) proofOrLinkTraffic();
        else if (e < 76) proofForStationPacket();
        else if (e < 82) replay();
        else if (e < 88) stationActs();
        else advanceClock();
        service();
    }
    for (int i = 0; i < 5; ++i) { simMs += 1000; service(); }

    checkClock();
    const rnsnode::Status s = rnsnode::status();
    char iface[rnsnode::INTERFACE_JSON_SIZE];
    rnsnode::interfaceJson(iface, sizeof(iface));
    // Niezmienniki: tablice w granicach konfiguracji, wpis odbiorcy zachowany.
    if (s.paths > RNS_PATH_TABLE_MAX + 2) fail("path table above limit");
    if (s.announceTable > RNS_ANNOUNCE_TABLE_MAX) fail("announce table above limit");
    if (!rnsnode::knows(peerDest[0].data())) fail("receiver identity lost");
    rnsnode::persist();
    msync(fram.bytes, FRAM_BYTES, MS_SYNC);
    saveClock();
    if (dump) fclose(dump);
    printf("{\"result\":\"ok\",\"identity\":\"%s\",\"new\":%s,\"fed\":%u,\"mutated\":%u,\"sent\":%u,\"paths\":%u,"
           "\"hashes\":%u,\"announce_table\":%u,\"pending\":%u,\"received\":%u,\"delivered\":%u,\"timed_out\":%u,"
           "\"announces\":%u,\"fs_files\":%u,\"fs_used\":%u,\"fs_capacity\":%u,\"writes\":%ld,\"clock_s\":%llu,\"traffic\":\"%016llx\","
           "\"iface\":{%s},\"flood\":{%s},\"generated\":{%s}}\n",
           id.c_str(), s.identityNew ? "true" : "false", fed, mutated, radio.sent, (unsigned)s.paths, (unsigned)s.packetHashes,
           (unsigned)s.announceTable, (unsigned)s.receiptsPending, s.packetsReceived, s.delivered, s.timedOut, s.announcesSeen,
           (unsigned)s.fsFiles, (unsigned)s.fsUsedBytes, (unsigned)s.fsCapacityBytes, fram.writes,
           static_cast<unsigned long long>(simMs / 1000), static_cast<unsigned long long>(trafficHash), iface,
           floodJson(), generatedJson().c_str());
    fflush(stdout);
    quit(0);
}
