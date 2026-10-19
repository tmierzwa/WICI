// SPDX-License-Identifier: MIT
// Ramka wzorcowa poleceń TXPKT/RXPER: stała długość len (4..255 B; najdłuższą dla układu podaje
// radiolink::Driver::maxTestLength: P1 103 B, LoRa 255 B), numer porządkowy
// (2 B, starszy bajt pierwszy), wypełnienie pseudolosowe PN9 zależne od numeru albo same
// zera lub same jedynki (radio.md: odporność na długie ciągi jednakowych bitów),
// na końcu CRC-16 ramki P1 liczone z poprzedzających bajtów. Bez zależności od Arduino.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace testframe {

constexpr size_t MIN_LENGTH = 4;
constexpr size_t MAX_LENGTH = 255;  // najdłuższa ramka LoRa (SX1262); P1: 103 B (LEN + BODY + CRC)

enum class Fill : uint8_t { PN9, ZEROS, ONES };

// Wypełnia frame[0..length) ramką o numerze seq; zwraca false dla złej długości.
bool build(uint8_t* frame, size_t length, uint16_t seq, Fill fill = Fill::PN9);

// Sprawdza CRC i podaje numer; zwraca false przy złym CRC albo długości.
bool check(const uint8_t* frame, size_t length, uint16_t* seq);

}  // namespace testframe
