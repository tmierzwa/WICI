# SPDX-License-Identifier: MIT
"""Host checks of the radio link layer shared by bench A, bench B and the L0 station: the S2-LP link driver
(firmware/src/s2lp_link.cpp) against a model of the chip (SPI headers, states, FIFOs, read-clear IRQ
status, DS11896), measure::Bench (firmware/src/measure.cpp) against a fake radiolink::Driver
(test series, P1 send with CCA and debt, P1 receive and assembly, FOFF, carrier), and the SX1262 driver
(firmware/src/sx1262.cpp, sx1262_link.cpp) in the LoRa pilot profile against a command-level model of the
chip (BUSY, status byte, registers, buffer, IRQ, warm sleep with the retention list), with measure::Bench
on top of it (TXPKT/TXCW debt and series limit in LoRa air time, RX/RXPER with SNR, no P1 link)."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "firmware" / "src"

STUBS = {
    "Arduino.h": r"""
#pragma once
#include <cmath>
#include <cstdarg>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
constexpr uint8_t OUTPUT = 1, INPUT = 0, INPUT_PULLUP = 2, HIGH = 1, LOW = 0;
extern uint32_t fakeUs;  // one clock for micros() and millis()
inline uint32_t micros() { return fakeUs += 10; }
inline uint32_t millis() { return fakeUs / 1000; }
inline void delay(uint32_t ms) { fakeUs += ms * 1000; }
inline void delayMicroseconds(uint32_t us) { fakeUs += us; }
inline void pinMode(uint8_t, uint8_t) {}
int digitalRead(uint8_t pin);
void digitalWrite(uint8_t pin, uint8_t level);
inline long random(long max) { return std::rand() % max; }
inline void randomSeed(uint32_t seed) { std::srand(seed); }
struct Print {
    size_t write(uint8_t c) { std::putchar(c); return 1; }
    size_t write(const uint8_t* data, size_t n) { return std::fwrite(data, 1, n, stdout); }
    void print(const char* text) { std::fputs(text, stdout); }
    void print(char c) { std::putchar(c); }
};
struct FakeSerial : Print {
    int printf(const char* format, ...) {
        va_list args;
        va_start(args, format);
        const int n = std::vprintf(format, args);
        va_end(args);
        return n;
    }
    void println(const char* text) { std::puts(text); }
    void flush() {}
    int room = 4096;   // wolne miejsce w buforze portu
    int availableForWrite() { return room; }
};
extern FakeSerial Serial;
""",
    "SPI.h": r"""
#pragma once
#include "Arduino.h"
constexpr uint8_t MSBFIRST = 1, SPI_MODE0 = 0;
struct SPISettings { SPISettings() {} SPISettings(uint32_t, uint8_t, uint8_t) {} };
struct SPIClass {
    void beginTransaction(const SPISettings&) {}
    void endTransaction() {}
    uint8_t transfer(uint8_t out);
};
""",
}

S2LP_HARNESS = r"""
#include <deque>
#include <vector>
#include "s2lp_link.h"
#include "s2lp_p1_registers.h"

uint32_t fakeUs = 0;
FakeSerial Serial;
int digitalRead(uint8_t) { return LOW; }

// Model S2-LP: bajty statusu, rejestry, kolejki FIFO, IRQ_STATUS kasowane odczytem, stany po poleceniach.
struct Chip {
    uint8_t regs[256] = {};
    uint8_t state = s2lp::STATE_READY;
    std::vector<uint8_t> txFifo;
    std::deque<uint8_t> rxFifo;
    uint32_t irq = 0;
    int txCountdown = -1;  // transakcje do końca nadawania
    bool holdTx = false;   // nadawanie bez końca (brak TX_DATA_SENT)
    std::vector<uint8_t> lastTx;
    std::vector<uint8_t> commands;
} chip;
bool selected = false;
size_t position = 0;
uint8_t header = 0, address = 0;

void digitalWrite(uint8_t pin, uint8_t level) {
    if (pin != 10) return;
    if (level == LOW && !selected) {
        position = 0;
        if (!chip.holdTx && chip.txCountdown > 0 && --chip.txCountdown == 0) {
            chip.lastTx = chip.txFifo;
            chip.txFifo.clear();
            chip.irq |= s2lp::IRQ_TX_DATA_SENT;
            chip.state = s2lp::STATE_READY;
            chip.txCountdown = -1;
        }
    }
    selected = level == LOW;
}

uint8_t readRegister(uint8_t a) {
    if (a == s2lp::FIFO) {
        if (chip.rxFifo.empty()) return 0;
        const uint8_t v = chip.rxFifo.front();
        chip.rxFifo.pop_front();
        return v;
    }
    if (a == s2lp::MC_STATE0) return static_cast<uint8_t>(chip.state << 1 | 1);
    if (a == s2lp::RX_FIFO_STATUS) return static_cast<uint8_t>(chip.rxFifo.size());
    if (a == s2lp::TX_FIFO_STATUS) return static_cast<uint8_t>(chip.txFifo.size());
    if (a >= s2lp::IRQ_STATUS3 && a <= s2lp::IRQ_STATUS3 + 3) {
        const int shift = 8 * (3 - (a - s2lp::IRQ_STATUS3));
        const uint8_t v = static_cast<uint8_t>(chip.irq >> shift);
        chip.irq &= ~(0xFFu << shift);
        return v;
    }
    return chip.regs[a];
}

void command(uint8_t code) {
    chip.commands.push_back(code);
    switch (code) {
        case s2lp::CMD_TX:
            if (chip.state == s2lp::STATE_READY) {
                chip.state = s2lp::STATE_TX;
                chip.txCountdown = 4;
            }
            break;
        case s2lp::CMD_RX: if (chip.state == s2lp::STATE_READY) chip.state = s2lp::STATE_RX; break;
        case s2lp::CMD_READY: case s2lp::CMD_SABORT: chip.state = s2lp::STATE_READY; chip.txCountdown = -1; break;
        case s2lp::CMD_FLUSHRXFIFO: chip.rxFifo.clear(); break;
        case s2lp::CMD_FLUSHTXFIFO: chip.txFifo.clear(); break;
        default: break;
    }
}

uint8_t SPIClass::transfer(uint8_t out) {
    uint8_t in = 0;
    if (position == 0) { header = out; in = chip.regs[s2lp::MC_STATE1]; }
    else if (position == 1) {
        address = out;
        in = static_cast<uint8_t>(chip.state << 1 | 1);
        if (header == s2lp::HEADER_COMMAND) command(out);
    } else if (header == s2lp::HEADER_READ) {
        in = readRegister(address == s2lp::FIFO ? address : static_cast<uint8_t>(address + position - 2));
    } else if (header == s2lp::HEADER_WRITE) {
        if (address == s2lp::FIFO) chip.txFifo.push_back(out);
        else chip.regs[static_cast<uint8_t>(address + position - 2)] = out;
    }
    ++position;
    return in;
}

void injectFrame(size_t length, uint8_t first, uint8_t rssiRaw, uint8_t sqi) {
    for (size_t i = 0; i < length; ++i) chip.rxFifo.push_back(static_cast<uint8_t>(first + i));
    chip.regs[s2lp::RX_PCKT_LEN1] = static_cast<uint8_t>(length >> 8);
    chip.regs[s2lp::RX_PCKT_LEN1 + 1] = static_cast<uint8_t>(length);
    chip.regs[s2lp::RSSI_LEVEL] = rssiRaw;
    chip.regs[s2lp::LINK_QUALIF1] = static_cast<uint8_t>(0x80 | sqi);
    chip.irq |= s2lp::IRQ_VALID_SYNC | s2lp::IRQ_RX_DATA_READY;
}

void printCommands(const char* tag) {
    printf("%s", tag);
    for (uint8_t c : chip.commands) printf(" %02X", c);
    printf("\n");
    chip.commands.clear();
}

uint32_t synt() {
    return (static_cast<uint32_t>(chip.regs[s2lp::SYNT3] & 0x0F) << 24) | (static_cast<uint32_t>(chip.regs[s2lp::SYNT3 + 1]) << 16) |
           (static_cast<uint32_t>(chip.regs[s2lp::SYNT3 + 2]) << 8) | chip.regs[s2lp::SYNT3 + 3];
}

