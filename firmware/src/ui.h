// SPDX-License-Identifier: MIT
// Model ekranu i przycisków stacji (docs/spec/oprogramowanie.md, "Ekran i przyciski stacji"):
// wybór języka po włączeniu, ekran główny z pięciu krótkich form, cisza radiowa, pasek trybu
// przygotowania, menu (ZGŁOSZENIE, WIADOMOŚCI, TEST, STAN, JĘZYK), ekran STAN z przewijaniem.
// Wynikiem jest 5 wierszy tekstu UTF-8 po najwyżej 20 znaków z zaznaczeniem wiersza
// odwróconego; rysowanie jest poza modelem. Bez zależności od Arduino; sprawdzany na komputerze.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "ui_texts.h"

namespace ui {

using ui_texts::Lang;

constexpr size_t LINES = 5;
constexpr size_t COLS = ui_texts::MAX_COLUMNS;
constexpr size_t LINE_BYTES = 3 * COLS + 1;  // UTF-8 do 3 B na znak
constexpr uint32_t IDLE_MS = 180000;          // powrót do ekranu głównego po 3 min bezczynności
constexpr size_t STATUS_MAX_LINES = 16;

enum class Button : uint8_t { UP, DOWN, OK, BACK };
enum class Screen : uint8_t { LANGUAGE, MAIN, MENU, STATUS, ITEM, LANGUAGE_MENU, COUNT };
const char* screenName(Screen screen);

// Stan stacji pokazywany na ekranie; wartości dostarcza main.cpp.
struct Status {
    bool prep = false;
    bool silence = false;
    bool radioOk = false;
    bool contactKnown = false;   // false: dolne oszacowanie "PONAD [czas]" (bez RTC)
    uint32_t contactS = 0;       // czas od ostatniego kontaktu albo dolne oszacowanie [s]
    bool mains12 = true;         // praca z 12 V (false: ogniwa)
    uint16_t millivolts = 0;     // napięcie 12 V
    uint32_t cellHours = 0;      // szacowany czas pracy z ogniw [h]
    uint32_t queued = 0;         // niewysłane zgłoszenia
    uint32_t queueAgeS = 0;      // wiek najstarszego [s]
    uint32_t newMessages = 0;
    uint32_t rxOk = 0, rxBad = 0, txDatagrams = 0, txDrop = 0, deferrals = 0;
    uint32_t debtMs = 0;
    bool foffValid = false;
    int32_t foffHz = 0;
    const char* version = "";
    const char* name = "";
};

struct Lines {
    char text[LINES][LINE_BYTES] = {};
    bool inverted[LINES] = {};
};

class Model {
public:
    // Po włączeniu: ekran wyboru języka (lang to tylko położenie kursora).
    void start(Lang lang);
    // Po restarcie przez watchdog: język z pamięci i poprzedni ekran.
    void restore(Lang lang, Screen screen);
    void press(Button button, uint32_t nowMs);
    void tick(uint32_t nowMs);
    void render(const Status& status, Lines& out) const;
    Lang language() const { return lang_; }
    Screen screen() const { return screen_; }
    bool languageChosen() const { return chosen_; }
    // true jeden raz po zmianie języka albo ekranu (do zapisu w FRAM).
    bool takeChange();
    // Wiersze ekranu STAN (również do testów); zwraca ich liczbę.
    size_t statusLines(const Status& status, char out[][LINE_BYTES], size_t max) const;

private:
    void go(Screen screen);
    size_t window(const Status& status) const { return status.prep ? LINES - 1 : LINES; }
    void moveCursor(int delta, size_t count, size_t window);
    void renderMain(const Status& status, char out[][LINE_BYTES], size_t count) const;
    void renderList(const char* const* items, size_t count, size_t window, Lines& out, size_t first, bool mark) const;

    Lang lang_ = Lang::PL;
    bool chosen_ = false;
    Screen screen_ = Screen::LANGUAGE;
    uint8_t cursor_ = 0;
    uint8_t top_ = 0;
    uint8_t item_ = 0;
    uint32_t lastPressMs_ = 0;
    bool changed_ = false;
};

// Pomocnicze (sprawdzane osobno).
// Łamanie tekstu na wiersze po najwyżej COLS znaków, na spacjach; zwraca liczbę wierszy.
size_t wrap(const char* text, char out[][LINE_BYTES], size_t maxLines);
// [czas]: minuty do 99 MIN, potem godziny (H), od 48 H doby (D, do 99 D), jednostki języka.
void duration(uint32_t seconds, Lang lang, char* out, size_t size);
// Napięcie z jednym miejscem po przecinku (kropka w EN).
void voltage(uint16_t millivolts, Lang lang, char* out, size_t size);
// Podstawienie pierwszego wystąpienia klucza (np. "[czas]").
void substitute(const char* text, const char* key, const char* value, char* out, size_t size);
// Kopia obcięta do COLS znaków.
void copyLine(char* out, size_t size, const char* text);
size_t utf8Length(const char* text);

}  // namespace ui
