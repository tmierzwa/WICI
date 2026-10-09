// SPDX-License-Identifier: MIT
// Protokół USB laptop–stacja, kontrakt "usb":2 (docs/spec/protokol-usb.md): koperta z `seq` i `re`,
// `hello` po otwarciu portu, `sync`/`ack`/`snapshot` nad pierścieniem zdarzeń w FRAM (store.h) z epoką,
// najwyżej 8 zdarzeń w drodze i ponowieniem po 5 s od `cursor` + 1, polecenia `submit`, `cancel`,
// `test`, `announce`, `silence`, `mark_read`, `status`, `close`, `destroy`, `card` i transfery
// `xfer_*` (`configure`, `config_get`). `silence`, `close` i `destroy` czekają na przycisk OK do 30 s
// bez blokowania pętli stacji (`pending`, potem wynik); w tym czasie inne polecenia dostają `busy`.
// Pole nieznane albo złego typu daje `invalid` z nazwą pola. Każde polecenie trafia do dziennika.
// Wyjście idzie przez kolejkę na jeden pełny wiersz, którą main.cpp opróżnia tyle, ile przyjmie port
// (zapis nie blokuje pętli stacji); następny wiersz wejścia jest czytany dopiero przy pustej kolejce,
// a migawka wychodzi wierszami w miarę miejsca. Laptop, który przestał czytać, wstrzymuje tylko siebie.
// Nie ma jeszcze PRZENIEŚ STACJĘ (`migrate`, `export`, `import`: odmowa `migration` albo `invalid`)
// ani aktualizacji oprogramowania (`firmware`), co opisuje przegląd (F107).
// Węzeł stanowiska używa protokołu tylko w trybie przygotowania; poza nim interfejs danych przenosi
// ramki KISS (rns_node.h), a polecenia stacji schronienia dają `role`.
// Bez zależności od Arduino; sprawdzany na komputerze.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "jsonlite.h"
#include "station.h"
#include "store.h"

