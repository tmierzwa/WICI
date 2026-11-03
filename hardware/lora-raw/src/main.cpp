// SPDX-License-Identifier: MIT
// lora-raw: raw LoRa frames over USB for the RAK4631 (nRF52840 + SX1262 in the RAK4630 module).
// Bench tool only: no WICI, RNode or Reticulum logic, no frame header, no channel access rules, no duty-cycle
// limit. Bytes from "tx" go on air unchanged; every received frame (also with a CRC error) goes to USB.
//
// USB serial, one command per line:
//   info                 -> {"info":"lora-raw-0.2",...,"reset":RESETREAS,"cut":lines cut on a stalled host}
//   rx on | rx off       -> {"rx_stream":true|false}; frames: {"rx":"<hex>","len":N,"rssi":..,"snr":..,"crc":true,"t_us":T}
//   tx <hex>             -> {"tx":"done","n":K,"len":N,"start_us":S,"done_us":D,"air_us":D-S,"toa_us":..,"power_dbm":P}
//   power <dBm>          -> {"power_dbm":P}   (-9..22, SX1262 high-power PA)
// Errors: {"err":"<what>","code":C}. Times are microseconds of a 1 MHz TIMER4 clock since boot, extended to
// 64 bits; t_us of a received frame is the RxDone interrupt (end of the frame on air).
//
// Profile: docs/spec/radio.md "Profil LoRa pilotażu" (as firmware/src/lora_profile.h).
// RAK4631 SX1262 wiring (RAK4630 module): NSS P1.10 (42), SCK P1.11 (43), MOSI P1.12 (44), MISO P1.13 (45),
// BUSY P1.14 (46), DIO1 P1.15 (47), NRESET P1.06 (38), P1.05 (37) powers the antenna switch, DIO2 switches it,
// DIO3 supplies the TCXO. Sources: RNode_Firmware 56775c51 Boards.h (BOARD_RAK4631: pin_cs 42, sclk 43, mosi 44,
// miso 45, busy 46, dio 47, reset 38, rxen 37, DIO2_AS_RF_SWITCH) and sx126x.cpp enableTCXO (3.3 V for
// RAK4631); RAKwireless SX126x-Arduino lora_rak4630_init (same pins, RADIO_RXEN 37 "power for antenna switch",
// USE_RXEN_ANT_PWR, DIO2 antenna switch, DIO3 TCXO with the library default TCXO_CTRL_3_3V, DC-DC);
// meshtastic/firmware variants/nrf52840/rak4631/variant.h (same pins, SX126X_POWER_EN 37, DIO2 RF switch).
// Meshtastic sets the TCXO to 1.8 V; this tool follows the module vendor's library and RNode (3.3 V).
#include <Arduino.h>
#include <RadioLib.h>