int main() {
    SPIClass spi;
    s2lp::Radio radio(spi, 10, 9, 1000000);
    radio.begin();
    radio.configure(p1s2::REGISTERS, p1s2::REGISTER_COUNT);
    s2lp::LinkDriver link(radio);
    chip.commands.clear();

    // Nośna CW: MOD_TYPE 7, dane PN9; po STOP wartości z tablicy P1.
    const bool cw = link.startCw();
    printf("CW %d %s %02X %02X\n", cw, link.stateName(), chip.regs[s2lp::MOD2], chip.regs[s2lp::PCKTCTRL1]);
    link.stopCw();
    printf("CWSTOP %s %02X %02X\n", link.stateName(), chip.regs[s2lp::MOD2], chip.regs[s2lp::PCKTCTRL1]);
    chip.commands.clear();

    // Ramka P1 (zmienna długość): LEN z PCKTLEN, w kolejce BODY i CRC bez bajtu LEN.
    uint8_t frame[21];
    frame[0] = 20;
    for (int i = 1; i < 21; ++i) frame[i] = static_cast<uint8_t>(0xA0 + i);
    const bool sentVariable = link.transmit(frame, sizeof(frame), true, nullptr);
    printf("TXV %d %02X %u %zu %02X %02X %s\n", sentVariable, chip.regs[s2lp::PCKTCTRL2],
           (chip.regs[s2lp::PCKTLEN1] << 8) | chip.regs[s2lp::PCKTLEN0], chip.lastTx.size(), chip.lastTx.front(),
           chip.lastTx.back(), link.stateName());
    printCommands("TXVCMD");

    // Ramka wzorcowa (stała długość) z czasami: bez wyjścia „pakiet w powietrzu” tylko czas całkowity.
    radiolink::TxTiming timing;
    const bool sentFixed = link.transmit(frame, 10, false, &timing);
    printf("TXF %d %02X %u %zu %d %d\n", sentFixed, chip.regs[s2lp::PCKTCTRL2],
           (chip.regs[s2lp::PCKTLEN1] << 8) | chip.regs[s2lp::PCKTLEN0], chip.lastTx.size(), timing.valid, timing.totalUs > 0);

    // Brak przerwania TX_DATA_SENT: po czasie ramki SABORT, opróżnienie kolejki TX, READY.
    chip.holdTx = true;
    chip.commands.clear();
    const uint32_t before = millis();
    const bool stuck = link.transmit(frame, sizeof(frame), true, nullptr);
    printf("TXSTUCK %d %s %zu %d\n", stuck, link.stateName(), chip.txFifo.size(), millis() - before >= 120);
    printCommands("TXSTUCKCMD");
    chip.holdTx = false;

    // Odbiór P1 w trybie zmiennej długości: PCKTLEN = 102, stan RX.
    const bool rx = link.startRx(true, 0);
    printf("RX %d %s %02X %u\n", rx, link.stateName(), chip.regs[s2lp::PCKTCTRL2],
           (chip.regs[s2lp::PCKTLEN1] << 8) | chip.regs[s2lp::PCKTLEN0]);
    radiolink::Frame out;
    printf("POLL0 %d\n", static_cast<int>(link.pollRx(out)));
    chip.irq |= s2lp::IRQ_VALID_SYNC;
    printf("SYNC %d\n", link.receivingFrame());
    injectFrame(20, 0x10, 60, 0x15);
    const radiolink::RxPoll got = link.pollRx(out);
    printf("FRAME %d %zu %02X %02X %02X %d %u %d\n", static_cast<int>(got), out.length, out.bytes[0], out.bytes[1],
           out.bytes[out.length - 1], out.rssiDbm, out.quality, link.receivingFrame());
    printf("POLL1 %d\n", static_cast<int>(link.pollRx(out)));
    chip.commands.clear();
    injectFrame(5, 0x10, 60, 0x15);  // LEN poniżej MIN_LEN: odrzucona, kolejka opróżniona, znów RX
    // pollRx zmienia stan: wynik najpierw do zmiennej (kolejność argumentów printf zależy od kompilatora).
    int polled = static_cast<int>(link.pollRx(out));
    printf("SHORT %d %s %zu\n", polled, link.stateName(), chip.rxFifo.size());
    printCommands("SHORTCMD");
    // Bajty następnego pakietu w kolejce obok ramki (pętla stała): ramka odpada, kolejka pusta, znów RX.
    injectFrame(20, 0x10, 60, 0x15);
    chip.rxFifo.push_back(0x55);
    polled = static_cast<int>(link.pollRx(out));
    printf("EXTRA %d %s %zu\n", polled, link.stateName(), chip.rxFifo.size());
    chip.irq |= s2lp::IRQ_RX_FIFO_ERROR;
    polled = static_cast<int>(link.pollRx(out));
    printf("OVERFLOW %d %s\n", polled, link.stateName());
    chip.irq |= s2lp::IRQ_RX_DATA_DISC;
    printf("DISC %d\n", static_cast<int>(link.pollRx(out)));
    chip.state = s2lp::STATE_READY;  // np. SABORT z polecenia portu
    polled = static_cast<int>(link.pollRx(out));
    printf("REENTER %d %s\n", polled, link.stateName());
    chip.regs[s2lp::RSSI_LEVEL_RUN] = 40;
    const radiolink::Rssi r = link.rssi();
    printf("RSSI %d %d\n", r.valid, r.dbm);

    // Ramka wzorcowa w odbiorze stałej długości.
    link.startRx(false, 12);
    injectFrame(12, 0x40, 70, 0x10);
    const radiolink::RxPoll fixed = link.pollRx(out);
    printf("FIXED %d %zu %02X %02X %02X\n", static_cast<int>(fixed), out.length, out.bytes[0], out.bytes[11],
           chip.regs[s2lp::PCKTCTRL2]);

    // Korekta częstotliwości przez słowo SYNT; odbiór wraca po zapisie.
    const uint32_t base = synt();
    const bool inRange = link.setFrequencyOffset(1000);
    printf("FOFF %d %ld %ld %ld %s\n", inRange, static_cast<long>(synt()) - static_cast<long>(base),
           static_cast<long>(link.frequencyOffsetRaw()), static_cast<long>(link.frequencyOffsetHz()), link.stateName());
    printf("FOFFMAX %d %d\n", link.setFrequencyOffset(1000001), link.setFrequencyOffset(-1000000));
    link.setFrequencyOffset(0);
    printf("FOFF0 %ld %02X\n", static_cast<long>(synt()) - static_cast<long>(base), chip.regs[s2lp::SYNT3]);
    return 0;
}
"""

BENCH_HARNESS = r"""
#include <deque>
#include <vector>
#include "measure.h"
#include "p1frame.h"
#include "testframe.h"

uint32_t fakeUs = 0;
FakeSerial Serial;
int digitalRead(uint8_t) { return HIGH; }
void digitalWrite(uint8_t, uint8_t) {}
// Generator stacji (w obrazie: main.cpp nad drbg); tu deterministyczny licznik.
void measure::randomBytes(uint8_t* out, size_t count) {
    static uint8_t next = 1;
    for (size_t i = 0; i < count; ++i) out[i] = next++;
}

struct RamStorage : journal::Storage {
    std::vector<uint8_t> bytes = std::vector<uint8_t>(512 * 1024, 0xFF);
    bool read(uint32_t address, uint8_t* data, size_t count) override {
        memcpy(data, &bytes[address], count);
        return true;
    }
    bool write(uint32_t address, const uint8_t* data, size_t count) override {
        memcpy(&bytes[address], data, count);
        return true;
    }
};

// Sterownik zastępczy: zapisuje nadane ramki, podaje ramki z kolejki, kanał zajęty przez busyChecks sprawdzeń.
struct FakeDriver : radiolink::Driver {
    std::vector<std::vector<uint8_t>> sent;
    std::vector<bool> sentVariable;
    std::deque<radiolink::Frame> rxQueue;
    std::deque<radiolink::RxPoll> rxErrors;
    bool rxActive = false, rxVariable = false, cw = false;
    uint8_t rxLength = 0;
    int busyChecks = 0;
    int32_t offset = 0;
    const char* stateName() override { return cw ? "TX" : rxActive ? "RX" : "IDLE"; }
    void idle() override { rxActive = false; cw = false; }
    bool startCw() override { cw = true; return true; }
    void stopCw() override { cw = false; }
    bool transmit(const uint8_t* frame, size_t length, bool variable, radiolink::TxTiming* timing) override {
        sent.emplace_back(frame, frame + length);
        sentVariable.push_back(variable);
        if (timing) { timing->valid = true; timing->totalUs = 1000; timing->leadUs = 100; timing->onAirUs = 800; timing->tailUs = 100; }
        return true;
    }
    bool startRx(bool variable, uint8_t fixedLength) override {
        rxActive = true; rxVariable = variable; rxLength = fixedLength;
        return true;
    }
    radiolink::RxPoll pollRx(radiolink::Frame& out) override {
        if (!rxErrors.empty()) { const radiolink::RxPoll e = rxErrors.front(); rxErrors.pop_front(); return e; }
        if (rxQueue.empty()) return radiolink::RxPoll::Nothing;
        out = rxQueue.front();
        rxQueue.pop_front();
        return radiolink::RxPoll::Frame;
    }
    bool receivingFrame() override { return busyChecks > 0 && busyChecks--; }
    radiolink::Rssi rssi() override { radiolink::Rssi r; r.valid = true; r.dbm = -120; return r; }
    bool setFrequencyOffset(int32_t hz) override {
        if (hz > 1000000 || hz < -1000000) return false;
        offset = hz / 25;
        return true;
    }
    void reapplyFrequencyOffset() override {}
    int32_t frequencyOffsetHz() override { return offset * 25; }
    int32_t frequencyOffsetRaw() override { return offset; }
    double frequencyStepHz() const override { return 25.0; }
    bool frequencyErrorHz(int32_t&) override { return false; }
    // Profil P1 jak na CC1120 i S2-LP.
    uint32_t frameAirMs(size_t length) const override { return radiolink::p1FrameAirMs(length, 4800); }
    double onAirMs(size_t length) const override { return length * 8 * 1000.0 / 4800; }
    size_t maxTestLength() const override { return p1frame::MAX_FRAME; }
    uint32_t seriesMaxMs() const override { return radiolink::P1_SERIES_MAX_MS; }
    bool p1Link() const override { return true; }
};

