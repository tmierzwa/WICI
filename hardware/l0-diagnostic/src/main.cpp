// SPDX-License-Identifier: MIT
// Diagnostic image for WICI L0 only. Boot never writes FRAM.
#include <Arduino.h>
#include <RadioLib.h>
#include <driver/gpio.h>
#include <esp_system.h>

#include "board.h"
#include "commands.h"
#include "diagnostic.h"
#include "fram.h"
#include "sharp.h"

namespace {
using namespace board;
using commands::Kind;
using commands::Mode;

constexpr uint32_t RADIO_SPI_HZ = 1000000;
constexpr uint32_t FRAM_SPI_HZ = 8000000;
constexpr uint32_t LCD_SPI_HZ = 1000000;
constexpr unsigned BUZZER_CHANNEL = 0;

SX1262 radio = new Module(RADIO_NSS, RADIO_DIO1, RADIO_NRST, RADIO_BUSY,
                         SPI, SPISettings(RADIO_SPI_HZ, MSBFIRST, SPI_MODE0));
fram::Memory memory(SPI, FRAM_CS, FRAM_SPI_HZ);
sharp::Display display(SPI, LCD_CS, LCD_EXTCOMIN, LCD_SPI_HZ);

volatile bool received = false;
bool radioOk = false;
bool framOk = false;
bool lcdOk = false;
bool buzzerOk = false;
Mode mode = Mode::Idle;
uint32_t bootId = 0;
uint32_t lastTx = 0;
uint32_t txInterval = 0;
uint32_t mixStarted = 0;
uint32_t mixTick = 0;
uint32_t mixCycles = 0;
uint32_t mixErrors = 0;
uint32_t mixMaxGap = 0;
uint32_t lcdFrames = 0;
const uint8_t inputs[] = {BTN_UP, BTN_DOWN, BTN_OK, BTN_BACK, SW_CISZA, BTN_PREP};
uint8_t lastInputs = 0;
commands::LineBuffer command;

void IRAM_ATTR receive() { received = true; }

// Each complete record is flushed: on the S3 USB-Serial/JTAG a short record could stay
// queued until the next host command (seen as 2.9 s USB lag in the R0 bench test).
void reply(const char* record) {
    Serial.println(record);
    Serial.flush();
}

void error(const char* where, int code) {
    Serial.printf("ERR %s %d\n", where, code);
    Serial.flush();
}

bool listen() {
    received = false;
    const int code = radio.startReceive();
    if (code != RADIOLIB_ERR_NONE) {
        radioOk = false;
        error("receive", code);
    }
    return code == RADIOLIB_ERR_NONE;
}

bool silence() { return digitalRead(SW_CISZA) == LOW; }

uint8_t panel() {
    uint8_t mask = 0;
    for (size_t i = 0; i < sizeof(inputs) / sizeof(inputs[0]); ++i)
        if (digitalRead(inputs[i]) == LOW) mask |= 1U << i;
    return mask;
}

void info() {
    Serial.printf("INFO %s %012llX %d %d %08lX 869.525 125 7 5 0 1.8\n",
                  diagnostic::VERSION, ESP.getEfuseMac(), radioOk && framOk && lcdOk && buzzerOk,
                  esp_reset_reason(), static_cast<unsigned long>(bootId));
    Serial.flush();
}

void status() {
    Serial.printf("STATUS radio=%d fram=%d ext=%d ext_counter=%lu inputs=%02X "
                  "silence=%d mixed=%d guard=%d cycles=%lu errors=%lu frames=%lu buzzer=%d\n",
                  radioOk, framOk, lcdOk, static_cast<unsigned long>(display.extcominCounter()),
                  panel(), silence(), mode == Mode::Mixed, mode == Mode::Guard,
                  static_cast<unsigned long>(mixCycles), static_cast<unsigned long>(mixErrors),
                  static_cast<unsigned long>(lcdFrames), buzzerOk);
    Serial.flush();
}

void printFramId(const fram::Id& id) {
    Serial.printf("FRAM_ID %s ", fram::partName(id.part));
    for (uint8_t byte : id.bytes) Serial.printf("%02X", byte);
    Serial.printf(" status=%02X\n", id.status);
    Serial.flush();
}

bool screen(unsigned pattern) {
    if (!lcdOk) {
        error("lcd_timer", -1);
        return false;
    }
    if (pattern == 0) {
        display.clear();
    } else {
        for (unsigned y = 0; y < sharp::HEIGHT; ++y) {
            for (unsigned x = 0; x < sharp::WIDTH; ++x) {
                const bool black = pattern == 1 ||
                    (pattern == 2 && ((x / 8 + y / 8) & 1)) ||
                    (pattern == 3 && (x % 10 == 0 || y % 10 == 0));
                display.setPixel(x, y, black);
            }
        }
        if (pattern == 4) {
            display.drawLine(0, "WICI L0 TEST", false);
            display.drawLine(1, "LCD FRAM LoRa", false);
            display.drawLine(2, "UP DOWN OK BACK", true);
        }
        display.refresh();
    }
    ++lcdFrames;
    return true;
}

void framTest(uint32_t seed, bool verifyOnly) {
    if (!framOk) {
        error("fram_unknown", -1);
        return;
    }
    uint8_t expected[diagnostic::BLOCK_SIZE];
    uint8_t actual[diagnostic::BLOCK_SIZE];
    for (unsigned pass = verifyOnly ? 4 : 0; pass < 5; ++pass) {
        if (!verifyOnly) {
            for (uint32_t address = 0; address < diagnostic::FRAM_SIZE; address += sizeof(expected)) {
                for (size_t i = 0; i < sizeof(expected); ++i)
                    expected[i] = diagnostic::pattern(address + i, pass, seed);
                if (!memory.write(address, expected, sizeof(expected))) {
                    error("fram_write", -1);
                    return;
                }
                delay(1);  // Yield to USB/RTOS/watchdog during the full-memory test.
            }
        }
        uint32_t errors = 0;
        uint32_t want = 0xFFFFFFFFUL;
        uint32_t got = 0xFFFFFFFFUL;
        for (uint32_t address = 0; address < diagnostic::FRAM_SIZE; address += sizeof(actual)) {
            if (!memory.read(address, actual, sizeof(actual))) {
                error("fram_read", -1);
                return;
            }
            for (size_t i = 0; i < sizeof(actual); ++i) {
                const uint8_t byte = diagnostic::pattern(address + i, pass, seed);
                errors += actual[i] != byte;
                want = diagnostic::crc(want, byte);
                got = diagnostic::crc(got, actual[i]);
            }
            delay(1);
        }
        Serial.printf("FRAM_PASS %u %lu %08lX %08lX\n", pass,
                      static_cast<unsigned long>(errors),
                      static_cast<unsigned long>(want ^ 0xFFFFFFFFUL),
                      static_cast<unsigned long>(got ^ 0xFFFFFFFFUL));
        Serial.flush();
        if (errors != 0 || want != got) {
            error("fram_compare", -1);
            return;
        }
    }
    Serial.printf("FRAM_DONE %08lX %s\n", static_cast<unsigned long>(seed),
                  verifyOnly ? "VERIFY" : "WRITE");
    Serial.flush();
}

void transmit(const char* payload) {
    if (!radioOk) {
        error("not_ready", -1);
        return;
    }
    if (silence()) {
        reply("BLOCKED SILENCE");
        return;
    }
    if (!diagnostic::validPayload(payload)) {
        error("payload", -1);
        return;
    }
    if (!diagnostic::cooldownElapsed(millis(), lastTx, txInterval)) {
        error("cooldown", -1);
        return;
    }
    String packet(payload);  // RadioLib's blocking API requires a mutable String.
    if (silence()) {  // Check again immediately before starting TX.
        reply("BLOCKED SILENCE");
        return;
    }
    lastTx = millis();
    txInterval = (radio.getTimeOnAir(packet.length()) * 13UL + 999UL) / 1000UL;
    radio.clearDio1Action();
    const int code = radio.transmit(packet);
    Serial.printf("TX %d %s\n", code, payload);
    Serial.flush();
    radio.setDio1Action(receive);
    if (code != RADIOLIB_ERR_NONE) error("transmit", code);
    listen();
}

void startGuard() {
    if (!framOk) {
        error("fram_unknown", -1);
        return;
    }
    // Keep the radio idle while FRAM owns a deliberately open SPI transaction.
    if (radioOk) {
        const int code = radio.standby();
        if (code != RADIOLIB_ERR_NONE) {
            error("standby", code);
            return;
        }
        received = false;
    }
    SPI.beginTransaction(SPISettings(FRAM_SPI_HZ, MSBFIRST, SPI_MODE0));
    digitalWrite(FRAM_CS, LOW);
    SPI.transfer(fram::OP_WREN);
    digitalWrite(FRAM_CS, HIGH);
    delayMicroseconds(1);
    digitalWrite(FRAM_CS, LOW);
    SPI.transfer(fram::OP_WRITE);
    SPI.transfer(0);
    SPI.transfer(0);
    SPI.transfer(0);
    mode = Mode::Guard;
    // Acknowledge only after CS is low; STOP or power loss ends this transaction.
    reply("GUARD_START ERASES_FRAM CS_LOW");
}

void stop() {
    const bool wasGuard = mode == Mode::Guard;
    if (wasGuard) {
        digitalWrite(FRAM_CS, HIGH);
        SPI.endTransaction();
        reply("GUARD_STOP");
    }
    mode = Mode::Idle;
    ledcWrite(BUZZER_CHANNEL, 0);
    if (wasGuard && radioOk) listen();
    reply("STOPPED");
}

void startMixed() {
    if (!radioOk || !framOk || !lcdOk || !buzzerOk) {
        error("mixed_not_ready", -1);
        return;
    }
    mode = Mode::Mixed;
    mixStarted = millis();
    mixTick = mixStarted - diagnostic::MIX_INTERVAL_MS;
    mixCycles = mixErrors = mixMaxGap = lcdFrames = 0;
    Serial.printf("MIX_START %lu\n", static_cast<unsigned long>(diagnostic::MIX_DURATION_MS));
    Serial.flush();
}

void execute(const char* line) {
    Serial.printf("CMD %s\n", line);  // Host separates command responses from stale boot output.
    Serial.flush();
    const commands::Command parsed = commands::parse(line);
    if (!commands::allowed(parsed.kind, mode)) {
        error(mode == Mode::Guard ? "guard_busy_use_STOP" : "mixed_busy_use_STOP", -1);
        return;
    }
    switch (parsed.kind) {
    case Kind::Info: info(); break;
    case Kind::Status: status(); break;
    case Kind::Stop: stop(); break;
    case Kind::Help:
        reply("COMMANDS INFO STATUS RDID LCD 0..4 LED 0/1 BUZZ 0/1 PAUSE 10000 "
              "FRAMTEST ERASE seedhex FRAMVERIFY seedhex GUARD ERASE MIXSTART ERASE STOP TX payload");
        break;
    case Kind::Tx: transmit(parsed.payload); break;
    case Kind::Rdid: printFramId(memory.identify()); break;
    case Kind::Led:
        digitalWrite(LED_ALARM, parsed.value ? HIGH : LOW);
        reply("LED_SET");
        break;
    case Kind::Buzzer:
        if (!buzzerOk) error("buzzer_timer", -1);
        else {
            ledcWrite(BUZZER_CHANNEL, parsed.value ? 128 : 0);
            reply("BUZZ_SET");
        }
        break;
    case Kind::Lcd:
        if (screen(parsed.value)) reply("LCD_DONE");
        break;
    case Kind::Pause:
        reply("PAUSE_START 10000");
        delay(10000);
        reply("PAUSE_DONE");
        break;
    case Kind::FramTest: framTest(parsed.value, false); break;
    case Kind::FramVerify: framTest(parsed.value, true); break;
    case Kind::Guard: startGuard(); break;
    case Kind::Mixed: startMixed(); break;
    case Kind::Unknown: error("command", -1); break;
    }
}

void pollRadio() {
    if (!radioOk || !received) return;
    received = false;
    String packet;
    const int code = radio.readData(packet);
    if (code == RADIOLIB_ERR_NONE) {
        if (packet.length() <= diagnostic::MAX_PACKET &&
            strlen(packet.c_str()) == packet.length() && diagnostic::validPayload(packet.c_str())) {
            Serial.printf("RX %.1f %.1f %s\n", radio.getRSSI(), radio.getSNR(), packet.c_str());
            Serial.flush();
        } else error("rx_payload", -1);
    } else error("read", code);
    listen();
}

void pollMixed() {
    const uint32_t now = millis();
    const uint32_t gap = now - mixTick;
    if (mode != Mode::Mixed || gap < diagnostic::MIX_INTERVAL_MS) return;
    mixTick = now;
    if (gap > mixMaxGap) mixMaxGap = gap;
    if (gap > diagnostic::MIX_MAX_GAP_MS) {
        ++mixErrors;
        error("mixed_gap", -1);
    }
    uint8_t out[diagnostic::BLOCK_SIZE];
    uint8_t in[diagnostic::BLOCK_SIZE];
    for (size_t i = 0; i < sizeof(out); ++i) out[i] = diagnostic::pattern(i, 4, mixCycles);
    const uint32_t address = diagnostic::FRAM_SIZE - sizeof(out);
    const bool ok = memory.write(address, out, sizeof(out)) &&
                    memory.read(address, in, sizeof(in)) && memcmp(out, in, sizeof(out)) == 0;
    if (!ok) {
        ++mixErrors;
        error("mixed_fram", -1);
    }
    if (!screen(2 + mixCycles % 2)) ++mixErrors;
    ++mixCycles;
    const uint32_t elapsed = millis() - mixStarted;
    if (elapsed >= diagnostic::MIX_DURATION_MS) {
        mode = Mode::Idle;
        Serial.printf("MIX_DONE %lu %lu %lu %lu %lu\n",
                      static_cast<unsigned long>(mixCycles), static_cast<unsigned long>(mixErrors),
                      static_cast<unsigned long>(lcdFrames), static_cast<unsigned long>(elapsed),
                      static_cast<unsigned long>(mixMaxGap));
        Serial.flush();
    }
}

void pollUsb() {
    while (Serial.available()) {
        const auto event = command.append(static_cast<char>(Serial.read()));
        if (event == commands::LineBuffer::Event::Complete) execute(command.text());
        else if (event == commands::LineBuffer::Event::Invalid) error("usb_line", -1);
    }
}

void output(uint8_t pin, uint8_t value) {
    digitalWrite(pin, value);
    pinMode(pin, OUTPUT);
}
}  // namespace