namespace {

constexpr const char *VERSION = "lora-raw-0.2";
constexpr float CARRIER_MHZ = 869.525f;
constexpr float BANDWIDTH_KHZ = 125.0f;
constexpr uint8_t SPREADING_FACTOR = 7;
constexpr uint8_t CODING_RATE = 5;  // 4/5
constexpr uint8_t SYNC_WORD = 0x12;  // registers 0x0740 = 0x14, 0x0741 = 0x24 (RadioLib control bits 0x44)
constexpr uint16_t PREAMBLE_SYMBOLS = 24;
constexpr float TCXO_VOLTS = 3.3f;
constexpr int8_t POWER_MIN_DBM = -9;  // SX1262 high-power PA range in RadioLib: -9..22 dBm
constexpr int8_t POWER_MAX_DBM = 22;

constexpr int PIN_NSS = 42, PIN_DIO1 = 47, PIN_RESET = 38, PIN_BUSY = 46, PIN_ANT_POWER = 37;

SX1262 radio = new Module(PIN_NSS, PIN_DIO1, PIN_RESET, PIN_BUSY);

enum class State { Idle, Receiving, Transmitting };
State state = State::Idle;
bool ready = false;
bool rxStream = true;
int8_t powerDbm = POWER_MIN_DBM;
uint32_t txCount = 0;
size_t txLength = 0;
uint64_t txStartUs = 0;
uint32_t txToaUs = 0;
int beginCode = 0;

volatile bool dio1 = false;
volatile uint32_t dio1At = 0;

char line[600];
size_t lineLength = 0;
bool lineOverflow = false;
char out[700];

// USB output must never stop the loop. Adafruit_USBD_CDC::write waits for FIFO room for as long as the host
// keeps the port open, so a host that stops reading without closing the port would stall the tool. emit()
// writes only what fits and gives a line EMIT_MS; the rest is cut and counted (info "cut").
constexpr uint32_t EMIT_MS = 100;
uint32_t emitCut = 0;
// Watchdog: a loop that stops for WATCHDOG_S for any other reason restarts the tool; info "reset" shows
// RESETREAS of that start (bit 1 DOG: watchdog; 0: power on), so a hang is visible instead of silent.
constexpr uint32_t WATCHDOG_S = 4;
uint32_t resetReason = 0;

// 1 MHz free-running 32-bit TIMER4 (the core and this program use no other TIMER4 user); HFXO is started in
// setup so the clock is crystal accurate.
void clockBegin() {
  NRF_CLOCK->EVENTS_HFCLKSTARTED = 0;
  NRF_CLOCK->TASKS_HFCLKSTART = 1;
  while (!NRF_CLOCK->EVENTS_HFCLKSTARTED) {
  }
  NRF_TIMER4->TASKS_STOP = 1;
  NRF_TIMER4->MODE = TIMER_MODE_MODE_Timer;
  NRF_TIMER4->BITMODE = TIMER_BITMODE_BITMODE_32Bit;
  NRF_TIMER4->PRESCALER = 4;  // 16 MHz / 2^4
  NRF_TIMER4->TASKS_CLEAR = 1;
  NRF_TIMER4->TASKS_START = 1;
}

// Capture channel 0 is used only from loop context, channel 1 only from the DIO1 interrupt.
uint32_t clock32() {
  NRF_TIMER4->TASKS_CAPTURE[0] = 1;
  return NRF_TIMER4->CC[0];
}

uint64_t now64 = 0;
uint32_t last32 = 0;

uint64_t clockNow() {
  const uint32_t now = clock32();
  now64 += static_cast<uint32_t>(now - last32);
  last32 = now;
  return now64;
}

// A 32-bit stamp taken at most one wrap (71 min) ago, extended to the 64-bit clock.
uint64_t extend(uint32_t stamp) {
  const uint64_t now = clockNow();
  return now - static_cast<uint32_t>(last32 - stamp);
}

// newlib-nano in the Adafruit core has no %llu (it prints "lu" and shifts the later arguments),
// so 64-bit times go into the JSON as decimal text with %s.
struct Dec {
  char text[21];
  explicit Dec(uint64_t value) {
    char reversed[20];
    size_t n = 0;
    do {
      reversed[n++] = static_cast<char>('0' + value % 10);
      value /= 10;
    } while (value);
    for (size_t i = 0; i < n; ++i) text[i] = reversed[n - 1 - i];
    text[n] = 0;
  }
};

void onDio1() {
  NRF_TIMER4->TASKS_CAPTURE[1] = 1;
  dio1At = NRF_TIMER4->CC[1];
  dio1 = true;
}

bool writeWithin(const char *data, size_t length, uint32_t startMs) {
  while (length && Serial) {
    const int room = Serial.availableForWrite();
    if (room > 0) {
      const size_t n = length < static_cast<size_t>(room) ? length : static_cast<size_t>(room);
      Serial.write(reinterpret_cast<const uint8_t *>(data), n);
      data += n;
      length -= n;
    } else if (millis() - startMs > EMIT_MS) {
      return false;
    } else {
      yield();
    }
  }
  return length == 0;
}

void emit(const char *text) {
  const uint32_t start = millis();
  if (!writeWithin(text, strlen(text), start) || !writeWithin("\r\n", 2, start)) ++emitCut;
  Serial.flush();
}

void watchdogBegin() {
  resetReason = NRF_POWER->RESETREAS;
  NRF_POWER->RESETREAS = resetReason;  // write-1-to-clear: the next start reports only its own cause
  NRF_WDT->CONFIG = (WDT_CONFIG_HALT_Pause << WDT_CONFIG_HALT_Pos) | (WDT_CONFIG_SLEEP_Run << WDT_CONFIG_SLEEP_Pos);
  NRF_WDT->CRV = WATCHDOG_S * 32768;
  NRF_WDT->RREN = WDT_RREN_RR0_Msk;
  NRF_WDT->TASKS_START = 1;  // after a soft reset it may still run with this configuration (it cannot stop)
}

void watchdogFeed() { NRF_WDT->RR[0] = WDT_RR_RR_Reload; }

void error(const char *what, int code) {
  snprintf(out, sizeof(out), "{\"err\":\"%s\",\"code\":%d}", what, code);
  emit(out);
}

void listen() {
  dio1 = false;
  if (!rxStream) {
    radio.standby();
    state = State::Idle;
    return;
  }
  const int code = radio.startReceive();
  if (code != RADIOLIB_ERR_NONE) {
    state = State::Idle;
    error("receive", code);
    return;
  }
  state = State::Receiving;
}

void info() {
  snprintf(out, sizeof(out),
           "{\"info\":\"%s\",\"board\":\"rak4631\",\"ready\":%s,\"begin\":%d,\"mhz\":869.525,\"bw_khz\":125,"
           "\"sf\":%u,\"cr\":%u,\"preamble\":%u,\"sync_word\":%u,\"crc\":true,\"explicit_header\":true,"
           "\"tcxo_v\":3.3,\"power_dbm\":%d,\"rx_stream\":%s,\"tx_count\":%lu,\"reset\":%lu,\"cut\":%lu,"
           "\"t_us\":%s}",
           VERSION, ready ? "true" : "false", beginCode, SPREADING_FACTOR, CODING_RATE, PREAMBLE_SYMBOLS,
           SYNC_WORD, powerDbm, rxStream ? "true" : "false", static_cast<unsigned long>(txCount),
           static_cast<unsigned long>(resetReason), static_cast<unsigned long>(emitCut), Dec(clockNow()).text);
  emit(out);
}

int nibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

void transmit(const char *hex) {
  if (!ready) return error("not_ready", -1);
  if (state == State::Transmitting) return error("busy", -1);
  const size_t digits = strlen(hex);
  if (digits < 2 || digits > 510 || digits % 2) return error("length", static_cast<int>(digits));
  uint8_t frame[255];
  const size_t length = digits / 2;
  for (size_t i = 0; i < length; ++i) {
    const int high = nibble(hex[2 * i]), low = nibble(hex[2 * i + 1]);
    if (high < 0 || low < 0) return error("hex", static_cast<int>(i));
    frame[i] = static_cast<uint8_t>((high << 4) | low);
  }
  radio.standby();
  dio1 = false;
  txToaUs = radio.getTimeOnAir(length);
  const int code = radio.startTransmit(frame, length);
  txStartUs = clockNow();
  if (code != RADIOLIB_ERR_NONE) {
    error("transmit", code);
    listen();
    return;
  }
  txLength = length;
  state = State::Transmitting;
}

void transmitted(uint64_t doneUs) {
  radio.finishTransmit();
  ++txCount;
  snprintf(out, sizeof(out),
           "{\"tx\":\"done\",\"n\":%lu,\"len\":%u,\"start_us\":%s,\"done_us\":%s,\"air_us\":%s,"
           "\"toa_us\":%lu,\"power_dbm\":%d}",
           static_cast<unsigned long>(txCount), static_cast<unsigned>(txLength), Dec(txStartUs).text,
           Dec(doneUs).text, Dec(doneUs - txStartUs).text, static_cast<unsigned long>(txToaUs), powerDbm);
  emit(out);
  listen();
}

void received(uint64_t doneUs) {
  uint8_t frame[256];
  const size_t length = radio.getPacketLength();
  if (length == 0 || length > 255) {
    error("rx_length", static_cast<int>(length));
    listen();
    return;
  }
  // RadioLib reads the buffer also when the CRC failed and then returns RADIOLIB_ERR_CRC_MISMATCH.
  const int code = radio.readData(frame, length);
  if (code != RADIOLIB_ERR_NONE && code != RADIOLIB_ERR_CRC_MISMATCH) {
    error("read", code);
    listen();
    return;
  }
  const float rssi = radio.getRSSI(), snr = radio.getSNR();
  static const char digits[] = "0123456789abcdef";
  char hex[511];
  for (size_t i = 0; i < length; ++i) {
    hex[2 * i] = digits[frame[i] >> 4];
    hex[2 * i + 1] = digits[frame[i] & 15];
  }
  hex[2 * length] = 0;
  snprintf(out, sizeof(out), "{\"rx\":\"%s\",\"len\":%u,\"rssi\":%.1f,\"snr\":%.2f,\"crc\":%s,\"t_us\":%s}", hex,
           static_cast<unsigned>(length), rssi, snr, code == RADIOLIB_ERR_NONE ? "true" : "false",
           Dec(doneUs).text);
  emit(out);
  listen();
}

void setPower(const char *argument) {
  char *end = nullptr;
  const long value = strtol(argument, &end, 10);
  if (end == argument || *end || value < POWER_MIN_DBM || value > POWER_MAX_DBM)
    return error("power_range", static_cast<int>(value));
  if (state == State::Transmitting) return error("busy", -1);
  const int code = radio.setOutputPower(static_cast<int8_t>(value));
  if (code != RADIOLIB_ERR_NONE) return error("power", code);
  powerDbm = static_cast<int8_t>(value);
  snprintf(out, sizeof(out), "{\"power_dbm\":%d}", powerDbm);
  emit(out);
}

void execute(char *command) {
  if (!strcmp(command, "info")) return info();
  if (!strncmp(command, "tx ", 3)) return transmit(command + 3);
  if (!strncmp(command, "power ", 6)) return setPower(command + 6);
  if (!strcmp(command, "rx on") || !strcmp(command, "rx off") || !strcmp(command, "rx")) {
    rxStream = strcmp(command, "rx off") != 0;
    if (ready && state != State::Transmitting) listen();
    snprintf(out, sizeof(out), "{\"rx_stream\":%s}", rxStream ? "true" : "false");
    return emit(out);
  }
  error("command", -1);
}

}  // namespace

