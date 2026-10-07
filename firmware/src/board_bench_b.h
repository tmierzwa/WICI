// SPDX-License-Identifier: MIT
// Stanowisko deweloperskie B na płytce nośnej N1 (hardware/dev-bench/plytka-nosna.md):
// ESP32-S3-DevKitC-1 (moduł N8, N8R2 albo N8R8, flash quad SPI) w J5/J6 z X-NUCLEO-S2868A2 (ST S2-LP,
// kwarc 50 MHz) w J1-J4, FRAM MB85RS4MT, ekranem Sharp (Adafruit 4694) i panelem płytki
// (przyciski, CISZA, przycisk przygotowania, dioda alarmu, brzęczyk, VTEST).
// Przypisanie według kolumny ESP32-S3 tabeli "Przypisanie sygnałów" i
// hardware/dev-bench/polaczenia.md (złącza J5/J6 = J1/J3 DevKitC); zgodność pin po pinie:
// hardware/dev-bench/checks/zgodnosc-firmware.md.
// Numery pinów to numery GPIO ESP32-S3. Płytka omija piny konfiguracyjne (GPIO0, 3, 45, 46),
// USB (19, 20), UART0 (43, 44), diodę RGB, PSRAM ośmiobitową (35-37) i piny 1,8 V (47, 48).
#pragma once

#include <Arduino.h>

#define WICI_BOARD_N1 1  // płytka nośna N1: panel i linia DISP ekranu (board.h)

namespace board {

constexpr const char* NAME = "N1";

// SPI: piny IO_MUX FSPI (FSPID 11, FSPICLK 12, FSPIQ 13) na kontrolerze SPI2 (FSPI).
// SCK przez 33 Ω (R18) przy GPIO12; sieć SCK ma około 240 mm z odgałęzieniami, więc SCK i MOSI
// startują z najniższym napędem (DRIVE_CAP 0, około 5 mA); polecenie DRIVE zmienia go do restartu.
constexpr uint8_t SPI_SCK = 12;   // J5.18 -> R18 -> S2-LP SCLK, FRAM, ekran, J11
constexpr uint8_t SPI_MOSI = 11;  // J5.17 -> S2-LP SDI, FRAM, ekran
constexpr uint8_t SPI_MISO = 13;  // J5.19 -> S2-LP SDO, FRAM
constexpr uint8_t SPI_DRIVE = 0;  // gpio_drive_cap_t: 0 = najsłabszy

// S2-LP na X-NUCLEO-S2868A2 (kwarc 50 MHz na module).
constexpr uint8_t RADIO_CS = 10;     // J5.16 -> CSn (R13), 10 kΩ do 3,3 V
constexpr uint8_t RADIO_SDN = 9;     // J5.15 -> SDN: stan wysoki wyłącza układ; 10 kΩ do masy
constexpr uint8_t RADIO_GPIO0 = 14;  // J5.20 -> GPIO0 (R12), J11
constexpr uint8_t RADIO_GPIO1 = 21;  // J6.18 -> GPIO1
constexpr uint8_t RADIO_GPIO2 = 4;   // J5.4  -> GPIO2, J11
constexpr uint8_t RADIO_GPIO3 = 42;  // J6.6  -> GPIO3
constexpr uint32_t RADIO_XTAL_HZ = 50000000;

// FRAM MB85RS4MT (Adafruit 4719) na tej samej magistrali SPI.
constexpr uint8_t FRAM_CS = 8;  // J5.12

// Ekran Sharp LS027B7DH01 (Adafruit 4694): CS aktywny stanem wysokim (10 kΩ do masy), EXTCOMIN
// z MCPWM, EMD na stałe wysoki. DISP: 2,2 kΩ do masy (R19), więc ekran jest wyłączony, dopóki
// program po wyczyszczeniu pamięci ekranu nie poda stanu wysokiego.
constexpr uint8_t DISPLAY_CS = 7;         // J5.7
constexpr uint8_t DISPLAY_EXTCOMIN = 17;  // J5.10
constexpr uint8_t DISPLAY_DISP = 16;      // J5.9
constexpr uint32_t DISPLAY_SPI_HZ = 1000000;  // 2 MHz dopiero po próbie z analizatorem na J11

// Panel płytki: przyciski i przełącznik do masy, podciągnięte na płytce 10 kΩ do 3,3 V
// (OK i WSTECZ dodatkowo 2,2 kΩ na X-NUCLEO, linie I2C złącza Arduino).
constexpr uint8_t BTN_UP = 41;      // J6.7
constexpr uint8_t BTN_DOWN = 40;    // J6.8
constexpr uint8_t BTN_OK = 39;      // J6.9
constexpr uint8_t BTN_BACK = 2;     // J6.5
constexpr uint8_t SW_SILENCE = 1;   // J6.4 przez 1 kΩ (R16); masa = cisza
constexpr uint8_t BTN_PREP = 6;     // J5.6; przycisk trybu przygotowania

// Dioda alarmu (przez 1 kΩ do masy, aktywna stanem wysokim) i brzęczyk (tranzystor Q1 z +5 V,
// aktywny stanem wysokim; tylko przebieg z tone(), nie stały stan wysoki).
constexpr uint8_t LED_ALARM = 18;  // J5.11
constexpr uint8_t BUZZER = 15;     // J5.8
constexpr uint16_t BUZZER_HZ = 2048;

// VTEST: zacisk J12 przez dzielnik 100 kΩ / 20 kΩ, czyli VTEST_IN / 6, na GPIO5 (ADC1_CH4).
constexpr uint8_t VTEST = 5;  // J5.5
constexpr uint8_t VTEST_ADC_CHANNEL = 4;
constexpr uint8_t VTEST_DIVIDER = 6;

// Diody stanu jak LED1-LED4 płytki DK: brak (DevKitC ma tylko diodę RGB WS2812, nieużywaną).
constexpr int16_t LED_HEARTBEAT = -1;
constexpr int16_t LED_RADIO = -1;
constexpr int16_t LED_FRAM = -1;
constexpr int16_t LED_USB = -1;

constexpr uint32_t SPI_HZ = 1000000;  // radio i FRAM, jak na stanowisku A

}  // namespace board
