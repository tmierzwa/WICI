// SPDX-License-Identifier: MIT
// Emulowane układy płytki N1: S2-LP (ST DS11896), FRAM CY15B104Q, ekran Sharp LS027B7DH01A.
// Każdy odpowiada na magistrali SPI tak, jak opisuje karta katalogowa; sterowniki z firmware/src
// rozmawiają z nimi bez zmian. Zachowania analogowe radia (czułość, kolizje, pomiar RSSI) są modelem.
#pragma once

#include <stdint.h>

#include <deque>
#include <vector>

#include "vboard.h"

namespace chips {

// Ramka w eterze (czas bezwzględny symulacji w µs), widziana przez jeden odbiornik.
struct AirFrame {
    uint32_t id = 0;
    uint64_t startUs = 0;     // początek preambuły
    uint64_t syncUs = 0;      // koniec słowa synchronizacji
    uint64_t endUs = 0;       // koniec pakietu (przy przerwaniu nadawania skrócony)
    double freqHz = 0;
    double rate = 0;          // symbole/s
    uint32_t sync = 0;
    uint8_t syncBits = 0;
    int16_t dbm = 0;          // moc u odbiorcy
    bool carrier = false;     // nośna CW albo PN9 (bez pakietu)
    bool aborted = false;
    bool seen = false;        // odbiornik już ocenił słowo synchronizacji
    std::vector<uint8_t> payload;   // bajty po słowie synchronizacji: pole LEN i treść
};

class S2lp : public vb::SpiDevice {
public:
    S2lp();
    void select() override;
    uint8_t exchange(uint8_t wire) override;
    void deselect() override;
    void setShutdown(bool on);     // pin SDN
    void setDead(bool dead);       // awaria: SDO bez odpowiedzi
    void tick(uint64_t worldUs);   // zdarzenia czasowe (koniec nadawania, odbiór)
    bool gpio(uint8_t index) const;  // stan wyjść GPIO0..3 według GPIOx_CONF
    // Eter: ramki nadane przez ten układ (środowisko je odbiera) i ramki innych (wstrzykiwane).
    std::vector<AirFrame> takeTransmitted();
    void airUpdate(const AirFrame& frame);   // nowa ramka albo skrócenie przerwanej
    double frequencyHz() const;
    bool transmitting() const { return txActive_; }
    double rate() const;
    int16_t txDbm() const;

private:
    void reset();
    void command(uint8_t code, uint64_t now);
    uint8_t readReg(uint8_t address);
    void writeReg(uint8_t address, uint8_t value);
    void raise(uint32_t bits) { irq_ |= bits & mask(); }
    uint32_t mask() const;
    void startTx(uint64_t now);
    void endTx(uint64_t now, bool aborted);
    void deliver(AirFrame& f, uint64_t now);
    int16_t rssiNow(uint64_t now) const;
    uint8_t status1() const;
    uint8_t status0() const { return static_cast<uint8_t>(state_ << 1 | 1); }

    uint8_t regs_[256] = {};
    uint8_t state_ = 0;
    bool shutdown_ = false;
    bool dead_ = false;
    uint32_t irq_ = 0;
    std::deque<uint8_t> txFifo_, rxFifo_;
    // transakcja SPI
    int byteIndex_ = 0;
    uint8_t header_ = 0, address_ = 0;
    // nadawanie
    bool txActive_ = false;
    AirFrame tx_;
    uint32_t nextId_ = 1;
    std::vector<AirFrame> transmitted_;
    // odbiór
    uint64_t rxSince_ = 0;
    std::vector<AirFrame> air_;
    uint32_t locked_ = 0;          // ramka po słowie synchronizacji
    uint8_t rssiLevel_ = 0, sqi_ = 0;
    uint16_t rxLength_ = 0;
    uint64_t lastUs_ = 0;
};

class Fram : public vb::SpiDevice {
public:
    explicit Fram(std::vector<uint8_t>& memory) : memory_(memory) {}
    void select() override { index_ = 0; }
    uint8_t exchange(uint8_t wire) override;
    void deselect() override;
    bool failWrites = false;   // awaria: zapis nie zostaje w pamięci

private:
    std::vector<uint8_t>& memory_;
    int index_ = 0;
    uint8_t opcode_ = 0;
    uint32_t address_ = 0;
    bool wel_ = false;
    bool wrote_ = false;
};

class Sharp : public vb::SpiDevice {
public:
    Sharp();
    void select() override;
    uint8_t exchange(uint8_t wire) override;
    void deselect() override;
    uint8_t frame[240][50];    // bit 0 bajtu = lewy piksel, 1 = biały (piksel odbija światło)
    uint32_t version = 1;      // rośnie z każdą zmianą obrazu
    uint32_t lineWrites = 0;

private:
    void bit(bool b);
    enum class Phase : uint8_t { MODE, ADDRESS, DATA, GAP, DUMMY };
    Phase phase_ = Phase::MODE;
    int count_ = 0;
    uint8_t mode_ = 0, address_ = 0;
    uint8_t line_[50] = {};
    bool changed_ = false;
};

}  // namespace chips
