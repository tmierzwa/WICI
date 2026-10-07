// SPDX-License-Identifier: MIT
// WICI, stanowisko deweloperskie B: ESP32-S3-DevKitC-1 z X-NUCLEO-S2868A2 (ST S2-LP) na płytce
// nośnej N1. Zakres: uruchomienie N1 według kroków B3-B4 (hardware/dev-bench/uruchomienie.md):
// polecenia diagnostyczne panelu jak w bench-n1 (stan wejść, dioda alarmu, brzęczyk, VTEST),
// FRAM, ekran Sharp z EXTCOMIN z MCPWM i menu stacji na przyciskach panelu (bez magazynu
// w FRAM), identyfikacja S2-LP (PARTNUM, VERSION) oraz zapis rejestrów profilu P1 z weryfikacją
// odczytem. Bez łącza P1, dziennika, magazynu i protokołu USB laptop-stacja: te części są
// w main.cpp stanowiska A (następne kroki w firmware/README.md).
#if defined(WICI_BENCH_B)
#include <Arduino.h>
#include <SPI.h>
#include <driver/gpio.h>
#include <esp_system.h>

#include "board_bench_b.h"
#include "fram.h"
#include "s2lp.h"
#include "s2lp_p1_registers.h"
#include "sharp.h"
#include "ui.h"

#ifndef WICI_FW_VERSION
#define WICI_FW_VERSION "bench-b-dev"
#endif

