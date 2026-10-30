// SPDX-License-Identifier: MIT
// Polecenia pomiarowe interfejsu diagnostyki (docs/spec/radio.md, "USB do laptopa"):
// TXCW, TXPKT, RX, FOFF (RXPER tylko czyta liczniki). Działają tylko w trybie przygotowania
// i przy zapisanym profilu układu (P1 albo LoRa), podlegają ciszy radiowej i limitowi nadawania (dług ciszy 12 x czas TX
// zapisany w dzienniku FRAM przed serią, seria nie dłuższa niż najdłuższy datagram profilu); dłuższą serię dopuszcza
// argument conducted potwierdzony przyciskiem OK w ciągu 30 s i zapisany w dzienniku.
// Operacje układu radiowego idą przez radiolink::Driver (CC1120: cc1120_link.cpp, S2-LP:
// s2lp_link.cpp, SX1262: sx1262_link.cpp), czas ramki w eterze też; reszta, w tym łącze P1, jest
// wspólna. Łącze P1 działa tylko na układzie, który je ma (Driver::p1Link).
//
// Łącze stosu (linkSend, odbiór w tle): część wspólna (dług ciszy z dziennika, CCA, odroczenia, cisza
// z wyjątkiem, zwrotne wywołania) i ramkowanie z układu (Driver::framing):
// - P1 (CC1120, S2-LP): fragmenty p1frame, CCA próbkowane w pętli przez 50 ms, rezerwacja z najdłuższych ramek;
// - RNode (SX1262, radio.md, „Ramka w eterze” i „Dostęp do kanału”, punkt 5): 1 albo 2 ramki loraframe,
//   kolejno: dług z dziennika, 50 ms bez aktywności ze znaczników próbek odbioru (postój pętli nie zrywa
//   okna), wyjście z odbioru z załadowaniem ramki 1 (nieodczytana ramka odracza), CAD (zajęty kanał odracza
//   bez zapisu długu), zapis długu 12 x dokładny czas ramek (błąd: powrót do odbioru bez nadania), ramka 1,
//   ramka 2, odbiór. Całość pod blokadą operacji radia (platform::RadioLock), bo obok pętli układ obsługuje
//   zadanie odbioru (L0).
// Obraz z flagą WICI_NO_P1_LINK (l0, l0-port) nie ma składania P1 (8 x 600 B RAM).
//
// Tryb pracy do badań EMC (EMC, Issue #21 punkt 5): reszta stacji pracuje normalnie, a radio co `period` s nadaje
// jedną ramkę wzorcową `len` B z kolejnym numerem i między ramkami odbiera ramki wzorcowe tej samej
// długości (liczniki jak RX, odczyt RXPER), np. od drugiej stacji w roli stacji pomocniczej.
// Każda ramka ma dług ciszy 12 x czas ramki zapisany w dzienniku przed nadaniem, a okres jest nie
// krótszy niż 13 x czas ramki, więc cisza mija przed następną ramką, a cykl pracy ≤ 1/13 (< 10 %
// w godzinie). Bez CCA, jak TXPKT. Cisza radiowa pomija ramki, odbiór trwa; nadawanie stosu stoi. Włączenie tylko w trybie przygotowania;
// tryb zapisany w dzienniku FRAM (rekord ustawień) wraca sam po restarcie także bez trybu
// przygotowania, żeby laboratorium widziało powrót funkcji bez obsługi (kryterium B badań odporności).
// Kończy go EMC 0 albo STOP; wyjście z trybu przygotowania go nie kończy.
#pragma once

#include <Arduino.h>

#include "journal.h"
#include "loraframe.h"
#include "p1frame.h"
#include "radio_link.h"
#include "testframe.h"

