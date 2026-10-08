# SPDX-License-Identifier: MIT
"""Host checks of the radio link layer shared by bench A and bench B: the S2-LP link driver
(firmware/src/s2lp_link.cpp) against a model of the chip (SPI headers, states, FIFOs, read-clear IRQ
status, DS11896) and measure::Bench (firmware/src/measure.cpp) against a fake radiolink::Driver
(test series, P1 send with CCA and debt, P1 receive and assembly, FOFF, carrier)."""

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
    const char* foffInside = bench.foff(1000) ? "error" : "-";
    printf("FOFF %s %s %ld\n", foffOutside ? foffOutside : "-", foffInside, static_cast<long>(radio.offset));
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

    def test_test_frames_received_with_driver_rssi(self):
        self.assertEqual(line(self.out, "RXSTART"), "RXSTART - 1 0 20")
        self.assertEqual(line(self.out, "TESTRX"), "TESTRX 3 -240 90")

    def test_frequency_offset_and_carrier_via_driver(self):
        self.assertEqual(line(self.out, "FOFF"), "FOFF FOFF outside the radio range (about +-1 MHz) - 40")
        self.assertIn('{"foff_hz":1000,"set":true,"freqoff":40,"applied_hz":1000.0,"step_hz":25.00}', self.out)
        self.assertEqual(line(self.out, "TXCW"), "TXCW - 1")
        self.assertIn('"marc":"TX"', next(text for text in self.out if text.startswith('{"txcw":true')))
        self.assertEqual(line(self.out, "TXCWEND"), "TXCWEND 0")


if __name__ == "__main__":
    unittest.main()
