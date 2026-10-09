// SPDX-License-Identifier: MIT
#include "measure.h"

#include <string.h>

#include "cmdargs.h"
#include "jsonprint.h"
#include "p1_registers.h"
#include "testframe.h"

namespace measure {

namespace {

using cmdargs::boolName;

// Czas nadawania jednej ramki wzorcowej: preambuła 8 B, słowo 4 B, ramka len B, narastanie.
constexpr uint32_t frameAirMs(uint8_t length) {
    return (static_cast<uint32_t>(12 + length) * 8 * 1000 + p1::SYMBOL_RATE - 1) / p1::SYMBOL_RATE + 3;
}
static_assert(MAX_DEBT_MS == SERIES_MAX_MS * p1::DEBT_FACTOR, "MAX_DEBT_MS");
static_assert(p1frame::MAX_FRAGMENTS * frameAirMs(p1frame::MAX_LEN + 1) <= SERIES_MAX_MS, "rezerwacja P1 mieści się w MAX_DEBT_MS");

}  // namespace

namespace {

// Wiersz diagnostyczny z inicjatywy stacji (odbiór, koniec nadania) tylko przy wolnym miejscu w buforze
// portu: zapis do CDC na nRF52 czeka, aż komputer odczyta, więc terminal, który przestał czytać,
// zatrzymałby pętlę stacji aż do watchdoga. Pominięty wiersz nie zmienia liczników łącza.
bool diagFree() { return Serial.availableForWrite() > 0; }

}  // namespace

Bench::Bench(radiolink::Driver& radio, uint8_t pinOk, int16_t pinLed) : radio_(radio), pinOk_(pinOk), pinLed_(pinLed) {}

void Bench::led(bool on) {
    if (pinLed_ >= 0) digitalWrite(static_cast<uint8_t>(pinLed_), on ? LOW : HIGH);  // diody DK aktywne stanem niskim
}

void Bench::attach(journal::Journal* journal, uint32_t (*uptimeS)()) {
    journal_ = journal;
    uptime_ = uptimeS;
}

void Bench::restoreDebt(uint32_t debtMs) {
    debtUntilMs_ = millis() + debtMs;
    debtActive_ = debtMs > 0;
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
            Serial.printf("%s{\"seq\":%lu,\"uptime_s\":%lu,", first ? "" : ",", static_cast<unsigned long>(record.seq),
                          static_cast<unsigned long>(record.uptimeS));
            jsonprint::field(Serial, "event", record.text);  // tekst z laptopa i stosu: z sekwencjami ucieczki
            Serial.print('}');
            first = false;
        }
        Serial.printf("],\"total\":%lu,\"fram\":true}\n", static_cast<unsigned long>(journal_->eventSeq()));
        return;
    }
    Serial.printf("{\"log\":[");
    const size_t available = eventCount_ < LOG_ENTRIES ? eventCount_ : LOG_ENTRIES;
    const size_t shown = count < available ? count : available;
    for (size_t i = 0; i < shown; ++i) {  // od najnowszego, jak z FRAM
        const Event& e = events_[(eventCount_ - 1 - i) % LOG_ENTRIES];
        Serial.printf("%s{\"ms\":%lu,", i ? "," : "", static_cast<unsigned long>(e.ms));
        jsonprint::field(Serial, "event", e.text);
        Serial.print('}');
    }
    Serial.printf("],\"total\":%u,\"fram\":false}\n", static_cast<unsigned>(eventCount_));
}

uint32_t Bench::debtRemainingMs() const {
    // Odczekany dług gaśnie na stałe: inaczej po 2^31 ms bez nadawania (cisza dłuższa niż 24,8 doby)
    // różnica znowu wyszłaby dodatnia i zablokowała nadawanie na tyle samo.
    if (!debtActive_) return 0;
    const uint32_t now = millis();
    if (static_cast<int32_t>(debtUntilMs_ - now) > 0) return debtUntilMs_ - now;
    debtActive_ = false;
    return 0;
}

