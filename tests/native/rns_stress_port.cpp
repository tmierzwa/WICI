// SPDX-License-Identifier: MIT
// Część próby odporności tylko dla stacji na porcie microReticulum (tests/test_rns_hostile.py buduje ją bez
// rdzenia): port i microStore mają widzieć zegar symulowany programu prób (rns_stress.cpp), inaczej próby
// czasu niczego nie sprawdzają. Osobny plik, bo nagłówki portu i rdzenia (Packet.h i packet.h) kolidują
// w systemie plików bez rozróżniania wielkości liter.
#include <stdint.h>

#include <microReticulum/Utilities/OS.h>
#include <microStore/Utility.h>

const char* stackClockError(uint64_t ms) {
    const double s = static_cast<double>(ms / 1000);
    const double stack = RNS::Utilities::OS::time();
    if (stack < s - 1 || stack > s + 1) return "stack does not follow the simulated clock";
    if (microStore::time() != static_cast<uint32_t>(ms / 1000)) return "microStore does not follow the simulated clock";
    if (microStore::millis() != static_cast<uint32_t>(ms)) return "microStore::millis does not follow the simulated clock";
    return nullptr;
}