namespace measure {

constexpr uint32_t CW_MAX_MS = 10000;         // TXCW <= 10 s (specyfikacja)
// Najdłuższa seria każdego profilu (P1: 7 ramek po 103 B z narastaniem; LoRa: dwie ramki 255 B, ≤ tyle).
constexpr uint32_t SERIES_MAX_MS = radiolink::P1_SERIES_MAX_MS;
// Największy dług, jaki stanowisko zapisuje (seria do SERIES_MAX_MS i rezerwacja datagramu P1
// z 7 najdłuższych ramek, 1365 ms): odczekiwany po starcie bez poprawnego rekordu długu.
// Górna granica wszystkich profili; obraz odczekuje dług swojego łącza (Bench::maxDebtMs).
constexpr uint32_t MAX_DEBT_MS = SERIES_MAX_MS * 12;
constexpr uint32_t CONFIRM_MS = 30000;        // potwierdzenie przyciskiem OK
// FOFF: kanał LoRa 125 kHz ze środkiem 869,525 MHz mieści się w podpaśmie 869,4–869,65 MHz tylko przy
// przesunięciu ≤ 62,5 kHz (radio.md, "Współdzielenie kanału"); granica z zapasem także dla P1. Błąd
// kwarcu modułów (±20 ppm, około 17 kHz) mieści się w niej, a pomyłka o rząd wielkości nie wyprowadzi
// nadawania poza podpasmo.
constexpr int32_t FOFF_MAX_HZ = 50000;
constexpr size_t LOG_ENTRIES = 16;            // dziennik zapasowy w RAM, gdy nie ma FRAM
constexpr uint32_t CCA_MS = 50;               // kanał wolny przez 50 ms przed serią
constexpr uint32_t CCA_GAP_MS = 10;           // przerwa między próbkami CCA ponad tyle zaczyna okno od nowa
constexpr uint32_t BACKOFF_MIN_MS = 100;      // odroczenie losowe 100..1000 ms
constexpr uint32_t BACKOFF_MAX_MS = 1000;
constexpr uint32_t LONG_DEFERRAL_MS = 1000;   // odroczenie łączne powyżej 1 s liczy się jako długie
constexpr uint8_t MAX_DEFERRALS = 30;         // potem datagram odrzucony (wybór stanowiska, tx_drop)
// Pętla czeka na blokadę operacji radia najwyżej tyle (zadanie odbioru trzyma ją ≤5 ms, ekran ≤5 ms).
constexpr uint32_t RADIO_LOCK_WAIT_MS = 500;
constexpr uint32_t EMC_PERIOD_MAX_S = 3600;
constexpr uint32_t EMC_PERIOD_FACTOR = 13;    // okres ≥ 13 x czas ramki: ramka i jej dług ciszy 12 x

// Rekord trybu EMC w dzienniku (journal::Journal::writeEmc): znacznik, długość ramki i okres [s].
constexpr uint32_t EMC_ON = 0x80000000u;
constexpr uint32_t emcEncode(uint32_t periodS, uint8_t length) { return EMC_ON | (static_cast<uint32_t>(length) << 16) | (periodS & 0xFFFF); }
constexpr uint32_t emcPeriodS(uint32_t mode) { return mode & 0xFFFF; }
constexpr uint8_t emcLength(uint32_t mode) { return static_cast<uint8_t>(mode >> 16); }

struct Counters {
    uint32_t rxOk = 0;        // ramki z poprawnym CRC
    uint32_t rxBad = 0;       // ramki z błędnym CRC
    uint32_t missing = 0;     // brakujące numery porządkowe
    uint32_t reordered = 0;   // numer nie większy od poprzedniego (duplikat albo zmiana kolejności)
    uint32_t overflow = 0;    // przepełnienia kolejki RX
    bool haveSeq = false;
    uint16_t lastSeq = 0;
    int32_t rssiSum = 0;      // suma RSSI poprawnych ramek (dBm)
    uint32_t lqiSum = 0;      // CC1120: LQI, S2-LP: SQI
    int32_t snrSumQdb = 0;    // SX1262: suma SNR poprawnych ramek (ćwiartki dB)
    uint32_t startedMs = 0;
};

struct Event {
    uint32_t ms;
    char text[40];
};

// Liczniki łącza stosu (pola INFO ze specyfikacji: rx_ok, rx_bad, tx_drop; LoRa także powody odroczeń).
struct LinkCounters {
    uint32_t rxOk = 0;          // ramki z poprawnym CRC (P1: i nagłówkiem)
    uint32_t rxBad = 0;         // ramki odrzucone przez układ (CRC, nagłówek, za późno) albo przy rozbiorze
    uint32_t rxDatagrams = 0;   // złożone datagramy
    uint32_t txDatagrams = 0;
    uint32_t txFragments = 0;   // nadane ramki (P1: fragmenty, LoRa: ramki RNode)
    uint32_t txDrop = 0;        // datagramy odrzucone (cisza, STOP, dziennik, zbyt wiele odroczeń)
    uint32_t deferrals = 0;     // odroczenia CCA
    uint32_t longDeferrals = 0; // nadania odroczone przez CCA łącznie o ponad 1 s (bez czekania na dług)
    uint32_t cadBusy = 0;       // LoRa: CAD wykrył preambułę
    uint32_t rssiBusy = 0;      // LoRa: RSSI ponad progiem CCA w oknie albo przy decyzji
    uint32_t rxBusy = 0;        // LoRa: preambuła, nagłówek albo ramka w oknie, albo nieodczytana ramka w układzie
};

enum class RxMode : uint8_t { NONE, TEST, LINK };

// Bajty losowe z generatora stacji (drbg.h, ziarno z platform::entropy); dostarcza main.cpp.
void randomBytes(uint8_t* out, size_t count);

class Bench {
public:
    // pinLed: dioda miganiem sygnalizująca czekanie na potwierdzenie OK (aktywna stanem niskim); -1 = brak.
    Bench(radiolink::Driver& radio, uint8_t pinOk, int16_t pinLed);

