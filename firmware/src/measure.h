// SPDX-License-Identifier: MIT
// Polecenia pomiarowe interfejsu diagnostyki (docs/spec/radio.md, "USB do laptopa"):
// TXCW, TXPKT, RXPER, FOFF. Działają tylko w trybie przygotowania, podlegają ciszy
// radiowej i limitowi nadawania (dług ciszy 12 x czas TX, seria nie dłuższa niż
// najdłuższy datagram P1); dłuższą serię dopuszcza argument conducted potwierdzony
// przyciskiem OK w ciągu 30 s i zapisany w dzienniku zdarzeń.
#pragma once

#include <Arduino.h>

#include "cc1120.h"

namespace measure {

constexpr uint32_t CW_MAX_MS = 10000;         // TXCW <= 10 s (specyfikacja)
constexpr uint32_t SERIES_MAX_MS = 1400;      // najdłuższa seria P1: 7 ramek po 103 B z narastaniem
constexpr uint8_t DEBT_FACTOR = 12;           // dług ciszy = 12 x czas nadawania
constexpr uint32_t CONFIRM_MS = 30000;        // potwierdzenie przyciskiem OK
constexpr size_t LOG_ENTRIES = 16;

struct Counters {
    uint32_t rxOk = 0;        // ramki z poprawnym CRC
    uint32_t rxBad = 0;       // ramki z błędnym CRC
    uint32_t missing = 0;     // brakujące numery porządkowe
    uint32_t reordered = 0;   // numer nie większy od poprzedniego (duplikat albo zmiana kolejności)
    uint32_t overflow = 0;    // przepełnienia kolejki RX
    bool haveSeq = false;
    uint16_t lastSeq = 0;
    int32_t rssiSum = 0;      // suma RSSI poprawnych ramek (dBm)
    uint32_t lqiSum = 0;
    uint32_t startedMs = 0;
};

struct Event {
    uint32_t ms;
    char text[40];
};

class Bench {
public:
    Bench(cc1120::Radio& radio, uint8_t pinSync, uint8_t pinOk, uint8_t pinLed);

    bool prep = false;     // tryb przygotowania (na stacji: przycisk pod plombowaną pokrywą)
    bool silence = false;  // cisza radiowa (na stacji: przełącznik CISZA)

    // Każda funkcja zwraca nullptr po przyjęciu polecenia albo tekst błędu do odpowiedzi JSON.
    const char* txcw(uint32_t seconds, bool conducted);
    const char* txpkt(uint16_t count, uint8_t length, uint32_t intervalMs, bool conducted);
    const char* rxStart(uint8_t length);
    const char* foff(int32_t hz);
    void stop();         // przerwanie zadania i IDLE
    void poll();         // z loop(): nadawanie serii, odbiór ramek, koniec nośnej
    void rxper();        // drukuje i zeruje liczniki
    void printFoff();
    void printLog();
    void printStatus();
    void log(const char* text);
    void applyOffset();  // ponowny zapis FREQOFF po CONFIG
    bool confirm();      // czeka na przycisk OK do CONFIRM_MS
    uint32_t debtRemainingMs() const;
    bool busy() const { return cwActive_ || pktActive_; }
    bool receiving() const { return rxActive_; }
    const Counters& counters() const { return counters_; }

private:
    const char* gate(uint32_t txMs, bool conducted);  // tryb, cisza, dług, limit serii, potwierdzenie
    void startDebt(uint32_t txMs);
    void stopCw();
    bool sendOne();
    void finishPkt();
    void receive();
    bool waitSync(bool level, uint32_t timeoutUs);
    void restore(const char* name);

    cc1120::Radio& radio_;
    uint8_t pinSync_;
    uint8_t pinOk_;
    uint8_t pinLed_;

    bool cwActive_ = false;
    uint32_t cwStartMs_ = 0;
    uint32_t cwEndMs_ = 0;

    bool pktActive_ = false;
    uint16_t pktTotal_ = 0;
    uint16_t pktSent_ = 0;
    uint8_t pktLen_ = 0;
    uint32_t pktIntervalMs_ = 0;
    uint32_t pktNextMs_ = 0;
    uint32_t pktStartMs_ = 0;
    uint32_t pktTxUs_ = 0;       // suma czasu od STX do IDLE
    uint32_t pktLeadUs_ = 0;     // pierwsza ramka: STX -> początek słowa synchronizacji
    uint32_t pktOnAirUs_ = 0;    // pierwsza ramka: słowo synchronizacji -> koniec pakietu
    uint32_t pktTailUs_ = 0;     // pierwsza ramka: koniec pakietu -> IDLE
    bool pktSyncSeen_ = false;
    bool pktConducted_ = false;
    uint16_t pktFailed_ = 0;

    bool rxActive_ = false;
    uint8_t rxLen_ = 0;
    uint32_t rxPollMs_ = 0;
    Counters counters_;

    uint32_t debtUntilMs_ = 0;
    int32_t foffHz_ = 0;
    bool foffSet_ = false;

    Event events_[LOG_ENTRIES];
    size_t eventCount_ = 0;
};

}  // namespace measure
