// SPDX-License-Identifier: MIT
// Stanowisko deweloperskie A na płytce nośnej N1 (hardware/dev-bench/plytka-nosna.md):
// nRF52840-DK (wariant pca10056 rdzenia Adafruit) pod nakładką N1 z modułem TI CC1120EM-868-915
// w J9/J10, FRAM MB85RS4MT, ekranem Sharp (Adafruit 4694) i panelem płytki (przyciski, CISZA,
// przycisk przygotowania, dioda alarmu, brzęczyk, VTEST).
// Przypisanie według tabeli "Przypisanie sygnałów" i hardware/dev-bench/polaczenia.md; różnice
// wobec okablowania przewodami: hardware/dev-bench/checks/zgodnosc-firmware.md.
// Numery pinów to numery GPIO nRF52840 w rdzeniu Adafruit: P0.xx = xx, P1.xx = 32 + xx.
#pragma once

#include <Arduino.h>

#define WICI_BOARD_N1 1  // płytka nośna N1: panel i linia DISP ekranu (board.h)

namespace board {

constexpr const char* NAME = "N1";

// SPI na D3/D11/D12, nie na D13 domyślnego SPI wariantu (D13 to na N1 przełącznik CISZA).
// Własna instancja SPIClass na SPIM2 (platform_nrf.cpp); SPIClass::begin() rdzenia ustawia napęd H0H1
// na SCK i MOSI. P1.04 i P1.13 Nordic zaleca tylko do sygnałów
// wolnozmiennych ("low frequency I/O only"), żeby nie zakłócać radia 2,4 GHz; stanowisko go nie
// używa, więc ograniczenie nie dotyczy działania, a zegar zostaje przy 1 MHz.
constexpr uint8_t SPI_SCK = 32 + 4;    // P1.04, D3  -> 33 Ω (R17) -> EM P1.16, FRAM, ekran
constexpr uint8_t SPI_MOSI = 32 + 13;  // P1.13, D11 -> EM P1.18
constexpr uint8_t SPI_MISO = 32 + 14;  // P1.14, D12 -> EM P1.20 (IOCFG1 w P1: wysoka impedancja)

// Moduł radiowy CC1120EM na pozycjach X-NUCLEO-S2868A2.
constexpr uint8_t RADIO_CS = 4;          // P0.04, A1 -> EM P1.14 (CSn), 10 kΩ do 3,3 V
constexpr uint8_t RADIO_RESET = 32 + 8;  // P1.08, D7 -> EM P2.15 (RESET_N), 10 kΩ do masy
constexpr uint8_t RADIO_GPIO0 = 3;       // P0.03, A0 -> EM P1.10 (GPIO0)
constexpr uint8_t RADIO_GPIO2 = 29;      // P0.29, A3 -> EM P1.12 (GPIO2)
constexpr uint8_t RADIO_GPIO3 = 31;      // P0.31, A5 -> EM P2.18 (GPIO3), nieużywany

// FRAM MB85RS4MT (Adafruit 4719) na tej samej magistrali SPI.
constexpr uint8_t FRAM_CS = 32 + 11;  // P1.11, D9

// Ekran Sharp LS027B7DH01 (Adafruit 4694): CS aktywny stanem wysokim (10 kΩ do masy), EXTCOMIN
// z licznika RTC2, EMD na stałe wysoki. DISP: 2,2 kΩ do masy (R19), więc ekran jest wyłączony,
// dopóki program po wyczyszczeniu pamięci ekranu nie poda stanu wysokiego.
constexpr uint8_t DISPLAY_CS = 32 + 5;        // P1.05, D4
constexpr uint8_t DISPLAY_EXTCOMIN = 32 + 7;  // P1.07, D6
constexpr uint8_t DISPLAY_DISP = 32 + 10;     // P1.10, D8
// Sieć SCK ma około 240 mm z odgałęzieniami; 2 MHz (granica LS027B7DH01) dopiero po próbie
// z analizatorem na J11 (polecenie DISPLAY <hz>).
constexpr uint32_t DISPLAY_SPI_HZ = 1000000;

// Panel płytki: przyciski i przełącznik do masy, podciągnięte na płytce 10 kΩ do 3,3 V.
constexpr uint8_t BTN_UP = 32 + 1;     // P1.01, D0
constexpr uint8_t BTN_DOWN = 32 + 2;   // P1.02, D1
constexpr uint8_t BTN_OK = 26;         // P0.26, SDA
constexpr uint8_t BTN_BACK = 27;       // P0.27, SCL
constexpr uint8_t SW_SILENCE = 32 + 15;  // P1.15, D13 przez 1 kΩ (R16); masa = cisza
constexpr uint8_t BTN_PREP = 2;          // P0.02, AREF; przycisk trybu przygotowania

// Dioda alarmu (przez 1 kΩ do masy, aktywna stanem wysokim) i brzęczyk (tranzystor Q1 z +5 V,
// aktywny stanem wysokim; stały stan wysoki to około 75 mA, więc tylko przebieg z tone()).
constexpr uint8_t LED_ALARM = 32 + 12;  // P1.12, D10
constexpr uint8_t BUZZER = 32 + 3;      // P1.03, D2
constexpr uint16_t BUZZER_HZ = 2048;

// VTEST: zacisk J12 przez dzielnik 100 kΩ / 20 kΩ, czyli VTEST_IN / 6, na P0.30 (AIN6).
constexpr uint8_t VTEST = 30;  // P0.30, A4
constexpr uint8_t VTEST_DIVIDER = 6;

// Diody płytki DK (aktywne stanem niskim) zostają w dotychczasowych rolach.
constexpr uint8_t LED_HEARTBEAT = PIN_LED1;  // P0.13
constexpr uint8_t LED_RADIO = PIN_LED2;      // P0.14
constexpr uint8_t LED_FRAM = PIN_LED3;       // P0.15
constexpr uint8_t LED_USB = PIN_LED4;        // P0.16

constexpr uint32_t SPI_HZ = 1000000;  // radio i FRAM, jak na przewodach

}  // namespace board
