// SPDX-License-Identifier: MIT
#include "s2lp.h"

namespace s2lp {

const char* stateName(uint8_t state) {
    switch (state) {
        case STATE_READY: return "READY";
        case STATE_SLEEP_A: return "SLEEP_A";
        case STATE_STANDBY: return "STANDBY";
        case STATE_SLEEP_B: return "SLEEP_B";
        case STATE_LOCK: return "LOCK";
        case STATE_RX: return "RX";
        case STATE_SYNTH_SETUP: return "SYNTH_SETUP";
        case STATE_TX: return "TX";
        default: return "INVALID";
    }
}

const char* versionName(uint8_t version) {
    // Wersje krzemu według biblioteki ST (S2LP_Types.h, S2LPCutType); karta DS11896 Rev 5 podaje
    // wartość domyślną 0x91.
    switch (version) {
        case 0x81: return "2.0";
        case 0x91: return "2.1";
        case 0xC1: return "3.0";
        default: return "unknown";
    }
}

Radio::Radio(SPIClass& spi, uint8_t pinCs, uint8_t pinSdn, uint32_t spiHz)
    : spi_(spi), pinCs_(pinCs), pinSdn_(pinSdn), settings_(spiHz, MSBFIRST, SPI_MODE0) {}

void Radio::begin() {
    pinMode(pinCs_, OUTPUT);
    digitalWrite(pinCs_, HIGH);
    pinMode(pinSdn_, OUTPUT);
    digitalWrite(pinSdn_, LOW);
    shutdown_ = false;
}

void Radio::shutdown(bool on) {
    digitalWrite(pinSdn_, on ? HIGH : LOW);
    if (!on && shutdown_) delayMicroseconds(SHUTDOWN_TO_READY_US + 100);
    shutdown_ = on;
}

void Radio::reset() {
    shutdown(true);
    delay(1);
    shutdown(false);
    command(CMD_SRES);
    delayMicroseconds(SHUTDOWN_TO_READY_US);
}

void Radio::begin(uint8_t header, uint8_t second) {
    spi_.beginTransaction(settings_);
    digitalWrite(pinCs_, LOW);
    status_.mcState1 = spi_.transfer(header);
    status_.mcState0 = spi_.transfer(second);
}

void Radio::end() {
    digitalWrite(pinCs_, HIGH);
    spi_.endTransaction();
}

uint8_t Radio::readReg(uint8_t address) {
    uint8_t value = 0;
    readRegs(address, &value, 1);
    return value;
}

void Radio::readRegs(uint8_t address, uint8_t* data, size_t count) {
    begin(HEADER_READ, address);
    for (size_t i = 0; i < count; ++i) data[i] = spi_.transfer(0x00);
    end();
}

void Radio::writeReg(uint8_t address, uint8_t value) { writeRegs(address, &value, 1); }

void Radio::writeRegs(uint8_t address, const uint8_t* data, size_t count) {
    begin(HEADER_WRITE, address);
    for (size_t i = 0; i < count; ++i) spi_.transfer(data[i]);
    end();
}

void Radio::command(uint8_t code) {
    begin(HEADER_COMMAND, code);
    end();
}

Status Radio::status() {
    uint8_t bytes[2] = {};
    readRegs(MC_STATE1, bytes, 2);
    Status s{bytes[0], bytes[1]};
    return s;
}

Identity Radio::identify() {
    Identity id{};
    uint8_t bytes[2] = {};
    readRegs(DEVICE_INFO1, bytes, 2);  // PARTNUM, VERSION (kolejne adresy)
    id.status = status_;
    id.partNumber = bytes[0];
    id.version = bytes[1];
    id.s2lp = id.partNumber == PARTNUM_S2LP;
    return id;
}

uint32_t Radio::readIrqStatus() {
    uint8_t bytes[4] = {};
    readRegs(IRQ_STATUS3, bytes, 4);
    return (static_cast<uint32_t>(bytes[0]) << 24) | (static_cast<uint32_t>(bytes[1]) << 16) |
           (static_cast<uint32_t>(bytes[2]) << 8) | bytes[3];
}

bool Radio::commandAndWait(uint8_t code, uint8_t state, uint32_t timeoutUs) {
    command(code);
    return waitState(state, timeoutUs);
}

bool Radio::waitState(uint8_t state, uint32_t timeoutUs) {
    const uint32_t start = micros();
    do {
        if (status().state() == state) return true;
    } while (micros() - start < timeoutUs);
    return false;
}

VerifyResult Radio::verify(const RegisterValue* table, size_t count) {
    VerifyResult result{};
    for (size_t i = 0; i < count; ++i) {
        const RegisterValue& r = table[i];
        const uint8_t actual = readReg(r.address);
        ++result.checked;
        if ((actual & r.verifyMask) != (r.value & r.verifyMask)) {
            if (result.mismatches++ == 0) {
                result.firstAddress = r.address;
                result.expected = r.value;
                result.actual = actual;
                result.firstName = r.name;
            }
        }
    }
    return result;
}

VerifyResult Radio::configure(const RegisterValue* table, size_t count) {
    // Rejestry konfiguracji zapisuje się w READY (z RX/TX najpierw SABORT).
    const uint8_t state = status().state();
    if (state == STATE_RX || state == STATE_TX) commandAndWait(CMD_SABORT, STATE_READY, 1000);
    else if (state != STATE_READY) commandAndWait(CMD_READY, STATE_READY, 1000);
    for (size_t i = 0; i < count; ++i) writeReg(table[i].address, table[i].value);
    return verify(table, count);
}

}  // namespace s2lp
