// SPDX-License-Identifier: MIT
// Emulacja S2-LP (ST DS11896) na poziomie magistrali SPI: nagłówek 0x00 zapis, 0x01 odczyt,
// 0x80 polecenie; w pierwszych dwóch bajtach układ zwraca MC_STATE1 i MC_STATE0. Rejestry, polecenia
// (TX, RX, READY, SABORT, SRES, FLUSH*), kolejki 128 B, IRQ_STATUS kasowane odczytem (zgłaszane tylko
// zdarzenia włączone w IRQ_MASK), tryb pakietu BASIC: preambuła z PCKTCTRL6/5, słowo synchronizacji
// z PCKTCTRL6 i SYNC3..0, pole długości 1 B, treść, bez CRC układu (P1 liczy CRC programowo);
// szybkość z MOD4..2 (wzór 14), częstotliwość z SYNT (wzór 7), moc z PA_POWER (wzór biblioteki ST).
// Odbiór: słowo synchronizacji wykryte, gdy odbiornik był w RX od początku ramki, a konfiguracja
// (słowo, szybkość, częstotliwość w paśmie filtru) i moc pozwalają; inna ramka, która nakłada się
// na odbieraną z mocą wyższą niż ona − 10 dB, przekłamuje bity (CRC P1 odrzuci ramkę). Model, nie pomiar.
#include "chips.h"

#include <math.h>
#include <string.h>

#include <algorithm>

namespace chips {

namespace {

constexpr uint8_t ST_READY = 0x00, ST_STANDBY = 0x02, ST_SLEEP = 0x01, ST_LOCK = 0x0C, ST_RX = 0x30, ST_TX = 0x5C;
constexpr uint32_t IRQ_RX_READY = 1u << 0, IRQ_RX_DISC = 1u << 1, IRQ_TX_SENT = 1u << 2, IRQ_TX_FIFO_ERR = 1u << 5,
                   IRQ_RX_FIFO_ERR = 1u << 6, IRQ_VALID_SYNC = 1u << 13;
constexpr size_t FIFO = 128;
constexpr double F_XO = 50e6;
constexpr int16_t NOISE_DBM = -120;
constexpr int16_t SENSITIVITY_DBM = -112;   // 2-GFSK 4,8 kBd, filtr 25 kHz: około −112 dBm (model)
constexpr int16_t CAPTURE_DB = 10;

}  // namespace
}  // namespace chips

namespace vb { uint64_t worldUs(); }   // czas bezwzględny symulacji (vboard.cpp)

