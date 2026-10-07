// SPDX-License-Identifier: MIT
// WICI, stanowisko deweloperskie A: pierwsze kroki oprogramowania stacji na nRF52840-DK.
// Zakres: USB CDC z poleceniami tekstowymi, identyfikacja CC1120 i FRAM przez SPI,
// konfiguracja rejestrów profilu P1 z weryfikacją odczytu i kalibracją syntezera,
// polecenia pomiarowe TXCW, TXPKT, RXPER, FOFF w trybie przygotowania, dziennik
// w FRAM (dług ciszy, zegar czasu pracy z liczbą restartów, zdarzenia), odczyt
// częstotliwości i RSSI, łącze P1 (odbiór i składanie datagramów, nadawanie z CCA,
// odroczeniem i długiem ciszy), przyciski i diody płytki. Bez stosu Reticulum
// i ekranu (następne kroki).
#include <Arduino.h>
#include <Adafruit_TinyUSB.h>
#include <SPI.h>

#include "board_bench_a.h"
#include "cc1120.h"
#include "fram.h"
#include "journal.h"
#include "measure.h"
#include "p1_registers.h"
#include "p1frame.h"

#ifndef WICI_FW_VERSION
#define WICI_FW_VERSION "bench-a-dev"
#endif

namespace {

cc1120::Radio radio(SPI, board::RADIO_CS, board::RADIO_RESET, board::SPI_HZ);
fram::Memory memory(SPI, board::FRAM_CS, board::SPI_HZ);
journal::Journal stationJournal(memory);
measure::Bench bench(radio, board::RADIO_GPIO2, board::BTN_OK, board::LED_HEARTBEAT);

bool radioOk = false;
bool framOk = false;
bool journalOk = false;
bool p1Ok = false;        // tablica P1 zapisana, zweryfikowana i syntezer skalibrowany
uint32_t restarts = 0;    // z dziennika zegara w FRAM, +1 przy każdym starcie
uint32_t uptimeBaseS = 0; // czas pracy z dziennika przy starcie; zegar monotoniczny między restartami
uint32_t journalResets = 0;  // brak poprawnego rekordu długu przy starcie
constexpr uint32_t CLOCK_WRITE_MS = 60000;  // zapis zegara co 60 s (oprogramowanie.md, "Czas")
char line[1400];  // P1TX przyjmuje do 600 B datagramu zapisanego szesnastkowo
size_t lineLength = 0;

const uint8_t buttons[] = {board::BTN_UP, board::BTN_DOWN, board::BTN_OK, board::BTN_BACK};
const char* const buttonNames[] = {"up", "down", "ok", "back"};
const uint8_t leds[] = {board::LED_HEARTBEAT, board::LED_RADIO, board::LED_FRAM, board::LED_USB};

void ledWrite(uint8_t pin, bool on) { digitalWrite(pin, on ? LOW : HIGH); }  // diody DK aktywne stanem niskim

bool pressed(uint8_t pin) { return digitalRead(pin) == LOW; }

const char* boolName(bool value) { return value ? "true" : "false"; }

uint32_t uptimeS() { return uptimeBaseS + millis() / 1000; }

void printError(const char* text) { Serial.printf("{\"error\":\"%s\"}\n", text); }

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

// Zapis tablicy P1, weryfikacja odczytem, ręczna kalibracja i ponowny zapis FOFF; ustala p1Ok.
cc1120::VerifyResult configureP1(bool& calibrated) {
    bench.stop();
    const cc1120::VerifyResult result = radio.configure(p1::REGISTERS, p1::REGISTER_COUNT);
    calibrated = result.mismatches == 0 && radio.calibrate();
    bench.applyOffset();
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
                  cc1120::marcStateName(marc), marc, radio.lastStatus(), radio.rxBytes(), radio.txBytes());
}

void printFram() {
    const fram::Id id = memory.identify();
    framOk = id.mb85rs4m;
    ledWrite(board::LED_FRAM, framOk);
    Serial.printf("{\"fram\":\"MB85RS4MT\",\"id\":\"%02X%02X%02X%02X\",\"status\":\"0x%02X\",\"fujitsu\":%s,\"ok\":%s}\n",
                  id.bytes[0], id.bytes[1], id.bytes[2], id.bytes[3], id.status, boolName(id.fujitsu), boolName(framOk));
}

