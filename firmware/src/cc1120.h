// SPDX-License-Identifier: MIT
// Dostęp do CC1120 przez SPI: strobe, rejestry zwykłe i rozszerzone, identyfikacja,
// zapis tablicy konfiguracji z weryfikacją odczytu, ręczna kalibracja syntezera
// według erraty, odczyt częstotliwości i RSSI. Adresy i wzory: SWRU295E.
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
constexpr uint16_t FREQOFF1 = 0x2F0A;
constexpr uint16_t FREQOFF0 = 0x2F0B;
constexpr uint16_t FREQ2 = 0x2F0C;
constexpr uint16_t FREQ1 = 0x2F0D;
constexpr uint16_t FREQ0 = 0x2F0E;
constexpr uint16_t FS_CAL2 = 0x2F15;
constexpr uint16_t FS_CHP = 0x2F18;
constexpr uint16_t FS_VCO4 = 0x2F23;
constexpr uint16_t FS_VCO2 = 0x2F25;
constexpr uint16_t RSSI1 = 0x2F71;
constexpr uint16_t RSSI0 = 0x2F72;
constexpr uint16_t MARCSTATE = 0x2F73;
constexpr uint16_t FREQOFF_EST1 = 0x2F77;
constexpr uint16_t FREQOFF_EST0 = 0x2F78;
constexpr uint16_t PARTNUMBER = 0x2F8F;
constexpr uint16_t PARTVERSION = 0x2F90;
constexpr uint16_t NUM_TXBYTES = 0x2FD6;
constexpr uint16_t NUM_RXBYTES = 0x2FD7;

constexpr uint8_t PARTNUMBER_CC1120 = 0x48;

// Bajt stanu zwracany przy każdym nagłówku: bit 7 = CHIP_RDYn, bity 6:4 = stan.
constexpr uint8_t STATUS_CHIP_RDYn = 0x80;
inline uint8_t statusState(uint8_t status) { return (status >> 4) & 0x07; }
const char* stateName(uint8_t state);

// MARCSTATE: bity 6:5 = stan dwupinowy, bity 4:0 = stan MARC (marcState()).
constexpr uint8_t MARC_STATE_IDLE = 0x01;
constexpr uint8_t MARC_STATE_RX = 0x0D;
constexpr uint8_t MARC_STATE_RX_FIFO_ERR = 0x11;
constexpr uint8_t MARC_STATE_TX = 0x13;
constexpr uint8_t MARC_STATE_TX_FIFO_ERR = 0x16;

// Rejestry zwykłe używane przez pomiary (pełna tablica P1 w p1_registers.h).
constexpr uint16_t DEVIATION_M = 0x000A;
constexpr uint16_t MODCFG_DEV_E = 0x000B;
constexpr uint16_t PKT_CFG2 = 0x0026;
constexpr uint16_t PKT_CFG0 = 0x0028;
constexpr uint16_t PKT_LEN = 0x002E;
constexpr uint8_t PKT_FORMAT_RANDOM = 0x02;        // PKT_CFG2.PKT_FORMAT = 10: dane z generatora PN9
constexpr uint8_t LENGTH_CONFIG_INFINITE = 0x40;   // PKT_CFG0.LENGTH_CONFIG = 10
inline uint8_t marcState(uint8_t marcstate) { return marcstate & 0x1F; }
const char* marcStateName(uint8_t marcState);

// RSSI0: bity 6:3 = RSSI[3:0], bit 2 = CARRIER_SENSE, bit 1 = CARRIER_SENSE_VALID, bit 0 = RSSI_VALID.
constexpr uint8_t RSSI0_CARRIER_SENSE = 0x04;
constexpr uint8_t RSSI0_CARRIER_SENSE_VALID = 0x02;
constexpr uint8_t RSSI0_VALID = 0x01;

struct Identity {
    bool ready;          // CHIP_RDYn = 0 po resecie
    uint8_t status;      // ostatni bajt stanu
    uint8_t partNumber;  // 0x48 = CC1120
    uint8_t partVersion;
    uint8_t marcState;
};

// Wiersz tablicy konfiguracji (generowanej do p1_registers.h).
struct RegisterValue {
    uint16_t address;    // 0x00xx: przestrzeń zwykła, 0x2Fxx: rozszerzona
    uint8_t value;
    uint8_t verifyMask;  // bity porównywane po odczycie (bity tylko do odczytu pominięte)
    const char* name;
};

struct VerifyResult {
    uint16_t checked;
    uint16_t mismatches;
    const char* firstName;  // pierwszy niezgodny rejestr albo nullptr
    uint16_t firstAddress;
    uint8_t expected;
    uint8_t actual;
};

struct Rssi {
    bool valid;
    int16_t dbm;         // RSSI[11:4] + przesunięcie podane przez wołającego
    bool carrierSense;
    bool carrierSenseValid;
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

    // Zapis całej tablicy (w stanie IDLE), potem odczyt i porównanie z maską.
    VerifyResult configure(const RegisterValue* table, size_t count);
    VerifyResult verify(const RegisterValue* table, size_t count);
    // Ręczna kalibracja syntezera z erraty CC112x (TI swrc253e, manualCalibration):
    // dwa przebiegi SCAL z różnym VCDAC_START, zachowany wynik z większym FS_VCO2.
    bool calibrate(uint32_t timeoutMs = 100);
    // Przejście do IDLE i oczekiwanie na MARCSTATE = IDLE.
    bool idle(uint32_t timeoutMs = 50);
    bool waitMarcState(uint8_t marcState, uint32_t timeoutMs);
    uint8_t readMarcState() { return marcState(readReg(MARCSTATE)); }

    // Kolejki FIFO: zapis i odczyt seryjny (nagłówek 0x7F / 0xFF), liczba bajtów w kolejkach.
    void writeFifo(const uint8_t* data, size_t count);
    void readFifo(uint8_t* data, size_t count);
    uint8_t rxBytes() { return readReg(NUM_RXBYTES); }
    uint8_t txBytes() { return readReg(NUM_TXBYTES); }

    uint32_t frequencyWord();                  // FREQ[23:0]
    int16_t frequencyOffset();                 // FREQOFF, dopełnienie do dwóch
    void setFrequencyOffset(int16_t offset);   // zapis FREQOFF1/0 (w IDLE)
    int16_t frequencyOffsetEstimate();         // FREQOFF_EST z ostatniego odbioru
    Rssi rssi(int8_t offsetDb);                // ważne w stanie RX

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
