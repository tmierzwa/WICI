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
#include "annunciator.h"
#include "crc16.h"
#include "fram_id.h"
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
// "E <ack 0|1>" krok łącza (nadanie z kolejki, dowód transportowy od OSP), "Y <s>" czas pracy,
// "KD/KU <przycisk> <ms>" naciśnięcie i zwolnienie, "M" lista WIADOMOŚCI, "J" kolejka,
// "ON <0|1>" konfiguracja węzła OSP, "RN <0|1>" stos sieciowy działa, "PC <słyszany> <s> <usb in> <usb out> <odrzuty>" komputer stanowiska.
struct UiServices : station::Services {
    uint32_t uptime = 100;
    bool silence_ = false;
    std::vector<uint8_t> air;
    uint8_t counter = 0;
    uint32_t handle = 0;
    uint32_t uptimeS() override { return uptime; }
    bool silence() override { return silence_; }
    bool radioReady() override { return true; }
    bool busy() override { return !air.empty(); }
    uint32_t send(const uint8_t*, const uint8_t* data, size_t length, uint32_t) override {
        printf("-> %.*s\n", static_cast<int>(length), reinterpret_cast<const char*>(data));
        air.assign(data, data + length);
        return ++handle;
    }
    void randomBytes(uint8_t* out, size_t count) override { for (size_t i = 0; i < count; ++i) out[i] = static_cast<uint8_t>(0x30 + (++counter)); }
    void log(const char* text) override { printf("log %s\n", text); }
    void destroyed() override { printf("stack wiped\n"); }
    bool stack = true;
    bool announce() override { if (stack) printf("announce requested\n"); return stack; }
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
            cfg.stations = 2;
            strncpy(cfg.address, line + 2, store::ADDRESS_MAX);
            memset(cfg.osp[0], 0xCC, store::HASH);
            memset(cfg.osp[1], 0xDD, store::HASH);
            printf("config %d\n", store.writeConfig(cfg));
            con.invalidate();
        } else if (!strncmp(line, "AL ", 3)) {
            // Lista obiektów "a|b|c" (configure "addresses").
            store::Config cfg = store.config();
            memset(cfg.osp[0], 0xCC, store::HASH);
            memset(cfg.osp[1], 0xDD, store::HASH);
            memset(cfg.address, 0, sizeof(cfg.address));
            memset(cfg.objects, 0, sizeof(cfg.objects));
            cfg.objectCount = 0;
            char list[512];
            strncpy(list, line + 3, sizeof(list) - 1);
            list[sizeof(list) - 1] = '\0';
            size_t n = 0;
            for (char* s = strtok(list, "|"); s && n < store::ADDRESSES; s = strtok(nullptr, "|"), ++n) {
                strncpy(n ? cfg.objects[n - 1] : cfg.address, s, store::ADDRESS_MAX);
            }
            cfg.objectCount = static_cast<uint8_t>(n ? n - 1 : 0);
            printf("config %d\n", store.writeConfig(cfg));
            con.invalidate();
        } else if (sscanf(line, "ON %u", &a) == 1) {
            store::Config cfg = store.config();
            cfg.ospNode = static_cast<uint8_t>(a);
            if (a) { memset(cfg.address, 0, sizeof(cfg.address)); memset(cfg.osp, 0, sizeof(cfg.osp)); }
            printf("config %d\n", store.writeConfig(cfg));
            con.invalidate();
        } else if (sscanf(line, "RN %u", &a) == 1) {
            services.stack = a;
        } else if (sscanf(line, "PC %u %u %u %u %u", &a, &b, &c, &d, &e) == 5) {
            status.computerHeard = a; status.computerS = b; status.usbIn = c; status.usbOut = d; status.usbDrop = e;
        } else if (!strcmp(line, "AD")) {
            printf("addresses %zu selected %zu", store.addressCount(), store.selectedAddress());
            for (size_t i = 0; i < store.addressCount(); ++i) printf(" |%s", store.addressAt(i));
            printf(" |location %s\n", store.address());
        } else if (sscanf(line, "SEL %u", &a) == 1) {
            store.selectAddress(a);
        } else if (sscanf(line, "RV %u %u", &a, &b) == 2) {
            uint32_t newSeq = 0;
            const int result = static_cast<int>(app.revise(a, static_cast<uint16_t>(b), 0, nullptr, newSeq));
            printf("revise %d %u\n", result, newSeq);
        } else if (!strcmp(line, "PH")) {
            // Własna lista fraz stacji (jedna fraza) zamiast domyślnej.
            store::Config cfg = store.config();
            cfg.phraseCount = 1;
            strcpy(cfg.phrases[0][0], "brama zamknięta");
            strcpy(cfg.phrases[0][1], "ворота зачинені");
            strcpy(cfg.phrases[0][2], "gate closed");
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
                services.air.clear();
                if (a) app.receipt(services.handle, true);   // dowód transportowy od OSP
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
    bool prep_ = true, silence_ = false, confirm_ = true, switch_ = false;
    uint32_t uptime_ = 100;
    uint8_t counter_ = 0;
    uint32_t uptimeS() override { return uptime_; }
    bool prep() override { return prep_; }
    bool silence() override { return silence_; }
    void setSilence(bool on) override { silence_ = on; }
    bool silenceSwitch() override { return switch_; }
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
// "W <0|1>" przełącznik CISZA, "U <s>" czas pracy, "R" restart stacji (ta sama pamięć), "Z <adres> <bajt>" uszkodzenie bajtu FRAM,
// "S" stan magazynu, "N" konfiguracja węzła OSP, "Q <seq>" rekord kolejki, "X <seq> <flagi>" zapis stanu intencji.
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
        else if (sscanf(line, "W %u", &a) == 1) host.switch_ = a;
        else if (sscanf(line, "U %u", &a) == 1) host.uptime_ = a;
        else if (line[0] == 'R') {
            delete proto; delete store;
            store = new store::Store(ram); printf("begin %d\n", store->begin());
            proto = new usbproto::Protocol(*store, host); proto->begin();
        } else if (sscanf(line, "Z %u %u", &a, &b) == 2) ram.bytes[a] = static_cast<uint8_t>(b);
        else if (line[0] == 'N') {
            const store::Config& c = store->config();
            printf("node %u osp %02x phrases %u stations %u objects %u ifac %02x seq %u\n", c.ospNode, c.osp[0][0], c.phraseCount, c.stations,
                   c.objectCount, c.ifac[0], c.seq);
        }
        else if (line[0] == 'S') printf("store live %zu inbox %zu pending %zu latest %u configured %d address %s\n", store->queueLive(), store->inboxCount(), store->notesPending(), store->noteLatest(), store->configured(), store->config().address);
        else if (sscanf(line, "X %u %u", &a, &b) == 2) { store::QueueRecord r; printf("update %d\n", store->queueRead(a, r) && (r.flags = static_cast<uint8_t>(b), store->queueUpdate(r))); }
        else if (sscanf(line, "Q %u", &a) == 1) { store::QueueRecord r; if (store->queueRead(a, r)) printf("queue %u flags %u attempts %u %s\n", r.seq, r.flags, r.attempts, r.sa1); else printf("queue none\n"); }
    }
    delete proto; delete store;
    return 0;
}