void printInfo() {
    // Pola jak w INFO ze specyfikacji radia; napięcie jest zerowe, bo stanowisko go nie mierzy.
    // uptime_s to zegar z dziennika FRAM (ciągły między restartami), boot_s czas od startu.
    const measure::LinkCounters& c = bench.link();
    Serial.printf("{\"contract\":2,\"profile\":\"P1\",\"radio\":\"CC1120\",\"mcu\":\"nRF52840\",\"fw\":\"%s\","
                  "\"src\":\"USB\",\"mv\":0,\"tx_wait_ms\":%lu,\"rx_ok\":%lu,\"rx_bad\":%lu,\"tx_drop\":%lu,\"restarts\":%lu,"
                  "\"bench\":\"A\",\"prep\":%s,\"silence\":%s,\"radio_ok\":%s,\"p1_ok\":%s,\"fram_ok\":%s,\"journal_ok\":%s,"
                  "\"journal_resets\":%lu,\"carrier_hz\":%lu,\"symbol_rate\":%u,\"deviation_hz\":%u,\"rx_filter_hz\":%u,"
                  "\"tx_power_dbm\":%d,\"uptime_s\":%lu,\"boot_s\":%lu}\n",
                  WICI_FW_VERSION, static_cast<unsigned long>(bench.debtRemainingMs()), static_cast<unsigned long>(c.rxOk),
                  static_cast<unsigned long>(c.rxBad), static_cast<unsigned long>(c.txDrop),
                  static_cast<unsigned long>(restarts), boolName(bench.prep),
                  boolName(bench.silence), boolName(radioOk), boolName(p1Ok), boolName(framOk), boolName(journalOk),
                  static_cast<unsigned long>(journalResets), static_cast<unsigned long>(p1::CARRIER_HZ), p1::SYMBOL_RATE,
                  p1::DEVIATION_HZ, p1::RX_FILTER_HZ, p1::TX_POWER_DBM, static_cast<unsigned long>(uptimeS()),
                  static_cast<unsigned long>(millis() / 1000));
}

void printJournal() {
    const journal::SmallRecord& d = stationJournal.debt();
    const journal::SmallRecord& k = stationJournal.clock();
    Serial.printf("{\"journal_ok\":%s,\"debt_seq\":%lu,\"debt_ms\":%lu,\"debt_written_at_s\":%lu,\"debt_records\":%lu,"
                  "\"tx_wait_ms\":%lu,\"clock_seq\":%lu,\"uptime_s\":%lu,\"restarts\":%lu,\"event_seq\":%lu,"
                  "\"max_debt_ms\":%lu,\"journal_resets\":%lu}\n",
                  boolName(journalOk), static_cast<unsigned long>(d.seq), static_cast<unsigned long>(d.a),
                  static_cast<unsigned long>(d.b), static_cast<unsigned long>(stationJournal.debtValid()),
                  static_cast<unsigned long>(bench.debtRemainingMs()), static_cast<unsigned long>(k.seq),
                  static_cast<unsigned long>(uptimeS()), static_cast<unsigned long>(restarts),
                  static_cast<unsigned long>(stationJournal.eventSeq()), static_cast<unsigned long>(p1::MAX_DEBT_MS),
                  static_cast<unsigned long>(journalResets));
}

// Start dziennika: zegar i restarty, dług do odczekania albo nowy dziennik z największym długiem.
void beginJournal() {
    journalOk = framOk && stationJournal.begin();
    if (!journalOk) {
        restarts = 0;
        return;
    }
    uptimeBaseS = stationJournal.clock().a;
    restarts = stationJournal.clock().b + 1;
    stationJournal.writeClock(uptimeS(), restarts);
    bench.attach(&stationJournal, uptimeS);
    uint32_t debtMs = stationJournal.debt().a;
    if (stationJournal.debtFresh()) {
        // radio.md, "Dostęp do kanału": bez poprawnego rekordu odczekać największy możliwy dług,
        // założyć nowy dziennik i zliczyć zdarzenie w diagnostyce.
        debtMs = p1::MAX_DEBT_MS;
        journalResets = 1;
        stationJournal.writeDebt(debtMs, uptimeS());
        bench.log("debt journal missing: new journal, max debt");
    }
    bench.restoreDebt(debtMs);
    char text[48];
    snprintf(text, sizeof(text), "start %lu, debt %lu ms", static_cast<unsigned long>(restarts), static_cast<unsigned long>(debtMs));
    bench.log(text);
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
                   "\"PREP <0|1>\",\"SILENCE <0|1>\",\"TXCW <s> [CONDUCTED]\",\"TXPKT <n> <len> [<ms>] [CONDUCTED]\","
                   "\"RX [<len>]\",\"RXPER\",\"FOFF [<hz>]\",\"P1RX\",\"P1TX <hex>\",\"P1\",\"STOP\",\"LOG [<n>]\",\"JOURNAL\",\"BENCH\",\"IDLE\",\"RSSI\",\"STATE\","
                   "\"REG <hex>\",\"FRAM\",\"BTN\",\"LED <1-4> <0|1>\"]}");
}

