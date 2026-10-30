// SPDX-License-Identifier: MIT
#include "sx1262_link.h"

#include "platform.h"

#include <math.h>

namespace sx1262 {

namespace {

constexpr uint32_t TX_MARGIN_MS = 100;       // ponad czas ramki do TxDone
constexpr int32_t OFFSET_MAX_HZ = 1000000;   // jak FOFF na układach P1
// Najdłuższa ramka w powietrzu z zapasem: tyle najwyżej trwa „odbiór w toku” po preambule.
constexpr uint32_t FRAME_MAX_MS = lora::frameAirMs(lora::MAX_PAYLOAD) + 10;
// Przerwania zapisywane w rejestrze IRQ (bez bitu w masce układ ich nie zgłasza, rozdz. 13.3.2).
constexpr uint16_t IRQ_MASK = IRQ_TX_DONE | IRQ_RX_DONE | IRQ_PREAMBLE_DETECTED | IRQ_HEADER_VALID | IRQ_HEADER_ERR | IRQ_CRC_ERR |
                              IRQ_CAD_DONE | IRQ_CAD_DETECTED | IRQ_TIMEOUT;
// Koniec ramki w odbiorze i początek ramki (preambuła, nagłówek).
constexpr uint16_t IRQ_RX_END = IRQ_RX_DONE | IRQ_HEADER_ERR | IRQ_CRC_ERR;
// DIO1: tylko koniec odbieranej ramki (plan L4: jeden właściciel każdej flagi); ta sama maska co IRQ_RX_END,
// bo to samo zdarzenie widzi pin i próbka odbioru.
constexpr uint16_t IRQ_DIO1 = IRQ_RX_END;
constexpr uint16_t IRQ_RX_START = IRQ_PREAMBLE_DETECTED | IRQ_HEADER_VALID;
// Nieodczytana ramka albo ramka w toku: wyjście z odbioru nadpisałoby ją w buforze.
constexpr uint16_t IRQ_RX_PENDING = IRQ_RX_DONE | IRQ_PREAMBLE_DETECTED | IRQ_HEADER_VALID;
constexpr uint16_t IRQ_CAD = IRQ_CAD_DONE | IRQ_CAD_DETECTED;

// Kod liczby symboli CAD dla SetCadParams (tabela 13-72: 1, 2, 4, 8, 16 symboli → 0x00–0x04).
constexpr uint8_t cadSymbolCode(uint8_t symbols) {
    return symbols == 1 ? 0x00 : symbols == 2 ? 0x01 : symbols == 4 ? 0x02 : symbols == 8 ? 0x03 : 0x04;
}
static_assert(lora::CAD_SYMBOLS == 1 || lora::CAD_SYMBOLS == 2 || lora::CAD_SYMBOLS == 4 || lora::CAD_SYMBOLS == 8 ||
                  lora::CAD_SYMBOLS == 16,
              "SX1262 wykonuje CAD tylko na 1, 2, 4, 8 albo 16 symbolach");
constexpr uint8_t CAD_ONLY = 0x00;  // tabela 13-73: po CAD powrót do STDBY_RC, bez odbioru
// Najdłuższa przerwa między próbkami odbioru, przy której HeaderValid zastany przy RxDone można jeszcze
// uznać za nagłówek tej samej ramki. Następna ramka zaczyna nadpisywać bufor najwcześniej po około 30 ms
// od końca poprzedniej (preambuła 24,6 ms, słowo synchronizacji i nagłówek; plan, sekcja 3 punkt 4),
// więc 25 ms zostawia zapas; przy dłuższej przerwie nie wiadomo, czyj to nagłówek, i ramka idzie do rx_late.
constexpr uint32_t LATE_GAP_MS = 25;
// CAD 2 symbole to około 2 ms plus przetwarzanie; limit z zapasem, potem błąd (wyjęty moduł, zawieszony układ).
constexpr uint32_t CAD_LIMIT_MS = 20;

constexpr uint8_t REGULATOR_DC_DC = 0x01;
constexpr uint8_t CALIBRATE_ALL = 0x7F;
constexpr uint8_t IMAGE_863_870[2] = {0xD7, 0xDB};  // tabela 9-2
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
static_assert(lora::SERIES_MAX_MS <= radiolink::MAX_SERIES_MS_ANY_LINK, "dług serii LoRa w granicy measure::MAX_DEBT_MS (górnej granicy profili)");

constexpr uint32_t BASE_RF_WORD =
    static_cast<uint32_t>(((static_cast<uint64_t>(lora::CARRIER_HZ) << 25) + F_XTAL_HZ / 2) / F_XTAL_HZ);
static_assert(BASE_RF_WORD == 911763046u, "869,525 MHz: f x 2^25 / 32 MHz");

// Bity rejestrów ustawianych w configure() i sprawdzanych w CHECKS (rozdz. 15 noty układu).
constexpr uint8_t TX_CLAMP_BITS = 0x1E;       // rozdz. 15.2: bity 4:1 przy niedopasowaniu anteny
constexpr uint8_t TX_MODULATION_BIT = 0x04;   // rozdz. 15.1: pasmo inne niż 500 kHz
constexpr uint8_t IQ_POLARITY_BIT = 0x04;     // rozdz. 15.4: zwykła polaryzacja IQ

// RSSI układu: surowa wartość w półdecybelach poniżej 0 dBm (RssiInst, RssiPkt: -raw/2 dBm).
constexpr int16_t rssiDbm(uint8_t raw) { return static_cast<int16_t>(-raw / 2); }

// Wynik próbki odbioru jako rodzaj wpisu dla pętli (Late liczy się jak ramka zła).
radiolink::RxPoll pollKind(RxService result) {
    switch (result) {
        case RxService::Frame: return radiolink::RxPoll::Frame;
        case RxService::Bad:
        case RxService::Late: return radiolink::RxPoll::Bad;
        default: return radiolink::RxPoll::Nothing;
    }
}

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
    {REG_IQ_POLARITY, IQ_POLARITY_BIT, IQ_POLARITY_BIT, "IQ_POLARITY"},
    {REG_TX_MODULATION, TX_MODULATION_BIT, TX_MODULATION_BIT, "TX_MODULATION"},
    {REG_TX_CLAMP, TX_CLAMP_BITS, TX_CLAMP_BITS, "TX_CLAMP"},
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

bool LinkDriver::toStandby() {
    rxen(false);  // RXEN niski w TX i spoczynku (polaczenia-MCU-L0.csv)
    rxActive_ = false;
    inFrame_ = false;
    return radio_.command(OP_SET_STANDBY, &STDBY_XOSC, 1);
}

void LinkDriver::toStandbyRc() {
    rxen(false);
    rxActive_ = false;
    inFrame_ = false;
    radio_.command(OP_SET_STANDBY, &STDBY_RC, 1);
}

bool LinkDriver::setPacketParams(uint8_t payloadLength) {
    const uint8_t params[6] = {static_cast<uint8_t>(lora::PREAMBLE_SYMBOLS >> 8), static_cast<uint8_t>(lora::PREAMBLE_SYMBOLS),
                               static_cast<uint8_t>(lora::EXPLICIT_HEADER ? 0x00 : 0x01), payloadLength,
                               static_cast<uint8_t>(lora::CRC_ON ? 0x01 : 0x00), 0x00 /* zwykła polaryzacja IQ */};
    return radio_.command(OP_SET_PACKET_PARAMS, params, sizeof(params));
}

uint32_t LinkDriver::rfWord() const { return static_cast<uint32_t>(static_cast<int64_t>(BASE_RF_WORD) + offsetSteps_); }

void LinkDriver::writeFrequency() {
    const uint32_t word = rfWord();
    const uint8_t params[4] = {static_cast<uint8_t>(word >> 24), static_cast<uint8_t>(word >> 16), static_cast<uint8_t>(word >> 8),
                               static_cast<uint8_t>(word)};
    radio_.command(OP_SET_RF_FREQUENCY, params, 4);
}

VerifyResult LinkDriver::configure() {
    toStandbyRc();  // Calibrate, SetRegulatorMode i SetPacketType tylko w STDBY_RC (rozdz. 13.1.12, 9.4, 13.4.2)
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
    radio_.command(OP_SET_RX_TX_FALLBACK, &FALLBACK_STDBY_XOSC, 1);  // TCXO pracuje między ramkami
    radio_.command(OP_CALIBRATE_IMAGE, IMAGE_863_870, 2);
    writeFrequency();
    radio_.command(OP_SET_PA_CONFIG, PA_CONFIG, 4);
    radio_.writeReg(REG_OCP, OCP_60_MA);
    const uint8_t txParams[2] = {TX_PARAMS_POWER, RAMP_200_US};
    radio_.command(OP_SET_TX_PARAMS, txParams, 2);
    setBits(radio_, REG_TX_CLAMP, TX_CLAMP_BITS);  // rozdz. 15.2 (RadioLib: fixPaClamping)
    const uint8_t modulation[4] = {lora::SPREADING_FACTOR, BW_125_KHZ, CR_4_5, static_cast<uint8_t>(lora::LOW_DATA_RATE_OPTIMIZE)};
    radio_.command(OP_SET_MODULATION_PARAMS, modulation, 4);
    setBits(radio_, REG_TX_MODULATION, TX_MODULATION_BIT);  // rozdz. 15.1
    setPacketParams(lora::MAX_PAYLOAD);
    setBits(radio_, REG_IQ_POLARITY, IQ_POLARITY_BIT);  // rozdz. 15.4
    const uint8_t sync[2] = {lora::SYNC_WORD_MSB, lora::SYNC_WORD_LSB};
    radio_.writeRegs(REG_SYNC_WORD, sync, 2);
    const uint8_t base[2] = {0x00, 0x00};
    radio_.command(OP_SET_BUFFER_BASE, base, 2);
    const uint8_t irq[8] = {static_cast<uint8_t>(IRQ_MASK >> 8), static_cast<uint8_t>(IRQ_MASK), static_cast<uint8_t>(IRQ_DIO1 >> 8),
                            static_cast<uint8_t>(IRQ_DIO1), 0, 0, 0, 0};
    radio_.command(OP_SET_DIO_IRQ_PARAMS, irq, 8);
    // Parametry CAD zostają w układzie do resetu; cadTimeout tylko dla CAD_RX.
    const uint8_t cadParams[7] = {cadSymbolCode(lora::CAD_SYMBOLS), lora::CAD_DET_PEAK, lora::CAD_DET_MIN, CAD_ONLY, 0, 0, 0};
    radio_.command(OP_SET_CAD_PARAMS, cadParams, 7);
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
    toStandbyRc();  // SetSleep z zachowaniem konfiguracji ze STDBY_RC (rozdz. 13.1.1)
    radio_.sleepWarm();
    const bool woke = radio_.wake();
    rxGainAfter = radio_.readReg(REG_RX_GAIN);
    radio_.command(OP_SET_STANDBY, &STDBY_RC, 1);
    return woke;
}

void LinkDriver::idle() {
    toStandbyRc();
    collectIrq(radio_.irqStatus());
    radio_.clearIrq(IRQ_ALL);
}

bool LinkDriver::startCw() {
    idle();
    radio_.command(OP_SET_TX_CW);  // DIO2 przełącza tor na nadawanie
    return radio_.status().mode() == MODE_TX;
}

void LinkDriver::stopCw() { toStandby(); }

bool LinkDriver::load(const uint8_t* frame, size_t length) {
    // Ze stanu spoczynku: długość w parametrach pakietu, ramka w buforze od adresu 0 (SetBufferBaseAddress 0, 0).
    // Zapis nadpisuje ramki odebrane wcześniej, więc prepareTx sprawdza najpierw, że żadna nie czeka.
    txLength_ = length;
    return setPacketParams(static_cast<uint8_t>(length)) && radio_.writeBuffer(0x00, frame, length);
}

radiolink::TxPrep LinkDriver::prepareTx(const uint8_t* frame, size_t length) {
    if (length == 0 || length > lora::MAX_PAYLOAD) return radiolink::TxPrep::Error;
    if (rxActive_) {
        // Sprawdzenie bez kasowania: nieodczytaną ramkę albo ramkę w toku odbierze próbka odbioru
        // (serviceRx) po odroczeniu; ładowanie ramki do bufora by ją nadpisało.
        uint16_t irq = 0;
        if (!radio_.readIrq(irq)) return radiolink::TxPrep::Error;
        collectIrq(irq);
        if (irq & IRQ_RX_PENDING) return radiolink::TxPrep::RxPending;
        // Ramka w toku, której flagi skasowała już próbka odbioru: wyjście z odbioru by ją przerwało.
        if (frameInProgress(millis())) return radiolink::TxPrep::RxPending;
    }
    if (!toStandby() || !load(frame, length)) return radiolink::TxPrep::Error;
    return radiolink::TxPrep::Ready;
}

radiolink::Cad LinkDriver::cad() {
    // Tylko ze stanu spoczynku (po prepareTx): SetCad nie działa z odbioru. Po CAD_ONLY układ jest
    // w STDBY_RC (tabela 13-73), a ramka i parametry pakietu zostają (bufor trwa poza uśpieniem, rozdz. 7.4).
    if (rxActive_) return radiolink::Cad::Error;
    // RXEN wysoki w CAD: przełącznik antenowy w odbiorze (jak w SetRx); wraca niski przed SetTx.
    rxen(true);
    if (radio_.clearIrq(IRQ_CAD) && radio_.command(OP_SET_CAD)) {
        const uint32_t start = millis();
        uint16_t irq = 0;
        while (radio_.readIrq(irq)) {
            collectIrq(irq);
            if (irq & IRQ_CAD_DONE) {
                // CadDetected z tego samego odczytu co CadDone: oba ustawia koniec jednego CAD (rozdz. 13.1.8).
                rxen(false);
                if (!radio_.clearIrq(IRQ_CAD)) break;
                return (irq & IRQ_CAD_DETECTED) ? radiolink::Cad::Busy : radiolink::Cad::Free;
            }
            if (millis() - start >= CAD_LIMIT_MS) break;
            delayMicroseconds(200);
        }
    }
    toStandby();  // także RXEN niski
    return radiolink::Cad::Error;
}

bool LinkDriver::sendPrepared(radiolink::TxTiming* timing) {
    // Ramka załadowana (prepareTx albo transmit); układ w STDBY_XOSC albo w STDBY_RC po CAD (wtedy SetTx
    // czeka jeszcze na start TCXO, rozdz. 13.3.6).
    const uint32_t t0 = micros();
    bool sent = false;
    const uint8_t noTimeout[3] = {0, 0, 0};  // limit czasu pilnuje program
    if (radio_.clearIrq(IRQ_TX_DONE | IRQ_TIMEOUT) && radio_.command(OP_SET_TX, noTimeout, 3)) {
        const uint32_t start = millis();
        const uint32_t limitMs = lora::frameAirMs(txLength_) + TX_MARGIN_MS;
        uint16_t irq = 0;
        while (millis() - start < limitMs && radio_.readIrq(irq)) {
            collectIrq(irq);
            if (irq & IRQ_TX_DONE) {
                sent = true;
                break;
            }
            if (irq & IRQ_TIMEOUT) break;
            delayMicroseconds(200);
        }
        radio_.clearIrq(IRQ_TX_DONE | IRQ_TIMEOUT);
    }
    // Po TxDone układ wraca sam do STDBY_XOSC (tryb powrotu); inaczej przerwanie nadawania.
    if (!sent || radio_.status().mode() != MODE_STBY_XOSC) toStandby();
    if (timing) {
        timing->valid = false;  // bez wyjścia „pakiet w powietrzu”: tylko czas całkowity
        timing->totalUs = micros() - t0;
        timing->leadUs = timing->onAirUs = timing->tailUs = 0;
    }
    return sent;
}

bool LinkDriver::transmit(const uint8_t* frame, size_t length, bool, radiolink::TxTiming* timing) {
    // Jawny nagłówek niesie długość, więc ramka P1 (variable) i wzorcowa idą tak samo: `length` bajtów treści.
    // Nadawanie pomiarowe (TXPKT, EMC) wychodzi z odbioru bez sprawdzania: odbiór wyłączony na czas własnego nadawania.
    if (length == 0 || length > lora::MAX_PAYLOAD) return false;
    if (!toStandby() || !load(frame, length) || !radio_.clearIrq(IRQ_ALL)) {
        if (timing) *timing = radiolink::TxTiming{};
        toStandby();
        return false;
    }
    return sendPrepared(timing);
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
    headerSeen_ = false;     // flagi skasowane: start odbioru liczy się jak próbka
    lastSampleMs_ = millis();
    return rxActive_;
}

bool LinkDriver::frameInProgress(uint32_t now) const {
    // Różnica ze znakiem: czas zapisany przez zadanie po odczycie millis() przez wołającego daje wynik ujemny,
    // czyli ramka w toku.
    return inFrame_ && static_cast<int32_t>(now - inFrameSinceMs_) < static_cast<int32_t>(FRAME_MAX_MS);
}

void LinkDriver::noteActivity(uint16_t irq, uint32_t now) {
    // Preambuła bez ramki (jak w receivingFrame): po czasie najdłuższej ramki stan nieaktualny, więc następny
    // początek ramki liczy się od nowa (inaczej ochrona ramki w toku w recentActivity już by nie działała).
    if (inFrame_ && !frameInProgress(now)) inFrame_ = false;
    if (irq & IRQ_PREAMBLE_DETECTED) activity_.mark(Activity::PREAMBLE, now);
    if (irq & IRQ_HEADER_VALID) activity_.mark(Activity::HEADER, now);
    if (irq & IRQ_RX_END) {
        activity_.mark(Activity::FRAME, now);  // także ramka z błędem CRC albo nagłówka
        inFrame_ = false;
    }
    // Początek ramki po końcu poprzedniej w tej samej próbce to już następna ramka.
    if ((irq & IRQ_RX_START) && !inFrame_) {
        inFrameSinceMs_ = now;
        inFrame_ = true;
    }
}

bool LinkDriver::readRssi(radiolink::Rssi& out) {
    out = radiolink::Rssi{};
    uint8_t raw = 0;
    if (!radio_.read(OP_GET_RSSI_INST, &raw, 1)) return false;
    if (radio_.lastStatus().mode() != MODE_RX) return true;  // RSSI ważne tylko w odbiorze
    out.valid = true;
    out.dbm = rssiDbm(raw);
    return true;
}

RxService LinkDriver::serviceRx(radiolink::Frame& out, bool sampleRssi) {
    out.length = 0;
    if (!rxActive_) return RxService::NotRx;
    const uint32_t now = millis();
    const uint32_t gapMs = now - lastSampleMs_;  // od poprzedniej udanej próbki
    uint16_t irq = 0;
    if (!radio_.readIrq(irq)) return RxService::BusyTimeout;
    const uint8_t mode = radio_.lastStatus().mode();
    collectIrq(irq);

    if (!(irq & IRQ_RX_END)) {
        // Bez końca ramki: znaczniki aktywności i skasowanie widzianych flag początku ramki, żeby przy
        // RxDone HeaderValid znaczył nagłówek następnej ramki.
        noteActivity(irq, now);
        const uint16_t start = irq & IRQ_RX_START;
        if (start && !radio_.clearIrq(start)) return RxService::BusyTimeout;
        if (irq & IRQ_HEADER_VALID) headerSeen_ = true;  // nagłówek bieżącej ramki już widziany
        if (sampleRssi) {
            radiolink::Rssi r;
            if (!readRssi(r)) return RxService::BusyTimeout;
            if (r.valid && r.dbm > ccaThresholdDbm()) activity_.mark(Activity::RSSI, now);
        }
        lastSampleMs_ = now;
        // Odbiór ciągły nie kończy się sam; inny tryb oznacza przerwanie z zewnątrz (np. polecenie z portu)
        // albo reset układu.
        if (mode != MODE_RX) startRx(rxVariable_, rxFixedLength_);
        return RxService::Nothing;
    }

    // Koniec ramki. Każda próbka kasuje flagi początku ramki (plan, sekcja 4, „Wykrycie spóźnienia”).
    // HeaderValid zastany przy RxDone jest nagłówkiem następnej ramki, która pisze już do bufora za tą
    // (odbiór ciągły, rozdz. 7.2) i po zawinięciu ją nadpisuje, gdy:
    // - nagłówek bieżącej ramki widziała już wcześniejsza próbka (headerSeen_), albo
    // - od poprzedniej próbki minęło ponad LATE_GAP_MS: nie wiadomo, czyj to nagłówek.
    // Inaczej to nagłówek tej samej, krótkiej ramki (nagłówek i koniec między dwiema próbkami): ramka dobra.
    // Przy HeaderErr bez RxDone ramka nie miała ważnego nagłówka, więc HeaderValid jest następnej ramki.
    uint16_t seen = irq & (IRQ_RX_END | IRQ_RX_START);
    const bool nextHeader =
        (irq & IRQ_HEADER_VALID) && (!(irq & IRQ_RX_DONE) || headerSeen_ || gapMs > LATE_GAP_MS);
    // Ramka z błędem CRC albo nagłówka to rx_bad, nie rx_late, także z nagłówkiem następnej ramki.
    bool late = !(irq & (IRQ_HEADER_ERR | IRQ_CRC_ERR)) && (irq & IRQ_RX_DONE) && nextHeader;
    bool headerAfter = false;  // nagłówek następnej ramki w trakcie odczytu
    RxService result = RxService::Frame;
    if (irq & (IRQ_HEADER_ERR | IRQ_CRC_ERR)) {
        result = RxService::Bad;  // układ zostaje w odbiorze
    } else if (!late) {
        // Własny nagłówek (i preambuła) tej ramki kasowane przed odczytem, żeby HeaderValid po odczycie
        // znaczył tylko nagłówek następnej ramki.
        const uint16_t ownStart = seen & IRQ_RX_START;
        if (ownStart) {
            if (!radio_.clearIrq(ownStart)) return RxService::BusyTimeout;
            noteActivity(ownStart, now);
            seen &= static_cast<uint16_t>(~ownStart);
        }
        uint8_t buffer[2] = {};
        if (!radio_.read(OP_GET_RX_BUFFER_STATUS, buffer, 2)) return RxService::BusyTimeout;
        const size_t length = buffer[0];
        const uint8_t first = buffer[1];
        if (length == 0 || (!rxVariable_ && length != rxFixedLength_)) {
            result = RxService::Bad;
        } else {
            // Ramka może przechodzić przez koniec bufora (pierścień 256 B): odczyt w dwóch częściach, bez
            // polegania na zawijaniu adresu w ReadBuffer, którego karta nie opisuje (zawijanie podaje tylko
            // dla WriteBuffer, rozdz. 13.2.3 i 13.2.4).
            const size_t head = length < 256u - first ? length : 256u - first;
            if (!radio_.readBuffer(first, out.bytes, head)) return RxService::BusyTimeout;
            if (head < length && !radio_.readBuffer(0x00, out.bytes + head, length - head)) return RxService::BusyTimeout;
            uint8_t packet[3] = {};
            if (!radio_.read(OP_GET_PACKET_STATUS, packet, 3)) return RxService::BusyTimeout;
            // Drugie sprawdzenie po odczycie: nagłówek następnej ramki w trakcie odczytu też ją psuje.
            uint16_t after = 0;
            if (!radio_.readIrq(after)) return RxService::BusyTimeout;
            collectIrq(after);
            headerAfter = after & IRQ_HEADER_VALID;
            late = headerAfter;
            seen |= after & IRQ_RX_START;  // koniec następnej ramki zostaje dla następnej próbki
            if (!late) {
                out.length = length;
                out.receivedMs = now;  // czas próbki, nie obsługi w pętli (limit składania LoRa)
                out.rssiDbm = rssiDbm(packet[0]);  // RssiPkt
                out.snrQdb = static_cast<int8_t>(packet[1]);       // SnrPkt: ze znakiem, /4 dB
                out.quality = 0;
            }
        }
    }
    noteActivity(seen, now);
    // Tylko flagi widziane w tej próbce: te, które układ ustawił po odczycie, zostają.
    if (!radio_.clearIrq(seen)) {
        out.length = 0;
        return RxService::BusyTimeout;
    }
    // Ramka zakończona: dalej liczy się tylko nagłówek następnej ramki, jeśli był w tej próbce.
    headerSeen_ = nextHeader || headerAfter;
    if (headerSeen_) inFrameSinceMs_ = now;  // następna ramka w toku liczy się od tej próbki
    inFrame_ = headerSeen_;
    lastSampleMs_ = now;
    if (late) {
        out.length = 0;
        rxLate_.fetch_add(1, std::memory_order_relaxed);
        return RxService::Late;
    }
    return result;
}

radiolink::RxPoll LinkDriver::pollRx(radiolink::Frame& out) {
    if (background_) {
        // Ramki z pierścienia zadania odbioru (pętla nie czyta flag odbioru układu).
        RxEntry entry;
        if (!ring_.pop(entry)) return radiolink::RxPoll::Nothing;
        out = entry.frame;
        return entry.kind;
    }
    // Bez zadania odbioru próbkuje pętla, więc także RSSI dla okna CCA.
    return pollKind(serviceRx(out, true));
}

void LinkDriver::discardRx() {
    RxEntry entry;
    while (ring_.pop(entry)) {
    }
}

void LinkDriver::taskCycle(bool dio1High) {
    signals_.tick();
    const uint32_t now = millis();
    if (busyBackoffMs_ && now - busyBackoffMs_ < BUSY_BACKOFF_MS) return;
    const bool rssiDue = now - lastRssiMs_ >= RSSI_SAMPLE_MS;
    if (!dio1High && !rssiDue) return;
    platform::RadioLock lock(0);  // bez czekania: pętla nadaje, konfiguruje albo obsługuje polecenie
    if (!lock.held() || !rxActive_) return;
    const uint32_t t0 = micros();
    RxEntry entry;
    const RxService result = serviceRx(entry.frame, rssiDue);
    if (result == RxService::BusyTimeout) {
        busyBackoffMs_ = now ? now : 1;
        return;
    }
    busyBackoffMs_ = 0;
    if (rssiDue) lastRssiMs_ = now;
    entry.kind = pollKind(result);
    if (entry.kind != radiolink::RxPoll::Nothing) ring_.push(entry);  // pełny: odpada ta ramka (overflow)
    signals_.serviced(now, micros() - t0);
}

bool LinkDriver::receivingFrame() {
    uint16_t irq = 0;
    if (!radio_.readIrq(irq)) return false;
    collectIrq(irq);
    if (irq & IRQ_RX_END) {  // ramka skończona: odbierze ją serviceRx (flag nie kasuje)
        inFrame_ = false;
        return false;
    }
    const uint32_t now = millis();
    noteActivity(irq, now);
    const uint16_t start = irq & IRQ_RX_START;
    // Jak próbka odbioru: tylko widziane flagi początku ramki.
    if (!start || radio_.clearIrq(start)) {
        if (irq & IRQ_HEADER_VALID) headerSeen_ = true;
        lastSampleMs_ = now;
    }
    // Preambuła bez ramki (szum albo ramka obca): po czasie najdłuższej ramki kanał znów wolny (noteActivity
    // wyżej wygasiło stan z tym samym `now`).
    return inFrame_;
}

radiolink::Rssi LinkDriver::rssi() {
    radiolink::Rssi out;
    readRssi(out);
    return out;
}

radiolink::Activity LinkDriver::recentActivity(uint32_t windowMs) {
    const uint32_t now = millis();
    if (!activity_.quietFor(now, windowMs, Activity::RX_KINDS)) return radiolink::Activity::Rx;
    // Ramka w toku (nagłówek bez końca) nadal zajmuje kanał, choć znaczniki zestarzały się przed jej końcem
    // (ramka do FRAME_MAX_MS); stan ustawia zadanie odbioru, tu odczyt bez blokady.
    if (frameInProgress(now)) return radiolink::Activity::Rx;
    if (!activity_.quietFor(now, windowMs, 1u << Activity::RSSI)) return radiolink::Activity::Rssi;
    return radiolink::Activity::None;
}

int8_t LinkDriver::ccaThresholdDbm() const { return lora::CCA_RSSI_THRESHOLD_DBM; }

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