bool Bench::confirm() {
    // Pętla stacji stoi w czasie oczekiwania, więc nośna albo seria nie może trwać dłużej niż jej dług.
    if (cwActive_ || pktActive_) {
        log("series stopped for confirmation");
        if (cwActive_) stopCw();
        if (pktActive_) finishPkt();
    }
    Serial.printf("{\"confirm\":\"press OK within %lu s\"}\n", static_cast<unsigned long>(CONFIRM_MS / 1000));
    const uint32_t start = millis();
    // Czekaj na puszczenie, jeśli już wciśnięty (zablokowany przycisk nie zatrzyma pętli dłużej niż CONFIRM_MS).
    while (digitalRead(pinOk_) == LOW && millis() - start < CONFIRM_MS) delay(5);
    while (millis() - start < CONFIRM_MS) {
        led((millis() / 100) & 1);  // szybkie miganie: czekam
        if (digitalRead(pinOk_) == LOW) {
            delay(20);
            if (digitalRead(pinOk_) == LOW) {
                // Puszczenie też liczone od startu: całe oczekiwanie ≤ CONFIRM_MS, poniżej limitu watchdoga.
                while (digitalRead(pinOk_) == LOW && millis() - start < CONFIRM_MS) delay(5);
                led(false);
                return true;
            }
        }
        delay(5);
    }
    led(false);
    return false;
}

const char* Bench::gate(uint32_t txMs, bool conducted) {
    if (!prep) return "preparation mode off: PREP 1";
    if (silence) return "radio silence";
    if (busy()) return "busy: STOP first";
    if (!p1Ready) return "radio not configured: CONFIG";  // bez tablicy P1 układ nadawałby na wartościach domyślnych
    if (conducted) {
        if (!confirm()) {
            log("conducted not confirmed");
            return "conducted not confirmed by OK";
        }
        log("conducted confirmed by OK");
        seriesDebtMs_ = 0;  // seria przewodowa do tłumika nie zapisuje długu
        return nullptr;
    }
    if (debtRemainingMs()) return "silence debt pending: see INFO tx_wait_ms";
    if (txMs > SERIES_MAX_MS) return "series above limit: add conducted";
    // Dług ciszy zapisany w dzienniku przed pierwszą ramką; błąd zapisu blokuje nadawanie.
    if (!journal_ || !journal_->ok()) return "debt journal unavailable: no FRAM";
    const uint32_t debtMs = txMs * p1::DEBT_FACTOR;
    if (!journal_->writeDebt(debtMs, uptimeS())) return "debt journal write failed";
    debtUntilMs_ = millis() + txMs + debtMs;  // dług liczy się od końca serii (endSeriesDebt)
    debtActive_ = true;
    seriesDebtMs_ = debtMs;
    debtPending_ = true;
    return nullptr;
}

void Bench::endSeriesDebt() {
    // radio.md: po nadaniu odczekuje się zapisany dług, więc liczy się go od końca serii.
    if (seriesDebtMs_) { debtUntilMs_ = millis() + seriesDebtMs_; debtActive_ = true; }
    seriesDebtMs_ = 0;
}

const char* Bench::txcw(uint32_t seconds, bool conducted) {
    if (seconds == 0 || seconds * 1000 > CW_MAX_MS) return "TXCW 1..10 s";
    const char* error = gate(seconds * 1000, conducted);
    if (error) return error;
    rxMode_ = RxMode::NONE;
    cwStartMs_ = millis();
    cwEndMs_ = cwStartMs_ + seconds * 1000;
    cwActive_ = true;
    const bool tx = radio_.startCw();
    char text[40];
    snprintf(text, sizeof(text), "TXCW %lu s%s", static_cast<unsigned long>(seconds), conducted ? " conducted" : "");
    log(text);
    // "marc": stan układu (CC1120: MARC, S2-LP: stan głównego sterownika).
    Serial.printf("{\"txcw\":%s,\"seconds\":%lu,\"conducted\":%s,\"marc\":\"%s\"}\n", boolName(tx),
                  static_cast<unsigned long>(seconds), boolName(conducted), radio_.stateName());
    if (!tx) stopCw();
    return nullptr;
}

