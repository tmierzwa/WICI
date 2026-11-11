// SPDX-License-Identifier: MIT
// Warstwa MCU dla ESP32-S3 (Arduino-ESP32 3.x): stanowisko B na płytce N1.
#if defined(ARDUINO_ARCH_ESP32)
#include "platform.h"

#include <bootloader_random.h>
#include <driver/gpio.h>
#include <esp_heap_caps.h>
#include <esp_mac.h>
#include <esp_random.h>
#include <esp_sleep.h>
#include <esp32-hal-periman.h>
#include <esp_system.h>
#include <esp_timer.h>
#include <esp_task_wdt.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

#include <atomic>
#include "board.h"
#include "cmdargs.h"

namespace platform {

const char* const MCU = "ESP32-S3";
const char* const EXTCOMIN_SOURCE = "MCPWM0";

namespace {

SPIClass spiBus(FSPI);  // SPI2 na pinach IO_MUX FSPI
uint8_t spiDrive = board::SPI_DRIVE;

// Napęd SCK i MOSI (gpio_drive_cap_t 0-3, około 5/10/20/40 mA); sieć SCK N1 ma około 300 mm.
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

bool entropy(uint8_t* out, size_t count) {
    bootloader_random_enable();
    esp_fill_random(out, count);   // rejestr RNG czytany bez czekania na gotowość
    bootloader_random_disable();
    return true;
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

#if defined(WICI_BOARD_N1)
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
#else
void beginVtest() {}
void printVtest() {}
#endif

namespace {

// Mutex w pamięci statycznej (bez sterty), utworzony przy inicjalizacji programu, przed setup() i przed
// każdym zadaniem; FreeRTOS pozwala tworzyć obiekty przed startem planisty.
StaticSemaphore_t radioMutexStorage;
const SemaphoreHandle_t radioMutex = xSemaphoreCreateRecursiveMutexStatic(&radioMutexStorage);
std::atomic<uint32_t> lockTimeouts{0};

// Zadanie odbioru: priorytet nad pętlą (1), zadaniem zdarzeń USB (5) i esp_timer (22). Zadanie urządzenia
// TinyUSB ("usbd") ma w Arduino-ESP32 3.3.12 configMAX_PRIORITIES - 1 (esp32-hal-tinyusb.c), czyli
// najwyższy priorytet, więc wyżej od niego się nie da; poniżej niego zostają też zadania IPC ESP-IDF.
// usbd głównie czeka na zdarzenia, a obieg zadania odbioru trwa ≤5 ms.
constexpr UBaseType_t RX_TASK_PRIORITY = configMAX_PRIORITIES - 2;
constexpr BaseType_t RX_TASK_CORE = 0;          // pętla stacji (loopTask) i tak pracuje na rdzeniu 1
constexpr size_t RX_TASK_STACK_BYTES = 4096;    // zapas sprawdza RNS (rx_stack_free)
// ESP-IDF: StackType_t to uint8_t, a głębokość stosu podaje się w jednostkach StackType_t (czyli w bajtach).
alignas(16) StackType_t rxTaskStack[RX_TASK_STACK_BYTES / sizeof(StackType_t)];
StaticTask_t rxTaskStorage;
TaskHandle_t rxTask = nullptr;
void (*rxCycle)() = nullptr;

void rxTaskMain(void*) {
    for (;;) {
        rxCycle();
        vTaskDelay(1);  // obieg co takt (CONFIG_FREERTOS_HZ = 1000): rdzeń 0 dostaje bezczynność i inne zadania
    }
}

}  // namespace

bool radioLockTake(uint32_t timeoutMs) {
    // W górę do taktów: krótki limit nie może stać się próbą bez czekania.
    TickType_t ticks = pdMS_TO_TICKS(timeoutMs);
    if (timeoutMs > 0 && ticks == 0) ticks = 1;
    const bool taken = xSemaphoreTakeRecursive(radioMutex, ticks) == pdTRUE;
    if (!taken && timeoutMs > 0) lockTimeouts.fetch_add(1, std::memory_order_relaxed);
    return taken;
}

void radioLockGive() { xSemaphoreGiveRecursive(radioMutex); }

uint32_t radioLockTimeouts() { return lockTimeouts.load(std::memory_order_relaxed); }

bool radioLockOk() { return !rxTask || xSemaphoreGetMutexHolder(radioMutex) == xTaskGetCurrentTaskHandle(); }

bool startRxTask(void (*cycle)()) {
    if (rxTask) return true;
    rxCycle = cycle;
    rxTask = xTaskCreateStaticPinnedToCore(rxTaskMain, "wici_rx", sizeof(rxTaskStack) / sizeof(StackType_t), nullptr,
                                           RX_TASK_PRIORITY, rxTaskStack, &rxTaskStorage, RX_TASK_CORE);
    return rxTask != nullptr;
}

int32_t rxTaskStackFree() {
    if (!rxTask) return -1;
    return static_cast<int32_t>(uxTaskGetStackHighWaterMark(rxTask) * sizeof(StackType_t));
}

// Sterta ESP-IDF: port microReticulum bierze z niej pamięć stosu (pula TLSF jest tylko na nRF52840).
int32_t heapSize() { return static_cast<int32_t>(heap_caps_get_total_size(MALLOC_CAP_DEFAULT)); }
int32_t heapFree() { return static_cast<int32_t>(esp_get_free_heap_size()); }
int32_t heapMinFree() { return static_cast<int32_t>(esp_get_minimum_free_heap_size()); }

#if defined(WICI_MCU_SLEEP)
// Lekkie uśpienie (platform.h, mcu_sleep.h). W lekkim uśpieniu domena cyfrowa ma zasilanie, więc przy obecnych
// ustawieniach Arduino-ESP32 piny i tak zostają w stanie sprzed uśpienia; tu trzyma się je jawnie, żeby zmiana
// ustawień ESP-IDF (izolacja GPIO w uśpieniu, CONFIG_PM_SLP_DISABLE_GPIO, wyłączanie domeny peryferiów) nie
// zresetowała radia ani nie wygasiła ekranu:
// - gpio_sleep_sel_dis: pin w uśpieniu zostaje przy zwykłej konfiguracji (kierunek, poziom, podciąganie), a nie
//   przechodzi na osobną konfigurację uśpienia; dotyczy wyjść i linii budzenia (te muszą zostać wejściami);
// - gpio_hold_en: zatrzaśnięcie stanu wyjścia na czas uśpienia; zwalniane po wybudzeniu, bo zatrzaśnięty pin
//   nie zmienia stanu także w pracy (RXEN, CS, EXTCOMIN).
// Budzenie poziomem (gpio_wakeup_enable): lekkie uśpienie ESP32-S3 nie budzi zboczem, więc poziomy wybiera
// mcu_sleep::arm (zmiana stanu dla linii ANY_CHANGE, stan wysoki dla DIO1).
mcu_sleep::Result sleep(uint32_t maxMs) {
    constexpr size_t holdCount = sizeof(board::SLEEP_HOLD) / sizeof(board::SLEEP_HOLD[0]);
    constexpr size_t lineCount = sizeof(board::SLEEP_WAKE) / sizeof(board::SLEEP_WAKE[0]);
    static_assert(lineCount <= mcu_sleep::MAX_LINES, "linie budzenia mieszczą się w tablicach poziomów");
    mcu_sleep::Result result{mcu_sleep::Cause::BUSY, -1, 0};

    // Blokada radia: zadanie odbioru nie może być w środku transakcji SPI, gdy rdzenie stają. Próby bez czekania,
    // bo nieudane czekanie z limitem liczy się jako błąd radia (radioLockTimeouts).
    bool locked = false;
    for (int i = 0; i < 20 && !(locked = radioLockTake(0)); ++i) delay(1);
    if (!locked) return result;

    uint8_t levels[mcu_sleep::MAX_LINES] = {};
    uint8_t armed[mcu_sleep::MAX_LINES] = {};
    for (size_t i = 0; i < lineCount; ++i) {
        // Linie bez innego użytkownika (na v2 INT wyłącznika i USB_LAPTOP) stają się wejściami; podciągnięcia
        // są na płytce (R47, R75). Linie ustawione już przez program (przyciski, DIO1) zostają bez zmian.
        const uint8_t pin = board::SLEEP_WAKE[i].pin;
        if (perimanGetPinBus(pin, ESP32_BUS_TYPE_GPIO) == nullptr) pinMode(pin, INPUT);
        levels[i] = digitalRead(pin) ? 1 : 0;
    }
    const int active = mcu_sleep::arm(board::SLEEP_WAKE, lineCount, levels, armed);
    if (active >= 0 || (maxMs == 0 && lineCount == 0)) {
        radioLockGive();
        result.line = static_cast<int8_t>(active);
        return result;
    }

    // Brzęczyk wyłączony przed uśpieniem: LEDC stoi w uśpieniu, więc przebieg z tone() mógłby zatrzymać się
    // w stanie wysokim (prąd przez brzęczyk). noTone() tylko wysyła polecenie do zadania tone(), które odłącza
    // LEDC od pinu; w czasie dźwięku z czasem trwania zadanie czeka do jego końca. Program czeka więc najwyżej
    // 50 ms na odłączenie, a przy trwającym dźwięku nie zasypia (BUSY), żeby nie zabrać pinu zadaniu tone()
    // w trakcie jego zapisu. Potem pin niski i trzymany niżej razem z innymi wyjściami.
    if (perimanGetPinBus(board::BUZZER, ESP32_BUS_TYPE_LEDC) != nullptr) {
        noTone(board::BUZZER);
        for (int i = 0; i < 50 && perimanGetPinBus(board::BUZZER, ESP32_BUS_TYPE_LEDC) != nullptr; ++i) delay(1);
        if (perimanGetPinBus(board::BUZZER, ESP32_BUS_TYPE_LEDC) != nullptr) {
            radioLockGive();
            return result;
        }
    }
    pinMode(board::BUZZER, OUTPUT);
    digitalWrite(board::BUZZER, LOW);

    for (size_t i = 0; i < holdCount; ++i) {
        const gpio_num_t pin = static_cast<gpio_num_t>(board::SLEEP_HOLD[i]);
        gpio_sleep_sel_dis(pin);
        gpio_hold_en(pin);
    }
    for (size_t i = 0; i < lineCount; ++i) {
        const gpio_num_t pin = static_cast<gpio_num_t>(board::SLEEP_WAKE[i].pin);
        gpio_sleep_sel_dis(pin);
        gpio_wakeup_enable(pin, armed[i] ? GPIO_INTR_HIGH_LEVEL : GPIO_INTR_LOW_LEVEL);
    }
    if (lineCount) esp_sleep_enable_gpio_wakeup();
    if (maxMs) esp_sleep_enable_timer_wakeup(static_cast<uint64_t>(maxMs) * 1000);

    feedWatchdog();
    const int64_t startUs = esp_timer_get_time();
    const esp_err_t err = esp_light_sleep_start();
    const int64_t endUs = esp_timer_get_time();
    const esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();

    for (size_t i = 0; i < lineCount; ++i) levels[i] = digitalRead(board::SLEEP_WAKE[i].pin) ? 1 : 0;
    for (size_t i = 0; i < lineCount; ++i) gpio_wakeup_disable(static_cast<gpio_num_t>(board::SLEEP_WAKE[i].pin));
    esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_ALL);
    for (size_t i = 0; i < holdCount; ++i) gpio_hold_dis(static_cast<gpio_num_t>(board::SLEEP_HOLD[i]));
    feedWatchdog();
    radioLockGive();

    result.sleptMs = static_cast<uint32_t>((endUs - startUs) / 1000);
    if (err != ESP_OK) result.cause = mcu_sleep::Cause::REJECTED;
    else if (cause == ESP_SLEEP_WAKEUP_TIMER) result.cause = mcu_sleep::Cause::TIMER;
    else if (cause == ESP_SLEEP_WAKEUP_GPIO) {
        result.cause = mcu_sleep::Cause::LINE;
        result.line = static_cast<int8_t>(mcu_sleep::woke(lineCount, levels, armed));
    } else result.cause = mcu_sleep::Cause::OTHER;
    return result;
}
#endif

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