FakeDriver radio;
std::vector<uint8_t> received;
int txDone = -1;
uint32_t uptime() { return millis() / 1000; }

void runFor(measure::Bench& bench, uint32_t ms) {
    const uint32_t end = millis() + ms;
    while (millis() < end) {
        fakeUs += 1000;
        bench.poll();
    }
}

int main() {
    RamStorage ram;
    journal::Journal journal(ram);
    journal.begin();
    measure::Bench bench(radio, 3, -1);
    bench.attach(&journal, uptime);
    bench.onDatagram([](const uint8_t* data, size_t length, void*) { received.assign(data, data + length); }, nullptr);
    bench.onTxDone([](bool ok, void*) { txDone = ok; }, nullptr);
    fakeUs = 1000000;

    const char* error = bench.txpkt(3, 20, 0, false);
    printf("NOPREP %s\n", error ? error : "-");
    bench.prep = true;
    printf("NOCONFIG %s %s\n", bench.txpkt(3, 20, 0, false), bench.p1send(reinterpret_cast<const uint8_t*>("x"), 1));
    bench.p1Ready = true;  // tablica P1 zapisana (main.cpp: radiocon::p1Ok)
    error = bench.txpkt(3, 20, 0, false);
    runFor(bench, 50);
    int good = 0;
    for (const auto& f : radio.sent) good += testframe::check(f.data(), f.size(), nullptr);
    printf("TXPKT %s %zu %d %d %d %lu\n", error ? error : "-", radio.sent.size(), good, static_cast<int>(radio.sentVariable[0]),
           bench.busy(), static_cast<unsigned long>(bench.debtRemainingMs() > 0));
    printf("DEBTLOCK %s\n", bench.txpkt(1, 20, 0, false));

    // Nadanie datagramu P1: czeka na dług, CCA 50 ms z jednym zajęciem kanału, fragmenty o zmiennej długości.
    radio.sent.clear();
    radio.sentVariable.clear();
    uint8_t datagram[300];
    for (size_t i = 0; i < sizeof(datagram); ++i) datagram[i] = static_cast<uint8_t>(i * 7);
    radio.busyChecks = 1;
    error = bench.p1send(datagram, sizeof(datagram));
    printf("P1SEND %s %d %d\n", error ? error : "-", radio.rxActive, radio.rxVariable);
    runFor(bench, 5000);
    bool lengthsOk = true;
    p1frame::Assembler assembler;
    size_t assembled = 0;
    for (size_t i = 0; i < radio.sent.size(); ++i) {
        const auto& f = radio.sent[i];
        lengthsOk = lengthsOk && radio.sentVariable[i] && f[0] + 1u == f.size();
        p1frame::Fragment fragment;
        if (p1frame::parseFrame(f.data(), f.size(), fragment) == p1frame::Parse::OK) {
            if (assembler.push(fragment, millis()) == p1frame::Outcome::COMPLETE) assembled = assembler.completedLength();
        }
    }
    const measure::LinkCounters& c = bench.link();
    printf("P1TX %zu %d %d %lu %lu %lu %d %d\n", radio.sent.size(), lengthsOk, txDone, static_cast<unsigned long>(c.txDatagrams),
           static_cast<unsigned long>(c.txFragments), static_cast<unsigned long>(c.deferrals), static_cast<int>(assembled),
           radio.rxActive);

    // Odbiór P1: fragmenty z sterownika, zły i przepełnienie liczone jako rx_bad, datagram do warstwy aplikacji.
    uint8_t id[p1frame::ID_BYTES] = {1, 2, 3, 4, 5, 6, 7, 8};
    uint8_t incoming[200];
    for (size_t i = 0; i < sizeof(incoming); ++i) incoming[i] = static_cast<uint8_t>(255 - i);
    for (uint8_t index = 0; index < p1frame::fragmentCount(sizeof(incoming)); ++index) {
        radiolink::Frame f;
        f.length = p1frame::buildFrame(incoming, sizeof(incoming), id, index, f.bytes);
        f.rssiDbm = -90;
        f.quality = 20;
        radio.rxQueue.push_back(f);
    }
    radio.rxErrors.push_back(radiolink::RxPoll::Bad);
    radio.rxErrors.push_back(radiolink::RxPoll::Overflow);
    runFor(bench, 50);
    printf("P1RX %zu %d %lu %lu %lu\n", received.size(), received.size() == sizeof(incoming) &&
           !memcmp(received.data(), incoming, sizeof(incoming)), static_cast<unsigned long>(c.rxOk),
           static_cast<unsigned long>(c.rxBad), static_cast<unsigned long>(c.rxDatagrams));

    // Wiersz datagramu tylko w całości: 200 B to wiersz około 500 B, więc przy 256 B wolnego bufora (CDC nRF52)
    // wychodzi wiersz bez danych, a przy 60 B żaden; datagram i tak trafia do warstwy aplikacji.
    for (const int room : {256, 60}) {
        Serial.room = room;
        received.clear();
        ++id[0];
        for (uint8_t index = 0; index < p1frame::fragmentCount(sizeof(incoming)); ++index) {
            radiolink::Frame f;
            f.length = p1frame::buildFrame(incoming, sizeof(incoming), id, index, f.bytes);
            f.rssiDbm = -90;
            radio.rxQueue.push_back(f);
        }
        runFor(bench, 50);
        printf("P1RXROOM %d %zu\n", room, received.size());
    }
    Serial.room = 4096;

    // Odbiór ramek wzorcowych: RSSI i jakość z ramki sterownika.
    bench.stop();
    // rxStart zmienia stan atrapy radia: najpierw wynik, potem odczyt pól.
    const char* rxStarted = bench.rxStart(20) ? "error" : "-";
    printf("RXSTART %s %d %d %u\n", rxStarted, radio.rxActive, radio.rxVariable, radio.rxLength);
    for (uint16_t seq = 0; seq < 3; ++seq) {
        radiolink::Frame f;
        testframe::build(f.bytes, 20, seq);
        f.length = 20;
        f.rssiDbm = -80;
        f.quality = 30;
        radio.rxQueue.push_back(f);
    }
    runFor(bench, 50);
    const measure::Counters& t = bench.counters();
    printf("TESTRX %lu %ld %lu\n", static_cast<unsigned long>(t.rxOk), static_cast<long>(t.rssiSum), static_cast<unsigned long>(t.lqiSum));

    const char* foffOutside = bench.foff(2000000);
    const char* foffBand = bench.foff(-50001);   // w zakresie układu, poza podpasmem: bez zapisu do układu
    const char* foffEdge = bench.foff(50000) ? "error" : "-";
    const long edgeOffset = static_cast<long>(radio.offset);
    const char* foffInside = bench.foff(1000) ? "error" : "-";
    printf("FOFF %s %s %ld\n", foffOutside ? foffOutside : "-", foffInside, static_cast<long>(radio.offset));
    printf("FOFFBAND %s|%s %ld\n", foffBand ? foffBand : "-", foffEdge, edgeOffset);
    bench.printFoff();

    // Nośna po odczekaniu długu: stan układu w polu "marc", koniec po czasie.
    bench.stop();
    runFor(bench, 20000);
    error = bench.txcw(1, false);
    printf("TXCW %s %d\n", error ? error : "-", radio.cw);
    runFor(bench, 1100);
    printf("TXCWEND %d\n", radio.cw);
    return 0;
}
"""


SX1262_HARNESS = r"""
#include <vector>
#include "journal.h"
#include "measure.h"
#include "sx1262_link.h"
#include "testframe.h"

uint32_t fakeUs = 0;
FakeSerial Serial;
void measure::randomBytes(uint8_t* out, size_t count) {
    static uint8_t next = 1;
    for (size_t i = 0; i < count; ++i) out[i] = next++;
}

constexpr uint8_t PIN_CS = 10, PIN_RESET = 9, PIN_BUSY = 14, PIN_RXEN = 42, PIN_OK = 39;

