# SPDX-License-Identifier: MIT
"""Host checks of Arduino-free firmware units: the P1 CRC, the test frame, the FRAM journal, the P1 frame codec,
SHA-256, HMAC-DRBG, the configuration document, the FRAM store, the station application layer, the USB protocol
"usb":2, the screen model with its texts, the console and the bitmap font, and the SA1 codec."""

from pathlib import Path
import base64
import hashlib
import hmac
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "firmware" / "src"
sys.path.insert(0, str(ROOT / "software" / "reference"))
from reference import MAX_CONTENT, PREFIX, check_button_configuration, crc16, encode_message, fragment  # noqa: E402

sys.path.insert(0, str(ROOT / "firmware" / "tools"))
import ui_texts  # noqa: E402

SOURCES = ("testframe.cpp", "annunciator.cpp", "journal.cpp", "p1frame.cpp", "ui.cpp", "font.cpp", "jsonlite.cpp", "sa1.cpp",
           "config.cpp", "sha2.cpp", "drbg.cpp", "store.cpp", "station.cpp", "usbproto.cpp", "console.cpp")

HARNESS = r"""
#include <cstdio>
#include <cstdlib>
#include <algorithm>
#include <cstring>
#include <string>
#include <vector>
#include "annunciator.h"
#include "config.h"
#include "console.h"
#include "crc16.h"
#include "crc32.h"
#include "drbg.h"
#include "font.h"
#include "fram_id.h"
#include "hexstr.h"
#include "journal.h"
#include "p1frame.h"
#include "sa1.h"
#include "sha2.h"
#include "station.h"
#include "store.h"
#include "testframe.h"
#include "ui.h"
#include "usbproto.h"

// Wywołania ze skutkami liczone przed printf: kolejność argumentów zależy od kompilatora (GCC, Clang).

// FRAM w RAM: 512 KiB skasowane do 0xFF jak nowy układ. budget: bajty zapisu od store::TX_BASE do
// zaniku zasilania (zapis przerwany w połowie, potem każdy zapis magazynu zawodzi); -1 bez limitu.
struct RamStorage : journal::Storage {
    std::vector<uint8_t> bytes = std::vector<uint8_t>(512 * 1024, 0xFF);
    size_t readBytes = 0;
    long budget = -1;
    bool read(uint32_t address, uint8_t* data, size_t count) override {
        if (address + count > bytes.size()) return false;
        memcpy(data, &bytes[address], count);
        readBytes += count;
        return true;
    }
    bool write(uint32_t address, const uint8_t* data, size_t count) override {
        if (address + count > bytes.size()) return false;
        size_t n = count;
        if (budget >= 0 && address >= store::TX_BASE) {
            if (static_cast<size_t>(budget) < n) n = static_cast<size_t>(budget);
            budget -= static_cast<long>(n);
        }
        memcpy(&bytes[address], data, n);
        return n == count;
    }
};

void printHex(const uint8_t* data, size_t length) {
    for (size_t i = 0; i < length; ++i) printf("%02X", data[i]);
}

void printLower(const uint8_t* data, size_t length) {
    for (size_t i = 0; i < length; ++i) printf("%02x", data[i]);
}

std::vector<uint8_t> unhex(const char* text) {
    std::vector<uint8_t> out;
    for (size_t i = 0; text[i] && text[i + 1]; i += 2) {
        const char byte[3] = {text[i], text[i + 1], 0};
        out.push_back(static_cast<uint8_t>(strtoul(byte, nullptr, 16)));
    }
    return out;
}

// --- Dziennik ----------------------------------------------------------------------------------

int journalScenario() {
    RamStorage ram;
    journal::Journal j(ram);
    const bool begun = j.begin();
    printf("fresh %d %d %u %u %u %d\n", begun, j.debtFresh(), j.debtValid(), j.clock().seq, j.eventSeq(), static_cast<int>(j.formatState()));
    const bool first = j.writeDebt(16228, 10);
    const bool second = j.writeDebt(5000, 20);
    printf("write %d %d\n", first, second);
    journal::Journal j2(ram);
    j2.begin();
    printf("reread %u %u %u %u\n", j2.debt().seq, j2.debt().a, j2.debt().b, j2.debtValid());
    // Zanik zasilania: treść rekordu 3 bez znacznika zatwierdzenia.
    journal::SmallRecord lost;
    lost.seq = 3; lost.a = 999; lost.b = 30;
    uint8_t body[journal::SMALL_RECORD];
    journal::encodeSmall(lost, body);
    ram.write(journal::DEBT_BASE + (3 % journal::SMALL_SLOTS) * journal::SMALL_RECORD, body, sizeof(body));
    journal::Journal j3(ram);
    j3.begin();
    printf("uncommitted %u %u %u\n", j3.debt().seq, j3.debt().a, j3.debtValid());
    // Uszkodzony bajt rekordu 2: zostaje rekord 1.
    ram.bytes[journal::DEBT_BASE + (2 % journal::SMALL_SLOTS) * journal::SMALL_RECORD + 5] ^= 0x01;
    journal::Journal j4(ram);
    j4.begin();
    printf("corrupt %u %u %u\n", j4.debt().seq, j4.debt().a, j4.debtValid());
    for (int i = 0; i < 40; ++i) j4.writeDebt(100 + i, 40 + i);
    journal::Journal j5(ram);
    j5.begin();
    printf("ring %u %u %u\n", j5.debt().seq, j5.debt().a, j5.debtValid());
    // Zegar: start +60 s do licznika i S, liczba startów; zapis co 60 s bez cofania.
    const bool started = j5.startClock();
    printf("start %d %u %u %u\n", started, j5.counterAtStart(), j5.skipS(), j5.starts());
    const bool ticked = j5.writeClock(500);
    const bool backwards = j5.writeClock(100);
    printf("clock %d %d %u %u %u\n", ticked, backwards, j5.clock().a, j5.skipS(), j5.starts());
    journal::Journal j6(ram);
    j6.begin();
    const bool restarted = j6.startClock();
    printf("restart %d %u %u %u\n", restarted, j6.counterAtStart(), j6.skipS(), j6.starts());
    // Ustawienia ekranu i rezerwacja numerów zapisu (tylko rosnąca, także ponad 32 bity).
    const bool settings = j6.writeSettings(3, 5);
    const bool r1 = j6.writeReservation(1024);
    const bool r2 = j6.writeReservation(0x100000400ULL);
    const bool r3 = j6.writeReservation(2048);
    printf("settings %d %u %u reserve %d %d %d\n", settings, j6.settings().a, j6.settings().b, r1, r2, r3);
    // Format: READY ze znacznikiem tożsamości, potem DESTROYING.
    const bool f1 = j6.writeFormat(journal::FormatState::READY, journal::FORMAT_IDENTITY);
    journal::Journal j7(ram);
    j7.begin();
    printf("format %d %d %u %u %llu %u %u\n", f1, static_cast<int>(j7.formatState()), j7.formatVersion(), j7.formatFlags(),
           static_cast<unsigned long long>(j7.reservation()), j7.settings().a, j7.settings().b);
    const bool f2 = j7.writeFormat(journal::FormatState::DESTROYING, 0);
    journal::Journal j8(ram);
    j8.begin();
    printf("destroying %d %d %u\n", f2, static_cast<int>(j8.formatState()), j8.formatFlags());
    // Zdarzenia z zawinięciem bufora 512 wpisów, długi tekst obcięty do 53 znaków.
    for (int i = 1; i <= 600; ++i) { char text[16]; snprintf(text, sizeof(text), "e%d", i); j8.writeEvent(i, text); }
    journal::Journal j9(ram);
    j9.begin();
    journal::EventRecord e0, e511, e512;
    const bool g0 = j9.readEvent(0, e0);
    const bool g511 = j9.readEvent(511, e511);
    const bool g512 = j9.readEvent(512, e512);
    printf("events %u %d %s %d %s %d\n", j9.eventSeq(), g0, e0.text, g511, e511.text, g512);
    j9.writeEvent(7, "0123456789012345678901234567890123456789012345678901234567890123456789");
    journal::EventRecord longest;
    j9.readEvent(0, longest);
    printf("long %zu\n", strlen(longest.text));
    // ZNISZCZ DANE: zdarzenia, zegar i ustawienia znikają; dług, rezerwacja i format zostają.
    const bool erased = j9.erase();
    journal::Journal j10(ram);
    j10.begin();
    printf("erase %d %u %u %u %u %llu %d %u\n", erased, j10.eventSeq(), j10.clock().seq, j10.settings().seq, j10.debt().a,
           static_cast<unsigned long long>(j10.reservation()), static_cast<int>(j10.formatState()), j10.formatVersion());
    // Rekordy formatu zatwierdzone z błędnym CRC bez żadnego poprawnego: uszkodzenie, nie nowa pamięć.
    for (uint32_t slot = 0; slot < journal::SMALL_SLOTS; ++slot) {
        const uint32_t at = journal::FORMAT_BASE + slot * journal::SMALL_RECORD;
        if (!journal::blank(&ram.bytes[at], journal::SMALL_RECORD)) ram.bytes[at + 5] ^= 0x01;
    }
    journal::Journal j11(ram);
    j11.begin();
    printf("format_corrupt %d\n", static_cast<int>(j11.formatState()));
    return 0;
}

// --- SHA-256, HMAC, DRBG, konfiguracja ----------------------------------------------------------

int shaCommand(int argc, char** argv) {
    uint8_t out[sha2::DIGEST];
    if (argc == 4 && !strcmp(argv[2], "digest")) {
        const std::vector<uint8_t> data = unhex(argv[3]);
        sha2::digest(data.data(), data.size(), out);
        // Ten sam skrót w częściach po 7 B (bufor bloku).
        sha2::Hash h;
        for (size_t i = 0; i < data.size(); i += 7) h.update(data.data() + i, data.size() - i < 7 ? data.size() - i : 7);
        uint8_t parts[sha2::DIGEST];
        h.finish(parts);
        printLower(out, sizeof(out));
        printf(" %d\n", !memcmp(out, parts, sizeof(out)));
    } else if (argc == 5 && !strcmp(argv[2], "hmac")) {
        const std::vector<uint8_t> key = unhex(argv[3]), data = unhex(argv[4]);
        sha2::Hmac mac(key.data(), key.size());
        mac.update(data.data(), data.size());
        mac.finish(out);
        printLower(out, sizeof(out));
        printf("\n");
    } else if (argc == 5 && !strcmp(argv[2], "dest")) {
        const std::vector<uint8_t> key = unhex(argv[3]);
        if (key.size() != 64) return 2;
        uint8_t dest[16];
        sha2::destinationHash(key.data(), argv[4], dest);
        printLower(dest, sizeof(dest));
        printf("\n");
    } else return 2;
    return 0;
}

int drbgCommand(int argc, char** argv) {
    // drbg <entropia> <nonce> <długość>...
    const std::vector<uint8_t> entropy = unhex(argv[2]), nonce = unhex(argv[3]);
    drbg::Drbg d;
    std::vector<uint8_t> out(1);
    const bool unseeded = d.generate(out.data(), 1);
    d.seed(entropy.data(), entropy.size(), nonce.data(), nonce.size());
    printf("ready %d %d\n", d.ready(), unseeded);
    for (int i = 4; i < argc; ++i) {
        out.assign(strtoul(argv[i], nullptr, 10), 0);
        const bool ok = d.generate(out.data(), out.size());
        printf("%d ", ok);
        printLower(out.data(), out.size());
        printf("\n");
    }
    return 0;
}

struct TextSource : config::Source {
    std::string doc;
    size_t reads = 0, largest = 0;
    bool read(uint32_t offset, char* out, size_t length) override {
        if (offset + length > doc.size()) return false;
        memcpy(out, doc.data() + offset, length);
        ++reads;
        if (length > largest) largest = length;
        return true;
    }
};

void dumpConfig(const config::Config& c) {
    printf("conf role=%u stations=%u profile=%s\n", static_cast<unsigned>(c.role), c.stations, c.profile);
    for (size_t i = 0; i < c.addressCount; ++i) printf("conf address %s\n", c.addresses[i]);
    for (size_t i = 0; i < c.phraseCount; ++i) printf("conf phrase %s|%s|%s\n", c.phrases[i][0], c.phrases[i][1], c.phrases[i][2]);
    printf("conf ifac ");
    printLower(c.ifac, sizeof(c.ifac));
    printf("\n");
    if (c.role != config::Role::STATION) return;
    for (size_t r = 0; r < 2; ++r) {
        printf("conf receiver %zu ", r);
        printLower(c.receivers[r].lxmf, config::HASH);
        printf(" ");
        printLower(c.receivers[r].sa1, config::HASH);
        printf(" ");
        printLower(c.receivers[r].key, config::KEY);
        printf("\n");
    }
}

int configParse(const char* profile) {
    // Dokument ze standardowego wejścia; odczyt kawałkami jak z kopii w FRAM.
    TextSource source;
    char chunk[4096];
    size_t n;
    while ((n = fread(chunk, 1, sizeof(chunk), stdin)) > 0) source.doc.append(chunk, n);
    while (!source.doc.empty() && source.doc.back() == '\n') source.doc.pop_back();
    config::Config c;
    size_t worst = 0;
    const char* detail = config::parse(source, static_cast<uint32_t>(source.doc.size()), profile, c, worst);
    if (detail) { printf("parse err %s\n", detail); return 0; }
    printf("parse ok worst=%zu largest=%zu\n", worst, source.largest);
    dumpConfig(c);
    return 0;
}

// --- Stacja: magazyn, warstwa aplikacji, protokół USB, konsola i ekran nad wspólną FRAM w RAM -----

uint32_t storeCounter = 0;
void storeRandom(uint8_t* out, size_t count) {
    for (size_t i = 0; i < count; ++i) out[i] = static_cast<uint8_t>(0xE0 + (++storeCounter & 0x1F));
}

uint8_t xorshift(uint32_t& state) {
    state ^= state << 13;
    state ^= state >> 17;
    state ^= state << 5;
    return static_cast<uint8_t>(state >> 24);
}

struct World;

struct FakeServices : station::Services {
    World* w = nullptr;
    bool sw = false, forced = false, ready = true, busyFlag = false, refuse = false;
    uint32_t handle = 0;
    uint32_t rng = 12345;
    bool silence() override;
    bool silenceSwitch() override { return sw; }
    bool radioReady() override { return ready; }
    bool busy() override { return busyFlag; }
    uint32_t send(const uint8_t to[store::HASH], const uint8_t* data, size_t length, uint32_t) override {
        if (refuse) { printf("send refused\n"); return 0; }
        ++handle;
        char hex[2 * store::HASH + 1];
        hexstr::encode(to, store::HASH, hex);
        printf("send %u %s %.*s\n", handle, hex, static_cast<int>(length), reinterpret_cast<const char*>(data));
        return handle;
    }
    void randomBytes(uint8_t* out, size_t count) override { for (size_t i = 0; i < count; ++i) out[i] = xorshift(rng); }
    void log(const char* text) override { printf("log %s\n", text); }
    void address(uint8_t out[store::HASH]) override { memset(out, 0xAB, store::HASH); }
    void changed() override;
};

struct FakeHost : usbproto::Host {
    World* w = nullptr;
    bool prepFlag = true, announceOk = true;
    uint32_t rng = 777;
    bool prep() override { return prepFlag; }
    bool silenceSwitch() override;
    void randomBytes(uint8_t* out, size_t count) override { for (size_t i = 0; i < count; ++i) out[i] = xorshift(rng); }
    void log(const char* text) override { printf("log %s\n", text); }
    bool identity(uint8_t key[64], uint8_t lxmf[store::HASH]) override {
        for (size_t i = 0; i < 64; ++i) key[i] = static_cast<uint8_t>(0x40 + i);
        sha2::destinationHash(key, config::LXMF_NAME, lxmf);
        return true;
    }
    const char* stationName() override { return "WICI-TEST00"; }
    const char* version() override { return "host"; }
    uint32_t counterS() override;
    bool contactBeforeStart() override { return false; }
    void power(char* out, size_t size) override { snprintf(out, size, "\"source\":\"12v\""); }
    void diag(char* out, size_t size) override { snprintf(out, size, "\"corrupt\":0"); }
    bool announce() override { printf("announce %d\n", announceOk); return announceOk; }
    bool destroy() override;
    void configChanged(bool roleChanged) override { printf("config changed %d\n", roleChanged); }
    void confirmBegin(usbproto::Question question, const char* detail) override;
    usbproto::Confirm confirmPoll() override;
    void confirmEnd() override;
    void showCard(const char* fingerprint) override;
};

struct FakeActions : console::Actions {
    World* w = nullptr;
    bool announce() override;
    bool destroy() override;
    bool node() override;
    void log(const char* text) override { printf("log %s\n", text); }
};

struct World {
    RamStorage ram;
    journal::Journal* journal = nullptr;
    store::Store* store = nullptr;
    station::Station* app = nullptr;
    usbproto::Protocol* proto = nullptr;
    console::Console* con = nullptr;
    FakeServices services;
    FakeHost host;
    FakeActions actions;
    ui::Model model;
    bool hosted = false;
    bool stalled = false;   // laptop nie czyta portu (kolejka wyjściowa się nie opróżnia)
    std::string received;   // bajty z kolejki do najbliższego LF
    uint32_t ms = 0;
    World() { services.w = this; host.w = this; actions.w = this; }
    ~World() { stop(); }
    void stop() {
        delete con; delete proto; delete app; delete store; delete journal;
        con = nullptr; proto = nullptr; app = nullptr; store = nullptr; journal = nullptr;
    }
    store::Begin start() {
        stop();
        journal = new journal::Journal(ram);
        journal->begin();
        store = new store::Store(ram, *journal, storeRandom, "p1");
        const store::Begin result = store->begin();
        store->now(ms / 1000);
        app = new station::Station(*store, services);
        proto = new usbproto::Protocol(*store, *app, host);
        proto->begin();
        con = new console::Console(*store, *app, actions);
        if (hosted) model.attach(con);
        return result;
    }
    int slotOf(unsigned number) {
        for (size_t i = 0; i < store::REGISTER_SLOTS; ++i) {
            if (store->request(i).used() && store->request(i).number() == number) return static_cast<int>(i);
        }
        return -1;
    }
};

bool FakeServices::silence() { return sw || forced || (w->store->ok() && w->store->meta().silence); }
void FakeServices::changed() { w->con->invalidate(); }
bool FakeHost::silenceSwitch() { return w->services.sw; }
uint32_t FakeHost::counterS() { return w->store->now() + 1000; }
bool FakeHost::destroy() {
    const bool ok = w->store->destroy();
    printf("destroyed %d\n", ok);
    w->con->invalidate();
    return ok;
}
void FakeHost::confirmBegin(usbproto::Question question, const char* detail) {
    printf("ask %u\n", static_cast<unsigned>(question));
    w->model.ask(static_cast<ui::Question>(question), detail);
}
usbproto::Confirm FakeHost::confirmPoll() {
    const ui::Answer a = w->model.answer();
    return a == ui::Answer::WAITING ? usbproto::Confirm::WAITING : a == ui::Answer::YES ? usbproto::Confirm::YES : usbproto::Confirm::NO;
}
void FakeHost::confirmEnd() { printf("ask end\n"); w->model.dismiss(); }
void FakeHost::showCard(const char* fingerprint) { w->model.ask(ui::Question::CARD, fingerprint); }
bool FakeActions::announce() { return w->host.announce(); }
bool FakeActions::destroy() { return w->host.destroy(); }
bool FakeActions::node() { return w->store->configured() && !w->store->station(); }

const char* const RESULTS[] = {"stored", "duplicate", "no_config", "no_address", "full", "number_taken", "conflict",
                               "stale", "closed", "too_late", "invalid", "memory", "not_found"};
const char* const CONFIG_RESULTS[] = {"ok", "hash", "invalid", "memory"};

void commitConfig(World& w, const char* doc, bool badSha) {
    const size_t size = strlen(doc);
    uint8_t sha[32];
    sha2::digest(reinterpret_cast<const uint8_t*>(doc), size, sha);
    if (badSha) sha[0] ^= 0x01;
    bool written = w.store->configBegin();
    for (size_t offset = 0; offset < size && written; offset += 200) {
        written = w.store->configWrite(static_cast<uint32_t>(offset), reinterpret_cast<const uint8_t*>(doc) + offset,
                                       size - offset < 200 ? size - offset : 200);
    }
    const char* detail = nullptr;
    size_t worst = 0;
    const store::Store::ConfigResult result = w.store->configCommit(static_cast<uint32_t>(size), sha, detail, worst);
    printf("cfg %d %s %s worst=%zu seq=%u\n", written, CONFIG_RESULTS[static_cast<int>(result)], detail ? detail : "-", worst,
           w.store->config().seq);
    w.con->invalidate();
}

void deliver(World& w, const char* fromHex, const char* sa1) {
    std::string packet = std::string("[\"WICI\",1,\"") + fromHex + "\",\"abababababababababababababababab\"," + sa1 + "]";
    const bool resolved = w.app->received(reinterpret_cast<const uint8_t*>(packet.data()), packet.size());
    const bool traffic = w.app->exceptionTraffic();
    printf("rx %d %d\n", resolved, traffic);
    w.con->invalidate();
}

void dumpRegister(World& w, const char* label) {
    for (size_t i = 0; i < store::REGISTER_SLOTS; ++i) {
        store::Request r;
        if (!w.store->request(i).used() || !w.store->readRequest(i, r)) continue;
        char id[2 * store::HASH + 1];
        hexstr::encode(r.id, store::HASH, id);
        const bool closed = w.store->requestClosed(i);
        printf("reg %s slot=%zu num=%04u id=%s type=%u origin=%u stage=%u flags=%u dec=%u drev=%u rmax=%u rrcv=%d att=%u next=%u "
               "shi=%u rhi=%u gen=%u closed=%d alarm=%u\n",
               label, i, store::shortNumber(r.id), id, r.type, r.origin, static_cast<unsigned>(r.stage), r.flags, r.decision, r.decisionRev,
               r.rMax, r.rRcv, r.attempts, r.nextTryS, r.statusHi, r.replyHi, r.gen, closed, w.store->request(i).alarmS);
    }
}

void dumpInbox(World& w, const char* label) {
    for (size_t i = 0; i < store::INBOX_SLOTS; ++i) {
        store::Message m;
        if (!w.store->message(i).used() || !w.store->readMessage(i, m)) continue;
        printf("msg %s slot=%zu type=%u msg=%u read=%d event=%u source=%u sa1=%s\n", label, i, m.type, m.number, m.read, m.event, m.source, m.sa1);
    }
}

// Ekran sterowany z wejścia (bez "H" sam model, z "H" dołączona konsola nad magazynem):
// "L <0-2>" język po restarcie, "S <0-2>" start z wyborem języka, "K <UP|DOWN|OK|BACK> <ms>" przycisk,
// "KD/KU <przycisk> <ms>" naciśnięcie i zwolnienie, "T <ms>" czas, "P <0|1>" tryb przygotowania,
// "Q <0|1>" cisza, "O <0|1>" radio, "U <s>" kontakt, "N <n>" nowe, "C <n> <s>" kolejka, "V <mV>" napięcie,
// "X <rxok> <rxbad> <tx> <drop> <defer> <debt_ms>", "F <hz>" odchyłka, "PC <słyszany> <s> <in> <out> <odrzuty>"
// komputer stanowiska, "R" ekran, "M" lista WIADOMOŚCI, "B" bajty odczytane z FRAM, "W <tekst>" łamanie,
// "D <s>" czas, "G <tekst>" glify. Polecenia stacji (małe litery): zob. world().
int world() {
    World* wp = new World();
    World& w = *wp;
    w.start();
    w.model.start(ui::Lang::PL);
    ui::Status status;
    status.version = "bench-a-test";
    status.name = "WICI-000000";
    const char* const names[] = {"UP", "DOWN", "OK", "BACK"};
    static char line[16384];
    // Laptop czyta port po każdym poleceniu programu testowego: wiersze z kolejki wyjściowej, a migawka
    // biegnie dalej (poll), dopóki jest miejsce.
    const auto drain = [&w]() {
        while (!w.stalled) {
            size_t n = 0;
            const char* data = w.proto->output(n);
            if (!n) {
                if (!w.proto->snapshotActive()) return;
                w.proto->poll(w.ms);
                continue;
            }
            for (size_t i = 0; i < n; ++i) {
                if (data[i] != '\n') { w.received += data[i]; continue; }
                printf("<- %s\n", w.received.c_str());
                w.received.clear();
            }
            w.proto->consume(n);
        }
    };
    while (fgets(line, sizeof(line), stdin)) {
        drain();
        char* nl = strchr(line, '\n');
        if (nl) *nl = '\0';
        char cmd[16] = "";
        sscanf(line, "%15s", cmd);
        const char* arg = strchr(line, ' ') ? strchr(line, ' ') + 1 : "";
        unsigned a = 0, b = 0, c = 0, d = 0, e = 0, f = 0;
        char word[16];
        char hex[80] = "";
        if (!strcmp(cmd, "restart")) {
            const store::Begin result = w.start();
            printf("begin %s\n", store::beginName(result));
        } else if (!strcmp(cmd, "wipe")) {
            // Nowy układ FRAM (same 0xFF), start magazynu od zera.
            std::fill(w.ram.bytes.begin(), w.ram.bytes.end(), static_cast<uint8_t>(0xFF));
            const store::Begin result = w.start();
            printf("begin %s\n", store::beginName(result));
        } else if (!strcmp(cmd, "now")) {
            w.ms = static_cast<uint32_t>(strtoul(arg, nullptr, 10)) * 1000;
            w.store->now(w.ms / 1000);
        } else if (!strcmp(cmd, "ms")) {
            w.ms = static_cast<uint32_t>(strtoul(arg, nullptr, 10));
            w.store->now(w.ms / 1000);
        } else if (!strcmp(cmd, "cfg")) commitConfig(w, arg, false);
        else if (!strcmp(cmd, "cfgbad")) commitConfig(w, arg, true);
        else if (!strcmp(cmd, "cfgdump")) dumpConfig(w.store->config());
        else if (!strcmp(cmd, "staged")) {
            sscanf(arg, "%u %u", &a, &b);
            std::vector<uint8_t> out(b);
            const bool ok = w.store->configStaged(a, out.data(), b);
            printf("staged %d %.*s\n", ok, static_cast<int>(b), reinterpret_cast<const char*>(out.data()));
        } else if (!strcmp(cmd, "sub")) {
            sa1::Message m;
            const char* why = sa1::decode(arg, strlen(arg), m);
            if (why) { printf("sub err %s\n", why); continue; }
            station::Stored s;
            const station::Result result = w.app->submit(m, s);
            printf("sub %s %d %d %04u\n", RESULTS[static_cast<int>(result)], s.duplicate, s.released, s.number);
        } else if (!strcmp(cmd, "create")) {
            char text[200] = "";
            sscanf(arg, "%u %u %u %199[^\n]", &a, &b, &c, text);
            uint16_t number = 0;
            const station::Result result = w.app->create(static_cast<uint8_t>(a), static_cast<uint16_t>(b), static_cast<uint8_t>(c), text, number);
            printf("create %s %04u\n", RESULTS[static_cast<int>(result)], number);
        } else if (!strcmp(cmd, "revise")) {
            char text[200] = "";
            const int fields = sscanf(arg, "%u %u %u %199[^\n]", &a, &b, &c, text);
            const int slot = w.slotOf(a);
            const station::Result result = slot < 0 ? station::Result::NOT_FOUND
                                                    : w.app->revise(static_cast<uint16_t>(slot), static_cast<uint16_t>(b), static_cast<uint8_t>(c),
                                                                    fields == 4 ? text : nullptr);
            printf("revise %s\n", RESULTS[static_cast<int>(result)]);
        } else if (!strcmp(cmd, "cancel")) {
            uint8_t id[store::HASH] = {};
            hexstr::decode(arg, id, store::HASH);
            bool released = false;
            const station::Result result = w.app->cancel(id, released);
            printf("cancel %s %d\n", RESULTS[static_cast<int>(result)], released);
        } else if (!strcmp(cmd, "test")) {
            uint8_t nonce[store::NONCE] = {};
            hexstr::decode(arg, nonce, store::NONCE);
            station::Stored s;
            const station::Result result = w.app->test(nonce, s);
            printf("test %s ", RESULTS[static_cast<int>(result)]);
            printLower(s.id, store::HASH);
            printf(" %d\n", s.released);
        } else if (!strcmp(cmd, "stest")) {
            const station::Result result = w.app->scheduleTest(atoi(arg) != 0);
            printf("stest %s\n", RESULTS[static_cast<int>(result)]);
        } else if (!strcmp(cmd, "pause")) {
            const bool ok = w.app->pauseTest(atoi(arg) != 0);
            printf("pause %d %d\n", ok, w.app->testPaused());
        } else if (!strcmp(cmd, "backup")) {
            const bool ok = w.app->switchBackup();
            printf("backup %d\n", ok);
        } else if (!strcmp(cmd, "silence")) {
            const int fields = sscanf(arg, "%u %64s", &a, hex);
            uint8_t id[store::HASH] = {};
            const bool exception = fields == 2 && hexstr::decode(hex, id, store::HASH);
            const bool ok = w.app->setSilence(a != 0, exception ? id : nullptr, w.services.sw);
            printf("silence %d\n", ok);
        } else if (!strcmp(cmd, "switch")) w.services.sw = atoi(arg) != 0;
        else if (!strcmp(cmd, "radio")) w.services.ready = atoi(arg) != 0;
        else if (!strcmp(cmd, "busy")) w.services.busyFlag = atoi(arg) != 0;
        else if (!strcmp(cmd, "refuse")) w.services.refuse = atoi(arg) != 0;
        else if (!strcmp(cmd, "poll")) {
            w.app->poll();
            printf("inflight %zu\n", w.app->inFlight());
        } else if (!strcmp(cmd, "rcpt")) {
            sscanf(arg, "%u %u", &a, &b);
            w.app->receipt(a, b != 0);
        } else if (!strcmp(cmd, "in")) {
            char from[2 * store::HASH + 1] = "00000000000000000000000000000000";
            if (w.store->recipient()) hexstr::encode(w.store->recipient(), store::HASH, from);
            deliver(w, from, arg);
        } else if (!strcmp(cmd, "infrom")) {
            sscanf(arg, "%64s", hex);
            deliver(w, hex, arg + strlen(hex) + 1);
        } else if (!strcmp(cmd, "inraw")) {
            const bool resolved = w.app->received(reinterpret_cast<const uint8_t*>(arg), strlen(arg));
            printf("rx %d 0\n", resolved);
        } else if (!strcmp(cmd, "reg")) dumpRegister(w, arg);
        else if (!strcmp(cmd, "inbox")) dumpInbox(w, arg);
        else if (!strcmp(cmd, "stats")) {
            const station::Stats& s = w.app->stats();
            printf("stats %s sent=%u delivered=%u failed=%u received=%u rejected=%u skipped=%u bulletins=%u full=%u evicted=%u\n", arg, s.sent,
                   s.delivered, s.failed, s.received, s.rejected, s.skipped, s.bulletinsSkipped, s.inboxFull, s.evicted);
        } else if (!strcmp(cmd, "alarm")) {
            station::Alarm al;
            const bool any = w.app->alarm(al);
            const bool cause = w.app->alarmCause();
            if (any) printf("alarm %u %04u %u cause=%d\n", static_cast<unsigned>(al.kind), al.number, al.minutes, cause);
            else printf("alarm none cause=%d\n", cause);
        } else if (!strcmp(cmd, "ackalarm")) {
            station::Alarm al;
            if (w.app->alarm(al)) w.app->ackAlarm(al);
        } else if (!strcmp(cmd, "retry")) {
            sscanf(arg, "%u %u %u %u", &a, &b, &c, &d);
            printf("retry %u\n", station::Station::retryDelayS(static_cast<uint16_t>(a), b != 0, c, d));
        } else if (!strcmp(cmd, "sevents")) {
            unsigned ok = 0;
            for (unsigned i = 0; i < strtoul(arg, nullptr, 10); ++i) ok += w.app->stationEvent(store::PREP, i);
            printf("sevents %u\n", ok);
        } else if (!strcmp(cmd, "radioev")) {
            const bool ok = w.app->radioEvent(atoi(arg) != 0);
            printf("radioev %d\n", ok);
        } else if (!strcmp(cmd, "sa1s")) {
            for (size_t i = 0; i < store::REGISTER_SLOTS; ++i) {
                store::Request r;
                if (w.store->request(i).used() && w.store->readRequest(i, r)) printf("sa1 %04u %s\n", store::shortNumber(r.id), r.sa1);
            }
        } else if (!strcmp(cmd, "diag")) {
            const store::Diagnostics& g = w.store->diagnostics();
            printf("diag ok=%d corrupt=%u replayed=%u scrubbed=%u cfgcorrupt=%d head=%u min=%u requests=%zu messages=%zu free=%d ident=%d "
                   "receiver=%u silence=%d paused=%d epoch=",
                   w.store->ok(), g.corruptSlots, g.replayed, g.scrubbed, g.configCorrupt, w.store->head(), w.store->minEvent(),
                   w.store->requestCount(), w.store->messageCount(), w.store->freeRequestSlot(), w.store->identitySaved(),
                   w.store->meta().receiver, w.store->meta().silence, w.store->meta().testPaused);
            printLower(w.store->meta().epoch, store::EPOCH);
            printf("\n");
        } else if (!strcmp(cmd, "ev")) {
            store::Event ev;
            const bool ok = w.store->readEvent(static_cast<uint32_t>(strtoul(arg, nullptr, 10)), ev);
            printf("ev %d %u kind=%u a=%u value=%u\n", ok, ev.ev, static_cast<unsigned>(ev.kind), ev.a, ev.value);
        } else if (!strcmp(cmd, "slot")) {
            printf("slot %d state=%u\n", atoi(arg), static_cast<unsigned>(w.store->request(static_cast<size_t>(atoi(arg))).state));
        } else if (!strcmp(cmd, "close")) {
            const bool ok = w.store->close(w.store->head());
            printf("close %d\n", ok);
        } else if (!strcmp(cmd, "maintain")) {
            unsigned rounds = 0;
            while (w.store->maintain()) ++rounds;
            printf("maintain %u\n", rounds);
        } else if (!strcmp(cmd, "destroy")) {
            const bool ok = w.store->destroy();
            printf("destroy %d\n", ok);
        } else if (!strcmp(cmd, "ident")) {
            const bool ok = w.store->setIdentitySaved();
            printf("ident %d %d\n", ok, w.store->identitySaved());
        } else if (!strcmp(cmd, "destroying")) {
            const bool ok = w.journal->writeFormat(journal::FormatState::DESTROYING, w.journal->formatFlags());
            printf("destroying %d\n", ok);
        } else if (!strcmp(cmd, "txreq")) {
            // Wpis rejestru wprost przez transakcję: gniazdo, bajt id, r_max, nowy wpis.
            sscanf(arg, "%u %x %u %u", &a, &b, &c, &d);
            store::Request r;
            memset(r.id, static_cast<int>(b), store::HASH);
            hexstr::encode(r.id, store::HASH, hex);
            r.rMax = static_cast<uint16_t>(c);
            r.sa1Length = static_cast<uint16_t>(snprintf(r.sa1, sizeof(r.sa1), "[1,0,\"%s\",%u,1,1,\"a\",\"\",0]", hex, c));
            r.createdS = r.changedS = w.store->now();
            store::Tx tx(*w.store);
            tx.request(static_cast<uint16_t>(a), r, d != 0);
            const bool ok = tx.commit();
            printf("txreq %d %d\n", ok, w.store->ok());
        } else if (!strcmp(cmd, "tear")) w.ram.budget = atol(arg);
        else if (!strcmp(cmd, "flip")) w.ram.bytes[strtoul(arg, nullptr, 0)] ^= 0x01;
        else if (!strcmp(cmd, "poke")) {
            sscanf(arg, "%u %u", &a, &b);
            w.ram.bytes[a] = static_cast<uint8_t>(b);
        }
        else if (!strcmp(cmd, "addr")) {
            printf("addresses %zu selected %zu", w.store->addressCount(), w.store->selectedAddress());
            for (size_t i = 0; i < w.store->addressCount(); ++i) printf(" |%s", w.store->addressAt(i));
            printf(" |location %s\n", w.store->address());
        } else if (!strcmp(cmd, "sel")) w.store->selectAddress(strtoul(arg, nullptr, 10));
        else if (!strcmp(cmd, "connect")) w.proto->connected(w.ms);
        else if (!strcmp(cmd, "stall")) w.stalled = atoi(arg) != 0;
        else if (!strcmp(cmd, "markread")) printf("markread %d\n", w.app->markRead(static_cast<uint32_t>(strtoul(arg, nullptr, 10))));
        else if (!strcmp(cmd, "queue")) {
            size_t n = 0;
            w.proto->output(n);
            printf("queue accepts=%d snapshot=%d dropped=%u first=%zu\n", w.proto->acceptsInput(), w.proto->snapshotActive(),
                   w.proto->stats().dropped, n);
        }
        else if (!strcmp(cmd, "disconnect")) w.proto->disconnected();
        else if (!strcmp(cmd, "usb")) {
            w.proto->feed(arg, strlen(arg), w.ms);
            w.proto->feed("\n", 1, w.ms);
        } else if (!strcmp(cmd, "usbraw")) {
            const std::string longLine(strtoul(arg, nullptr, 10), 'x');
            w.proto->feed(longLine.data(), longLine.size(), w.ms);
            w.proto->feed("\n", 1, w.ms);
        } else if (!strcmp(cmd, "upoll")) w.proto->poll(w.ms);
        else if (!strcmp(cmd, "prep")) w.host.prepFlag = atoi(arg) != 0;
        else if (!strcmp(cmd, "announce")) w.host.announceOk = atoi(arg) != 0;
        else if (!strcmp(cmd, "cause")) printf("cause %d\n", w.con->alarmCause());
        else if (!strcmp(cmd, "ask")) {
            char detail[32] = "";
            sscanf(arg, "%u %31s", &a, detail);
            w.model.ask(static_cast<ui::Question>(a), detail);
        } else if (!strcmp(cmd, "answer")) printf("answer %u\n", static_cast<unsigned>(w.model.answer()));
        else if (!strcmp(cmd, "dismiss")) w.model.dismiss();
        else if (!strcmp(cmd, "H")) {
            w.hosted = true;
            w.model.attach(w.con);
        } else if (sscanf(line, "L %u", &a) == 1) w.model.restore(static_cast<ui::Lang>(a), ui::Screen::MAIN);
        else if (sscanf(line, "S %u", &a) == 1) w.model.start(static_cast<ui::Lang>(a));
        else if (sscanf(line, "PC %u %u %u %u %u", &a, &b, &c, &d, &e) == 5) {
            status.computerHeard = a; status.computerS = b; status.usbIn = c; status.usbOut = d; status.usbDrop = e;
        } else if (sscanf(line, "KD %15s %u", word, &a) == 2 || sscanf(line, "KU %15s %u", word, &a) == 2) {
            size_t i = 0;
            while (i < 4 && strcmp(word, names[i])) ++i;
            if (i < 4) { if (line[1] == 'D') w.model.down(static_cast<ui::Button>(i), a); else w.model.up(static_cast<ui::Button>(i), a); }
        } else if (sscanf(line, "K %15s %u", word, &a) == 2) {
            size_t i = 0;
            while (i < 4 && strcmp(word, names[i])) ++i;
            if (i < 4) w.model.press(static_cast<ui::Button>(i), a);
        } else if (sscanf(line, "T %u", &a) == 1) w.model.tick(a);
        else if (sscanf(line, "P %u", &a) == 1) status.prep = a;
        else if (sscanf(line, "Q %u", &a) == 1) { status.silence = a; w.services.forced = a; }
        else if (sscanf(line, "O %u", &a) == 1) { status.radioOk = a; w.con->setRadioFault(!a); }   // jak main.cpp: jedno źródło
        else if (sscanf(line, "U %u", &a) == 1) status.contactS = a;
        else if (sscanf(line, "N %u", &a) == 1) status.newMessages = a;
        else if (sscanf(line, "C %u %u", &a, &b) == 2) { status.queued = a; status.queueAgeS = b; }
        else if (sscanf(line, "V %u", &a) == 1) status.millivolts = static_cast<uint16_t>(a);
        else if (sscanf(line, "X %u %u %u %u %u %u", &a, &b, &c, &d, &e, &f) == 6) {
            status.rxOk = a; status.rxBad = b; status.txDatagrams = c; status.txDrop = d; status.deferrals = e; status.debtMs = f;
        } else if (sscanf(line, "F %u", &a) == 1) { status.foffValid = true; status.foffHz = static_cast<int32_t>(a); }
        else if (!strcmp(line, "M")) {
            const size_t count = w.con->itemCount();
            printf("items %zu\n", count);
            for (size_t i = 0; i < count; ++i) {
                ui::Item item;
                if (!w.con->item(i, item)) continue;
                printf("item %d %u %04u %u %u %u %u %u %d %u %d |%s\n", item.own, item.type, item.number, item.category, item.people, item.urgency,
                       static_cast<unsigned>(item.stage), item.decision, item.sentOnce, item.attempts, item.unread, item.text);
            }
        } else if (!strcmp(line, "B")) {
            printf("read %zu\n", w.ram.readBytes);
            w.ram.readBytes = 0;
        } else if (line[0] == 'R' && !line[1]) {
            if (w.hosted) status.newMessages = static_cast<uint32_t>(w.store->unread());
            ui::Lines lines;
            w.model.render(status, lines);
            printf("screen %s %d\n", ui::screenName(w.model.screen()), static_cast<int>(w.model.language()));
            for (size_t i = 0; i < ui::LINES; ++i) printf("%d|%s\n", lines.inverted[i], lines.text[i]);
        } else if (line[0] == 'W' && line[1] == ' ') {
            char out[8][ui::LINE_BYTES];
            const size_t n = ui::wrap(line + 2, out, 8);
            printf("wrap %zu\n", n);
            for (size_t i = 0; i < n; ++i) printf("|%s\n", out[i]);
        } else if (sscanf(line, "D %u", &a) == 1) {
            char out[3][24];
            for (size_t l = 0; l < 3; ++l) ui::duration(a, static_cast<ui::Lang>(l), out[l], sizeof(out[l]));
            printf("%s|%s|%s\n", out[0], out[1], out[2]);
        } else if (line[0] == 'G' && line[1] == ' ') {
            const char* p = line + 2;
            size_t missing = 0, total = 0;
            for (uint32_t cp = font::next(p); cp; cp = font::next(p)) { ++total; if (!font::has(cp)) ++missing; }
            printf("glyphs %zu %zu\n", total, missing);
        } else if (line[0]) {
            printf("unknown command %s\n", line);
            delete wp;
            return 3;
        }
    }
    drain();
    delete wp;
    return 0;
}

// --- P1 -----------------------------------------------------------------------------------------

// Wszystkie długości 1..600 z danymi i % 256 i identyfikatorem "12345678": jedna ramka na wiersz.
int buildAll() {
    uint8_t data[p1frame::MAX_DATAGRAM];
    for (size_t i = 0; i < sizeof(data); ++i) data[i] = static_cast<uint8_t>(i);
    const uint8_t id[8] = {'1', '2', '3', '4', '5', '6', '7', '8'};
    for (size_t length = 1; length <= p1frame::MAX_DATAGRAM; ++length) {
        const uint8_t count = p1frame::fragmentCount(length);
        for (uint8_t index = 0; index < count; ++index) {
            uint8_t frame[p1frame::MAX_FRAME];
            const size_t n = p1frame::buildFrame(data, length, id, index, frame);
            printf("%zu %u ", length, index);
            printHex(frame, n);
            printf("\n");
        }
    }
    return 0;
}

// Składanie sterowane z wejścia: "P <ms> <hex>" ramka, "X <ms>" wygaszanie, "S" statystyki, "A" liczba prób.
int assembleScript() {
    p1frame::Assembler assembler;
    char line[4096];
    while (fgets(line, sizeof(line), stdin)) {
        unsigned long ms = 0;
        char hex[2048];
        if (sscanf(line, "P %lu %2047s", &ms, hex) == 2) {
            uint8_t frame[p1frame::MAX_FRAME + 8];
            const size_t n = strlen(hex) / 2;
            if (n > sizeof(frame)) { printf("too long\n"); continue; }
            for (size_t i = 0; i < n; ++i) { unsigned v; sscanf(hex + 2 * i, "%2x", &v); frame[i] = static_cast<uint8_t>(v); }
            p1frame::Fragment fragment;
            const p1frame::Parse parse = p1frame::parseFrame(frame, n, fragment);
            if (parse != p1frame::Parse::OK) { printf("parse %s\n", p1frame::parseName(parse)); continue; }
            const p1frame::Outcome outcome = assembler.push(fragment, ms);
            printf("%s", p1frame::outcomeName(outcome));
            if (outcome == p1frame::Outcome::COMPLETE) {
                printf(" %zu ", assembler.completedLength());
                printHex(assembler.completed(), assembler.completedLength());
            }
            printf("\n");
        } else if (sscanf(line, "X %lu", &ms) == 1) {
            assembler.expire(ms);
            printf("expired\n");
        } else if (line[0] == 'S') {
            const p1frame::Stats& s = assembler.stats();
            printf("stats %u %u %u %u %u %u %u\n", s.stored, s.completed, s.duplicates, s.conflicts, s.late, s.evicted, s.expired);
        } else if (line[0] == 'A') {
            printf("active %zu\n", assembler.active());
        }
    }
    return 0;
}

int main(int argc, char** argv) {
    if (argc >= 3 && !strcmp(argv[1], "annun")) {
        // Kroki "<ms>/<znaczniki>/<nieprzeczytane>": S ekran alarmu, C przyczyna alarmu, Q cisza,
        // M wyciszony dźwięk; wynik na krok "<dioda>,<sygnał ms>".
        annunciator::Annunciator a;
        for (int i = 2; i < argc; ++i) {
            char flags[8] = {};
            unsigned ms = 0, unread = 0;
            if (sscanf(argv[i], "%u/%7[A-Z]/%u", &ms, flags, &unread) != 3 && sscanf(argv[i], "%u//%u", &ms, &unread) != 2) return 2;
            annunciator::Inputs in;
            in.alarmScreen = strchr(flags, 'S') != nullptr;
            in.alarmCause = strchr(flags, 'C') != nullptr;
            in.silence = strchr(flags, 'Q') != nullptr;
            in.muted = strchr(flags, 'M') != nullptr;
            in.unread = unread;
            const uint32_t beep = a.poll(ms, in);
            printf("%d,%u\n", a.led() ? 1 : 0, static_cast<unsigned>(beep));
        }
        return 0;
    }
    if (argc == 3 && !strcmp(argv[1], "framid")) {
        uint8_t id[fram::ID_BYTES] = {};
        for (size_t i = 0; i < fram::ID_BYTES && argv[2][2 * i] && argv[2][2 * i + 1]; ++i) {
            char byte[3] = {argv[2][2 * i], argv[2][2 * i + 1], 0};
            id[i] = static_cast<uint8_t>(strtoul(byte, nullptr, 16));
        }
        printf("%s\n", fram::partName(fram::classify(id)));
        return 0;
    }
    if (argc == 2 && !strcmp(argv[1], "world")) return world();
    if (argc >= 3 && !strcmp(argv[1], "sha")) return shaCommand(argc, argv);
    if (argc >= 4 && !strcmp(argv[1], "drbg")) return drbgCommand(argc, argv);
    if (argc == 3 && !strcmp(argv[1], "cfgparse")) return configParse(argv[2]);
    if (argc == 3 && !strcmp(argv[1], "crc32")) {
        printf("%08X\n", crc32::of(reinterpret_cast<const uint8_t*>(argv[2]), strlen(argv[2])));
        return 0;
    }
    if (argc == 3 && !strcmp(argv[1], "sa1")) {
        sa1::Message m;
        const char* why = sa1::decode(argv[2], strlen(argv[2]), m);
        if (why) { printf("err %s\n", why); return 0; }
        char out[sa1::MAX_CONTENT + 1];
        const size_t n = sa1::encode(m, out, sizeof(out));
        printf("ok %zu %s\n", n, n ? out : "");
        return 0;
    }
    if (argc >= 3 && !strcmp(argv[1], "config")) {
        const char* why = nullptr;
        const size_t n = sa1::buttonConfigurationSize(argv[2], const_cast<const char* const*>(argv + 3), static_cast<size_t>(argc - 3), &why);
        if (n) printf("ok %zu\n", n); else printf("err %s\n", why);
        return 0;
    }
    if (argc == 3 && !strcmp(argv[1], "crc")) {
        printf("%04X\n", p1::crc16(reinterpret_cast<const uint8_t*>(argv[2]), strlen(argv[2])));
        return 0;
    }
    if (argc == 2 && !strcmp(argv[1], "journal")) return journalScenario();
    if (argc == 2 && !strcmp(argv[1], "buildall")) return buildAll();
    if (argc == 2 && !strcmp(argv[1], "assemble")) return assembleScript();
    if ((argc == 4 || argc == 5) && !strcmp(argv[1], "frame")) {
        uint8_t frame[testframe::MAX_LENGTH];
        const size_t length = strtoul(argv[2], nullptr, 10);
        const uint16_t seq = static_cast<uint16_t>(strtoul(argv[3], nullptr, 10));
        const testframe::Fill fill = argc == 5 ? static_cast<testframe::Fill>(atoi(argv[4])) : testframe::Fill::PN9;
        if (!testframe::build(frame, length, seq, fill)) { printf("build failed\n"); return 1; }
        for (size_t i = 0; i < length; ++i) printf("%02X", frame[i]);
        printf("\n");
        uint16_t back = 0;
        const bool ok = testframe::check(frame, length, &back);
        frame[2] ^= 0x01;  // one flipped bit must fail the check (length 4 flips a CRC byte)
        const bool corrupt = testframe::check(frame, length, nullptr);
        printf("%s %u %s\n", ok ? "ok" : "bad", back, corrupt ? "accepted" : "rejected");
        return 0;
    }
    return 2;
}
"""

