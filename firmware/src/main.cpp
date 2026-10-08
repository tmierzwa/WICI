// SPDX-License-Identifier: MIT
// WICI, stanowiska deweloperskie A i B: oprogramowanie stacji ze stosem Reticulum (bez LXMF).
// Zakres: USB z dwoma interfejsami CDC (diagnostyka z poleceniami tekstowymi i dane z protokołem
// laptop–stacja: sync, submit, event/ack, polecenia nad kolejką, skrzynką i konfiguracją w FRAM),
// identyfikacja radia i FRAM przez SPI, konfiguracja rejestrów profilu P1 z weryfikacją odczytu,
// polecenia pomiarowe TXCW, TXPKT, RXPER, FOFF w trybie przygotowania, dziennik w FRAM (dług
// ciszy, zegar czasu pracy z liczbą restartów, zdarzenia), łącze P1 (odbiór i składanie
// datagramów, nadawanie z CCA, odroczeniem i długiem ciszy), stos Reticulum (port microReticulum,
// rns_node.h) z interfejsem P1 nad łączem, tożsamością i tablicami w FRAM, warstwa aplikacji nad
// stosem (kolejka, ponawianie, potwierdzenia transportowe), ekran Sharp z EXTCOMIN z licznika MCU
// i przyciski jako menu stacji
// (kreator zgłoszenia, WIADOMOŚCI, TEST, STAN, USŁUGI, alarmy), panel płytki N1 (przełącznik
// CISZA, przycisk przygotowania, dioda alarmu, brzęczyk, VTEST).
// Wykonania: bench-a (nRF52840-DK + CC1120EM na przewodach), bench-n1 (to samo na płytce N1),
// bench-b (ESP32-S3-DevKitC-1 + X-NUCLEO-S2868A2 z S2-LP na N1). Zależne od MCU części są
// w platform_*.cpp, zależne od układu radiowego w radio_console_*.cpp i *_link.cpp.
#include <Arduino.h>
#include <SPI.h>
#if defined(ARDUINO_ARCH_NRF52)
#include <Adafruit_TinyUSB.h>
#elif defined(ARDUINO_ARCH_ESP32)
#include <USB.h>
#endif

#include "board.h"
#include "console.h"
#include "fram.h"
#include "journal.h"
#include "measure.h"
#include "p1_registers.h"
#include "p1frame.h"
#include "platform.h"
#include "radio_console.h"
#include "rns_announce.h"
#include "rns_node.h"
#include "sharp.h"
#include "station.h"
#include "store.h"
#include "ui.h"
#include "usbproto.h"

#ifndef WICI_FW_VERSION
#define WICI_FW_VERSION "bench-a-dev"
#endif

