// SPDX-License-Identifier: MIT
// SX1262 w profilu LoRa pilotażu jako radiolink::Driver dla measure::Bench (stacja L0):
// - konfiguracja jak w programie diagnostycznym L0 (RadioLib 7.6.0, SX1262::begin): TCXO 1,8 V
//   z DIO3, kalibracja po włączeniu TCXO, przetwornica DC-DC, DIO2 jako przełącznik nadawania,
//   RXEN z MCU (stan wysoki tylko w RX), poprawki z rozdziału 15 karty; moc, preambuła i słowo
//   synchronizacji z lora_profile.h; Rx Boosted (0x08AC = 0x96) dopisany do listy rejestrów
//   zachowywanych w uśpieniu (rozdz. 9.6);
// - stany: konfiguracja, uśpienie i idle() w STDBY_RC (karta wymaga go dla Calibrate, SetPacketType
//   i SetSleep z zachowaniem konfiguracji); między nadawaniem, odbiorem i CAD STDBY_XOSC, także jako
//   tryb powrotu po TxDone (SetRxTxFallbackMode 0x30, tabela 13-23): TCXO pracuje, więc SetTx i SetRx
//   nie czekają 5 ms na jego start (rozdz. 13.3.6, uwaga o opóźnieniu TCXO);
// - nadawanie z bufora od adresu 0 z jawnym nagłówkiem (ramka wzorcowa to `length` bajtów treści),
//   koniec po przerwaniu TxDone, bez niego po czasie ramki + 100 ms powrót do STDBY_XOSC i błąd;
//   kroki dla interfejsu LoRa: prepareTx (sprawdzenie odbioru bez kasowania flag, wyjście z odbioru,
//   ramka i długość), cad, sendPrepared;
// - CAD (SetCadParams, SetCad, rozdz. 13.1.8 i 13.4.7) tylko ze stanu spoczynku, CAD_ONLY: po CAD układ
//   wraca według karty do STDBY_RC niezależnie od trybu powrotu (tabela 13-73), więc SetTx po CAD
//   płaci start TCXO (5 ms); CadDone i CadDetected z jednego odczytu GetIrqStatus;
// - odbiór ciągły (SetRx 0xFFFFFF): bufor 256 B jest pierścieniem, a w odbiorze ciągłym każdy pakiet
//   pisze się od miejsca, w którym skończył się poprzedni (rozdz. 7.2 i 13.2.3), więc druga ramka
//   255 B nadpisuje pierwszą. serviceRx() to jedna próbka odbioru (z pętli albo z zadania odbioru):
//   kasuje tylko flagi, które widziała; ramka, przy której jest już HeaderValid następnej ramki (przy
//   RxDone, gdy nagłówek bieżącej ramki był już widziany albo od poprzedniej próbki minęło ponad 25 ms,
//   albo po odczycie bufora), jest podejrzana (rx_late) i odrzucona; HeaderValid i RxDone tej samej
//   krótkiej ramki w jednej próbce to ramka dobra; znaczniki aktywności
//   kanału (preambuła, nagłówek, ramka, RSSI ponad progiem) są atomowe dla okna CCA. Pierwsze
//   przekroczenie czasu BUSY przerywa próbkę bez ramki;
// - DIO1 tylko dla RxDone, CrcErr i HeaderErr (zadanie odbioru sprawdza poziom linii); TxDone
//   i CadDone sterownik czyta sam przez SPI;
// - nośna CW poleceniem SetTxContinuousWave; korekta częstotliwości słowem RF (krok 0,954 Hz).
// Łącze stosu w ramkach RNode (framing() = RNODE), bez łącza P1. Wywołujący trzyma blokadę operacji radia (platform::RadioLock),
// gdy pracuje też zadanie odbioru (pętla: przez radiolink::LockedDriver, radio_lock.h); sterownik sam jej nie bierze,
// z wyjątkiem obiegu zadania odbioru (taskCycle: próba bez czekania).
// Odwołania do karty bez numeru wersji: DS.SX1261-2.W.APP; rozdziały i tabele CAD, trybu powrotu
// i bufora sprawdzone w rev. 1.2 (czerwiec 2019).
#pragma once

#include <Arduino.h>

#include <atomic>

#include "lora_profile.h"
#include "radio_link.h"
#include "rx_watch.h"
#include "spsc_ring.h"
#include "sx1262.h"

