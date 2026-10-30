// SPDX-License-Identifier: MIT
#include "measure.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "cmdargs.h"
#include "jsonprint.h"
#include "platform.h"
#include "testframe.h"

namespace measure {

namespace {

using cmdargs::boolName;

// Czas ramki w eterze podaje sterownik (Driver::frameAirMs); P1 tutaj tylko do sprawdzenia rezerwacji.
static_assert(MAX_DEBT_MS == SERIES_MAX_MS * radiolink::P1_DEBT_FACTOR, "MAX_DEBT_MS");
static_assert(p1frame::MAX_FRAGMENTS * radiolink::p1FrameAirMs(p1frame::MAX_LEN + 1) <= SERIES_MAX_MS,
              "rezerwacja P1 mieści się w MAX_DEBT_MS");
static_assert(radiolink::MAX_FRAME >= testframe::MAX_LENGTH && testframe::MAX_LENGTH >= p1frame::MAX_FRAME, "bufory ramek");

constexpr const char* NO_P1_LINK = "no P1 link on this radio";
constexpr const char* NO_LINK = "no stack link on this radio";
// Datagram LoRa mieści się w buforze nadawania wspólnym z P1; dług LoRa w granicy MAX_DEBT_MS.
static_assert(loraframe::MAX_DATAGRAM <= p1frame::MAX_DATAGRAM, "bufor datagramu");
static_assert(loraframe::reservedTxMs(loraframe::MAX_DATAGRAM) <= SERIES_MAX_MS, "rezerwacja LoRa mieści się w MAX_DEBT_MS");
static_assert(loraframe::reservedTxMs(loraframe::MAX_DATAGRAM) <= lora::SERIES_MAX_MS, "rezerwacja LoRa w limicie serii LoRa");
constexpr const char* EMC_ON_ERROR = "EMC mode on: EMC 0 first";
static_assert(FOFF_MAX_HZ == 50000, "tekst błędu FOFF");
// Okres EMC: ramka i jej dług ciszy (cykl pracy ≤ 1/13).
static_assert(EMC_PERIOD_FACTOR == radiolink::P1_DEBT_FACTOR + 1, "EMC_PERIOD_FACTOR");

}  // namespace

namespace {

// Wiersz diagnostyczny z inicjatywy stacji (odbiór, koniec nadania) wychodzi tylko w całości i tylko wtedy,
// gdy cały mieści się w wolnym miejscu bufora portu: zapis do CDC na nRF52 czeka, aż komputer odczyta, więc
// terminal, który przestał czytać, zatrzymałby pętlę stacji aż do watchdoga, także w połowie wiersza.
// Pominięty wiersz nie zmienia liczników łącza.
constexpr size_t DIAG_LINE = 192;   // najdłuższy wiersz poza datagramem: p1tx i emc, około 140 B

bool diagFits(size_t length) {
    const int room = Serial.availableForWrite();
    return room > 0 && static_cast<size_t>(room) >= length;
}

void diagLine(const char* format, ...) {
    char line[DIAG_LINE];
    va_list args;
    va_start(args, format);
    const int n = vsnprintf(line, sizeof(line), format, args);
    va_end(args);
    if (n > 0 && static_cast<size_t>(n) < sizeof(line) && diagFits(static_cast<size_t>(n)))
        Serial.write(reinterpret_cast<const uint8_t*>(line), static_cast<size_t>(n));
}

void hexInto(char* out, const uint8_t* data, size_t length) {
    for (size_t i = 0; i < length; ++i) snprintf(out + 2 * i, 3, "%02X", data[i]);
}

}  // namespace

Bench::Bench(radiolink::Driver& radio, uint8_t pinOk, int16_t pinLed) : radio_(radio), pinOk_(pinOk), pinLed_(pinLed) {}

const char* Bench::lengthError() {
    snprintf(lengthError_, sizeof(lengthError_), "len %u..%u", static_cast<unsigned>(testframe::MIN_LENGTH),
             static_cast<unsigned>(radio_.maxTestLength()));
    return lengthError_;
}

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
    if (emcActive_) return EMC_ON_ERROR;
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
    if (txMs > radio_.seriesMaxMs()) return "series above limit: add conducted";
    // Dług ciszy zapisany w dzienniku przed pierwszą ramką; błąd zapisu blokuje nadawanie.
    if (!journal_ || !journal_->ok()) return "debt journal unavailable: no FRAM";
    const uint32_t debtMs = txMs * radiolink::P1_DEBT_FACTOR;
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
    if (seriesDebtMs_ && txMs * radiolink::P1_DEBT_FACTOR > seriesDebtMs_) {
        seriesDebtMs_ = txMs * radiolink::P1_DEBT_FACTOR;
        if (journal_) journal_->writeDebt(seriesDebtMs_, uptimeS());
    }
    endSeriesDebt();
    Serial.printf("{\"txcw\":\"done\",\"tx_ms\":%lu,\"tx_wait_ms\":%lu}\n", static_cast<unsigned long>(txMs),
                  static_cast<unsigned long>(debtRemainingMs()));
}

