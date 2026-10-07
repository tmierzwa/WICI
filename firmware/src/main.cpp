// SPDX-License-Identifier: MIT
// WICI, stanowisko deweloperskie A: pierwsze kroki oprogramowania stacji na nRF52840-DK.
// Zakres: USB CDC z poleceniami tekstowymi, identyfikacja CC1120 i FRAM przez SPI,
// konfiguracja rejestrów profilu P1 z weryfikacją odczytu i kalibracją syntezera,
// polecenia pomiarowe TXCW, TXPKT, RXPER, FOFF w trybie przygotowania, dziennik
// w FRAM (dług ciszy, zegar czasu pracy z liczbą restartów, zdarzenia), odczyt
// częstotliwości i RSSI, łącze P1 (odbiór i składanie datagramów, nadawanie z CCA,
// odroczeniem i długiem ciszy), ekran Sharp z EXTCOMIN z licznika RTC2 i przyciski
// płytki jako menu stacji (wybór języka, ekran główny, cisza, STAN), drugi interfejs CDC
// z protokołem USB laptop–stacja (sync, submit, event/ack, polecenia) nad kolejką, skrzynką
// i konfiguracją w FRAM, warstwa aplikacji nad P1 (kolejka, ponawianie, potwierdzenia) oraz
// ekrany stacji (kreator zgłoszenia, WIADOMOŚCI, TEST, STAN, USŁUGI, alarmy).
// Bez stosu Reticulum (następne kroki).
#include <Arduino.h>
#include <Adafruit_TinyUSB.h>
#include <SPI.h>

#include "board_bench_a.h"
#include "cc1120.h"
#include "console.h"
#include "fram.h"
#include "journal.h"
#include "measure.h"
#include "p1_registers.h"
#include "p1frame.h"
#include "sharp.h"
#include "station.h"
#include "store.h"
#include "ui.h"
#include "usbproto.h"

#ifndef WICI_FW_VERSION
#define WICI_FW_VERSION "bench-a-dev"
#endif

