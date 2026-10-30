// SPDX-License-Identifier: MIT
// Sterownik łącza pod blokadą operacji radia (platform::RadioLock) dla pętli stacji, gdy układ obsługuje
// też zadanie odbioru (stacja L0, plan interfejsu LoRa: „Blokady”, L6). measure::Bench dostaje ten widok
// zamiast sterownika, więc każda jego operacja na układzie idzie pod blokadą bez wyliczania miejsc wywołań;
// sekwencje kilku operacji (nadanie LoRa: prepareTx, CAD, dług, ramki) Bench trzyma pod blokadą sam,
// a mutex jest rekurencyjny. Zadanie odbioru używa sterownika wprost (z próbą blokady bez czekania).
// Pętla czeka na blokadę najwyżej waitMs; przekroczenie liczy platform::radioLockTimeouts(), a kontrola
// radia (radiocon::check) zamienia je w radio_awaria. Operacja bez blokady zwraca wynik błędu, z dwoma
// wyjątkami: idle() i stopCw() idą także bez niej, bo zatrzymanie nadawania jest ważniejsze (magistrala SPI
// i tak ma własną blokadę, a w nadawaniu zadanie nie obsługuje układu).
// Funkcje bez dostępu do układu (czas ramek, profil, znaczniki atomowe) idą bez blokady.
#pragma once

#include "platform.h"
#include "radio_link.h"

namespace radiolink {

class LockedDriver : public Driver {
public:
    // constexpr: stała inicjalizacja globalnego obiektu, zanim Bench z innej jednostki weźmie do niego referencję.
    constexpr LockedDriver(Driver& inner, uint32_t waitMs) : inner_(inner), waitMs_(waitMs) {}

    const char* stateName() override {
        platform::RadioLock lock(waitMs_);
        return lock.held() ? inner_.stateName() : "LOCK_TIMEOUT";
    }
    void idle() override {
        platform::RadioLock lock(waitMs_);
        inner_.idle();
    }
    bool startCw() override {
        platform::RadioLock lock(waitMs_);
        return lock.held() && inner_.startCw();
    }
    void stopCw() override {
        platform::RadioLock lock(waitMs_);
        inner_.stopCw();
    }
    bool transmit(const uint8_t* frame, size_t length, bool variable, TxTiming* timing) override {
        platform::RadioLock lock(waitMs_);
        if (lock.held()) return inner_.transmit(frame, length, variable, timing);
        if (timing) *timing = TxTiming{};
        return false;
    }
    bool startRx(bool variable, uint8_t fixedLength) override {
        platform::RadioLock lock(waitMs_);
        return lock.held() && inner_.startRx(variable, fixedLength);
    }
    RxPoll pollRx(Frame& out) override {
        platform::RadioLock lock(waitMs_);
        return lock.held() ? inner_.pollRx(out) : RxPoll::Nothing;
    }
    bool receivingFrame() override {
        platform::RadioLock lock(waitMs_);
        return lock.held() && inner_.receivingFrame();
    }
    Rssi rssi() override {
        platform::RadioLock lock(waitMs_);
        return lock.held() ? inner_.rssi() : Rssi{};
    }
    bool setFrequencyOffset(int32_t hz) override {
        platform::RadioLock lock(waitMs_);
        return lock.held() && inner_.setFrequencyOffset(hz);
    }
    void reapplyFrequencyOffset() override {
        platform::RadioLock lock(waitMs_);
        if (lock.held()) inner_.reapplyFrequencyOffset();
    }
    int32_t frequencyOffsetHz() override {
        platform::RadioLock lock(waitMs_);
        return lock.held() ? inner_.frequencyOffsetHz() : 0;
    }
    int32_t frequencyOffsetRaw() override {
        platform::RadioLock lock(waitMs_);
        return lock.held() ? inner_.frequencyOffsetRaw() : 0;
    }
    bool frequencyErrorHz(int32_t& hz) override {
        platform::RadioLock lock(waitMs_);
        return lock.held() && inner_.frequencyErrorHz(hz);
    }
    TxPrep prepareTx(const uint8_t* frame, size_t length) override {
        platform::RadioLock lock(waitMs_);
        return lock.held() ? inner_.prepareTx(frame, length) : TxPrep::Error;
    }
    Cad cad() override {
        platform::RadioLock lock(waitMs_);
        return lock.held() ? inner_.cad() : Cad::Error;
    }
    bool sendPrepared(TxTiming* timing) override {
        platform::RadioLock lock(waitMs_);
        return lock.held() && inner_.sendPrepared(timing);
    }

    // Bez dostępu do układu.
    double frequencyStepHz() const override { return inner_.frequencyStepHz(); }
    uint32_t frameAirMs(size_t length) const override { return inner_.frameAirMs(length); }
    double onAirMs(size_t length) const override { return inner_.onAirMs(length); }
    size_t maxTestLength() const override { return inner_.maxTestLength(); }
    uint32_t seriesMaxMs() const override { return inner_.seriesMaxMs(); }
    Framing framing() const override { return inner_.framing(); }
    bool hasSnr() const override { return inner_.hasSnr(); }
    int8_t ccaThresholdDbm() const override { return inner_.ccaThresholdDbm(); }
    Activity recentActivity(uint32_t windowMs) override { return inner_.recentActivity(windowMs); }
    void clearActivity() override { inner_.clearActivity(); }
    uint32_t rxLate() const override { return inner_.rxLate(); }
    uint32_t rxRingOverflow() const override { return inner_.rxRingOverflow(); }

private:
    Driver& inner_;
    uint32_t waitMs_;
};

}  // namespace radiolink