const char* Bench::txpkt(uint16_t count, uint8_t length, uint32_t intervalMs, bool conducted, testframe::Fill fill) {
    if (count == 0) return "TXPKT <n> <len> [<ms>]";
    if (length < testframe::MIN_LENGTH || length > radio_.maxTestLength()) return lengthError();
    const uint32_t txMs = static_cast<uint32_t>(count) * radio_.frameAirMs(length);
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
                  pktOnAirUs_ / 1000.0, pktTailUs_ / 1000.0, radio_.onAirMs(pktLen_));
}

bool Bench::enterRx(RxMode mode, uint8_t length) {
    // Ramki wzorcowe: stała długość; ramki łącza: zmienna długość (P1: bajt LEN do 102, F79; LoRa: jawny nagłówek).
    if (mode == RxMode::LINK && radio_.framing() == radiolink::Framing::NONE) return false;
    rxLen_ = length;
    if (mode != ringMode_) {
        // Ramki innego trybu z pierścienia zadania odbioru nie idą do nowego (powrót do odbioru po
        // własnym nadaniu w tym samym trybie zostawia nieodczytane ramki).
        radio_.discardRx();
        ringMode_ = mode;
    }
    rxMode_ = radio_.startRx(mode == RxMode::LINK, length) ? mode : RxMode::NONE;
    if (rxMode_ == RxMode::LINK) rxSinceMs_ = millis();
    return rxMode_ == mode;
}

const char* Bench::rxStart(uint8_t length) {
    // Odbiór ramek wzorcowych wyłącza odbiór P1 stacji: tylko w trybie przygotowania.
    if (!prep) return "preparation mode off: PREP 1";
    if (emcActive_) return EMC_ON_ERROR;
    if (length < testframe::MIN_LENGTH || length > radio_.maxTestLength()) return lengthError();
    if (busy()) return "busy: STOP first";
    counters_ = Counters();
    counters_.startedMs = millis();
    return enterRx(RxMode::TEST, length) ? nullptr : "radio did not enter RX";
}

const char* Bench::linkRxStart() {
    if (radio_.framing() == radiolink::Framing::NONE) return NO_LINK;
    if (emcActive_) return EMC_ON_ERROR;
    if (busy()) return "busy: STOP first";
    return enterRx(RxMode::LINK, 0) ? nullptr : "radio did not enter RX";
}

const char* Bench::p1rxStart() { return radio_.p1Link() ? linkRxStart() : NO_P1_LINK; }

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
            counters_.snrSumQdb += frame.snrQdb;
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
    // SX1262: średni SNR osobnym wierszem, bez zmiany wiersza P1.
    if (radio_.hasSnr()) Serial.printf("{\"snr_avg_db\":%.2f,\"rx_ok\":%lu}\n", c.rxOk ? c.snrSumQdb / 4.0 / c.rxOk : 0.0,
                                       static_cast<unsigned long>(c.rxOk));
    counters_ = Counters();
    counters_.startedMs = millis();
}

const char* Bench::foff(int32_t hz) {
    // Sterownik: CC1120 FREQOFF (krok 30,5 Hz), S2-LP słowo SYNT (23,8 Hz), SX1262 słowo RF (0,95 Hz),
    // każdy do około ±1 MHz; stanowisko ogranicza korektę do podpasma (FOFF_MAX_HZ). Zmienia
    // częstotliwość łącza stacji: tylko w trybie przygotowania i bez nadawania w toku.
    if (!prep) return "preparation mode off: PREP 1";
    if (emcActive_) return EMC_ON_ERROR;
    if (busy()) return "busy: STOP first";
    if (hz > FOFF_MAX_HZ || hz < -FOFF_MAX_HZ) return "FOFF outside the subband: max +-50000 Hz";
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
    // "freqoff": rejestr korekty (CC1120: FREQOFF; S2-LP: zmiana słowa SYNT wobec tablicy P1; SX1262:
    // zmiana słowa RF wobec profilu LoRa).
    const int32_t reg = radio_.frequencyOffsetRaw();
    const double stepHz = radio_.frequencyStepHz();
    Serial.printf("{\"foff_hz\":%ld,\"set\":%s,\"freqoff\":%ld,\"applied_hz\":%.1f,\"step_hz\":%.2f}\n",
                  static_cast<long>(foffHz_), boolName(foffSet_), static_cast<long>(reg), reg * stepHz, stepHz);
}

