// SPDX-License-Identifier: MIT
// Sterownik Semtech SX1262 przez SPI (karta SX1261/2 DS.SX1261-2.W.APP rev. 2.2, rozdziały 8, 11-13):
// polecenia z parametrami, odczyt z bajtem statusu, rejestry pod adresem 16-bitowym, bufor danych,
// linia BUSY przed każdą transakcją, reset pinem NRESET, uśpienie i wybudzenie przez NSS. Nie zależy
// od MCU (Arduino SPI). Profil LoRa i sterowanie RXEN są w sx1262_link.cpp.
// SPI w trybie 0, MSB pierwszy. Polecenie: kod, parametry. Odczyt (GetStatus, GetIrqStatus, ...): kod,
// bajt statusu (układ wysyła go w miejscu NOP), dane. Rejestry: 0x0D/0x1D, adres starszym bajtem
// pierwszy; odczyt z bajtem statusu przed danymi. Każda transakcja dopiero przy BUSY w stanie niskim.
#pragma once

#include <Arduino.h>
#include <SPI.h>

namespace sx1262 {

// Polecenia (tabela 11-1 i następne).
constexpr uint8_t OP_SET_SLEEP = 0x84;
constexpr uint8_t OP_SET_STANDBY = 0x80;
constexpr uint8_t OP_SET_TX = 0x83;
constexpr uint8_t OP_SET_RX = 0x82;
constexpr uint8_t OP_SET_TX_CW = 0xD1;
constexpr uint8_t OP_SET_REGULATOR_MODE = 0x96;
constexpr uint8_t OP_CALIBRATE = 0x89;
constexpr uint8_t OP_CALIBRATE_IMAGE = 0x98;
constexpr uint8_t OP_SET_PA_CONFIG = 0x95;
constexpr uint8_t OP_SET_RX_TX_FALLBACK = 0x93;
constexpr uint8_t OP_WRITE_REGISTER = 0x0D;
constexpr uint8_t OP_READ_REGISTER = 0x1D;
constexpr uint8_t OP_WRITE_BUFFER = 0x0E;
constexpr uint8_t OP_READ_BUFFER = 0x1E;
constexpr uint8_t OP_SET_DIO_IRQ_PARAMS = 0x08;
constexpr uint8_t OP_GET_IRQ_STATUS = 0x12;
constexpr uint8_t OP_CLEAR_IRQ_STATUS = 0x02;
constexpr uint8_t OP_SET_DIO2_RF_SWITCH = 0x9D;
constexpr uint8_t OP_SET_DIO3_TCXO = 0x97;
constexpr uint8_t OP_SET_RF_FREQUENCY = 0x86;
constexpr uint8_t OP_SET_PACKET_TYPE = 0x8A;
constexpr uint8_t OP_GET_PACKET_TYPE = 0x11;
constexpr uint8_t OP_SET_TX_PARAMS = 0x8E;
constexpr uint8_t OP_SET_MODULATION_PARAMS = 0x8B;
constexpr uint8_t OP_SET_PACKET_PARAMS = 0x8C;
constexpr uint8_t OP_SET_BUFFER_BASE = 0x8F;
constexpr uint8_t OP_GET_STATUS = 0xC0;
constexpr uint8_t OP_GET_RX_BUFFER_STATUS = 0x13;
constexpr uint8_t OP_GET_PACKET_STATUS = 0x14;
constexpr uint8_t OP_GET_RSSI_INST = 0x15;
constexpr uint8_t OP_GET_DEVICE_ERRORS = 0x17;
constexpr uint8_t OP_CLEAR_DEVICE_ERRORS = 0x07;
constexpr uint8_t OP_SET_CAD = 0xC5;
constexpr uint8_t OP_SET_CAD_PARAMS = 0x88;

// Rejestry (tabela 12-1) i zmiany z rozdziału 15 (ograniczenia układu).
constexpr uint16_t REG_RETENTION_COUNT = 0x029F;  // liczba rejestrów zachowywanych w uśpieniu (rozdz. 9.6)
constexpr uint16_t REG_RETENTION_LIST = 0x02A0;   // adresy po 2 B, starszy bajt pierwszy
constexpr uint16_t REG_VERSION = 0x0320;          // tekst wersji, np. "SX1261 V2D 2D02" (16 B; tak czyta go RadioLib)
constexpr size_t VERSION_BYTES = 16;
constexpr uint16_t REG_IQ_POLARITY = 0x0736;      // bit 2 = 1 przy zwykłej polaryzacji IQ (rozdz. 15.4)
constexpr uint16_t REG_SYNC_WORD = 0x0740;        // słowo synchronizacji LoRa, 2 B
constexpr uint16_t REG_TX_MODULATION = 0x0889;    // bit 2 = 1 przy szerokości pasma innej niż 500 kHz (rozdz. 15.1)
constexpr uint16_t REG_RX_GAIN = 0x08AC;          // 0x94 tryb oszczędny (po resecie), 0x96 Rx Boosted
constexpr uint16_t REG_TX_CLAMP = 0x08D8;         // bity 4:1 = 1111 przy niedopasowaniu anteny (rozdz. 15.2)
constexpr uint16_t REG_OCP = 0x08E7;              // limit prądu PA, krok 2,5 mA

constexpr uint8_t RX_GAIN_POWER_SAVING = 0x94;
constexpr uint8_t RX_GAIN_BOOSTED = 0x96;

// Parametr SetStandby (tabela 13-4).
constexpr uint8_t STDBY_RC = 0x00;
constexpr uint8_t STDBY_XOSC = 0x01;
// Tryb powrotu po TxDone i po odbiorze pojedynczym (SetRxTxFallbackMode, tabela 13-23).
constexpr uint8_t FALLBACK_STDBY_RC = 0x20;
constexpr uint8_t FALLBACK_STDBY_XOSC = 0x30;

// Bajt statusu: [6:4] tryb układu, [3:1] stan polecenia (tabela 13-76).
constexpr uint8_t MODE_STBY_RC = 0x2;
constexpr uint8_t MODE_STBY_XOSC = 0x3;
constexpr uint8_t MODE_FS = 0x4;
constexpr uint8_t MODE_RX = 0x5;
constexpr uint8_t MODE_TX = 0x6;

// Przerwania (tabela 13-29).
constexpr uint16_t IRQ_TX_DONE = 1u << 0;
constexpr uint16_t IRQ_RX_DONE = 1u << 1;
constexpr uint16_t IRQ_PREAMBLE_DETECTED = 1u << 2;
constexpr uint16_t IRQ_HEADER_VALID = 1u << 4;
constexpr uint16_t IRQ_HEADER_ERR = 1u << 5;
constexpr uint16_t IRQ_CRC_ERR = 1u << 6;
constexpr uint16_t IRQ_CAD_DONE = 1u << 7;
constexpr uint16_t IRQ_CAD_DETECTED = 1u << 8;
constexpr uint16_t IRQ_TIMEOUT = 1u << 9;
constexpr uint16_t IRQ_ALL = 0x03FF;

constexpr uint8_t PACKET_TYPE_LORA = 0x01;
constexpr uint32_t F_XTAL_HZ = 32000000;   // TCXO 32 MHz na module
constexpr uint32_t BUSY_TIMEOUT_US = 20000;  // najdłużej Calibrate z TCXO (3,5 ms) i start TCXO z zapasem

struct Status {
    uint8_t raw = 0;
    uint8_t mode() const { return (raw >> 4) & 0x7; }
};

struct Identity {
    char version[VERSION_BYTES + 1];  // z REG_VERSION, znaki spoza ASCII zamienione na '.'
    bool sx126x;                      // tekst zaczyna się od "SX126" (RadioLib: SX126x::findChip)
};

const char* modeName(uint8_t mode);

class Radio {
public:
    Radio(SPIClass& spi, uint8_t pinCs, uint8_t pinReset, uint8_t pinBusy, uint32_t spiHz);

