// SPDX-License-Identifier: MIT
// Prototyp płytki v2: ESP32-S3-DevKitC-1-N8R8 v1.1 w J5/J6, moduł Seeed Wio-SX1262 w J8/J9, FRAM U1, panel
// ekranu Sharp w J7, panel obsługi i tor zasilania z ogniw AA i 12 V. Przypisanie według
// hardware/plytka-v2/polaczenia.md (tabela „Sygnały MCU”, generowana z hardware/plytka-v2/tools/design.py);
// tests/test_board_netlist.py sprawdza je z hardware/plytka-v2/checks/netlist.xml. Przypisania v1.1 (L0)
// zostają, więc piny radia, FRAM, ekranu i panelu są takie jak w board_l0.h. Nowe są pomiar ogniw i 12 V,
// klucz dzielnika ogniw, PWM przetwornicy, INT i KILL sterownika wyłącznika oraz wykrywanie laptopa.
// Numery pinów to numery GPIO ESP32-S3.
#pragma once

#include <Arduino.h>

#include "mcu_sleep.h"

// Panel obsługi, linia DISP ekranu i pomiar na GPIO5 są jak na płytce nośnej N1 (board.h), więc v2 korzysta
// z tych samych ścieżek programu.
#define WICI_BOARD_N1 1
#define WICI_MCU_SLEEP 1  // lekkie uśpienie: listy SLEEP_HOLD i SLEEP_WAKE niżej, polecenie NAP
// Pętla czuwania (standby.h): uśpienie między terminami w zwykłej pracy. Wymaga wykrywania napięcia na VBUS
// (USB_LAPTOP) dla zasady 10 s, więc jest tylko na v2; L0 i XIAO śpią wyłącznie w poleceniu NAP.
#define WICI_STANDBY 1

