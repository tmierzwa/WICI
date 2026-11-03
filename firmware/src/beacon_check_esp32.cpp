// SPDX-License-Identifier: MIT
// Zadanie sprawdzania podpisów BEACON-ów na ESP32-S3 (beacon_check.h).
#include "beacon_check.h"

#if defined(ARDUINO_ARCH_ESP32) && defined(WICI_NO_P1_LINK)

#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

namespace beaconcheck {
namespace {

// Rdzeń inny niż pętla stacji (loopTask, rdzeń 1), więc pętla i jej HACK nie czekają na sprawdzenie.
// Na rdzeniu 0 zadanie odbioru (configMAX_PRIORITIES - 2), USB i esp_timer mają wyższy priorytet
// i wywłaszczają sprawdzenie; niżej jest tylko zadanie bezczynności (bez watchdoga, idle_core_mask = 0).
constexpr UBaseType_t PRIORITY = tskIDLE_PRIORITY + 1;
// Ed25519::verify z SHA-512 i punktami krzywej zajmuje około 2 KiB stosu; zapas podaje HACK (beacon_stack_free).
constexpr size_t STACK_BYTES = 8192;
alignas(16) StackType_t stack[STACK_BYTES / sizeof(StackType_t)];
StaticTask_t storage;
TaskHandle_t task = nullptr;
// Ustawiane przez pętlę przed powiadomieniem, czytane przez zadanie po nim; Shelter daje jedno
// sprawdzenie naraz (gniazdo wolne dopiero po wyniku), więc zadanie czeka wtedy na powiadomienie.
void (*volatile pendingCheck)(void*) = nullptr;
void* volatile pendingJob = nullptr;

void taskMain(void*) {
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        if (pendingCheck) pendingCheck(pendingJob);
    }
}

struct Worker : wici_radio::BeaconCheck {
    bool start(void (*check)(void*), void* job) override {
        if (!task || !check) return false;
        pendingCheck = check;
        pendingJob = job;
        xTaskNotifyGive(task);
        return true;
    }
} instance;

}  // namespace

wici_radio::BeaconCheck* worker() {
    if (!task) {
        const BaseType_t core = xPortGetCoreID() ? 0 : 1;
        task = xTaskCreateStaticPinnedToCore(taskMain, "wici_beacon", sizeof(stack) / sizeof(StackType_t), nullptr,
                                                 PRIORITY, stack, &storage, core);
    }
    return task ? &instance : nullptr;
}

int32_t stackFree() {
    if (!task) return -1;
    return static_cast<int32_t>(uxTaskGetStackHighWaterMark(task) * sizeof(StackType_t));
}

}  // namespace beaconcheck

#endif
