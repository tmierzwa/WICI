// SPDX-License-Identifier: MIT
// Wiadomości SA1 (docs/spec/oprogramowanie.md, "Wiadomości SA1"): rozbiór i kontrola tablicy
// JSON, kodowanie kanoniczne (bez spacji, Unicode bez \u), limit 256 B treści i kontrola konfiguracji
// przycisków, jak w software/reference/reference.py. Liczniki STATUS i REPLY stosuje station.cpp
// według "Cyklu życia zgłoszenia" (wyższy `event` wygrywa).
// Teksty sprawdza tak samo jak _text() modelu: odrzuca cudzysłów, odwrotny ukośnik, znaki
// z kategorii Cc, Cf, Cs, Co, Cn, Zl, Zp, tekst spoza NFC i niepoprawne UTF-8 (tablice
// unicode_tables.h z firmware/tools/unicode_tables.py, wersja Unicode ucd::UNIDATA_VERSION).
// Bez zależności od Arduino; sprawdzany na komputerze.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace sa1 {

constexpr size_t MAX_CONTENT = 256;   // cała treść po kodowaniu
constexpr size_t ID_HEX = 32;         // 16 losowych bajtów szesnastkowo
constexpr size_t LOCATION_MAX = 64;
constexpr size_t TEXT_MAX = 96;
constexpr size_t BULLETIN_MAX = 192;
constexpr uint16_t REVISION_MAX = 65535;
constexpr uint32_t EVENT_MAX = 2147483647;

enum Type : uint8_t { REQUEST = 0, RECEIVED = 1, STATUS = 2, REPLY = 3, BULLETIN = 4, TEST = 5 };

struct Message {
    uint8_t type = REQUEST;
    char id[ID_HEX + 1] = {};
    uint16_t revision = 0;     // nie dotyczy BULLETIN
    uint8_t category = 0;      // REQUEST, TEST
    uint16_t people = 0;
    char location[LOCATION_MAX + 1] = {};
    char text[BULLETIN_MAX + 1] = {};  // REQUEST, TEST, REPLY (<= 96 B), BULLETIN (<= 192 B)
    uint8_t urgency = 0;
    uint32_t event = 0;        // RECEIVED (1), STATUS, REPLY, BULLETIN
    uint8_t state = 0;         // RECEIVED (1), STATUS
};

// Kontrola tekstu jak _text() modelu, w tej samej kolejności (rozmiar, niepoprawne UTF-8,
// cudzysłów i ukośnik, kategoria, NFC); zwraca nullptr albo powód. Tekst dłuższy niż
// MAX_CONTENT jest zawsze odrzucany jako za długi (bufor kontroli NFC na stosie ok. 1,5 KB).
const char* checkText(const char* text, size_t maximum, size_t minimum = 0);
// Rozbiór i kontrola tablicy z tekstu JSON; nullptr albo powód odrzucenia.
const char* decode(const char* wire, size_t length, Message& out);
// Kodowanie kanoniczne do bufora; 0 przy błędzie (również gdy treść przekracza 256 B).
size_t encode(const Message& message, char* out, size_t size);
// check_button_configuration modelu: największe zgłoszenie z przycisków; 0 (i powód), gdy przekracza limit.
size_t buttonConfigurationSize(const char* address, const char* const* phrases, size_t count, const char** reason = nullptr);

}  // namespace sa1
