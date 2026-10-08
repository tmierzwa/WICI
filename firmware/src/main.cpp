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
// CISZA, przycisk przygotowania, dioda alarmu, brzęczyk, VTEST). Konfiguracja węzła OSP (D19):
// poza trybem przygotowania interfejs danych przenosi pakiety Reticulum do komputera stanowiska
// w ramkach KISS (rns_node.h, kiss.h), a ekran pokazuje kontakt z komputerem.
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

#include "annunciator.h"
#include "board.h"
#include "cmdargs.h"
#include "console.h"
#include "fram.h"
#include "journal.h"
#include "jsonprint.h"
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

using cmdargs::boolName;

// Czas pracy z dziennika plus czas od startu z 64-bitowego licznika platformy: millis() zawija się
// po około 49 dniach (na nRF52840 po 48,5 dnia, bez przejścia przez 2^32), a zegar stacji nie może się cofnąć.
uint32_t uptimeS() { return uptimeBaseS + static_cast<uint32_t>(platform::uptimeMs() / 1000); }
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
    void emit(const char* line) override;
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
// Układ odpowiada, tablica P1 zapisana i zweryfikowana, łącze P1 w odbiorze.
bool p1Listening() { return radiocon::ok() && radiocon::p1Ok() && bench.receiving(); }

struct BenchRadio : rnsnode::Radio {
    bool ready() override { return p1Listening() && !bench.busy() && !bench.silence; }
    bool transmit(const uint8_t* data, size_t length) override { return bench.p1send(data, length) == nullptr; }
    uint32_t debtMs() override { return bench.debtRemainingMs(); }
};
BenchRadio benchRadio;
bool rnsOk = false;               // stos uruchomiony (FRAM i dziennik działają)
rnsannounce::Policy announcePolicy;
// Węzeł OSP: stos z interfejsem USB (od startu stosu; zmiana konfiguracji działa po restarcie).
// Poza trybem przygotowania interfejs danych przenosi ramki KISS, nie protokół laptop–stacja.
bool ospNode() { return rnsOk && rnsnode::ospNode(); }
bool kissMode() { return ospNode() && !bench.prep; }
uint32_t rebootAtMs = 0;          // restart po zmianie konfiguracji węzła OSP (0 = brak)
bool computerHeard = false;       // pakiet od komputera stanowiska od startu
uint32_t computerAtS = 0;         // czas pracy przy ostatnim pakiecie od komputera
uint32_t computerPackets = 0;

void BenchHost::emit(const char* line) {
    // Odpowiedzi idą na interfejs danych; bez otwartego portu danych albo przy ramkach KISS
    // (węzeł OSP poza trybem przygotowania) na diagnostykę (polecenie USB).
    if (SerialData && !kissMode()) SerialData.println(line);
    else Serial.println(line);
}

// Usługi warstwy aplikacji: pakiety przez stos Reticulum i interfejs P1.
struct BenchServices : station::Services {
    uint32_t uptimeS() override { return ::uptimeS(); }
    bool silence() override { return bench.silence; }
    bool radioReady() override { return rnsOk && p1Listening() && rnsnode::online(); }
    bool busy() override { return rnsnode::queueFull(); }
    uint32_t send(const uint8_t to[store::HASH], const uint8_t* data, size_t length, uint32_t timeoutS) override {
        return rnsnode::send(to, data, length, timeoutS);
    }
    void randomBytes(uint8_t* out, size_t count) override { measure::randomBytes(out, count); }
    void log(const char* text) override { bench.log(text); }
    void destroyed() override;
    bool announce() override { return host.announce(); }
    bool notify(uint8_t kind, uint32_t ref, const char* fields) override { return protocol.event(kind, ref, fields, millis()); }
    void address(uint8_t out[store::HASH]) override { host.stationAddress(out); }
    void changed() override;
};
BenchServices services;
station::Station app(stationStore, services);
console::Console screenHost(stationStore, app, services, &stationJournal);
bool linkAuto = true;  // LINK 0 zatrzymuje nadawanie z kolejki (próby ręczne P1TX)
// Zmiana danych ekranu: przerysowanie raz na obieg pętli, także po serii zapisów z USB.
bool screenDirty = false;

