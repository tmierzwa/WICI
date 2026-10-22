// SPDX-License-Identifier: MIT
// RNG biblioteki Crypto w programie prób na hoście (tests/test_rns_hostile.py zamiast Crypto/RNG.cpp).
// Oryginał na hoście przy każdym przekluczeniu miesza micros() z zegara monotonicznego, więc klucze
// węzłów generatora, skróty losowe ogłoszeń i IV tokenów zależały od czasu rzeczywistego, nie od --seed.
// Tu stan zależy tylko od danych z stir(): rns_stress miesza ziarno --seed, a stacja portu swoje ziarno
// (rns_node.cpp), więc te same --seed i zegar symulowany dają te same bajty. Nie do obrazów: tylko próby.
#include <RNG.h>

#include <string.h>

namespace {

uint64_t state = 0x6a09e667f3bcc908ull;

// splitmix64 (Steele, Lea, Flood 2014): wystarcza do prób, nie do kryptografii.
uint64_t next() {
    uint64_t z = (state += 0x9e3779b97f4a7c15ull);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ull;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebull;
    return z ^ (z >> 31);
}

}  // namespace

RNGClass RNG;

RNGClass::RNGClass()
    : credits(0), firstSave(0), initialized(0), trngPending(0), timer(0), timeout(0), count(0), trngPosn(0) {
    memset(block, 0, sizeof(block));
    memset(stream, 0, sizeof(stream));
    memset(noiseSources, 0, sizeof(noiseSources));
}

RNGClass::~RNGClass() {}

void RNGClass::begin(const char*) { initialized = 1; }
void RNGClass::addNoiseSource(NoiseSource&) {}
void RNGClass::setAutoSaveTime(uint16_t) {}

void RNGClass::rand(uint8_t* data, size_t len) {
    while (len > 0) {
        const uint64_t r = next();
        const size_t n = len < sizeof(r) ? len : sizeof(r);
        memcpy(data, &r, n);
        data += n;
        len -= n;
    }
}

bool RNGClass::available(size_t) const { return true; }

void RNGClass::stir(const uint8_t* data, size_t len, unsigned int) {
    for (size_t i = 0; i < len; ++i) {
        state ^= data[i];
        next();
    }
}

void RNGClass::save() {}
void RNGClass::loop() {}
void RNGClass::destroy() {}
void RNGClass::rekey() {}
void RNGClass::mixTRNG() {}
