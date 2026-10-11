// SPDX-License-Identifier: MIT
// Rdzeń Arduino dla symulatora: tyle API Arduino-ESP32, ile używa oprogramowanie stacji
// (firmware/src) i biblioteki stosu (.pio/stack), nad wirtualną płytką (vboard.h). Czas jest
// czasem symulacji: delay() i transmisje SPI przesuwają zegar, kod między nimi trwa zero.
#pragma once

#include <math.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <algorithm>
#include <string>

#include "vboard.h"

#define ARDUINO_SIM 1

#define HIGH 0x1
#define LOW 0x0
#define INPUT 0x01
#define OUTPUT 0x03
#define INPUT_PULLUP 0x05
#define INPUT_PULLDOWN 0x09
#define LSBFIRST 0
#define MSBFIRST 1
#define CHANGE 0x03
#define FALLING 0x02
#define RISING 0x01
#define DEC 10
#define HEX 16
#define OCT 8
#define BIN 2

typedef uint8_t byte;
typedef bool boolean;
typedef unsigned int word;

using std::max;
using std::min;
template <typename T, typename L, typename H>
constexpr T constrain(T x, L lo, H hi) { return x < lo ? lo : (x > hi ? hi : x); }

inline unsigned long millis() { return static_cast<unsigned long>(vb::nowUs() / 1000); }
inline unsigned long micros() { return static_cast<unsigned long>(vb::nowUs()); }
inline void delay(unsigned long ms) { vb::sleepUs(static_cast<uint64_t>(ms) * 1000); }
inline void delayMicroseconds(unsigned int us) { vb::sleepUs(us); }
inline void yield() { vb::sleepUs(0); }
inline void pinMode(uint8_t pin, uint8_t mode) { vb::pinMode(pin, mode); }
inline void digitalWrite(uint8_t pin, uint8_t value) { vb::digitalWrite(pin, value != 0); }
inline int digitalRead(uint8_t pin) { return vb::digitalRead(pin) ? HIGH : LOW; }
inline int analogRead(uint8_t pin) { return vb::analogRead(pin); }
inline void analogReadResolution(int) {}
inline void tone(uint8_t pin, unsigned int hz, unsigned long ms = 0) { vb::tone(pin, hz, ms); }
inline void noTone(uint8_t pin) { vb::tone(pin, 0, 0); }
inline void interrupts() {}
inline void noInterrupts() {}
inline long random(long howbig) { return howbig <= 0 ? 0 : static_cast<long>(vb::random32() % static_cast<uint32_t>(howbig)); }
inline long random(long lo, long hi) { return lo >= hi ? lo : lo + random(hi - lo); }
inline void randomSeed(unsigned long) {}

// ---- String (podzbiór Arduino) ----

