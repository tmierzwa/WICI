// SPDX-License-Identifier: MIT
// WICI, stanowiska deweloperskie A i B oraz stacja pilotażowa L0: oprogramowanie stacji ze stosem
// Reticulum (bez LXMF).
// Zakres: USB z dwoma interfejsami CDC (diagnostyka z poleceniami tekstowymi i dane z protokołem
// laptop–stacja "usb":2 nad rejestrem, skrzynką, pierścieniem zdarzeń i konfiguracją w FRAM, usbproto.h),
// identyfikacja radia i FRAM przez SPI, konfiguracja rejestrów profilu P1 z weryfikacją odczytu,
// polecenia pomiarowe TXCW, TXPKT, RXPER, FOFF w trybie przygotowania, dziennik w FRAM (dług
// ciszy, licznik czasu pracy, zdarzenia), generator stacji HMAC-DRBG (drbg.h), łącze P1 (odbiór i składanie
// datagramów, nadawanie z CCA, odroczeniem i długiem ciszy), stos Reticulum (port microReticulum,
// rns_node.h) z interfejsem P1 nad łączem, tożsamością i tablicami w FRAM, warstwa aplikacji nad
// stosem (rejestr zgłoszeń, wysyłka, ponowienia, decyzje odbiorcy, station.h), ekran Sharp
// z EXTCOMIN z licznika MCU i przyciski jako menu stacji (kreator zgłoszenia, WIADOMOŚCI, TEST,
// STAN, USŁUGI, alarmy, pytania poleceń USB), panel płytki N1 (przełącznik CISZA, przycisk
// przygotowania, dioda alarmu, brzęczyk, VTEST). Konfiguracja węzła stanowiska (rola `wezel`):
// poza trybem przygotowania interfejs danych przenosi pakiety Reticulum do komputera stanowiska
// w ramkach KISS (rns_node.h, kiss.h), a ekran pokazuje kontakt z komputerem.
// Wykonania: bench-a (nRF52840-DK + CC1120EM na przewodach), bench-n1 (to samo na płytce N1),
// bench-b (ESP32-S3-DevKitC-1 + X-NUCLEO-S2868A2 z S2-LP na N1), l0 (ESP32-S3-DevKitC-1 + Wio-SX1262
// na N1, profil LoRa: polecenia pomiarowe bez łącza P1, README, "Stacja L0"). Zależne od MCU części są
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
#if defined(WICI_RNS_CORE)
#include "core_selftest.h"
#endif
#include "drbg.h"
#include "fram.h"
#include "hexstr.h"
#include "journal.h"
#include "jsonprint.h"
#include "measure.h"
#include "p1_registers.h"
#include "p1frame.h"
#include "platform.h"
#include "radio_console.h"
#include "rns_announce.h"
#include "rns_node.h"
#include "sha2.h"
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
#if defined(WICI_L0)
constexpr const char* BENCH = "L0";
#elif defined(WICI_BENCH_B)
constexpr const char* BENCH = "B";
#else
constexpr const char* BENCH = "A";
#endif

fram::Memory memory(platform::bus(), board::FRAM_CS, board::FRAM_SPI_HZ);
journal::Journal stationJournal(memory);
measure::Bench bench(radiocon::link(), board::BTN_OK, board::LED_HEARTBEAT);
#if defined(WICI_BOARD_N1)
sharp::Display display(platform::bus(), board::DISPLAY_CS, board::DISPLAY_EXTCOMIN, board::DISPLAY_SPI_HZ);
#else
sharp::Display display(platform::bus(), board::DISPLAY_CS, board::DISPLAY_EXTCOMIN);
#endif
// Generator stacji (drbg.h): ziarno ze sprzętowego źródła entropii przy starcie (platform::entropy).
drbg::Drbg generator;
bool entropyHealthy = false;   // odczyt ziarna przeszedł test zdrowia (drbg::healthy); bez tego bez nowej tożsamości
bool entropyTimeout = false;   // źródło entropii nie odpowiedziało w ograniczonym czasie (platform::entropy)
// Stan stosu w INFO (`rns_state`): not_started, unavailable (FRAM, dziennik albo magazyn), entropy_failed (bez
// zdrowego ziarna dla nowej tożsamości), selftest_failed (samotest rdzenia), identity_lost, start_failed,
// running, halted (ZNISZCZ DANE). Wszystkie poza running i halted mają też wpis w dzienniku i dają alarm
// brak_lacznosci; beginStack() w setup() ustawia stan przed pierwszym obiegiem, więc not_started w pracy
// nie występuje.
enum class StackState : uint8_t {
    NOT_STARTED, UNAVAILABLE, ENTROPY_FAILED, SELFTEST_FAILED, IDENTITY_LOST, START_FAILED, RUNNING, HALTED
};
constexpr const char* STACK_STATE_NAMES[] = {"not_started", "unavailable", "entropy_failed", "selftest_failed",
                                             "identity_lost", "start_failed", "running", "halted"};
static_assert(sizeof(STACK_STATE_NAMES) / sizeof(STACK_STATE_NAMES[0]) == static_cast<size_t>(StackState::HALTED) + 1,
              "nazwa każdego stanu stosu");
StackState stackState = StackState::NOT_STARTED;
// Stos sieciowy nie działa, choć powinien (alarm brak_lacznosci, oprogramowanie.md, ekran główny).
bool stackFault() { return stackState != StackState::RUNNING && stackState != StackState::HALTED; }
void stationRandom(uint8_t* out, size_t count) {
    // Ziarno powstaje pierwsze w stationSetup(); odmowa to błąd programu: restart zamiast bajtów spoza generatora.
    if (!generator.generate(out, count)) platform::reboot();
}
#if defined(WICI_L0)
constexpr const char* RADIO_PROFILE = "lora-sf7";  // profil radiowy stacji L0 (`radio.profile` w configure, protokol-usb.md)
#else
constexpr const char* RADIO_PROFILE = "p1";   // profil radiowy stanowisk A i B (`radio.profile` w configure, protokol-usb.md)
#endif
store::Store stationStore(memory, stationJournal, stationRandom, RADIO_PROFILE);
// Drugi interfejs CDC: dane (protokół laptop–stacja); Serial = diagnostyka.
#if defined(ARDUINO_ARCH_NRF52)
Adafruit_USBD_CDC SerialData;
#else
USBCDC SerialData(1);  // interfejs dopisany do deskryptora przed USB.begin() rdzenia
#endif
bool storeOk = false;
bool destroyed = false;   // po ZNISZCZ DANE do restartu: bez zapisu zegara i ustawień ekranu
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
uint32_t counterBaseS = 0;   // licznik czasu pracy z dziennika przy starcie (już z przeskokiem 60 s)
uint32_t skipS = 0;          // suma przeskoków restartów S: czas dla obsługi = licznik − S
uint32_t journalResets = 0;  // brak poprawnego rekordu długu przy starcie
constexpr uint32_t CLOCK_WRITE_MS = 60000;  // zapis zegara co 60 s (oprogramowanie.md, "Czas")
char line[1400];  // P1TX przyjmuje do 600 B datagramu zapisanego szesnastkowo
size_t lineLength = 0;

const uint8_t buttons[] = {board::BTN_UP, board::BTN_DOWN, board::BTN_OK, board::BTN_BACK};
const char* const buttonNames[] = {"up", "down", "ok", "back"};
const int16_t leds[] = {board::LED_HEARTBEAT, board::LED_RADIO, board::LED_FRAM, board::LED_USB};

// Diody DK aktywne stanem niskim; -1: płytka bez diody (stanowisko B).
void ledWrite(int16_t pin, bool on);

// Zapis dziennika nie powiódł się: dziennik wyłączony (LED3 gaśnie); zegar, ustawienia, tryb przygotowania.
void journalFailed() {
    journalOk = false;
    ledWrite(board::LED_FRAM, false);
}

void ledWrite(int16_t pin, bool on) {
    if (pin >= 0) digitalWrite(static_cast<uint8_t>(pin), on ? LOW : HIGH);
}

bool pressed(uint8_t pin) { return digitalRead(pin) == LOW; }

using cmdargs::boolName;

// Licznik czasu pracy (oprogramowanie.md, "Czas"): z dziennika plus czas od startu z 64-bitowego
// licznika platformy (millis() zawija się po około 49 dniach), więc nie cofa się także po restarcie.
// Czas dla obsługi (rekordy magazynu, `at` zdarzeń) = licznik − S.
uint32_t counterS() { return counterBaseS + static_cast<uint32_t>(platform::uptimeMs() / 1000); }
uint32_t serviceS() { return counterS() - skipS; }
uint32_t startServiceS = 0;  // czas dla obsługi przy tym starcie (kontakt sprzed startu = dolne oszacowanie)
void updateScreen(bool force);
void setStationName();
void wipeStack();
void restartSoon(const char* why);

