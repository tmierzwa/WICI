// SPDX-License-Identifier: MIT
// Wirtualna płytka stanowiska B na N1 (firmware/src/board_bench_b.h): zegar symulacji, piny,
// magistrala SPI z emulowanymi układami (FRAM CY15B104Q, ekran Sharp LS027B7DH01A, radio S2-LP),
// dwa porty USB CDC, watchdog i restart. Oprogramowanie stacji widzi ją przez Arduino.h, SPI.h
// i platform_sim.cpp; środowisko (przeglądarka albo Node: web/device.js; cli.cpp w budowie natywnej) przez sim_*.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace vb {

// ---- dla oprogramowania (przez Arduino.h, SPI.h, platform_sim.cpp) ----
uint64_t nowUs();                          // czas od startu MCU
void sleepUs(uint64_t us);                 // upływ czasu (delay, oczekiwanie)
void pinMode(uint8_t pin, uint8_t mode);
void digitalWrite(uint8_t pin, bool high);
bool digitalRead(uint8_t pin);
int analogRead(uint8_t pin);
void tone(uint8_t pin, unsigned hz, unsigned long ms);
uint32_t random32();                       // generator płytki (ziarno instancji)
void spiBegin();
uint8_t spiTransfer(uint8_t byte, bool lsbFirst, uint8_t mode, uint32_t hz);
bool usbOpen(uint8_t itf);
int usbAvailable(uint8_t itf);
int usbRead(uint8_t itf);
int usbPeek(uint8_t itf);
size_t usbWrite(uint8_t itf, const uint8_t* data, size_t n);
int usbWritable(uint8_t itf);
[[noreturn]] void reboot(const char* why);
void watchdogBegin(uint32_t seconds);
void feedTaskWatchdog();
uint32_t heapSize();
uint32_t heapFree();
uint32_t resetReason();                    // esp_reset_reason_t: 1 włączenie, 3 programowy, 6 watchdog zadań
void chipId(uint8_t mac[6]);
void entropy(uint8_t* out, size_t count);
uint32_t extcominTicks();                  // licznik źródła EXTCOMIN (okres 1 s)
bool extcominStart(uint8_t pin);

// ---- emulowane układy SPI ----
struct SpiDevice {
    virtual ~SpiDevice() = default;
    virtual void select() {}
    virtual uint8_t exchange(uint8_t wire) = 0;   // bajt w kolejności bitów na linii: bit 7 pierwszy
    virtual void deselect() {}
};

// Wyjątek restartu: przerywa setup()/loop(); środowisko tworzy nową instancję (globalne od nowa),
// przenosząc FRAM i segment wici_noinit.
struct Reboot {
    uint32_t reason;
};

}  // namespace vb