    bool prep = false;     // tryb przygotowania (na stacji: przycisk pod naklejką serwisową)
    bool silence = false;  // cisza radiowa (przełącznik CISZA albo panel): blokuje każde nadanie
    // Cisza z panelu z wyjątkiem jednego zgłoszenia: nadanie P1 od stosu (p1send z stack = true)
    // przechodzi, bo stos przepuszcza wtedy tylko ruch wyjątku (rns_node.h); pomiary i P1TX nie.
    bool silenceException = false;
    // Układ skonfigurowany profilem (P1 albo LoRa): warunek każdego nadania. Na układzie z łączem P1
    // poza trybem przygotowania odbiór P1 wraca sam po każdym przerwaniu (radio.md: odbiór wyłącza się
    // tylko na czas własnego nadawania).
    bool p1Ready = false;

    // Dziennik FRAM i zegar czasu pracy; bez dziennika nadawanie radiowe jest zablokowane.
    void attach(journal::Journal* journal, uint32_t (*uptimeS)());
    // Dług odczytany z dziennika przy starcie: odczekiwany w całości, potem kasowany zapisem 0.
    void restoreDebt(uint32_t debtMs);

    // Każda funkcja zwraca nullptr po przyjęciu polecenia albo tekst błędu do odpowiedzi JSON.
    const char* txcw(uint32_t seconds, bool conducted);
    const char* txpkt(uint16_t count, uint8_t length, uint32_t intervalMs, bool conducted,
                      testframe::Fill fill = testframe::Fill::PN9);
    const char* rxStart(uint8_t length);
    // Łącze stosu: odbiór w tle i nadanie datagramu z CCA 50 ms, odroczeniem losowym 100..1000 ms
    // i długiem ciszy w dzienniku, w ramkowaniu układu. p1rxStart i p1send (polecenia P1RX, P1TX) tylko
    // na układzie z łączem P1.
    const char* linkRxStart();
    const char* linkSend(const uint8_t* data, size_t length, bool stack);
    const char* p1rxStart();
    const char* p1send(const uint8_t* data, size_t length, bool stack = false);
    void printLink();
    const LinkCounters& link() const { return link_; }
    // Największy dług łącza: 12 x najdłuższa seria układu (P1 16,8 s, LoRa 12 x 838 ms ≈ 10,06 s),
    // odczekiwany po starcie bez poprawnego rekordu długu.
    // Ramkowanie łącza układu (RNODE: LoRa); stos bierze z niego czas łącza (p1iface::LinkTiming).
    radiolink::Framing linkFraming() const { return radio_.framing(); }
    uint32_t maxDebtMs() const { return radio_.seriesMaxMs() * radiolink::P1_DEBT_FACTOR; }
    // Złożony datagram łącza i koniec nadawania (ok = seria wyszła) dla warstwy aplikacji.
    void onDatagram(void (*handler)(const uint8_t* data, size_t length, void* context), void* context) { datagramHandler_ = handler; datagramContext_ = context; }
    void onTxDone(void (*handler)(bool ok, void* context), void* context) { txDoneHandler_ = handler; txDoneContext_ = context; }
    const char* foff(int32_t hz);
    // Tryb EMC: start (tryb przygotowania, zapis w dzienniku przed pierwszą ramką), wznowienie po
    // restarcie z rekordu dziennika (false: rekord nie pasuje do układu i zostaje skasowany),
    // koniec z kasowaniem rekordu (nullptr albo tekst błędu, gdy rekord został w dzienniku), stan w JSON.
    const char* emcStart(uint32_t periodS, uint8_t length);
    bool emcResume(uint32_t mode);
    const char* emcStop();
    void printEmc();
    bool emcActive() const { return emcActive_; }
    uint32_t emcMinPeriodS(uint8_t length) const;
    void stop();         // przerwanie zadania i IDLE (tryb EMC zostaje: odbiór wraca w ciągu 1 s)
    // Datagram czekający na dług, kanał albo odstęp odpada (cisza albo inny wyjątek ciszy niż przy
    // przyjęciu); nadawany właśnie (SEND) kończy się.
    void dropLinkTx();
    void poll();         // z loop(): nadawanie serii, odbiór ramek, koniec nośnej, kasowanie długu
    void rxper();        // drukuje i zeruje liczniki
    void printFoff();
    void printLog(uint32_t count);
    void printStatus();
    void log(const char* text);
    void applyOffset();  // ponowny zapis korekty częstotliwości po CONFIG
    bool confirm();      // czeka na przycisk OK do CONFIRM_MS (seria TXCW/TXPKT w toku zostaje przerwana)
    uint32_t debtRemainingMs() const;
    bool busy() const { return cwActive_ || pktActive_ || txState_ != TxState::IDLE; }
    // Układ nadaje albo mierzy kanał przed nadaniem; datagram czekający na dług lub odstęp (układ w
    // odbiorze) nie wstrzymuje kontroli radia, inaczej pod stałym ruchem nie byłoby jej wcale.
    bool transmitting() const { return cwActive_ || pktActive_ || txState_ == TxState::CCA || txState_ == TxState::SEND; }
    bool receiving() const { return rxMode_ != RxMode::NONE; }
    const Counters& counters() const { return counters_; }

private:
    const char* gate(uint32_t txMs, bool conducted);  // tryb, cisza, dług, limit serii, potwierdzenie, zapis długu
    void stopCw();
    bool sendOne();
    void finishPkt();
    void endSeriesDebt();
    void receive();
    void receiveLink();
    void receiveP1();
    void receiveLora();
    void datagramLine(const char* head, int headLength, const uint8_t* data, size_t length);
    bool enterRx(RxMode mode, uint8_t length);
    bool channelBusy();
    void startCca(uint32_t now, bool first);
    void defer(uint32_t now);
    void pollLinkTx();
    bool sendFragments();
    void sendLora(uint32_t now);
    void finishLinkTx(const char* result);
    const char* txStateName() const;
    void pollEmc(uint32_t now);
    void emcSend(uint32_t now);
    bool emcValid(uint32_t periodS, uint8_t length) const;  // długość ramki i okres ≥ 13 x czas ramki
    void emcCommon(uint32_t periodS, uint8_t length);       // wspólne dla startu i wznowienia (po emcValid)
    void led(bool on);
    uint32_t uptimeS() const { return uptime_ ? uptime_() : millis() / 1000; }
    const char* lengthError();  // "len 4..<najdłuższa ramka wzorcowa układu>"

