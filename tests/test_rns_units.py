# SPDX-License-Identifier: MIT
"""Host checks of the station's own Reticulum-stack units that do not need the stack itself: the P1
interface core (queue of 4 datagrams, priorities, announce limit, air time, IFAC masking against a
vector from reference Reticulum e40191b), the FRAM file system with its power-loss repairs and the
identity record, and the 8-byte packet hash list."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "firmware" / "src"

# Wektor z RNS.Transport.handle_outgoing_ifac (Reticulum e40191b): passphrase = klucz 16 B jako
# 32 cyfry szesnastkowe, ifac_size = 16; maska = HKDF(len(raw) + 16, tag, ifac_key).
IFAC_RAW = "0000000102030405060708090a0b0c0d0e0f00574943492049464143207465737420766563746f72"
IFAC_TAG = "606f0c2c5b0d4da76ba4092618f30206"
IFAC_MASK = ("6894d15a225ad596f8103b371c1f93e602cc50b96ca1a8caa4c2084dbd91d785"
             "510a9373c7152de386fa67b859cb3419990ecba86b597083")
IFAC_WIRE = ("e894606f0c2c5b0d4da76ba4092618f3020650b86ea2accfa2c50044b79adb88"
             "5f0593248e5664c3cfbc26fb79bf516aed2ebdcd082d1ff1")

HARNESS = r"""
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include "framfs.h"
#include "kiss.h"
#include "p1iface.h"
#include "pkthash.h"
#include "rns_announce.h"

struct Ram : journal::Storage {
    std::vector<uint8_t> bytes = std::vector<uint8_t>(512 * 1024, 0xFF);
    bool read(uint32_t a, uint8_t* d, size_t n) override {
        if (a + n > bytes.size()) return false;
        memcpy(d, &bytes[a], n);
        return true;
    }
    bool write(uint32_t a, const uint8_t* d, size_t n) override {
        if (a + n > bytes.size()) return false;
        memcpy(&bytes[a], d, n);
        return true;
    }
};

std::vector<uint8_t> unhex(const char* s) {
    std::vector<uint8_t> v;
    for (size_t i = 0; s[i] && s[i + 1]; i += 2) { unsigned x; sscanf(s + i, "%2x", &x); v.push_back((uint8_t)x); }
    return v;
}
std::string hex(const uint8_t* d, size_t n) {
    std::string s; char b[3];
    for (size_t i = 0; i < n; ++i) { snprintf(b, sizeof(b), "%02x", d[i]); s += b; }
    return s;
}

void listOne(const char* name, void*) { printf("entry %s\n", name); }

int fsScenario() {
    Ram ram;
    framfs::Fs fs(ram);
    // Argumenty ze skutkami ubocznymi najpierw do zmiennych: kolejność obliczania argumentów printf
    // zależy od kompilatora (gcc na x86-64 liczy od prawej).
    const int mounted = fs.mount();
    printf("mount %d formats %u blocks %u\n", mounted, fs.stats().formats, (unsigned)framfs::BLOCKS);
    const int a = fs.create("./path_store/seg0.dat");
    std::vector<uint8_t> data(1000);
    for (size_t i = 0; i < data.size(); ++i) data[i] = (uint8_t)(i * 7 + 3);
    printf("write %u\n", (unsigned)fs.write(a, 0, data.data(), data.size()));
    printf("append %u\n", (unsigned)fs.write(a, 1000, data.data(), 300));
    std::vector<uint8_t> back(1300);
    printf("read %u size %u\n", (unsigned)fs.read(a, 0, back.data(), back.size()), (unsigned)fs.size(a));
    printf("same %d %d\n", !memcmp(back.data(), data.data(), 1000), !memcmp(back.data() + 1000, data.data(), 300));
    printf("overwrite %u\n", (unsigned)fs.write(a, 120, data.data(), 20));
    fs.read(a, 120, back.data(), 20);
    printf("overwritten %d\n", !memcmp(back.data(), data.data(), 20));
    printf("find %d %d %d\n", fs.find("path_store/seg0.dat") == a, fs.find("/path_store//seg0.dat") == a, fs.find("path_store/seg1.dat"));
    const int b = fs.create("cache/0011");
    fs.write(b, 0, data.data(), 10);
    fs.create("cache/2233");
    fs.create("cache/sub/x");
    printf("list %u\n", (unsigned)fs.list("./cache", listOne, nullptr));
    printf("dir %d %d\n", fs.directoryExists("cache"), fs.directoryExists("nothing"));
    const int renamed = fs.rename("cache/0011", "cache/2233");
    printf("rename %d %d %d\n", renamed, fs.find("cache/0011"), fs.size(fs.find("cache/2233")) == 10);
    const size_t used = fs.stats().usedBlocks;
    const int truncated = fs.truncate(a);
    printf("truncate %d size %u freed %d\n", truncated, (unsigned)fs.size(a), fs.stats().usedBlocks < used);
    const int removed = fs.remove("cache/2233");
    const int removedAgain = fs.remove("cache/2233");
    printf("remove %d %d files %u\n", removed, removedAgain, (unsigned)fs.stats().files);
    fs.write(a, 0, data.data(), 700);
    framfs::Fs again(ram);
    const int remounted = again.mount();
    printf("remount %d files %u formats %u size %u\n", remounted, (unsigned)again.stats().files, again.stats().formats,
           (unsigned)again.size(again.find("path_store/seg0.dat")));
    char name[framfs::NAME_LEN + 1];
    printf("name %d %s\n", again.name(again.find("path_store/seg0.dat"), name), name);
    const int removedDir = again.removeDirectory("cache");
    printf("removedir %d files %u\n", removedDir, (unsigned)again.stats().files);
    return 0;
}

int fsFull() {
    Ram ram;
    framfs::Fs fs(ram);
    fs.mount();
    std::vector<uint8_t> block(4096, 0x5A);
    size_t total = 0;
    for (int i = 0; i < 100; ++i) {
        const int f = fs.create(("big/" + std::to_string(i)).c_str());
        if (f < 0) break;
        const size_t n = fs.write(f, 0, block.data(), block.size());
        total += n;
        if (n < block.size()) break;
    }
    printf("total %u capacity %u full %u free %u\n", (unsigned)total, (unsigned)fs.capacityBytes(), fs.stats().full,
           (unsigned)fs.freeBytes());
    int created = 0;
    for (int i = 0; i < 400; ++i) created += fs.create(("n/" + std::to_string(i)).c_str()) >= 0;
    printf("inodes %d\n", created);
    return 0;
}

