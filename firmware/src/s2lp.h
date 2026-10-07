// SPDX-License-Identifier: MIT
// Sterownik ST S2-LP przez SPI (karta DS11896, rozdziały 6 i 9.1): odczyt i zapis rejestrów,
// polecenia, stan głównego sterownika z bajtów statusu, wyłączenie pinem SDN, zapis tablicy
// rejestrów z weryfikacją odczytem. Nie zależy od MCU (Arduino SPI).
// SPI w trybie 0, MSB pierwszy. Pierwszy bajt: 0x00 zapis, 0x01 odczyt, 0x80 polecenie; drugi
// bajt to adres albo kod polecenia. W tym czasie układ wysyła na MISO MC_STATE1 i MC_STATE0.
#pragma once

#include <Arduino.h>
#include <SPI.h>

namespace s2lp {

constexpr uint8_t HEADER_WRITE = 0x00;
constexpr uint8_t HEADER_READ = 0x01;
constexpr uint8_t HEADER_COMMAND = 0x80;

// Polecenia (tabela 49).
constexpr uint8_t CMD_TX = 0x60;
constexpr uint8_t CMD_RX = 0x61;
constexpr uint8_t CMD_READY = 0x62;
constexpr uint8_t CMD_STANDBY = 0x63;
constexpr uint8_t CMD_SLEEP = 0x64;
constexpr uint8_t CMD_LOCKRX = 0x65;
constexpr uint8_t CMD_LOCKTX = 0x66;
constexpr uint8_t CMD_SABORT = 0x67;
constexpr uint8_t CMD_SRES = 0x70;
constexpr uint8_t CMD_FLUSHRXFIFO = 0x71;
constexpr uint8_t CMD_FLUSHTXFIFO = 0x72;

// Rejestry konfiguracji używane w czasie pracy (pełna tablica P1 w s2lp_p1_registers.h).
constexpr uint8_t SYNT3 = 0x05;          // [7:5] PLL_CP_ISEL, [4] BS, [3:0] SYNT[27:24]
constexpr uint8_t MOD2 = 0x10;           // [7:4] MOD_TYPE, [3:0] DATARATE_E
constexpr uint8_t MOD_TYPE_CW = 0x7;     // nośna bez modulacji
constexpr uint8_t PCKTCTRL2 = 0x2F;      // [0] FIX_VAR_LEN
constexpr uint8_t PCKTCTRL1 = 0x30;      // [3:2] TXSOURCE
constexpr uint8_t TXSOURCE_PN9 = 0x0C;
constexpr uint8_t PCKTLEN1 = 0x31;
constexpr uint8_t PCKTLEN0 = 0x32;
constexpr uint8_t IRQ_MASK3 = 0x50;
constexpr uint8_t FIFO = 0xFF;           // adres kolejek: zapis TX, odczyt RX

// Rejestry stanu i identyfikacji (tabela rejestrów karty).
constexpr uint8_t MC_STATE1 = 0x8D;
constexpr uint8_t MC_STATE0 = 0x8E;  // [7:1] STATE, [0] XO_ON
constexpr uint8_t TX_FIFO_STATUS = 0x8F;
constexpr uint8_t RX_FIFO_STATUS = 0x90;
constexpr uint8_t AFC_CORR = 0x9E;
constexpr uint8_t LINK_QUALIF1 = 0xA0;  // [7] CS, [6:0] SQI
constexpr uint8_t RSSI_LEVEL = 0xA2;    // RSSI pakietu zapamiętane po słowie synchronizacji
constexpr uint8_t RX_PCKT_LEN1 = 0xA4;
constexpr uint8_t RSSI_LEVEL_RUN = 0xEF;
constexpr int16_t RSSI_OFFSET_DB = -146;  // dBm = RSSI_LEVEL - 146 (tabela 62)
constexpr uint8_t IRQ_STATUS3 = 0xFA;   // IRQ_STATUS3..0: bity 31..0, kasowane odczytem
constexpr uint8_t DEVICE_INFO1 = 0xF0;  // PARTNUM
constexpr uint8_t DEVICE_INFO0 = 0xF1;  // VERSION
constexpr uint8_t PARTNUM_S2LP = 0x03;

// Stany głównego sterownika (tabela 48); inne kody oznaczają błąd konfiguracji albo sprzętu.
constexpr uint8_t STATE_READY = 0x00;
constexpr uint8_t STATE_SLEEP_A = 0x01;
constexpr uint8_t STATE_STANDBY = 0x02;
constexpr uint8_t STATE_SLEEP_B = 0x03;
constexpr uint8_t STATE_LOCK = 0x0C;
constexpr uint8_t STATE_RX = 0x30;
constexpr uint8_t STATE_SYNTH_SETUP = 0x50;
constexpr uint8_t STATE_TX = 0x5C;

constexpr uint32_t SHUTDOWN_TO_READY_US = 500;  // tabela 50

// Przerwania (tabela 59); zdarzenia trafiają do IRQ_STATUS tylko przy bicie IRQ_MASK = 1.
constexpr uint32_t IRQ_RX_DATA_READY = 1u << 0;
constexpr uint32_t IRQ_RX_DATA_DISC = 1u << 1;
constexpr uint32_t IRQ_TX_DATA_SENT = 1u << 2;
constexpr uint32_t IRQ_TX_FIFO_ERROR = 1u << 5;
constexpr uint32_t IRQ_RX_FIFO_ERROR = 1u << 6;
constexpr uint32_t IRQ_VALID_SYNC = 1u << 13;

// Bajty statusu z początku każdej transakcji.
struct Status {
    uint8_t mcState1;
    uint8_t mcState0;
    uint8_t state() const { return mcState0 >> 1; }
    bool xoOn() const { return mcState0 & 1u; }
};

struct Identity {
    Status status;
    uint8_t partNumber;
    uint8_t version;
    bool s2lp;  // PARTNUM = 0x03
};

// Wpis tablicy rejestrów: adres, wartość, maska porównania przy weryfikacji, nazwa.
struct RegisterValue {
    uint8_t address;
    uint8_t value;
    uint8_t verifyMask;
    const char* name;
};

struct VerifyResult {
    uint16_t checked;
    uint16_t mismatches;
    uint8_t firstAddress;
    uint8_t expected;
    uint8_t actual;
    const char* firstName;
};

const char* stateName(uint8_t state);
const char* versionName(uint8_t version);  // wersja krzemu z DEVICE_INFO0, jeśli znana

class Radio {
public:
    Radio(SPIClass& spi, uint8_t pinCs, uint8_t pinSdn, uint32_t spiHz);

