// SPDX-License-Identifier: MIT
// Warstwa MCU programu stacji (main.cpp): magistrala SPI płytki, identyfikator układu, przyczyna
// restartu, watchdog, restart programowy, pamięć niezerowana i pomiar VTEST. Wykonania:
// platform_nrf.cpp (nRF52840, rdzeń Adafruit) i platform_esp32.cpp (ESP32-S3, Arduino-ESP32 3.x).
#pragma once

#include <Arduino.h>
#include <SPI.h>

#if defined(ARDUINO_ARCH_ESP32)
#include <esp_attr.h>
// Pamięć RTC niezerowana przy restarcie programowym i przez watchdog (po włączeniu zasilania przypadkowa).
#define PLATFORM_NOINIT RTC_NOINIT_ATTR
#else
#define PLATFORM_NOINIT __attribute__((section(".noinit")))
#endif

namespace platform {

extern const char* const MCU;              // pole "mcu" w INFO
extern const char* const EXTCOMIN_SOURCE;  // licznik EXTCOMIN ekranu (pole "extcomin" w DISPLAY)

SPIClass& bus();  // magistrala radia, FRAM i ekranu
void beginBus();  // piny i kontroler SPI (po ustawieniu CS wszystkich układów w stan nieaktywny)

// 8 bajtów identyfikatora układu (nRF52840: FICR DEVICEID; ESP32-S3: adres MAC z eFuse);
// id[0] & 0xFFFFFF daje nazwę WICI-xxxxxx.
void chipId(uint32_t id[2]);
uint32_t resetReason();  // nRF52840: RESETREAS; ESP32-S3: esp_reset_reason()
bool resetByWatchdog();

void beginWatchdog(uint32_t seconds);
void feedWatchdog();
[[noreturn]] void reboot();  // pamięć niezerowana zostaje

void beginVtest();
void printVtest();  // odpowiedź na VTEST (tylko płytka N1)

// Polecenia tylko tego MCU (ESP32-S3: DRIVE); false, gdy polecenie nieznane.
bool handle(const char* cmd, char* words[], size_t n);
const char* helpCommands();  // dopisek do listy HELP, z przecinkiem na początku albo pusty

}  // namespace platform