// Zanik zasilania: stan FRAM sprzeczny na trzy sposoby, montowanie naprawia.
int fsRepair() {
    Ram ram;
    {
        framfs::Fs fs(ram);
        fs.mount();
        std::vector<uint8_t> data(600, 0x11);
        const int a = fs.create("a");
        fs.write(a, 0, data.data(), 600);           // 5 bloków
        const int b = fs.create("b");
        fs.write(b, 0, data.data(), 300);           // 3 bloki
        const int c = fs.create("c");
        fs.write(c, 0, data.data(), 200);           // 2 bloki
        printf("before used %u\n", (unsigned)fs.stats().usedBlocks);
    }
    const uint32_t nodes = framfs::FS_BASE + framfs::HEADER;
    const uint32_t fat = nodes + framfs::INODES * framfs::INODE;
    // 1. Plik "a" (600 B) z zerwanym łańcuchem: wpis FAT drugiego bloku wolny (przerwane zwalnianie).
    uint16_t first = ram.bytes[nodes + 6] | (ram.bytes[nodes + 7] << 8);
    uint16_t second = ram.bytes[fat + first * 2] | (ram.bytes[fat + first * 2 + 1] << 8);
    ram.bytes[fat + second * 2] = 0; ram.bytes[fat + second * 2 + 1] = 0;
    // 2. Węzeł "b" z uszkodzonym bajtem nazwy: CRC odrzuca węzeł.
    ram.bytes[nodes + framfs::INODE + 8] ^= 0x01;
    // 3. Blok-sierota: wpis FAT zajęty bez właściciela.
    ram.bytes[fat + 1400 * 2] = 0xFF; ram.bytes[fat + 1400 * 2 + 1] = 0xFF;
    framfs::Fs fs(ram);
    fs.mount();
    printf("after files %u dropped %u reclaimed %u used %u\n", (unsigned)fs.stats().files, fs.stats().dropped,
           fs.stats().reclaimed, (unsigned)fs.stats().usedBlocks);
    printf("exists %d %d %d\n", fs.find("a") >= 0, fs.find("b") >= 0, fs.find("c") >= 0);
    std::vector<uint8_t> back(200);
    const unsigned readC = (unsigned)fs.read(fs.find("c"), 0, back.data(), 200);
    printf("c intact %u %d\n", readC, back[199] == 0x11);
    framfs::Fs fs2(ram);
    fs2.mount();
    printf("stable dropped %u reclaimed %u used %u\n", fs2.stats().dropped, fs2.stats().reclaimed, (unsigned)fs2.stats().usedBlocks);
    return 0;
}

int keyScenario() {
    Ram ram;
    uint8_t key[64], out[64];
    printf("empty %d\n", framfs::loadKey(ram, out));
    for (int i = 0; i < 64; ++i) key[i] = (uint8_t)i;
    printf("save %d\n", framfs::saveKey(ram, key));
    int loaded = framfs::loadKey(ram, out);
    printf("load %d %d\n", loaded, !memcmp(out, key, 64));
    key[0] = 0xAA;
    framfs::saveKey(ram, key);
    loaded = framfs::loadKey(ram, out);
    printf("newer %d %02x\n", loaded, out[0]);
    // Uszkodzony nowszy slot: zostaje starszy.
    ram.bytes[framfs::IDENTITY_BASE + framfs::IDENTITY_SLOT + 20] ^= 0x40;
    loaded = framfs::loadKey(ram, out);
    printf("fallback %d %02x\n", loaded, out[0]);
    return 0;
}

struct FakeBytes {
    std::vector<uint8_t> v;
    const uint8_t* data() const { return v.data(); }
    size_t size() const { return v.size(); }
};
struct NoStore {};

int hashScenario() {
    static pkthash::List list;
    uint8_t h[32] = {};
    printf("zero %d\n", pkthash::key(h, 32) == 1);
    for (uint64_t i = 1; i <= pkthash::CAPACITY; ++i) list.add(i * 0x100000001ULL);
    printf("full %u %d %d\n", (unsigned)list.size(), list.contains(0x100000001ULL), list.contains(pkthash::CAPACITY * 0x100000001ULL));
    list.add(7);
    printf("evict %u %d %d %u\n", (unsigned)list.size(), list.contains(0x100000001ULL), list.contains(7), list.evicted());
    list.add(7);
    printf("dup %u\n", list.evicted());
    const int removed = list.remove(7);
    const int still = list.contains(7);
    printf("remove %d %d %d\n", removed, still, list.remove(7));
    NoStore store;
    static pkthash::ShortHashList<FakeBytes, NoStore> shl(store);
    FakeBytes a{std::vector<uint8_t>(32, 0x42)}, b{std::vector<uint8_t>(32, 0x42)};
    b.v[31] = 0;   // inny skrót, te same pierwsze 8 B: lista traktuje jak ten sam
    shl.put(a, {}, 0);
    printf("short %d %d %u\n", shl.exists(a), shl.exists(b), (unsigned)shl.size());
    printf("bytes %u\n", (unsigned)sizeof(pkthash::List));
    return 0;
}

// Pakiet Reticulum (nagłówek typu 1): bajt 0, skoki, cel 16 B, kontekst, dane (cel zapytania o trasę).
const uint8_t* pkt(uint8_t flags, uint8_t hops, const uint8_t* dest, size_t length, uint8_t context = 0,
                   const uint8_t* target = nullptr) {
    static uint8_t raw[600];
    memset(raw, 0, sizeof(raw));
    raw[0] = flags;
    raw[1] = hops;
    if (dest) memcpy(raw + 2, dest, 16);
    raw[18] = context;
    if (target) memcpy(raw + 19, target, 16);
    (void)length;
    return raw;
}

