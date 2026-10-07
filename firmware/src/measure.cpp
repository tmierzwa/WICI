// SPDX-License-Identifier: MIT
#include "measure.h"

#include <string.h>

#include "p1_registers.h"
#include "testframe.h"

namespace measure {

namespace {

const char* boolName(bool value) { return value ? "true" : "false"; }

// Czas nadawania jednej ramki wzorcowej: preambuła 8 B, słowo 4 B, ramka len B, narastanie.
uint32_t frameAirMs(uint8_t length) {
    return (static_cast<uint32_t>(12 + length) * 8 * 1000 + p1::SYMBOL_RATE - 1) / p1::SYMBOL_RATE + 3;
}

const cc1120::RegisterValue* find(const char* name) {
    for (size_t i = 0; i < p1::REGISTER_COUNT; ++i) {
        if (!strcmp(p1::REGISTERS[i].name, name)) return &p1::REGISTERS[i];
    }
    return nullptr;
}

}  // namespace

Bench::Bench(cc1120::Radio& radio, uint8_t pinSync, uint8_t pinOk, uint8_t pinLed)
    : radio_(radio), pinSync_(pinSync), pinOk_(pinOk), pinLed_(pinLed) {}

void Bench::attach(journal::Journal* journal, uint32_t (*uptimeS)()) {
    journal_ = journal;
    uptime_ = uptimeS;
}

void Bench::restoreDebt(uint32_t debtMs) {
    debtUntilMs_ = millis() + debtMs;
    debtPending_ = debtMs > 0;
}

void Bench::log(const char* text) {
    if (journal_ && journal_->ok() && journal_->writeEvent(uptimeS(), text)) return;
    // Dziennik zapasowy w RAM, gdy FRAM nie odpowiada; najstarsze wpisy nadpisywane.
    Event& e = events_[eventCount_ % LOG_ENTRIES];
    e.ms = millis();
    strncpy(e.text, text, sizeof(e.text) - 1);
    e.text[sizeof(e.text) - 1] = '\0';
    ++eventCount_;
}

void Bench::printLog(uint32_t count) {
    if (journal_ && journal_->ok()) {
        // Od najnowszego wstecz; numery rekordów rosną od startu dziennika.
        Serial.printf("{\"log\":[");
        journal::EventRecord record;
        bool first = true;
        for (uint32_t back = 0; back < count; ++back) {
            if (!journal_->readEvent(back, record)) break;
            Serial.printf("%s{\"seq\":%lu,\"uptime_s\":%lu,\"event\":\"%s\"}", first ? "" : ",",
                          static_cast<unsigned long>(record.seq), static_cast<unsigned long>(record.uptimeS), record.text);
            first = false;
        }
        Serial.printf("],\"total\":%lu,\"fram\":true}\n", static_cast<unsigned long>(journal_->eventSeq()));
        return;
    }
    Serial.printf("{\"log\":[");
    const size_t shown = eventCount_ < LOG_ENTRIES ? eventCount_ : LOG_ENTRIES;
    const size_t firstIndex = eventCount_ - shown;
    for (size_t i = 0; i < shown; ++i) {
        const Event& e = events_[(firstIndex + i) % LOG_ENTRIES];
        Serial.printf("%s{\"ms\":%lu,\"event\":\"%s\"}", i ? "," : "", static_cast<unsigned long>(e.ms), e.text);
    }
    Serial.printf("],\"total\":%u,\"fram\":false}\n", static_cast<unsigned>(eventCount_));
}

uint32_t Bench::debtRemainingMs() const {
    const uint32_t now = millis();
    return static_cast<int32_t>(debtUntilMs_ - now) > 0 ? debtUntilMs_ - now : 0;
}

bool Bench::confirm() {
    Serial.printf("{\"confirm\":\"press OK within %lu s\"}\n", static_cast<unsigned long>(CONFIRM_MS / 1000));
    const uint32_t start = millis();
    while (digitalRead(pinOk_) == LOW) delay(5);  // czekaj na puszczenie, jeśli już wciśnięty
    while (millis() - start < CONFIRM_MS) {
        digitalWrite(pinLed_, ((millis() / 100) & 1) ? LOW : HIGH);  // szybkie miganie: czekam
        if (digitalRead(pinOk_) == LOW) {
            delay(20);
            if (digitalRead(pinOk_) == LOW) {
                while (digitalRead(pinOk_) == LOW) delay(5);
                digitalWrite(pinLed_, HIGH);
                return true;
            }
        }
        delay(5);
    }
    digitalWrite(pinLed_, HIGH);
    return false;
}

const char* Bench::gate(uint32_t txMs, bool conducted) {
    if (!prep) return "preparation mode off: PREP 1";
    if (silence) return "radio silence";
    if (busy()) return "busy: STOP first";
    if (conducted) {
        if (!confirm()) {
            log("conducted not confirmed");
            return "conducted not confirmed by OK";
        }
        log("conducted confirmed by OK");
        return nullptr;
    }
    if (debtRemainingMs()) return "silence debt pending: see INFO tx_wait_ms";
    if (txMs > SERIES_MAX_MS) return "series above limit: add conducted";
    // Dług ciszy zapisany w dzienniku przed pierwszą ramką; błąd zapisu blokuje nadawanie.
    if (!journal_ || !journal_->ok()) return "debt journal unavailable: no FRAM";
    const uint32_t debtMs = txMs * p1::DEBT_FACTOR;
    if (!journal_->writeDebt(debtMs, uptimeS())) return "debt journal write failed";
    debtUntilMs_ = millis() + debtMs;
    debtPending_ = true;
    return nullptr;
}

void Bench::restore(const char* name) {
    const cc1120::RegisterValue* reg = find(name);
    if (reg) radio_.writeReg(reg->address, reg->value);
}

const char* Bench::txcw(uint32_t seconds, bool conducted) {
    if (seconds == 0 || seconds * 1000 > CW_MAX_MS) return "TXCW 1..10 s";
    const char* error = gate(seconds * 1000, conducted);
    if (error) return error;
    if (rxActive_) {
        rxActive_ = false;
    }
    radio_.idle();
    radio_.strobe(cc1120::SFTX);
    // Nośna bez modulacji: 2-FSK z dewiacją 0, dane losowe PN9, pakiet nieskończony.
    radio_.writeReg(cc1120::DEVIATION_M, 0x00);
    radio_.writeReg(cc1120::MODCFG_DEV_E, 0x00);
    radio_.writeReg(cc1120::PKT_CFG2, static_cast<uint8_t>((find("PKT_CFG2")->value & ~0x03) | cc1120::PKT_FORMAT_RANDOM));
    radio_.writeReg(cc1120::PKT_CFG0, cc1120::LENGTH_CONFIG_INFINITE);
    const uint8_t seed = 0x00;
    radio_.writeFifo(&seed, 1);  // TXLAST != TXFIRST wymagane w trybie losowym
    cwStartMs_ = millis();
    cwEndMs_ = cwStartMs_ + seconds * 1000;
    cwActive_ = true;
    radio_.strobe(cc1120::STX);
    const bool tx = radio_.waitMarcState(cc1120::MARC_STATE_TX, 50);
    char text[40];
    snprintf(text, sizeof(text), "TXCW %lu s%s", static_cast<unsigned long>(seconds), conducted ? " conducted" : "");
    log(text);
    Serial.printf("{\"txcw\":%s,\"seconds\":%lu,\"conducted\":%s,\"marc\":\"%s\"}\n", boolName(tx),
                  static_cast<unsigned long>(seconds), boolName(conducted), cc1120::marcStateName(radio_.readMarcState()));
    if (!tx) stopCw();
    return nullptr;
}

void Bench::stopCw() {
    radio_.idle();
    radio_.strobe(cc1120::SFTX);
    restore("DEVIATION_M");
    restore("MODCFG_DEV_E");
    restore("PKT_CFG2");
    restore("PKT_CFG0");
    cwActive_ = false;
    const uint32_t txMs = millis() - cwStartMs_;
    Serial.printf("{\"txcw\":\"done\",\"tx_ms\":%lu,\"tx_wait_ms\":%lu}\n", static_cast<unsigned long>(txMs),
                  static_cast<unsigned long>(debtRemainingMs()));
}

const char* Bench::txpkt(uint16_t count, uint8_t length, uint32_t intervalMs, bool conducted) {
    if (count == 0) return "TXPKT <n> <len> [<ms>]";
    if (length < testframe::MIN_LENGTH || length > testframe::MAX_LENGTH) return "len 4..103";
    const uint32_t txMs = static_cast<uint32_t>(count) * frameAirMs(length);
    const char* error = gate(txMs, conducted);
    if (error) return error;
    rxActive_ = false;
    radio_.idle();
    radio_.writeReg(cc1120::PKT_LEN, length);
    pktTotal_ = count;
    pktSent_ = 0;
    pktFailed_ = 0;
    pktLen_ = length;
    pktIntervalMs_ = intervalMs;
    pktNextMs_ = millis();
    pktStartMs_ = pktNextMs_;
    pktTxUs_ = pktLeadUs_ = pktOnAirUs_ = pktTailUs_ = 0;
    pktSyncSeen_ = false;
    pktConducted_ = conducted;
    pktActive_ = true;
    char text[40];
    snprintf(text, sizeof(text), "TXPKT %u x %u B%s", count, length, conducted ? " conducted" : "");
    log(text);
    Serial.printf("{\"txpkt\":\"started\",\"n\":%u,\"len\":%u,\"ms\":%lu,\"conducted\":%s,\"tx_ms_planned\":%lu}\n", count,
                  length, static_cast<unsigned long>(intervalMs), boolName(conducted), static_cast<unsigned long>(txMs));
    return nullptr;
}

bool Bench::waitSync(bool level, uint32_t timeoutUs) {
    const uint32_t start = micros();
    while (micros() - start < timeoutUs) {
        if ((digitalRead(pinSync_) == HIGH) == level) return true;
    }
    return false;
}

bool Bench::sendOne() {
    uint8_t frame[testframe::MAX_LENGTH];
    testframe::build(frame, pktLen_, pktSent_);
    radio_.strobe(cc1120::SFTX);
    radio_.writeFifo(frame, pktLen_);
    const uint32_t t0 = micros();
    radio_.strobe(cc1120::STX);
    // GPIO2 = PKT_SYNC_RXTX: wysoki od wysłania słowa synchronizacji do końca pakietu.
    const uint32_t onAirUs = static_cast<uint32_t>(pktLen_) * 8 * 1000000UL / p1::SYMBOL_RATE;
    const bool rose = waitSync(true, 80000);
    const uint32_t tSync = micros();
    bool fell = false;
    if (rose) {
        fell = waitSync(false, onAirUs + 50000);
    }
    const uint32_t tEnd = micros();
    const bool idle = radio_.waitMarcState(cc1120::MARC_STATE_IDLE, rose ? 30 : (onAirUs / 1000) + 120);
    const uint32_t tIdle = micros();
    if (radio_.readMarcState() == cc1120::MARC_STATE_TX_FIFO_ERR) {
        radio_.strobe(cc1120::SFTX);
        radio_.idle();
    }
    pktTxUs_ += tIdle - t0;
    if (pktSent_ == 0) {
        pktSyncSeen_ = rose && fell;
        pktLeadUs_ = rose ? tSync - t0 : 0;
        pktOnAirUs_ = fell ? tEnd - tSync : 0;
        pktTailUs_ = fell ? tIdle - tEnd : 0;
    }
    return idle;
}

void Bench::finishPkt() {
    pktActive_ = false;
    const uint32_t seriesMs = millis() - pktStartMs_;
    const uint32_t txMs = (pktTxUs_ + 999) / 1000;
    Serial.printf("{\"txpkt\":\"done\",\"sent\":%u,\"failed\":%u,\"len\":%u,\"series_ms\":%lu,\"tx_ms\":%lu,"
                  "\"tx_wait_ms\":%lu,\"sync_gpio\":%s,\"lead_ms\":%.2f,\"on_air_ms\":%.2f,\"tail_ms\":%.2f,"
                  "\"expected_on_air_ms\":%.2f}\n",
                  pktSent_, pktFailed_, pktLen_, static_cast<unsigned long>(seriesMs), static_cast<unsigned long>(txMs),
                  static_cast<unsigned long>(debtRemainingMs()), boolName(pktSyncSeen_), pktLeadUs_ / 1000.0,
                  pktOnAirUs_ / 1000.0, pktTailUs_ / 1000.0, pktLen_ * 8 * 1000.0 / p1::SYMBOL_RATE);
}

const char* Bench::rxStart(uint8_t length) {
    if (length < testframe::MIN_LENGTH || length > testframe::MAX_LENGTH) return "len 4..103";
    if (busy()) return "busy: STOP first";
    radio_.idle();
    radio_.strobe(cc1120::SFRX);
    radio_.writeReg(cc1120::PKT_LEN, length);
    rxLen_ = length;
    counters_ = Counters();
    counters_.startedMs = millis();
    radio_.strobe(cc1120::SRX);
    rxActive_ = radio_.waitMarcState(cc1120::MARC_STATE_RX, 50);
    return rxActive_ ? nullptr : "radio did not enter RX";
}

void Bench::receive() {
    const uint8_t marc = radio_.readMarcState();
    if (marc == cc1120::MARC_STATE_RX_FIFO_ERR) {
        ++counters_.overflow;
        radio_.idle();
        radio_.strobe(cc1120::SFRX);
        radio_.strobe(cc1120::SRX);
        return;
    }
    if (marc != cc1120::MARC_STATE_RX) {
        radio_.strobe(cc1120::SRX);  // np. po IDLE z innego polecenia
        return;
    }
    const size_t packet = static_cast<size_t>(rxLen_) + 2;  // ramka + RSSI + LQI
    uint8_t bytes = radio_.rxBytes();
    uint8_t buffer[testframe::MAX_LENGTH + 2];
    while (bytes >= packet) {
        radio_.readFifo(buffer, packet);
        bytes -= packet;
        const int8_t rssiRaw = static_cast<int8_t>(buffer[rxLen_]);
        const uint8_t lqi = buffer[rxLen_ + 1] & 0x7F;
        uint16_t seq = 0;
        if (testframe::check(buffer, rxLen_, &seq)) {
            ++counters_.rxOk;
            counters_.rssiSum += static_cast<int32_t>(rssiRaw) + p1::RSSI_OFFSET_DB;
            counters_.lqiSum += lqi;
            if (counters_.haveSeq) {
                if (seq > counters_.lastSeq + 1) counters_.missing += seq - counters_.lastSeq - 1;
                else if (seq <= counters_.lastSeq) ++counters_.reordered;
            }
            counters_.haveSeq = true;
            counters_.lastSeq = seq;
        } else {
            ++counters_.rxBad;
        }
    }
}

void Bench::rxper() {
    const Counters& c = counters_;
    const uint32_t seconds = (millis() - c.startedMs) / 1000;
    const uint32_t expected = c.rxOk + c.rxBad + c.missing;
    const double per = expected ? 100.0 * (c.rxBad + c.missing) / expected : 0.0;
    Serial.printf("{\"rx_ok\":%lu,\"rx_bad\":%lu,\"missing\":%lu,\"reordered\":%lu,\"overflow\":%lu,\"last_seq\":%d,"
                  "\"per_percent\":%.2f,\"rssi_avg_dbm\":%.1f,\"lqi_avg\":%.1f,\"len\":%u,\"seconds\":%lu,\"rx\":%s}\n",
                  static_cast<unsigned long>(c.rxOk), static_cast<unsigned long>(c.rxBad),
                  static_cast<unsigned long>(c.missing), static_cast<unsigned long>(c.reordered),
                  static_cast<unsigned long>(c.overflow), c.haveSeq ? c.lastSeq : -1, per,
                  c.rxOk ? static_cast<double>(c.rssiSum) / c.rxOk : 0.0, c.rxOk ? static_cast<double>(c.lqiSum) / c.rxOk : 0.0,
                  rxLen_, static_cast<unsigned long>(seconds), boolName(rxActive_));
    counters_ = Counters();
    counters_.startedMs = millis();
}

const char* Bench::foff(int32_t hz) {
    // FREQOFF = hz * LO_DIVIDER * 2^18 / f_xosc (SWRU295E, równanie 27); krok 30,5 Hz.
    const double raw = static_cast<double>(hz) * p1::LO_DIVIDER * 262144.0 / p1::F_XOSC_HZ;
    if (raw > 32767.0 || raw < -32768.0) return "FOFF outside +-1000000 Hz";
    foffHz_ = hz;
    foffSet_ = true;
    applyOffset();
    char text[40];
    snprintf(text, sizeof(text), "FOFF %ld Hz", static_cast<long>(hz));
    log(text);
    return nullptr;
}

void Bench::applyOffset() {
    if (!foffSet_) return;
    const int16_t reg = static_cast<int16_t>(lround(static_cast<double>(foffHz_) * p1::LO_DIVIDER * 262144.0 / p1::F_XOSC_HZ));
    const bool wasRx = rxActive_;
    radio_.idle();
    radio_.setFrequencyOffset(reg);
    if (wasRx) radio_.strobe(cc1120::SRX);
}

void Bench::printFoff() {
    const int16_t reg = radio_.frequencyOffset();
    const double appliedHz = static_cast<double>(reg) * p1::F_XOSC_HZ / 262144.0 / p1::LO_DIVIDER;
    Serial.printf("{\"foff_hz\":%ld,\"set\":%s,\"freqoff\":%d,\"applied_hz\":%.1f,\"step_hz\":%.2f}\n",
                  static_cast<long>(foffHz_), boolName(foffSet_), reg, appliedHz,
                  static_cast<double>(p1::F_XOSC_HZ) / 262144.0 / p1::LO_DIVIDER);
}

void Bench::printStatus() {
    Serial.printf("{\"prep\":%s,\"silence\":%s,\"txcw\":%s,\"txpkt\":%s,\"rx\":%s,\"tx_wait_ms\":%lu,"
                  "\"debt_pending\":%s,\"journal\":%s,\"foff_hz\":%ld}\n",
                  boolName(prep), boolName(silence), boolName(cwActive_), boolName(pktActive_), boolName(rxActive_),
                  static_cast<unsigned long>(debtRemainingMs()), boolName(debtPending_),
                  boolName(journal_ && journal_->ok()), static_cast<long>(foffHz_));
}

void Bench::stop() {
    if (cwActive_) stopCw();
    if (pktActive_) finishPkt();
    rxActive_ = false;
    radio_.idle();
}

void Bench::poll() {
    const uint32_t now = millis();
    if (debtPending_ && !busy() && debtRemainingMs() == 0) {
        // Dług kasuje się dopiero po odczekaniu (radio.md, "Dostęp do kanału", punkt 4).
        if (journal_ && journal_->ok() && journal_->writeDebt(0, uptimeS())) {
            debtPending_ = false;
            log("silence debt cleared");
        }
    }
    if (cwActive_) {
        if (static_cast<int32_t>(now - cwEndMs_) >= 0) stopCw();
        else if (silence) { log("silence during TXCW"); stopCw(); }
        return;
    }
    if (pktActive_) {
        if (silence && !pktConducted_) { log("silence during TXPKT"); finishPkt(); return; }
        if (static_cast<int32_t>(now - pktNextMs_) >= 0) {
            if (!sendOne()) ++pktFailed_;
            ++pktSent_;
            pktNextMs_ = millis() + pktIntervalMs_;
            if (pktSent_ >= pktTotal_) finishPkt();
        }
        return;
    }
    if (rxActive_ && now - rxPollMs_ >= 5) {
        rxPollMs_ = now;
        receive();
    }
}

}  // namespace measure
