// SPDX-License-Identifier: MIT
#include "cc1120.h"

namespace cc1120 {

const char* stateName(uint8_t state) {
    switch (state) {
        case 0: return "IDLE";
        case 1: return "RX";
        case 2: return "TX";
        case 3: return "FSTXON";
        case 4: return "CALIBRATE";
        case 5: return "SETTLING";
        case 6: return "RX_FIFO_ERROR";
        case 7: return "TX_FIFO_ERROR";
        default: return "?";
    }
}

Radio::Radio(SPIClass& spi, uint8_t cs, uint8_t resetPin, uint32_t hz)
    : spi_(spi), cs_(cs), reset_(resetPin), settings_(hz, MSBFIRST, SPI_MODE0) {}

void Radio::begin() {
    pinMode(cs_, OUTPUT);
    digitalWrite(cs_, HIGH);
    pinMode(reset_, OUTPUT);
    digitalWrite(reset_, LOW);  // radio trzymane w resecie do jawnego reset()
}

void Radio::select() {
    spi_.beginTransaction(settings_);
    digitalWrite(cs_, LOW);
}

void Radio::release() {
    digitalWrite(cs_, HIGH);
    spi_.endTransaction();
}

uint8_t Radio::strobe(uint8_t command) {
    select();
    lastStatus_ = spi_.transfer(command);
    release();
    return lastStatus_;
}

uint8_t Radio::readReg(uint16_t address) {
    select();
    uint8_t value;
    if (address > 0xFF) {
        lastStatus_ = spi_.transfer(READ | EXT_ADDR);
        spi_.transfer(static_cast<uint8_t>(address & 0xFF));
    } else {
        lastStatus_ = spi_.transfer(READ | static_cast<uint8_t>(address & 0x3F));
    }
    value = spi_.transfer(0x00);
    release();
    return value;
}

uint8_t Radio::writeReg(uint16_t address, uint8_t value) {
    select();
    if (address > 0xFF) {
        lastStatus_ = spi_.transfer(EXT_ADDR);
        spi_.transfer(static_cast<uint8_t>(address & 0xFF));
    } else {
        lastStatus_ = spi_.transfer(static_cast<uint8_t>(address & 0x3F));
    }
    spi_.transfer(value);
    release();
    return lastStatus_;
}

bool Radio::waitReady(uint32_t timeoutMs) {
    const uint32_t start = millis();
    while (millis() - start < timeoutMs) {
        if ((strobe(SNOP) & STATUS_CHIP_RDYn) == 0) {
            return true;
        }
        delay(1);
    }
    return false;
}

bool Radio::reset() {
    digitalWrite(reset_, LOW);
    delay(2);
    digitalWrite(reset_, HIGH);
    delay(5);
    if (!waitReady()) {
        return false;
    }
    strobe(SRES);
    delay(2);
    return waitReady();
}

Identity Radio::identify() {
    Identity id{};
    id.ready = waitReady();
    id.partNumber = readReg(PARTNUMBER);
    id.partVersion = readReg(PARTVERSION);
    id.marcState = readReg(MARCSTATE) & 0x1F;
    id.status = lastStatus_;
    return id;
}

}  // namespace cc1120
