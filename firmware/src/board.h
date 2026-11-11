// SPDX-License-Identifier: MIT
// Wybór pliku opisu płytki według środowiska PlatformIO. Płytka nośna N1 (bench-n1, bench-b, l0)
// definiuje WICI_BOARD_N1: panel (CISZA, przycisk przygotowania, dioda alarmu, brzęczyk, VTEST)
// i linia DISP ekranu; prototyp płytki v2 (v2) ma te same i też go definiuje (board_v2.h). L0 i v2 definiują
// WICI_MCU_SLEEP: lekkie uśpienie z listami wyjść i linii budzenia (mcu_sleep.h). Zestaw XIAO (xiao) definiuje WICI_HEADLESS i WICI_FRAM_PSRAM (board_xiao.h).
#pragma once

#if defined(WICI_XIAO)
#include "board_xiao.h"
#elif defined(WICI_V2)
#include "board_v2.h"
#elif defined(WICI_L0)
#include "board_l0.h"
#elif defined(WICI_BENCH_B)
#include "board_bench_b.h"
#elif defined(WICI_BENCH_N1)
#include "board_bench_n1.h"
#elif defined(WICI_BENCH_A)
#include "board_bench_a.h"
#else
#error "Brak pliku opisu płytki: WICI_BENCH_A, WICI_BENCH_N1, WICI_BENCH_B, WICI_L0, WICI_V2 albo WICI_XIAO"
#endif
