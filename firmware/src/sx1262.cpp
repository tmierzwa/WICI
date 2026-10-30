// SPDX-License-Identifier: MIT
#include "sx1262.h"

#include <string.h>

#if defined(WICI_RADIO_LOCK_CHECK)
#include "platform.h"
#endif

namespace sx1262 {

const char* modeName(uint8_t mode) {
    switch (mode) {
        case MODE_STBY_RC: return "STBY_RC";
        case MODE_STBY_XOSC: return "STBY_XOSC";
        case MODE_FS: return "FS";
        case MODE_RX: return "RX";
        case MODE_TX: return "TX";
        default: return "UNKNOWN";  // 0x0 i 0x7: brak odpowiedzi układu albo przerwa na MISO
    }
}

Radio::Radio(SPIClass& spi, uint8_t pinCs, uint8_t pinReset, uint8_t pinBusy, uint32_t spiHz)
    : spi_(spi), pinCs_(pinCs), pinReset_(pinReset), pinBusy_(pinBusy), settings_(spiHz, MSBFIRST, SPI_MODE0) {}

void Radio::begin() {
    pinMode(pinCs_, OUTPUT);
    digitalWrite(pinCs_, HIGH);
    pinMode(pinReset_, OUTPUT);
    digitalWrite(pinReset_, HIGH);
    pinMode(pinBusy_, INPUT);
}

bool Radio::reset() {
    digitalWrite(pinReset_, LOW);
    delay(1);
    digitalWrite(pinReset_, HIGH);
    delay(2);  // start układu do STDBY_RC; potem BUSY
    return waitBusy();
}

bool Radio::busy() const { return digitalRead(pinBusy_) == HIGH; }

bool Radio::waitBusy() {
    const uint32_t start = micros();
    while (busy()) {
        if (micros() - start > BUSY_TIMEOUT_US) {
            ++busyTimeouts_;
            return false;
        }
        delayMicroseconds(10);
    }
    return true;
}

void Radio::select() {
#if defined(WICI_RADIO_LOCK_CHECK)
    // Każda transakcja z układem, gdy pracuje zadanie odbioru, idzie pod blokadą operacji radia (plan L6).
    if (!platform::radioLockOk()) lockMisses_.fetch_add(1, std::memory_order_relaxed);
#endif
    spi_.beginTransaction(settings_);
    digitalWrite(pinCs_, LOW);
}

void Radio::deselect() {
    digitalWrite(pinCs_, HIGH);
    spi_.endTransaction();
}

bool Radio::command(uint8_t op, const uint8_t* params, size_t count) {
    if (!waitBusy()) return false;
    select();
    status_.raw = spi_.transfer(op);
    for (size_t i = 0; i < count; ++i) spi_.transfer(params[i]);
    deselect();
    return true;
}

bool Radio::read(uint8_t op, uint8_t* data, size_t count) {
    if (!waitBusy()) return false;
    select();
    spi_.transfer(op);
    status_.raw = spi_.transfer(0x00);
    for (size_t i = 0; i < count; ++i) data[i] = spi_.transfer(0x00);
    deselect();
    return true;
}

bool Radio::writeRegs(uint16_t address, const uint8_t* data, size_t count) {
    if (!waitBusy()) return false;
    select();
    status_.raw = spi_.transfer(OP_WRITE_REGISTER);
    spi_.transfer(static_cast<uint8_t>(address >> 8));
    spi_.transfer(static_cast<uint8_t>(address));
    for (size_t i = 0; i < count; ++i) spi_.transfer(data[i]);
    deselect();
    return true;
}

bool Radio::readRegs(uint16_t address, uint8_t* data, size_t count) {
    if (!waitBusy()) return false;
    select();
    spi_.transfer(OP_READ_REGISTER);
    spi_.transfer(static_cast<uint8_t>(address >> 8));
    spi_.transfer(static_cast<uint8_t>(address));
    status_.raw = spi_.transfer(0x00);
    for (size_t i = 0; i < count; ++i) data[i] = spi_.transfer(0x00);
    deselect();
    return true;
}

uint8_t Radio::readReg(uint16_t address) {
    uint8_t value = 0;
    readRegs(address, &value, 1);
    return value;
}

bool Radio::writeBuffer(uint8_t offset, const uint8_t* data, size_t count) {
    if (!waitBusy()) return false;
    select();
    status_.raw = spi_.transfer(OP_WRITE_BUFFER);
    spi_.transfer(offset);
    for (size_t i = 0; i < count; ++i) spi_.transfer(data[i]);
    deselect();
    return true;
}

bool Radio::readBuffer(uint8_t offset, uint8_t* data, size_t count) {
    if (!waitBusy()) return false;
    select();
    spi_.transfer(OP_READ_BUFFER);
    spi_.transfer(offset);
    status_.raw = spi_.transfer(0x00);
    for (size_t i = 0; i < count; ++i) data[i] = spi_.transfer(0x00);
    deselect();
    return true;
}

Status Radio::status() {
    if (!waitBusy()) return Status{};
    select();
    spi_.transfer(OP_GET_STATUS);
    status_.raw = spi_.transfer(0x00);
    deselect();
    return status_;
}

Identity Radio::identify() {
    Identity id{};
    uint8_t raw[VERSION_BYTES] = {};
    readRegs(REG_VERSION, raw, VERSION_BYTES);
    for (size_t i = 0; i < VERSION_BYTES; ++i) {
        const uint8_t c = raw[i];
        id.version[i] = c == 0 ? '\0' : (c >= 0x20 && c < 0x7F && c != '"' && c != '\\') ? static_cast<char>(c) : '.';
    }
    id.version[VERSION_BYTES] = '\0';
    id.sx126x = !strncmp(id.version, "SX126", 5);
    return id;
}

bool Radio::readIrq(uint16_t& irq) {
    uint8_t data[2] = {};
    const bool ok = read(OP_GET_IRQ_STATUS, data, 2);
    irq = static_cast<uint16_t>((data[0] << 8) | data[1]);
    return ok;
}

uint16_t Radio::irqStatus() {
    uint16_t irq = 0;
    readIrq(irq);
    return irq;
}

bool Radio::clearIrq(uint16_t mask) {
    const uint8_t params[2] = {static_cast<uint8_t>(mask >> 8), static_cast<uint8_t>(mask)};
    return command(OP_CLEAR_IRQ_STATUS, params, 2);
}

uint16_t Radio::deviceErrors() {
    uint8_t data[2] = {};
    if (!read(OP_GET_DEVICE_ERRORS, data, 2)) return 0xFFFF;
    return static_cast<uint16_t>((data[0] << 8) | data[1]);
}

void Radio::sleepWarm() {
    const uint8_t config = 0x04;  // ciepły start: konfiguracja zachowana (rozdz. 13.1.1)
    command(OP_SET_SLEEP, &config, 1);
    delayMicroseconds(500);       // karta: 500 µs przed następnym zboczem NSS
}

bool Radio::wake() {
    // Zbocze opadające NSS budzi układ; transakcja dopiero po zejściu BUSY.
    select();
    delayMicroseconds(100);
    deselect();
    delay(1);
    return waitBusy();
}

}  // namespace sx1262