void Bench::printStatus() {
    Serial.printf("{\"prep\":%s,\"silence\":%s,\"txcw\":%s,\"txpkt\":%s,\"rx\":%s,\"tx_wait_ms\":%lu,"
                  "\"debt_pending\":%s,\"journal\":%s,\"foff_hz\":%ld,\"emc\":%s}\n",
                  boolName(prep), boolName(silence), boolName(cwActive_), boolName(pktActive_), boolName(receiving()),
                  static_cast<unsigned long>(debtRemainingMs()), boolName(debtPending_),
                  boolName(journal_ && journal_->ok()), static_cast<long>(foffHz_), boolName(emcActive_));
}

void Bench::stop() {
    if (cwActive_) stopCw();
    if (pktActive_) finishPkt();
    if (txState_ != TxState::IDLE) { ++link_.txDrop; finishLinkTx("stopped"); }
    rxMode_ = RxMode::NONE;
    radio_.idle();
    // Rekonfiguracja i IDLE: znaczniki aktywności, ramki w pierścieniu zadania odbioru i oczekująca część
    // składania przestają obowiązywać.
    radio_.clearActivity();
    radio_.discardRx();
    loraAssembler_.reset();
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
    if (txState_ != TxState::IDLE) pollLinkTx();
    if (emcActive_) pollEmc(now);
    if (!prep && !emcActive_ && p1Ready && radio_.framing() != radiolink::Framing::NONE && rxMode_ == RxMode::NONE && !busy() &&
        now - autoRxMs_ >= 1000) {
        autoRxMs_ = now;  // najwyżej raz na sekundę, gdy układ nie wchodzi w odbiór
        if (enterRx(RxMode::LINK, 0)) log("link RX resumed");
    }
    if (rxMode_ != RxMode::NONE && now - rxPollMs_ >= 5) {
        rxPollMs_ = now;
        if (rxMode_ == RxMode::TEST) receive();
        else receiveLink();
    }
}

// --- tryb pracy do badań EMC ------------------------------------------------------

uint32_t Bench::emcMinPeriodS(uint8_t length) const { return (EMC_PERIOD_FACTOR * radio_.frameAirMs(length) + 999) / 1000; }

bool Bench::emcValid(uint32_t periodS, uint8_t length) const {
    if (length < testframe::MIN_LENGTH || length > radio_.maxTestLength()) return false;
    return periodS >= emcMinPeriodS(length) && periodS <= EMC_PERIOD_MAX_S;
}

void Bench::emcCommon(uint32_t periodS, uint8_t length) {
    stop();  // seria, odbiór P1 i datagram w drodze kończą się; dalej tylko ramki EMC
    emcActive_ = true;
    emcPeriodMs_ = periodS * 1000;
    emcLen_ = length;
    emcNextMs_ = millis();
    emcSeq_ = 0;
    emcSent_ = emcFailed_ = emcSilenced_ = emcSkipped_ = 0;
    emcStartedMs_ = millis();
    counters_ = Counters();
    counters_.startedMs = emcStartedMs_;
    rxLen_ = length;
}

const char* Bench::emcStart(uint32_t periodS, uint8_t length) {
    if (!prep) return "preparation mode off: PREP 1";
    if (busy()) return "busy: STOP first";
    if (!p1Ready) return "radio not configured: CONFIG";
    if (length < testframe::MIN_LENGTH || length > radio_.maxTestLength()) return lengthError();
    if (!emcValid(periodS, length)) {
        snprintf(emcError_, sizeof(emcError_), "period %lu..%lu s", static_cast<unsigned long>(emcMinPeriodS(length)),
                 static_cast<unsigned long>(EMC_PERIOD_MAX_S));
        return emcError_;
    }
    // Zapis w dzienniku przed pierwszą ramką: po restarcie tryb wraca z tymi samymi ustawieniami.
    if (!journal_ || !journal_->ok()) return "debt journal unavailable: no FRAM";
    if (!journal_->writeEmc(emcEncode(periodS, length))) return "EMC journal write failed";
    emcCommon(periodS, length);
    emcResumed_ = false;
    char text[40];
    snprintf(text, sizeof(text), "EMC %lu s x %u B", static_cast<unsigned long>(periodS), length);
    log(text);
    return nullptr;
}

bool Bench::emcResume(uint32_t mode) {
    if (!(mode & EMC_ON)) return false;
    if (!emcValid(emcPeriodS(mode), emcLength(mode))) {
        // Rekord spoza zakresu tego układu (np. obraz innej stacji na tej samej FRAM): bez nadawania.
        if (journal_ && journal_->ok()) journal_->writeEmc(0);
        log("EMC record invalid: cleared");
        return false;
    }
    emcCommon(emcPeriodS(mode), emcLength(mode));
    emcResumed_ = true;
    log("EMC resumed after restart");
    return true;
}

