// SPDX-License-Identifier: MIT
// Kiedy stacja ogłasza swój adres (docs/spec/oprogramowanie.md, "Ogłoszenia adresu"):
// - przy starcie z losowym opóźnieniem 0–120 s;
// - na polecenie opiekuna (request);
// - rola stacji: gdy od ostatniego ogłoszenia doszły 2 nieudane próby (brak potwierdzenia
//   transportowego), najwyżej raz na 30 min;
// - rola OSP: co 6 h ±20% i po restarcie;
// - w ciszy radiowej i bez kodu IFAC (interfejs nie nadaje) nigdy; zaległe ogłoszenie czeka;
// - ogłoszenie, którego stos nie wysłał, wraca po 60 s.
// Bez zależności od Arduino i od stosu; sprawdzany na komputerze (tests/test_rns_units.py).
#pragma once

#include <stdint.h>

namespace rnsannounce {

constexpr uint32_t START_DELAY_MAX_S = 120;
constexpr uint32_t AUTO_MIN_INTERVAL_S = 1800;
constexpr uint32_t AUTO_FAILURES = 2;
constexpr uint32_t OSP_PERIOD_S = 6 * 3600;
constexpr uint32_t RETRY_S = 60;

class Policy {
public:
    void begin(bool osp, uint32_t nowS, uint32_t random) {
        osp_ = osp;
        scheduled_ = true;
        nextS_ = nowS + random % (START_DELAY_MAX_S + 1);
    }
    // Zmiana roli na OSP w czasie pracy (configure): ogłoszenie od razu, potem co 6 h.
    void setRole(bool osp, uint32_t nowS) {
        if (osp && !osp_ && !scheduled_) {
            scheduled_ = true;
            nextS_ = nowS;
        }
        osp_ = osp;
    }
    void request() { manual_ = true; }
    // failures: licznik nieudanych prób warstwy aplikacji (station::Stats::failed).
    bool due(uint32_t nowS, bool silence, bool online, uint32_t failures) const {
        if (silence || !online) return false;
        if (manual_) return true;
        if (scheduled_ && static_cast<int32_t>(nowS - nextS_) >= 0) return true;
        return !osp_ && failures - failuresAtLast_ >= AUTO_FAILURES && (!announced_ || nowS - lastS_ >= AUTO_MIN_INTERVAL_S);
    }
    void done(uint32_t nowS, uint32_t random, uint32_t failures) {
        manual_ = false;
        announced_ = true;
        lastS_ = nowS;
        failuresAtLast_ = failures;
        scheduled_ = osp_;
        if (osp_) nextS_ = nowS + OSP_PERIOD_S / 100 * (80 + random % 41);
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
    bool osp_ = false;
    bool scheduled_ = false;
    bool manual_ = false;
    bool announced_ = false;
    uint32_t nextS_ = 0;
    uint32_t lastS_ = 0;
    uint32_t failuresAtLast_ = 0;
    uint32_t count_ = 0;
};

}  // namespace rnsannounce