// Model SX1262 na poziomie poleceń: bajt statusu (tryb), rejestry 16-bitowe, bufor 256 B, IRQ kasowane
// poleceniem, tryb powrotu STDBY_RC po TxDone, odbiór ciągły, uśpienie z ciepłym startem i listą
// rejestrów zachowywanych (karta, rozdz. 9.6: bez wpisu 0x08AC wraca do 0x94), BUSY, NRESET i RXEN.
struct Chip {
    std::vector<uint8_t> regs = std::vector<uint8_t>(0x10000, 0);
    uint8_t buffer[256] = {};
    uint8_t mode = sx1262::MODE_STBY_RC;
    bool sleeping = false;
    uint16_t irq = 0, errors = 0;
    uint8_t packetType = 0;
    uint8_t packetParams[6] = {}, modulation[4] = {}, paConfig[4] = {}, txParams[2] = {}, tcxo[4] = {};
    uint32_t rf = 0, rxTimeout = 0;
    int txCountdown = -1;
    bool holdTx = false, busyStuck = false, rxen = false, rxenAtTx = true;
    unsigned txCount = 0;
    std::vector<uint8_t> lastTx;
    uint8_t rxLength = 0, rxStart = 0, rssiPkt = 0, snrPkt = 0, rssiInst = 0;
    std::vector<uint8_t> ops;
} chip;
std::vector<uint8_t> bytes;

void resetChip() {
    std::fill(chip.regs.begin(), chip.regs.end(), 0);
    const char* version = "SX1261 V2D 2D02";
    for (size_t i = 0; i < 16; ++i) chip.regs[0x0320 + i] = static_cast<uint8_t>(version[i]);
    chip.regs[0x0740] = 0x14; chip.regs[0x0741] = 0x24;
    chip.regs[0x08AC] = 0x94; chip.regs[0x0736] = 0x09; chip.regs[0x08D8] = 0xC0; chip.regs[0x08E7] = 0x18;
    chip.packetType = 0;
    chip.mode = sx1262::MODE_STBY_RC;
    chip.sleeping = false;
    chip.irq = 0;
    chip.errors = 0x20;  // kalibracja po włączeniu zasilania bez TCXO: XOSC_START
    std::fill(chip.tcxo, chip.tcxo + 4, 0);
    chip.txCountdown = -1;
}

uint8_t status() { return static_cast<uint8_t>(chip.mode << 4); }

void execute() {
    if (bytes.empty()) return;
    const uint8_t op = bytes[0];
    const uint8_t* p = bytes.data() + 1;
    const size_t n = bytes.size() - 1;
    chip.ops.push_back(op);
    switch (op) {
        case sx1262::OP_SET_STANDBY: chip.mode = sx1262::MODE_STBY_RC; chip.txCountdown = -1; break;
        case sx1262::OP_SET_TX:
            if (chip.mode == sx1262::MODE_STBY_RC || chip.mode == sx1262::MODE_STBY_XOSC) {
                chip.mode = sx1262::MODE_TX;
                chip.txCountdown = 3;
                chip.rxenAtTx = chip.rxen;
            }
            break;
        case sx1262::OP_SET_RX: chip.mode = sx1262::MODE_RX; chip.rxTimeout = p[0] << 16 | p[1] << 8 | p[2]; break;
        case sx1262::OP_SET_TX_CW: chip.mode = sx1262::MODE_TX; chip.txCountdown = -1; chip.rxenAtTx = chip.rxen; break;
        case sx1262::OP_SET_SLEEP: {
            chip.sleeping = true;
            chip.mode = 0;
            const bool retained = chip.regs[0x029F] >= 1 && chip.regs[0x02A0] == 0x08 && chip.regs[0x02A1] == 0xAC;
            if (!(p[0] & 0x04)) resetChip(), chip.sleeping = true, chip.mode = 0;
            else if (!retained) chip.regs[0x08AC] = 0x94;
            break;
        }
        case sx1262::OP_WRITE_REGISTER: {
            const uint16_t a = static_cast<uint16_t>(p[0] << 8 | p[1]);
            for (size_t i = 2; i < n; ++i) chip.regs[static_cast<uint16_t>(a + i - 2)] = p[i];
            break;
        }
        case sx1262::OP_WRITE_BUFFER: for (size_t i = 1; i < n; ++i) chip.buffer[static_cast<uint8_t>(p[0] + i - 1)] = p[i]; break;
        case sx1262::OP_CLEAR_IRQ_STATUS: chip.irq &= static_cast<uint16_t>(~(p[0] << 8 | p[1])); break;
        case sx1262::OP_SET_PACKET_TYPE: chip.packetType = p[0]; break;
        case sx1262::OP_SET_PACKET_PARAMS: std::copy(p, p + 6, chip.packetParams); break;
        case sx1262::OP_SET_MODULATION_PARAMS: std::copy(p, p + 4, chip.modulation); break;
        case sx1262::OP_SET_RF_FREQUENCY: chip.rf = static_cast<uint32_t>(p[0]) << 24 | p[1] << 16 | p[2] << 8 | p[3]; break;
        case sx1262::OP_SET_PA_CONFIG: std::copy(p, p + 4, chip.paConfig); chip.regs[0x08E7] = 0x38; break;
        case sx1262::OP_SET_TX_PARAMS: std::copy(p, p + 2, chip.txParams); break;
        case sx1262::OP_SET_DIO3_TCXO: std::copy(p, p + 4, chip.tcxo); break;
        case sx1262::OP_CLEAR_DEVICE_ERRORS: chip.errors = 0; break;
        case sx1262::OP_CALIBRATE: if (!chip.tcxo[0]) chip.errors |= 0x20; break;
        default: break;
    }
}

int digitalRead(uint8_t pin) {
    if (pin == PIN_BUSY) return chip.busyStuck || chip.sleeping ? HIGH : LOW;
    return pin == PIN_OK ? HIGH : LOW;
}

void digitalWrite(uint8_t pin, uint8_t level) {
    if (pin == PIN_RESET && level == LOW) resetChip();
    if (pin == PIN_RXEN) chip.rxen = level == HIGH;
    if (pin != PIN_CS) return;
    if (level == LOW) {
        if (chip.sleeping) { chip.sleeping = false; chip.mode = sx1262::MODE_STBY_RC; }
        bytes.clear();
        if (!chip.holdTx && chip.txCountdown > 0 && --chip.txCountdown == 0) {
            chip.lastTx.assign(chip.buffer, chip.buffer + chip.packetParams[3]);
            chip.irq |= sx1262::IRQ_TX_DONE;
            chip.mode = sx1262::MODE_STBY_RC;
            chip.txCountdown = -1;
            ++chip.txCount;
        }
    } else {
        execute();
    }
}

uint8_t SPIClass::transfer(uint8_t out) {
    const size_t pos = bytes.size();
    bytes.push_back(out);
    if (pos == 0) return status();
    switch (bytes[0]) {
        case sx1262::OP_READ_REGISTER:
            return pos < 4 ? status() : chip.regs[static_cast<uint16_t>((bytes[1] << 8 | bytes[2]) + pos - 4)];
        case sx1262::OP_READ_BUFFER: return pos < 3 ? status() : chip.buffer[static_cast<uint8_t>(bytes[1] + pos - 3)];
        case sx1262::OP_GET_IRQ_STATUS: return pos == 1 ? status() : pos == 2 ? chip.irq >> 8 : chip.irq & 0xFF;
        case sx1262::OP_GET_RX_BUFFER_STATUS: return pos == 1 ? status() : pos == 2 ? chip.rxLength : chip.rxStart;
        case sx1262::OP_GET_PACKET_STATUS: return pos == 1 ? status() : pos == 2 ? chip.rssiPkt : pos == 3 ? chip.snrPkt : 0;
        case sx1262::OP_GET_RSSI_INST: return pos == 1 ? status() : chip.rssiInst;
        case sx1262::OP_GET_DEVICE_ERRORS: return pos == 1 ? status() : pos == 2 ? chip.errors >> 8 : chip.errors & 0xFF;
        case sx1262::OP_GET_PACKET_TYPE: return pos == 1 ? status() : chip.packetType;
        default: return status();
    }
}

void injectFrame(size_t length, uint8_t start, uint8_t first, uint16_t extraIrq = 0) {
    for (size_t i = 0; i < length; ++i) chip.buffer[static_cast<uint8_t>(start + i)] = static_cast<uint8_t>(first + i);
    chip.rxLength = static_cast<uint8_t>(length);
    chip.rxStart = start;
    chip.rssiPkt = 160;  // -80 dBm
    chip.snrPkt = 0xE4;  // -28 ćwiartek: -7 dB
    chip.irq |= sx1262::IRQ_PREAMBLE_DETECTED | sx1262::IRQ_HEADER_VALID | sx1262::IRQ_RX_DONE | extraIrq;
}

int indexOf(uint8_t op) {
    for (size_t i = 0; i < chip.ops.size(); ++i) if (chip.ops[i] == op) return static_cast<int>(i);
    return -1;
}

struct RamStorage : journal::Storage {
    std::vector<uint8_t> data = std::vector<uint8_t>(512 * 1024, 0xFF);
    bool failWrites = false;  // zapis do FRAM odrzucony (np. uszkodzona pamięć)
    long budget = -1;         // bajty zapisu do zaniku zasilania (zapis przerwany w połowie serii); -1 bez limitu
    bool read(uint32_t address, uint8_t* out, size_t count) override { memcpy(out, &data[address], count); return true; }
    bool write(uint32_t address, const uint8_t* in, size_t count) override {
        if (failWrites) return false;
        size_t n = count;
        if (budget >= 0) {
            if (static_cast<size_t>(budget) < n) n = static_cast<size_t>(budget);
            budget -= static_cast<long>(n);
        }
        memcpy(&data[address], in, n);
        return n == count;
    }
};
uint32_t uptime() { return millis() / 1000; }

