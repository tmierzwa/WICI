// SPDX-License-Identifier: MIT
// Pętla czuwania (docs/spec/oprogramowanie.md, „Czuwanie”): decyzja, czy i na jak długo uśpić MCU po obiegu
// pętli stacji. Uśpienie wykonuje platform::sleep (mcu_sleep.h, platform_esp32.cpp); tu są tylko reguły:
// - Usb: zasada 10 s dla VBUS. Laptop połączony (host wyliczył urządzenie) albo napięcie na VBUS od mniej niż
//   10 s wstrzymuje uśpienie, a stacja jest wtedy na magistrali USB. Napięcie bez połączenia przez 10 s (np.
//   ładowarka w gnieździe) uśpienia nie wstrzymuje: przed uśpieniem stacja odłącza się od magistrali (bez
//   podciągnięcia D+), żeby laptop nie zaczynał połączenia ze śpiącym MCU. Nowe okno 10 s daje dopiero ponowne
//   pojawienie się napięcia albo zakończenie połączenia przez host przy napięciu na VBUS. Okno 10 s jest też
//   po starcie programu: laptop przy stole podłączony do złącza USB modułu DevKitC (te same linie danych, ale
//   bez napięcia na VBUS gniazda płytki) wylicza stację i może wgrać program.
// - Plan: powody pracy bez uśpienia i terminy. Pierwszy zgłoszony powód wygrywa; bez powodu stacja śpi do
//   najbliższego terminu, najwyżej MAX_SLEEP_MS. Termin bliższy niż MIN_SLEEP_MS: bez uśpienia (SHORT).
//   Powody trwałe (tryb przygotowania, węzeł stanowiska, laptop) kończą czuwanie: pętla oddaje EXTCOMIN
//   licznikowi i wraca na magistralę USB. Pozostałe (radio, panel, ekran, praca) to krótkie przerwy w czuwaniu.
// - Hold: przedłużenie pracy po zdarzeniu (ramka radiowa, przycisk), żeby krótkie terminy modułów po zdarzeniu
//   (HACK 200 ms, oczekiwanie na HACK 600 ms, składanie ramek 1 s, przekazanie ogłoszenia) nie czekały na zegar.
// - Vcom: EXTCOMIN ekranu w czuwaniu. Licznik MCPWM w lekkim uśpieniu stoi, a pin jest zatrzaśnięty, więc
//   w czuwaniu pętla przejmuje pin (stan wymuszony ponad przebieg licznika) i odwraca go co 500 ms czasu
//   rzeczywistego, także w krótkich przerwach czuwania; uśpienie kończy się najpóźniej na następnej zmianie.
// Czas w ms z millis() (liczy się dalej w lekkim uśpieniu); różnice odporne na przejście przez zero.
// Bez zależności od Arduino; sprawdzany na komputerze (tests/test_standby.py).
#pragma once

#include <stdint.h>