// Pakiet od stosu: w eterze raw + 16 B IFAC, pierwszy bajt w eterze = mark (rozpoznanie w kolejce).
p1iface::Admit put(p1iface::Queue& q, uint8_t flags, uint8_t hops, const uint8_t* dest, size_t length, uint32_t nowMs,
                   uint8_t mark, p1iface::Hint hint = p1iface::Hint::NONE, uint8_t context = 0, const uint8_t* target = nullptr) {
    static uint8_t wire[700];
    memset(wire, 0, sizeof(wire));
    wire[0] = mark;
    return q.offer(pkt(flags, hops, dest, length, context, target), length, wire, length + p1iface::IFAC_SIZE, nowMs, hint);
}

void drain(p1iface::Queue& q) {
    const uint8_t* d;
    size_t n;
    while (q.start(d, n)) q.finish(true);
}

std::string order(p1iface::Queue& q) {
    std::string s;
    const uint8_t* d;
    size_t n;
    char b[4];
    while (q.start(d, n)) { snprintf(b, sizeof(b), "%02x ", d[0]); s += b; q.finish(true); }
    return s;
}

const char* kindName(p1iface::Kind k) {
    return k == p1iface::Kind::CONTROL ? "control" : k == p1iface::Kind::DATA ? "data" : "announce";
}

int ifaceScenario() {
    using namespace p1iface;
    printf("air %u %u %u %u bitrate %u\n", airtimeMs(1), airtimeMs(86), airtimeMs(87), airtimeMs(600), declaredBitrate());
    const uint8_t data[] = {0x00, 0, 1}, announce[] = {0x01, 0, 1}, proof[] = {0x03, 0, 1}, plain[] = {0x08, 0, 1},
                  link[] = {0x02, 0, 1}, plainProof[] = {0x0B, 0, 1};
    printf("kind %s %s %s %s %s %s\n", kindName(classify(data, 3)), kindName(classify(announce, 3)), kindName(classify(proof, 3)),
           kindName(classify(plain, 3)), kindName(classify(link, 3)), kindName(classify(plainProof, 3)));
    uint8_t h1[40] = {0x00, 0x00}, h2[40] = {0x40, 0x00};
    for (int i = 0; i < 38; ++i) { h1[2 + i] = (uint8_t)i; h2[2 + i] = (uint8_t)i; }
    printf("dest %d %d %d", destination(h1, 40) == h1 + 2, destination(h2, 40) == h2 + 18, destination(h2, 30) == nullptr);   // wiersz kończy "pr"
    uint8_t r1[40] = {0x01, 0x02}, r2[40] = {0x41, 0x02};
    r1[18] = 0x0B;
    r2[34] = 0x0B;
    h1[18] = 0x0B;   // DATA z tym samym bajtem kontekstu
    printf(" pr %d %d %d %d\n", pathResponse(r1, 40), pathResponse(r2, 40), pathResponse(h1, 40), pathResponse(r2, 34));

    Queue q;
    const uint8_t d1[16] = {1}, d2[16] = {2}, d3[16] = {3}, d4[16] = {4}, d5[16] = {5}, d6[16] = {6}, d7[16] = {7};
    // 4 miejsca, piąty odrzucony z licznikiem (84 B + IFAC = 100 B w eterze).
    for (int i = 0; i < 5; ++i) printf("offer%d %s\n", i, admitName(put(q, 0x00, 0, d1, 84, 0, (uint8_t)(0x10 + i))));
    printf("counters queued %u full %u waitMs %u\n", q.counters().queued, q.counters().full, q.waitMs(1000));
    const uint8_t* p; size_t n;
    q.start(p, n);
    const uint8_t first = p[0];
    const unsigned firstLength = (unsigned)n;
    const int busy = q.transmitting();
    printf("first %02x len %u busy %d second %d\n", first, firstLength, busy, q.start(p, n));
    // W trakcie nadawania wchodzi dowód (wyższa klasa): kończy się nadawany, nie dowód.
    q.finish(true);
    printf("proof %s\n", admitName(put(q, 0x03, 0, d1, 34, 0, 0xC0)));
    q.start(p, n);
    printf("next %02x\n", p[0]);
    q.finish(true);
    q.start(p, n);
    printf("during %s\n", admitName(put(q, 0x03, 0, d1, 34, 0, 0xE0)));
    const uint8_t sending = p[0];
    q.finish(true);
    q.start(p, n);
    printf("kept %02x then %02x\n", sending, p[0]);
    q.finish(false);
    printf("failed %u sent %u left %u\n", q.counters().sendFailed, q.counters().sent, (unsigned)q.queued());
    drain(q);

    // Limit ogłoszeń 2% czasu zegarowego z czasu TX: własne i przekazywane (202 B + IFAC = 218 B).
    Queue a;
    const char* own1 = admitName(put(a, 0x01, 0, d1, 202, 1000, 0xA1));
    printf("own %s %s\n", own1, admitName(put(a, 0x01, 0, d1, 202, 1001, 0xA2)));
    const uint32_t gap = a.announceAllowedInMs(1000);
    printf("gap %u expected %u\n", gap, reservedTxMs(218) * 100 / ANNOUNCE_CAP_PERCENT);
    // Oczekujące: jedno na cel (nowsze zastępuje), 4 miejsca; przy pełnej liście ogłoszenie
    // z mniejszą liczbą skoków zastępuje to z największą, inne odpada.
    const char* held1 = admitName(put(a, 0x01, 2, d3, 202, 1100, 0xA3));
    const char* held2 = admitName(put(a, 0x01, 1, d3, 202, 1200, 0xA4));
    const char* held3 = admitName(put(a, 0x01, 1, d4, 202, 1300, 0xA5));
    const char* held4 = admitName(put(a, 0x01, 3, d5, 202, 1400, 0xA6));
    printf("held %s %s %s held %u\n", held1, held2, held3, (unsigned)a.held());
    printf("fourth %s\n", held4);
    const char* dropped = admitName(put(a, 0x01, 3, d6, 202, 1500, 0xA7));
    const char* better = admitName(put(a, 0x01, 1, d7, 202, 1600, 0xA8));
    printf("drop %s better %s held %u dropped %u\n", dropped, better, (unsigned)a.held(), a.counters().announcesDropped);
    // Odpowiedź na zapytanie o trasę (K0): poza limitem ogłoszeń.
    const char* response = admitName(put(a, 0x01, 4, d2, 202, 1700, 0xB0, Hint::NONE, 0x0B));
    printf("path response %s lane %s\n", response, laneName(a.lane(pkt(0x01, 4, d2, 202, 0x0B), 202)));
    drain(a);
    a.poll(1000 + gap - 1);
    printf("early %u\n", (unsigned)a.queued());
    a.poll(1000 + gap);
    a.start(p, n);
    printf("released %u held %u first %02x\n", (unsigned)a.queued(), (unsigned)a.held(), p[0]);   // najmniej skoków najpierw
    a.finish(true);
    a.poll(1000 + gap + 1);
    printf("one per gap %u\n", (unsigned)a.queued());
    a.poll(1000 + gap + HELD_LIFE_MS + 1);
    printf("expired %u held %u\n", a.counters().announcesExpired, (unsigned)a.held());
    printf("too large %s\n", admitName(put(a, 0x00, 0, d1, MAX_WIRE + 1 - IFAC_SIZE, 0, 0)));
    // Ponad 2^31 ms bez ogłoszenia: limit nie może się znów zamknąć przez zmianę znaku.
    drain(a);
    const uint32_t t = 2000000000u;
    put(a, 0x01, 1, d1, 202, t, 0xA9);
    drain(a);
    const uint32_t open = t + a.announceAllowedInMs(t);
    a.poll(open);
    const char* idle = admitName(put(a, 0x01, 1, d2, 202, open + 0x80000000u + 1, 0xAA));
    printf("idle %s wait %u\n", idle, a.announceAllowedInMs(open + 0x80000000u + 1) > 0);
    return 0;
}

