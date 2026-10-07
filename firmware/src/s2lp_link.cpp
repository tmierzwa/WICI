// SPDX-License-Identifier: MIT
#include "s2lp_link.h"

#include <math.h>
#include <string.h>

#include "p1frame.h"
#include "s2lp_p1_registers.h"

namespace s2lp {

namespace {

constexpr uint32_t STATE_TIMEOUT_US = 2000;   // READY <-> LOCK <-> RX/TX: do około 100 us (tabela 50)
constexpr uint32_t FRAME_MAX_MS = 300;        // najdłuższa ramka P1 w powietrzu (około 200 ms) z zapasem
constexpr int32_t OFFSET_MAX_HZ = 1000000;    // jak FOFF na CC1120
constexpr size_t FIFO_BYTES = 128;

uint8_t tableValue(const char* name) {
    for (size_t i = 0; i < p1s2::REGISTER_COUNT; ++i) {
        if (!strcmp(p1s2::REGISTERS[i].name, name)) return p1s2::REGISTERS[i].value;
    }
    return 0;
}

uint32_t baseSynth() {
    return (static_cast<uint32_t>(tableValue("SYNT3") & 0x0F) << 24) | (static_cast<uint32_t>(tableValue("SYNT2")) << 16) |
           (static_cast<uint32_t>(tableValue("SYNT1")) << 8) | tableValue("SYNT0");
}

}  // namespace

void LinkDriver::collectIrq() {
    const uint32_t irq = radio_.readIrqStatus();
    irqPending_ |= irq;
    irqSeen_ |= irq;
    if (irq & (IRQ_RX_DATA_READY | IRQ_RX_DATA_DISC | IRQ_RX_FIFO_ERROR)) inFrame_ = false;
    else if (irq & IRQ_VALID_SYNC) {
        inFrame_ = true;
        inFrameSinceMs_ = millis();
    }
}

void LinkDriver::toReady() {
    const uint8_t state = radio_.status().state();
    if (state == STATE_RX || state == STATE_TX) radio_.commandAndWait(CMD_SABORT, STATE_READY, STATE_TIMEOUT_US);
    else if (state != STATE_READY) radio_.commandAndWait(CMD_READY, STATE_READY, STATE_TIMEOUT_US);
    rxActive_ = false;
    inFrame_ = false;
}

void LinkDriver::idle() {
    toReady();
    radio_.command(CMD_FLUSHRXFIFO);
    radio_.command(CMD_FLUSHTXFIFO);
    collectIrq();
    irqPending_ = 0;
}

bool LinkDriver::startCw() {
    idle();
    radio_.writeReg(MOD2, static_cast<uint8_t>((MOD_TYPE_CW << 4) | (tableValue("MOD2") & 0x0F)));
    radio_.writeReg(PCKTCTRL1, static_cast<uint8_t>((tableValue("PCKTCTRL1") & ~0x0C) | TXSOURCE_PN9));
    return radio_.commandAndWait(CMD_TX, STATE_TX, STATE_TIMEOUT_US);
}

void LinkDriver::stopCw() {
    toReady();
    radio_.writeReg(MOD2, tableValue("MOD2"));
    radio_.writeReg(PCKTCTRL1, tableValue("PCKTCTRL1"));
    radio_.command(CMD_FLUSHTXFIFO);
}

void LinkDriver::setLength(bool variable, uint16_t length) {
    radio_.writeReg(PCKTCTRL2, static_cast<uint8_t>((tableValue("PCKTCTRL2") & ~0x01) | (variable ? 0x01 : 0x00)));
    const uint8_t bytes[2] = {static_cast<uint8_t>(length >> 8), static_cast<uint8_t>(length)};
    radio_.writeRegs(PCKTLEN1, bytes, 2);
}

bool LinkDriver::transmit(const uint8_t* frame, size_t length, bool variable, radiolink::TxTiming* timing) {
    // Zmienna długość: pole LEN wysyła układ z PCKTLEN, więc do kolejki idą BODY i CRC.
    const uint8_t* payload = variable ? frame + 1 : frame;
    const size_t payloadLength = variable ? length - 1 : length;
    if (length == 0 || payloadLength > FIFO_BYTES) return false;
    toReady();  // TX tylko ze stanu READY; odbiór wyłączony na czas własnego nadawania
    setLength(variable, static_cast<uint16_t>(payloadLength));
    radio_.command(CMD_FLUSHTXFIFO);
    radio_.writeFifo(payload, payloadLength);
    collectIrq();
    irqPending_ &= ~(IRQ_TX_DATA_SENT | IRQ_TX_FIFO_ERROR);
    const uint32_t frameMs = static_cast<uint32_t>(12 + length) * 8 * 1000 / p1s2::SYMBOL_RATE;
    const uint32_t t0 = micros();
    radio_.command(CMD_TX);
    const uint32_t start = millis();
    bool sent = false;
    while (millis() - start < frameMs + 120) {
        collectIrq();
        if (irqPending_ & IRQ_TX_FIFO_ERROR) break;
        if (irqPending_ & IRQ_TX_DATA_SENT) {
            sent = true;
            break;
        }
        delayMicroseconds(200);
    }
    irqPending_ &= ~(IRQ_TX_DATA_SENT | IRQ_TX_FIFO_ERROR);
    // Po nadaniu układ wraca sam do READY; inaczej przerwanie i opróżnienie kolejki.
    const bool ready = radio_.waitState(STATE_READY, STATE_TIMEOUT_US);
    if (!sent || !ready) {
        toReady();
        radio_.command(CMD_FLUSHTXFIFO);
    }
    if (timing) {
        timing->valid = false;  // bez wyjścia „pakiet w powietrzu” dla TX: tylko czas całkowity
        timing->totalUs = micros() - t0;
        timing->leadUs = timing->onAirUs = timing->tailUs = 0;
    }
    return sent && ready;
}

bool LinkDriver::startRx(bool variable, uint8_t fixedLength) {
    toReady();
    radio_.command(CMD_FLUSHRXFIFO);
    setLength(variable, variable ? p1frame::MAX_LEN : fixedLength);
    rxVariable_ = variable;
    rxFixedLength_ = fixedLength;
    collectIrq();
    irqPending_ = 0;
    rxActive_ = radio_.commandAndWait(CMD_RX, STATE_RX, STATE_TIMEOUT_US);
    return rxActive_;
}

radiolink::RxPoll LinkDriver::restartRx(radiolink::RxPoll result) {
    toReady();
    radio_.command(CMD_FLUSHRXFIFO);
    irqPending_ &= ~(IRQ_RX_DATA_READY | IRQ_RX_DATA_DISC | IRQ_RX_FIFO_ERROR | IRQ_VALID_SYNC);
    rxActive_ = radio_.commandAndWait(CMD_RX, STATE_RX, STATE_TIMEOUT_US);
    return result;
}

radiolink::RxPoll LinkDriver::pollRx(radiolink::Frame& out) {
    collectIrq();
    if (irqPending_ & IRQ_RX_FIFO_ERROR) return restartRx(radiolink::RxPoll::Overflow);
    if (irqPending_ & IRQ_RX_DATA_DISC) return restartRx(radiolink::RxPoll::Bad);
    if (!(irqPending_ & IRQ_RX_DATA_READY)) {
        // Z PERS_RX układ sam z RX nie wychodzi; READY oznacza przerwanie z zewnątrz (np. polecenie z portu).
        if (radio_.status().state() == STATE_READY) rxActive_ = radio_.commandAndWait(CMD_RX, STATE_RX, STATE_TIMEOUT_US);
        return radiolink::RxPoll::Nothing;
    }
    irqPending_ &= ~IRQ_RX_DATA_READY;
    uint8_t lengthBytes[2] = {};
    radio_.readRegs(RX_PCKT_LEN1, lengthBytes, 2);
    const size_t length = (static_cast<size_t>(lengthBytes[0]) << 8) | lengthBytes[1];
    const size_t available = radio_.readReg(RX_FIFO_STATUS);
    // Kolejka ma trzymać dokładnie tę ramkę. Z PERS_RX następny pakiet pisze do tej samej kolejki,
    // a RX_PCKT_LEN opisuje tylko ostatni; nadmiar (pętla stała dłużej niż przerwa między ramkami)
    // przesunąłby kolejne odczyty, więc wtedy ramka odpada, a odbiór startuje od pustej kolejki.
    const size_t expected = rxVariable_ ? length : rxFixedLength_;
    if (available != expected) return restartRx(radiolink::RxPoll::Bad);
    if (rxVariable_) {
        if (length < p1frame::MIN_LEN || length > p1frame::MAX_LEN) return restartRx(radiolink::RxPoll::Bad);
        out.bytes[0] = static_cast<uint8_t>(length);
        radio_.readFifo(out.bytes + 1, length);
        out.length = length + 1;
    } else {
        radio_.readFifo(out.bytes, rxFixedLength_);
        out.length = rxFixedLength_;
    }
    out.rssiDbm = static_cast<int16_t>(radio_.readReg(RSSI_LEVEL)) + RSSI_OFFSET_DB;
    out.quality = radio_.readReg(LINK_QUALIF1) & 0x7F;
    return radiolink::RxPoll::Frame;
}

bool LinkDriver::receivingFrame() {
    collectIrq();
    if (inFrame_ && millis() - inFrameSinceMs_ > FRAME_MAX_MS) inFrame_ = false;
    return inFrame_;
}

radiolink::Rssi LinkDriver::rssi() {
    radiolink::Rssi out;
    if (radio_.status().state() != STATE_RX) return out;
    out.valid = true;
    out.dbm = static_cast<int16_t>(radio_.readReg(RSSI_LEVEL_RUN)) + RSSI_OFFSET_DB;
    return out;
}

double LinkDriver::frequencyStepHz() const {
    return static_cast<double>(p1s2::F_XO_HZ) / 524288.0 / p1s2::BAND_FACTOR / p1s2::REF_DIVIDER;
}

void LinkDriver::writeSynth(int32_t steps) {
    const uint32_t word = static_cast<uint32_t>(static_cast<int32_t>(baseSynth()) + steps);
    const bool wasRx = rxActive_;
    toReady();  // słowo SYNT działa przy następnym przejściu do LOCK
    const uint8_t bytes[4] = {static_cast<uint8_t>((tableValue("SYNT3") & 0xF0) | ((word >> 24) & 0x0F)),
                              static_cast<uint8_t>(word >> 16), static_cast<uint8_t>(word >> 8), static_cast<uint8_t>(word)};
    radio_.writeRegs(SYNT3, bytes, 4);
    if (wasRx) rxActive_ = radio_.commandAndWait(CMD_RX, STATE_RX, STATE_TIMEOUT_US);
}

bool LinkDriver::setFrequencyOffset(int32_t hz) {
    if (hz > OFFSET_MAX_HZ || hz < -OFFSET_MAX_HZ) return false;
    offsetSteps_ = static_cast<int32_t>(lround(hz / frequencyStepHz()));
    offsetSet_ = true;
    writeSynth(offsetSteps_);
    return true;
}

void LinkDriver::reapplyFrequencyOffset() {
    if (offsetSet_) writeSynth(offsetSteps_);
}

int32_t LinkDriver::frequencyOffsetRaw() {
    uint8_t bytes[4] = {};
    radio_.readRegs(SYNT3, bytes, 4);
    const uint32_t word = (static_cast<uint32_t>(bytes[0] & 0x0F) << 24) | (static_cast<uint32_t>(bytes[1]) << 16) |
                          (static_cast<uint32_t>(bytes[2]) << 8) | bytes[3];
    return static_cast<int32_t>(word) - static_cast<int32_t>(baseSynth());
}

int32_t LinkDriver::frequencyOffsetHz() { return static_cast<int32_t>(lround(frequencyOffsetRaw() * frequencyStepHz())); }

}  // namespace s2lp
