// SPDX-License-Identifier: MIT
#include "sharp.h"

#include <string.h>

namespace sharp {

Display::Display(SPIClass& spi, uint8_t pinCs, uint8_t pinExtcomin, uint32_t spiHz)
    : spi_(spi), pinCs_(pinCs), pinExtcomin_(pinExtcomin), spiHz_(spiHz) {
    memset(buffer_, 0xFF, sizeof(buffer_));
    memset(dirty_, 0xFF, sizeof(dirty_));
}

void Display::begin() {
    pinMode(pinCs_, OUTPUT);
    digitalWrite(pinCs_, LOW);  // CS aktywny stanem wysokim
    beginExtcomin();
    clear();
}

void Display::send(uint8_t byte) { spi_.transfer(byte); }

void Display::transaction(uint8_t command, bool lines) {
    spi_.beginTransaction(SPISettings(spiHz_, LSBFIRST, SPI_MODE0));
    digitalWrite(pinCs_, HIGH);
    delayMicroseconds(3);  // tsSCS >= 3 us
    send(command | vcom_);
    if (lines) {
        for (uint16_t y = 0; y < HEIGHT; ++y) {
            if (!(dirty_[y / 8] & (1u << (y % 8)))) continue;
            send(static_cast<uint8_t>(y + 1));  // adres wiersza 1..240, bit AG0 pierwszy
            for (size_t i = 0; i < LINE_BYTES; ++i) send(buffer_[y][i]);
            send(0x00);  // 8 bitów odstępu po wierszu
        }
        memset(dirty_, 0, sizeof(dirty_));
    }
    send(0x00);  // 16 bitów na końcu transmisji (razem z odstępem ostatniego wiersza)
    delayMicroseconds(1);  // thSCS >= 1 us
    digitalWrite(pinCs_, LOW);
    delayMicroseconds(1);  // twSCSL >= 1 us
    spi_.endTransaction();
}

void Display::clear() {
    memset(buffer_, 0xFF, sizeof(buffer_));
    memset(dirty_, 0, sizeof(dirty_));
    transaction(CMD_CLEAR, false);
}

uint16_t Display::refresh() {
    uint16_t count = 0;
    for (uint16_t y = 0; y < HEIGHT; ++y) count += (dirty_[y / 8] >> (y % 8)) & 1u;
    if (count == 0) return 0;
    transaction(CMD_WRITE, true);
    ++refreshes_;
    return count;
}

void Display::softwareVcom(bool on) {
    softwareVcom_ = on;
    if (!on) vcom_ = 0;
}

void Display::maintain(uint32_t nowMs) {
    if (!softwareVcom_ || nowMs - lastVcomMs_ < EXTCOMIN_HALF_PERIOD_MS) return;
    lastVcomMs_ = nowMs;
    vcom_ ^= CMD_VCOM;
    transaction(0x00, false);  // polecenie podtrzymania z nowym stanem VCOM
}

void Display::setPixel(uint16_t x, uint16_t y, bool black) {
    if (x >= WIDTH || y >= HEIGHT) return;
    uint8_t& byte = buffer_[y][x / 8];
    const uint8_t mask = static_cast<uint8_t>(1u << (x % 8));
    const uint8_t next = black ? static_cast<uint8_t>(byte & ~mask) : static_cast<uint8_t>(byte | mask);
    if (next != byte) {
        byte = next;
        dirty_[y / 8] |= static_cast<uint8_t>(1u << (y % 8));
    }
}

void Display::drawGlyph(uint16_t x, uint16_t y, const font::Glyph& glyph, bool inverse) {
    for (uint8_t gy = 0; gy < font::HEIGHT; ++gy) {
        const uint8_t* row = glyph.rows + gy * font::ROW_BYTES;
        for (uint8_t gx = 0; gx < font::WIDTH; ++gx) {
            const bool ink = (row[gx / 8] >> (7 - gx % 8)) & 1u;
            setPixel(x + gx, y + gy, ink != inverse);
        }
    }
}

void Display::drawLine(uint8_t row, const char* utf8, bool inverse) {
    if (row >= ROWS) return;
    const uint16_t top = static_cast<uint16_t>(row * font::LINE_PITCH);
    // Tło całego pasa wiersza (również marginesy nad i pod znakami).
    for (uint16_t y = top; y < top + font::LINE_PITCH; ++y) {
        for (uint16_t x = 0; x < WIDTH; ++x) setPixel(x, y, inverse);
    }
    const uint16_t baseline = top + (font::LINE_PITCH - font::HEIGHT) / 2;
    const char* p = utf8;
    for (uint8_t col = 0; col < COLUMNS; ++col) {
        const uint32_t codepoint = font::next(p);
        if (codepoint == 0) break;
        drawGlyph(static_cast<uint16_t>(col * font::WIDTH), baseline, font::glyph(codepoint), inverse);
    }
}

}  // namespace sharp