namespace {

#if defined(WICI_BOARD_N1)
constexpr const char* BOARD_NAME = board::NAME;
#else
constexpr const char* BOARD_NAME = "wires";
#endif
#if defined(WICI_BENCH_B)
constexpr const char* BENCH = "B";
#else
constexpr const char* BENCH = "A";
#endif

fram::Memory memory(platform::bus(), board::FRAM_CS, board::SPI_HZ);
journal::Journal stationJournal(memory);
measure::Bench bench(radiocon::link(), board::BTN_OK, board::LED_HEARTBEAT);
#if defined(WICI_BOARD_N1)
sharp::Display display(platform::bus(), board::DISPLAY_CS, board::DISPLAY_EXTCOMIN, board::DISPLAY_SPI_HZ);
#else
sharp::Display display(platform::bus(), board::DISPLAY_CS, board::DISPLAY_EXTCOMIN);
#endif
store::Store stationStore(memory);
// Drugi interfejs CDC: dane (protokół laptop–stacja); Serial = diagnostyka.
#if defined(ARDUINO_ARCH_NRF52)
Adafruit_USBD_CDC SerialData;
#else
USBCDC SerialData(1);  // interfejs dopisany do deskryptora przed USB.begin() rdzenia
#endif
bool storeOk = false;
bool dataWas = false;
ui::Model screenModel;
ui::Lines shown;                 // wiersze wysłane na ekran
bool buttonWas[4] = {};          // stan przycisków po eliminacji drgań (zbocze = naciśnięcie)
bool buttonSample[4] = {};       // ostatnia próbka przycisków
uint32_t buttonPollMs = 0;
constexpr uint32_t BUTTON_POLL_MS = 10;   // odpytywanie przycisków (drgania styków)
constexpr uint32_t SCREEN_POLL_MS = 200;  // odświeżanie ekranu po zmianie treści
constexpr uint32_t APP_POLL_MS = 100;     // przegląd kolejki nadawczej
constexpr uint32_t WDT_TIMEOUT_S = 60;    // watchdog: dłużej niż potwierdzenie przyciskiem (30 s)
char stationName[12];            // WICI-xxxxxx ze skrótu tożsamości (bez stosu: z identyfikatora układu, platform::chipId)

// Pamięć niezerowana przy starcie: po restarcie programowym albo przez watchdog zostaje język
// i ekran, więc stacja wraca tam, gdzie była; po włączeniu zasilania słowa są przypadkowe.
struct Retained {
    uint32_t magic;
    uint32_t check;
    uint8_t lang;
    uint8_t screen;
};
constexpr uint32_t RETAINED_MAGIC = 0x57494349;  // "WICI"
PLATFORM_NOINIT Retained retained;

bool framOk = false;
bool journalOk = false;
uint32_t restarts = 0;    // z dziennika zegara w FRAM, +1 przy każdym starcie
uint32_t uptimeBaseS = 0; // czas pracy z dziennika przy starcie; zegar monotoniczny między restartami
uint32_t journalResets = 0;  // brak poprawnego rekordu długu przy starcie
constexpr uint32_t CLOCK_WRITE_MS = 60000;  // zapis zegara co 60 s (oprogramowanie.md, "Czas")
char line[1400];  // P1TX przyjmuje do 600 B datagramu zapisanego szesnastkowo
size_t lineLength = 0;

const uint8_t buttons[] = {board::BTN_UP, board::BTN_DOWN, board::BTN_OK, board::BTN_BACK};
const char* const buttonNames[] = {"up", "down", "ok", "back"};
const int16_t leds[] = {board::LED_HEARTBEAT, board::LED_RADIO, board::LED_FRAM, board::LED_USB};

// Diody DK aktywne stanem niskim; -1: płytka bez diody (stanowisko B).
void ledWrite(int16_t pin, bool on) {
    if (pin >= 0) digitalWrite(static_cast<uint8_t>(pin), on ? LOW : HIGH);
}

bool pressed(uint8_t pin) { return digitalRead(pin) == LOW; }

const char* boolName(bool value) { return value ? "true" : "false"; }

uint32_t uptimeS() { return uptimeBaseS + millis() / 1000; }
void updateScreen(bool force);
void setStationName();

// Usługi stacji dla protokołu USB.
struct BenchHost : usbproto::Host {
    uint32_t uptimeS() override { return ::uptimeS(); }
    bool prep() override { return bench.prep; }
    bool silence() override { return bench.silence; }
    void setSilence(bool on) override;
    bool silenceSwitch() override;
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
    bool eraseJournal() override { return !journalOk || stationJournal.eraseEvents(); }
    void destroyed() override;
    bool announce() override;
};
BenchHost host;
usbproto::Protocol protocol(stationStore, host);

// Łącze P1 stanowiska pod interfejsem P1 stosu: datagram z kolejki interfejsu idzie przez
// Bench (dług ciszy, CCA, odroczenia, fragmentacja); w ciszy radiowej kolejka czeka.
struct BenchRadio : rnsnode::Radio {
    bool ready() override { return radiocon::ok() && radiocon::p1Ok() && bench.receiving() && !bench.busy() && !bench.silence; }
    bool transmit(const uint8_t* data, size_t length) override { return bench.p1send(data, length) == nullptr; }
    uint32_t debtMs() override { return bench.debtRemainingMs(); }
};
BenchRadio benchRadio;
bool rnsOk = false;               // stos uruchomiony (FRAM i dziennik działają)
rnsannounce::Policy announcePolicy;

// Usługi warstwy aplikacji: pakiety przez stos Reticulum i interfejs P1.
struct BenchServices : station::Services {
    uint32_t uptimeS() override { return ::uptimeS(); }
    bool silence() override { return bench.silence; }
    bool radioReady() override { return rnsOk && radiocon::ok() && radiocon::p1Ok() && bench.receiving() && rnsnode::online(); }
    bool busy() override { return rnsnode::queueFull(); }
    uint32_t send(const uint8_t to[store::HASH], const uint8_t* data, size_t length, uint32_t timeoutS) override {
        return rnsnode::send(to, data, length, timeoutS);
    }
    void randomBytes(uint8_t* out, size_t count) override { measure::randomBytes(out, count); }
    void log(const char* text) override { bench.log(text); }
    void destroyed() override;
    bool notify(uint8_t kind, uint32_t ref, const char* fields) override { return protocol.event(kind, ref, fields, millis()); }
    void address(uint8_t out[store::HASH]) override { host.stationAddress(out); }
    void changed() override;
};
BenchServices services;
station::Station app(stationStore, services);
console::Console screenHost(stationStore, app, services, &stationJournal);
bool linkAuto = true;  // LINK 0 zatrzymuje nadawanie z kolejki (próby ręczne P1TX)

void BenchHost::configChanged() {
    if (rnsOk) rnsnode::setIfac(stationStore.config().ifac);   // configure może zmienić kod IFAC
    screenHost.invalidate();
    updateScreen(false);
}
void BenchHost::queueChanged() { screenHost.invalidate(); updateScreen(false); }
void BenchServices::changed() { screenHost.invalidate(); updateScreen(false); }

void onDatagram(const uint8_t* data, size_t length, void*) { if (rnsOk) rnsnode::received(data, length); }
void onTxDone(bool ok, void*) { rnsnode::txDone(ok); }

bool onPacket(const uint8_t* data, size_t length, void*) { return storeOk && app.received(data, length); }
void onReceipt(uint32_t handle, bool delivered, void*) { app.receipt(handle, delivered); }
void onStackLog(const char* text, void*) { bench.log(text); }

// ZNISZCZ DANE (menu albo destroy przez USB): tożsamość i tablice w FRAM skasowane; stos stoi
// do restartu, potem nowa tożsamość.
void wipeStack() {
    if (rnsOk && !rnsnode::wipe()) bench.log("rns wipe failed");
    rnsOk = false;
    setStationName();
}
void BenchHost::destroyed() { wipeStack(); }
void BenchServices::destroyed() { wipeStack(); }

bool BenchHost::announce() {
    if (!rnsOk) return false;
    announcePolicy.request();
    return true;
}

// Ogłoszenie adresu, gdy pozwala na nie polityka (rns_announce.h); bez danych aplikacji.
void pollAnnounce() {
    if (!rnsOk || !storeOk) return;
    const uint32_t nowS = uptimeS();
    announcePolicy.setRole(stationStore.config().role == store::OSP, nowS);
    if (!announcePolicy.due(nowS, bench.silence, rnsnode::online(), app.stats().failed)) return;
    if (!rnsnode::announce(nullptr, 0)) { announcePolicy.failed(nowS); return; }
    uint32_t random = 0;
    measure::randomBytes(reinterpret_cast<uint8_t*>(&random), sizeof(random));
    announcePolicy.counted();
    announcePolicy.done(nowS, random, app.stats().failed);
}

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

#if defined(WICI_BOARD_N1)
// Panel płytki N1: przełącznik CISZA, przycisk przygotowania, dioda alarmu i brzęczyk.
// Przełącznik i przycisk działają na zmianę stanu, więc polecenia SILENCE i PREP zostają jako
// zapasowe i obowiązują do następnego przełączenia.
constexpr uint32_t SWITCH_SETTLE_MS = 50;   // przełącznik CISZA: stan stały przez 50 ms
constexpr uint32_t PREP_HOLD_MS = 3000;     // przytrzymanie przycisku przygotowania
constexpr uint32_t ALARM_BEEP_MS = 200;     // ekran alarmu: sygnał co 2 s do potwierdzenia OK
constexpr uint32_t ALARM_BEEP_EVERY_MS = 2000;
bool silenceSwitchLevel = false;
uint32_t silenceSwitchSince = 0;
bool silenceSwitchState = false;
uint32_t prepPressedSince = 0;
bool prepWas = false;
bool prepToggled = false;
bool alarmLedOn = false;
bool alarmLedWanted = false;  // stan wynikający z alarmu i ciszy; LED 5 zmienia tylko alarmLedOn
bool alarmCause = false;     // przyczyna alarmu trwa (także po potwierdzeniu OK)
uint32_t alarmCauseMs = 0;
uint32_t lastAlarmBeep = 0;

bool silenceSwitch() { return digitalRead(board::SW_SILENCE) == LOW; }

void beep(uint32_t ms) { tone(board::BUZZER, board::BUZZER_HZ, ms); }

void alarmLed(bool on) {
    alarmLedOn = on;
    digitalWrite(board::LED_ALARM, on ? HIGH : LOW);  // dioda alarmu aktywna stanem wysokim
}

void setSilenceFromSwitch(bool on) {
    if (bench.silence == on) return;
    bench.silence = on;
    bench.log(on ? "silence on (switch)" : "silence off (switch)");
    radioEvent();
}

// Przełącznik na stacji ma pierwszeństwo: w położeniu „cisza” polecenie z USB nie wyłącza ciszy.
bool silenceLocked() { return silenceSwitchState; }

void setPrepFromButton(bool on) {
    if (!on) bench.stop();
    bench.prep = on;
    bench.log(on ? "preparation mode on (button)" : "preparation mode off (button)");
    beep(100);
    radioEvent();
}

void beginPanel() {
    pinMode(board::LED_ALARM, OUTPUT);
    alarmLed(false);
    pinMode(board::BUZZER, OUTPUT);
    digitalWrite(board::BUZZER, LOW);
    pinMode(board::SW_SILENCE, INPUT);  // podciągnięcia na płytce
    pinMode(board::BTN_PREP, INPUT);
    platform::beginVtest();
    silenceSwitchLevel = silenceSwitchState = silenceSwitch();
    silenceSwitchSince = millis();
    bench.silence = silenceSwitchState;  // położenie przełącznika przy starcie
    if (bench.silence) bench.log("silence on (switch at start)");
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
        setSilenceFromSwitch(level);
    }
    const bool prep = pressed(board::BTN_PREP);
    if (prep && !prepWas) prepPressedSince = now;
    if (!prep) prepToggled = false;
    else if (!prepToggled && now - prepPressedSince >= PREP_HOLD_MS) {
        prepToggled = true;
        setPrepFromButton(!bench.prep);
    }
    prepWas = prep;
    // Dioda świeci do usunięcia przyczyny alarmu (potwierdzenie OK gasi tylko dźwięk) i w ciszy radiowej;
    // przyczyna sprawdzana co sekundę jak alarmy ekranu. Zapis tylko przy zmianie tego stanu, więc LED 5
    // obowiązuje do następnej zmiany alarmu albo ciszy.
    const bool alarm = screenModel.screen() == ui::Screen::ALARM;
    if (now - alarmCauseMs >= 1000) {
        alarmCauseMs = now;
        alarmCause = storeOk && app.alarmCause(uptimeS());
    }
    const bool led = alarm || alarmCause || bench.silence;
    if (led != alarmLedWanted) {
        alarmLedWanted = led;
        alarmLed(led);
    }
    if (alarm && now - lastAlarmBeep >= ALARM_BEEP_EVERY_MS) {
        lastAlarmBeep = now;
        beep(ALARM_BEEP_MS);
    }
}

