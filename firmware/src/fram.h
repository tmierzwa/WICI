// SPDX-License-Identifier: MIT
// Identyfikacja FRAM SPI (RAMXEED/Fujitsu MB85RS4MT): RDID i rejestr stanu.
#pragma once

#include <Arduino.h>
#include <SPI.h>

namespace fram {

constexpr uint8_t OP_WREN = 0x06;
constexpr uint8_t OP_RDSR = 0x05;
constexpr uint8_t OP_READ = 0x03;
constexpr uint8_t OP_WRITE = 0x02;
constexpr uint8_t OP_RDID = 0x9F;

// Odpowiedź RDID MB85RS4MT: producent 0x04, kod kontynuacji 0x7F, produkt 0x49 0x03
// (MB85RS4MTY: 0x49 0x0B). Tablica zgodna z biblioteką Adafruit_FRAM_SPI.
constexpr uint8_t MANUFACTURER_FUJITSU = 0x04;

struct Id {
    uint8_t bytes[4];
    uint8_t status;
    bool fujitsu;
    bool mb85rs4m;  // 4 Mbit: produkt 0x4903 albo 0x490B
};

class Memory {
public:
    Memory(SPIClass& spi, uint8_t cs, uint32_t hz);
    void begin();
    Id identify();

private:
    SPIClass& spi_;
    uint8_t cs_;
    SPISettings settings_;
};

}  // namespace fram
