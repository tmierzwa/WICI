// SPDX-License-Identifier: MIT
// Warstwa aplikacji stacji (docs/spec/oprogramowanie.md, "Cykl życia zgłoszenia", "Trwałość
// i potwierdzenia", "Wysyłanie", "Tryby kryzysowe"): rejestr zgłoszeń z etapami wysyłki i decyzją
// odbiorcy, czynności lokalne (nowe zgłoszenie, rewizja, ANULUJ WYSYŁKĘ przed `nadane`, TEST,
// WSTRZYMAJ/WZNÓW, KLUCZ ZAPASOWY, zwolnienie wpisu zamkniętego), wysyłka najwyżej 2 własnych
// wiadomości naraz w kolejności REQUEST pilności 2, pozostałe REQUEST według COMMIT, TEST na końcu,
// ponowienia (po FAILED 1, 2, 5, 15 min ±20%, po 6 h co 60 min; po DELIVERED 10 min na RECEIVED,
// potem co 30–60 min), wiadomości od aktywnej tożsamości odbiorcy (RECEIVED, STATUS, REPLY, BULLETIN)
// z licznikami event i zbiorem powtórzeń BULLETIN, alarmy brak_potwierdzenia i brak_odczytu.
// Każda zmiana to jedna transakcja magazynu razem ze zdarzeniem dla laptopa (store.h).
//
// Wiadomość idzie pakietem okazjonalnym Reticulum do celu "wici.sa1" aktywnej tożsamości odbiorcy
// (klucz z karty, config.h), szyfrowanym do niej, z dowodem transportowym jako DELIVERED. Do czasu
// LXMF (D14) treść ma zastępczą kopertę ["WICI",1,od,do,<SA1>] bez podpisu: pakiet okazjonalny nie
// niesie adresu nadawcy. Dowód dla wiadomości przychodzącej stos wysyła dopiero po rozstrzygnięciu
// (received() = true: COMMIT albo trwałe odrzucenie); brak miejsca i błąd zapisu nie dają dowodu.
// Bez zależności od Arduino i od stosu; sprawdzany na komputerze.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "store.h"

