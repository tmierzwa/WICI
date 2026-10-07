// SPDX-License-Identifier: MIT
// EXTCOMIN ekranu Sharp na ESP32-S3: timer 0 jednostki MCPWM0 z wyjściem PWM0A na pinie,
// 1 Hz przy wypełnieniu 50 %, bez udziału programu. Rozdzielczość grupy 640 kHz (160 MHz / 250)
// i timera 10 kHz (/ 64), więc okres to 10 000 taktów licznika 16-bitowego.
#if defined(ARDUINO_ARCH_ESP32)
#include "sharp.h"

#include <driver/gpio.h>
#include <driver/mcpwm.h>
#include <soc/mcpwm_struct.h>

namespace sharp {

namespace {
constexpr unsigned long GROUP_HZ = 640000;
constexpr unsigned long TIMER_HZ = 10000;
}  // namespace

void Display::beginExtcomin() {
    pinMode(pinExtcomin_, OUTPUT);
    digitalWrite(pinExtcomin_, LOW);
    mcpwm_gpio_init(MCPWM_UNIT_0, MCPWM0A, pinExtcomin_);
    mcpwm_group_set_resolution(MCPWM_UNIT_0, GROUP_HZ);
    mcpwm_timer_set_resolution(MCPWM_UNIT_0, MCPWM_TIMER_0, TIMER_HZ);
    mcpwm_config_t config = {};
    config.frequency = 1000 / (2 * EXTCOMIN_HALF_PERIOD_MS);  // 1 Hz
    config.cmpr_a = 50.0f;
    config.cmpr_b = 0.0f;
    config.counter_mode = MCPWM_UP_COUNTER;
    config.duty_mode = MCPWM_DUTY_MODE_0;
    mcpwm_init(MCPWM_UNIT_0, MCPWM_TIMER_0, &config);
    // Wejście pinu włączone obok wyjścia, żeby extcominLevel() czytało stan na pinie.
    gpio_set_direction(static_cast<gpio_num_t>(pinExtcomin_), GPIO_MODE_INPUT_OUTPUT);
}

uint32_t Display::extcominCounter() const { return MCPWM0.timer[0].timer_status.timer_value; }

bool Display::extcominLevel() const { return gpio_get_level(static_cast<gpio_num_t>(pinExtcomin_)) != 0; }

}  // namespace sharp

#endif
