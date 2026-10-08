// SPDX-License-Identifier: MIT
// Protokół USB laptop–stacja na interfejsie danych (docs/spec/oprogramowanie.md, "Protokół USB
// laptop–stacja"): wiersze UTF-8 JSON do 1024 B z numerem seq, kontrakt "usb":1, identyfikator
// sesji boot po obu stronach, sync z kursorem, submit -> stored/rejected po zapisie w FRAM,
// event/incoming -> ack, polecenia test, silence, configure, close, destroy, announce (export,
// import, trust i revoke odrzucane jako nieobsługiwane do czasu kluczy i kart). Każde polecenie trafia do dziennika zdarzeń.
// Bez zależności od Arduino; sprawdzany na komputerze.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "jsonlite.h"
#include "store.h"

namespace usbproto {

constexpr size_t MAX_LINE = 1024;
constexpr uint32_t CONTRACT = 1;
constexpr uint32_t RESEND_MS = 5000;  // ponowne wysłanie niepotwierdzonego zdarzenia
constexpr size_t BOOT_HEX = 16;

// Usługi stacji dla protokołu; dostarcza je main.cpp albo program testowy.
struct Host {
    virtual ~Host() = default;
    virtual uint32_t uptimeS() = 0;
    virtual bool prep() = 0;
    virtual bool silence() = 0;
    virtual void setSilence(bool on) = 0;
    virtual bool silenceSwitch() { return false; }  // przełącznik CISZA w położeniu „cisza”
    virtual bool confirm() = 0;  // przycisk OK na stacji w ciągu 30 s
    virtual void randomBytes(uint8_t* out, size_t count) = 0;
    virtual void log(const char* text) = 0;
    virtual void emit(const char* line) = 0;  // wiersz do laptopa bez znaku nowego wiersza
    virtual void stationAddress(uint8_t out[store::HASH]) = 0;
    virtual const char* stationName() = 0;
    virtual const char* version() = 0;
    virtual void configChanged() {}
    virtual void queueChanged() {}
    virtual bool eraseJournal() { return true; }  // ZNISZCZ DANE: dziennik zdarzeń poza magazynem
    virtual void destroyed() {}                   // ZNISZCZ DANE: tożsamość i tablice stosu poza magazynem
    virtual bool announce() { return false; }     // ogłoszenie adresu na polecenie; false = brak stosu
};

struct Stats {
    uint32_t linesIn = 0;
    uint32_t linesOut = 0;
    uint32_t rejected = 0;
    uint32_t stored = 0;
    uint32_t overflow = 0;   // wiersze dłuższe niż 1024 B albo z bajtem NUL
    uint32_t resends = 0;
};

class Protocol {
public:
    Protocol(store::Store& store, Host& host);
    void begin();                 // losowy identyfikator sesji
    void connected(uint32_t nowMs);   // port otwarty: wysyła sync
    void disconnected();          // port zamknięty: niepełny wiersz odrzucony
    bool isConnected() const { return connected_; }
    void feed(const char* bytes, size_t count, uint32_t nowMs);
    void handleLine(const char* line, uint32_t nowMs);
    void poll(uint32_t nowMs);
    // Zdarzenie stacji do laptopa: zapis w FRAM, wysłanie (gdy połączony), ponawianie do ack.
    bool event(uint8_t kind, uint32_t ref, const char* fields, uint32_t nowMs);
    const char* bootId() const { return boot_; }
    const Stats& stats() const { return stats_; }
    bool synced() const { return synced_; }

private:
    void send(const char* type, int64_t re, const char* fields);
    void rejected(int64_t re, const char* reason, const char* detail = nullptr);
    void sendSync(int64_t re);
    bool sendNote(uint32_t seq);
    void doSubmit(const json::Value& msg, int64_t seq);
    void doTest(int64_t seq);
    void doSilence(const json::Value& msg, int64_t seq);
    void doConfigure(const json::Value& msg, int64_t seq);
    void doAck(const json::Value& msg, uint32_t nowMs);
    void recipient(uint8_t out[store::HASH]) const;

    store::Store& store_;
    Host& host_;
    char boot_[BOOT_HEX + 1] = {};
    uint32_t seq_ = 0;
    bool connected_ = false;
    bool synced_ = false;
    uint32_t cursor_ = 0;        // ostatnie zdarzenie potwierdzone przez laptop
    uint32_t lastSentSeq_ = 0;
    uint32_t lastSentMs_ = 0;
    char line_[MAX_LINE + 1] = {};
    size_t lineLength_ = 0;
    bool overflow_ = false;
    Stats stats_;
};

}  // namespace usbproto
