// SPDX-License-Identifier: MIT
// ESP-IDF <esp_attr.h>: pamięć niezerowana przy restarcie programowym (RTC_NOINIT_ATTR) to w symulatorze
// osobny segment danych `wici_noinit`; środowisko przenosi go do nowej instancji przy restarcie, nie przy
// włączeniu zasilania (vboard.cpp, vb::noinit).
#pragma once
#define RTC_NOINIT_ATTR __attribute__((section("wici_noinit"), used))
