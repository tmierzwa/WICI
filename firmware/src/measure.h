// SPDX-License-Identifier: MIT
// Polecenia pomiarowe interfejsu diagnostyki (docs/spec/radio.md, "USB do laptopa"):
// TXCW, TXPKT, RXPER, FOFF. Działają tylko w trybie przygotowania, podlegają ciszy
// radiowej i limitowi nadawania (dług ciszy 12 x czas TX zapisany w dzienniku FRAM
// przed serią, seria nie dłuższa niż najdłuższy datagram P1); dłuższą serię dopuszcza
// argument conducted potwierdzony przyciskiem OK w ciągu 30 s i zapisany w dzienniku.
#pragma once

#include <Arduino.h>

#include "cc1120.h"
#include "journal.h"
#include "p1frame.h"

namespace measure {

constexpr uint32_t CW_MAX_MS = 10000;         // TXCW <= 10 s (specyfikacja)
constexpr uint32_t SERIES_MAX_MS = 1400;      // najdłuższa seria P1: 7 ramek po 103 B z narastaniem
constexpr uint32_t CONFIRM_MS = 30000;        // potwierdzenie przyciskiem OK
constexpr size_t LOG_ENTRIES = 16;            // dziennik zapasowy w RAM, gdy nie ma FRAM
constexpr uint32_t CCA_MS = 50;               // kanał wolny przez 50 ms przed serią
constexpr uint32_t BACKOFF_MIN_MS = 100;      // odroczenie losowe 100..1000 ms
constexpr uint32_t BACKOFF_MAX_MS = 1000;
constexpr uint32_t LONG_DEFERRAL_MS = 1000;   // odroczenie łączne powyżej 1 s liczy się jako długie
constexpr uint8_t MAX_DEFERRALS = 30;         // potem datagram odrzucony (wybór stanowiska, tx_drop)

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

// Liczniki łącza P1 (pola INFO ze specyfikacji: rx_ok, rx_bad, tx_drop).
struct LinkCounters {
    uint32_t rxOk = 0;          // ramki P1 z poprawnym CRC i nagłówkiem
    uint32_t rxBad = 0;         // ramki odrzucone przy rozbiorze albo niekompletne w kolejce
    uint32_t rxDatagrams = 0;   // złożone datagramy
    uint32_t txDatagrams = 0;
    uint32_t txFragments = 0;
    uint32_t txDrop = 0;        // datagramy odrzucone (cisza, dziennik, zbyt wiele odroczeń)
    uint32_t deferrals = 0;     // odroczenia CCA
    uint32_t longDeferrals = 0; // nadania odroczone łącznie o ponad 1 s
};

enum class RxMode : uint8_t { NONE, TEST, P1 };

// Bajty losowe z generatora sprzętowego nRF52840 (RNG z korekcją obciążenia).
void randomBytes(uint8_t* out, size_t count);

class Bench {
public:
    Bench(cc1120::Radio& radio, uint8_t pinSync, uint8_t pinOk, uint8_t pinLed);

    bool prep = false;     // tryb przygotowania (na stacji: przycisk pod plombowaną pokrywą)
    bool silence = false;  // cisza radiowa (na stacji: przełącznik CISZA)

    // Dziennik FRAM i zegar czasu pracy; bez dziennika nadawanie radiowe jest zablokowane.
    void attach(journal::Journal* journal, uint32_t (*uptimeS)());
    // Dług odczytany z dziennika przy starcie: odczekiwany w całości, potem kasowany zapisem 0.
    void restoreDebt(uint32_t debtMs);

    // Każda funkcja zwraca nullptr po przyjęciu polecenia albo tekst błędu do odpowiedzi JSON.
    const char* txcw(uint32_t seconds, bool conducted);
    const char* txpkt(uint16_t count, uint8_t length, uint32_t intervalMs, bool conducted);
    const char* rxStart(uint8_t length);
    // Łącze P1: odbiór ramek P1 w tle (tryb zmiennej długości) i nadanie datagramu
    // z CCA 50 ms, odroczeniem losowym 100..1000 ms i długiem ciszy w dzienniku.
    const char* p1rxStart();
    const char* p1send(const uint8_t* data, size_t length);
    void printLink();
    const LinkCounters& link() const { return link_; }
    const char* foff(int32_t hz);
    void stop();         // przerwanie zadania i IDLE
    void poll();         // z loop(): nadawanie serii, odbiór ramek, koniec nośnej, kasowanie długu
    void rxper();        // drukuje i zeruje liczniki
    void printFoff();
    void printLog(uint32_t count);
    void printStatus();
    void log(const char* text);
    void applyOffset();  // ponowny zapis FREQOFF po CONFIG
    bool confirm();      // czeka na przycisk OK do CONFIRM_MS
    uint32_t debtRemainingMs() const;
    bool busy() const { return cwActive_ || pktActive_ || txState_ != TxState::IDLE; }
    bool receiving() const { return rxMode_ != RxMode::NONE; }
    const Counters& counters() const { return counters_; }

private:
    const char* gate(uint32_t txMs, bool conducted);  // tryb, cisza, dług, limit serii, potwierdzenie, zapis długu
    void stopCw();
    bool sendOne();
    void finishPkt();
    void receive();
    void receiveP1();
    bool enterRx(RxMode mode, uint8_t length);
    bool channelBusy();
    void pollP1Tx();
    bool sendFragments();
    void finishP1Tx(const char* result);
    bool waitSync(bool level, uint32_t timeoutUs);
    void restore(const char* name);
    uint32_t uptimeS() const { return uptime_ ? uptime_() : millis() / 1000; }

    cc1120::Radio& radio_;
    uint8_t pinSync_;
    uint8_t pinOk_;
    uint8_t pinLed_;
    journal::Journal* journal_ = nullptr;
    uint32_t (*uptime_)() = nullptr;

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

    RxMode rxMode_ = RxMode::NONE;
    uint8_t rxLen_ = 0;
    uint32_t rxPollMs_ = 0;
    Counters counters_;

    // Odbiór P1: bajt LEN odczytany, reszta ramki w drodze.
    uint8_t rxPendingLen_ = 0;
    uint32_t rxDeadlineMs_ = 0;
    p1frame::Assembler assembler_;
    LinkCounters link_;

    // Nadawanie P1: oczekiwanie na dług, CCA, odroczenie, seria fragmentów.
    enum class TxState : uint8_t { IDLE, WAIT_DEBT, CCA, BACKOFF, SEND };
    TxState txState_ = TxState::IDLE;
    uint8_t txData_[p1frame::MAX_DATAGRAM] = {};
    size_t txLength_ = 0;
    uint8_t txId_[p1frame::ID_BYTES] = {};
    uint32_t txRequestedMs_ = 0;
    uint32_t ccaStartMs_ = 0;
    uint32_t ccaCheckMs_ = 0;
    uint32_t backoffUntilMs_ = 0;
    uint8_t txDeferrals_ = 0;

    uint32_t debtUntilMs_ = 0;
    bool debtPending_ = false;   // dług zapisany w dzienniku, jeszcze nieskasowany
    int32_t foffHz_ = 0;
    bool foffSet_ = false;

    Event events_[LOG_ENTRIES];
    size_t eventCount_ = 0;
};

}  // namespace measure
