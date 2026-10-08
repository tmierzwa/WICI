// SPDX-License-Identifier: MIT
// Warstwa aplikacji stacji nad łączem P1 (docs/spec/oprogramowanie.md, "Trwałość i potwierdzenia",
// "Wiadomości SA1"): nadawanie intencji z kolejki w kolejności ze specyfikacji, ponawianie
// (1, 2, 5, 15 min ±20%, po 6 h co 60 min; po dostarczeniu 10 min na RECEIVED, potem 30–60 min),
// odbiór RECEIVED, STATUS, REPLY i BULLETIN do skrzynki tylko od przypiętej OSP, STATUS według
// status_after, zdarzenia do laptopa. Stacja ma jedną rolę: OSP działa na komputerze stanowiska
// (D19, docs/spec/stanowisko-osp.md), a stacja przy OSP tylko przekazuje ruch. Wiadomość idzie pakietem okazjonalnym Reticulum do celu "wici.sa1"
// odbiorcy (rns_node.h), szyfrowanym do jego tożsamości, a dostarczenie potwierdza dowód
// transportowy (PacketReceipt) zamiast dawnego datagramu "ack". Treść pakietu ma do czasu LXMF
// zastępczą kopertę ["WICI",1,od,do,<SA1>]: pakiet okazjonalny nie niesie adresu nadawcy, więc
// "od" jest w treści, bez podpisu (podpis i adres nadawcy da LXMF w następnym etapie T3).
// Bez zależności od Arduino i od stosu; sprawdzany na komputerze.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "store.h"

namespace station {

constexpr uint32_t ACK_TIMEOUT_S = 60;          // limit potwierdzenia transportowego (bez kolejki radiowej)
constexpr uint32_t RECEIPT_GUARD_S = 900;       // brak żadnego wyniku potwierdzenia od stosu = FAILED
constexpr uint32_t RECEIVED_WAIT_S = 600;       // po dostarczeniu: 10 min na RECEIVED
constexpr uint32_t RESEND_MIN_S = 1800;         // potem 30–60 min
constexpr uint32_t RESEND_MAX_S = 3600;
constexpr uint32_t FAILED_LATE_S = 6 * 3600;    // po 6 h co 60 min
constexpr uint32_t FAILED_LATE_INTERVAL_S = 3600;
// Treść pakietu okazjonalnego do celu SINGLE przy MTU 500 (Packet.ENCRYPTED_MDU w Reticulum);
// koperta z treścią SA1 do 256 B mieści się z zapasem.
constexpr size_t PACKET_MAX = 383;
constexpr uint32_t TEST_WINDOW_S = 900;             // TEST startowy bez liczby stacji: okno 15 min
constexpr uint32_t TEST_WINDOW_PER_STATION_S = 50;  // 50 s x liczba stacji z configure
constexpr uint32_t TEST_ALARM_S = 1800;             // brak_potwierdzenia dla TEST: 30 min od nadania
constexpr uint32_t READ_ALARM_S = 1800;             // brak_odczytu: 30 min od stanu 1 (pilność 2)
constexpr uint32_t CONFIRM_ALARM_S[3] = {6 * 3600, 3600, 900};  // brak_potwierdzenia według pilności 0, 1, 2

// Usługi stacji dla warstwy aplikacji (main.cpp albo program testowy).
struct Services {
    virtual ~Services() = default;
    virtual uint32_t uptimeS() = 0;
    virtual bool silence() = 0;
    virtual bool radioReady() = 0;                        // łącze P1 skonfigurowane i w odbiorze
    virtual bool busy() = 0;                              // kolejka radiowa pełna albo inne zadanie radia
    // Pakiet do celu "wici.sa1" stacji o adresie to z potwierdzeniem transportowym. Zwraca uchwyt
    // potwierdzenia albo 0 (cel jeszcze nieznany, interfejs odmówił); wynik przychodzi do
    // Station::receipt, najpóźniej po timeoutS i czasie oczekiwania w kolejce radiowej.
    virtual uint32_t send(const uint8_t to[store::HASH], const uint8_t* data, size_t length, uint32_t timeoutS) = 0;
    virtual void randomBytes(uint8_t* out, size_t count) = 0;
    virtual void log(const char* text) = 0;
    virtual bool notify(uint8_t kind, uint32_t ref, const char* fields) = 0;  // zdarzenie do laptopa
    virtual void address(uint8_t out[store::HASH]) = 0;   // własny adres
    virtual void changed() {}                             // odświeżenie ekranu
    virtual void destroyed() {}                           // ZNISZCZ DANE z menu: tożsamość i tablice stosu
    virtual bool announce() { return false; }             // OGŁOŚ ADRES z menu; false = stos nie działa
};

// Wynik utworzenia zgłoszenia z przycisków (REQUEST, TEST, nowa rewizja).
enum class Create : uint8_t { STORED, NO_ADDRESS, FULL, ERROR, TOO_LARGE, NOT_FOUND };

// Alarm ekranu (oprogramowanie.md, "Alarmy"): brak potwierdzenia albo brak odczytu zgłoszenia.
enum class AlarmKind : uint8_t { NONE, NO_CONFIRMATION, NO_READ };
struct Alarm {
    AlarmKind kind = AlarmKind::NONE;
    uint32_t seq = 0;        // intencja
    uint16_t number = 0;     // krótki numer
    uint32_t minutes = 0;    // czas bez potwierdzenia
};

struct Stats {
    uint32_t sent = 0;          // pakiety przyjęte przez stos
    uint32_t delivered = 0;     // potwierdzenia transportowe
    uint32_t failed = 0;        // brak potwierdzenia w czasie
    uint32_t refused = 0;       // stos nie przyjął pakietu (cel nieznany, pełna kolejka)
    uint32_t received = 0;      // pakiety z poprawnym formatem
    uint32_t rejected = 0;      // zły format, obcy adresat, nadawca spoza zaufania, zły typ
    uint32_t duplicates = 0;
    uint32_t conflicts = 0;
    uint32_t confirmed = 0;     // intencje zakończone RECEIVED/STATUS/REPLY
};

class Station {
public:
    Station(store::Store& store, Services& services);
    void poll(uint32_t nowMs);
    // Zaległe zdarzenia do laptopa dla wiadomości w skrzynce (INBOX_NOTIFY), najstarsze najpierw;
    // niezależne od radia i LINK, wołane razem z poll().
    void notifyPending();
    // Wynik potwierdzenia transportowego pakietu o uchwycie z Services::send.
    void receipt(uint32_t handle, bool delivered);
    // Pakiet do celu "wici.sa1" stacji; true = przyjęty (zapisany albo duplikat), wtedy stos
    // wysyła nadawcy dowód transportowy (rns_node.h, PROVE_APP).
    bool received(const uint8_t* data, size_t length);
    bool inFlight() const { return inFlightSeq_ != 0; }
    uint32_t inFlightSeq() const { return inFlightSeq_; }
    const Stats& stats() const { return stats_; }
    // Odstęp do następnej próby po nieudanej (failed) albo dostarczonej bez RECEIVED próbie.
    uint32_t retryDelayS(uint16_t attempts, bool delivered, uint32_t ageS, uint32_t random);
    // Intencja do nadania teraz (najwyższy priorytet, gotowa): 0, gdy brak.
    uint32_t nextToSend(uint32_t nowS) const;

