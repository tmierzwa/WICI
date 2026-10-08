// SPDX-License-Identifier: MIT
// EXTCOMIN ekranu Sharp na ESP32-S3: timer jednostki MCPWM0 z generatorem na pinie, 1 Hz przy
// wypełnieniu 50 %, bez udziału programu (sterownik MCPWM z ESP-IDF 5: driver/mcpwm_prelude.h).
// Licznik 10 kHz, okres 10 000 taktów: stan wysoki od zera licznika do porównania 5000.
#if defined(ARDUINO_ARCH_ESP32)
#include "sharp.h"

#include <driver/gpio.h>
#include <driver/mcpwm_prelude.h>
#include <soc/mcpwm_struct.h>

namespace sharp {

namespace {
constexpr uint32_t TIMER_HZ = 10000;
constexpr uint32_t PERIOD_TICKS = TIMER_HZ * 2 * EXTCOMIN_HALF_PERIOD_MS / 1000;  // 1 s
bool started = false;
}  // namespace

// Błąd sterownika MCPWM zwraca false i zostawia pin w stanie niskim. Bitu VCOM nie włącza się
// zamiast licznika: przy EXTMODE w stanie wysokim (N1) panel go pomija, więc jedyną bezpieczną
// reakcją jest panel wyłączony (DISP = L) i zgłoszona usterka (main.cpp).
bool Display::beginExtcomin() {
    if (started) return true;  // drugi begin(): przebieg już biegnie (pinMode odłączyłby pin od MCPWM)
    pinMode(pinExtcomin_, OUTPUT);
    digitalWrite(pinExtcomin_, LOW);
    mcpwm_timer_handle_t timer = nullptr;
    mcpwm_timer_config_t timerConfig = {};
    timerConfig.group_id = 0;
    timerConfig.clk_src = MCPWM_TIMER_CLK_SRC_DEFAULT;
    timerConfig.resolution_hz = TIMER_HZ;
    timerConfig.count_mode = MCPWM_TIMER_COUNT_MODE_UP;
    timerConfig.period_ticks = PERIOD_TICKS;
    if (mcpwm_new_timer(&timerConfig, &timer) != ESP_OK) return false;
    mcpwm_oper_handle_t oper = nullptr;
    mcpwm_operator_config_t operConfig = {};
    operConfig.group_id = 0;
    if (mcpwm_new_operator(&operConfig, &oper) != ESP_OK || mcpwm_operator_connect_timer(oper, timer) != ESP_OK) return false;
    mcpwm_cmpr_handle_t comparator = nullptr;
    mcpwm_comparator_config_t cmprConfig = {};
    cmprConfig.flags.update_cmp_on_tez = 1;
    if (mcpwm_new_comparator(oper, &cmprConfig, &comparator) != ESP_OK ||
        mcpwm_comparator_set_compare_value(comparator, PERIOD_TICKS / 2) != ESP_OK) return false;
    mcpwm_gen_handle_t generator = nullptr;
    mcpwm_generator_config_t genConfig = {};
    genConfig.gen_gpio_num = pinExtcomin_;
    genConfig.flags.io_loop_back = 1;  // wejście pinu włączone, żeby extcominLevel() czytało stan
    if (mcpwm_new_generator(oper, &genConfig, &generator) != ESP_OK) return false;
    const bool actions =
        mcpwm_generator_set_action_on_timer_event(
            generator, MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, MCPWM_TIMER_EVENT_EMPTY, MCPWM_GEN_ACTION_HIGH)) == ESP_OK &&
        mcpwm_generator_set_action_on_compare_event(
            generator, MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, comparator, MCPWM_GEN_ACTION_LOW)) == ESP_OK;
    if (!actions || mcpwm_timer_enable(timer) != ESP_OK || mcpwm_timer_start_stop(timer, MCPWM_TIMER_START_NO_STOP) != ESP_OK) return false;
    started = true;
    return true;
}

// Pierwszy przydzielony timer grupy 0 to timer 0 (MCPWM nie ma innych użytkowników w programie).
uint32_t Display::extcominCounter() const { return MCPWM0.timer[0].timer_status.timer_value; }

bool Display::extcominLevel() const { return gpio_get_level(static_cast<gpio_num_t>(pinExtcomin_)) != 0; }

}  // namespace sharp

#endif
