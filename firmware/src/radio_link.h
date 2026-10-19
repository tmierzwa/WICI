// SPDX-License-Identifier: MIT
// Interfejs układu radiowego dla stanowiska pomiarowego i łącza P1 (measure::Bench): operacje,
// które różnią się między CC1120 (wykonanie A, cc1120_link.cpp), S2-LP (wykonanie B,
// s2lp_link.cpp) i SX1262 w profilu LoRa (L0, sx1262_link.cpp). Bench nie zna rejestrów układu
// ani profilu: czas ramki w eterze, najdłuższą ramkę wzorcową i limit serii podaje sterownik.
// Logika P1 (dług ciszy, CCA, odroczenia, fragmentacja, składanie) jest wspólna; SX1262 nie ma
// łącza P1 (interfejs LoRa stosu to osobny etap), więc ma tylko polecenia pomiarowe.
//
// Ramki: w trybie stałej długości (ramki wzorcowe TXPKT/RX) ramka to `length` bajtów treści;
// w trybie zmiennej długości (P1) ramka zaczyna się od bajtu LEN, a za nim LEN bajtów BODY i CRC,
// niezależnie od tego, czy układ trzyma LEN w kolejce FIFO (CC1120), czy w rejestrze (S2-LP).
// W LoRa długość niesie jawny nagłówek, więc ramka to zawsze `length` bajtów treści.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace radiolink {

constexpr size_t MAX_FRAME = 255;  // najdłuższa ramka: LoRa 255 B (SX1262); P1 103 B (LEN + BODY + CRC)

// Profil P1 (CC1120, S2-LP): ramka w eterze to preambuła 8 B, słowo synchronizacji 4 B i `length` B
// przy symbolRate Bd, plus 3 ms na narastanie mocy (zaokrąglenie w górę).
constexpr uint32_t p1FrameAirMs(size_t length, uint32_t symbolRate) {
    return (static_cast<uint32_t>(12 + length) * 8 * 1000 + symbolRate - 1) / symbolRate + 3;
}
// Najdłuższa seria pomiarowa bez CONDUCTED w P1: 7 ramek po 103 B z narastaniem (najdłuższy datagram P1).
// Także górna granica długu, który stanowisko zapisuje (measure::MAX_DEBT_MS).
constexpr uint32_t P1_SERIES_MAX_MS = 1400;

struct Rssi {
    bool valid = false;
    int16_t dbm = 0;
};

struct Frame {
    uint8_t bytes[MAX_FRAME];
    size_t length = 0;      // z bajtem LEN w trybie zmiennej długości
    int16_t rssiDbm = 0;    // RSSI pakietu (dBm, z przesunięciem przyjętym dla układu)
    uint8_t quality = 0;    // CC1120: LQI; S2-LP: SQI; SX1262: 0 (jakość jako SNR w snrQdb)
    int16_t snrQdb = 0;     // SX1262: SNR pakietu w ćwiartkach dB; układy P1 go nie podają
};

enum class RxPoll : uint8_t {
    // Nazwy nie wielkimi literami: OVERFLOW to makro z math.h.
    Nothing,   // nic nowego
    Frame,     // ramka w `Frame`; wywołać ponownie, bo w kolejce mogą być następne
    Bad,       // ramka odrzucona przez układ albo niepełna (zła długość, przekroczony czas)
    Overflow,  // przepełnienie kolejki RX; układ wrócił do odbioru
};

// Czasy pierwszej ramki serii z wyjścia GPIO układu (CC1120: PKT_SYNC_RXTX); valid = false,
// gdy układ ich nie podaje.
struct TxTiming {
    bool valid = false;
    uint32_t totalUs = 0;   // od polecenia TX do powrotu do stanu spoczynku
    uint32_t leadUs = 0;    // polecenie TX -> początek słowa synchronizacji
    uint32_t onAirUs = 0;   // słowo synchronizacji -> koniec pakietu
    uint32_t tailUs = 0;    // koniec pakietu -> stan spoczynku
};

class Driver {
public:
    virtual ~Driver() = default;

    virtual const char* stateName() = 0;      // stan układu do odpowiedzi poleceń
    virtual void idle() = 0;                  // przerwanie TX i RX, stan spoczynku, kolejki opróżnione

    // Nośna bez modulacji do stopCw(); true, gdy układ wszedł w TX.
    virtual bool startCw() = 0;
    virtual void stopCw() = 0;

    // Nadanie jednej ramki i czekanie na koniec (blokujące, do czasu ramki + zapas).
    // variable = false: ramka wzorcowa o stałej długości; true: ramka P1 z bajtem LEN.
    virtual bool transmit(const uint8_t* frame, size_t length, bool variable, TxTiming* timing) = 0;

    // Odbiór: variable = true dla P1 (LEN do p1frame::MAX_LEN), inaczej ramki po fixedLength B.
    virtual bool startRx(bool variable, uint8_t fixedLength) = 0;
    virtual RxPoll pollRx(Frame& out) = 0;
    virtual bool receivingFrame() = 0;        // trwa odbiór po słowie synchronizacji
    virtual Rssi rssi() = 0;                  // bieżące RSSI (ważne w RX)

    // Korekta częstotliwości do restartu; false, gdy poza zakresem układu.
    virtual bool setFrequencyOffset(int32_t hz) = 0;
    virtual void reapplyFrequencyOffset() = 0;  // po ponownym zapisie konfiguracji
    virtual int32_t frequencyOffsetHz() = 0;    // zastosowana korekta z rejestrów
    virtual int32_t frequencyOffsetRaw() = 0;   // wartość rejestru korekty
    virtual double frequencyStepHz() const = 0;
    virtual bool frequencyErrorHz(int32_t& hz) = 0;  // błąd nośnej ostatniego odbioru, jeśli układ go mierzy

    // Profil w eterze. Czas nadawania jednej ramki wzorcowej o `length` B (ms, w górę, z narastaniem
    // mocy): podstawa długu ciszy serii TXPKT i rezerwacji datagramu P1.
    virtual uint32_t frameAirMs(size_t length) const = 0;
    // Oczekiwany czas ramki w powietrzu bez narastania (pole expected_on_air_ms w TXPKT): P1 od
    // słowa synchronizacji do końca pakietu, LoRa cała ramka od preambuły.
    virtual double onAirMs(size_t length) const = 0;
    virtual size_t maxTestLength() const = 0;  // najdłuższa ramka wzorcowa TXPKT i RX
    // Najdłuższa seria bez CONDUCTED (ms czasu nadawania): najdłuższy datagram profilu, ≤ P1_SERIES_MAX_MS.
    virtual uint32_t seriesMaxMs() const = 0;
    virtual bool p1Link() const = 0;           // łącze P1 (P1RX, P1TX, stos) na tym układzie
    virtual bool hasSnr() const { return false; }  // ramki niosą SNR (snrQdb), RXPER podaje średnią
};

}  // namespace radiolink