namespace station {

constexpr size_t IN_FLIGHT = 2;                 // własne wiadomości przekazane naraz do stosu
constexpr uint32_t ACK_TIMEOUT_S = 60;          // limit potwierdzenia transportowego (bez kolejki radiowej)
constexpr uint32_t RECEIPT_GUARD_S = 900;       // brak wyniku potwierdzenia od stosu = FAILED
constexpr uint32_t RECEIVED_WAIT_S = 600;       // po DELIVERED: 10 min na RECEIVED
constexpr uint32_t RESEND_MIN_S = 1800;         // potem 30–60 min
constexpr uint32_t RESEND_MAX_S = 3600;
constexpr uint32_t FAILED_LATE_S = 6 * 3600;    // po 6 h od pierwszej próby co 60 min
constexpr uint32_t FAILED_LATE_INTERVAL_S = 3600;
// Treść pakietu okazjonalnego do celu SINGLE przy MTU 500 (Packet.ENCRYPTED_MDU w Reticulum).
constexpr size_t PACKET_MAX = 383;
constexpr uint32_t TEST_WINDOW_S = 900;             // TEST startowy bez liczby stacji: okno 15 min
constexpr uint32_t TEST_WINDOW_PER_STATION_S = 50;  // 50 s x liczba stacji z configure
constexpr uint32_t TEST_ALARM_S = 1800;             // brak_potwierdzenia TEST: 30 min od test_wyslany
constexpr uint32_t READ_ALARM_S = 1800;             // brak_odczytu: 30 min po RECEIVED r_max (pilność 2)
constexpr uint32_t CONFIRM_ALARM_S[3] = {6 * 3600, 3600, 900};  // brak_potwierdzenia według pilności 0, 1, 2
constexpr const char* RESOLVED_TEXT = "potrzeba ustała";        // POTRZEBA USTAŁA (fraza domyślna)

// Usługi stacji dla warstwy aplikacji (main.cpp albo program testowy).
struct Services {
    virtual ~Services() = default;
    virtual bool silence() = 0;                           // cisza radiowa (przełącznik albo panel)
    virtual bool silenceSwitch() = 0;                     // przełącznik CISZA w położeniu „cisza”
    virtual bool radioReady() = 0;                        // stos i interfejs radiowy nadają
    virtual bool busy() = 0;                              // kolejka radiowa pełna
    // Pakiet do celu `to` z potwierdzeniem transportowym; uchwyt potwierdzenia albo 0 (cel nieznany,
    // interfejs odmówił). Wynik przychodzi do Station::receipt.
    virtual uint32_t send(const uint8_t to[store::HASH], const uint8_t* data, size_t length, uint32_t timeoutS) = 0;
    virtual void randomBytes(uint8_t* out, size_t count) = 0;
    virtual void log(const char* text) = 0;
    virtual void address(uint8_t out[store::HASH]) = 0;   // własny cel "wici.sa1"
    virtual void changed() {}                             // odświeżenie ekranu
};

enum class Result : uint8_t {
    STORED, DUPLICATE, NO_CONFIG, NO_ADDRESS, FULL, NUMBER_TAKEN, CONFLICT, STALE, CLOSED, TOO_LATE, INVALID, MEMORY, NOT_FOUND
};
const char* resultName(Result result);   // przyczyna odmowy protokołu USB

enum class AlarmKind : uint8_t { NONE, NO_CONFIRMATION, NO_READ };
struct Alarm {
    AlarmKind kind = AlarmKind::NONE;
    uint16_t slot = 0;
    uint16_t gen = 0;
    uint16_t number = 0;
    uint32_t minutes = 0;
};

struct Stats {
    uint32_t sent = 0;          // pakiety przyjęte przez stos
    uint32_t delivered = 0;     // potwierdzenia transportowe
    uint32_t failed = 0;        // brak potwierdzenia w czasie albo odmowa stosu
    uint32_t received = 0;      // wiadomości od aktywnej tożsamości odbiorcy przyjęte albo pominięte
    uint32_t rejected = 0;      // zły format, obcy nadawca albo adresat, zły typ (z dowodem)
    uint32_t skipped = 0;       // spoza rejestru, r > r_max, powtórzenia, spóźnione, anulowane
    uint32_t bulletinsSkipped = 0;
    uint32_t inboxFull = 0;     // wiadomość nieprzyjęta z braku miejsca (bez dowodu)
    uint32_t evicted = 0;       // nieprzeczytany BULLETIN usunięty ze skrzynki
};

// Wynik zapisu z `submit` albo `test` (odpowiedź `stored`).
struct Stored {
    uint8_t id[store::HASH] = {};
    uint16_t revision = 0;
    uint16_t number = 0;
    bool duplicate = false;
    bool released = false;
};

class Station {
public:
    Station(store::Store& store, Services& services);
    void poll();
    void receipt(uint32_t handle, bool delivered);
    // Pakiet do celu "wici.sa1" stacji: true = rozstrzygnięty (stos wysyła dowód).
    bool received(const uint8_t* data, size_t length);
    // Ostatni pakiet z received() dotyczył zgłoszenia z wyjątkiem ciszy (jego dowód może wyjść w ciszy).
    bool exceptionTraffic() const { return exceptionTraffic_; }
    const Stats& stats() const { return stats_; }
    size_t inFlight() const;
    // Odstęp następnej próby (random: liczba losowa do ±20% i 30–60 min).
    static uint32_t retryDelayS(uint16_t attempts, bool delivered, uint32_t ageS, uint32_t random);
    int nextToSend() const;     // gniazdo do nadania teraz albo -1

