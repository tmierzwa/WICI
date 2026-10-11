// SPDX-License-Identifier: MIT
// Wirtualna płytka (vboard.h) i interfejs środowiska. Piny i układy według firmware/src/board.h
// (stanowisko B na N1: WICI_BENCH_B), więc to samo przypisanie, poziomy aktywne i podciągnięcia co na
// płytce. Jedna instancja WebAssembly albo jeden proces = jedno urządzenie; środowisko woła sim_run()
// do kolejnych chwil czasu bezwzględnego, a ramki radiowe między urządzeniami przenosi samo.
//
// Polecenia środowiska (sim_command, wiersz tekstu, odpowiedź tekst):
//   boot <czas µs> <przyczyna> <ziarno>   chwila włączenia (czas bezwzględny), esp_reset_reason, ziarno płytki
//   pin <numer> <0|1>                      poziom wejścia sterowanego z zewnątrz (przycisk, przełącznik)
//   pins                                   numery pinów panelu z board.h (JSON)
//   reads <numer>                          liczba odczytów pinu przez program (naciśnięcia skryptów)
//   usb <0|1> open|close                   port CDC otwarty przez komputer (0 diagnostyka, 1 dane)
//   usbin <0|1> <hex>                      bajty od komputera; usbout <0|1>: bajty do komputera (hex)
//   air                                    ramki nadane od ostatniego odczytu (JSON)
//   airin <JSON ramki>                     ramka innego urządzenia (moc już u tego odbiorcy)
//   fault radio|fram <0|1>                 awaria układu
//   events                                 dioda, brzęczyk, ekran, restart od ostatniego odczytu (JSON)
//   screen                                 tekst ekranu odczytany z pikseli panelu (JSON)
//   state                                  stan płytki (JSON)
#include "vboard.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <deque>
#include <string>
#include <vector>

#include "Arduino.h"
#include "SPI.h"
#include "board.h"
#include "chips.h"
#include "font.h"
#include "nvs.h"

#include <map>

USBCDC Serial(0);
SPIClass SPI;
EspClass ESP;

extern char __start_wici_noinit[];
extern char __stop_wici_noinit[];

void setup();
void loop();