namespace usbproto {

constexpr size_t MAX_LINE = 1024;
constexpr size_t LINE_ROOM = MAX_LINE + 1;      // wiersz z LF
// Kolejka wyjściowa: jeden pełny wiersz. Odpowiedź na wiersz wejścia to jeden wiersz, a dwa tylko przy
// odmowie `contract` (`rejected` do 160 B i `hello` do 460 B), więc pusta kolejka mieści każdą odpowiedź.
constexpr size_t OUT_BYTES = LINE_ROOM;
// Miejsce na odpowiedź po pytaniu przyciskiem (najdłuższa: `ok` polecenia `silence` z polami ciszy,
// do 230 B), którego zdarzenia nie zajmują.
constexpr size_t PENDING_RESERVE = 256;
constexpr uint32_t CONTRACT = 2;
constexpr uint32_t RESEND_MS = 5000;     // ponowienie zdarzeń bez `ack`
constexpr uint32_t WINDOW = 8;           // zdarzenia w drodze bez `ack`
constexpr uint32_t CONFIRM_MS = 30000;   // potwierdzenie przyciskiem OK
constexpr uint32_t XFER_IDLE_MS = 60000; // transfer bez części porzucany
constexpr uint32_t ANNOUNCE_MERGE_MS = 30000;
constexpr size_t PART_MAX = 512;         // dane binarne w jednym wierszu
constexpr size_t BOOT_HEX = 16;

enum class Question : uint8_t { SILENCE_ON, SILENCE_OFF, CLOSE, DESTROY, SILENCE_EXCEPTION };
enum class Confirm : uint8_t { WAITING, YES, NO };

// Usługi stacji dla protokołu; dostarcza je main.cpp albo program testowy.
struct Host {
    virtual ~Host() = default;
    virtual bool prep() = 0;
    virtual bool silenceSwitch() = 0;
    virtual void randomBytes(uint8_t* out, size_t count) = 0;
    virtual void log(const char* text) = 0;
    // Tożsamość stacji: klucz publiczny 64 B i adres LXMF; false bez tożsamości (węzeł, brak stosu).
    virtual bool identity(uint8_t key[64], uint8_t lxmf[store::HASH]) = 0;
    virtual const char* stationName() = 0;
    virtual const char* version() = 0;
    virtual uint32_t counterS() = 0;                       // licznik czasu pracy (journal.h)
    virtual bool contactBeforeStart() = 0;                 // ostatni kontakt sprzed tego startu (dolne oszacowanie)
    // Pola `power` i `diag` odpowiedzi `status` (obiekty JSON bez nawiasów zewnętrznych).
    virtual void power(char* out, size_t size) = 0;
    virtual void diag(char* out, size_t size) = 0;
    virtual bool announce() = 0;                           // ogłoszenie adresu; false: stos nie działa
    virtual bool destroy() = 0;                            // ZNISZCZ DANE: magazyn, dziennik, tożsamość
    virtual void configChanged(bool roleChanged) = 0;      // nowa konfiguracja (zmiana roli: restart)
    // Pytanie na ekranie; detail: krótki numer zgłoszenia dla SILENCE_EXCEPTION, inaczej pusty.
    virtual void confirmBegin(Question question, const char* detail) = 0;
    virtual Confirm confirmPoll() = 0;                     // OK = YES, WSTECZ = NO
    virtual void confirmEnd() = 0;
    virtual void showCard(const char* fingerprint) = 0;   // odcisk `card` na ekranie do porównania
};

struct Stats {
    uint32_t linesIn = 0;
    uint32_t linesOut = 0;
    uint32_t rejected = 0;
    uint32_t stored = 0;
    uint32_t overflow = 0;   // wiersze dłuższe niż 1024 B albo z bajtem NUL
    uint32_t resends = 0;
    uint32_t dropped = 0;    // wiersze bez miejsca w kolejce (błąd programu: wejście czeka na pustą kolejkę)
};

class Protocol {
public:
    Protocol(store::Store& store, station::Station& station, Host& host);
    void begin();                     // losowy identyfikator sesji `boot`
    void connected(uint32_t nowMs);   // port otwarty: `hello`
    void disconnected();              // port zamknięty: niepełny wiersz i oczekujące pytanie odrzucone
    bool isConnected() const { return connected_; }
    void feed(const char* bytes, size_t count, uint32_t nowMs);
    void handleLine(const char* line, uint32_t nowMs);
    void poll(uint32_t nowMs);        // migawka, zdarzenia, ponowienia, potwierdzenie przyciskiem, limit transferu
    // Następny wiersz wejścia może być przetworzony: kolejka pusta (każda odpowiedź się zmieści)
    // i migawka nie trwa. Inaczej port nie jest czytany, a wiersze czekają u laptopa.
    bool acceptsInput() const { return !snap_.active && outCount_ == 0; }
    bool snapshotActive() const { return snap_.active; }
    // Kolejka wyjściowa: ciągły fragment do zapisu w porcie i consume() z liczbą bajtów, które port
    // przyjął (zapis częściowy zostaje w kolejce).
    const char* output(size_t& length) const;
    void consume(size_t length);
    const char* bootId() const { return boot_; }
    const Stats& stats() const { return stats_; }
    bool synced() const { return synced_; }
    bool pending() const { return pending_.type != Pending::NONE; }

private:
    struct Pending {
        enum Type : uint8_t { NONE, SILENCE, CLOSE, DESTROY } type = NONE;
        int64_t seq = 0;
        uint32_t sinceMs = 0;
        bool on = false;
        bool exceptionSet = false;
        uint8_t exception[store::HASH] = {};
        uint8_t epoch[store::EPOCH] = {};
        uint32_t head = 0;
    };
    // Migawka w toku: wiersze `snap` po kolei z rejestru, pamięci zwolnionych wpisów i skrzynki.
    struct Snap {
        bool active = false;
        int64_t seq = 0;
        uint8_t phase = 0;
        size_t index = 0;
        uint32_t head = 0;
        uint32_t changes = 0;   // store::Store::changes() przy `snap_begin`
        uint8_t epoch[store::EPOCH] = {};
    };
    struct Xfer {
        enum Op : uint8_t { NONE, CONFIGURE, CONFIG_GET } op = NONE;
        uint32_t id = 0;
        uint32_t size = 0;
        uint32_t next = 0;
        uint8_t sha[32] = {};
        uint32_t lastMs = 0;
    };
    void send(const char* type, int64_t re, const char* fields);
    bool push(const char* type, int64_t re, const char* fields, size_t reserve);
    void rejected(int64_t re, const char* reason, const char* detail = nullptr);
    void hello();
    bool sendEvent(const store::Event& e);
    void loseSync(const char* reason);
    bool sendSnapRequired(int64_t re, const char* reason, size_t reserve);
    void dispatch(const char* type, const json::Value& msg, int64_t seq, uint32_t nowMs);
    void doSync(const json::Value& msg, int64_t seq, uint32_t nowMs);
    void doAck(const json::Value& msg, uint32_t nowMs);
    void doSnapshot(const json::Value& msg, int64_t seq);
    void continueSnapshot();
    bool snapItem(char* fields, size_t size);
    size_t room() const { return OUT_BYTES - outCount_; }
    void doSubmit(const json::Value& msg, int64_t seq);
    void doCancel(const json::Value& msg, int64_t seq);
    void doTest(const json::Value& msg, int64_t seq);
    void doSilence(const json::Value& msg, int64_t seq, uint32_t nowMs);
    void doClose(const json::Value& msg, int64_t seq, uint32_t nowMs);
    void doStatus(int64_t seq);
    void doCard(int64_t seq);
    void doXferBegin(const json::Value& msg, int64_t seq, uint32_t nowMs);
    void doXferPart(const json::Value& msg, int64_t seq, uint32_t nowMs);
    void doXferRead(const json::Value& msg, int64_t seq, uint32_t nowMs);
    void doXferCommit(const json::Value& msg, int64_t seq);
    void finishPending(bool confirmed);
    void stored(int64_t seq, const station::Stored& s);
    size_t requestFields(const store::Request& r, char* out, size_t size);
    size_t radioFields(char* out, size_t size, uint8_t bits, const uint8_t* exception, uint16_t revision, bool lost = false);
    size_t currentRadioFields(char* out, size_t size);
    bool xferOpen(const json::Value& msg, int64_t seq, uint32_t nowMs);