void setup() {
    // Selects and DISP are safe before attaching the shared bus.
    output(board::RADIO_NSS, HIGH);
    output(board::FRAM_CS, HIGH);
    output(board::LCD_CS, LOW);
    output(board::LCD_DISP, LOW);
    output(board::RADIO_NRST, LOW);
    output(board::RADIO_RXEN, LOW);
    output(board::LED_ALARM, LOW);
    output(board::BUZZER, LOW);
    for (uint8_t pin : inputs) pinMode(pin, INPUT_PULLUP);
    buzzerOk = ledcSetup(BUZZER_CHANNEL, 2048, 8) > 0;
    if (buzzerOk) ledcAttachPin(board::BUZZER, BUZZER_CHANNEL);
    ledcWrite(BUZZER_CHANNEL, 0);
    Serial.begin(115200);
    if (!buzzerOk) error("buzzer_timer", -1);
    bootId = esp_random();
    SPI.begin(board::SPI_SCK, board::SPI_MISO, board::SPI_MOSI, board::RADIO_NSS);
    gpio_set_drive_capability(static_cast<gpio_num_t>(board::SPI_SCK), GPIO_DRIVE_CAP_0);
    gpio_set_drive_capability(static_cast<gpio_num_t>(board::SPI_MOSI), GPIO_DRIVE_CAP_0);

    memory.begin();
    const auto id = memory.identify();
    // N1 fits either BOM part on the same footprint (CY15B104QN-50SXI or MB85RS4MTPF-G-BCERE1);
    // both take the same commands, 3-byte address and 8 MHz clock. Any other ID stops FRAM tests.
    framOk = id.part == fram::Part::CY15B104QN || id.part == fram::Part::MB85RS4MT;
    printFramId(id);
    if (!framOk) error("fram_id_unsupported", -1);
    lcdOk = display.begin();
    if (lcdOk) {
        digitalWrite(board::LCD_DISP, HIGH);
        screen(4);
    } else error("lcd_timer", -1);

    radio.setRfSwitchPins(board::RADIO_RXEN, RADIOLIB_NC);
    int code = radio.begin(869.525, 125.0, 7, 5, RADIOLIB_SX126X_SYNC_WORD_PRIVATE, 0, 8, 1.8);
    if (code == RADIOLIB_ERR_NONE) code = radio.setDio2AsRfSwitch(true);
    // Profile RX gain: catalogue -124 dBm (SF7/125 kHz) holds only in Rx Boosted gain.
    if (code == RADIOLIB_ERR_NONE) code = radio.setRxBoostedGainMode(true);
    if (code != RADIOLIB_ERR_NONE) error("radio_begin", code);
    else {
        radio.setDio1Action(receive);
        radioOk = listen();
    }
    lastInputs = panel();
    info();
    status();
}

void loop() {
    if (mode == Mode::Guard) {
        for (unsigned i = 0; i < 32; ++i) SPI.transfer(static_cast<uint8_t>(i ^ millis()));
    } else {
        pollRadio();
        pollMixed();
    }
    const uint8_t state = panel();
    if (state != lastInputs) {
        lastInputs = state;
        Serial.printf("INPUT %02X\n", state);
        Serial.flush();
    }
    pollUsb();
    delay(1);
}
