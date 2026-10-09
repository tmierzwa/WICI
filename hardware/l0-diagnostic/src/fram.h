// SPDX-License-Identifier: MIT
// FRAM SPI 4 Mbit (CY15B104QN, 512 KiB, adres 3-bajtowy):
// identyfikacja RDID, odczyt i zapis dowolnej długości (FRAM nie ma stron ani czasu programowania).
#pragma once

#include <Arduino.h>
#include <SPI.h>

#include "fram_id.h"

namespace fram {

constexpr uint8_t OP_WREN = 0x06;
constexpr uint8_t OP_RDSR = 0x05;
constexpr uint8_t OP_READ = 0x03;
constexpr uint8_t OP_WRITE = 0x02;
constexpr uint8_t OP_RDID = 0x9F;

struct Id {
    uint8_t bytes[ID_BYTES];
    uint8_t status;
    Part part;  // UNKNOWN: brak układu albo inna pamięć
};

class Memory {
public:
    Memory(SPIClass& spi, uint8_t cs, uint32_t hz);
    void begin();
    Id identify();
    bool read(uint32_t address, uint8_t* data, size_t count);
    bool write(uint32_t address, const uint8_t* data, size_t count);

private:
    void select();
    void release();
    void sendAddress(uint8_t opcode, uint32_t address);
    SPIClass& spi_;
    uint8_t cs_;
    SPISettings settings_;
};

}  // namespace fram