int ifacVector(const char* rawHex, const char* tagHex, const char* maskHex, const char* wireHex) {
    const auto raw = unhex(rawHex), tag = unhex(tagHex), mask = unhex(maskHex), wire = unhex(wireHex);
    std::vector<uint8_t> out(raw.size() + tag.size()), back(raw.size());
    p1iface::ifacMask(raw.data(), raw.size(), tag.data(), tag.size(), mask.data(), out.data());
    printf("wire %s\n", hex(out.data(), out.size()).c_str());
    printf("present %d %d\n", p1iface::ifacPresent(wire.data(), wire.size(), 16), p1iface::ifacPresent(raw.data(), raw.size(), 16));
    p1iface::ifacUnmask(wire.data(), wire.size(), 16, mask.data(), back.data());
    printf("raw %s\n", hex(back.data(), back.size()).c_str());
    printf("tag %s\n", hex(wire.data() + 2, 16).c_str());
    return 0;
}

int announceScenario() {
    using rnsannounce::Policy;
    Policy st;
    st.begin(1000, 250);   // opóźnienie startowe 250 % 121 = 8 s
    printf("start %d %d %d\n", st.due(1007, false, true, 0), st.due(1008, false, true, 0), st.due(1008, true, true, 0));
    printf("offline %d\n", st.due(1008, false, false, 0));
    st.done(1008, 0);
    printf("once %d\n", st.due(5000, false, true, 0));
    printf("auto %d %d\n", st.due(1100, false, true, 1), st.due(1100, false, true, 2));   // 2 nieudane, ale < 30 min
    printf("auto late %d\n", st.due(1008 + 1800, false, true, 2));
    st.done(1008 + 1800, 2);
    printf("auto reset %d\n", st.due(1008 + 3600, false, true, 3));
    st.request();
    printf("manual %d %d\n", st.due(3000, true, true, 0), st.due(3000, false, true, 0));
    st.done(3000, 3);
    printf("after manual %d\n", st.due(3001, false, true, 3));
    Policy retry;
    retry.begin(0, 0);
    retry.done(0, 0);
    retry.request();
    retry.failed(600);
    // Każde due() osobno (kolejność obliczania argumentów printf).
    const bool now = retry.due(600, false, true, 0);
    const bool later = retry.due(600 + rnsannounce::RETRY_S, false, true, 0);
    printf("failed %d %d\n", now, later);
    return 0;
}