// Argumenty po poleceniu: do czterech słów; zwraca liczbę słów.
size_t splitArgs(char* text, char* words[], size_t max) {
    size_t n = 0;
    for (char* word = strtok(text, " "); word && n < max; word = strtok(nullptr, " ")) words[n++] = word;
    return n;
}

bool lastIsConducted(char* words[], size_t& n) {
    if (n && !strcmp(words[n - 1], "CONDUCTED")) { --n; return true; }
    return false;
}

void handle(char* cmd) {
    for (char* p = cmd; *p; ++p) *p = toupper(*p);
    char* arg = strchr(cmd, ' ');
    if (arg) *arg++ = '\0';
    char* words[4];
    size_t n = arg ? splitArgs(arg, words, 4) : 0;
    if (!strcmp(cmd, "INFO")) printInfo();
    else if (!strcmp(cmd, "RADIO")) printRadio();
    else if (!strcmp(cmd, "RESET")) {
        bench.stop();
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
        bench.stop();
        const bool ok = radio.calibrate();
        Serial.printf("{\"cal\":%s,\"fs_vco2\":\"0x%02X\",\"fs_vco4\":\"0x%02X\",\"fs_chp\":\"0x%02X\",\"fs_cal2\":\"0x%02X\"}\n",
                      boolName(ok), radio.readReg(cc1120::FS_VCO2), radio.readReg(cc1120::FS_VCO4),
                      radio.readReg(cc1120::FS_CHP), radio.readReg(cc1120::FS_CAL2));
    } else if (!strcmp(cmd, "FREQ")) printFrequency();
    else if (!strcmp(cmd, "PREP") && n == 1) {
        // Na stacji tryb przygotowania włącza przycisk pod plombowaną pokrywą; na stanowisku
        // zastępuje go polecenie potwierdzone przyciskiem OK w ciągu 30 s.
        const bool on = atoi(words[0]) != 0;
        if (on && !bench.prep && !bench.confirm()) {
            bench.log("PREP not confirmed");
            printError("PREP not confirmed by OK");
        } else {
            if (!on) bench.stop();
            bench.prep = on;
            bench.log(on ? "preparation mode on" : "preparation mode off");
            Serial.printf("{\"prep\":%s}\n", boolName(bench.prep));
        }
    } else if (!strcmp(cmd, "SILENCE") && n == 1) {
        bench.silence = atoi(words[0]) != 0;  // na stacji: przełącznik CISZA
        bench.log(bench.silence ? "silence on" : "silence off");
        Serial.printf("{\"silence\":%s}\n", boolName(bench.silence));
    } else if (!strcmp(cmd, "TXCW")) {
        const bool conducted = lastIsConducted(words, n);
        if (n != 1) printError("TXCW <s> [CONDUCTED]");
        else {
            const char* error = bench.txcw(strtoul(words[0], nullptr, 10), conducted);
            if (error) printError(error);
        }
    } else if (!strcmp(cmd, "TXPKT")) {
        const bool conducted = lastIsConducted(words, n);
        if (n < 2 || n > 3) printError("TXPKT <n> <len> [<ms>] [CONDUCTED]");
        else {
            const char* error = bench.txpkt(static_cast<uint16_t>(strtoul(words[0], nullptr, 10)),
                                            static_cast<uint8_t>(strtoul(words[1], nullptr, 10)),
                                            n == 3 ? strtoul(words[2], nullptr, 10) : 0, conducted);
            if (error) printError(error);
        }
    } else if (!strcmp(cmd, "RX")) {
        const uint8_t length = n ? static_cast<uint8_t>(strtoul(words[0], nullptr, 10)) : p1::MAX_PACKET_BYTES;
        const char* error = bench.rxStart(length);
        if (error) printError(error);
        else Serial.printf("{\"rx\":true,\"len\":%u}\n", length);
        printState();
    } else if (!strcmp(cmd, "RXPER")) bench.rxper();
    else if (!strcmp(cmd, "P1RX")) {
        const char* error = bench.p1rxStart();
        if (error) printError(error);
        else Serial.println("{\"p1rx\":true}");
    } else if (!strcmp(cmd, "P1TX") && n == 1) {
        // Datagram szesnastkowo (1..600 B); identyfikator losuje stacja.
        static uint8_t data[p1frame::MAX_DATAGRAM];
        const size_t hexLength = strlen(words[0]);
        if (hexLength % 2 || hexLength < 2 || hexLength > 2 * p1frame::MAX_DATAGRAM) { printError("P1TX <hex of 1..600 B>"); return; }
        for (size_t i = 0; i < hexLength / 2; ++i) {
            char pair[3] = {words[0][2 * i], words[0][2 * i + 1], '\0'};
            char* end = nullptr;
            data[i] = static_cast<uint8_t>(strtoul(pair, &end, 16));
            if (*end) { printError("P1TX: not hex"); return; }
        }
        const char* error = bench.p1send(data, hexLength / 2);
        if (error) printError(error);
        else Serial.printf("{\"p1tx\":\"queued\",\"len\":%u,\"fragments\":%u}\n", static_cast<unsigned>(hexLength / 2),
                           p1frame::fragmentCount(hexLength / 2));
    } else if (!strcmp(cmd, "P1")) bench.printLink();
    else if (!strcmp(cmd, "FOFF")) {
        if (n == 1) {
            const char* error = bench.foff(strtol(words[0], nullptr, 10));
            if (error) { printError(error); return; }
        }
        bench.printFoff();
    } else if (!strcmp(cmd, "STOP")) {
        bench.stop();
        Serial.println("{\"stop\":true}");
        printState();
    } else if (!strcmp(cmd, "LOG")) {
        const uint32_t count = n ? strtoul(words[0], nullptr, 10) : 16;
        bench.printLog(count > 64 ? 64 : count);
    } else if (!strcmp(cmd, "JOURNAL")) printJournal();
    else if (!strcmp(cmd, "BENCH")) bench.printStatus();
    else if (!strcmp(cmd, "IDLE")) {
        bench.stop();
        Serial.printf("{\"idle\":%s}\n", boolName(radio.idle()));
        printState();
    } else if (!strcmp(cmd, "RSSI")) printRssi();
    else if (!strcmp(cmd, "STATE")) printState();
    else if (!strcmp(cmd, "REG") && n == 1) {
        const uint16_t address = static_cast<uint16_t>(strtoul(words[0], nullptr, 16));
        const uint8_t value = radio.readReg(address);
        Serial.printf("{\"reg\":\"0x%04X\",\"value\":\"0x%02X\",\"status\":\"0x%02X\"}\n", address, value, radio.lastStatus());
    } else if (!strcmp(cmd, "FRAM")) printFram();
    else if (!strcmp(cmd, "BTN")) printButtons();
    else if (!strcmp(cmd, "LED") && n == 2) {
        const int index = atoi(words[0]);
        if (index >= 1 && index <= 4) {
            ledWrite(leds[index - 1], atoi(words[1]) != 0);
            Serial.printf("{\"led\":%d,\"on\":%s}\n", index, boolName(atoi(words[1]) != 0));
        } else printError("LED <1-4> <0|1>");
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
    beginJournal();
    ledWrite(board::LED_FRAM, framOk && journalOk);  // LED3 świeci dopiero z działającym dziennikiem
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
        printJournal();
    }
    if (!usb) reported = false;
    static uint32_t lastClock = 0;
    if (journalOk && now - lastClock >= CLOCK_WRITE_MS) {
        lastClock = now;
        if (!stationJournal.writeClock(uptimeS(), restarts)) {
            journalOk = false;
            ledWrite(board::LED_FRAM, false);
        }
    }
    if (radioOk) bench.poll();
    pollSerial();
}
