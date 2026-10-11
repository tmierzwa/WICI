// SPDX-License-Identifier: MIT
// ESP-IDF <esp_task_wdt.h> dla stosu: karmienie watchdoga zadania (vboard.h).
#pragma once
#include "vboard.h"
inline int esp_task_wdt_reset() { vb::feedTaskWatchdog(); return 0; }