class String {
public:
    String() = default;
    String(const char* s) : s_(s ? s : "") {}
    String(const std::string& s) : s_(s) {}
    String(char c) : s_(1, c) {}
    String(int v, unsigned char base = DEC) : s_(num(static_cast<long long>(v), base)) {}
    String(unsigned int v, unsigned char base = DEC) : s_(num(static_cast<long long>(v), base)) {}
    String(long v, unsigned char base = DEC) : s_(num(static_cast<long long>(v), base)) {}
    String(unsigned long v, unsigned char base = DEC) : s_(num(static_cast<long long>(v), base)) {}
    String(long long v, unsigned char base = DEC) : s_(num(v, base)) {}
    String(unsigned long long v, unsigned char base = DEC) : s_(num(static_cast<long long>(v), base)) {}
    String(double v, unsigned int decimals = 2) {
        char b[64];
        snprintf(b, sizeof(b), "%.*f", decimals, v);
        s_ = b;
    }
    const char* c_str() const { return s_.c_str(); }
    unsigned int length() const { return static_cast<unsigned int>(s_.size()); }
    bool reserve(unsigned int n) { s_.reserve(n); return true; }
    char operator[](unsigned int i) const { return i < s_.size() ? s_[i] : 0; }
    char& operator[](unsigned int i) { return s_[i]; }
    char charAt(unsigned int i) const { return (*this)[i]; }
    String& operator+=(const String& o) { s_ += o.s_; return *this; }
    String& operator+=(const char* o) { s_ += o ? o : ""; return *this; }
    String& operator+=(char c) { s_ += c; return *this; }
    bool concat(const char* o, unsigned int n) { s_.append(o, n); return true; }
    bool concat(const String& o) { s_ += o.s_; return true; }
    bool concat(const char* o) { s_ += o; return true; }
    bool concat(char c) { s_ += c; return true; }
    bool operator==(const String& o) const { return s_ == o.s_; }
    bool operator==(const char* o) const { return s_ == (o ? o : ""); }
    bool operator!=(const String& o) const { return s_ != o.s_; }
    bool operator<(const String& o) const { return s_ < o.s_; }
    explicit operator bool() const { return true; }
    int indexOf(char c, unsigned int from = 0) const { const size_t p = s_.find(c, from); return p == std::string::npos ? -1 : static_cast<int>(p); }
    String substring(unsigned int a) const { return a < s_.size() ? String(s_.substr(a)) : String(); }
    String substring(unsigned int a, unsigned int b) const { return a < s_.size() && b > a ? String(s_.substr(a, b - a)) : String(); }
    long toInt() const { return atol(s_.c_str()); }
    double toFloat() const { return atof(s_.c_str()); }
    void toCharArray(char* buf, unsigned int size, unsigned int index = 0) const {
        if (!size) return;
        const size_t n = index < s_.size() ? std::min<size_t>(size - 1, s_.size() - index) : 0;
        memcpy(buf, s_.data() + index, n);
        buf[n] = 0;
    }
    void getBytes(unsigned char* buf, unsigned int size, unsigned int index = 0) const { toCharArray(reinterpret_cast<char*>(buf), size, index); }
    void trim() {
        const size_t a = s_.find_first_not_of(" \t\r\n"), b = s_.find_last_not_of(" \t\r\n");
        s_ = a == std::string::npos ? std::string() : s_.substr(a, b - a + 1);
    }
    const std::string& str() const { return s_; }

private:
    static std::string num(long long v, unsigned char base) {
        if (base == DEC) return std::to_string(v);
        std::string out;
        unsigned long long u = static_cast<unsigned long long>(v);
        do { out.insert(out.begin(), "0123456789abcdef"[u % base]); u /= base; } while (u);
        return out;
    }
    std::string s_;
};
class StringSumHelper : public String {
public:
    StringSumHelper(const String& s) : String(s) {}
    StringSumHelper(const char* s) : String(s) {}
};
inline StringSumHelper operator+(const String& a, const String& b) { String r(a); r += b; return r; }
inline StringSumHelper operator+(const String& a, const char* b) { String r(a); r += b; return r; }
inline StringSumHelper operator+(const char* a, const String& b) { String r(a); r += b; return r; }
inline StringSumHelper operator+(const String& a, char b) { String r(a); r += b; return r; }

class __FlashStringHelper;
#define F(s) (s)
#define PROGMEM
#define pgm_read_byte(p) (*reinterpret_cast<const uint8_t*>(p))
#define pgm_read_word(p) (*reinterpret_cast<const uint16_t*>(p))
#define pgm_read_dword(p) (*reinterpret_cast<const uint32_t*>(p))
#define strlen_P strlen
#define memcpy_P memcpy

// ---- Print, Stream ----

class Print;
class Printable {
public:
    virtual ~Printable() = default;
    virtual size_t printTo(Print& p) const = 0;
};

class Print {
public:
    virtual ~Print() = default;
    virtual size_t write(uint8_t c) = 0;
    virtual size_t write(const uint8_t* data, size_t n) {
        size_t done = 0;
        while (done < n && write(data[done])) ++done;
        return done;
    }
    size_t write(const char* s) { return s ? write(reinterpret_cast<const uint8_t*>(s), strlen(s)) : 0; }
    size_t write(const char* s, size_t n) { return write(reinterpret_cast<const uint8_t*>(s), n); }
    virtual int availableForWrite() { return 0; }
    virtual void flush() {}
    size_t print(const char* s) { return write(s); }
    size_t print(const String& s) { return write(s.c_str(), s.length()); }
    size_t print(const Printable& p) { return p.printTo(*this); }
    size_t print(char c) { return write(static_cast<uint8_t>(c)); }
    size_t print(int v, int base = DEC) { return print(String(v, static_cast<unsigned char>(base))); }
    size_t print(unsigned int v, int base = DEC) { return print(String(v, static_cast<unsigned char>(base))); }
    size_t print(long v, int base = DEC) { return print(String(v, static_cast<unsigned char>(base))); }
    size_t print(unsigned long v, int base = DEC) { return print(String(v, static_cast<unsigned char>(base))); }
    size_t print(long long v, int base = DEC) { return print(String(v, static_cast<unsigned char>(base))); }
    size_t print(unsigned long long v, int base = DEC) { return print(String(v, static_cast<unsigned char>(base))); }
    size_t print(double v, int digits = 2) { return print(String(v, static_cast<unsigned int>(digits))); }
    template <typename T> size_t println(const T& v) { const size_t n = print(v); return n + println(); }
    template <typename T> size_t println(const T& v, int f) { const size_t n = print(v, f); return n + println(); }
    size_t println() { return write("\r\n"); }
    // Arduino-ESP32: Print::printf bez limitu długości (vsnprintf do bufora na stercie).
    size_t printf(const char* format, ...) __attribute__((format(printf, 2, 3))) {
        va_list a, b;
        va_start(a, format);
        va_copy(b, a);
        char small[256];
        const int n = vsnprintf(small, sizeof(small), format, a);
        va_end(a);
        size_t out = 0;
        if (n < 0) { va_end(b); return 0; }
        if (static_cast<size_t>(n) < sizeof(small)) out = write(small, static_cast<size_t>(n));
        else {
            std::string big(static_cast<size_t>(n) + 1, '\0');
            vsnprintf(&big[0], big.size(), format, b);
            out = write(big.data(), static_cast<size_t>(n));
        }
        va_end(b);
        return out;
    }
};

