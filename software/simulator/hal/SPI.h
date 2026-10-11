// SPDX-License-Identifier: MIT
// SPI Arduino dla symulatora: bajty idą do układu wybranego linią CS na wirtualnej płytce,
// w kolejności bitów z SPISettings, a każdy bajt trwa 8 taktów zegara magistrali.
#pragma once

#include "Arduino.h"

#define SPI_MODE0 0x00
#define SPI_MODE1 0x01
#define SPI_MODE2 0x02
#define SPI_MODE3 0x03

class SPISettings {
public:
    SPISettings() = default;
    SPISettings(uint32_t hz, uint8_t bitOrder, uint8_t mode) : hz(hz), bitOrder(bitOrder), mode(mode) {}
    uint32_t hz = 4000000;
    uint8_t bitOrder = MSBFIRST;
    uint8_t mode = SPI_MODE0;
};

class SPIClass {
public:
    void begin(int8_t = -1, int8_t = -1, int8_t = -1, int8_t = -1) { vb::spiBegin(); }
    void end() {}
    void beginTransaction(const SPISettings& s) { settings_ = s; }
    void endTransaction() {}
    uint8_t transfer(uint8_t data) { return vb::spiTransfer(data, settings_.bitOrder == LSBFIRST, settings_.mode, settings_.hz); }
    void transfer(void* buf, size_t count) {
        uint8_t* p = static_cast<uint8_t*>(buf);
        for (size_t i = 0; i < count; ++i) p[i] = transfer(p[i]);
    }
    void setFrequency(uint32_t hz) { settings_.hz = hz; }

private:
    SPISettings settings_;
};
extern SPIClass SPI;