namespace board {

constexpr const char* NAME = "v2";

// SPI: piny IO_MUX FSPI na kontrolerze SPI2, SCK przez 33 Ω (R18).
constexpr uint8_t SPI_SCK = 12;   // J5.18 -> R18 -> SPI_SCK; Wio J9.6
constexpr uint8_t SPI_MOSI = 11;  // J5.17; Wio J9.4
constexpr uint8_t SPI_MISO = 13;  // J5.19; Wio J9.5
constexpr uint8_t SPI_DRIVE = 0;  // gpio_drive_cap_t: 0 = najsłabszy

// SX1262 na Wio-SX1262.
constexpr uint8_t RADIO_CS = 10;    // J5.16 RF_CS -> Wio J8.4 NSS, aktywny stanem niskim; R11 10 kΩ do 3,3 V
constexpr uint8_t RADIO_RESET = 9;  // J5.15 RF_RESET -> Wio J8.3; R12 1 kΩ do masy: napędzany wysoko
constexpr uint8_t RADIO_BUSY = 14;  // J5.20 RF_GPIO0 -> Wio J8.2 BUSY, wejście
constexpr uint8_t RADIO_DIO1 = 21;  // J6.18 RF_GPIO1 -> Wio J8.1 DIO1, wejście przerwania
constexpr uint8_t RADIO_RXEN = 42;  // J6.6 RF_GPIO3 -> Wio J8.5 RXEN: wysoki w RX; R64 10 kΩ do masy

// FRAM U1 (przez bramkę U4 nadzorcy U3) na tej samej magistrali SPI.
constexpr uint8_t FRAM_CS = 8;  // J5.12; R20 10 kΩ do 3,3 V

// Panel Sharp w J7: SCS aktywny stanem wysokim (R13 10 kΩ do masy), EXTCOMIN z MCPWM, DISP wysoki po
// wyczyszczeniu ekranu (R19 10 kΩ do masy).
constexpr uint8_t DISPLAY_CS = 7;         // J5.7
constexpr uint8_t DISPLAY_EXTCOMIN = 17;  // J5.10
constexpr uint8_t DISPLAY_DISP = 16;      // J5.9
constexpr uint32_t DISPLAY_SPI_HZ = 1000000;

// Panel: przyciski do masy przez filtr RC (R80-R83, C60-C63), podciągnięte 10 kΩ do 3,3 V (R5-R8);
// przełącznik CISZA przez R16 1 kΩ, podciągnięty R9 10 kΩ.
constexpr uint8_t BTN_UP = 41;      // J6.7
constexpr uint8_t BTN_DOWN = 40;    // J6.8
constexpr uint8_t BTN_OK = 39;      // J6.9
constexpr uint8_t BTN_BACK = 2;     // J6.5
constexpr uint8_t SW_SILENCE = 1;   // J6.4; masa = cisza
constexpr uint8_t BTN_PREP = 6;     // J5.6; przycisk trybu przygotowania (R10 10 kΩ do 3,3 V)

// Dioda alarmu (aktywna stanem wysokim, R1 1 kΩ) i brzęczyk przez klucz Q1 (MMBT3904, R3 1 kΩ do bazy,
// R4 100 kΩ do masy): stan wysoki włącza brzęczyk, więc tylko przebieg z tone(), a w spoczynku stan niski.
constexpr uint8_t LED_ALARM = 18;  // J5.11
constexpr uint8_t BUZZER = 15;     // J5.8
constexpr uint16_t BUZZER_HZ = 2048;

// Pomiar 12 V (V_12_ADC) na GPIO5 (ADC1_CH4), tym samym pinie co VTEST na N1, więc polecenie VTEST podaje
// napięcie 12 V. Dzielnik to dzielnik UV sterownika U5: V12 -> R37 221 kΩ -> R38 10,0 kΩ -> węzeł V_12_DIV
// -> R39 15,4 kΩ -> masa (wszystkie 0,1%), czyli V_12_DIV = V12 × 15,4 / 246,4 = V12 / 16,00 (BOM: R39
// „0,0625 × V12”). R76 10 kΩ do pinu i C33 100 nF to filtr, nie część dzielnika. Napięcie jest tylko przy
// włączonej stacji (Q4 podłącza dzielnik z szyny ON); 36 V daje 2,25 V, w zakresie tłumienia 11 dB.
constexpr uint8_t VTEST = 5;  // J5.5
constexpr uint8_t VTEST_ADC_CHANNEL = 4;
constexpr uint8_t VTEST_DIVIDER = 16;

// Pomiar ogniw (V_AA_ADC) na GPIO4 (ADC1_CH3) przez klucz Q6 (DIV_EN wysoki podłącza dzielnik): R44 39,0 kΩ
// / R45 10,0 kΩ (0,1%), czyli V_AA = V_AA_DIV × 4,9. Program jeszcze go nie mierzy.
constexpr uint8_t BATTERY_ADC = 4;  // J5.4
constexpr uint8_t BATTERY_ADC_CHANNEL = 3;
constexpr uint8_t BATTERY_DIV_EN = 46;  // J5.14; pin konfiguracji startu, R43 100 kΩ do masy (niski przy resecie)

// Przetwornica 3,3 V (U7 LTC3115-1): PWM_SYNC wysoki = PWM na czas nadawania, niski = Burst Mode.
constexpr uint8_t CONVERTER_PWM = 45;  // J6.15; pin konfiguracji startu, R63 100 kΩ do masy (niski przy resecie)

// Sterownik wyłącznika U6 (LTC2955-2): INT to otwarty dren z R47 10 kΩ do 3,3 V, niski przy naciśniętym
// wyłączniku. KILL_MCU wysoki otwiera Q11, który ściąga KILL i wyłącza stację; R72 100 kΩ do masy trzyma Q11
// wyłączony przy resecie i bez sterowania.
constexpr uint8_t POWER_INT = 48;   // J6.16
constexpr uint8_t POWER_KILL = 47;  // J6.17

// Wykrywanie laptopa: VBUS gniazda USB-C przez R73/R74 włącza Q12, który ściąga USB_LAPTOP (R75 100 kΩ do
// 3,3 V): stan niski = napięcie na VBUS.
constexpr uint8_t USB_LAPTOP = 3;  // J5.13

// Diody stanu jak LED1-LED4 płytki DK: brak.
constexpr int16_t LED_HEARTBEAT = -1;
constexpr int16_t LED_RADIO = -1;
constexpr int16_t LED_FRAM = -1;
constexpr int16_t LED_USB = -1;

// Lekkie uśpienie (mcu_sleep.h, platform::sleep): wyjścia trzymane w uśpieniu przez gpio_hold_en, bo rezystory
// płytki ściągnęłyby je do stanu, który resetuje radio (R12 1 kΩ do masy na NRESET), wyłącza odbiór (RXEN do
// masy) albo wygasza ekran (DISP do masy); CS-y nieaktywne, a brzęczyk w stanie niskim.
// Na v2 dochodzą klucz dzielnika ogniw, tryb przetwornicy i KILL; program ich jeszcze nie steruje, więc hold
// zatrzaskuje stan z rezystorów do masy (R43, R63, R72: niski, stacja zostaje włączona).
constexpr uint8_t SLEEP_HOLD[] = {RADIO_CS, RADIO_RESET, RADIO_RXEN, FRAM_CS, DISPLAY_CS, DISPLAY_EXTCOMIN,
                                 DISPLAY_DISP, LED_ALARM, BUZZER, BATTERY_DIV_EN, CONVERTER_PWM, POWER_KILL};
// Linie budzenia: DIO1 stanem wysokim; przyciski, CISZA, INT wyłącznika i wykrywanie laptopa przy każdej zmianie
// stanu, bo INT trwa, dopóki wyłącznik jest wciśnięty, a USB_LAPTOP, dopóki jest napięcie na VBUS.
constexpr mcu_sleep::Line SLEEP_WAKE[] = {
    {RADIO_DIO1, mcu_sleep::Wake::ACTIVE_HIGH, "dio1"}, {BTN_UP, mcu_sleep::Wake::ANY_CHANGE, "up"},
    {BTN_DOWN, mcu_sleep::Wake::ANY_CHANGE, "down"},       {BTN_OK, mcu_sleep::Wake::ANY_CHANGE, "ok"},
    {BTN_BACK, mcu_sleep::Wake::ANY_CHANGE, "back"},       {SW_SILENCE, mcu_sleep::Wake::ANY_CHANGE, "silence"},
    {BTN_PREP, mcu_sleep::Wake::ANY_CHANGE, "prep"},       {POWER_INT, mcu_sleep::Wake::ANY_CHANGE, "power_int"},
    {USB_LAPTOP, mcu_sleep::Wake::ANY_CHANGE, "laptop"},
};

constexpr uint32_t SPI_HZ = 1000000;  // radio, jak na L0
constexpr uint32_t FRAM_SPI_HZ = 8000000;

}  // namespace board