namespace {

SPIClass bus(FSPI);  // SPI2 na pinach IO_MUX FSPI
s2lp::Radio radio(bus, board::RADIO_CS, board::RADIO_SDN, board::SPI_HZ);
fram::Memory memory(bus, board::FRAM_CS, board::SPI_HZ);
sharp::Display display(bus, board::DISPLAY_CS, board::DISPLAY_EXTCOMIN, board::DISPLAY_SPI_HZ);
ui::Model screenModel;
ui::Lines shown;
char stationName[12];  // WICI-xxxxxx z adresu MAC w eFuse
bool radioOk = false;
bool p1Ok = false;
bool framOk = false;
bool silence = false;
bool prep = false;
uint8_t spiDrive = board::SPI_DRIVE;
char line[256];
size_t lineLength = 0;

const uint8_t buttons[] = {board::BTN_UP, board::BTN_DOWN, board::BTN_OK, board::BTN_BACK};
const char* const buttonNames[] = {"up", "down", "ok", "back"};
const uint8_t radioGpios[] = {board::RADIO_GPIO0, board::RADIO_GPIO1, board::RADIO_GPIO2, board::RADIO_GPIO3};
bool buttonWas[4] = {};
uint32_t buttonPollMs = 0;
constexpr uint32_t BUTTON_POLL_MS = 10;
constexpr uint32_t SCREEN_POLL_MS = 200;
constexpr uint32_t CONFIRM_MS = 30000;  // PREP z portu: potwierdzenie przyciskiem OK

// Panel N1 jak w bench-n1: przełącznik CISZA na zmianę położenia po 50 ms, przycisk
// przygotowania przytrzymany 3 s, dioda alarmu w ciszy i na ekranie alarmu, brzęczyk 2048 Hz.
constexpr uint32_t SWITCH_SETTLE_MS = 50;
constexpr uint32_t PREP_HOLD_MS = 3000;
bool silenceSwitchLevel = false;
uint32_t silenceSwitchSince = 0;
bool silenceSwitchState = false;
uint32_t prepPressedSince = 0;
bool prepWas = false;
bool prepToggled = false;
bool alarmLedOn = false;
bool alarmLedWanted = false;

const char* boolName(bool value) { return value ? "true" : "false"; }
bool pressed(uint8_t pin) { return digitalRead(pin) == LOW; }
bool silenceSwitch() { return digitalRead(board::SW_SILENCE) == LOW; }
void beep(uint32_t ms) { tone(board::BUZZER, board::BUZZER_HZ, ms); }
void printError(const char* text) { Serial.printf("{\"error\":\"%s\"}\n", text); }

void alarmLed(bool on) {
    alarmLedOn = on;
    digitalWrite(board::LED_ALARM, on ? HIGH : LOW);  // dioda alarmu aktywna stanem wysokim
}

void setSpiDrive(uint8_t level) {
    spiDrive = level;
    const gpio_drive_cap_t cap = static_cast<gpio_drive_cap_t>(level);
    gpio_set_drive_capability(static_cast<gpio_num_t>(board::SPI_SCK), cap);
    gpio_set_drive_capability(static_cast<gpio_num_t>(board::SPI_MOSI), cap);
}

void beginPanel() {
    pinMode(board::LED_ALARM, OUTPUT);
    alarmLed(false);
    pinMode(board::BUZZER, OUTPUT);
    digitalWrite(board::BUZZER, LOW);
    pinMode(board::SW_SILENCE, INPUT);  // podciągnięcia na płytce
    pinMode(board::BTN_PREP, INPUT);
    for (uint8_t pin : buttons) pinMode(pin, INPUT);
    for (uint8_t pin : radioGpios) pinMode(pin, INPUT);
    analogReadResolution(12);
    analogSetPinAttenuation(board::VTEST, ADC_11db);
    silenceSwitchLevel = silenceSwitchState = silenceSwitch();
    silenceSwitchSince = millis();
    silence = silenceSwitchState;  // położenie przełącznika przy starcie
    prepWas = pressed(board::BTN_PREP);
    prepToggled = prepWas;  // przycisk trzymany przy starcie nie przełącza trybu
}

void pollPanel(uint32_t now) {
    const bool level = silenceSwitch();
    if (level != silenceSwitchLevel) {
        silenceSwitchLevel = level;
        silenceSwitchSince = now;
    } else if (level != silenceSwitchState && now - silenceSwitchSince >= SWITCH_SETTLE_MS) {
        silenceSwitchState = level;
        silence = level;  // cisza nie daje dźwięku (oprogramowanie.md, "Alarmy")
    }
    const bool held = pressed(board::BTN_PREP);
    if (held && !prepWas) prepPressedSince = now;
    if (!held) prepToggled = false;
    else if (!prepToggled && now - prepPressedSince >= PREP_HOLD_MS) {
        prepToggled = true;
        prep = !prep;
        beep(100);
    }
    prepWas = held;
    // Dioda: ekran alarmu albo cisza; zapis tylko przy zmianie, więc LED 5 obowiązuje do następnej.
    const bool led = screenModel.screen() == ui::Screen::ALARM || silence;
    if (led != alarmLedWanted) {
        alarmLedWanted = led;
        alarmLed(led);
    }
}

ui::Status screenStatus() {
    ui::Status s;
    s.prep = prep;
    s.silence = silence;
    s.radioOk = radioOk && p1Ok;
    s.contactKnown = false;
    s.contactS = millis() / 1000;
    s.mains12 = true;
    s.version = WICI_FW_VERSION;
    s.name = stationName;
    return s;
}

void updateScreen(bool force) {
    ui::Lines lines;
    screenModel.render(screenStatus(), lines);
    for (size_t i = 0; i < ui::LINES; ++i) {
        if (force || strcmp(lines.text[i], shown.text[i]) || lines.inverted[i] != shown.inverted[i]) {
            display.drawLine(static_cast<uint8_t>(i), lines.text[i], lines.inverted[i]);
        }
    }
    shown = lines;
    display.refresh();
}

const char* langName(ui::Lang lang) { return lang == ui::Lang::PL ? "PL" : lang == ui::Lang::UK ? "UK" : "EN"; }

void printScreen() {
    Serial.printf("{\"screen\":\"%s\",\"lang\":\"%s\",\"lines\":[", ui::screenName(screenModel.screen()), langName(screenModel.language()));
    for (size_t i = 0; i < ui::LINES; ++i) {
        Serial.print('"');
        for (const char* p = shown.text[i]; *p; ++p) {
            if (*p == '"' || *p == '\\') Serial.print('\\');
            Serial.print(*p);
        }
        Serial.printf("\"%s", i + 1 < ui::LINES ? "," : "");
    }
    Serial.printf("],\"refreshes\":%lu}\n", static_cast<unsigned long>(display.refreshes()));
}

void printDisplay() {
    Serial.printf("{\"extcomin\":\"MCPWM0\",\"counter\":%lu,\"level\":%s,\"software_vcom\":%s,\"refreshes\":%lu,\"cs\":%u,"
                  "\"extcomin_pin\":%u,\"disp_pin\":%u,\"spi_hz\":%lu}\n",
                  static_cast<unsigned long>(display.extcominCounter()), boolName(display.extcominLevel()),
                  boolName(display.softwareVcom()), static_cast<unsigned long>(display.refreshes()), board::DISPLAY_CS,
                  board::DISPLAY_EXTCOMIN, board::DISPLAY_DISP, static_cast<unsigned long>(display.spiHz()));
}

void pollButtons(uint32_t now) {
    if (now - buttonPollMs < BUTTON_POLL_MS) return;
    buttonPollMs = now;
    for (size_t i = 0; i < 4; ++i) {
        const bool is = pressed(buttons[i]);
        if (is && !buttonWas[i]) screenModel.down(static_cast<ui::Button>(i), now);
        else if (!is && buttonWas[i]) screenModel.up(static_cast<ui::Button>(i), now);
        buttonWas[i] = is;
    }
}

void syncButtons() {
    for (size_t i = 0; i < 4; ++i) buttonWas[i] = pressed(buttons[i]);
}

void printRadio() {
    const s2lp::Identity id = radio.identify();
    radioOk = id.s2lp;
    const s2lp::Status st = radio.status();
    Serial.printf("{\"radio\":\"S2LP\",\"partnumber\":\"0x%02X\",\"partversion\":\"0x%02X\",\"cut\":\"%s\",\"mc_state1\":\"0x%02X\","
                  "\"mc_state0\":\"0x%02X\",\"state\":\"%s\",\"xo_on\":%s,\"sdn\":%s,\"gpio\":[%d,%d,%d,%d],\"p1_ok\":%s,\"ok\":%s}\n",
                  id.partNumber, id.version, s2lp::versionName(id.version), st.mcState1, st.mcState0,
                  s2lp::stateName(st.state()), boolName(st.xoOn()), boolName(radio.isShutdown()),
                  digitalRead(board::RADIO_GPIO0), digitalRead(board::RADIO_GPIO1), digitalRead(board::RADIO_GPIO2),
                  digitalRead(board::RADIO_GPIO3), boolName(p1Ok), boolName(radioOk));
}

void printState() {
    const s2lp::Status st = radio.status();
    Serial.printf("{\"state\":\"%s\",\"mc_state1\":\"0x%02X\",\"mc_state0\":\"0x%02X\",\"xo_on\":%s,\"txbytes\":%u,\"rxbytes\":%u}\n",
                  s2lp::stateName(st.state()), st.mcState1, st.mcState0, boolName(st.xoOn()),
                  radio.readReg(s2lp::TX_FIFO_STATUS), radio.readReg(s2lp::RX_FIFO_STATUS));
}

void printVerify(const char* step, const s2lp::VerifyResult& result) {
    Serial.printf("{\"%s\":%s,\"checked\":%u,\"mismatches\":%u", step, boolName(result.mismatches == 0), result.checked,
                  result.mismatches);
    if (result.mismatches) {
        Serial.printf(",\"first\":\"%s\",\"reg\":\"0x%02X\",\"expected\":\"0x%02X\",\"actual\":\"0x%02X\"", result.firstName,
                      result.firstAddress, result.expected, result.actual);
    }
    Serial.printf(",\"state\":\"%s\"}\n", s2lp::stateName(radio.status().state()));
}

void configureP1() {
    const s2lp::VerifyResult result = radio.configure(p1s2::REGISTERS, p1s2::REGISTER_COUNT);
    p1Ok = result.mismatches == 0;
    printVerify("config", result);
}

// f_base = f_xo * SYNT / 2^19 / B / D (DS11896, eq. 7).
void printFrequency() {
    uint8_t synt[4];
    radio.readRegs(0x05, synt, 4);
    const uint32_t word = (static_cast<uint32_t>(synt[0] & 0x0F) << 24) | (static_cast<uint32_t>(synt[1]) << 16) |
                          (static_cast<uint32_t>(synt[2]) << 8) | synt[3];
    const uint8_t band = (synt[0] & 0x10) ? 8 : 4;
    const double hz = static_cast<double>(p1s2::F_XO_HZ) * word / 524288.0 / band / p1s2::REF_DIVIDER;
    Serial.printf("{\"synt\":\"0x%07lX\",\"band\":%u,\"hz\":%.1f,\"target_hz\":%lu,\"error_hz\":%.1f,\"step_hz\":%.2f}\n",
                  static_cast<unsigned long>(word), band, hz, static_cast<unsigned long>(p1s2::CARRIER_HZ),
                  hz - p1s2::CARRIER_HZ, static_cast<double>(p1s2::F_XO_HZ) / 524288.0 / band / p1s2::REF_DIVIDER);
}

void printFram() {
    const fram::Id id = memory.identify();
    framOk = id.mb85rs4m;
    Serial.printf("{\"fram\":\"MB85RS4MT\",\"id\":\"%02X%02X%02X%02X\",\"status\":\"0x%02X\",\"fujitsu\":%s,\"ok\":%s}\n",
                  id.bytes[0], id.bytes[1], id.bytes[2], id.bytes[3], id.status, boolName(id.fujitsu), boolName(framOk));
}

void printInfo() {
    // Pola jak w INFO ze specyfikacji radia (wariant ST: radio S2LP, wariant Espressif: mcu ESP32-S3);
    // liczniki łącza zerowe, bo obraz nie ma jeszcze łącza P1.
    Serial.printf("{\"contract\":2,\"profile\":\"P1\",\"radio\":\"S2LP\",\"mcu\":\"ESP32-S3\",\"fw\":\"%s\",\"src\":\"USB\",\"mv\":0,"
                  "\"tx_wait_ms\":0,\"rx_ok\":0,\"rx_bad\":0,\"tx_drop\":0,\"restarts\":0,\"bench\":\"B\",\"board\":\"%s\","
                  "\"prep\":%s,\"silence\":%s,\"radio_ok\":%s,\"p1_ok\":%s,\"fram_ok\":%s,\"carrier_hz\":%lu,\"symbol_rate\":%u,"
                  "\"deviation_hz\":%u,\"rx_filter_hz\":%u,\"tx_power_dbm\":%d,\"boot_s\":%lu,\"screen\":\"%s\",\"lang\":\"%s\","
                  "\"name\":\"%s\",\"reset_reason\":%d,\"spi_hz\":%lu,\"spi_drive\":%u,\"flash_mb\":%lu,\"psram_kb\":%lu}\n",
                  WICI_FW_VERSION, board::NAME, boolName(prep), boolName(silence), boolName(radioOk), boolName(p1Ok),
                  boolName(framOk), static_cast<unsigned long>(p1s2::CARRIER_HZ), p1s2::SYMBOL_RATE, p1s2::DEVIATION_HZ,
                  p1s2::RX_FILTER_HZ, p1s2::TX_POWER_DBM, static_cast<unsigned long>(millis() / 1000),
                  ui::screenName(screenModel.screen()), langName(screenModel.language()), stationName,
                  static_cast<int>(esp_reset_reason()), static_cast<unsigned long>(board::SPI_HZ), spiDrive,
                  static_cast<unsigned long>(ESP.getFlashChipSize() >> 20), static_cast<unsigned long>(ESP.getPsramSize() >> 10));
}

void printButtons() {
    Serial.print("{\"buttons\":{");
    for (size_t i = 0; i < 4; ++i) {
        Serial.printf("\"%s\":%s%s", buttonNames[i], boolName(pressed(buttons[i])), i < 3 ? "," : "");
    }
    // Stan linii panelu N1 (krok B3 = A3): true = zwarte do masy.
    Serial.printf("},\"silence_switch\":%s,\"prep_button\":%s,\"silence\":%s,\"prep\":%s,\"alarm_led\":%s}\n",
                  boolName(silenceSwitch()), boolName(pressed(board::BTN_PREP)), boolName(silence), boolName(prep),
                  boolName(alarmLedOn));
}

// VTEST: średnia z 16 odczytów ADC1_CH4 w mV (analogReadMilliVolts: tłumienie 11 dB, kalibracja eFuse).
void printVtest() {
    uint32_t sum = 0;
    for (int i = 0; i < 16; ++i) sum += analogReadMilliVolts(board::VTEST);
    const uint32_t pinMv = sum / 16;
    Serial.printf("{\"vtest_mv\":%lu,\"pin_mv\":%lu,\"adc\":\"ADC1_CH%u\",\"divider\":%u}\n",
                  static_cast<unsigned long>(pinMv * board::VTEST_DIVIDER), static_cast<unsigned long>(pinMv),
                  board::VTEST_ADC_CHANNEL, board::VTEST_DIVIDER);
}

void printHelp() {
    Serial.println("{\"commands\":[\"HELP\",\"INFO\",\"RADIO\",\"RESET\",\"SDN <0|1>\",\"STATE\",\"REG <hex>\",\"CONFIG\",\"VERIFY\","
                   "\"FREQ\",\"FRAM\",\"BTN\",\"LED 5 <0|1>\",\"BUZZ [<ms>] [<hz>]\",\"VTEST\",\"SCREEN\",\"KEY <UP|DOWN|OK|BACK> [ms]\","
                   "\"DISPLAY [<hz>]\",\"VCOM <0|1>\",\"DRIVE [<0-3>]\",\"PREP <0|1>\",\"SILENCE <0|1>\",\"REBOOT\"]}");
}

// Polecenie PREP 1 z portu: jak na stanowisku A potwierdzenie przyciskiem OK w ciągu 30 s.
bool confirmByOk() {
    Serial.println("{\"confirm\":\"press OK within 30 s\"}");
    const uint32_t start = millis();
    while (millis() - start < CONFIRM_MS) {
        if (pressed(board::BTN_OK)) return true;
        delay(10);
    }
    return false;
}

size_t splitArgs(char* text, char* words[], size_t max) {
    size_t n = 0;
    for (char* word = strtok(text, " "); word && n < max; word = strtok(nullptr, " ")) words[n++] = word;
    return n;
}

void handle(char* cmd) {
    for (char* p = cmd; *p; ++p) *p = toupper(*p);
    char* arg = strchr(cmd, ' ');
    if (arg) *arg++ = '\0';
    char* words[4];
    const size_t n = arg ? splitArgs(arg, words, 4) : 0;
    if (!strcmp(cmd, "INFO")) printInfo();
    else if (!strcmp(cmd, "RADIO")) printRadio();
    else if (!strcmp(cmd, "RESET")) {
        // SDN na 1 ms, potem SRES: rejestry wracają do wartości domyślnych, p1_ok = false.
        radio.reset();
        p1Ok = false;
        printRadio();
    } else if (!strcmp(cmd, "SDN") && n == 1) {
        radio.shutdown(atoi(words[0]) != 0);  // wyłączenie kasuje rejestry
        p1Ok = false;
        Serial.printf("{\"sdn\":%s}\n", boolName(radio.isShutdown()));
    } else if (!strcmp(cmd, "STATE")) printState();
    else if (!strcmp(cmd, "REG") && n == 1) {
        const uint8_t address = static_cast<uint8_t>(strtoul(words[0], nullptr, 16));
        const uint8_t value = radio.readReg(address);
        const s2lp::Status st = radio.lastStatus();
        Serial.printf("{\"reg\":\"0x%02X\",\"value\":\"0x%02X\",\"mc_state1\":\"0x%02X\",\"mc_state0\":\"0x%02X\"}\n", address, value,
                      st.mcState1, st.mcState0);
    } else if (!strcmp(cmd, "CONFIG")) configureP1();
    else if (!strcmp(cmd, "VERIFY")) printVerify("verify", radio.verify(p1s2::REGISTERS, p1s2::REGISTER_COUNT));
    else if (!strcmp(cmd, "FREQ")) printFrequency();
    else if (!strcmp(cmd, "FRAM")) printFram();
    else if (!strcmp(cmd, "BTN")) printButtons();
    else if (!strcmp(cmd, "LED") && n == 2 && atoi(words[0]) == 5) {
        alarmLed(atoi(words[1]) != 0);  // obowiązuje do następnej zmiany ciszy albo ekranu alarmu
        Serial.printf("{\"led\":5,\"on\":%s}\n", boolName(alarmLedOn));
    } else if (!strcmp(cmd, "BUZZ") && n <= 2) {
        const uint32_t ms = n >= 1 ? strtoul(words[0], nullptr, 10) : 500;
        const uint32_t hz = n == 2 ? strtoul(words[1], nullptr, 10) : board::BUZZER_HZ;
        if (ms > 5000 || hz < 100 || hz > 10000) { printError("BUZZ [<0..5000 ms>] [<100..10000 Hz>]"); return; }
        if (ms) tone(board::BUZZER, hz, ms);
        else noTone(board::BUZZER);
        Serial.printf("{\"buzz_ms\":%lu,\"hz\":%lu}\n", static_cast<unsigned long>(ms), static_cast<unsigned long>(hz));
    } else if (!strcmp(cmd, "VTEST")) printVtest();
    else if (!strcmp(cmd, "SCREEN")) printScreen();
    else if (!strcmp(cmd, "KEY") && (n == 1 || n == 2)) {
        const char* const names[] = {"UP", "DOWN", "OK", "BACK"};
        size_t index = 0;
        while (index < 4 && strcmp(words[0], names[index])) ++index;
        if (index == 4) { printError("KEY <UP|DOWN|OK|BACK> [ms]"); return; }
        const uint32_t now = millis();
        const uint32_t held = n == 2 ? static_cast<uint32_t>(atoi(words[1])) : 0;
        screenModel.down(static_cast<ui::Button>(index), now - held);
        if (held) screenModel.tick(now);
        screenModel.up(static_cast<ui::Button>(index), now);
        updateScreen(false);
        printScreen();
    } else if (!strcmp(cmd, "DISPLAY") && n == 1) {
        // Zegar SPI ekranu do prób z analizatorem na J11; do restartu. Odpowiedź po pełnym przerysowaniu.
        const uint32_t hz = strtoul(words[0], nullptr, 10);
        if (hz < 125000 || hz > sharp::SPI_HZ) { printError("DISPLAY <125000..2000000>"); return; }
        display.spiHz(hz);
        updateScreen(true);
        printDisplay();
    } else if (!strcmp(cmd, "DISPLAY")) printDisplay();
    else if (!strcmp(cmd, "VCOM") && n == 1) {
        display.softwareVcom(atoi(words[0]) != 0);
        printDisplay();
    } else if (!strcmp(cmd, "DRIVE")) {
        // Napęd SCK i MOSI (gpio_drive_cap_t 0-3, około 5/10/20/40 mA) do prób zboczy na J11; do restartu.
        if (n == 1) {
            const int level = atoi(words[0]);
            if (level < 0 || level > 3) { printError("DRIVE <0-3>"); return; }
            setSpiDrive(static_cast<uint8_t>(level));
        }
        Serial.printf("{\"spi_drive\":%u,\"sck\":%u,\"mosi\":%u}\n", spiDrive, board::SPI_SCK, board::SPI_MOSI);
    } else if (!strcmp(cmd, "PREP") && n == 1) {
        const bool on = atoi(words[0]) != 0;
        if (on && !prep && !confirmByOk()) printError("PREP not confirmed by OK");
        else {
            prep = on;  // do następnego przytrzymania przycisku przygotowania
            Serial.printf("{\"prep\":%s}\n", boolName(prep));
        }
    } else if (!strcmp(cmd, "SILENCE") && n == 1) {
        silence = atoi(words[0]) != 0;  // do następnego przełączenia CISZA
        Serial.printf("{\"silence\":%s}\n", boolName(silence));
    } else if (!strcmp(cmd, "REBOOT")) {
        Serial.println("{\"reboot\":true}");
        Serial.flush();
        delay(20);
        ESP.restart();
    } else if (!strcmp(cmd, "HELP") || !*cmd) printHelp();
    else Serial.printf("{\"error\":\"unknown\",\"cmd\":\"%s\"}\n", cmd);
}

void pollSerial() {
    while (Serial.available()) {
        const char c = static_cast<char>(Serial.read());
        if (c == '\n' || c == '\r') {
            line[lineLength] = '\0';
            if (lineLength) { handle(line); syncButtons(); }
            lineLength = 0;
        } else if (lineLength < sizeof(line) - 1) {
            line[lineLength++] = c;
        }
    }
}

}  // namespace