const char* Bench::emcStop() {
    // Rekord kasowany przed zatrzymaniem; nieudany zapis zostawia tryb w dzienniku (wróci po restarcie),
    // więc wynik idzie do odpowiedzi, a następne EMC 0 albo STOP próbuje znowu.
    const char* error = nullptr;
    if (journal_ && journal_->ok() && journal_->emc() && !journal_->writeEmc(0)) {
        error = "EMC journal clear failed: mode returns after restart";
        log("EMC journal clear failed");
    }
    if (!emcActive_) return error;
    emcActive_ = false;
    if (rxMode_ == RxMode::TEST) {
        rxMode_ = RxMode::NONE;
        radio_.idle();
    }
    log("EMC stopped");
    return error;
}

void Bench::pollEmc(uint32_t now) {
    if (busy()) return;
    if (static_cast<int32_t>(now - emcNextMs_) >= 0) {
        // Dług sprzed restartu albo ramka dłuższa od rezerwacji (brak TxDone): ramka po jego odczekaniu.
        const uint32_t wait = debtRemainingMs();
        if (wait) emcNextMs_ = now + wait;
        else {
            emcNextMs_ = now + emcPeriodMs_;
            emcSend(now);
        }
    }
    if (rxMode_ == RxMode::NONE && now - autoRxMs_ >= 1000) {
        autoRxMs_ = now;  // najwyżej raz na sekundę, gdy układ nie wchodzi w odbiór
        enterRx(RxMode::TEST, emcLen_);
    }
}

void Bench::emcSend(uint32_t now) {
    if (silence) { ++emcSilenced_; return; }  // cisza blokuje każde nadanie, odbiór trwa
    if (!p1Ready) { ++emcSkipped_; return; }  // bez profilu układ nadawałby na wartościach domyślnych
    const uint32_t txMs = radio_.frameAirMs(emcLen_);
    const uint32_t debtMs = txMs * radiolink::P1_DEBT_FACTOR;
    // Dług ciszy w dzienniku przed ramką, jak w TXPKT; błąd zapisu blokuje nadanie.
    if (!journal_ || !journal_->ok() || !journal_->writeDebt(debtMs, uptimeS())) {
        ++emcSkipped_;
        log("EMC frame skipped: debt journal");
        return;
    }
    debtUntilMs_ = now + txMs + debtMs;
    debtActive_ = true;
    debtPending_ = true;
    uint8_t frame[testframe::MAX_LENGTH];
    testframe::build(frame, emcLen_, emcSeq_);
    rxMode_ = RxMode::NONE;
    const bool ok = radio_.transmit(frame, emcLen_, false, nullptr);
    debtUntilMs_ = millis() + debtMs;  // dług od końca ramki
    ++emcSent_;
    if (!ok) ++emcFailed_;
    const uint16_t seq = emcSeq_++;
    enterRx(RxMode::TEST, emcLen_);
    diagLine("{\"emc\":\"tx\",\"seq\":%u,\"ok\":%s,\"sent\":%lu,\"rx_ok\":%lu,\"rx_bad\":%lu,\"tx_wait_ms\":%lu}\n", seq,
             boolName(ok), static_cast<unsigned long>(emcSent_), static_cast<unsigned long>(counters_.rxOk),
             static_cast<unsigned long>(counters_.rxBad), static_cast<unsigned long>(debtRemainingMs()));
}

void Bench::printEmc() {
    // Wiersz w dwóch częściach poniżej 256 znaków (Print::printf rdzenia nRF52).
    Serial.printf("{\"emc\":%s,\"period_s\":%lu,\"len\":%u,\"min_period_s\":%lu,\"resumed\":%s,\"journal\":%s,",
                  boolName(emcActive_), static_cast<unsigned long>(emcPeriodMs_ / 1000), emcLen_,
                  static_cast<unsigned long>(emcActive_ ? emcMinPeriodS(emcLen_) : 0), boolName(emcResumed_),
                  boolName(journal_ && journal_->ok() && journal_->emc()));
    const Counters& c = counters_;
    Serial.printf("\"sent\":%lu,\"failed\":%lu,\"silenced\":%lu,\"skipped\":%lu,\"rx_ok\":%lu,\"rx_bad\":%lu,\"missing\":%lu,"
                  "\"seconds\":%lu,\"tx_wait_ms\":%lu}\n",
                  static_cast<unsigned long>(emcSent_), static_cast<unsigned long>(emcFailed_),
                  static_cast<unsigned long>(emcSilenced_), static_cast<unsigned long>(emcSkipped_),
                  static_cast<unsigned long>(c.rxOk), static_cast<unsigned long>(c.rxBad), static_cast<unsigned long>(c.missing),
                  static_cast<unsigned long>(emcActive_ ? (millis() - emcStartedMs_) / 1000 : 0),
                  static_cast<unsigned long>(debtRemainingMs()));
}