    // CSn w stan wysoki, SDN w stan niski (układ włączony).
    void begin();
    // SDN w stan wysoki na 1 ms, potem niski i 500 us do READY, potem SRES. Kasuje rejestry.
    void reset();
    void shutdown(bool on);
    bool isShutdown() const { return shutdown_; }

    uint8_t readReg(uint8_t address);
    void readRegs(uint8_t address, uint8_t* data, size_t count);
    void writeReg(uint8_t address, uint8_t value);
    void writeRegs(uint8_t address, const uint8_t* data, size_t count);
    void command(uint8_t code);
    Status status();  // odczyt MC_STATE1 i MC_STATE0 rejestrami
    Status lastStatus() const { return status_; }
    Identity identify();
    void writeFifo(const uint8_t* data, size_t count) { writeRegs(FIFO, data, count); }
    void readFifo(uint8_t* data, size_t count) { readRegs(FIFO, data, count); }
    uint32_t readIrqStatus();  // IRQ_STATUS3..0 jako słowo 32-bitowe; odczyt je kasuje
    // Polecenie i czekanie na stan, najwyżej timeoutUs; true, gdy stan osiągnięty.
    bool commandAndWait(uint8_t code, uint8_t state, uint32_t timeoutUs);
    bool waitState(uint8_t state, uint32_t timeoutUs);

    // Zapis tablicy w stanie READY i porównanie odczytem; verify bez zapisu.
    VerifyResult configure(const RegisterValue* table, size_t count);
    VerifyResult verify(const RegisterValue* table, size_t count);

private:
    void begin(uint8_t header, uint8_t second);
    void end();

    SPIClass& spi_;
    uint8_t pinCs_;
    uint8_t pinSdn_;
    SPISettings settings_;
    Status status_{};
    bool shutdown_ = false;
};

}  // namespace s2lp
