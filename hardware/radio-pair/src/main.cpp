// SPDX-License-Identifier: MIT
// Seeed 102010611 only. Diagnostic point-to-point LoRa, not WICI/RNode.
#include <Arduino.h>
#include <RadioLib.h>
#include <esp_system.h>
SX1262 radio = new Module(41, 39, 42, 40);
volatile bool received = false;
volatile uint32_t receivedAtMs = 0;
bool ready = false;
uint32_t nextTx = 0;
String command;
uint32_t bootId;
// Last transmission, re-readable with LAST: the S3 USB-Serial/JTAG can drop a
// TX record while later records arrive (R0 range point P03).
uint32_t txCount = 0;
int lastTxCode = 0;
String lastTx = "-";
void IRAM_ATTR onReceive() { receivedAtMs = millis(); received = true; }
int nibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}
String hexBytes(const uint8_t *bytes, size_t count) {
  static const char digits[] = "0123456789abcdef";
  String result;
  result.reserve(count * 2);
  for (size_t i = 0; i < count; ++i) {
    result += digits[bytes[i] >> 4];
    result += digits[bytes[i] & 15];
  }
  return result;
}
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
  Serial.printf("INFO pair-0.4 %012llX %d %d %08lX 869.525 125 7 5 0 1.8\n",
                ESP.getEfuseMac(), ready, esp_reset_reason(), static_cast<unsigned long>(bootId));
  Serial.flush();
}
void last() {
  Serial.printf("LAST %lu %d %s\n", static_cast<unsigned long>(txCount), lastTxCode, lastTx.c_str());
  Serial.flush();
}
void execute(const String &line) {
  if (line == "INFO") { info(); return; }
  if (line == "LAST") { last(); return; }
  if (line.startsWith("TXHEX ")) {
    if (!ready) { error("not_ready", -1); return; }
    String payload = line.substring(6);
    if (payload.length() < 2 || payload.length() > 510 || payload.length() % 2) {
      error("length", -1); return;
    }
    uint8_t packet[255];
    const size_t count = payload.length() / 2;
    for (size_t i = 0; i < count; ++i) {
      const int high = nibble(payload[2 * i]), low = nibble(payload[2 * i + 1]);
      if (high < 0 || low < 0) { error("hex", -1); return; }
      packet[i] = static_cast<uint8_t>((high << 4) | low);
    }
    if (static_cast<int32_t>(millis() - nextTx) < 0) { error("cooldown", -1); return; }
    const uint32_t airtime = radio.getTimeOnAir(count);
    nextTx = millis() + (airtime * 13UL + 999UL) / 1000UL;
    radio.clearDio1Action();
    const uint32_t startMs = millis();
    const int code = radio.transmit(packet, count);
    ++txCount;
    lastTxCode = code;
    lastTx = payload;
    Serial.printf("TXHEX %d %lu %s\n", code,
                  static_cast<unsigned long>(startMs - receivedAtMs), payload.c_str());
    Serial.flush();
    radio.setDio1Action(onReceive);
    if (code) error("transmit", code);
    listen();
    return;
  }
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
  ++txCount;
  lastTxCode = code;
  lastTx = packet;
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
    uint8_t bytes[255];
    const size_t count = radio.getPacketLength();
    int code = count <= sizeof(bytes) ? radio.readData(bytes, count) : -1;
    if (code == RADIOLIB_ERR_NONE) {
      // Never print arbitrary RF bytes as serial protocol records.
      bool valid = count <= 80;
      for (size_t i = 0; i < count; ++i)
        if (bytes[i] < 32 || bytes[i] > 126) valid = false;
      if (valid) {
        String packet(reinterpret_cast<const char *>(bytes), count);
        Serial.printf("RX %.1f %.1f %s\n", radio.getRSSI(), radio.getSNR(), packet.c_str());
        Serial.flush();
      } else {
        const String hex = hexBytes(bytes, count);
        Serial.printf("RXHEX %lu %.1f %.1f %s\n", static_cast<unsigned long>(receivedAtMs),
                      radio.getRSSI(), radio.getSNR(), hex.c_str());
        Serial.flush();
      }
    } else error("read", code);
    listen();
  }
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { execute(command); command = ""; }
    else if (c != '\r') {
      command += c;
      if (command.length() > 520) { command = ""; error("usb_length", -1); }
    }
  }
  delay(1);
}