// Usługi stacji dla protokołu USB.
struct BenchHost : usbproto::Host {
    bool prep() override { return bench.prep; }
    bool silenceSwitch() override;
    void randomBytes(uint8_t* out, size_t count) override { stationRandom(out, count); }
    void log(const char* text) override { bench.log(text); }
    bool identity(uint8_t key[64], uint8_t lxmf[store::HASH]) override;
    const char* stationName() override;
    const char* version() override { return WICI_FW_VERSION; }
    uint32_t counterS() override { return ::counterS(); }
    bool contactBeforeStart() override { return stationStore.meta().contactS < startServiceS; }
    void power(char* out, size_t size) override;
    void diag(char* out, size_t size) override;
    bool announce() override;
    bool destroy() override;
    void configChanged(bool roleChanged) override;
    void confirmBegin(usbproto::Question question, const char* detail) override;
    usbproto::Confirm confirmPoll() override;
    void confirmEnd() override;
    void showCard(const char* fingerprint) override;
};
BenchHost host;


// Układ radiowy odpowiada, a tablica P1 jest zapisana i zweryfikowana (wiersz 1 ekranu, LED2, radio_awaria).
bool radioWorks() { return radiocon::ok() && radiocon::p1Ok(); }

// Radio służy stacji: działa i nie jest zajęte trybem EMC. Tryb EMC zatrzymuje nadawanie stosu, więc
// stacja daje radio_awaria (wiersz 1, ekran alarmu): stacja, której po badaniach nie wyłączono trybu,
// nie wyjdzie w teren jako sprawna (firmware/README.md, tryb pracy do badań EMC).
bool radioServes() { return radioWorks() && !bench.emcActive(); }

// Łącze stanowiska pod interfejsem radiowym stosu (P1 albo LoRa w ramkach RNode, Driver::framing):
// datagram z kolejki interfejsu idzie przez Bench (dług ciszy, CCA, odroczenia, ramki); w ciszy
// radiowej kolejka czeka. Radio służy stacji i łącze jest w odbiorze.
bool p1Listening() { return radioServes() && bench.receiving(); }

// Alarm radio_awaria (oprogramowanie.md, ekran główny): radio nie służy stacji albo odbiór w tle stoi
// (stacja L0: zadanie odbioru bez postępu przez 10 s przy uzbrojonym odbiorze stosu, radiocon::rxStalled).
bool rxStalled = false;
bool radioFault() { return !radioServes() || rxStalled; }

// Gotowość radiowa (plan interfejsu LoRa, L6): czas od startu do uzbrojenia odbioru stosu, -1 przed nim;
// odbiór startuje przed ekranem. Najdłuższy obieg pętli od startu (loop_max_ms).
int32_t rxReadyMs = -1;
uint32_t loopMaxMs = 0;
const char* linkName() {
    const radiolink::Framing f = bench.linkFraming();
    return f == radiolink::Framing::RNODE ? "lora" : f == radiolink::Framing::P1 ? "p1" : "none";
}

struct BenchRadio : rnsnode::Radio {
    bool ready() override { return p1Listening() && !bench.busy() && (!bench.silence || bench.silenceException); }
    bool transmit(const uint8_t* data, size_t length) override { return bench.linkSend(data, length, true) == nullptr; }
    uint32_t debtMs() override { return bench.debtRemainingMs(); }
    const p1iface::LinkTiming& timing() override {
        return bench.linkFraming() == radiolink::Framing::RNODE ? p1iface::loraTiming() : p1iface::p1Timing();
    }
};
BenchRadio benchRadio;
bool rnsOk = false;               // stos uruchomiony (FRAM i dziennik działają)
rnsannounce::Policy announcePolicy;
// Węzeł stanowiska: stos z interfejsem USB (od startu stosu; zmiana roli działa po restarcie).
// Poza trybem przygotowania interfejs danych przenosi ramki KISS, nie protokół laptop–stacja.
bool nodeRole() { return rnsOk && rnsnode::node(); }
bool kissMode() { return nodeRole() && !bench.prep; }
uint32_t rebootAtMs = 0;          // restart po zmianie roli (0 = brak)
bool computerHeard = false;       // pakiet od komputera stanowiska od startu
uint32_t computerAtS = 0;         // czas pracy przy ostatnim pakiecie od komputera
uint32_t computerPackets = 0;

// Przełącznik CISZA na stacji (na stanowisku bez przełącznika: polecenie SILENCE); ma pierwszeństwo
// przed ciszą z panelu (meta) i wyklucza wyjątek dla pojedynczego zgłoszenia.
bool switchSilence = false;
bool silenceAny() { return switchSilence || (storeOk && stationStore.meta().silence); }

// Usługi warstwy aplikacji: pakiety przez stos Reticulum i interfejs P1.
struct BenchServices : station::Services {
    bool silence() override { return silenceAny(); }
    bool silenceSwitch() override { return switchSilence; }
    bool radioReady() override { return rnsOk && p1Listening() && rnsnode::online(); }
    bool busy() override { return rnsnode::queueFull(); }
    uint32_t send(const uint8_t to[store::HASH], const uint8_t* data, size_t length, uint32_t timeoutS) override {
        return rnsnode::send(to, data, length, timeoutS);
    }
    bool sendReady(const uint8_t to[store::HASH]) override { return rnsnode::sendReady(to); }
    void randomBytes(uint8_t* out, size_t count) override { stationRandom(out, count); }
    void log(const char* text) override { bench.log(text); }
    void address(uint8_t out[store::HASH]) override { memcpy(out, rnsnode::address(), store::HASH); }
    void changed() override;
};
BenchServices services;
station::Station app(stationStore, services);
usbproto::Protocol protocol(stationStore, app, host);

// Kolejka wyjściowa (protokół laptop–stacja albo ramki KISS) do portu: tyle, ile przyjmie bufor CDC,
// z wynikiem write() (ESP32 może przyjąć mniej po limicie czasu), więc komputer, który nie czyta, nie
// zatrzymuje pętli stacji, a zapis częściowy zostaje w kolejce. Source: output(length) i consume(n).
template <typename Port, typename Source>
void drain(Port& port, Source& source) {
    int room = port.availableForWrite();
    while (room > 0) {
        size_t n = 0;
        const uint8_t* data = reinterpret_cast<const uint8_t*>(source.output(n));
        if (!n) return;
        if (n > static_cast<size_t>(room)) n = static_cast<size_t>(room);
        const size_t written = port.write(data, n);
        source.consume(written);
        if (written < n) return;
        room -= static_cast<int>(written);
    }
}
struct KissOutput {   // ramki KISS węzła stanowiska jako źródło dla drain()
    const uint8_t* output(size_t& length) { return rnsnode::usbOutput(length); }
    void consume(size_t length) { rnsnode::usbConsume(length); }
} kissOutput;

// Działania ekranu poza magazynem: OGŁOŚ ADRES, ZNISZCZ DANE, rola.
struct ScreenActions : console::Actions {
    bool announce() override { return host.announce(); }
    bool destroy() override { return host.destroy(); }
    bool node() override { return nodeRole(); }
    void log(const char* text) override { bench.log(text); }
};
ScreenActions screenActions;
console::Console screenHost(stationStore, app, screenActions);
bool linkAuto = true;  // LINK 0 zatrzymuje nadawanie z kolejki (próby ręczne P1TX)
// Zmiana danych ekranu: przerysowanie raz na obieg pętli, także po serii zapisów z USB.
bool screenDirty = false;

void screenChanged() {
    screenHost.invalidate();
    screenDirty = true;
}

// Tożsamości odbiorcy z karty w konfiguracji (configure, KLUCZ ZAPASOWY): znane stosowi bez
// ogłoszenia, aktywna jako cel K1 kolejki P1, obie chronione w pełnych tablicach.
void applyReceivers() {
    if (!storeOk) return;
    // Tylko po zmianie konfiguracji albo aktywnej tożsamości: zapamiętanie tożsamości pisze do FRAM.
    static uint32_t appliedSeq = 0;
    static uint8_t appliedReceiver = 0xFF;
    const config::Config& c = stationStore.config();
    if (c.seq == appliedSeq && stationStore.meta().receiver == appliedReceiver && rnsOk) return;
    appliedSeq = c.seq;
    appliedReceiver = stationStore.meta().receiver;
    uint8_t keys[2][64], sa1[2][store::HASH];
    for (size_t i = 0; i < 2; ++i) {
        memcpy(keys[i], c.receivers[i].key, 64);
        memcpy(sa1[i], c.receivers[i].sa1, store::HASH);
    }
    rnsnode::setReceivers(keys, sa1, stationStore.meta().receiver);
}