    store::Store& store_;
    station::Station& station_;
    Host& host_;
    char boot_[BOOT_HEX + 1] = {};
    uint32_t seqOut_ = 0;
    int64_t seqIn_ = 0;
    bool connected_ = false;
    bool synced_ = false;
    const char* lostSync_ = nullptr;   // powód `snap_required` bez `re` do wysłania po utracie synchronizacji
    uint8_t syncedEpoch_[store::EPOCH] = {};
    uint32_t cursor_ = 0;        // ostatnie zdarzenie potwierdzone przez laptop
    uint32_t nextEv_ = 0;        // następne zdarzenie do wysłania
    uint32_t lastSentMs_ = 0;
    uint32_t announceMs_ = 0;
    bool announced_ = false;
    Pending pending_;
    Snap snap_;
    Xfer xfer_;
    char out_[OUT_BYTES] = {};
    size_t outStart_ = 0;
    size_t outCount_ = 0;
    char line_[MAX_LINE + 1] = {};
    size_t lineLength_ = 0;
    bool overflow_ = false;
    Stats stats_;
};

// Base64 (RFC 4648, z dopełnieniem): zwraca długość albo -1 przy błędzie.
int base64Decode(const char* text, uint8_t* out, size_t size);
size_t base64Encode(const uint8_t* data, size_t length, char* out);

}  // namespace usbproto
