// SPDX-License-Identifier: MIT
// CC1120 w programie stacji (stanowisko A, bench-a i bench-n1); polecenia jak wcześniej w main.cpp.
#if defined(WICI_BENCH_A) || defined(WICI_BENCH_N1)
#include "radio_console.h"

#include "board.h"
#include "cc1120.h"
#include "cc1120_link.h"
#include "p1_registers.h"
#include "platform.h"

namespace radiocon {

const char* const NAME = "CC1120";
const uint16_t RX_FILTER_HZ = p1::RX_FILTER_HZ;
const int8_t TX_POWER_DBM = p1::TX_POWER_DBM;

namespace {

cc1120::Radio chip(platform::bus(), board::RADIO_CS, board::RADIO_RESET, board::SPI_HZ);
cc1120::LinkDriver driver(chip, board::RADIO_GPIO2);
measure::Bench* bench = nullptr;
bool radioOk = false;
bool configured = false;  // tablica P1 zapisana, zweryfikowana i syntezer skalibrowany

const char* boolName(bool value) { return value ? "true" : "false"; }

cc1120::Radio& radio() { return chip; }

void printRadio() {
    const cc1120::Identity id = radio().identify();
    radioOk = id.ready && id.partNumber == cc1120::PARTNUMBER_CC1120;
    Serial.printf("{\"radio\":\"CC1120\",\"ready\":%s,\"partnumber\":\"0x%02X\",\"partversion\":\"0x%02X\","
                  "\"marcstate\":\"0x%02X\",\"marc\":\"%s\",\"state\":\"%s\",\"p1_ok\":%s,\"ok\":%s}\n",
                  boolName(id.ready), id.partNumber, id.partVersion, id.marcState,
                  cc1120::marcStateName(id.marcState), cc1120::stateName(cc1120::statusState(id.status)),
                  boolName(configured), boolName(radioOk));
}

void printVerify(const char* step, const cc1120::VerifyResult& result, bool calibrated) {
    Serial.printf("{\"%s\":%s,\"checked\":%u,\"mismatches\":%u", step, boolName(result.mismatches == 0 && calibrated),
                  result.checked, result.mismatches);
    if (result.mismatches) {
        Serial.printf(",\"first\":\"%s\",\"reg\":\"0x%04X\",\"expected\":\"0x%02X\",\"actual\":\"0x%02X\"",
                      result.firstName, result.firstAddress, result.expected, result.actual);
    }
    Serial.printf(",\"calibrated\":%s,\"marcstate\":\"0x%02X\"}\n", boolName(calibrated), radio().readReg(cc1120::MARCSTATE));
}

// Zapis tablicy P1, weryfikacja odczytem, ręczna kalibracja i ponowny zapis FOFF; ustala p1Ok.
cc1120::VerifyResult configureP1(bool& calibrated) {
    bench->stop();
    const cc1120::VerifyResult result = radio().configure(p1::REGISTERS, p1::REGISTER_COUNT);
    calibrated = result.mismatches == 0 && radio().calibrate();
    bench->applyOffset();
    configured = calibrated;
    return result;
}

void printFrequency() {
    const uint32_t word = radio().frequencyWord();
    const int16_t offset = radio().frequencyOffset();
    // f_RF = (FREQ * f_xosc / 2^16 + FREQOFF * f_xosc / 2^18) / LO_DIVIDER (SWRU295E, eq. 26, 27).
    const double hz = (static_cast<double>(word) * p1::F_XOSC_HZ / 65536.0 +
                       static_cast<double>(offset) * p1::F_XOSC_HZ / 262144.0) / p1::LO_DIVIDER;
    const double stepHz = static_cast<double>(p1::F_XOSC_HZ) / 262144.0 / p1::LO_DIVIDER;
    Serial.printf("{\"freq\":\"0x%06lX\",\"freqoff\":%d,\"hz\":%.1f,\"target_hz\":%lu,\"error_hz\":%.1f,"
                  "\"offset_step_hz\":%.2f,\"freqoff_est\":%d}\n",
                  static_cast<unsigned long>(word), offset, hz, static_cast<unsigned long>(p1::CARRIER_HZ),
                  hz - p1::CARRIER_HZ, stepHz, radio().frequencyOffsetEstimate());
}

void printRssi() {
    const uint8_t marc = radio().readMarcState();
    const cc1120::Rssi r = radio().rssi(p1::RSSI_OFFSET_DB);
    Serial.printf("{\"rssi_valid\":%s,\"rssi_dbm\":%d,\"rssi_offset_db\":%d,\"cs\":%s,\"cs_valid\":%s,\"marc\":\"%s\"}\n",
                  boolName(r.valid), r.dbm, p1::RSSI_OFFSET_DB, boolName(r.carrierSense), boolName(r.carrierSenseValid),
                  cc1120::marcStateName(marc));
}

}  // namespace

radiolink::Driver& link() { return driver; }

void attach(measure::Bench& b) { bench = &b; }

void begin() {
    pinMode(board::RADIO_GPIO0, INPUT);
    pinMode(board::RADIO_GPIO2, INPUT);
#if defined(WICI_BOARD_N1)
    pinMode(board::RADIO_GPIO3, INPUT);
#endif
    chip.begin();
}

void start() {
    radio().reset();
    const cc1120::Identity id = radio().identify();
    radioOk = id.ready && id.partNumber == cc1120::PARTNUMBER_CC1120;
    if (radioOk) {
        bool calibrated = false;
        configureP1(calibrated);
    }
}

bool ok() { return radioOk; }
bool p1Ok() { return configured; }

void report() {
    printRadio();
    if (radioOk) {
        const cc1120::VerifyResult result = radio().verify(p1::REGISTERS, p1::REGISTER_COUNT);
        printVerify("verify", result, configured);
        printFrequency();
    }
}

void printState() {
    const uint8_t marc = radio().readMarcState();
    Serial.printf("{\"marc\":\"%s\",\"marcstate\":\"0x%02X\",\"status\":\"0x%02X\",\"rxbytes\":%u,\"txbytes\":%u}\n",
                  cc1120::marcStateName(marc), marc, radio().lastStatus(), radio().rxBytes(), radio().txBytes());
}

bool handle(const char* cmd, char* words[], size_t n) {
    if (!strcmp(cmd, "RADIO")) printRadio();
    else if (!strcmp(cmd, "RESET")) {
        bench->stop();
        const bool done = radio().reset();
        configured = false;
        Serial.printf("{\"reset\":%s,\"status\":\"0x%02X\"}\n", boolName(done), radio().lastStatus());
        printRadio();
    } else if (!strcmp(cmd, "CONFIG")) {
        bool calibrated = false;
        const cc1120::VerifyResult result = configureP1(calibrated);
        printVerify("config", result, calibrated);
    } else if (!strcmp(cmd, "VERIFY")) {
        const cc1120::VerifyResult result = radio().verify(p1::REGISTERS, p1::REGISTER_COUNT);
        printVerify("verify", result, configured);
    } else if (!strcmp(cmd, "CAL")) {
        bench->stop();
        const bool done = radio().calibrate();
        Serial.printf("{\"cal\":%s,\"fs_vco2\":\"0x%02X\",\"fs_vco4\":\"0x%02X\",\"fs_chp\":\"0x%02X\",\"fs_cal2\":\"0x%02X\"}\n",
                      boolName(done), radio().readReg(cc1120::FS_VCO2), radio().readReg(cc1120::FS_VCO4),
                      radio().readReg(cc1120::FS_CHP), radio().readReg(cc1120::FS_CAL2));
    } else if (!strcmp(cmd, "FREQ")) printFrequency();
    else if (!strcmp(cmd, "IDLE")) {
        bench->stop();
        Serial.printf("{\"idle\":%s}\n", boolName(radio().idle()));
        printState();
    } else if (!strcmp(cmd, "RSSI")) printRssi();
    else if (!strcmp(cmd, "STATE")) printState();
    else if (!strcmp(cmd, "REG") && n == 1) {
        const uint16_t address = static_cast<uint16_t>(strtoul(words[0], nullptr, 16));
        const uint8_t value = radio().readReg(address);
        Serial.printf("{\"reg\":\"0x%04X\",\"value\":\"0x%02X\",\"status\":\"0x%02X\"}\n", address, value, radio().lastStatus());
    } else return false;
    return true;
}

const char* helpCommands() { return ",\"RADIO\",\"RESET\",\"CONFIG\",\"VERIFY\",\"CAL\",\"FREQ\",\"IDLE\",\"RSSI\",\"STATE\",\"REG <hex>\""; }

}  // namespace radiocon

#endif