// Cisza w łączu i stosie: każda cisza blokuje pomiary i P1TX; przy wyjątku łącze przyjmuje tylko
// datagramy od stosu, który przepuszcza wymianę jednego zgłoszenia (rns_node.h).
void applySilence() {
    const store::Silence mode = storeOk ? store::silenceMode(stationStore.meta(), switchSilence) : switchSilence ? store::Silence::FULL : store::Silence::OFF;
    bench.silence = mode != store::Silence::OFF;
    bench.silenceException = mode == store::Silence::EXCEPTION;
    rnsnode::setSilence(mode == store::Silence::EXCEPTION ? rnsnode::Silence::EXCEPTION : bench.silence ? rnsnode::Silence::FULL : rnsnode::Silence::OFF);
    // Datagram przyjęty przed ciszą albo dla innego wyjątku nie wychodzi: przy wyjątku łącze przepuszcza
    // każdy datagram stosu, więc ruch sprzed zmiany (przekazywany, ogłoszenie) odpada tu, nie w łączu.
    static store::Silence lastMode = store::Silence::OFF;
    static uint8_t lastException[store::HASH] = {};
    const uint8_t* exception = stationStore.meta().exception;
    if (mode != store::Silence::OFF && (mode != lastMode || (mode == store::Silence::EXCEPTION && memcmp(exception, lastException, store::HASH)))) {
        bench.dropLinkTx();
        rnsnode::dropQueue();
    }
    lastMode = mode;
    memcpy(lastException, exception, store::HASH);
}

void restartSoon(const char* why) {
    if (rebootAtMs) return;
    bench.log(why);
    rebootAtMs = millis() + 500;
    if (!rebootAtMs) rebootAtMs = 1;
}

void BenchHost::configChanged(bool roleChanged) {
    // Nowa konfiguracja w bieżącym wejściu w tryb przygotowania (STAN, PRZEKAZANIE ZMIANY).
    const uint8_t* sha = stationStore.configSha();
    // Konfiguracja jest już zatwierdzona; nieudany zapis wyłącza dziennik, więc STAN pokazuje licznik „?”.
    if (journalOk && !stationJournal.notePrep(journal::PREP_CONFIG, static_cast<uint16_t>((sha[0] << 8) | sha[1]))) {
        bench.log("prep log: config not noted");
        journalFailed();
    }
    if (rnsOk) rnsnode::setIfac(stationStore.config().ifac);   // configure może zmienić kod IFAC
    applyReceivers();
    // Zmiana roli: interfejs USB i cel stacji (port "wici.sa1", rdzeń "lxmf.delivery") zmienia dopiero
    // start stosu, więc stacja wraca
    // po restarcie (po wysłaniu odpowiedzi na configure).
    if (roleChanged) restartSoon("role changed: restart");
    screenChanged();
}
void BenchServices::changed() {
    applyReceivers();
    applySilence();
    screenChanged();
}

void onDatagram(const uint8_t* data, size_t length, void*) { if (rnsOk) rnsnode::received(data, length); }
void onTxDone(bool ok, void*) { rnsnode::txDone(ok); }

bool onPacket(const uint8_t* data, size_t length, bool& exception, void*) {
    if (!storeOk) return false;
    const bool resolved = app.received(data, length);
    exception = app.exceptionTraffic();
    return resolved;
}
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

// ZNISZCZ DANE (menu albo destroy przez USB): stos staje, magazyn, dziennik, tożsamość i tablice
// w FRAM są kasowane (store::Store::destroy); po restarcie nowa tożsamość.
void wipeStack() {
    if (rnsOk) rnsnode::halt();
    rnsOk = false;
    stackState = StackState::HALTED;
    setStationName();
}

bool BenchHost::destroy() {
    // Po skasowaniu restart: stan w RAM (próby w drodze, potwierdzone alarmy, stos bez tożsamości)
    // należy do skasowanych rekordów, a nowa tożsamość powstaje przy starcie stosu.
    wipeStack();
    bench.emcStop();  // rekord ustawień i tak znika; bez ramek do restartu
    destroyed = true;
    retained.magic = 0;   // język i ekran nie wracają po restarcie (ustawienia ekranu skasowane)
    const bool ok = stationStore.destroy();
    storeOk = ok;
    bench.log(ok ? "data destroyed" : "destroy failed");
    applySilence();
    screenChanged();
    restartSoon("destroy: restart");
    return ok;
}

bool BenchHost::announce() {
    if (!rnsOk || nodeRole()) return false;
    announcePolicy.request();
    return true;
}

// Ogłoszenie adresu, gdy pozwala na nie polityka (rns_announce.h); bez danych aplikacji.
// Węzeł stanowiska nie ma adresu i się nie ogłasza (adres stanowiska ogłasza jego komputer).
void pollAnnounce() {
    if (!rnsOk || !storeOk || nodeRole()) return;
    const uint32_t nowS = counterS();
    if (!announcePolicy.due(nowS, silenceAny(), rnsnode::online(), app.stats().failed)) return;
    if (!rnsnode::announce(nullptr, 0)) { announcePolicy.failed(nowS); return; }
    announcePolicy.counted();
    announcePolicy.done(nowS, app.stats().failed);
}

// Przełącznik CISZA (albo polecenie SILENCE na stanowisku): wpis w dzienniku i zdarzenie `radio`
// w FRAM. Węzeł stanowiska nie ma laptopa ani zdarzeń (stanowisko-osp.md): zmiana zostaje w dzienniku.
void setSwitchSilence(bool on, const char* source) {
    if (switchSilence == on) return;
    switchSilence = on;
    applySilence();
    char text[40];
    snprintf(text, sizeof(text), "silence switch %s%s", on ? "on" : "off", source);
    bench.log(text);
    if (storeOk && !nodeRole()) app.radioEvent(on);
    screenChanged();
}

// Zwraca false, gdy wejście w tryb odmówiono (brak zapisu w dzienniku).
bool applyPrep(bool on, const char* source) {
    if (!on) bench.stop();  // wyjście z trybu przygotowania przerywa pomiary
    if (bench.prep == on) return true;
    char text[48];
    // Wejście zapisane w dzienniku FRAM, zanim tryb zacznie działać (oprogramowanie.md, "Tryb
    // przygotowania i naklejka serwisowa"); bez zapisu tryb się nie włącza.
    if (on && !(journalOk && stationJournal.enterPrep(counterS()))) {
        if (journalOk) journalFailed();
        snprintf(text, sizeof(text), "preparation mode refused: journal%s", source);
        bench.log(text);
        screenChanged();   // STAN pokazuje licznik „?”
        return false;
    }
    bench.prep = on;
    snprintf(text, sizeof(text), "preparation mode %s%s", on ? "on" : "off", source);
    bench.log(text);
    if (storeOk && !nodeRole()) app.stationEvent(store::PREP, on);
    return true;
}

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
    switchSilence = silenceSwitchState;  // położenie przełącznika przy starcie (przed radiem i stosem)
    bench.silence = switchSilence;
    if (switchSilence) bench.log("silence switch on at start");
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
        setSwitchSilence(level, "");
    }
    const bool prep = pressed(board::BTN_PREP);
    if (prep && !prepWas) prepPressedSince = now;
    if (!prep) prepToggled = false;
    else if (!prepToggled && now - prepPressedSince >= PREP_HOLD_MS) {
        prepToggled = true;
        // Krótki sygnał: tryb przełączony; długi: wejście odmówione (dziennik FRAM nie przyjął zapisu).
        beep(applyPrep(!bench.prep, " (button)") ? 100 : 1500);
    }
    prepWas = prep;
    // Dioda i brzęczyk (annunciator.h); przyczyna alarmu sprawdzana co sekundę jak alarmy ekranu.
    // LED 5 obowiązuje do następnej zmiany powodu migania (alarm, cisza, nieprzeczytane).
    if (now - alarmCauseMs >= 1000) {
        alarmCauseMs = now;
        alarmCause = screenHost.alarmCause();
    }
    annunciator::Inputs in;
    in.alarmScreen = screenModel.screen() == ui::Screen::ALARM;
    in.alarmCause = alarmCause;
    in.silence = silenceAny();
    in.muted = screenModel.muted();
    in.unread = storeOk ? static_cast<uint32_t>(stationStore.unread()) : 0;
    const uint32_t ms = annunciation.poll(now, in);
    if (ms) beep(ms);
    if (annunciation.active() != ledActive) {
        ledActive = annunciation.active();
        ledManual = false;
    }
    if (!ledManual && annunciation.led() != alarmLedOn) alarmLed(annunciation.led());
}

