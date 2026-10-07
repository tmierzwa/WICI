// SPDX-License-Identifier: MIT
// Minimalny dostęp do CC1120 przez SPI: strobe, rejestry zwykłe i rozszerzone,
// identyfikacja układu. Bez konfiguracji profilu P1 (następny krok).
#pragma once

#include <Arduino.h>
#include <SPI.h>

namespace cc1120 {

// Nagłówek SPI: bit 7 = odczyt, bit 6 = seria (burst), bity 5:0 = adres.
constexpr uint8_t READ = 0x80;
constexpr uint8_t BURST = 0x40;
constexpr uint8_t EXT_ADDR = 0x2F;  // dostęp do przestrzeni rozszerzonej
constexpr uint8_t FIFO = 0x3F;

// Polecenia (command strobes).
constexpr uint8_t SRES = 0x30;
constexpr uint8_t SFSTXON = 0x31;
constexpr uint8_t SXOFF = 0x32;
constexpr uint8_t SCAL = 0x33;
constexpr uint8_t SRX = 0x34;
constexpr uint8_t STX = 0x35;
constexpr uint8_t SIDLE = 0x36;
constexpr uint8_t SAFC = 0x37;
constexpr uint8_t SWOR = 0x38;
constexpr uint8_t SPWD = 0x39;
constexpr uint8_t SFRX = 0x3A;
constexpr uint8_t SFTX = 0x3B;
constexpr uint8_t SWORRST = 0x3C;
constexpr uint8_t SNOP = 0x3D;

// Rejestry rozszerzone (adres 0x2Fxx).
constexpr uint16_t FREQ2 = 0x2F0C;
constexpr uint16_t FREQ1 = 0x2F0D;
constexpr uint16_t FREQ0 = 0x2F0E;
constexpr uint16_t RSSI1 = 0x2F71;
constexpr uint16_t RSSI0 = 0x2F72;
constexpr uint16_t MARCSTATE = 0x2F73;
constexpr uint16_t PARTNUMBER = 0x2F8F;
constexpr uint16_t PARTVERSION = 0x2F90;
constexpr uint16_t NUM_TXBYTES = 0x2FD6;
constexpr uint16_t NUM_RXBYTES = 0x2FD7;

constexpr uint8_t PARTNUMBER_CC1120 = 0x48;
constexpr uint8_t PARTNUMBER_CC1121 = 0x49;
constexpr uint8_t PARTNUMBER_CC1125 = 0x58;

// Bajt stanu zwracany przy każdym nagłówku: bit 7 = CHIP_RDYn, bity 6:4 = stan.
constexpr uint8_t STATUS_CHIP_RDYn = 0x80;
inline uint8_t statusState(uint8_t status) { return (status >> 4) & 0x07; }
const char* stateName(uint8_t state);

struct Identity {
    bool ready;          // CHIP_RDYn = 0 po resecie
    uint8_t status;      // ostatni bajt stanu
    uint8_t partNumber;  // 0x48 = CC1120
    uint8_t partVersion;
    uint8_t marcState;
};

class Radio {
public:
    Radio(SPIClass& spi, uint8_t cs, uint8_t resetPin, uint32_t hz);
    void begin();
    // Reset sprzętowy (RESET_N) i programowy (SRES); zwraca true, gdy układ zgłosił gotowość.
    bool reset();
    uint8_t strobe(uint8_t command);
    uint8_t readReg(uint16_t address);
    uint8_t writeReg(uint16_t address, uint8_t value);
    bool waitReady(uint32_t timeoutMs = 50);
    Identity identify();
    uint8_t lastStatus() const { return lastStatus_; }

private:
    void select();
    void release();
    SPIClass& spi_;
    uint8_t cs_;
    uint8_t reset_;
    SPISettings settings_;
    uint8_t lastStatus_ = 0xFF;
};

}  // namespace cc1120
