// SPDX-License-Identifier: MIT
#include "ui.h"

#include <stdio.h>
#include <string.h>

namespace ui {

namespace {

using ui_texts::Id;
using ui_texts::text;

// Nazwy języków na ekranie wyboru: nie ma ich w kanonicznej liście tekstów (do dopisania w specyfikacji).
const char* const LANGUAGE_NAMES[ui_texts::LANGS] = {"POLSKI", "УКРАЇНСЬКА", "ENGLISH"};

constexpr uint8_t MENU_ITEMS = static_cast<uint8_t>(ui_texts::MENU_ITEMS);
constexpr uint8_t MENU_STATUS = static_cast<uint8_t>(ui_texts::Menu::STAN);
constexpr uint8_t MENU_LANGUAGE = static_cast<uint8_t>(ui_texts::Menu::JEZYK);

size_t utf8Bytes(const char* text, size_t chars) {
    // Długość w bajtach pierwszych `chars` znaków.
    size_t bytes = 0;
    size_t n = 0;
    while (text[bytes] && n < chars) {
        const uint8_t first = static_cast<uint8_t>(text[bytes]);
        size_t width = 1;
        if ((first & 0xE0) == 0xC0) width = 2;
        else if ((first & 0xF0) == 0xE0) width = 3;
        else if ((first & 0xF8) == 0xF0) width = 4;
        for (size_t i = 1; i < width && text[bytes + i]; ++i) {
            if ((static_cast<uint8_t>(text[bytes + i]) & 0xC0) != 0x80) { width = i; break; }
        }
        bytes += width;
        ++n;
    }
    return bytes;
}

void formatNumber(char* out, size_t size, uint32_t value) { snprintf(out, size, "%lu", static_cast<unsigned long>(value)); }

void substituteNumber(char* line, size_t size, const char* key, uint32_t value) {
    char number[12];
    char tmp[LINE_BYTES * 2];
    formatNumber(number, sizeof(number), value);
    substitute(line, key, number, tmp, sizeof(tmp));
    copyLine(line, size, tmp);
}

}  // namespace

const char* screenName(Screen screen) {
    switch (screen) {
        case Screen::LANGUAGE: return "language";
        case Screen::MAIN: return "main";
        case Screen::MENU: return "menu";
        case Screen::STATUS: return "status";
        case Screen::ITEM: return "item";
        case Screen::LANGUAGE_MENU: return "language_menu";
        case Screen::COUNT: break;
    }
    return "?";
}

size_t utf8Length(const char* text) {
    size_t n = 0;
    for (const char* p = text; *p; ++p) {
        if ((static_cast<uint8_t>(*p) & 0xC0) != 0x80) ++n;
    }
    return n;
}

void copyLine(char* out, size_t size, const char* text) {
    size_t bytes = utf8Bytes(text, COLS);
    if (bytes >= size) bytes = size - 1;
    memcpy(out, text, bytes);
    out[bytes] = '\0';
}

void substitute(const char* text, const char* key, const char* value, char* out, size_t size) {
    const char* at = strstr(text, key);
    if (!at) {
        snprintf(out, size, "%s", text);
        return;
    }
    snprintf(out, size, "%.*s%s%s", static_cast<int>(at - text), text, value, at + strlen(key));
}

void duration(uint32_t seconds, Lang lang, char* out, size_t size) {
    const char* const* units = ui_texts::UNITS[static_cast<size_t>(lang)];
    const uint32_t minutes = seconds / 60;
    const uint32_t hours = seconds / 3600;
    const uint32_t days = seconds / 86400;
    if (minutes <= 99) snprintf(out, size, "%lu %s", static_cast<unsigned long>(minutes), units[0]);
    else if (hours < 48) snprintf(out, size, "%lu %s", static_cast<unsigned long>(hours), units[1]);
    else snprintf(out, size, "%lu %s", static_cast<unsigned long>(days > 99 ? 99 : days), units[2]);
}

void voltage(uint16_t millivolts, Lang lang, char* out, size_t size) {
    const unsigned tenths = (millivolts + 50) / 100;
    snprintf(out, size, "%u%c%u", tenths / 10, ui_texts::DECIMAL[static_cast<size_t>(lang)], tenths % 10);
}

size_t wrap(const char* text, char out[][LINE_BYTES], size_t maxLines) {
    size_t lines = 0;
    const char* p = text;
    while (*p && lines < maxLines) {
        while (*p == ' ') ++p;
        if (!*p) break;
        // Najdłuższy przedrostek do COLS znaków kończący się przed spacją albo na końcu tekstu.
        size_t bestBytes = 0;
        size_t chars = 0;
        size_t bytes = 0;
        bool fits = true;
        while (p[bytes]) {
            if (p[bytes] == ' ') bestBytes = bytes;
            const size_t width = utf8Bytes(p + bytes, 1);
            if (chars == COLS) { fits = false; break; }
            bytes += width;
            ++chars;
        }
        if (fits) bestBytes = bytes;  // reszta tekstu mieści się w wierszu
        if (bestBytes == 0) bestBytes = utf8Bytes(p, COLS);  // słowo dłuższe niż wiersz: podział twardy
        memcpy(out[lines], p, bestBytes);
        out[lines][bestBytes] = '\0';
        ++lines;
        p += bestBytes;
    }
    return lines;
}

void Model::start(Lang lang) {
    lang_ = lang;
    chosen_ = false;
    screen_ = Screen::LANGUAGE;
    cursor_ = static_cast<uint8_t>(lang);
    top_ = 0;
}

void Model::restore(Lang lang, Screen screen) {
    lang_ = lang;
    chosen_ = true;
    screen_ = screen == Screen::LANGUAGE || screen >= Screen::COUNT ? Screen::MAIN : screen;
    cursor_ = 0;
    top_ = 0;
    item_ = 0;
}

bool Model::takeChange() {
    const bool changed = changed_;
    changed_ = false;
    return changed;
}

void Model::go(Screen screen) {
    if (screen == screen_) return;
    screen_ = screen;
    cursor_ = screen == Screen::LANGUAGE_MENU ? static_cast<uint8_t>(lang_) : 0;
    top_ = 0;
    changed_ = true;
}

void Model::moveCursor(int delta, size_t count, size_t window) {
    if (count == 0) return;
    const int next = static_cast<int>(cursor_) + delta;
    if (next < 0 || next >= static_cast<int>(count)) return;
    cursor_ = static_cast<uint8_t>(next);
    if (cursor_ < top_) top_ = cursor_;
    if (cursor_ >= top_ + window) top_ = static_cast<uint8_t>(cursor_ - window + 1);
}

void Model::tick(uint32_t nowMs) {
    if (screen_ == Screen::LANGUAGE || screen_ == Screen::MAIN) return;
    if (nowMs - lastPressMs_ >= IDLE_MS) go(Screen::MAIN);
}

void Model::press(Button button, uint32_t nowMs) {
    lastPressMs_ = nowMs;
    // Rozmiar okna listy zależy od trybu przygotowania, którego model tu nie zna; przyjmuje pełne 5 wierszy,
    // a render() dosuwa okno do kursora.
    switch (screen_) {
        case Screen::LANGUAGE:
        case Screen::LANGUAGE_MENU:
            if (button == Button::UP) moveCursor(-1, ui_texts::LANGS, LINES);
            else if (button == Button::DOWN) moveCursor(1, ui_texts::LANGS, LINES);
            else if (button == Button::OK) {
                lang_ = static_cast<Lang>(cursor_);
                chosen_ = true;
                changed_ = true;
                go(screen_ == Screen::LANGUAGE ? Screen::MAIN : Screen::MENU);
            } else if (button == Button::BACK && screen_ == Screen::LANGUAGE_MENU) go(Screen::MENU);
            break;
        case Screen::MAIN:
            if (button == Button::OK) go(Screen::MENU);
            break;
        case Screen::MENU:
            if (button == Button::UP) moveCursor(-1, MENU_ITEMS, LINES);
            else if (button == Button::DOWN) moveCursor(1, MENU_ITEMS, LINES);
            else if (button == Button::BACK) go(Screen::MAIN);
            else if (button == Button::OK) {
                item_ = cursor_;
                if (cursor_ == MENU_STATUS) go(Screen::STATUS);
                else if (cursor_ == MENU_LANGUAGE) go(Screen::LANGUAGE_MENU);
                else go(Screen::ITEM);
            }
            break;
        case Screen::STATUS:
            if (button == Button::UP && top_ > 0) --top_;
            else if (button == Button::DOWN && top_ < STATUS_MAX_LINES - 1) ++top_;  // render() ogranicza do listy
            else if (button == Button::BACK) go(Screen::MENU);
            break;
        case Screen::ITEM:
            if (button == Button::BACK) go(Screen::MENU);
            break;
        case Screen::COUNT:
            break;
    }
    if (screen_ == Screen::MENU && item_ != cursor_ && button == Button::BACK) cursor_ = item_;  // powrót na pozycję
}

void Model::renderMain(const Status& s, char out[][LINE_BYTES], size_t count) const {
    const size_t L = static_cast<size_t>(lang_);
    char value[24];
    char tmp[LINE_BYTES * 2];
    size_t n = 0;
    if (s.silence) {
        // Wiersze 1-3: pełny tekst ciszy; wiersze 4-5: zasilanie i kolejka.
        char lines[3][LINE_BYTES];
        const size_t wrapped = wrap(text(Id::CISZA, lang_), lines, 3);
        for (size_t i = 0; i < 3; ++i) copyLine(out[n++], LINE_BYTES, i < wrapped ? lines[i] : "");
    } else {
        copyLine(out[n++], LINE_BYTES, s.radioOk ? text(Id::RADIO_WLACZONE, lang_) : "RADIO ---");
        duration(s.contactS, lang_, value, sizeof(value));
        substitute(text(s.contactKnown ? Id::KONTAKT_KROTKI : Id::KONTAKT_PONAD_KROTKI, lang_), "[czas]", value, tmp, sizeof(tmp));
        copyLine(out[n++], LINE_BYTES, tmp);
    }
    if (s.mains12) {
        voltage(s.millivolts, lang_, value, sizeof(value));
        substitute(text(Id::ZASILANIE_12V, lang_), "[x]", value, tmp, sizeof(tmp));
    } else {
        formatNumber(value, sizeof(value), s.cellHours);
        substitute(text(Id::ZASILANIE_AA, lang_), "[x]", value, tmp, sizeof(tmp));
    }
    copyLine(out[n++], LINE_BYTES, tmp);
    if (s.queued) {
        duration(s.queueAgeS, lang_, value, sizeof(value));
        substitute(text(Id::KOLEJKA_KROTKI, lang_), "[czas]", value, tmp, sizeof(tmp));
        copyLine(out[n], LINE_BYTES, tmp);
        substituteNumber(out[n], LINE_BYTES, "[n]", s.queued);
    } else {
        out[n][0] = '\0';
    }
    ++n;
    if (n < count) {
        copyLine(out[n], LINE_BYTES, text(Id::NOWE_KROTKI, lang_));
        substituteNumber(out[n], LINE_BYTES, "[n]", s.newMessages);
        ++n;
    }
    (void)L;
}

size_t Model::statusLines(const Status& s, char out[][LINE_BYTES], size_t max) const {
    size_t n = 0;
    char value[24];
    char tmp[LINE_BYTES * 2];
    auto put = [&](const char* line) { if (n < max) copyLine(out[n++], LINE_BYTES, line); };
    put(s.radioOk ? text(Id::RADIO_WLACZONE, lang_) : "RADIO ---");
    snprintf(tmp, sizeof(tmp), "RX OK %lu", static_cast<unsigned long>(s.rxOk)); put(tmp);
    snprintf(tmp, sizeof(tmp), "RX BAD %lu", static_cast<unsigned long>(s.rxBad)); put(tmp);
    snprintf(tmp, sizeof(tmp), "TX %lu DROP %lu", static_cast<unsigned long>(s.txDatagrams), static_cast<unsigned long>(s.txDrop)); put(tmp);
    snprintf(tmp, sizeof(tmp), "DEFER %lu", static_cast<unsigned long>(s.deferrals)); put(tmp);
    snprintf(tmp, sizeof(tmp), "WAIT %lu S", static_cast<unsigned long>((s.debtMs + 999) / 1000)); put(tmp);
    duration(s.contactS, lang_, value, sizeof(value));
    substitute(text(s.contactKnown ? Id::OSTATNI_KONTAKT : Id::OSTATNI_KONTAKT_PONAD, lang_), "[czas]", value, tmp, sizeof(tmp));
    char lines[4][LINE_BYTES];
    const size_t wrapped = wrap(tmp, lines, 4);
    for (size_t i = 0; i < wrapped; ++i) put(lines[i]);
    if (s.mains12) {
        voltage(s.millivolts, lang_, value, sizeof(value));
        substitute(text(Id::ZASILANIE_12V, lang_), "[x]", value, tmp, sizeof(tmp));
    } else {
        formatNumber(value, sizeof(value), s.cellHours);
        substitute(text(Id::OGNIWA_CZAS, lang_), "[x]", value, tmp, sizeof(tmp));
    }
    put(tmp);
    if (s.foffValid) snprintf(tmp, sizeof(tmp), "FOFF %+ld HZ", static_cast<long>(s.foffHz));
    else snprintf(tmp, sizeof(tmp), "FOFF ---");
    put(tmp);
    put(s.version);
    put(s.name);
    return n;
}

void Model::renderList(const char* const* items, size_t count, size_t window, Lines& out, size_t first, bool mark) const {
    size_t top = top_;
    if (mark) {
        // Okno dosunięte do kursora (rozmiar okna zależy od paska trybu przygotowania).
        if (cursor_ < top) top = cursor_;
        if (cursor_ >= top + window) top = cursor_ - window + 1;
    }
    if (top + window > count) top = count > window ? count - window : 0;
    for (size_t i = 0; i < window; ++i) {
        const size_t index = top + i;
        copyLine(out.text[first + i], LINE_BYTES, index < count ? items[index] : "");
        out.inverted[first + i] = mark && index == cursor_;
    }
}

void Model::render(const Status& s, Lines& out) const {
    for (size_t i = 0; i < LINES; ++i) { out.text[i][0] = '\0'; out.inverted[i] = false; }
    size_t first = 0;
    if (s.prep) copyLine(out.text[first++], LINE_BYTES, text(Id::TRYB_PRZYGOTOWANIA, lang_));
    const size_t window = LINES - first;
    const size_t L = static_cast<size_t>(lang_);
    switch (screen_) {
        case Screen::LANGUAGE:
        case Screen::LANGUAGE_MENU:
            renderList(LANGUAGE_NAMES, ui_texts::LANGS, window, out, first, true);
            break;
        case Screen::MAIN: {
            char lines[LINES][LINE_BYTES];
            renderMain(s, lines, LINES);
            for (size_t i = 0; i < window; ++i) copyLine(out.text[first + i], LINE_BYTES, lines[i]);
            break;
        }
        case Screen::MENU: {
            const char* items[MENU_ITEMS];
            for (size_t i = 0; i < MENU_ITEMS; ++i) items[i] = ui_texts::MENU[i][L];
            renderList(items, MENU_ITEMS, window, out, first, true);
            break;
        }
        case Screen::STATUS: {
            char lines[STATUS_MAX_LINES][LINE_BYTES];
            const size_t count = statusLines(s, lines, STATUS_MAX_LINES);
            const char* items[STATUS_MAX_LINES];
            for (size_t i = 0; i < count; ++i) items[i] = lines[i];
            renderList(items, count, window, out, first, false);
            break;
        }
        case Screen::ITEM:
            copyLine(out.text[first], LINE_BYTES, ui_texts::MENU[item_ < MENU_ITEMS ? item_ : 0][L]);
            break;
        case Screen::COUNT:
            break;
    }
}

}  // namespace ui
