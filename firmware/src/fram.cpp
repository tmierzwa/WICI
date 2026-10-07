// SPDX-License-Identifier: MIT
#include "fram.h"

namespace fram {

Memory::Memory(SPIClass& spi, uint8_t cs, uint32_t hz)
    : spi_(spi), cs_(cs), settings_(hz, MSBFIRST, SPI_MODE0) {}

void Memory::begin() {
    pinMode(cs_, OUTPUT);
    digitalWrite(cs_, HIGH);
}

Id Memory::identify() {
    Id id{};
    spi_.beginTransaction(settings_);
    digitalWrite(cs_, LOW);
    spi_.transfer(OP_RDID);
    for (uint8_t& b : id.bytes) {
        b = spi_.transfer(0x00);
    }
    digitalWrite(cs_, HIGH);
    digitalWrite(cs_, LOW);
    spi_.transfer(OP_RDSR);
    id.status = spi_.transfer(0x00);
    digitalWrite(cs_, HIGH);
    spi_.endTransaction();
    id.fujitsu = id.bytes[0] == MANUFACTURER_FUJITSU && id.bytes[1] == 0x7F;
    id.mb85rs4m = id.fujitsu && id.bytes[2] == 0x49 && (id.bytes[3] == 0x03 || id.bytes[3] == 0x0B);
    return id;
}

}  // namespace fram
