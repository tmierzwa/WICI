// SPDX-License-Identifier: MIT
// SX1262 w profilu LoRa pilotażu jako radiolink::Driver dla measure::Bench (stacja L0):
// - konfiguracja jak w programie diagnostycznym L0 (RadioLib 7.6.0, SX1262::begin): TCXO 1,8 V
//   z DIO3, kalibracja po włączeniu TCXO, przetwornica DC-DC, DIO2 jako przełącznik nadawania,
//   RXEN z MCU (stan wysoki tylko w RX), poprawki z rozdziału 15 karty; moc, preambuła i słowo
//   synchronizacji z lora_profile.h; Rx Boosted (0x08AC = 0x96) dopisany do listy rejestrów
//   zachowywanych w uśpieniu (rozdz. 9.6);
// - nadawanie z bufora od adresu 0 z jawnym nagłówkiem (ramka wzorcowa to `length` bajtów treści),
//   koniec po przerwaniu TxDone, bez niego po czasie ramki + 100 ms powrót do STDBY_RC;
// - odbiór ciągły (SetRx 0xFFFFFF): ramka po RxDone, długość i początek z GetRxBufferStatus, RSSI
//   i SNR z GetPacketStatus; błąd CRC albo nagłówka daje Bad, układ zostaje w odbiorze;
// - przerwania czytane przez SPI (GetIrqStatus) przy każdym odpytaniu, bez linii DIO1;
// - nośna CW poleceniem SetTxContinuousWave; korekta częstotliwości słowem RF (krok 0,954 Hz).
// Łącza P1 nie ma (p1Link() = false): interfejs LoRa stosu w formacie RNode to osobny etap.
#pragma once

#include <Arduino.h>

#include "lora_profile.h"
#include "radio_link.h"
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
    bool p1Link() const override { return false; }
    bool hasSnr() const override { return true; }

private:
    void toStandby();
    void rxen(bool on);
    void setPacketParams(uint8_t payloadLength);
    void writeFrequency();
    void collectIrq(uint16_t irq) { irqSeen_ |= irq; }

    Radio& radio_;
    uint8_t pinRxen_;
    bool rxen_ = false;
    bool rxActive_ = false;
    bool rxVariable_ = false;
    uint8_t rxFixedLength_ = 0;
    bool inFrame_ = false;      // preambuła albo nagłówek wykryte, ramka jeszcze nieodebrana
    uint32_t inFrameSinceMs_ = 0;
    uint16_t irqSeen_ = 0;
    int32_t offsetSteps_ = 0;
};

}  // namespace sx1262
