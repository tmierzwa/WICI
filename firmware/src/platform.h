// SPDX-License-Identifier: MIT
// Warstwa MCU programu stacji (main.cpp): magistrala SPI płytki, identyfikator układu, przyczyna
// restartu, watchdog, restart programowy, pamięć niezerowana i pomiar VTEST. Wykonania:
// platform_nrf.cpp (nRF52840, rdzeń Adafruit) i platform_esp32.cpp (ESP32-S3, Arduino-ESP32 3.x).
#pragma once

#include <Arduino.h>
#include <SPI.h>

#if defined(ARDUINO_ARCH_ESP32)
#include <esp_attr.h>
// Pamięć RTC niezerowana przy restarcie programowym i przez watchdog (po włączeniu zasilania przypadkowa).
#define PLATFORM_NOINIT RTC_NOINIT_ATTR
#else
// Skrypty linkera rdzenia Adafruit nie znają .noinit: zwykła sekcja trafiłaby między .data i .bss
// z kopią we flashu nadpisywaną przy starcie. Sekcja oznaczona jako NOBITS (bez treści w obrazie)
// trafia za .bss, poza kopiowanie .data i zerowanie .bss (sprawdzenie: objdump -h, tylko ALLOC).
#define PLATFORM_NOINIT __attribute__((section(".noinit,\"aw\",%nobits@")))
#endif

namespace platform {

extern const char* const MCU;              // pole "mcu" w INFO
extern const char* const EXTCOMIN_SOURCE;  // licznik EXTCOMIN ekranu (pole "extcomin" w DISPLAY)

SPIClass& bus();  // magistrala radia, FRAM i ekranu
void beginBus();  // piny i kontroler SPI (po ustawieniu CS wszystkich układów w stan nieaktywny)

// Identyfikator układu w dwóch słowach (nRF52840: 8 B FICR DEVICEID; ESP32-S3: 6 B adresu MAC z eFuse);
// id[0] & 0xFFFFFF daje nazwę WICI-xxxxxx.
void chipId(uint32_t id[2]);
// Bajty ze sprzętowego źródła entropii do ziarna generatora stacji (drbg.h): nRF52840 RNG z korekcją
// obciążenia; ESP32-S3 esp_fill_random ze źródłem SAR ADC włączonym bootloader_random_enable() (bez
// radia Wi-Fi/BT jedyne pełne źródło), więc przed konfiguracją ADC pomiaru VTEST (beginVtest). Fałsz,
// gdy źródło nie odpowiada w ograniczonym czasie (nRF52840: brak VALRDY); reszta out jest wtedy zerowa.
bool entropy(uint8_t* out, size_t count);
uint32_t resetReason();  // nRF52840: RESETREAS; ESP32-S3: esp_reset_reason()
// Czas od startu w ms bez zawijania (millis() zawija się po około 49 dniach). Na nRF52840 liczy
// przejścia licznika taktów FreeRTOS, więc trzeba go wołać częściej niż co 48 dni (obieg pętli).
uint64_t uptimeMs();
bool resetByWatchdog();

void beginWatchdog(uint32_t seconds);
void feedWatchdog();
[[noreturn]] void reboot();  // pamięć niezerowana zostaje

void beginVtest();
void printVtest();  // odpowiedź na VTEST (tylko płytka N1)

// Blokada operacji radia: jedna operacja sterownika radia (kilka transakcji SPI: BUSY, status, kasowanie
// przerwań, bufor) naraz, gdy obok pętli stacji obsługuje układ zadanie odbioru (ESP32-S3, stacja L0).
// ESP32-S3: rekurencyjny mutex FreeRTOS z dziedziczeniem priorytetu (pętla może wziąć go ponownie
// wewnątrz własnej operacji). nRF52840 i symulator: pusta (nie ma tam zadania odbioru); program `host`
// nie kompiluje warstwy MCU ani sterowników radia.
// Kolejność zawsze: najpierw blokada radia, potem magistrala SPI (SPIClass::beginTransaction w Radio);
// nigdy blokada radia wewnątrz transakcji SPI. Zapis do FRAM bierze tylko magistralę, więc nie ma zakleszczenia.
// Zadanie odbioru bierze ją bez czekania (timeoutMs = 0) i przy zajętej pomija obieg; pętla czeka z limitem.
bool radioLockTake(uint32_t timeoutMs);  // true, gdy wzięta w timeoutMs (0: tylko próba)
void radioLockGive();
// Nieudane czekania z limitem (timeoutMs > 0, czyli po stronie pętli) od startu: błąd operacji radia,
// który kontrola radia zamienia w radio_awaria. Próby bez czekania (zadanie) się nie liczą.
uint32_t radioLockTimeouts();
// Sprawdzenie blokady (WICI_RADIO_LOCK_CHECK, sx1262::Radio przed każdą transakcją): true, gdy zadanie
// odbioru nie pracuje (blokada niepotrzebna) albo bieżące zadanie trzyma blokadę.
bool radioLockOk();

// Zadanie odbioru radia (stacja L0, plan interfejsu LoRa, L6): ESP32-S3 rdzeń 0, wysoki priorytet, obieg
// co takt FreeRTOS (vTaskDelay(1), 1 ms); w każdym obiegu woła cycle. Stos i blok zadania w pamięci
// statycznej; zadanie nie jest w watchdogu zadań. false, gdy MCU nie ma zadania (nRF52840, symulator)
// albo nie powstało: wtedy pętla obsługuje układ sama.
bool startRxTask(void (*cycle)());
int32_t rxTaskStackFree();  // najmniejszy zapas stosu zadania od startu w bajtach; -1 bez zadania

class RadioLock {
public:
    explicit RadioLock(uint32_t timeoutMs) : held_(radioLockTake(timeoutMs)) {}
    ~RadioLock() {
        if (held_) radioLockGive();
    }
    RadioLock(const RadioLock&) = delete;
    RadioLock& operator=(const RadioLock&) = delete;
    bool held() const { return held_; }

private:
    bool held_;
};

// Polecenia tylko tego MCU (ESP32-S3: DRIVE); false, gdy polecenie nieznane.
bool handle(const char* cmd, char* words[], size_t n);
const char* helpCommands();  // dopisek do listy HELP, z przecinkiem na początku albo pusty

}  // namespace platform
