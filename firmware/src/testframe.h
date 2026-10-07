// SPDX-License-Identifier: MIT
// Ramka wzorcowa poleceń TXPKT/RXPER: stała długość len (4..103 B), numer porządkowy
// (2 B, starszy bajt pierwszy), wypełnienie pseudolosowe PN9 zależne od numeru,
// na końcu CRC-16 ramki P1 liczone z poprzedzających bajtów. Bez zależności od Arduino.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace testframe {

constexpr size_t MIN_LENGTH = 4;
constexpr size_t MAX_LENGTH = 103;  // najdłuższy pakiet P1 (LEN + BODY + CRC)

// Wypełnia frame[0..length) ramką o numerze seq; zwraca false dla złej długości.
bool build(uint8_t* frame, size_t length, uint16_t seq);

// Sprawdza CRC i podaje numer; zwraca false przy złym CRC albo długości.
bool check(const uint8_t* frame, size_t length, uint16_t* seq);

}  // namespace testframe
