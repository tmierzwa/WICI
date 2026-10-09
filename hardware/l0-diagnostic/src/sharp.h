// SPDX-License-Identifier: MIT
// Sharp LS027B7DH01A on N1: 400x240 framebuffer, dirty-line SPI updates.
// N1 ties EXTMODE high. Hardware MCPWM must provide EXTCOMIN (1Hz);
// the caller keeps DISP low if begin() fails. No software VCOM fallback.
#pragma once

#include <Arduino.h>
#include <SPI.h>

#include "font.h"

namespace sharp {

constexpr uint16_t WIDTH = 400;
constexpr uint16_t HEIGHT = 240;
constexpr size_t LINE_BYTES = WIDTH / 8;
constexpr uint32_t SPI_HZ = 2000000;  // LS027B7DH01: do 2 MHz; domyślny zegar
constexpr uint8_t COLUMNS = WIDTH / font::WIDTH;        // 20 znaków
constexpr uint8_t ROWS = HEIGHT / font::LINE_PITCH;     // 5 wierszy
// Polecenia w kolejności bitów LSB-first, jak idą na magistralę (M0 pierwszy).
constexpr uint8_t CMD_WRITE = 0x01;
constexpr uint8_t CMD_CLEAR = 0x04;

class Display {
public:
    Display(SPIClass& spi, uint8_t pinCs, uint8_t pinExtcomin, uint32_t spiHz = SPI_HZ);

    // CS w stan niski, bufor biały, polecenie CLEAR, EXTCOMIN z licznika MCU. Zwraca false, gdy
    // licznik EXTCOMIN nie ruszył: wtedy nie wolno włączać panelu przy EXTMODE w stanie wysokim.
    bool begin();
    void clear();
    // Wiersz tekstu UTF-8 (20 komórek, dopełniany spacjami); inverse = białe litery na czarnym.
    void drawLine(uint8_t row, const char* utf8, bool inverse);
    void setPixel(uint16_t x, uint16_t y, bool black);
    // Wysyła zmienione wiersze; zwraca ich liczbę.
    uint16_t refresh();
    uint32_t extcominCounter() const;  // Hardware timer counter, not an LCD-pin measurement.

private:
    bool beginExtcomin();
    void drawGlyph(uint16_t x, uint16_t y, const font::Glyph& glyph, bool inverse);
    void transaction(uint8_t command, bool lines);
    void send(uint8_t byte);

    SPIClass& spi_;
    uint8_t pinCs_;
    uint8_t pinExtcomin_;
    uint32_t spiHz_;
    uint8_t buffer_[HEIGHT][LINE_BYTES];  // bit 0 bajtu 0 = lewy piksel; 1 = biały
    uint8_t dirty_[HEIGHT / 8];
    bool extcominOk_ = false;
};

}  // namespace sharp
