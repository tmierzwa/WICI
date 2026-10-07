// SPDX-License-Identifier: MIT
// Wiadomości SA1 (docs/spec/oprogramowanie.md, "Wiadomości SA1"): rozbiór i kontrola tablicy
// JSON, kodowanie kanoniczne (bez spacji, Unicode bez \u), limit 256 B treści, przejścia stanu
// STATUS (status_after) i kontrola konfiguracji przycisków, jak w software/reference/reference.py.
// Stacja nie sprawdza NFC ani znaków nieprzydzielonych (robi to laptop); odrzuca cudzysłów,
// odwrotny ukośnik, znaki sterujące, formatujące, separatory wierszy, obszar prywatny
// i niepoprawne UTF-8. Bez zależności od Arduino; sprawdzany na komputerze.
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

// Kontrola tekstu jak _text() modelu (bez NFC i Cn); zwraca nullptr albo powód.
const char* checkText(const char* text, size_t maximum, size_t minimum = 0);
// Rozbiór i kontrola tablicy z tekstu JSON; nullptr albo powód odrzucenia.
const char* decode(const char* wire, size_t length, Message& out);
// Kodowanie kanoniczne do bufora; 0 przy błędzie (również gdy treść przekracza 256 B).
size_t encode(const Message& message, char* out, size_t size);
// status_after modelu: nullptr i nowe (event, state) albo powód odrzucenia.
const char* statusAfter(uint32_t currentEvent, uint8_t currentState, uint32_t event, uint8_t state,
                        uint32_t& outEvent, uint8_t& outState);
// check_button_configuration modelu: największe zgłoszenie z przycisków; 0 (i powód), gdy przekracza limit.
size_t buttonConfigurationSize(const char* address, const char* const* phrases, size_t count, const char** reason = nullptr);
bool isHexId(const char* id);  // 32 małe cyfry szesnastkowe

}  // namespace sa1