#else
bool silenceLocked() { return false; }  // przewody: bez przełącznika CISZA
#endif

bool BenchHost::silenceSwitch() { return silenceLocked(); }

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
    s.radioOk = radiocon::ok() && radiocon::p1Ok();
    s.contactKnown = false;          // bez odbiorcy: dolne oszacowanie z czasu pracy
    s.contactS = uptimeS();
    s.mains12 = true;
    s.millivolts = 0;                // stanowisko nie mierzy napięcia (INFO: mv = 0)
    bool found = false;
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
    int32_t foffHz = 0;
    s.foffValid = radiocon::ok() && c.rxOk > 0 && radiocon::link().frequencyErrorHz(foffHz);
    s.foffHz = foffHz;
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
    Serial.printf("{\"extcomin\":\"%s\",\"counter\":%lu,\"level\":%s,\"software_vcom\":%s,\"refreshes\":%lu,\"cs\":%u,\"extcomin_pin\":%u,"
                  "\"spi_hz\":%lu}\n",
                  platform::EXTCOMIN_SOURCE, static_cast<unsigned long>(display.extcominCounter()), boolName(display.extcominLevel()),
                  boolName(display.softwareVcom()), static_cast<unsigned long>(display.refreshes()), board::DISPLAY_CS,
                  board::DISPLAY_EXTCOMIN, static_cast<unsigned long>(display.spiHz()));
}