    // Zgłoszenia z przycisków (oprogramowanie.md, "Zgłoszenie z przycisków"): location z adresu
    // konfiguracji, id losowane aż krótki numer będzie wolny, text = fraza PL albo pusty.
    Create createRequest(uint8_t category, uint16_t people, uint8_t urgency, const char* text, uint32_t& seq);
    // Nowa rewizja własnego zgłoszenia (ZMIEŃ LICZBĘ OSÓB, ZMIEŃ PILNOŚĆ, POTRZEBA USTAŁA):
    // ten sam id, revision + 1; nienadana starsza rewizja zostaje oznaczona jako zastąpiona.
    Create revise(uint32_t seq, uint16_t people, uint8_t urgency, const char* text, uint32_t& newSeq);
    // ANULUJ WYSYŁKĘ: tylko przed stanem 1; wpis w dzienniku zdarzeń przez log().
    bool cancel(uint32_t seq);
    // TEST z menu (od razu) albo startowy (losowe opóźnienie w oknie 50 s x liczba stacji, bez niej 15 min).
    Create scheduleTest(bool startup, uint32_t& seq);
    bool cancelTest();                     // anuluje TEST czekający na nadanie
    void pauseTest(bool paused);           // WSTRZYMAJ anuluje czekający TEST i blokuje nadawanie TEST
    bool testPaused() const { return testPaused_; }
    uint32_t pendingTest() const;          // seq TEST czekającego na nadanie; 0 gdy brak
    // Najpilniejszy niepotwierdzony alarm (bez potwierdzonych przez ackAlarm); false gdy brak.
    // withAcked = true: także potwierdzone, czyli przyczyna alarmu nadal trwa.
    bool alarm(uint32_t nowS, Alarm& out, bool withAcked = false) const;
    // Przyczyna alarmu trwa (dioda alarmu): potwierdzenie OK gasi dźwięk, nie diodę.
    bool alarmCause(uint32_t nowS) const { Alarm a; return alarm(nowS, a, true); }
    void ackAlarm(const Alarm& alarm);
    // Po ODBIORCA ZAPASOWY: niepotwierdzone intencje do nadania od razu, już do tożsamości zapasowej.
    void backupSwitched();

private:
    bool buildDatagram(const store::QueueRecord& record, char* out, size_t size, size_t& length);
    bool handleMessage(const uint8_t from[store::HASH], const sa1::Message& m, const char* wire, size_t wireLength);
    bool notifyInbox(const store::InboxRecord& record);   // zdarzenie do laptopa; true = zapisane w FRAM
    void attemptFailed(uint32_t seq);
    void finishIntent(store::QueueRecord& record, uint32_t event, uint8_t state);
    int priority(const store::QueueEntry& e) const;
    bool trustedSource(const uint8_t from[store::HASH]) const;
    Create putIntent(sa1::Message& m, uint8_t type, const uint8_t id[store::HASH], uint32_t delayS, uint32_t& seq);
    bool alarmAcked(size_t slot, const store::QueueEntry& e, AlarmKind kind) const;
    const uint8_t* recipient(const store::QueueRecord& r) const;

    store::Store& store_;
    Services& services_;
    Stats stats_;
    uint32_t inFlightSeq_ = 0;
    uint32_t inFlightHandle_ = 0;    // uchwyt potwierdzenia transportowego
    uint32_t inFlightSentS_ = 0;
    uint16_t refusals_ = 0;          // kolejne odmowy stosu (odstęp następnej próby)
    bool testPaused_ = false;
    // Potwierdzone alarmy według slotu kolejki: bit 0 brak potwierdzenia, bit 1 brak odczytu, ważne
    // tylko dla intencji o tym numerze (młodsze 16 bitów), bo zakończony slot dostaje nową intencję.
    uint8_t alarmAcked_[store::QUEUE_SLOTS] = {};
    uint16_t alarmAckedSeq_[store::QUEUE_SLOTS] = {};
};

}  // namespace station
