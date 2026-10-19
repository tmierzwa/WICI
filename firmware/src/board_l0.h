// SPDX-License-Identifier: MIT
// Stacja pilotażowa L0: ESP32-S3-DevKitC-1-N8R8 w J5/J6 płytki nośnej N1, moduł Seeed Wio-SX1262
// (SX1262, TCXO 1,8 V z DIO3, przełącznik RF: DIO2 nadawanie, RXEN odbiór) w J1-J4, FRAM U1, panel
// ekranu Sharp w J7 i panel obsługi N1. Przypisanie według
// hardware/l0-diagnostic/reference/polaczenia-MCU-L0.csv (te same piny co program diagnostyczny
// L0, hardware/l0-diagnostic/src/board.h); nazwy jak w board_bench_b.h, bo resztę programu stacji
// (warstwa MCU, ekran, panel) dzieli z obrazem bench-b. Numery pinów to numery GPIO ESP32-S3.
#pragma once

#include <Arduino.h>

#define WICI_BOARD_N1 1  // płytka nośna N1: panel i linia DISP ekranu (board.h)

namespace board {

constexpr const char* NAME = "N1";

// SPI: piny IO_MUX FSPI na kontrolerze SPI2, SCK przez 33 Ω (R18); napęd jak na bench-b.
constexpr uint8_t SPI_SCK = 12;   // J5.18 -> R18 -> SPI_SCK; Wio J2.6
constexpr uint8_t SPI_MOSI = 11;  // J5.17; Wio J2.4
constexpr uint8_t SPI_MISO = 13;  // J5.19; Wio J2.5 (Wio zwalnia MISO przy NSS wysokim)
constexpr uint8_t SPI_DRIVE = 0;  // gpio_drive_cap_t: 0 = najsłabszy

// SX1262 na Wio-SX1262.
constexpr uint8_t RADIO_CS = 10;    // J5.16 -> Wio J1.4 NSS, aktywny stanem niskim; N1 R11 10 kΩ do 3,3 V
constexpr uint8_t RADIO_RESET = 9;  // J5.15 -> Wio J1.3 NRESET; N1 R12 1 kΩ do masy, Wio 10 kΩ do 3,3 V: napędzany wysoko
constexpr uint8_t RADIO_BUSY = 14;  // J5.20 -> Wio J1.2 BUSY, wejście (nie zastępuje DIO1)
constexpr uint8_t RADIO_DIO1 = 21;  // J6.18 -> Wio J1.1 DIO1, wejście przerwania (stan w RADIO; sterownik czyta przerwania przez SPI)
constexpr uint8_t RADIO_RXEN = 42;  // J6.6 -> Wio J1.5 RF_SW1/RXEN: wysoki w RX, niski w TX i spoczynku; 10 kΩ do masy

// FRAM U1 na płytce N1 (CY15B104QN albo MB85RS4MT) na tej samej magistrali SPI.
constexpr uint8_t FRAM_CS = 8;  // J5.12

// Panel Sharp w J7: SCS aktywny stanem wysokim, EXTCOMIN z MCPWM, DISP wysoki po wyczyszczeniu ekranu.
constexpr uint8_t DISPLAY_CS = 7;         // J5.7
constexpr uint8_t DISPLAY_EXTCOMIN = 17;  // J5.10
constexpr uint8_t DISPLAY_DISP = 16;      // J5.9
constexpr uint32_t DISPLAY_SPI_HZ = 1000000;

// Panel płytki: przyciski i przełącznik do masy, podciągnięte na płytce 10 kΩ do 3,3 V.
constexpr uint8_t BTN_UP = 41;      // J6.7
constexpr uint8_t BTN_DOWN = 40;    // J6.8
constexpr uint8_t BTN_OK = 39;      // J6.9
constexpr uint8_t BTN_BACK = 2;     // J6.5
constexpr uint8_t SW_SILENCE = 1;   // J6.4 przez 1 kΩ (R16); masa = cisza
constexpr uint8_t BTN_PREP = 6;     // J5.6; przycisk trybu przygotowania

// Dioda alarmu (aktywna stanem wysokim) i brzęczyk (tylko przebieg z tone()).
constexpr uint8_t LED_ALARM = 18;  // J5.11
constexpr uint8_t BUZZER = 15;     // J5.8
constexpr uint16_t BUZZER_HZ = 2048;

// VTEST: zacisk J12 płytki N1 przez dzielnik 100 kΩ / 20 kΩ na GPIO5 (ADC1_CH4); poza tabelą L0,
// bo nie dotyczy modułu radiowego, jak na bench-b.
constexpr uint8_t VTEST = 5;  // J5.5
constexpr uint8_t VTEST_ADC_CHANNEL = 4;
constexpr uint8_t VTEST_DIVIDER = 6;

// Diody stanu jak LED1-LED4 płytki DK: brak (DevKitC ma tylko diodę RGB, nieużywaną).
constexpr int16_t LED_HEARTBEAT = -1;
constexpr int16_t LED_RADIO = -1;
constexpr int16_t LED_FRAM = -1;
constexpr int16_t LED_USB = -1;

constexpr uint32_t SPI_HZ = 1000000;  // radio, jak w programie diagnostycznym L0
constexpr uint32_t FRAM_SPI_HZ = 8000000;

}  // namespace board