// Stacja A i odbiorca B połączone "eterem" bez strat albo ze stratami. OSP działa na komputerze
// stanowiska (D19), więc B to model odbiorcy w programie testowym: przyjmuje każdy pakiet
// w kopercie do swojego adresu (dowód transportowy), wypisuje "B got <SA1>" i nadaje wiadomości
// z polecenia "B> <SA1>" w kopercie do A. A ma własną FRAM w RAM, magazyn, protokół USB
// i warstwę aplikacji.
struct Node;
struct LinkServices : station::Services {
    Node* node = nullptr;
    uint32_t uptimeS() override;
    bool silence() override;
    bool radioReady() override { return true; }
    bool busy() override;
    uint32_t send(const uint8_t* to, const uint8_t* data, size_t length, uint32_t timeoutS) override;
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
    station::Station* app = nullptr;   // nullptr: model odbiorcy (B)
    Node* peer = nullptr;
    uint32_t uptime = 100;
    bool lossy = false;
    std::vector<uint8_t> air;  // pakiet w drodze (dostarczany przy następnym kroku czasu)
    bool txBusy = false;
    // Potwierdzenie transportowe jak w stosie: dowód odbiorcy wraca krok po dostarczeniu,
    // bez dowodu wynik "nie dostarczono" po limicie z send (bez kolejki radiowej w modelu).
    uint32_t handles = 0, outstanding = 0, sentS = 0, timeoutS = 0;
    bool proofDue = false;
    bool refuse = false;   // stos odmawia (cel nieznany, pełna kolejka): send zwraca 0
    uint8_t addr;
    uint32_t sent = 0, delivered = 0, failed = 0, received = 0;   // liczniki modelu odbiorcy
};
uint32_t LinkServices::uptimeS() { return node->uptime; }
bool LinkServices::silence() { return node->host.silence_; }
bool LinkServices::busy() { return node->txBusy; }
uint32_t LinkServices::send(const uint8_t*, const uint8_t* data, size_t length, uint32_t timeoutS) {
    if (node->refuse) { printf("%c-> refused\n", node->name); return 0; }
    printf("%c-> %.*s\n", node->name, static_cast<int>(length), reinterpret_cast<const char*>(data));
    node->air.assign(data, data + length);
    node->txBusy = true;
    node->outstanding = ++node->handles;
    node->sentS = node->uptime;
    node->timeoutS = timeoutS;
    node->proofDue = false;
    return node->outstanding;
}
void LinkServices::randomBytes(uint8_t* out, size_t count) { for (size_t i = 0; i < count; ++i) out[i] = static_cast<uint8_t>(0x55 + i + node->name); }
void LinkServices::log(const char* text) { printf("%c:log %s\n", node->name, text); }
bool LinkServices::notify(uint8_t kind, uint32_t ref, const char* fields) { return node->proto->event(kind, ref, fields, node->uptime * 1000); }
void LinkServices::address(uint8_t* out) { memset(out, node->addr, store::HASH); }

