// SPDX-License-Identifier: MIT
// WICI, stanowisko deweloperskie A: pierwsze kroki oprogramowania stacji na nRF52840-DK.
// Zakres: USB CDC z poleceniami tekstowymi, identyfikacja CC1120 i FRAM przez SPI,
// konfiguracja rejestrów profilu P1 z weryfikacją odczytu i kalibracją syntezera,
// odczyt częstotliwości i RSSI, przyciski i diody płytki. Bez nadawania, odbioru
// ramek, stosu Reticulum i ekranu (następne kroki).
#include <Arduino.h>
#include <Adafruit_TinyUSB.h>
#include <SPI.h>

#include "board_bench_a.h"
#include "cc1120.h"
#include "fram.h"
#include "p1_registers.h"

#ifndef WICI_FW_VERSION
#define WICI_FW_VERSION "bench-a-dev"
#endif

namespace {

cc1120::Radio radio(SPI, board::RADIO_CS, board::RADIO_RESET, board::SPI_HZ);
fram::Memory memory(SPI, board::FRAM_CS, board::SPI_HZ);

bool radioOk = false;
bool framOk = false;
bool p1Ok = false;        // tablica P1 zapisana, zweryfikowana i syntezer skalibrowany
uint32_t restarts = 0;  // licznik restartów trafi do FRAM w następnym kroku
char line[128];
size_t lineLength = 0;

const uint8_t buttons[] = {board::BTN_UP, board::BTN_DOWN, board::BTN_OK, board::BTN_BACK};
const char* const buttonNames[] = {"up", "down", "ok", "back"};
const uint8_t leds[] = {board::LED_HEARTBEAT, board::LED_RADIO, board::LED_FRAM, board::LED_USB};

void ledWrite(uint8_t pin, bool on) { digitalWrite(pin, on ? LOW : HIGH); }  // diody DK aktywne stanem niskim

bool pressed(uint8_t pin) { return digitalRead(pin) == LOW; }

const char* boolName(bool value) { return value ? "true" : "false"; }

void printRadio() {
    const cc1120::Identity id = radio.identify();
    radioOk = id.ready && id.partNumber == cc1120::PARTNUMBER_CC1120;
    ledWrite(board::LED_RADIO, radioOk && p1Ok);
    Serial.printf("{\"radio\":\"CC1120\",\"ready\":%s,\"partnumber\":\"0x%02X\",\"partversion\":\"0x%02X\","
                  "\"marcstate\":\"0x%02X\",\"marc\":\"%s\",\"state\":\"%s\",\"p1_ok\":%s,\"ok\":%s}\n",
                  boolName(id.ready), id.partNumber, id.partVersion, id.marcState,
                  cc1120::marcStateName(id.marcState), cc1120::stateName(cc1120::statusState(id.status)),
                  boolName(p1Ok), boolName(radioOk));
}

void printVerify(const char* step, const cc1120::VerifyResult& result, bool calibrated) {
    Serial.printf("{\"%s\":%s,\"checked\":%u,\"mismatches\":%u", step, boolName(result.mismatches == 0 && calibrated),
                  result.checked, result.mismatches);
    if (result.mismatches) {
        Serial.printf(",\"first\":\"%s\",\"reg\":\"0x%04X\",\"expected\":\"0x%02X\",\"actual\":\"0x%02X\"",
                      result.firstName, result.firstAddress, result.expected, result.actual);
    }
    Serial.printf(",\"calibrated\":%s,\"marcstate\":\"0x%02X\"}\n", boolName(calibrated), radio.readReg(cc1120::MARCSTATE));
}

// Zapis tablicy P1, weryfikacja odczytem i ręczna kalibracja; ustala p1Ok.
cc1120::VerifyResult configureP1(bool& calibrated) {
    const cc1120::VerifyResult result = radio.configure(p1::REGISTERS, p1::REGISTER_COUNT);
    calibrated = result.mismatches == 0 && radio.calibrate();
    p1Ok = calibrated;
    ledWrite(board::LED_RADIO, radioOk && p1Ok);
    return result;
}

void printFrequency() {
    const uint32_t word = radio.frequencyWord();
    const int16_t offset = radio.frequencyOffset();
    // f_RF = (FREQ * f_xosc / 2^16 + FREQOFF * f_xosc / 2^18) / LO_DIVIDER (SWRU295E, eq. 26, 27).
    const double hz = (static_cast<double>(word) * p1::F_XOSC_HZ / 65536.0 +
                       static_cast<double>(offset) * p1::F_XOSC_HZ / 262144.0) / p1::LO_DIVIDER;
    const double stepHz = static_cast<double>(p1::F_XOSC_HZ) / 262144.0 / p1::LO_DIVIDER;
    Serial.printf("{\"freq\":\"0x%06lX\",\"freqoff\":%d,\"hz\":%.1f,\"target_hz\":%lu,\"error_hz\":%.1f,"
                  "\"offset_step_hz\":%.2f,\"freqoff_est\":%d}\n",
                  static_cast<unsigned long>(word), offset, hz, static_cast<unsigned long>(p1::CARRIER_HZ),
                  hz - p1::CARRIER_HZ, stepHz, radio.frequencyOffsetEstimate());
}

void printRssi() {
    const uint8_t marc = radio.readMarcState();
    const cc1120::Rssi r = radio.rssi(p1::RSSI_OFFSET_DB);
    Serial.printf("{\"rssi_valid\":%s,\"rssi_dbm\":%d,\"rssi_offset_db\":%d,\"cs\":%s,\"cs_valid\":%s,\"marc\":\"%s\"}\n",
                  boolName(r.valid), r.dbm, p1::RSSI_OFFSET_DB, boolName(r.carrierSense), boolName(r.carrierSenseValid),
                  cc1120::marcStateName(marc));
}

void printState() {
    const uint8_t marc = radio.readMarcState();
    Serial.printf("{\"marc\":\"%s\",\"marcstate\":\"0x%02X\",\"status\":\"0x%02X\",\"rxbytes\":%u,\"txbytes\":%u}\n",
                  cc1120::marcStateName(marc), marc, radio.lastStatus(), radio.readReg(cc1120::NUM_RXBYTES),
                  radio.readReg(cc1120::NUM_TXBYTES));
}

void printFram() {
    const fram::Id id = memory.identify();
    framOk = id.mb85rs4m;
    ledWrite(board::LED_FRAM, framOk);
    Serial.printf("{\"fram\":\"MB85RS4MT\",\"id\":\"%02X%02X%02X%02X\",\"status\":\"0x%02X\",\"fujitsu\":%s,\"ok\":%s}\n",
                  id.bytes[0], id.bytes[1], id.bytes[2], id.bytes[3], id.status, boolName(id.fujitsu), boolName(framOk));
}

void printInfo() {
    // Pola jak w INFO ze specyfikacji radia; liczniki ruchu i napięcie są zerowe,
    // bo stanowisko nie nadaje jeszcze ramek ani nie mierzy zasilania.
    Serial.printf("{\"contract\":2,\"profile\":\"P1\",\"radio\":\"CC1120\",\"mcu\":\"nRF52840\",\"fw\":\"%s\","
                  "\"src\":\"USB\",\"mv\":0,\"tx_wait_ms\":0,\"rx_ok\":0,\"rx_bad\":0,\"tx_drop\":0,\"restarts\":%lu,"
                  "\"bench\":\"A\",\"radio_ok\":%s,\"p1_ok\":%s,\"fram_ok\":%s,\"carrier_hz\":%lu,\"symbol_rate\":%u,"
                  "\"deviation_hz\":%u,\"rx_filter_hz\":%u,\"tx_power_dbm\":%d,\"uptime_s\":%lu}\n",
                  WICI_FW_VERSION, static_cast<unsigned long>(restarts), boolName(radioOk), boolName(p1Ok),
                  boolName(framOk), static_cast<unsigned long>(p1::CARRIER_HZ), p1::SYMBOL_RATE, p1::DEVIATION_HZ,
                  p1::RX_FILTER_HZ, p1::TX_POWER_DBM, static_cast<unsigned long>(millis() / 1000));
}

void printButtons() {
    Serial.print("{\"buttons\":{");
    for (size_t i = 0; i < 4; ++i) {
        Serial.printf("\"%s\":%s%s", buttonNames[i], boolName(pressed(buttons[i])), i < 3 ? "," : "");
    }
    Serial.println("}}");
}

void printHelp() {
    Serial.println("{\"commands\":[\"HELP\",\"INFO\",\"RADIO\",\"RESET\",\"CONFIG\",\"VERIFY\",\"CAL\",\"FREQ\","
                   "\"RX\",\"IDLE\",\"RSSI\",\"STATE\",\"REG <hex>\",\"FRAM\",\"BTN\",\"LED <1-4> <0|1>\"]}");
}

void handle(char* cmd) {
    for (char* p = cmd; *p; ++p) *p = toupper(*p);
    char* arg = strchr(cmd, ' ');
    if (arg) *arg++ = '\0';
    if (!strcmp(cmd, "INFO")) printInfo();
    else if (!strcmp(cmd, "RADIO")) printRadio();
    else if (!strcmp(cmd, "RESET")) {
        const bool ok = radio.reset();
        p1Ok = false;
        Serial.printf("{\"reset\":%s,\"status\":\"0x%02X\"}\n", boolName(ok), radio.lastStatus());
        printRadio();
    } else if (!strcmp(cmd, "CONFIG")) {
        bool calibrated = false;
        const cc1120::VerifyResult result = configureP1(calibrated);
        printVerify("config", result, calibrated);
    } else if (!strcmp(cmd, "VERIFY")) {
        const cc1120::VerifyResult result = radio.verify(p1::REGISTERS, p1::REGISTER_COUNT);
        printVerify("verify", result, p1Ok);
    } else if (!strcmp(cmd, "CAL")) {
        const bool ok = radio.calibrate();
        Serial.printf("{\"cal\":%s,\"fs_vco2\":\"0x%02X\",\"fs_vco4\":\"0x%02X\",\"fs_chp\":\"0x%02X\",\"fs_cal2\":\"0x%02X\"}\n",
                      boolName(ok), radio.readReg(cc1120::FS_VCO2), radio.readReg(cc1120::FS_VCO4),
                      radio.readReg(cc1120::FS_CHP), radio.readReg(cc1120::FS_CAL2));
    } else if (!strcmp(cmd, "FREQ")) printFrequency();
    else if (!strcmp(cmd, "RX")) {
        radio.strobe(cc1120::SRX);
        const bool ok = radio.waitMarcState(cc1120::MARC_STATE_RX, 50);
        Serial.printf("{\"rx\":%s}\n", boolName(ok));
        printState();
    } else if (!strcmp(cmd, "IDLE")) {
        Serial.printf("{\"idle\":%s}\n", boolName(radio.idle()));
        printState();
    } else if (!strcmp(cmd, "RSSI")) printRssi();
    else if (!strcmp(cmd, "STATE")) printState();
    else if (!strcmp(cmd, "REG") && arg) {
        const uint16_t address = static_cast<uint16_t>(strtoul(arg, nullptr, 16));
        const uint8_t value = radio.readReg(address);
        Serial.printf("{\"reg\":\"0x%04X\",\"value\":\"0x%02X\",\"status\":\"0x%02X\"}\n", address, value, radio.lastStatus());
    } else if (!strcmp(cmd, "FRAM")) printFram();
    else if (!strcmp(cmd, "BTN")) printButtons();
    else if (!strcmp(cmd, "LED") && arg) {
        const int index = atoi(arg);
        char* state = strchr(arg, ' ');
        if (index >= 1 && index <= 4 && state) {
            ledWrite(leds[index - 1], atoi(state + 1) != 0);
            Serial.printf("{\"led\":%d,\"on\":%s}\n", index, boolName(atoi(state + 1) != 0));
        } else Serial.println("{\"error\":\"LED <1-4> <0|1>\"}");
    } else if (!strcmp(cmd, "HELP") || !*cmd) printHelp();
    else Serial.printf("{\"error\":\"unknown\",\"cmd\":\"%s\"}\n", cmd);
}

void pollSerial() {
    while (Serial.available()) {
        const char c = static_cast<char>(Serial.read());
        if (c == '\n' || c == '\r') {
            line[lineLength] = '\0';
            if (lineLength) handle(line);
            lineLength = 0;
        } else if (lineLength < sizeof(line) - 1) {
            line[lineLength++] = c;
        }
    }
}

}  // namespace