    // Zgłoszenie z przycisków: location z wybranego obiektu, text = fraza PL albo pusty.
    Result create(uint8_t category, uint16_t people, uint8_t urgency, const char* text, uint16_t& number);
    // Nowa rewizja (ZMIEŃ LICZBĘ OSÓB, ZMIEŃ PILNOŚĆ, POTRZEBA USTAŁA; text = nullptr: bez zmiany).
    Result revise(uint16_t slot, uint16_t people, uint8_t urgency, const char* text);
    // `submit` z laptopa: tablica REQUEST albo TEST po kontroli SA1 (protokol-usb.md, reguły submit).
    Result submit(const sa1::Message& m, Stored& out);
    // ANULUJ WYSYŁKĘ (menu i `cancel`): tylko przed `nadane`. released: id ze zwolnionego wpisu anulowanego.
    Result cancel(const uint8_t id[store::HASH], bool& released);
    // TEST z menu (od razu) albo startowy (losowe opóźnienie w oknie 50 s x liczba stacji, bez niej 15 min).
    Result scheduleTest(bool startup);
    // `test` z laptopa: nonce chroni przed podwójnym TEST (8 ostatnich w meta).
    Result test(const uint8_t nonce[store::NONCE], Stored& out);
    bool cancelTest();                     // TEST czekający na pierwsze nadanie
    bool pauseTest(bool paused);           // WSTRZYMAJ anuluje czekający TEST
    bool testPaused() const { return store_.meta().testPaused; }
    int pendingTest() const;               // gniazdo TEST przed pierwszym nadaniem albo -1
    int latestTest() const;                // najnowszy TEST albo -1
    bool switchBackup();                   // KLUCZ ZAPASOWY (nieodwracalny poza przygotowaniem)
    bool markRead(uint32_t number);        // wiadomość skrzynki
    // Ustawienia ciszy z panelu (meta) i zdarzenie `radio`; switchOn: położenie przełącznika.
    bool setSilence(bool on, const uint8_t* exception, bool switchOn);
    bool radioEvent(bool switchOn);
    bool stationEvent(store::StationWhat what, uint32_t detail);   // zdarzenie `station` (restart, przygotowanie)

    // Najpilniejszy alarm (bez potwierdzonych przez ackAlarm, chyba że withAcked).
    bool alarm(Alarm& out, bool withAcked = false) const;
    bool alarmCause() const { Alarm a; return alarm(a, true); }
    void ackAlarm(const Alarm& alarm);

private:
    struct Flight {
        int16_t slot = -1;
        uint16_t gen = 0;
        uint16_t revision = 0;
        uint32_t handle = 0;
        uint32_t sentS = 0;
    };
    bool transmit(uint16_t slot);
    void finishFlight(Flight& f, bool delivered);
    bool silencedFor(const store::RequestIndex& r) const;
    const store::RequestIndex* exceptionEntry() const;   // wpis rejestru z wyjątkiem ciszy albo nullptr
    bool due(const store::RequestIndex& r) const;
    bool handleOwn(const sa1::Message& m, const uint8_t id[store::HASH], const char* wire, size_t wireLength);
    bool handleBulletin(const sa1::Message& m, const uint8_t id[store::HASH], const char* wire, size_t wireLength);
    int inboxSlot();
    bool addMessage(store::Tx& tx, const sa1::Message& m, const uint8_t id[store::HASH], const char* wire, size_t wireLength);
    bool releaseOne();
    Result save(store::Request& r, int slot, uint8_t origin, uint16_t& gen, const uint8_t* nonce);
    Result revision(uint16_t slot, store::Request& r, const sa1::Message& m, const char* wire, size_t length, uint8_t origin);
    Result createWith(uint8_t type, uint8_t category, uint16_t people, uint8_t urgency, const char* location, const char* text,
                      uint32_t delayS, uint8_t origin, const uint8_t* nonce, uint8_t id[store::HASH], uint16_t& number);
    uint32_t random32();
    void stageEvent(store::Tx& tx, uint16_t slot, uint16_t gen, const store::Request& r, store::StageCode code, bool decisionChanged);
    void touchContact(store::Tx& tx);
    void markCancelled(store::Tx& tx, uint16_t slot, store::Request& r);   // ANULUJ albo WSTRZYMAJ TEST
    bool note(const store::Event& e);   // samo zdarzenie w jednej transakcji

    store::Store& store_;
    Services& services_;
    Stats stats_;
    bool exceptionTraffic_ = false;
    // Gniazdo wpisu z wyjątkiem ciszy (indeks ma tylko przedrostek id, więc pełne id sprawdza odczyt rekordu).
    mutable int exceptionSlot_ = -1;
    mutable uint16_t exceptionGen_ = 0;
    mutable uint8_t exceptionId_[store::HASH] = {};
    Flight flights_[IN_FLIGHT];
    // Potwierdzone alarmy według gniazda (bit 0 brak potwierdzenia, bit 1 brak odczytu) dla generacji gniazda.
    uint8_t alarmAcked_[store::REGISTER_SLOTS] = {};
    uint16_t alarmAckedGen_[store::REGISTER_SLOTS] = {};
};

}  // namespace station
