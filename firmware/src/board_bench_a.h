// SPDX-License-Identifier: MIT
// Stanowisko deweloperskie A: nRF52840-DK (wariant pca10056 rdzenia Adafruit)
// z modułem TI CC1120EM-868-915, FRAM MB85RS4MT i ekranem Sharp (Adafruit 4694) na złączu
// Arduino płytki.
// Numery pinów to numery GPIO nRF52840 w rdzeniu Adafruit: P0.xx = xx, P1.xx = 32 + xx.
#pragma once

#include <Arduino.h>

namespace board {

// SPI0 płytki (złącze Arduino: D13/D11/D12). Wspólne dla radia, FRAM i ekranu.
constexpr uint8_t SPI_SCK = PIN_SPI_SCK;    // P1.15, D13 -> EM P1.16
constexpr uint8_t SPI_MOSI = PIN_SPI_MOSI;  // P1.13, D11 -> EM P1.18
constexpr uint8_t SPI_MISO = PIN_SPI_MISO;  // P1.14, D12 -> EM P1.20

// Moduł radiowy CC1120EM (numery złączy EM według hardware/dev-bench/README.md).
constexpr uint8_t RADIO_CS = 32 + 12;     // P1.12, D10 -> EM P1.14 (CSn)
constexpr uint8_t RADIO_RESET = 32 + 10;  // P1.10, D8  -> EM P2.15 (RESET_N)
constexpr uint8_t RADIO_GPIO0 = 32 + 3;   // P1.03, D2  -> EM P1.10 (GPIO0)
constexpr uint8_t RADIO_GPIO2 = 32 + 4;   // P1.04, D3  -> EM P1.12 (GPIO2)

// FRAM MB85RS4MT (Adafruit 4719) albo CY15B104Q na tej samej magistrali SPI.
constexpr uint8_t FRAM_CS = 32 + 11;  // P1.11, D9

// Ekran Sharp LS027B7DH01 (Adafruit 4694): CS aktywny stanem wysokim, EXTCOMIN z licznika RTC2.
constexpr uint8_t DISPLAY_CS = 32 + 5;        // P1.05, D4
constexpr uint8_t DISPLAY_EXTCOMIN = 32 + 6;  // P1.06, D5

// Przyciski płytki DK (aktywne stanem niskim) w roli przycisków stacji.
constexpr uint8_t BTN_UP = PIN_BUTTON1;     // P0.11
constexpr uint8_t BTN_DOWN = PIN_BUTTON2;   // P0.12
constexpr uint8_t BTN_OK = PIN_BUTTON3;     // P0.24
constexpr uint8_t BTN_BACK = PIN_BUTTON4;   // P0.25

// Diody płytki DK (aktywne stanem niskim).
constexpr uint8_t LED_HEARTBEAT = PIN_LED1;  // P0.13
constexpr uint8_t LED_RADIO = PIN_LED2;      // P0.14
constexpr uint8_t LED_FRAM = PIN_LED3;       // P0.15
constexpr uint8_t LED_USB = PIN_LED4;        // P0.16

constexpr uint32_t SPI_HZ = 1000000;  // pierwsza próba 1 MHz, jak w lekcjach R02
// FRAM na przewodach zostaje przy 1 MHz: ten wariant nie spełnia wymagania ≥8 MHz stacji
// i nie służy do prób zaniku zasilania; spełniają je płytka N1 (bench-n1, bench-b).
constexpr uint32_t FRAM_SPI_HZ = SPI_HZ;

}  // namespace board
