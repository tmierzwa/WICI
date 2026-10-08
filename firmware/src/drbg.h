// SPDX-License-Identifier: MIT
// Generator liczb losowych stacji (docs/spec/oprogramowanie.md, "Model zaufania i kluczy"):
// HMAC-DRBG z SHA-256 (NIST SP 800-90A Rev. 1, punkt 10.1.2) z ziarnem ze sprzętowego źródła
// entropii MCU (≥256 b: 48 B entropii i identyfikator układu jako nonce). Z niego pochodzą klucz
// tożsamości, `id` zgłoszeń, `epoch`, `boot`, `mid` i losowe opóźnienia; źródło sprzętowe działa
// tylko przy ziarnie (ESP32-S3: bootloader_random_enable() ze źródłem SAR ADC przed konfiguracją
// ADC pomiaru VTEST; nRF52840: RNG z korekcją obciążenia). Bez ziarna generator nie daje bajtów
// (ready() = false), a stacja nie tworzy tożsamości ani zgłoszeń.
// Bez zależności od Arduino; sprawdzany na komputerze wobec HMAC-DRBG z modułu hmac Pythona.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "sha2.h"

namespace drbg {

constexpr size_t SEED_ENTROPY = 48;   // 384 b: entropia i bezpieczeństwo 256 b według SP 800-90A, tabela 2

class Drbg {
public:
    // Instantiate: entropy ‖ nonce, bez ciągu personalizacji; ziarno krótsze niż 32 B nie uruchamia generatora.
    void seed(const uint8_t* entropy, size_t entropyLength, const uint8_t* nonce, size_t nonceLength);
    bool ready() const { return seeded_; }
    // Generate bez danych dodatkowych; do 65 536 B na wywołanie (SP 800-90A: max 2^19 b).
    bool generate(uint8_t* out, size_t length);

private:
    void update(const uint8_t* a, size_t aLength, const uint8_t* b = nullptr, size_t bLength = 0);
    uint8_t key_[sha2::DIGEST] = {};
    uint8_t value_[sha2::DIGEST] = {};
    bool seeded_ = false;
};

}  // namespace drbg
