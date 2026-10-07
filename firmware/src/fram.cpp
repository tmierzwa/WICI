// SPDX-License-Identifier: MIT
#include "fram.h"

namespace fram {

Memory::Memory(SPIClass& spi, uint8_t cs, uint32_t hz)
    : spi_(spi), cs_(cs), settings_(hz, MSBFIRST, SPI_MODE0) {}

void Memory::begin() {
    pinMode(cs_, OUTPUT);
    digitalWrite(cs_, HIGH);
}

void Memory::select() {
    spi_.beginTransaction(settings_);
    digitalWrite(cs_, LOW);
}

void Memory::release() {
    digitalWrite(cs_, HIGH);
    spi_.endTransaction();
}

void Memory::sendAddress(uint8_t opcode, uint32_t address) {
    spi_.transfer(opcode);
    spi_.transfer(static_cast<uint8_t>((address >> 16) & 0x07));
    spi_.transfer(static_cast<uint8_t>((address >> 8) & 0xFF));
    spi_.transfer(static_cast<uint8_t>(address & 0xFF));
}

Id Memory::identify() {
    Id id{};
    select();
    spi_.transfer(OP_RDID);
    for (uint8_t& b : id.bytes) {
        b = spi_.transfer(0x00);
    }
    digitalWrite(cs_, HIGH);
    delayMicroseconds(1);  // CS w stanie wysokim między poleceniami (tCSH MB85RS4MT)
    digitalWrite(cs_, LOW);
    spi_.transfer(OP_RDSR);
    id.status = spi_.transfer(0x00);
    release();
    id.fujitsu = id.bytes[0] == MANUFACTURER_FUJITSU && id.bytes[1] == 0x7F;
    id.mb85rs4m = id.fujitsu && id.bytes[2] == 0x49 && (id.bytes[3] == 0x03 || id.bytes[3] == 0x0B);
    return id;
}

bool Memory::read(uint32_t address, uint8_t* data, size_t count) {
    if (address + count > SIZE) return false;
    select();
    sendAddress(OP_READ, address);
    for (size_t i = 0; i < count; ++i) {
        data[i] = spi_.transfer(0x00);
    }
    release();
    return true;
}

bool Memory::write(uint32_t address, const uint8_t* data, size_t count) {
    if (address + count > SIZE) return false;
    select();
    spi_.transfer(OP_WREN);  // WEL kasuje się po każdym zapisie
    digitalWrite(cs_, HIGH);
    delayMicroseconds(1);  // CS w stanie wysokim między poleceniami (tCSH MB85RS4MT)
    digitalWrite(cs_, LOW);
    sendAddress(OP_WRITE, address);
    for (size_t i = 0; i < count; ++i) {
        spi_.transfer(data[i]);
    }
    release();
    return true;
}

}  // namespace fram
