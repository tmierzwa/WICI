// SPDX-License-Identifier: MIT
// Bench station on the Seeed kit 102010611: XIAO ESP32-S3 (ESP32-S3R8, 8 MB flash, 8 MB octal PSRAM)
// with the Wio-SX1262 board on its B2B connector (SX1262, TCXO 1.8 V from DIO3, RF switch: DIO2 for
// transmit, RF_SW1 for receive). Pins as in hardware/radio-pair (src/main.cpp, ZRODLA-I-WERYFIKACJA.txt:
// Seeed wiki of the kit and the upstream Meshtastic variant seeed_xiao_s3), where both kits passed 100/100
// exchanges and the WICI-Link raw frame check (evidence/). GPIO numbers of the ESP32-S3.
// The kit has no FRAM, display, panel, buzzer or VTEST: WICI_HEADLESS drops the display and the button
// wizard (the screen model stays: SCREEN, KEY and REQ stand in for them), WICI_FRAM_PSRAM keeps the FRAM image
// in PSRAM (fram_ram.h). Octal PSRAM takes GPIO33-37; the radio uses none of them.
#pragma once

#include <Arduino.h>

#define WICI_HEADLESS 1    // no display and no wizard buttons (main.cpp)
#define WICI_FRAM_PSRAM 1  // FRAM emulated in PSRAM, lost on power-off (fram_ram.h)

namespace board {

constexpr const char* NAME = "XIAO";

// SPI on the FSPI controller through the GPIO matrix; short traces to the Wio board.
constexpr uint8_t SPI_SCK = 7;    // D8
constexpr uint8_t SPI_MISO = 8;   // D9
constexpr uint8_t SPI_MOSI = 9;   // D10
constexpr uint8_t SPI_DRIVE = 2;  // gpio_drive_cap_t: ESP-IDF default (about 20 mA)

// SX1262 on the Wio-SX1262 (B2B connector).
constexpr uint8_t RADIO_CS = 41;     // NSS, active low
constexpr uint8_t RADIO_RESET = 42;  // NRESET
constexpr uint8_t RADIO_BUSY = 40;   // BUSY
constexpr uint8_t RADIO_DIO1 = 39;   // DIO1 (state shown by RADIO; the driver reads interrupts over SPI)
constexpr uint8_t RADIO_RXEN = 38;   // RF_SW1: high only while receiving (rnode-xiao-rf-sw1.patch, evidence 2026-10-31)

// Buttons: only BOOT (GPIO0, to ground, pull-up) as OK: it confirms PREP 1 and CONDUCTED like the OK
// button of the other boards. The other buttons are absent; the console KEY command replaces them.
constexpr int16_t BTN_UP = -1;
constexpr int16_t BTN_DOWN = -1;
constexpr uint8_t BTN_OK = 0;
constexpr int16_t BTN_BACK = -1;

// User LED (yellow, GPIO21, active low like the DK LEDs): heartbeat and the blinking while PREP 1 waits
// for BOOT.
constexpr int16_t LED_HEARTBEAT = 21;
constexpr int16_t LED_RADIO = -1;
constexpr int16_t LED_FRAM = -1;
constexpr int16_t LED_USB = -1;

constexpr uint32_t SPI_HZ = 1000000;  // radio, as on L0

}  // namespace board