namespace {

cc1120::Radio radio(SPI, board::RADIO_CS, board::RADIO_RESET, board::SPI_HZ);
fram::Memory memory(SPI, board::FRAM_CS, board::SPI_HZ);
journal::Journal stationJournal(memory);
measure::Bench bench(radio, board::RADIO_GPIO2, board::BTN_OK, board::LED_HEARTBEAT);
sharp::Display display(SPI, board::DISPLAY_CS, board::DISPLAY_EXTCOMIN);
store::Store stationStore(memory);
Adafruit_USBD_CDC SerialData;    // drugi interfejs CDC: dane (protokół laptop–stacja); Serial = diagnostyka
bool storeOk = false;
bool dataWas = false;
ui::Model screenModel;
ui::Lines shown;                 // wiersze wysłane na ekran
bool buttonWas[4] = {};          // stan przycisków po ostatnim odpytaniu (zbocze = naciśnięcie)
uint32_t buttonPollMs = 0;
constexpr uint32_t BUTTON_POLL_MS = 10;   // odpytywanie przycisków (drgania styków)
constexpr uint32_t SCREEN_POLL_MS = 200;  // odświeżanie ekranu po zmianie treści
char stationName[12];            // WICI-xxxxxx z identyfikatora układu (FICR)

// Pamięć niezerowana przy starcie: po restarcie programowym albo przez watchdog zostaje język
// i ekran, więc stacja wraca tam, gdzie była; po włączeniu zasilania słowa są przypadkowe.
struct Retained {
    uint32_t magic;
    uint32_t check;
    uint8_t lang;
    uint8_t screen;
};
constexpr uint32_t RETAINED_MAGIC = 0x57494349;  // "WICI"
Retained retained __attribute__((section(".noinit")));

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
void updateScreen(bool force);

// Usługi stacji dla protokołu USB.
struct BenchHost : usbproto::Host {
    uint32_t uptimeS() override { return ::uptimeS(); }
    bool prep() override { return bench.prep; }
    bool silence() override { return bench.silence; }
    void setSilence(bool on) override;
    bool confirm() override { return bench.confirm(); }
    void randomBytes(uint8_t* out, size_t count) override { measure::randomBytes(out, count); }
    void log(const char* text) override { bench.log(text); }
    void emit(const char* line) override {
        // Odpowiedzi idą na interfejs danych; bez otwartego portu danych na diagnostykę (polecenie USB).
        if (SerialData) SerialData.println(line);
        else Serial.println(line);
    }
    void stationAddress(uint8_t out[store::HASH]) override;
    const char* stationName() override;
    const char* version() override { return WICI_FW_VERSION; }
    void configChanged() override;
    void queueChanged() override;
};
BenchHost host;
usbproto::Protocol protocol(stationStore, host);

// Usługi warstwy aplikacji: nadawanie przez łącze P1 stanowiska.
struct BenchServices : station::Services {
    uint32_t uptimeS() override { return ::uptimeS(); }
    bool silence() override { return bench.silence; }
    bool radioReady() override { return radioOk && p1Ok && bench.receiving(); }
    bool busy() override { return bench.busy(); }
    bool send(const uint8_t* data, size_t length) override { return bench.p1send(data, length) == nullptr; }
    void randomBytes(uint8_t* out, size_t count) override { measure::randomBytes(out, count); }
    void log(const char* text) override { bench.log(text); }
    bool notify(uint8_t kind, uint32_t ref, const char* fields) override { return protocol.event(kind, ref, fields, millis()); }
    void address(uint8_t out[store::HASH]) override { host.stationAddress(out); }
    void changed() override;
};
BenchServices services;
station::Station app(stationStore, services);
console::Console screenHost(stationStore, app, services, &stationJournal);
bool linkAuto = true;  // LINK 0 zatrzymuje nadawanie z kolejki (próby ręczne P1TX)

void BenchHost::configChanged() { screenHost.invalidate(); updateScreen(false); }
void BenchHost::queueChanged() { screenHost.invalidate(); updateScreen(false); }
void BenchServices::changed() { screenHost.invalidate(); updateScreen(false); }

void onDatagram(const uint8_t* data, size_t length, void*) { if (storeOk) app.received(data, length); }
void onTxDone(bool ok, void*) { app.txDone(ok); }

// Zdarzenie stanu radia do laptopa (cisza, tryb przygotowania).
void radioEvent() {
    char fields[96];
    snprintf(fields, sizeof(fields), "\"kind\":\"radio\",\"silence\":%s,\"prep\":%s", boolName(bench.silence), boolName(bench.prep));
    if (storeOk) protocol.event(store::NOTE_RADIO, 0, fields, millis());
}

void BenchHost::setSilence(bool on) {
    if (bench.silence == on) return;
    bench.silence = on;
    bench.log(on ? "silence on (usb)" : "silence off (usb)");
    radioEvent();
}

const char* langName(ui::Lang lang) { return lang == ui::Lang::PL ? "PL" : lang == ui::Lang::UK ? "UK" : "EN"; }

void retain() {
    retained.lang = static_cast<uint8_t>(screenModel.language());
    retained.screen = static_cast<uint8_t>(screenModel.screen());
    retained.magic = RETAINED_MAGIC;
    retained.check = ~RETAINED_MAGIC;
}

// Stan stacji dla ekranu: wartości ze stanowiska (brak pomiaru napięcia i kontaktu z odbiorcą).
ui::Status screenStatus() {
    ui::Status s;
    const measure::LinkCounters& c = bench.link();
    s.prep = bench.prep;
    s.silence = bench.silence;
    s.radioOk = radioOk && p1Ok;
    s.contactKnown = false;          // bez odbiorcy: dolne oszacowanie z czasu pracy
    s.contactS = uptimeS();
    s.mains12 = true;
    s.millivolts = 0;                // stanowisko nie mierzy napięcia (INFO: mv = 0)
    bool found = false;
    const uint32_t oldest = storeOk ? stationStore.queueOldestActiveS(found) : 0;
    s.queued = storeOk ? stationStore.queueLive() : 0;
    s.queueAgeS = found && uptimeS() > oldest ? uptimeS() - oldest : 0;
    s.newMessages = storeOk ? stationStore.inboxUnread() : 0;
    s.queued = storeOk ? stationStore.queueUnsent() : 0;  // najstarsze niewysłane: bez potwierdzenia łącza
    const uint32_t oldestUnsent = storeOk ? stationStore.queueOldestUnsentS(found) : 0;
    s.queueAgeS = found && uptimeS() > oldestUnsent ? uptimeS() - oldestUnsent : 0;
    s.rxOk = c.rxOk;
    s.rxBad = c.rxBad;
    s.txDatagrams = c.txDatagrams;
    s.txDrop = c.txDrop;
    s.deferrals = c.deferrals;
    s.debtMs = bench.debtRemainingMs();
    s.foffValid = radioOk && c.rxOk > 0;
    s.foffHz = static_cast<int32_t>(radio.frequencyOffsetEstimate() * (p1::F_XOSC_HZ / 262144.0 / p1::LO_DIVIDER));
    s.version = WICI_FW_VERSION;
    s.name = stationName;
    return s;
}

// Rysuje tylko zmienione wiersze i wysyła je na ekran.
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
    Serial.print("],\"inverted\":[");
    for (size_t i = 0; i < ui::LINES; ++i) Serial.printf("%s%s", boolName(shown.inverted[i]), i + 1 < ui::LINES ? "," : "");
    Serial.printf("],\"refreshes\":%lu}\n", static_cast<unsigned long>(display.refreshes()));
}

