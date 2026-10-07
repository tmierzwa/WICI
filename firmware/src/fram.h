// SPDX-License-Identifier: MIT
// FRAM SPI (RAMXEED/Fujitsu MB85RS4MT, 512 KiB, adres 3-bajtowy): identyfikacja RDID,
// odczyt i zapis dowolnej długości (FRAM nie ma stron ani czasu programowania).
// Implementuje journal::Storage dla dziennika stacji.
#pragma once

#include <Arduino.h>
#include <SPI.h>

#include "journal.h"

namespace fram {

constexpr uint8_t OP_WREN = 0x06;
constexpr uint8_t OP_RDSR = 0x05;
constexpr uint8_t OP_READ = 0x03;
constexpr uint8_t OP_WRITE = 0x02;
constexpr uint8_t OP_RDID = 0x9F;
constexpr uint32_t SIZE = 512UL * 1024;

// Odpowiedź RDID MB85RS4MT: producent 0x04, kod kontynuacji 0x7F, produkt 0x49 0x03
// (MB85RS4MTY: 0x49 0x0B). Tablica zgodna z biblioteką Adafruit_FRAM_SPI.
constexpr uint8_t MANUFACTURER_FUJITSU = 0x04;

struct Id {
    uint8_t bytes[4];
    uint8_t status;
    bool fujitsu;
    bool mb85rs4m;  // 4 Mbit: produkt 0x4903 albo 0x490B
};

class Memory : public journal::Storage {
public:
    Memory(SPIClass& spi, uint8_t cs, uint32_t hz);
    void begin();
    Id identify();
    bool read(uint32_t address, uint8_t* data, size_t count) override;
    bool write(uint32_t address, const uint8_t* data, size_t count) override;

private:
    void select();
    void release();
    void sendAddress(uint8_t opcode, uint32_t address);
    SPIClass& spi_;
    uint8_t cs_;
    SPISettings settings_;
};

}  // namespace fram