    radiolink::Driver& radio_;
    uint8_t pinOk_;
    int16_t pinLed_;
    journal::Journal* journal_ = nullptr;
    uint32_t (*uptime_)() = nullptr;

    bool cwActive_ = false;
    uint32_t cwStartMs_ = 0;
    uint32_t cwEndMs_ = 0;

    bool pktActive_ = false;
    uint16_t pktTotal_ = 0;
    uint16_t pktSent_ = 0;
    uint8_t pktLen_ = 0;
    testframe::Fill pktFill_ = testframe::Fill::PN9;
    uint32_t pktIntervalMs_ = 0;
    uint32_t pktNextMs_ = 0;
    uint32_t pktStartMs_ = 0;
    uint32_t pktTxUs_ = 0;       // suma czasu od polecenia TX do stanu spoczynku
    uint32_t pktLeadUs_ = 0;     // pierwsza ramka: STX -> początek słowa synchronizacji
    uint32_t pktOnAirUs_ = 0;    // pierwsza ramka: słowo synchronizacji -> koniec pakietu
    uint32_t pktTailUs_ = 0;     // pierwsza ramka: koniec pakietu -> IDLE
    bool pktSyncSeen_ = false;
    bool pktConducted_ = false;
    uint16_t pktFailed_ = 0;

