// SPDX-License-Identifier: MIT
// Układ radiowy stanowiska w programie stacji (main.cpp): sterownik układu, sterownik łącza dla
// measure::Bench, start z konfiguracją P1 i polecenia diagnostyczne zależne od układu (RADIO,
// RESET, CONFIG, VERIFY, FREQ, RSSI, STATE, REG, IDLE; CC1120: CAL; S2-LP: SDN, REGW). Wykonania:
// radio_console_cc1120.cpp (stanowisko A) i radio_console_s2lp.cpp (stanowisko B).
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
// Kontrola sprawności w pracy (main.cpp co CHECK_MS, gdy łącze nie nadaje): numer części i słowo
// synchronizacji P1, które po resecie albo zaniku zasilania układu wraca do wartości domyślnej.
// Układ, który stracił konfigurację P1, dostaje ją od nowa (true: odbiór trzeba wznowić); układ,
// który nie odpowiada, jest niesprawny do następnej udanej kontroli. Brak ruchu nie jest awarią.
constexpr uint32_t CHECK_MS = 10000;
bool check();

// Wpis tablicy rejestrów o nazwie name albo nullptr.
template <typename Register>
const Register* findRegister(const Register* table, size_t count, const char* name) {
    for (size_t i = 0; i < count; ++i) if (!strcmp(table[i].name, name)) return &table[i];
    return nullptr;
}
constexpr size_t SYNC_REGISTERS = 4;   // SYNC3..SYNC0, kolejne wpisy tablicy P1

void report();       // raport po otwarciu portu diagnostyki: RADIO, VERIFY, FREQ
void printState();   // stan układu (STATE; także po RX, STOP i IDLE)
// Polecenia układu; false, gdy polecenie nie należy do układu.
bool handle(const char* cmd, char* words[], size_t n);
const char* helpCommands();  // lista do HELP, z przecinkiem na początku

}  // namespace radiocon