void screenChanged() {
    screenHost.invalidate();
    screenDirty = true;
}

// Przypięte OSP z konfiguracji (configure, ODBIORCA ZAPASOWY): rezerwa czasu kanału dla aktywnej
// w interfejsie P1, trasy i tożsamości obu chronione przed usunięciem z pełnych tablic.
void pinOsp() {
    if (!rnsOk || !storeOk) return;
    const store::Config& c = stationStore.config();
    rnsnode::setOsp(c.osp, c.activeOsp);
}

void BenchHost::configChanged() {
    if (rnsOk) rnsnode::setIfac(stationStore.config().ifac);   // configure może zmienić kod IFAC
    pinOsp();
    // Węzeł OSP włączony albo wyłączony: interfejs USB i cel "wici.sa1" zmienia dopiero start stosu,
    // więc stacja wraca po restarcie (po wysłaniu odpowiedzi na configure).
    if (rnsOk && storeOk && (stationStore.config().ospNode != 0) != rnsnode::ospNode() && !rebootAtMs) {
        bench.log("osp node configuration changed: restart");
        rebootAtMs = millis() + 500;
        if (!rebootAtMs) rebootAtMs = 1;
    }
    screenChanged();
}
void BenchHost::queueChanged() { screenChanged(); }
void BenchServices::changed() {
    pinOsp();
    screenChanged();
}

void onDatagram(const uint8_t* data, size_t length, void*) { if (rnsOk) rnsnode::received(data, length); }
void onTxDone(bool ok, void*) { rnsnode::txDone(ok); }

bool onPacket(const uint8_t* data, size_t length, void*) { return storeOk && app.received(data, length); }
void onReceipt(uint32_t handle, bool delivered, void*) { app.receipt(handle, delivered); }
// Wiersze stosu w dzienniku zdarzeń: najwyżej 10 na minutę, żeby powtarzający się błąd stosu
// nie wypchnął z pierścienia w FRAM zdarzeń obsługi; pominięte są liczone w następnym oknie.
void onStackLog(const char* text, void*) {
    constexpr uint32_t WINDOW_MS = 60000;
    constexpr uint8_t PER_WINDOW = 10;
    static uint32_t windowMs = 0;
    static uint8_t count = 0;
    static uint32_t suppressed = 0;
    const uint32_t now = millis();
    if (now - windowMs >= WINDOW_MS) {
        if (suppressed) {
            char line[48];
            snprintf(line, sizeof(line), "rns: %lu log lines suppressed", static_cast<unsigned long>(suppressed));
            bench.log(line);
        }
        windowMs = now;
        count = 0;
        suppressed = 0;
    }
    if (count >= PER_WINDOW) { ++suppressed; return; }
    ++count;
    bench.log(text);
}

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
    if (!rnsOk || ospNode()) return false;
    announcePolicy.request();
    return true;
}

// Ogłoszenie adresu, gdy pozwala na nie polityka (rns_announce.h); bez danych aplikacji.
// Węzeł OSP nie ma adresu i się nie ogłasza (adres OSP ogłasza komputer stanowiska).
void pollAnnounce() {
    if (!rnsOk || !storeOk || ospNode()) return;
    const uint32_t nowS = uptimeS();
    if (!announcePolicy.due(nowS, bench.silence, rnsnode::online(), app.stats().failed)) return;
    if (!rnsnode::announce(nullptr, 0)) { announcePolicy.failed(nowS); return; }
    announcePolicy.counted();
    announcePolicy.done(nowS, app.stats().failed);
}

// Zdarzenie stanu radia do laptopa (cisza, tryb przygotowania). Węzeł OSP nie ma laptopa ani
// zdarzeń w FRAM (stanowisko-osp.md): zmiana zostaje tylko w dzienniku.
void radioEvent() {
    if (ospNode()) return;
    char fields[96];
    snprintf(fields, sizeof(fields), "\"kind\":\"radio\",\"silence\":%s,\"prep\":%s", boolName(bench.silence), boolName(bench.prep));
    if (storeOk) protocol.event(store::NOTE_RADIO, 0, fields, millis());
}

