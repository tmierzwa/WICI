// SPDX-License-Identifier: MIT
#include "cc1120_link.h"

#include "p1_registers.h"
#include "p1frame.h"

namespace cc1120 {

namespace {

// Wartość P1 rejestru z tablicy; rejestry przywracane po nośnej muszą w niej być.
constexpr size_t tableIndex(uint16_t address) {
    size_t i = 0;
    while (i < p1::REGISTER_COUNT && p1::REGISTERS[i].address != address) ++i;
    return i;
}
constexpr bool inTable(uint16_t address) { return tableIndex(address) < p1::REGISTER_COUNT; }
static_assert(inTable(DEVIATION_M) && inTable(MODCFG_DEV_E) && inTable(PKT_CFG2) && inTable(PKT_CFG0), "rejestry nośnej w tablicy P1");
constexpr uint8_t tableValue(uint16_t address) { return p1::REGISTERS[tableIndex(address)].value; }

void restore(Radio& radio, uint16_t address) { radio.writeReg(address, tableValue(address)); }

}  // namespace

void LinkDriver::idle() {
    rxActive_ = false;
    rxPendingLen_ = 0;
    radio_.idle();
    radio_.strobe(SFRX);  // kolejki opróżnione, jak obiecuje radiolink::Driver::idle
    radio_.strobe(SFTX);
}

bool LinkDriver::startCw() {
    idle();
    radio_.strobe(SFTX);
    // Nośna bez modulacji: 2-FSK z dewiacją 0, dane losowe PN9, pakiet nieskończony.
    radio_.writeReg(DEVIATION_M, 0x00);
    radio_.writeReg(MODCFG_DEV_E, 0x00);
    radio_.writeReg(PKT_CFG2, static_cast<uint8_t>((tableValue(PKT_CFG2) & ~0x03) | PKT_FORMAT_RANDOM));
    radio_.writeReg(PKT_CFG0, LENGTH_CONFIG_INFINITE);
    const uint8_t seed = 0x00;
    radio_.writeFifo(&seed, 1);  // TXLAST != TXFIRST wymagane w trybie losowym
    radio_.strobe(STX);
    return radio_.waitMarcState(MARC_STATE_TX, 50);
}

void LinkDriver::stopCw() {
    radio_.idle();
    radio_.strobe(SFTX);
    restore(radio_, DEVIATION_M);
    restore(radio_, MODCFG_DEV_E);
    restore(radio_, PKT_CFG2);
    restore(radio_, PKT_CFG0);
}

void LinkDriver::setLength(bool variable, uint8_t fixedLength) {
    // Ramki wzorcowe: stała długość z PKT_LEN; ramki P1: zmienna długość z bajtem LEN do 102 (F79).
    // Zapis przy każdej ramce: CONFIG i RESET zmieniają te rejestry poza sterownikiem łącza.
    radio_.writeReg(PKT_CFG0, variable ? 0x20 : 0x00);
    radio_.writeReg(PKT_LEN, variable ? p1frame::MAX_LEN : fixedLength);
    fixedLength_ = fixedLength;
}

bool LinkDriver::waitSync(bool level, uint32_t timeoutUs) {
    const uint32_t start = micros();
    while (micros() - start < timeoutUs) {
        if ((digitalRead(pinSync_) == HIGH) == level) return true;
    }
    return false;
}

bool LinkDriver::transmit(const uint8_t* frame, size_t length, bool variable, radiolink::TxTiming* timing) {
    if (length == 0 || length > radiolink::MAX_FRAME) return false;
    if (rxActive_) idle();  // odbiór wyłączony tylko na czas własnego nadawania
    setLength(variable, static_cast<uint8_t>(length));
    radio_.strobe(SFTX);
    radio_.writeFifo(frame, length);
    const uint32_t t0 = micros();
    radio_.strobe(STX);
    // Ramka w powietrzu: preambuła 8 B, słowo 4 B, treść; zapas jak w poleceniach pomiarowych.
    const uint32_t onAirUs = static_cast<uint32_t>(length) * 8 * 1000000UL / p1::SYMBOL_RATE;
    if (!timing) {
        const uint32_t frameMs = static_cast<uint32_t>(12 + length) * 8 * 1000 / p1::SYMBOL_RATE;
        if (radio_.waitMarcState(MARC_STATE_IDLE, frameMs + 120)) return true;
        radio_.idle();
        radio_.strobe(SFTX);
        return false;
    }
    // GPIO2 = PKT_SYNC_RXTX: wysoki od wysłania słowa synchronizacji do końca pakietu.
    const bool rose = waitSync(true, 80000);
    const uint32_t tSync = micros();
    bool fell = false;
    if (rose) fell = waitSync(false, onAirUs + 50000);
    const uint32_t tEnd = micros();
    const bool idleReached = radio_.waitMarcState(MARC_STATE_IDLE, rose ? 30 : (onAirUs / 1000) + 120);
    const uint32_t tIdle = micros();
    if (!idleReached) {  // także TX_FIFO_ERR: nadajnik nie może zostać włączony po powrocie
        radio_.idle();
        radio_.strobe(SFTX);
    }
    timing->valid = rose && fell;
    timing->totalUs = tIdle - t0;
    timing->leadUs = rose ? tSync - t0 : 0;
    timing->onAirUs = fell ? tEnd - tSync : 0;
    timing->tailUs = fell ? tIdle - tEnd : 0;
    return idleReached;
}

bool LinkDriver::startRx(bool variable, uint8_t fixedLength) {
    if (!variable && (fixedLength == 0 || fixedLength > radiolink::MAX_FRAME)) return false;
    radio_.idle();
    radio_.strobe(SFRX);
    setLength(variable, fixedLength);
    rxVariable_ = variable;
    rxPendingLen_ = 0;
    radio_.strobe(SRX);
    rxActive_ = radio_.waitMarcState(MARC_STATE_RX, 50);
    return rxActive_;
}

radiolink::RxPoll LinkDriver::restartRx(radiolink::RxPoll result) {
    rxPendingLen_ = 0;
    radio_.idle();
    radio_.strobe(SFRX);
    radio_.strobe(SRX);
    return result;
}

radiolink::RxPoll LinkDriver::pollRx(radiolink::Frame& out) {
    const uint8_t marc = radio_.readMarcState();
    if (marc == MARC_STATE_RX_FIFO_ERR) return restartRx(radiolink::RxPoll::Overflow);
    if (marc != MARC_STATE_RX) {
        // Po IDLE z innego polecenia wystarczy SRX; TX_FIFO_ERR wymaga opróżnienia kolejki (stany
        // przejściowe, np. ustalanie syntezera po SRX, przechodzą same).
        if (marc == MARC_STATE_IDLE) radio_.strobe(SRX);
        else if (marc == MARC_STATE_TX_FIFO_ERR) { radio_.strobe(SFTX); restartRx(radiolink::RxPoll::Nothing); }
        return radiolink::RxPoll::Nothing;
    }
    uint8_t bytes = radio_.rxBytes();
    uint8_t buffer[radiolink::MAX_FRAME + 2];
    if (!rxVariable_) {
        const size_t packet = static_cast<size_t>(fixedLength_) + 2;  // ramka + RSSI + LQI
        if (bytes < packet) return radiolink::RxPoll::Nothing;
        radio_.readFifo(buffer, packet);
        memcpy(out.bytes, buffer, fixedLength_);
        out.length = fixedLength_;
        out.rssiDbm = static_cast<int16_t>(static_cast<int8_t>(buffer[fixedLength_])) + p1::RSSI_OFFSET_DB;
        out.quality = buffer[fixedLength_ + 1] & 0x7F;
        return radiolink::RxPoll::Frame;
    }
    if (rxPendingLen_ == 0) {
        if (bytes < 1) return radiolink::RxPoll::Nothing;
        radio_.readFifo(&rxPendingLen_, 1);  // bajt LEN; reszta ramki może być jeszcze w powietrzu
        --bytes;
        rxDeadlineMs_ = millis() + (static_cast<uint32_t>(rxPendingLen_) + 2) * 8 * 1000 / p1::SYMBOL_RATE + 50;
        // Układ odrzuca LEN > PKT_LEN, krótsze trzeba wyrzucić samemu.
        if (rxPendingLen_ < p1frame::MIN_LEN || rxPendingLen_ > p1frame::MAX_LEN) return restartRx(radiolink::RxPoll::Bad);
    }
    const size_t rest = static_cast<size_t>(rxPendingLen_) + 2;  // BODY + CRC + RSSI + LQI
    if (bytes < rest) {
        if (static_cast<int32_t>(millis() - rxDeadlineMs_) > 0) return restartRx(radiolink::RxPoll::Bad);
        return radiolink::RxPoll::Nothing;
    }
    buffer[0] = rxPendingLen_;
    radio_.readFifo(buffer + 1, rest);
    const size_t length = static_cast<size_t>(rxPendingLen_) + 1;
    rxPendingLen_ = 0;
    memcpy(out.bytes, buffer, length);
    out.length = length;
    out.rssiDbm = static_cast<int16_t>(static_cast<int8_t>(buffer[length])) + p1::RSSI_OFFSET_DB;
    out.quality = buffer[length + 1] & 0x7F;
    return radiolink::RxPoll::Frame;
}

bool LinkDriver::receivingFrame() { return digitalRead(pinSync_) == HIGH || rxPendingLen_ != 0; }

radiolink::Rssi LinkDriver::rssi() {
    const Rssi r = radio_.rssi(p1::RSSI_OFFSET_DB);
    radiolink::Rssi out;
    out.valid = r.valid;
    out.dbm = r.dbm;
    return out;
}

double LinkDriver::frequencyStepHz() const { return static_cast<double>(p1::F_XOSC_HZ) / 262144.0 / p1::LO_DIVIDER; }

bool LinkDriver::setFrequencyOffset(int32_t hz) {
    // FREQOFF = hz * LO_DIVIDER * 2^18 / f_xosc (SWRU295E, równanie 27); krok 30,5 Hz.
    const double raw = static_cast<double>(hz) * p1::LO_DIVIDER * 262144.0 / p1::F_XOSC_HZ;
    if (raw > 32767.0 || raw < -32768.0) return false;
    offsetHz_ = hz;
    offsetSet_ = true;
    applyOffset();
    return true;
}

void LinkDriver::reapplyFrequencyOffset() {
    if (offsetSet_) applyOffset();
}

void LinkDriver::applyOffset() {
    const int16_t reg = static_cast<int16_t>(lround(static_cast<double>(offsetHz_) * p1::LO_DIVIDER * 262144.0 / p1::F_XOSC_HZ));
    const bool wasRx = rxActive_;
    radio_.idle();
    radio_.setFrequencyOffset(reg);
    // Ramka przerwana w połowie zostawiłaby bajty w kolejce, a tryb stałej długości nie odzyskuje
    // wyrównania: odbiór od nowa z pustą kolejką.
    if (wasRx) restartRx(radiolink::RxPoll::Nothing);
}

int32_t LinkDriver::frequencyOffsetHz() {
    return static_cast<int32_t>(lround(radio_.frequencyOffset() * frequencyStepHz()));
}

bool LinkDriver::frequencyErrorHz(int32_t& hz) {
    hz = static_cast<int32_t>(radio_.frequencyOffsetEstimate() * frequencyStepHz());
    return true;
}

}  // namespace cc1120
