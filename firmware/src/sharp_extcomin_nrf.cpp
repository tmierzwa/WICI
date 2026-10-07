// SPDX-License-Identifier: MIT
// EXTCOMIN ekranu Sharp na nRF52840: licznik RTC2 przez PPI i GPIOTE, bez udziału programu.
#if defined(ARDUINO_ARCH_NRF52)
#include "sharp.h"

namespace sharp {

void Display::beginExtcomin() {
    // Pin w GPIOTE w trybie zadania (toggle), RTC2 z preskalerem 4095 (8 Hz) i COMPARE0 = 4
    // (0,5 s); PPI: zdarzenie COMPARE0 -> zadanie OUT pinu i (rozgałęzienie) CLEAR licznika.
    const uint32_t pin = g_ADigitalPinMap[pinExtcomin_];
    pinMode(pinExtcomin_, OUTPUT);
    digitalWrite(pinExtcomin_, LOW);
    // pinMode(OUTPUT) rdzenia odłącza bufor wejściowy, a extcominLevel() czyta stan z rejestru IN.
    NRF_GPIO_Type* port = pin >= 32 ? NRF_P1 : NRF_P0;
    port->PIN_CNF[pin & 0x1F] = (port->PIN_CNF[pin & 0x1F] & ~GPIO_PIN_CNF_INPUT_Msk) |
                                (GPIO_PIN_CNF_INPUT_Connect << GPIO_PIN_CNF_INPUT_Pos);
    NRF_GPIOTE->CONFIG[GPIOTE_CHANNEL] = (GPIOTE_CONFIG_MODE_Task << GPIOTE_CONFIG_MODE_Pos) |
                                         ((pin & 0x1F) << GPIOTE_CONFIG_PSEL_Pos) |
                                         ((pin >> 5) << GPIOTE_CONFIG_PORT_Pos) |
                                         (GPIOTE_CONFIG_POLARITY_Toggle << GPIOTE_CONFIG_POLARITY_Pos) |
                                         (GPIOTE_CONFIG_OUTINIT_Low << GPIOTE_CONFIG_OUTINIT_Pos);
    if (!(NRF_CLOCK->LFCLKSTAT & CLOCK_LFCLKSTAT_STATE_Msk)) {
        NRF_CLOCK->TASKS_LFCLKSTART = 1;  // rdzeń uruchamia LFCLK w init(); zapasowo tutaj
        while (!(NRF_CLOCK->LFCLKSTAT & CLOCK_LFCLKSTAT_STATE_Msk)) {}
    }
    NRF_RTC2->TASKS_STOP = 1;
    NRF_RTC2->TASKS_CLEAR = 1;
    NRF_RTC2->PRESCALER = 4095;  // 32768 Hz / 4096 = 8 Hz
    NRF_RTC2->CC[0] = 8 * EXTCOMIN_HALF_PERIOD_MS / 1000;
    NRF_RTC2->EVTENSET = RTC_EVTENSET_COMPARE0_Msk;
    NRF_PPI->CH[PPI_CHANNEL].EEP = reinterpret_cast<uint32_t>(&NRF_RTC2->EVENTS_COMPARE[0]);
    NRF_PPI->CH[PPI_CHANNEL].TEP = reinterpret_cast<uint32_t>(&NRF_GPIOTE->TASKS_OUT[GPIOTE_CHANNEL]);
    NRF_PPI->FORK[PPI_CHANNEL].TEP = reinterpret_cast<uint32_t>(&NRF_RTC2->TASKS_CLEAR);
    NRF_PPI->CHENSET = 1u << PPI_CHANNEL;
    NRF_RTC2->TASKS_START = 1;
}

uint32_t Display::extcominCounter() const { return NRF_RTC2->COUNTER; }

bool Display::extcominLevel() const {
    const uint32_t pin = g_ADigitalPinMap[pinExtcomin_];
    NRF_GPIO_Type* port = pin >= 32 ? NRF_P1 : NRF_P0;
    return (port->IN >> (pin & 0x1F)) & 1u;
}

}  // namespace sharp

#endif
