// SPDX-License-Identifier: MIT
// CC1120 w programie stacji (stanowisko A, bench-a i bench-n1); polecenia jak wcześniej w main.cpp.
#if defined(WICI_BENCH_A) || defined(WICI_BENCH_N1)
#include "radio_console.h"

#include "board.h"
#include "cmdargs.h"
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

using cmdargs::boolName;

cc1120::Identity identify() {
    const cc1120::Identity id = chip.identify();
    radioOk = id.ready && id.partNumber == cc1120::PARTNUMBER_CC1120;
    return id;
}

void printRadio() {
    const cc1120::Identity id = identify();
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
    Serial.printf(",\"calibrated\":%s,\"marcstate\":\"0x%02X\"}\n", boolName(calibrated), chip.readReg(cc1120::MARCSTATE));
}

// Zapis tablicy P1, weryfikacja odczytem, ręczna kalibracja i ponowny zapis FOFF; ustala p1Ok.
cc1120::VerifyResult configureP1(bool& calibrated) {
    bench->stop();
    const cc1120::VerifyResult result = chip.configure(p1::REGISTERS, p1::REGISTER_COUNT);
    calibrated = result.mismatches == 0 && chip.calibrate();
    bench->applyOffset();
    configured = calibrated;
    return result;
}

void printFrequency() {
    const uint32_t word = chip.frequencyWord();
    const int16_t offset = chip.frequencyOffset();
    // f_RF = (FREQ * f_xosc / 2^16 + FREQOFF * f_xosc / 2^18) / LO_DIVIDER (SWRU295E, eq. 26, 27).
    const double hz = (static_cast<double>(word) * p1::F_XOSC_HZ / 65536.0 +
                       static_cast<double>(offset) * p1::F_XOSC_HZ / 262144.0) / p1::LO_DIVIDER;
    const double stepHz = static_cast<double>(p1::F_XOSC_HZ) / 262144.0 / p1::LO_DIVIDER;
    Serial.printf("{\"freq\":\"0x%06lX\",\"freqoff\":%d,\"hz\":%.1f,\"target_hz\":%lu,\"error_hz\":%.1f,"
                  "\"offset_step_hz\":%.2f,\"freqoff_est\":%d}\n",
                  static_cast<unsigned long>(word), offset, hz, static_cast<unsigned long>(p1::CARRIER_HZ),
                  hz - p1::CARRIER_HZ, stepHz, chip.frequencyOffsetEstimate());
}

void printRssi() {
    const uint8_t marc = chip.readMarcState();
    const cc1120::Rssi r = chip.rssi(p1::RSSI_OFFSET_DB);
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
    chip.reset();
    identify();
    if (radioOk) {
        bool calibrated = false;
        configureP1(calibrated);
    }
}

bool ok() { return radioOk; }
bool p1Ok() { return configured; }

bool check() {
    // lost: konfiguracja utracona w pracy (nie poleceniem RESET), więc wraca bez polecenia CONFIG.
    static const cc1120::RegisterValue* const sync = findRegister(p1::REGISTERS, p1::REGISTER_COUNT, "SYNC3");
    static bool lost = false;
    identify();
    if (!radioOk) { lost = lost || configured; configured = false; return false; }
    if (configured ? chip.verify(sync, SYNC_REGISTERS).mismatches == 0 : !lost) return false;
    bool calibrated = false;
    configureP1(calibrated);
    lost = !configured;
    return configured;
}

void report() {
    printRadio();
    if (radioOk) {
        const cc1120::VerifyResult result = chip.verify(p1::REGISTERS, p1::REGISTER_COUNT);
        printVerify("verify", result, configured);
        printFrequency();
    }
}

void printState() {
    const uint8_t marc = chip.readMarcState();
    // Status z odczytu MARCSTATE, zanim następne odczyty go nadpiszą (kolejność argumentów printf jest nieokreślona).
    const uint8_t status = chip.lastStatus();
    const uint8_t rxBytes = chip.rxBytes();
    const uint8_t txBytes = chip.txBytes();
    Serial.printf("{\"marc\":\"%s\",\"marcstate\":\"0x%02X\",\"status\":\"0x%02X\",\"rxbytes\":%u,\"txbytes\":%u}\n",
                  cc1120::marcStateName(marc), marc, status, rxBytes, txBytes);
}

bool handle(const char* cmd, char* words[], size_t n) {
    if (!strcmp(cmd, "RADIO")) printRadio();
    else if (!strcmp(cmd, "RESET")) {
        bench->stop();
        const bool done = chip.reset();
        configured = false;
        Serial.printf("{\"reset\":%s,\"status\":\"0x%02X\"}\n", boolName(done), chip.lastStatus());
        printRadio();
    } else if (!strcmp(cmd, "CONFIG")) {
        bool calibrated = false;
        const cc1120::VerifyResult result = configureP1(calibrated);
        printVerify("config", result, calibrated);
    } else if (!strcmp(cmd, "VERIFY")) {
        const cc1120::VerifyResult result = chip.verify(p1::REGISTERS, p1::REGISTER_COUNT);
        printVerify("verify", result, configured);
    } else if (!strcmp(cmd, "CAL")) {
        bench->stop();
        const bool done = chip.calibrate();
        // P1 gotowe tylko przy udanej kalibracji i tablicy zgodnej z odczytem (także po RESET bez CONFIG).
        configured = done && chip.verify(p1::REGISTERS, p1::REGISTER_COUNT).mismatches == 0;
        Serial.printf("{\"cal\":%s,\"fs_vco2\":\"0x%02X\",\"fs_vco4\":\"0x%02X\",\"fs_chp\":\"0x%02X\",\"fs_cal2\":\"0x%02X\"}\n",
                      boolName(done), chip.readReg(cc1120::FS_VCO2), chip.readReg(cc1120::FS_VCO4),
                      chip.readReg(cc1120::FS_CHP), chip.readReg(cc1120::FS_CAL2));
    } else if (!strcmp(cmd, "FREQ")) printFrequency();
    else if (!strcmp(cmd, "IDLE")) {
        bench->stop();
        Serial.printf("{\"idle\":%s}\n", boolName(chip.idle()));
        printState();
    } else if (!strcmp(cmd, "RSSI")) printRssi();
    else if (!strcmp(cmd, "STATE")) printState();
    else if (!strcmp(cmd, "REG") && n == 1) {
        // Tylko rejestry: adresy nagłówka 0x30-0x3D to polecenia (STX, SRES...), 0x3E i 0x3F kolejki FIFO.
        uint32_t address = 0;
        if (!cmdargs::parseUint(words[0], 0, 0x2FFF, address, 16) || (address > 0x2E && address < 0x2F00)) {
            Serial.println("{\"error\":\"REG <00-2E|2F00-2FFF>\"}");
            return true;
        }
        const uint8_t value = chip.readReg(static_cast<uint16_t>(address));
        Serial.printf("{\"reg\":\"0x%04X\",\"value\":\"0x%02X\",\"status\":\"0x%02X\"}\n", address, value, chip.lastStatus());
    } else return false;
    return true;
}

const char* helpCommands() { return ",\"RADIO\",\"RESET\",\"CONFIG\",\"VERIFY\",\"CAL\",\"FREQ\",\"IDLE\",\"RSSI\",\"STATE\",\"REG <00-2E|2F00-2FFF>\""; }

}  // namespace radiocon

#endif
