// SPDX-License-Identifier: MIT
// Warstwa MCU symulatora (firmware/src/platform.h) w miejsce platform_esp32.cpp: magistrala SPI płytki,
// adres MAC i entropia z ziarna płytki, przyczyna restartu (kody esp_reset_reason_t), czas, watchdog
// zadań i restart wirtualnej płytki (vboard.h). Odpowiedzi poleceń jak na ESP32-S3.
#include "platform.h"

#include "board.h"

namespace platform {

const char* const MCU = "ESP32-S3 (symulator)";
const char* const EXTCOMIN_SOURCE = "MCPWM0 (symulator)";

SPIClass& bus() { return SPI; }

void beginBus() { SPI.begin(board::SPI_SCK, board::SPI_MISO, board::SPI_MOSI, -1); }

void chipId(uint32_t id[2]) {
    uint8_t mac[6] = {};
    vb::chipId(mac);
    id[0] = (static_cast<uint32_t>(mac[3]) << 16) | (static_cast<uint32_t>(mac[4]) << 8) | mac[5];
    id[1] = (static_cast<uint32_t>(mac[0]) << 16) | (static_cast<uint32_t>(mac[1]) << 8) | mac[2];
}

bool entropy(uint8_t* out, size_t count) {
    vb::entropy(out, count);
    return true;
}

uint32_t resetReason() { return vb::resetReason(); }

uint64_t uptimeMs() { return vb::nowUs() / 1000; }

bool resetByWatchdog() {
    const uint32_t r = vb::resetReason();
    return r == 5 || r == 6 || r == 7;   // ESP_RST_INT_WDT, ESP_RST_TASK_WDT, ESP_RST_WDT
}

void beginWatchdog(uint32_t seconds) { vb::watchdogBegin(seconds); }

void feedWatchdog() { vb::feedTaskWatchdog(); }

void reboot() { vb::reboot("platform::reboot"); }

void beginVtest() {}

// VTEST: wejście zasilacza laboratoryjnego na N1; w symulatorze niepodłączone (0 V).
void printVtest() {
    Serial.printf("{\"vtest_mv\":%lu,\"pin_mv\":%lu,\"adc\":\"ADC1_CH%u\",\"divider\":%u}\n", 0UL, 0UL, board::VTEST_ADC_CHANNEL,
                  board::VTEST_DIVIDER);
}

bool handle(const char*, char*[], size_t) { return false; }

const char* helpCommands() { return ""; }

}  // namespace platform
