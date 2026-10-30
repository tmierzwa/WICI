# SPDX-License-Identifier: MIT
"""Host checks of the radio link layer shared by bench A, bench B and the L0 station: the S2-LP link driver
(firmware/src/s2lp_link.cpp) against a model of the chip (SPI headers, states, FIFOs, read-clear IRQ
status, DS11896), measure::Bench (firmware/src/measure.cpp) against a fake radiolink::Driver
(test series, P1 send with CCA and debt, P1 receive and assembly, FOFF, carrier), and the SX1262 driver
(firmware/src/sx1262.cpp, sx1262_link.cpp) in the LoRa pilot profile against a command-level model of the
chip (BUSY, status byte, registers, ring buffer of continuous receive, IRQ, standby modes and fallback, CAD,
warm sleep with the retention list): transmit in steps with CAD, the receive sample (late frames, seen flags
only, activity marks, removed module under the radio lock), with measure::Bench on top of it (TXPKT/TXCW
debt and series limit in LoRa air time, RX/RXPER with SNR, no P1 link), and measure::Bench with the RNode
framing over a fake LoRa driver (stack link: TX sequence, deferrals, silence, assembly, re-arm, EMC)."""

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

    // Układ P1: bez CAD i bez nadawania w krokach; próg CCA wspólny P1.
    const uint8_t one[1] = {0};
    printf("P1DEFAULTS %d %d %d %d\n", static_cast<int>(link.cad()), static_cast<int>(link.prepareTx(one, 1)), link.sendPrepared(nullptr),
           link.ccaThresholdDbm());
    return 0;
}
"""

BENCH_HARNESS = r"""
#include <deque>
#include <vector>
#include "measure.h"
#include "p1frame.h"
#include "platform.h"
#include "testframe.h"

uint32_t fakeUs = 0;
FakeSerial Serial;
int digitalRead(uint8_t) { return HIGH; }
void digitalWrite(uint8_t, uint8_t) {}
bool platform::radioLockTake(uint32_t) { return true; }  // łącze P1: bez zadania odbioru
void platform::radioLockGive() {}
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
    radiolink::Framing framing() const override { return radiolink::Framing::P1; }
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
#include <algorithm>
#include <functional>
#include <vector>
#include "journal.h"
#include "platform.h"
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

// Blokada operacji radia: licznik zamiast mutexu FreeRTOS (sprawdza, że próbka nie zwalnia cudzej blokady).
int lockDepth = 0;
bool platform::radioLockTake(uint32_t) { ++lockDepth; return true; }
void platform::radioLockGive() { --lockDepth; }

// Model SX1262 na poziomie poleceń: bajt statusu (tryb), rejestry 16-bitowe, bufor 256 B jako pierścień
// (odbiór ciągły pisze każdy pakiet dalej od końca poprzedniego, karta rozdz. 7.2 i 13.2.3), IRQ kasowane
// poleceniem, SetStandby do STDBY_RC albo STDBY_XOSC, tryb powrotu po TxDone z SetRxTxFallbackMode,
// CAD z powrotem do STDBY_RC (tabela 13-73), odbiór ciągły, uśpienie z ciepłym startem i listą
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
    int txCountdown = -1, cadCountdown = -1;
    bool holdTx = false, busyStuck = false, rxen = false, rxenAtTx = true;
    bool cadBusy = false, cadHang = false;  // CAD wykrywa preambułę; CAD bez końca
    uint8_t fallback = 0x20, rxPtr = 0, cadParams[7] = {}, dioIrq[8] = {};
    unsigned cadCount = 0;
    uint8_t hookOp = 0;               // polecenie, przed którym model zmienia stan eteru (hook)
    std::function<void()> hook;
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
    chip.cadCountdown = -1;
    chip.fallback = 0x20;
}

uint8_t status() { return static_cast<uint8_t>(chip.mode << 4); }

