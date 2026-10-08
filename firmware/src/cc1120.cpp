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

const char* marcStateName(uint8_t state) {
    // SWRU295E, rejestr MARCSTATE, bity 4:0.
    static const char* const names[] = {
        "SLEEP", "IDLE", "XOFF", "BIAS_SETTLE_MC", "REG_SETTLE_MC", "MANCAL", "BIAS_SETTLE", "REG_SETTLE",
        "STARTCAL", "BWBOOST", "FS_LOCK", "IFADCON", "ENDCAL", "RX", "RX_END", "RESERVED",
        "TXRX_SWITCH", "RX_FIFO_ERR", "FSTXON", "TX", "TX_END", "RXTX_SWITCH", "TX_FIFO_ERR", "IFADCON_TXRX",
    };
    return state < sizeof(names) / sizeof(names[0]) ? names[state] : "?";
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

VerifyResult Radio::verify(const RegisterValue* table, size_t count) {
    VerifyResult result{};
    for (size_t i = 0; i < count; ++i) {
        const uint8_t actual = readReg(table[i].address);
        ++result.checked;
        if ((actual & table[i].verifyMask) != (table[i].value & table[i].verifyMask)) {
            if (result.mismatches == 0) {
                result.firstName = table[i].name;
                result.firstAddress = table[i].address;
                result.expected = table[i].value;
                result.actual = actual;
            }
            ++result.mismatches;
        }
    }
    return result;
}

VerifyResult Radio::configure(const RegisterValue* table, size_t count) {
    idle();
    for (size_t i = 0; i < count; ++i) {
        writeReg(table[i].address, table[i].value);
    }
    return verify(table, count);
}

bool Radio::waitMarcState(uint8_t state, uint32_t timeoutMs) {
    const uint32_t start = millis();
    do {
        if (readMarcState() == state) {
            return true;
        }
        delayMicroseconds(200);
    } while (millis() - start < timeoutMs);
    return false;
}

bool Radio::idle(uint32_t timeoutMs) {
    strobe(SIDLE);
    return waitMarcState(MARC_STATE_IDLE, timeoutMs);
}

bool Radio::calibrate(uint32_t timeoutMs) {
    // Kolejność kroków jak w manualCalibration() z TI swrc253e (errata CC112x).
    constexpr uint8_t VCDAC_START_OFFSET = 2;
    if (!idle()) {
        return false;
    }
    const uint8_t originalFsCal2 = readReg(FS_CAL2);

    // 1) Pojemności VCO na zero, 2) wyższy VCDAC_START, 3) kalibracja.
    writeReg(FS_VCO2, 0x00);
    writeReg(FS_CAL2, static_cast<uint8_t>(originalFsCal2 + VCDAC_START_OFFSET));
    strobe(SCAL);
    if (!waitMarcState(MARC_STATE_IDLE, timeoutMs)) {
        idle();
        writeReg(FS_CAL2, originalFsCal2);  // FS_CAL2 nie jest w tablicy P1: CONFIG by go nie przywrócił
        return false;
    }
    // 4) Wynik dla wyższego VCDAC_START.
    const uint8_t highVco2 = readReg(FS_VCO2);
    const uint8_t highVco4 = readReg(FS_VCO4);
    const uint8_t highChp = readReg(FS_CHP);

    // 5) Pojemności na zero, 6) pierwotny VCDAC_START, 7) kalibracja.
    writeReg(FS_VCO2, 0x00);
    writeReg(FS_CAL2, originalFsCal2);
    strobe(SCAL);
    if (!waitMarcState(MARC_STATE_IDLE, timeoutMs)) {
        idle();
        return false;
    }
    // 8) Wynik dla pierwotnego VCDAC_START.
    const uint8_t midVco2 = readReg(FS_VCO2);
    const uint8_t midVco4 = readReg(FS_VCO4);
    const uint8_t midChp = readReg(FS_CHP);

    // 9) Zostaje wynik z większym FS_VCO2 wraz z jego FS_VCO4 i FS_CHP.
    if (highVco2 > midVco2) {
        writeReg(FS_VCO2, highVco2);
        writeReg(FS_VCO4, highVco4);
        writeReg(FS_CHP, highChp);
    } else {
        writeReg(FS_VCO2, midVco2);
        writeReg(FS_VCO4, midVco4);
        writeReg(FS_CHP, midChp);
    }
    return true;
}

void Radio::writeFifo(const uint8_t* data, size_t count) {
    select();
    lastStatus_ = spi_.transfer(BURST | FIFO);
    for (size_t i = 0; i < count; ++i) {
        spi_.transfer(data[i]);
    }
    release();
}

void Radio::readFifo(uint8_t* data, size_t count) {
    select();
    lastStatus_ = spi_.transfer(READ | BURST | FIFO);
    for (size_t i = 0; i < count; ++i) {
        data[i] = spi_.transfer(0x00);
    }
    release();
}

uint32_t Radio::frequencyWord() {
    const uint32_t f2 = readReg(FREQ2);
    const uint32_t f1 = readReg(FREQ1);
    const uint32_t f0 = readReg(FREQ0);
    return (f2 << 16) | (f1 << 8) | f0;
}

int16_t Radio::frequencyOffset() {
    const uint16_t raw = (static_cast<uint16_t>(readReg(FREQOFF1)) << 8) | readReg(FREQOFF0);
    return static_cast<int16_t>(raw);
}

void Radio::setFrequencyOffset(int16_t offset) {
    const uint16_t raw = static_cast<uint16_t>(offset);
    writeReg(FREQOFF1, static_cast<uint8_t>(raw >> 8));
    writeReg(FREQOFF0, static_cast<uint8_t>(raw & 0xFF));
}

int16_t Radio::frequencyOffsetEstimate() {
    const uint16_t raw = (static_cast<uint16_t>(readReg(FREQOFF_EST1)) << 8) | readReg(FREQOFF_EST0);
    return static_cast<int16_t>(raw);
}

Rssi Radio::rssi(int8_t offsetDb) {
    Rssi r{};
    const int8_t coarse = static_cast<int8_t>(readReg(RSSI1));  // RSSI[11:4], 1 dB
    const uint8_t fine = readReg(RSSI0);
    r.valid = (fine & RSSI0_VALID) != 0;
    r.carrierSense = (fine & RSSI0_CARRIER_SENSE) != 0;
    r.carrierSenseValid = (fine & RSSI0_CARRIER_SENSE_VALID) != 0;
    r.dbm = static_cast<int16_t>(coarse) + offsetDb;
    return r;
}

}  // namespace cc1120
