// SPDX-License-Identifier: MIT
// CC1120 jako radiolink::Driver dla measure::Bench (wykonanie A): ramki wzorcowe ze stałą długością
// z PKT_LEN, ramki P1 ze zmienną długością (LEN w kolejce FIFO), status RSSI i LQI dopisany
// do każdej ramki, czasy ramki z GPIO2 = PKT_SYNC_RXTX, nośna CW z dewiacją 0 i danymi PN9,
// korekta FREQOFF (krok 30,5 Hz).
#pragma once

#include <Arduino.h>

#include "cc1120.h"
#include "radio_link.h"

namespace cc1120 {

class LinkDriver : public radiolink::Driver {
public:
    LinkDriver(Radio& radio, uint8_t pinSync) : radio_(radio), pinSync_(pinSync) {}

    const char* name() const override { return "CC1120"; }
    const char* stateName() override { return marcStateName(radio_.readMarcState()); }
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
    int32_t frequencyOffsetRaw() override { return radio_.frequencyOffset(); }
    double frequencyStepHz() const override;
    bool frequencyErrorHz(int32_t& hz) override;

private:
    void setLength(bool variable, uint8_t fixedLength);
    bool waitSync(bool level, uint32_t timeoutUs);
    radiolink::RxPoll restartRx(radiolink::RxPoll result);
    void applyOffset();

    Radio& radio_;
    uint8_t pinSync_;
    uint8_t fixedLength_ = 0;
    bool rxActive_ = false;
    bool rxVariable_ = false;
    uint8_t rxPendingLen_ = 0;   // P1: bajt LEN odczytany, reszta ramki w drodze
    uint32_t rxDeadlineMs_ = 0;
    int32_t offsetHz_ = 0;
    bool offsetSet_ = false;
};

}  // namespace cc1120