# Klucze tożsamości odbiorcy w próbach (dowolne 64 B wystarczą do skrótów).
MAIN_KEY = bytes(range(64))
BACKUP_KEY = bytes(range(64, 128))
SELF = "ab" * 16


def destination(key, name):
    """Reticulum destination hash: sha256(sha256(name)[:10] + sha256(key)[:16])[:16]."""
    return hashlib.sha256(hashlib.sha256(name.encode()).digest()[:10] + hashlib.sha256(key).digest()[:16]).digest()[:16]


def card(key):
    return {"lxmf": destination(key, "lxmf.delivery").hex(), "key": key.hex()}


MAIN_SA1 = destination(MAIN_KEY, "wici.sa1").hex()
BACKUP_SA1 = destination(BACKUP_KEY, "wici.sa1").hex()


def station_doc(addresses=("Szkoła, wejście B",), phrases=None, stations=2, profile="p1", **extra):
    doc = {"role": "stacja", "addresses": list(addresses), "receiver": {"main": card(MAIN_KEY), "backup": card(BACKUP_KEY)},
           "stations": stations, "phrases": phrases if phrases is not None else [], "ifac": "11" * 16,
           "radio": {"profile": profile}}
    doc.update(extra)
    return doc


def node_doc(profile="p1"):
    return {"role": "wezel", "ifac": "22" * 16, "radio": {"profile": profile}}


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def hmac_drbg(entropy, nonce, lengths):
    """HMAC-DRBG with SHA-256 (NIST SP 800-90A Rev. 1, 10.1.2): instantiate with entropy || nonce, no
    personalization string; generate without additional input."""
    key, value = b"\x00" * 32, b"\x01" * 32

    def mac(k, data):
        return hmac.new(k, data, hashlib.sha256).digest()

    def update(data):
        nonlocal key, value
        key = mac(key, value + b"\x00" + data)
        value = mac(key, value)
        if data:
            key = mac(key, value + b"\x01" + data)
            value = mac(key, value)

    update(entropy + nonce)
    out = []
    for length in lengths:
        stream = b""
        while len(stream) < length:
            value = mac(key, value)
            stream += value
        out.append(stream[:length])
        update(b"")
    return out