#endif

bool BenchHost::silenceSwitch() { return switchSilence; }

static_assert(static_cast<int>(usbproto::Question::SILENCE_EXCEPTION) == static_cast<int>(ui::Question::SILENCE_EXCEPTION), "pytania USB i ekranu");
void BenchHost::confirmBegin(usbproto::Question question, const char* detail) {
    screenModel.ask(static_cast<ui::Question>(question), detail);
    screenChanged();
}
usbproto::Confirm BenchHost::confirmPoll() {
    const ui::Answer a = screenModel.answer();
    return a == ui::Answer::WAITING ? usbproto::Confirm::WAITING : a == ui::Answer::YES ? usbproto::Confirm::YES : usbproto::Confirm::NO;
}
void BenchHost::confirmEnd() {
    screenModel.dismiss();
    screenChanged();
}
void BenchHost::showCard(const char* fingerprint) {
    screenModel.ask(ui::Question::CARD, fingerprint);   // OK albo WSTECZ zamyka
    screenChanged();
}

// Stanowisko jest zasilane z USB i nie mierzy napięć: źródło "12v", napięcia 0, bez alarmu energii.
void BenchHost::power(char* out, size_t size) { snprintf(out, size, "\"source\":\"12v\",\"mv_aa\":0,\"mv_12v\":0,\"alarm\":\"none\""); }

void BenchHost::diag(char* out, size_t size) {
    const station::Stats& a = app.stats();
    snprintf(out, size, "\"rejected\":%lu,\"k2_dropped\":%lu,\"long_deferrals\":%lu,\"watchdog_restart\":%s,\"bulletins_skipped\":%lu",
             static_cast<unsigned long>(a.rejected), static_cast<unsigned long>(rnsnode::status().k2Dropped),
             static_cast<unsigned long>(bench.link().longDeferrals), boolName(platform::resetByWatchdog()),
             static_cast<unsigned long>(a.bulletinsSkipped));
}

bool BenchHost::identity(uint8_t key[64], uint8_t lxmf[store::HASH]) {
    if (!rnsOk || nodeRole() || !rnsnode::publicKey(key)) return false;
    sha2::destinationHash(key, config::LXMF_NAME, lxmf);
    return true;
}

const char* langName(ui::Lang lang) { return lang == ui::Lang::PL ? "PL" : lang == ui::Lang::UK ? "UK" : "EN"; }

void retain() {
    retained.lang = static_cast<uint8_t>(screenModel.language());
    retained.screen = static_cast<uint8_t>(screenModel.screen());
    retained.magic = RETAINED_MAGIC;
    retained.check = ~RETAINED_MAGIC;
}

// Stan stacji dla ekranu: wartości ze stanowiska (bez pomiaru napięcia) i z magazynu.
ui::Status screenStatus() {
    ui::Status s;
    const measure::LinkCounters& c = bench.link();
    const uint32_t nowS = serviceS();
    s.prep = bench.prep;
    s.silence = silenceAny();
    s.radioOk = !radioFault();
    s.stackOk = !stackFault();
    s.storeOk = stationStore.ok();
    // Kontakt z odbiorcą: znany od ostatniej przyjętej wiadomości; bez niej dolne oszacowanie z czasu pracy.
    const store::Meta& m = stationStore.meta();
    s.contactKnown = storeOk && m.contactKnown && m.contactS >= startServiceS;
    s.contactS = storeOk && m.contactKnown ? nowS - m.contactS : nowS;
    s.mains12 = true;
    s.millivolts = 0;                // stanowisko nie mierzy napięcia (INFO: mv = 0)
    uint32_t oldest = 0;
    s.queued = storeOk ? static_cast<uint32_t>(stationStore.unsent(oldest)) : 0;
    s.queueAgeS = s.queued && nowS > oldest ? nowS - oldest : 0;
    s.newMessages = storeOk ? static_cast<uint32_t>(stationStore.unread()) : 0;
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
    s.prepKnown = journalOk && !stationJournal.prepCorrupt();
    s.prepEntries = stationJournal.prepEntries();
    // Licznik czasu pracy cofa się tylko po ZNISZCZ DANE: wtedy czas od wejścia jest nieznany.
    s.prepAgeKnown = s.prepEntries && counterS() >= stationJournal.prepAtS();
    s.prepAgeS = s.prepAgeKnown ? counterS() - stationJournal.prepAtS() : 0;
    s.prepConfig = stationJournal.prepChanges() & journal::PREP_CONFIG;
    s.prepConfigSha = stationJournal.prepConfigSha();
    const rnsnode::UsbStatus usb = rnsnode::usbStatus();
    s.computerHeard = computerHeard;
    s.computerS = computerHeard && counterS() > computerAtS ? counterS() - computerAtS : 0;
    s.usbIn = usb.counters.fromComputer;
    s.usbOut = usb.counters.toComputer;
    s.usbDrop = usb.counters.rxDropped + usb.counters.rxTooLarge + usb.counters.txDropped;
    return s;
}

// Rysuje tylko zmienione wiersze w buforze ekranu.
void updateScreen(bool force) {
    ui::Lines lines;
    screenModel.render(screenStatus(), lines);
    for (size_t i = 0; i < ui::LINES; ++i) {
        if (force || strcmp(lines.text[i], shown.text[i]) || lines.inverted[i] != shown.inverted[i]) {
            display.drawLine(static_cast<uint8_t>(i), lines.text[i], lines.inverted[i]);
        }
    }
    shown = lines;
    // Wysyła je pętla po 9 wierszy pikseli na obieg (display.refresh() w stationLoop).
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
    Serial.printf("{\"extcomin\":\"%s\",\"extcomin_ok\":%s,\"counter\":%lu,\"level\":%s,\"software_vcom\":%s,\"refreshes\":%lu,"
                  "\"cs\":%u,\"extcomin_pin\":%u,\"spi_hz\":%lu}\n",
                  platform::EXTCOMIN_SOURCE, boolName(display.extcominOk()), static_cast<unsigned long>(display.extcominCounter()),
                  boolName(display.extcominLevel()), boolName(display.softwareVcom()), static_cast<unsigned long>(display.refreshes()), board::DISPLAY_CS,
                  board::DISPLAY_EXTCOMIN, static_cast<unsigned long>(display.spiHz()));
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
    if (!screenModel.takeChange() || destroyed) return;
    retain();
    const uint32_t lang = static_cast<uint32_t>(screenModel.language()) + 1;
    const uint32_t flags = SETTINGS_FLAGS | (screenModel.muted() ? SETTINGS_MUTED : 0) |
                           ((static_cast<uint32_t>(stationStore.selectedAddress()) << SETTINGS_OBJECT_SHIFT) & SETTINGS_OBJECT_MASK);
    const journal::SmallRecord& saved = stationJournal.settings();
    if (journalOk && (saved.a != lang || saved.b != flags) && !stationJournal.writeSettings(lang, flags)) journalFailed();
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
        if (storeOk && !nodeRole()) app.powerOn();   // bez RTC: czas wyłączenia nieznany (oprogramowanie.md, "Czas")
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
    Serial.printf("{\"fram\":\"%s\",\"id\":\"%s\",\"status\":\"0x%02X\",\"ok\":%s,\"spi_hz\":%lu}\n",
                  fram::partName(id.part), hex, id.status, boolName(framOk), static_cast<unsigned long>(board::FRAM_SPI_HZ));
}

