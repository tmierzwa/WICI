// SPDX-License-Identifier: MIT
// Dedicated MCPWM timer: output continues while the main loop is paused.
#include "sharp.h"
#include <driver/mcpwm.h>
#include <soc/mcpwm_struct.h>

namespace sharp {
bool Display::beginExtcomin() {
    if (mcpwm_gpio_init(MCPWM_UNIT_0, MCPWM0A, pinExtcomin_) != ESP_OK) return false;
    // 160MHz /160 -> 1MHz group; /100 -> 10kHz timer: 10000 ticks at 1Hz.
    if (mcpwm_group_set_resolution(MCPWM_UNIT_0, 1000000) != ESP_OK ||
        mcpwm_timer_set_resolution(MCPWM_UNIT_0, MCPWM_TIMER_0, 10000) != ESP_OK)
        return false;
    mcpwm_config_t config = {};
    config.frequency = 1;
    config.cmpr_a = 50;
    config.counter_mode = MCPWM_UP_COUNTER;
    config.duty_mode = MCPWM_DUTY_MODE_0;
    if (mcpwm_init(MCPWM_UNIT_0, MCPWM_TIMER_0, &config) != ESP_OK) return false;
    return mcpwm_get_frequency(MCPWM_UNIT_0, MCPWM_TIMER_0) == 1;
}

uint32_t Display::extcominCounter() const {
    return extcominOk_ ? MCPWM0.timer[0].timer_status.timer_value : 0;
}
}  // namespace sharp
