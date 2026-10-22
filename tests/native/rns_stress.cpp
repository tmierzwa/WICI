// SPDX-License-Identifier: MIT
// Próba odporności stosu Reticulum stacji na komputerze (tests/test_rns_hostile.py): ruch od
// węzła z kodem IFAC (ważne ogłoszenia, zapytania o trasę, pakiety do stacji i przez stację,
// dowody, żądania łącza, powtórki) z mutacjami, przez warstwę rnsnode jak na stacji, z zegarem
// symulowanym (dni i tygodnie w sekundach) i z FRAM w pliku, w której zapis może się urwać
// w dowolnym miejscu (zanik zasilania). Jeden proces to jeden start stacji; FRAM, zegar
// i skrót tożsamości przechodzą do następnego startu w plikach obok FRAM.
//
// Generator ruchu buduje pakiety klasami portu microReticulum (pakiety jak z Reticulum
// w Pythonie); stos stacji widzi je wyłącznie jako datagramy z IFAC w rnsnode::received().
// Wynik: wiersz JSON na stdout; kod 3 = złamany niezmiennik, 75 = zanik zasilania w zapisie.
//
// rns_stress <fram> [--seed N] [--events N] [--mutate PERCENT] [--start S] [--gap S]
//            [--long-jumps] [--cut-after-writes N] [--defect token48|short-announce|held-announce|flood|damaged-receiver]
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/time.h>
#include <unistd.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include <microReticulum.h>
#include <microReticulum/Cryptography/HKDF.h>
#include <microReticulum/Cryptography/HMAC.h>
#include <microReticulum/Cryptography/X25519.h>
#include <microReticulum/Utilities/OS.h>
#include <microStore/Utility.h>

#include "framfs.h"
#include "p1iface.h"
#include "rns_node.h"

namespace {

// ---- zegar symulowany: rns_node (debugClock) i stos przez gettimeofday ----
uint64_t simMs = 0;
uint64_t simClock() { return simMs; }

}  // namespace

#ifdef WICI_RNS_CORE
// Stacja na rdzeniu (tests/test_rns_hostile.py, CoreHostileStackTests): port tylko generuje ruch, a jego
// magazyn wymaga funkcji ochrony wpisów, którą w obrazie z portem daje rns_node.cpp.
namespace microStore {
bool pinned_key(const uint8_t*, size_t) { return false; }
}  // namespace microStore

// Licznik operacji asymetrycznych rdzenia (identity.h; nagłówków rdzenia program prób nie włącza, bo
// packet.h rdzenia i Packet.h portu kolidują w systemie plików bez rozróżniania wielkości liter).
namespace rnscore {
uint32_t asymmetricOperations();
}  // namespace rnscore
#endif

extern "C" int gettimeofday(struct timeval* __restrict tv, void* __restrict) {
    tv->tv_sec = static_cast<time_t>(simMs / 1000);   // glibc deklaruje tv jako nonnull
    tv->tv_usec = static_cast<suseconds_t>((simMs % 1000) * 1000);
    return 0;
}

namespace {

constexpr int EXIT_INVARIANT = 3;
constexpr int EXIT_POWER_CUT = 75;
constexpr size_t FRAM_BYTES = 512 * 1024;

uint32_t rngState = 1;
uint32_t rnd() {
    rngState = rngState * 1103515245u + 12345u;
    return (rngState >> 16) & 0x7fff;
}
uint32_t rnd32() { return (rnd() << 15) ^ rnd(); }

RNS::Bytes randomBytes(size_t n) {
    RNS::Bytes b;
    for (size_t i = 0; i < n; ++i) b.append(static_cast<uint8_t>(rnd()));
    return b;
}

std::string hex(const uint8_t* d, size_t n) {
    static const char* digits = "0123456789abcdef";
    std::string s;
    for (size_t i = 0; i < n; ++i) { s += digits[d[i] >> 4]; s += digits[d[i] & 15]; }
    return s;
}

[[noreturn]] void fail(const char* what) {
    printf("{\"result\":\"invariant\",\"what\":\"%s\"}\n", what);
    fflush(stdout);
    _exit(EXIT_INVARIANT);
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
        _exit(EXIT_POWER_CUT);
    }
    memcpy(bytes + address, data, count);
    return true;
}

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
        if (recent.size() >= 32) recent.erase(recent.begin());
        recent.emplace_back(data, data + length);
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

