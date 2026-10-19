// SPDX-License-Identifier: MIT
// Profil LoRa pilotażu (docs/spec/radio.md, "Profil LoRa pilotażu") dla SX1262 i czas ramki w eterze
// (karta SX1261/2, rozdz. 6.1.4; ten sam wzór co lora_frame_seconds w software/reference/obliczenia.py).
// Inicjalizacja jak w programie diagnostycznym L0 (hardware/l0-diagnostic, RadioLib 7.6.0:
// SX1262::begin z TCXO 1,8 V, setRfSwitchPins(RXEN), setDio2AsRfSwitch, setRxBoostedGainMode),
// z mocą i preambułą profilu zamiast wartości diagnostycznych (0 dBm, 8 symboli).
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace lora {

constexpr uint32_t CARRIER_HZ = 869525000;
constexpr uint32_t BANDWIDTH_HZ = 125000;
constexpr uint8_t SPREADING_FACTOR = 7;
constexpr uint8_t CODING_RATE = 5;         // mianownik: 4/5 (w SetModulationParams kod 0x01)
constexpr bool LOW_DATA_RATE_OPTIMIZE = false;  // SF7, 125 kHz: symbol 1,024 ms < 16,38 ms
constexpr bool EXPLICIT_HEADER = true;
constexpr bool CRC_ON = true;
constexpr int8_t TX_POWER_DBM = 13;        // na złączu modułu; do pomiaru (R1-R3, T4)
// Do ustalenia wobec RNode (T3): specyfikacja przyjmuje 18 symboli preambuły jako założenie modelu;
// słowo 0x12 (prywatne LoRa) to wartość domyślna RadioLib i programu diagnostycznego L0.
constexpr uint16_t PREAMBLE_SYMBOLS = 18;
constexpr uint8_t SYNC_WORD = 0x12;
constexpr uint8_t SYNC_WORD_MSB = (SYNC_WORD & 0xF0) | 0x04;         // rejestry 0x0740/0x0741 jak w RadioLib
constexpr uint8_t SYNC_WORD_LSB = static_cast<uint8_t>((SYNC_WORD << 4) | 0x04);
constexpr uint16_t TCXO_MILLIVOLTS = 1800;  // DIO3 zasila TCXO modułu Wio-SX1262
constexpr uint32_t TCXO_DELAY_US = 5000;    // czas startu TCXO (domyślny RadioLib)
// Narastanie mocy, przełącznik RF i start nadajnika na ramkę: założenie jak w P1 (3 ms), do pomiaru
// w T4; rampa PA w SetTxParams to 200 µs.
constexpr uint32_t RAMP_MS = 3;
constexpr size_t MAX_PAYLOAD = 255;

constexpr uint32_t SYMBOL_US = (1u << SPREADING_FACTOR) * 1000000u / BANDWIDTH_HZ;  // 1024 µs

// Liczba symboli treści (z nagłówkiem jawnym i CRC): 8 + ceil((8 PL - 4 SF + 28 + 16 CRC - 20 IH) / (4 (SF - 2 DE))) (CR + 4),
// gdzie CR + 4 to mianownik kodowania (5 dla 4/5).
constexpr uint32_t payloadSymbols(size_t length) {
    const int32_t numerator = 8 * static_cast<int32_t>(length) - 4 * SPREADING_FACTOR + 28 + (CRC_ON ? 16 : 0) - (EXPLICIT_HEADER ? 0 : 20);
    const int32_t denominator = 4 * (SPREADING_FACTOR - (LOW_DATA_RATE_OPTIMIZE ? 2 : 0));
    const int32_t blocks = numerator > 0 ? (numerator + denominator - 1) / denominator : 0;
    return 8 + static_cast<uint32_t>(blocks) * CODING_RATE;
}

// Ramka w eterze w µs: (preambuła + 4,25 + symbole treści) x czas symbolu.
constexpr uint32_t frameAirUs(size_t length) {
    return (4 * PREAMBLE_SYMBOLS + 17 + 4 * payloadSymbols(length)) * SYMBOL_US / 4;
}

// Rezerwacja na ramkę do długu ciszy: w górę do ms, z narastaniem.
constexpr uint32_t frameAirMs(size_t length) { return (frameAirUs(length) + 999) / 1000 + RAMP_MS; }

// Najdłuższy datagram (508 B) to dwie ramki po 255 B jedną serią: limit serii pomiarowej bez CONDUCTED.
constexpr uint32_t SERIES_MAX_MS = 2 * frameAirMs(MAX_PAYLOAD);

static_assert(frameAirUs(255) == 409856, "255 B w SF7: 400,25 symbolu");
static_assert(SERIES_MAX_MS == 826, "dwie ramki 255 B z narastaniem");

}  // namespace lora