// Zmiana ciszy albo trybu przygotowania: wpis w dzienniku ze źródłem i zdarzenie do laptopa.
void applySilence(bool on, const char* source) {
    if (bench.silence == on) return;
    bench.silence = on;
    char text[40];
    snprintf(text, sizeof(text), "silence %s%s", on ? "on" : "off", source);
    bench.log(text);
    radioEvent();
}

void applyPrep(bool on, const char* source) {
    if (!on) bench.stop();  // wyjście z trybu przygotowania przerywa pomiary
    if (bench.prep == on) return;
    bench.prep = on;
    char text[48];
    snprintf(text, sizeof(text), "preparation mode %s%s", on ? "on" : "off", source);
    bench.log(text);
    radioEvent();
}

void BenchHost::setSilence(bool on) { applySilence(on, " (usb)"); }

#if defined(WICI_BOARD_N1)
// Panel płytki N1: przełącznik CISZA, przycisk przygotowania, dioda alarmu i brzęczyk.
// Przełącznik i przycisk działają na zmianę stanu, więc polecenia SILENCE i PREP zostają jako
// zapasowe i obowiązują do następnego przełączenia.
constexpr uint32_t SWITCH_SETTLE_MS = 50;   // przełącznik CISZA: stan stały przez 50 ms
constexpr uint32_t PREP_HOLD_MS = 3000;     // przytrzymanie przycisku przygotowania
bool silenceSwitchLevel = false;
uint32_t silenceSwitchSince = 0;
bool silenceSwitchState = false;
uint32_t prepPressedSince = 0;
bool prepWas = false;
bool prepToggled = false;
bool alarmLedOn = false;
bool ledManual = false;      // LED 5: stan ręczny do następnej zmiany powodu migania
bool ledActive = false;
bool alarmCause = false;     // przyczyna alarmu trwa (także po potwierdzeniu OK)
uint32_t alarmCauseMs = 0;
annunciator::Annunciator annunciation;

bool silenceSwitch() { return digitalRead(board::SW_SILENCE) == LOW; }

void beep(uint32_t ms) { tone(board::BUZZER, board::BUZZER_HZ, ms); }

void alarmLed(bool on) {
    alarmLedOn = on;
    digitalWrite(board::LED_ALARM, on ? HIGH : LOW);  // dioda alarmu aktywna stanem wysokim
}

// Przełącznik na stacji ma pierwszeństwo: w położeniu „cisza” polecenie z USB nie wyłącza ciszy.
bool silenceLocked() { return silenceSwitchState; }

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
        applySilence(level, " (switch)");
    }
    const bool prep = pressed(board::BTN_PREP);
    if (prep && !prepWas) prepPressedSince = now;
    if (!prep) prepToggled = false;
    else if (!prepToggled && now - prepPressedSince >= PREP_HOLD_MS) {
        prepToggled = true;
        applyPrep(!bench.prep, " (button)");
        beep(100);
    }
    prepWas = prep;
    // Dioda i brzęczyk (annunciator.h); przyczyna alarmu sprawdzana co sekundę jak alarmy ekranu.
    // LED 5 obowiązuje do następnej zmiany powodu migania (alarm, cisza, nieprzeczytane).
    if (now - alarmCauseMs >= 1000) {
        alarmCauseMs = now;
        alarmCause = storeOk && app.alarmCause(uptimeS());
    }
    annunciator::Inputs in;
    in.alarmScreen = screenModel.screen() == ui::Screen::ALARM;
    in.alarmCause = alarmCause;
    in.silence = bench.silence;
    in.muted = screenModel.muted();
    in.unread = storeOk ? static_cast<uint32_t>(stationStore.inboxUnread()) : 0;
    const uint32_t ms = annunciation.poll(now, in);
    if (ms) beep(ms);
    if (annunciation.active() != ledActive) {
        ledActive = annunciation.active();
        ledManual = false;
    }
    if (!ledManual && annunciation.led() != alarmLedOn) alarmLed(annunciation.led());
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
    const rnsnode::UsbStatus usb = rnsnode::usbStatus();
    s.computerHeard = computerHeard;
    s.computerS = computerHeard && uptimeS() > computerAtS ? uptimeS() - computerAtS : 0;
    s.usbIn = usb.counters.fromComputer;
    s.usbOut = usb.counters.toComputer;
    s.usbDrop = usb.counters.rxDropped + usb.counters.rxTooLarge + usb.counters.txDropped;
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
        jsonprint::text(Serial, shown.text[i]);
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