void execute() {
    if (bytes.empty()) return;
    const uint8_t op = bytes[0];
    const uint8_t* p = bytes.data() + 1;
    const size_t n = bytes.size() - 1;
    chip.ops.push_back(op);
    if (chip.hook && op == chip.hookOp) {
        std::function<void()> hook = chip.hook;
        chip.hook = nullptr;
        hook();
    }
    switch (op) {
        case sx1262::OP_SET_STANDBY:
            chip.mode = p[0] == sx1262::STDBY_XOSC ? sx1262::MODE_STBY_XOSC : sx1262::MODE_STBY_RC;
            chip.txCountdown = chip.cadCountdown = -1;
            break;
        case sx1262::OP_SET_RX_TX_FALLBACK: chip.fallback = p[0]; break;
        case sx1262::OP_SET_DIO_IRQ_PARAMS: std::copy(p, p + 8, chip.dioIrq); break;
        case sx1262::OP_SET_CAD_PARAMS: std::copy(p, p + 7, chip.cadParams); break;
        case sx1262::OP_SET_CAD:
            if (chip.mode == sx1262::MODE_STBY_RC || chip.mode == sx1262::MODE_STBY_XOSC) {
                chip.mode = sx1262::MODE_RX;  // demodulator pracuje w czasie CAD
                chip.cadCountdown = 2;
            }
            break;
        case sx1262::OP_SET_TX:
            if (chip.mode == sx1262::MODE_STBY_RC || chip.mode == sx1262::MODE_STBY_XOSC) {
                chip.mode = sx1262::MODE_TX;
                chip.txCountdown = 3;
                chip.rxenAtTx = chip.rxen;
            }
            break;
        case sx1262::OP_SET_RX:
            chip.mode = sx1262::MODE_RX;
            chip.rxTimeout = p[0] << 16 | p[1] << 8 | p[2];
            chip.rxPtr = 0;  // RxBaseAddr; w odbiorze ciągłym dalej od poprzedniego pakietu
            break;
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
            chip.mode = chip.fallback == 0x30 ? sx1262::MODE_STBY_XOSC : chip.fallback == 0x40 ? sx1262::MODE_FS : sx1262::MODE_STBY_RC;
            chip.txCountdown = -1;
            ++chip.txCount;
        }
        if (!chip.cadHang && chip.cadCountdown > 0 && --chip.cadCountdown == 0) {
            chip.irq |= sx1262::IRQ_CAD_DONE | (chip.cadBusy ? sx1262::IRQ_CAD_DETECTED : 0);
            chip.mode = sx1262::MODE_STBY_RC;  // CAD_ONLY: zawsze STDBY_RC, niezależnie od trybu powrotu
            chip.cadCountdown = -1;
            ++chip.cadCount;
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

// Koniec ramki w buforze od `start`. Flagi początku ramki skasowała już wcześniejsza próbka odbioru.
void injectFrame(size_t length, uint8_t start, uint8_t first, uint16_t extraIrq = 0) {
    for (size_t i = 0; i < length; ++i) chip.buffer[static_cast<uint8_t>(start + i)] = static_cast<uint8_t>(first + i);
    chip.rxLength = static_cast<uint8_t>(length);
    chip.rxStart = start;
    chip.rssiPkt = 160;  // -80 dBm
    chip.snrPkt = 0xE4;  // -28 ćwiartek: -7 dB
    chip.irq |= sx1262::IRQ_RX_DONE | extraIrq;
}

// Odbiór ciągły w eterze: początek ramki (preambuła, nagłówek) i pierwsze `written` bajtów treści od
// wskaźnika odbioru, potem koniec ramki; następny pakiet pisze się dalej, z zawinięciem bufora.
uint8_t frameStart = 0;
void airHeader(uint8_t first, size_t written) {
    frameStart = chip.rxPtr;
    for (size_t i = 0; i < written; ++i) chip.buffer[static_cast<uint8_t>(frameStart + i)] = static_cast<uint8_t>(first + i);
    chip.irq |= sx1262::IRQ_PREAMBLE_DETECTED | sx1262::IRQ_HEADER_VALID;
}
void airEnd(size_t length, uint8_t first) {
    for (size_t i = 0; i < length; ++i) chip.buffer[static_cast<uint8_t>(frameStart + i)] = static_cast<uint8_t>(first + i);
    chip.rxStart = frameStart;
    chip.rxLength = static_cast<uint8_t>(length);
    chip.rxPtr = static_cast<uint8_t>(frameStart + length);
    chip.irq |= sx1262::IRQ_RX_DONE;
}
void airFrame(size_t length, uint8_t first) {  // cała ramka między dwiema próbkami odbioru
    airHeader(first, 0);
    chip.irq &= static_cast<uint16_t>(~(sx1262::IRQ_PREAMBLE_DETECTED | sx1262::IRQ_HEADER_VALID));  // próbka w trakcie ramki
    airEnd(length, first);
}
bool bytesFrom(const radiolink::Frame& f, uint8_t first) {
    for (size_t i = 0; i < f.length; ++i) if (f.bytes[i] != static_cast<uint8_t>(first + i)) return false;
    return f.length > 0;
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

    // Konfiguracja interfejsu LoRa: tryb powrotu STDBY_XOSC, DIO1 tylko dla końca ramki, parametry CAD.
    printf("FALLBACK %02X\n", chip.fallback);
    printf("DIOIRQ %02X%02X %02X%02X %02X%02X %02X%02X\n", chip.dioIrq[0], chip.dioIrq[1], chip.dioIrq[2], chip.dioIrq[3],
           chip.dioIrq[4], chip.dioIrq[5], chip.dioIrq[6], chip.dioIrq[7]);
    printf("CADPARAMS %02X %u %u %02X %d\n", chip.cadParams[0], chip.cadParams[1], chip.cadParams[2], chip.cadParams[3],
           link.ccaThresholdDbm());

    // Nadanie w krokach z odbioru: prepareTx (STDBY_XOSC, ramka), CAD (potem STDBY_RC), SetTx, po TxDone STDBY_XOSC.
    link.startRx(true, 0);
    chip.ops.clear();
    const radiolink::TxPrep prep = link.prepareTx(frame, 30);
    const char* prepMode = link.stateName();
    const bool prepRxen = chip.rxen;
    const radiolink::Cad cadFree = link.cad();
    const char* cadMode = link.stateName();
    const unsigned txBeforeCad = chip.txCount;
    radiolink::TxTiming cadTiming;
    const bool cadSent = link.sendPrepared(&cadTiming);
    printf("CADTX %d %s %d %d %s %d %zu %02X %s %u\n", static_cast<int>(prep), prepMode, prepRxen, static_cast<int>(cadFree), cadMode,
           cadSent, chip.lastTx.size(), chip.lastTx.front(), link.stateName(), chip.txCount - txBeforeCad);
    // Kolejność: SetStandby, parametry pakietu, bufor, SetCad, SetTx; bez SetStandby między CAD a SetTx.
    printf("CADORDER %d %d %d %d %d %d\n", indexOf(sx1262::OP_SET_STANDBY), indexOf(sx1262::OP_SET_PACKET_PARAMS),
           indexOf(sx1262::OP_WRITE_BUFFER), indexOf(sx1262::OP_SET_CAD), indexOf(sx1262::OP_SET_TX),
           static_cast<int>(std::count(chip.ops.begin(), chip.ops.end(), sx1262::OP_SET_STANDBY)));
    // Druga ramka datagramu ze stanu spoczynku, bez CAD; potem odbiór.
    const radiolink::TxPrep prep2 = link.prepareTx(frame + 1, 20);
    const bool sent2 = link.sendPrepared(nullptr);
    printf("SECOND %d %d %zu %02X %s\n", static_cast<int>(prep2), sent2, chip.lastTx.size(), chip.lastTx.front(), link.stateName());
    // CAD zajęty, CAD bez końca, CAD w odbiorze.
    chip.cadBusy = true;
    link.prepareTx(frame, 30);
    const radiolink::Cad cadBusy = link.cad();
    chip.cadBusy = false;
    chip.cadHang = true;
    const uint32_t cadT0 = millis();
    const radiolink::Cad cadHung = link.cad();
    const uint32_t cadHangMs = millis() - cadT0;
    const char* hungMode = link.stateName();
    chip.cadHang = false;
    link.startRx(true, 0);
    const radiolink::Cad cadInRx = link.cad();
    printf("CADBUSY %d %d %s %d %d %u %04X\n", static_cast<int>(cadBusy), static_cast<int>(cadHung), hungMode, cadHangMs >= 20,
           static_cast<int>(cadInRx), chip.cadCount, chip.irq);

    // Przed wyjściem z odbioru: nieodczytana ramka albo ramka w toku odracza nadanie, bez kasowania flag
    // i bez zapisu bufora.
    link.startRx(true, 0);
    airFrame(40, 0x60);
    chip.ops.clear();
    const radiolink::TxPrep pendingDone = link.prepareTx(frame, 30);
    printf("PENDING %d %s %d %04X %02X %d\n", static_cast<int>(pendingDone), link.stateName(), chip.rxen, chip.irq,
           chip.buffer[0], indexOf(sx1262::OP_WRITE_BUFFER));
    radiolink::Frame rxf;
    const sx1262::RxService pendingFrame = link.serviceRx(rxf, false);
    airHeader(0x70, 0);
    const radiolink::TxPrep pendingStart = link.prepareTx(frame, 30);
    printf("PENDINGRX %d %d %d %d\n", static_cast<int>(pendingFrame), bytesFrom(rxf, 0x60), static_cast<int>(pendingStart),
           chip.irq == (sx1262::IRQ_PREAMBLE_DETECTED | sx1262::IRQ_HEADER_VALID));

    // Odbiór ciągły: próbka kasuje widziane flagi początku ramki i zapisuje znaczniki aktywności; ramka
    // 255 B od 0, następna od 255 z zawinięciem bufora (nadpisuje pierwszą).
    link.startRx(true, 0);
    link.clearActivity();
    const bool quietBefore = link.activity().quietFor(millis(), 50);
    airHeader(0x00, 10);
    const sx1262::RxService sample = link.serviceRx(rxf, false);
    printf("SAMPLE %d %04X %d %d\n", static_cast<int>(sample), chip.irq, quietBefore, link.activity().quietFor(millis(), 50));
    airEnd(255, 0x00);
    const sx1262::RxService first = link.serviceRx(rxf, false);
    printf("RING1 %d %zu %d %u\n", static_cast<int>(first), rxf.length, bytesFrom(rxf, 0x00), chip.rxStart);
    airFrame(255, 0x80);
    const sx1262::RxService second = link.serviceRx(rxf, false);
    printf("RING2 %d %zu %d %u %u %02X %lu\n", static_cast<int>(second), rxf.length, bytesFrom(rxf, 0x80), chip.rxStart, chip.rxPtr,
           chip.buffer[0], static_cast<unsigned long>(link.rxLate()));

    // Krótka ramka: nagłówek i koniec tej samej ramki w jednej próbce (przerwa ≤ 25 ms) to ramka dobra.
    airHeader(0x40, 0);
    airEnd(5, 0x40);
    const sx1262::RxService shortFrame = link.serviceRx(rxf, false);
    printf("SHORTFRAME %d %zu %d %lu %04X\n", static_cast<int>(shortFrame), rxf.length, bytesFrom(rxf, 0x40),
           static_cast<unsigned long>(link.rxLate()), chip.irq);
    // Przerwa w próbkach ponad 25 ms z nagłówkiem przy RxDone: nie wiadomo, czyj, więc rx_late.
    link.serviceRx(rxf, false);
    fakeUs += 30000;
    airHeader(0x50, 0);
    airEnd(60, 0x50);
    airHeader(0x58, 8);  // następna ramka; flaga HeaderValid ta sama
    const sx1262::RxService gapLate = link.serviceRx(rxf, false);
    printf("GAPLATE %d %zu %lu %04X\n", static_cast<int>(gapLate), rxf.length, static_cast<unsigned long>(link.rxLate()), chip.irq);
    airEnd(40, 0x58);
    const sx1262::RxService afterGap = link.serviceRx(rxf, false);  // nagłówek tej ramki skasowany przy GAPLATE
    printf("AFTERGAP %d %d\n", static_cast<int>(afterGap), bytesFrom(rxf, 0x58));

    // Spóźnienie: nagłówek ramki widziany wcześniej, a przy RxDone już nagłówek następnej (przed odczytem),
    // albo nagłówek w trakcie odczytu bufora (po odczycie). Ramka odrzucona i policzona, flagi widziane skasowane.
    airHeader(0x20, 0);
    link.serviceRx(rxf, false);
    airEnd(200, 0x20);
    airHeader(0x90, 20);
    const sx1262::RxService lateBefore = link.serviceRx(rxf, false);
    printf("LATE1 %d %zu %lu %04X\n", static_cast<int>(lateBefore), rxf.length, static_cast<unsigned long>(link.rxLate()), chip.irq);
    airEnd(100, 0x90);
    chip.hookOp = sx1262::OP_READ_BUFFER;
    chip.hook = [] { airHeader(0xB0, 4); };
    const sx1262::RxService lateAfter = link.serviceRx(rxf, false);
    printf("LATE2 %d %zu %lu %04X\n", static_cast<int>(lateAfter), rxf.length, static_cast<unsigned long>(link.rxLate()), chip.irq);
    // Flaga ustawiona między odczytem przerwań a kasowaniem zostaje (kasowane tylko widziane).
    airEnd(30, 0xB0);
    chip.hookOp = sx1262::OP_CLEAR_IRQ_STATUS;
    chip.hook = [] { chip.irq |= sx1262::IRQ_CRC_ERR; };
    const sx1262::RxService kept = link.serviceRx(rxf, false);
    printf("ONLYSEEN %d %d %04X\n", static_cast<int>(kept), bytesFrom(rxf, 0xB0), chip.irq);
    const sx1262::RxService keptBad = link.serviceRx(rxf, false);
    printf("ONLYSEENBAD %d %04X\n", static_cast<int>(keptBad), chip.irq);

    // RSSI ponad progiem jako aktywność; okno 50 ms bez aktywności; kasowanie znaczników.
    link.clearActivity();
    chip.rssiInst = 180;  // -90 dBm > -100 dBm
    link.serviceRx(rxf, true);
    const bool rssiBusy = !link.activity().quietFor(millis(), 50);
    fakeUs += 60000;
    const bool rssiAged = link.activity().quietFor(millis(), 50);
    chip.rssiInst = 220;  // -110 dBm
    link.clearActivity();
    link.serviceRx(rxf, true);
    printf("RSSIMARK %d %d %d\n", rssiBusy, rssiAged, link.activity().quietFor(millis(), 50));
    link.idle();
    const sx1262::RxService notRx = link.serviceRx(rxf, false);
    printf("NOTRX %d\n", static_cast<int>(notRx));

    // Wyjęty moduł (BUSY wysoki) przy trzymanej blokadzie radia: próbka przerwana po pierwszym przekroczeniu
    // czasu BUSY, bez ramki; blokada zostaje u wywołującego; po powrocie BUSY ramka czeka w układzie.
    link.startRx(true, 0);
    airFrame(12, 0x30);
    {
        platform::RadioLock lock(500);
        chip.busyStuck = true;
        const unsigned long timeoutsBefore = radio.busyTimeouts();
        const uint32_t t0 = millis();
        rxf.length = 99;
        const sx1262::RxService stuck = link.serviceRx(rxf, true);
        const uint32_t stuckMs = millis() - t0;
        printf("STUCKRX %d %zu %lu %d %d %d %04X\n", static_cast<int>(stuck), rxf.length, radio.busyTimeouts() - timeoutsBefore,
               stuckMs >= 20 && stuckMs < 25, lock.held(), lockDepth, chip.irq);
        chip.busyStuck = false;
    }
    const sx1262::RxService recovered = link.serviceRx(rxf, false);
    printf("STUCKAFTER %d %d %d\n", lockDepth, static_cast<int>(recovered), bytesFrom(rxf, 0x30));
    link.idle();

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


LORA_BENCH_HARNESS = r"""
#include <deque>
#include <string>
#include <vector>
#include "loraframe.h"
#include "lora_profile.h"
#include "measure.h"
#include "platform.h"

uint32_t fakeUs = 0;
FakeSerial Serial;
int digitalRead(uint8_t) { return HIGH; }
void digitalWrite(uint8_t, uint8_t) {}
void measure::randomBytes(uint8_t* out, size_t count) {
    static uint8_t next = 0x31;
    for (size_t i = 0; i < count; ++i) out[i] = next += 0x37;
}

// Blokada operacji radia: pętla bierze ją zawsze (rekurencyjnie), zadanie odbioru tylko próbuje (limit 0)
// i przy blokadzie trzymanej przez pętlę pomija obieg, jak zadanie na ESP32-S3.
int loopDepth = 0;
bool inTask = false;
int taskSkipped = 0, taskServiced = 0;
bool platform::radioLockTake(uint32_t) {
    if (!inTask) { ++loopDepth; return true; }
    return loopDepth == 0;
}
void platform::radioLockGive() {
    if (!inTask) --loopDepth;
}
void rxTaskCycle() {
    inTask = true;
    {
        platform::RadioLock lock(0);
        if (lock.held()) ++taskServiced;
        else ++taskSkipped;
    }
    inTask = false;
}

struct RamStorage : journal::Storage {
    std::vector<uint8_t> bytes = std::vector<uint8_t>(512 * 1024, 0xFF);
    bool fail = false;  // zapis do FRAM nie przechodzi
    bool read(uint32_t address, uint8_t* data, size_t count) override {
        memcpy(data, &bytes[address], count);
        return true;
    }
    bool write(uint32_t address, const uint8_t* data, size_t count) override {
        if (fail) return false;
        memcpy(&bytes[address], data, count);
        return true;
    }
};
RamStorage ram;
journal::Journal dj(ram);

// Sterownik zastępczy LoRa: kroki nadawania z L4 zapisane w ops razem z długiem w dzienniku w tej chwili,
// znaczniki aktywności z czasem, zajęty CAD przez cadBusy sprawdzeń, RSSI ponad progiem przez rssiBusy odczytów.
struct FakeLora : radiolink::Driver {
    std::vector<std::string> ops;
    std::vector<std::vector<uint8_t>> sent;
    std::deque<radiolink::Frame> rxQueue;
    std::vector<uint8_t> loaded;
    bool rxActive = false, rxVariable = false, rxPending = false, failDebtAtCad = false, cw = false;
    int cadBusy = 0, rssiBusy = 0, taskCyclesPerFrame = 0;
    radiolink::Activity mark = radiolink::Activity::None;
    uint32_t markMs = 0;
    void op(const char* name) { ops.push_back(std::string(name) + ":" + std::to_string(dj.debt().a)); }
    const char* stateName() override { return cw ? "TX" : rxActive ? "RX" : "STBY_XOSC"; }
    void idle() override { rxActive = false; cw = false; }
    bool startCw() override { cw = true; return true; }
    void stopCw() override { cw = false; }
    bool send(const uint8_t* frame, size_t length) {
        sent.emplace_back(frame, frame + length);
        for (int i = 0; i < taskCyclesPerFrame; ++i) { rxTaskCycle(); fakeUs += 100000; }  // ramka 255 B to 419 ms
        return true;
    }
    bool transmit(const uint8_t* frame, size_t length, bool, radiolink::TxTiming*) override {
        op("tx");
        rxActive = false;
        return send(frame, length);
    }
    bool startRx(bool variable, uint8_t) override {
        ops.push_back("rx");
        rxActive = true;
        rxVariable = variable;
        return true;
    }
    radiolink::RxPoll pollRx(radiolink::Frame& out) override {
        if (rxQueue.empty()) return radiolink::RxPoll::Nothing;
        out = rxQueue.front();
        rxQueue.pop_front();
        return radiolink::RxPoll::Frame;
    }
    bool receivingFrame() override { return false; }
    radiolink::Rssi rssi() override {
        radiolink::Rssi r;
        r.valid = rxActive;
        r.dbm = rssiBusy > 0 && rssiBusy-- ? -90 : -120;
        return r;
    }
    bool setFrequencyOffset(int32_t) override { return true; }
    void reapplyFrequencyOffset() override {}
    int32_t frequencyOffsetHz() override { return 0; }
    int32_t frequencyOffsetRaw() override { return 0; }
    double frequencyStepHz() const override { return 1.0; }
    bool frequencyErrorHz(int32_t&) override { return false; }
    uint32_t frameAirMs(size_t length) const override { return lora::frameAirMs(length); }
    double onAirMs(size_t length) const override { return lora::frameAirUs(length) / 1000.0; }
    size_t maxTestLength() const override { return lora::MAX_PAYLOAD; }
    uint32_t seriesMaxMs() const override { return lora::SERIES_MAX_MS; }
    radiolink::Framing framing() const override { return radiolink::Framing::RNODE; }
    bool hasSnr() const override { return true; }
    int8_t ccaThresholdDbm() const override { return lora::CCA_RSSI_THRESHOLD_DBM; }
    radiolink::TxPrep prepareTx(const uint8_t* frame, size_t length) override {
        op("prep");
        if (rxPending) { rxPending = false; return radiolink::TxPrep::RxPending; }  // układ zostaje w odbiorze
        rxActive = false;
        loaded.assign(frame, frame + length);
        return radiolink::TxPrep::Ready;
    }
    radiolink::Cad cad() override {
        op("cad");
        if (failDebtAtCad) ram.fail = true;
        return cadBusy > 0 && cadBusy-- ? radiolink::Cad::Busy : radiolink::Cad::Free;
    }
    bool sendPrepared(radiolink::TxTiming*) override {
        op("send");
        return send(loaded.data(), loaded.size());
    }
    radiolink::Activity recentActivity(uint32_t windowMs) override {
        ops.push_back("window");
        return mark != radiolink::Activity::None && millis() - markMs < windowMs ? mark : radiolink::Activity::None;
    }
    void clearActivity() override { mark = radiolink::Activity::None; }
    uint32_t rxLate() const override { return 2; }
};

FakeLora radio;
measure::Bench bench(radio, 3, -1);
std::vector<uint8_t> received;
int txDone = -1;
uint32_t uptime() { return millis() / 1000; }

void runFor(uint32_t ms) {
    const uint32_t end = millis() + ms;
    while (millis() < end) {
        fakeUs += 1000;
        bench.poll();
    }
}
// Do końca nadania (txDone) albo limitu; potem odczekanie długu, żeby następny przypadek startował bez niego.
void untilDone(uint32_t limitMs) {
    const uint32_t end = millis() + limitMs;
    while (txDone < 0 && millis() < end) {
        fakeUs += 1000;
        bench.poll();
    }
}
void settle() { runFor(bench.debtRemainingMs() + 100); }
std::string ops() {
    std::string out;
    for (const auto& o : radio.ops) out += (out.empty() ? "" : " ") + o;
    radio.ops.clear();
    return out;
}
std::vector<uint8_t> datagram(size_t length, uint8_t seed) {
    std::vector<uint8_t> d(length);
    for (size_t i = 0; i < length; ++i) d[i] = static_cast<uint8_t>(seed + i * 13);
    return d;
}
const char* text(const char* error) { return error ? error : "-"; }

int main() {
    dj.begin();
    bench.attach(&dj, uptime);
    bench.onDatagram([](const uint8_t* data, size_t length, void*) { received.assign(data, data + length); }, nullptr);
    bench.onTxDone([](bool ok, void*) { txDone = ok; }, nullptr);
    fakeUs = 1000000;

    // Start bez poprawnego rekordu długu: 12 x seria LoRa (2 x 419 ms), nie stała P1 16,8 s.
    bench.restoreDebt(bench.maxDebtMs());
    printf("MAXDEBT %lu %lu %lu\n", static_cast<unsigned long>(bench.maxDebtMs()), static_cast<unsigned long>(bench.debtRemainingMs()),
           static_cast<unsigned long>(measure::MAX_DEBT_MS));
    printf("FRAMING %d\n", bench.linkFraming() == radiolink::Framing::RNODE);   // BenchRadio::timing(): czas LoRa
    // Odbiór stosu startuje sam poza trybem przygotowania, gdy układ ma profil.
    bench.p1Ready = true;
    runFor(1100);
    printf("AUTORX %d %d %d\n", bench.receiving(), radio.rxActive, radio.rxVariable);
    const uint8_t one[1] = {0};
    const char* p1send = bench.p1send(one, 1, true);
    printf("NOP1 %s|%s\n", p1send, bench.p1rxStart());
    const std::vector<uint8_t> big = datagram(509, 1);
    printf("TOOBIG %s\n", text(bench.linkSend(big.data(), big.size(), true)));
    settle();

    // Nadanie 508 B: dług odczekany, okno bez aktywności, ramka 1 przed CAD, zapis długu po wolnym CAD,
    // ramka 1, ramka 2, odbiór. W trakcie ramek zadanie odbioru próbuje blokady bez czekania i pomija obiegi.
    const std::vector<uint8_t> d508 = datagram(508, 7);
    radio.ops.clear();
    radio.taskCyclesPerFrame = 3;
    const char* error = bench.linkSend(d508.data(), d508.size(), true);
    untilDone(100);
    radio.taskCyclesPerFrame = 0;
    printf("ORDER %s|%s\n", text(error), ops().c_str());
    rxTaskCycle();  // po nadaniu blokada wolna
    printf("TRYLOCK %d %d %d %d\n", taskSkipped, taskServiced, txDone, loopDepth);
    loraframe::Assembler check;
    size_t assembled = 0;
    for (const auto& f : radio.sent)
        if (check.push(f.data(), f.size(), millis()) == loraframe::Outcome::COMPLETE) assembled = check.length();
    printf("FRAMES %zu %zu %zu %02X %d %d\n", radio.sent.size(), radio.sent[0].size(), radio.sent[1].size(),
           radio.sent[0][0] & 0x0F, radio.sent[0][0] == radio.sent[1][0], assembled == 508 && !memcmp(check.datagram(), d508.data(), 508));

    // Restart w trakcie długu: odczekany cały dług z dziennika, potem nadanie.
    const uint32_t journalDebt = dj.debt().a;
    bench.restoreDebt(journalDebt);
    txDone = -1;
    radio.sent.clear();
    const std::vector<uint8_t> d20 = datagram(20, 3);
    bench.linkSend(d20.data(), d20.size(), true);
    runFor(journalDebt - 100);
    const size_t sentDuringDebt = radio.sent.size();
    untilDone(1000);
    printf("RESTART %lu %zu %zu %d\n", static_cast<unsigned long>(journalDebt), sentDuringDebt, radio.sent.size(), txDone);
    settle();

    // Zajęty CAD: odroczenie bez zapisu długu, powrót do odbioru, potem nadanie.
    txDone = -1;
    radio.ops.clear();
    radio.cadBusy = 1;
    bench.linkSend(d20.data(), d20.size(), true);
    untilDone(3000);
    printf("CADBUSY %s|%lu %lu %d\n", ops().c_str(), static_cast<unsigned long>(bench.link().cadBusy),
           static_cast<unsigned long>(bench.link().deferrals), txDone);
    settle();

    // Aktywność w oknie (ramka 20 ms temu) i RSSI ponad progiem przy decyzji: dwa odroczenia, bez CAD.
    txDone = -1;
    radio.ops.clear();
    radio.mark = radiolink::Activity::Rx;
    radio.markMs = millis() - 20;
    radio.rssiBusy = 1;
    const uint32_t deferralsBefore = bench.link().deferrals;
    bench.linkSend(d20.data(), d20.size(), true);
    bench.poll();
    radio.mark = radiolink::Activity::None;
    untilDone(3000);
    const std::string activityOps = ops();
    printf("ACTIVITY %lu %lu %lu %d|%s\n", static_cast<unsigned long>(bench.link().rxBusy), static_cast<unsigned long>(bench.link().rssiBusy),
           static_cast<unsigned long>(bench.link().deferrals - deferralsBefore), txDone, activityOps.c_str());
    settle();

    // Nieodczytana ramka w układzie przy wyjściu z odbioru: odroczenie (rx_busy), układ zostaje w odbiorze.
    txDone = -1;
    radio.rxPending = true;
    bench.linkSend(d20.data(), d20.size(), true);
    bench.poll();
    const int pendingRx = radio.rxActive;
    untilDone(3000);
    printf("RXPENDING %lu %d %d\n", static_cast<unsigned long>(bench.link().rxBusy), pendingRx, txDone);
    settle();

    // Postój pętli 150 ms w czasie okna: decyzja ze znaczników, więc nadanie zaraz po postoju, bez nowego okna.
    bench.stop();
    bench.linkRxStart();
    txDone = -1;
    bench.linkSend(d20.data(), d20.size(), true);
    fakeUs += 1000;
    bench.poll();  // okno krótsze niż 50 ms od startu odbioru: czeka
    const int waited = txDone;
    fakeUs += 150000;
    bench.poll();
    printf("STALL %d %d\n", waited, txDone);
    settle();
    // Ten sam postój z ramką 30 ms przed jego końcem: odroczenie.
    bench.stop();
    bench.linkRxStart();
    txDone = -1;
    const uint32_t stallDeferrals = bench.link().deferrals;
    bench.linkSend(d20.data(), d20.size(), true);
    fakeUs += 1000;
    bench.poll();
    radio.mark = radiolink::Activity::Rx;
    radio.markMs = millis() + 120;
    fakeUs += 150000;
    bench.poll();
    printf("STALLBUSY %d %lu\n", txDone, static_cast<unsigned long>(bench.link().deferrals - stallDeferrals));
    radio.mark = radiolink::Activity::None;
    untilDone(3000);
    settle();

    // 30 odroczeń, a przy 31. zajętym CAD odrzut; dług nie zapisany.
    txDone = -1;
    radio.cadBusy = 1000;
    const measure::LinkCounters before = bench.link();
    bench.linkSend(d20.data(), d20.size(), true);
    untilDone(60000);
    radio.cadBusy = 0;
    printf("DEFER30 %d %lu %lu %lu %lu\n", txDone, static_cast<unsigned long>(bench.link().deferrals - before.deferrals),
           static_cast<unsigned long>(bench.link().cadBusy - before.cadBusy), static_cast<unsigned long>(bench.link().txDrop - before.txDrop),
           static_cast<unsigned long>(dj.debt().a));

    // Błąd zapisu długu po wolnym CAD: bez nadania, odbiór wraca.
    txDone = -1;
    radio.sent.clear();
    radio.ops.clear();
    radio.failDebtAtCad = true;
    bench.linkSend(d20.data(), d20.size(), true);
    untilDone(1000);
    radio.failDebtAtCad = false;
    ram.fail = false;
    printf("DEBTFAIL %d %zu %d %s\n", txDone, radio.sent.size(), radio.rxActive, ops().c_str());

    // Cisza: datagram czekający na dług odpada; wyjątek ciszy przepuszcza datagram od stosu, pomiar z portu nie.
    bench.restoreDebt(500);
    txDone = -1;
    bench.linkSend(d20.data(), d20.size(), true);
    bench.silence = true;
    runFor(10);
    const int silenced = txDone;
    bench.silenceException = true;
    settle();
    txDone = -1;
    bench.prep = true;
    const char* fromPort = bench.linkSend(d20.data(), d20.size(), false);
    error = bench.linkSend(d20.data(), d20.size(), true);
    untilDone(1000);
    printf("SILENCE %d %s|%s %d\n", silenced, fromPort, text(error), txDone);
    bench.silence = bench.silenceException = bench.prep = false;
    settle();

    // Odbiór: 508 B jako dwie ramki RNode z trzecią ramką z samym nagłówkiem; pętla obsługuje je 1,5 s po
    // odbiorze, a limit 1 s liczy się z czasów odbioru ramek. Potem pierwsza część bez drugiej (po 1 s
    // przepada) i pierwsza część przerwana ramką bez podziału.
    loraframe::Splitter splitter;
    loraframe::Frame parts[2];
    splitter.split(d508.data(), d508.size(), 0xA0, parts);
    const uint32_t t0 = millis();
    for (int i = 0; i < 3; ++i) {
        radiolink::Frame f;
        f.length = i < 2 ? parts[i].length : 1;
        memcpy(f.bytes, parts[i < 2 ? i : 0].bytes, f.length);
        f.receivedMs = t0 + 500 * static_cast<uint32_t>(i);
        f.rssiDbm = -95;
        radio.rxQueue.push_back(f);
    }
    fakeUs += 1500000;
    runFor(10);
    printf("RX508 %zu %d\n", received.size(), received.size() == 508 && !memcmp(received.data(), d508.data(), 508));
    radio.rxQueue.push_back([&] { radiolink::Frame f; f.length = parts[0].length; memcpy(f.bytes, parts[0].bytes, f.length); f.receivedMs = millis(); return f; }());
    runFor(1100);
    radio.rxQueue.push_back([&] { radiolink::Frame f; f.length = parts[0].length; memcpy(f.bytes, parts[0].bytes, f.length); f.receivedMs = millis(); return f; }());
    radio.rxQueue.push_back([&] { radiolink::Frame f; f.length = 21; f.bytes[0] = 0x50; memcpy(f.bytes + 1, d20.data(), 20); f.receivedMs = millis(); return f; }());
    runFor(10);
    printf("RXSHORT %zu\n", received.size());
    bench.printLink();

    // Rekonfiguracja (radiocon: bench.stop() przed CONFIG): odbiór wraca od razu przez linkRxStart, także
    // w trybie przygotowania, w którym sam nie wraca.
    bench.prep = true;
    bench.stop();
    runFor(1500);
    const int stopped = radio.rxActive;
    error = bench.linkRxStart();
    printf("REARM %d %s %d %d\n", stopped, text(error), radio.rxActive, bench.receiving());

    // Tryb EMC wstrzymuje łącze stosu: odbiór ramek wzorcowych, datagramy odmówione; po EMC 0 odbiór łącza wraca.
    const char* emc = bench.emcStart(6, 20);
    const char* emcSend = bench.linkSend(d20.data(), d20.size(), true);
    const char* emcRx = bench.linkRxStart();
    runFor(100);
    printf("EMC %s|%s|%s %d %d\n", text(emc), emcSend, emcRx, radio.rxActive, radio.rxVariable);
    bench.emcStop();
    bench.prep = false;
    runFor(1100);
    printf("EMCOFF %d %d %d\n", bench.emcActive(), radio.rxActive, radio.rxVariable);
    return 0;
}
"""


def host_compiler():
    for name in ("c++", "g++", "clang++"):
        if shutil.which(name):
            return shutil.which(name)
    return None


def build_and_run(harness, sources, flags=()):
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        for name, text in STUBS.items():
            (root / name).write_text(text, encoding="utf-8")
        (root / "harness.cpp").write_text(harness, encoding="utf-8")
        subprocess.run([host_compiler(), "-std=c++17", "-Wall", "-Wextra", "-Werror", *flags, f"-I{root}", f"-I{SRC}",
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

    def test_p1_driver_has_no_cad_and_the_p1_cca_threshold(self):
        # Cad::Unsupported (3), TxPrep::Unsupported (3), no prepared send, P1 threshold -100 dBm.
        self.assertEqual(line(self.out, "P1DEFAULTS"), "P1DEFAULTS 3 3 0 -100")


@unittest.skipUnless(host_compiler(), "no host C++ compiler")
class BenchTests(unittest.TestCase):
    """measure.cpp over radiolink::Driver: the same measurement and P1 link logic on both radios."""

    @classmethod
    def setUpClass(cls):
        cls.out = build_and_run(BENCH_HARNESS, ["measure.cpp", "loraframe.cpp", "p1frame.cpp", "testframe.cpp", "journal.cpp"])

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
        cls.out = build_and_run(SX1262_HARNESS, ["sx1262.cpp", "sx1262_link.cpp", "measure.cpp", "loraframe.cpp", "p1frame.cpp", "testframe.cpp",
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
        self.assertEqual(line(self.out, "CWSTOP"), "CWSTOP STBY_XOSC")

    def test_transmit_frame_and_timeout(self):
        # After TxDone the chip falls back to STDBY_XOSC by itself (fallback mode 0x30), TCXO stays on.
        self.assertEqual(line(self.out, "TX"), "TX 1 20 20 A0 B3 0 STBY_XOSC 0 1")
        self.assertEqual(line(self.out, "TXLEN"), "TXLEN 0 0")
        self.assertEqual(line(self.out, "TXSTUCK"), "TXSTUCK 0 STBY_XOSC 1 1")

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
        self.assertEqual(line(self.out, "BUSY"), "BUSY 0 2")  # the second timeout; the first one is in STUCKRX

    def test_lora_interface_configuration(self):
        self.assertEqual(line(self.out, "FALLBACK"), "FALLBACK 30")  # STDBY_XOSC after TX (datasheet table 13-23)
        # IRQ mask: TxDone, RxDone, PreambleDetected, HeaderValid, HeaderErr, CrcErr, CadDone, CadDetected,
        # Timeout (0x03F7); DIO1 only RxDone, HeaderErr and CrcErr (0x0062); DIO2 and DIO3 none.
        self.assertEqual(line(self.out, "DIOIRQ"), "DIOIRQ 03F7 0062 0000 0000")
        # CAD on 2 symbols, cadDetPeak 22, cadDetMin 10, CAD_ONLY; CCA threshold -100 dBm.
        self.assertEqual(line(self.out, "CADPARAMS"), "CADPARAMS 01 22 10 00 -100")

    def test_transmit_in_steps_with_free_cad(self):
        # prepareTx Ready in STDBY_XOSC with RXEN low; CAD Free leaves STDBY_RC (CAD_ONLY, table 13-73);
        # the loaded 30 B frame is sent and the chip falls back to STDBY_XOSC.
        self.assertEqual(line(self.out, "CADTX"), "CADTX 0 STBY_XOSC 0 0 STBY_RC 1 30 A0 STBY_XOSC 1")
        standby, params, write, cad, tx, standbys = (int(v) for v in line(self.out, "CADORDER").split()[1:])
        self.assertTrue(standby < params < write < cad < tx)  # frame loaded before CAD, SetTx right after it
        self.assertEqual(standbys, 1)
        self.assertEqual(line(self.out, "SECOND"), "SECOND 0 1 20 A1 STBY_XOSC")

    def test_cad_busy_hung_and_from_receive(self):
        # Busy (1); no CadDone within the limit: Error (2) and STDBY_XOSC; CAD from RX refused (2);
        # two CADs finished; CAD flags cleared.
        self.assertEqual(line(self.out, "CADBUSY"), "CADBUSY 1 2 STBY_XOSC 1 2 2 0000")

    def test_pending_reception_defers_transmit_without_clearing(self):
        # Unread RxDone: RxPending (1), still in RX, flag kept, buffer not written; the frame is then received.
        self.assertEqual(line(self.out, "PENDING"), "PENDING 1 RX 1 0002 60 -1")
        # A frame starting (preamble and header) defers too, flags kept.
        self.assertEqual(line(self.out, "PENDINGRX"), "PENDINGRX 1 1 1 1")

    def test_sample_clears_seen_start_flags_and_marks_activity(self):
        self.assertEqual(line(self.out, "SAMPLE"), "SAMPLE 0 0000 1 0")
        self.assertEqual(line(self.out, "RSSIMARK"), "RSSIMARK 1 1 1")  # -90 dBm busy, aged after 60 ms, -110 dBm quiet
        self.assertEqual(line(self.out, "NOTRX"), "NOTRX 4")

    def test_continuous_receive_buffer_continues_and_wraps(self):
        self.assertEqual(line(self.out, "RING1"), "RING1 1 255 1 0")
        # The second 255 B frame starts at 255 and wraps: it overwrites the first from address 0.
        self.assertEqual(line(self.out, "RING2"), "RING2 1 255 1 255 254 81 0")

    def test_short_frame_with_header_and_end_in_one_sample_is_accepted(self):
        self.assertEqual(line(self.out, "SHORTFRAME"), "SHORTFRAME 1 5 1 0 0000")

    def test_header_at_end_after_a_sampling_gap_is_late(self):
        # Over 25 ms since the previous sample: the header cannot be attributed, the frame goes to rx_late;
        # the next frame (whose header that was) is then received normally.
        self.assertEqual(line(self.out, "GAPLATE"), "GAPLATE 3 0 1 0000")
        self.assertEqual(line(self.out, "AFTERGAP"), "AFTERGAP 1 1")

    def test_late_frame_dropped_and_counted(self):
        # Header seen earlier and a new HeaderValid with RxDone (before the read); HeaderValid during the
        # buffer read (after it).
        self.assertEqual(line(self.out, "LATE1"), "LATE1 3 0 2 0000")
        self.assertEqual(line(self.out, "LATE2"), "LATE2 3 0 3 0000")

    def test_only_seen_flags_are_cleared(self):
        # CrcErr set between GetIrqStatus and ClearIrqStatus survives and is reported by the next sample.
        self.assertEqual(line(self.out, "ONLYSEEN"), "ONLYSEEN 1 1 0040")
        self.assertEqual(line(self.out, "ONLYSEENBAD"), "ONLYSEENBAD 2 0000")

    def test_removed_module_aborts_service_with_lock_held(self):
        # BUSY stuck high: BusyTimeout (5) after the first timeout (~20 ms), no frame, lock still held by the
        # caller, RxDone kept; after BUSY returns the lock is released and the frame is received.
        self.assertEqual(line(self.out, "STUCKRX"), "STUCKRX 5 0 1 1 1 1 0002")
        self.assertEqual(line(self.out, "STUCKAFTER"), "STUCKAFTER 0 1 1")

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


@unittest.skipUnless(host_compiler(), "no host C++ compiler")
class LoraBenchTests(unittest.TestCase):
    """measure.cpp with the RNode framing (plan L5) over a fake LoRa driver: the TX sequence of the
    stack link (debt, 50 ms window from activity marks, frame 1 loaded before CAD, debt written after a
    free CAD, two frames, receive), deferrals, silence, assembly from frame receive times, re-arm and EMC.
    Built with WICI_NO_P1_LINK like the l0 images (no P1 assembly)."""

    @classmethod
    def setUpClass(cls):
        cls.out = build_and_run(LORA_BENCH_HARNESS, ["measure.cpp", "loraframe.cpp", "p1frame.cpp", "testframe.cpp", "journal.cpp"],
                                flags=["-DWICI_NO_P1_LINK"])

    def test_start_without_a_debt_record_waits_the_lora_maximum(self):
        # 12 x 838 ms (two 255 B frames with ramp-up), not the P1 bound of 16.8 s.
        self.assertEqual(line(self.out, "MAXDEBT"), "MAXDEBT 10056 10056 16800")
        self.assertEqual(line(self.out, "FRAMING"), "FRAMING 1")   # stacja z LoRa bierze czas łącza z loraTiming()

    def test_stack_receive_starts_by_itself_and_p1_commands_stay_refused(self):
        self.assertEqual(line(self.out, "AUTORX"), "AUTORX 1 1 1")
        self.assertEqual(line(self.out, "NOP1"), "NOP1 no P1 link on this radio|no P1 link on this radio")
        self.assertEqual(line(self.out, "TOOBIG"), "TOOBIG datagram 1..508 B")

    def test_transmit_order_debt_window_cad_debt_write_frames_receive(self):
        # The debt in the journal at each step: 0 up to the free CAD, 12 x (419 + 419) ms from frame 1 on.
        self.assertEqual(line(self.out, "ORDER"), "ORDER -|window prep:0 cad:0 send:10056 tx:10056 rx")
        # Two 255 B frames with the same split header; they reassemble to the datagram.
        self.assertEqual(line(self.out, "FRAMES"), "FRAMES 2 255 255 01 1 1")

    def test_508_b_while_the_receive_task_tries_the_lock(self):
        # Six task cycles during the two frames skip (lock held by the loop), none waits or fails; after
        # the transmit the task gets the lock; the datagram went out and the loop released the lock.
        self.assertEqual(line(self.out, "TRYLOCK"), "TRYLOCK 6 1 1 0")

    def test_restart_with_debt_waits_the_journal_debt(self):
        self.assertEqual(line(self.out, "RESTART"), "RESTART 10056 0 1 1")

    def test_busy_cad_defers_without_writing_debt(self):
        ops, counts = line(self.out, "CADBUSY")[len("CADBUSY "):].split("|")
        self.assertEqual(ops.split()[:5], ["window", "prep:0", "cad:0", "rx", "window"])
        self.assertEqual(ops.split()[5:], ["prep:0", "cad:0", "send:912", "rx"])  # 12 x 76 ms (21 B frame: 73 ms + 3 ms ramp)
        self.assertEqual(counts, "1 1 1")  # cad_busy, deferrals, sent

    def test_activity_in_the_window_and_rssi_defer_before_cad(self):
        counts, ops = line(self.out, "ACTIVITY")[len("ACTIVITY "):].split("|")
        self.assertEqual(counts, "1 1 2 1")  # rx_busy, rssi_busy, two deferrals, sent
        self.assertEqual(ops.split()[:3], ["window", "window", "window"])  # no CAD while the channel is busy
        self.assertEqual(ops.split().count("cad:0"), 1)
        # An unread frame in the chip at prepareTx defers too; the chip stays in RX.
        self.assertEqual(line(self.out, "RXPENDING"), "RXPENDING 2 1 1")

    def test_loop_stall_does_not_break_the_window(self):
        # 50 ms not yet passed since RX start: waits; after a 150 ms stall the marks decide at once.
        self.assertEqual(line(self.out, "STALL"), "STALL -1 1")
        # The same stall with a frame 30 ms before its end: deferred.
        self.assertEqual(line(self.out, "STALLBUSY"), "STALLBUSY -1 1")

    def test_30_deferrals_then_drop_without_debt(self):
        self.assertEqual(line(self.out, "DEFER30"), "DEFER30 0 30 31 1 0")

    def test_failed_debt_write_after_free_cad_sends_nothing(self):
        self.assertEqual(line(self.out, "DEBTFAIL"), "DEBTFAIL 0 0 1 window prep:0 cad:0 rx")
        self.assertTrue(any(l.startswith('{"loratx":"debt journal write failed"') for l in self.out))

    def test_silence_and_its_exception(self):
        self.assertEqual(line(self.out, "SILENCE"), "SILENCE 0 radio silence|- 1")

    def test_receive_assembles_508_b_from_frame_times(self):
        self.assertEqual(line(self.out, "RX508"), "RX508 508 1")
        self.assertEqual(line(self.out, "RXSHORT"), "RXSHORT 20")
        lora = json.loads(next(l for l in self.out if l.startswith('{"lora":')))["lora"]
        self.assertEqual((lora["rx_datagrams"], lora["header_only"], lora["assembly_timeout"], lora["split_lost"]), (2, 1, 1, 1))
        self.assertEqual((lora["rx_late"], lora["rx_ring_overflow"], lora["cca_threshold_dbm"]), (2, 0, -100))
        self.assertEqual((lora["cad_busy"], lora["rssi_busy"], lora["rx_busy"]), (32, 1, 3))

    def test_receive_rearmed_after_reconfiguration(self):
        self.assertEqual(line(self.out, "REARM"), "REARM 0 - 1 1")

    def test_emc_pauses_the_stack_link(self):
        self.assertEqual(line(self.out, "EMC"), "EMC -|EMC mode on: EMC 0 first|EMC mode on: EMC 0 first 1 0")
        self.assertEqual(line(self.out, "EMCOFF"), "EMCOFF 0 1 1")


if __name__ == "__main__":
    unittest.main()
