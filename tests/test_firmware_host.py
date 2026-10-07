# SPDX-License-Identifier: MIT
"""Host checks of Arduino-free firmware units: the P1 CRC, the test frame, the FRAM journal, the P1 frame codec,
the screen model with its texts and the bitmap font, the SA1 codec, the FRAM store and the USB protocol."""

from pathlib import Path
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "firmware" / "src"
sys.path.insert(0, str(ROOT / "software" / "reference"))
from reference import (MAX_CONTENT, PREFIX, check_button_configuration, crc16, encode_message, fragment,  # noqa: E402
                       status_after)

sys.path.insert(0, str(ROOT / "firmware" / "tools"))
import ui_texts  # noqa: E402

HARNESS = r"""
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include "crc16.h"
#include "journal.h"
#include "p1frame.h"
#include "testframe.h"
#include "font.h"
#include "ui.h"
#include "sa1.h"
#include "store.h"
#include "usbproto.h"
#include "station.h"
#include "console.h"
#include <string>

// FRAM w RAM: 512 KiB skasowane do 0xFF jak nowy układ.
struct RamStorage : journal::Storage {
    std::vector<uint8_t> bytes = std::vector<uint8_t>(512 * 1024, 0xFF);
    size_t readBytes = 0;  // licznik odczytów (koszt SPI przy rysowaniu ekranu)
    bool read(uint32_t address, uint8_t* data, size_t count) override {
        if (address + count > bytes.size()) return false;
        memcpy(data, &bytes[address], count);
        readBytes += count;
        return true;
    }
    bool write(uint32_t address, const uint8_t* data, size_t count) override {
        if (address + count > bytes.size()) return false;
        memcpy(&bytes[address], data, count);
        return true;
    }
};

int journalScenario() {
    RamStorage ram;
    journal::Journal j(ram);
    // Wywołania ze skutkami poza argumentami printf: kolejność argumentów zależy od kompilatora.
    const bool begun = j.begin();
    printf("fresh %d %d %u %u %u\n", begun, j.debtFresh(), j.debtValid(), j.clock().seq, j.eventSeq());
    const bool first = j.writeDebt(16228, 10);
    const bool second = j.writeDebt(5000, 20);
    printf("write %d %d\n", first, second);
    journal::Journal j2(ram);
    j2.begin();
    printf("reread %u %u %u %u\n", j2.debt().seq, j2.debt().a, j2.debt().b, j2.debtValid());
    // Zanik zasilania: treść rekordu 3 bez znacznika zatwierdzenia.
    journal::SmallRecord lost; lost.seq = 3; lost.a = 999; lost.b = 30;
    uint8_t body[journal::SMALL_RECORD];
    journal::encodeSmall(lost, body);
    ram.write(journal::DEBT_BASE + (3 % journal::DEBT_SLOTS) * journal::SMALL_RECORD, body, sizeof(body));
    journal::Journal j3(ram);
    j3.begin();
    printf("uncommitted %u %u %u\n", j3.debt().seq, j3.debt().a, j3.debtValid());
    // Uszkodzony bajt rekordu 2: zostaje rekord 1.
    ram.bytes[journal::DEBT_BASE + (2 % journal::DEBT_SLOTS) * journal::SMALL_RECORD + 5] ^= 0x01;
    journal::Journal j4(ram);
    j4.begin();
    printf("corrupt %u %u %u\n", j4.debt().seq, j4.debt().a, j4.debtValid());
    // Pierścień długu: po 40 zapisach 32 poprawne rekordy, najnowszy numer 41.
    for (int i = 0; i < 40; ++i) j4.writeDebt(100 + i, 40 + i);
    journal::Journal j5(ram);
    j5.begin();
    printf("ring %u %u %u\n", j5.debt().seq, j5.debt().a, j5.debtValid());
    // Zegar i zdarzenia z zawinięciem bufora 512 wpisów.
    printf("clock %d\n", j5.writeClock(100, 3));
    for (int i = 1; i <= 600; ++i) { char text[16]; snprintf(text, sizeof(text), "e%d", i); j5.writeEvent(i, text); }
    journal::Journal j6(ram);
    j6.begin();
    journal::EventRecord e0, e511, e512;
    const bool r0 = j6.readEvent(0, e0), r511 = j6.readEvent(511, e511), r512 = j6.readEvent(512, e512);
    printf("events %u %u %u %d %s %d %s %d\n", j6.clock().a, j6.clock().b, j6.eventSeq(), r0, e0.text, r511, e511.text, r512);
    // Długi tekst zdarzenia jest obcinany do 53 znaków.
    j6.writeEvent(7, "0123456789012345678901234567890123456789012345678901234567890123456789");
    journal::EventRecord longest;
    j6.readEvent(0, longest);
    printf("long %zu\n", strlen(longest.text));
    return 0;
}

void printHex(const uint8_t* data, size_t length) {
    for (size_t i = 0; i < length; ++i) printf("%02X", data[i]);
}

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

// Model ekranu sterowany z wejścia: "L <0-2>" język po restarcie, "S <0-2>" start z wyborem języka,
// "K <UP|DOWN|OK|BACK> <ms>" przycisk, "T <ms>" bezczynność, "P <0|1>" tryb przygotowania,
// "Q <0|1>" cisza, "O <0|1>" radio, "U <s>" kontakt, "N <n>" nowe, "C <n> <s>" kolejka,
// "V <mV>" napięcie, "X <rxok> <rxbad> <tx> <drop> <defer> <debt_ms>", "F <hz>" odchyłka,
// "R" wypisuje ekran, "W <tekst>" łamie tekst, "D <s>" formatuje czas, "G <tekst>" sprawdza glify.
// Ekran sterowany z wejścia. Bez "H" model działa bez stacji (sam ekran); "H" dołącza magazyn w RAM,
// warstwę aplikacji i konsolę: "A <adres>" konfiguracja (OSP 0xCC.., 2 stacje), "I <sa1>" wiadomość od OSP,
// "E <ack 0|1>" krok łącza (nadanie z kolejki, potwierdzenie łącza od OSP), "Y <s>" czas pracy,
// "KD/KU <przycisk> <ms>" naciśnięcie i zwolnienie, "M" lista WIADOMOŚCI, "J" kolejka.
struct UiServices : station::Services {
    uint32_t uptime = 100;
    bool silence_ = false;
    std::vector<uint8_t> air;
    uint8_t counter = 0;
    uint32_t uptimeS() override { return uptime; }
    bool silence() override { return silence_; }
    bool radioReady() override { return true; }
    bool busy() override { return !air.empty(); }
    bool send(const uint8_t* data, size_t length) override {
        printf("-> %.*s\n", static_cast<int>(length), reinterpret_cast<const char*>(data));
        air.assign(data, data + length);
        return true;
    }
    void randomBytes(uint8_t* out, size_t count) override { for (size_t i = 0; i < count; ++i) out[i] = static_cast<uint8_t>(0x30 + (++counter)); }
    void log(const char* text) override { printf("log %s\n", text); }
    bool notify(uint8_t kind, uint32_t ref, const char* fields) override { printf("event %u %u %s\n", kind, ref, fields); return true; }
    void address(uint8_t* out) override { memset(out, 0xAB, store::HASH); }
};

int uiScript() {
    ui::Model model;
    model.start(ui::Lang::PL);
    ui::Status status;
    status.version = "bench-a-test";
    status.name = "WICI-000000";
    const char* const names[] = {"UP", "DOWN", "OK", "BACK"};
    RamStorage ram;
    journal::Journal journal(ram);
    store::Store store(ram);
    UiServices services;
    station::Station app(store, services);
    console::Console con(store, app, services, &journal);
    bool hosted = false;
    char line[1024];
    while (fgets(line, sizeof(line), stdin)) {
        unsigned a = 0, b = 0, c = 0, d = 0, e = 0, f = 0;
        char word[16];
        char* nl = strchr(line, '\n');
        if (nl) *nl = '\0';
        if (sscanf(line, "L %u", &a) == 1) model.restore(static_cast<ui::Lang>(a), ui::Screen::MAIN);
        else if (sscanf(line, "S %u", &a) == 1) model.start(static_cast<ui::Lang>(a));
        else if (!strcmp(line, "H")) {
            journal.begin();
            store.begin();
            model.attach(&con);
            hosted = true;
        } else if (!strncmp(line, "A ", 2)) {
            store::Config cfg;
            cfg.role = store::STATION;
            cfg.stations = 2;
            strncpy(cfg.address, line + 2, store::ADDRESS_MAX);
            memset(cfg.osp[0], 0xCC, store::HASH);
            memset(cfg.osp[1], 0xDD, store::HASH);
            printf("config %d\n", store.writeConfig(cfg));
            con.invalidate();
        } else if (!strncmp(line, "I ", 2)) {
            char datagram[700];
            snprintf(datagram, sizeof(datagram), "[\"WICI\",1,\"%s\",\"%s\",%s]",
                     "cccccccccccccccccccccccccccccccc", "abababababababababababababababab", line + 2);
            app.received(reinterpret_cast<const uint8_t*>(datagram), strlen(datagram));
            con.invalidate();
        } else if (sscanf(line, "E %u", &a) == 1) {
            app.poll(services.uptime * 1000);
            if (!services.air.empty()) {
                std::vector<uint8_t> sent = services.air;
                services.air.clear();
                app.txDone(true);
                if (a) {
                    // Potwierdzenie łącza od OSP dla nadanego datagramu: id, revision, typ z treści SA1.
                    std::string text(sent.begin(), sent.end());
                    const size_t payload = text.find(",[", 70);
                    sa1::Message m;
                    if (payload != std::string::npos && !sa1::decode(text.c_str() + payload + 1, text.size() - payload - 2, m)) {
                        char ack[200];
                        snprintf(ack, sizeof(ack), "[\"WICI\",1,\"%s\",\"%s\",\"ack\",\"%s\",%u,%u,%u]",
                                 "cccccccccccccccccccccccccccccccc", "abababababababababababababababab", m.id, m.revision, m.type,
                                 m.type == sa1::STATUS || m.type == sa1::REPLY || m.type == sa1::BULLETIN ? m.event : 0);
                        app.received(reinterpret_cast<const uint8_t*>(ack), strlen(ack));
                    }
                }
            }
            con.invalidate();
        } else if (!strcmp(line, "LED")) printf("alarm_cause %d\n", app.alarmCause(services.uptime));
        else if (sscanf(line, "Y %u", &a) == 1) services.uptime = a;
        else if (sscanf(line, "KD %15s %u", word, &a) == 2 || sscanf(line, "KU %15s %u", word, &a) == 2) {
            size_t i = 0;
            while (i < 4 && strcmp(word, names[i])) ++i;
            if (i < 4) { if (line[1] == 'D') model.down(static_cast<ui::Button>(i), a); else model.up(static_cast<ui::Button>(i), a); }
        } else if (sscanf(line, "K %15s %u", word, &a) == 2) {
            size_t i = 0;
            while (i < 4 && strcmp(word, names[i])) ++i;
            if (i < 4) model.press(static_cast<ui::Button>(i), a);
        } else if (sscanf(line, "T %u", &a) == 1) model.tick(a);
        else if (sscanf(line, "P %u", &a) == 1) status.prep = a;
        else if (sscanf(line, "Q %u", &a) == 1) { status.silence = a; services.silence_ = a; }
        else if (sscanf(line, "O %u", &a) == 1) status.radioOk = a;
        else if (sscanf(line, "U %u", &a) == 1) status.contactS = a;
        else if (sscanf(line, "N %u", &a) == 1) status.newMessages = a;
        else if (sscanf(line, "C %u %u", &a, &b) == 2) { status.queued = a; status.queueAgeS = b; }
        else if (sscanf(line, "V %u", &a) == 1) status.millivolts = static_cast<uint16_t>(a);
        else if (sscanf(line, "X %u %u %u %u %u %u", &a, &b, &c, &d, &e, &f) == 6) {
            status.rxOk = a; status.rxBad = b; status.txDatagrams = c; status.txDrop = d; status.deferrals = e; status.debtMs = f;
        } else if (sscanf(line, "F %u", &a) == 1) { status.foffValid = true; status.foffHz = static_cast<int32_t>(a); }
        else if (!strcmp(line, "M")) {
            const size_t count = con.itemCount();
            printf("items %zu\n", count);
            for (size_t i = 0; i < count; ++i) {
                ui::Item item;
                if (!con.item(i, item)) continue;
                printf("item %u %d %u %04u %u %u %u %u %u %d %d |%s\n", item.ref, item.own, item.type, item.number, item.category, item.people,
                       item.urgency, item.state, item.attempts, item.cancelled, item.unread, item.text);
            }
        } else if (!strcmp(line, "B")) {
            printf("read %zu\n", ram.readBytes);
            ram.readBytes = 0;
        } else if (!strcmp(line, "J")) {
            printf("queue live %zu unsent %zu configured %d paused %d\n", store.queueLive(), store.queueUnsent(), store.configured(), app.testPaused());
            for (size_t i = 0; i < store.queueSize(); ++i) {
                const store::QueueEntry* q = store.queueEntry(i);
                if (!q) continue;
                store::QueueRecord r;
                store.queueRead(q->seq, r);
                printf("intent %u type %u rev %u flags %u attempts %u next %u state %u number %04u sa1 %s\n", q->seq, q->type, q->revision,
                       q->flags, q->attempts, q->nextTryS, q->state, store::shortNumber(q->id), r.sa1);
            }
        } else if (line[0] == 'R') {
            if (hosted) status.newMessages = static_cast<uint32_t>(store.inboxUnread());
            ui::Lines lines;
            model.render(status, lines);
            printf("screen %s %d\n", ui::screenName(model.screen()), static_cast<int>(model.language()));
            for (size_t i = 0; i < ui::LINES; ++i) printf("%d|%s\n", lines.inverted[i], lines.text[i]);
        } else if (line[0] == 'W') {
            char out[8][ui::LINE_BYTES];
            const size_t n = ui::wrap(line + 2, out, 8);
            printf("wrap %zu\n", n);
            for (size_t i = 0; i < n; ++i) printf("|%s\n", out[i]);
        } else if (sscanf(line, "D %u", &a) == 1) {
            char out[3][24];
            for (size_t l = 0; l < 3; ++l) ui::duration(a, static_cast<ui::Lang>(l), out[l], sizeof(out[l]));
            printf("%s|%s|%s\n", out[0], out[1], out[2]);
        } else if (line[0] == 'G') {
            const char* p = line + 2;
            size_t missing = 0, total = 0;
            for (uint32_t cp = font::next(p); cp; cp = font::next(p)) { ++total; if (!font::has(cp)) ++missing; }
            printf("glyphs %zu %zu\n", total, missing);
        }
    }
    return 0;
}

struct TestHost : usbproto::Host {
    bool prep_ = true, silence_ = false, confirm_ = true;
    uint32_t uptime_ = 100;
    uint8_t counter_ = 0;
    uint32_t uptimeS() override { return uptime_; }
    bool prep() override { return prep_; }
    bool silence() override { return silence_; }
    void setSilence(bool on) override { silence_ = on; }
    bool confirm() override { return confirm_; }
    void randomBytes(uint8_t* out, size_t n) override { for (size_t i = 0; i < n; ++i) out[i] = static_cast<uint8_t>(++counter_); }
    void log(const char* text) override { printf("log %s\n", text); }
    void emit(const char* line) override { printf("<- %s\n", line); }
    void stationAddress(uint8_t* out) override { memset(out, 0xAB, store::HASH); }
    const char* stationName() override { return "WICI-TEST00"; }
    const char* version() override { return "host"; }
};

// Protokół USB sterowany z wejścia: "> <json>" wiersz od laptopa, "E <kind> <pola>" zdarzenie stacji,
// "T <ms>" poll, "C <ms>" połączenie, "D" rozłączenie, "P <0|1>" tryb przygotowania, "K <0|1>" potwierdzenie,
// "U <s>" czas pracy, "R" restart stacji (ta sama pamięć), "Z <adres> <bajt>" uszkodzenie bajtu FRAM,
// "S" stan magazynu, "Q <seq>" rekord kolejki.
int usbScript() {
    RamStorage ram;
    TestHost host;
    store::Store* store = new store::Store(ram);
    store->begin();
    usbproto::Protocol* proto = new usbproto::Protocol(*store, host);
    proto->begin();
    char line[2048];
    while (fgets(line, sizeof(line), stdin)) {
        char* nl = strchr(line, '\n');
        if (nl) *nl = '\0';
        unsigned a = 0, b = 0;
        if (line[0] == '>' && line[1] == ' ') { proto->feed(line + 2, strlen(line + 2), 1000); proto->feed("\n", 1, 1000); }
        else if (line[0] == 'E') { unsigned kind = 0; int offset = 0; sscanf(line, "E %u %n", &kind, &offset); printf("event %d\n", proto->event(static_cast<uint8_t>(kind), 0, line + offset, 1000)); }
        else if (sscanf(line, "T %u", &a) == 1) proto->poll(a);
        else if (sscanf(line, "C %u", &a) == 1) proto->connected(a);
        else if (line[0] == 'D') proto->disconnected();
        else if (sscanf(line, "P %u", &a) == 1) host.prep_ = a;
        else if (sscanf(line, "K %u", &a) == 1) host.confirm_ = a;
        else if (sscanf(line, "U %u", &a) == 1) host.uptime_ = a;
        else if (line[0] == 'R') {
            delete proto; delete store;
            store = new store::Store(ram); printf("begin %d\n", store->begin());
            proto = new usbproto::Protocol(*store, host); proto->begin();
        } else if (sscanf(line, "Z %u %u", &a, &b) == 2) ram.bytes[a] = static_cast<uint8_t>(b);
        else if (line[0] == 'S') printf("store live %zu inbox %zu pending %zu latest %u configured %d address %s\n", store->queueLive(), store->inboxCount(), store->notesPending(), store->noteLatest(), store->configured(), store->config().address);
        else if (sscanf(line, "Q %u", &a) == 1) { store::QueueRecord r; if (store->queueRead(a, r)) printf("queue %u flags %u attempts %u %s\n", r.seq, r.flags, r.attempts, r.sa1); else printf("queue none\n"); }
    }
    delete proto; delete store;
    return 0;
}

// Dwie stacje (A: rola stacji, B: rola OSP) połączone "eterem" bez strat albo ze stratami;
// każda ma własną FRAM w RAM, magazyn, protokół USB i warstwę aplikacji.
struct Node;
struct LinkServices : station::Services {
    Node* node = nullptr;
    uint32_t uptimeS() override;
    bool silence() override;
    bool radioReady() override { return true; }
    bool busy() override;
    bool send(const uint8_t* data, size_t length) override;
    void randomBytes(uint8_t* out, size_t count) override;
    void log(const char* text) override;
    bool notify(uint8_t kind, uint32_t ref, const char* fields) override;
    void address(uint8_t* out) override;
};
struct Node {
    char name;
    RamStorage ram;
    TestHost host;
    store::Store* store = nullptr;
    usbproto::Protocol* proto = nullptr;
    LinkServices services;
    station::Station* app = nullptr;
    Node* peer = nullptr;
    uint32_t uptime = 100;
    bool lossy = false;
    std::vector<uint8_t> air;  // datagram w drodze (dostarczany przy następnym kroku czasu)
    bool txBusy = false;
    uint8_t addr;
    void start() {
        store = new store::Store(ram); store->begin();
        proto = new usbproto::Protocol(*store, host); proto->begin(); proto->connected(0);
        services.node = this;
        app = new station::Station(*store, services);
    }
    void restart() { delete app; delete proto; delete store; start(); }
};
uint32_t LinkServices::uptimeS() { return node->uptime; }
bool LinkServices::silence() { return node->host.silence_; }
bool LinkServices::busy() { return node->txBusy; }
bool LinkServices::send(const uint8_t* data, size_t length) {
    printf("%c-> %.*s\n", node->name, static_cast<int>(length), reinterpret_cast<const char*>(data));
    node->air.assign(data, data + length);
    node->txBusy = true;
    return true;
}
void LinkServices::randomBytes(uint8_t* out, size_t count) { for (size_t i = 0; i < count; ++i) out[i] = static_cast<uint8_t>(0x55 + i + node->name); }
void LinkServices::log(const char* text) { printf("%c:log %s\n", node->name, text); }
bool LinkServices::notify(uint8_t kind, uint32_t ref, const char* fields) { return node->proto->event(kind, ref, fields, node->uptime * 1000); }
void LinkServices::address(uint8_t* out) { memset(out, node->addr, store::HASH); }

int linkScript() {
    Node a, b;
    a.name = 'A'; a.addr = 0xAA; a.host = TestHost(); b.name = 'B'; b.addr = 0xBB;
    a.peer = &b; b.peer = &a;
    // Emisje USB z nazwą węzła.
    struct NamedHost : TestHost { char name; void emit(const char* line) override { printf("%c<- %s\n", name, line); } void log(const char* text) override { printf("%c:log %s\n", name, text); } };
    static NamedHost ha, hb; ha.name = 'A'; hb.name = 'B';
    // Zastąpienie hosta: protokół bierze referencję, więc tworzymy węzły z nazwanymi hostami.
    Node* nodes[2] = {&a, &b};
    NamedHost* hosts[2] = {&ha, &hb};
    for (int i = 0; i < 2; ++i) {
        Node& n = *nodes[i];
        n.store = new store::Store(n.ram); n.store->begin();
        n.proto = new usbproto::Protocol(*n.store, *hosts[i]); n.proto->begin(); n.proto->connected(0);
        const char* sync = "{\"usb\":1,\"seq\":0,\"type\":\"sync\",\"boot\":\"laptop\",\"cursor\":0}\n";
        n.proto->feed(sync, strlen(sync), 0);
        n.services.node = &n;
        n.app = new station::Station(*n.store, n.services);
    }
    char line[2048];
    while (fgets(line, sizeof(line), stdin)) {
        char* nl = strchr(line, '\n');
        if (nl) *nl = '\0';
        unsigned v = 0;
        Node* n = line[0] == 'A' ? &a : line[0] == 'B' ? &b : nullptr;
        if (n && line[1] == ' ') { n->proto->feed(line + 2, strlen(line + 2), n->uptime * 1000); n->proto->feed("\n", 1, n->uptime * 1000); }
        else if (sscanf(line, "T %u", &v) == 1) {
            // Krok czasu: koniec nadawania, dostarczenie datagramów, poll obu stron.
            for (Node* x : nodes) {
                x->uptime = v;
                if (x->txBusy) { x->txBusy = false; x->app->txDone(true); }
                if (!x->air.empty()) {
                    std::vector<uint8_t> d = x->air; x->air.clear();
                    if (!x->lossy) x->peer->app->received(d.data(), d.size()); else printf("%c-> lost\n", x->name);
                }
            }
            for (Node* x : nodes) x->app->poll(v * 1000);
        } else if (sscanf(line, "L %u", &v) == 1) a.lossy = b.lossy = v;
        else if (sscanf(line, "Q %u", &v) == 1) { a.host.silence_ = v; }
        else if (line[0] == 'R' && line[1] == 'A') {
            delete a.app; delete a.proto; delete a.store;
            a.store = new store::Store(a.ram); a.store->begin();
            a.proto = new usbproto::Protocol(*a.store, ha); a.proto->begin(); a.proto->connected(0);
            const char* sync = "{\"usb\":1,\"seq\":0,\"type\":\"sync\",\"boot\":\"laptop\",\"cursor\":0}\n";
            a.proto->feed(sync, strlen(sync), 0);
            a.app = new station::Station(*a.store, a.services);
        } else if (line[0] == 'S') {
            for (Node* x : nodes) {
                const station::Stats& s = x->app->stats();
                printf("%c stats sent %u delivered %u failed %u received %u rejected %u duplicates %u conflicts %u acks %u confirmed %u live %zu unsent %zu inbox %zu unread %zu\n",
                       x->name, s.sent, s.delivered, s.failed, s.received, s.rejected, s.duplicates, s.conflicts, s.acksSent, s.confirmed,
                       x->store->queueLive(), x->store->queueUnsent(), x->store->inboxCount(), x->store->inboxUnread());
            }
        } else if (line[0] == 'X') {
            for (Node* x : nodes) {
                for (size_t i = 0; i < x->store->queueSize(); ++i) {
                    const store::QueueEntry* e = x->store->queueEntry(i);
                    if (!e) continue;
                    store::QueueRecord r; x->store->queueRead(e->seq, r);
                    printf("%c queue %u type %u flags %u attempts %u next %u event %u state %u\n", x->name, r.seq, r.type, r.flags, r.attempts, r.nextTryS, r.statusEvent, r.state);
                }
            }
        } else if (sscanf(line, "D %u", &v) == 1) {
            // Harmonogram ponowień dla kolejnych prób z losową liczbą v.
            for (unsigned attempts = 0; attempts < 6; ++attempts) printf("%u ", a.app->retryDelayS(static_cast<uint16_t>(attempts), false, 0, v));
            printf("| %u %u\n", a.app->retryDelayS(1, false, 7 * 3600, v), a.app->retryDelayS(2, true, 0, v));
        }
    }
    for (Node* x : nodes) { delete x->app; delete x->proto; delete x->store; }
    return 0;
}

int main(int argc, char** argv) {
    if (argc == 2 && !strcmp(argv[1], "ui")) return uiScript();
    if (argc == 2 && !strcmp(argv[1], "link")) return linkScript();
    if (argc == 2 && !strcmp(argv[1], "usb")) return usbScript();
    if (argc == 3 && !strcmp(argv[1], "sa1")) {
        sa1::Message m;
        const char* why = sa1::decode(argv[2], strlen(argv[2]), m);
        if (why) { printf("err %s\n", why); return 0; }
        char out[sa1::MAX_CONTENT + 1];
        const size_t n = sa1::encode(m, out, sizeof(out));
        printf("ok %zu %s\n", n, n ? out : "");
        return 0;
    }
    if (argc == 6 && !strcmp(argv[1], "status")) {
        uint32_t e = 0; uint8_t s = 0;
        const char* why = sa1::statusAfter(strtoul(argv[2], nullptr, 10), static_cast<uint8_t>(atoi(argv[3])), strtoul(argv[4], nullptr, 10), static_cast<uint8_t>(atoi(argv[5])), e, s);
        if (why) printf("err %s\n", why); else printf("ok %u %u\n", e, s);
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
    if (argc == 4 && !strcmp(argv[1], "frame")) {
        uint8_t frame[testframe::MAX_LENGTH];
        const size_t length = strtoul(argv[2], nullptr, 10);
        const uint16_t seq = strtoul(argv[3], nullptr, 10);
        if (!testframe::build(frame, length, seq)) { printf("build failed\n"); return 1; }
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


def compiler():
    for name in ("c++", "g++", "clang++"):
        path = shutil.which(name)
        if path:
            return path
    return None


@unittest.skipUnless(compiler(), "no host C++ compiler")
class HostUnitTests(unittest.TestCase):
    """Compile crc16.h and testframe.cpp with the host compiler and compare with the model."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        (root / "harness.cpp").write_text(HARNESS, encoding="utf-8")
        cls.binary = root / "harness"
        subprocess.run([compiler(), "-std=c++17", "-Wall", "-Wextra", "-Werror", f"-I{SRC}", str(root / "harness.cpp"),
                        str(SRC / "testframe.cpp"), str(SRC / "journal.cpp"), str(SRC / "p1frame.cpp"), str(SRC / "ui.cpp"),
                        str(SRC / "font.cpp"), str(SRC / "jsonlite.cpp"), str(SRC / "sa1.cpp"), str(SRC / "store.cpp"),
                        str(SRC / "usbproto.cpp"), str(SRC / "station.cpp"), str(SRC / "console.cpp"), "-o", str(cls.binary)],
                       check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_harness(self, *args):
        return subprocess.run([str(self.binary), *args], capture_output=True, text=True, check=True).stdout.split()

    def test_crc_matches_spec_vector_and_model(self):
        self.assertEqual(self.run_harness("crc", "123456789"), ["29B1"])
        for text in ("", "A", "WICI 0.5"):
            self.assertEqual(int(self.run_harness("crc", text)[0] if text else "FFFF", 16), crc16(text.encode()))

    def test_frame_round_trip_and_corruption(self):
        for length, seq in ((4, 0), (18, 1), (103, 65535), (50, 1234)):
            frame_hex, ok, back, corrupt = self.run_harness("frame", str(length), str(seq))
            frame = bytes.fromhex(frame_hex)
            self.assertEqual(len(frame), length)
            self.assertEqual(int.from_bytes(frame[:2], "big"), seq)
            self.assertEqual(int.from_bytes(frame[-2:], "big"), crc16(frame[:-2]))
            self.assertEqual((ok, int(back), corrupt), ("ok", seq, "rejected"), (length, seq))

    def test_filler_depends_on_sequence_and_is_not_constant(self):
        a = bytes.fromhex(self.run_harness("frame", "40", "7")[0])
        b = bytes.fromhex(self.run_harness("frame", "40", "8")[0])
        self.assertNotEqual(a[2:-2], b[2:-2])
        self.assertGreater(len(set(a[2:-2])), 10)

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
        out = subprocess.run([str(self.binary), "assemble"], input="\n".join(script) + "\n", capture_output=True,
                             text=True, check=True).stdout.splitlines()
        return out

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

    def test_journal_scenario(self):
        lines = subprocess.run([str(self.binary), "journal"], capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertEqual(lines, [
            "fresh 1 1 0 0 0",
            "write 1 1",
            "reread 2 5000 20 2",
            "uncommitted 2 5000 2",
            "corrupt 1 16228 1",
            "ring 41 139 32",
            "clock 1",
            "events 100 3 600 1 e600 1 e89 0",
            "long 53",
        ])

    def ui(self, script):
        return subprocess.run([str(self.binary), "ui"], input="\n".join(script) + "\n", capture_output=True, text=True,
                              check=True).stdout.splitlines()

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
        menu = [strings[0] for _, strings in data["menu"]]
        out = self.ui(["L 0", "O 1", "X 12 3 4 1 7 16228", "F 123", "K OK 0", "R", "K DOWN 0", "K DOWN 0", "K DOWN 0", "R",
                       "K OK 0", "R"] + ["K DOWN 0"] * 12 + ["R",
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
        self.assertEqual(status_end[-2:], ["bench-a-test", "WICI-000000"])
        self.assertIn("FOFF +123 HZ", status_end)
        self.assertEqual([inv for inv, _ in screens[4][2]], [False, False, False, True, False])  # kursor wraca na STAN
        self.assertEqual([t for _, t in screens[5][2]][:3], ["POLSKI", "УКРАЇНСЬКА", "ENGLISH"])
        self.assertEqual(screens[6][1], 2)  # wybrano ENGLISH, powrót do menu
        self.assertEqual([t for _, t in screens[6][2]], [strings[2] for _, strings in data["menu"]])
        self.assertEqual([t for _, t in screens[8][2]][0], "MEDICAL HELP")  # kreator: kategoria 0 w języku EN
        self.assertEqual(screens[9][0], "category")   # 179 999 ms bez naciśnięcia: ekran zostaje
        self.assertEqual(screens[10][0], "main")  # 3 min bezczynności: ekran główny

    HOSTED = ["H", "A Szkoła, wejście B", "L 0", "O 1"]
    REQUEST_ID = "3132333435363738393a3b3c3d3e3f40"  # pierwsze 16 bajtów z generatora programu testowego

    @staticmethod
    def wire(message):
        return encode_message(message).decode()

    def assertHas(self, text, out):
        """Jakiś wiersz wyjścia zawiera tekst (rekordy kolejki i listy mają dalsze pola)."""
        self.assertTrue(any(text in line for line in out), text)

    def assertShows(self, screen, text):
        """Okno 5 wierszy pokazuje początek tekstu (dłuższy tekst przewija się)."""
        shown = " ".join(self.lines(screen)).strip()
        self.assertTrue(text.startswith(shown) and shown, (shown, text))

    def hosted(self, script):
        return self.ui(self.HOSTED + script)

    @staticmethod
    def lines(screen):
        return [t for _, t in screen[2]]

    def test_startup_address_check_and_test_offer(self):
        texts = ui_texts.load()["texts"]
        out = self.ui(["H", "A Szkoła, wejście B", "S 0", "O 1", "K OK 0", "R", "K BACK 0", "R", "K OK 0", "R", "K OK 0", "R", "J",
                       "K BACK 0", "R", "J"])
        address, missing, offer, test, menu = self.screens(out)
        self.assertEqual(address[0], "address")
        self.assertEqual(" ".join(self.lines(address)).strip(), texts["adres_kontrola"][0].replace("[x]", "Szkoła, wejście B"))
        self.assertEqual(" ".join(self.lines(missing)).strip(), texts["adres_brak"][0])  # WSTECZ = NIE
        self.assertEqual(offer[0], "test_offer")
        self.assertEqual(test[0], "test")
        self.assertIn("log startup test scheduled", out)
        # TEST startowy: losowe opóźnienie w oknie 50 s x 2 stacje, ekran test_zaplanowany, WSTECZ anuluje.
        intents = [line for line in out if line.startswith("intent ")]
        self.assertEqual(len(intents), 2)
        self.assertHas("type 5 rev 0 flags 1 attempts 0 next 161", intents[:1])
        self.assertEqual(" ".join(self.lines(test)).strip(), texts["test_zaplanowany"][0].replace("[mm]", "2"))
        self.assertIn("log test cancelled", out)
        self.assertHas("type 5 rev 0 flags 8", intents[1:])
        self.assertEqual(menu[0], "menu")

    def test_wizard_creates_request_with_phrase_and_short_number(self):
        data = ui_texts.load()
        texts = data["texts"]
        script = ["K OK 0", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0", "R", "K DOWN 0", "K DOWN 0", "K OK 0", "R", "K OK 0", "R",
                  "K DOWN 0", "R", "K DOWN 0", "K OK 0", "R", "K DOWN 0", "K OK 0", "R", "K OK 0", "R", "J", "M", "K OK 0", "R",
                  "E 1", "J", "M"]
        out = self.hosted(script)
        people, urgency, still, picked, phrase, summary, result, main = self.screens(out)
        self.assertEqual(people[0], "people")
        self.assertEqual(self.lines(people), ["1", "2", "5", "10", "20"])
        self.assertEqual(urgency[0], "urgency")
        self.assertEqual(self.lines(urgency)[:3], [texts["pilnosc_2"][0], texts["pilnosc_1"][0], texts["pilnosc_0"][0]])
        self.assertFalse(any(inv for inv, _ in urgency[2]))  # pilność bez wartości domyślnej
        self.assertEqual(still[0], "urgency")                 # OK bez wyboru nic nie robi
        self.assertEqual([inv for inv, _ in picked[2]], [True, False, False, False, False])
        self.assertEqual(phrase[0], "phrase")
        self.assertEqual(self.lines(phrase)[:2], ["-", data["phrases"][0][0]])
        self.assertEqual(summary[0], "summary")
        self.assertEqual(self.lines(summary)[:3], [data["categories"][2][0], "5 " + texts["pilnosc_1"][0][:18], data["phrases"][0][0]])
        self.assertEqual(result[0], "result")
        self.assertEqual(" ".join(self.lines(result)).strip(),
                         texts["zapisane_w_stacji"][0] + " " + texts["zapisz_numer"][0].replace("[xxxx]", "2594"))
        self.assertEqual(main[0], "main")
        self.assertIn("log request 2594 created", out)
        sa1 = [1, 0, self.REQUEST_ID, 0, 2, 5, "Szkoła, wejście B", "osoba na wózku", 1]
        self.assertIn("intent 1 type 0 rev 0 flags 1 attempts 0 next 0 state 0 number 2594 sa1 " + self.wire(sa1), out)
        self.assertIn("item 1 1 0 2594 2 5 1 0 0 0 0 |osoba na wózku", out)
        self.assertTrue(any(line.startswith('-> ["WICI",1,"abab') and line.endswith(self.wire(sa1) + "]") for line in out))
        self.assertHas("intent 1 type 0 rev 0 flags 17 attempts 1 next 700", out)  # dostarczone: 10 min na RECEIVED

    def test_digits_hold_repeat_discard_and_language_hold(self):
        texts = ui_texts.load()["texts"]
        script = ["K OK 0", "K OK 0", "K OK 0"] + ["K DOWN 0"] * 7 + ["R", "K OK 0", "R", "K UP 0", "K UP 0", "K OK 0", "K OK 0",
                  "K DOWN 0", "K DOWN 0", "R", "KD UP 1000", "T 1400", "T 1600", "T 1900", "KU UP 1900", "R", "K OK 0", "R",
                  "KD BACK 2000", "T 3000", "R", "T 4100", "R", "KU BACK 4200", "R", "K BACK 0", "R", "KD BACK 5000", "T 7100",
                  "R", "KU BACK 7100", "R", "K OK 0", "R", "KD BACK 8000", "T 11100", "KU BACK 11100", "R", "K BACK 0", "R",
                  "K UP 0", "K UP 0", "K UP 0", "K UP 0", "K OK 0", "K OK 0", "R"]
        out = self.hosted(script)
        s = self.screens(out)
        self.assertEqual([x[0] for x in s], ["people", "digits", "digits", "digits", "urgency", "urgency", "discard", "discard",
                                             "urgency", "discard", "discard", "main", "language_menu", "menu", "people"])
        self.assertEqual([inv for inv, _ in s[0][2]], [False, False, False, False, True])  # INNA
        self.assertEqual(self.lines(s[1])[1:3], ["0 0 1", "^"])
        self.assertEqual(self.lines(s[2])[1:3], ["2 0 9", "    ^"])
        self.assertEqual(self.lines(s[3])[1:3], ["2 0 2", "    ^"])  # przytrzymanie: 9 -> 0 od razu, potem co 150 ms
        self.assertEqual(" ".join(self.lines(s[6])).strip(), texts["porzucic"][0])
        self.assertEqual(s[8][0], "urgency")  # WSTECZ na ekranie porzucenia wraca do kroku
        self.assertEqual(s[12][1], 0)
        self.assertEqual(self.lines(s[12])[:3], ["POLSKI", "УКРАЇНСЬКА", "ENGLISH"])  # 3 s poza kreatorem
        self.assertEqual([inv for inv, _ in s[14][2]], [True, False, False, False, False])  # po porzuceniu: szkic skasowany

    def test_messages_item_menu_revision_and_cancel(self):
        data = ui_texts.load()
        texts = data["texts"]
        labels = {name.lower(): strings for name, strings in data["labels"].items()}
        create = ["K OK 0", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0", "K DOWN 0", "K DOWN 0",
                  "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0", "E 1",
                  "I [1,1,\"%s\",0,1,1]" % self.REQUEST_ID,
                  "I [1,3,\"%s\",0,1,\"Zadzwoń pod 112\"]" % self.REQUEST_ID,
                  "I [1,4,\"41424344454647484950515253545556\",7,\"Komunikat gminy: woda z beczkowozu o 10\"]"]
        script = create + ["K OK 0", "K DOWN 0", "K OK 0", "R", "M", "K OK 0", "R", "K DOWN 0", "K DOWN 0", "R", "K BACK 0",
                           "R", "K DOWN 0", "K DOWN 0", "K OK 0", "R", "K OK 0", "R", "K DOWN 0", "K DOWN 0", "K OK 0",
                           "R", "K OK 0", "R", "J", "M", "K OK 0", "K OK 0", "K DOWN 0", "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "R",
                           "K DOWN 0", "K DOWN 0", "K DOWN 0", "R", "K OK 0", "R", "J", "M"]
        out = self.hosted(script)
        s = self.screens(out)
        self.assertEqual([x[0] for x in s], ["messages", "item", "item", "messages", "item", "item_menu", "summary", "result",
                                             "item_menu", "item_menu", "messages"])
        self.assertEqual(self.lines(s[0]), ["*Komunikat gminy: wo", "*Zadzwoń pod 112", "2594 " + data["categories"][2][0][:15], "", ""])
        self.assertIn("items 3", out)
        # Komunikat: treść, czas od odbioru, stopka; otwarcie oznacza jako przeczytany.
        bulletin = " ".join(self.lines(s[1]) + self.lines(s[2]))
        self.assertIn("Komunikat gminy: woda z beczkowozu o 10", bulletin)
        self.assertIn("0 MIN", bulletin)
        self.assertEqual(self.lines(s[3])[0], " Komunikat gminy: wo")
        self.assertIn(texts["stopka_komunikatu"][0][:18], " ".join(self.lines(s[2])))
        # Własne zgłoszenie po RECEIVED: etap stan_1, kategoria, osoby i pilność, fraza, numer.
        own = " ".join(self.lines(s[4]))
        self.assertTrue(own.startswith(texts["stan_1"][0]))
        self.assertIn(data["categories"][2][0], own)
        self.assertEqual(self.lines(s[5]), [labels["zmien_liczbe_osob"][0], labels["zmien_pilnosc"][0], labels["potrzeba_ustala"][0], "", ""])
        self.assertEqual(self.lines(s[6])[2], data["phrases"][10][0])  # POTRZEBA USTAŁA: fraza w podsumowaniu
        self.assertIn("log request 2594 revision 1", out)
        revised = [1, 0, self.REQUEST_ID, 1, 2, 5, "Szkoła, wejście B", "potrzeba ustała", 1]
        self.assertIn("intent 2 type 0 rev 1 flags 1 attempts 0 next 0 state 0 number 2594 sa1 " + self.wire(revised), out)
        self.assertHas("intent 1 type 0 rev 0 flags 18 attempts 1", out)  # potwierdzona rewizja 0 zostaje zakończona, nie zastąpiona
        self.assertIn("item 2 1 0 2594 2 5 1 0 0 0 0 |potrzeba ustała", out)  # lista pokazuje najnowszą rewizję
        # Rewizja bez potwierdzenia: ANULUJ WYSYŁKĘ dostępne; po anulowaniu intencja nieaktywna.
        self.assertEqual(self.lines(s[8])[3], labels["anuluj_wysylke"][0])
        self.assertEqual([inv for inv, _ in s[9][2]], [False, False, False, True, False])
        self.assertIn("log request 2594 cancelled", out)
        self.assertHas("intent 2 type 0 rev 1 flags 8", out)
        self.assertIn("item 2 1 0 2594 2 5 1 0 0 1 0 |potrzeba ustała", out)

    def test_test_screen_menu_pause_and_resume(self):
        texts = ui_texts.load()["texts"]
        labels = {name.lower(): strings for name, strings in ui_texts.load()["labels"].items()}
        script = ["K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0", "R", "K OK 0", "R", "K OK 0", "R", "J", "E 1", "R",
                  "I [1,1,\"%s\",0,1,1]" % self.REQUEST_ID, "R", "K OK 0", "K DOWN 0", "R", "K OK 0", "R", "J", "K OK 0", "K DOWN 0",
                  "R", "K OK 0", "R", "K OK 0", "K OK 0", "R", "J"]
        out = self.hosted(script)
        s = self.screens(out)
        self.assertEqual([x[0] for x in s], ["test", "test_menu", "test", "test", "test", "test_menu", "test", "test_menu", "test",
                                             "test"])
        self.assertEqual(self.lines(s[0])[0], labels["test"][0])  # bez TEST: sama etykieta
        self.assertEqual(self.lines(s[1])[:2], [labels["test"][0], labels["wstrzymaj"][0]])
        self.assertEqual(" ".join(self.lines(s[2])).strip(), texts["test_zaplanowany"][0].replace("[mm]", "0"))  # z menu: od razu
        self.assertHas("intent 1 type 5 rev 0 flags 1 attempts 0 next 0", out)
        self.assertEqual(" ".join(self.lines(s[3])).strip(), texts["test_wyslany"][0])
        self.assertEqual(" ".join(self.lines(s[4])).strip(), texts["stan_1"][0])
        self.assertEqual(" ".join(self.lines(s[6])).strip(), texts["test_wstrzymany"][0])
        self.assertHas("paused 1", out)
        self.assertEqual(self.lines(s[7])[1], labels["wznow"][0])
        self.assertEqual(" ".join(self.lines(s[9])).strip(), texts["test_zaplanowany"][0].replace("[mm]", "0"))  # nowy TEST po WZNÓW
        self.assertHas("intent 2 type 5 rev 0 flags 1 attempts 0", out)

    def test_alarms_no_confirmation_then_no_read(self):
        texts = ui_texts.load()["texts"]
        create = ["K OK 0", "K OK 0", "K OK 0", "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0"]
        script = create + ["Y 999", "LED", "T 100000", "R", "Y 1000", "T 101000", "R", "K OK 0", "R", "LED", "T 102000", "R",
                           "I [1,1,\"%s\",0,1,1]" % self.REQUEST_ID, "Y 2799", "LED", "T 103000", "R", "Y 2800", "T 104000", "R",
                           "K OK 0", "R", "Y 9000", "T 105000", "R", "LED"]
        out = self.hosted(script)
        s = self.screens(out)
        self.assertEqual([x[0] for x in s], ["main", "alarm", "main", "main", "main", "alarm", "main", "main"])
        self.assertShows(s[1], texts["brak_potwierdzenia"][0].replace("[n]", "15") + " " + texts["zapisz_numer"][0].replace("[xxxx]", "2594"))
        self.assertShows(s[5], texts["brak_odczytu"][0] + " " + texts["zapisz_numer"][0].replace("[xxxx]", "2594"))
        # Dioda alarmu: przyczyna trwa po potwierdzeniu OK i znika dopiero z potwierdzeniem od odbiorcy.
        self.assertEqual([x for x in out if x.startswith("alarm_cause")],
                         ["alarm_cause 0", "alarm_cause 1", "alarm_cause 0", "alarm_cause 1"])

    def test_lists_render_from_the_ram_index(self):
        # Lista WIADOMOŚCI i PRZEKAZANIE ZMIANY korzystają ze skrótu z indeksu w RAM: rysowanie nie czyta rekordów
        # własnych zgłoszeń z FRAM; pełny rekord czyta się dopiero po otwarciu pozycji i dla treści odebranych.
        create = ["K OK 0", "K OK 0", "K OK 0", "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0"]
        script = create * 3 + ["I [1,4,\"41424344454647484950515253545556\",7,\"Komunikat\"]", "K OK 0", "K DOWN 0", "K OK 0", "R", "B",
                               "R", "B", "K OK 0", "R", "B", "K BACK 0", "K BACK 0", "K DOWN 0", "K DOWN 0", "K OK 0"] + \
                 ["K DOWN 0"] * 13 + ["K OK 0", "R", "B", "R", "B"]
        out = self.hosted(script)
        s = self.screens(out)
        self.assertEqual([x[0] for x in s], ["messages", "messages", "item", "handover", "handover"])
        reads = [int(line.split()[1]) for line in out if line.startswith("read ")]
        self.assertEqual(reads[1], 452)   # lista: jeden rekord skrzynki (część stała i stan) dla treści komunikatu
        self.assertGreaterEqual(reads[2], 452)  # otwarty komunikat: pełny rekord
        self.assertEqual(reads[4], 0)     # PRZEKAZANIE ZMIANY: wyłącznie indeks w RAM

    def test_services_backup_and_destroy_sequences(self):
        labels = {name.lower(): strings for name, strings in ui_texts.load()["labels"].items()}
        texts = ui_texts.load()["texts"]
        to_services = ["K OK 0", "K DOWN 0", "K DOWN 0", "K DOWN 0", "K OK 0"] + ["K DOWN 0"] * 14 + ["R", "K OK 0", "R"]
        # Po przełączeniu: zgłoszenie W CIĄGU DOBY bez frazy, nadane do zapasowej tożsamości; potem ZNISZCZ DANE.
        script = to_services + ["K OK 0", "R", "K UP 0", "K DOWN 0", "K UP 0", "K OK 0", "R", "K BACK 0", "K UP 0", "K UP 0", "K UP 0",
                                "K OK 0", "K OK 0", "K OK 0", "K UP 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0", "E 1", "J", "K OK 0",
                                "K DOWN 0", "K DOWN 0", "K DOWN 0", "K OK 0"] + ["K DOWN 0"] * 14 + \
                 ["K OK 0", "K DOWN 0", "K OK 0", "R", "K UP 0", "K DOWN 0", "K DOWN 0", "K UP 0", "R", "K UP 0", "K DOWN 0", "K UP 0",
                  "K OK 0", "R", "J"]
        out = self.hosted(script)
        s = self.screens(out)
        self.assertEqual([x[0] for x in s], ["status", "services", "backup", "status", "destroy", "destroy", "main"])
        self.assertEqual(self.lines(s[0])[-2:], [labels["przekazanie_zmiany"][0], labels["uslugi"][0]])
        self.assertEqual([inv for inv, _ in s[0][2]], [False, False, False, False, True])
        self.assertEqual(self.lines(s[1])[:2], [labels["odbiorca_zapasowy"][0], labels["zniszcz_dane"][0]])
        self.assertEqual(" ".join(self.lines(s[2])).strip(), texts["odbiorca_zapasowy"][0])
        self.assertIn("log switched to backup recipient", out)
        # Nowe zgłoszenie idzie do zapasowej tożsamości OSP (0xDD..).
        self.assertTrue(any(line.startswith('-> ["WICI",1,"abab') and '"dddddddddddddddddddddddddddddddd"' in line for line in out))
        self.assertEqual(" ".join(self.lines(s[4])).strip(), texts["zniszcz_ostrzezenie"][0])
        self.assertEqual(s[5][0], "destroy")  # zła sekwencja: nic się nie dzieje
        self.assertIn("log data destroyed", out)
        self.assertIn("queue live 0 unsent 0 configured 0 paused 0", out)

    def test_wrap_duration_and_glyph_coverage(self):
        data = ui_texts.load()
        texts = data["texts"]
        long_pl = texts["pilnosc_2_potw"][0]
        out = self.ui([f"W {long_pl}", "D 5940", "D 6000", "D 172799", "D 172800", "D 9000000", "W " + "A" * 45])
        count = int(out[0].split()[1])
        lines = [row[1:] for row in out[1:1 + count]]
        self.assertEqual(" ".join(lines), long_pl)
        self.assertTrue(all(len(line) <= 20 for line in lines), lines)
        self.assertEqual(out[1 + count:1 + count + 5], ["99 MIN|99 ХВ|99 MIN", "1 H|1 ГОД|1 H", "47 H|47 ГОД|47 H",
                                                       "2 D|2 Д|2 D", "99 D|99 Д|99 D"])
        self.assertEqual(out[1 + count + 5:], ["wrap 3", "|" + "A" * 20, "|" + "A" * 20, "|" + "A" * 5])
        # Każdy znak każdego tekstu kanonicznego ma glif w foncie.
        every = "".join(sorted(ui_texts.charset(data)))
        self.assertEqual(self.ui([f"G {every}"]), [f"glyphs {len(every)} 0"])
        self.assertEqual(self.ui(["G ĄĆĘŁŃÓŚŹŻąćęłńóśźż ҐґЇїЄєІі 漢"]), ["glyphs 29 1"])

    # --- SA1 ---------------------------------------------------------------

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
            ([1, 3, self.MID, 0, 1, "a\u200bb"], "Control, format, separator, private or unassigned character"),
            ([1, 3, self.MID, 0, 1, "a\u2028b"], "Control, format, separator, private or unassigned character"),
            ([1, 3, self.MID, 0, 1, "a\ue000b"], "Control, format, separator, private or unassigned character"),
            ([1, 3, self.MID, 0, 1, "a\u0007b"], "Control, format, separator, private or unassigned character"),
            ([1, 3, self.MID, 0, 1, "a\u00adb"], "Control, format, separator, private or unassigned character"),
            ({"a": 1}, "Expected message array"),
            ([1, 0, self.MID, 0.0, 1, 1, "a", "", 0], "Invalid integer"),
            ([1, 4, self.MID, 1, "ż" * 96 + "x"], "Invalid UTF-8 text size"),
        ]
        for value, reason in cases:
            self.assertEqual(self.sa1(value), ["err", reason], value)
        self.assertEqual(self.sa1(" " * (MAX_CONTENT + 1)), ["err", "Content too large"])

    def test_status_after_and_button_configuration_match_model(self):
        for args in ((3, 3, 1, 1), (1, 1, 2, 2), (2, 2, 2, 3), (2, 2, 3, 1), (2, 5, 3, 3), (3, 3, 4, 6), (4, 6, 5, 2), (1, 1, 2, 7)):
            out = self.run_harness("status", *map(str, args))
            try:
                expected = status_after(*args)
                self.assertEqual(out, ["ok", str(expected[0]), str(expected[1])], args)
            except ValueError as error:
                self.assertEqual(out, ["err"] + str(error).split(), args)
        self.assertEqual(self.run_harness("config", "ś" * 32, "Potrzeba ustała", "ł" * 48),
                         ["ok", str(check_button_configuration("ś" * 32, ("Potrzeba ustała", "ł" * 48)))])
        self.assertEqual(self.run_harness("config", "Testowa 10", "ł" * 49)[0], "err")
        self.assertEqual(self.run_harness("config", 'Testowa "10"')[0], "err")

    # --- protokół USB -------------------------------------------------------

    def usb(self, script):
        out = subprocess.run([str(self.binary), "usb"], input="\n".join(script) + "\n", capture_output=True, text=True,
                             check=True).stdout.splitlines()
        return out

    @staticmethod
    def replies(out):
        return [json.loads(line[3:]) for line in out if line.startswith("<- ")]

    def submit(self, seq, value, to="00112233445566778899aabbccddeeff", resend=False):
        msg = {"usb": 1, "seq": seq, "type": "submit", "to": to, "id": value[2], "revision": value[3] if value[1] != 4 else 0,
               "sa1": value}
        if resend:
            msg["resend"] = True
        return "> " + json.dumps(msg, ensure_ascii=False)

    def test_usb_sync_submit_duplicate_conflict_and_role(self):
        request = [1, 0, self.MID, 0, 2, 10, "Szkoła", "osoba na wózku", 2]
        changed = request[:5] + [11] + request[6:]
        configure = {"usb": 1, "seq": 2, "type": "configure", "address": "Szkoła, wejście B", "osp": "00112233445566778899aabbccddeeff",
                     "phrases": [["osoba na wózku", "людина на візку", "wheelchair user"]], "stations": 5}
        out = self.usb(["C 0", '> {"usb":1,"seq":1,"type":"sync","boot":"deadbeef","cursor":0}', "> " + json.dumps(configure, ensure_ascii=False),
                        self.submit(3, request), self.submit(4, request), self.submit(5, changed),
                        self.submit(6, [1, 0, self.MID, 1, 2, 11, "Szkoła", "", 2], to="ff" * 16),
                        self.submit(7, [1, 2, self.MID, 0, 2, 2]), '> {"usb":1,"seq":8,"type":"test"}',
                        self.submit(9, [1, 0, self.MID[:4] + "f" * 28, 0, 2, 10, "Szkoła", "", 2]), "S"])
        r = self.replies(out)
        self.assertEqual([x["type"] for x in r], ["sync", "sync", "ok", "stored", "stored", "rejected", "rejected", "rejected", "stored",
                                                  "rejected"])
        self.assertEqual(r[9]["reason"], "numer_zajety")  # te same pierwsze 16 bitów id: krótki numer zajęty
        self.assertEqual(len(r[0]["boot"]), 16)
        self.assertEqual((r[1]["re"], r[1]["configured"]), (1, False))
        self.assertEqual(r[2]["worst_request"], check_button_configuration("Szkoła, wejście B", ("osoba na wózku",)))
        self.assertEqual((r[3]["record"], r[3]["duplicate"]), (1, False))
        self.assertEqual((r[4]["record"], r[4]["duplicate"]), (1, True))
        self.assertEqual(r[5]["reason"], "conflict")
        self.assertEqual(r[6]["detail"], "recipient is not the active OSP")
        self.assertEqual(r[7]["detail"], "type not allowed for this role")
        self.assertEqual((r[8]["revision"], r[8]["record"]), (0, 2))
        self.assertIn("store live 2 inbox 0 pending 0 latest 0 configured 1 address Szkoła, wejście B", out)
        self.assertIn("log usb submit", out)

    def test_usb_queue_full_resend_and_persistence(self):
        script = ["C 0"]
        for i in range(129):
            # Pierwsze 16 bitów id dają krótki numer, który musi być wolny (numer_zajety).
            script.append(self.submit(10 + i, [1, 0, "%04x%028x" % (i * 7, i), 0, 1, 1, "a", "", 0]))
        script += ["S", "R", "S", "Q 1", self.submit(500, [1, 0, "%032x" % 0, 0, 1, 1, "a", "", 0], resend=True),
                   "Z %d 0" % (0x10000 + 448 + 1 + 2), "R", "Q 2"]
        out = self.usb(script)
        r = self.replies(out)[1:]  # pierwsza odpowiedź to sync po otwarciu portu
        self.assertEqual([x["type"] for x in r[:129]], ["stored"] * 128 + ["rejected"])
        self.assertEqual(r[128]["reason"], "full")
        self.assertEqual(out.count("store live 128 inbox 0 pending 0 latest 0 configured 0 address "), 2)
        self.assertIn("begin 1", out)
        self.assertTrue(any(line.startswith("queue 1 flags 1 attempts 0 [1,0,") for line in out))
        self.assertEqual(r[129]["duplicate"], True)  # ponowne uaktywnienie żywej intencji to duplikat
        self.assertTrue(any(line.startswith("queue 2 flags 1 attempts 0 ") for line in out))  # uszkodzony stan: aktywna od nowa

    def test_usb_events_ack_resend_and_commands(self):
        out = self.usb(["C 0", '> {"usb":1,"seq":1,"type":"sync","boot":"b","cursor":0}', 'E 2 "kind":"radio","silence":true',
                        "T 2000", "T 7000", '> {"usb":1,"seq":2,"type":"ack","cursor":1}', "T 13000", 'E 2 "kind":"radio","silence":false',
                        "D", "C 20000", '> {"usb":1,"seq":3,"type":"sync","boot":"b","cursor":1}', "T 20001", "T 26000",
                        '> {"usb":1,"seq":4,"type":"ack","record":2}', "T 32000",
                        'K 0', '> {"usb":1,"seq":5,"type":"silence","on":true}', 'K 1', '> {"usb":1,"seq":6,"type":"silence","on":true}',
                        'P 0', '> {"usb":1,"seq":7,"type":"configure","address":"x"}', '> {"usb":1,"seq":8,"type":"export"}',
                        '> {"usb":1,"seq":9,"type":"trust"}', "> nonsense", '> {"usb":2,"seq":10,"type":"sync"}', '> {"usb":1,"type":"sync"}',
                        '> {"usb":1,"seq":11,"type":"close"}', "S"])
        r = self.replies(out)
        types = [x["type"] for x in r]
        self.assertEqual(types[:4], ["sync", "sync", "event", "event"])  # zdarzenie od razu i ponownie po 5 s
        self.assertEqual((r[2]["record"], r[2]["silence"]), (1, True))
        self.assertEqual(types[4:7], ["event", "sync", "sync"])  # drugie zdarzenie, potem nowa sesja
        self.assertEqual(r[6]["pending"], 1)
        self.assertEqual(types[7:9], ["event", "event"])  # zaległe zdarzenie 2 po sync z kursorem 1, ponowione po 5 s
        self.assertEqual((r[7]["record"], r[8]["record"]), (2, 2))
        self.assertEqual(types[9:], ["rejected", "ok", "rejected", "rejected", "rejected", "rejected", "rejected", "rejected", "ok"])
        self.assertEqual([x["reason"] for x in r[9:10] + r[11:17]],
                         ["not confirmed", "preparation mode required", "preparation mode required", "unsupported", "not json", "contract", "seq"])
        self.assertEqual(r[10]["silence"], True)
        self.assertIn("log usb silence not confirmed", out)
        self.assertIn("store live 0 inbox 0 pending 0 latest 0 configured 0 address ", out)

    def test_usb_line_too_long_is_rejected(self):
        out = self.usb(["C 0", "> " + "x" * 1500, '> {"usb":1,"seq":1,"type":"sync","boot":"b","cursor":0}'])
        r = self.replies(out)
        self.assertEqual([x["type"] for x in r], ["sync", "rejected", "sync"])
        self.assertEqual(r[1]["reason"], "line too long")

    # --- łącze aplikacyjne --------------------------------------------------

    A = "aa" * 16
    B = "bb" * 16

    def link(self, script):
        return subprocess.run([str(self.binary), "link"], input="\n".join(script) + "\n", capture_output=True, text=True,
                              check=True).stdout.splitlines()

    @staticmethod
    def usb_replies(out, node):
        return [json.loads(line[3:]) for line in out if line.startswith(node + "<- ")]

    def usb_submit(self, node, seq, value, to):
        msg = {"usb": 1, "seq": seq, "type": "submit", "to": to, "id": value[2], "revision": value[3] if value[1] != 4 else 0, "sa1": value}
        return node + " " + json.dumps(msg, ensure_ascii=False)

    def test_link_request_received_status_and_osp_replay(self):
        request = [1, 0, self.MID, 0, 2, 10, "Szkoła", "osoba na wózku", 2]
        received = [1, 1, self.MID, 0, 1, 1]
        status = [1, 2, self.MID, 0, 2, 2]
        closed = [1, 2, self.MID, 0, 3, 6]
        regression = [1, 2, self.MID, 0, 4, 2]
        out = self.link(['B {"usb":1,"seq":1,"type":"configure","role":"osp"}', self.usb_submit("A", 2, request, self.B),
                         "T 101", "T 102", "T 103", "S", "X",
                         self.usb_submit("B", 3, received, self.A), "T 104", "T 105", "T 106", "X",
                         self.usb_submit("B", 4, status, self.A), "T 107", "T 108", "T 109",
                         self.usb_submit("B", 5, closed, self.A), "T 110", "T 111", "T 112",
                         self.usb_submit("B", 7, regression, self.A), "T 113", "T 114", "T 115", "X", "S",
                         # Powtórzony REQUEST (resend): OSP odpowiada zapisanym RECEIVED i STATUS.
                         "A " + json.dumps({"usb": 1, "seq": 6, "type": "submit", "to": self.B, "id": self.MID, "revision": 0, "sa1": request, "resend": True}),
                         "T 116", "T 117", "T 118", "T 119", "T 120", "T 121", "T 122", "T 123", "T 124", "S"])
        sent = [line for line in out if line.startswith("A-> ") or line.startswith("B-> ")]
        self.assertTrue(sent[0].startswith('A-> ["WICI",1,"%s","%s",[1,0,' % (self.A, self.B)), sent[0])
        self.assertEqual(sent[1], 'B-> ["WICI",1,"%s","%s","ack","%s",0,0,0]' % (self.B, self.A, self.MID))
        incoming = [r for r in self.usb_replies(out, "B") if r["type"] == "incoming"]
        self.assertEqual(len(incoming), 1)
        self.assertEqual((incoming[0]["source"], incoming[0]["sa1"]), (self.A, request))
        events = [r for r in self.usb_replies(out, "A") if r["type"] == "event" and r.get("kind") == "message"]
        self.assertEqual([e["sa1"] for e in events], [received, status, closed, regression])
        self.assertIn("A:log Status regression", out)
        queue_a = [line for line in out if line.startswith("A queue 1 ")]
        self.assertTrue(queue_a[0].endswith("flags 17 attempts 1 next 703 event 0 state 0"), queue_a[0])  # ACTIVE|SENT, 10 min na RECEIVED
        self.assertTrue(queue_a[1].endswith("flags 18 attempts 1 next 703 event 1 state 1"), queue_a[1])  # DONE|SENT po RECEIVED
        self.assertTrue(queue_a[2].endswith("flags 18 attempts 1 next 703 event 3 state 6"), queue_a[2])  # STATUS 3/6; regresja odrzucona
        stats = [line for line in out if line.startswith("A stats") or line.startswith("B stats")]
        self.assertEqual(stats[0], "A stats sent 1 delivered 1 failed 0 received 1 rejected 0 duplicates 0 conflicts 0 acks 0 confirmed 0 live 1 unsent 0 inbox 0 unread 0")
        self.assertEqual(stats[1], "B stats sent 0 delivered 0 failed 0 received 1 rejected 0 duplicates 0 conflicts 0 acks 1 confirmed 0 live 0 unsent 0 inbox 1 unread 1")
        self.assertEqual(stats[2], "A stats sent 1 delivered 1 failed 0 received 5 rejected 0 duplicates 0 conflicts 0 acks 4 confirmed 3 live 0 unsent 0 inbox 4 unread 4")
        # Po ponownym REQUEST: B zalicza duplikat, uaktywnia RECEIVED i najnowszy STATUS i nadaje je ponownie; A liczy duplikaty.
        self.assertEqual(stats[4], "A stats sent 2 delivered 2 failed 0 received 8 rejected 0 duplicates 2 conflicts 0 acks 6 confirmed 3 live 1 unsent 0 inbox 4 unread 4")
        self.assertEqual(stats[5], "B stats sent 6 delivered 6 failed 0 received 8 rejected 0 duplicates 1 conflicts 0 acks 2 confirmed 6 live 0 unsent 0 inbox 1 unread 1")

    def test_link_loss_retry_schedule_and_untrusted_source(self):
        request = [1, 0, self.MID, 0, 2, 10, "Szkoła", "", 1]
        out = self.link(['B {"usb":1,"seq":1,"type":"configure","role":"osp"}', "L 1", self.usb_submit("A", 1, request, self.B),
                         "T 101", "T 102", "T 160", "T 161", "T 162", "X", "S", "D 0", "D 40",
                         "L 0", "T 240", "T 241", "T 242", "X", "S",
                         # Stacja z kartą OSP X odrzuca datagram od B.
                         'A {"usb":1,"seq":2,"type":"configure","address":"a","osp":"' + "cc" * 16 + '"}',
                         "B " + json.dumps({"usb": 1, "seq": 3, "type": "submit", "to": self.A, "id": self.MID, "revision": 0, "sa1": [1, 1, self.MID, 0, 1, 1]}),
                         "T 300", "T 301", "T 302", "S"])
        queue = [line for line in out if line.startswith("A queue 1 ")]
        first = int(re.search(r"next (\d+)", queue[0]).group(1))
        self.assertTrue(queue[0].split(" next ")[0].endswith("flags 1 attempts 1"), queue[0])  # FAILED po 60 s bez ack
        self.assertTrue(162 + 48 <= first <= 162 + 72, first)                                   # kolejna po 60 s ±20%
        second = int(re.search(r"next (\d+)", queue[1]).group(1))
        self.assertTrue(queue[1].split(" next ")[0].endswith("flags 17 attempts 2"), queue[1])  # dostarczona za drugim razem
        self.assertTrue(242 + 600 + 1800 <= second <= 242 + 600 + 3600, second)                 # 10 min na RECEIVED + 30–60 min
        self.assertIn("48 48 96 240 720 720 | 2880 1800", out)      # 0,8 x (60, 60, 120, 300, 900, 900); po 6 h 0,8 x 3600; po dostarczeniu 1800
        self.assertIn("72 72 144 360 1080 1080 | 4320 1840", out)  # 1,2 x ...
        stats = [line for line in out if line.startswith("A stats")]
        self.assertTrue(stats[0].startswith("A stats sent 1 delivered 0 failed 1 received 0"))
        self.assertTrue(stats[1].startswith("A stats sent 2 delivered 1 failed 1 received 1 rejected 0"), stats[1])  # received liczy też ack
        self.assertTrue(stats[2].startswith("A stats sent 2 delivered 1 failed 1 received 2 rejected 1"), stats[2])
        self.assertIn("A:log datagram from untrusted source", out)

    def test_rejects_bad_lengths(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_harness("frame", "3", "1")
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_harness("frame", "104", "1")


if __name__ == "__main__":
    unittest.main()
