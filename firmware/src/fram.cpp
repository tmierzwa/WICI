// SPDX-License-Identifier: MIT
#include "fram.h"

#include <string.h>

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
    delayMicroseconds(1);  // CS w stanie wysokim między poleceniami (MB85RS4MT i CY15B104Q: kilkadziesiąt ns)
    digitalWrite(cs_, LOW);
    spi_.transfer(OP_RDSR);
    id.status = spi_.transfer(0x00);
    release();
    id.part = classify(id.bytes);
    return id;
}

bool Memory::read(uint32_t address, uint8_t* data, size_t count) {
    if (address + count > SIZE) return false;
    select();
    sendAddress(OP_READ, address);
    // Bufor w jednym wywołaniu (DMA SPIM na nRF52840) zamiast osobnej transakcji na każdy bajt.
    memset(data, 0, count);
    spi_.transfer(data, count);
    release();
    return true;
}

bool Memory::write(uint32_t address, const uint8_t* data, size_t count) {
    if (address + count > SIZE) return false;
    select();
    spi_.transfer(OP_WREN);  // WEL kasuje się po każdym zapisie
    digitalWrite(cs_, HIGH);
    delayMicroseconds(1);  // CS w stanie wysokim między poleceniami (MB85RS4MT i CY15B104Q: kilkadziesiąt ns)
    digitalWrite(cs_, LOW);
    sendAddress(OP_WRITE, address);
    uint8_t chunk[64];  // transfer nadpisuje bufor odebranymi bajtami, więc kopia danych
    for (size_t done = 0; done < count; done += sizeof(chunk)) {
        const size_t n = count - done < sizeof(chunk) ? count - done : sizeof(chunk);
        memcpy(chunk, data + done, n);
        spi_.transfer(chunk, n);
    }
    release();
    return true;
}

}  // namespace fram