namespace vb {

namespace {

constexpr size_t FRAM_BYTES = 512 * 1024;
constexpr size_t USB_BUFFER = 8192;

struct Pin {
    uint8_t mode = INPUT;
    bool out = false;       // wyjście MCU
    bool external = true;   // poziom z zewnątrz (dla wejść z podciągnięciem domyślnie wysoki)
    bool driven = false;    // poziom wejścia ustawiony przez środowisko
    uint32_t reads = 0;     // odczyty pinu przez program (do naciśnięć skryptów ćwiczeń)
};

struct Usb {
    bool open = false;
    std::deque<uint8_t> in;
    std::string out;
};

struct Board {
    uint64_t bootWorldUs = 0;
    uint64_t uptimeUs = 0;
    uint32_t reason = 1;
    uint64_t rng = 0x9E3779B97F4A7C15ull;
    uint32_t seed = 1;
    Pin pins[64];
    Usb usb[2];
    std::vector<uint8_t> fram = std::vector<uint8_t>(FRAM_BYTES, 0xFF);
    chips::Fram framChip{fram};
    chips::Sharp lcd;
    chips::S2lp radio;
    vb::SpiDevice* selected = nullptr;
    bool started = false;
    bool rebooted = false;
    uint32_t rebootReason = 0;
    std::string rebootWhy;
    bool watchdog = false;
    uint64_t watchdogUs = 0;
    uint64_t fedUs = 0;
    bool extcomin = false;
    uint8_t extcominPin = 0;
    uint64_t extcominSinceUs = 0;
    uint64_t toneEndUs = 0;
    std::vector<std::string> events;
    std::string reply;
    std::map<std::string, std::map<std::string, std::string>> nvs;   // flash ESP32-S3: przestrzeń -> klucz -> blob
    std::vector<std::string> nvsHandles;
};

Board& b() {
    static Board board;
    return board;
}

uint64_t splitmix(uint64_t& state) {
    uint64_t z = (state += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}

void event(const std::string& json) {
    Board& d = b();
    char t[48];
    snprintf(t, sizeof(t), "{\"t\":%llu,", static_cast<unsigned long long>(d.bootWorldUs + d.uptimeUs));
    d.events.push_back(t + json.substr(1));
    if (d.events.size() > 4000) d.events.erase(d.events.begin(), d.events.begin() + 2000);
}

// Układ wybrany linią CS: FRAM i S2-LP aktywne stanem niskim, ekran Sharp stanem wysokim.
vb::SpiDevice* chipOn(uint8_t pin, bool high) {
    Board& d = b();
    if (pin == board::FRAM_CS && !high) return &d.framChip;
    if (pin == board::RADIO_CS && !high) return &d.radio;
    if (pin == board::DISPLAY_CS && high) return &d.lcd;
    return nullptr;
}

bool isCs(uint8_t pin) { return pin == board::FRAM_CS || pin == board::RADIO_CS || pin == board::DISPLAY_CS; }

bool level(uint8_t pin) {
    Board& d = b();
    if (pin >= 64) return false;
    const Pin& p = d.pins[pin];
    if (d.extcomin && pin == d.extcominPin) return ((d.uptimeUs - d.extcominSinceUs) / 500000) & 1;
    if (p.mode == OUTPUT) return p.out;
    if (pin == board::RADIO_GPIO0) return d.radio.gpio(0x00);
    if (pin == board::RADIO_GPIO1) return d.radio.gpio(0x01);
    if (pin == board::RADIO_GPIO2) return d.radio.gpio(0x02);
    if (pin == board::RADIO_GPIO3) return d.radio.gpio(0x03);
    if (p.driven) return p.external;
    return p.mode == INPUT_PULLUP || p.mode == INPUT;   // podciągnięcia na płytce N1 (przyciski, CISZA)
}

}  // namespace

uint64_t worldUs() { return b().bootWorldUs + b().uptimeUs; }
uint64_t nowUs() { return b().uptimeUs; }

void sleepUs(uint64_t us) {
    Board& d = b();
    d.uptimeUs += us;
    d.radio.tick(worldUs());
    if (d.toneEndUs && d.uptimeUs >= d.toneEndUs) d.toneEndUs = 0;
    if (d.watchdog && d.uptimeUs - d.fedUs > d.watchdogUs) {
        event("{\"kind\":\"watchdog\"}");
        throw Reboot{6};   // ESP_RST_TASK_WDT
    }
}

void pinMode(uint8_t pin, uint8_t mode) {
    if (pin < 64) b().pins[pin].mode = mode;
}

void digitalWrite(uint8_t pin, bool high) {
    Board& d = b();
    if (pin >= 64) return;
    Pin& p = d.pins[pin];
    const bool was = p.out;
    p.out = high;
    if (isCs(pin) && was != high) {
        if (d.selected) d.selected->deselect();
        d.selected = chipOn(pin, high);
        if (d.selected) d.selected->select();
    }
    if (pin == board::RADIO_SDN) d.radio.setShutdown(high);
    if (was != high && (pin == board::LED_ALARM || pin == board::DISPLAY_DISP)) {
        char e[80];
        snprintf(e, sizeof(e), "{\"kind\":\"%s\",\"on\":%s}", pin == board::LED_ALARM ? "led" : "disp", high ? "true" : "false");
        event(e);
    }
}

bool digitalRead(uint8_t pin) {
    if (pin < 64) ++b().pins[pin].reads;
    return level(pin);
}

int analogRead(uint8_t) { return 0; }

void tone(uint8_t pin, unsigned hz, unsigned long ms) {
    if (pin != board::BUZZER) return;
    char e[80];
    snprintf(e, sizeof(e), "{\"kind\":\"tone\",\"hz\":%u,\"ms\":%lu}", hz, ms);
    event(e);
    b().toneEndUs = hz ? b().uptimeUs + ms * 1000ull : 0;
}

uint32_t random32() { return static_cast<uint32_t>(splitmix(b().rng) >> 32); }

void spiBegin() {}

uint8_t spiTransfer(uint8_t byte, bool lsbFirst, uint8_t mode, uint32_t hz) {
    Board& d = b();
    // Bajt trwa 8 taktów magistrali; tryb inny niż 0 daje przesunięte bity (wszystkie układy N1: tryb 0).
    sleepUs(hz ? (8000000ull + hz - 1) / hz / 1 : 0);
    auto reverse = [](uint8_t v) {
        v = static_cast<uint8_t>((v & 0xF0) >> 4 | (v & 0x0F) << 4);
        v = static_cast<uint8_t>((v & 0xCC) >> 2 | (v & 0x33) << 2);
        return static_cast<uint8_t>((v & 0xAA) >> 1 | (v & 0x55) << 1);
    };
    if (!d.selected) return 0xFF;
    uint8_t wire = lsbFirst ? reverse(byte) : byte;
    if (mode != 0) wire = static_cast<uint8_t>(wire << 1);
    const uint8_t back = d.selected->exchange(wire);
    return lsbFirst ? reverse(back) : back;
}

bool usbOpen(uint8_t itf) { return itf < 2 && b().usb[itf].open; }
int usbAvailable(uint8_t itf) { return itf < 2 ? static_cast<int>(b().usb[itf].in.size()) : 0; }
int usbRead(uint8_t itf) {
    if (itf > 1 || b().usb[itf].in.empty()) return -1;
    const uint8_t c = b().usb[itf].in.front();
    b().usb[itf].in.pop_front();
    return c;
}
int usbPeek(uint8_t itf) { return itf > 1 || b().usb[itf].in.empty() ? -1 : b().usb[itf].in.front(); }
size_t usbWrite(uint8_t itf, const uint8_t* data, size_t n) {
    if (itf > 1) return 0;
    Usb& u = b().usb[itf];
    // Zamknięty port: USBCDC::write w Arduino-ESP32 nie przyjmuje bajtów, gdy komputer nie jest
    // podłączony (wynik 0); oprogramowanie i tak pisze tylko tyle, ile zwraca availableForWrite().
    if (!u.open) return 0;
    const size_t room = USB_BUFFER > u.out.size() ? USB_BUFFER - u.out.size() : 0;
    const size_t take = n < room ? n : room;
    u.out.append(reinterpret_cast<const char*>(data), take);
    return take;
}
int usbWritable(uint8_t itf) {
    if (itf > 1) return 0;
    const Usb& u = b().usb[itf];
    return u.open ? static_cast<int>(USB_BUFFER - u.out.size()) : 0;
}

void reboot(const char* why) {
    b().rebootWhy = why;
    throw Reboot{3};   // ESP_RST_SW
}

void watchdogBegin(uint32_t seconds) {
    Board& d = b();
    d.watchdog = true;
    d.watchdogUs = seconds * 1000000ull;
    d.fedUs = d.uptimeUs;
}
void feedTaskWatchdog() { b().fedUs = b().uptimeUs; }
uint32_t heapSize() { return 327680; }
uint32_t heapFree() { return 196608; }
uint32_t resetReason() { return b().reason; }

void chipId(uint8_t mac[6]) {
    // Adres MAC z ziarna płytki (Espressif OUI 0x7C:DF:A1).
    mac[0] = 0x7C; mac[1] = 0xDF; mac[2] = 0xA1;
    mac[3] = static_cast<uint8_t>(b().seed >> 16); mac[4] = static_cast<uint8_t>(b().seed >> 8); mac[5] = static_cast<uint8_t>(b().seed);
}

void entropy(uint8_t* out, size_t count) {
    for (size_t i = 0; i < count; ++i) out[i] = static_cast<uint8_t>(random32());
}

bool extcominStart(uint8_t pin) {
    Board& d = b();
    if (d.extcomin) return true;
    d.extcomin = true;
    d.extcominPin = pin;
    d.extcominSinceUs = d.uptimeUs;
    return true;
}
uint32_t extcominTicks() {
    const Board& d = b();
    return d.extcomin ? static_cast<uint32_t>((d.uptimeUs - d.extcominSinceUs) / 1000) % 1000 : 0;
}

}  // namespace vb

// ---- NVS (flash ESP32-S3) ----

esp_err_t nvs_open(const char* name, nvs_open_mode_t, nvs_handle_t* handle) {
    vb::Board& d = vb::b();
    d.nvsHandles.push_back(name);
    *handle = static_cast<nvs_handle_t>(d.nvsHandles.size());
    return ESP_OK;
}
esp_err_t nvs_get_blob(nvs_handle_t handle, const char* key, void* out, size_t* length) {
    vb::Board& d = vb::b();
    if (!handle || handle > d.nvsHandles.size()) return ESP_ERR_NVS_NOT_FOUND;
    const auto& space = d.nvs[d.nvsHandles[handle - 1]];
    const auto it = space.find(key);
    if (it == space.end()) return ESP_ERR_NVS_NOT_FOUND;
    if (!out) { *length = it->second.size(); return ESP_OK; }
    if (*length < it->second.size()) return ESP_ERR_NVS_INVALID_LENGTH;
    memcpy(out, it->second.data(), it->second.size());
    *length = it->second.size();
    return ESP_OK;
}
esp_err_t nvs_set_blob(nvs_handle_t handle, const char* key, const void* value, size_t length) {
    vb::Board& d = vb::b();
    if (!handle || handle > d.nvsHandles.size()) return ESP_ERR_NVS_NOT_FOUND;
    d.nvs[d.nvsHandles[handle - 1]][key] = std::string(static_cast<const char*>(value), length);
    return ESP_OK;
}
esp_err_t nvs_erase_all(nvs_handle_t handle) {
    vb::Board& d = vb::b();
    if (handle && handle <= d.nvsHandles.size()) d.nvs[d.nvsHandles[handle - 1]].clear();
    return ESP_OK;
}
esp_err_t nvs_commit(nvs_handle_t) { return ESP_OK; }
void nvs_close(nvs_handle_t) {}

// ---- interfejs środowiska ---------------------------------------------------------------------

namespace {

using vb::b;

std::string hex(const uint8_t* data, size_t n) {
    static const char digits[] = "0123456789abcdef";
    std::string out(2 * n, '0');
    for (size_t i = 0; i < n; ++i) { out[2 * i] = digits[data[i] >> 4]; out[2 * i + 1] = digits[data[i] & 15]; }
    return out;
}
std::vector<uint8_t> unhex(const char* text) {
    std::vector<uint8_t> out;
    for (const char* p = text; p[0] && p[1]; p += 2) {
        auto v = [](char c) { return c <= '9' ? c - '0' : (c | 32) - 'a' + 10; };
        out.push_back(static_cast<uint8_t>(v(p[0]) << 4 | v(p[1])));
    }
    return out;
}

std::string frameJson(const chips::AirFrame& f) {
    char head[400];
    snprintf(head, sizeof(head),
             "{\"id\":%u,\"start\":%llu,\"sync_at\":%llu,\"end\":%llu,\"freq\":%.1f,\"rate\":%.3f,\"sync\":%u,\"sync_bits\":%u,"
             "\"dbm\":%d,\"carrier\":%s,\"aborted\":%s,\"payload\":\"",
             f.id, static_cast<unsigned long long>(f.startUs), static_cast<unsigned long long>(f.syncUs == UINT64_MAX ? 0 : f.syncUs),
             static_cast<unsigned long long>(f.endUs == UINT64_MAX ? 0 : f.endUs), f.freqHz, f.rate, f.sync, f.syncBits, f.dbm,
             f.carrier ? "true" : "false", f.aborted ? "true" : "false");
    return head + hex(f.payload.data(), f.payload.size()) + "\"}";
}

// Prosty odczyt pól liczbowych i napisu z JSON ramki (format z frameJson).
double field(const char* json, const char* key) {
    char k[32];
    snprintf(k, sizeof(k), "\"%s\":", key);
    const char* p = strstr(json, k);
    return p ? atof(p + strlen(k)) : 0;
}
bool flag(const char* json, const char* key) {
    char k[32];
    snprintf(k, sizeof(k), "\"%s\":true", key);
    return strstr(json, k) != nullptr;
}

// Odczyt ekranu z pikseli panelu Sharp jak kamerą: komórki 20 × 40 px w wierszach co 48 px porównane
// z glifami fontu oprogramowania (font_glyphs.h); wiersz odwrócony ma czarne tło. Bez dostępu do stanu MCU.
std::string screenText() {
    vb::Board& d = b();
    static std::vector<std::pair<std::string, uint32_t>> glyphs;
    if (glyphs.empty()) {
        for (size_t i = 0; i < font::GLYPH_COUNT; ++i) {
            const font::Glyph& g = font::GLYPHS[i];
            glyphs.emplace_back(std::string(reinterpret_cast<const char*>(g.rows), sizeof(g.rows)), g.codepoint);
        }
    }
    auto px = [&](int x, int y) { return ((d.lcd.frame[y][x / 8] >> (x % 8)) & 1u) == 0; };   // czarny
    const bool on = d.pins[board::DISPLAY_DISP].mode == OUTPUT && d.pins[board::DISPLAY_DISP].out;
    std::string out = std::string("{\"on\":") + (on ? "true" : "false") + ",\"lines\":[";
    std::string inv;
    for (int row = 0; row < 5; ++row) {
        const int top = row * font::LINE_PITCH, base = top + (font::LINE_PITCH - font::HEIGHT) / 2;
        const bool inverted = px(399, top) && px(0, top);
        std::string text;
        for (int col = 0; col < 20; ++col) {
            std::string cell(font::HEIGHT * font::ROW_BYTES, '\0');
            for (int gy = 0; gy < font::HEIGHT; ++gy)
                for (int gx = 0; gx < font::WIDTH; ++gx)
                    if (px(col * font::WIDTH + gx, base + gy) != inverted) cell[gy * font::ROW_BYTES + gx / 8] |= static_cast<char>(0x80 >> (gx % 8));
            uint32_t cp = '?';
            for (const auto& g : glyphs) if (g.first == cell) { cp = g.second; break; }
            char utf[5] = {};
            if (cp < 0x80) utf[0] = static_cast<char>(cp);
            else if (cp < 0x800) { utf[0] = static_cast<char>(0xC0 | cp >> 6); utf[1] = static_cast<char>(0x80 | (cp & 0x3F)); }
            else { utf[0] = static_cast<char>(0xE0 | cp >> 12); utf[1] = static_cast<char>(0x80 | ((cp >> 6) & 0x3F)); utf[2] = static_cast<char>(0x80 | (cp & 0x3F)); }
            text += utf;
        }
        while (!text.empty() && text.back() == ' ') text.pop_back();
        out += "\"";
        for (char c : text) { if (c == '"' || c == '\\') out += '\\'; out += c; }
        out += row < 4 ? "\"," : "\"";
        inv += inverted ? (row < 4 ? "true," : "true") : (row < 4 ? "false," : "false");
    }
    return out + "],\"inverted\":[" + inv + "]}";
}

std::string run(const char* line) {
    vb::Board& d = b();
    char cmd[16] = "", a1[32] = "", a2[32] = "";
    sscanf(line, "%15s %31s %31s", cmd, a1, a2);
    const char* rest = strchr(line, ' ') ? strchr(line, ' ') + 1 : "";
    const char* rest2 = strchr(rest, ' ') ? strchr(rest, ' ') + 1 : "";
    if (!strcmp(cmd, "boot")) {
        unsigned long long t = 0;
        unsigned reason = 1, seed = 1;
        sscanf(rest, "%llu %u %u", &t, &reason, &seed);
        d.bootWorldUs = t;
        d.reason = reason;
        d.seed = seed;
        d.rng = 0x5EED0000ull ^ (static_cast<uint64_t>(seed) << 20) ^ t;
        return "ok";
    }
    if (!strcmp(cmd, "pin")) {
        const int pin = atoi(a1);
        if (pin < 0 || pin >= 64) return "err pin";
        d.pins[pin].driven = true;
        d.pins[pin].external = atoi(a2) != 0;
        return "ok";
    }
    if (!strcmp(cmd, "reads")) {
        const int pin = atoi(a1);
        return pin >= 0 && pin < 64 ? std::to_string(d.pins[pin].reads) : "0";
    }
    if (!strcmp(cmd, "pins")) {
        char out[400];
        snprintf(out, sizeof(out),
                 "{\"UP\":%u,\"DOWN\":%u,\"OK\":%u,\"BACK\":%u,\"SILENCE\":%u,\"PREP\":%u,\"LED\":%u,\"BUZZER\":%u,\"DISP\":%u,\"EXTCOMIN\":%u}",
                 board::BTN_UP, board::BTN_DOWN, board::BTN_OK, board::BTN_BACK, board::SW_SILENCE, board::BTN_PREP, board::LED_ALARM,
                 board::BUZZER, board::DISPLAY_DISP, board::DISPLAY_EXTCOMIN);
        return out;
    }
    if (!strcmp(cmd, "usb")) {
        const int itf = atoi(a1) ? 1 : 0;
        d.usb[itf].open = !strcmp(a2, "open");
        if (!d.usb[itf].open) d.usb[itf].in.clear();
        return "ok";
    }
    if (!strcmp(cmd, "usbin")) {
        const int itf = atoi(a1) ? 1 : 0;
        for (uint8_t c : unhex(rest2)) d.usb[itf].in.push_back(c);
        return "ok";
    }
    if (!strcmp(cmd, "usbout")) {
        const int itf = atoi(a1) ? 1 : 0;
        std::string out = hex(reinterpret_cast<const uint8_t*>(d.usb[itf].out.data()), d.usb[itf].out.size());
        d.usb[itf].out.clear();
        return out;
    }
    if (!strcmp(cmd, "air")) {
        std::string out = "[";
        for (const chips::AirFrame& f : d.radio.takeTransmitted()) { out += frameJson(f); out += ','; }
        if (out.size() > 1) out.pop_back();
        return out + "]";
    }
    if (!strcmp(cmd, "airin")) {
        chips::AirFrame f;
        f.id = static_cast<uint32_t>(field(rest, "id"));
        f.startUs = static_cast<uint64_t>(field(rest, "start"));
        f.syncUs = static_cast<uint64_t>(field(rest, "sync_at"));
        f.endUs = static_cast<uint64_t>(field(rest, "end"));
        f.freqHz = field(rest, "freq");
        f.rate = field(rest, "rate");
        f.sync = static_cast<uint32_t>(field(rest, "sync"));
        f.syncBits = static_cast<uint8_t>(field(rest, "sync_bits"));
        f.dbm = static_cast<int16_t>(field(rest, "dbm"));
        f.carrier = flag(rest, "carrier");
        f.aborted = flag(rest, "aborted");
        if (f.carrier) f.syncUs = f.endUs = f.endUs ? f.endUs : UINT64_MAX;
        const char* p = strstr(rest, "\"payload\":\"");
        if (p) {
            std::string h(p + 11);
            h = h.substr(0, h.find('"'));
            f.payload = unhex(h.c_str());
        }
        d.radio.airUpdate(f);
        return "ok";
    }
    if (!strcmp(cmd, "nvs")) {
        // nvs: zawartość flasha (hex: przestrzeń, klucz, wartość z długościami 1/1/2 B); nvs <hex>: wczytanie.
        if (!a1[0]) {
            std::string raw;
            for (const auto& space : d.nvs) for (const auto& kv : space.second) {
                raw += static_cast<char>(space.first.size()); raw += space.first;
                raw += static_cast<char>(kv.first.size()); raw += kv.first;
                raw += static_cast<char>(kv.second.size() >> 8); raw += static_cast<char>(kv.second.size() & 0xFF); raw += kv.second;
            }
            return hex(reinterpret_cast<const uint8_t*>(raw.data()), raw.size());
        }
        const std::vector<uint8_t> raw = unhex(rest);
        d.nvs.clear();
        for (size_t i = 0; i < raw.size();) {
            const std::string space(raw.begin() + i + 1, raw.begin() + i + 1 + raw[i]); i += 1 + raw[i];
            const std::string key(raw.begin() + i + 1, raw.begin() + i + 1 + raw[i]); i += 1 + raw[i];
            const size_t n = static_cast<size_t>(raw[i]) << 8 | raw[i + 1]; i += 2;
            d.nvs[space][key] = std::string(raw.begin() + i, raw.begin() + i + n); i += n;
        }
        return "ok";
    }
    if (!strcmp(cmd, "fault")) {
        const bool on = atoi(a2) != 0;
        if (!strcmp(a1, "radio")) d.radio.setDead(on);
        else if (!strcmp(a1, "fram")) d.framChip.failWrites = on;
        else return "err fault radio|fram";
        return "ok";
    }
    if (!strcmp(cmd, "events")) {
        std::string out = "[";
        for (const std::string& e : d.events) { out += e; out += ','; }
        if (out.size() > 1) out.pop_back();
        d.events.clear();
        return out + "]";
    }
    if (!strcmp(cmd, "screen")) return screenText();
    if (!strcmp(cmd, "state")) {
        char out[400];
        const bool lcdOn = d.pins[board::DISPLAY_DISP].mode == OUTPUT && d.pins[board::DISPLAY_DISP].out;
        snprintf(out, sizeof(out),
                 "{\"uptime_us\":%llu,\"world_us\":%llu,\"lcd_on\":%s,\"extcomin\":%s,\"lcd_version\":%u,\"led\":%s,\"buzzer\":%s,"
                 "\"radio_mhz\":%.4f,\"radio_dbm\":%d,\"tx\":%s,\"reboot\":%s}",
                 static_cast<unsigned long long>(d.uptimeUs), static_cast<unsigned long long>(vb::worldUs()), lcdOn ? "true" : "false",
                 d.extcomin ? "true" : "false", d.lcd.version, d.pins[board::LED_ALARM].out ? "true" : "false",
                 d.toneEndUs ? "true" : "false", d.radio.frequencyHz() / 1e6, d.radio.txDbm(), d.radio.transmitting() ? "true" : "false",
                 d.rebooted ? "true" : "false");
        return out;
    }
    return "err nieznane polecenie";
}

}  // namespace

extern "C" {

// Bufor wejściowy poleceń (przeglądarka zapisuje w nim tekst).
char* sim_input() {
    static char buffer[16384];
    return buffer;
}

const char* sim_command() {
    b().reply = run(sim_input());
    return b().reply.c_str();
}

const char* sim_command_line(const char* line) {
    b().reply = run(line);
    return b().reply.c_str();
}

uint8_t* sim_fram() { return b().fram.data(); }
uint32_t sim_fram_size() { return static_cast<uint32_t>(b().fram.size()); }
uint8_t* sim_noinit() { return reinterpret_cast<uint8_t*>(__start_wici_noinit); }
uint32_t sim_noinit_size() { return static_cast<uint32_t>(__stop_wici_noinit - __start_wici_noinit); }
const uint8_t* sim_lcd() { return &b().lcd.frame[0][0]; }
uint32_t sim_lcd_version() { return b().lcd.version; }

// Praca do chwili `until` (µs czasu bezwzględnego). 0: dalej; 1: restart (nowa instancja, przyczyna w
// sim_reboot_reason, FRAM i segment wici_noinit do przeniesienia).
int sim_run(double until) {
    vb::Board& d = b();
    if (d.rebooted) return 1;
    try {
        if (!d.started) {
            d.started = true;
            setup();
        }
        while (vb::worldUs() < static_cast<uint64_t>(until)) loop();
    } catch (const vb::Reboot& r) {
        d.rebooted = true;
        d.rebootReason = r.reason;
        return 1;
    }
    return 0;
}

uint32_t sim_reboot_reason() { return b().rebootReason; }

}  // extern "C"