void setup() {
    for (uint8_t pin : leds) { pinMode(pin, OUTPUT); ledWrite(pin, false); }
    for (uint8_t pin : buttons) pinMode(pin, INPUT_PULLUP);
    pinMode(board::RADIO_GPIO0, INPUT);
    pinMode(board::RADIO_GPIO2, INPUT);
    SPI.begin();
    radio.begin();
    memory.begin();
    Serial.begin(115200);
    delay(50);
    radio.reset();
    const cc1120::Identity id = radio.identify();
    radioOk = id.ready && id.partNumber == cc1120::PARTNUMBER_CC1120;
    if (radioOk) {
        bool calibrated = false;
        configureP1(calibrated);  // LED2 świeci dopiero po zapisanym i skalibrowanym P1
    }
    framOk = memory.identify().mb85rs4m;
    ledWrite(board::LED_FRAM, framOk);
}

void loop() {
    static uint32_t lastBeat = 0;
    static bool beat = false;
    static bool reported = false;
    const uint32_t now = millis();
    if (now - lastBeat >= 500) {
        lastBeat = now;
        beat = !beat;
        ledWrite(board::LED_HEARTBEAT, beat);
    }
    const bool usb = Serial;  // CDC otwarty przez hosta
    ledWrite(board::LED_USB, usb);
    if (usb && !reported) {  // jednorazowy raport po otwarciu portu
        reported = true;
        printInfo();
        printRadio();
        if (radioOk) {
            const cc1120::VerifyResult result = radio.verify(p1::REGISTERS, p1::REGISTER_COUNT);
            printVerify("verify", result, p1Ok);
            printFrequency();
        }
        printFram();
    }
    if (!usb) reported = false;
    pollSerial();
}
