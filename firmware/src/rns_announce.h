// SPDX-License-Identifier: MIT
// Kiedy stacja ogłasza swój adres (docs/spec/oprogramowanie.md, "Ogłoszenia adresu"):
// - przy starcie z losowym opóźnieniem 0–120 s;
// - na polecenie opiekuna (request);
// - gdy od ostatniego ogłoszenia doszły 2 nieudane próby (brak potwierdzenia transportowego),
//   najwyżej raz na 30 min;
// - w ciszy radiowej i bez kodu IFAC (interfejs nie nadaje) nigdy; zaległe ogłoszenie czeka;
// - ogłoszenie, którego stos nie wysłał, wraca po 60 s.
// Adres OSP co 6 h ogłasza aplikacja OSP na komputerze stanowiska (D19); stacja w konfiguracji
// węzła OSP nie ma adresu LXMF i nie ogłasza się wcale (main.cpp nie używa wtedy tej polityki).
// Bez zależności od Arduino i od stosu; sprawdzany na komputerze (tests/test_rns_units.py).
#pragma once

#include <stdint.h>

namespace rnsannounce {

constexpr uint32_t START_DELAY_MAX_S = 120;
constexpr uint32_t AUTO_MIN_INTERVAL_S = 1800;
constexpr uint32_t AUTO_FAILURES = 2;
constexpr uint32_t RETRY_S = 60;

class Policy {
public:
    void begin(uint32_t nowS, uint32_t random) {
        scheduled_ = true;
        nextS_ = nowS + random % (START_DELAY_MAX_S + 1);
    }
    void request() { manual_ = true; }
    // failures: licznik nieudanych prób warstwy aplikacji (station::Stats::failed).
    bool due(uint32_t nowS, bool silence, bool online, uint32_t failures) const {
        if (silence || !online) return false;
        if (manual_) return true;
        if (scheduled_ && static_cast<int32_t>(nowS - nextS_) >= 0) return true;
        return failures - failuresAtLast_ >= AUTO_FAILURES && (!announced_ || nowS - lastS_ >= AUTO_MIN_INTERVAL_S);
    }
    void done(uint32_t nowS, uint32_t failures) {
        manual_ = false;
        announced_ = true;
        lastS_ = nowS;
        failuresAtLast_ = failures;
        scheduled_ = false;
    }
    // Stos nie wysłał ogłoszenia: ponowienie po RETRY_S (także zgłoszenia na polecenie).
    void failed(uint32_t nowS) {
        manual_ = false;
        scheduled_ = true;
        nextS_ = nowS + RETRY_S;
    }
    uint32_t count() const { return count_; }
    void counted() { ++count_; }
    bool scheduled() const { return scheduled_; }
    uint32_t nextS() const { return nextS_; }

private:
    bool scheduled_ = false;
    bool manual_ = false;
    bool announced_ = false;
    uint32_t nextS_ = 0;
    uint32_t lastS_ = 0;
    uint32_t failuresAtLast_ = 0;
    uint32_t count_ = 0;
};

}  // namespace rnsannounce