void BenchHost::stationAddress(uint8_t out[store::HASH]) {
    // Skrót celu "wici.sa1" stacji; zera, gdy stos nie wystartował (brak FRAM).
    memcpy(out, rnsnode::address(), store::HASH);
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

// Nazwa wyświetlana: 6 cyfr szesnastkowych skrótu tożsamości (oprogramowanie.md, "Tryby kryzysowe");
// bez stosu (brak FRAM, po ZNISZCZ DANE do restartu) z identyfikatora układu.
void setStationName() {
    if (rnsOk) {
        const uint8_t* h = rnsnode::identityHash();
        snprintf(stationName, sizeof(stationName), "WICI-%02X%02X%02X", h[0], h[1], h[2]);
    } else {
        uint32_t id[2];
        platform::chipId(id);
        snprintf(stationName, sizeof(stationName), "WICI-%06lX", static_cast<unsigned long>(id[0] & 0xFFFFFF));
    }
}

// Po włączeniu zasilania: wybór języka; po restarcie programowym: język i ekran sprzed restartu.
void beginScreen() {
    setStationName();
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
    // Zmiana stanu dopiero po dwóch jednakowych próbkach (eliminacja drgań styków, około 20 ms).
    for (size_t i = 0; i < 4; ++i) {
        const bool is = pressed(buttons[i]);
        if (is == buttonSample[i] && is != buttonWas[i]) {
            if (is) screenModel.down(static_cast<ui::Button>(i), now);
            else screenModel.up(static_cast<ui::Button>(i), now);
            buttonWas[i] = is;
        }
        buttonSample[i] = is;
    }
}

void syncButtons() {
    for (size_t i = 0; i < 4; ++i) buttonWas[i] = buttonSample[i] = pressed(buttons[i]);  // po poleceniu blokującym (CONDUCTED, PREP)
}

// Liczba z polecenia nasycona do `cap`, żeby rzutowanie ani mnożenie nie zawinęło wartości
// (np. TXPKT 1 260 dałoby długość 4); wartości ponad limit odrzuca potem kontrola zakresu.
uint32_t parseArg(const char* text, uint32_t cap) {
    const unsigned long value = strtoul(text, nullptr, 10);
    return value > cap ? cap : static_cast<uint32_t>(value);
}

void printError(const char* text) { Serial.printf("{\"error\":\"%s\"}\n", text); }

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
    // Wiersz w częściach poniżej 256 znaków (Print::printf rdzenia nRF52, zob. printRns).
    const measure::LinkCounters& c = bench.link();
    Serial.printf("{\"contract\":2,\"profile\":\"P1\",\"radio\":\"%s\",\"mcu\":\"%s\",\"fw\":\"%s\","
                  "\"src\":\"USB\",\"mv\":0,\"tx_wait_ms\":%lu,\"rx_ok\":%lu,\"rx_bad\":%lu,\"tx_drop\":%lu,\"restarts\":%lu,",
                  radiocon::NAME, platform::MCU, WICI_FW_VERSION, static_cast<unsigned long>(bench.debtRemainingMs()),
                  static_cast<unsigned long>(c.rxOk), static_cast<unsigned long>(c.rxBad), static_cast<unsigned long>(c.txDrop),
                  static_cast<unsigned long>(restarts));
    Serial.printf("\"bench\":\"%s\",\"prep\":%s,\"silence\":%s,\"radio_ok\":%s,\"p1_ok\":%s,\"fram_ok\":%s,\"journal_ok\":%s,"
                  "\"journal_resets\":%lu,\"carrier_hz\":%lu,\"symbol_rate\":%u,\"deviation_hz\":%u,\"rx_filter_hz\":%u,",
                  BENCH, boolName(bench.prep),
                  boolName(bench.silence), boolName(radiocon::ok()), boolName(radiocon::p1Ok()), boolName(framOk), boolName(journalOk),
                  static_cast<unsigned long>(journalResets), static_cast<unsigned long>(p1::CARRIER_HZ), p1::SYMBOL_RATE,
                  p1::DEVIATION_HZ, radiocon::RX_FILTER_HZ);
    Serial.printf("\"tx_power_dbm\":%d,\"uptime_s\":%lu,\"boot_s\":%lu,\"screen\":\"%s\",\"lang\":\"%s\",\"name\":\"%s\","
                  "\"reset_reason\":\"0x%08lX\",\"store_ok\":%s,\"queued\":%u,\"inbox\":%u,\"pending\":%u,",
                  radiocon::TX_POWER_DBM, static_cast<unsigned long>(uptimeS()),
                  static_cast<unsigned long>(millis() / 1000), ui::screenName(screenModel.screen()), langName(screenModel.language()),
                  stationName, static_cast<unsigned long>(platform::resetReason()), boolName(storeOk),
                  static_cast<unsigned>(storeOk ? stationStore.queueLive() : 0), static_cast<unsigned>(storeOk ? stationStore.inboxCount() : 0),
                  static_cast<unsigned>(storeOk ? stationStore.notesPending() : 0));
    Serial.printf("\"usb_data\":%s,\"usb_in\":%lu,\"usb_out\":%lu,\"usb_rejected\":%lu,\"usb_boot\":\"%s\",\"wdt_s\":%lu,"
                  "\"board\":\"%s\"}\n",
                  boolName(protocol.isConnected()), static_cast<unsigned long>(protocol.stats().linesIn),
                  static_cast<unsigned long>(protocol.stats().linesOut),
                  static_cast<unsigned long>(protocol.stats().rejected), protocol.bootId(), static_cast<unsigned long>(WDT_TIMEOUT_S), BOARD_NAME);
}