void Bench::stopCw() {
    radio_.stopCw();
    cwActive_ = false;
    const uint32_t txMs = millis() - cwStartMs_;
    // Nośna trwała dłużej niż zaplanowano (pętla stała): dług z rzeczywistego czasu, zapisany ponownie.
    if (seriesDebtMs_ && txMs * p1::DEBT_FACTOR > seriesDebtMs_) {
        seriesDebtMs_ = txMs * p1::DEBT_FACTOR;
        if (journal_) journal_->writeDebt(seriesDebtMs_, uptimeS());
    }
    endSeriesDebt();
    Serial.printf("{\"txcw\":\"done\",\"tx_ms\":%lu,\"tx_wait_ms\":%lu}\n", static_cast<unsigned long>(txMs),
                  static_cast<unsigned long>(debtRemainingMs()));
}

const char* Bench::txpkt(uint16_t count, uint8_t length, uint32_t intervalMs, bool conducted, testframe::Fill fill) {
    if (count == 0) return "TXPKT <n> <len> [<ms>]";
    if (length < testframe::MIN_LENGTH || length > testframe::MAX_LENGTH) return "len 4..103";
    const uint32_t txMs = static_cast<uint32_t>(count) * frameAirMs(length);
    const char* error = gate(txMs, conducted);
    if (error) return error;
    rxMode_ = RxMode::NONE;
    radio_.idle();
    pktFill_ = fill;
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

bool Bench::sendOne() {
    uint8_t frame[testframe::MAX_LENGTH];
    testframe::build(frame, pktLen_, pktSent_, pktFill_);
    radiolink::TxTiming timing;
    const bool ok = radio_.transmit(frame, pktLen_, false, &timing);
    pktTxUs_ += timing.totalUs;
    if (pktSent_ == 0) {
        pktSyncSeen_ = timing.valid;
        pktLeadUs_ = timing.leadUs;
        pktOnAirUs_ = timing.onAirUs;
        pktTailUs_ = timing.tailUs;
    }
    return ok;
}

void Bench::finishPkt() {
    pktActive_ = false;
    endSeriesDebt();
    const uint32_t seriesMs = millis() - pktStartMs_;
    const uint32_t txMs = (pktTxUs_ + 999) / 1000;
    Serial.printf("{\"txpkt\":\"done\",\"sent\":%u,\"failed\":%u,\"len\":%u,\"series_ms\":%lu,\"tx_ms\":%lu,"
                  "\"tx_wait_ms\":%lu,\"sync_gpio\":%s,\"lead_ms\":%.2f,\"on_air_ms\":%.2f,\"tail_ms\":%.2f,"
                  "\"expected_on_air_ms\":%.2f}\n",
                  pktSent_, pktFailed_, pktLen_, static_cast<unsigned long>(seriesMs), static_cast<unsigned long>(txMs),
                  static_cast<unsigned long>(debtRemainingMs()), boolName(pktSyncSeen_), pktLeadUs_ / 1000.0,
                  pktOnAirUs_ / 1000.0, pktTailUs_ / 1000.0, pktLen_ * 8 * 1000.0 / p1::SYMBOL_RATE);
}

bool Bench::enterRx(RxMode mode, uint8_t length) {
    // Ramki wzorcowe: stała długość; ramki P1: zmienna długość z bajtem LEN do 102 (F79).
    rxLen_ = length;
    rxMode_ = radio_.startRx(mode == RxMode::P1, length) ? mode : RxMode::NONE;
    return rxMode_ == mode;
}

const char* Bench::rxStart(uint8_t length) {
    // Odbiór ramek wzorcowych wyłącza odbiór P1 stacji: tylko w trybie przygotowania.
    if (!prep) return "preparation mode off: PREP 1";
    if (length < testframe::MIN_LENGTH || length > testframe::MAX_LENGTH) return "len 4..103";
    if (busy()) return "busy: STOP first";
    counters_ = Counters();
    counters_.startedMs = millis();
    return enterRx(RxMode::TEST, length) ? nullptr : "radio did not enter RX";
}

const char* Bench::p1rxStart() {
    if (busy()) return "busy: STOP first";
    return enterRx(RxMode::P1, 0) ? nullptr : "radio did not enter RX";
}

void Bench::receive() {
    radiolink::Frame frame;
    for (;;) {
        const radiolink::RxPoll result = radio_.pollRx(frame);
        if (result == radiolink::RxPoll::Overflow) { ++counters_.overflow; return; }
        if (result == radiolink::RxPoll::Bad) { ++counters_.rxBad; return; }  // odbiór uruchomiony od nowa
        if (result != radiolink::RxPoll::Frame) return;
        uint16_t seq = 0;
        if (testframe::check(frame.bytes, rxLen_, &seq)) {
            ++counters_.rxOk;
            counters_.rssiSum += frame.rssiDbm;
            counters_.lqiSum += frame.quality;
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
                  rxLen_, static_cast<unsigned long>(seconds), boolName(rxMode_ == RxMode::TEST));
    counters_ = Counters();
    counters_.startedMs = millis();
}

const char* Bench::foff(int32_t hz) {
    // CC1120: FREQOFF (krok 30,5 Hz, zakres ±999 985 Hz); S2-LP: słowo SYNT (krok 23,8 Hz, ±1 MHz).
    // Zmienia częstotliwość łącza P1 stacji: tylko w trybie przygotowania i bez nadawania w toku.
    if (!prep) return "preparation mode off: PREP 1";
    if (busy()) return "busy: STOP first";
    if (!radio_.setFrequencyOffset(hz)) return "FOFF outside the radio range (about +-1 MHz)";
    foffHz_ = hz;
    foffSet_ = true;
    char text[40];
    snprintf(text, sizeof(text), "FOFF %ld Hz", static_cast<long>(hz));
    log(text);
    return nullptr;
}

void Bench::applyOffset() {
    if (foffSet_) radio_.reapplyFrequencyOffset();
}

void Bench::printFoff() {
    // "freqoff": rejestr korekty (CC1120: FREQOFF; S2-LP: zmiana słowa SYNT wobec tablicy P1).
    const int32_t reg = radio_.frequencyOffsetRaw();
    const double stepHz = radio_.frequencyStepHz();
    Serial.printf("{\"foff_hz\":%ld,\"set\":%s,\"freqoff\":%ld,\"applied_hz\":%.1f,\"step_hz\":%.2f}\n",
                  static_cast<long>(foffHz_), boolName(foffSet_), static_cast<long>(reg), reg * stepHz, stepHz);
}

void Bench::printStatus() {
    Serial.printf("{\"prep\":%s,\"silence\":%s,\"txcw\":%s,\"txpkt\":%s,\"rx\":%s,\"tx_wait_ms\":%lu,"
                  "\"debt_pending\":%s,\"journal\":%s,\"foff_hz\":%ld}\n",
                  boolName(prep), boolName(silence), boolName(cwActive_), boolName(pktActive_), boolName(receiving()),
                  static_cast<unsigned long>(debtRemainingMs()), boolName(debtPending_),
                  boolName(journal_ && journal_->ok()), static_cast<long>(foffHz_));
}

void Bench::stop() {
    if (cwActive_) stopCw();
    if (pktActive_) finishPkt();
    if (txState_ != TxState::IDLE) { ++link_.txDrop; finishP1Tx("stopped"); }
    rxMode_ = RxMode::NONE;
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
    // Cisza radiowa przerywa każdą serię, także przewodową (radio.md: cisza blokuje każde nadawanie).
    if (cwActive_) {
        if (static_cast<int32_t>(now - cwEndMs_) >= 0) stopCw();
        else if (silence) { log("silence during TXCW"); stopCw(); }
        return;
    }
    if (pktActive_) {
        if (silence) { log("silence during TXPKT"); finishPkt(); return; }
        if (static_cast<int32_t>(now - pktNextMs_) >= 0) {
            if (!sendOne()) ++pktFailed_;
            ++pktSent_;
            pktNextMs_ = millis() + pktIntervalMs_;
            if (pktSent_ >= pktTotal_) finishPkt();
        }
        return;
    }
    if (txState_ != TxState::IDLE) pollP1Tx();
    if (!prep && p1Ready && rxMode_ == RxMode::NONE && !busy() && now - autoRxMs_ >= 1000) {
        autoRxMs_ = now;  // najwyżej raz na sekundę, gdy układ nie wchodzi w odbiór
        if (enterRx(RxMode::P1, 0)) log("P1 RX resumed");
    }
    if (rxMode_ != RxMode::NONE && now - rxPollMs_ >= 5) {
        rxPollMs_ = now;
        if (rxMode_ == RxMode::TEST) receive();
        else receiveP1();
    }
}

// --- łącze P1 -------------------------------------------------------------------

void Bench::receiveP1() {
    assembler_.expire(millis());
    radiolink::Frame received;
    for (;;) {
        const radiolink::RxPoll result = radio_.pollRx(received);
        if (result == radiolink::RxPoll::Overflow || result == radiolink::RxPoll::Bad) {
            ++link_.rxBad;  // przepełnienie, zła długość albo ramka niepełna; odbiór uruchomiony od nowa
            return;
        }
        if (result != radiolink::RxPoll::Frame) return;
        const uint8_t* frame = received.bytes;
        const size_t length = received.length;
        const int16_t rssiDbm = received.rssiDbm;
        p1frame::Fragment fragment;
        const p1frame::Parse parse = p1frame::parseFrame(frame, length, fragment);
        if (parse != p1frame::Parse::OK) {
            ++link_.rxBad;
            if (diagFree()) Serial.printf("{\"p1rx\":\"rejected\",\"reason\":\"%s\",\"len\":%u,\"rssi_dbm\":%d}\n", p1frame::parseName(parse),
                          frame[0], rssiDbm);
            continue;
        }
        ++link_.rxOk;
        const p1frame::Outcome outcome = assembler_.push(fragment, millis());
        if (outcome == p1frame::Outcome::COMPLETE) {
            ++link_.rxDatagrams;
            if (diagFree()) {
                Serial.printf("{\"p1rx\":\"datagram\",\"id\":\"");
                for (size_t i = 0; i < p1frame::ID_BYTES; ++i) Serial.printf("%02X", assembler_.completedId()[i]);
                Serial.printf("\",\"len\":%u,\"fragments\":%u,\"rssi_dbm\":%d,\"data\":\"",
                              static_cast<unsigned>(assembler_.completedLength()), fragment.count, rssiDbm);
                for (size_t i = 0; i < assembler_.completedLength(); ++i) Serial.printf("%02X", assembler_.completed()[i]);
                Serial.println("\"}");
            }
            if (datagramHandler_) datagramHandler_(assembler_.completed(), assembler_.completedLength(), datagramContext_);
        } else if (diagFree()) {
            Serial.printf("{\"p1rx\":\"%s\",\"index\":%u,\"count\":%u,\"total\":%u,\"rssi_dbm\":%d}\n",
                          p1frame::outcomeName(outcome), fragment.index, fragment.count, fragment.total, rssiDbm);
        }
    }
}

namespace {

// Odroczenie losowe 100..1000 ms z generatora stacji (nie z identyfikatora, który idzie w eter).
uint32_t backoffMs() {
    uint8_t b[2];
    randomBytes(b, sizeof(b));
    return BACKOFF_MIN_MS + ((static_cast<uint32_t>(b[0]) << 8) | b[1]) % (BACKOFF_MAX_MS - BACKOFF_MIN_MS + 1);
}

}  // namespace

const char* Bench::p1send(const uint8_t* data, size_t length, bool stack) {
    if (length < 1 || length > p1frame::MAX_DATAGRAM) return "datagram 1..600 B";
    if (!stack && !prep) return "preparation mode off: PREP 1";   // P1TX z portu diagnostycznego: tylko w przygotowaniu
    if (busy()) return "busy: STOP first";
    if (!p1Ready) return "radio not configured: CONFIG";
    if (silence && !(stack && silenceException)) { ++link_.txDrop; return "radio silence"; }
    if (!journal_ || !journal_->ok()) { ++link_.txDrop; return "debt journal unavailable: no FRAM"; }
    memcpy(txData_, data, length);
    txLength_ = length;
    txStack_ = stack;
    randomBytes(txId_, p1frame::ID_BYTES);  // identyfikator datagramu z generatora stacji
    txDeferrals_ = 0;
    txRequestedMs_ = millis();
    if (rxMode_ != RxMode::P1 && !enterRx(RxMode::P1, 0)) return "radio did not enter RX";
    if (debtRemainingMs()) txState_ = TxState::WAIT_DEBT;
    else startCca(txRequestedMs_, true);
    return nullptr;
}

void Bench::startCca(uint32_t now, bool first) {
    txState_ = TxState::CCA;
    if (first) ccaFirstMs_ = now;
    ccaStartMs_ = now;
    ccaCheckMs_ = now;
    ccaFrames_ = link_.rxOk + link_.rxBad;
}

bool Bench::channelBusy() {
    // Kanał zajęty: trwa odbiór po słowie synchronizacji, ramka przyszła w czasie okna CCA albo
    // RSSI ponad progiem CCA.
    if (radio_.receivingFrame()) return true;
    receiveP1();  // ramka, która zaczęła się i skończyła między próbkami, czeka w kolejce
    if (link_.rxOk + link_.rxBad != ccaFrames_) return true;
    const radiolink::Rssi r = radio_.rssi();
    return r.valid && r.dbm > p1::CCA_THRESHOLD_DBM;
}

void Bench::pollP1Tx() {
    const uint32_t now = millis();
    if (silence && !(txStack_ && silenceException)) { ++link_.txDrop; finishP1Tx("silence"); return; }
    switch (txState_) {
        case TxState::WAIT_DEBT:
            if (debtRemainingMs() == 0) startCca(now, true);
            return;
        case TxState::BACKOFF:
            if (static_cast<int32_t>(now - backoffUntilMs_) >= 0) startCca(now, false);
            return;
        case TxState::CCA: {
            if (now == ccaCheckMs_) return;
            // Okno 50 ms musi być obserwowane: po długiej przerwie między próbkami (pętla zajęta
            // kryptografią stosu) zaczyna się od nowa.
            const bool gap = now - ccaCheckMs_ > CCA_GAP_MS;
            ccaCheckMs_ = now;
            if (channelBusy()) {
                if (++txDeferrals_ > MAX_DEFERRALS) { ++link_.txDrop; finishP1Tx("too many deferrals"); return; }
                ++link_.deferrals;
                backoffUntilMs_ = now + backoffMs();
                txState_ = TxState::BACKOFF;
                return;
            }
            if (gap) { startCca(now, false); return; }
            if (now - ccaStartMs_ < CCA_MS) return;
            txState_ = TxState::SEND;  // nadanie w tym samym obiegu, bez przerwy po ostatniej próbce
        }
            [[fallthrough]];
        case TxState::SEND: {
            if (now - ccaFirstMs_ > LONG_DEFERRAL_MS) ++link_.longDeferrals;
            const uint8_t count = p1frame::fragmentCount(txLength_);
            const uint32_t txMs = count * frameAirMs(p1frame::MAX_LEN + 1);  // rezerwacja: najdłuższe ramki
            if (!journal_->writeDebt(txMs * p1::DEBT_FACTOR, uptimeS())) { ++link_.txDrop; finishP1Tx("debt journal write failed"); return; }
            debtPending_ = true;
            const bool ok = sendFragments();
            debtUntilMs_ = millis() + txMs * p1::DEBT_FACTOR;  // dług od końca nadawania
            debtActive_ = true;
            finishP1Tx(ok ? "sent" : "tx error");
            return;
        }
        case TxState::IDLE:
            return;
    }
}

bool Bench::sendFragments() {
    const uint8_t count = p1frame::fragmentCount(txLength_);
    bool ok = true;
    radio_.idle();
    for (uint8_t index = 0; index < count; ++index) {
        // Zmienna długość: układ wysyła LEN bajtów po bajcie LEN.
        uint8_t frame[p1frame::MAX_FRAME];
        const size_t n = p1frame::buildFrame(txData_, txLength_, txId_, index, frame);
        if (!radio_.transmit(frame, n, true, nullptr)) ok = false;
        ++link_.txFragments;
    }
    ++link_.txDatagrams;
    enterRx(RxMode::P1, 0);  // odbiór wyłączony tylko na czas własnego nadawania
    return ok;
}

void Bench::dropP1Tx() {
    if (txState_ != TxState::WAIT_DEBT && txState_ != TxState::CCA && txState_ != TxState::BACKOFF) return;
    ++link_.txDrop;
    finishP1Tx("silence");
}

void Bench::finishP1Tx(const char* result) {
    txState_ = TxState::IDLE;
    if (diagFree()) {
        Serial.printf("{\"p1tx\":\"%s\",\"id\":\"", result);
        for (size_t i = 0; i < p1frame::ID_BYTES; ++i) Serial.printf("%02X", txId_[i]);
        Serial.printf("\",\"len\":%u,\"fragments\":%u,\"deferrals\":%u,\"wait_ms\":%lu,\"tx_wait_ms\":%lu}\n",
                      static_cast<unsigned>(txLength_), p1frame::fragmentCount(txLength_), txDeferrals_,
                      static_cast<unsigned long>(millis() - txRequestedMs_), static_cast<unsigned long>(debtRemainingMs()));
    }
    if (rxMode_ != RxMode::P1) enterRx(RxMode::P1, 0);
    if (txDoneHandler_) txDoneHandler_(!strcmp(result, "sent"), txDoneContext_);
}

void Bench::printLink() {
    const p1frame::Stats& s = assembler_.stats();
    // Dwie części poniżej 256 znaków: Print::printf rdzenia Adafruit nRF52 formatuje do bufora 256 B.
    Serial.printf("{\"p1\":{\"rx\":%s,\"tx\":\"%s\",\"rx_ok\":%lu,\"rx_bad\":%lu,\"rx_datagrams\":%lu,\"tx_datagrams\":%lu,"
                  "\"tx_fragments\":%lu,\"tx_drop\":%lu,\"deferrals\":%lu,\"long_deferrals\":%lu,",
                  boolName(rxMode_ == RxMode::P1), txState_ == TxState::IDLE ? "idle" : txState_ == TxState::WAIT_DEBT ? "wait_debt"
                  : txState_ == TxState::CCA ? "cca" : txState_ == TxState::BACKOFF ? "backoff" : "send",
                  static_cast<unsigned long>(link_.rxOk), static_cast<unsigned long>(link_.rxBad),
                  static_cast<unsigned long>(link_.rxDatagrams), static_cast<unsigned long>(link_.txDatagrams),
                  static_cast<unsigned long>(link_.txFragments), static_cast<unsigned long>(link_.txDrop),
                  static_cast<unsigned long>(link_.deferrals), static_cast<unsigned long>(link_.longDeferrals));
    Serial.printf("\"attempts\":%u,\"stored\":%lu,\"duplicates\":%lu,\"conflicts\":%lu,\"late\":%lu,\"evicted\":%lu,\"expired\":%lu,"
                  "\"cca_threshold_dbm\":%d,\"tx_wait_ms\":%lu}}\n",
                  static_cast<unsigned>(assembler_.active()), static_cast<unsigned long>(s.stored),
                  static_cast<unsigned long>(s.duplicates), static_cast<unsigned long>(s.conflicts),
                  static_cast<unsigned long>(s.late), static_cast<unsigned long>(s.evicted),
                  static_cast<unsigned long>(s.expired), p1::CCA_THRESHOLD_DBM, static_cast<unsigned long>(debtRemainingMs()));
}

}  // namespace measure