// Rekord ustawień w FRAM: a = język + 1, b = znaczniki (SETTINGS_FLAGS odróżnia je od numeru
// ekranu zapisywanego tam przez wcześniejsze wersje).
constexpr uint32_t SETTINGS_FLAGS = 0x100;
constexpr uint32_t SETTINGS_MUTED = 0x001;
constexpr uint32_t SETTINGS_OBJECT_SHIFT = 4;   // bity 4–6: obiekt wybrany z listy adresów
constexpr uint32_t SETTINGS_OBJECT_MASK = 0x070;

// Język i ekran w pamięci niezerowanej po każdej zmianie (restart programowy, watchdog); w FRAM
// język i wyciszenie przy ich zmianie (po włączeniu zasilania stacja zaczyna od wyboru języka z podpowiedzią).
void persistScreen() {
    if (!screenModel.takeChange()) return;
    retain();
    const uint32_t lang = static_cast<uint32_t>(screenModel.language()) + 1;
    const uint32_t flags = SETTINGS_FLAGS | (screenModel.muted() ? SETTINGS_MUTED : 0) |
                           ((static_cast<uint32_t>(stationStore.selectedAddress()) << SETTINGS_OBJECT_SHIFT) & SETTINGS_OBJECT_MASK);
    const journal::SmallRecord& saved = stationJournal.settings();
    if (journalOk && (saved.a != lang || saved.b != flags) && !stationJournal.writeSettings(lang, flags)) {
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
    // Wyciszenie dźwięku przetrwa także zanik zasilania (rekord ustawień w FRAM).
    screenModel.setMuted(journalOk && (saved.b & SETTINGS_FLAGS) && (saved.b & SETTINGS_MUTED));
    // Obiekt z listy adresów wybrany przed restartem albo wyłączeniem (po włączeniu kursor listy).
    if (journalOk && (saved.b & SETTINGS_FLAGS)) stationStore.selectAddress((saved.b & SETTINGS_OBJECT_MASK) >> SETTINGS_OBJECT_SHIFT);
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
// false, gdy tekst nie jest liczbą dziesiętną bez znaku.
bool parseArg(const char* text, uint32_t cap, uint32_t& out) {
    if (*text < '0' || *text > '9') return false;
    char* end = nullptr;
    const unsigned long value = strtoul(text, &end, 10);
    if (*end) return false;
    out = value > cap ? cap : static_cast<uint32_t>(value);
    return true;
}

void printError(const char* text) { Serial.printf("{\"error\":\"%s\"}\n", text); }

void printFram() {
    const fram::Id id = memory.identify();
    framOk = id.part != fram::Part::UNKNOWN;
    ledWrite(board::LED_FRAM, framOk && journalOk);  // jak przy starcie: FRAM i działający dziennik
    char hex[2 * fram::ID_BYTES + 1];
    for (size_t i = 0; i < fram::ID_BYTES; ++i) snprintf(hex + 2 * i, 3, "%02X", id.bytes[i]);
    Serial.printf("{\"fram\":\"%s\",\"id\":\"%s\",\"status\":\"0x%02X\",\"ok\":%s}\n",
                  fram::partName(id.part), hex, id.status, boolName(framOk));
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
                  static_cast<unsigned long>(platform::uptimeMs() / 1000), ui::screenName(screenModel.screen()), langName(screenModel.language()),
                  stationName, static_cast<unsigned long>(platform::resetReason()), boolName(storeOk),
                  static_cast<unsigned>(storeOk ? stationStore.queueLive() : 0), static_cast<unsigned>(storeOk ? stationStore.inboxCount() : 0),
                  static_cast<unsigned>(storeOk ? stationStore.notesPending() : 0));
    char usb[400];
    rnsnode::usbJson(usb, sizeof(usb));
    Serial.print(usb);   // pola węzła OSP (interfejs Reticulum przez USB)
    Serial.printf(",\"computer_s\":%ld,", computerHeard ? static_cast<long>(uptimeS() - computerAtS) : -1L);
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
                  static_cast<unsigned long>(stationJournal.eventSeq()), static_cast<unsigned long>(measure::MAX_DEBT_MS),
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
        debtMs = measure::MAX_DEBT_MS;
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
                 "\"FRAM\",\"BTN\","
#if !defined(WICI_BENCH_B)
                 "\"LED <1-4> <0|1>\","  // stanowisko B nie ma diod stanu
#endif
                 "\"SCREEN\",\"KEY <UP|DOWN|OK|BACK> [ms]\",\"DISPLAY\","
                 "\"VCOM <0|1>\",\"REBOOT\",\"STORE\",\"USB <json>\",\"APP\",\"LINK <0|1>\",\"RNS\",\"ANNOUNCE\""
#if defined(WICI_BOARD_N1)
                 ",\"LED 5 <0|1>\",\"BUZZ [<ms>] [<hz>]\",\"VTEST\",\"DISPLAY <hz>\""
#endif
    );
    Serial.print(platform::helpCommands());
    Serial.println("]}");
}

