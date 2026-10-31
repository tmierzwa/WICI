// SPDX-License-Identifier: MIT
// Seeed 102010611 only. RF_SW1 (GPIO38) probe for the RNode test; based on pair-0.4.
// Records the GPIO38 configuration left by a power-on reset and the Arduino core (what RNode
// 1.86 runs with), checks how the line behaves undriven, and compares reception with RF_SW1
// high, low and in that reset configuration, switching state at every beacon slot.
#include <Arduino.h>
#include <RadioLib.h>
#include <esp_rom_sys.h>
#include <esp_system.h>
#include <driver/gpio.h>
#include <soc/gpio_periph.h>
#include <soc/gpio_reg.h>
#include <soc/io_mux_reg.h>

constexpr uint8_t RF_SW1 = 38;  // Meshtastic seeed_xiao_s3 SX126X_RXEN; this probe checks it
constexpr gpio_num_t RF_SW1_GPIO = GPIO_NUM_38;
constexpr uint32_t RF_SW1_BIT = BIT(RF_SW1 - 32);  // GPIO32-48 live in the *1 registers
constexpr uint32_t BEACON_MS = 1000;
constexpr uint32_t WINDOW_MS = 1500;  // no beacon in this time: one miss for the state
constexpr uint32_t FLOAT_MS = 200;    // settling time of an undriven line before reading it

SX1262 radio = new Module(41, 39, 42, 40);
volatile bool received = false;
bool ready = false;
String command;

// GPIO38 as found at the start of setup(): IO_MUX, pad, output matrix, enable and level.
uint32_t resetMux, resetPad, resetOutSel;
bool resetOe, resetOut;
// Level with the internal pull-up, the pull-down, and undriven after being driven high or low.
int levelUp = -1, levelDown = -1, floatAfterHigh = -1, floatAfterLow = -1;

enum Role { IDLE, BEACON, RECEIVE } role = IDLE;
// R (reset configuration) follows both H and L, so a level left on an undriven line by the
// previous state shows up as a difference between RH and RL.
enum State { HIGH_STATE, RESET_AFTER_HIGH, LOW_STATE, RESET_AFTER_LOW };
const char *const STATE_NAMES[] = {"H", "RH", "L", "RL"};
State state = HIGH_STATE;
uint32_t nextBeacon = 0, windowStart = 0, beaconCount = 0;

void IRAM_ATTR onReceive() { received = true; }

volatile uint32_t *outSelReg() {
  return reinterpret_cast<volatile uint32_t *>(GPIO_FUNC0_OUT_SEL_CFG_REG + 4 * RF_SW1);
}

volatile uint32_t *padReg() { return reinterpret_cast<volatile uint32_t *>(GPIO_PIN0_REG + 4 * RF_SW1); }

void recordReset() {
  resetMux = REG_READ(GPIO_PIN_MUX_REG[RF_SW1]);
  resetPad = *padReg();
  resetOutSel = *outSelReg();
  resetOe = REG_READ(GPIO_ENABLE1_REG) & RF_SW1_BIT;
  resetOut = REG_READ(GPIO_OUT1_REG) & RF_SW1_BIT;
}

void restoreReset() {
  REG_WRITE(GPIO_ENABLE1_W1TC_REG, RF_SW1_BIT);
  *outSelReg() = resetOutSel;
  *padReg() = resetPad;
  REG_WRITE(GPIO_PIN_MUX_REG[RF_SW1], resetMux);
  REG_WRITE(resetOut ? GPIO_OUT1_W1TS_REG : GPIO_OUT1_W1TC_REG, RF_SW1_BIT);
  if (resetOe) REG_WRITE(GPIO_ENABLE1_W1TS_REG, RF_SW1_BIT);
}

int readWithPull(gpio_pull_mode_t pull) {
  gpio_set_direction(RF_SW1_GPIO, GPIO_MODE_INPUT);
  gpio_set_pull_mode(RF_SW1_GPIO, pull);
  delay(20);
  return gpio_get_level(RF_SW1_GPIO);
}

int readFloatingAfter(int level) {
  gpio_set_pull_mode(RF_SW1_GPIO, GPIO_FLOATING);
  gpio_set_direction(RF_SW1_GPIO, GPIO_MODE_OUTPUT);
  gpio_set_level(RF_SW1_GPIO, level);
  delay(10);
  gpio_set_direction(RF_SW1_GPIO, GPIO_MODE_INPUT);
  delay(FLOAT_MS);
  return gpio_get_level(RF_SW1_GPIO);
}

void pullTest() {
  gpio_reset_pin(RF_SW1_GPIO);  // GPIO function with input enabled
  levelUp = readWithPull(GPIO_PULLUP_ONLY);
  levelDown = readWithPull(GPIO_PULLDOWN_ONLY);
  floatAfterHigh = readFloatingAfter(1);
  floatAfterLow = readFloatingAfter(0);
  restoreReset();
}

