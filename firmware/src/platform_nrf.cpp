// SPDX-License-Identifier: MIT
// Warstwa MCU dla nRF52840 (rdzeń Adafruit): stanowisko A na przewodach i na płytce N1.
#if defined(ARDUINO_ARCH_NRF52)
#include "platform.h"

#include "board.h"

namespace platform {

const char* const MCU = "nRF52840";
const char* const EXTCOMIN_SOURCE = "RTC2";

namespace {
#if defined(WICI_BOARD_N1)
// N1: SPI na D3/D11/D12 na SPIM2; domyślne SPI (SPIM3, SCK na D13) nie jest uruchamiane.
SPIClass spiBus(NRF_SPIM2, board::SPI_MISO, board::SPI_SCK, board::SPI_MOSI);
#endif
}  // namespace

SPIClass& bus() {
#if defined(WICI_BOARD_N1)
    return spiBus;
#else
    return SPI;
#endif
}

void beginBus() { bus().begin(); }  // rdzeń ustawia napęd H0H1 na SCK i MOSI

void chipId(uint32_t id[2]) {
    id[0] = NRF_FICR->DEVICEID[0];
    id[1] = NRF_FICR->DEVICEID[1];
}

uint32_t resetReason() { return readResetReason(); }

uint64_t uptimeMs() {
    // millis() rdzenia to takty FreeRTOS (1024 Hz) przeliczone na ms: po 2^32 taktach spada do zera
    // z około 4,19 mln s, nie z 2^32 ms. Różnica taktów bez znaku jest poprawna mimo zawinięcia.
    static uint32_t lastTick = 0;
    static uint64_t ticks = 0;
    const uint32_t tick = xTaskGetTickCount();
    ticks += static_cast<uint32_t>(tick - lastTick);
    lastTick = tick;
    return ticks * 1000 / configTICK_RATE_HZ;
}

bool resetByWatchdog() { return readResetReason() & POWER_RESETREAS_DOG_Msk; }

// Watchdog sprzętowy (WDT, LFCLK): zatrzymany, gdy debugger zatrzyma rdzeń; raz uruchomionego
// nie da się wyłączyć bez restartu.
void beginWatchdog(uint32_t seconds) {
    NRF_WDT->CONFIG = (WDT_CONFIG_HALT_Pause << WDT_CONFIG_HALT_Pos) | (WDT_CONFIG_SLEEP_Run << WDT_CONFIG_SLEEP_Pos);
    NRF_WDT->CRV = seconds * 32768 - 1;
    NRF_WDT->RREN = WDT_RREN_RR0_Msk;
    NRF_WDT->TASKS_START = 1;
}

void feedWatchdog() { NRF_WDT->RR[0] = WDT_RR_RR_Reload; }

void reboot() {
    NVIC_SystemReset();
    for (;;) {}
}

#if defined(WICI_BOARD_N1)
void beginVtest() { analogReadResolution(12); }

// VTEST: średnia z 16 próbek SAADC (12 bitów, odniesienie 0,6 V, wzmocnienie 1/6: 3,6 V pełnej skali).
void printVtest() {
    uint32_t sum = 0;
    for (int i = 0; i < 16; ++i) sum += analogRead(board::VTEST);
    const uint32_t raw = sum / 16;
    const uint32_t pinMv = raw * 3600 / 4096;
    Serial.printf("{\"vtest_mv\":%lu,\"pin_mv\":%lu,\"raw\":%lu,\"ain\":6,\"divider\":%u}\n",
                  static_cast<unsigned long>(pinMv * board::VTEST_DIVIDER), static_cast<unsigned long>(pinMv),
                  static_cast<unsigned long>(raw), board::VTEST_DIVIDER);
}
#else
void beginVtest() {}
void printVtest() {}
#endif

bool handle(const char*, char*[], size_t) { return false; }

const char* helpCommands() { return ""; }

}  // namespace platform

#endif