def compiler():
    for name in ("c++", "g++", "clang++"):
        path = shutil.which(name)
        if path:
            return path
    return None


@unittest.skipUnless(compiler(), "no host C++ compiler")
class HostUnitTests(unittest.TestCase):
    """Compile the Arduino-free firmware units with the host compiler and compare with the models and the spec."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        (root / "harness.cpp").write_text(HARNESS, encoding="utf-8")
        cls.binary = root / "harness"
        subprocess.run([compiler(), "-std=c++17", "-Wall", "-Wextra", "-Werror", f"-I{SRC}", str(root / "harness.cpp"),
                        *(str(SRC / name) for name in SOURCES), "-o", str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_harness(self, *args):
        return subprocess.run([str(self.binary), *args], capture_output=True, text=True, check=True).stdout.split()

    # --- sygnalizacja, identyfikacja FRAM, CRC, ramki -------------------------

    def annun(self, *steps):
        return [tuple(int(v) for v in s.split(",")) for s in self.run_harness("annun", *steps)]

    def test_led_flashes_one_percent_for_each_cause(self):
        # oprogramowanie.md: dioda miga krótkimi błyskami do odczytu, do usunięcia przyczyny alarmu i w ciszy.
        for flags, unread in (("", 1), ("C", 0), ("Q", 0), ("S", 0)):
            steps = [f"{ms}/{flags}/{unread}" for ms in (1000, 1049, 1050, 3000, 5999, 6000, 6050)]
            self.assertEqual([led for led, _ in self.annun(*steps)], [1, 1, 0, 0, 0, 1, 0], (flags, unread))
        self.assertEqual([led for led, _ in self.annun("1000//0", "6000//0", "12000//0")], [0, 0, 0])

    def test_flash_survives_slow_loop(self):
        # Obieg pętli dłuższy niż błysk: błysk trwa do następnego obiegu, żaden okres nie ginie.
        self.assertEqual([led for led, _ in self.annun("0/Q/0", "300/Q/0", "5200/Q/0", "5400/Q/0", "10500/Q/0")],
                         [1, 0, 1, 0, 1])

    def test_alarm_beeps_every_two_seconds_until_ok(self):
        steps = ["0//0", "100/SC/0", "1000/SC/0", "2100/SC/0", "3000/C/0", "4200/C/0", "4300/SC/0"]
        self.assertEqual([beep for _, beep in self.annun(*steps)], [0, 200, 0, 200, 0, 0, 200])

    def test_new_message_beep_respects_mute_only(self):
        # Wyciszenie dotyczy tylko zwykłego sygnału nowej wiadomości; po starcie bez sygnału za stare.
        self.assertEqual([b for _, b in self.annun("0//3", "100//4", "200//4", "300//3", "400//4")], [0, 100, 0, 0, 100])
        self.assertEqual([b for _, b in self.annun("0/M/0", "100/M/1", "200/QM/2")], [0, 0, 0])
        self.assertEqual([b for _, b in self.annun("0//0", "100/Q/1")], [0, 100])
        self.assertEqual([b for _, b in self.annun("0//0", "100/SMC/1")], [0, 200])

    def test_fram_identification(self):
        # RDID: MB85RS4MT 4 bajty (Adafruit_FRAM_SPI), CY15B104Q 9 bajtów (karta Infineon 001-94895, „Device ID”).
        cases = {"047F4903": "MB85RS4MT", "047F490B": "MB85RS4MT", "7F7F7F7F7F7FC22608": "CY15B104Q",
                 "7F7F7F7F7F7FC22610": "CY15B104Q",   # inna wersja układu
                 # CY15B104QN (karta 002-20526, tabela 19): -50SXI, -20LPXI, -20LPXC; 1,8 V CY15V104QN odrzucony
                 "7F7F7F7F7F7FC22C00": "CY15B104QN", "7F7F7F7F7F7FC22C01": "CY15B104QN",
                 "7F7F7F7F7F7FC22CA1": "CY15B104QN", "7F7F7F7F7F7FC22C04": "unknown", "7F7F7F7F7F7FC22CA5": "unknown",
                 "7F7F7F7F7F7FC22508": "unknown",     # FM25V20A, 2 Mbit
                 "047F4803": "unknown",               # MB85RS2MT, 2 Mbit
                 "7F7F7F7F7FC22608": "unknown", "FFFFFFFFFFFFFFFFFF": "unknown", "000000000000000000": "unknown"}
        for hexid, part in cases.items():
            self.assertEqual(self.run_harness("framid", hexid), [part], hexid)

    def test_crc_matches_spec_vector_and_model(self):
        self.assertEqual(self.run_harness("crc", "123456789"), ["29B1"])
        for text in ("", "A", "WICI 0.5"):
            self.assertEqual(int(self.run_harness("crc", text)[0] if text else "FFFF", 16), crc16(text.encode()))
        # CRC-32 znacznika zatwierdzenia rekordów FRAM: wektor z crc32.h i zlib.
        self.assertEqual(self.run_harness("crc32", "123456789"), ["CBF43926"])
        self.assertEqual(int(self.run_harness("crc32", "WICI rekord")[0], 16), zlib.crc32(b"WICI rekord"))

    def test_frame_round_trip_and_corruption(self):
        for length, seq in ((4, 0), (18, 1), (103, 65535), (50, 1234)):
            frame_hex, ok, back, corrupt = self.run_harness("frame", str(length), str(seq))
            frame = bytes.fromhex(frame_hex)
            self.assertEqual(len(frame), length)
            self.assertEqual(int.from_bytes(frame[:2], "big"), seq)
            self.assertEqual(int.from_bytes(frame[-2:], "big"), crc16(frame[:-2]))
            self.assertEqual((ok, int(back), corrupt), ("ok", seq, "rejected"), (length, seq))

    def test_zeros_and_ones_fill(self):
        # radio.md: ramki wzorcowe z samych zer i samych jedynek (długie ciągi jednakowych bitów).
        for fill, byte in ((1, 0x00), (2, 0xFF)):
            frame_hex, ok, back, _ = self.run_harness("frame", "103", "5", str(fill))
            frame = bytes.fromhex(frame_hex)
            self.assertEqual(set(frame[2:-2]), {byte})
            self.assertEqual((ok, int(back)), ("ok", 5))

    def test_filler_depends_on_sequence_and_is_not_constant(self):
        a = bytes.fromhex(self.run_harness("frame", "40", "7")[0])
        b = bytes.fromhex(self.run_harness("frame", "40", "8")[0])
        self.assertNotEqual(a[2:-2], b[2:-2])
        self.assertGreater(len(set(a[2:-2])), 10)

    def test_rejects_bad_lengths(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_harness("frame", "3", "1")
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_harness("frame", "104", "1")

    def test_p1_frames_match_model_for_every_length(self):
        lines = subprocess.run([str(self.binary), "buildall"], capture_output=True, text=True, check=True).stdout.splitlines()
        built = {}
        for line in lines:
            length, index, frame_hex = line.split()
            built[(int(length), int(index))] = bytes.fromhex(frame_hex)
        expected = {}
        for length in range(1, 601):
            data = bytes(i % 256 for i in range(length))
            for index, frame in enumerate(fragment(data, b"12345678")):
                expected[(length, index)] = frame[len(PREFIX):]
        self.assertEqual(built, expected)

    def assemble(self, script):
        return subprocess.run([str(self.binary), "assemble"], input="\n".join(script) + "\n", capture_output=True,
                              text=True, check=True).stdout.splitlines()

    @staticmethod
    def air(frame):
        return frame[len(PREFIX):].hex()

    def test_p1_assembly_matches_spec_rules(self):
        data = bytes(range(256)) * 2 + b"tail" * 22  # 600 B
        frames = fragment(data, b"ABCDEFGH")
        # Odwrócona kolejność, potem duplikat pierwszej ramki po złożeniu: spóźniony duplikat.
        script = [f"P {i} {self.air(f)}" for i, f in enumerate(reversed(frames))] + [f"P 10 {self.air(frames[0])}", "S"]
        out = self.assemble(script)
        self.assertEqual(out[:6], ["stored"] * 6)
        self.assertEqual(out[6], f"complete 600 {data.hex().upper()}")
        self.assertEqual(out[7:], ["late", "stats 7 1 0 0 1 0 0"])
        # Poprawny duplikat w trakcie składania, potem sprzeczny duplikat usuwa próbę.
        altered = bytearray(frames[0][len(PREFIX):-2])
        altered[-1] ^= 1
        altered_hex = (bytes(altered) + crc16(bytes(altered)).to_bytes(2, "big")).hex()
        out = self.assemble([f"P 0 {self.air(frames[0])}", f"P 1 {self.air(frames[0])}", f"P 2 {altered_hex}", "A",
                             f"P 3 {self.air(frames[0])}", "A", "S"])
        self.assertEqual(out, ["stored", "duplicate", "conflict", "active 0", "stored", "active 1", "stats 2 0 1 1 0 0 0"])
        # Ten sam identyfikator z inną długością datagramu usuwa próbę.
        other = fragment(b"x" * 100, b"ABCDEFGH")
        out = self.assemble([f"P 0 {self.air(frames[1])}", f"P 1 {self.air(other[0])}", "A", "S"])
        self.assertEqual(out, ["stored", "conflict", "active 0", "stats 1 0 0 1 0 0 0"])
        # Uszkodzone CRC i stare znaczenie LEN są odrzucane przy rozbiorze.
        corrupt = bytearray(frames[0][len(PREFIX):])
        corrupt[20] ^= 1
        old_len = bytearray(frames[0][len(PREFIX):-2])
        old_len[0] -= 2
        old_len_hex = (bytes(old_len) + crc16(bytes(old_len)).to_bytes(2, "big")).hex()
        out = self.assemble([f"P 0 {bytes(corrupt).hex()}", f"P 0 {old_len_hex}"])
        self.assertEqual(out, ["parse crc", "parse length"])

    def test_p1_assembly_overflow_and_expiry(self):
        starts = []
        for n in range(9):
            frames = fragment(bytes([n]) * 100, bytes([n]) * 8)  # dwa fragmenty, nadany tylko pierwszy
            starts.append((frames[0], frames[1]))
        script = [f"P {n * 10} {self.air(first)}" for n, (first, _) in enumerate(starts)] + ["A", "S",
                  f"P 100 {self.air(starts[0][1])}", "A", f"P 101 {self.air(starts[8][1])}", "S"]
        out = self.assemble(script)
        # Dziewiąta próba wypiera najstarszą z ośmiu równych; jej drugi fragment zaczyna nową próbę,
        # a dziewiąty datagram kończy się poprawnie.
        self.assertEqual(out[:9], ["stored"] * 9)
        self.assertEqual(out[9:12], ["active 8", "stats 9 0 0 0 0 1 0", "stored"])
        self.assertEqual(out[12], "active 8")
        self.assertTrue(out[13].startswith("complete 100 "))
        self.assertEqual(out[14], "stats 11 1 0 0 0 2 0")
        frames = fragment(b"z" * 200, b"EXPIRE01")
        out = self.assemble([f"P 0 {self.air(frames[0])}", "X 119999", "A", "X 120000", "A", "S"])
        self.assertEqual(out, ["stored", "expired", "active 1", "expired", "active 0", "stats 1 0 0 0 0 0 1"])

    # --- dziennik FRAM --------------------------------------------------------

    def test_journal_clock_reservation_format_and_erase(self):
        lines = subprocess.run([str(self.binary), "journal"], capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertEqual(lines, [
            "fresh 1 1 0 0 0 0",                 # pusta pamięć: BLANK
            "write 1 1",
            "reread 2 5000 20 2",
            "uncommitted 2 5000 2",              # rekord bez znacznika zatwierdzenia pominięty
            "corrupt 1 16228 1",                 # rekord z błędnym CRC pominięty
            "ring 41 139 32",                    # 32 gniazda, najnowszy numer 41
            "start 1 60 60 1",                   # start: licznik +60 s, S +60 s, liczba startów 1
            "clock 1 0 500 60 1",                # zapis co 60 s; licznik się nie cofa
            "restart 1 560 120 2",               # po restarcie czas nie cofa się wobec czasu sprzed restartu
            "settings 1 3 5 reserve 1 1 0",      # rezerwacja tylko rosnąca
            "format 1 1 2 1 4294968320 3 5",     # READY, wersja 2, znacznik tożsamości
            "destroying 1 2 0",
            "events 600 1 e600 1 e89 0",
            "long 53",
            "erase 1 0 0 0 139 4294968320 2 2",  # dług, rezerwacja i format zostają
            "format_corrupt 3",                  # zatwierdzone z błędnym CRC bez poprawnych: CORRUPT
        ])

    # --- SHA-256, HMAC, DRBG --------------------------------------------------

    def test_sha256_hmac_and_destination_hash_match_python(self):
        for length in (0, 1, 55, 56, 63, 64, 65, 200, 1000):
            data = bytes((i * 7 + 3) % 256 for i in range(length))
            digest, parts = self.run_harness("sha", "digest", data.hex())
            self.assertEqual((digest, parts), (hashlib.sha256(data).hexdigest(), "1"), length)
        for key in (b"", b"k", bytes(range(32)), bytes(range(64)), bytes(range(100))):
            for data in (b"", b"WICI", bytes(range(130))):
                self.assertEqual(self.run_harness("sha", "hmac", key.hex(), data.hex()),
                                 [hmac.new(key, data, hashlib.sha256).hexdigest()], (len(key), len(data)))
        for key in (MAIN_KEY, BACKUP_KEY):
            for name in ("lxmf.delivery", "wici.sa1"):
                self.assertEqual(self.run_harness("sha", "dest", key.hex(), name), [destination(key, name).hex()])

    def test_drbg_matches_python_hmac_drbg(self):
        for entropy, nonce, lengths in ((bytes(range(48)), b"chip-0001", (32, 16, 100, 1)),
                                        (bytes(range(100, 132)), b"", (8, 65)),
                                        (b"\xff" * 48, bytes(8), (64, 64, 64))):
            out = subprocess.run([str(self.binary), "drbg", entropy.hex(), nonce.hex() or "", *map(str, lengths)],
                                 capture_output=True, text=True, check=True).stdout.splitlines()
            self.assertEqual(out[0], "ready 1 0")   # bez ziarna generator nie daje bajtów
            self.assertEqual(out[1:], ["1 " + x.hex() for x in hmac_drbg(entropy, nonce, lengths)])
        # Ziarno krótsze niż 32 B nie uruchamia generatora.
        out = subprocess.run([str(self.binary), "drbg", "00" * 31, "", "4"], capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertEqual(out, ["ready 0 0", "0 00000000"])

    # --- dokument configure ---------------------------------------------------

    def parse(self, doc, profile="p1"):
        text = doc if isinstance(doc, str) else json.dumps(doc, ensure_ascii=False)
        return subprocess.run([str(self.binary), "cfgparse", profile], input=text, capture_output=True, text=True,
                              check=True).stdout.splitlines()

    def test_config_document_parse_and_rejections(self):
        phrases = [["osoba na wózku", "людина на візку", "wheelchair user"], ["brak wody", "", ""]]
        doc = station_doc(addresses=["Szkoła A", "ś" * 32], phrases=phrases, stations=7)
        out = self.parse(doc)
        worst = max(check_button_configuration(a, tuple(p[0] for p in phrases)) for a in doc["addresses"])
        # Odczyt kawałkami: pole albo element listy najwyżej 640 B w RAM (karta odbiorcy ≈ 400 B).
        self.assertEqual(out[0].rsplit(" ", 1)[0], f"parse ok worst={worst}")
        self.assertLessEqual(int(out[0].rsplit("=", 1)[1]), 640)
        self.assertEqual(out[1:], [
            "conf role=0 stations=7 profile=p1", "conf address Szkoła A", "conf address " + "ś" * 32,
            "conf phrase osoba na wózku|людина на візку|wheelchair user", "conf phrase brak wody||", "conf ifac " + "11" * 16,
            f"conf receiver 0 {destination(MAIN_KEY, 'lxmf.delivery').hex()} {MAIN_SA1} {MAIN_KEY.hex()}",
            f"conf receiver 1 {destination(BACKUP_KEY, 'lxmf.delivery').hex()} {BACKUP_SA1} {BACKUP_KEY.hex()}"])
        # Największe zgłoszenie z przycisków przy najdłuższym adresie i frazie (64 B i 96 B) to 220 B: limit 256 B
        # SA1 nie daje się przekroczyć, bo limity tekstów odrzucają dłuższe pola wcześniej ("addresses", "phrases").
        longest = station_doc(addresses=["a" * 64], phrases=[["b" * 96, "", ""]])
        self.assertTrue(self.parse(longest)[0].startswith(f"parse ok worst={check_button_configuration('a' * 64, ('b' * 96,))} "))
        self.assertEqual(check_button_configuration("a" * 64, ("b" * 96,)), 220)
        node = self.parse(node_doc())
        self.assertEqual(node[1:], ["conf role=1 stations=0 profile=p1", "conf ifac " + "22" * 16])
        wrong_lxmf = station_doc()
        wrong_lxmf["receiver"]["backup"]["lxmf"] = destination(MAIN_KEY, "lxmf.delivery").hex()   # adres innego klucza
        same = station_doc()
        same["receiver"]["backup"] = card(MAIN_KEY)   # główna i zapasowa to ta sama tożsamość
        cases = [
            (station_doc(colour="red"), "colour"),                       # pole nieznane: jego nazwa
            (station_doc(addresses=["a\\\\b"]), "addresses"),             # ukośnik wsteczny w dokumencie
            (wrong_lxmf, "receiver"), (same, "receiver"),
            (station_doc(profile="p2"), "radio"),                        # profil spoza układu radiowego
            (station_doc(addresses=[]), "addresses"), (station_doc(addresses=["a"] * 9), "addresses"),
            (station_doc(addresses=["a" * 65]), "addresses"), (station_doc(addresses=['a"b']), "addresses"),
            (station_doc(phrases=[["ł" * 49, "", ""]]), "phrases"), (station_doc(phrases=[["", "", ""]]), "phrases"),
            (station_doc(phrases=[["a", "b"]]), "phrases"), (station_doc(stations=0), "stations"),
            (station_doc(stations=1001), "stations"), (dict(node_doc(), stations=3), "stations"),
            ({"role": "osp", "ifac": "00" * 16, "radio": {"profile": "p1"}}, "role"),
            ({"role": "wezel", "radio": {"profile": "p1"}}, "ifac"), ("[1,2]", "json"), ("", "json"),
        ]
        for value, detail in cases:
            self.assertEqual(self.parse(value), [f"parse err {detail}"], value)
        self.assertEqual(self.parse(station_doc(), profile="p2"), ["parse err radio"])

    # --- stacja: magazyn, warstwa aplikacji, USB, ekran ------------------------

    def world(self, script):
        result = subprocess.run([str(self.binary), "world"], input="\n".join(script) + "\n", capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr)
        return result.stdout.splitlines()

    @staticmethod
    def records(out, prefix, label):
        """Rows "<prefix> <label> key=value ..." as dicts (values as int where possible)."""
        rows = []
        for line in out:
            parts = line.split(" ")
            if len(parts) < 2 or parts[0] != prefix or parts[1] != label:
                continue
            row = {}
            for part in parts[2:]:
                key, _, value = part.partition("=")
                row[key] = int(value) if value.lstrip("-").isdigit() and key not in ("num", "id") else value
            rows.append(row)
        return rows

    def regs(self, out, label):
        return {r["id"]: r for r in self.records(out, "reg", label)}

    def stats(self, out, label):
        return self.records(out, "stats", label)[0]

    @staticmethod
    def find(out, prefix):
        return [line for line in out if line.startswith(prefix)]

    CONFIG = "cfg " + json.dumps(station_doc(phrases=[["osoba na wózku", "людина на візку", "wheelchair user"]]), ensure_ascii=False)

    @staticmethod
    def rid(n):
        """Request id with short number n (first 16 bits) and distinct tail."""
        return "%04x" % n + "%028x" % (n * 7919 + 1)

    @staticmethod
    def request(rid, revision=0, people=1, urgency=0, text="", category=2, location="Szkoła"):
        return [1, 0, rid, revision, category, people, location, text, urgency]

    def sub(self, value):
        return "sub " + compact(value)

    def test_store_transactions_restart_and_torn_writes(self):
        register = 0x10000   # store::REGISTER_BASE, gniazda po 512 B
        out = self.world([
            "wipe", "diag", "restart", "diag",
            "now 5", "txreq 0 11 0 1", "txreq 1 22 0 1", "txreq 0 11 1 0", "reg a",
            "restart", "reg b", "diag",
            # Zanik zasilania przed znacznikiem COMMIT (nagłówek 24 B i część rekordu): gniazdo zachowuje poprzednią treść.
            "tear 300", "txreq 0 11 2 0", "restart", "reg c", "diag",
            # Zanik po COMMIT (24 + 520 + 8 B), przed przepisaniem do gniazda: transakcja wykonana ponownie przy starcie.
            "tear 552", "txreq 0 11 3 0", "diag", "tear -1", "restart", "reg d", "diag",
            # Uszkodzony rekord gniazda i śmieci w pustym gnieździe: wyłączone z użycia, nigdy wolne.
            f"flip {register + 40}", f"poke {register + 3 * 512 + 100} 90", "restart", "slot 0", "slot 1", "slot 2", "slot 3",
            "reg e", "diag",
        ])
        self.assertEqual(self.find(out, "begin "), ["begin new"] + ["begin ok"] * 5)   # pusta FRAM: nowa stacja
        diags = self.find(out, "diag ")
        self.assertIn("ok=1", diags[0])
        self.assertIn("head=0 min=1 requests=0", diags[1])
        first = self.records(out, "reg", "a")
        self.assertEqual([(r["slot"], r["rmax"], r["gen"]) for r in first], [(0, 1, 1), (1, 0, 1)])
        self.assertEqual(self.records(out, "reg", "b"), first)   # indeks odtworzony z FRAM po restarcie
        self.assertEqual(self.find(out, "txreq "), ["txreq 1 1"] * 3 + ["txreq 0 1", "txreq 0 0"])
        self.assertEqual([r["rmax"] for r in self.records(out, "reg", "c")], [1, 0])   # zapis bez COMMIT odrzucony
        self.assertIn("replayed=0", diags[3])
        self.assertIn("ok=0", diags[4])                                                 # magazyn stoi do restartu
        self.assertEqual([r["rmax"] for r in self.records(out, "reg", "d")], [3, 0])   # zatwierdzona: wykonana ponownie
        self.assertIn("replayed=1", diags[5])
        # Uszkodzone gniazda: stan CORRUPT (2), liczone w diagnostyce; pierwsze wolne gniazdo to 2.
        self.assertEqual(self.find(out, "slot "), ["slot 0 state=2", "slot 1 state=1", "slot 2 state=0", "slot 3 state=2"])
        self.assertEqual([r["slot"] for r in self.records(out, "reg", "e")], [1])
        self.assertIn("corrupt=2", diags[6])
        self.assertIn("free=2", diags[6])

    def test_store_corrupt_ring_block_is_rewritten(self):
        # Blok pierścienia z błędnym znacznikiem (policzony przy starcie) nie blokuje transakcji ze zdarzeniem.
        ring = 0x42000   # store::RING_BASE
        out = self.world([self.CONFIG, self.sub(self.request(self.rid(41))), "diag", "flip %d" % (ring + 40), "restart", "diag",
                          self.sub(self.request(self.rid(42))), "maintain", "restart", "diag"])
        self.assertEqual(self.find(out, "sub ")[1].split()[1], "stored")
        diags = [dict(f.split("=", 1) for f in line.split()[1:] if "=" in f) for line in self.find(out, "diag ")]
        self.assertEqual([d["corrupt"] for d in diags], ["0", "1", "0"])   # maintain zapisał blok od nowa
        # Nowa epoka pierścienia (laptop robi migawkę), numeracja dalej za uszkodzonym blokiem; rejestr zostaje.
        self.assertNotEqual(diags[0]["epoch"], diags[1]["epoch"])
        self.assertEqual(diags[1]["epoch"], diags[2]["epoch"])
        self.assertEqual((diags[0]["head"], diags[1]["head"], diags[1]["min"], diags[2]["head"]), ("2", "16", "17", "17"))
        self.assertEqual([d["requests"] for d in diags], ["1", "1", "2"])
        # Dwa uszkodzone bloki na końcu pierścienia (zdarzenia 33-64): numeracja za najwyższym możliwym
        # numerem (32 + 2 × 16), więc nowa wiadomość nie dostaje numeru `msg` zachowanej wiadomości 49.
        out = self.world([self.CONFIG, "sevents 47", "in " + compact([1, 4, self.rid(78), 7, "Komunikat"]), "sevents 15", "diag",
                          "flip %d" % (ring + 2 * 512 + 40), "flip %d" % (ring + 3 * 512 + 40), "restart", "diag",
                          "in " + compact([1, 4, self.rid(79), 8, "Komunikat 2"]), "inbox a"])
        diags = [dict(f.split("=", 1) for f in line.split()[1:] if "=" in f) for line in self.find(out, "diag ")]
        self.assertEqual((diags[0]["head"], diags[1]["head"], diags[1]["corrupt"]), ("64", "64", "2"))
        self.assertEqual(sorted(int(line.split("msg=")[1].split()[0]) for line in self.find(out, "msg a ")), [49, 65])
        # Uszkodzony blok zbioru BULLETIN: `bulletin_floor` = najwyższy przyjęty event, komunikat nie wraca.
        bulletin = 0xF200   # store::BULLETIN_BASE
        b = self.rid(77)
        out = self.world([self.CONFIG, "in " + compact([1, 4, b, 7, "Komunikat"]), "flip %d" % (bulletin + 40), "restart",
                          "in " + compact([1, 4, b, 7, "Komunikat"]), "in " + compact([1, 4, b, 8, "Komunikat 2"]), "diag"])
        self.assertIn("messages=2", self.find(out, "diag ")[0])

    def test_store_event_ring_close_maintain_and_destroy(self):
        out = self.world([
            "sevents 300", "ev 44", "ev 45", "ev 300", "diag", "restart", "ev 45", "ev 300", "diag",
            "txreq 0 11 0 1", "txreq 5 22 0 1", "close", "slot 0", "slot 5", "diag", "restart", "slot 0", "slot 5", "diag",
            "maintain", "slot 0", "slot 5", "diag", "restart", "slot 0", "diag",
            "ident", "txreq 3 33 0 1", "destroy", "diag", "restart", "diag",
            # ZNISZCZ DANE przerwane zanikiem zasilania: dokończone przy starcie, nowa pamięć.
            "txreq 3 33 0 1", "destroying", "restart", "diag",
            # Zdarzenie `radio`: przełącznik ma pierwszeństwo i wyklucza wyjątek ciszy z panelu.
            "silence 1 " + "11" * 16, "ev 1", "radioev 1", "ev 2", "radioev 0", "ev 3",
        ])
        self.assertEqual(self.find(out, "sevents"), ["sevents 300"])
        evs = self.find(out, "ev ")
        self.assertEqual(evs[0].split()[:2], ["ev", "0"])           # nadpisane: najstarsze w pierścieniu to 45
        self.assertEqual(evs[1], "ev 1 45 kind=6 a=3 value=44")
        self.assertEqual(evs[2], "ev 1 300 kind=6 a=3 value=299")
        self.assertEqual(evs[3:5], evs[1:3])
        diags = self.find(out, "diag ")
        self.assertIn("head=300 min=45", diags[0])
        self.assertIn("head=300 min=45", diags[1])
        epoch = diags[1].split("epoch=")[1]
        # ZAMKNIJ ZDARZENIE: nowa epoka, wpisy starej epoki STALE (3) i wolne do użycia, pierścień od zera.
        self.assertEqual(self.find(out, "close "), ["close 1"])
        slots = self.find(out, "slot ")
        self.assertEqual(slots[:4], ["slot 0 state=3", "slot 5 state=3"] * 2)
        self.assertIn("head=0 min=1 requests=0", diags[2])
        self.assertNotEqual(diags[2].split("epoch=")[1], epoch)
        self.assertEqual(diags[3].split("epoch=")[1], diags[2].split("epoch=")[1])
        # maintain() nadpisuje gniazda starej epoki (2 wpisy + 16 bloków pierścienia) transakcjami po 3.
        self.assertEqual(self.find(out, "maintain "), ["maintain 6"])
        self.assertEqual(slots[4:], ["slot 0 state=0", "slot 5 state=0", "slot 0 state=0"])
        self.assertIn("scrubbed=18", diags[4])
        # ZNISZCZ DANE: pusty magazyn bez znacznika tożsamości, nowa epoka.
        self.assertEqual(self.find(out, "ident "), ["ident 1 1"])
        self.assertEqual(self.find(out, "destroy "), ["destroy 1"])
        self.assertIn("requests=0", diags[6])
        self.assertIn("ident=0", diags[6])
        self.assertEqual(self.find(out, "begin "), ["begin ok"] * 4 + ["begin new"])
        self.assertIn("requests=0", diags[8])
        self.assertEqual(self.find(out, "ev ")[-3:], ["ev 1 1 kind=4 a=5 value=4369", "ev 1 2 kind=4 a=3 value=0", "ev 1 3 kind=4 a=5 value=4369"])

    def test_store_config_copies_hash_invalid_and_restart(self):
        doc = json.dumps(station_doc(addresses=["Obiekt A", "Obiekt B"]), ensure_ascii=False)
        bad = json.dumps(station_doc(addresses=["x"], colour=1), ensure_ascii=False)
        out = self.world(["cfg " + doc, "addr", "cfgbad " + json.dumps(station_doc(addresses=["Inny"]), ensure_ascii=False), "addr",
                          "cfg " + bad, "addr", "staged 0 20", "restart", "addr", "cfgdump", "diag",
                          "cfg " + json.dumps(station_doc(addresses=["Trzeci"]), ensure_ascii=False), "restart", "addr"])
        cfgs = self.find(out, "cfg ")
        self.assertEqual(cfgs[0], "cfg 1 ok - worst=%d seq=1" % check_button_configuration("Obiekt A", ()))
        self.assertEqual(cfgs[1], "cfg 1 hash - worst=0 seq=1")       # SHA-256 dokumentu nie zgadza się
        self.assertEqual(cfgs[2], "cfg 1 invalid colour worst=0 seq=1")
        self.assertEqual(cfgs[3].split()[:2], ["cfg", "1"])
        self.assertTrue(cfgs[3].endswith("seq=2"))
        addresses = self.find(out, "addresses ")
        self.assertEqual(addresses[:4], ["addresses 2 selected 0 |Obiekt A |Obiekt B |location Obiekt A"] * 4)  # poprzednia zostaje
        self.assertEqual(addresses[4], "addresses 1 selected 0 |Trzeci |location Trzeci")
        self.assertEqual(self.find(out, "staged "), ["staged 1 " + bad[:20]])   # nieaktywna kopia w zapisie
        # Konfiguracja czytana kawałkami z kopii w FRAM po restarcie równa rozbiorowi dokumentu w RAM.
        self.assertEqual(self.find(out, "conf "), [x for x in self.parse(doc) if x.startswith("conf ")])
        self.assertIn("cfgcorrupt=0", self.find(out, "diag ")[0])

    def lifecycle(self, messages, setup=None):
        """Request X with r_max = 1 and r_rcv = -1, then messages from the active receiver identity."""
        x = self.rid(1234)
        script = [self.CONFIG, self.sub(self.request(x)), self.sub(self.request(x, 1, people=2))]
        script += setup or []
        for m in messages:
            script.append(m if isinstance(m, str) else "in " + compact(m))
        script += ["reg end", "inbox end", "stats end"]
        out = self.world(script)
        return out, self.regs(out, "end")[x], self.stats(out, "end")

    def test_station_lifecycle_vectors(self):
        x = self.rid(1234)
        # RECEIVED(X,0), RECEIVED(X,1): r_rcv = 1, etap odebrane.
        _, r, s = self.lifecycle([[1, 1, x, 0, 1, 1], [1, 1, x, 1, 1, 1]])
        self.assertEqual((r["rrcv"], r["stage"], r["dec"]), (1, 3, 0))
        # STATUS(X,0,e=10,s=3), RECEIVED(X,1): decyzja 3, etap odebrane.
        _, r, s = self.lifecycle([[1, 2, x, 0, 10, 3], [1, 1, x, 1, 1, 1]])
        self.assertEqual((r["dec"], r["drev"], r["stage"], r["shi"]), (3, 0, 3, 10))
        # STATUS(X,1,e=10,s=2), STATUS(X,0,e=9,s=3): drugi pominięty; decyzja 2.
        _, r, s = self.lifecycle([[1, 2, x, 1, 10, 2], [1, 2, x, 0, 9, 3]])
        self.assertEqual((r["dec"], r["drev"], r["stage"], s["skipped"], s["received"]), (2, 1, 3, 1, 2))
        # STATUS(X,1,e=10,s=6) dwa razy: drugi pominięty jako powtórzenie; wpis zamknięty (decyzja 6 z r_max).
        _, r, s = self.lifecycle([[1, 2, x, 1, 10, 6], [1, 2, x, 1, 10, 6]])
        self.assertEqual((r["dec"], s["skipped"], r["closed"]), (6, 1, 1))
        # RECEIVED(X,2): pominięty (r > r_max).
        out, r, s = self.lifecycle([[1, 1, x, 2, 1, 1]])
        self.assertEqual((r["rrcv"], r["stage"], s["skipped"]), (-1, 0, 1))
        self.assertEqual(self.find(out, "rx "), ["rx 1 0"])   # rozstrzygnięty: dowód
        # REPLY(X,1,e=5), STATUS(X,1,e=4,s=5): oba przyjęte (osobne liczniki); decyzja 5, odpowiedź w skrzynce.
        out, r, s = self.lifecycle([[1, 3, x, 1, 5, "Zadzwoń pod 112"], [1, 2, x, 1, 4, 5]])
        self.assertEqual((r["dec"], r["rhi"], r["shi"], s["skipped"]), (5, 5, 4, 0))
        inbox = self.records(out, "msg", "end")
        self.assertEqual([(m["type"], m["event"], m["read"]) for m in inbox], [(3, 5, 0)])
        # STATUS(X,0,e=10,s=6), potem nowa rewizja 2: decyzja 6 zostaje, etap zapisane, wpis nie jest zamknięty.
        _, r, s = self.lifecycle([[1, 2, x, 0, 10, 6], self.sub(self.request(x, 2, people=3))])
        self.assertEqual((r["dec"], r["drev"], r["stage"], r["rmax"], r["closed"]), (6, 0, 0, 2, 0))
        # X nadany (`nadane`), dowód i RECEIVED utracone, ANULUJ: too_late; późny RECEIVED(X,1) daje odebrane.
        out, r, s = self.lifecycle(["poll", "rcpt 1 0", "cancel " + x, [1, 1, x, 1, 1, 1]])
        self.assertEqual(self.find(out, "cancel "), ["cancel too_late 0"])
        self.assertEqual((r["stage"], r["flags"] & 1), (3, 1))
        # STATUS(Y,0,e=3,s=3) dla Y spoza rejestru: pominięty.
        out, r, s = self.lifecycle([[1, 2, self.rid(4321), 0, 3, 3]])
        self.assertEqual((s["skipped"], r["dec"]), (1, 0))
        # BULLETIN(B,e=100) dwa razy: drugi pominięty; BULLETIN(B1,e=200 000), BULLETIN(B2,e=100 000): drugi
        # pominięty (starszy o ponad dobę).
        b1, b2 = self.rid(7001), self.rid(7002)
        out, r, s = self.lifecycle([[1, 4, b1, 100, "Woda o 10"], [1, 4, b1, 100, "Woda o 10"], [1, 4, b1, 200000, "Prąd"],
                                    [1, 4, b2, 100000, "Stary"], [1, 4, b2, 113601, "Nowy"]])
        self.assertEqual(s["bulletins"], 2)
        self.assertEqual([m["event"] for m in self.records(out, "msg", "end")], [100, 200000, 113601])

    def test_station_messages_only_from_active_receiver(self):
        x = self.rid(1234)
        received = compact([1, 1, x, 1, 1, 1])
        out = self.world([self.CONFIG, self.sub(self.request(x)), self.sub(self.request(x, 1)),
                          f"infrom {BACKUP_SA1} {received}", f"infrom {'cd' * 16} {received}", "inraw nonsense",
                          "in " + compact([1, 0, x, 0, 2, 1, "a", "", 0]),   # REQUEST od odbiorcy: zły typ
                          "reg a", "stats a", "backup", f"infrom {MAIN_SA1} {received}", f"infrom {BACKUP_SA1} {received}",
                          "reg b", "stats b"])
        # Obca tożsamość, nieaktywna zapasowa, zły format i zły typ: trwałe odrzucenie z dowodem.
        self.assertEqual(self.find(out, "rx "), ["rx 1 0"] * 6)
        self.assertEqual((self.stats(out, "a")["rejected"], self.regs(out, "a")[x]["stage"]), (4, 0))
        # Po KLUCZ ZAPASOWY tylko zapasowa tożsamość jest aktywna.
        self.assertEqual((self.stats(out, "b")["rejected"], self.regs(out, "b")[x]["stage"]), (5, 3))

    def test_station_register_full_release_and_inbox_full(self):
        z = self.rid(1)
        script = [self.CONFIG, "silence 1", self.sub(self.request(z)), "poll", "cancel " + z]
        script += [self.sub(self.request(self.rid(100 + i))) for i in range(255)]
        script += ["diag", self.sub(self.request(self.rid(400))), "diag", "cancel " + z, self.sub(self.request(z, 0)),
                   self.sub(self.request(self.rid(401)))]
        # X zamknięty (decyzja 6 z r_max), nowe zgłoszenie zwalnia go; późny STATUS pominięty.
        x = self.rid(100)
        script += ["in " + compact([1, 2, x, 0, 10, 6]), self.sub(self.request(self.rid(402))), "in " + compact([1, 2, x, 0, 11, 2]),
                   "stats a", self.sub(self.request(self.rid(403))), self.sub(self.request(x, 0)), self.sub(self.request(x, 1))]
        out = self.world(script)
        subs = self.find(out, "sub ")
        self.assertEqual(subs[:256], ["sub stored 0 0 %04d" % n for n in [1] + list(range(100, 355))])
        diags = self.find(out, "diag ")
        self.assertIn("requests=256", diags[0])
        self.assertIn("free=-1", diags[0])
        # Z (anulowany w ciszy, nigdy nie nadany) zwolniony; ANULUJ i ponowny submit tej rewizji: z pamięci zwolnionych.
        self.assertEqual(subs[256], "sub stored 0 0 0400")
        self.assertEqual(self.find(out, "cancel "), ["cancel stored 0", "cancel stored 1"])
        self.assertEqual(subs[257], "sub duplicate 1 1 0001")
        self.assertEqual(subs[258], "sub full 0 0 0401")   # brak wpisu zamkniętego: kolejka_pelna
        self.assertEqual(subs[259], "sub stored 0 0 0402")
        self.assertEqual(self.stats(out, "a")["skipped"], 1)
        self.assertEqual(subs[260:], ["sub full 0 0 0403", "sub duplicate 1 1 0100", "sub closed 0 0 0100"])
        # Skrzynka pełna REPLY otwartego zgłoszenia (bez dowodu, odbiorca ponowi).
        y = self.rid(500)
        script = [self.CONFIG, self.sub(self.request(y))]
        script += ["in " + compact([1, 3, y, 0, e, "odp %d" % e]) for e in range(1, 130)]
        script += ["stats b"]
        out = self.world(script)
        self.assertEqual(self.find(out, "rx "), ["rx 1 0"] * 128 + ["rx 0 0"])
        self.assertEqual((self.stats(out, "b")["full"], self.stats(out, "b")["evicted"]), (1, 0))

    def test_station_retry_schedule(self):
        out = self.world([f"retry {a} 0 0 {r}" for r in (0, 40) for a in range(0, 6)] +
                         [f"retry 1 0 {6 * 3600} {r}" for r in (0, 40)] + [f"retry 2 1 0 {r}" for r in (0, 1800, 1801)])
        values = [int(x.split()[1]) for x in self.find(out, "retry ")]
        # Po FAILED 1, 2, 5, 15 min ±20% (0,8 i 1,2), po 6 h co 60 min ±20%; po DELIVERED 30–60 min.
        self.assertEqual(values, [48, 48, 96, 240, 720, 720, 72, 72, 144, 360, 1080, 1080, 2880, 4320, 1800, 3600, 1800])
        x = self.rid(1234)
        out = self.world([self.CONFIG, "now 100", self.sub(self.request(x)), "poll", "reg a", "now 160", "rcpt 1 0", "reg b",
                          "now 400", "poll", "now 401", "rcpt 2 1", "reg c", "now 1001", "poll", "rcpt 3 1", "reg d", "stats e"])
        a, b, c, d = (self.regs(out, label)[x] for label in "abcd")
        self.assertEqual((a["stage"], a["att"], a["next"], a["flags"]), (1, 1, 160, 1))   # limit potwierdzenia 60 s
        self.assertTrue(160 + 48 <= b["next"] <= 160 + 72, b)                             # FAILED: 60 s ±20%
        self.assertEqual((c["stage"], c["att"], c["next"]), (2, 2, 401 + 600))            # DELIVERED: 10 min na RECEIVED
        self.assertEqual((d["stage"], d["att"]), (2, 3))
        self.assertTrue(1001 + 1800 <= d["next"] <= 1001 + 3600, d)                       # potem co 30–60 min
        self.assertEqual(self.find(out, "send ")[0].split()[2], MAIN_SA1)                 # do celu "wici.sa1" odbiorcy
        self.assertEqual(self.find(out, "send ")[0].split(" ", 3)[3],
                         '["WICI",1,"%s","%s",%s]' % (SELF, MAIN_SA1, compact(self.request(x))))
        self.assertEqual(self.find(out, "stats e")[0], "stats e sent=3 delivered=2 failed=1 received=0 rejected=0 skipped=0 bulletins=0 "
                                                      "full=0 evicted=0")

    def test_station_queue_order_in_flight_and_silence(self):
        ids = [self.rid(n) for n in (11, 12, 13, 14)]
        test = [1, 5, ids[0], 0, 9, 1, "Szkoła", "test", 0]
        script = [self.CONFIG, "now 10", self.sub(test), "now 20", self.sub(self.request(ids[1], urgency=0)), "now 30",
                  self.sub(self.request(ids[2], urgency=1)), "now 40", self.sub(self.request(ids[3], urgency=2)),
                  "poll", "poll", "rcpt 1 1", "poll", "rcpt 2 1", "rcpt 3 1", "poll"]
        out = self.world(script)
        sent = [line.split()[3] for line in self.find(out, "send ")]
        order = [json.loads(p)[4][2] for p in sent]
        # Pilność 2 pierwsza, potem REQUEST według COMMIT, TEST na końcu; najwyżej 2 w drodze.
        self.assertEqual(order, [ids[3], ids[1], ids[2], ids[0]])
        self.assertEqual(self.find(out, "inflight "), ["inflight 2", "inflight 2", "inflight 2", "inflight 1"])
        # Cisza z panelu wstrzymuje wysyłkę; wyjątek przepuszcza jedno zgłoszenie, ale nie przy przełączniku.
        a, b = self.rid(21), self.rid(22)
        out = self.world([self.CONFIG, self.sub(self.request(a)), self.sub(self.request(b)), "silence 1", "poll", "switch 1",
                          "silence 1 " + b, "poll", "switch 0", "poll", "in " + compact([1, 1, b, 0, 1, 1]),
                          "in " + compact([1, 2, self.rid(99), 0, 3, 3]), "silence 0", "poll"])
        sends = [json.loads(line.split()[3])[4][2] for line in self.find(out, "send ")]
        self.assertEqual(sends, [b, a])
        self.assertEqual(self.find(out, "inflight "), ["inflight 0", "inflight 0", "inflight 1", "inflight 2"])
        self.assertEqual(self.find(out, "rx "), ["rx 1 1", "rx 1 0"])   # ruch zgłoszenia z wyjątkiem (dowód w ciszy)
        # Wyjątek obejmuje parę (id, revision) i dowody RECEIVED i STATUS: REPLY bez dowodu w ciszy,
        # nowa rewizja tego id czeka jak każda inna wiadomość.
        out = self.world([self.CONFIG, self.sub(self.request(b)), "silence 1 " + b, "in " + compact([1, 1, b, 0, 1, 1]),
                          "in " + compact([1, 2, b, 0, 2, 3]), "in " + compact([1, 3, b, 0, 3, "Czekajcie"]),
                          self.sub(self.request(b, 1)), "poll"])
        self.assertEqual(self.find(out, "rx "), ["rx 1 1", "rx 1 1", "rx 1 0"])
        self.assertEqual(self.find(out, "send "), [])
        # Cisza z panelu (z wyjątkiem) jest w rekordzie meta: przetrwa restart i dalej wstrzymuje wysyłkę.
        out = self.world([self.CONFIG, self.sub(self.request(a)), self.sub(self.request(b)), "silence 1 " + b, "restart", "diag", "poll"])
        self.assertIn("silence=1", self.find(out, "diag ")[0])
        self.assertEqual([json.loads(line.split()[3])[4][2] for line in self.find(out, "send ")], [b])

    def test_station_backup_switch_retargets(self):
        x = self.rid(1234)
        out = self.world([self.CONFIG, "now 100", self.sub(self.request(x)), "poll", "rcpt 1 1", "in " + compact([1, 2, x, 0, 7, 2]),
                          "reg a", "now 101", self.sub(self.request(x, 1)), "poll", "rcpt 2 1", "now 102", "backup", "poll",
                          "reg b", "backup", "diag"])
        sends = self.find(out, "send ")
        self.assertEqual([s.split()[2] for s in sends], [MAIN_SA1, MAIN_SA1, BACKUP_SA1])   # od razu do zapasowej
        b = self.regs(out, "b")[x]
        self.assertEqual((b["flags"] & 4, b["shi"], b["dec"]), (4, 0, 2))   # liczniki od zera, decyzja zostaje
        self.assertEqual(self.find(out, "backup "), ["backup 1", "backup 0"])   # nieodwracalne
        self.assertIn("receiver=1", self.find(out, "diag ")[0])

    def test_station_alarms_and_tests(self):
        x, y = self.rid(31), self.rid(32)
        out = self.world([self.CONFIG, "now 1000", self.sub(self.request(x, urgency=2)), "now 1899", "alarm", "now 1900", "alarm",
                          "ackalarm", "alarm", "in " + compact([1, 1, x, 0, 1, 1]), "now 3699", "alarm", "now 3700", "alarm",
                          "in " + compact([1, 2, x, 0, 3, 3]), "alarm", "now 5000", self.sub(self.request(y, urgency=1)),
                          "now 8599", "alarm", "now 8600", "alarm"])
        self.assertEqual(self.find(out, "alarm "), [
            "alarm none cause=0", "alarm 1 0031 15 cause=1",      # pilność 2: 15 min bez RECEIVED
            "alarm none cause=1",                                 # potwierdzony OK; przyczyna trwa
            "alarm none cause=0", "alarm 2 0031 30 cause=1",      # brak_odczytu: 30 min po RECEIVED bez STATUS r_max
            "alarm none cause=0", "alarm none cause=0", "alarm 1 0032 60 cause=1"])   # pilność 1: 60 min
        out = self.world([self.CONFIG, "now 100", self.sub(self.request(x, urgency=0)), "now 21699", "alarm", "now 21700", "alarm"])
        self.assertEqual(self.find(out, "alarm "), ["alarm none cause=0", "alarm 1 0031 360 cause=1"])   # pilność 0: 6 h
        # TEST: z menu od razu, startowy w oknie 50 s x liczba stacji; WSTRZYMAJ anuluje czekający TEST.
        out = self.world([self.CONFIG, "now 100", "stest 1", "reg a", "stest 1", "pause 1", "reg b", "stest 0", "pause 0",
                          "stest 0", "reg c", "poll", "now 1899", "alarm", "now 1900", "alarm", "test 0102030405060708",
                          "test 0102030405060708", "reg d"])
        a = list(self.regs(out, "a").values())
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]["type"], 5)
        self.assertTrue(100 <= a[0]["next"] < 100 + 50 * 2, a)
        self.assertEqual(self.find(out, "stest "), ["stest stored", "stest stored", "stest invalid", "stest stored"])
        self.assertEqual([r["stage"] for r in self.regs(out, "b").values()], [4])
        self.assertEqual(self.find(out, "pause "), ["pause 1 1", "pause 1 0"])
        self.assertEqual(sorted(r["stage"] for r in self.regs(out, "c").values()), [0, 4])
        self.assertEqual(self.find(out, "alarm "), ["alarm none cause=0", "alarm 1 %s 30 cause=1" % [
            r["num"] for r in self.regs(out, "c").values() if r["stage"] == 0][0]])
        tests = self.find(out, "test ")
        self.assertEqual(tests[0], tests[1])   # powtórzone nonce: ten sam wynik
        self.assertEqual(len(self.regs(out, "d")), 3)

    # --- protokół USB "usb":2 --------------------------------------------------

    @staticmethod
    def replies(out):
        return [json.loads(line[3:]) for line in out if line.startswith("<- ")]

    class Lines:
        """USB lines with an increasing `seq`."""

        def __init__(self):
            self.seq = 0

        def __call__(self, type_, **fields):
            self.seq += 1
            return "usb " + json.dumps({"usb": 2, "seq": self.seq, "type": type_, **fields}, ensure_ascii=False)

    def usb_session(self, steps):
        """Run USB steps: a callable gets the line builder, "XFER" runs the script so far and takes the `xfer` id from
        the last `ok` (the harness generator is deterministic), ("PART", offset, data) and "COMMIT" use that id."""
        script, u = [], self.Lines()
        xfer = None
        for step in steps:
            if callable(step):
                step = step(u)
            if isinstance(step, tuple) and step[0] == "PART":
                script.append(u("xfer_part", xfer=xfer, offset=step[1], data=step[2]))
            elif step == "COMMIT":
                script.append(u("xfer_commit", xfer=xfer))
            elif step == "connect":
                u.seq = 0   # nowa sesja zaczyna `seq` od 1
                script.append(step)
            elif step == "XFER":
                xfer = [r for r in self.replies(self.world(script)) if r["type"] == "ok" and "xfer" in r][-1]["xfer"]
            else:
                script.append(step)
        return self.world(script), u

    def test_usb_hello_seq_fields_and_rejections(self):
        def line(seq, type_, usb=2, **fields):
            return "usb " + json.dumps({"usb": usb, "seq": seq, "type": type_, **fields})
        script = ["now 50", "connect", line(1, "status"), line(5, "status"), line(6, "status"), line(7, "status", colour=1),
                  line(8, "fly"), line(9, "cancel", id=5),
                  line(10, "status", usb=1),   # inna wersja kontraktu: odmowa i ponowne hello, numer nie przepada
                  "usb nonsense", "usb " + json.dumps({"usb": 2, "type": "status"}), "prep 0", line(10, "card"), "usbraw 1500",
                  line(11, "export"), "prep 1", line(12, "migrate"), line(13, "card")]
        r = self.replies(self.world(script))
        hello = r[0]
        self.assertEqual(hello["type"], "hello")
        self.assertEqual(set(hello), {"usb", "seq", "type", "boot", "contracts", "name", "lxmf", "fw", "role", "prep", "configured",
                                      "epoch", "head", "min", "migration"})
        self.assertEqual((hello["usb"], hello["seq"], hello["contracts"], hello["role"], hello["configured"], hello["lxmf"]),
                         (2, 1, [2], "stacja", False, ""))
        self.assertEqual((len(hello["boot"]), len(hello["epoch"]), hello["head"], hello["min"]), (16, 16, 0, 1))
        status = r[1]
        self.assertEqual((status["type"], status["re"], status["configured"], status["uptime"], status["register"],
                          status["receiver"], status["last_contact"], status["fram_format"]),
                         ("status", 1, False, 1050, 0, "main", None, 2))
        self.assertEqual((status["silence"], status["silence_source"], status["exception_id"], status["exception_revision"], status["power"]),
                         (False, None, None, None, {"source": "12v"}))
        rejected = [(x.get("re"), x["reason"], x.get("detail")) for x in r[2:] if x["type"] == "rejected"]
        self.assertEqual(rejected, [
            (5, "seq", None),                           # przeskok numeru; dalej od numeru laptopa
            (7, "invalid", "colour"), (8, "unknown_type", None), (9, "invalid", "id"), (10, "contract", None),
            (None, "invalid", "json"), (None, "seq", None), (10, "seq", None), (None, "too_long", None),
            (11, "unknown_type", None),                 # `export` to `op` transferu, nie polecenie
            (12, "migration", "unsupported"), (13, "not_configured", None)])
        self.assertEqual([x["type"] for x in r].count("hello"), 2)
        self.assertEqual([x["type"] for x in r][3], "status")   # po odmowie `seq` liczy się dalej od numeru laptopa
        self.assertEqual([x["seq"] for x in r], list(range(1, len(r) + 1)))

    def test_usb_configure_transfer_config_get_and_role(self):
        doc = station_doc(addresses=["Szkoła A", "Hala B"], phrases=[["osoba na wózku", "людина на візку", "wheelchair user"]])
        data = json.dumps(doc, ensure_ascii=False).encode()
        sha = hashlib.sha256(data).hexdigest()
        parts = [base64.b64encode(data[o:o + 300]).decode() for o in range(0, len(data), 300)]
        self.assertGreaterEqual(len(parts), 3)
        steps = ["connect", lambda u: u("xfer_begin", op="configure", size=len(data), sha256=sha), "XFER",
                 ("PART", 0, parts[0]), ("PART", 0, parts[0]),                      # powtórzona część z tą samą treścią
                 ("PART", 0, base64.b64encode(b"x" * 300).decode()),               # ta sama część z inną treścią
                 ("PART", 600, parts[2]),                                           # przeskok przesunięcia
                 lambda u: u("xfer_commit", xfer="00000000")]
        steps += [("PART", 300 * i, p) for i, p in enumerate(parts) if i] + ["COMMIT", lambda u: u("xfer_begin", op="config_get"),
                                                                              "XFER"]
        out, _ = self.usb_session(steps)
        get = self.replies(out)[-1]
        self.assertEqual((get["type"], get["size"], get["sha256"]), ("ok", len(data), sha))
        # Odczyt w częściach po 512 B (identyfikator transferu deterministyczny w programie testowym).
        reads = [lambda u, o=o: u("xfer_read", xfer=get["xfer"], offset=o, length=min(512, len(data) - o)) for o in range(0, len(data), 512)]
        out, _ = self.usb_session(steps + reads + [lambda u: u("xfer_read", xfer=get["xfer"], offset=0, length=513),
                                                   lambda u: u("xfer_commit", xfer=get["xfer"]), lambda u: u("status"),
                                                   "prep 0", lambda u: u("card"), "prep 1", lambda u: u("card"), "connect"])
        r = self.replies(out)
        kinds = [(x["type"], x.get("reason"), x.get("detail")) for x in r]
        self.assertEqual(kinds[:7], [("hello", None, None), ("ok", None, None), ("ok", None, None), ("ok", None, None),
                                     ("rejected", "invalid", "data"), ("rejected", "invalid", "offset"), ("rejected", "invalid", "xfer")])
        self.assertEqual((r[1]["max_part"], r[2]["next"], r[3]["next"]), (512, 300, 300))
        commit = [x for x in r if x["type"] == "ok" and "config_seq" in x][0]
        self.assertEqual((commit["config_seq"], commit["worst_request"]),
                         (1, max(check_button_configuration(a, ("osoba na wózku",)) for a in doc["addresses"])))
        self.assertIn("config changed 0", out)
        datas = [x for x in r if x["type"] == "data"]
        self.assertEqual(b"".join(base64.b64decode(x["data"]) for x in datas), data)   # config_get: ten sam dokument
        tail = r[-6:]
        self.assertEqual([(x["type"], x.get("reason")) for x in tail],
                         [("rejected", "size"), ("ok", None), ("status", None), ("rejected", "prep_required"), ("card", None), ("hello", None)])
        self.assertEqual((tail[2]["configured"], tail[2]["config_seq"], tail[2]["role"]), (True, 1, "stacja"))
        key = bytes(0x40 + i for i in range(64))
        fp = hashlib.sha256(key).hexdigest()[:16]
        self.assertEqual((tail[4]["key"], tail[4]["lxmf"], tail[4]["address"], tail[4]["fingerprint"]),
                         (key.hex(), destination(key, "lxmf.delivery").hex(), ["Szkoła A", "Hala B"],
                          " ".join(fp[i:i + 4] for i in range(0, 16, 4))))
        self.assertEqual((tail[5]["configured"], tail[5]["lxmf"]), (True, destination(key, "lxmf.delivery").hex()))
        # Skrót niezgodny z dokumentem: `hash`; dokument niepoprawny: `invalid` z nazwą pola.
        bad = json.dumps(station_doc(addresses=["x"], colour=1)).encode()
        steps = ["connect", lambda u: u("xfer_begin", op="configure", size=len(data), sha256="00" * 32), "XFER"] + \
                [("PART", 300 * i, p) for i, p in enumerate(parts)] + ["COMMIT"] + \
                [lambda u: u("xfer_begin", op="configure", size=len(bad), sha256=hashlib.sha256(bad).hexdigest()), "XFER",
                 *[("PART", o, base64.b64encode(bad[o:o + 300]).decode()) for o in range(0, len(bad), 300)], "COMMIT",
                 lambda u: u("xfer_begin", op="configure", size=8000, sha256="00" * 32),
                 lambda u: u("xfer_begin", op="import"), lambda u: u("xfer_begin", op="config_get")]
        out, _ = self.usb_session(steps)
        rejected = [(x["reason"], x.get("detail")) for x in self.replies(out) if x["type"] == "rejected"]
        self.assertEqual(rejected, [("hash", None), ("invalid", "colour"), ("size", None), ("migration", "op"), ("not_configured", None)])
        # Konfiguracja węzła stanowiska: polecenia stacji schronienia dają `role`.
        node = json.dumps(node_doc()).encode()
        steps = ["connect", lambda u: u("xfer_begin", op="configure", size=len(node), sha256=hashlib.sha256(node).hexdigest()), "XFER",
                 ("PART", 0, base64.b64encode(node).decode()), "COMMIT", "connect",
                 lambda u: u("submit", id=self.rid(5), revision=0, sa1=self.request(self.rid(5))),
                 lambda u: u("test", nonce="00" * 8), lambda u: u("status")]
        out, _ = self.usb_session(steps)
        r = self.replies(out)
        self.assertIn("config changed 1", out)
        self.assertEqual((r[-4]["type"], r[-4]["role"]), ("hello", "wezel"))
        self.assertEqual([(x["type"], x.get("reason")) for x in r[-3:]], [("rejected", "role"), ("rejected", "role"), ("status", None)])
        self.assertEqual(r[-1]["role"], "wezel")

    def test_usb_submit_cancel_test_and_rejections(self):
        u = self.Lines()
        x, y, z, w = self.rid(1234), self.rid(2345), self.rid(3456), self.rid(4567)
        req = self.request(x, text="osoba na wózku")
        script = [self.CONFIG, "connect", u("submit", id=x, revision=0, sa1=req), u("submit", id=x, revision=0, sa1=req),
                  u("submit", id=x, revision=0, sa1=self.request(x, people=9)),        # ta sama rewizja, inna treść
                  u("submit", id=x, revision=1, sa1=req),                              # revision niezgodne z SA1
                  u("submit", id=y, revision=0, sa1=self.request(x)),                  # id niezgodne z SA1
                  u("submit", id=x, revision=0, sa1=[1, 2, x, 0, 2, 2]),               # STATUS nie jest poleceniem stacji
                  u("submit", id="%04x" % 1234 + "f" * 28, revision=0, sa1=self.request("%04x" % 1234 + "f" * 28)),
                  u("submit", id=y, revision=0, sa1=self.request(y)), "poll",
                  u("cancel", id=y), u("submit", id=w, revision=0, sa1=self.request(w)), u("cancel", id=w), u("cancel", id=w),
                  u("submit", id=w, revision=1, sa1=self.request(w, 1)), u("cancel", id=z), u("cancel", id="zz"),
                  u("test", nonce="0102030405060708"), u("test", nonce="0102030405060708"), u("test", nonce="0102"),
                  u("submit", id=x, revision=1, sa1=self.request(x, 1, people=3)), u("submit", id=x, revision=0, sa1=req)]
        out = self.world(script)
        r = self.replies(out)[1:]
        kinds = [(x_["type"], x_.get("reason"), x_.get("detail")) for x_ in r]
        self.assertEqual(kinds, [
            ("stored", None, None), ("stored", None, None), ("rejected", "conflict", None), ("rejected", "invalid", "revision"),
            ("rejected", "invalid", "id"), ("rejected", "invalid", "sa1"), ("rejected", "numer_zajety", None), ("stored", None, None),
            ("rejected", "too_late", None),                       # po `nadane` tylko POTRZEBA USTAŁA
            ("stored", None, None), ("ok", None, None), ("ok", None, None), ("rejected", "closed", None),
            ("rejected", "invalid", "id"), ("rejected", "invalid", "id"),
            ("stored", None, None), ("stored", None, None), ("rejected", "invalid", "nonce"),
            ("stored", None, None), ("rejected", "stale", None)])
        self.assertEqual((r[0]["id"], r[0]["revision"], r[0]["number"], r[0]["duplicate"]), (x, 0, "1234", False))
        self.assertTrue(r[1]["duplicate"])
        # nonce: jeden TEST; krótki numer już w pierwszej odpowiedzi (ponowienie liczy go z id).
        self.assertEqual((r[15]["id"], r[15]["number"]), (r[16]["id"], r[16]["number"]))
        self.assertIn("log usb submit", out)

    def test_usb_sync_events_window_resend_and_snapshot(self):
        x = self.rid(1234)
        u = self.Lines()
        epoch = self.replies(self.world(["connect"]))[0]["epoch"]   # epoka z `hello` (generator programu testowego)
        script = [self.CONFIG, "sevents 11", "connect",
                  u("sync", boot="b", epoch="00" * 8, cursor=0), u("sync", boot="b", epoch=epoch, cursor=99),
                  u("sync", boot="b", epoch=epoch, cursor=0), "ms 1000", "upoll", "ms 3000", "upoll", "ms 6000", "upoll",
                  u("ack", epoch=epoch, cursor=8), "upoll", u("ack", epoch=epoch, cursor=12), "upoll",
                  self.sub(self.request(x)), "upoll", "ms 7000", u("snapshot", epoch=epoch), u("snapshot", epoch="00" * 8),
                  "sevents 300", u("sync", boot="b", epoch=epoch, cursor=5)]
        out = self.world(script)
        r = self.replies(out)[1:]
        self.assertEqual((r[0]["type"], r[0]["reason"]), ("snap_required", "epoch"))
        self.assertEqual((r[1]["type"], r[1]["reason"], r[1]["head"]), ("snap_required", "ahead", 12))
        self.assertEqual((r[2]["type"], r[2]["from"], r[2]["head"]), ("sync_ok", 1, 12))
        events = [x_ for x_ in r if x_["type"] == "event"]
        # Okno 8 zdarzeń bez ack, ponowienie od cursor + 1 po 5 s, po ack dalsze.
        self.assertEqual([e["ev"] for e in events[:16]], list(range(1, 9)) + list(range(1, 9)))
        self.assertEqual([e["ev"] for e in events[16:20]], [9, 10, 11, 12])
        self.assertEqual(events[0]["kind"], "station")
        self.assertEqual((events[0]["what"], events[19]["what"], events[19]["detail"]), ("config", "prep", 10))
        own = events[20]
        self.assertEqual((own["ev"], own["kind"], own["id"], own["origin"], own["sa1"]), (13, "own", x, "usb", self.request(x)))
        snap = [x_ for x_ in r if x_["type"] in ("snap_begin", "snap", "snap_end")]
        self.assertEqual([s["type"] for s in snap[:3]], ["snap_begin", "snap", "snap_end"])
        self.assertEqual((snap[0]["count"], snap[0]["head"], snap[1]["item"], snap[1]["id"], snap[1]["stage"], snap[1]["number"]),
                         (1, 13, "request", x, "stored", "1234"))
        self.assertEqual(len(snap), 3)
        self.assertEqual([(x_["reason"], x_.get("detail")) for x_ in r if x_["type"] == "rejected"], [("invalid", "epoch")])
        last = r[-1]
        self.assertEqual((last["type"], last["reason"], last["min"]), ("snap_required", "gap", 313 - 256 + 1))

    def test_usb_output_queue_with_stalled_laptop(self):
        # Laptop przestaje czytać w trakcie migawki: kolejka ma najwyżej jeden pełny wiersz, wejście czeka,
        # nic nie przepada; po wznowieniu odczytu migawka kończy się pełna. Zdarzenie w trakcie: `stale`.
        u = self.Lines()
        epoch = self.replies(self.world(["connect"]))[0]["epoch"]
        subs = [self.sub(self.request(self.rid(2000 + i))) for i in range(30)]
        out = self.world([self.CONFIG] + subs + ["connect", "stall 1", u("snapshot", epoch=epoch), "upoll", "upoll", "queue",
                                                 "stall 0", "queue"])
        snap = [x_ for x_ in self.replies(out) if x_["type"] in ("snap_begin", "snap", "snap_end")]
        self.assertEqual([s_["type"] for s_ in snap], ["snap_begin"] + ["snap"] * 30 + ["snap_end"])
        self.assertEqual(snap[0]["count"], 30)
        queues = self.find(out, "queue ")
        self.assertTrue(queues[0].startswith("queue accepts=0 snapshot=1 dropped=0"), queues[0])
        self.assertTrue(0 < int(queues[0].split("first=")[1]) <= 1025)
        self.assertTrue(queues[1].startswith("queue accepts=1 snapshot=0 dropped=0"), queues[1])
        u = self.Lines()
        out = self.world([self.CONFIG] + subs + ["connect", "stall 1", u("snapshot", epoch=epoch), "sevents 1", "stall 0", "upoll"])
        r = [x_ for x_ in self.replies(out) if x_["type"] in ("snap_begin", "snap", "snap_end", "rejected")]
        self.assertEqual((r[0]["type"], r[-1]["type"], r[-1]["reason"], r[-1]["re"]), ("snap_begin", "rejected", "stale", r[0]["re"]))
        self.assertNotIn("snap_end", [x_["type"] for x_ in r])
        # Odczyt wiadomości na ekranie nie daje zdarzenia, a też zmienia stan: migawka z wiadomością 2
        # nieprzeczytaną nie może skończyć się wiadomością 10 przeczytaną (stan, którego nie było).
        u = self.Lines()
        messages = ["in " + compact([1, 4, self.rid(80), 7, "Komunikat"]), "sevents 7", "in " + compact([1, 4, self.rid(81), 8, "Komunikat 2"])]
        out = self.world([self.CONFIG] + messages + ["inbox a", "connect", "stall 1", u("snapshot", epoch=epoch), "upoll", "markread 2",
                                                     "markread 10", "stall 0", "upoll"])
        self.assertEqual(sorted(int(line.split("msg=")[1].split()[0]) for line in self.find(out, "msg a ")), [2, 10])
        self.assertEqual(self.find(out, "markread "), ["markread 1", "markread 1"])
        r = [x_ for x_ in self.replies(out) if x_["type"] in ("snap_begin", "snap", "snap_end", "rejected")]
        self.assertEqual((r[0]["type"], r[-1]["type"], r[-1]["reason"]), ("snap_begin", "rejected", "stale"))

    def test_usb_confirmed_commands_silence_close_destroy(self):
        u = self.Lines()
        epoch = self.replies(self.world(["connect"]))[0]["epoch"]
        x = self.rid(1234)
        # Zgłoszenie x przed poleceniami: wyjątek ciszy dotyczy tylko wpisu rejestru.
        script = ["H", self.CONFIG, self.sub(self.request(x)), "connect", u("silence", on=True), u("status"), u("cancel", id=x), "R", "K OK 0", "upoll", "R",
                  u("silence", on=False), "K BACK 0", "upoll",
                  u("silence", on=True, exception_id=x), "ms 29999", "upoll", "ms 30000", "upoll",
                  "switch 1", u("silence", on=False), u("silence", on=True, exception_id=x), "switch 0",
                  u("silence", on=True, exception_id=self.rid(999)), "ms 31000", u("close", epoch=epoch, head=1), "K OK 0", "upoll",
                  "sevents 1", u("close", epoch=epoch, head=3), "K OK 0", "upoll", u("close", epoch=epoch, head=3),
                  u("destroy"), "K OK 0", "upoll", "diag"]
        out = self.world(script)
        r = self.replies(out)[1:]
        kinds = [(x_["type"], x_.get("reason")) for x_ in r]
        self.assertEqual(kinds, [
            ("pending", None), ("status", None), ("rejected", "busy"), ("ok", None),     # OK na ekranie stacji
            ("pending", None), ("rejected", "not_confirmed"),                             # WSTECZ
            ("pending", None), ("rejected", "not_confirmed"),                             # brak odpowiedzi przez 30 s
            ("rejected", "silence_switch"), ("rejected", "silence_switch"),
            ("rejected", "invalid"),                           # wyjątek dla id spoza rejestru
            ("pending", None), ("rejected", "stale"),          # po head 1 jest `own` (`radio` nie blokuje)
            ("pending", None), ("ok", None), ("ok", None), ("pending", None), ("ok", None)])
        self.assertEqual(r[0]["confirm_s"], 30)
        self.assertEqual((r[3]["silence"], r[3]["silence_source"]), (True, "panel"))
        close = r[14]
        self.assertEqual(close["duplicate"], False)
        self.assertNotEqual(close["epoch"], epoch)
        # Powtórzone `close`: ten sam wynik, także gdy po head 3 przyszło zdarzenie nieblokujące (`station` 4).
        self.assertEqual((r[15]["duplicate"], r[15]["epoch"]), (True, close["epoch"]))
        self.assertIn("ask 0", out)
        screens = [line for line in out if line.startswith("screen ")]
        self.assertEqual(screens[0].split()[1], "confirm")
        self.assertNotEqual(screens[1].split()[1], "confirm")
        self.assertIn("destroyed 1", out)
        self.assertIn("requests=0", self.find(out, "diag ")[0])

    def test_usb_radio_events_keep_their_exception(self):
        # Zdarzenie `radio` podaje wyjątek z chwili zdarzenia: po wyłączeniu ciszy (meta bez wyjątku)
        # i po zwolnieniu wpisu (id z pamięci zwolnionych wpisów).
        u = self.Lines()
        epoch = self.replies(self.world(["connect"]))[0]["epoch"]
        x = self.rid(1234)
        script = ["H", self.CONFIG, self.sub(self.request(x)), "connect", u("silence", on=True, exception_id=x), "K OK 0", "upoll",
                  u("silence", on=False), "K OK 0", "upoll", u("cancel", id=x)]
        # Pełny rejestr (x w gnieździe 0): nowe zgłoszenie zwalnia anulowane x do pamięci zwolnionych wpisów.
        script += ["txreq %d %x 0 1" % (slot, slot) for slot in range(1, 256)]
        script += [self.sub(self.request(self.rid(4321))), u("cancel", id=x), u("sync", boot="b", epoch=epoch, cursor=0), "upoll"]
        out = self.world(script)
        self.assertEqual([x_.get("released") for x_ in self.replies(out) if x_["type"] == "ok" and "silence" not in x_], [None, True])
        radio = [x_ for x_ in self.replies(out) if x_["type"] == "event" and x_["kind"] == "radio"]
        self.assertEqual([(e["silence"], e["exception_id"], e["exception_revision"]) for e in radio], [(True, x, 0), (False, None, None)])
        self.assertNotIn("lost", radio[0])

    # --- ekran -----------------------------------------------------------------

    def ui(self, script):
        return self.world(script)

    @staticmethod
    def screens(out):
        """Split harness output into (screen name, language, [(inverted, text)]) tuples."""
        result = []
        i = 0
        while i < len(out):
            if out[i].startswith("screen "):
                _, name, lang = out[i].split()
                lines = [(row[0] == "1", row[2:]) for row in out[i + 1:i + 6]]
                result.append((name, int(lang), lines))
                i += 6
            else:
                i += 1
        return result

    @staticmethod
    def lines(screen):
        return [t for _, t in screen[2]]

    def shown(self, screen):
        return " ".join(self.lines(screen)).strip()

    def test_screen_language_choice_then_main_screen(self):
        texts = ui_texts.load()["texts"]
        out = self.ui(["S 0", "O 1", "R", "K DOWN 0", "R", "K OK 1", "R", "K BACK 2", "R"])
        first, moved, main, still = self.screens(out)
        self.assertEqual(first[0], "language")
        self.assertEqual([t for _, t in first[2]], ["POLSKI", "УКРАЇНСЬКА", "ENGLISH", "", ""])
        self.assertEqual([inv for inv, _ in first[2]], [True, False, False, False, False])
        self.assertEqual([inv for inv, _ in moved[2]], [False, True, False, False, False])
        self.assertEqual((main[0], main[1]), ("main", 1))
        self.assertEqual(main[2][0][1], texts["radio_wlaczone"][1])
        self.assertEqual(main[2][1][1], texts["kontakt_ponad_krotki"][1].replace("[czas]", "0 ХВ"))
        self.assertEqual(main[2][2][1], texts["zasilanie_12v"][1].replace("[x]", "0,0"))
        self.assertEqual(main[2][3][1], "")
        self.assertEqual(main[2][4][1], texts["nowe_krotki"][1].replace("[n]", "0"))
        self.assertEqual(still[0], "main")  # WSTECZ na ekranie głównym nic nie zmienia

    def test_short_forms_fit_twenty_columns_with_largest_values(self):
        # oprogramowanie.md: krótkie formy <= 20 znaków po wstawieniu największych wartości w każdym języku.
        texts = ui_texts.load()["texts"]
        for lang in range(3):
            unit = ui_texts.UNITS[ui_texts.LANGS[lang]][0]
            out = self.ui([f"L {lang}", "O 1", "U 5940", "N 128", "C 128 5940", "V 13800", "R", "P 1", "R", "Q 1", "R"])
            plain, prep, silence = self.screens(out)
            expected = [
                texts["radio_wlaczone"][lang],
                texts["kontakt_ponad_krotki"][lang].replace("[czas]", f"99 {unit}"),
                texts["zasilanie_12v"][lang].replace("[x]", "13" + ui_texts.DECIMAL[ui_texts.LANGS[lang]] + "8"),
                texts["kolejka_krotki"][lang].replace("[n]", "128").replace("[czas]", f"99 {unit}"),
                texts["nowe_krotki"][lang].replace("[n]", "128"),
            ]
            self.assertEqual([t for _, t in plain[2]], expected, lang)
            for text in expected:
                self.assertLessEqual(len(text), 20, text)
            self.assertEqual([t for _, t in prep[2]], [texts["tryb_przygotowania"][lang]] + expected[:4], lang)
            # Cisza: pełny tekst `cisza` w wierszach 1-3, potem zasilanie i kolejka.
            silence_lines = [t for _, t in silence[2]]
            self.assertEqual(silence_lines[0], texts["tryb_przygotowania"][lang])
            self.assertEqual(" ".join(silence_lines[1:4]), texts["cisza"][lang])
            self.assertEqual(silence_lines[4], expected[2])

    def test_menu_status_and_language_navigation(self):
        data = ui_texts.load()
        labels = data["labels"]
        menu = [strings[0] for _, strings in data["menu"]]
        out = self.ui(["L 0", "O 1", "X 12 3 4 1 7 16228", "F 123", "K OK 0", "R", "K DOWN 0", "K DOWN 0", "K DOWN 0", "R",
                       "K OK 0", "R"] + ["K DOWN 0"] * 14 + ["R",
                       "K BACK 0", "R", "K DOWN 0", "K OK 0", "R", "K DOWN 0", "K DOWN 0", "K OK 0", "R", "K BACK 0", "R",
                       "K OK 0", "K OK 0", "R", "T 179999", "R", "T 180000", "R"])
        screens = self.screens(out)
        self.assertEqual([s[0] for s in screens],
                         ["menu", "menu", "status", "status", "menu", "language_menu", "menu", "main", "category", "category", "main"])
        self.assertEqual([t for _, t in screens[0][2]], menu)
        self.assertEqual([inv for inv, _ in screens[0][2]], [True, False, False, False, False])
        self.assertEqual([inv for inv, _ in screens[1][2]], [False, False, False, True, False])
        status_top = [t for _, t in screens[2][2]]
        self.assertEqual(status_top[:5], [data["texts"]["radio_wlaczone"][0], "RX OK 12", "RX BAD 3", "TX 4 DROP 1", "DEFER 7"])
        status_end = [t for _, t in screens[3][2]]
        # Koniec ekranu STAN: wersja, nazwa, PRZEKAZANIE ZMIANY i USŁUGI (kursor na ostatnim wierszu).
        self.assertEqual(status_end[-4:], ["bench-a-test", "WICI-000000", labels["PRZEKAZANIE_ZMIANY"][0], labels["USLUGI"][0]])
        self.assertEqual([inv for inv, _ in screens[3][2]], [False, False, False, False, True])
        self.assertIn("FOFF +123 HZ", status_end)
        self.assertEqual([inv for inv, _ in screens[4][2]], [False, False, False, True, False])  # kursor wraca na STAN
        self.assertEqual([t for _, t in screens[5][2]][:3], ["POLSKI", "УКРАЇНСЬКА", "ENGLISH"])
        self.assertEqual(screens[6][1], 2)  # wybrano ENGLISH, powrót do menu
        self.assertEqual([t for _, t in screens[6][2]], [strings[2] for _, strings in data["menu"]])
        self.assertEqual([t for _, t in screens[8][2]][0], "MEDICAL HELP")  # kreator: kategoria 0 w języku EN
        self.assertEqual(screens[9][0], "category")   # 179 999 ms bez naciśnięcia: ekran zostaje
        self.assertEqual(screens[10][0], "main")  # 3 min bezczynności: ekran główny

    def test_wrap_duration_and_glyph_coverage(self):
        data = ui_texts.load()
        texts = data["texts"]
        long_pl = texts["pilnosc_2_potw"][0]
        out = self.ui([f"W {long_pl}", "D 5940", "D 6000", "D 172799", "D 172800", "D 9000000", "W " + "A" * 45,
                       "W " + "\U0001F600" * 25])
        count = int(out[0].split()[1])
        lines = [row[1:] for row in out[1:1 + count]]
        self.assertEqual(" ".join(lines), long_pl)
        self.assertTrue(all(len(line) <= 20 for line in lines), lines)
        self.assertEqual(out[1 + count:1 + count + 5], ["99 MIN|99 ХВ|99 MIN", "1 H|1 ГОД|1 H", "47 H|47 ГОД|47 H",
                                                       "2 D|2 Д|2 D", "99 D|99 Д|99 D"])
        self.assertEqual(out[1 + count + 5:1 + count + 9], ["wrap 3", "|" + "A" * 20, "|" + "A" * 20, "|" + "A" * 5])
        # Znaki 4-bajtowe (spoza BMP, np. z komunikatu przez radio): 20 znaków = 80 B mieści się w wierszu.
        self.assertEqual(out[1 + count + 9:1 + count + 12], ["wrap 2", "|" + "\U0001F600" * 20, "|" + "\U0001F600" * 5])
        # Każdy znak każdego tekstu kanonicznego ma glif w foncie.
        every = "".join(sorted(ui_texts.charset(data)))
        self.assertEqual(self.ui([f"G {every}"]), [f"glyphs {len(every)} 0"])
        self.assertEqual(self.ui(["G ĄĆĘŁŃÓŚŹŻąćęłńóśźż ҐґЇїЄєІі 漢"]), ["glyphs 29 1"])

    HOSTED = ["H", CONFIG, "L 0", "O 1"]
    # Kreator: kategoria 0, 1 osoba, pilność 2 z potwierdzeniem, bez frazy, zapis, powrót do ekranu głównego.
    CREATE = ["K OK 0", "K OK 0", "K OK 0", "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0"]

    def test_startup_address_check_object_list_and_test_offer(self):
        texts = ui_texts.load()["texts"]
        out = self.ui(["H", self.CONFIG, "S 0", "O 1", "K OK 0", "R", "K BACK 0", "R", "K OK 0", "R", "K OK 0", "R", "reg a",
                       "K BACK 0", "R", "reg b"])
        address, missing, offer, test, menu = self.screens(out)
        self.assertEqual(address[0], "address")
        self.assertEqual(self.shown(address), texts["adres_kontrola"][0].replace("[x]", "Szkoła, wejście B"))
        self.assertEqual(self.shown(missing), texts["adres_brak"][0])  # WSTECZ = NIE
        self.assertEqual(offer[0], "test_offer")
        self.assertEqual(test[0], "test")
        # TEST startowy: losowe opóźnienie w oknie 50 s x 2 stacje, ekran test_zaplanowany, WSTECZ anuluje.
        scheduled = list(self.regs(out, "a").values())
        self.assertEqual([(r["type"], r["stage"]) for r in scheduled], [(5, 0)])
        self.assertTrue(0 <= scheduled[0]["next"] < 100)
        minutes = (scheduled[0]["next"] + 59) // 60
        self.assertEqual(self.shown(test), texts["test_zaplanowany"][0].replace("[mm]", str(minutes)))
        self.assertEqual([r["stage"] for r in self.regs(out, "b").values()], [4])
        self.assertEqual(menu[0], "menu")
        # Lista obiektów: wybór przyciskami; WSTECZ na kontroli wraca do listy, WSTECZ na liście = adres_brak.
        objects = "cfg " + json.dumps(station_doc(addresses=["Szkoła A", "Hala sportowa B", "Kościół C"]), ensure_ascii=False)
        out = self.ui(["H", objects, "S 0", "O 1", "K OK 0", "R", "K DOWN 0", "K OK 0", "R", "K BACK 0", "R", "K BACK 0", "R", "addr",
                       "K OK 0", "K OK 0", "reg c"])
        listed, check, again, missing = self.screens(out)
        self.assertEqual(listed[0], "address_list")
        self.assertEqual(self.lines(listed), ["Szkoła A", "Hala sportowa B", "Kościół C", "", ""])
        self.assertEqual(self.shown(check), texts["adres_kontrola"][0].replace("[x]", "Hala sportowa B"))
        self.assertEqual((again[0], [inv for inv, _ in again[2]]), ("address_list", [False, True, False, False, False]))
        self.assertEqual(self.shown(missing), texts["adres_brak"][0])
        self.assertIn("addresses 3 selected 1 |Szkoła A |Hala sportowa B |Kościół C |location Hala sportowa B", out)

    def test_chosen_object_goes_into_requests_and_revision_keeps_it(self):
        objects = "cfg " + json.dumps(station_doc(addresses=["Obiekt Alfa", "Obiekt Beta", "Obiekt Gamma"]), ensure_ascii=False)
        out = self.ui(["H", objects, "S 0", "O 1", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0", "reg a", "sa1s"])
        number = list(self.regs(out, "a").values())[0]["num"]
        out = self.ui(["H", objects, "S 0", "O 1", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0", "sel 0",
                       f"revise {number} 3 0", "sa1s", "restart", "addr"])
        sa1 = self.find(out, "sa1 ")
        self.assertIn('"Obiekt Gamma"', sa1[0])            # TEST startowy z wybranego obiektu
        self.assertIn("revise not_found", out)             # TEST nie ma rewizji z przycisków
        self.assertNotIn("Obiekt Alfa", " ".join(sa1))
        # Wybór obiektu jest w RAM (main.cpp odtwarza go z ustawień): po starcie magazynu pierwszy obiekt.
        self.assertIn("addresses 3 selected 0 |Obiekt Alfa |Obiekt Beta |Obiekt Gamma |location Obiekt Alfa", out)
        # Rewizja zgłoszenia po zmianie wyboru zachowuje lokalizację.
        out = self.ui(["H", objects, "S 0", "O 1", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0", "K OK 0", "K BACK 0"] + self.CREATE +
                      ["reg a", "sel 0"])
        number = list(self.regs(out, "a").values())[0]["num"]
        out = self.ui(["H", objects, "S 0", "O 1", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0", "K OK 0", "K BACK 0"] + self.CREATE +
                      ["sel 0", f"revise {number} 3 0", "sa1s"])
        self.assertIn("revise stored", out)
        self.assertEqual(len(self.find(out, "sa1 ")), 1)
        self.assertIn(',3,"Obiekt Gamma",', self.find(out, "sa1 ")[0])

    def test_digits_hold_repeat_discard_and_language_hold(self):
        texts = ui_texts.load()["texts"]
        script = ["K OK 0", "K OK 0", "K OK 0"] + ["K DOWN 0"] * 7 + ["R", "K OK 0", "R", "K UP 0", "K UP 0", "K OK 0", "K OK 0",
                  "K DOWN 0", "K DOWN 0", "R", "KD UP 1000", "T 1400", "T 1600", "T 1900", "KU UP 1900", "R", "K OK 0", "R",
                  "KD BACK 2000", "T 3000", "R", "T 4100", "R", "KU BACK 4200", "R", "K BACK 0", "R", "KD BACK 5000", "T 7100",
                  "R", "KU BACK 7100", "R", "K OK 0", "R", "KD BACK 8000", "T 11100", "KU BACK 11100", "R", "K BACK 0", "R",
                  "K UP 0", "K UP 0", "K UP 0", "K UP 0", "K OK 0", "K OK 0", "R"]
        s = self.screens(self.ui(self.HOSTED + script))
        self.assertEqual([x[0] for x in s], ["people", "digits", "digits", "digits", "urgency", "urgency", "discard", "discard",
                                             "urgency", "discard", "discard", "main", "language_menu", "menu", "people"])
        self.assertEqual([inv for inv, _ in s[0][2]], [False, False, False, False, True])  # INNA
        self.assertEqual(self.lines(s[1])[1:3], ["0 0 1", "^"])
        self.assertEqual(self.lines(s[2])[1:3], ["2 0 9", "    ^"])
        self.assertEqual(self.lines(s[3])[1:3], ["2 0 2", "    ^"])  # przytrzymanie: 9 -> 0 od razu, potem co 150 ms
        self.assertEqual(self.shown(s[6]), texts["porzucic"][0])
        self.assertEqual(s[8][0], "urgency")  # WSTECZ na ekranie porzucenia wraca do kroku
        self.assertEqual(s[12][1], 0)
        self.assertEqual(self.lines(s[12])[:3], ["POLSKI", "УКРАЇНСЬКА", "ENGLISH"])  # 3 s poza kreatorem
        self.assertEqual([inv for inv, _ in s[14][2]], [True, False, False, False, False])  # po porzuceniu: szkic skasowany

    def test_own_phrase_list_revision_keeps_and_translates_phrase(self):
        # Własna lista fraz: rewizja liczby osób pokazuje zachowaną frazę w podsumowaniu, a POTRZEBA USTAŁA
        # (fraza domyślna spoza listy) jest tłumaczona na ekranie zgłoszenia.
        phrases = "cfg " + json.dumps(station_doc(phrases=[["brama zamknięta", "ворота зачинені", "gate closed"]]), ensure_ascii=False)
        create = ["K OK 0", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0", "K DOWN 0",
                  "K DOWN 0", "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0", "poll", "rcpt 1 1"]
        # WIADOMOŚCI → zgłoszenie → ZMIEŃ LICZBĘ OSÓB → ta sama liczba → podsumowanie; wysłanie.
        people = ["L 2", "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0"]
        # Najnowsza rewizja → POTRZEBA USTAŁA → wysłanie; potem ekran zgłoszenia przewinięty do frazy.
        resolved = ["K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0",
                    "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "K DOWN 0", "K DOWN 0"]
        script = ["H", phrases, "L 0", "O 1"] + create
        for key in people + resolved:
            script += [key, "R"]
        s = [x for x in self.screens(self.ui(script)) if x[0] in ("summary", "item")]
        self.assertEqual([x[0] for x in s], ["item", "summary", "item", "summary", "item", "item", "item"])
        self.assertEqual(self.lines(s[1])[3], "gate closed")      # zachowana fraza z listy stacji, po angielsku
        self.assertIn("need resolved", self.lines(s[-1]))         # nie „potrzeba ustała”

    def test_wizard_creates_request_and_item_shows_stage(self):
        data = ui_texts.load()
        texts, labels = data["texts"], data["labels"]
        script = self.HOSTED + ["now 100", "K OK 0", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0",
                                "K DOWN 0", "K DOWN 0", "K OK 0", "K DOWN 0", "K OK 0", "R", "K OK 0", "R", "K OK 0", "reg a",
                                # WIADOMOŚCI → zgłoszenie: etap zapisane, w ciszy zapisane_w_ciszy, po nadaniu wysylanie.
                                "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "R", "K OK 0", "R", "K BACK 0", "Q 1", "R", "Q 0",
                                "poll", "R", "K OK 0", "R", "K BACK 0", "K BACK 0", "M"]
        out = self.ui(script)
        reg = list(self.regs(out, "a").values())
        self.assertEqual(len(reg), 1)
        number, x = reg[0]["num"], reg[0]["id"]
        self.assertEqual((reg[0]["type"], reg[0]["origin"], reg[0]["stage"]), (0, 0, 0))
        s = self.screens(out)
        summary, result, item, menu, silent, sending, sending_menu = s
        self.assertEqual(self.lines(summary)[:4], [data["categories"][2][0], "5 PILNE – KILKA", "GODZIN", data["phrases"][0][0]])
        self.assertEqual(self.shown(result), texts["zapisane_w_stacji"][0] + " " + texts["zapisz_numer"][0].replace("[xxxx]", number))
        self.assertTrue(self.shown(item).startswith(texts["zapisane_w_stacji"][0]), item)
        # Przed `nadane`: ANULUJ WYSYŁKĘ dostępne.
        self.assertEqual(self.lines(menu)[:4], [labels["ZMIEN_LICZBE_OSOB"][0], labels["ZMIEN_PILNOSC"][0], labels["POTRZEBA_USTALA"][0],
                                                labels["ANULUJ_WYSYLKE"][0]])
        self.assertTrue(self.shown(silent).startswith(texts["zapisane_w_ciszy"][0]), silent)
        self.assertTrue(self.shown(sending).startswith(texts["wysylanie"][0].replace("[n]", "1").replace("[m]", "1")), sending)
        self.assertEqual(self.lines(sending_menu)[3], "")   # po `nadane` tylko POTRZEBA USTAŁA
        self.assertIn(f"item 1 0 {number} 2 5 1 1 0 1 1 0 |osoba na wózku", out)
        # STATUS(X,0,e=10,s=6), potem nowa rewizja (ZMIEŃ LICZBĘ OSÓB): zapisane_w_stacji i pod nim stan_6.
        script2 = script + ["in " + compact([1, 2, x, 0, 10, 6]), "K OK 0", "R", "K OK 0", "K OK 0", "K DOWN 0", "K OK 0", "R",
                            "K OK 0", "K OK 0", "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "R", "reg b"]
        out = self.ui(script2)
        s = self.screens(out)[7:]
        self.assertTrue(self.shown(s[0]).startswith(texts["stan_6"][0]), s[0])
        self.assertEqual(s[1][0], "summary")
        self.assertTrue(self.shown(s[2]).startswith(texts["zapisane_w_stacji"][0] + " " + texts["stan_6"][0]), s[2])
        b = self.regs(out, "b")[x]
        self.assertEqual((b["rmax"], b["stage"], b["dec"], b["closed"]), (1, 0, 6, 0))
        self.assertIn(f"log request {number} revision 1", out)

    def test_cancel_removes_item_and_test_screen_states(self):
        texts = ui_texts.load()["texts"]
        # Nowe zgłoszenie, WIADOMOŚCI → pozycja → ANULUJ WYSYŁKĘ: znika z listy.
        out = self.ui(self.HOSTED + self.CREATE + ["M", "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0", "K DOWN 0", "K DOWN 0",
                                                   "K DOWN 0", "K OK 0", "R", "M", "reg a"])
        self.assertIn("items 1", out)
        self.assertEqual(self.find(out, "items "), ["items 1", "items 0"])
        self.assertEqual(self.screens(out)[-1][0], "messages")
        self.assertEqual([r["stage"] for r in self.regs(out, "a").values()], [4])
        self.assertTrue(any(line.startswith("log request ") and line.endswith(" cancelled") for line in out))
        # TEST: bez TEST, zaplanowany (z menu od razu), wysłany, potwierdzony, wstrzymany.
        to_test = ["K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0"]
        out = self.ui(self.HOSTED + to_test + ["R", "K OK 0", "K OK 0", "R", "reg a", "poll", "R"])
        tid = list(self.regs(out, "a").values())[0]["id"]
        out = self.ui(self.HOSTED + to_test + ["R", "K OK 0", "K OK 0", "R", "reg a", "poll", "R", "in " + compact([1, 1, tid, 0, 1, 1]),
                                               "R", "K OK 0", "K DOWN 0", "K OK 0", "R", "K OK 0", "R"])
        s = self.screens(out)
        self.assertEqual([x[0] for x in s], ["test", "test", "test", "test", "test", "test_menu"])
        self.assertEqual(self.shown(s[1]), texts["test_zaplanowany"][0].replace("[mm]", "0"))
        self.assertEqual(self.shown(s[2]), texts["test_wyslany"][0])
        self.assertEqual(self.shown(s[3]), texts["stan_1"][0])
        self.assertEqual(self.shown(s[4]), texts["test_wstrzymany"][0])
        self.assertEqual(self.lines(s[5])[1], ui_texts.load()["labels"]["WZNOW"][0])

    def test_alarm_screen_ack_and_handover(self):
        texts = ui_texts.load()["texts"]
        labels = ui_texts.load()["labels"]
        out = self.ui(self.HOSTED + ["now 10"] + self.CREATE + ["reg a", "now 909", "T 100000", "R", "now 910", "T 101000", "R",
                                                               "K OK 0", "R", "T 103000", "R"])
        number = list(self.regs(out, "a").values())[0]["num"]
        s = self.screens(out)
        self.assertEqual([x[0] for x in s], ["main", "alarm", "main", "main"])
        self.assertTrue((texts["brak_potwierdzenia"][0].replace("[n]", "15") + " " +
                         texts["zapisz_numer"][0].replace("[xxxx]", number)).startswith(self.shown(s[1])))
        # PRZEKAZANIE ZMIANY: otwarte zgłoszenie z numerem, kategorią i etapem.
        out = self.ui(self.HOSTED + self.CREATE + ["K OK 0", "K DOWN 0", "K DOWN 0", "K DOWN 0", "K OK 0"] + ["K DOWN 0"] * 13 +
                      ["R", "K OK 0", "R", "reg a"])
        number = list(self.regs(out, "a").values())[0]["num"]
        status, handover = self.screens(out)
        self.assertEqual([t for inv, t in status[2] if inv], [labels["PRZEKAZANIE_ZMIANY"][0]])
        self.assertEqual(handover[0], "handover")
        self.assertEqual(self.lines(handover)[:2], [labels["PRZEKAZANIE_ZMIANY"][0], number + " " + ui_texts.load()["categories"][0][0]])
        self.assertTrue(" ".join(self.lines(handover)[2:]).startswith(texts["zapisane_w_stacji"][0][:15]))

    def test_radio_fault_alarm(self):
        # oprogramowanie.md: radio_awaria to alarm krytyczny jak brak_potwierdzenia: ekran alarmu do OK,
        # przyczyna (dioda, PRZEKAZANIE ZMIANY) trwa do naprawy; nowa awaria alarmuje od nowa.
        texts = ui_texts.load()["texts"]
        labels = ui_texts.load()["labels"]
        out = self.ui(["H", self.CONFIG, "L 0", "O 0", "cause", "T 1000", "R", "K OK 1000", "T 2000", "R", "cause",
                       "K OK 2050", "K DOWN 2100", "K DOWN 2200", "K DOWN 2300", "K OK 2400"] + ["K DOWN 2500"] * 13 + ["K OK 2600", "R",
                       "O 1", "cause", "K BACK 2700", "K BACK 2800", "K BACK 2900", "T 4000", "R", "O 0", "T 5000", "R"])
        s = self.screens(out)
        self.assertEqual([x[0] for x in s], ["alarm", "main", "handover", "main", "alarm"])
        self.assertEqual(self.shown(s[0]), texts["radio_awaria"][0])
        self.assertEqual(self.lines(s[1])[0], texts["radio_awaria"][0])
        self.assertIn(texts["radio_awaria"][0], self.lines(s[2]))
        self.assertEqual(self.lines(s[2])[0], labels["PRZEKAZANIE_ZMIANY"][0])
        self.assertEqual(self.find(out, "cause "), ["cause 1", "cause 1", "cause 0"])
        # Magazyn zatrzymany (zanik zasilania w zapisie): awaria radia nadal jest przyczyną alarmu (dioda).
        out = self.ui([self.CONFIG, "txreq 0 11 0 1", "tear 552", "txreq 0 11 1 0", "diag", "O 0", "cause", "O 1", "cause"])
        self.assertIn("ok=0", self.find(out, "diag ")[0])
        self.assertEqual(self.find(out, "cause "), ["cause 1", "cause 0"])

    def test_confirm_question_and_node_menu(self):
        out = self.ui(["L 0", "ask 0", "R", "answer", "K OK 0", "answer", "R", "ask 3", "K BACK 0", "answer", "ask 5 ABCD", "R",
                       "K OK 0", "answer", "ask 1", "dismiss", "answer", "R", "ask 4 0427", "R", "dismiss"])
        s = self.screens(out)
        self.assertEqual([x[0] for x in s], ["confirm", "main", "confirm", "main", "confirm"])
        self.assertTrue(self.shown(s[0]).startswith("LAPTOP: WŁĄCZYĆ CISZĘ RADIOWĄ?"))
        self.assertIn("ABCD", self.shown(s[2]))
        self.assertIn("NR 0427", self.shown(s[4]))   # pytanie_cisza_wyjatek z krótkim numerem
        # OK = TAK, WSTECZ = NIE, odcisk karty zamyka się bez zgody, dismiss() kończy pytanie bez odpowiedzi.
        self.assertEqual(self.find(out, "answer "), ["answer 0", "answer 1", "answer 2", "answer 2", "answer 2"])
        # Konfiguracja węzła stanowiska: menu tylko STAN i JĘZYK, bez kontroli adresu i TEST.
        data = ui_texts.load()
        menu = [strings[0] for _, strings in data["menu"]]
        texts, labels = data["texts"], data["labels"]
        out = self.ui(["H", "cfg " + json.dumps(node_doc()), "S 0", "O 1", "K OK 0", "R", "PC 1 300 12 30 1", "R", "K OK 0", "R",
                       "K OK 0", "R"] + ["K DOWN 0"] * 14 + ["R", "K OK 0", "R"])
        main, heard, menu_screen, status_top, status_end, services = self.screens(out)
        power = texts["zasilanie_12v"][0].replace("[x]", "0,0")
        self.assertEqual(self.lines(main), [texts["radio_wlaczone"][0], texts["komputer_brak"][0], power, "", ""])
        self.assertEqual(self.lines(heard)[1], texts["komputer_osp"][0].replace("[czas]", "5 " + ui_texts.UNITS["PL"][0]))
        self.assertEqual(self.lines(menu_screen), [menu[3], menu[4], "", "", ""])
        self.assertEqual(status_top[0], "status")
        self.assertEqual(self.lines(status_end), [power, "FOFF ---", "bench-a-test", "WICI-000000", labels["USLUGI"][0]])
        self.assertEqual(self.lines(services), [labels["WYCISZ_DZWIEK"][0], labels["ZNISZCZ_DANE"][0], "", "", ""])

    def test_services_backup_and_destroy_sequences(self):
        labels = ui_texts.load()["labels"]
        texts = ui_texts.load()["texts"]
        to_services = ["K OK 0", "K DOWN 0", "K DOWN 0", "K DOWN 0", "K OK 0"] + ["K DOWN 0"] * 14 + ["K OK 0", "R"]
        script = self.HOSTED + self.CREATE + to_services + [
            "K OK 0", "R", "K OK 0",                                    # OGŁOŚ ADRES: wynik, powrót
            "K DOWN 0", "K OK 0", "R",                                  # WYCISZ DŹWIĘK
            "K DOWN 0", "K OK 0", "R", "K UP 0", "K DOWN 0", "K UP 0", "K OK 0", "R", "diag", "poll"] + \
            ["K DOWN 0"] * 16 + ["K OK 0", "K DOWN 0", "K DOWN 0", "K DOWN 0", "K OK 0", "R", "K UP 0", "K DOWN 0", "K DOWN 0", "R",
                                 "K UP 0", "K DOWN 0", "K UP 0", "K OK 0", "R", "diag"]
        out = self.ui(script)
        s = self.screens(out)
        self.assertEqual([x[0] for x in s], ["services", "result", "services", "backup", "status", "destroy", "destroy", "main"])
        self.assertEqual(self.lines(s[0])[:4], [labels["OGLOS_ADRES"][0], labels["WYCISZ_DZWIEK"][0], labels["KLUCZ_ZAPASOWY"][0],
                                                labels["ZNISZCZ_DANE"][0]])
        self.assertIn("announce 1", out)
        self.assertEqual(self.shown(s[1]), texts["adres_ogloszony"][0])
        self.assertEqual(self.lines(s[2])[1], labels["WLACZ_DZWIEK"][0])
        self.assertEqual(self.shown(s[3]), texts["klucz_zapasowy"][0])
        self.assertIn("log switched to backup receiver", out)
        self.assertIn("receiver=1", self.find(out, "diag ")[0])
        # Zgłoszenie zapisane przed przełączeniem idzie do zapasowej tożsamości.
        self.assertEqual([line.split()[2] for line in self.find(out, "send ")], [BACKUP_SA1])
        self.assertEqual(self.shown(s[5]), texts["zniszcz_ostrzezenie"][0])
        self.assertEqual(s[6][0], "destroy")   # zła sekwencja: nic się nie dzieje
        self.assertIn("destroyed 1", out)
        self.assertIn("requests=0", self.find(out, "diag ")[1])
        self.assertIn(texts["dzwiek_wyciszony"][0], self.lines(s[7]))
        # Bez działającego stosu: własny komunikat.
        failed = self.screens(self.ui(self.HOSTED + to_services + ["announce 0", "K OK 0", "R"]))[-1]
        self.assertEqual((failed[0], self.shown(failed)), ("result", texts["adres_nie_ogloszony"][0]))

    def test_lists_render_from_the_ram_index(self):
        # Lista WIADOMOŚCI i PRZEKAZANIE ZMIANY korzystają ze skrótu z indeksu w RAM: rysowanie nie czyta rekordów
        # własnych zgłoszeń z FRAM; treść komunikatu dekoduje się raz na rekord.
        script = self.HOSTED + self.CREATE * 3 + ["in " + compact([1, 4, self.rid(77), 7, "Komunikat"]), "K OK 0", "K DOWN 0",
                                                  "K OK 0", "R", "B", "R", "B", "K OK 0", "R", "B", "K BACK 0", "K BACK 0",
                                                  "K DOWN 0", "K DOWN 0", "K OK 0"] + ["K DOWN 0"] * 13 + ["K OK 0", "R", "B", "R", "B"]
        out = self.ui(script)
        s = self.screens(out)
        self.assertEqual([x[0] for x in s], ["messages", "messages", "item", "handover", "handover"])
        reads = [int(line.split()[1]) for line in out if line.startswith("read ")]
        self.assertEqual(reads[1], 0)            # ponowne rysowanie listy: treść z pamięci ostatniej pozycji
        self.assertGreaterEqual(reads[2], 512)   # otwarcie oznacza jako przeczytany: rekord czytany od nowa
        self.assertEqual(reads[3:], [0, 0])      # PRZEKAZANIE ZMIANY: wyłącznie indeks w RAM

    # --- SA1 -----------------------------------------------------------------

    MID = "0123456789abcdef0123456789abcdef"
    SHAPES = (
        [1, 0, MID, 65535, 9, 999, "ś" * 32, "ł" * 48, 2],
        [1, 1, MID, 7, 1, 1],
        [1, 2, MID, 7, 2147483647, 6],
        [1, 3, MID, 7, 5, "ż" * 48],
        [1, 4, MID, 2147483647, "ż" * 96],
        [1, 5, MID, 0, 9, 1, "Szkoła, wejście B", "test", 0],
    )

    def sa1(self, value):
        wire = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if not isinstance(value, str) else value
        line = subprocess.run([str(self.binary), "sa1", wire], capture_output=True, text=True, check=True).stdout.rstrip("\n")
        return line.split(" ", 2) if line.startswith("ok") else line.split(" ", 1)

    def test_sa1_every_shape_matches_model_encoding(self):
        for value in self.SHAPES:
            out = self.sa1(value)
            self.assertEqual(out[0], "ok", value)
            self.assertEqual(out[2].encode(), encode_message(value), value)
            self.assertLessEqual(int(out[1]), MAX_CONTENT)
        # Zapis z \u i spacjami daje tę samą postać kanoniczną.
        loose = json.dumps(self.SHAPES[5], ensure_ascii=True, separators=(", ", ": "))
        self.assertEqual(self.sa1(loose)[2].encode(), encode_message(self.SHAPES[5]))

    def test_sa1_rejections_match_model(self):
        cases = [
            ([1, 0, "x" * 32, 0, 1, 1, "a", "", 0], "Invalid message id"),
            ([1, 0, self.MID, 0, 1, 1, "a", "", 0, 0], "Invalid message arity"),
            ([1, 2, self.MID, 0, 1, 2], "Invalid integer"),           # STATUS event 1
            ([1, 2, self.MID, 0, 2, 7], "Invalid integer"),           # state 7
            ([1, 1, self.MID, 0, True, 1], "Invalid integer"),        # bool
            ([1, 0, self.MID, 0, 1, 1, "", "", 0], "Invalid UTF-8 text size"),
            ([1, 0, self.MID, 0, 1, 1, "a", "ł" * 49, 0], "Invalid UTF-8 text size"),
            ([1, 3, self.MID, 0, 1, 'a"b'], "Quotation mark or backslash"),
            ([1, 3, self.MID, 0, 1, "a\\b"], "Quotation mark or backslash"),
            ([1, 3, self.MID, 0, 1, "a​b"], "Control, format, separator, private or unassigned character"),
            ([1, 3, self.MID, 0, 1, "a b"], "Control, format, separator, private or unassigned character"),
            ([1, 3, self.MID, 0, 1, "ab"], "Control, format, separator, private or unassigned character"),
            ([1, 3, self.MID, 0, 1, "a\u0007b"], "Control, format, separator, private or unassigned character"),
            ([1, 3, self.MID, 0, 1, "a­b"], "Control, format, separator, private or unassigned character"),
            ({"a": 1}, "Expected message array"),
            ([1, 0, self.MID, 0.0, 1, 1, "a", "", 0], "Invalid integer"),
            ([1, 4, self.MID, 1, "ż" * 96 + "x"], "Invalid UTF-8 text size"),
        ]
        for value, reason in cases:
            self.assertEqual(self.sa1(value), ["err", reason], value)
        self.assertEqual(self.sa1(" " * (MAX_CONTENT + 1)), ["err", "Content too large"])

    def test_button_configuration_matches_model(self):
        self.assertEqual(self.run_harness("config", "ś" * 32, "Potrzeba ustała", "ł" * 48),
                         ["ok", str(check_button_configuration("ś" * 32, ("Potrzeba ustała", "ł" * 48)))])
        self.assertEqual(self.run_harness("config", "Testowa 10", "ł" * 49)[0], "err")
        self.assertEqual(self.run_harness("config", 'Testowa "10"')[0], "err")


if __name__ == "__main__":
    unittest.main()
