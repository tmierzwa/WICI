// SPDX-License-Identifier: MIT
// Rozpoznanie FRAM SPI 4 Mbit po odpowiedzi RDID (0x9F). Oba układy mają ten sam zestaw poleceń
// (WREN, RDSR, READ, WRITE, adres 3-bajtowy, tryb SPI 0), więc sterownik różni się tylko tym.
// Bez zależności od Arduino; sprawdzane na komputerze w tests/test_firmware_host.py.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace fram {

// RDID zwraca 4 bajty (RAMXEED) albo 9 bajtów (Infineon); czyta się 9.
constexpr size_t ID_BYTES = 9;

enum class Part : uint8_t { UNKNOWN, MB85RS4MT, CY15B104Q };

// RAMXEED/Fujitsu MB85RS4MT: producent 0x04, kod kontynuacji 0x7F, produkt 0x49 0x03
// (MB85RS4MTY: 0x49 0x0B); tablica zgodna z biblioteką Adafruit_FRAM_SPI.
// Infineon (Cypress, dawniej Ramtron) CY15B104Q: sześć kodów kontynuacji 0x7F, producent 0xC2,
// produkt 0x26 0x08 (karta 001-94895, tabela „Device ID”): rodzina 001 i gęstość 00110 (4 Mbit)
// w pierwszym bajcie, podkod 00, wersja 001 i bity zarezerwowane w drugim. Wersja układu
// (bity 5–3) może się zmienić, więc sprawdza się tylko rodzinę, gęstość i podkod.
inline Part classify(const uint8_t id[ID_BYTES]) {
    if (id[0] == 0x04 && id[1] == 0x7F && id[2] == 0x49 && (id[3] == 0x03 || id[3] == 0x0B)) return Part::MB85RS4MT;
    for (size_t i = 0; i < 6; ++i) {
        if (id[i] != 0x7F) return Part::UNKNOWN;
    }
    if (id[6] == 0xC2 && id[7] == 0x26 && (id[8] & 0xC0) == 0) return Part::CY15B104Q;
    return Part::UNKNOWN;
}

inline const char* partName(Part part) {
    switch (part) {
        case Part::MB85RS4MT: return "MB85RS4MT";
        case Part::CY15B104Q: return "CY15B104Q";
        default: return "unknown";
    }
}

}  // namespace fram