void printDisplay() {
    Serial.printf("{\"extcomin\":\"RTC2\",\"counter\":%lu,\"level\":%s,\"software_vcom\":%s,\"refreshes\":%lu,\"cs\":%u,\"extcomin_pin\":%u}\n",
                  static_cast<unsigned long>(display.extcominCounter()), boolName(display.extcominLevel()),
                  boolName(display.softwareVcom()), static_cast<unsigned long>(display.refreshes()), board::DISPLAY_CS,
                  board::DISPLAY_EXTCOMIN);
}

void BenchHost::stationAddress(uint8_t out[store::HASH]) {
    // Bez tożsamości Reticulum: 16 B z identyfikatora układu (FICR) jako adres stanowiska.
    memset(out, 0, store::HASH);
    const uint32_t id0 = NRF_FICR->DEVICEID[0];
    const uint32_t id1 = NRF_FICR->DEVICEID[1];
    memcpy(out, &id0, 4);
    memcpy(out + 4, &id1, 4);
    memcpy(out + 8, &id0, 4);
    memcpy(out + 12, &id1, 4);
}

const char* BenchHost::stationName() { return ::stationName; }

// Zapis języka i ekranu w FRAM i w pamięci niezerowanej po każdej zmianie.
void persistScreen() {
    if (!screenModel.takeChange()) return;
    retain();
    if (journalOk && !stationJournal.writeSettings(static_cast<uint32_t>(screenModel.language()) + 1,
                                                   static_cast<uint32_t>(screenModel.screen()))) {
        journalOk = false;
        ledWrite(board::LED_FRAM, false);
    }
}

// Po włączeniu zasilania: wybór języka; po restarcie programowym: język i ekran sprzed restartu.
void beginScreen() {
    const uint32_t id = NRF_FICR->DEVICEID[0];
    snprintf(stationName, sizeof(stationName), "WICI-%06lX", static_cast<unsigned long>(id & 0xFFFFFF));
    const journal::SmallRecord& saved = stationJournal.settings();
    const ui::Lang savedLang = journalOk && saved.a >= 1 && saved.a <= ui_texts::LANGS ? static_cast<ui::Lang>(saved.a - 1) : ui::Lang::PL;
    if (retained.magic == RETAINED_MAGIC && retained.check == ~RETAINED_MAGIC && retained.lang < ui_texts::LANGS) {
        screenModel.restore(static_cast<ui::Lang>(retained.lang), static_cast<ui::Screen>(retained.screen));
        bench.log("screen restored after restart");
    } else {
        screenModel.start(savedLang);
    }
    retain();
    updateScreen(true);
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
    for (size_t i = 0; i < 4; ++i) buttonWas[i] = pressed(buttons[i]);  // po poleceniu blokującym (CONDUCTED, PREP)
}

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
                  "\"tx_power_dbm\":%d,\"uptime_s\":%lu,\"boot_s\":%lu,\"screen\":\"%s\",\"lang\":\"%s\",\"name\":\"%s\","
                  "\"reset_reason\":\"0x%08lX\",\"store_ok\":%s,\"queued\":%u,\"inbox\":%u,\"pending\":%u,\"usb_data\":%s,"
                  "\"usb_in\":%lu,\"usb_out\":%lu,\"usb_rejected\":%lu,\"usb_boot\":\"%s\"}\n",
                  WICI_FW_VERSION, static_cast<unsigned long>(bench.debtRemainingMs()), static_cast<unsigned long>(c.rxOk),
                  static_cast<unsigned long>(c.rxBad), static_cast<unsigned long>(c.txDrop),
                  static_cast<unsigned long>(restarts), boolName(bench.prep),
                  boolName(bench.silence), boolName(radioOk), boolName(p1Ok), boolName(framOk), boolName(journalOk),
                  static_cast<unsigned long>(journalResets), static_cast<unsigned long>(p1::CARRIER_HZ), p1::SYMBOL_RATE,
                  p1::DEVIATION_HZ, p1::RX_FILTER_HZ, p1::TX_POWER_DBM, static_cast<unsigned long>(uptimeS()),
                  static_cast<unsigned long>(millis() / 1000), ui::screenName(screenModel.screen()), langName(screenModel.language()),
                  stationName, static_cast<unsigned long>(readResetReason()), boolName(storeOk),
                  static_cast<unsigned>(storeOk ? stationStore.queueLive() : 0), static_cast<unsigned>(storeOk ? stationStore.inboxCount() : 0),
                  static_cast<unsigned>(storeOk ? stationStore.notesPending() : 0), boolName(protocol.isConnected()),
                  static_cast<unsigned long>(protocol.stats().linesIn), static_cast<unsigned long>(protocol.stats().linesOut),
                  static_cast<unsigned long>(protocol.stats().rejected), protocol.bootId());
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
                   "\"REG <hex>\",\"FRAM\",\"BTN\",\"LED <1-4> <0|1>\",\"SCREEN\",\"KEY <UP|DOWN|OK|BACK> [ms]\",\"DISPLAY\","
                   "\"VCOM <0|1>\",\"REBOOT\",\"STORE\",\"USB <json>\",\"APP\",\"LINK <0|1>\"]}");
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

