#pragma once
#include <array>
#include <cassert>
#include <cstdio>
#include <deque>
#include <string>
#include <stdint.h>

#define IRAM_ATTR
constexpr int LOW=0, HIGH=1, OUTPUT=1, INPUT_PULLUP=2;
using String = std::string;
extern uint32_t mockNow;
extern std::array<int,49> pins;
extern bool timerOk;
extern bool buzzerTimerOk;
extern unsigned buzzerDuty;
void gpioHook(int pin,int value);
inline void digitalWrite(int pin,int value) { gpioHook(pin,value); pins[pin]=value; }
inline int digitalRead(int pin) { return pins[pin]; }
inline void pinMode(int pin,int mode) { if(mode==INPUT_PULLUP)pins[pin]=HIGH; }
inline uint32_t millis() { return mockNow; }
inline void delay(uint32_t ms) { mockNow+=ms; }
inline void delayMicroseconds(unsigned) {}
inline double ledcSetup(unsigned,double hz,unsigned) { return buzzerTimerOk?hz:0; }
inline void ledcAttachPin(unsigned,unsigned) {}
inline void ledcWrite(unsigned,unsigned duty) { buzzerDuty=duty; }
struct SerialMock {
    std::string output;
    std::string unflushed;  // Every complete record must be flushed, never a partial one.
    std::deque<char> input;
    void begin(unsigned) {}
    void flush() { assert(unflushed.empty() || unflushed.back()=='\n');unflushed.clear(); }
    int available() { return static_cast<int>(input.size()); }
    int read() { char c=input.front();input.pop_front();return c; }
    void write(const std::string& text) {
        assert(unflushed.empty() || unflushed.back()!='\n');output+=text;unflushed+=text;
    }
    void println(const char* text) { write(std::string(text)+'\n'); }
    template<typename... Args> void printf(const char* format,Args... args) {
        char text[512];int n=snprintf(text,sizeof(text),format,args...);
        assert(n>=0 && n<static_cast<int>(sizeof(text)));write(text);
    }
};
extern SerialMock Serial;
struct EspMock { unsigned long long getEfuseMac() { return 0x001122334455ULL; } };
extern EspMock ESP;