std::vector<uint8_t> ifacWrap(const RNS::Bytes& raw) {
    std::vector<uint8_t> wire(p1iface::MAX_WIRE);
    wire.resize(rnsnode::debugIfacWrap(raw.data(), raw.size(), wire.data()));
    return wire;
}

RNS::Bytes ifacUnwrap(const std::vector<uint8_t>& wire) {
    uint8_t raw[p1iface::MAX_WIRE];
    const size_t n = rnsnode::debugIfacUnwrap(wire.data(), wire.size(), raw);
    return n ? RNS::Bytes(raw, n) : RNS::Bytes();
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
std::vector<RNS::Identity> peers;
std::vector<RNS::Bytes> peerDest;     // cele "wici.sa1" węzłów
RNS::Identity station(RNS::Type::NONE);
RNS::Bytes stationDest, stationTransport;
std::vector<RNS::Bytes> recentHashes, linkIds;
std::vector<std::vector<uint8_t>> recentWire;
uint32_t mutatePercent = 0;
uint32_t fed = 0, mutated = 0;

void remember(std::vector<RNS::Bytes>& v, const RNS::Bytes& b) {
    if (v.size() < 64) v.push_back(b);
    else v[rnd() % v.size()] = b;
}

RNS::Bytes headerTwo(const RNS::Bytes& raw, const RNS::Bytes& transportId) {
    RNS::Bytes out;
    out.append(static_cast<uint8_t>(raw.data()[0] | 0x40 | 0x10));
    out.append(raw.data()[1]);
    out << transportId << raw.mid(2);
    return out;
}

RNS::Bytes withHops(const RNS::Bytes& raw, uint8_t hops) {
    if (raw.size() < 2) return raw;
    std::vector<uint8_t> v(raw.data(), raw.data() + raw.size());
    v[1] = hops;
    return RNS::Bytes(v.data(), v.size());
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
void feed(const RNS::Bytes& raw, const char*) {
    std::vector<uint8_t> v(raw.data(), raw.data() + raw.size());
    const bool m = mutatePercent && rnd() % 100 < mutatePercent;
    const bool afterIfac = m && rnd() % 7 == 0;
    if (m && !afterIfac) mutate(v, 0);
    std::vector<uint8_t> wire = v.size() > p1iface::HW_MTU ? oversize(v) : v.size() >= 2 ? ifacWrap(RNS::Bytes(v.data(), v.size())) : v;
    if (afterIfac) mutate(wire, 1);
    if (m) ++mutated;
    ++fed;
    if (wire.empty()) return;
    if (recentWire.size() < 32) recentWire.push_back(wire);
    else recentWire[rnd() % recentWire.size()] = wire;
    rnsnode::received(wire.data(), wire.size());
}

RNS::Bytes packetHash(const RNS::Bytes& raw) {
    RNS::Packet p(raw);
    return p.unpack() ? p.get_hash() : RNS::Bytes();
}

void announceFromPeer() {
    const size_t i = rnd() % PEERS;
    RNS::Destination d(peers[i], RNS::Type::Destination::IN, RNS::Type::Destination::SINGLE, rnsnode::APP_NAME, rnsnode::ASPECT);
    RNS::Packet p = d.announce(randomBytes(rnd() % 40), rnd() % 4 == 0, {RNS::Type::NONE}, {}, false);
    RNS::Transport::deregister_destination(d);   // cel generatora nie może być celem lokalnym stosu
    p.pack();
    RNS::Bytes raw = p.raw();
    if (rnd() % 2) raw = headerTwo(raw, rnd() % 3 ? randomBytes(16) : stationTransport);
    feed(withHops(raw, randomHops()), "announce");
}

RNS::Bytes someDestination() {
    switch (rnd() % 4) {
        case 0: return randomBytes(16);
        case 1: return stationDest;
        default: return peerDest[rnd() % PEERS];
    }
}

void pathRequest() {
    RNS::Destination pr({RNS::Type::NONE}, RNS::Type::Destination::OUT, RNS::Type::Destination::PLAIN, "rnstransport", "path.request");
    RNS::Bytes data = someDestination();
    if (rnd() % 2) data << randomBytes(16);
    data << randomBytes(rnd() % 3 ? 16 : rnd() % 20);
    RNS::Packet p(pr, data, RNS::Type::Packet::DATA);
    p.pack();
    feed(withHops(p.raw(), randomHops()), "path-request");
}

void dataThroughStation() {
    RNS::Destination out(peers[rnd() % PEERS], RNS::Type::Destination::OUT, RNS::Type::Destination::SINGLE, rnsnode::APP_NAME,
                         rnsnode::ASPECT);
    RNS::Packet p(out, randomBytes(1 + rnd() % 300), RNS::Type::Packet::DATA);
    p.pack();
    const RNS::Bytes raw = headerTwo(p.raw(), rnd() % 4 ? stationTransport : randomBytes(16));
    remember(recentHashes, packetHash(raw));
    feed(withHops(raw, randomHops()), "transit");
}

void dataToStation() {
    RNS::Destination out(station, RNS::Type::Destination::OUT, RNS::Type::Destination::SINGLE, rnsnode::APP_NAME, rnsnode::ASPECT);
    RNS::Packet p(out, randomBytes(1 + rnd() % 300), RNS::Type::Packet::DATA);
    p.pack();
    RNS::Bytes raw = p.raw();
    if (rnd() % 2) raw = headerTwo(raw, stationTransport);
    remember(recentHashes, packetHash(raw));
    feed(withHops(raw, randomHops()), "local");
}

void linkRequest() {
    RNS::Identity ephemeral;
    RNS::Bytes data = ephemeral.get_public_key();
    if (rnd() % 2) data << randomBytes(3);
    const bool local = rnd() % 3 == 0;
    RNS::Destination out(local ? station : peers[rnd() % PEERS], RNS::Type::Destination::OUT, RNS::Type::Destination::SINGLE,
                         rnsnode::APP_NAME, rnsnode::ASPECT);
    RNS::Packet lr(out, data, RNS::Type::Packet::LINKREQUEST);
    lr.pack();
    RNS::Bytes raw = local ? lr.raw() : headerTwo(lr.raw(), stationTransport);
    RNS::Packet q(raw);
    if (q.unpack()) remember(linkIds, RNS::Link::link_id_from_lr_packet(q));
    feed(withHops(raw, randomHops()), "link-request");
}

void proofOrLinkTraffic() {
    RNS::Bytes raw;
    const uint32_t r = rnd() % 3;
    if (r == 0 && !linkIds.empty()) {   // LRPROOF do łącza
        raw.append(static_cast<uint8_t>(0x0F));
        raw.append(randomHops());
        raw << linkIds[rnd() % linkIds.size()];
        raw.append(static_cast<uint8_t>(0xFF));
        raw << randomBytes(rnd() % 2 ? 99 : rnd() % 140);
    } else if (r == 1 && !linkIds.empty()) {   // dane albo dowód w łączu
        raw.append(static_cast<uint8_t>(0x0C | (rnd() % 2 ? 0x03 : 0x00)));
        raw.append(randomHops());
        raw << linkIds[rnd() % linkIds.size()];
        raw.append(static_cast<uint8_t>(rnd()));
        raw << randomBytes(rnd() % 200);
    } else {   // dowód pakietu (jawny albo skrócony) do niedawnego pakietu
        const RNS::Bytes h = recentHashes.empty() ? randomBytes(32) : recentHashes[rnd() % recentHashes.size()];
        if (h.size() < 16) return;
        raw.append(static_cast<uint8_t>(0x03));
        raw.append(randomHops());
        raw << h.left(16);
        raw.append(static_cast<uint8_t>(0x00));
        if (rnd() % 2) raw << h;
        raw << randomBytes(64);
    }
    feed(raw, "proof");
}

// Ważny dowód od węzła dla pakietu, który wysłała stacja (potwierdzenie doręczenia).
void proofForStationPacket() {
    if (radio.recent.empty()) return;
    const RNS::Bytes raw = ifacUnwrap(radio.recent[rnd() % radio.recent.size()]);
    RNS::Packet p(raw);
    if (!raw || !p.unpack() || p.packet_type() != RNS::Type::Packet::DATA) return;
    for (size_t i = 0; i < PEERS; ++i) {
        if (p.destination_hash() != peerDest[i]) continue;
        const RNS::Bytes h = p.get_hash();
        RNS::Bytes proof;
        proof.append(static_cast<uint8_t>(0x03));
        proof.append(static_cast<uint8_t>(rnd() % 3));
        proof << h.left(16);
        proof.append(static_cast<uint8_t>(0x00));
        proof << h << peers[i].sign(h);
        feed(proof, "station-proof");
        return;
    }
}

void replay() {
    if (rnd() % 2 && !radio.recent.empty()) {   // datagram stacji wraca od innego przekaźnika
        const std::vector<uint8_t>& w = radio.recent[rnd() % radio.recent.size()];
        rnsnode::received(w.data(), w.size());
    } else if (!recentWire.empty()) {
        const std::vector<uint8_t>& w = recentWire[rnd() % recentWire.size()];
        rnsnode::received(w.data(), w.size());
    }
}

void stationActs() {
    switch (rnd() % 3) {
        case 0: rnsnode::announce(nullptr, 0); break;
        case 1: {
            const RNS::Bytes& d = peerDest[rnd() % PEERS];
            const RNS::Bytes data = randomBytes(1 + rnd() % 200);
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
    const double s = static_cast<double>(simMs / 1000);
    const double stack = RNS::Utilities::OS::time();
    if (stack < s - 1 || stack > s + 1) fail("stack does not follow the simulated clock");
    if (microStore::time() != static_cast<uint32_t>(simMs / 1000)) fail("microStore does not follow the simulated clock");
}

// Zalew wrogimi datagramami (stacja na rdzeniu): bez flagi IFAC, z kodem IFAC spoza sieci, z ważnym
// IFAC ogłoszenia z błędnym podpisem (także z celem odbiorcy z karty), dowody do nieznanych pakietów,
// pakiety do stacji bez ważnego tokenu, powtórzone nagranie jednego poprawnego ogłoszenia (IFAC przechodzi
// bez klucza sieci) i ogłoszenia z celem odbiorcy i obcym kluczem (kolizja). Dwa datagramy na obieg
// loop(), czyli szybciej, niż stacja je przetwarza. W każdym obiegu najwyżej jedna operacja asymetryczna
// (audyt rdzenia, U2). W trakcie zalewu: ogłoszenia odbiorcy z karty, pakiet stacji do odbiorcy i jego
// dowód (wynik w polu "flood", także gdy ruch ginie w pełnej kolejce). Pakiet do stacji, na który
// warstwa aplikacji odpowiada dowodem, kosztuje w jednym obiegu do trzech operacji (odszyfrowanie,
// podpis dowodu, IFAC dowodu; reticulum-core.md, tabela różnic).
#ifdef WICI_RNS_CORE
std::string floodResult;
std::vector<uint8_t> replayWire;   // nagrane poprawne ogłoszenie węzła 1 z IFAC

void serviceCounted(uint32_t limit = 1) {
    radio.poll();
    const uint32_t before = rnscore::asymmetricOperations();
    rnsnode::loop(static_cast<uint32_t>(simMs));
    if (rnscore::asymmetricOperations() - before > limit) fail("too many asymmetric operations in one loop pass");
}

void receive(const RNS::Bytes& raw) {
    const std::vector<uint8_t> wire = ifacWrap(raw);
    if (!wire.empty()) rnsnode::received(wire.data(), wire.size());
}

RNS::Bytes announceOf(size_t peer) {
    RNS::Destination d(peers[peer], RNS::Type::Destination::IN, RNS::Type::Destination::SINGLE, rnsnode::APP_NAME,
                       rnsnode::ASPECT);
    RNS::Packet a = d.announce(RNS::Bytes(), false, {RNS::Type::NONE}, {}, false);
    RNS::Transport::deregister_destination(d);
    a.pack();
    return a.raw();
}

uint32_t interfaceCounter(const char* name) {
    char iface[rnsnode::INTERFACE_JSON_SIZE];
    rnsnode::interfaceJson(iface, sizeof(iface));
    const std::string key = std::string("\"") + name + "\":";
    const char* at = strstr(iface, key.c_str());
    return at ? static_cast<uint32_t>(strtoul(at + key.size(), nullptr, 10)) : 0;
}

// Jawny dowód odbiorcy dla ostatniego pakietu stacji do niego; pusty, gdy stacja go jeszcze nie nadała.
RNS::Bytes receiverProof() {
    for (auto w = radio.recent.rbegin(); w != radio.recent.rend(); ++w) {
        const RNS::Bytes raw = ifacUnwrap(*w);
        RNS::Packet p(raw);
        if (!raw || !p.unpack() || p.packet_type() != RNS::Type::Packet::DATA || p.destination_hash() != peerDest[0]) continue;
        const RNS::Bytes h = p.get_hash();
        RNS::Bytes proof;
        proof.append(static_cast<uint8_t>(0x03));
        proof.append(static_cast<uint8_t>(0x00));
        proof << h.left(16);
        proof.append(static_cast<uint8_t>(0x00));
        proof << h << peers[0].sign(h);
        return proof;
    }
    return RNS::Bytes();
}

void hostileDatagram(bool replayOnly) {
    std::vector<uint8_t> v;
    switch (replayOnly ? 5 + rnd() % 2 : rnd() % 7) {
        case 0:   // bez flagi IFAC
            v = {static_cast<uint8_t>(rnd() & 0x7F), static_cast<uint8_t>(rnd())};
            for (uint32_t n = 18 + rnd() % 300; n; --n) v.push_back(static_cast<uint8_t>(rnd()));
            rnsnode::received(v.data(), v.size());
            return;
        case 1:   // flaga IFAC, kod spoza sieci
            v = {static_cast<uint8_t>(rnd() | 0x80), static_cast<uint8_t>(rnd())};
            for (uint32_t n = 40 + rnd() % 450; n; --n) v.push_back(static_cast<uint8_t>(rnd()));
            rnsnode::received(v.data(), v.size());
            return;
        case 2: {   // ogłoszenie z błędnym podpisem (bez danych aplikacji podpis to ostatnie 64 B)
            RNS::Bytes raw = announceOf(rnd() % 2 ? 0 : 1 + rnd() % (PEERS - 1));
            std::vector<uint8_t> a(raw.data(), raw.data() + raw.size());
            a[a.size() - 1 - rnd() % 64] ^= static_cast<uint8_t>(1u << (rnd() % 8));
            receive(RNS::Bytes(a.data(), a.size()));
            return;
        }
        case 3: {   // dowód niejawny do nieznanego pakietu
            RNS::Bytes raw;
            raw.append(static_cast<uint8_t>(0x03));
            raw.append(static_cast<uint8_t>(0x00));
            raw << randomBytes(16);
            raw.append(static_cast<uint8_t>(0x00));
            raw << randomBytes(64);
            receive(raw);
            return;
        }
        case 4: {   // pakiet do stacji z przypadkowym tokenem (ECDH, potem zły HMAC)
            RNS::Bytes raw;
            raw.append(static_cast<uint8_t>(0x00));
            raw.append(static_cast<uint8_t>(0x00));
            raw << stationDest;
            raw.append(static_cast<uint8_t>(0x00));
            raw << randomBytes(32 + 16 + 32 + 16 * (1 + rnd() % 4));
            receive(raw);
            return;
        }
        case 5:   // to samo nagranie poprawnego ogłoszenia (bez klucza sieci: kod IFAC jest deterministyczny)
            rnsnode::received(replayWire.data(), replayWire.size());
            return;
        default: {   // cel odbiorcy z karty z kluczem innego węzła (kolizja z wpisem odbiorcy)
            RNS::Bytes raw = announceOf(1 + rnd() % (PEERS - 1));
            std::vector<uint8_t> a(raw.data(), raw.data() + raw.size());
            memcpy(a.data() + 2, peerDest[0].data(), 16);
            receive(RNS::Bytes(a.data(), a.size()));
            return;
        }
    }
}

// Datagramy jednego obiegu: dwa wrogie i, gdy jest, jeden prawdziwy w przypadkowym miejscu między nimi.
void floodPass(bool replayOnly, const RNS::Bytes& genuine) {
    const uint32_t at = genuine ? rnd() % 3 : 3;
    for (uint32_t k = 0; k < 3; ++k) {
        if (k == at) receive(genuine);
        if (k < 2) hostileDatagram(replayOnly);
    }
    serviceCounted();
}

void flood() {
    replayWire = ifacWrap(announceOf(1));
    const uint32_t delivered0 = rnsnode::status().delivered;
    const uint8_t message[] = "report during the flood";
    uint32_t handle = 0, announceTries = 0, proofTries = 0;
    int pathRound = -1, deliveredRound = -1;
    for (int round = 0; round < 1200; ++round) {
        RNS::Bytes genuine;
        if (round == 100) handle = rnsnode::send(peerDest[0].data(), message, sizeof(message), rnsnode::RECEIPT_MIN_S);
        if (round >= 100 && pathRound < 0 && round % 100 == 0) {   // odbiorca ogłasza się co sekundę
            genuine = withHops(announceOf(0), 1);
            ++announceTries;
        } else if (handle && deliveredRound < 0 && round % 50 == 25) {   // dowód odbiorcy co pół sekundy
            genuine = receiverProof();
            if (genuine) ++proofTries;
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
        RNS::Bytes genuine;
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
    RNS::Destination out(station, RNS::Type::Destination::OUT, RNS::Type::Destination::SINGLE, rnsnode::APP_NAME, rnsnode::ASPECT);
    RNS::Packet p(out, RNS::Bytes("report after the flood"), RNS::Type::Packet::DATA);
    p.pack();
    receive(p.raw());
    for (int i = 0; i < 4; ++i) serviceCounted(3);
    if (rnsnode::status().packetsReceived != before + 1) fail("packet to the station lost after the flood");

    char text[256];
    snprintf(text, sizeof(text),
             "\"path_round\":%d,\"announce_tries\":%u,\"delivered_round\":%d,\"proof_tries\":%u,"
             "\"replay_announces\":%u,\"replay_accepted\":%u,\"replay_limited\":%u",
             pathRound, announceTries, deliveredRound, proofTries, replayAnnounces, replayAccepted, replayLimited);
    floodResult = text;
}

const char* floodJson() { return floodResult.c_str(); }

// Uszkodzone gniazdo odbiorcy z karty w tablicy znanych celów rdzenia (FRAM od framfs::FS_BASE, gniazda
// 568 B, cel od bajtu 16; lib/reticulum_core/src/table.h): pakiet stacji do odbiorcy wychodzi mimo to
// (wpis z kluczy karty od nowa), a gniazdo liczy "table_corrupt".
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
    const uint8_t message[] = "report after a damaged slot";
    if (!rnsnode::send(peerDest[0].data(), message, sizeof(message), rnsnode::RECEIPT_MIN_S)) {
        fail("damaged-receiver: report not sent");
    }
}
#else
void flood() { fail("flood: station core only"); }
const char* floodJson() { return ""; }
void damagedReceiver() { fail("damaged-receiver: station core only"); }
#endif

// Awarie portu z przeglądu 2026-10-21 (poprawione łatami 0005-0007) jako próby regresji.
void defect(const std::string& name) {
    if (name == "token48") {
        // Token z poprawnym HMAC (klucz z ECDH z kluczem publicznym stacji), ale bez szyfrogramu.
        auto ephemeral = RNS::Cryptography::X25519PrivateKey::generate();
        const RNS::Bytes shared = ephemeral->exchange(station.get_public_key().left(32));
        const RNS::Bytes derived = RNS::Cryptography::hkdf(64, shared, station.hash(), {RNS::Bytes::NONE});
        const RNS::Bytes iv = randomBytes(16);
        RNS::Bytes raw;
        raw.append(static_cast<uint8_t>(0x00));   // HEADER_1, SINGLE, DATA
        raw.append(static_cast<uint8_t>(0x00));
        raw << stationDest;
        raw.append(static_cast<uint8_t>(0x00));
        raw << ephemeral->public_key()->public_bytes() << iv << RNS::Cryptography::HMAC::generate(derived.left(32), iv)->digest();
        feed(raw, "defect");
    } else if (name == "short-announce") {
        RNS::Bytes raw;
        raw.append(static_cast<uint8_t>(0x01));   // HEADER_1, SINGLE, ANNOUNCE
        raw.append(static_cast<uint8_t>(0x00));
        raw << randomBytes(16);
        raw.append(static_cast<uint8_t>(0x00));
        raw << randomBytes(40);                   // urwane w kluczu Ed25519: odczyt poza buforem
        feed(raw, "defect");
    } else if (name == "held-announce") {
        // Ogłoszenie sąsiada i zaraz zapytanie o trasę do tego celu: odpowiedź odkłada ogłoszenie do
        // _held_announces, a Transport::jobs wstawia je z powrotem do _announce_table w pętli po niej.
        for (int round = 0; round < 8; ++round) {
            const size_t i = 1 + rnd() % (PEERS - 1);
            RNS::Destination d(peers[i], RNS::Type::Destination::IN, RNS::Type::Destination::SINGLE, rnsnode::APP_NAME,
                               rnsnode::ASPECT);
            RNS::Packet a = d.announce(randomBytes(8), false, {RNS::Type::NONE}, {}, false);
            RNS::Transport::deregister_destination(d);
            a.pack();
            feed(withHops(a.raw(), 1), "defect");
            RNS::Destination pr({RNS::Type::NONE}, RNS::Type::Destination::OUT, RNS::Type::Destination::PLAIN, "rnstransport",
                                "path.request");
            RNS::Bytes data = peerDest[i];
            data << randomBytes(16) << randomBytes(16);
            RNS::Packet q(pr, data, RNS::Type::Packet::DATA);
            q.pack();
            feed(withHops(q.raw(), 0), "defect");
            for (int k = 0; k < 30; ++k) { simMs += 1000; service(); }
        }
    } else if (name == "flood") {
        flood();
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
        else { fprintf(stderr, "unknown option %s\n", a.c_str()); return 2; }
    }

    fram.clockPath = framPath + ".clock";
    const std::string idPath = framPath + ".id";
    const std::string savedClock = readFile(fram.clockPath);
    simMs = savedClock.empty() ? startS * 1000 : strtoull(savedClock.c_str(), nullptr, 10) + gapS * 1000;
    if (setClockS) simMs = setClockS * 1000;
    if (!fram.open(framPath)) { fprintf(stderr, "fram %s\n", framPath.c_str()); return 2; }
    rnsnode::debugClock(simClock);

    // Węzły generatora i odbiorca stacji (pierwszy węzeł) przed startem stosu.
    for (size_t i = 0; i < PEERS; ++i) {
        peers.emplace_back();
        RNS::Destination d(peers.back(), RNS::Type::Destination::IN, RNS::Type::Destination::SINGLE, rnsnode::APP_NAME, rnsnode::ASPECT);
        peerDest.push_back(d.hash());
        RNS::Transport::deregister_destination(d);
    }
    uint8_t keys[2][64] = {}, sa1[2][16] = {};
    memcpy(keys[0], peers[0].get_public_key().data(), 64);
    memcpy(sa1[0], peerDest[0].data(), 16);
    rnsnode::setReceivers(keys, sa1, 0);

    const std::string savedId = readFile(idPath);
    uint8_t seed[32];
    for (uint8_t& b : seed) b = static_cast<uint8_t>(rnd());
    rnsnode::Hooks hooks;
    hooks.packet = [](const uint8_t*, size_t, bool& exception, void*) { exception = false; return rnd() % 4 != 0; };
    if (!rnsnode::begin(fram, radio, IFAC_KEY, simMs, !savedId.empty(), seed, hooks)) {
        const rnsnode::Status s = rnsnode::status();
        printf("{\"result\":\"%s\"}\n", s.identityLost ? "identity_lost" : "begin_failed");
        return 0;
    }
    const std::string id = hex(rnsnode::identityHash(), 16);
    if (savedId.empty()) writeFile(idPath, id);
    else if (savedId != id) fail("identity changed across restart");

    uint8_t pub[64];
    if (!rnsnode::publicKey(pub)) fail("no station key");
    station = RNS::Identity(false);
    station.load_public_key(RNS::Bytes(pub, 64));
    stationDest = RNS::Bytes(rnsnode::address(), 16);
    stationTransport = RNS::Bytes(rnsnode::identityHash(), 16);
    checkClock();

    if (!defectName.empty()) {
        defect(defectName);
        for (int i = 0; i < 20; ++i) { simMs += 1000; service(); }
    }
    for (long n = 0; n < events; ++n) {
        try {
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
        } catch (const std::exception&) {
            // wyjątek generatora (np. Packet nie mieści danych), nie stosu stacji
        }
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
    printf("{\"result\":\"ok\",\"identity\":\"%s\",\"new\":%s,\"fed\":%u,\"mutated\":%u,\"sent\":%u,\"paths\":%u,"
           "\"hashes\":%u,\"announce_table\":%u,\"pending\":%u,\"received\":%u,\"delivered\":%u,\"timed_out\":%u,"
           "\"announces\":%u,\"fs_files\":%u,\"fs_used\":%u,\"fs_capacity\":%u,\"writes\":%ld,\"clock_s\":%llu,\"iface\":{%s},\"flood\":{%s}}\n",
           id.c_str(), s.identityNew ? "true" : "false", fed, mutated, radio.sent, (unsigned)s.paths, (unsigned)s.packetHashes,
           (unsigned)s.announceTable, (unsigned)s.receiptsPending, s.packetsReceived, s.delivered, s.timedOut, s.announcesSeen,
           (unsigned)s.fsFiles, (unsigned)s.fsUsedBytes, (unsigned)s.fsCapacityBytes, fram.writes,
           static_cast<unsigned long long>(simMs / 1000), iface, floodJson());
    fflush(stdout);
    _exit(0);   // bez destruktorów statycznych portu (kolejność niszczenia nie jest częścią próby)
}