namespace chips {
namespace {
uint64_t world() { return vb::worldUs(); }
}  // namespace

S2lp::S2lp() { reset(); }

void S2lp::reset() {
    memset(regs_, 0, sizeof(regs_));
    regs_[0x01] = 0xA2;  // GPIO1_CONF
    regs_[0x03] = 0xA2;  // GPIO3_CONF
    regs_[0x2E] = 0x20;  // PCKTCTRL3: tryb bezpośredni przez GPIO
    regs_[0x30] = 0x2C;  // PCKTCTRL1: TX z PN9
    regs_[0x40] = 0x40;  // PCKT_FLT_OPTIONS
    regs_[0x63] = 0x03;  // PA_CONFIG1
    regs_[0x64] = 0x8A;  // PA_CONFIG0
    regs_[0x6C] = 0x45;  // XO_RCO_CONF1
    regs_[0x6D] = 0x30;  // XO_RCO_CONF0
    regs_[0xF0] = 0x03;  // DEVICE_INFO1: PARTNUM S2-LP
    regs_[0xF1] = 0xC1;  // DEVICE_INFO0: wersja krzemu 3.0
    state_ = ST_READY;
    irq_ = 0;
    txFifo_.clear();
    rxFifo_.clear();
    txActive_ = false;
    locked_ = 0;
    rxLength_ = 0;
}

void S2lp::setShutdown(bool on) {
    if (on && !shutdown_) {
        if (txActive_) endTx(world(), true);
        reset();
    }
    shutdown_ = on;
}

void S2lp::setDead(bool dead) { dead_ = dead; }

uint32_t S2lp::mask() const {
    return static_cast<uint32_t>(regs_[0x50]) << 24 | static_cast<uint32_t>(regs_[0x51]) << 16 | static_cast<uint32_t>(regs_[0x52]) << 8 | regs_[0x53];
}

double S2lp::rate() const {
    // Wzór 14: DR = f_dig · (2^16 + M) · 2^E / 2^33 dla E > 0, f_dig = f_xo / 2 przy PD_CLKDIV = 0.
    const double fdig = (regs_[0x6C] & 0x10) ? F_XO : F_XO / 2;
    const uint16_t m = static_cast<uint16_t>(regs_[0x0E] << 8 | regs_[0x0F]);
    const uint8_t e = regs_[0x10] & 0x0F;
    if (e == 0) return fdig * m / 8589934592.0;
    return fdig * (65536.0 + m) * pow(2.0, e) / 8589934592.0;
}

double S2lp::frequencyHz() const {
    // Wzór 7: f = f_xo · SYNT / 2^19 / B / D; B = 4 (BS = 0) albo 8, D = 1 albo 2 (REFDIV).
    const uint32_t synt = static_cast<uint32_t>(regs_[0x05] & 0x0F) << 24 | static_cast<uint32_t>(regs_[0x06]) << 16 |
                          static_cast<uint32_t>(regs_[0x07]) << 8 | regs_[0x08];
    const double band = (regs_[0x05] & 0x10) ? 8 : 4;
    const double div = (regs_[0x6D] & 0x08) ? 2 : 1;
    return F_XO * synt / 524288.0 / band / div;
}

int16_t S2lp::txDbm() const {
    // Biblioteka ST: poziom indeksu PA_LEVEL_MAX_IDX w PA_POWER8 + 7 − indeks, dBm = (29 − wartość) / 2.
    const uint8_t index = regs_[0x62] & 0x07;
    const uint8_t value = regs_[0x5A + 7 - index] & 0x7F;
    return static_cast<int16_t>((29 - static_cast<int>(value)) / 2);
}

uint8_t S2lp::status1() const {
    // MC_STATE1: bit 2 RX_FIFO_EMPTY, bit 1 TX_FIFO_FULL (podzbiór).
    return static_cast<uint8_t>((rxFifo_.empty() ? 0x04 : 0) | (txFifo_.size() >= FIFO ? 0x02 : 0));
}

void S2lp::select() { byteIndex_ = 0; }

uint8_t S2lp::exchange(uint8_t wire) {
    if (shutdown_ || dead_) return 0x00;
    tick(world());
    uint8_t out = 0;
    if (byteIndex_ == 0) {
        header_ = wire;
        out = status1();
    } else if (byteIndex_ == 1) {
        address_ = wire;
        out = status0();
        if (header_ == 0x80) command(wire, world());
    } else if (header_ == 0x00) {
        writeReg(address_, wire);
        if (address_ != 0xFF) ++address_;
    } else if (header_ == 0x01) {
        out = readReg(address_);
        if (address_ != 0xFF) ++address_;
    }
    ++byteIndex_;
    return out;
}

void S2lp::deselect() {}

uint8_t S2lp::readReg(uint8_t a) {
    const uint64_t now = world();
    switch (a) {
        case 0xFF: {
            if (rxFifo_.empty()) { raise(IRQ_RX_FIFO_ERR); return 0; }
            const uint8_t b = rxFifo_.front();
            rxFifo_.pop_front();
            return b;
        }
        case 0x8D: return status1();
        case 0x8E: return status0();
        case 0x8F: return static_cast<uint8_t>(txFifo_.size());
        case 0x90: return static_cast<uint8_t>(rxFifo_.size());
        case 0xA0: return static_cast<uint8_t>((rssiNow(now) + 146 > regs_[0x18] ? 0x80 : 0) | sqi_);
        case 0xA2: return rssiLevel_;
        case 0xA4: return static_cast<uint8_t>(rxLength_ >> 8);
        case 0xA5: return static_cast<uint8_t>(rxLength_);
        case 0xEF: return static_cast<uint8_t>(std::max(0, std::min(255, rssiNow(now) + 146)));
        case 0xFA: case 0xFB: case 0xFC: case 0xFD: {
            const int shift = (0xFD - a) * 8;
            const uint8_t v = static_cast<uint8_t>(irq_ >> shift);
            irq_ &= ~(0xFFu << shift);
            return v;
        }
        default: return regs_[a];
    }
}

void S2lp::writeReg(uint8_t a, uint8_t v) {
    if (a == 0xFF) {
        if (txFifo_.size() >= FIFO) raise(IRQ_TX_FIFO_ERR);
        else txFifo_.push_back(v);
        return;
    }
    if (a >= 0x8D) return;  // rejestry stanu tylko do odczytu
    regs_[a] = v;
}

void S2lp::command(uint8_t code, uint64_t now) {
    switch (code) {
        case 0x60:  // TX
            if (state_ == ST_READY || state_ == ST_LOCK) startTx(now);
            break;
        case 0x61:  // RX
            if (state_ == ST_READY || state_ == ST_LOCK) {
                state_ = ST_RX;
                rxSince_ = now;
                locked_ = 0;
            }
            break;
        case 0x62: if (state_ == ST_STANDBY || state_ == ST_SLEEP || state_ == ST_LOCK) state_ = ST_READY; break;
        case 0x63: if (state_ == ST_READY) state_ = ST_STANDBY; break;
        case 0x64: if (state_ == ST_READY) state_ = ST_SLEEP; break;
        case 0x65: case 0x66: if (state_ == ST_READY) state_ = ST_LOCK; break;
        case 0x67:  // SABORT
            if (state_ == ST_TX) endTx(now, true);
            if (state_ == ST_RX) locked_ = 0;
            if (state_ == ST_TX || state_ == ST_RX) state_ = ST_READY;
            break;
        case 0x70: { const bool off = shutdown_; reset(); shutdown_ = off; break; }
        case 0x71: rxFifo_.clear(); break;
        case 0x72: txFifo_.clear(); break;
        default: break;
    }
}

void S2lp::startTx(uint64_t now) {
    AirFrame f;
    f.id = nextId_++;
    f.startUs = now;
    f.freqHz = frequencyHz();
    f.rate = rate();
    const uint8_t modType = regs_[0x10] >> 4;
    const uint8_t source = regs_[0x30] & 0x0C;
    f.carrier = modType == 0x7 || source == 0x0C;
    const uint32_t preambleBits = ((static_cast<uint32_t>(regs_[0x2B] & 0x03) << 8) | regs_[0x2C]) * 2;
    f.syncBits = static_cast<uint8_t>(regs_[0x2B] >> 2);
    f.sync = static_cast<uint32_t>(regs_[0x33]) << 24 | static_cast<uint32_t>(regs_[0x34]) << 16 | static_cast<uint32_t>(regs_[0x35]) << 8 | regs_[0x36];
    if (f.carrier) {
        f.syncUs = f.endUs = UINT64_MAX;
    } else {
        const bool variable = regs_[0x2F] & 0x01;
        const size_t length = static_cast<size_t>(regs_[0x31]) << 8 | regs_[0x32];
        if (txFifo_.size() < length) { raise(IRQ_TX_FIFO_ERR); state_ = ST_READY; return; }
        if (variable) f.payload.push_back(static_cast<uint8_t>(length));
        for (size_t i = 0; i < length; ++i) { f.payload.push_back(txFifo_.front()); txFifo_.pop_front(); }
        const double bits = preambleBits + f.syncBits + 8.0 * f.payload.size();
        f.syncUs = now + static_cast<uint64_t>((preambleBits + f.syncBits) * 1e6 / f.rate);
        f.endUs = now + static_cast<uint64_t>(bits * 1e6 / f.rate);
    }
    f.dbm = txDbm();
    tx_ = f;
    txActive_ = true;
    state_ = ST_TX;
    transmitted_.push_back(f);
}

void S2lp::endTx(uint64_t now, bool aborted) {
    txActive_ = false;
    if (aborted && now < tx_.endUs) {
        tx_.endUs = now;
        tx_.aborted = true;
        transmitted_.push_back(tx_);   // to samo id: odbiorcy skracają ramkę
    }
    if (!aborted) {
        raise(IRQ_TX_SENT);
        state_ = ST_READY;
    }
}

std::vector<AirFrame> S2lp::takeTransmitted() {
    std::vector<AirFrame> out;
    out.swap(transmitted_);
    return out;
}

void S2lp::airUpdate(const AirFrame& frame) {
    for (AirFrame& f : air_) {
        if (f.id == frame.id) { f.endUs = frame.endUs; f.aborted = frame.aborted; return; }
    }
    air_.push_back(frame);
}

int16_t S2lp::rssiNow(uint64_t now) const {
    // Suma mocy ramek w eterze i szumu (mW), jak pomiar RSSI w paśmie odbiornika.
    double mw = pow(10.0, NOISE_DBM / 10.0);
    const double f0 = frequencyHz();
    for (const AirFrame& f : air_) {
        if (f.startUs <= now && now < f.endUs && fabs(f.freqHz - f0) < 50000) mw += pow(10.0, f.dbm / 10.0);
    }
    if (txActive_) mw += pow(10.0, 0.0);   // własne nadawanie zatyka odbiornik
    return static_cast<int16_t>(lround(10.0 * log10(mw)));
}

void S2lp::deliver(AirFrame& f, uint64_t now) {
    // Przekłamania od nakładających się ramek (bez przechwycenia przy różnicy mocy < CAPTURE_DB).
    bool corrupt = false;
    for (const AirFrame& o : air_) {
        if (o.id == f.id || o.endUs <= f.startUs || o.startUs >= f.endUs) continue;
        if (fabs(o.freqHz - f.freqHz) < 25000 && o.dbm > f.dbm - CAPTURE_DB) corrupt = true;
    }
    std::vector<uint8_t> bytes = f.payload;
    if (f.aborted) corrupt = true;
    if (corrupt) {
        for (size_t i = 1; i < bytes.size(); ++i) bytes[i] ^= static_cast<uint8_t>(vb::random32() & 0x5A);
    }
    // Pole długości odczytuje układ (zmienna długość), treść trafia do kolejki RX.
    const bool variable = regs_[0x2F] & 0x01;
    size_t length = variable && !bytes.empty() ? bytes[0] : static_cast<size_t>(regs_[0x31]) << 8 | regs_[0x32];
    const size_t first = variable ? 1 : 0;
    const size_t maxLength = static_cast<size_t>(regs_[0x31]) << 8 | regs_[0x32];
    if (variable && length > maxLength) { raise(IRQ_RX_DISC); return; }
    if (bytes.size() < first + length) length = bytes.size() > first ? bytes.size() - first : 0;
    if (rxFifo_.size() + length > FIFO) { raise(IRQ_RX_FIFO_ERR); return; }
    for (size_t i = 0; i < length; ++i) rxFifo_.push_back(bytes[first + i]);
    rxLength_ = static_cast<uint16_t>(length);
    rssiLevel_ = static_cast<uint8_t>(std::max(0, std::min(255, f.dbm + 146)));
    sqi_ = corrupt ? 0x10 : 0x3F;
    raise(IRQ_RX_READY);
    (void)now;
}

void S2lp::tick(uint64_t now) {
    if (now < lastUs_) now = lastUs_;
    lastUs_ = now;
    if (shutdown_) return;
    if (txActive_ && !tx_.carrier && now >= tx_.endUs) endTx(tx_.endUs, false);
    if (state_ != ST_RX) {
        locked_ = 0;
    } else {
        const double f0 = frequencyHz(), dr = rate();
        const uint32_t sync = static_cast<uint32_t>(regs_[0x33]) << 24 | static_cast<uint32_t>(regs_[0x34]) << 16 |
                              static_cast<uint32_t>(regs_[0x35]) << 8 | regs_[0x36];
        // Ramki w kolejności czasu: wykrycie słowa synchronizacji, potem koniec pakietu.
        std::sort(air_.begin(), air_.end(), [](const AirFrame& a, const AirFrame& b) { return a.startUs < b.startUs; });
        for (AirFrame& f : air_) {
            if (locked_ == f.id && now >= f.endUs) {
                deliver(f, now);
                locked_ = 0;
                continue;
            }
            if (locked_ || f.carrier || f.syncUs > now || f.syncUs < rxSince_ + 1) continue;
            if (f.startUs < rxSince_) continue;   // odbiornik włączony po początku preambuły
            if (f.seen) continue;
            f.seen = true;
            const bool match = f.sync == sync && f.syncBits == (regs_[0x2B] >> 2) && fabs(f.rate - dr) < dr * 0.02 &&
                               fabs(f.freqHz - f0) < 12500 && f.dbm >= SENSITIVITY_DBM && !f.aborted;
            if (!match) continue;
            raise(IRQ_VALID_SYNC);
            locked_ = f.id;
            if (now >= f.endUs) { deliver(f, now); locked_ = 0; }
        }
    }
    // Ramki starsze niż 2 s nie wpływają już na pomiar ani kolizje.
    air_.erase(std::remove_if(air_.begin(), air_.end(), [now](const AirFrame& f) { return f.endUs + 2000000 < now; }), air_.end());
}

bool S2lp::gpio(uint8_t index) const {
    // GPIOx_CONF[7:3]: 0 = nIRQ (aktywne niskim), 15 = słowo synchronizacji wykryte, 20 = masa.
    const uint8_t function = regs_[index] >> 3;
    if (shutdown_) return false;
    if (function == 0) return (irq_ & mask()) == 0;
    if (function == 15) return locked_ != 0;
    return false;
}

}  // namespace chips
