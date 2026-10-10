// SPDX-License-Identifier: MIT
// Seeed 102010611 only. Diagnostic point-to-point LoRa, not WICI/RNode.
#include <Arduino.h>
#include <RadioLib.h>
#include <esp_system.h>
SX1262 radio = new Module(41, 39, 42, 40);
volatile bool received = false;
bool ready = false;
uint32_t nextTx = 0;
String command;
uint32_t bootId;
void IRAM_ATTR onReceive() { received = true; }
// Each record is flushed: on the S3 USB-Serial/JTAG a short record could stay
// queued until the next host command (seen as 2.9 s USB lag in the R0 bench test).
void error(const char *where, int code) {
  Serial.printf("ERR %s %d\n", where, code);
  Serial.flush();
}
bool listen() {
  received = false;
  int code = radio.startReceive();
  if (code) { ready = false; error("receive", code); }
  return code == RADIOLIB_ERR_NONE;
}
void info() {
  Serial.printf("INFO pair-0.3 %012llX %d %d %08lX 869.525 125 7 5 0 1.8\n",
                ESP.getEfuseMac(), ready, esp_reset_reason(), static_cast<unsigned long>(bootId));
  Serial.flush();
}
void execute(const String &line) {
  if (line == "INFO") { info(); return; }
  if (!line.startsWith("TX ")) { error("command", -1); return; }
  if (!ready) { error("not_ready", -1); return; }
  String packet = line.substring(3);
  if (packet.length() == 0 || packet.length() > 80) { error("length", -1); return; }
  if (static_cast<int32_t>(millis() - nextTx) < 0) { error("cooldown", -1); return; }
  // >= 13 airtimes between starts. Also enforced on-device across USB reconnects.
  uint32_t airtime = radio.getTimeOnAir(packet.length()); // microseconds
  nextTx = millis() + (airtime * 13UL + 999UL) / 1000UL;
  radio.clearDio1Action();
  int code = radio.transmit(packet);
  Serial.printf("TX %d %s\n", code, packet.c_str());
  Serial.flush();
  radio.setDio1Action(onReceive);
  if (code) error("transmit", code);
  listen();
}
void setup() {
  Serial.begin(115200);
  bootId = esp_random();
  // Do not wait for a USB terminal: both nodes must boot autonomously.
  SPI.begin(7, 8, 9, 41);
  // Latest upstream Meshtastic variant: RX enable GPIO38, DIO2 TX switch, TCXO 1.8 V.
  radio.setRfSwitchPins(38, RADIOLIB_NC);
  int code = radio.begin(869.525, 125.0, 7, 5,
                        RADIOLIB_SX126X_SYNC_WORD_PRIVATE, 0, 8, 1.8);
  if (code) { error("begin", code); return; }
  code = radio.setDio2AsRfSwitch(true);
  if (code) { error("switch", code); return; }
  // Profile RX gain: catalogue -124 dBm (SF7/125 kHz) holds only in Rx Boosted gain.
  code = radio.setRxBoostedGainMode(true);
  if (code) { error("rx_gain", code); return; }
  radio.setDio1Action(onReceive);
  ready = listen();
  info();
}
void loop() {
  if (ready && received) {
    received = false;
    String packet;
    int code = radio.readData(packet);
    if (code == RADIOLIB_ERR_NONE) {
      // Never print arbitrary RF bytes as serial protocol records.
      bool valid = packet.length() <= 80;
      for (size_t i = 0; i < packet.length(); ++i)
        if (packet[i] < 32 || packet[i] > 126) valid = false;
      if (valid) {
        Serial.printf("RX %.1f %.1f %s\n", radio.getRSSI(), radio.getSNR(), packet.c_str());
        Serial.flush();
      } else error("payload", -1);
    } else error("read", code);
    listen();
  }
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { execute(command); command = ""; }
    else if (c != '\r') {
      command += c;
      if (command.length() > 90) { command = ""; error("usb_length", -1); }
    }
  }
  delay(1);
}