void printApp() {
    const station::Stats& s = app.stats();
    Serial.printf("{\"link\":%s,\"in_flight\":%lu,\"sent\":%lu,\"delivered\":%lu,\"failed\":%lu,\"received\":%lu,\"rejected\":%lu,"
                  "\"duplicates\":%lu,\"conflicts\":%lu,\"acks_sent\":%lu,\"confirmed\":%lu,\"live\":%u,\"unsent\":%u,\"next\":%lu,"
                  "\"test_paused\":%s,\"items\":%u}\n",
                  boolName(linkAuto), static_cast<unsigned long>(app.inFlightSeq()), static_cast<unsigned long>(s.sent),
                  static_cast<unsigned long>(s.delivered), static_cast<unsigned long>(s.failed), static_cast<unsigned long>(s.received),
                  static_cast<unsigned long>(s.rejected), static_cast<unsigned long>(s.duplicates), static_cast<unsigned long>(s.conflicts),
                  static_cast<unsigned long>(s.acksSent), static_cast<unsigned long>(s.confirmed),
                  static_cast<unsigned>(stationStore.queueLive()), static_cast<unsigned>(stationStore.queueUnsent()),
                  static_cast<unsigned long>(app.nextToSend(uptimeS())), boolName(app.testPaused()),
                  static_cast<unsigned>(screenHost.itemCount()));
}

void printStore() {
    const store::Config& c = stationStore.config();
    char osp[2 * store::HASH + 1];
    store::bytesToHex(c.osp[c.activeOsp ? 1 : 0], osp);
    Serial.printf("{\"store_ok\":%s,\"configured\":%s,\"config_seq\":%lu,\"role\":\"%s\",\"address\":\"%s\",\"osp\":\"%s\","
                  "\"phrases\":%u,\"stations\":%u,\"queued\":%u,\"inbox\":%u,\"unread\":%u,\"notes_pending\":%u,\"note_latest\":%lu,"
                  "\"usb_synced\":%s,\"usb_stored\":%lu,\"usb_overflow\":%lu,\"usb_resends\":%lu}\n",
                  boolName(storeOk), boolName(stationStore.configured()), static_cast<unsigned long>(c.seq),
                  c.role == store::OSP ? "osp" : "station", c.address, osp, c.phraseCount, c.stations,
                  static_cast<unsigned>(stationStore.queueLive()), static_cast<unsigned>(stationStore.inboxCount()),
                  static_cast<unsigned>(stationStore.inboxUnread()), static_cast<unsigned>(stationStore.notesPending()),
                  static_cast<unsigned long>(stationStore.noteLatest()), boolName(protocol.synced()),
                  static_cast<unsigned long>(protocol.stats().stored), static_cast<unsigned long>(protocol.stats().overflow),
                  static_cast<unsigned long>(protocol.stats().resends));
}