namespace sx1262 {

struct VerifyResult {
    uint16_t checked = 0;
    uint16_t mismatches = 0;
    uint16_t firstAddress = 0;  // adres rejestru; 0 dla typu pakietu i błędów układu
    uint16_t expected = 0;
    uint16_t actual = 0;
    const char* firstName = "";
};

// Wynik jednej próbki odbioru (serviceRx).
enum class RxService : uint8_t {
    Nothing,      // brak końca ramki (ewentualnie znaczniki aktywności odświeżone)
    Frame,        // ramka w `out`
    Bad,          // ramka z błędem CRC albo nagłówka, albo zła długość
    Late,         // ramka odczytana za późno (HeaderValid następnej ramki): odrzucona, w rxLate()
    NotRx,        // sterownik nie jest w odbiorze
    BusyTimeout,  // przekroczony czas BUSY: próbka przerwana, `out` bez ramki
};

// Znaczniki aktywności kanału (millis()) dla okna CCA. Pisze je próbka odbioru (zadanie albo pętla),
// czyta pętla bez blokady radia. Bit w masce mówi, że znacznik jest ważny (od clearActivity()).
struct Activity {
    enum Kind : uint8_t { PREAMBLE = 0, HEADER, FRAME, RSSI, KINDS };
    std::atomic<uint32_t> ms[KINDS];
    std::atomic<uint8_t> seen{0};
    Activity() {
        for (auto& m : ms) m.store(0, std::memory_order_relaxed);
    }
    void mark(Kind kind, uint32_t now) {
        ms[kind].store(now, std::memory_order_relaxed);
        seen.fetch_or(static_cast<uint8_t>(1u << kind), std::memory_order_release);
    }
    static constexpr uint8_t ALL = (1u << KINDS) - 1;
    static constexpr uint8_t RX_KINDS = (1u << PREAMBLE) | (1u << HEADER) | (1u << FRAME);
    // Ostatnia aktywność rodzajów z kinds dawniej niż windowMs temu (albo żadnej od clearActivity()).
    bool quietFor(uint32_t now, uint32_t windowMs, uint8_t kinds = ALL) const {
        const uint8_t mask = seen.load(std::memory_order_acquire) & kinds;
        for (uint8_t k = 0; k < KINDS; ++k)
            if ((mask & (1u << k)) && now - ms[k].load(std::memory_order_relaxed) < windowMs) return false;
        return true;
    }
    void clear() { seen.store(0, std::memory_order_release); }
};

class LinkDriver : public radiolink::Driver {
public:
    LinkDriver(Radio& radio, uint8_t pinRxen) : radio_(radio), pinRxen_(pinRxen) {}

    void begin();  // RXEN jako wyjście w stanie niskim (spoczynek)
    // Zapis profilu LoRa po resecie (układ w STDBY_RC) i weryfikacja odczytem.
    VerifyResult configure();
    VerifyResult verify();
    // Układ stracił profil (reset albo zanik zasilania): typ pakietu nie LoRa albo wzmocnienie odbiornika
    // wróciło do wartości po resecie.
    bool profileLost();
    // Uśpienie z ciepłym startem i wybudzenie; zwraca 0x08AC po wybudzeniu (0x96, gdy lista zachowywanych działa).
    bool sleepAndWake(uint8_t& rxGainAfter);
    uint8_t packetType();
    uint32_t rfWord() const;  // słowo SetRfFrequency z korektą FOFF
    bool rxenHigh() const { return rxen_; }
    uint16_t irqSeen() const { return irqSeen_; }

    // Jedna próbka odbioru: przerwania, znaczniki aktywności, RSSI (gdy sampleRssi) i ramka po RxDone.
    // Dla pętli (pollRx) i zadania odbioru; zawsze pod blokadą operacji radia, gdy zadanie pracuje.
    RxService serviceRx(radiolink::Frame& out, bool sampleRssi);
    const Activity& activity() const { return activity_; }
    void clearActivity() override { activity_.clear(); }  // po rekonfiguracji i IDLE (pętla, pod blokadą)
    uint32_t rxLate() const override { return rxLate_.load(std::memory_order_relaxed); }
    radiolink::Activity recentActivity(uint32_t windowMs) override;