// Dostęp do kanału (radio.md, punkt 6): klasy K0/K1/K2, pula 60%, 25% na cel, zapytania o trasę,
// kolejność nadawania, okno przesuwne 3600 s.
int channelScenario() {
    using namespace p1iface;
    uint8_t rx[16], other[16], third[16];
    memset(rx, 0x11, 16);
    memset(other, 0x22, 16);
    memset(third, 0x33, 16);
    const uint32_t t0 = 3600000;
    // Klasy.
    Queue c;
    c.setReceiver(rx);
    uint8_t h2[60] = {0x40, 3};   // nagłówek typu 2: identyfikator transportu, potem cel
    memcpy(h2 + 18, rx, 16);
    std::string lanes;
    lanes += std::string(laneName(c.lane(pkt(0x00, 0, other, 100), 100))) + " ";                  // własne dane
    lanes += std::string(laneName(c.lane(pkt(0x00, 2, other, 100), 100))) + " ";                  // przekazywane obce
    lanes += std::string(laneName(c.lane(pkt(0x00, 2, rx, 100), 100))) + " ";                     // do odbiorcy
    lanes += std::string(laneName(c.lane(h2, 60))) + " ";                                         // do odbiorcy, nagłówek 2
    lanes += std::string(laneName(c.lane(pkt(0x00, 2, other, 100), 100, Hint::RECEIVER))) + " ";  // węzeł: USB
    lanes += std::string(laneName(c.lane(pkt(0x00, 2, other, 100), 100, Hint::OWN))) + " ";
    lanes += std::string(laneName(c.lane(pkt(0x03, 3, other, 34), 34))) + " ";                     // dowód przekazywany
    lanes += std::string(laneName(c.lane(pkt(0x08, 0, other, 67), 67))) + " ";                     // zapytanie o trasę
    lanes += std::string(laneName(c.lane(pkt(0x01, 0, rx, 150, 0x0B), 150))) + " ";               // odpowiedź na nie
    lanes += std::string(laneName(c.lane(pkt(0x01, 0, rx, 150), 150)));                            // ogłoszenie własne
    printf("lanes %s\n", lanes.c_str());
    c.setReceiver(nullptr);
    printf("unset %s\n", laneName(c.lane(pkt(0x00, 2, rx, 100), 100)));

    // Ostatnie wolne miejsce nie dla K2.
    Queue s;
    s.setReceiver(rx);
    for (int i = 0; i < 3; ++i) put(s, 0x00, 0, other, 500, t0, 0x01);
    const char* k2 = admitName(put(s, 0x00, 1, other, 500, t0, 0x02));
    const char* k1 = admitName(put(s, 0x00, 1, rx, 500, t0, 0x03));
    printf("last slot %s %s slot %u\n", k2, k1, s.counters().k2Slot);

    // Pula 60%: K2 (różne cele) do wyczerpania, potem K0, K1, dowód dalej; ogłoszenie czeka.
    Queue q;
    q.setReceiver(rx);
    unsigned admitted = 0;
    uint8_t d[16] = {};
    for (;;) {
        d[0] = (uint8_t)admitted;
        d[1] = (uint8_t)(admitted >> 8);
        if (put(q, 0x00, 1, d, 500, t0, 0x20) != Admit::QUEUED) break;
        ++admitted;
        drain(q);
    }
    printf("pool %u used %u k2_pool %u\n", admitted, q.poolUsedMs(t0), q.counters().k2Pool);
    const char* own = admitName(put(q, 0x00, 0, other, 500, t0, 0x30));
    const char* toRx = admitName(put(q, 0x00, 1, rx, 500, t0, 0x31));
    const char* proof = admitName(put(q, 0x03, 1, other, 34, t0, 0x32));
    printf("exempt own %s k1 %s proof %s\n", own, toRx, proof);
    drain(q);
    const char* ann = admitName(put(q, 0x01, 1, other, 150, t0, 0x33));
    q.poll(t0 + 59 * 60000);
    const unsigned at59 = (unsigned)q.queued();
    const char* k2at59 = admitName(put(q, 0x00, 1, other, 500, t0 + 59 * 60000, 0x34));
    // Okno przesuwne: przedział z t0 wypada po 60 min.
    q.poll(t0 + 60 * 60000);
    const unsigned at60 = (unsigned)q.queued();
    printf("announce %s at59 %u %s at60 %u used %u\n", ann, at59, k2at59, at60, q.poolUsedMs(t0 + 60 * 60000));
    drain(q);

    // Ogłoszenia liczą się do puli.
    Queue an;
    put(an, 0x01, 0, rx, 150, t0, 0x40);
    printf("announce pool %u expected %u\n", an.poolUsedMs(t0), channelMs(166));

    // 25% na cel w K2 tylko przy czekającym K0 lub K1.
    Queue g;
    g.setReceiver(rx);
    unsigned one = 0;
    for (; one < 80; ++one) {
        if (put(g, 0x00, 1, other, 500, t0, 0x50) != Admit::QUEUED) break;
        drain(g);
    }
    const uint32_t destUsed = g.destUsedMs(other, t0);
    put(g, 0x00, 0, rx, 500, t0, 0x51);               // K0 czeka
    const char* busyDest = admitName(put(g, 0x00, 1, other, 500, t0, 0x52));
    const char* busyOther = admitName(put(g, 0x00, 1, third, 500, t0, 0x53));   // inny cel K2
    printf("dest free %u used %u contended %s other %s k2_dest %u\n", one, destUsed, busyDest, busyOther, g.counters().k2Dest);
    drain(g);
    put(g, 0x00, 0, rx, 500, t0, 0x54);
    const uint8_t* p;
    size_t n;
    g.start(p, n);                                    // K0 w nadawaniu, nie czeka
    const char* sending = admitName(put(g, 0x00, 1, other, 500, t0, 0x55));
    printf("k0 sending %s\n", sending);
    g.finish(true);
    drain(g);
    put(g, 0x00, 1, rx, 500, t0, 0x56);               // K1 czeka
    const char* k1wait = admitName(put(g, 0x00, 1, other, 500, t0, 0x57));
    printf("k1 waiting %s\n", k1wait);
    drain(g);

    // Przekazywane zapytania o trasę: 1 na cel na 60 s, łącznie 5%; własne bez limitu.
    Queue r;
    uint8_t target[16], target2[16];
    memset(target, 0x77, 16);
    memset(target2, 0x78, 16);
    const char* r1 = admitName(put(r, 0x08, 0, other, 67, t0, 0x60, Hint::NONE, 0, target));
    drain(r);
    const char* r2 = admitName(put(r, 0x08, 0, other, 67, t0 + 59999, 0x61, Hint::NONE, 0, target));
    const char* r3 = admitName(put(r, 0x08, 0, other, 67, t0 + 1000, 0x62, Hint::NONE, 0, target2));
    const char* r4 = admitName(put(r, 0x08, 0, other, 67, t0 + 1000, 0x63, Hint::OWN, 0, target));
    const char* r5 = admitName(put(r, 0x08, 0, other, 67, t0 + 1000, 0x64, Hint::RECEIVER, 0, target));
    drain(r);
    const char* r6 = admitName(put(r, 0x08, 0, other, 67, t0 + 60000, 0x65, Hint::NONE, 0, target));
    drain(r);
    printf("path requests %s %s %s own %s receiver %s after %s limited %u used %u\n", r1, r2, r3, r4, r5, r6,
           r.counters().pathRequestLimited, r.pathRequestUsedMs(t0 + 60000));
    Queue r5q;
    unsigned requests = 0;
    for (;;) {
        uint8_t tg[16] = {};
        tg[0] = (uint8_t)requests;
        tg[1] = (uint8_t)(requests >> 8);
        if (put(r5q, 0x08, 0, other, 67, t0, 0x66, Hint::NONE, 0, tg) != Admit::QUEUED) break;
        ++requests;
        drain(r5q);
    }
    const char* ownOver = admitName(put(r5q, 0x08, 0, other, 67, t0, 0x67, Hint::OWN, 0, target));
    printf("path request share %u used %u own %s\n", requests, r5q.pathRequestUsedMs(t0), ownOver);

    // Kolejność: dowody i zapytania o trasę, potem K0 i K1 (od najstarszego), potem K2, na końcu ogłoszenia.
    Queue o;
    o.setReceiver(rx);
    put(o, 0x01, 1, other, 150, t0, 0xA0);   // ogłoszenie
    put(o, 0x00, 1, other, 100, t0, 0x20);   // K2
    put(o, 0x00, 1, rx, 100, t0, 0x10);      // K1
    put(o, 0x03, 1, other, 34, t0, 0x01);    // dowód
    const std::string first = order(o);
    put(o, 0x00, 1, rx, 100, t0, 0x11);      // K1
    put(o, 0x00, 0, other, 100, t0, 0x12);   // K0
    put(o, 0x08, 0, other, 67, t0, 0x02, Hint::OWN, 0, target);   // zapytanie o trasę
    put(o, 0x01, 1, rx, 150, t0, 0x03, Hint::NONE, 0x0B);          // odpowiedź na zapytanie
    printf("order %s| %s\n", first.c_str(), order(o).c_str());
    return 0;
}