    // NSS wysoki, NRESET jako wyjście w stanie wysokim (na N1 R12 = 1 kΩ do masy: bez napędu układ
    // zostałby w resecie), BUSY jako wejście.
    void begin();
    // NRESET niski na 1 ms (karta: ≥100 µs), potem wysoki i czekanie na BUSY niski; układ w STDBY_RC.
    bool reset();

    // Transakcje; false, gdy BUSY nie zszedł przed transakcją do BUSY_TIMEOUT_US (liczone w busyTimeouts).
    bool command(uint8_t op, const uint8_t* params = nullptr, size_t count = 0);
    bool read(uint8_t op, uint8_t* data, size_t count);  // status w lastStatus()
    bool writeRegs(uint16_t address, const uint8_t* data, size_t count);
    bool readRegs(uint16_t address, uint8_t* data, size_t count);
    bool writeReg(uint16_t address, uint8_t value) { return writeRegs(address, &value, 1); }
    uint8_t readReg(uint16_t address);
    bool writeBuffer(uint8_t offset, const uint8_t* data, size_t count);
    bool readBuffer(uint8_t offset, uint8_t* data, size_t count);

    Status status();  // GetStatus
    Status lastStatus() const { return status_; }
    Identity identify();
    uint16_t irqStatus();                // 0 także przy przekroczeniu czasu BUSY
    bool readIrq(uint16_t& irq);         // jak irqStatus(), ale false przy przekroczeniu czasu BUSY
    bool clearIrq(uint16_t mask);
    uint16_t deviceErrors();

    // Uśpienie z zachowaniem konfiguracji (ciepły start) i wybudzenie zboczem NSS.
    void sleepWarm();
    bool wake();

    bool busy() const;
    uint32_t busyTimeouts() const { return busyTimeouts_; }

private:
    bool waitBusy();
    void select();
    void deselect();

    SPIClass& spi_;
    uint8_t pinCs_;
    uint8_t pinReset_;
    uint8_t pinBusy_;
    SPISettings settings_;
    Status status_{};
    uint32_t busyTimeouts_ = 0;
};

}  // namespace sx1262
