// SPDX-License-Identifier: MIT
// Warstwa aplikacji stacji nad łączem P1 (docs/spec/oprogramowanie.md, "Trwałość i potwierdzenia",
// "Wiadomości SA1"): nadawanie intencji z kolejki w kolejności ze specyfikacji, ponawianie
// (1, 2, 5, 15 min ±20%, po 6 h co 60 min; po dostarczeniu 10 min na RECEIVED, potem 30–60 min),
// odbiór do skrzynki tylko od przypiętej OSP (rola stacji) albo od stacji (rola OSP), STATUS
// według status_after, zdarzenia do laptopa, odpowiedź stacji OSP zapisanym RECEIVED i STATUS
// na powtórzony REQUEST. Bez stosu Reticulum datagram ma zastępczy format
// ["WICI",1,od,do,<SA1>] i ["WICI",1,od,do,"ack",id,revision,typ,event] bez podpisu ani szyfrowania;
// zastępuje go LXMF w T3. Bez zależności od Arduino; sprawdzany na komputerze.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "store.h"

namespace station {

constexpr uint32_t ACK_TIMEOUT_S = 60;          // brak potwierdzenia łącza = FAILED
constexpr uint32_t RECEIVED_WAIT_S = 600;       // po dostarczeniu: 10 min na RECEIVED
constexpr uint32_t RESEND_MIN_S = 1800;         // potem 30–60 min
constexpr uint32_t RESEND_MAX_S = 3600;
constexpr uint32_t FAILED_LATE_S = 6 * 3600;    // po 6 h co 60 min
constexpr uint32_t FAILED_LATE_INTERVAL_S = 3600;
constexpr size_t DATAGRAM_MAX = 600;
constexpr uint8_t MAX_INFLIGHT = 1;

// Usługi stacji dla warstwy aplikacji (main.cpp albo program testowy).
struct Services {
    virtual ~Services() = default;
    virtual uint32_t uptimeS() = 0;
    virtual bool silence() = 0;
    virtual bool radioReady() = 0;                        // łącze P1 skonfigurowane i w odbiorze
    virtual bool busy() = 0;                              // trwa nadawanie albo inne zadanie radia
    virtual bool send(const uint8_t* data, size_t length) = 0;  // przekazanie datagramu do łącza
    virtual void randomBytes(uint8_t* out, size_t count) = 0;
    virtual void log(const char* text) = 0;
    virtual bool notify(uint8_t kind, uint32_t ref, const char* fields) = 0;  // zdarzenie do laptopa
    virtual void address(uint8_t out[store::HASH]) = 0;   // własny adres
    virtual void changed() {}                             // odświeżenie ekranu
};

struct Stats {
    uint32_t sent = 0;          // datagramy przekazane do łącza
    uint32_t delivered = 0;     // potwierdzenia łącza (ack)
    uint32_t failed = 0;        // brak ack w czasie
    uint32_t received = 0;      // datagramy z poprawnym formatem
    uint32_t rejected = 0;      // zły format, obcy adresat, nadawca spoza zaufania, zły typ
    uint32_t duplicates = 0;
    uint32_t conflicts = 0;
    uint32_t acksSent = 0;
    uint32_t confirmed = 0;     // intencje zakończone RECEIVED/STATUS/REPLY
};

class Station {
public:
    Station(store::Store& store, Services& services);
    void poll(uint32_t nowMs);
    void txDone(bool ok);
    void received(const uint8_t* data, size_t length);
    bool inFlight() const { return inFlightSeq_ != 0; }
    uint32_t inFlightSeq() const { return inFlightSeq_; }
    const Stats& stats() const { return stats_; }
    // Odstęp do następnej próby po nieudanej (failed) albo dostarczonej bez RECEIVED próbie.
    uint32_t retryDelayS(uint16_t attempts, bool delivered, uint32_t ageS, uint32_t random);
    // Intencja do nadania teraz (najwyższy priorytet, gotowa): 0, gdy brak.
    uint32_t nextToSend(uint32_t nowS) const;

private:
    bool buildDatagram(const store::QueueRecord& record, char* out, size_t size, size_t& length);
    void sendAck(const uint8_t to[store::HASH], const char* id, uint16_t revision, uint8_t type, uint32_t event);
    void handleMessage(const uint8_t from[store::HASH], const sa1::Message& m, const char* wire, size_t wireLength);
    void handleAck(const uint8_t from[store::HASH], const char* id, uint16_t revision, uint8_t type, uint32_t event);
    void finishIntent(store::QueueRecord& record, uint32_t event, uint8_t state);
    int priority(const store::QueueEntry& e) const;
    bool trustedSource(const uint8_t from[store::HASH]) const;

    store::Store& store_;
    Services& services_;
    Stats stats_;
    uint32_t inFlightSeq_ = 0;
    uint32_t inFlightSentS_ = 0;
    bool awaitingTx_ = false;
    bool pendingAck_ = false;        // ack do wysłania po bieżącym nadawaniu
    uint8_t ackTo_[store::HASH] = {};
    char ackId_[sa1::ID_HEX + 1] = {};
    uint16_t ackRevision_ = 0;
    uint8_t ackType_ = 0;
    uint32_t ackEvent_ = 0;
};

}  // namespace station
