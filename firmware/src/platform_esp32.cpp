// SPDX-License-Identifier: MIT
// Warstwa MCU dla ESP32-S3 (Arduino-ESP32 3.x): stanowisko B na płytce N1.
#if defined(ARDUINO_ARCH_ESP32)
#include "platform.h"

#include <driver/gpio.h>
#include <esp_mac.h>
#include <esp_system.h>
#include <esp_timer.h>
#include <esp_task_wdt.h>

#include "board.h"
#include "cmdargs.h"

namespace platform {

const char* const MCU = "ESP32-S3";
const char* const EXTCOMIN_SOURCE = "MCPWM0";

namespace {

SPIClass spiBus(FSPI);  // SPI2 na pinach IO_MUX FSPI
uint8_t spiDrive = board::SPI_DRIVE;

// Napęd SCK i MOSI (gpio_drive_cap_t 0-3, około 5/10/20/40 mA); sieć SCK N1 ma około 240 mm.
void setSpiDrive(uint8_t level) {
    spiDrive = level;
    const gpio_drive_cap_t cap = static_cast<gpio_drive_cap_t>(level);
    gpio_set_drive_capability(static_cast<gpio_num_t>(board::SPI_SCK), cap);
    gpio_set_drive_capability(static_cast<gpio_num_t>(board::SPI_MOSI), cap);
}

}  // namespace

SPIClass& bus() { return spiBus; }

void beginBus() {
    spiBus.begin(board::SPI_SCK, board::SPI_MISO, board::SPI_MOSI, -1);  // CS sterują sterowniki
    setSpiDrive(board::SPI_DRIVE);
}

void chipId(uint32_t id[2]) {
    // Adres MAC z eFuse: bajty 3-5 (część przydzielana przez producenta) w id[0] & 0xFFFFFF.
    uint8_t mac[6] = {};
    esp_efuse_mac_get_default(mac);
    id[0] = (static_cast<uint32_t>(mac[3]) << 16) | (static_cast<uint32_t>(mac[4]) << 8) | mac[5];
    id[1] = (static_cast<uint32_t>(mac[0]) << 16) | (static_cast<uint32_t>(mac[1]) << 8) | mac[2];
}

uint32_t resetReason() { return static_cast<uint32_t>(esp_reset_reason()); }

uint64_t uptimeMs() { return static_cast<uint64_t>(esp_timer_get_time()) / 1000; }

bool resetByWatchdog() {
    const esp_reset_reason_t r = esp_reset_reason();
    return r == ESP_RST_TASK_WDT || r == ESP_RST_INT_WDT || r == ESP_RST_WDT;
}

// Watchdog zadań (TWDT) pilnuje zadania pętli stacji; po przekroczeniu czasu restart układu.
void beginWatchdog(uint32_t seconds) {
    esp_task_wdt_config_t config = {};
    config.timeout_ms = seconds * 1000;
    config.idle_core_mask = 0;
    config.trigger_panic = true;
    if (esp_task_wdt_reconfigure(&config) != ESP_OK) esp_task_wdt_init(&config);
    esp_task_wdt_add(nullptr);
}

void feedWatchdog() { esp_task_wdt_reset(); }

void reboot() {
    esp_restart();
}

void beginVtest() {
    analogReadResolution(12);
    analogSetPinAttenuation(board::VTEST, ADC_11db);
}

// VTEST: średnia z 16 odczytów ADC1_CH4 w mV (analogReadMilliVolts: tłumienie 11 dB, kalibracja eFuse).
void printVtest() {
    uint32_t sum = 0;
    for (int i = 0; i < 16; ++i) sum += analogReadMilliVolts(board::VTEST);
    const uint32_t pinMv = sum / 16;
    Serial.printf("{\"vtest_mv\":%lu,\"pin_mv\":%lu,\"adc\":\"ADC1_CH%u\",\"divider\":%u}\n",
                  static_cast<unsigned long>(pinMv * board::VTEST_DIVIDER), static_cast<unsigned long>(pinMv),
                  board::VTEST_ADC_CHANNEL, board::VTEST_DIVIDER);
}

bool handle(const char* cmd, char* words[], size_t n) {
    if (strcmp(cmd, "DRIVE") || n > 1) return false;
    // Napęd SCK i MOSI do prób zboczy z analizatorem na J11; do restartu.
    if (n == 1) {
        uint32_t level = 0;
        if (!cmdargs::parseUint(words[0], 0, 3, level)) {
            Serial.println("{\"error\":\"DRIVE <0-3>\"}");
            return true;
        }
        setSpiDrive(static_cast<uint8_t>(level));
    }
    Serial.printf("{\"spi_drive\":%u,\"sck\":%u,\"mosi\":%u}\n", spiDrive, board::SPI_SCK, board::SPI_MOSI);
    return true;
}

const char* helpCommands() { return ",\"DRIVE [<0-3>]\""; }

}  // namespace platform

#endif