void runFor(measure::Bench& bench, uint32_t ms) {
    const uint32_t end = millis() + ms;
    while (millis() < end) {
        fakeUs += 1000;
        bench.poll();
    }
}

int main() {
    SPIClass spi;
    sx1262::Radio radio(spi, PIN_CS, PIN_RESET, PIN_BUSY, 1000000);
    sx1262::LinkDriver link(radio, PIN_RXEN);
    radio.begin();
    link.begin();
    fakeUs = 1000000;

    // Reset i identyfikacja z tekstu wersji; profil utracony przed CONFIG.
    const bool reset = radio.reset();
    const sx1262::Identity id = radio.identify();
    printf("ID %d %d %s\n", reset, id.sx126x, id.version);
    const bool lostBefore = link.profileLost();
    chip.ops.clear();
    const sx1262::VerifyResult config = link.configure();
    printf("CONFIG %u %u %s\n", config.checked, config.mismatches, config.firstName);
    printf("LOST %d %d\n", lostBefore, link.profileLost());
    // Kolejność: TCXO, kasowanie błędów, kalibracja, DC-DC, DIO2, typ pakietu, obraz, częstotliwość, PA, moc.
    printf("ORDER %d %d %d %d %d %d %d %d %d %d\n", indexOf(sx1262::OP_SET_DIO3_TCXO), indexOf(sx1262::OP_CLEAR_DEVICE_ERRORS),
           indexOf(sx1262::OP_CALIBRATE), indexOf(sx1262::OP_SET_REGULATOR_MODE), indexOf(sx1262::OP_SET_DIO2_RF_SWITCH),
           indexOf(sx1262::OP_SET_PACKET_TYPE), indexOf(sx1262::OP_CALIBRATE_IMAGE), indexOf(sx1262::OP_SET_RF_FREQUENCY),
           indexOf(sx1262::OP_SET_PA_CONFIG), indexOf(sx1262::OP_SET_TX_PARAMS));
    printf("TCXO %02X %02X %02X %02X\n", chip.tcxo[0], chip.tcxo[1], chip.tcxo[2], chip.tcxo[3]);
    printf("RF %08lX\n", static_cast<unsigned long>(chip.rf));
    printf("MOD %02X %02X %02X %02X\n", chip.modulation[0], chip.modulation[1], chip.modulation[2], chip.modulation[3]);
    printf("PKT %02X %02X %02X %02X %02X %02X\n", chip.packetParams[0], chip.packetParams[1], chip.packetParams[2], chip.packetParams[3],
           chip.packetParams[4], chip.packetParams[5]);
    printf("PA %02X %02X %02X %02X %02X %02X %02X\n", chip.paConfig[0], chip.paConfig[1], chip.paConfig[2], chip.paConfig[3],
           chip.txParams[0], chip.txParams[1], chip.regs[0x08E7]);
    printf("REGS %02X %02X %02X %02X %02X %02X %02X %02X %02X\n", chip.regs[0x0740], chip.regs[0x0741], chip.regs[0x08AC],
           chip.regs[0x029F], chip.regs[0x02A0], chip.regs[0x02A1], chip.regs[0x0736], chip.regs[0x0889], chip.regs[0x08D8]);
    printf("RXEN %d %s\n", chip.rxen, link.stateName());

    // Uśpienie z ciepłym startem: Rx Boosted zostaje dzięki liście; bez wpisu wraca do 0x94.
    uint8_t gain = 0;
    bool woke = link.sleepAndWake(gain);
    printf("SLEEP %d %02X %s\n", woke, gain, link.stateName());
    chip.regs[0x029F] = 0;
    woke = link.sleepAndWake(gain);
    printf("SLEEPNORET %d %02X %d\n", woke, gain, link.profileLost());
    radio.reset();
    link.configure();
    const sx1262::VerifyResult again = link.verify();
    chip.regs[0x0740] = 0x34;  // słowo synchronizacji publiczne: VERIFY wskazuje rejestr
    const sx1262::VerifyResult changed = link.verify();
    printf("VERIFY %u %u %s %04X %02X %02X\n", again.mismatches, changed.mismatches, changed.firstName, changed.firstAddress,
           changed.expected, changed.actual);
    chip.regs[0x0740] = 0x14;

    // Nośna CW: SetTxContinuousWave, RXEN niski; STOP do STDBY_RC.
    chip.ops.clear();
    const bool cw = link.startCw();
    printf("CW %d %s %d %d\n", cw, link.stateName(), chip.rxenAtTx, indexOf(sx1262::OP_SET_TX_CW) >= 0);
    link.stopCw();
    printf("CWSTOP %s\n", link.stateName());

    // Ramka wzorcowa 20 B: długość w parametrach pakietu, treść z bufora, RXEN niski przy TX, powrót do STDBY_RC.
    uint8_t frame[255];
    for (int i = 0; i < 255; ++i) frame[i] = static_cast<uint8_t>(0xA0 + i);
    radiolink::TxTiming timing;
    const bool sent = link.transmit(frame, 20, false, &timing);
    printf("TX %d %u %zu %02X %02X %d %s %d %d\n", sent, chip.packetParams[3], chip.lastTx.size(), chip.lastTx.front(), chip.lastTx.back(),
           chip.rxenAtTx, link.stateName(), timing.valid, timing.totalUs > 0);
    printf("TXLEN %d %d\n", link.transmit(frame, 0, false, nullptr), link.transmit(frame, 256, false, nullptr));
    chip.holdTx = true;
    const uint32_t before = millis();
    const bool stuck = link.transmit(frame, 20, false, nullptr);
    printf("TXSTUCK %d %s %d %d\n", stuck, link.stateName(), millis() - before >= lora::frameAirMs(20) + 100,
           millis() - before < lora::frameAirMs(20) + 120);
    chip.holdTx = false;

    // Odbiór ciągły ramek 12 B: RXEN wysoki, SetRx 0xFFFFFF; ramka z bufora od wskaźnika, RSSI i SNR pakietu.
    const bool rx = link.startRx(false, 12);
    printf("RX %d %s %d %06lX\n", rx, link.stateName(), chip.rxen, static_cast<unsigned long>(chip.rxTimeout));
    radiolink::Frame out;
    int polled = static_cast<int>(link.pollRx(out));
    printf("POLL0 %d\n", polled);
    chip.irq |= sx1262::IRQ_PREAMBLE_DETECTED;
    const bool busyPreamble = link.receivingFrame();
    printf("BUSYPRE %d\n", busyPreamble);
    injectFrame(12, 0x40, 0x10);
    polled = static_cast<int>(link.pollRx(out));
    const bool busyAfter = link.receivingFrame();
    printf("FRAME %d %zu %02X %02X %d %d %u %d %04X\n", polled, out.length, out.bytes[0], out.bytes[11], out.rssiDbm, out.snrQdb,
           out.quality, busyAfter, chip.irq);
    injectFrame(10, 0x00, 0x10);
    polled = static_cast<int>(link.pollRx(out));
    printf("WRONGLEN %d %s\n", polled, link.stateName());
    injectFrame(12, 0x00, 0x10, sx1262::IRQ_CRC_ERR);
    polled = static_cast<int>(link.pollRx(out));
    printf("CRC %d %s\n", polled, link.stateName());
    chip.irq |= sx1262::IRQ_HEADER_ERR;
    polled = static_cast<int>(link.pollRx(out));
    printf("HEADER %d %s\n", polled, link.stateName());
    chip.mode = sx1262::MODE_STBY_RC;  // np. SetStandby z polecenia portu
    polled = static_cast<int>(link.pollRx(out));
    printf("REENTER %d %s %d\n", polled, link.stateName(), chip.rxen);
    chip.rssiInst = 200;
    const radiolink::Rssi r = link.rssi();
    printf("RSSI %d %d\n", r.valid, r.dbm);
    // Preambuła bez końca ramki: kanał zajęty najwyżej przez czas najdłuższej ramki.
    chip.irq |= sx1262::IRQ_PREAMBLE_DETECTED;
    const bool preambleBusy = link.receivingFrame();
    fakeUs += 500000;
    const bool preambleLater = link.receivingFrame();
    printf("PREAMBLE %d %d %04X\n", preambleBusy, preambleLater, chip.irq);
    link.startRx(true, 0);
    injectFrame(33, 0x80, 0x20);
    polled = static_cast<int>(link.pollRx(out));
    printf("VAR %d %zu\n", polled, out.length);

    // Korekta częstotliwości słowem RF (krok 0,954 Hz); odbiór wraca po zapisie.
    const bool inRange = link.setFrequencyOffset(1000);
    printf("FOFF %d %ld %ld %ld %s\n", inRange, static_cast<long>(chip.rf) - 911763046L, static_cast<long>(link.frequencyOffsetRaw()),
           static_cast<long>(link.frequencyOffsetHz()), link.stateName());
    printf("FOFFMAX %d %d\n", link.setFrequencyOffset(1000001), link.setFrequencyOffset(-1000000));
    link.setFrequencyOffset(0);
    printf("FOFF0 %08lX\n", static_cast<unsigned long>(chip.rf));
    link.idle();
    const radiolink::Rssi idleRssi = link.rssi();
    printf("IDLE %s %d %d\n", link.stateName(), chip.rxen, idleRssi.valid);

    // BUSY bez zejścia: transakcja odrzucona i policzona.
    chip.busyStuck = true;
    const bool commandOk = radio.command(sx1262::OP_SET_STANDBY);
    printf("BUSY %d %lu\n", commandOk, static_cast<unsigned long>(radio.busyTimeouts()));
    chip.busyStuck = false;

    // Polecenia pomiarowe w profilu LoRa (measure::Bench nad tym sterownikiem).
    RamStorage ram;
    journal::Journal journal(ram);
    journal.begin();
    measure::Bench bench(link, PIN_OK, -1);
    bench.attach(&journal, uptime);
    bench.prep = true;
    bench.p1Ready = true;
    const uint8_t datagram[1] = {0x42};
    const char* p1rx = bench.p1rxStart();
    const char* p1tx = bench.p1send(datagram, 1);
    printf("NOP1 %s|%s|%lu\n", p1rx, p1tx, static_cast<unsigned long>(bench.link().txDrop));
    printf("LEN %s|%s\n", bench.txpkt(1, 3, 0, false), bench.rxStart(3));
    printf("LIMIT %s\n", bench.txpkt(3, 255, 0, false));
    const unsigned txBefore = chip.txCount;
    const char* started = bench.txpkt(2, 255, 0, false);
    const uint32_t debtLogged = journal.debt().a;
    runFor(bench, 50);
    const bool frameOk = testframe::check(chip.lastTx.data(), chip.lastTx.size(), nullptr);
    printf("TXPKT %s %u %zu %d %lu %d\n", started ? started : "-", chip.txCount - txBefore, chip.lastTx.size(), frameOk,
           static_cast<unsigned long>(debtLogged), bench.busy());
    const uint32_t wait = bench.debtRemainingMs();
    printf("DEBT %d %s\n", wait > 9900 && wait <= 10056, bench.txpkt(1, 20, 0, false));
    runFor(bench, 10200);
    printf("CLEARED %lu %lu\n", static_cast<unsigned long>(bench.debtRemainingMs()), static_cast<unsigned long>(journal.debt().a));
    bench.silence = true;
    printf("SILENCE %s\n", bench.txpkt(1, 20, 0, false));
    bench.silence = false;
    // TXCW 1 s nie mieści się w limicie serii LoRa (838 ms) bez CONDUCTED.
    printf("TXCW %s\n", bench.txcw(1, false));
    // Odbiór ramek wzorcowych 255 B: RXPER ze średnim SNR.
    const char* rxStarted = bench.rxStart(255);
    printf("RXSTART %s %s %d\n", rxStarted ? rxStarted : "-", link.stateName(), chip.rxen);
    for (uint16_t seq = 0; seq < 3; ++seq) {
        testframe::build(chip.buffer, 255, seq);
        chip.rxLength = 255;
        chip.rxStart = 0;
        chip.rssiPkt = 180;
        chip.snrPkt = static_cast<uint8_t>(20 + 4 * seq);
        chip.irq |= sx1262::IRQ_RX_DONE;
        runFor(bench, 10);
    }
    bench.rxper();

    // Tryb pracy do badań EMC: ramka 255 B co 6 s (13 x 419 ms = 5,4 s), odbiór ramek wzorcowych
    // między ramkami, tryb zapisany w dzienniku i wznawiany po restarcie bez trybu przygotowania.
    bench.prep = false;
    printf("EMCPREP %s\n", bench.emcStart(6, 255));
    bench.prep = true;
    printf("EMCPERIOD %s\n", bench.emcStart(5, 255));
    const unsigned emcTxBefore = chip.txCount;
    const char* emcStarted = bench.emcStart(6, 255);
    const uint32_t emcRecord = journal.emc();
    printf("EMCBUSY %s|%s\n", bench.txpkt(1, 20, 0, false), bench.rxStart(20));
    runFor(bench, 50);
    const bool emcFrameOk = testframe::check(chip.lastTx.data(), chip.lastTx.size(), nullptr);
    printf("EMCFIRST %s %u %zu %d %lu %s %d\n", emcStarted ? emcStarted : "-", chip.txCount - emcTxBefore, chip.lastTx.size(),
           emcFrameOk, static_cast<unsigned long>(journal.debt().a), link.stateName(), chip.rxen);
    testframe::build(chip.buffer, 255, 7);  // ramka stacji pomocniczej
    chip.rxLength = 255;
    chip.rxStart = 0;
    chip.irq |= sx1262::IRQ_RX_DONE;
    runFor(bench, 12010);
    printf("EMCRUN %u\n", chip.txCount - emcTxBefore);
    bench.silence = true;
    runFor(bench, 6000);
    bench.silence = false;
    printf("EMCSILENT %u\n", chip.txCount - emcTxBefore);
    bench.stop();  // jak CONFIG albo wyjście z trybu przygotowania: tryb zostaje, odbiór wraca
    bench.prep = false;
    runFor(bench, 1100);
    printf("EMCRX %s %d %d\n", link.stateName(), chip.rxen, bench.emcActive());
    bench.printEmc();
    // Restart: nowy dziennik i stanowisko na tej samej pamięci, bez trybu przygotowania.
    journal::Journal journal2(ram);
    journal2.begin();
    measure::Bench bench2(link, PIN_OK, -1);
    bench2.attach(&journal2, uptime);
    bench2.p1Ready = true;
    journal2.writeSettings(3, 5);  // zapis ustawień ekranu nie kasuje trybu
    const bool resumed = bench2.emcResume(journal2.emc());
    const unsigned beforeResume = chip.txCount;
    runFor(bench2, 100);
    printf("EMCRESUME %d %08lX %08lX %u %d\n", resumed, static_cast<unsigned long>(emcRecord),
           static_cast<unsigned long>(journal2.emc()), chip.txCount - beforeResume, bench2.prep);
    bench2.emcStop();
    journal::Journal journal3(ram);
    journal3.begin();
    printf("EMCSTOP %d %lu %lu %lu\n", bench2.emcActive(), static_cast<unsigned long>(journal2.emc()),
           static_cast<unsigned long>(journal3.emc()), static_cast<unsigned long>(journal3.settings().a));
    const bool badResumed = bench2.emcResume(measure::emcEncode(1, 255));
    printf("EMCBAD %d %d %lu\n", badResumed, bench2.emcActive(), static_cast<unsigned long>(journal2.emc()));
    // EMC 0 przy nieudanym zapisie: tryb staje, ale rekord zostaje i wynik to błąd; następna próba kasuje.
    bench2.prep = true;
    const char* restarted = bench2.emcStart(6, 255);
    ram.failWrites = true;
    const char* clearError = bench2.emcStop();
    const bool keptActive = bench2.emcActive();
    journal::Journal journal4(ram);
    journal4.begin();
    printf("EMCCLEARFAIL %s|%s|%d %d\n", restarted ? restarted : "-", clearError ? clearError : "-", keptActive,
           journal4.emc() != 0);
    ram.failWrites = false;
    const char* retryError = bench2.emcStop();
    journal::Journal journal5(ram);
    journal5.begin();
    printf("EMCCLEARRETRY %s %lu\n", retryError ? retryError : "-", static_cast<unsigned long>(journal5.emc()));
    // Zanik zasilania w trakcie nadpisywania zatwierdzonego gniazda pierścienia wejść w tryb
    // przygotowania: zapis przerwany, nie rekord uszkodzony (fałszywe PREP_RESTARTED przy kontroli naklejki).
    RamStorage torn;
    journal::Journal prepJournal(torn);
    prepJournal.begin();
    bool prepWritten = true;
    for (uint32_t entry = 0; entry < 11; ++entry) prepWritten = prepJournal.enterPrep(entry) && prepWritten;
    torn.budget = 10;
    const bool tornWritten = prepJournal.enterPrep(11);
    torn.budget = -1;
    journal::Journal prepAfter(torn);
    prepAfter.begin();
    printf("PREPTORN %d %d %d %lu\n", prepWritten, tornWritten, prepAfter.prepCorrupt(),
           static_cast<unsigned long>(prepAfter.prepEntries()));
    return 0;
}
"""


def host_compiler():
    for name in ("c++", "g++", "clang++"):
        if shutil.which(name):
            return shutil.which(name)
    return None


def build_and_run(harness, sources):
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        for name, text in STUBS.items():
            (root / name).write_text(text, encoding="utf-8")
        (root / "harness.cpp").write_text(harness, encoding="utf-8")
        subprocess.run([host_compiler(), "-std=c++17", "-Wall", "-Wextra", "-Werror", f"-I{root}", f"-I{SRC}",
                        str(root / "harness.cpp")] + [str(SRC / s) for s in sources] + ["-o", str(root / "harness")],
                       check=True)
        out = subprocess.run([str(root / "harness")], capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def line(lines, tag):
    return next(text for text in lines if text.split(" ", 1)[0] == tag)


@unittest.skipUnless(host_compiler(), "no host C++ compiler")
class S2lpLinkTests(unittest.TestCase):
    """s2lp_link.cpp against a model of the S2-LP (DS11896): packet handler, FIFOs, IRQ, states."""

    @classmethod
    def setUpClass(cls):
        cls.out = build_and_run(S2LP_HARNESS, ["s2lp.cpp", "s2lp_link.cpp"])

    def test_carrier_uses_cw_modulation_and_restores_table(self):
        self.assertEqual(line(self.out, "CW"), "CW 1 TX 74 0C")  # MOD_TYPE 7, DATARATE_E 4; TXSOURCE PN9
        self.assertEqual(line(self.out, "CWSTOP"), "CWSTOP READY A4 00")  # P1 table: 2-GFSK BT 0.5, normal TX source

    def test_variable_frame_len_comes_from_pcktlen(self):
        # PCKTCTRL2 bit FIX_VAR_LEN, PCKTLEN = LEN = 20; the FIFO holds BODY and CRC (20 B) without LEN.
        self.assertEqual(line(self.out, "TXV"), "TXV 1 01 20 20 A1 B4 READY")
        cmds = line(self.out, "TXVCMD").split()[1:]
        self.assertIn("72", cmds)  # FLUSHTX before the write
        self.assertEqual(cmds[-1], "60")  # TX from READY

    def test_missing_tx_done_aborts_and_flushes(self):
        self.assertEqual(line(self.out, "TXSTUCK"), "TXSTUCK 0 READY 0 1")
        self.assertEqual(line(self.out, "TXSTUCKCMD").split()[-3:], ["60", "67", "72"])  # TX, SABORT, FLUSHTX

    def test_fixed_frame_reports_total_time_only(self):
        self.assertEqual(line(self.out, "TXF"), "TXF 1 00 10 10 0 1")

    def test_receive_variable_frame_with_rssi_and_sqi(self):
        self.assertEqual(line(self.out, "RX"), "RX 1 RX 01 102")
        self.assertEqual(line(self.out, "POLL0"), "POLL0 0")
        self.assertEqual(line(self.out, "SYNC"), "SYNC 1")  # VALID_SYNC: channel busy for CCA
        # LEN byte rebuilt from RX_PCKT_LEN, 20 payload bytes; RSSI_LEVEL 60 - 146 dBm; SQI from LINK_QUALIF1.
        self.assertEqual(line(self.out, "FRAME"), "FRAME 1 21 14 10 23 -86 21 0")
        self.assertEqual(line(self.out, "POLL1"), "POLL1 0")

    def test_bad_length_overflow_and_discard_restart_receive(self):
        self.assertEqual(line(self.out, "SHORT"), "SHORT 2 RX 0")
        self.assertEqual(line(self.out, "SHORTCMD").split()[1:], ["67", "71", "61"])  # SABORT from RX, FLUSHRX, RX
        self.assertEqual(line(self.out, "EXTRA"), "EXTRA 2 RX 0")
        self.assertEqual(line(self.out, "OVERFLOW"), "OVERFLOW 3 RX")
        self.assertEqual(line(self.out, "DISC"), "DISC 2")
        self.assertEqual(line(self.out, "REENTER"), "REENTER 0 RX")
        self.assertEqual(line(self.out, "RSSI"), "RSSI 1 -106")

    def test_fixed_receive(self):
        self.assertEqual(line(self.out, "FIXED"), "FIXED 1 12 40 4B 00")

    def test_frequency_offset_moves_synt_word(self):
        # Step f_xo / 2^19 / 4 = 23.84 Hz: 1000 Hz -> 42 steps -> 1001.4 Hz; receiver back in RX.
        self.assertEqual(line(self.out, "FOFF"), "FOFF 1 42 42 1001 RX")
        self.assertEqual(line(self.out, "FOFFMAX"), "FOFFMAX 0 1")
        self.assertEqual(line(self.out, "FOFF0"), "FOFF0 0 62")  # SYNT3 keeps CP_ISEL 3, BS 0


@unittest.skipUnless(host_compiler(), "no host C++ compiler")
class BenchTests(unittest.TestCase):
    """measure.cpp over radiolink::Driver: the same measurement and P1 link logic on both radios."""

    @classmethod
    def setUpClass(cls):
        cls.out = build_and_run(BENCH_HARNESS, ["measure.cpp", "p1frame.cpp", "testframe.cpp", "journal.cpp"])

    def test_test_series_needs_preparation_and_writes_debt(self):
        self.assertEqual(line(self.out, "NOPREP"), "NOPREP preparation mode off: PREP 1")
        # Bez zapisanej tablicy P1 nie nadaje ani seria, ani datagram (układ na wartościach domyślnych).
        self.assertEqual(line(self.out, "NOCONFIG"), "NOCONFIG radio not configured: CONFIG radio not configured: CONFIG")
        self.assertEqual(line(self.out, "TXPKT"), "TXPKT - 3 3 0 0 1")  # fixed length, valid test frames
        self.assertEqual(line(self.out, "DEBTLOCK"), "DEBTLOCK silence debt pending: see INFO tx_wait_ms")

    def test_p1_send_waits_cca_and_sends_variable_fragments(self):
        self.assertEqual(line(self.out, "P1SEND"), "P1SEND - 1 1")
        # 300 B -> 4 fragments with LEN first; one deferral; the fragments reassemble; receiver back on.
        self.assertEqual(line(self.out, "P1TX"), "P1TX 4 1 1 1 4 1 300 1")

    def test_p1_receive_assembles_and_counts_errors(self):
        self.assertEqual(line(self.out, "P1RX"), "P1RX 200 1 3 2 1")
        datagrams = [l for l in self.out if l.startswith('{"p1rx":"datagram"')]
        self.assertEqual(len(datagrams), 2)
        full, omitted = (json.loads(l) for l in datagrams)
        self.assertEqual(bytes.fromhex(full["data"]), bytes(255 - i for i in range(200)))
        self.assertEqual((omitted["len"], omitted["data_omitted"], "data" in omitted), (200, True, False))
        self.assertEqual([l for l in self.out if l.startswith("P1RXROOM")], ["P1RXROOM 256 200", "P1RXROOM 60 200"])

    def test_test_frames_received_with_driver_rssi(self):
        self.assertEqual(line(self.out, "RXSTART"), "RXSTART - 1 0 20")
        self.assertEqual(line(self.out, "TESTRX"), "TESTRX 3 -240 90")

    def test_frequency_offset_and_carrier_via_driver(self):
        self.assertEqual(line(self.out, "FOFF"), "FOFF FOFF outside the subband: max +-50000 Hz - 40")
        # 125 kHz channel at 869.525 MHz leaves the 869.4-869.65 MHz subband beyond 62.5 kHz
        self.assertEqual(line(self.out, "FOFFBAND"), "FOFFBAND FOFF outside the subband: max +-50000 Hz|- 2000")
        self.assertIn('{"foff_hz":1000,"set":true,"freqoff":40,"applied_hz":1000.0,"step_hz":25.00}', self.out)
        self.assertEqual(line(self.out, "TXCW"), "TXCW - 1")
        self.assertIn('"marc":"TX"', next(text for text in self.out if text.startswith('{"txcw":true')))
        self.assertEqual(line(self.out, "TXCWEND"), "TXCWEND 0")


@unittest.skipUnless(host_compiler(), "no host C++ compiler")
class Sx1262LinkTests(unittest.TestCase):
    """sx1262_link.cpp in the LoRa pilot profile against a command-level model of the SX1262, and
    measure::Bench on top of it: the measurement commands of the L0 station."""

    @classmethod
    def setUpClass(cls):
        cls.out = build_and_run(SX1262_HARNESS, ["sx1262.cpp", "sx1262_link.cpp", "measure.cpp", "p1frame.cpp", "testframe.cpp",
                                                 "journal.cpp"])

    def test_identity_and_profile_verified(self):
        self.assertEqual(line(self.out, "ID"), "ID 1 1 SX1261 V2D 2D02")  # the SX1262 reports this string (RadioLib checks "SX126")
        self.assertEqual(line(self.out, "CONFIG"), "CONFIG 12 0 ")  # packet type, 10 registers, device errors
        self.assertEqual(line(self.out, "LOST"), "LOST 1 0")

    def test_tcxo_before_calibration_then_profile(self):
        order = [int(v) for v in line(self.out, "ORDER").split()[1:]]
        self.assertNotIn(-1, order)
        self.assertEqual(order, sorted(order))
        self.assertEqual(line(self.out, "TCXO"), "TCXO 02 00 01 40")  # 1.8 V, 5 ms = 320 x 15.625 us

    def test_lora_pilot_profile_parameters(self):
        self.assertEqual(line(self.out, "RF"), "RF 36586666")  # 869.525 MHz x 2^25 / 32 MHz
        self.assertEqual(line(self.out, "MOD"), "MOD 07 04 01 00")  # SF7, 125 kHz, CR 4/5, LDRO off
        self.assertEqual(line(self.out, "PKT"), "PKT 00 18 00 FF 01 00")  # 24 symbols, explicit header, CRC on, normal IQ
        self.assertEqual(line(self.out, "PA"), "PA 01 04 00 01 13 04 18")  # PA as RadioLib paOptTable for 13 dBm, 200 us ramp, OCP 60 mA

    def test_rx_boosted_sync_word_and_errata_registers(self):
        # sync 0x12 -> 0x14 0x24; 0x08AC = 0x96 with retention list {0x08AC}; IQ, modulation and clamp fixes.
        self.assertEqual(line(self.out, "REGS"), "REGS 14 24 96 01 08 AC 0D 04 DE")
        self.assertEqual(line(self.out, "RXEN"), "RXEN 0 STBY_RC")

    def test_rx_boosted_kept_after_warm_sleep_only_with_retention(self):
        self.assertEqual(line(self.out, "SLEEP"), "SLEEP 1 96 STBY_RC")
        self.assertEqual(line(self.out, "SLEEPNORET"), "SLEEPNORET 1 94 1")
        self.assertEqual(line(self.out, "VERIFY"), "VERIFY 0 1 SYNC_WORD_MSB 0740 14 34")

    def test_carrier(self):
        self.assertEqual(line(self.out, "CW"), "CW 1 TX 0 1")
        self.assertEqual(line(self.out, "CWSTOP"), "CWSTOP STBY_RC")

    def test_transmit_frame_and_timeout(self):
        self.assertEqual(line(self.out, "TX"), "TX 1 20 20 A0 B3 0 STBY_RC 0 1")
        self.assertEqual(line(self.out, "TXLEN"), "TXLEN 0 0")
        self.assertEqual(line(self.out, "TXSTUCK"), "TXSTUCK 0 STBY_RC 1 1")

    def test_continuous_receive_with_rssi_and_snr(self):
        self.assertEqual(line(self.out, "RX"), "RX 1 RX 1 FFFFFF")
        self.assertEqual(line(self.out, "POLL0"), "POLL0 0")
        self.assertEqual(line(self.out, "BUSYPRE"), "BUSYPRE 1")
        # 12 B from buffer offset 0x40; RssiPkt 160 -> -80 dBm; SnrPkt -28 quarter dB; receive IRQs cleared.
        self.assertEqual(line(self.out, "FRAME"), "FRAME 1 12 10 1B -80 -28 0 0 0000")
        self.assertEqual(line(self.out, "WRONGLEN"), "WRONGLEN 2 RX")
        self.assertEqual(line(self.out, "CRC"), "CRC 2 RX")
        self.assertEqual(line(self.out, "HEADER"), "HEADER 2 RX")
        self.assertEqual(line(self.out, "REENTER"), "REENTER 0 RX 1")
        self.assertEqual(line(self.out, "RSSI"), "RSSI 1 -100")
        self.assertEqual(line(self.out, "PREAMBLE"), "PREAMBLE 1 0 0000")
        self.assertEqual(line(self.out, "VAR"), "VAR 1 33")

    def test_frequency_offset_moves_rf_word(self):
        # Step 32 MHz / 2^25 = 0.954 Hz: 1000 Hz -> 1049 steps -> 1000 Hz; receiver back in RX.
        self.assertEqual(line(self.out, "FOFF"), "FOFF 1 1049 1049 1000 RX")
        self.assertEqual(line(self.out, "FOFFMAX"), "FOFFMAX 0 1")
        self.assertEqual(line(self.out, "FOFF0"), "FOFF0 36586666")
        self.assertEqual(line(self.out, "IDLE"), "IDLE STBY_RC 0 0")

    def test_busy_timeout_refuses_transaction(self):
        self.assertEqual(line(self.out, "BUSY"), "BUSY 0 1")

    def test_measurement_commands_in_lora_air_time(self):
        self.assertEqual(line(self.out, "NOP1"), "NOP1 no P1 link on this radio|no P1 link on this radio|0")
        self.assertEqual(line(self.out, "LEN"), "LEN len 4..255|len 4..255")
        # 3 x 255 B = 3 x 419 ms > 838 ms (the largest datagram in two frames).
        self.assertEqual(line(self.out, "LIMIT"), "LIMIT series above limit: add conducted")
        # 2 x 255 B: debt 12 x 838 ms in the FRAM journal before the first frame.
        self.assertEqual(line(self.out, "TXPKT"), "TXPKT - 2 255 1 10056 0")
        self.assertEqual(line(self.out, "DEBT"), "DEBT 1 silence debt pending: see INFO tx_wait_ms")
        self.assertEqual(line(self.out, "CLEARED"), "CLEARED 0 0")
        self.assertEqual(line(self.out, "SILENCE"), "SILENCE radio silence")
        self.assertEqual(line(self.out, "TXCW"), "TXCW series above limit: add conducted")
        planned = next(text for text in self.out if text.startswith('{"txpkt":"started"'))
        self.assertIn('"tx_ms_planned":838', planned)
        done = next(text for text in self.out if text.startswith('{"txpkt":"done"'))
        self.assertIn('"sent":2,"failed":0,"len":255', done)
        self.assertIn('"expected_on_air_ms":416.00', done)

    def test_rxper_reports_snr(self):
        self.assertEqual(line(self.out, "RXSTART"), "RXSTART - RX 1")
        per = next(text for text in self.out if text.startswith('{"rx_ok":'))
        self.assertIn('"rx_ok":3,"rx_bad":0,"missing":0', per)
        self.assertIn('"rssi_avg_dbm":-90.0', per)
        self.assertIn('{"snr_avg_db":6.00,"rx_ok":3}', self.out)  # (20 + 24 + 28) / 3 / 4

    def test_emc_mode_needs_preparation_and_a_period_of_13_frames(self):
        self.assertEqual(line(self.out, "EMCPREP"), "EMCPREP preparation mode off: PREP 1")
        self.assertEqual(line(self.out, "EMCPERIOD"), "EMCPERIOD period 6..3600 s")  # 13 x 419 ms = 5.4 s
        self.assertEqual(line(self.out, "EMCBUSY"), "EMCBUSY EMC mode on: EMC 0 first|EMC mode on: EMC 0 first")

    def test_emc_mode_sends_with_debt_and_receives_between_frames(self):
        # First frame at once, debt 12 x 419 ms in the journal before it, then reception of test frames.
        self.assertEqual(line(self.out, "EMCFIRST"), "EMCFIRST - 1 255 1 5028 RX 1")
        self.assertEqual(line(self.out, "EMCRUN"), "EMCRUN 3")  # 0, 6 and 12 s
        self.assertEqual(line(self.out, "EMCSILENT"), "EMCSILENT 3")  # silence skips the 18 s frame
        self.assertEqual(line(self.out, "EMCRX"), "EMCRX RX 1 1")  # STOP of a task or leaving preparation keeps the mode
        tx = [text for text in self.out if text.startswith('{"emc":"tx"')]
        self.assertEqual(len(tx), 4)  # three before the restart, one after it
        self.assertIn('"seq":2,"ok":true,"sent":3,"rx_ok":1', tx[2])
        self.assertIn('"seq":0,"ok":true,"sent":1,', tx[3])
        status = next(text for text in self.out if text.startswith('{"emc":true'))
        self.assertIn('"period_s":6,"len":255,"min_period_s":6,"resumed":false,"journal":true,', status)
        self.assertIn('"sent":3,"failed":0,"silenced":1,"skipped":0,"rx_ok":1,"rx_bad":0,"missing":0', status)

    def test_emc_mode_resumes_after_restart_and_stops_with_record(self):
        # The record survives a screen-settings write and brings the mode back without preparation mode.
        self.assertEqual(line(self.out, "EMCRESUME"), "EMCRESUME 1 80FF0006 80FF0006 1 0")
        self.assertEqual(line(self.out, "EMCSTOP"), "EMCSTOP 0 0 0 3")  # cleared, language kept
        self.assertEqual(line(self.out, "EMCBAD"), "EMCBAD 0 0 0")  # a 1 s period is refused on resume too

    def test_emc_stop_reports_a_record_left_in_the_journal(self):
        # A failed clear stops the frames but keeps the record, so EMC 0 must report it; a retry clears it.
        self.assertEqual(line(self.out, "EMCCLEARFAIL"),
                         "EMCCLEARFAIL -|EMC journal clear failed: mode returns after restart|0 1")
        self.assertEqual(line(self.out, "EMCCLEARRETRY"), "EMCCLEARRETRY - 0")

    def test_torn_overwrite_of_a_small_record_is_not_corrupt(self):
        # The mark is cleared before the slot is overwritten: a torn write leaves an uncommitted slot,
        # so the 11 entries stay readable and preparation entries are not flagged as tampered.
        self.assertEqual(line(self.out, "PREPTORN"), "PREPTORN 1 0 0 11")


if __name__ == "__main__":
    unittest.main()