namespace standby {

constexpr uint32_t NEVER = 0xFFFFFFFFu;
constexpr uint32_t VBUS_WINDOW_MS = 10000;   // napięcie na VBUS bez połączenia USB tyle nie wstrzymuje uśpienia
constexpr uint32_t MAX_SLEEP_MS = 1000;      // najdłuższe uśpienie: terminy modułów bez własnego terminu w planie
constexpr uint32_t MIN_SLEEP_MS = 10;        // krótszego czekania nie opłaca się przesypiać
constexpr uint32_t RADIO_HOLD_MS = 2000;     // praca po ramce radiowej i po końcu nadawania
constexpr uint32_t INPUT_HOLD_MS = 1000;     // praca po zmianie stanu przycisku, CISZY, wyłącznika
constexpr uint32_t VCOM_HALF_PERIOD_MS = 500;  // EXTCOMIN 1 Hz, jak licznik (sharp::EXTCOMIN_HALF_PERIOD_MS)
constexpr uint32_t AFTER_WAKE_MS = 2;        // praca po każdym wybudzeniu: obieg zadania odbioru (takt 1 ms)

// Czas do chwili `at` [ms]; chwila minęła albo jest teraz: 0.
inline uint32_t until(uint32_t now, uint32_t at) {
    const int32_t left = static_cast<int32_t>(at - now);
    return left > 0 ? static_cast<uint32_t>(left) : 0;
}

class Usb {
public:
    // vbus: napięcie na gnieździe (na v2 USB_LAPTOP w stanie niskim); mounted: host wyliczył urządzenie;
    // suspended: magistrala w zawieszeniu. PHY ESP32-S3 nie mierzy VBUS, więc wyjęty przewód wygląda jak
    // zawieszenie, a urządzenie zostaje wyliczone. Połączenie trwa więc przy wyliczeniu bez zawieszenia albo
    // z napięciem na VBUS gniazda (laptop uśpiony z przewodem w gnieździe dalej jest połączony).
    void update(uint32_t now, bool vbus, bool mounted, bool suspended) {
        mounted = mounted && (vbus || !suspended);
        if (!started_) {  // okno po starcie programu
            started_ = true;
            window_ = true;
            sinceMs_ = now;
            vbus_ = vbus;
        }
        if (mounted) {
            window_ = false;
        } else {
            if (vbus && (!vbus_ || mounted_)) {  // napięcie się pojawiło albo host zakończył połączenie
                window_ = true;
                sinceMs_ = now;
            }
            // Odłączenie napięcia kończy okno (okno po starcie trwa bez napięcia).
            if ((vbus_ && !vbus) || (window_ && now - sinceMs_ >= VBUS_WINDOW_MS)) window_ = false;
        }
        vbus_ = vbus;
        mounted_ = mounted;
    }
    bool blocks() const { return mounted_ || window_; }  // laptop połączony albo okno 10 s trwa
    // mounted(): połączenie według reguły wyżej
    bool mounted() const { return mounted_; }
    bool vbus() const { return vbus_; }
    bool window() const { return window_; }
    uint32_t untilMs(uint32_t now) const {
        return window_ ? VBUS_WINDOW_MS - (now - sinceMs_) : NEVER;
    }

private:
    bool started_ = false;
    bool vbus_ = false;
    bool mounted_ = false;
    bool window_ = false;
    uint32_t sinceMs_ = 0;
};

enum class Reason : uint8_t { SLEEP, PREP, NODE, USB, RADIO, PANEL, SCREEN, WORK, SHORT };

inline const char* reasonName(Reason r) {
    switch (r) {
    case Reason::SLEEP: return "sleep";
    case Reason::PREP: return "prep";
    case Reason::NODE: return "node";
    case Reason::USB: return "usb";
    case Reason::RADIO: return "radio";
    case Reason::PANEL: return "panel";
    case Reason::SCREEN: return "screen";
    case Reason::WORK: return "work";
    case Reason::SHORT: return "short";
    }
    return "work";
}

// Powód kończy czuwanie (pętla oddaje EXTCOMIN licznikowi i wraca na magistralę USB).
inline bool persistent(Reason r) { return r == Reason::PREP || r == Reason::NODE || r == Reason::USB; }

class Plan {
public:
    explicit Plan(uint32_t now) : now_(now) {}
    void block(Reason r) {
        if (reason_ == Reason::SLEEP) reason_ = r;
    }
    void wakeIn(uint32_t ms) {
        if (ms < sleepMs_) sleepMs_ = ms;
    }
    void wakeAt(uint32_t at) { wakeIn(until(now_, at)); }
    // Powód pracy: SLEEP, gdy stacja śpi sleepMs().
    Reason reason() const {
        if (reason_ != Reason::SLEEP) return reason_;
        return sleepMs_ < MIN_SLEEP_MS ? Reason::SHORT : Reason::SLEEP;
    }
    uint32_t sleepMs() const { return reason() == Reason::SLEEP ? sleepMs_ : 0; }

private:
    uint32_t now_;
    Reason reason_ = Reason::SLEEP;
    uint32_t sleepMs_ = MAX_SLEEP_MS;
};

class Hold {
public:
    void extend(uint32_t now, uint32_t ms) {
        if (!active_ || ms > until(now, endMs_)) endMs_ = now + ms;
        active_ = true;
    }
    bool active(uint32_t now) {
        if (active_ && until(now, endMs_) == 0) active_ = false;
        return active_;
    }

private:
    bool active_ = false;
    uint32_t endMs_ = 0;
};

class Vcom {
public:
    bool forced() const { return forced_; }
    bool level() const { return level_; }
    // Pętla przejmuje pin w stanie `level` (stan z licznika); następna zmiana za VCOM_HALF_PERIOD_MS.
    void take(uint32_t now, bool level) {
        forced_ = true;
        level_ = level;
        edgeMs_ = now;
    }
    void release() { forced_ = false; }
    // true: stan pinu zmienił się (level()) i trzeba go ustawić teraz.
    bool tick(uint32_t now) {
        if (!forced_ || now - edgeMs_ < VCOM_HALF_PERIOD_MS) return false;
        level_ = !level_;
        edgeMs_ = now;  // spóźnione wybudzenie: następna zmiana pełne pół okresu później
        return true;
    }
    uint32_t untilEdgeMs(uint32_t now) const {
        if (!forced_) return VCOM_HALF_PERIOD_MS;
        const uint32_t since = now - edgeMs_;
        return since >= VCOM_HALF_PERIOD_MS ? 0 : VCOM_HALF_PERIOD_MS - since;
    }

private:
    bool forced_ = false;
    bool level_ = false;
    uint32_t edgeMs_ = 0;
};

// Liczniki do polecenia STANDBY: udział uśpienia w czasie pracy i przyczyny wybudzeń.
struct Counters {
    uint32_t sleeps = 0;
    uint64_t sleptMs = 0;
    uint32_t wakeTimer = 0;
    uint32_t wakeRadio = 0;   // DIO1
    uint32_t wakeInput = 0;   // inna linia z listy (przycisk, CISZA, wyłącznik, laptop)
    uint32_t wakeOther = 0;   // przyczyna nierozpoznana albo linia, która wróciła przed odczytem
    uint32_t rejected = 0;    // ESP-IDF odmówił uśpienia
    uint32_t busy = 0;        // bez uśpienia: DIO1 wysokie, blokada radia zajęta, brzęczyk gra
};

}  // namespace standby