void setup() {
  watchdogBegin();
  clockBegin();
  Serial.begin(115200);
  // Power of the RF switch in the RAK4630 module: held on, DIO2 selects TX/RX.
  pinMode(PIN_ANT_POWER, OUTPUT);
  digitalWrite(PIN_ANT_POWER, HIGH);
  beginCode = radio.begin(CARRIER_MHZ, BANDWIDTH_KHZ, SPREADING_FACTOR, CODING_RATE, SYNC_WORD, POWER_MIN_DBM,
                          PREAMBLE_SYMBOLS, TCXO_VOLTS, false);
  if (beginCode == RADIOLIB_ERR_NONE) beginCode = radio.setDio2AsRfSwitch(true);
  if (beginCode == RADIOLIB_ERR_NONE) beginCode = radio.setCRC(2);
  if (beginCode == RADIOLIB_ERR_NONE) beginCode = radio.setRxBoostedGainMode(true);
  ready = beginCode == RADIOLIB_ERR_NONE;
  if (ready) {
    radio.setDio1Action(onDio1);
    listen();
  }
}

void loop() {
  if (dio1) {
    noInterrupts();
    const uint32_t stamp = dio1At;
    dio1 = false;
    interrupts();
    const uint64_t at = extend(stamp);
    if (state == State::Transmitting) transmitted(at);
    else if (state == State::Receiving) received(at);
  }
  if (state == State::Transmitting && clockNow() - txStartUs > 2ull * txToaUs + 200000ull) {
    error("tx_timeout", static_cast<int>(txLength));
    radio.finishTransmit();
    listen();
  }
  while (Serial.available()) {
    const int c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (lineLength && !lineOverflow) {
        line[lineLength] = 0;
        execute(line);
      } else if (lineOverflow) {
        error("usb_length", -1);
      }
      lineLength = 0;
      lineOverflow = false;
    } else if (lineLength + 1 < sizeof(line)) {
      line[lineLength++] = static_cast<char>(c);
    } else {
      lineOverflow = true;
    }
  }
  clockNow();  // keeps the 64-bit extension ahead of a 32-bit wrap
  watchdogFeed();
  yield();
}