void setState(State s) {
  state = s;
  if (s == RESET_AFTER_HIGH || s == RESET_AFTER_LOW) { restoreReset(); return; }
  pinMode(RF_SW1, OUTPUT);
  digitalWrite(RF_SW1, s == HIGH_STATE ? HIGH : LOW);
}

void error(const char *where, int code) {
  Serial.printf("ERR %s %d\n", where, code);
  Serial.flush();
}

void info() {
  uint32_t m = resetMux;
  Serial.printf("INFO rfsw-0.3 %012llX %d %d mux=%08lX mcu_sel=%lu ie=%d pu=%d pd=%d drv=%lu oe=%d "
                "out_sel=%08lX up=%d down=%d fh=%d fl=%d\n",
                ESP.getEfuseMac(), ready, esp_rom_get_reset_reason(0), static_cast<unsigned long>(m),
                static_cast<unsigned long>((m >> MCU_SEL_S) & MCU_SEL), (m & FUN_IE) != 0,
                (m & FUN_PU) != 0, (m & FUN_PD) != 0, static_cast<unsigned long>((m >> FUN_DRV_S) & 3),
                resetOe, static_cast<unsigned long>(resetOutSel), levelUp, levelDown, floatAfterHigh,
                floatAfterLow);
  Serial.flush();
}

void stop() {
  role = IDLE;
  radio.standby();
  restoreReset();
  Serial.println("STOP");
  Serial.flush();
}

void execute(const String &line) {
  if (line == "INFO") { info(); return; }
  if (line == "STOP") { stop(); return; }
  if (!ready) { error("not_ready", -1); return; }
  if (line == "BEACON") {
    // Transmitter: RF_SW1 low, DIO2 selects the transmit path.
    setState(LOW_STATE);
    radio.clearDio1Action();
    role = BEACON;
    beaconCount = 0;
    nextBeacon = millis();
    Serial.println("BEACON");
    Serial.flush();
    return;
  }
  if (line == "RECEIVE") {
    role = RECEIVE;
    setState(HIGH_STATE);
    radio.setDio1Action(onReceive);
    received = false;
    int code = radio.startReceive();
    if (code) { error("receive", code); role = IDLE; return; }
    windowStart = millis();
    Serial.println("RECEIVE");
    Serial.flush();
    return;
  }
  error("command", -1);
}

void nextState() { setState(static_cast<State>((state + 1) % 4)); }

void beacon() {
  if (static_cast<int32_t>(millis() - nextBeacon) < 0) return;
  nextBeacon += BEACON_MS;
  char packet[24];
  snprintf(packet, sizeof packet, "RFSW%lu", static_cast<unsigned long>(++beaconCount));
  int code = radio.transmit(packet);
  Serial.printf("TX %d %s\n", code, packet);
  Serial.flush();
}

void receive() {
  if (received) {
    received = false;
    String packet;
    int code = radio.readData(packet);
    const char *s = STATE_NAMES[state];
    if (code == RADIOLIB_ERR_NONE && packet.startsWith("RFSW") && packet.length() <= 16)
      Serial.printf("RX %s %.1f %.1f %s\n", s, radio.getRSSI(), radio.getSNR(), packet.c_str());
    else
      Serial.printf("BAD %s %d\n", s, code);  // -7: CRC error; 0: someone else's packet
    Serial.flush();
    // Switch between packets only, so that no packet is received across a change.
    nextState();
    windowStart = millis();  // resynchronise to the beacon just received
    code = radio.startReceive();
    if (code) error("receive", code);
  } else if (millis() - windowStart > WINDOW_MS) {
    Serial.printf("MISS %s\n", STATE_NAMES[state]);
    Serial.flush();
    nextState();
    // Stay on the beacon grid: the next window covers exactly the next beacon.
    windowStart += BEACON_MS;
  }
}

void setup() {
  recordReset();  // before anything touches GPIO38
  pullTest();
  Serial.begin(115200);
  SPI.begin(7, 8, 9, 41);
  // Profile of pair-0.4, without setRfSwitchPins: this program drives RF_SW1 itself.
  int code = radio.begin(869.525, 125.0, 7, 5, RADIOLIB_SX126X_SYNC_WORD_PRIVATE, 0, 8, 1.8);
  if (code) { error("begin", code); return; }
  code = radio.setDio2AsRfSwitch(true);
  if (code) { error("switch", code); return; }
  code = radio.setRxBoostedGainMode(true);
  if (code) { error("rx_gain", code); return; }
  radio.setDio1Action(onReceive);
  ready = true;
  info();
}

void loop() {
  if (role == BEACON) beacon();
  else if (role == RECEIVE) receive();
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { execute(command); command = ""; }
    else if (c != '\r') {
      command += c;
      if (command.length() > 32) { command = ""; error("usb_length", -1); }
    }
  }
  delay(1);
}