void printJournal() {
    const journal::SmallRecord& d = stationJournal.debt();
    const journal::SmallRecord& k = stationJournal.clock();
    // Dwie części poniżej 256 znaków (zob. printRns).
    Serial.printf("{\"journal_ok\":%s,\"debt_seq\":%lu,\"debt_ms\":%lu,\"debt_written_at_s\":%lu,\"debt_records\":%lu,",
                  boolName(journalOk), static_cast<unsigned long>(d.seq), static_cast<unsigned long>(d.a),
                  static_cast<unsigned long>(d.b), static_cast<unsigned long>(stationJournal.debtValid()));
    Serial.printf("\"tx_wait_ms\":%lu,\"clock_seq\":%lu,\"uptime_s\":%lu,\"restarts\":%lu,\"event_seq\":%lu,"
                  "\"max_debt_ms\":%lu,\"journal_resets\":%lu}\n",
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
#if defined(WICI_BOARD_N1)
    // Stan linii panelu N1 (krok A3 uruchomienia): true = zwarte do masy.
    Serial.printf("},\"silence_switch\":%s,\"prep_button\":%s,\"silence\":%s,\"prep\":%s,\"alarm_led\":%s}\n",
                  boolName(silenceSwitch()), boolName(pressed(board::BTN_PREP)), boolName(bench.silence),
                  boolName(bench.prep), boolName(alarmLedOn));
#else
    Serial.println("}}");
#endif
}

void printHelp() {
    Serial.print("{\"commands\":[\"HELP\",\"INFO\"");
    Serial.print(radiocon::helpCommands());
    Serial.print(",\"PREP <0|1>\",\"SILENCE <0|1>\",\"TXCW <s> [CONDUCTED]\",\"TXPKT <n> <len> [<ms>] [ZEROS|ONES] [CONDUCTED]\","
                 "\"RX [<len>]\",\"RXPER\",\"FOFF [<hz>]\",\"P1RX\",\"P1TX <hex>\",\"P1\",\"STOP\",\"LOG [<n>]\",\"JOURNAL\",\"BENCH\","
                 "\"FRAM\",\"BTN\",\"LED <1-4> <0|1>\",\"SCREEN\",\"KEY <UP|DOWN|OK|BACK> [ms]\",\"DISPLAY\","
                 "\"VCOM <0|1>\",\"REBOOT\",\"STORE\",\"USB <json>\",\"APP\",\"LINK <0|1>\",\"RNS\",\"ANNOUNCE\""
#if defined(WICI_BOARD_N1)
                 ",\"LED 5 <0|1>\",\"BUZZ [<ms>] [<hz>]\",\"VTEST\",\"DISPLAY <hz>\""
#endif
    );
    Serial.print(platform::helpCommands());
    Serial.println("]}");
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
    // Dwie części poniżej 256 znaków (zob. printRns).
    Serial.printf("{\"link\":%s,\"in_flight\":%lu,\"sent\":%lu,\"delivered\":%lu,\"failed\":%lu,\"received\":%lu,\"rejected\":%lu,",
                  boolName(linkAuto), static_cast<unsigned long>(app.inFlightSeq()), static_cast<unsigned long>(s.sent),
                  static_cast<unsigned long>(s.delivered), static_cast<unsigned long>(s.failed), static_cast<unsigned long>(s.received),
                  static_cast<unsigned long>(s.rejected));
    Serial.printf("\"duplicates\":%lu,\"conflicts\":%lu,\"refused\":%lu,\"confirmed\":%lu,\"live\":%u,\"unsent\":%u,\"next\":%lu,"
                  "\"test_paused\":%s,\"items\":%u}\n",
                  static_cast<unsigned long>(s.duplicates), static_cast<unsigned long>(s.conflicts),
                  static_cast<unsigned long>(s.refused), static_cast<unsigned long>(s.confirmed),
                  static_cast<unsigned>(stationStore.queueLive()), static_cast<unsigned>(stationStore.queueUnsent()),
                  static_cast<unsigned long>(app.nextToSend(uptimeS())), boolName(app.testPaused()),
                  static_cast<unsigned>(screenHost.itemCount()));
}

// Stan stosu Reticulum: tablice, pula pamięci, system plików FRAM, liczniki interfejsu P1.
void printRns() {
    const rnsnode::Status s = rnsnode::status();
    char address[2 * store::HASH + 1], identity[2 * store::HASH + 1], iface[480];
    store::bytesToHex(rnsnode::address(), address);
    store::bytesToHex(rnsnode::identityHash(), identity);
    rnsnode::interfaceJson(iface, sizeof(iface));
    // Wiersz ma ponad 256 znaków, a Print::printf rdzenia Adafruit nRF52 formatuje do bufora 256 B
    // (dłuższy wynik wypisuje ze śmieciami): części poniżej 256 znaków i opis interfejsu przez print.
    Serial.printf("{\"rns\":%s,\"online\":%s,\"address\":\"%s\",\"identity\":\"%s\",\"identity_new\":%s,\"paths\":%u,",
                  boolName(rnsOk), boolName(s.online), address, identity, boolName(s.identityNew), static_cast<unsigned>(s.paths));
    Serial.printf("\"hashes\":%u,\"announce_table\":%u,\"receipts\":%u,\"pool\":%u,\"pool_used\":%u,\"pool_peak\":%u,"
                  "\"fs_files\":%u,\"fs_used\":%u,\"fs_capacity\":%u,",
                  static_cast<unsigned>(s.packetHashes), static_cast<unsigned>(s.announceTable), static_cast<unsigned>(s.receiptsPending),
                  static_cast<unsigned>(s.poolSize), static_cast<unsigned>(s.poolUsed), static_cast<unsigned>(s.poolPeak),
                  static_cast<unsigned>(s.fsFiles), static_cast<unsigned>(s.fsUsedBytes), static_cast<unsigned>(s.fsCapacityBytes));
    Serial.printf("\"sent\":%lu,\"received\":%lu,\"unproven\":%lu,\"delivered\":%lu,\"timed_out\":%lu,\"announces_seen\":%lu,",
                  static_cast<unsigned long>(s.packetsSent), static_cast<unsigned long>(s.packetsReceived),
                  static_cast<unsigned long>(s.packetsUnproven), static_cast<unsigned long>(s.delivered),
                  static_cast<unsigned long>(s.timedOut), static_cast<unsigned long>(s.announcesSeen));
    Serial.printf("\"announced\":%lu,\"announce_next_s\":%ld,\"wait_ms\":%lu,\"bitrate\":%lu,",
                  static_cast<unsigned long>(announcePolicy.count()),
                  announcePolicy.scheduled() ? static_cast<long>(announcePolicy.nextS() - uptimeS()) : -1L,
                  static_cast<unsigned long>(s.queueWaitMs), static_cast<unsigned long>(s.bitrate));
    Serial.print(iface);
    Serial.print("}\n");
}

void printStore() {
    const store::Config& c = stationStore.config();
    char osp[2 * store::HASH + 1];
    store::bytesToHex(c.osp[c.activeOsp ? 1 : 0], osp);
    // Dwie części poniżej 256 znaków (zob. printRns); adres ma do 64 znaków.
    Serial.printf("{\"store_ok\":%s,\"configured\":%s,\"config_seq\":%lu,\"role\":\"%s\",\"address\":\"%s\",\"osp\":\"%s\","
                  "\"phrases\":%u,\"stations\":%u,",
                  boolName(storeOk), boolName(stationStore.configured()), static_cast<unsigned long>(c.seq),
                  c.role == store::OSP ? "osp" : "station", c.address, osp, c.phraseCount, c.stations);
    Serial.printf("\"queued\":%u,\"inbox\":%u,\"unread\":%u,\"notes_pending\":%u,\"note_latest\":%lu,"
                  "\"usb_synced\":%s,\"usb_stored\":%lu,\"usb_overflow\":%lu,\"usb_resends\":%lu}\n",
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
    else if (radiocon::handle(cmd, words, n)) return;
    else if (platform::handle(cmd, words, n)) return;
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
        if (!on && silenceLocked()) printError("silence switch on");
        else if (on != bench.silence) {
            bench.silence = on;
            bench.log(bench.silence ? "silence on" : "silence off");
            radioEvent();
        }
        Serial.printf("{\"silence\":%s}\n", boolName(bench.silence));
    } else if (!strcmp(cmd, "TXCW")) {
        const bool conducted = lastIsConducted(words, n);
        if (n != 1) printError("TXCW <s> [CONDUCTED]");
        else {
            const char* error = bench.txcw(parseArg(words[0], 1000), conducted);
            if (error) printError(error);
        }
    } else if (!strcmp(cmd, "TXPKT")) {
        const bool conducted = lastIsConducted(words, n);
        testframe::Fill fill = testframe::Fill::PN9;  // ZEROS / ONES: wypełnienie ramek wzorcowych
        if (n && !strcmp(words[n - 1], "ZEROS")) { fill = testframe::Fill::ZEROS; --n; }
        else if (n && !strcmp(words[n - 1], "ONES")) { fill = testframe::Fill::ONES; --n; }
        if (n < 2 || n > 3) printError("TXPKT <n> <len> [<ms>] [ZEROS|ONES] [CONDUCTED]");
        else {
            const char* error = bench.txpkt(static_cast<uint16_t>(parseArg(words[0], 0xFFFF)),
                                            static_cast<uint8_t>(parseArg(words[1], 0xFF)),
                                            n == 3 ? parseArg(words[2], 3600000) : 0, conducted, fill);
            if (error) printError(error);
        }
    } else if (!strcmp(cmd, "RX")) {
        const uint8_t length = n ? static_cast<uint8_t>(parseArg(words[0], 0xFF)) : p1::MAX_PACKET_BYTES;
        const char* error = bench.rxStart(length);
        if (error) printError(error);
        else Serial.printf("{\"rx\":true,\"len\":%u}\n", length);
        radiocon::printState();
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
        radiocon::printState();
    } else if (!strcmp(cmd, "LOG")) {
        const uint32_t count = n ? strtoul(words[0], nullptr, 10) : 16;
        bench.printLog(count > 64 ? 64 : count);
    } else if (!strcmp(cmd, "JOURNAL")) printJournal();
    else if (!strcmp(cmd, "BENCH")) bench.printStatus();
    else if (!strcmp(cmd, "FRAM")) printFram();
    else if (!strcmp(cmd, "BTN")) printButtons();
    else if (!strcmp(cmd, "LED") && n == 2) {
        const int index = atoi(words[0]);
#if defined(WICI_BOARD_N1)
        if (index == 5) {  // dioda alarmu N1; obowiązuje do następnej zmiany stanu alarmu albo ciszy
            alarmLed(atoi(words[1]) != 0);
            Serial.printf("{\"led\":5,\"on\":%s}\n", boolName(alarmLedOn));
            return;
        }
#endif
        if (index >= 1 && index <= 4 && leds[index - 1] >= 0) {
            ledWrite(leds[index - 1], atoi(words[1]) != 0);
            Serial.printf("{\"led\":%d,\"on\":%s}\n", index, boolName(atoi(words[1]) != 0));
        } else printError(leds[0] >= 0 ? "LED <1-4> <0|1>" : "LED 5 <0|1>");
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
    }
#if defined(WICI_BOARD_N1)
    else if (!strcmp(cmd, "DISPLAY") && n == 1) {
        // Zegar SPI ekranu do prób z analizatorem na J11; do restartu. Odpowiedź po pełnym przerysowaniu.
        const uint32_t hz = strtoul(words[0], nullptr, 10);
        if (hz < 125000 || hz > sharp::SPI_HZ) { printError("DISPLAY <125000..2000000>"); return; }
        display.spiHz(hz);
        updateScreen(true);
        printDisplay();
    } else if (!strcmp(cmd, "BUZZ") && n <= 2) {
        const uint32_t ms = n >= 1 ? strtoul(words[0], nullptr, 10) : 500;
        const uint32_t hz = n == 2 ? strtoul(words[1], nullptr, 10) : board::BUZZER_HZ;
        if (ms > 5000 || hz < 100 || hz > 10000) { printError("BUZZ [<0..5000 ms>] [<100..10000 Hz>]"); return; }
        if (ms) tone(board::BUZZER, hz, ms);
        else noTone(board::BUZZER);
        Serial.printf("{\"buzz_ms\":%lu,\"hz\":%lu}\n", static_cast<unsigned long>(ms), static_cast<unsigned long>(hz));
    } else if (!strcmp(cmd, "VTEST")) platform::printVtest();
#endif
    else if (!strcmp(cmd, "DISPLAY")) printDisplay();
    else if (!strcmp(cmd, "STORE")) printStore();
    else if (!strcmp(cmd, "APP")) printApp();
    else if (!strcmp(cmd, "LINK") && n == 1) { linkAuto = atoi(words[0]) != 0; printApp(); }
    else if (!strcmp(cmd, "RNS")) printRns();
    else if (!strcmp(cmd, "ANNOUNCE")) {
        // Ogłoszenie na polecenie: wychodzi przy najbliższym obiegu, poza ciszą radiową i z kodem IFAC.
        if (!host.announce()) printError("rns not running");
        else printRns();
    }
    else if (!strcmp(cmd, "VCOM") && n == 1) {
        display.softwareVcom(atoi(words[0]) != 0);  // zapasowo, gdy zworka EXTMODE płytki jest niska
        printDisplay();
    } else if (!strcmp(cmd, "REBOOT")) {
        // Restart programowy: pamięć niezerowana zostaje, więc ekran i język wracają (jak po watchdogu).
        if (rnsOk) rnsnode::persist();   // tablice stosu w FRAM przed restartem
        Serial.println("{\"reboot\":true}");
        Serial.flush();
        delay(20);
        platform::reboot();
    } else if (!strcmp(cmd, "HELP") || !*cmd) printHelp();
    else {
        // Słowo polecenia ma do 1399 znaków (bufor wiersza): przez print, nie przez Print::printf (zob. printRns).
        Serial.print("{\"error\":\"unknown\",\"cmd\":\"");
        Serial.print(cmd);
        Serial.print("\"}\n");
    }
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

// Stos Reticulum: tożsamość i tablice w FRAM, zegar stosu z czasu pracy w dzienniku; kod IFAC
// z konfiguracji (bez niego interfejs P1 nie nadaje). Ogłoszenie startowe po 0–120 s.
void beginStack() {
    if (!framOk || !journalOk) { bench.log("rns not started: FRAM or journal unavailable"); return; }
    rnsnode::Hooks hooks;
    hooks.packet = onPacket;
    hooks.receipt = onReceipt;
    hooks.log = onStackLog;
    uint8_t ifac[store::HASH] = {};
    if (storeOk) memcpy(ifac, stationStore.config().ifac, sizeof(ifac));
    rnsOk = rnsnode::begin(memory, benchRadio, ifac, static_cast<uint64_t>(uptimeS()) * 1000, hooks);
    if (!rnsOk) { bench.log("rns start failed"); return; }
    uint32_t random = 0;
    measure::randomBytes(reinterpret_cast<uint8_t*>(&random), sizeof(random));
    announcePolicy.begin(storeOk && stationStore.config().role == store::OSP, uptimeS(), random);
    bench.log(rnsnode::status().identityNew ? "rns started, new identity" : "rns started");
}

}  // namespace

void stationSetup() {
    pinMode(board::DISPLAY_CS, OUTPUT);  // CS ekranu aktywny stanem wysokim: najpierw w stan niski
    digitalWrite(board::DISPLAY_CS, LOW);
#if defined(WICI_BOARD_N1)
    pinMode(board::DISPLAY_DISP, OUTPUT);  // ekran wyłączony do wyczyszczenia jego pamięci
    digitalWrite(board::DISPLAY_DISP, LOW);
#endif
    for (int16_t pin : leds) {
        if (pin >= 0) pinMode(static_cast<uint8_t>(pin), OUTPUT);
        ledWrite(pin, false);
    }
#if defined(WICI_BOARD_N1)
    for (uint8_t pin : buttons) pinMode(pin, INPUT);  // podciągnięcia na płytce
    beginPanel();
#else
    for (uint8_t pin : buttons) pinMode(pin, INPUT_PULLUP);
#endif
    radiocon::attach(bench);
    radiocon::begin();  // CS radia w stan nieaktywny
    memory.begin();
    platform::beginBus();
    // Dwa interfejsy CDC ACM z deskryptorami IAD (radio.md, "USB do laptopa"): diagnostyka i dane.
#if defined(ARDUINO_ARCH_NRF52)
    Serial.setStringDescriptor("WICI diagnostyka");
    SerialData.setStringDescriptor("WICI dane");
    Serial.begin(115200);
    SerialData.begin(115200);
    if (TinyUSBDevice.mounted()) {  // host zdążył wyliczyć urządzenie z jednym interfejsem
        TinyUSBDevice.detach();
        delay(10);
        TinyUSBDevice.attach();
    }
#else
    // ESP32-S3: USB-OTG z TinyUSB; rdzeń uruchamia Serial (interfejs 0) i USB przed setup(), a oba
    // interfejsy są w deskryptorze od startu. Nazwy interfejsów ustala rdzeń ("TinyUSB CDC", "TinyUSB CDC2").
    SerialData.begin(115200);
#endif
    delay(50);
    radiocon::start();  // LED2 świeci dopiero po zapisanym i (CC1120) skalibrowanym P1
    framOk = memory.identify().mb85rs4m;
    beginJournal();
    ledWrite(board::LED_FRAM, framOk && journalOk);  // LED3 świeci dopiero z działającym dziennikiem
    storeOk = framOk && stationStore.begin();
    protocol.begin();
    beginStack();
    bench.onDatagram(onDatagram, nullptr);
    bench.onTxDone(onTxDone, nullptr);
    if (radiocon::ok() && radiocon::p1Ok()) bench.p1rxStart();  // łącze P1 w odbiorze od startu (radio niezależne od ekranu)
    display.begin();  // CLEAR czyści pamięć ekranu
#if defined(WICI_BOARD_N1)
    digitalWrite(board::DISPLAY_DISP, HIGH);
#endif
    if (storeOk) screenModel.attach(&screenHost);  // bez magazynu: ekran bez kreatora i wiadomości
    beginScreen();
    syncButtons();
    if (platform::resetByWatchdog()) bench.log("restart by watchdog");
    platform::beginWatchdog(WDT_TIMEOUT_S);
}

void stationLoop() {
    static uint32_t lastBeat = 0;
    static bool beat = false;
    static bool reported = false;
    static bool radioLed = false;
    const uint32_t now = millis();
    platform::feedWatchdog();
    if (now - lastBeat >= 500) {
        lastBeat = now;
        beat = !beat;
        ledWrite(board::LED_HEARTBEAT, beat);
    }
    // LED2: P1 gotowe; zapis przy zmianie, więc LED 2 z portu obowiązuje do następnej zmiany.
    const bool radioReady = radiocon::ok() && radiocon::p1Ok();
    if (radioReady != radioLed) {
        radioLed = radioReady;
        ledWrite(board::LED_RADIO, radioReady);
    }
    const bool usb = Serial;  // CDC otwarty przez hosta
    ledWrite(board::LED_USB, usb);
    if (usb && !reported) {  // jednorazowy raport po otwarciu portu
        reported = true;
        printInfo();
        radiocon::report();
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
    bench.p1Ready = radiocon::ok() && radiocon::p1Ok();
    if (radiocon::ok()) bench.poll();
    if (rnsOk) {
        rnsnode::loop(now);
        pollAnnounce();
    }
    static uint32_t lastApp = 0;
    if (storeOk && linkAuto && radiocon::ok() && now - lastApp >= APP_POLL_MS) {  // przegląd kolejki co 100 ms, nie w każdym obiegu
        lastApp = now;
        app.poll(now);
    }
    pollSerial();
    pollButtons(now);
#if defined(WICI_BOARD_N1)
    pollPanel(now);
#endif
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

#if defined(ARDUINO_ARCH_NRF52)
// Cała praca stacji biegnie w osobnym zadaniu FreeRTOS z 16 KB stosu: zadanie loop() rdzenia
// Adafruit ma 4 KB, a rysowanie ekranu z odczytem rekordów FRAM i `configure` przez USB
// potrzebują więcej.
constexpr uint32_t STATION_STACK_WORDS = 4096;

void stationTask() {
    static bool started = false;
    if (!started) {
        started = true;
        stationSetup();
    }
    stationLoop();
}

void setup() {
    Scheduler.startLoop(stationTask, STATION_STACK_WORDS, TASK_PRIO_LOW, "station");
}

void loop() {
    vTaskSuspend(nullptr);  // zadanie rdzenia nie jest potrzebne
}
#else
// ESP32-S3: pętla stacji w zadaniu loop() rdzenia z 16 KB stosu (domyślnie 8 KB).
SET_LOOP_TASK_STACK_SIZE(16 * 1024);

void setup() { stationSetup(); }

void loop() {
    stationLoop();
    delay(1);  // oddaje rdzeń innym zadaniom (USB, bezczynność); obieg pętli zostaje co około 1 ms
}
#endif