void handle(char* cmd) {
    // USB <wiersz JSON>: wiersz protokołu danych podany przez port diagnostyki (próby z jednym portem);
    // treść zostaje w oryginalnej wielkości liter.
    if (!strncasecmp(cmd, "USB ", 4)) {
        if (!storeOk) { printError("store not ready"); return; }
        protocol.handleLine(cmd + 4, millis());
        return;
    }
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
            if (bench.prep != on) {
                bench.prep = on;
                bench.log(on ? "preparation mode on" : "preparation mode off");
                radioEvent();
            }
            Serial.printf("{\"prep\":%s}\n", boolName(bench.prep));
        }
    } else if (!strcmp(cmd, "SILENCE") && n == 1) {
        const bool on = atoi(words[0]) != 0;  // na stacji: przełącznik CISZA
        if (on != bench.silence) {
            bench.silence = on;
            bench.log(bench.silence ? "silence on" : "silence off");
            radioEvent();
        }
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
    } else if (!strcmp(cmd, "SCREEN")) printScreen();
    else if (!strcmp(cmd, "KEY") && (n == 1 || n == 2)) {
        // Przycisk z portu USB (do prób bez dotykania płytki); drugi argument to czas przytrzymania [ms];
        // odpowiedź jak SCREEN po odświeżeniu.
        const char* const names[] = {"UP", "DOWN", "OK", "BACK"};
        size_t index = 0;
        while (index < 4 && strcmp(words[0], names[index])) ++index;
        if (index == 4) { printError("KEY <UP|DOWN|OK|BACK> [ms]"); return; }
        const uint32_t now = millis();
        const uint32_t held = n == 2 ? static_cast<uint32_t>(atoi(words[1])) : 0;
        screenModel.down(static_cast<ui::Button>(index), now - held);
        if (held) screenModel.tick(now);
        screenModel.up(static_cast<ui::Button>(index), now);
        persistScreen();
        updateScreen(false);
        printScreen();
    } else if (!strcmp(cmd, "DISPLAY")) printDisplay();
    else if (!strcmp(cmd, "STORE")) printStore();
    else if (!strcmp(cmd, "APP")) printApp();
    else if (!strcmp(cmd, "LINK") && n == 1) { linkAuto = atoi(words[0]) != 0; printApp(); }
    else if (!strcmp(cmd, "VCOM") && n == 1) {
        display.softwareVcom(atoi(words[0]) != 0);  // zapasowo, gdy zworka EXTMODE płytki jest niska
        printDisplay();
    } else if (!strcmp(cmd, "REBOOT")) {
        // Restart programowy: pamięć niezerowana zostaje, więc ekran i język wracają (jak po watchdogu).
        Serial.println("{\"reboot\":true}");
        Serial.flush();
        delay(20);
        NVIC_SystemReset();
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
    for (uint8_t pin : leds) { pinMode(pin, OUTPUT); ledWrite(pin, false); }
    for (uint8_t pin : buttons) pinMode(pin, INPUT_PULLUP);
    pinMode(board::RADIO_GPIO0, INPUT);
    pinMode(board::RADIO_GPIO2, INPUT);
    SPI.begin();
    radio.begin();
    memory.begin();
    // Dwa interfejsy CDC ACM z deskryptorami IAD (radio.md, "USB do laptopa"): diagnostyka i dane.
    Serial.setStringDescriptor("WICI diagnostyka");
    SerialData.setStringDescriptor("WICI dane");
    Serial.begin(115200);
    SerialData.begin(115200);
    if (TinyUSBDevice.mounted()) {  // host zdążył wyliczyć urządzenie z jednym interfejsem
        TinyUSBDevice.detach();
        delay(10);
        TinyUSBDevice.attach();
    }
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
    storeOk = framOk && stationStore.begin();
    protocol.begin();
    bench.onDatagram(onDatagram, nullptr);
    bench.onTxDone(onTxDone, nullptr);
    if (radioOk && p1Ok) bench.p1rxStart();  // łącze P1 w odbiorze od startu (radio niezależne od ekranu)
    display.begin();
    if (storeOk) screenModel.attach(&screenHost);  // bez magazynu: ekran bez kreatora i wiadomości
    beginScreen();
    syncButtons();
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
    if (storeOk && linkAuto && radioOk) app.poll(now);
    pollSerial();
    pollButtons(now);
    screenModel.tick(now);
    persistScreen();
    static uint32_t lastScreen = 0;
    if (now - lastScreen >= SCREEN_POLL_MS) {
        lastScreen = now;
        updateScreen(false);
    }
    display.maintain(now);
    // Interfejs danych: otwarcie portu wysyła sync, zamknięcie odrzuca niepełny wiersz.
    const bool dataOpen = SerialData;
    if (dataOpen && !dataWas) protocol.connected(now);
    else if (!dataOpen && dataWas) protocol.disconnected();
    dataWas = dataOpen;
    if (dataOpen && storeOk) {
        char chunk[64];
        while (SerialData.available()) {
            size_t n = 0;
            while (n < sizeof(chunk) && SerialData.available()) chunk[n++] = static_cast<char>(SerialData.read());
            protocol.feed(chunk, n, now);
        }
        protocol.poll(now);
    }
}