    RxMode rxMode_ = RxMode::NONE;
    uint8_t rxLen_ = 0;
    uint32_t rxPollMs_ = 0;
    uint32_t autoRxMs_ = 0;      // ostatnia próba samoczynnego powrotu do odbioru łącza
    uint32_t rxSinceMs_ = 0;     // początek odbioru łącza (okno CCA LoRa nie krótsze niż odbiór)
    uint32_t seriesDebtMs_ = 0;  // dług serii TXCW/TXPKT do odliczenia od jej końca
    Counters counters_;

#ifndef WICI_NO_P1_LINK
    p1frame::Assembler assembler_;
#endif
    loraframe::Assembler loraAssembler_;
    loraframe::Splitter splitter_;  // połówka nagłówka ostatniego nadanego datagramu dzielonego
    LinkCounters link_;

    // Nadawanie łącza: oczekiwanie na dług, CCA, odroczenie, seria ramek.
    enum class TxState : uint8_t { IDLE, WAIT_DEBT, CCA, BACKOFF, SEND };
    TxState txState_ = TxState::IDLE;
    uint8_t txData_[p1frame::MAX_DATAGRAM] = {};
    size_t txLength_ = 0;
    bool txStack_ = false;      // datagram od stosu (wyjątek ciszy)
    uint8_t txId_[p1frame::ID_BYTES] = {};  // P1: identyfikator datagramu
    uint8_t txRandom_ = 0;      // LoRa: bajt losowy nagłówka RNode (jeden na datagram, także po odroczeniach)
    uint32_t txRequestedMs_ = 0;
    uint32_t ccaFirstMs_ = 0;    // pierwsze wejście w CCA (po odczekaniu długu): miara odroczeń
    uint32_t ccaStartMs_ = 0;
    uint32_t ccaFrames_ = 0;     // ramki odebrane do początku okna CCA
    uint32_t ccaCheckMs_ = 0;
    uint32_t backoffUntilMs_ = 0;
    uint8_t txDeferrals_ = 0;

    uint32_t debtUntilMs_ = 0;
    mutable bool debtActive_ = false;   // dług jeszcze nieodczekany; gaszony w debtRemainingMs() (main.cpp co obieg)
    bool debtPending_ = false;   // dług zapisany w dzienniku, jeszcze nieskasowany
    int32_t foffHz_ = 0;
    bool foffSet_ = false;

    bool emcActive_ = false;
    bool emcResumed_ = false;    // wznowiony po restarcie z dziennika
    uint32_t emcPeriodMs_ = 0;
    uint8_t emcLen_ = 0;
    uint32_t emcNextMs_ = 0;
    uint16_t emcSeq_ = 0;
    uint32_t emcSent_ = 0;
    uint32_t emcFailed_ = 0;     // brak TxDone
    uint32_t emcSilenced_ = 0;   // ramki pominięte w ciszy radiowej
    uint32_t emcSkipped_ = 0;    // ramki pominięte: profil niezapisany albo błąd dziennika długu
    uint32_t emcStartedMs_ = 0;

    char lengthError_[16] = {};
    char emcError_[32] = {};   // "period <min>..3600 s"; GCC liczy pełny zakres uint32
    Event events_[LOG_ENTRIES];
    size_t eventCount_ = 0;
    void (*datagramHandler_)(const uint8_t*, size_t, void*) = nullptr;
    void* datagramContext_ = nullptr;
    void (*txDoneHandler_)(bool, void*) = nullptr;
    void* txDoneContext_ = nullptr;
};

}  // namespace measure
