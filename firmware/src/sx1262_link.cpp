// SPDX-License-Identifier: MIT
#include "sx1262_link.h"

#include <math.h>

namespace sx1262 {

namespace {

constexpr uint32_t TX_MARGIN_MS = 100;       // ponad czas ramki do TxDone
constexpr int32_t OFFSET_MAX_HZ = 1000000;   // jak FOFF na układach P1
// Najdłuższa ramka w powietrzu z zapasem: tyle najwyżej trwa „odbiór w toku” po preambule.
constexpr uint32_t FRAME_MAX_MS = lora::frameAirMs(lora::MAX_PAYLOAD) + 10;
constexpr uint16_t IRQ_MASK = IRQ_TX_DONE | IRQ_RX_DONE | IRQ_PREAMBLE_DETECTED | IRQ_HEADER_VALID | IRQ_HEADER_ERR | IRQ_CRC_ERR | IRQ_TIMEOUT;
constexpr uint16_t IRQ_RX_END = IRQ_RX_DONE | IRQ_HEADER_ERR | IRQ_CRC_ERR | IRQ_PREAMBLE_DETECTED | IRQ_HEADER_VALID;

constexpr uint8_t STANDBY_RC = 0x00;
constexpr uint8_t REGULATOR_DC_DC = 0x01;
constexpr uint8_t CALIBRATE_ALL = 0x7F;
constexpr uint8_t IMAGE_863_870[2] = {0xD7, 0xDB};  // tabela 9-2
constexpr uint8_t FALLBACK_STDBY_RC = 0x20;
constexpr uint8_t TCXO_1V8 = 0x02;                  // tabela 13-35
constexpr uint8_t BW_125_KHZ = 0x04;                // tabela 13-48
constexpr uint8_t CR_4_5 = 0x01;
constexpr uint8_t RAMP_200_US = 0x04;
// PA jak w programie diagnostycznym L0 (RadioLib 7.6.0, SX1262::setOutputPower z optymalizacją,
// paOptTable dla 13 dBm): paDutyCycle 0x01, hpMax 0x04, SX1262, paLut 1 i wartość 19 w SetTxParams
// (nie moc w dBm: 13 dBm daje tabela). Limit prądu 60 mA jak SX126x::begin, przywrócony po SetPaConfig.
// Wybór ostateczny po pomiarze mocy na złączu (TXCW CONDUCTED).
constexpr uint8_t PA_CONFIG[4] = {0x01, 0x04, 0x00, 0x01};
constexpr uint8_t TX_PARAMS_POWER = 19;  // dla lora::TX_POWER_DBM = 13
static_assert(lora::TX_POWER_DBM == 13, "PA_CONFIG i TX_PARAMS_POWER z paOptTable RadioLib dla 13 dBm");
constexpr uint8_t OCP_60_MA = 0x18;  // krok 2,5 mA; SetPaConfig ustawia 140 mA (0x38), więc zapis po nim

static_assert(lora::SPREADING_FACTOR == 7 && lora::BANDWIDTH_HZ == 125000 && lora::CODING_RATE == 5, "kody SetModulationParams");
static_assert(lora::SERIES_MAX_MS <= radiolink::P1_SERIES_MAX_MS, "dług serii LoRa w granicy measure::MAX_DEBT_MS");

constexpr uint32_t BASE_RF_WORD =
    static_cast<uint32_t>(((static_cast<uint64_t>(lora::CARRIER_HZ) << 25) + F_XTAL_HZ / 2) / F_XTAL_HZ);
static_assert(BASE_RF_WORD == 911763046u, "869,525 MHz: f x 2^25 / 32 MHz");

// Rejestry sprawdzane przy weryfikacji: wartość i maska porównania.
struct Check {
    uint16_t address;
    uint8_t value;
    uint8_t mask;
    const char* name;
};
constexpr Check CHECKS[] = {
    {REG_SYNC_WORD, lora::SYNC_WORD_MSB, 0xFF, "SYNC_WORD_MSB"},
    {REG_SYNC_WORD + 1, lora::SYNC_WORD_LSB, 0xFF, "SYNC_WORD_LSB"},
    {REG_RX_GAIN, RX_GAIN_BOOSTED, 0xFF, "RX_GAIN"},
    {REG_RETENTION_COUNT, 0x01, 0xFF, "RETENTION_COUNT"},
    {REG_RETENTION_LIST, static_cast<uint8_t>(REG_RX_GAIN >> 8), 0xFF, "RETENTION_0_MSB"},
    {REG_RETENTION_LIST + 1, static_cast<uint8_t>(REG_RX_GAIN), 0xFF, "RETENTION_0_LSB"},
    {REG_OCP, OCP_60_MA, 0xFF, "OCP"},
    {REG_IQ_POLARITY, 0x04, 0x04, "IQ_POLARITY"},
    {REG_TX_MODULATION, 0x04, 0x04, "TX_MODULATION"},
    {REG_TX_CLAMP, 0x1E, 0x1E, "TX_CLAMP"},
};

void setBits(Radio& radio, uint16_t address, uint8_t bits) { radio.writeReg(address, static_cast<uint8_t>(radio.readReg(address) | bits)); }

}  // namespace

void LinkDriver::begin() {
    pinMode(pinRxen_, OUTPUT);
    rxen(false);
}

void LinkDriver::rxen(bool on) {
    digitalWrite(pinRxen_, on ? HIGH : LOW);
    rxen_ = on;
}

void LinkDriver::toStandby() {
    rxen(false);  // RXEN niski w TX i spoczynku (polaczenia-MCU-L0.csv)
    radio_.command(OP_SET_STANDBY, &STANDBY_RC, 1);
    rxActive_ = false;
    inFrame_ = false;
}

void LinkDriver::setPacketParams(uint8_t payloadLength) {
    const uint8_t params[6] = {static_cast<uint8_t>(lora::PREAMBLE_SYMBOLS >> 8), static_cast<uint8_t>(lora::PREAMBLE_SYMBOLS),
                               static_cast<uint8_t>(lora::EXPLICIT_HEADER ? 0x00 : 0x01), payloadLength,
                               static_cast<uint8_t>(lora::CRC_ON ? 0x01 : 0x00), 0x00 /* zwykła polaryzacja IQ */};
    radio_.command(OP_SET_PACKET_PARAMS, params, sizeof(params));
}

uint32_t LinkDriver::rfWord() const { return static_cast<uint32_t>(static_cast<int64_t>(BASE_RF_WORD) + offsetSteps_); }

void LinkDriver::writeFrequency() {
    const uint32_t word = rfWord();
    const uint8_t params[4] = {static_cast<uint8_t>(word >> 24), static_cast<uint8_t>(word >> 16), static_cast<uint8_t>(word >> 8),
                               static_cast<uint8_t>(word)};
    radio_.command(OP_SET_RF_FREQUENCY, params, 4);
}

VerifyResult LinkDriver::configure() {
    toStandby();
    // TCXO przed kalibracją: kalibracja po włączeniu zasilania bez TCXO kończy się błędem XOSC_START
    // (karta, rozdz. 13.3.6), więc błędy kasowane i kalibracja wszystkich bloków od nowa.
    const uint32_t start = lora::TCXO_DELAY_US * 64 / 1000;  // jednostka 15,625 µs
    static_assert(lora::TCXO_MILLIVOLTS == 1800, "kod napięcia TCXO");
    const uint8_t tcxo[4] = {TCXO_1V8, static_cast<uint8_t>(start >> 16), static_cast<uint8_t>(start >> 8), static_cast<uint8_t>(start)};
    radio_.command(OP_SET_DIO3_TCXO, tcxo, 4);
    const uint8_t noErrors[2] = {0, 0};
    radio_.command(OP_CLEAR_DEVICE_ERRORS, noErrors, 2);
    radio_.command(OP_CALIBRATE, &CALIBRATE_ALL, 1);
    radio_.command(OP_SET_REGULATOR_MODE, &REGULATOR_DC_DC, 1);
    const uint8_t on = 0x01;
    radio_.command(OP_SET_DIO2_RF_SWITCH, &on, 1);
    radio_.command(OP_SET_PACKET_TYPE, &PACKET_TYPE_LORA, 1);
    radio_.command(OP_SET_RX_TX_FALLBACK, &FALLBACK_STDBY_RC, 1);
    radio_.command(OP_CALIBRATE_IMAGE, IMAGE_863_870, 2);
    writeFrequency();
    radio_.command(OP_SET_PA_CONFIG, PA_CONFIG, 4);
    radio_.writeReg(REG_OCP, OCP_60_MA);
    const uint8_t txParams[2] = {TX_PARAMS_POWER, RAMP_200_US};
    radio_.command(OP_SET_TX_PARAMS, txParams, 2);
    setBits(radio_, REG_TX_CLAMP, 0x1E);  // rozdz. 15.2 (RadioLib: fixPaClamping)
    const uint8_t modulation[4] = {lora::SPREADING_FACTOR, BW_125_KHZ, CR_4_5, static_cast<uint8_t>(lora::LOW_DATA_RATE_OPTIMIZE)};
    radio_.command(OP_SET_MODULATION_PARAMS, modulation, 4);
    setBits(radio_, REG_TX_MODULATION, 0x04);  // rozdz. 15.1: pasmo inne niż 500 kHz
    setPacketParams(lora::MAX_PAYLOAD);
    setBits(radio_, REG_IQ_POLARITY, 0x04);    // rozdz. 15.4: zwykła polaryzacja IQ
    const uint8_t sync[2] = {lora::SYNC_WORD_MSB, lora::SYNC_WORD_LSB};
    radio_.writeRegs(REG_SYNC_WORD, sync, 2);
    const uint8_t base[2] = {0x00, 0x00};
    radio_.command(OP_SET_BUFFER_BASE, base, 2);
    const uint8_t irq[8] = {static_cast<uint8_t>(IRQ_MASK >> 8), static_cast<uint8_t>(IRQ_MASK),
                            static_cast<uint8_t>((IRQ_TX_DONE | IRQ_RX_DONE | IRQ_TIMEOUT) >> 8),
                            static_cast<uint8_t>(IRQ_TX_DONE | IRQ_RX_DONE | IRQ_TIMEOUT), 0, 0, 0, 0};
    radio_.command(OP_SET_DIO_IRQ_PARAMS, irq, 8);
    // Rx Boosted i jego miejsce na liście rejestrów zachowywanych w uśpieniu (RadioLib: setRxBoostedGainMode(true)).
    radio_.writeReg(REG_RX_GAIN, RX_GAIN_BOOSTED);
    const uint8_t retention[3] = {0x01, static_cast<uint8_t>(REG_RX_GAIN >> 8), static_cast<uint8_t>(REG_RX_GAIN)};
    radio_.writeRegs(REG_RETENTION_COUNT, retention, 3);
    radio_.clearIrq(IRQ_ALL);
    return verify();
}

uint8_t LinkDriver::packetType() {
    uint8_t type = 0xFF;
    radio_.read(OP_GET_PACKET_TYPE, &type, 1);
    return type;
}

VerifyResult LinkDriver::verify() {
    VerifyResult result;
    auto compare = [&result](uint16_t address, uint16_t expected, uint16_t actual, const char* name) {
        ++result.checked;
        if (expected == actual) return;
        if (result.mismatches++ == 0) {
            result.firstAddress = address;
            result.expected = expected;
            result.actual = actual;
            result.firstName = name;
        }
    };
    compare(0, PACKET_TYPE_LORA, packetType(), "PACKET_TYPE");
    for (const Check& c : CHECKS) compare(c.address, c.value & c.mask, radio_.readReg(c.address) & c.mask, c.name);
    compare(0, 0, radio_.deviceErrors(), "DEVICE_ERRORS");
    return result;
}

bool LinkDriver::profileLost() { return packetType() != PACKET_TYPE_LORA || radio_.readReg(REG_RX_GAIN) != RX_GAIN_BOOSTED; }

bool LinkDriver::sleepAndWake(uint8_t& rxGainAfter) {
    toStandby();
    radio_.sleepWarm();
    const bool woke = radio_.wake();
    rxGainAfter = radio_.readReg(REG_RX_GAIN);
    radio_.command(OP_SET_STANDBY, &STANDBY_RC, 1);
    return woke;
}

void LinkDriver::idle() {
    toStandby();
    collectIrq(radio_.irqStatus());
    radio_.clearIrq(IRQ_ALL);
}

bool LinkDriver::startCw() {
    idle();
    radio_.command(OP_SET_TX_CW);  // DIO2 przełącza tor na nadawanie
    return radio_.status().mode() == MODE_TX;
}

void LinkDriver::stopCw() { toStandby(); }

bool LinkDriver::transmit(const uint8_t* frame, size_t length, bool, radiolink::TxTiming* timing) {
    // Jawny nagłówek niesie długość, więc ramka P1 (variable) i wzorcowa idą tak samo: `length` bajtów treści.
    if (length == 0 || length > lora::MAX_PAYLOAD) return false;
    toStandby();  // TX ze stanu spoczynku; odbiór wyłączony na czas własnego nadawania
    setPacketParams(static_cast<uint8_t>(length));
    radio_.writeBuffer(0x00, frame, length);
    radio_.clearIrq(IRQ_ALL);
    const uint32_t t0 = micros();
    const uint8_t noTimeout[3] = {0, 0, 0};  // limit czasu pilnuje program
    radio_.command(OP_SET_TX, noTimeout, 3);
    const uint32_t start = millis();
    const uint32_t limitMs = lora::frameAirMs(length) + TX_MARGIN_MS;
    bool sent = false;
    while (millis() - start < limitMs) {
        const uint16_t irq = radio_.irqStatus();
        collectIrq(irq);
        if (irq & IRQ_TX_DONE) {
            sent = true;
            break;
        }
        if (irq & IRQ_TIMEOUT) break;
        delayMicroseconds(200);
    }
    radio_.clearIrq(IRQ_TX_DONE | IRQ_TIMEOUT);
    // Po TxDone układ wraca sam do STDBY_RC (tryb powrotu); inaczej przerwanie nadawania.
    if (!sent || radio_.status().mode() != MODE_STBY_RC) toStandby();
    if (timing) {
        timing->valid = false;  // bez wyjścia „pakiet w powietrzu”: tylko czas całkowity
        timing->totalUs = micros() - t0;
        timing->leadUs = timing->onAirUs = timing->tailUs = 0;
    }
    return sent;
}

bool LinkDriver::startRx(bool variable, uint8_t fixedLength) {
    toStandby();
    setPacketParams(lora::MAX_PAYLOAD);  // przy jawnym nagłówku długość odbioru podaje nagłówek ramki
    radio_.clearIrq(IRQ_ALL);
    rxVariable_ = variable;
    rxFixedLength_ = fixedLength;
    rxen(true);
    const uint8_t continuous[3] = {0xFF, 0xFF, 0xFF};
    radio_.command(OP_SET_RX, continuous, 3);
    rxActive_ = radio_.status().mode() == MODE_RX;
    if (!rxActive_) rxen(false);
    return rxActive_;
}

radiolink::RxPoll LinkDriver::pollRx(radiolink::Frame& out) {
    const uint16_t irq = radio_.irqStatus();
    collectIrq(irq);
    if (!(irq & (IRQ_RX_DONE | IRQ_HEADER_ERR))) {
        // Odbiór ciągły nie kończy się sam; inny stan oznacza przerwanie z zewnątrz (np. polecenie z portu).
        if (rxActive_ && radio_.status().mode() != MODE_RX) startRx(rxVariable_, rxFixedLength_);
        return radiolink::RxPoll::Nothing;
    }
    radio_.clearIrq(IRQ_RX_END);
    inFrame_ = false;
    if (irq & (IRQ_HEADER_ERR | IRQ_CRC_ERR)) return radiolink::RxPoll::Bad;  // układ zostaje w odbiorze
    uint8_t buffer[2] = {};
    radio_.read(OP_GET_RX_BUFFER_STATUS, buffer, 2);
    const size_t length = buffer[0];
    if (length == 0 || (!rxVariable_ && length != rxFixedLength_)) return radiolink::RxPoll::Bad;
    radio_.readBuffer(buffer[1], out.bytes, length);
    out.length = length;
    uint8_t packet[3] = {};
    radio_.read(OP_GET_PACKET_STATUS, packet, 3);
    out.rssiDbm = static_cast<int16_t>(-packet[0] / 2);  // RssiPkt: -RssiPkt/2 dBm
    out.snrQdb = static_cast<int8_t>(packet[1]);       // SnrPkt: ze znakiem, /4 dB
    out.quality = 0;
    return radiolink::RxPoll::Frame;
}

bool LinkDriver::receivingFrame() {
    const uint16_t irq = radio_.irqStatus();
    collectIrq(irq);
    if (irq & (IRQ_RX_DONE | IRQ_HEADER_ERR | IRQ_CRC_ERR)) {  // ramka skończona: odbierze ją pollRx
        inFrame_ = false;
        return false;
    }
    if ((irq & (IRQ_PREAMBLE_DETECTED | IRQ_HEADER_VALID)) && !inFrame_) {
        inFrame_ = true;
        inFrameSinceMs_ = millis();
    }
    if (inFrame_ && millis() - inFrameSinceMs_ > FRAME_MAX_MS) {
        // Preambuła bez ramki (szum albo ramka obca): po czasie najdłuższej ramki kanał znów wolny.
        radio_.clearIrq(IRQ_PREAMBLE_DETECTED | IRQ_HEADER_VALID);
        inFrame_ = false;
    }
    return inFrame_;
}

radiolink::Rssi LinkDriver::rssi() {
    radiolink::Rssi out;
    uint8_t raw = 0;
    if (!radio_.read(OP_GET_RSSI_INST, &raw, 1) || radio_.lastStatus().mode() != MODE_RX) return out;
    out.valid = true;
    out.dbm = static_cast<int16_t>(-raw / 2);
    return out;
}

double LinkDriver::frequencyStepHz() const { return static_cast<double>(F_XTAL_HZ) / 33554432.0; }  // f_xtal / 2^25

bool LinkDriver::setFrequencyOffset(int32_t hz) {
    if (hz > OFFSET_MAX_HZ || hz < -OFFSET_MAX_HZ) return false;
    offsetSteps_ = static_cast<int32_t>(lround(hz / frequencyStepHz()));
    reapplyFrequencyOffset();
    return true;
}

void LinkDriver::reapplyFrequencyOffset() {
    const bool wasRx = rxActive_;
    toStandby();  // SetRfFrequency w stanie spoczynku
    writeFrequency();
    if (wasRx) startRx(rxVariable_, rxFixedLength_);
}

int32_t LinkDriver::frequencyOffsetHz() { return static_cast<int32_t>(lround(offsetSteps_ * frequencyStepHz())); }

}  // namespace sx1262
