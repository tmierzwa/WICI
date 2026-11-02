// SPDX-License-Identifier: MIT
// Minimal Adafruit nRF52 core variant for the RAK4631 WisBlock core (nRF52840 + SX1262), used only by the
// lora-raw tool. Arduino pin n is GPIO n (P0.x = x, P1.x = 32 + x), as in the RAK and Meshtastic variants.
// Default SPI is the SX1262 bus inside the RAK4630 module (P1.11 SCK, P1.12 MOSI, P1.13 MISO), like
// meshtastic/firmware variants/nrf52840/rak4631/variant.h. Nothing else of the WisBlock base is used.
#pragma once

#define VARIANT_MCK (64000000ul)
#define USE_LFXO  // RAK4630 has a 32.768 kHz crystal

#include "WVariant.h"

#ifdef __cplusplus
extern "C" {
#endif

#define PINS_COUNT (48)
#define NUM_DIGITAL_PINS (48)
#define NUM_ANALOG_INPUTS (6)
#define NUM_ANALOG_OUTPUTS (0)

// WisBlock LEDs: green P1.03, blue P1.04, active high.
#define PIN_LED1 (35)
#define PIN_LED2 (36)
#define LED_BUILTIN PIN_LED1
#define LED_GREEN PIN_LED1
#define LED_BLUE PIN_LED2
#define LED_STATE_ON 1

#define PIN_A0 (5)
#define PIN_A1 (31)
#define PIN_A2 (28)
#define PIN_A3 (29)
#define PIN_A4 (4)
#define PIN_A5 (2)
static const uint8_t A0 = PIN_A0;
static const uint8_t A1 = PIN_A1;
static const uint8_t A2 = PIN_A2;
static const uint8_t A3 = PIN_A3;
static const uint8_t A4 = PIN_A4;
static const uint8_t A5 = PIN_A5;
#define ADC_RESOLUTION 14

#define PIN_SERIAL1_RX (15)
#define PIN_SERIAL1_TX (16)

#define SPI_INTERFACES_COUNT 1
#define PIN_SPI_MISO (45)
#define PIN_SPI_MOSI (44)
#define PIN_SPI_SCK (43)
static const uint8_t SS = 42;
static const uint8_t MOSI = PIN_SPI_MOSI;
static const uint8_t MISO = PIN_SPI_MISO;
static const uint8_t SCK = PIN_SPI_SCK;

#define WIRE_INTERFACES_COUNT 1
#define PIN_WIRE_SDA (13)
#define PIN_WIRE_SCL (14)

#ifdef __cplusplus
}
#endif
