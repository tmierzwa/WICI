// SPDX-License-Identifier: MIT
// Układ radiowy stanowiska w programie stacji (main.cpp): sterownik układu, sterownik łącza dla
// measure::Bench, start z konfiguracją P1 i polecenia diagnostyczne zależne od układu (RADIO,
// RESET, CONFIG, VERIFY, CAL, FREQ, RSSI, STATE, REG, IDLE, SDN). Wykonania:
// radio_console_cc1120.cpp (stanowisko A) i radio_console_s2lp.cpp (stanowisko B); odpowiedzi
// stanowiska A bez zmian względem wcześniejszego main.cpp.
#pragma once

#include <Arduino.h>

#include "measure.h"
#include "radio_link.h"

namespace radiocon {

extern const char* const NAME;  // pole "radio" w INFO: "CC1120" albo "S2LP"
extern const uint16_t RX_FILTER_HZ;  // pasmo filtru odbiornika z tablicy rejestrów układu
extern const int8_t TX_POWER_DBM;

radiolink::Driver& link();
void attach(measure::Bench& bench);  // przed begin(): STOP pomiarów i FOFF po ponownej konfiguracji

void begin();  // piny układu (przed platform::beginBus)
// Reset, identyfikacja i zapis tablicy P1 (CC1120: z kalibracją syntezera).
void start();
bool ok();    // układ odpowiada właściwym numerem części
bool p1Ok();  // tablica P1 zapisana i zweryfikowana (CC1120: także skalibrowany syntezer)

void report();       // raport po otwarciu portu diagnostyki: RADIO, VERIFY, FREQ
void printState();   // stan układu (STATE; także po RX, STOP i IDLE)
// Polecenia układu; false, gdy polecenie nie należy do układu.
bool handle(const char* cmd, char* words[], size_t n);
const char* helpCommands();  // lista do HELP, z przecinkiem na początku

}  // namespace radiocon