std::string hexOf(const uint8_t* d, size_t n) {
    std::string s;
    char b[3];
    for (size_t i = 0; i < n; ++i) { snprintf(b, sizeof(b), "%02x", d[i]); s += b; }
    return s;
}

// Odczyt jak pętla stacji: fragmenty z output(), consume() po zapisie (najwyżej limit bajtów naraz).
std::string drainKiss(kiss::Port& p, size_t limit = 2048) {
    std::string s;
    for (;;) {
        size_t n = 0;
        const uint8_t* data = p.output(n);
        if (!n) return s;
        if (n > limit) n = limit;
        s += hexOf(data, n);
        p.consume(n);
    }
}

void feedHex(kiss::Port& p, const char* hex, uint32_t nowMs) {
    std::vector<uint8_t> b;
    for (size_t i = 0; hex[i] && hex[i + 1]; i += 2) { unsigned v; sscanf(hex + i, "%2x", &v); b.push_back(static_cast<uint8_t>(v)); }
    p.feed(b.data(), b.size(), nowMs);
}

// Interfejs Reticulum przez USB: ramki KISS jak KISSInterface Reticulum e40191b, bufor 8 pakietów,
// gotowość po przyjęciu pakietu, odrzuty liczone.
int kissScenario() {
    static kiss::Port p;
    p.setOpen(true);
    // Polecenia konfiguracji z configure_device() Reticulum: TXDELAY 35, TXTAIL 2, P 64, SLOTTIME 2, gotowość 1.
    feedHex(p, "c00123c0c00402c0c00240c0c00302c0c00f01c0", 0);
    const kiss::Counters& c = p.counters();
    // Każde wywołanie z efektem (output, send, pop) osobno: kolejność obliczania argumentów printf
    // nie jest określona (GCC od prawej).
    std::string out = drainKiss(p);
    printf("config commands %u flow %d ready %u out %s\n", c.commands, p.flowControl(), c.ready, out.c_str());
    // Ramka danych z FEND i FESC w treści: dekodowanie, gotowość od razu.
    feedHex(p, "c00001dbdcdbdd02c0", 10);
    const uint8_t* d;
    size_t n;
    p.peek(d, n);
    const std::string data = hexOf(d, n);
    out = drainKiss(p);
    printf("data %s buffered %zu ready %u out %s\n", data.c_str(), p.buffered(), c.ready, out.c_str());
    // Bufor 8 pakietów: siódmy dostaje gotowość, ósmy zapełnia bufor (gotowość zaległa), dziewiąty odpada.
    for (int i = 0; i < 7; ++i) feedHex(p, "c000aac0", 20);
    out = drainKiss(p);
    printf("full buffered %zu ready %u owed %s\n", p.buffered(), c.ready, out.c_str());
    feedHex(p, "c000bbc0", 30);
    printf("dropped %u buffered %zu\n", c.rxDropped, p.buffered());
    p.pop();
    out = drainKiss(p);
    printf("pop buffered %zu ready %u out %s\n", p.buffered(), c.ready, out.c_str());
    // Ramka rozdzielona między dwa odczyty z pop() pomiędzy: pakiet na swoim miejscu, kolejność zachowana.
    feedHex(p, "c000ccdd", 40);
    p.pop();
    feedHex(p, "eec0", 41);
    std::string order;
    while (p.peek(d, n)) { order += hexOf(d, n) + " "; p.pop(); }
    printf("split order %s\n", order.c_str());
    drainKiss(p);
    // Za długa ramka (501 B), przerwana ramka po 100 ms, wspólny FEND, numer portu w poleceniu.
    std::string big = "c000";
    for (int i = 0; i < 501; ++i) big += "11";
    big += "c0";
    feedHex(p, big.c_str(), 50);
    feedHex(p, "c00005", 60);
    feedHex(p, "06c0", 200);
    printf("large %u buffered %zu\n", c.rxTooLarge, p.buffered());
    feedHex(p, "c000aac000bbc0c010ccc0", 300);
    order.clear();
    while (p.peek(d, n)) { order += hexOf(d, n) + " "; p.pop(); }
    printf("shared %s\n", order.c_str());
    drainKiss(p);
    // Do komputera: kodowanie, miejsce na dwie ramki 500 B, zamknięty port.
    const uint8_t payload[4] = {0x01, 0xC0, 0xDB, 0x02};
    const bool sent = p.send(payload, sizeof(payload));
    out = drainKiss(p);
    printf("send %d out %s\n", sent, out.c_str());
    // Port przyjmuje po 3 B (zapis częściowy): bajty znikają z bufora dopiero po przyjęciu, ramka cała.
    const bool again = p.send(payload, sizeof(payload));
    out = drainKiss(p, 3);
    printf("partial %d out %s\n", again, out.c_str());
    static uint8_t block[500];
    memset(block, 0x5A, sizeof(block));
    const bool s1 = p.send(block, sizeof(block));
    const bool s2 = p.send(block, sizeof(block));
    const bool s3 = p.send(block, sizeof(block));
    printf("tx %d %d %d pending %zu dropped %u\n", s1, s2, s3, p.pendingBytes(), c.txDropped);
    p.setOpen(false);
    const bool closed = p.send(payload, sizeof(payload));
    printf("closed %d flow %d pending %zu dropped %u to %u from %u\n", closed, p.flowControl(), p.pendingBytes(), c.txDropped,
           c.toComputer, c.fromComputer);
    return 0;
}