void setup() {
    pinMode(board::DISPLAY_CS, OUTPUT);  // CS ekranu aktywny stanem wysokim: najpierw w stan niski
    digitalWrite(board::DISPLAY_CS, LOW);
    pinMode(board::DISPLAY_DISP, OUTPUT);  // ekran wyłączony do wyczyszczenia jego pamięci
    digitalWrite(board::DISPLAY_DISP, LOW);
    beginPanel();
    radio.begin();   // CSn wysoki, SDN niski
    memory.begin();  // CS FRAM wysoki
    bus.begin(board::SPI_SCK, board::SPI_MISO, board::SPI_MOSI, -1);
    setSpiDrive(board::SPI_DRIVE);
    Serial.begin(115200);
    const uint64_t mac = ESP.getEfuseMac();
    snprintf(stationName, sizeof(stationName), "WICI-%06lX", static_cast<unsigned long>((mac >> 24) & 0xFFFFFF));
    radio.reset();
    radioOk = radio.identify().s2lp;
    if (radioOk) p1Ok = radio.configure(p1s2::REGISTERS, p1s2::REGISTER_COUNT).mismatches == 0;
    framOk = memory.identify().mb85rs4m;
    display.begin();  // CLEAR czyści pamięć ekranu, potem DISP
    digitalWrite(board::DISPLAY_DISP, HIGH);
    screenModel.start(ui::Lang::PL);
    updateScreen(true);
    syncButtons();
}

void loop() {
    static bool reported = false;
    static uint32_t lastScreen = 0;
    const uint32_t now = millis();
    const bool usb = Serial;  // port otwarty przez hosta
    if (usb && !reported) {  // jednorazowy raport po otwarciu portu
        reported = true;
        printInfo();
        printRadio();
        if (radioOk) printVerify("verify", radio.verify(p1s2::REGISTERS, p1s2::REGISTER_COUNT));
        printFram();
    }
    if (!usb) reported = false;
    pollSerial();
    pollButtons(now);
    pollPanel(now);
    screenModel.tick(now);
    screenModel.takeChange();
    if (now - lastScreen >= SCREEN_POLL_MS) {
        lastScreen = now;
        updateScreen(false);
    }
    display.maintain(now);
    delay(1);
}

#endif
