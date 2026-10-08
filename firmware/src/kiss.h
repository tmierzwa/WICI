// SPDX-License-Identifier: MIT
// Interfejs Reticulum przez USB w konfiguracji węzła OSP (docs/spec/radio.md, "Interfejs
// Reticulum przez USB (węzeł OSP)"): ramki KISS zgodne z KISSInterface Reticulum e40191b.
// - Ramka danych FEND 0x00 <pakiet> FEND z sekwencjami FESC TFEND i FESC TFESC; jeden pakiet
//   Reticulum do 500 B. Starszy półbajt polecenia (numer portu) pomija się jak w Reticulum.
// - Polecenia konfiguracji (TXDELAY, P, SLOTTIME, TXTAIL, FULLDUPLEX, SETHARDWARE) są przyjmowane
//   i pomijane, bo dostęp do kanału określa P1.
// - Kontrola przepływu: komputer włącza ją poleceniem 0x0F z wartością różną od zera. Po
//   przyjęciu pakietu do bufora na 8 pakietów stacja wysyła ramkę gotowości FEND 0x0F 0x01 FEND
//   (jak RNode); przy pełnym buforze gotowość czeka na wolne miejsce. Pakiet ponad bufor jest
//   odrzucany i liczony (Reticulum na komputerze zwalnia blokadę sam po 5 s).
// - Niepełna ramka po 100 ms bez bajtu jest porzucana (jak readLoop w Reticulum).
// - Pakiety do komputera czekają w buforze bajtów zakodowanych ramek, z którego pętla stacji
//   zapisuje tyle, ile przyjmie interfejs CDC; ramka, która się nie mieści, przepada i jest liczona.
// Bez zależności od Arduino i od stosu; sprawdzany na komputerze (tests/test_rns_units.py).
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace kiss {

constexpr uint8_t FEND = 0xC0;
constexpr uint8_t FESC = 0xDB;
constexpr uint8_t TFEND = 0xDC;
constexpr uint8_t TFESC = 0xDD;
constexpr uint8_t CMD_DATA = 0x00;
constexpr uint8_t CMD_READY = 0x0F;
constexpr size_t MTU = 500;              // pakiet Reticulum (MTU interfejsu)
constexpr size_t RX_SLOTS = 8;           // bufor od komputera: co najmniej 8 pakietów po 500 B
constexpr size_t TX_BYTES = 1024;        // zakodowane ramki do komputera (dwie typowe, jedna najdłuższa)
constexpr uint32_t FRAME_TIMEOUT_MS = 100;

struct Counters {
    uint32_t fromComputer = 0;   // pakiety przyjęte do bufora
    uint32_t toComputer = 0;     // pakiety zakodowane do wysłania
    uint32_t rxDropped = 0;      // pełny bufor
    uint32_t rxTooLarge = 0;     // ramka danych ponad 500 B
    uint32_t txDropped = 0;      // brak miejsca w buforze do komputera albo port zamknięty
    uint32_t commands = 0;       // polecenia konfiguracji KISS (pomijane)
    uint32_t ready = 0;          // wysłane ramki gotowości
};

class Port {
public:
    // Port otwarty przez komputer albo zamknięty: niepełna ramka i zaległe bajty przepadają,
    // kontrola przepływu wraca do stanu wyłączonego (komputer włącza ją przy każdym połączeniu).
    void setOpen(bool open);
    bool open() const { return open_; }
    void feed(const uint8_t* bytes, size_t count, uint32_t nowMs);
    // Najstarszy pakiet od komputera; false, gdy bufor pusty.
    bool peek(const uint8_t*& data, size_t& length) const;
    void pop();                        // pakiet przekazany do stosu: wolne miejsce, zaległa gotowość
    size_t buffered() const { return count_; }
    // Pakiet do komputera; false: port zamknięty, pakiet za długi albo brak miejsca (liczone).
    bool send(const uint8_t* data, size_t length);
    size_t take(uint8_t* out, size_t max);   // bajty do zapisu w CDC (najwyżej max)
    size_t pendingBytes() const { return txCount_; }
    bool flowControl() const { return flowControl_; }
    const Counters& counters() const { return counters_; }

private:
    void endFrame();
    void readyNow();                   // ramka gotowości albo zaległa, gdy brak miejsca
    bool put(const uint8_t* bytes, size_t count);

    bool open_ = false;
    bool flowControl_ = false;
    bool readyOwed_ = false;
    // Dekoder.
    bool inFrame_ = false;
    bool escape_ = false;
    int16_t command_ = -1;             // -1: bajt polecenia jeszcze nie przyszedł
    int16_t target_ = -1;              // miejsce w buforze dla ramki danych; -1: bufor był pełny
    size_t length_ = 0;
    bool tooLarge_ = false;
    uint32_t lastByteMs_ = 0;
    uint8_t value_ = 0;                // pierwszy bajt treści polecenia (0x0F)
    bool hasValue_ = false;
    // Bufor pakietów od komputera.
    uint8_t slots_[RX_SLOTS][MTU] = {};
    uint16_t lengths_[RX_SLOTS] = {};
    size_t head_ = 0;
    size_t count_ = 0;
    // Bufor bajtów do komputera.
    uint8_t tx_[TX_BYTES] = {};
    size_t txHead_ = 0;
    size_t txCount_ = 0;
    Counters counters_;
};

}  // namespace kiss
