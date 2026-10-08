// SPDX-License-Identifier: MIT
// Dioda „NOWA WIADOMOŚĆ / ALARM” i brzęczyk stacji (docs/spec/oprogramowanie.md, podświetlenie
// i „Alarmy”; elektronika.md, model energii):
// - dioda miga krótkimi błyskami (50 ms co 5 s, czyli 1% czasu) do odczytu nowych wiadomości, do
//   usunięcia przyczyny alarmu i przez cały czas ciszy radiowej;
// - ekran alarmu daje sygnał co 2 s do potwierdzenia OK; nowy alarm wraca z ekranem alarmu;
// - nowa wiadomość daje jeden krótki sygnał, chyba że opiekun wyciszył dźwięk (WYCISZ DŹWIĘK
//   dotyczy tylko tego sygnału); cisza radiowa sama nie daje dźwięku.
// Przypomnienie `wymien_ogniwa` co 15 min przyjdzie z pomiarem ogniw (płytka R02).
// Bez zależności od Arduino; sprawdzany na komputerze w tests/test_firmware_host.py.
#pragma once

#include <stdint.h>

namespace annunciator {

constexpr uint32_t FLASH_MS = 50;
constexpr uint32_t FLASH_EVERY_MS = 5000;
constexpr uint32_t ALARM_BEEP_MS = 200;
constexpr uint32_t ALARM_BEEP_EVERY_MS = 2000;
constexpr uint32_t MESSAGE_BEEP_MS = 100;

struct Inputs {
    bool alarmScreen = false;  // ekran alarmu czeka na potwierdzenie OK
    bool alarmCause = false;   // przyczyna alarmu trwa (także po potwierdzeniu)
    bool silence = false;
    bool muted = false;        // WYCISZ DŹWIĘK
    uint32_t unread = 0;       // nieprzeczytane wiadomości w skrzynce
};

class Annunciator {
public:
    // Wywoływane w każdym obiegu pętli; zwraca czas sygnału do włączenia teraz [ms] (0 = bez).
    uint32_t poll(uint32_t nowMs, const Inputs& in);
    bool led() const { return led_; }        // stan diody po ostatnim poll()
    bool active() const { return active_; }  // jest powód do migania

private:
    bool started_ = false;
    bool active_ = false;
    bool led_ = false;
    bool flashed_ = false;       // był już błysk w obecnym okresie migania
    uint32_t flashAt_ = 0;
    bool alarmBeeped_ = false;
    uint32_t alarmBeepAt_ = 0;
    uint32_t unread_ = 0;
};

}  // namespace annunciator
