// SPDX-License-Identifier: MIT
// WICI, stanowisko deweloperskie A: pierwsze kroki oprogramowania stacji na nRF52840-DK.
// Zakres: USB CDC z poleceniami tekstowymi, identyfikacja CC1120 i FRAM przez SPI,
// przyciski i diody płytki. Bez profilu P1, stosu Reticulum i ekranu (następne kroki).
#include <Arduino.h>
#include <Adafruit_TinyUSB.h>
#include <SPI.h>

#include "board_bench_a.h"
#include "cc1120.h"
#include "fram.h"

#ifndef WICI_FW_VERSION
#define WICI_FW_VERSION "bench-a-dev"
#endif

namespace {

cc1120::Radio radio(SPI, board::RADIO_CS, board::RADIO_RESET, board::SPI_HZ);
fram::Memory memory(SPI, board::FRAM_CS, board::SPI_HZ);

bool radioOk = false;
bool framOk = false;
uint32_t restarts = 0;  // licznik restartów trafi do FRAM w następnym kroku
char line[128];
size_t lineLength = 0;

const uint8_t buttons[] = {board::BTN_UP, board::BTN_DOWN, board::BTN_OK, board::BTN_BACK};
const char* const buttonNames[] = {"up", "down", "ok", "back"};
const uint8_t leds[] = {board::LED_HEARTBEAT, board::LED_RADIO, board::LED_FRAM, board::LED_USB};

void ledWrite(uint8_t pin, bool on) { digitalWrite(pin, on ? LOW : HIGH); }  // diody DK aktywne stanem niskim

bool pressed(uint8_t pin) { return digitalRead(pin) == LOW; }

void printRadio() {
    const cc1120::Identity id = radio.identify();
    radioOk = id.ready && id.partNumber == cc1120::PARTNUMBER_CC1120;
    ledWrite(board::LED_RADIO, radioOk);
    Serial.printf("{\"radio\":\"CC1120\",\"ready\":%s,\"partnumber\":\"0x%02X\",\"partversion\":\"0x%02X\","
                  "\"marcstate\":\"0x%02X\",\"state\":\"%s\",\"ok\":%s}\n",
                  id.ready ? "true" : "false", id.partNumber, id.partVersion, id.marcState,
                  cc1120::stateName(cc1120::statusState(id.status)), radioOk ? "true" : "false");
}

void printFram() {
    const fram::Id id = memory.identify();
    framOk = id.mb85rs4m;
    ledWrite(board::LED_FRAM, framOk);
    Serial.printf("{\"fram\":\"MB85RS4MT\",\"id\":\"%02X%02X%02X%02X\",\"status\":\"0x%02X\",\"fujitsu\":%s,\"ok\":%s}\n",
                  id.bytes[0], id.bytes[1], id.bytes[2], id.bytes[3], id.status,
                  id.fujitsu ? "true" : "false", framOk ? "true" : "false");
}

void printInfo() {
    // Pola jak w INFO ze specyfikacji radia; wartości ruchu i zasilania są zerowe,
    // bo stanowisko nie ma jeszcze profilu P1 ani pomiaru napięcia.
    Serial.printf("{\"contract\":2,\"profile\":\"P1\",\"radio\":\"CC1120\",\"mcu\":\"nRF52840\",\"fw\":\"%s\","
                  "\"src\":\"USB\",\"mv\":0,\"tx_wait_ms\":0,\"rx_ok\":0,\"rx_bad\":0,\"tx_drop\":0,\"restarts\":%lu,"
                  "\"bench\":\"A\",\"radio_ok\":%s,\"fram_ok\":%s,\"uptime_s\":%lu}\n",
                  WICI_FW_VERSION, static_cast<unsigned long>(restarts), radioOk ? "true" : "false",
                  framOk ? "true" : "false", static_cast<unsigned long>(millis() / 1000));
}

void printButtons() {
    Serial.print("{\"buttons\":{");
    for (size_t i = 0; i < 4; ++i) {
        Serial.printf("\"%s\":%s%s", buttonNames[i], pressed(buttons[i]) ? "true" : "false", i < 3 ? "," : "");
    }
    Serial.println("}}");
}

void printHelp() {
    Serial.println("{\"commands\":[\"HELP\",\"INFO\",\"RADIO\",\"RESET\",\"REG <hex>\",\"FRAM\",\"BTN\",\"LED <1-4> <0|1>\"]}");
}

void handle(char* cmd) {
    for (char* p = cmd; *p; ++p) *p = toupper(*p);
    char* arg = strchr(cmd, ' ');
    if (arg) *arg++ = '\0';
    if (!strcmp(cmd, "INFO")) printInfo();
    else if (!strcmp(cmd, "RADIO")) printRadio();
    else if (!strcmp(cmd, "RESET")) {
        const bool ok = radio.reset();
        Serial.printf("{\"reset\":%s,\"status\":\"0x%02X\"}\n", ok ? "true" : "false", radio.lastStatus());
        printRadio();
    } else if (!strcmp(cmd, "REG") && arg) {
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
            Serial.printf("{\"led\":%d,\"on\":%s}\n", index, atoi(state + 1) ? "true" : "false");
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
    ledWrite(board::LED_RADIO, radioOk);
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
        printFram();
    }
    if (!usb) reported = false;
    pollSerial();
}