int main(int argc, char** argv) {
    const std::string mode = argc > 1 ? argv[1] : "";
    if (mode == "channel") return channelScenario();
    if (mode == "kiss") return kissScenario();
    if (mode == "announce") return announceScenario();
    if (mode == "fs") return fsScenario();
    if (mode == "fsfull") return fsFull();
    if (mode == "fsrepair") return fsRepair();
    if (mode == "key") return keyScenario();
    if (mode == "hash") return hashScenario();
    if (mode == "iface") return ifaceScenario();
    if (mode == "ifac" && argc == 6) return ifacVector(argv[2], argv[3], argv[4], argv[5]);
    return 2;
}
"""


def compiler():
    for name in ("c++", "g++", "clang++"):
        if shutil.which(name):
            return name
    raise unittest.SkipTest("no C++ compiler")


class StackUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "harness.cpp").write_text(HARNESS, encoding="utf-8")
        cls.binary = root / "harness"
        subprocess.run([compiler(), "-std=c++17", "-Wall", "-Wextra", "-Werror", f"-I{SRC}", str(root / "harness.cpp"),
                        str(SRC / "framfs.cpp"), str(SRC / "kiss.cpp"), str(SRC / "p1iface.cpp"), str(SRC / "p1frame.cpp"),
                        "-o", str(cls.binary)],
                       check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_harness(self, *args):
        out = subprocess.run([str(self.binary), *args], check=True, capture_output=True, text=True).stdout
        return out.splitlines()

    def test_file_system_operations_and_remount(self):
        out = self.run_harness("fs")
        self.assertEqual(out[0], "mount 1 formats 1 blocks 1527")
        self.assertIn("write 1000", out)
        self.assertIn("append 300", out)
        self.assertIn("read 1300 size 1300", out)
        self.assertIn("same 1 1", out)
        self.assertIn("overwritten 1", out)
        self.assertIn("find 1 1 -1", out)
        # Lista katalogu: tylko pliki bezpośrednio w katalogu, nazwy bez katalogu.
        self.assertEqual([x for x in out if x.startswith("entry ")], ["entry 0011", "entry 2233"])
        self.assertIn("list 2", out)
        self.assertIn("dir 1 0", out)
        self.assertIn("rename 1 -1 1", out)
        self.assertIn("truncate 1 size 0 freed 1", out)
        self.assertIn("remove 1 0 files 2", out)
        self.assertIn("remount 1 files 2 formats 0 size 700", out)
        self.assertIn("name 1 path_store/seg0.dat", out)
        self.assertIn("removedir 1 files 1", out)

    def test_file_system_full(self):
        out = self.run_harness("fsfull")
        total, capacity, full = (int(x) for x in out[0].split()[1:6:2])
        # Blok 0 jest zarezerwowany; zapis kończy się na pełnej pamięci bez przekroczenia pojemności.
        self.assertEqual(total, capacity - 128)
        self.assertGreater(full, 0)
        self.assertIn("free 0", out[0])
        # 320 węzłów: część zajmują pliki "big/", reszta dla "n/".
        files = total // 4096 + 1
        self.assertEqual(out[1], f"inodes {320 - files}")

    def test_file_system_repairs_after_power_loss(self):
        out = self.run_harness("fsrepair")
        self.assertEqual(out[0], "before used 11")   # blok 0 + 5 + 3 + 2
        # "a" (zerwany łańcuch) i "b" (zły CRC) odrzucone; zwolnione bloki: 4 z "a" (drugi już wolny),
        # 3 z "b" i sierota; "c" nietknięty.
        self.assertEqual(out[1], "after files 1 dropped 2 reclaimed 8 used 3")
        self.assertEqual(out[2], "exists 0 0 1")
        self.assertEqual(out[3], "c intact 200 1")
        self.assertEqual(out[4], "stable dropped 0 reclaimed 0 used 3")

    def test_identity_record_two_slots(self):
        self.assertEqual(self.run_harness("key"),
                         ["empty 0", "save 1", "load 1 1", "newer 1 aa", "fallback 1 00"])

    def test_packet_hash_list_eight_bytes(self):
        out = self.run_harness("hash")
        self.assertEqual(out[0], "zero 1")
        self.assertEqual(out[1], "full 4096 1 1")
        self.assertEqual(out[2], "evict 4096 0 1 1")   # najstarszy wypada
        self.assertEqual(out[3], "dup 1")
        self.assertEqual(out[4], "remove 1 0 0")
        self.assertEqual(out[5], "short 1 1 1")
        self.assertLessEqual(int(out[6].split()[1]), 32 * 1024 + 64)   # 4096 x 8 B i liczniki

    def test_p1_interface_channel_access(self):
        out = self.run_harness("channel")
        self.assertEqual(out[0], "lanes k0 k2 k1 k1 k1 k0 control control control announce")
        self.assertEqual(out[1], "unset k2")
        self.assertEqual(out[2], "last slot k2_slot queued slot 1")
        # 500 B + IFAC = 516 B: 6 ramek po 195 ms TX, czas kanału 13t = 15 210 ms; 60% z 1 h = 2 160 000 ms.
        cost = 6 * 195 * 13
        n = 2160000 // cost
        self.assertEqual(out[3], f"pool {n} used {n * cost} k2_pool 1")
        self.assertEqual(out[4], "exempt own queued k1 queued proof queued")
        # Ogłoszenie ponad pulę czeka; po 60 min przedział z t0 wypada i ogłoszenie (166 B: 2 ramki) wychodzi.
        self.assertEqual(out[5], f"announce held at59 0 k2_pool at60 1 used {2 * 195 * 13}")
        self.assertEqual(out[6], f"announce pool {2 * 195 * 13} expected {2 * 195 * 13}")
        # Jeden cel bez rywalizacji ponad 25% (900 000 ms); przy czekającym K0 albo K1 odmowa.
        self.assertEqual(out[7], f"dest free 80 used {80 * cost} contended k2_dest other queued k2_dest 1")
        self.assertEqual(out[8], "k0 sending queued")   # K0 w nadawaniu już nie czeka
        self.assertEqual(out[9], "k1 waiting k2_dest")
        # 67 B + IFAC = 83 B: jedna ramka, 2 535 ms czasu kanału; 5% z 1 h = 180 000 ms.
        pr = 195 * 13
        self.assertEqual(out[10], f"path requests queued path_request_limit queued own queued receiver queued after queued "
                                  f"limited 1 used {3 * pr}")
        self.assertEqual(out[11], f"path request share {180000 // pr} used {180000 // pr * pr} own queued")
        self.assertEqual(out[12], "order 01 10 20 a0 | 02 03 11 12 ")

    def test_p1_interface_queue_priorities_and_announce_limit(self):
        out = self.run_harness("iface")
        # 1 B: jedna ramka 18 B; 86 B: pełna ramka; 87 B: dwie; 600 B: 7 ramek, 1362 ms; dług 12x -> 271 bit/s.
        self.assertEqual(out[0], "air 53 195 248 1362 bitrate 271")
        self.assertEqual(out[1], "kind data announce control control data control")
        self.assertEqual(out[2], "dest 1 1 1 pr 1 1 0 0")   # PATH_RESPONSE: tylko ogłoszenie, nagłówek 1 i 2
        self.assertEqual(out[3:8], ["offer0 queued", "offer1 queued", "offer2 queued", "offer3 queued", "offer4 full"])
        self.assertEqual(out[8], f"counters queued 4 full 1 waitMs {1000 + 4 * (270 + 2 * 195 * 12)}")
        # 100 B: 2 ramki, 270 ms; dług jak rezerwacja łącza: 2 ramki pełnej długości (195 ms) x 12
        self.assertEqual(out[9], "first 10 len 100 busy 1 second 0")
        self.assertEqual(out[10], "proof queued")
        self.assertEqual(out[11], "next c0")   # dowód przed danymi
        # Pakiet przyjęty w trakcie nadawania nie zastępuje nadawanego (błąd znaleziony w próbie zgodności).
        self.assertEqual(out[12], "during queued")
        self.assertEqual(out[13], "kept 11 then e0")
        self.assertEqual(out[14], "failed 1 sent 3 left 2")
        # Ogłoszenia własne też w limicie 2%: odstęp = czas TX (218 B: 3 ramki po 195 ms) x 50.
        self.assertEqual(out[15], "own queued held")
        self.assertEqual(out[16], f"gap {3 * 195 * 50} expected {3 * 195 * 50}")
        # Oczekujące: jedno na cel (nowsze zastępuje), 4 miejsca; pełna lista: mniej skoków wypiera najwięcej.
        self.assertEqual(out[17], "held held held held held 4")
        self.assertEqual(out[18], "fourth held")
        self.assertEqual(out[19], "drop announce_limit better held held 4 dropped 2")
        self.assertEqual(out[20], "path response queued lane control")
        self.assertEqual(out[21], "early 0")
        self.assertEqual(out[22], "released 1 held 3 first a2")   # najmniej skoków najpierw, nowsze tego samego celu
        self.assertEqual(out[23], "one per gap 0")
        self.assertEqual(out[24], "expired 3 held 0")
        self.assertEqual(out[25], "too large too_large")
        self.assertEqual(out[26], "idle queued wait 1")   # po 2^31 ms przerwy ogłoszenie od razu, potem nowy odstęp

    def test_announce_policy(self):
        self.assertEqual(self.run_harness("announce"), [
            "start 0 1 0",          # 0-120 s po starcie, nie w ciszy
            "offline 0",            # bez IFAC nic nie wychodzi
            "once 0",               # stacja: bez okresowych ogłoszeń
            "auto 0 0",             # 2 nieudane próby, ale mniej niż 30 min od ogłoszenia
            "auto late 1",          # 2 nieudane próby i 30 min
            "auto reset 0",         # licznik od ostatniego ogłoszenia
            "manual 0 1",           # polecenie czeka na koniec ciszy
            "after manual 0",
            "failed 0 1",           # stos nie wysłał: ponowienie po 60 s
        ])

    def test_kiss_frames_flow_control_and_buffer(self):
        out = self.run_harness("kiss")
        ready = "c00f01c0"
        self.assertEqual(out[0], "config commands 4 flow 1 ready 0 out ")
        self.assertEqual(out[1], f"data 01c0db02 buffered 1 ready 1 out {ready}")
        # 1 + 7 pakietów: gotowość po każdym poza ostatnim, który zapełnił bufor.
        self.assertEqual(out[2], f"full buffered 8 ready 7 owed {ready * 6}")
        self.assertEqual(out[3], "dropped 1 buffered 8")
        self.assertEqual(out[4], f"pop buffered 7 ready 8 out {ready}")
        self.assertEqual(out[5], "split order " + "aa " * 6 + "ccddee ")
        self.assertEqual(out[6], "large 1 buffered 0")
        self.assertEqual(out[7], "shared aa bb cc ")
        self.assertEqual(out[8], "send 1 out c00001dbdcdbdd02c0")
        self.assertEqual(out[9], "partial 1 out c00001dbdcdbdd02c0")   # zapis po 3 B: ta sama ramka
        self.assertEqual(out[10], "tx 1 1 0 pending 1006 dropped 1")
        self.assertEqual(out[11], "closed 0 flow 0 pending 0 dropped 2 to 4 from 12")

    def test_ifac_masking_matches_reference_vector(self):
        out = self.run_harness("ifac", IFAC_RAW, IFAC_TAG, IFAC_MASK, IFAC_WIRE)
        self.assertEqual(out[0], f"wire {IFAC_WIRE}")
        self.assertEqual(out[1], "present 1 0")
        self.assertEqual(out[2], f"raw {IFAC_RAW}")
        self.assertEqual(out[3], f"tag {IFAC_TAG}")


if __name__ == "__main__":
    unittest.main()
