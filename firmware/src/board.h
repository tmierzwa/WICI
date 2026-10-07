// SPDX-License-Identifier: MIT
// Wybór pliku opisu płytki według środowiska PlatformIO. Płytka nośna N1 (bench-n1, bench-b)
// definiuje WICI_BOARD_N1: panel (CISZA, przycisk przygotowania, dioda alarmu, brzęczyk, VTEST)
// i linia DISP ekranu.
#pragma once

#if defined(WICI_BENCH_B)
#include "board_bench_b.h"
#elif defined(WICI_BENCH_N1)
#include "board_bench_n1.h"
#elif defined(WICI_BENCH_A)
#include "board_bench_a.h"
#else
#error "Brak pliku opisu płytki: WICI_BENCH_A, WICI_BENCH_N1 albo WICI_BENCH_B"
#endif
