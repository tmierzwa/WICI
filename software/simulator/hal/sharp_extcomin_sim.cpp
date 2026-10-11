// SPDX-License-Identifier: MIT
// EXTCOMIN ekranu Sharp w symulatorze w miejsce sharp_extcomin_esp32.cpp: licznik wirtualnej płytki
// przełącza pin co 500 ms bez udziału programu, jak MCPWM na ESP32-S3.
#include "sharp.h"

namespace sharp {

bool Display::beginExtcomin() {
    pinMode(pinExtcomin_, OUTPUT);
    return vb::extcominStart(pinExtcomin_);
}

uint32_t Display::extcominCounter() const { return vb::extcominTicks(); }

bool Display::extcominLevel() const { return digitalRead(pinExtcomin_) != 0; }

}  // namespace sharp