// Argumenty po poleceniu (najwięcej MAX_ARGS słów: TXPKT ma pięć); zwraca liczbę słów albo
// MAX_ARGS + 1, gdy słów jest więcej.
constexpr size_t MAX_ARGS = 5;
size_t splitArgs(char* text, char* words[]) {
    size_t n = 0;
    for (char* word = strtok(text, " "); word; word = strtok(nullptr, " ")) {
        if (n == MAX_ARGS) return MAX_ARGS + 1;
        words[n++] = word;
    }
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
    char usb[400];
    rnsnode::usbJson(usb, sizeof(usb));
    Serial.print(",");
    Serial.print(usb);
    Serial.printf(",\"computer_s\":%ld}\n", computerHeard ? static_cast<long>(uptimeS() - computerAtS) : -1L);
}

void printStore() {
    const store::Config& c = stationStore.config();
    char osp[2 * store::HASH + 1];
    store::bytesToHex(c.osp[c.activeOsp ? 1 : 0], osp);
    // Części poniżej 256 znaków (zob. printRns); adres z laptopa z sekwencjami ucieczki.
    Serial.printf("{\"store_ok\":%s,\"configured\":%s,\"config_seq\":%lu,\"osp_node\":%s,", boolName(storeOk),
                  boolName(stationStore.configured()), static_cast<unsigned long>(c.seq), boolName(c.ospNode != 0));
    jsonprint::field(Serial, "address", stationStore.address());   // obiekt wybrany na ekranie
    Serial.printf(",\"addresses\":%u,\"selected\":%u,\"osp\":\"%s\",\"phrases\":%u,\"stations\":%u,",
                  static_cast<unsigned>(stationStore.addressCount()), static_cast<unsigned>(stationStore.selectedAddress()), osp,
                  c.phraseCount, c.stations);
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
    for (char* p = cmd; *p; ++p) *p = static_cast<char>(toupper(static_cast<unsigned char>(*p)));
    char* arg = strchr(cmd, ' ');
    if (arg) *arg++ = '\0';
    char* words[MAX_ARGS];
    const size_t n = arg ? splitArgs(arg, words) : 0;
    if (n > MAX_ARGS) { printError("too many arguments"); return; }
    if (!strcmp(cmd, "INFO")) printInfo();
    else if (radiocon::handle(cmd, words, n)) return;
    else if (platform::handle(cmd, words, n)) return;
    else if (!strcmp(cmd, "PREP") && n == 1) {
        // Na stacji tryb przygotowania włącza przycisk pod plombowaną pokrywą; na stanowisku
        // zastępuje go polecenie potwierdzone przyciskiem OK w ciągu 30 s.
        bool on = false;
        if (!cmdargs::parseFlag(words[0], on)) printError("PREP <0|1>");
        else if (on && !bench.prep && !bench.confirm()) {
            bench.log("PREP not confirmed");
            printError("PREP not confirmed by OK");
        } else {
            applyPrep(on, "");
            Serial.printf("{\"prep\":%s}\n", boolName(bench.prep));
        }
    } else if (!strcmp(cmd, "SILENCE") && n == 1) {
        bool on = false;  // na stacji: przełącznik CISZA
        if (!cmdargs::parseFlag(words[0], on)) { printError("SILENCE <0|1>"); return; }
        if (!on && silenceLocked()) printError("silence switch on");
        else applySilence(on, "");
        Serial.printf("{\"silence\":%s}\n", boolName(bench.silence));
    } else if (!strcmp(cmd, "TXCW")) {
        size_t count = n;
        const bool conducted = lastIsConducted(words, count);
        uint32_t seconds = 0;
        if (count != 1 || !parseArg(words[0], 1000, seconds)) printError("TXCW <s> [CONDUCTED]");
        else {
            const char* error = bench.txcw(seconds, conducted);
            if (error) printError(error);
        }
    } else if (!strcmp(cmd, "TXPKT")) {
        size_t count = n;
        const bool conducted = lastIsConducted(words, count);
        testframe::Fill fill = testframe::Fill::PN9;  // ZEROS / ONES: wypełnienie ramek wzorcowych
        if (count && !strcmp(words[count - 1], "ZEROS")) { fill = testframe::Fill::ZEROS; --count; }
        else if (count && !strcmp(words[count - 1], "ONES")) { fill = testframe::Fill::ONES; --count; }
        uint32_t frames = 0, length = 0, interval = 0;
        if (count < 2 || count > 3 || !parseArg(words[0], 0xFFFF, frames) || !parseArg(words[1], 0xFF, length) ||
            (count == 3 && !parseArg(words[2], 3600000, interval))) {
            printError("TXPKT <n> <len> [<ms>] [ZEROS|ONES] [CONDUCTED]");
        } else {
            const char* error = bench.txpkt(static_cast<uint16_t>(frames), static_cast<uint8_t>(length), interval, conducted, fill);
            if (error) printError(error);
        }
    } else if (!strcmp(cmd, "RX") && n <= 1) {
        uint32_t value = p1::MAX_PACKET_BYTES;
        if (n && !parseArg(words[0], 0xFF, value)) { printError("RX [<len>]"); return; }
        const uint8_t length = static_cast<uint8_t>(value);
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
            const char pair[3] = {words[0][2 * i], words[0][2 * i + 1], '\0'};
            uint32_t value = 0;
            if (!isxdigit(static_cast<unsigned char>(pair[0])) || !cmdargs::parseUint(pair, 0, 0xFF, value, 16)) {
                printError("P1TX: not hex");
                return;
            }
            data[i] = static_cast<uint8_t>(value);
        }
        const char* error = bench.p1send(data, hexLength / 2);
        if (error) printError(error);
        else Serial.printf("{\"p1tx\":\"queued\",\"len\":%u,\"fragments\":%u}\n", static_cast<unsigned>(hexLength / 2),
                           p1frame::fragmentCount(hexLength / 2));
    } else if (!strcmp(cmd, "P1")) bench.printLink();
    else if (!strcmp(cmd, "FOFF")) {
        if (n == 1) {
            int32_t hz = 0;
            if (!cmdargs::parseInt(words[0], -2000000, 2000000, hz)) { printError("FOFF [<hz>]"); return; }
            const char* error = bench.foff(hz);
            if (error) { printError(error); return; }
        }
        bench.printFoff();
    } else if (!strcmp(cmd, "STOP")) {
        bench.stop();
        Serial.println("{\"stop\":true}");
        radiocon::printState();
    } else if (!strcmp(cmd, "LOG")) {
        uint32_t count = 16;
        if (n && !cmdargs::parseUint(words[0], 1, 64, count)) { printError("LOG [<1-64>]"); return; }
        bench.printLog(count);
    } else if (!strcmp(cmd, "JOURNAL")) printJournal();
    else if (!strcmp(cmd, "BENCH")) bench.printStatus();
    else if (!strcmp(cmd, "FRAM")) printFram();
    else if (!strcmp(cmd, "BTN")) printButtons();
    else if (!strcmp(cmd, "LED") && n == 2) {
        uint32_t index = 0;
        bool on = false;
        const bool valid = cmdargs::parseUint(words[0], 1, 5, index) && cmdargs::parseFlag(words[1], on);
#if defined(WICI_BOARD_N1)
        if (valid && index == 5) {  // dioda alarmu N1; obowiązuje do następnej zmiany powodu migania
            ledManual = true;
            alarmLed(on);
            Serial.printf("{\"led\":5,\"on\":%s}\n", boolName(alarmLedOn));
            return;
        }
#endif
        if (valid && index <= 4 && leds[index - 1] >= 0) {
            ledWrite(leds[index - 1], on);
            Serial.printf("{\"led\":%lu,\"on\":%s}\n", static_cast<unsigned long>(index), boolName(on));
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
        uint32_t held = 0;
        if (n == 2 && !cmdargs::parseUint(words[1], 0, 60000, held)) { printError("KEY <UP|DOWN|OK|BACK> [<0-60000 ms>]"); return; }
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
        uint32_t hz = 0;
        if (!cmdargs::parseUint(words[0], 125000, sharp::SPI_HZ, hz)) { printError("DISPLAY <125000..2000000>"); return; }
        display.spiHz(hz);
        updateScreen(true);
        printDisplay();
    } else if (!strcmp(cmd, "BUZZ") && n <= 2) {
        uint32_t ms = 500, hz = board::BUZZER_HZ;
        if ((n >= 1 && !cmdargs::parseUint(words[0], 0, 5000, ms)) || (n == 2 && !cmdargs::parseUint(words[1], 100, 10000, hz))) {
            printError("BUZZ [<0..5000 ms>] [<100..10000 Hz>]");
            return;
        }
        if (ms) tone(board::BUZZER, hz, ms);
        else noTone(board::BUZZER);
        Serial.printf("{\"buzz_ms\":%lu,\"hz\":%lu}\n", static_cast<unsigned long>(ms), static_cast<unsigned long>(hz));
    } else if (!strcmp(cmd, "VTEST")) platform::printVtest();
#endif
    else if (!strcmp(cmd, "DISPLAY")) printDisplay();
    else if (!strcmp(cmd, "STORE")) printStore();
    else if (!strcmp(cmd, "APP")) printApp();
    else if (!strcmp(cmd, "LINK") && n == 1) {
        if (!cmdargs::parseFlag(words[0], linkAuto)) printError("LINK <0|1>");
        else printApp();
    }
    else if (!strcmp(cmd, "RNS")) printRns();
    else if (!strcmp(cmd, "ANNOUNCE")) {
        // Ogłoszenie na polecenie: wychodzi przy najbliższym obiegu, poza ciszą radiową i z kodem IFAC.
        if (!host.announce()) printError("rns not running");
        else printRns();
    }
    else if (!strcmp(cmd, "VCOM") && n == 1) {
        bool on = false;
        if (!cmdargs::parseFlag(words[0], on)) { printError("VCOM <0|1>"); return; }
        display.softwareVcom(on);  // zapasowo, gdy pin EMD (EXTMODE) płytki jest niski
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
        Serial.print("{\"error\":\"unknown\",");
        jsonprint::field(Serial, "cmd", cmd);
        Serial.print("}\n");
    }
}