void printInfo() {
    // Pola jak w INFO ze specyfikacji radia; napięcie jest zerowe, bo stanowisko go nie mierzy.
    // uptime_s to zegar z dziennika FRAM (ciągły między restartami), boot_s czas od startu.
    // Wiersz w częściach poniżej 256 znaków (Print::printf rdzenia nRF52, zob. printRns).
    const measure::LinkCounters& c = bench.link();
    Serial.printf("{\"contract\":2,\"profile\":\"%s\",\"radio\":\"%s\",\"mcu\":\"%s\",\"fw\":\"%s\","
                  "\"src\":\"USB\",\"mv\":0,\"tx_wait_ms\":%lu,\"rx_ok\":%lu,\"rx_bad\":%lu,\"tx_drop\":%lu,\"restarts\":%lu,",
                  radiocon::PROFILE, radiocon::NAME, platform::MCU, WICI_FW_VERSION, static_cast<unsigned long>(bench.debtRemainingMs()),
                  static_cast<unsigned long>(c.rxOk), static_cast<unsigned long>(c.rxBad), static_cast<unsigned long>(c.txDrop),
                  static_cast<unsigned long>(stationJournal.starts()));
    Serial.printf("\"bench\":\"%s\",\"prep\":%s,\"silence\":%s,\"radio_ok\":%s,\"p1_ok\":%s,\"fram_ok\":%s,\"journal_ok\":%s,"
                  "\"journal_resets\":%lu,",
                  BENCH, boolName(bench.prep),
                  boolName(silenceAny()), boolName(radiocon::ok()), boolName(radiocon::p1Ok()), boolName(framOk), boolName(journalOk),
                  static_cast<unsigned long>(journalResets));
    radiocon::printProfile();
    Serial.printf("\"tx_power_dbm\":%d,\"uptime_s\":%lu,\"service_s\":%lu,\"boot_s\":%lu,\"screen\":\"%s\",\"lang\":\"%s\","
                  "\"name\":\"%s\",\"reset_reason\":\"0x%08lX\",",
                  radiocon::TX_POWER_DBM, static_cast<unsigned long>(counterS()), static_cast<unsigned long>(serviceS()),
                  static_cast<unsigned long>(platform::uptimeMs() / 1000), ui::screenName(screenModel.screen()), langName(screenModel.language()),
                  stationName, static_cast<unsigned long>(platform::resetReason()));
    Serial.printf("\"rns_state\":\"%s\",\"entropy_ok\":%s,", STACK_STATE_NAMES[static_cast<size_t>(stackState)], boolName(entropyHealthy));
    // Łącze stosu, odbiór w tle i pętla (plan interfejsu LoRa, L6); bez zadania odbioru liczniki zadania są zerowe.
    const radiocon::RxTaskInfo rx = radiocon::rxTaskInfo();
    Serial.printf("\"link\":\"%s\",\"rx_task\":%s,\"rx_armed\":%s,\"rx_ready_ms\":%ld,\"loop_max_ms\":%lu,\"rx_task_loops\":%lu,"
                  "\"rx_service_max_ms\":%lu,\"rx_stalled\":%s,\"rx_mode_lost\":%lu,\"lock_timeouts\":%lu,\"lock_misses\":%lu,",
                  linkName(), boolName(rx.running), boolName(rx.armed), static_cast<long>(rxReadyMs), static_cast<unsigned long>(loopMaxMs),
                  static_cast<unsigned long>(rx.loops), static_cast<unsigned long>((rx.serviceMaxUs + 999) / 1000), boolName(rxStalled),
                  static_cast<unsigned long>(rx.modeLost), static_cast<unsigned long>(platform::radioLockTimeouts()),
                  static_cast<unsigned long>(rx.lockMisses));
    Serial.printf("\"store_ok\":%s,\"register\":%u,\"inbox\":%u,\"head\":%lu,",
                  boolName(storeOk), static_cast<unsigned>(storeOk ? stationStore.requestCount() : 0),
                  static_cast<unsigned>(storeOk ? stationStore.messageCount() : 0), static_cast<unsigned long>(storeOk ? stationStore.head() : 0));
    char usb[rnsnode::USB_JSON_SIZE];
    rnsnode::usbJson(usb, sizeof(usb));
    Serial.print(usb);   // pola węzła stanowiska (interfejs Reticulum przez USB)
    Serial.printf(",\"computer_s\":%ld,", computerHeard ? static_cast<long>(counterS() - computerAtS) : -1L);
    Serial.printf("\"usb_data\":%s,\"usb_in\":%lu,\"usb_out\":%lu,\"usb_rejected\":%lu,\"usb_boot\":\"%s\",\"wdt_s\":%lu,"
                  "\"board\":\"%s\"}\n",
                  boolName(protocol.isConnected()), static_cast<unsigned long>(protocol.stats().linesIn),
                  static_cast<unsigned long>(protocol.stats().linesOut),
                  static_cast<unsigned long>(protocol.stats().rejected), protocol.bootId(), static_cast<unsigned long>(WDT_TIMEOUT_S), BOARD_NAME);
}

// Wejścia w tryb przygotowania (JOURNAL): licznik, licznik czasu przy wejściu, zmiany.
void printPrepLog(char* out, size_t size) {
    snprintf(out, size, "\"prep_entries\":%lu,\"prep_at_s\":%lu,\"prep_changes\":%lu,\"prep_config_sha\":\"%04X\","
             "\"prep_restarted\":%s,\"prep_corrupt\":%s",
             static_cast<unsigned long>(stationJournal.prepEntries()), static_cast<unsigned long>(stationJournal.prepAtS()),
             static_cast<unsigned long>(stationJournal.prepChanges()), static_cast<unsigned>(stationJournal.prepConfigSha()),
             boolName(stationJournal.prepRestarted()), boolName(stationJournal.prepCorrupt()));
}

void printJournal() {
    const journal::SmallRecord& d = stationJournal.debt();
    const journal::SmallRecord& k = stationJournal.clock();
    // Trzy części poniżej 256 znaków (zob. printRns).
    Serial.printf("{\"journal_ok\":%s,\"debt_seq\":%lu,\"debt_ms\":%lu,\"debt_written_at_s\":%lu,\"debt_records\":%lu,",
                  boolName(journalOk), static_cast<unsigned long>(d.seq), static_cast<unsigned long>(d.a),
                  static_cast<unsigned long>(d.b), static_cast<unsigned long>(stationJournal.debtValid()));
    Serial.printf("\"tx_wait_ms\":%lu,\"clock_seq\":%lu,\"uptime_s\":%lu,\"skip_s\":%lu,\"restarts\":%lu,\"event_seq\":%lu,"
                  "\"max_debt_ms\":%lu,\"journal_resets\":%lu,",
                  static_cast<unsigned long>(bench.debtRemainingMs()), static_cast<unsigned long>(k.seq),
                  static_cast<unsigned long>(counterS()), static_cast<unsigned long>(skipS), static_cast<unsigned long>(stationJournal.starts()),
                  static_cast<unsigned long>(stationJournal.eventSeq()), static_cast<unsigned long>(bench.maxDebtMs()),
                  static_cast<unsigned long>(journalResets));
    char prepLog[200];
    printPrepLog(prepLog, sizeof(prepLog));
    Serial.printf("%s}\n", prepLog);
}

// Start dziennika: licznik czasu pracy z przeskokiem 60 s zapisany przed pierwszą ramką i pierwszym
// rekordem, dług do odczekania albo nowy dziennik z największym długiem.
void beginJournal() {
    journalOk = framOk && stationJournal.begin() && stationJournal.startClock();
    if (!journalOk) return;
    counterBaseS = stationJournal.counterAtStart();
    skipS = stationJournal.skipS();
    startServiceS = serviceS();
    bench.attach(&stationJournal, counterS);
    uint32_t debtMs = stationJournal.debt().a;
    if (stationJournal.debtFresh()) {
        // radio.md, "Dostęp do kanału": bez poprawnego rekordu odczekać największy możliwy dług,
        // założyć nowy dziennik i zliczyć zdarzenie w diagnostyce.
        debtMs = bench.maxDebtMs();  // 12 x najdłuższa seria łącza układu
        journalResets = 1;
        stationJournal.writeDebt(debtMs, counterS());
        bench.log("debt journal missing: new journal, max debt");
    }
    bench.restoreDebt(debtMs);
    char text[48];
    snprintf(text, sizeof(text), "start %lu, debt %lu ms", static_cast<unsigned long>(stationJournal.starts()), static_cast<unsigned long>(debtMs));
    bench.log(text);
    // Tryb pracy do badań EMC wraca po restarcie bez trybu przygotowania (measure.h).
    if (stationJournal.emc()) bench.emcResume(stationJournal.emc());
}