// --- łącze stosu ------------------------------------------------------------------

void Bench::receiveLink() {
    if (radio_.framing() == radiolink::Framing::RNODE) receiveLora();
    else receiveP1();
}

void Bench::datagramLine(const char* head, int headLength, const uint8_t* data, size_t length) {
    // Datagram do 600 B to wiersz do około 1 300 B, a bufor CDC ma 256 B: dane wychodzą tylko w wierszu,
    // który zmieści się cały; inaczej wiersz bez danych z "data_omitted".
    static const char DATA[] = ",\"data\":\"", END[] = "\"}\n";
    if (headLength > 0 && static_cast<size_t>(headLength) < DIAG_LINE &&
        diagFits(static_cast<size_t>(headLength) + strlen(DATA) + 2 * length + strlen(END))) {
        Serial.write(reinterpret_cast<const uint8_t*>(head), static_cast<size_t>(headLength));
        Serial.print(DATA);
        for (size_t i = 0; i < length; ++i) Serial.printf("%02X", data[i]);
        Serial.print(END);
    } else {
        diagLine("%s,\"data_omitted\":true}\n", head);
    }
    if (datagramHandler_) datagramHandler_(data, length, datagramContext_);
}

void Bench::receiveP1() {
#ifndef WICI_NO_P1_LINK
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
            diagLine("{\"p1rx\":\"rejected\",\"reason\":\"%s\",\"len\":%u,\"rssi_dbm\":%d}\n", p1frame::parseName(parse), frame[0],
                     rssiDbm);
            continue;
        }
        ++link_.rxOk;
        const p1frame::Outcome outcome = assembler_.push(fragment, millis());
        if (outcome == p1frame::Outcome::COMPLETE) {
            ++link_.rxDatagrams;
            char id[2 * p1frame::ID_BYTES + 1];
            hexInto(id, assembler_.completedId(), p1frame::ID_BYTES);
            char head[DIAG_LINE];
            const int n = snprintf(head, sizeof(head), "{\"p1rx\":\"datagram\",\"id\":\"%s\",\"len\":%u,\"fragments\":%u,\"rssi_dbm\":%d",
                                   id, static_cast<unsigned>(assembler_.completedLength()), fragment.count, rssiDbm);
            datagramLine(head, n, assembler_.completed(), assembler_.completedLength());
        } else {
            diagLine("{\"p1rx\":\"%s\",\"index\":%u,\"count\":%u,\"total\":%u,\"rssi_dbm\":%d}\n", p1frame::outcomeName(outcome),
                     fragment.index, fragment.count, fragment.total, rssiDbm);
        }
    }
#endif
}

