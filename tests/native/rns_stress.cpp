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
//            [--long-jumps] [--cut-after-writes N] [--defect token48|short-announce]
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

#include "p1iface.h"
#include "rns_node.h"

namespace {

// ---- zegar symulowany: rns_node (debugClock) i stos przez gettimeofday ----
uint64_t simMs = 0;
uint64_t simClock() { return simMs; }

}  // namespace

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

// ---- IFAC jak w P1Interface (rns_node.cpp): klucz z 32 cyfr szesnastkowych ----
const uint8_t IFAC_KEY[16] = {0x57, 0x49, 0x43, 0x49, 0x2d, 0x73, 0x74, 0x72, 0x65, 0x73, 0x73, 0x2d, 0x69, 0x66, 0x61, 0x63};
const uint8_t IFAC_SALT[32] = {0xad, 0xf5, 0x4d, 0x88, 0x2c, 0x9a, 0x9b, 0x80, 0x77, 0x1e, 0xb4, 0x99, 0x5d, 0x70, 0x2d, 0x4a,
                               0x3e, 0x73, 0x33, 0x91, 0xb2, 0xa0, 0xf5, 0x3f, 0x41, 0x6d, 0x9f, 0x90, 0x7e, 0x55, 0xcf, 0xf8};
RNS::Bytes ifacKey;
RNS::Identity ifacIdentity(RNS::Type::NONE);

void ifacSetup() {
    char passphrase[33];
    for (int i = 0; i < 16; ++i) snprintf(passphrase + 2 * i, 3, "%02x", IFAC_KEY[i]);
    const RNS::Bytes origin = RNS::Identity::full_hash(RNS::Bytes(reinterpret_cast<const uint8_t*>(passphrase), 32));
    ifacKey = RNS::Cryptography::hkdf(64, RNS::Identity::full_hash(origin), RNS::Bytes(IFAC_SALT, sizeof(IFAC_SALT)));
    ifacIdentity = RNS::Identity(false);
    ifacIdentity.load_private_key(ifacKey);
}

std::vector<uint8_t> ifacWrap(const RNS::Bytes& raw) {
    if (raw.size() < 2 || raw.size() > p1iface::HW_MTU) return {};
    const RNS::Bytes signature = ifacIdentity.sign(raw);
    const uint8_t* tag = signature.data() + signature.size() - p1iface::IFAC_SIZE;
    const RNS::Bytes mask = RNS::Cryptography::hkdf(raw.size() + p1iface::IFAC_SIZE, RNS::Bytes(tag, p1iface::IFAC_SIZE), ifacKey);
    std::vector<uint8_t> wire(raw.size() + p1iface::IFAC_SIZE);
    p1iface::ifacMask(raw.data(), raw.size(), tag, p1iface::IFAC_SIZE, mask.data(), wire.data());
    return wire;
}

RNS::Bytes ifacUnwrap(const std::vector<uint8_t>& wire) {
    if (!p1iface::ifacPresent(wire.data(), wire.size(), p1iface::IFAC_SIZE)) return {};
    const RNS::Bytes mask = RNS::Cryptography::hkdf(wire.size(), RNS::Bytes(wire.data() + 2, p1iface::IFAC_SIZE), ifacKey);
    std::vector<uint8_t> raw(wire.size() - p1iface::IFAC_SIZE);
    p1iface::ifacUnmask(wire.data(), wire.size(), p1iface::IFAC_SIZE, mask.data(), raw.data());
    return RNS::Bytes(raw.data(), raw.size());
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
        switch (rnd() % 7) {
            case 0: v[at] ^= static_cast<uint8_t>(1u << (rnd() % 8)); break;
            case 1: v[at] = static_cast<uint8_t>(rnd()); break;
            case 2: v.erase(v.begin() + at); break;
            case 3: v.insert(v.begin() + at, static_cast<uint8_t>(rnd())); break;
            case 4: v[at] = (rnd() & 1) ? 0x00 : 0xFF; break;
            case 5: v.resize(at + 1); break;
            case 6: v[0] ^= static_cast<uint8_t>(1u << (rnd() % 7)); break;   // bez bitu IFAC
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
    std::vector<uint8_t> wire = v.size() >= 2 ? ifacWrap(RNS::Bytes(v.data(), v.size())) : v;
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

// Znane usterki portu jako jeden pakiet (przegląd 2026-10-21): token 48 B i krótkie ogłoszenie.
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

    ifacSetup();
    uint8_t pub[64];
    if (!rnsnode::publicKey(pub)) fail("no station key");
    station = RNS::Identity(false);
    station.load_public_key(RNS::Bytes(pub, 64));
    stationDest = RNS::Bytes(rnsnode::address(), 16);
    stationTransport = RNS::Bytes(rnsnode::identityHash(), 16);

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

    const rnsnode::Status s = rnsnode::status();
    // Niezmienniki: tablice w granicach konfiguracji, wpis odbiorcy zachowany.
    if (s.paths > RNS_PATH_TABLE_MAX + 2) fail("path table above limit");
    if (s.announceTable > RNS_ANNOUNCE_TABLE_MAX) fail("announce table above limit");
    if (!rnsnode::knows(peerDest[0].data())) fail("receiver identity lost");
    rnsnode::persist();
    msync(fram.bytes, FRAM_BYTES, MS_SYNC);
    saveClock();
    printf("{\"result\":\"ok\",\"identity\":\"%s\",\"new\":%s,\"fed\":%u,\"mutated\":%u,\"sent\":%u,\"paths\":%u,"
           "\"hashes\":%u,\"announce_table\":%u,\"pending\":%u,\"received\":%u,\"delivered\":%u,\"timed_out\":%u,"
           "\"announces\":%u,\"fs_files\":%u,\"fs_used\":%u,\"fs_capacity\":%u,\"writes\":%ld,\"clock_s\":%llu}\n",
           id.c_str(), s.identityNew ? "true" : "false", fed, mutated, radio.sent, (unsigned)s.paths, (unsigned)s.packetHashes,
           (unsigned)s.announceTable, (unsigned)s.receiptsPending, s.packetsReceived, s.delivered, s.timedOut, s.announcesSeen,
           (unsigned)s.fsFiles, (unsigned)s.fsUsedBytes, (unsigned)s.fsCapacityBytes, fram.writes,
           static_cast<unsigned long long>(simMs / 1000));
    fflush(stdout);
    _exit(0);   // bez destruktorów statycznych portu (kolejność niszczenia nie jest częścią próby)
}