void pollSerial() {
    static bool overflow = false;  // wiersz dłuższy niż bufor: odrzucony w całości, nie wykonany ucięty
    while (Serial.available()) {
        const char c = static_cast<char>(Serial.read());
        if (c == '\n' || c == '\r') {
            line[lineLength] = '\0';
            if (overflow) printError("line too long");
            else if (lineLength) { handle(line); syncButtons(); }
            lineLength = 0;
            overflow = false;
        } else if (lineLength < sizeof(line) - 1) {
            line[lineLength++] = c;
        } else {
            overflow = true;
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
    // Cele OSP przypięte przed startem: porządkowanie tablic przy starcie też ich nie usuwa.
    if (storeOk) rnsnode::setOsp(stationStore.config().osp, stationStore.config().activeOsp);
    rnsnode::setOspNode(storeOk && stationStore.config().ospNode);   // interfejs USB do komputera stanowiska
    rnsOk = rnsnode::begin(memory, benchRadio, ifac, static_cast<uint64_t>(uptimeS()) * 1000, hooks);
    if (!rnsOk) { bench.log("rns start failed"); return; }
    pinOsp();
    uint32_t random = 0;
    measure::randomBytes(reinterpret_cast<uint8_t*>(&random), sizeof(random));
    announcePolicy.begin(uptimeS(), random);
    bench.log(rnsnode::ospNode() ? "rns started as osp node" : rnsnode::status().identityNew ? "rns started, new identity" : "rns started");
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
    framOk = memory.identify().part != fram::Part::UNKNOWN;
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
    platform::uptimeMs();  // licznik 64-bitowy liczy przejścia przez zero przy każdym obiegu
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
    bench.p1Ready = radioReady;
    if (radiocon::ok()) bench.poll();
    if (rnsOk) {
        rnsnode::loop(now);
        pollAnnounce();
    }
    static uint32_t lastApp = 0;
    if (storeOk && now - lastApp >= APP_POLL_MS) {  // przegląd kolejki co 100 ms, nie w każdym obiegu
        lastApp = now;
        app.notifyPending();   // zdarzenia do laptopa także przy LINK 0 i bez radia
        if (linkAuto && radiocon::ok()) app.poll(now);
    }
    pollSerial();
    pollButtons(now);
#if defined(WICI_BOARD_N1)
    pollPanel(now);
#endif
    screenModel.tick(now);
    persistScreen();
    static uint32_t lastScreen = 0;
    if (screenDirty || now - lastScreen >= SCREEN_POLL_MS) {
        screenDirty = false;
        lastScreen = now;
        updateScreen(false);
    }
    display.maintain(now);
    // Interfejs danych: otwarcie portu wysyła sync, zamknięcie odrzuca niepełny wiersz. Bez magazynu
    // protokół też odpowiada (zapis kończy się odmową "memory"), żeby laptop nie czekał bez odpowiedzi.
    // Węzeł OSP poza trybem przygotowania: ramki KISS do komputera stanowiska zamiast protokołu.
    static bool kissWas = false;
    const bool dataOpen = SerialData;
    const bool kiss = kissMode();
    if (dataOpen != dataWas || kiss != kissWas) {
        if (kissWas) rnsnode::usbOpen(false);
        else if (dataWas) protocol.disconnected();
        if (kiss) rnsnode::usbOpen(dataOpen);
        else if (dataOpen) protocol.connected(now);
        dataWas = dataOpen;
        kissWas = kiss;
    }
    if (dataOpen) {
        char chunk[64];
        while (SerialData.available()) {
            size_t n = 0;
            while (n < sizeof(chunk) && SerialData.available()) chunk[n++] = static_cast<char>(SerialData.read());
            if (kiss) rnsnode::usbFeed(reinterpret_cast<const uint8_t*>(chunk), n, now);
            else protocol.feed(chunk, n, now);
        }
        if (kiss) {
            // Do komputera tyle, ile przyjmie bufor CDC (zapis nie blokuje pętli stacji).
            uint8_t out[64];
            int room = SerialData.availableForWrite();
            while (room > 0) {
                const size_t n = rnsnode::usbTake(out, static_cast<size_t>(room) < sizeof(out) ? static_cast<size_t>(room) : sizeof(out));
                if (!n) break;
                SerialData.write(out, n);
                room -= static_cast<int>(n);
            }
        } else protocol.poll(now);
    }
    if (ospNode()) {
        const uint32_t packets = rnsnode::usbStatus().counters.fromComputer;
        if (packets != computerPackets) {
            computerPackets = packets;
            computerHeard = true;
            computerAtS = uptimeS();
        }
    }
    if (rebootAtMs && static_cast<int32_t>(now - rebootAtMs) >= 0) {
        rnsnode::persist();   // tablice stosu w FRAM przed restartem
        Serial.flush();
        SerialData.flush();
        platform::reboot();
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
    delay(1);  // jak na ESP32: zadanie bezczynności (tryb uśpienia FreeRTOS) dostaje rdzeń, obieg co około 1 ms
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
