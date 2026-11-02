// SPDX-License-Identifier: MIT
// Sprawdzanie podpisów BEACON-ów poza pętlą stacji (wici-link.md, BEACON): pętla decyduje o HACK, a jedno
// sprawdzenie Ed25519 trwa dłużej niż 93 ms, które HACK ma po końcu odbioru. Obrazy z WICI-Link (l0, xiao,
// ESP32-S3, WICI_NO_P1_LINK) mają zadanie FreeRTOS na drugim rdzeniu niż pętla; pozostałe obrazy (bench-a,
// bench-n1, bench-b: bez SX1262 nie uruchamiają WICI-Link), symulator (obraz bench-b) i programy na komputerze
// nie mają zadania, więc wici_radio::Shelter sprawdza podpis na miejscu (deterministycznie w testach).
#pragma once

#include "wici_radio.h"

namespace beaconcheck {

#if defined(ARDUINO_ARCH_ESP32) && defined(WICI_NO_P1_LINK)
// Obraz z radiem WICI-Link wymaga zadania: bez niego WICI-Link nie startuje (main.cpp, beginWici), zamiast
// sprawdzać podpisy w pętli i spóźniać HACK. Ponowny start co 10 s próbuje utworzyć zadanie jeszcze raz.
constexpr bool REQUIRED = true;
// Zadanie powstaje przy pierwszym wywołaniu (z pętli); nullptr, gdy nie powstało.
wici_radio::BeaconCheck* worker();
int32_t stackFree();  // najmniejszy zapas stosu zadania od startu w bajtach; -1 bez zadania
#else
constexpr bool REQUIRED = false;
inline wici_radio::BeaconCheck* worker() { return nullptr; }
inline int32_t stackFree() { return -1; }
#endif

}  // namespace beaconcheck