class Stream : public Print {
public:
    virtual int available() = 0;
    virtual int read() = 0;
    virtual int peek() = 0;
    size_t readBytes(char* buf, size_t n) { size_t i = 0; while (i < n && available()) buf[i++] = static_cast<char>(read()); return i; }
    size_t readBytes(uint8_t* buf, size_t n) { return readBytes(reinterpret_cast<char*>(buf), n); }
    size_t readBytesUntil(char end, char* buf, size_t n) {
        size_t i = 0;
        while (i < n && available()) {
            const int c = read();
            if (c < 0 || c == end) break;
            buf[i++] = static_cast<char>(c);
        }
        return i;
    }
    size_t readBytesUntil(char end, uint8_t* buf, size_t n) { return readBytesUntil(end, reinterpret_cast<char*>(buf), n); }
    bool find(const char* target) { return find(target, strlen(target)); }
    bool find(const char* target, size_t length) {
        size_t matched = 0;
        while (length && available()) {
            const int c = read();
            matched = c == target[matched] ? matched + 1 : (c == target[0] ? 1 : 0);
            if (matched == length) return true;
        }
        return length == 0;
    }
    bool find(char c) { return find(&c, 1); }
    void setTimeout(unsigned long) {}
};

// Port USB CDC (Serial = diagnostyka, interfejs 0; USBCDC(1) = dane) nad buforami wirtualnej płytki.
class USBCDC : public Stream {
public:
    explicit USBCDC(uint8_t itf = 0) : itf_(itf) {}
    void begin(unsigned long = 0) {}
    void end() {}
    void setStringDescriptor(const char*) {}
    operator bool() const { return vb::usbOpen(itf_); }   // Arduino-ESP32: port otwarty przez komputer
    int available() override { return vb::usbAvailable(itf_); }
    int read() override { return vb::usbRead(itf_); }
    int peek() override { return vb::usbPeek(itf_); }
    size_t write(uint8_t c) override { return vb::usbWrite(itf_, &c, 1); }
    size_t write(const uint8_t* data, size_t n) override { return vb::usbWrite(itf_, data, n); }
    int availableForWrite() override { return vb::usbWritable(itf_); }
    void flush() override {}
    using Print::write;

private:
    uint8_t itf_;
};
using HWCDC = USBCDC;
extern USBCDC Serial;

// Arduino-ESP32: przydział z PSRAM; moduł stanowiska B pracuje bez PSRAM (platformio.ini), więc nullptr.
inline void* ps_malloc(size_t) { return nullptr; }
inline void* ps_calloc(size_t, size_t) { return nullptr; }

// Arduino-ESP32: rozmiar stosu zadania loop(); w symulatorze bez znaczenia.
#define SET_LOOP_TASK_STACK_SIZE(size)

// Obiekt ESP (Arduino-ESP32) dla bibliotek stosu: restart i statystyki pamięci.
class EspClass {
public:
    [[noreturn]] void restart() { vb::reboot("ESP.restart"); }
    uint32_t getHeapSize() { return vb::heapSize(); }
    uint32_t getFreeHeap() { return vb::heapFree(); }
    uint32_t getMinFreeHeap() { return vb::heapFree(); }
    uint32_t getMaxAllocHeap() { return vb::heapFree(); }
    uint32_t getPsramSize() { return 0; }
    uint32_t getFreePsram() { return 0; }
    uint32_t getMinFreePsram() { return 0; }
    uint32_t getMaxAllocPsram() { return 0; }
    uint64_t getEfuseMac() {
        uint8_t mac[6];
        vb::chipId(mac);
        uint64_t v = 0;
        for (int i = 5; i >= 0; --i) v = v << 8 | mac[i];
        return v;
    }
};
// ESP-IDF esp_random(): sprzętowy generator (na płytce symulatora: generator z ziarna płytki).
inline uint32_t esp_random() { return vb::random32(); }
inline void esp_fill_random(void* out, size_t n) { vb::entropy(static_cast<uint8_t*>(out), n); }
extern EspClass ESP;