void Bench::receiveLora() {
    // Ramki RNode z odbioru (L0: z pierścienia zadania odbioru) do składania; limit 1 s z czasów odbioru ramek.
    // Blokada radia tylko na odczyt ramki: wiersz datagramu i przekazanie do stosu idą bez niej.
    radiolink::Frame received;
    for (;;) {
        radiolink::RxPoll result;
        {
            platform::RadioLock lock(RADIO_LOCK_WAIT_MS);
            if (!lock.held()) return;
            result = radio_.pollRx(received);
        }
        if (result == radiolink::RxPoll::Overflow || result == radiolink::RxPoll::Bad) {
            ++link_.rxBad;  // CRC, nagłówek albo ramka odczytana za późno (rx_late); układ zostaje w odbiorze
            return;
        }
        if (result != radiolink::RxPoll::Frame) {
            // Pierścień pusty: dopiero teraz limit od czasu pętli (druga część, która czeka w pierścieniu,
            // zdąży po długim obiegu); sama pierwsza część nadal przepada po 1 s.
            if (result == radiolink::RxPoll::Nothing) loraAssembler_.expire(millis());
            return;
        }
        ++link_.rxOk;
        if (loraAssembler_.push(received.bytes, received.length, received.receivedMs) != loraframe::Outcome::COMPLETE) continue;
        ++link_.rxDatagrams;
        char head[DIAG_LINE];
        const int n = snprintf(head, sizeof(head), "{\"lorarx\":\"datagram\",\"len\":%u,\"frames\":%u,\"rssi_dbm\":%d",
                               static_cast<unsigned>(loraAssembler_.length()),
                               static_cast<unsigned>(loraframe::frameCount(loraAssembler_.length())), received.rssiDbm);
        datagramLine(head, n, loraAssembler_.datagram(), loraAssembler_.length());
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
    // P1TX z portu diagnostycznego i stos na układzie P1; nie liczy się jako tx_drop: datagram nie wszedł do łącza.
    return radio_.p1Link() ? linkSend(data, length, stack) : NO_P1_LINK;
}

const char* Bench::linkSend(const uint8_t* data, size_t length, bool stack) {
    const radiolink::Framing framing = radio_.framing();
    if (framing == radiolink::Framing::NONE) return NO_LINK;
    if (emcActive_) return EMC_ON_ERROR;
    if (framing == radiolink::Framing::P1 && (length < 1 || length > p1frame::MAX_DATAGRAM)) return "datagram 1..600 B";
    if (framing == radiolink::Framing::RNODE && loraframe::frameCount(length) == 0) return "datagram 1..508 B";
    if (!stack && !prep) return "preparation mode off: PREP 1";   // P1TX z portu diagnostycznego: tylko w przygotowaniu
    if (busy()) return "busy: STOP first";
    if (!p1Ready) return "radio not configured: CONFIG";
    if (silence && !(stack && silenceException)) { ++link_.txDrop; return "radio silence"; }
    if (!journal_ || !journal_->ok()) { ++link_.txDrop; return "debt journal unavailable: no FRAM"; }
    memcpy(txData_, data, length);
    txLength_ = length;
    txStack_ = stack;
    // Identyfikator P1 albo nagłówek RNode z generatora stacji, jeden na datagram.
    if (framing == radiolink::Framing::P1) randomBytes(txId_, p1frame::ID_BYTES);
    else randomBytes(&txRandom_, 1);
    txDeferrals_ = 0;
    txRequestedMs_ = millis();
    if (rxMode_ != RxMode::LINK && !enterRx(RxMode::LINK, 0)) return "radio did not enter RX";
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
    if (radio_.framing() == radiolink::Framing::RNODE) {
        // Okno 50 ms ze znaczników próbek odbioru (preambuła, nagłówek, ramka, RSSI ponad progiem), które
        // zbiera odbiór niezależnie od pętli, i RSSI w chwili decyzji.
        switch (radio_.recentActivity(CCA_MS)) {
            case radiolink::Activity::Rx: ++link_.rxBusy; return true;
            case radiolink::Activity::Rssi: ++link_.rssiBusy; return true;
            case radiolink::Activity::None: break;
        }
        const radiolink::Rssi r = radio_.rssi();
        if (r.valid && r.dbm > radio_.ccaThresholdDbm()) { ++link_.rssiBusy; return true; }
        return false;
    }
    // P1: trwa odbiór po słowie synchronizacji, ramka przyszła w czasie okna CCA albo RSSI ponad progiem CCA.
    if (radio_.receivingFrame()) return true;
    receiveP1();  // ramka, która zaczęła się i skończyła między próbkami, czeka w kolejce
    if (link_.rxOk + link_.rxBad != ccaFrames_) return true;
    const radiolink::Rssi r = radio_.rssi();
    return r.valid && r.dbm > radio_.ccaThresholdDbm();
}

void Bench::defer(uint32_t now) {
    if (++txDeferrals_ > MAX_DEFERRALS) { ++link_.txDrop; finishLinkTx("too many deferrals"); return; }
    ++link_.deferrals;
    backoffUntilMs_ = now + backoffMs();
    txState_ = TxState::BACKOFF;
}

void Bench::pollLinkTx() {
    const uint32_t now = millis();
    if (silence && !(txStack_ && silenceException)) { ++link_.txDrop; finishLinkTx("silence"); return; }
    switch (txState_) {
        case TxState::WAIT_DEBT:
            if (debtRemainingMs() == 0) startCca(now, true);
            return;
        case TxState::BACKOFF:
            if (static_cast<int32_t>(now - backoffUntilMs_) >= 0) startCca(now, false);
            return;
        case TxState::CCA: {
            if (radio_.framing() == radiolink::Framing::RNODE) { sendLora(now); return; }
            if (now == ccaCheckMs_) return;
            // Okno 50 ms musi być obserwowane: po długiej przerwie między próbkami (pętla zajęta
            // kryptografią stosu) zaczyna się od nowa.
            const bool gap = now - ccaCheckMs_ > CCA_GAP_MS;
            ccaCheckMs_ = now;
            if (channelBusy()) { defer(now); return; }
            if (gap) { startCca(now, false); return; }
            if (now - ccaStartMs_ < CCA_MS) return;
            txState_ = TxState::SEND;  // nadanie w tym samym obiegu, bez przerwy po ostatniej próbce
        }
            [[fallthrough]];
        case TxState::SEND: {
            if (now - ccaFirstMs_ > LONG_DEFERRAL_MS) ++link_.longDeferrals;
            const uint8_t count = p1frame::fragmentCount(txLength_);
            const uint32_t txMs = count * radio_.frameAirMs(p1frame::MAX_LEN + 1);  // rezerwacja: najdłuższe ramki
            if (!journal_->writeDebt(txMs * radiolink::P1_DEBT_FACTOR, uptimeS())) { ++link_.txDrop; finishLinkTx("debt journal write failed"); return; }
            debtPending_ = true;
            const bool ok = sendFragments();
            debtUntilMs_ = millis() + txMs * radiolink::P1_DEBT_FACTOR;  // dług od końca nadawania
            debtActive_ = true;
            finishLinkTx(ok ? "sent" : "tx error");
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
    enterRx(RxMode::LINK, 0);  // odbiór wyłączony tylko na czas własnego nadawania
    return ok;
}

void Bench::sendLora(uint32_t now) {
    // Okno nie krótsze niż odbiór: znaczniki sprzed startu odbioru nie mówią nic o kanale.
    if (rxMode_ != RxMode::LINK) {
        if (!enterRx(RxMode::LINK, 0)) { ++link_.txDrop; finishLinkTx("radio did not enter RX"); }
        return;
    }
    if (now - rxSinceMs_ < CCA_MS) return;
    // Od decyzji do powrotu do odbioru pętla trzyma blokadę operacji radia (do około 0,9 s), więc zadanie
    // odbioru pomija wtedy swoje obiegi.
    platform::RadioLock lock(RADIO_LOCK_WAIT_MS);
    // Bez blokady kanał nie był sprawdzony: bez odroczenia, CCA powtarza się w następnym obiegu.
    if (!lock.held()) return;
    now = millis();  // czekanie na blokadę trwa do RADIO_LOCK_WAIT_MS
    if (channelBusy()) { defer(now); return; }
    // Ramki z nagłówkiem datagramu; połówka liczy się jako użyta dopiero, gdy ramka 1 wyszła w eter.
    loraframe::Splitter next = splitter_;
    loraframe::Frame frames[2];
    const size_t count = next.split(txData_, txLength_, txRandom_, frames);
    const radiolink::TxPrep prep = radio_.prepareTx(frames[0].bytes, frames[0].length);
    if (prep == radiolink::TxPrep::RxPending) {  // nieodczytana albo odbierana ramka: układ zostaje w odbiorze
        ++link_.rxBusy;
        defer(now);
        return;
    }
    rxMode_ = RxMode::NONE;  // układ wyszedł z odbioru
    if (prep != radiolink::TxPrep::Ready) { ++link_.txDrop; finishLinkTx("tx error"); return; }
    const radiolink::Cad cad = radio_.cad();
    if (cad == radiolink::Cad::Busy) {
        ++link_.cadBusy;
        enterRx(RxMode::LINK, 0);
        defer(now);
        return;
    }
    if (cad != radiolink::Cad::Free) { ++link_.txDrop; finishLinkTx("tx error"); return; }
    // Dług po wolnym CAD, przed pierwszą ramką; błąd zapisu: bez nadania, odbiór wraca (finishLinkTx).
    const uint32_t txMs = loraframe::reservedTxMs(txLength_);
    if (!journal_->writeDebt(txMs * radiolink::P1_DEBT_FACTOR, uptimeS())) { ++link_.txDrop; finishLinkTx("debt journal write failed"); return; }
    debtPending_ = true;
    if (now - ccaFirstMs_ > LONG_DEFERRAL_MS) ++link_.longDeferrals;
    bool ok = radio_.sendPrepared(nullptr);
    ++link_.txFragments;
    splitter_ = next;
    // Ramka 2 zaraz po ramce 1, bez sprawdzania kanału (jak RNode); ramka 1 bez TxDone kończy datagram.
    if (ok && count == 2) {
        ok = radio_.transmit(frames[1].bytes, frames[1].length, true, nullptr);
        ++link_.txFragments;
    }
    ++link_.txDatagrams;
    debtUntilMs_ = millis() + txMs * radiolink::P1_DEBT_FACTOR;  // dług od końca nadawania
    debtActive_ = true;
    enterRx(RxMode::LINK, 0);
    finishLinkTx(ok ? "sent" : "tx error");
}

void Bench::dropLinkTx() {
    if (txState_ != TxState::WAIT_DEBT && txState_ != TxState::CCA && txState_ != TxState::BACKOFF) return;
    ++link_.txDrop;
    finishLinkTx("silence");
}

void Bench::finishLinkTx(const char* result) {
    txState_ = TxState::IDLE;
    if (radio_.framing() == radiolink::Framing::RNODE) {
        diagLine("{\"loratx\":\"%s\",\"len\":%u,\"frames\":%u,\"deferrals\":%u,\"wait_ms\":%lu,\"tx_wait_ms\":%lu}\n", result,
                 static_cast<unsigned>(txLength_), static_cast<unsigned>(loraframe::frameCount(txLength_)), txDeferrals_,
                 static_cast<unsigned long>(millis() - txRequestedMs_), static_cast<unsigned long>(debtRemainingMs()));
    } else {
        char id[2 * p1frame::ID_BYTES + 1];
        hexInto(id, txId_, p1frame::ID_BYTES);
        diagLine("{\"p1tx\":\"%s\",\"id\":\"%s\",\"len\":%u,\"fragments\":%u,\"deferrals\":%u,\"wait_ms\":%lu,\"tx_wait_ms\":%lu}\n", result, id,
                 static_cast<unsigned>(txLength_), p1frame::fragmentCount(txLength_), txDeferrals_,
                 static_cast<unsigned long>(millis() - txRequestedMs_), static_cast<unsigned long>(debtRemainingMs()));
    }
    if (rxMode_ != RxMode::LINK) enterRx(RxMode::LINK, 0);
    if (txDoneHandler_) txDoneHandler_(!strcmp(result, "sent"), txDoneContext_);
}

const char* Bench::txStateName() const {
    return txState_ == TxState::IDLE ? "idle" : txState_ == TxState::WAIT_DEBT ? "wait_debt" : txState_ == TxState::CCA ? "cca"
           : txState_ == TxState::BACKOFF ? "backoff" : "send";
}

void Bench::printLink() {
    // Dwie części poniżej 256 znaków: Print::printf rdzenia Adafruit nRF52 formatuje do bufora 256 B.
    Serial.printf("{\"%s\":{\"rx\":%s,\"tx\":\"%s\",\"rx_ok\":%lu,\"rx_bad\":%lu,\"rx_datagrams\":%lu,\"tx_datagrams\":%lu,"
                  "\"tx_fragments\":%lu,\"tx_drop\":%lu,\"deferrals\":%lu,\"long_deferrals\":%lu,",
                  radio_.framing() == radiolink::Framing::RNODE ? "lora" : "p1", boolName(rxMode_ == RxMode::LINK), txStateName(),
                  static_cast<unsigned long>(link_.rxOk), static_cast<unsigned long>(link_.rxBad),
                  static_cast<unsigned long>(link_.rxDatagrams), static_cast<unsigned long>(link_.txDatagrams),
                  static_cast<unsigned long>(link_.txFragments), static_cast<unsigned long>(link_.txDrop),
                  static_cast<unsigned long>(link_.deferrals), static_cast<unsigned long>(link_.longDeferrals));
    if (radio_.framing() == radiolink::Framing::RNODE) {
        const loraframe::Stats& a = loraAssembler_.stats();
        Serial.printf("\"cad_busy\":%lu,\"rssi_busy\":%lu,\"rx_busy\":%lu,\"split_lost\":%lu,\"header_only\":%lu,\"assembly_timeout\":%lu,"
                      "\"rx_late\":%lu,\"rx_ring_overflow\":%lu,\"cca_threshold_dbm\":%d,\"tx_wait_ms\":%lu}}\n",
                      static_cast<unsigned long>(link_.cadBusy), static_cast<unsigned long>(link_.rssiBusy),
                      static_cast<unsigned long>(link_.rxBusy), static_cast<unsigned long>(a.split_lost),
                      static_cast<unsigned long>(a.header_only), static_cast<unsigned long>(a.assembly_timeout),
                      static_cast<unsigned long>(radio_.rxLate()), static_cast<unsigned long>(radio_.rxRingOverflow()),
                      radio_.ccaThresholdDbm(), static_cast<unsigned long>(debtRemainingMs()));
        return;
    }
#ifndef WICI_NO_P1_LINK
    const p1frame::Stats& s = assembler_.stats();
    Serial.printf("\"attempts\":%u,\"stored\":%lu,\"duplicates\":%lu,\"conflicts\":%lu,\"late\":%lu,\"evicted\":%lu,\"expired\":%lu,"
                  "\"cca_threshold_dbm\":%d,\"tx_wait_ms\":%lu}}\n",
                  static_cast<unsigned>(assembler_.active()), static_cast<unsigned long>(s.stored),
                  static_cast<unsigned long>(s.duplicates), static_cast<unsigned long>(s.conflicts),
                  static_cast<unsigned long>(s.late), static_cast<unsigned long>(s.evicted),
                  static_cast<unsigned long>(s.expired), radio_.ccaThresholdDbm(), static_cast<unsigned long>(debtRemainingMs()));
#else
    Serial.printf("\"cca_threshold_dbm\":%d,\"tx_wait_ms\":%lu}}\n", radio_.ccaThresholdDbm(), static_cast<unsigned long>(debtRemainingMs()));
#endif
}

}  // namespace measure
