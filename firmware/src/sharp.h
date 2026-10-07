// SPDX-License-Identifier: MIT
// Ekran Sharp LS027B7DH01 (Adafruit 4694, 400 x 240) na magistrali SPI: bufor obrazu w RAM,
// zapis wierszy zmienionych, rysowanie znaków z font_glyphs.h. EXTCOMIN (inwersja VCOM,
// 1 Hz) generuje licznik RTC2 przez PPI i GPIOTE bez udziału programu (specyfikacja:
// "EXTCOMIN z wyjścia licznika MCU, nie z programu"); zapasowo bit VCOM w poleceniach,
// gdy zworka EXTMODE płytki jest w położeniu niskim.
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
constexpr uint8_t CMD_VCOM = 0x02;
constexpr uint8_t CMD_CLEAR = 0x04;
constexpr uint32_t EXTCOMIN_HALF_PERIOD_MS = 500;  // przebieg 1 Hz
constexpr uint8_t PPI_CHANNEL = 0;      // SoftDevice S140 zajmuje kanały 17-31
constexpr uint8_t GPIOTE_CHANNEL = 7;   // attachInterrupt rdzenia pomija kanały włączone

class Display {
public:
    Display(SPIClass& spi, uint8_t pinCs, uint8_t pinExtcomin, uint32_t spiHz = SPI_HZ);

    // CS w stan niski, bufor biały, polecenie CLEAR, EXTCOMIN z RTC2.
    void begin();
    void clear();
    // Wiersz tekstu UTF-8 (20 komórek, dopełniany spacjami); inverse = białe litery na czarnym.
    void drawLine(uint8_t row, const char* utf8, bool inverse);
    void drawGlyph(uint16_t x, uint16_t y, const font::Glyph& glyph, bool inverse);
    void setPixel(uint16_t x, uint16_t y, bool black);
    // Wysyła zmienione wiersze; zwraca ich liczbę.
    uint16_t refresh();
    // Zapasowe odwracanie VCOM z programu (EXTMODE niski): bit VCOM w poleceniu co 500 ms.
    void softwareVcom(bool on);
    bool softwareVcom() const { return softwareVcom_; }
    void maintain(uint32_t nowMs);
    uint32_t refreshes() const { return refreshes_; }
    void spiHz(uint32_t hz) { spiHz_ = hz; }
    uint32_t spiHz() const { return spiHz_; }
    uint32_t extcominCounter() const;  // licznik RTC2 (0..4), do diagnostyki
    bool extcominLevel() const;        // stan pinu EXTCOMIN

private:
    void beginExtcomin();
    void transaction(uint8_t command, bool allLines);
    void send(uint8_t byte);

    SPIClass& spi_;
    uint8_t pinCs_;
    uint8_t pinExtcomin_;
    uint32_t spiHz_;
    uint8_t buffer_[HEIGHT][LINE_BYTES];  // bit 0 bajtu 0 = lewy piksel; 1 = biały
    uint8_t dirty_[HEIGHT / 8];
    bool softwareVcom_ = false;
    uint8_t vcom_ = 0;
    uint32_t lastVcomMs_ = 0;
    uint32_t refreshes_ = 0;
};

}  // namespace sharp
