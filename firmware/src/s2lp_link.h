// SPDX-License-Identifier: MIT
// S2-LP jako radiolink::Driver dla measure::Bench (wykonanie B), według karty DS11896:
// - nadawanie z kolejki TX (pakiet BASIC; w trybie zmiennej długości układ sam wysyła pole LEN
//   z PCKTLEN, więc do kolejki idą BODY i CRC), polecenie TX tylko ze stanu READY, koniec po
//   przerwaniu TX_DATA_SENT i powrocie do READY;
// - odbiór w trybie stałym (PERS_RX): ramka po przerwaniu RX_DATA_READY, długość z RX_PCKT_LEN,
//   RSSI z RSSI_LEVEL (zapamiętane po słowie synchronizacji), jakość = SQI;
// - przerwania odczytywane z IRQ_STATUS (odczyt kasuje) i zbierane w programie, bo ten sam odczyt
//   służy CCA (słowo synchronizacji wykryte, ramka jeszcze trwa) i odbiorowi;
// - nośna CW: MOD_TYPE = 7 i dane PN9; korekta częstotliwości przez słowo SYNT (krok 23,8 Hz).
#pragma once

#include <Arduino.h>

#include "radio_link.h"
#include "s2lp.h"

namespace s2lp {

class LinkDriver : public radiolink::Driver {
public:
    explicit LinkDriver(Radio& radio) : radio_(radio) {}

    const char* name() const override { return "S2LP"; }
    const char* stateName() override { return s2lp::stateName(radio_.status().state()); }
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
    int32_t frequencyOffsetRaw() override;
    double frequencyStepHz() const override;
    bool frequencyErrorHz(int32_t&) override { return false; }  // AFC_CORR bez jednostki w karcie

    uint32_t irqSeen() const { return irqSeen_; }  // wszystkie przerwania od startu, do diagnostyki

private:
    void toReady();
    void setLength(bool variable, uint16_t length);
    void collectIrq();
    radiolink::RxPoll restartRx(radiolink::RxPoll result);
    void writeSynth(int32_t steps);

    Radio& radio_;
    uint32_t irqPending_ = 0;   // zebrane, jeszcze nieobsłużone
    uint32_t irqSeen_ = 0;
    bool rxActive_ = false;
    bool rxVariable_ = false;
    uint8_t rxFixedLength_ = 0;
    bool inFrame_ = false;      // słowo synchronizacji wykryte, ramka jeszcze nieodebrana
    uint32_t inFrameSinceMs_ = 0;
    int32_t offsetSteps_ = 0;
    bool offsetSet_ = false;
};

}  // namespace s2lp
