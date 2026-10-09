// SPDX-License-Identifier: MIT
#pragma once
#include <stdint.h>

namespace board {
constexpr uint8_t SPI_SCK = 12;
constexpr uint8_t SPI_MOSI = 11;
constexpr uint8_t SPI_MISO = 13;

constexpr uint8_t RADIO_NSS = 10;
constexpr uint8_t RADIO_NRST = 9;
constexpr uint8_t RADIO_BUSY = 14;
constexpr uint8_t RADIO_DIO1 = 21;
constexpr uint8_t RADIO_RXEN = 42;

constexpr uint8_t FRAM_CS = 8;
constexpr uint8_t LCD_CS = 7;
constexpr uint8_t LCD_EXTCOMIN = 17;
constexpr uint8_t LCD_DISP = 16;
constexpr uint8_t LED_ALARM = 18;
constexpr uint8_t BUZZER = 15;

constexpr uint8_t BTN_UP = 41;
constexpr uint8_t BTN_DOWN = 40;
constexpr uint8_t BTN_OK = 39;
constexpr uint8_t BTN_BACK = 2;
constexpr uint8_t SW_CISZA = 1;
constexpr uint8_t BTN_PREP = 6;
}  // namespace board