    // Odbiór w tle (stacja L0, plan interfejsu LoRa, L6). taskCycle() to jeden obieg zadania odbioru (co takt):
    // licznik obiegów; przy wysokim DIO1 (koniec ramki, poziom czytany przez wywołującego bez blokady) albo
    // co RSSI_SAMPLE_MS próba blokady radia bez czekania (zajęta: obieg pominięty); w odbiorze serviceRx
    // z próbką RSSI co RSSI_SAMPLE_MS; ramka, ramka zła i spóźniona idą do pierścienia RX_RING ramek z czasem
    // odbioru próbki (pełny: odpada najnowsza, rx_ring_overflow). Udana próbka odświeża lastServiceMs.
    // Pierwsze przekroczenie czasu BUSY przerywa obieg bez zapisu do pierścienia, a następna próba jest
    // po BUSY_BACKOFF_MS (wyjęty moduł nie zajmuje rdzenia 0 czekaniem na BUSY).
    // Przy setBackgroundRx(true) pollRx() czyta pierścień zamiast układu (zadanie jest jedynym właścicielem
    // flag odbioru); ustawiać pod blokadą przed startem zadania.
    static constexpr uint32_t RSSI_SAMPLE_MS = 5;
    static constexpr uint32_t BUSY_BACKOFF_MS = 100;
    static constexpr size_t RX_RING = 8;  // RNode wysyła kolejkę jedną serią
    void taskCycle(bool dio1High);
    void setBackgroundRx(bool on) { background_ = on; }
    bool backgroundRx() const { return background_; }
    const rxwatch::TaskSignals& taskSignals() const { return signals_; }
    uint32_t rxRingOverflow() const override { return ring_.overflow(); }

    const char* stateName() override { return modeName(radio_.status().mode()); }
    void idle() override;
    bool startCw() override;
    void stopCw() override;
    bool transmit(const uint8_t* frame, size_t length, bool variable, radiolink::TxTiming* timing) override;
    bool startRx(bool variable, uint8_t fixedLength) override;
    radiolink::RxPoll pollRx(radiolink::Frame& out) override;
    bool receivingFrame() override;
    radiolink::Rssi rssi() override;
    bool setFrequencyOffset(int32_t hz) override;
    void reapplyFrequencyOffset() override;
    int32_t frequencyOffsetHz() override;
    int32_t frequencyOffsetRaw() override { return offsetSteps_; }
    double frequencyStepHz() const override;
    bool frequencyErrorHz(int32_t&) override { return false; }  // karta nie opisuje rejestru błędu częstotliwości
    uint32_t frameAirMs(size_t length) const override { return lora::frameAirMs(length); }
    double onAirMs(size_t length) const override { return lora::frameAirUs(length) / 1000.0; }
    size_t maxTestLength() const override { return lora::MAX_PAYLOAD; }
    uint32_t seriesMaxMs() const override { return lora::SERIES_MAX_MS; }
    radiolink::Framing framing() const override { return radiolink::Framing::RNODE; }
    bool hasSnr() const override { return true; }
    int8_t ccaThresholdDbm() const override;
    radiolink::TxPrep prepareTx(const uint8_t* frame, size_t length) override;
    radiolink::Cad cad() override;
    bool sendPrepared(radiolink::TxTiming* timing) override;

private:
    bool toStandby();    // STDBY_XOSC: między nadawaniem, odbiorem i CAD; false przy przekroczeniu czasu BUSY
    void toStandbyRc();  // STDBY_RC: konfiguracja, uśpienie, idle()
    bool load(const uint8_t* frame, size_t length);
    void noteActivity(uint16_t irq, uint32_t now);
    void rxen(bool on);
    bool setPacketParams(uint8_t payloadLength);
    bool readRssi(radiolink::Rssi& out);  // false przy przekroczeniu czasu BUSY; out.valid tylko w RX
    void writeFrequency();
    void collectIrq(uint16_t irq) { irqSeen_ |= irq; }

    Radio& radio_;
    uint8_t pinRxen_;
    bool rxen_ = false;
    bool rxActive_ = false;
    size_t txLength_ = 0;  // ramka załadowana do nadania (limit czasu TxDone)
    bool rxVariable_ = false;
    uint8_t rxFixedLength_ = 0;
    std::atomic<bool> inFrame_{false};  // preambuła albo nagłówek wykryte, ramka jeszcze nieodebrana (CCA czyta bez blokady)
    bool headerSeen_ = false;   // próbka widziała i skasowała HeaderValid bieżącej ramki
    uint32_t lastSampleMs_ = 0; // ostatnia udana próbka odbioru (millis), do wykrycia spóźnienia
    std::atomic<uint32_t> inFrameSinceMs_{0};
    uint16_t irqSeen_ = 0;
    int32_t offsetSteps_ = 0;
    Activity activity_;
    std::atomic<uint32_t> rxLate_{0};

    // Pozycja pierścienia odbioru w tle: Frame albo Bad (zła i spóźniona ramka, jak pollRx bez zadania).
    struct RxEntry {
        radiolink::RxPoll kind = radiolink::RxPoll::Nothing;
        radiolink::Frame frame;
    };
    bool background_ = false;
    SpscRing<RxEntry, RX_RING> ring_;
    rxwatch::TaskSignals signals_;
    uint32_t lastRssiMs_ = 0;       // zadanie: ostatnia próbka z RSSI
    uint32_t busyBackoffMs_ = 0;    // zadanie: przekroczenie czasu BUSY (0: brak)
};

}  // namespace sx1262