void printButtons() {
    Serial.print("{\"buttons\":{");
    for (size_t i = 0; i < 4; ++i) {
        Serial.printf("\"%s\":%s%s", buttonNames[i], boolName(pressed(buttons[i])), i < 3 ? "," : "");
    }
#if defined(WICI_BOARD_N1)
    // Stan linii panelu N1 (krok A3 uruchomienia): true = zwarte do masy.
    Serial.printf("},\"silence_switch\":%s,\"prep_button\":%s,\"silence\":%s,\"prep\":%s,\"alarm_led\":%s}\n",
                  boolName(silenceSwitch()), boolName(pressed(board::BTN_PREP)), boolName(silenceAny()),
                  boolName(bench.prep), boolName(alarmLedOn));
#else
    Serial.println("}}");
#endif
}

void printHelp() {
    Serial.print("{\"commands\":[\"HELP\",\"INFO\"");
    Serial.print(radiocon::helpCommands());
    Serial.print(",\"PREP <0|1>\",\"SILENCE <0|1>\",\"TXCW <s> [CONDUCTED]\",\"TXPKT <n> <len> [<ms>] [ZEROS|ONES] [CONDUCTED]\","
                 "\"RX [<len>]\",\"RXPER\",\"FOFF [<hz>]\",\"P1RX\",\"P1TX <hex>\",\"P1\",\"EMC [<s> <len>|0]\",\"STOP\",\"LOG [<n>]\",\"JOURNAL\",\"BENCH\","
                 "\"FRAM\",\"BTN\","
#if !defined(WICI_BENCH_B) && !defined(WICI_L0)
                 "\"LED <1-4> <0|1>\","  // stanowisko B i L0 (DevKitC) nie mają diod stanu
#endif
                 "\"SCREEN\",\"KEY <UP|DOWN|OK|BACK> [ms]\",\"DISPLAY\","
                 "\"VCOM <0|1>\",\"REBOOT\",\"STORE\",\"USB <json>\",\"APP\",\"LINK <0|1>\",\"RNS\",\"ANNOUNCE\""
#if defined(WICI_BOARD_N1)
                 ",\"LED 5 <0|1>\",\"BUZZ [<ms>] [<hz>]\",\"VTEST\",\"DISPLAY <hz>\""
#endif
#if defined(WICI_RNS_CORE)
                 ",\"RNS SELFTEST\""
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
    // Części poniżej 256 znaków (zob. printRns).
    Serial.printf("{\"link\":%s,\"in_flight\":%u,\"sent\":%lu,\"delivered\":%lu,\"failed\":%lu,\"received\":%lu,\"rejected\":%lu,",
                  boolName(linkAuto), static_cast<unsigned>(app.inFlight()), static_cast<unsigned long>(s.sent),
                  static_cast<unsigned long>(s.delivered), static_cast<unsigned long>(s.failed), static_cast<unsigned long>(s.received),
                  static_cast<unsigned long>(s.rejected));
    uint32_t oldest = 0;
    const size_t unsent = stationStore.unsent(oldest), items = screenHost.itemCount();   // poza printf: kolejność wywołań
    Serial.printf("\"skipped\":%lu,\"bulletins_skipped\":%lu,\"inbox_full\":%lu,\"evicted\":%lu,\"intents\":%u,\"unsent\":%u,"
                  "\"next\":%d,\"test_paused\":%s,\"items\":%u}\n",
                  static_cast<unsigned long>(s.skipped), static_cast<unsigned long>(s.bulletinsSkipped),
                  static_cast<unsigned long>(s.inboxFull), static_cast<unsigned long>(s.evicted),
                  static_cast<unsigned>(stationStore.activeIntents()), static_cast<unsigned>(unsent), app.nextToSend(),
                  boolName(app.testPaused()), static_cast<unsigned>(items));
}

#if defined(WICI_RNS_CORE)
uint32_t selftestMicros() { return static_cast<uint32_t>(micros()); }

// RNS SELFTEST: wszystkie próby samotestu rdzenia z czasem w µs, wiersz JSON na próbę i wynik
// (README, „Samotest rdzenia na płytce”). Trwa kilka sekund; pętla stacji w tym czasie stoi.
void printSelftest() {
    coreselftest::Result results[coreselftest::COUNT];
    const bool ok = coreselftest::run(results, coreselftest::COUNT, selftestMicros);
    for (const coreselftest::Result& r : results) {
        Serial.printf("{\"selftest\":\"%s\",\"ok\":%s,\"us\":%lu}\n", r.name, boolName(r.ok), static_cast<unsigned long>(r.us));
    }
    Serial.printf("{\"selftest_ok\":%s,\"entropy_ok\":%s,\"version\":\"%s\"}\n", boolName(ok), boolName(entropyHealthy),
                  WICI_FW_VERSION);
}
#endif

// Stan stosu Reticulum: tablice, pula pamięci, system plików FRAM, liczniki interfejsu P1.
void printRns() {
    const rnsnode::Status s = rnsnode::status();
    char address[2 * store::HASH + 1], identity[2 * store::HASH + 1], iface[rnsnode::INTERFACE_JSON_SIZE];
    hexstr::encode(rnsnode::address(), store::HASH, address);
    hexstr::encode(rnsnode::identityHash(), store::HASH, identity);
    rnsnode::interfaceJson(iface, sizeof(iface));
    // Wiersz ma ponad 256 znaków, a Print::printf rdzenia Adafruit nRF52 formatuje do bufora 256 B
    // (dłuższy wynik wypisuje ze śmieciami): części poniżej 256 znaków i opis interfejsu przez print.
    Serial.printf("{\"rns\":%s,\"online\":%s,\"address\":\"%s\",\"identity\":\"%s\",\"identity_new\":%s,\"identity_lost\":%s,\"paths\":%u,",
                  boolName(rnsOk), boolName(s.online), address, identity, boolName(s.identityNew), boolName(s.identityLost),
                  static_cast<unsigned>(s.paths));
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
                  announcePolicy.scheduled() ? static_cast<long>(announcePolicy.nextS() - counterS()) : -1L,
                  static_cast<unsigned long>(s.queueWaitMs), static_cast<unsigned long>(s.bitrate));
    Serial.print(iface);
    char usb[rnsnode::USB_JSON_SIZE];
    rnsnode::usbJson(usb, sizeof(usb));
    Serial.print(",");
    Serial.print(usb);
    // Zapas stosu zadania odbioru (stacja L0; -1 bez zadania).
    Serial.printf(",\"computer_s\":%ld,\"rx_stack_free\":%ld}\n", computerHeard ? static_cast<long>(counterS() - computerAtS) : -1L,
                  static_cast<long>(radiocon::rxTaskInfo().stackFree));
}

void printStore() {
    const config::Config& c = stationStore.config();
    const store::Meta& m = stationStore.meta();
    const store::Diagnostics& d = stationStore.diagnostics();
    char epoch[2 * store::EPOCH + 1];
    hexstr::encode(m.epoch, store::EPOCH, epoch);
    // Części poniżej 256 znaków (zob. printRns); adres z laptopa z sekwencjami ucieczki.
    Serial.printf("{\"store_ok\":%s,\"configured\":%s,\"config_seq\":%lu,\"role\":\"%s\",\"identity_saved\":%s,", boolName(storeOk),
                  boolName(stationStore.configured()), static_cast<unsigned long>(c.seq),
                  c.role == config::Role::NODE ? "wezel" : "stacja", boolName(stationStore.identitySaved()));
    jsonprint::field(Serial, "address", stationStore.address());   // obiekt wybrany na ekranie
    Serial.printf(",\"addresses\":%u,\"selected\":%u,\"receiver\":\"%s\",\"phrases\":%u,\"stations\":%u,",
                  static_cast<unsigned>(stationStore.addressCount()), static_cast<unsigned>(stationStore.selectedAddress()),
                  m.receiver == config::BACKUP ? "backup" : "main", c.phraseCount, c.stations);
    Serial.printf("\"epoch\":\"%s\",\"head\":%lu,\"min\":%lu,\"tomb_floor\":%lu,\"register\":%u,\"inbox\":%u,\"unread\":%u,",
                  epoch, static_cast<unsigned long>(stationStore.head()), static_cast<unsigned long>(stationStore.minEvent()),
                  static_cast<unsigned long>(m.tombFloor), static_cast<unsigned>(stationStore.requestCount()),
                  static_cast<unsigned>(stationStore.messageCount()), static_cast<unsigned>(stationStore.unread()));
    Serial.printf("\"corrupt_slots\":%lu,\"replayed\":%lu,\"scrubbed\":%lu,\"config_corrupt\":%s,"
                  "\"usb_synced\":%s,\"usb_stored\":%lu,\"usb_overflow\":%lu,\"usb_resends\":%lu}\n",
                  static_cast<unsigned long>(d.corruptSlots), static_cast<unsigned long>(d.replayed), static_cast<unsigned long>(d.scrubbed),
                  boolName(d.configCorrupt), boolName(protocol.synced()), static_cast<unsigned long>(protocol.stats().stored),
                  static_cast<unsigned long>(protocol.stats().overflow), static_cast<unsigned long>(protocol.stats().resends));
}