// Model odbiorcy: pakiet w kopercie ["WICI",1,od,do,<SA1>] do adresu B przyjęty z dowodem.
bool receiverAccepts(Node& b, const uint8_t* data, size_t length) {
    char prefix[96];
    snprintf(prefix, sizeof(prefix), "[\"WICI\",1,\"%s\",\"%s\",", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
    const size_t p = strlen(prefix);
    if (length <= p + 1 || memcmp(data, prefix, p) || data[length - 1] != ']') return false;
    ++b.received;
    printf("B got %.*s\n", static_cast<int>(length - p - 1), reinterpret_cast<const char*>(data) + p);
    return true;
}

int linkScript() {
    Node a, b;
    a.name = 'A'; a.addr = 0xAA; b.name = 'B'; b.addr = 0xBB;
    a.peer = &b; b.peer = &a;
    // Emisje USB z nazwą węzła.
    struct NamedHost : TestHost { char name; void emit(const char* line) override { printf("%c<- %s\n", name, line); } void log(const char* text) override { printf("%c:log %s\n", name, text); } };
    static NamedHost ha;
    ha.name = 'A';
    Node* nodes[2] = {&a, &b};
    auto startA = [&]() {
        a.store = new store::Store(a.ram); a.store->begin();
        a.proto = new usbproto::Protocol(*a.store, ha); a.proto->begin(); a.proto->connected(0);
        const char* sync = "{\"usb\":1,\"seq\":0,\"type\":\"sync\",\"boot\":\"laptop\",\"cursor\":0}\n";
        a.proto->feed(sync, strlen(sync), 0);
        a.services.node = &a;
        a.app = new station::Station(*a.store, a.services);
    };
    startA();
    char line[2048];
    while (fgets(line, sizeof(line), stdin)) {
        char* nl = strchr(line, '\n');
        if (nl) *nl = '\0';
        unsigned v = 0;
        if (line[0] == 'A' && line[1] == ' ') { a.proto->feed(line + 2, strlen(line + 2), a.uptime * 1000); a.proto->feed("\n", 1, a.uptime * 1000); }
        else if (line[0] == 'B' && line[1] == '>' && line[2] == ' ') {
            // Odbiorca nadaje wiadomość SA1 do A (jak aplikacja OSP przez węzeł OSP).
            char envelope[700];
            snprintf(envelope, sizeof(envelope), "[\"WICI\",1,\"%s\",\"%s\",%s]", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                     "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", line + 3);
            printf("B-> %s\n", envelope);
            b.air.assign(envelope, envelope + strlen(envelope));
            b.txBusy = true;
            b.outstanding = ++b.handles;
            b.sentS = b.uptime;
            b.timeoutS = station::ACK_TIMEOUT_S;
            b.proofDue = false;
            ++b.sent;
        }
        else if (sscanf(line, "T %u", &v) == 1) {
            // Krok czasu: wyniki potwierdzeń, koniec nadawania, dostarczenie pakietów, poll stacji.
            for (Node* x : nodes) {
                x->uptime = v;
                if (x->outstanding && (x->proofDue || v - x->sentS >= x->timeoutS)) {
                    const uint32_t h = x->outstanding;
                    const bool delivered = x->proofDue;
                    x->outstanding = 0; x->proofDue = false;
                    if (x->app) x->app->receipt(h, delivered);
                    else if (delivered) ++x->delivered;
                    else ++x->failed;
                }
                x->txBusy = false;
                if (!x->air.empty()) {
                    std::vector<uint8_t> d = x->air; x->air.clear();
                    // Dowód tylko dla pakietu przyjętego przez warstwę aplikacji odbiorcy (PROVE_APP).
                    if (x->lossy) printf("%c-> lost\n", x->name);
                    else if (x->peer->app) x->proofDue = x->peer->app->received(d.data(), d.size());
                    else x->proofDue = receiverAccepts(*x->peer, d.data(), d.size());
                }
            }
            a.app->notifyPending();
            a.app->poll(v * 1000);
        } else if (sscanf(line, "L %u", &v) == 1) a.lossy = b.lossy = v;
        else if (sscanf(line, "F %u", &v) == 1) {
            // Pierścień zdarzeń A zapełniony niepotwierdzonymi zdarzeniami radia.
            unsigned ok = 0;
            for (unsigned i = 0; i < v; ++i) ok += a.proto->event(store::NOTE_RADIO, 0, "\"kind\":\"radio\"", a.uptime * 1000);
            printf("filled %u pending %zu\n", ok, a.store->notesPending());
        } else if (line[0] == 'P') {
            size_t notify = 0;
            for (size_t i = 0; i < store::INBOX_SLOTS; ++i) {
                const store::InboxEntry* e = a.store->inboxEntry(i);
                notify += e && (e->flags & store::INBOX_NOTIFY);
            }
            printf("A notes pending %zu inbox %zu notify %zu\n", a.store->notesPending(), a.store->inboxCount(), notify);
        }
        else if (sscanf(line, "Q %u", &v) == 1) { a.host.silence_ = v; }
        else if (sscanf(line, "N %u", &v) == 1) a.refuse = v;
        else if (line[0] == 'R' && line[1] == 'A') {
            delete a.app; delete a.proto; delete a.store;
            startA();
        } else if (line[0] == 'S') {
            const station::Stats& s = a.app->stats();
            printf("A stats sent %u delivered %u failed %u received %u rejected %u duplicates %u conflicts %u refused %u confirmed %u live %zu unsent %zu inbox %zu unread %zu\n",
                   s.sent, s.delivered, s.failed, s.received, s.rejected, s.duplicates, s.conflicts, s.refused, s.confirmed,
                   a.store->queueLive(), a.store->queueUnsent(), a.store->inboxCount(), a.store->inboxUnread());
            printf("B stats sent %u delivered %u failed %u received %u\n", b.sent, b.delivered, b.failed, b.received);
        } else if (line[0] == 'X') {
            for (size_t i = 0; i < a.store->queueSize(); ++i) {
                const store::QueueEntry* e = a.store->queueEntry(i);
                if (!e) continue;
                store::QueueRecord r; a.store->queueRead(e->seq, r);
                printf("A queue %u type %u flags %u attempts %u next %u event %u state %u\n", r.seq, r.type, r.flags, r.attempts, r.nextTryS, r.statusEvent, r.state);
            }
        } else if (sscanf(line, "D %u", &v) == 1) {
            // Harmonogram ponowień dla kolejnych prób z losową liczbą v.
            for (unsigned attempts = 0; attempts < 6; ++attempts) printf("%u ", a.app->retryDelayS(static_cast<uint16_t>(attempts), false, 0, v));
            printf("| %u %u\n", a.app->retryDelayS(1, false, 7 * 3600, v), a.app->retryDelayS(2, true, 0, v));
        }
    }
    delete a.app; delete a.proto; delete a.store;
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
    if ((argc == 4 || argc == 5) && !strcmp(argv[1], "frame")) {
        uint8_t frame[testframe::MAX_LENGTH];
        const size_t length = strtoul(argv[2], nullptr, 10);
        const uint16_t seq = strtoul(argv[3], nullptr, 10);
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
                        str(SRC / "testframe.cpp"), str(SRC / "annunciator.cpp"), str(SRC / "journal.cpp"), str(SRC / "p1frame.cpp"), str(SRC / "ui.cpp"),
                        str(SRC / "font.cpp"), str(SRC / "jsonlite.cpp"), str(SRC / "sa1.cpp"), str(SRC / "store.cpp"),
                        str(SRC / "usbproto.cpp"), str(SRC / "station.cpp"), str(SRC / "console.cpp"), "-o", str(cls.binary)],
                       check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_harness(self, *args):
        return subprocess.run([str(self.binary), *args], capture_output=True, text=True, check=True).stdout.split()

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

    def test_osp_node_screens(self):
        # D19 (oprogramowanie.md, „Węzeł OSP”): po wyborze języka ekran główny bez kontroli adresu
        # i TEST: radio, komputer stanowiska, zasilanie; menu STAN i JĘZYK; STAN z licznikami USB,
        # bez PRZEKAZANIA ZMIANY; USŁUGI tylko WYCISZ DŹWIĘK i ZNISZCZ DANE.
        data = ui_texts.load()
        texts, labels = data["texts"], data["labels"]
        menu = [strings[0] for _, strings in data["menu"]]
        minutes = ui_texts.UNITS["PL"][0]
        out = self.ui(["H", "ON 1", "S 0", "O 1", "K OK 0", "R", "PC 1 300 12 30 1", "R", "Q 1", "R", "Q 0",
                       "K OK 0", "R", "K OK 0", "R"] + ["K DOWN 0"] * 8 + ["R"] + ["K DOWN 0"] * 6 +
                      ["R", "K OK 0", "R", "K OK 0", "R", "K DOWN 0", "K OK 0", "R", "K BACK 0", "K BACK 0", "K BACK 0", "R",
                       "KD BACK 1000", "T 4100", "KU BACK 4200", "R", "K OK 5000", "R"])
        (first, heard, silence, menu_screen, status_top, status_usb, status_end, services, muted, destroy, back_menu,
         language, after_language) = self.screens(out)
        computer = texts["komputer_osp"][0].replace("[czas]", f"5 {minutes}")
        power = texts["zasilanie_12v"][0].replace("[x]", "0,0")
        self.assertEqual(first[0], "main")
        self.assertEqual(self.lines(first), [texts["radio_wlaczone"][0], texts["komputer_brak"][0], power, "", ""])
        self.assertEqual(self.lines(heard), [texts["radio_wlaczone"][0], computer, power, "", ""])
        self.assertEqual(" ".join(self.lines(silence)[:3]).strip(), texts["cisza"][0])
        self.assertEqual(self.lines(silence)[3:], [power, computer])
        self.assertEqual(self.lines(menu_screen), [menu[3], menu[4], "", "", ""])
        self.assertEqual(status_top[0], "status")
        self.assertEqual(self.lines(status_usb), ["DEFER 0", "WAIT 0 S", "USB IN 12", "USB OUT 30", "USB DROP 1"])
        # Ostatni wiersz to USŁUGI (bez PRZEKAZANIA ZMIANY), przed nim zasilanie, odchyłka, wersja i nazwa.
        self.assertEqual(self.lines(status_end), [power, "FOFF ---", "bench-a-test", "WICI-000000", labels["USLUGI"][0]])
        self.assertEqual(self.lines(services), [labels["WYCISZ_DZWIEK"][0], labels["ZNISZCZ_DANE"][0], "", "", ""])
        self.assertEqual(self.lines(muted)[0], labels["WLACZ_DZWIEK"][0])
        self.assertEqual(destroy[0], "destroy")
        self.assertEqual(back_menu[0], "menu")
        self.assertEqual(language[0], "language_menu")   # przytrzymanie WSTECZ: wybór języka
        self.assertEqual((after_language[0], [inv for inv, _ in after_language[2]]), ("menu", [False, True, False, False, False]))

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

    def test_object_list_choice_at_startup(self):
        # oprogramowanie.md, „Start”: lista adresów obiektów z wyborem przyciskami; WSTECZ na kontroli
        # adresu wraca do listy, WSTECZ na liście = żaden obiekt (adres_brak).
        texts = ui_texts.load()["texts"]
        out = self.ui(["H", "AL Szkoła A|Hala sportowa B|Kościół C", "S 0", "O 1", "K OK 0", "R", "K DOWN 0", "K OK 0", "R",
                       "K BACK 0", "R", "K BACK 0", "R", "AD"])
        listed, check, again, missing = self.screens(out)
        self.assertEqual(listed[0], "address_list")
        self.assertEqual(self.lines(listed), ["Szkoła A", "Hala sportowa B", "Kościół C", "", ""])
        self.assertEqual([inv for inv, _ in listed[2]], [True, False, False, False, False])
        self.assertEqual(" ".join(self.lines(check)).strip(), texts["adres_kontrola"][0].replace("[x]", "Hala sportowa B"))
        self.assertEqual(again[0], "address_list")
        self.assertEqual([inv for inv, _ in again[2]], [False, True, False, False, False])
        self.assertEqual(" ".join(self.lines(missing)).strip(), texts["adres_brak"][0])
        self.assertIn("addresses 3 selected 1 |Szkoła A |Hala sportowa B |Kościół C |location Hala sportowa B", out)

    def test_chosen_object_goes_into_requests_and_revision_keeps_it(self):
        out = self.ui(["H", "AL Obiekt Alfa|Obiekt Beta|Obiekt Gamma", "S 0", "O 1", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0",
                       "K OK 0", "K OK 0", "J", "SEL 0", "RV 1 3", "J", "H", "AD", "A Jeden adres", "AD"])
        intents = [line for line in out if line.startswith("intent ")]
        self.assertIn('"Obiekt Gamma"', intents[0])          # TEST startowy z wybranego obiektu
        self.assertIn("revise 0 2", out)
        self.assertIn('"Obiekt Gamma"', intents[-1])         # rewizja po zmianie wyboru: ta sama lokalizacja
        self.assertNotIn("Obiekt Alfa", " ".join(intents))
        # Lista w FRAM po ponownym starcie magazynu; wybór wraca do pierwszego (main.cpp odtwarza go z ustawień).
        self.assertIn("addresses 3 selected 0 |Obiekt Alfa |Obiekt Beta |Obiekt Gamma |location Obiekt Alfa", out)
        self.assertIn("addresses 1 selected 0 |Jeden adres |location Jeden adres", out)

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
        # Pilność słownie łamana na wiersze, nie obcinana do 20 znaków.
        self.assertEqual(self.lines(summary)[:4], [data["categories"][2][0], "5 PILNE – KILKA", "GODZIN", data["phrases"][0][0]])
        self.assertEqual(" ".join(self.lines(summary)[1:3]), "5 " + texts["pilnosc_1"][0])
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
        self.assertIn(data["phrases"][10][0], self.lines(s[6]))  # POTRZEBA USTAŁA: fraza w podsumowaniu
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

    def test_own_phrase_list_revision_keeps_and_translates_phrase(self):
        # Własna lista fraz: rewizja liczby osób pokazuje zachowaną frazę w podsumowaniu, a POTRZEBA USTAŁA
        # (fraza domyślna spoza listy) jest tłumaczona na ekranie zgłoszenia.
        create = ["PH", "K OK 0", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0", "K DOWN 0",
                  "K DOWN 0", "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0", "E 1", "I [1,1,\"%s\",0,1,1]" % self.REQUEST_ID]
        # WIADOMOŚCI → zgłoszenie → ZMIEŃ LICZBĘ OSÓB → ta sama liczba → podsumowanie; wysłanie.
        people = ["L 2", "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0"]
        # Najnowsza rewizja → POTRZEBA USTAŁA → wysłanie; potem ekran zgłoszenia przewinięty do frazy.
        resolved = ["K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0", "K DOWN 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0",
                    "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "K DOWN 0", "K DOWN 0", "R"]
        script = list(create)
        for key in people + resolved:
            script += [key, "R"] if key != "R" else []
        out = self.hosted(script)
        s = [x for x in self.screens(out) if x[0] in ("summary", "item")]
        self.assertEqual([x[0] for x in s], ["item", "summary", "item", "summary", "item", "item", "item"])
        self.assertEqual(self.lines(s[1])[3], "gate closed")      # zachowana fraza z listy stacji, po angielsku
        self.assertIn("need resolved", self.lines(s[-1]))         # nie „potrzeba ustała”

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
        # własnych zgłoszeń z FRAM; treść (liczba osób, fraza, tekst komunikatu) dekoduje się raz na rekord.
        create = ["K OK 0", "K OK 0", "K OK 0", "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0"]
        script = create * 3 + ["I [1,4,\"41424344454647484950515253545556\",7,\"Komunikat\"]", "K OK 0", "K DOWN 0", "K OK 0", "R", "B",
                               "R", "B", "K OK 0", "R", "B", "K BACK 0", "K BACK 0", "K DOWN 0", "K DOWN 0", "K OK 0"] + \
                 ["K DOWN 0"] * 13 + ["K OK 0", "R", "B", "R", "B"]
        out = self.hosted(script)
        s = self.screens(out)
        self.assertEqual([x[0] for x in s], ["messages", "messages", "item", "handover", "handover"])
        reads = [int(line.split()[1]) for line in out if line.startswith("read ")]
        self.assertEqual(reads[1], 0)     # ponowne rysowanie listy: treść komunikatu z pamięci ostatniej pozycji
        self.assertGreaterEqual(reads[2], 452)  # otwarcie oznacza jako przeczytany: rekord czytany raz od nowa
        self.assertEqual(reads[3:], [0, 0])   # PRZEKAZANIE ZMIANY: wyłącznie indeks w RAM

    def test_services_backup_and_destroy_sequences(self):
        labels = {name.lower(): strings for name, strings in ui_texts.load()["labels"].items()}
        texts = ui_texts.load()["texts"]
        # Zgłoszenie zapisane przed przełączeniem (do tożsamości głównej, bez nadania).
        before = ["K OK 0", "K OK 0", "K OK 0", "K OK 0", "K DOWN 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0"]
        to_services = before + ["K OK 0", "K DOWN 0", "K DOWN 0", "K DOWN 0", "K OK 0"] + ["K DOWN 0"] * 16 + ["R", "K OK 0", "R"]
        # USŁUGI: OGŁOŚ ADRES (wynik), powrót, WYCISZ DŹWIĘK, KLUCZ ZAPASOWY.
        services = ["K OK 0", "R", "K OK 0", "R", "K DOWN 0", "K OK 0", "R", "K DOWN 0", "K OK 0", "R"]
        # Po przełączeniu: zgłoszenie W CIĄGU DOBY bez frazy, nadane do zapasowej tożsamości; potem ZNISZCZ DANE.
        script = to_services + services + ["K UP 0", "K DOWN 0", "K UP 0", "K OK 0", "R", "K BACK 0", "K UP 0", "K UP 0", "K UP 0",
                                           "K OK 0", "K OK 0", "K OK 0", "K UP 0", "K OK 0", "K OK 0", "K OK 0", "K OK 0", "E 1", "J",
                                           "K OK 0", "K DOWN 0", "K DOWN 0", "K DOWN 0", "K OK 0"] + ["K DOWN 0"] * 16 + \
                 ["K OK 0", "K DOWN 0", "K DOWN 0", "K DOWN 0", "K OK 0", "R", "K UP 0", "K DOWN 0", "K DOWN 0", "K UP 0", "R",
                  "K UP 0", "K DOWN 0", "K UP 0", "K OK 0", "R", "J"]
        out = self.hosted(script)
        s = self.screens(out)
        self.assertEqual([x[0] for x in s], ["status", "services", "result", "services", "services", "backup", "status", "destroy",
                                             "destroy", "main"])
        self.assertEqual(self.lines(s[0])[-2:], [labels["przekazanie_zmiany"][0], labels["uslugi"][0]])
        self.assertEqual([inv for inv, _ in s[0][2]], [False, False, False, False, True])
        self.assertEqual(self.lines(s[1])[:4], [labels["oglos_adres"][0], labels["wycisz_dzwiek"][0], labels["klucz_zapasowy"][0],
                                                labels["zniszcz_dane"][0]])
        # OGŁOŚ ADRES: zlecenie bez sekwencji, wynik, powrót do USŁUG.
        self.assertIn("announce requested", out)
        self.assertEqual(" ".join(self.lines(s[2])).strip(), texts["adres_ogloszony"][0])
        # Bez działającego stosu: własny komunikat, nie błąd zapisu zgłoszenia.
        failed = self.screens(self.hosted(to_services + ["RN 0", "K OK 0", "R"]))[-1]
        self.assertEqual(failed[0], "result")
        self.assertEqual(" ".join(self.lines(failed)).strip(), texts["adres_nie_ogloszony"][0])
        # WYCISZ DŹWIĘK przełącza pozycję na WŁĄCZ DŹWIĘK; wyciszenie widać na ekranie głównym (wiersz 4, pusta kolejka).
        self.assertEqual(self.lines(s[4])[1], labels["wlacz_dzwiek"][0])
        self.assertIn(texts["dzwiek_wyciszony"][0], self.lines(s[9]))
        self.assertEqual(" ".join(self.lines(s[5])).strip(), texts["klucz_zapasowy"][0])
        self.assertIn("log switched to backup recipient", out)
        # Zgłoszenie zapisane przed przełączeniem (jedno w locie naraz) idzie do zapasowej tożsamości OSP (0xDD..),
        # nigdy do głównej.
        sent = [line for line in out if line.startswith('-> ["WICI",1,"abab')]
        self.assertTrue(sent)
        self.assertTrue(all('"dddddddddddddddddddddddddddddddd"' in line for line in sent), sent)
        self.assertIn("Szkoła, wejście B", sent[0])
        self.assertEqual(" ".join(self.lines(s[7])).strip(), texts["zniszcz_ostrzezenie"][0])
        self.assertEqual(s[8][0], "destroy")  # zła sekwencja: nic się nie dzieje
        self.assertIn("log data destroyed", out)
        self.assertEqual(out.count("stack wiped"), 1)   # tożsamość i kod IFAC stosu też, jak destroy przez USB
        self.assertIn("queue live 0 unsent 0 configured 0 paused 0", out)

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

    def test_usb_configure_object_list(self):
        # Lista obiektów: 1–8 adresów, nie razem z "address"; najgorsze zgłoszenie liczone dla każdego.
        def configure(seq, **fields):
            return "> " + json.dumps({"usb": 1, "seq": seq, "type": "configure", **fields}, ensure_ascii=False)
        objects = ["Szkoła A", "Hala sportowa B", "ś" * 32]
        out = self.usb(["C 0", configure(1, addresses=objects), "S", configure(2, addresses=["a"] * 9),
                        configure(3, addresses=[]), configure(4, addresses=["a", ""]), configure(5, addresses=["a", "x" * 65]),
                        configure(6, addresses=["a"], address="b"), configure(7, addresses="a"),
                        configure(8, addresses=["Testowa 10", "ł" * 49], phrases=[["ł" * 48, "a", "a"]]),
                        configure(9, address="Jeden"), "S"])
        r = self.replies(out)[1:]   # po C 0 stacja wysyła sync
        self.assertEqual([x["type"] for x in r], ["ok"] + ["rejected"] * 7 + ["ok"])
        self.assertEqual(r[0]["worst_request"], check_button_configuration("ś" * 32, ()))
        self.assertEqual({x["detail"] for x in r[1:6]}, {"addresses"})
        self.assertIn("store live 0 inbox 0 pending 0 latest 0 configured 1 address Szkoła A", out)
        self.assertIn("store live 0 inbox 0 pending 0 latest 0 configured 1 address Jeden", out)

    def test_usb_configure_osp_node(self):
        # D19 (stanowisko-osp.md, „Stacja stanowiska”): węzeł OSP bez adresu, karty OSP, fraz i liczby
        # stacji, z kodem dostępu sieci; bez zgłoszeń i TEST; wyjście tylko jawnym "osp_node":false.
        def configure(seq, **fields):
            return "> " + json.dumps({"usb": 1, "seq": seq, "type": "configure", **fields}, ensure_ascii=False)
        request = [1, 0, self.MID, 0, 2, 10, "Szkoła", "", 2]
        out = self.usb(["C 0", configure(1, address="Szkoła", osp="cc" * 16, stations=5, ifac="11" * 16,
                                         phrases=[["osoba na wózku", "людина на візку", "wheelchair user"]]),
                        configure(2, osp_node=True), "N",
                        configure(3, address="x"), configure(4, osp_node=True, osp="cc" * 16), configure(5, phrases=[]),
                        self.submit(6, request, to="cc" * 16), '> {"usb":1,"seq":7,"type":"test"}',
                        '> {"usb":1,"seq":8,"type":"sync","boot":"b","cursor":0}',
                        configure(9, osp_node=False, address="Szkoła B"), "N", configure(10, osp_node="tak"),
                        "P 0", configure(11, osp_node=True)])
        r = self.replies(out)[1:]   # po C 0 stacja wysyła sync
        self.assertEqual([x["type"] for x in r], ["ok", "ok"] + ["rejected"] * 5 + ["sync", "ok", "rejected", "rejected"])
        self.assertEqual((r[0]["osp_node"], r[1]["osp_node"], r[1]["worst_request"]), (False, True, 0))
        self.assertEqual({x.get("detail") for x in r[2:7]}, {"osp node"})
        self.assertEqual(r[7]["osp_node"], True)
        self.assertEqual(r[8]["osp_node"], False)
        self.assertEqual(r[9]["detail"], "osp_node")
        self.assertEqual(r[10]["reason"], "preparation mode required")
        nodes = [line for line in out if line.startswith("node ")]
        self.assertEqual(nodes[0], "node 1 osp 00 phrases 0 stations 0 objects 0 ifac 11 seq 2")
        self.assertEqual(nodes[1], "node 0 osp 00 phrases 0 stations 0 objects 0 ifac 11 seq 3")

    def test_usb_sync_submit_duplicate_conflict_and_single_role(self):
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
        self.assertEqual(r[7]["detail"], "type not allowed")   # jedna rola: STATUS tworzy aplikacja OSP (D19)
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
                         ["not confirmed", "preparation mode required", "preparation mode required", "unknown type", "not json", "contract", "seq"])
        self.assertEqual(r[10]["silence"], True)
        self.assertIn("log usb silence not confirmed", out)
        self.assertIn("store live 0 inbox 0 pending 0 latest 2 configured 0 address ", out)  # numeracja rośnie dalej

    def test_close_keeps_record_numbers_after_restart(self):
        # ZAMKNIJ ZDARZENIE nie cofa numerów: nowe zdarzenie ma numer większy od kursora laptopa także po restarcie.
        out = self.usb(["C 0", '> {"usb":1,"seq":1,"type":"sync","boot":"b","cursor":0}', 'E 2 "kind":"radio","silence":true',
                        'E 2 "kind":"radio","silence":false', '> {"usb":1,"seq":2,"type":"ack","cursor":2}',
                        '> {"usb":1,"seq":3,"type":"close"}', "R", "S", "C 0", '> {"usb":1,"seq":4,"type":"sync","boot":"b","cursor":2}',
                        'E 2 "kind":"radio","silence":true', "S"])
        self.assertIn("begin 1", out)
        self.assertIn("store live 0 inbox 0 pending 0 latest 2 configured 0 address ", out)
        events = [x for x in self.replies(out) if x["type"] == "event"]
        self.assertEqual(events[-1]["record"], 3)
        self.assertIn("store live 0 inbox 0 pending 1 latest 3 configured 0 address ", out)

    def test_torn_state_write_keeps_previous_state(self):
        # Stan intencji ma dwie kopie: uszkodzony zapis nowej kopii zostawia poprzedni stan, nie „aktywna od nowa”.
        slot_a = 0x10000 + 448
        out = self.usb(["C 0", self.submit(1, [1, 0, "%032x" % 1, 0, 1, 1, "a", "", 0]), "X 1 8", "X 1 2",
                        "Z %d 0" % (slot_a + 21 + 2), "R", "Q 1"])
        self.assertEqual(out.count("update 1"), 2)
        self.assertTrue(any(line.startswith("queue 1 flags 8 attempts 0 ") for line in out))

    def test_usb_silence_switch_has_priority(self):
        # Przełącznik CISZA ma pierwszeństwo przed panelem: laptop nie wyłącza ciszy ustawionej przełącznikiem.
        out = self.usb(["C 0", "W 1", '> {"usb":1,"seq":1,"type":"silence","on":true}', '> {"usb":1,"seq":2,"type":"silence","on":false}',
                        "W 0", '> {"usb":1,"seq":3,"type":"silence","on":false}'])
        r = [x for x in self.replies(out) if x["type"] != "sync"]
        self.assertEqual([x["type"] for x in r], ["ok", "rejected", "ok"])
        self.assertEqual(r[1]["reason"], "silence switch")
        self.assertEqual((r[0]["silence"], r[2]["silence"]), (True, False))

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

    @staticmethod
    def compact(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def test_link_request_received_status_and_duplicates(self):
        request = [1, 0, self.MID, 0, 2, 10, "Szkoła", "osoba na wózku", 2]
        received = [1, 1, self.MID, 0, 1, 1]
        status = [1, 2, self.MID, 0, 2, 2]
        closed = [1, 2, self.MID, 0, 3, 6]
        regression = [1, 2, self.MID, 0, 4, 2]
        out = self.link([self.usb_submit("A", 2, request, self.B), "T 101", "T 102", "T 103", "S", "X",
                         "B> " + self.compact(received), "T 104", "T 105", "T 106", "X",
                         "B> " + self.compact(status), "T 107", "T 108", "T 109",
                         "B> " + self.compact(closed), "T 110", "T 111", "T 112",
                         "B> " + self.compact(regression), "T 113", "T 114", "T 115", "X", "S",
                         # Powtórzony REQUEST (resend): odbiorca odpowiada ponownie zapisanym RECEIVED
                         # i najnowszym STATUS (deduplikacja w aplikacji OSP); A liczy je jako duplikaty.
                         "A " + json.dumps({"usb": 1, "seq": 6, "type": "submit", "to": self.B, "id": self.MID, "revision": 0, "sa1": request, "resend": True}),
                         "T 116", "T 117", "T 118", "T 119", "B> " + self.compact(received), "T 120", "T 121", "T 122",
                         "B> " + self.compact(closed), "T 123", "T 124", "T 125", "S"])
        sent = [line for line in out if line.startswith("A-> ") or line.startswith("B-> ")]
        self.assertTrue(sent[0].startswith('A-> ["WICI",1,"%s","%s",[1,0,' % (self.A, self.B)), sent[0])
        self.assertEqual(sent[1], 'B-> ["WICI",1,"%s","%s",%s]' % (self.B, self.A, self.compact(received)))
        got = [line for line in out if line.startswith("B got ")]
        self.assertEqual(got, ["B got " + self.compact(request)] * 2)
        events = [r for r in self.usb_replies(out, "A") if r["type"] == "event" and r.get("kind") == "message"]
        self.assertEqual([e["sa1"] for e in events], [received, status, closed, regression])
        self.assertEqual({e["source"] for e in events}, {self.B})
        self.assertIn("A:log Status regression", out)
        queue_a = [line for line in out if line.startswith("A queue 1 ")]
        self.assertTrue(queue_a[0].endswith("flags 17 attempts 1 next 703 event 0 state 0"), queue_a[0])  # ACTIVE|SENT, 10 min na RECEIVED
        self.assertTrue(queue_a[1].endswith("flags 18 attempts 1 next 703 event 1 state 1"), queue_a[1])  # DONE|SENT po RECEIVED
        self.assertTrue(queue_a[2].endswith("flags 18 attempts 1 next 703 event 3 state 6"), queue_a[2])  # STATUS 3/6; regresja odrzucona
        stats = [line for line in out if line.startswith("A stats") or line.startswith("B stats")]
        self.assertEqual(stats[0], "A stats sent 1 delivered 1 failed 0 received 0 rejected 0 duplicates 0 conflicts 0 refused 0 confirmed 0 live 1 unsent 0 inbox 0 unread 0")
        self.assertEqual(stats[1], "B stats sent 0 delivered 0 failed 0 received 1")
        self.assertEqual(stats[2], "A stats sent 1 delivered 1 failed 0 received 4 rejected 0 duplicates 0 conflicts 0 refused 0 confirmed 3 live 0 unsent 0 inbox 4 unread 4")
        self.assertEqual(stats[3], "B stats sent 4 delivered 4 failed 0 received 1")
        # Ponowiony REQUEST i powtórzone RECEIVED i STATUS: A przyjmuje je z dowodem jako duplikaty.
        self.assertEqual(stats[4], "A stats sent 2 delivered 2 failed 0 received 6 rejected 0 duplicates 2 conflicts 0 refused 0 confirmed 3 live 1 unsent 0 inbox 4 unread 4")
        self.assertEqual(stats[5], "B stats sent 6 delivered 6 failed 0 received 2")

    def test_link_full_event_ring_keeps_events_and_notifies_later(self):
        # 128 zdarzeń bez ack: nowe zdarzenie nie nadpisuje najstarszego, wiadomość od OSP czeka
        # w skrzynce z flagą INBOX_NOTIFY, a zdarzenie powstaje po ack laptopa.
        request = [1, 0, self.MID, 0, 2, 10, "Szkoła", "osoba na wózku", 2]
        received = [1, 1, self.MID, 0, 1, 1]
        out = self.link(["F 129", self.usb_submit("A", 2, request, self.B), "T 101", "T 102", "T 103",
                         "B> " + self.compact(received), "T 104", "P", "T 105", "P",
                         'A {"usb":1,"seq":3,"type":"ack","cursor":128}', "T 106", "P", "T 107", "P"])
        self.assertIn("filled 128 pending 128", out)   # 129. zdarzenie odrzucone, nic nie nadpisane
        pending = [line for line in out if line.startswith("A notes")]
        self.assertEqual(pending[0], "A notes pending 128 inbox 1 notify 1")
        self.assertEqual(pending[1], "A notes pending 128 inbox 1 notify 1")
        self.assertEqual(pending[3], "A notes pending 1 inbox 1 notify 0")
        events = [r for r in self.usb_replies(out, "A") if r["type"] == "event" and r.get("kind") == "message"]
        self.assertEqual([(r["source"], r["sa1"]) for r in events], [(self.B, received)])
        self.assertEqual(events[0]["record"], 129)   # numer po 128 potwierdzonych
        # Dowód poszedł mimo pełnego pierścienia: wiadomość jest zapisana w skrzynce.
        self.assertIn("B stats sent 1 delivered 1 failed 0 received 1",
                      self.link(["F 128", self.usb_submit("A", 2, request, self.B), "T 101", "T 102", "T 103",
                                 "B> " + self.compact(received), "T 104", "T 105", "S"]))

    def test_link_loss_retry_schedule_and_untrusted_source(self):
        request = [1, 0, self.MID, 0, 2, 10, "Szkoła", "", 1]
        out = self.link(["L 1", self.usb_submit("A", 1, request, self.B),
                         "T 101", "T 102", "T 160", "T 161", "T 162", "X", "S", "D 0", "D 40",
                         "L 0", "T 240", "T 241", "T 242", "X", "S",
                         # Stacja z kartą OSP X odrzuca wiadomość od B.
                         'A {"usb":1,"seq":2,"type":"configure","address":"a","osp":"' + "cc" * 16 + '"}',
                         "B> " + self.compact([1, 1, self.MID, 0, 1, 1]), "T 300", "T 301", "T 302", "S"])
        queue = [line for line in out if line.startswith("A queue 1 ")]
        first = int(re.search(r"next (\d+)", queue[0]).group(1))
        self.assertTrue(queue[0].split(" next ")[0].endswith("flags 1 attempts 1"), queue[0])  # FAILED po 60 s bez dowodu
        self.assertTrue(161 + 48 <= first <= 161 + 72, first)                                   # kolejna po 60 s ±20%
        second = int(re.search(r"next (\d+)", queue[1]).group(1))
        self.assertTrue(queue[1].split(" next ")[0].endswith("flags 17 attempts 2"), queue[1])  # dostarczona za drugim razem
        self.assertTrue(242 + 600 + 1800 <= second <= 242 + 600 + 3600, second)                 # 10 min na RECEIVED + 30–60 min
        self.assertIn("48 48 96 240 720 720 | 2880 1800", out)      # 0,8 x (60, 60, 120, 300, 900, 900); po 6 h 0,8 x 3600; po dostarczeniu 1800
        self.assertIn("72 72 144 360 1080 1080 | 4320 1840", out)  # 1,2 x ...
        stats = [line for line in out if line.startswith("A stats")]
        self.assertTrue(stats[0].startswith("A stats sent 1 delivered 0 failed 1 received 0"))
        self.assertTrue(stats[1].startswith("A stats sent 2 delivered 1 failed 1 received 0 rejected 0"), stats[1])
        self.assertTrue(stats[2].startswith("A stats sent 2 delivered 1 failed 1 received 1 rejected 1"), stats[2])
        self.assertIn("A:log datagram from untrusted source", out)
        # Odrzucony pakiet nie dostaje dowodu: B nie zalicza dostarczenia, próba kończy się po limicie 60 s.
        b_stats = [line for line in out if line.startswith("B stats")]
        self.assertEqual(b_stats[-1], "B stats sent 1 delivered 0 failed 1 received 1")

    def test_link_refused_by_stack_retries_without_attempt(self):
        request = [1, 0, self.MID, 0, 2, 10, "Szkoła", "", 1]
        out = self.link(["N 1", self.usb_submit("A", 1, request, self.B),
                         "T 101", "X", "S", "T 180", "X", "N 0", "T 400", "T 401", "T 402", "X", "S"])
        self.assertEqual(out.count("A-> refused"), 2)
        queue = [line for line in out if line.startswith("A queue 1 ")]
        # Odmowa stosu (np. cel bez ogłoszenia, stos pyta o trasę): bez liczenia próby, następna za 60 s ±20%,
        # po drugiej odmowie za 120 s ±20%.
        self.assertTrue(queue[0].split(" next ")[0].endswith("flags 1 attempts 0"), queue[0])
        self.assertTrue(101 + 48 <= int(re.search(r"next (\d+)", queue[0]).group(1)) <= 101 + 72, queue[0])
        self.assertTrue(180 + 96 <= int(re.search(r"next (\d+)", queue[1]).group(1)) <= 180 + 144, queue[1])
        self.assertTrue(queue[2].split(" next ")[0].endswith("flags 17 attempts 1"), queue[2])
        stats = [line for line in out if line.startswith("A stats")]
        self.assertTrue(stats[0].startswith("A stats sent 0 delivered 0 failed 0 received 0 rejected 0 duplicates 0 conflicts 0 refused 1"), stats[0])
        self.assertTrue(stats[1].startswith("A stats sent 1 delivered 1 failed 0"), stats[1])

    def test_rejects_bad_lengths(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_harness("frame", "3", "1")
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_harness("frame", "104", "1")


if __name__ == "__main__":
    unittest.main()