void handle(char* cmd) {
    // USB <wiersz JSON>: wiersz protokołu danych podany przez port diagnostyki (próby z jednym portem);
    // treść zostaje w oryginalnej wielkości liter.
    if (!strncasecmp(cmd, "USB ", 4)) {
        if (!storeOk) { printError("store not ready"); return; }
        if (!protocol.acceptsInput()) { printError("usb output busy"); return; }
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
        // Na stacji tryb przygotowania włącza przycisk pod naklejką serwisową; na stanowisku
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
        bool on = false;  // jak przełącznik CISZA (na płytce N1 do następnego przełączenia)
        if (!cmdargs::parseFlag(words[0], on)) { printError("SILENCE <0|1>"); return; }
        setSwitchSilence(on, " (command)");
        Serial.printf("{\"silence\":%s,\"switch\":%s}\n", boolName(silenceAny()), boolName(switchSilence));
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
    } else if (!strcmp(cmd, "EMC")) {
        // EMC: stan; EMC 0: koniec (rekord w dzienniku skasowany); EMC <s> <len>: start w trybie przygotowania.
        if (n == 1) {
            uint32_t zero = 1;
            if (!cmdargs::parseUint(words[0], 0, 0, zero)) { printError("EMC [<s> <len>|0]"); return; }
            const char* error = bench.emcStop();   // rekord został w dzienniku: tryb wróci po restarcie
            if (error) { printError(error); return; }
        } else if (n == 2) {
            uint32_t seconds = 0, length = 0;
            if (!cmdargs::parseUint(words[0], 1, measure::EMC_PERIOD_MAX_S, seconds) || !cmdargs::parseUint(words[1], 0, 255, length)) {
                printError("EMC [<s> <len>|0]");
                return;
            }
            const char* error = bench.emcStart(seconds, static_cast<uint8_t>(length));
            if (error) { printError(error); return; }
        } else if (n) { printError("EMC [<s> <len>|0]"); return; }
        bench.printEmc();
    } else if (!strcmp(cmd, "STOP")) {
        const char* emcError = bench.emcStop();  // STOP kończy też tryb EMC
        bench.stop();
        if (emcError) Serial.printf("{\"stop\":true,\"emc_error\":\"%s\"}\n", emcError);
        else Serial.println("{\"stop\":true}");
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
        // Kawałki po 9 wierszy z przerwą: magistrala wolna dla zadania odbioru między nimi.
        while (display.refresh()) delay(1);
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
#if defined(WICI_RNS_CORE)
    else if (!strcmp(cmd, "RNS") && n == 1 && !strcmp(words[0], "SELFTEST")) printSelftest();
#endif
    else if (!strcmp(cmd, "RNS")) printRns();
    else if (!strcmp(cmd, "ANNOUNCE")) {
        // Ogłoszenie na polecenie: wychodzi przy najbliższym obiegu, poza ciszą radiową i z kodem IFAC.
        if (!host.announce()) printError("rns not running");
        else printRns();
    }
    else if (!strcmp(cmd, "VCOM") && n == 1) {
        bool on = false;
        if (!cmdargs::parseFlag(words[0], on)) { printError("VCOM <0|1>"); return; }
#if defined(WICI_BOARD_N1)
        // EXTMODE panelu na N1 jest na stałe w stanie wysokim: bit VCOM nic by nie zmienił.
        printError("VCOM: EXTMODE tied high on N1");
#else
        display.softwareVcom(on);  // przewody: tylko przy pinie EMD (EXTMODE) w stanie niskim
        printDisplay();
#endif
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

// Stos Reticulum: tożsamość i tablice w FRAM, zegar stosu z licznika czasu pracy; kod IFAC
// z konfiguracji (bez niego interfejs P1 nie nadaje). Tożsamość: znacznik w rekordzie formatu
// FRAM; brak klucza przy znaczniku zostawia stację bez stosu (blad_pamieci). Ogłoszenie startowe po 0–120 s.
void beginStack() {
    // Wpis o źródle entropii przy każdym starcie z niezdrowym odczytem: także ze stacją z tożsamością
    // i bez FRAM.
    if (!entropyHealthy) bench.log(entropyTimeout ? "entropy source not responding" : "entropy source failed health test");
    if (!framOk || !journalOk || !storeOk) {
        stackState = StackState::UNAVAILABLE;
        bench.log("rns not started: FRAM, journal or store unavailable");
        return;
    }
    rnsnode::Hooks hooks;
    hooks.packet = onPacket;
    hooks.receipt = onReceipt;
    hooks.log = onStackLog;
    const config::Config& c = stationStore.config();
    applyReceivers();   // przed startem: porządkowanie tablic przy starcie nie usuwa wpisów odbiorcy
    rnsnode::setNode(c.role == config::Role::NODE && stationStore.configured());
    applySilence();
    // Klucz tożsamości powstaje z generatora stacji: bez zdrowego ziarna nowej tożsamości nie tworzymy
    // (zapisana tożsamość nie zależy od ziarna). Klucz bez znacznika po zaniku zasilania też czeka.
    if (!entropyHealthy && !stationStore.identitySaved()) {
        stackState = StackState::ENTROPY_FAILED;
        bench.log("rns not started: no healthy seed for a new identity");
        return;
    }
#if defined(WICI_RNS_CORE)
    // Samotest kryptografii rdzenia przed tożsamością (core_selftest.h): przy niezgodności stos nie startuje.
    // Czas samotestu w dzienniku (tools/board_selftest.py go odczytuje): o tyle później startują stos i radio.
    coreselftest::Result results[coreselftest::QUICK];
    const uint64_t selftestStartMs = platform::uptimeMs();
    if (!coreselftest::run(results, coreselftest::QUICK, selftestMicros)) {
        stackState = StackState::SELFTEST_FAILED;
        for (const coreselftest::Result& r : results) {
            if (r.ok) continue;
            char text[64];
            snprintf(text, sizeof(text), "rns not started: core selftest %s failed", r.name);
            bench.log(text);
        }
        return;
    }
    char selftestText[48];
    snprintf(selftestText, sizeof(selftestText), "core selftest ok %lu ms",
             static_cast<unsigned long>(platform::uptimeMs() - selftestStartMs));
    bench.log(selftestText);
#endif
    uint8_t seed[32];
    stationRandom(seed, sizeof(seed));
    rnsOk = rnsnode::begin(memory, benchRadio, c.ifac, static_cast<uint64_t>(counterS()) * 1000, stationStore.identitySaved(), seed, hooks);
    drbg::wipe(seed, sizeof(seed));
    if (!rnsOk) {
        const bool lost = rnsnode::status().identityLost;
        stackState = lost ? StackState::IDENTITY_LOST : StackState::START_FAILED;
        bench.log(lost ? "rns not started: identity lost (destroy data)" : "rns start failed");
        return;
    }
    stackState = StackState::RUNNING;
    // Znacznik także po starcie z kluczem bez znacznika (zanik zasilania między zapisem klucza a znacznikiem).
    if (!stationStore.setIdentitySaved()) bench.log("identity flag not saved");
    uint32_t random = 0;
    stationRandom(reinterpret_cast<uint8_t*>(&random), sizeof(random));
    announcePolicy.begin(counterS(), random);
    bench.log(rnsnode::node() ? "rns started as receiving station node" : rnsnode::status().identityNew ? "rns started, new identity" : "rns started");
}

// Ziarno generatora stacji: 48 B entropii ze źródła sprzętowego i identyfikator układu jako nonce
// (na ESP32-S3 przed konfiguracją ADC pomiaru VTEST, platform.h).
// Odczyt bez testu zdrowia (drbg::healthy) jest powtarzany do trzech razy; generator dostaje ziarno także
// po trzeciej odmowie (identyfikatory zgłoszeń, opóźnienia), ale stos nie tworzy wtedy tożsamości (beginStack).
void seedGenerator() {
    uint8_t entropy[drbg::SEED_ENTROPY];
    uint32_t id[2];
    for (int attempt = 0; attempt < 3 && !entropyHealthy; ++attempt) {
        const bool answered = platform::entropy(entropy, sizeof(entropy));
        entropyTimeout = entropyTimeout || !answered;
        entropyHealthy = answered && drbg::healthy(entropy, sizeof(entropy));
    }
    platform::chipId(id);
    generator.seed(entropy, sizeof(entropy), reinterpret_cast<const uint8_t*>(id), sizeof(id));
    drbg::wipe(entropy, sizeof(entropy));
}

}  // namespace

// Bajty losowe łącza P1 (odroczenia, identyfikatory datagramów) z generatora stacji.
void measure::randomBytes(uint8_t* out, size_t count) { stationRandom(out, count); }

void stationSetup() {
    seedGenerator();
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
    radiocon::startRxTask();  // stacja L0: odbiór w tle od tej chwili; dalej pętla dotyka układu pod blokadą
    framOk = memory.identify().part != fram::Part::UNKNOWN;
    beginJournal();
    ledWrite(board::LED_FRAM, framOk && journalOk);  // LED3 świeci dopiero z działającym dziennikiem
    if (journalOk) {
        stationStore.now(serviceS());
        const store::Begin begun = stationStore.begin();
        storeOk = begun == store::Begin::OK || begun == store::Begin::NEW;
        // ZNISZCZ DANE przerwane i dokończone w begin() skasowało zegar: licznik czasu od nowa.
        if (stationJournal.counterAtStart() < counterBaseS && stationJournal.startClock()) {
            counterBaseS = stationJournal.counterAtStart();
            skipS = stationJournal.skipS();
            startServiceS = serviceS();
            stationStore.now(serviceS());
        }
        char text[40];
        snprintf(text, sizeof(text), "store: %s", store::beginName(begun));
        bench.log(text);
    }
    protocol.begin();
    beginStack();
    if (storeOk && !nodeRole()) app.stationEvent(store::RESTART, stationJournal.starts());
    bench.onDatagram(onDatagram, nullptr);
    bench.onTxDone(onTxDone, nullptr);
    // Łącze stosu w odbiorze od startu, przed ekranem (radio niezależne od ekranu, gotowość ≤60 s).
    if (radioWorks() && !bench.linkRxStart() && rnsOk) rxReadyMs = static_cast<int32_t>(platform::uptimeMs());
    const bool extcominOk = display.begin();  // CLEAR czyści pamięć ekranu
#if defined(WICI_BOARD_N1)
    // Bez EXTCOMIN z licznika panel dostałby składową stałą (EXTMODE na stałe wysoki): zostaje wyłączony.
    if (extcominOk) digitalWrite(board::DISPLAY_DISP, HIGH);
    else bench.log("display off: EXTCOMIN timer failed");
#else
    if (!extcominOk) bench.log("EXTCOMIN timer failed");
#endif
    // Bez magazynu ekran nie ma kreatora ani wiadomości, ale alarm awarii radia działa.
    if (storeOk) screenModel.attach(&screenHost);
    else screenModel.attachAlarms(&screenHost);
    beginScreen();
    syncButtons();
    if (platform::resetByWatchdog()) bench.log("restart by watchdog");
    platform::beginWatchdog(WDT_TIMEOUT_S);
}

// Czas obiegu pętli do loop_max_ms (INFO).
struct PassTimer {
    uint32_t startMs = millis();
    ~PassTimer() {
        const uint32_t ms = millis() - startMs;
        if (ms > loopMaxMs) loopMaxMs = ms;
    }
};

void stationLoop() {
    PassTimer passTimer;
    static uint32_t lastBeat = 0;
    static bool beat = false;
    static bool reported = false;
    static bool radioLed = false;
    const uint32_t now = millis();
    platform::feedWatchdog();
    platform::uptimeMs();  // licznik 64-bitowy liczy przejścia przez zero przy każdym obiegu
    bench.debtRemainingMs();   // odczekany dług gaśnie, zanim millis() przejdzie przez 2^31 ms
    if (now - lastBeat >= 500) {
        lastBeat = now;
        beat = !beat;
        ledWrite(board::LED_HEARTBEAT, beat);
    }
    // rxArmed: odbiór stosu uzbrojony; polecenia diagnostyczne, tryb przygotowania, EMC i halt (rnsOk) go kasują.
    const bool armed = rnsOk && bench.stackRxArmed();
    radiocon::setRxArmed(armed);
    if (armed && rxReadyMs < 0) rxReadyMs = static_cast<int32_t>(platform::uptimeMs());
    // LED2: P1 gotowe; zapis przy zmianie, więc LED 2 z portu obowiązuje do następnej zmiany.
    static uint32_t radioCheckMs = 0;
    if (now - radioCheckMs >= radiocon::CHECK_MS && !bench.transmitting()) {
        radioCheckMs = now;
        // Kontrola i ponowne uzbrojenie odbioru pod jedną blokadą radia (zadanie odbioru pomija wtedy obiegi).
        platform::RadioLock lock(measure::RADIO_LOCK_WAIT_MS);
        if (radiocon::check()) {
            bench.log("radio check: receive re-armed (reconfigured or left RX)");
            bench.linkRxStart();  // odbiór stosu wraca od razu po rekonfiguracji (P1 i LoRa)
        }
    }
    rxStalled = radiocon::rxStalled(bench.transmitting(), now);
    const bool radio = radioWorks();
    if (radio != radioLed) {
        radioLed = radio;
        ledWrite(board::LED_RADIO, radio);
    }
    screenHost.setRadioFault(radioFault());     // alarm radio_awaria (oprogramowanie.md, ekran główny); także tryb EMC i zadanie odbioru
    screenHost.setStackFault(stackFault());     // alarm brak_lacznosci
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
    if (journalOk && !destroyed && now - lastClock >= CLOCK_WRITE_MS) {
        lastClock = now;
        if (!stationJournal.writeClock(counterS())) journalFailed();
    }
    bench.p1Ready = radio;
    // Także przy układzie uznanym za niesprawny w trakcie nośnej albo serii (np. polecenie RADIO):
    // koniec TXCW i TXPKT po czasie nie może czekać na odpowiedź układu.
    if (radiocon::ok() || bench.transmitting()) bench.poll();
    if (rnsOk) {
        rnsnode::loop(now);
        pollAnnounce();
    }
    static uint32_t lastApp = 0;
    if (storeOk && now - lastApp >= APP_POLL_MS) {  // przegląd rejestru co 100 ms, nie w każdym obiegu
        lastApp = now;
        stationStore.now(serviceS());
        stationStore.maintain();   // gniazda starej epoki po ZAMKNIJ ZDARZENIE (jedna transakcja na obieg)
        if (linkAuto && radiocon::ok() && !nodeRole()) app.poll();
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
    display.refresh();  // dalsze kawałki po 9 wierszy (sharp::LINES_PER_REFRESH), jeden na obieg
    display.maintain(now);
    // Interfejs danych: otwarcie portu wysyła sync, zamknięcie odrzuca niepełny wiersz. Bez magazynu
    // protokół też odpowiada (zapis kończy się odmową "memory"), żeby laptop nie czekał bez odpowiedzi.
    // Węzeł stanowiska poza trybem przygotowania: ramki KISS do komputera stanowiska zamiast protokołu.
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
        if (kiss) {
            char chunk[64];
            while (SerialData.available()) {
                size_t n = 0;
                while (n < sizeof(chunk) && SerialData.available()) chunk[n++] = static_cast<char>(SerialData.read());
                rnsnode::usbFeed(reinterpret_cast<const uint8_t*>(chunk), n, now);
            }
            drain(SerialData, kissOutput);
        } else {
            // Bajt po bajcie, dopóki odpowiedź zmieści się w kolejce: koniec wiersza może dać do dwóch wierszy.
            while (protocol.acceptsInput() && SerialData.available()) {
                const char c = static_cast<char>(SerialData.read());
                protocol.feed(&c, 1, now);
            }
        }
    }
    if (!kiss) protocol.poll(now);   // także bez portu: limit potwierdzenia przyciskiem i transferu
    // Odpowiedzi na interfejs danych; bez otwartego portu danych albo przy ramkach KISS na diagnostykę
    // (polecenie USB z portu diagnostyki).
    if (dataOpen && !kiss) drain(SerialData, protocol);
    else drain(Serial, protocol);
    if (nodeRole()) {
        const uint32_t packets = rnsnode::usbStatus().counters.fromComputer;
        if (packets != computerPackets) {
            computerPackets = packets;
            computerHeard = true;
            computerAtS = counterS();
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
