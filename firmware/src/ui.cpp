// SPDX-License-Identifier: MIT
#include "ui.h"

#include <stdio.h>
#include <string.h>

namespace ui {

namespace {

using ui_texts::Id;
using ui_texts::Label;
using ui_texts::text;
using ui_texts::label;

// Nazwy języków na ekranie wyboru: nie ma ich w kanonicznej liście tekstów (do dopisania w specyfikacji).
const char* const LANGUAGE_NAMES[ui_texts::LANGS] = {"POLSKI", "УКРАЇНСЬКА", "ENGLISH"};
// Lista liczby osób ze specyfikacji; ostatnia pozycja to INNA (wpis cyfra po cyfrze).
const uint16_t PEOPLE_VALUES[] = {1, 2, 5, 10, 20, 50, 100};
constexpr size_t PEOPLE_CHOICES = sizeof(PEOPLE_VALUES) / sizeof(PEOPLE_VALUES[0]) + 1;
constexpr uint8_t MENU_ITEMS = static_cast<uint8_t>(ui_texts::MENU_ITEMS);
constexpr size_t SERVICE_ITEMS = 4;  // OGŁOŚ ADRES, WYCISZ/WŁĄCZ DŹWIĘK, KLUCZ ZAPASOWY, ZNISZCZ DANE
constexpr Button SEQUENCE[4] = {Button::UP, Button::DOWN, Button::UP, Button::OK};
constexpr Id STATE_TEXTS[6] = {Id::STAN_1, Id::STAN_2, Id::STAN_3, Id::STAN_4, Id::STAN_5, Id::STAN_6};
constexpr Id URGENCY_TEXTS[3] = {Id::PILNOSC_0, Id::PILNOSC_1, Id::PILNOSC_2};
constexpr uint8_t SA1_REQUEST = 0, SA1_REPLY = 3, SA1_BULLETIN = 4, SA1_TEST = 5;
// Teksty pytań poleceń USB i odcisku `card` według ui::Question.
constexpr Id QUESTION_TEXTS[] = {Id::PYTANIE_CISZA_WLACZ, Id::PYTANIE_CISZA_WYLACZ, Id::PYTANIE_ZAMKNIJ, Id::PYTANIE_ZNISZCZ,
                                 Id::PYTANIE_CISZA_WYJATEK, Id::ODCISK_KLUCZA};

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

// Krótki numer zgłoszenia: cztery cyfry.
void formatShort(char* out, size_t size, uint16_t number) { snprintf(out, size, "%04u", static_cast<unsigned>(number % 10000)); }

}  // namespace

// Wiersze tekstu do przewijania: łamane teksty i pojedyncze wiersze.
struct Model::Text {
    char line[TEXT_MAX_LINES][LINE_BYTES];
    size_t count = 0;
    void add(const char* text) {
        if (count >= TEXT_MAX_LINES) return;
        count += wrap(text, line + count, TEXT_MAX_LINES - count);
    }
    void addLine(const char* text) {
        if (count < TEXT_MAX_LINES) copyLine(line[count++], LINE_BYTES, text);
    }
    void addNumber(Id id, const char* key, uint32_t value, Lang lang) {
        char tmp[320];
        char number[12];
        formatNumber(number, sizeof(number), value);
        substitute(text(id, lang), key, number, tmp, sizeof(tmp));
        add(tmp);
    }
    void addShort(Id id, uint16_t number, Lang lang) {
        char tmp[320];
        char digits[8];
        formatShort(digits, sizeof(digits), number);
        substitute(text(id, lang), "[xxxx]", digits, tmp, sizeof(tmp));
        add(tmp);
    }
};

const char* screenName(Screen screen) {
    switch (screen) {
        case Screen::LANGUAGE: return "language";
        case Screen::MAIN: return "main";
        case Screen::MENU: return "menu";
        case Screen::STATUS: return "status";
        case Screen::LANGUAGE_MENU: return "language_menu";
        case Screen::ADDRESS: return "address";
        case Screen::ADDRESS_LIST: return "address_list";
        case Screen::TEST_OFFER: return "test_offer";
        case Screen::CATEGORY: return "category";
        case Screen::PEOPLE: return "people";
        case Screen::DIGITS: return "digits";
        case Screen::URGENCY: return "urgency";
        case Screen::URGENCY_CONFIRM: return "urgency_confirm";
        case Screen::PHRASE: return "phrase";
        case Screen::SUMMARY: return "summary";
        case Screen::RESULT: return "result";
        case Screen::DISCARD: return "discard";
        case Screen::MESSAGES: return "messages";
        case Screen::ITEM: return "item";
        case Screen::ITEM_MENU: return "item_menu";
        case Screen::TEST: return "test";
        case Screen::TEST_MENU: return "test_menu";
        case Screen::HANDOVER: return "handover";
        case Screen::SERVICES: return "services";
        case Screen::BACKUP: return "backup";
        case Screen::DESTROY: return "destroy";
        case Screen::ALARM: return "alarm";
        case Screen::CONFIRM: return "confirm";
        case Screen::COUNT: break;
    }
    return "?";
}

void copyLine(char* out, size_t size, const char* text) {
    size_t bytes = utf8Bytes(text, COLS);
    if (bytes >= size) {
        bytes = size - 1;
        while (bytes && (static_cast<uint8_t>(text[bytes]) & 0xC0) == 0x80) --bytes;  // bez połowy znaku
    }
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

size_t Model::menu(ui_texts::Menu out[]) const {
    if (node()) {
        out[0] = ui_texts::Menu::STAN;
        out[1] = ui_texts::Menu::JEZYK;
        return 2;
    }
    for (size_t i = 0; i < MENU_ITEMS; ++i) out[i] = static_cast<ui_texts::Menu>(i);
    return MENU_ITEMS;
}

uint8_t Model::menuIndex(ui_texts::Menu item) const {
    ui_texts::Menu items[MENU_ITEMS];
    const size_t count = menu(items);
    for (size_t i = 0; i < count; ++i) if (items[i] == item) return static_cast<uint8_t>(i);
    return 0;
}

size_t Model::services(Service out[]) const {
    // Węzeł OSP nie ma adresu LXMF ani karty OSP: bez OGŁOŚ ADRES i KLUCZ ZAPASOWY.
    size_t n = 0;
    if (!node()) out[n++] = Service::ANNOUNCE;
    out[n++] = Service::MUTE;
    if (!node()) out[n++] = Service::BACKUP;
    out[n++] = Service::DESTROY;
    return n;
}

void Model::computerLine(const Status& s, char* out, size_t size) const {
    char value[24];
    char tmp[LINE_BYTES * 2];
    if (!s.computerHeard) { copyLine(out, size, text(Id::KOMPUTER_BRAK, lang_)); return; }
    duration(s.computerS, lang_, value, sizeof(value));
    substitute(text(Id::KOMPUTER_OSP, lang_), "[czas]", value, tmp, sizeof(tmp));
    copyLine(out, size, tmp);
}

void Model::start(Lang lang) {
    lang_ = lang;
    screen_ = Screen::LANGUAGE;
    cursor_ = static_cast<uint16_t>(lang);
    top_ = 0;
}

void Model::restore(Lang lang, Screen screen) {
    lang_ = lang;
    screen_ = screen == Screen::MENU || screen == Screen::STATUS ? screen : Screen::MAIN;
    cursor_ = 0;
    top_ = 0;
    item_ = 0;
}

void Model::ask(Question question, const char* detail) {
    if (screen_ != Screen::CONFIRM) beforeQuestion_ = screen_;
    question_ = question;
    answer_ = Answer::WAITING;
    snprintf(questionDetail_, sizeof(questionDetail_), "%s", detail ? detail : "");
    go(Screen::CONFIRM);
}

void Model::dismiss() {
    if (answer_ == Answer::WAITING) answer_ = Answer::NO;
    if (screen_ == Screen::CONFIRM) go(beforeQuestion_);
}

bool Model::takeChange() {
    const bool changed = changed_;
    changed_ = false;
    return changed;
}

void Model::scroll(bool up, bool down) {
    if (up && top_ > 0) --top_;
    else if (down && top_ + 1 < lastCount_) ++top_;
}

void Model::resetDraft() {
    draft_ = Draft();
    draft_.people = lastPeople_;
}

const char* Model::itemLabel(const Item& item) const {
    return item.type == SA1_TEST ? label(Label::TEST, lang_) : ui_texts::CATEGORIES[item.category < 10 ? item.category : 9][static_cast<size_t>(lang_)];
}

void Model::peopleLine(uint16_t people, uint8_t urgency, char* out, size_t size) const {
    snprintf(out, size, "%u %s", static_cast<unsigned>(people), text(URGENCY_TEXTS[urgency < 3 ? urgency : 0], lang_));
}

bool Model::inWizard() const { return screen_ >= Screen::CATEGORY && screen_ <= Screen::SUMMARY; }

void Model::go(Screen screen) {
    if (screen == screen_) return;
    if (screen == Screen::MESSAGES) cursor_ = messagesCursor_;  // powrót na pozycję listy
    else if (screen == Screen::LANGUAGE_MENU) cursor_ = static_cast<uint16_t>(lang_);
    else if (screen == Screen::MENU) cursor_ = item_;
    else if (screen == Screen::CATEGORY) cursor_ = draft_.category;
    else if (screen == Screen::PEOPLE) {
        cursor_ = PEOPLE_CHOICES - 1;  // INNA, chyba że liczba jest na liście
        for (size_t i = 0; i < PEOPLE_CHOICES - 1; ++i) if (PEOPLE_VALUES[i] == draft_.people) cursor_ = static_cast<uint16_t>(i);
    } else if (screen == Screen::URGENCY) { cursor_ = 0; urgencyPicked_ = false; }
    else if (screen == Screen::ADDRESS_LIST) cursor_ = static_cast<uint16_t>(host_ ? host_->selectedAddress() : 0);
    else if (screen == Screen::PHRASE) {
        const size_t none = draft_.category == 9 ? 0 : 1;
        cursor_ = static_cast<uint16_t>(draft_.phrase >= 0 ? draft_.phrase + none : 0);
    } else cursor_ = 0;
    screen_ = screen;
    top_ = 0;
    sequence_ = 0;
    changed_ = true;
    if (screen == Screen::STATUS) {
        char lines[STATUS_MAX_LINES][LINE_BYTES];
        lastCount_ = static_cast<uint16_t>(statusLines(lastStatus_, lines, STATUS_MAX_LINES));  // kursor przed pierwszym rysowaniem
    }
}

void Model::moveCursor(int delta, size_t count, size_t window) {
    if (count == 0) return;
    const int next = static_cast<int>(cursor_) + delta;
    if (next < 0 || next >= static_cast<int>(count)) return;
    cursor_ = static_cast<uint16_t>(next);
    if (cursor_ < top_) top_ = cursor_;
    if (cursor_ >= top_ + window) top_ = static_cast<uint16_t>(cursor_ - window + 1);
}

size_t Model::phraseListCount() const {
    const size_t phrases = host_ ? host_->phraseCount() : 0;
    return phrases + (draft_.category == 9 ? 0 : 1);
}

Screen Model::afterPeople() const { return draft_.kind == DraftKind::NEW ? Screen::URGENCY : Screen::SUMMARY; }
Screen Model::afterUrgency() const { return draft_.kind == DraftKind::NEW ? Screen::PHRASE : Screen::SUMMARY; }

void Model::beginWizard(DraftKind kind, uint32_t ref, const Item* item) {
    draft_.kind = kind;
    draft_.ref = ref;
    if (item) {
        draft_.category = item->category;
        draft_.people = item->people;
        draft_.urgency = item->urgency;
        draft_.phrase = phraseIndex(item->text);   // zmiana liczby osób albo pilności zachowuje frazę
    }
    if (kind == DraftKind::RESOLVED) draft_.phrase = PHRASE_RESOLVED;
}

int8_t Model::phraseIndex(const char* polish) const {
    if (!polish[0]) return PHRASE_NONE;
    const size_t count = host_ ? host_->phraseCount() : 0;
    for (size_t i = 0; i < count; ++i)
        if (!strcmp(host_->phrase(i, Lang::PL), polish)) return static_cast<int8_t>(i);
    if (!strcmp(ui_texts::PHRASES[ui_texts::PHRASES_COUNT - 1][0], polish)) return PHRASE_RESOLVED;
    return PHRASE_KEPT;
}

const char* Model::shownPhrase(const char* polish) const {
    const int8_t index = phraseIndex(polish);
    if (index >= 0) return host_->phrase(static_cast<size_t>(index), lang_);
    // Frazy domyślne także przy własnej liście stacji (np. POTRZEBA USTAŁA, zgłoszenie z panelu).
    for (size_t i = 0; i < ui_texts::PHRASES_COUNT; ++i)
        if (!strcmp(ui_texts::PHRASES[i][0], polish)) return ui_texts::PHRASES[i][static_cast<size_t>(lang_)];
    return polish;
}

void Model::tick(uint32_t nowMs) {
    // Alarm zajmuje cały ekran do potwierdzenia (sprawdzany co sekundę); pytanie USB czeka najwyżej 30 s.
    if (host_ && screen_ != Screen::ALARM && screen_ != Screen::LANGUAGE && screen_ != Screen::CONFIRM && nowMs - alarmCheckMs_ >= 1000) {
        alarmCheckMs_ = nowMs;
        AlarmInfo alarm;
        if (host_->alarm(alarm)) {
            alarm_ = alarm;
            beforeAlarm_ = screen_;
            go(Screen::ALARM);
            lastPressMs_ = nowMs;
        }
    }
    // Przytrzymanie WSTECZ: 2 s w kreatorze (porzucić?), 3 s poza nim (wybór języka).
    const size_t back = static_cast<size_t>(Button::BACK);
    if (held_[back] && !holdConsumed_) {
        const uint32_t held = nowMs - heldSinceMs_[back];
        if (inWizard() && held >= HOLD_DISCARD_MS) {
            holdConsumed_ = true;
            returnTo_ = screen_;
            go(Screen::DISCARD);
        } else if (!inWizard() && held >= HOLD_LANGUAGE_MS && screen_ != Screen::LANGUAGE && screen_ != Screen::ALARM &&
                   screen_ != Screen::BACKUP && screen_ != Screen::DESTROY && screen_ != Screen::RESULT && screen_ != Screen::DISCARD &&
                   screen_ != Screen::CONFIRM) {
            holdConsumed_ = true;
            item_ = menuIndex(ui_texts::Menu::JEZYK);
            go(Screen::LANGUAGE_MENU);
        }
    }
    // Wpis cyfr: przytrzymany przycisk GÓRA albo DÓŁ powtarza zmianę.
    if (screen_ == Screen::DIGITS) {
        const Button repeatable[2] = {Button::UP, Button::DOWN};
        for (Button b : repeatable) {
            const size_t i = static_cast<size_t>(b);
            if (held_[i] && nowMs - heldSinceMs_[i] >= REPEAT_DELAY_MS && nowMs - repeatMs_ >= REPEAT_MS) {
                repeatMs_ = nowMs;
                act(b, nowMs);
            }
        }
    }
    if (screen_ == Screen::LANGUAGE || screen_ == Screen::MAIN || screen_ == Screen::ALARM || screen_ == Screen::CONFIRM) return;
    if (nowMs - lastPressMs_ >= IDLE_MS) go(Screen::MAIN);  // szkic kreatora zostaje w pamięci
}

void Model::down(Button button, uint32_t nowMs) {
    const size_t i = static_cast<size_t>(button);
    held_[i] = true;
    heldSinceMs_[i] = nowMs;
    repeatMs_ = nowMs;
    if (button == Button::BACK) { holdConsumed_ = false; lastPressMs_ = nowMs; return; }
    act(button, nowMs);
}

void Model::up(Button button, uint32_t nowMs) {
    const size_t i = static_cast<size_t>(button);
    held_[i] = false;
    if (button == Button::BACK) {
        if (!holdConsumed_) act(button, nowMs);
        holdConsumed_ = false;
    }
}

void Model::press(Button button, uint32_t nowMs) {
    down(button, nowMs);
    up(button, nowMs);
}

void Model::submit() {
    uint16_t number = 0;
    result_ = host_ ? host_->submit(draft_, number) : Submit::ERROR;
    resultNumber_ = number;
    resultSilence_ = lastStatus_.silence;
    if (result_ == Submit::STORED) lastPeople_ = draft_.people;
}

void Model::act(Button button, uint32_t nowMs) {
    lastPressMs_ = nowMs;
    // Rozmiar okna listy zależy od trybu przygotowania, którego model tu nie zna; przyjmuje pełne 5 wierszy,
    // a render() dosuwa okno do kursora.
    const bool up = button == Button::UP, downB = button == Button::DOWN, ok = button == Button::OK, back = button == Button::BACK;
    switch (screen_) {
        case Screen::LANGUAGE:
        case Screen::LANGUAGE_MENU:
            if (up) moveCursor(-1, ui_texts::LANGS, LINES);
            else if (downB) moveCursor(1, ui_texts::LANGS, LINES);
            else if (ok) {
                lang_ = static_cast<Lang>(cursor_);
                            changed_ = true;
                if (screen_ == Screen::LANGUAGE) {
                    addressMissing_ = false;
                    // Węzeł OSP nie ma adresu i nie proponuje TEST: od razu ekran główny.
                    go(!host_ || node() ? Screen::MAIN : host_->addressCount() > 1 ? Screen::ADDRESS_LIST : Screen::ADDRESS);
                }
                else go(Screen::MENU);
            } else if (back && screen_ == Screen::LANGUAGE_MENU) go(Screen::MENU);
            break;
        case Screen::ADDRESS:
            if (ok || back) {
                // NIE: przy liście obiektów powrót do wyboru, przy jednym adresie adres_brak.
                if (!addressMissing_ && back && host_ && host_->addressCount() > 1) go(Screen::ADDRESS_LIST);
                else if (!addressMissing_ && back && host_ && host_->address()[0]) addressMissing_ = true;
                else go(Screen::TEST_OFFER);
            } else scroll(up, downB);
            break;
        case Screen::ADDRESS_LIST: {
            const size_t count = host_ ? host_->addressCount() : 0;
            if (up) moveCursor(-1, count, LINES);
            else if (downB) moveCursor(1, count, LINES);
            else if (ok) {
                if (host_) host_->selectAddress(cursor_);
                go(Screen::ADDRESS);   // zmiana ekranu zapisuje też wybór obiektu (main.cpp, ustawienia)
            } else if (back) {
                addressMissing_ = true;   // żaden obiekt z listy: adres_brak
                go(Screen::ADDRESS);
            }
            break;
        }
        case Screen::TEST_OFFER:
            if (ok) { if (host_) host_->scheduleTest(true); go(Screen::TEST); }
            else if (back) go(Screen::MAIN);
            break;
        case Screen::MAIN:
            if (ok) { item_ = 0; go(Screen::MENU); }
            break;
        case Screen::MENU: {
            ui_texts::Menu items[MENU_ITEMS];
            const size_t count = menu(items);
            if (up) moveCursor(-1, count, LINES);
            else if (downB) moveCursor(1, count, LINES);
            else if (back) go(Screen::MAIN);
            else if (ok && cursor_ < count) {
                item_ = static_cast<uint8_t>(cursor_);
                switch (items[cursor_]) {
                    case ui_texts::Menu::ZGLOSZENIE: beginWizard(DraftKind::NEW, 0, nullptr); go(Screen::CATEGORY); break;
                    case ui_texts::Menu::WIADOMOSCI: messagesCursor_ = 0; go(Screen::MESSAGES); break;
                    case ui_texts::Menu::TEST: go(Screen::TEST); break;
                    case ui_texts::Menu::STAN: go(Screen::STATUS); break;
                    case ui_texts::Menu::JEZYK: go(Screen::LANGUAGE_MENU); break;
                }
            }
            break;
        }
        case Screen::STATUS:
            // Ostatnie wiersze: PRZEKAZANIE ZMIANY (nie w węźle OSP) i USŁUGI.
            if (up) moveCursor(-1, lastCount_, LINES);
            else if (downB) moveCursor(1, lastCount_, LINES);
            else if (back) go(Screen::MENU);
            else if (ok && lastCount_ >= 2) {
                if (cursor_ == lastCount_ - 1) go(Screen::SERVICES);
                else if (cursor_ == lastCount_ - 2 && !node()) go(Screen::HANDOVER);
            }
            break;
        case Screen::HANDOVER:
            if (ok || back) go(Screen::STATUS);
            else scroll(up, downB);
            break;
        case Screen::SERVICES: {
            Service items[SERVICE_ITEMS];
            const size_t count = services(items);
            if (up) moveCursor(-1, count, LINES);
            else if (downB) moveCursor(1, count, LINES);
            else if (back) go(Screen::STATUS);
            else if (ok && cursor_ < count) {
                switch (items[cursor_]) {
                    case Service::ANNOUNCE:
                        // Ogłoszenie bez sekwencji: nie zmienia danych, w ciszy czeka na jej odwołanie.
                        result_ = host_ && host_->announce() ? Submit::ANNOUNCED : Submit::NOT_ANNOUNCED;
                        serviceResult_ = true;
                        go(Screen::RESULT);
                        break;
                    case Service::MUTE:
                        muted_ = !muted_;
                        changed_ = true;
                        break;
                    case Service::BACKUP: go(Screen::BACKUP); break;
                    case Service::DESTROY: go(Screen::DESTROY); break;
                }
            }
            break;
        }
        case Screen::BACKUP:
        case Screen::DESTROY:
            // Sekwencja GÓRA, DÓŁ, GÓRA, OK; inny przycisk zaczyna od nowa, WSTECZ wychodzi.
            if (back) go(Screen::SERVICES);
            else if (button == SEQUENCE[sequence_]) {
                if (++sequence_ == 4) {
                    const bool done = host_ && (screen_ == Screen::BACKUP ? host_->switchBackup() : host_->destroy());
                    if (done) go(screen_ == Screen::BACKUP ? Screen::STATUS : Screen::MAIN);
                    else {
                        // Brak zapasowej tożsamości OSP albo błąd zapisu: komunikat, nie cichy powrót.
                        result_ = Submit::ERROR;
                        serviceResult_ = true;
                        go(Screen::RESULT);
                    }
                }
            } else sequence_ = button == SEQUENCE[0] ? 1 : 0;
            break;
        case Screen::CATEGORY:
            if (up) moveCursor(-1, 10, LINES);
            else if (downB) moveCursor(1, 10, LINES);
            else if (back) go(Screen::MENU);
            else if (ok) {
                draft_.category = static_cast<uint8_t>(cursor_);
                go(Screen::PEOPLE);
            }
            break;
        case Screen::PEOPLE:
            if (up) moveCursor(-1, PEOPLE_CHOICES, LINES);
            else if (downB) moveCursor(1, PEOPLE_CHOICES, LINES);
            else if (back) go(draft_.kind == DraftKind::NEW ? Screen::CATEGORY : Screen::ITEM_MENU);
            else if (ok) {
                if (cursor_ == PEOPLE_CHOICES - 1) {
                    const uint16_t start = draft_.people > PEOPLE_MAX ? lastPeople_ : draft_.people;
                    digits_[0] = static_cast<uint8_t>(start / 100);
                    digits_[1] = static_cast<uint8_t>(start / 10 % 10);
                    digits_[2] = static_cast<uint8_t>(start % 10);
                    digitPos_ = 0;
                    go(Screen::DIGITS);
                } else {
                    draft_.people = PEOPLE_VALUES[cursor_];
                    go(afterPeople());
                }
            }
            break;
        case Screen::DIGITS:
            if (up) digits_[digitPos_] = static_cast<uint8_t>((digits_[digitPos_] + 1) % 10);
            else if (downB) digits_[digitPos_] = static_cast<uint8_t>((digits_[digitPos_] + 9) % 10);
            else if (back) { if (digitPos_ > 0) --digitPos_; else go(Screen::PEOPLE); }
            else if (ok) {
                if (digitPos_ < 2) ++digitPos_;
                else {
                    const uint16_t value = static_cast<uint16_t>(digits_[0] * 100 + digits_[1] * 10 + digits_[2]);
                    if (value >= 1) { draft_.people = value; go(afterPeople()); }
                }
            }
            break;
        case Screen::URGENCY:
            // Bez wartości domyślnej: pierwszy ruch kursora pokazuje wybór.
            if (up || downB) {
                if (!urgencyPicked_) { urgencyPicked_ = true; cursor_ = up ? 2 : 0; }
                else moveCursor(up ? -1 : 1, 3, LINES);
            } else if (back) go(draft_.kind == DraftKind::NEW ? Screen::PEOPLE : Screen::ITEM_MENU);
            else if (ok && urgencyPicked_) {
                draft_.urgency = static_cast<uint8_t>(2 - cursor_);
                go(draft_.urgency == 2 ? Screen::URGENCY_CONFIRM : afterUrgency());
            }
            break;
        case Screen::URGENCY_CONFIRM:
            if (ok) go(afterUrgency());
            else if (back) go(Screen::URGENCY);
            else scroll(up, downB);
            break;
        case Screen::PHRASE: {
            const size_t count = phraseListCount();
            if (up) moveCursor(-1, count, LINES);
            else if (downB) moveCursor(1, count, LINES);
            else if (back) go(Screen::URGENCY);
            else if (ok && count) {
                const size_t none = draft_.category == 9 ? 0 : 1;
                draft_.phrase = cursor_ < none ? PHRASE_NONE : static_cast<int8_t>(cursor_ - none);
                go(Screen::SUMMARY);
            }
            break;
        }
        case Screen::SUMMARY:
            if (ok) { submit(); go(Screen::RESULT); }
            else if (back) {
                switch (draft_.kind) {
                    case DraftKind::NEW: go(Screen::PHRASE); break;
                    case DraftKind::PEOPLE: go(Screen::PEOPLE); break;
                    case DraftKind::URGENCY: go(Screen::URGENCY); break;
                    case DraftKind::RESOLVED: go(Screen::ITEM_MENU); break;
                }
            } else scroll(up, downB);
            break;
        case Screen::RESULT:
            if ((ok || back) && serviceResult_) { serviceResult_ = false; go(Screen::SERVICES); }
            else if (ok || back) { resetDraft(); go(Screen::MAIN); }
            else scroll(up, downB);
            break;
        case Screen::DISCARD:
            if (ok) { resetDraft(); go(Screen::MAIN); }
            else if (back) go(returnTo_);
            break;
        case Screen::MESSAGES: {
            const size_t count = host_ ? host_->itemCount() : 0;
            if (up) moveCursor(-1, count, LINES);
            else if (downB) moveCursor(1, count, LINES);
            else if (back) go(Screen::MENU);
            else if (ok && count) {
                Item item;
                if (host_->item(cursor_, item)) {
                    messagesCursor_ = cursor_;
                    itemRef_ = item.ref;
                    itemIndex_ = cursor_;
                    if (!item.own && item.unread) host_->markRead(item.ref);
                    go(Screen::ITEM);
                }
            }
            break;
        }
        case Screen::ITEM: {
            if (back) go(Screen::MESSAGES);
            else if (ok) {
                Item item;
                uint8_t menu[4];
                if (openItem(item) && item.own && itemMenu(menu)) go(Screen::ITEM_MENU);
                else go(Screen::MESSAGES);
            } else scroll(up, downB);
            break;
        }
        case Screen::ITEM_MENU: {
            uint8_t menu[4];
            const size_t count = itemMenu(menu);
            if (up) moveCursor(-1, count, LINES);
            else if (downB) moveCursor(1, count, LINES);
            else if (back) go(Screen::ITEM);
            else if (ok && cursor_ < count) {
                Item item;
                if (!openItem(item)) { go(Screen::MESSAGES); break; }
                switch (static_cast<Label>(menu[cursor_])) {
                    case Label::ZMIEN_LICZBE_OSOB: beginWizard(DraftKind::PEOPLE, item.ref, &item); go(Screen::PEOPLE); break;
                    case Label::ZMIEN_PILNOSC: beginWizard(DraftKind::URGENCY, item.ref, &item); go(Screen::URGENCY); break;
                    case Label::POTRZEBA_USTALA: beginWizard(DraftKind::RESOLVED, item.ref, &item); go(Screen::SUMMARY); break;
                    case Label::ANULUJ_WYSYLKE: host_->cancel(item.ref); go(Screen::MESSAGES); break;
                    default: break;
                }
            }
            break;
        }
        case Screen::TEST:
            if (ok) go(Screen::TEST_MENU);
            else if (back) {
                if (host_ && host_->test().state == TestState::SCHEDULED) host_->cancelTest();  // WSTECZ = ANULUJ
                go(Screen::MENU);
            } else scroll(up, downB);
            break;
        case Screen::TEST_MENU:
            if (up) moveCursor(-1, 2, LINES);
            else if (downB) moveCursor(1, 2, LINES);
            else if (back) go(Screen::TEST);
            else if (ok && host_) {
                if (cursor_ == 0) host_->scheduleTest(false);
                else host_->pauseTest(host_->test().state != TestState::PAUSED);
                go(Screen::TEST);
            }
            break;
        case Screen::ALARM:
            if (ok) {
                if (host_) host_->ackAlarm(alarm_);
                alarmCheckMs_ = nowMs;  // następny alarm dopiero po sekundzie
                go(beforeAlarm_ == Screen::ALARM ? Screen::MAIN : beforeAlarm_);
            }
            break;
        case Screen::CONFIRM:
            if (ok || back) {
                answer_ = question_ == Question::CARD ? Answer::NO : ok ? Answer::YES : Answer::NO;
                go(beforeQuestion_);
            }
            break;
        case Screen::COUNT:
            break;
    }
}

size_t Model::itemMenu(uint8_t out[4]) const {
    // ZMIEŃ LICZBĘ OSÓB, ZMIEŃ PILNOŚĆ, POTRZEBA USTAŁA; ANULUJ WYSYŁKĘ tylko przed pierwszym nadaniem (`nadane`).
    Item item;
    if (!host_ || !host_->item(itemIndex_, item, true) || !item.own || item.ref != itemRef_) return 0;
    size_t n = 0;
    if (item.type == SA1_REQUEST) {
        out[n++] = static_cast<uint8_t>(Label::ZMIEN_LICZBE_OSOB);
        out[n++] = static_cast<uint8_t>(Label::ZMIEN_PILNOSC);
        out[n++] = static_cast<uint8_t>(Label::POTRZEBA_USTALA);
    }
    if (!item.sentOnce) out[n++] = static_cast<uint8_t>(Label::ANULUJ_WYSYLKE);
    return n;
}

void Model::renderMain(const Status& s, char out[][LINE_BYTES], size_t count) const {
    char value[24];
    char tmp[LINE_BYTES * 2];
    size_t n = 0;
    if (node()) {
        // Węzeł OSP: radio, komputer stanowiska, zasilanie (w ciszy: cisza, zasilanie, komputer).
        char computer[LINE_BYTES];
        computerLine(s, computer, sizeof(computer));
        if (s.mains12) {
            voltage(s.millivolts, lang_, value, sizeof(value));
            substitute(text(Id::ZASILANIE_12V, lang_), "[x]", value, tmp, sizeof(tmp));
        } else {
            formatNumber(value, sizeof(value), s.cellHours);
            substitute(text(Id::ZASILANIE_AA, lang_), "[x]", value, tmp, sizeof(tmp));
        }
        const char* lines[LINES] = {};
        char silence[3][LINE_BYTES];
        if (s.silence) {
            const size_t wrapped = wrap(text(Id::CISZA, lang_), silence, 3);
            for (size_t i = 0; i < 3; ++i) lines[i] = i < wrapped ? silence[i] : "";
            lines[3] = tmp;
            lines[4] = computer;
        } else {
            lines[0] = text(s.radioOk ? Id::RADIO_WLACZONE : Id::RADIO_AWARIA, lang_);
            lines[1] = computer;
            lines[2] = tmp;
            lines[3] = muted_ ? text(Id::DZWIEK_WYCISZONY, lang_) : "";
            lines[4] = "";
        }
        for (size_t i = 0; i < count && i < LINES; ++i) copyLine(out[i], LINE_BYTES, lines[i]);
        return;
    }
    if (s.silence) {
        // Wiersze 1-3: pełny tekst ciszy; wiersze 4-5: zasilanie i kolejka.
        char lines[3][LINE_BYTES];
        const size_t wrapped = wrap(text(Id::CISZA, lang_), lines, 3);
        for (size_t i = 0; i < 3; ++i) copyLine(out[n++], LINE_BYTES, i < wrapped ? lines[i] : "");
    } else {
        copyLine(out[n++], LINE_BYTES, text(s.radioOk ? Id::RADIO_WLACZONE : Id::RADIO_AWARIA, lang_));
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
        copyLine(out[n], LINE_BYTES, muted_ ? text(Id::DZWIEK_WYCISZONY, lang_) : "");
    }
    ++n;
    if (n < count) {
        copyLine(out[n], LINE_BYTES, text(Id::NOWE_KROTKI, lang_));
        substituteNumber(out[n], LINE_BYTES, "[n]", s.newMessages);
        ++n;
    }
}

size_t Model::statusLines(const Status& s, char out[][LINE_BYTES], size_t max) const {
    size_t n = 0;
    char value[24];
    char tmp[LINE_BYTES * 2];
    auto put = [&](const char* line) { if (n < max) copyLine(out[n++], LINE_BYTES, line); };
    put(text(s.radioOk ? Id::RADIO_WLACZONE : Id::RADIO_AWARIA, lang_));
    snprintf(tmp, sizeof(tmp), "RX OK %lu", static_cast<unsigned long>(s.rxOk)); put(tmp);
    snprintf(tmp, sizeof(tmp), "RX BAD %lu", static_cast<unsigned long>(s.rxBad)); put(tmp);
    snprintf(tmp, sizeof(tmp), "TX %lu DROP %lu", static_cast<unsigned long>(s.txDatagrams), static_cast<unsigned long>(s.txDrop)); put(tmp);
    snprintf(tmp, sizeof(tmp), "DEFER %lu", static_cast<unsigned long>(s.deferrals)); put(tmp);
    snprintf(tmp, sizeof(tmp), "WAIT %lu S", static_cast<unsigned long>((s.debtMs + 999) / 1000)); put(tmp);
    if (node()) {
        // Pakiety Reticulum przez USB w obu kierunkach, odrzucone i kontakt z komputerem.
        snprintf(tmp, sizeof(tmp), "USB IN %lu", static_cast<unsigned long>(s.usbIn)); put(tmp);
        snprintf(tmp, sizeof(tmp), "USB OUT %lu", static_cast<unsigned long>(s.usbOut)); put(tmp);
        snprintf(tmp, sizeof(tmp), "USB DROP %lu", static_cast<unsigned long>(s.usbDrop)); put(tmp);
        computerLine(s, tmp, sizeof(tmp));
        put(tmp);
    } else {
        duration(s.contactS, lang_, value, sizeof(value));
        substitute(text(s.contactKnown ? Id::OSTATNI_KONTAKT : Id::OSTATNI_KONTAKT_PONAD, lang_), "[czas]", value, tmp, sizeof(tmp));
        char lines[4][LINE_BYTES];
        const size_t wrapped = wrap(tmp, lines, 4);
        for (size_t i = 0; i < wrapped; ++i) put(lines[i]);
    }
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
    if (muted_) put(text(Id::DZWIEK_WYCISZONY, lang_));
    put(s.version);
    put(s.name);
    if (!node()) put(label(Label::PRZEKAZANIE_ZMIANY, lang_));
    put(label(Label::USLUGI, lang_));
    return n;
}

void Model::renderList(const char* const* items, size_t count, size_t window, Lines& out, size_t first, bool mark) {
    lastCount_ = static_cast<uint16_t>(count);
    if (cursor_ >= count) cursor_ = count ? static_cast<uint16_t>(count - 1) : 0;
    size_t top = top_;
    if (mark) {
        // Okno dosunięte do kursora (rozmiar okna zależy od paska trybu przygotowania).
        if (cursor_ < top) top = cursor_;
        if (cursor_ >= top + window) top = cursor_ - window + 1;
    }
    if (top + window > count) top = count > window ? count - window : 0;
    top_ = static_cast<uint16_t>(top);
    for (size_t i = 0; i < window; ++i) {
        const size_t index = top + i;
        copyLine(out.text[first + i], LINE_BYTES, index < count ? items[index] : "");
        out.inverted[first + i] = mark && index == cursor_;
    }
}

void Model::renderText(Text& text, size_t window, Lines& out, size_t first) {
    const char* items[TEXT_MAX_LINES];
    for (size_t i = 0; i < text.count; ++i) items[i] = text.line[i];
    renderList(items, text.count, window, out, first, false);
}

bool Model::openItem(Item& item) {
    // Nowa wiadomość przesuwa listę (najnowsze najpierw): pozycja szukana po numerze rekordu.
    if (!host_) return false;
    if (host_->item(itemIndex_, item) && item.ref == itemRef_) return true;
    const size_t count = host_->itemCount();
    for (size_t i = 0; i < count; ++i) {
        if (host_->item(i, item) && item.ref == itemRef_) {
            itemIndex_ = i;
            return true;
        }
    }
    return false;
}

void Model::stageText(const Item& item, const Status& status, char* out, size_t size) const {
    // Etap własnego zgłoszenia (oprogramowanie.md, "Cykl życia zgłoszenia", "Ekran"): `zapisane`
    // (w ciszy `zapisane_w_ciszy`), `wysylanie` i `dostarczone` z próbą, a pod nimi stan z decyzji;
    // `odebrane`: stan z decyzji albo `stan_1`.
    const char* decision = item.decision >= 2 && item.decision <= 6 ? text(STATE_TEXTS[item.decision - 1], lang_) : "";
    if (item.stage == Stage::RECEIVED) { snprintf(out, size, "%s", decision[0] ? decision : text(STATE_TEXTS[0], lang_)); return; }
    char tmp[320];
    if (item.stage == Stage::SAVED) snprintf(tmp, sizeof(tmp), "%s", text(status.silence ? Id::ZAPISANE_W_CISZY : Id::ZAPISANE_W_STACJI, lang_));
    else {
        char number[12], step[320];
        formatNumber(number, sizeof(number), item.attempts);
        substitute(text(Id::WYSYLANIE, lang_), "[n]", number, step, sizeof(step));
        formatNumber(number, sizeof(number), (item.nextInS + 59) / 60);
        substitute(step, "[m]", number, tmp, sizeof(tmp));
    }
    snprintf(out, size, decision[0] ? "%s %s" : "%s", tmp, decision);
}

void Model::buildSummary(Text& t) const {
    const size_t L = static_cast<size_t>(lang_);
    char tmp[LINE_BYTES * 2];
    t.addLine(ui_texts::CATEGORIES[draft_.category < 10 ? draft_.category : 9][L]);
    peopleLine(draft_.people, draft_.urgency, tmp, sizeof(tmp));
    t.add(tmp);  // pilność słownie, łamana na wiersze (nie obcinana)
    if (draft_.phrase == PHRASE_RESOLVED) t.add(ui_texts::PHRASES[ui_texts::PHRASES_COUNT - 1][L]);
    else if (draft_.phrase >= 0 && host_) t.add(host_->phrase(static_cast<size_t>(draft_.phrase), lang_));
    else if (draft_.phrase == PHRASE_KEPT && host_) {
        // Treść spoza listy (z panelu) zostaje w rewizji: pokazana z rekordu zgłoszenia.
        const size_t count = host_->itemCount();
        Item item;
        for (size_t i = 0; i < count; ++i) {
            if (!host_->item(i, item, true) || item.ref != draft_.ref) continue;
            if (host_->item(i, item)) t.add(shownPhrase(item.text));
            break;
        }
    }
    if (host_) t.add(host_->address());
    t.add(text(Id::PODSUMOWANIE_KLAWISZE, lang_));
}

void Model::buildItem(const Item& item, Text& t) const {
    char tmp[LINE_BYTES * 2];
    if (item.own) {
        t.addLine(itemLabel(item));
        if (item.type != SA1_TEST) {  // TEST nie ma liczby osób ani pilności do pokazania
            peopleLine(item.people, item.urgency, tmp, sizeof(tmp));
            t.add(tmp);
        }
        if (item.text[0]) t.add(shownPhrase(item.text));   // fraza w wybranym języku; treść z panelu po polsku
        t.addShort(Id::ZAPISZ_NUMER, item.number, lang_);
    } else {
        const char* polish = text(Id::ODPOWIEDZI_PO_POLSKU, lang_);
        if (polish[0]) t.add(polish);
        if (item.type == SA1_REPLY) {
            char digits[8];
            formatShort(digits, sizeof(digits), item.number);
            t.addLine(digits);
        }
        t.add(item.text);
        duration(item.ageS, lang_, tmp, sizeof(tmp));
        t.addLine(tmp);
        if (item.type == SA1_BULLETIN) t.add(text(Id::STOPKA_KOMUNIKATU, lang_));
    }
}

void Model::buildHandover(const Status& status, Text& t) {
    // Otwarte i niepotwierdzone zgłoszenia, nieprzeczytane wiadomości, awaria radia, energia, cisza.
    char tmp[LINE_BYTES * 2];
    char digits[8];
    t.addLine(label(Label::PRZEKAZANIE_ZMIANY, lang_));
    const size_t count = host_ ? host_->itemCount() : 0;
    for (size_t i = 0; i < count && t.count + 4 < TEXT_MAX_LINES; ++i) {
        Item item;
        if (!host_->item(i, item, true) || !item.own || (item.stage == Stage::RECEIVED && item.decision == 6)) continue;
        formatShort(digits, sizeof(digits), item.number);
        snprintf(tmp, sizeof(tmp), "%s %s", digits, itemLabel(item));
        t.addLine(tmp);
        if (item.stage != Stage::RECEIVED) {  // etap z podstawionymi [n] i [m], łamany na wiersze
            stageText(item, status, tmp, sizeof(tmp));
            t.add(tmp);
        }
    }
    copyLine(tmp, sizeof(tmp), text(Id::NOWE_KROTKI, lang_));
    substituteNumber(tmp, sizeof(tmp), "[n]", status.newMessages);
    t.addLine(tmp);
    char lines[LINES][LINE_BYTES];
    renderMain(status, lines, LINES);
    if (status.silence) t.addLine(lines[0]);
    if (!status.radioOk) t.addLine(text(Id::RADIO_AWARIA, lang_));  // wpis alarmu do usunięcia przyczyny
    t.addLine(lines[status.silence ? 3 : 2]);  // zasilanie
    if (muted_) t.addLine(text(Id::DZWIEK_WYCISZONY, lang_));
}

void Model::render(const Status& s, Lines& out) {
    for (size_t i = 0; i < LINES; ++i) { out.text[i][0] = '\0'; out.inverted[i] = false; }
    size_t first = 0;
    if (s.prep) copyLine(out.text[first++], LINE_BYTES, text(Id::TRYB_PRZYGOTOWANIA, lang_));
    const size_t window = LINES - first;
    const size_t L = static_cast<size_t>(lang_);
    lastStatus_ = s;
    char tmp[320];
    Text t;
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
            ui_texts::Menu entries[MENU_ITEMS];
            const size_t count = menu(entries);
            const char* items[MENU_ITEMS];
            for (size_t i = 0; i < count; ++i) items[i] = ui_texts::MENU[static_cast<size_t>(entries[i])][L];
            renderList(items, count, window, out, first, true);
            break;
        }
        case Screen::STATUS: {
            char lines[STATUS_MAX_LINES][LINE_BYTES];
            const size_t count = statusLines(s, lines, STATUS_MAX_LINES);
            const char* items[STATUS_MAX_LINES];
            for (size_t i = 0; i < count; ++i) items[i] = lines[i];
            renderList(items, count, window, out, first, true);
            break;
        }
        case Screen::ADDRESS: {
            const char* address = host_ ? host_->address() : "";
            if (addressMissing_ || !address[0]) t.add(text(Id::ADRES_BRAK, lang_));
            else { substitute(text(Id::ADRES_KONTROLA, lang_), "[x]", address, tmp, sizeof(tmp)); t.add(tmp); }
            renderText(t, window, out, first);
            break;
        }
        case Screen::ADDRESS_LIST: {
            const char* items[ADDRESS_CHOICES];
            const size_t count = host_ ? host_->addressCount() : 0;
            for (size_t i = 0; i < count && i < ADDRESS_CHOICES; ++i) items[i] = host_->addressAt(i);
            renderList(items, count < ADDRESS_CHOICES ? count : ADDRESS_CHOICES, window, out, first, true);
            break;
        }
        case Screen::TEST_OFFER:
            t.addLine(label(Label::TEST, lang_));
            snprintf(tmp, sizeof(tmp), "%s = %s", ui_texts::BUTTONS[L][2], label(Label::TEST, lang_));
            t.addLine(tmp);
            t.addLine(ui_texts::BUTTONS[L][3]);
            renderText(t, window, out, first);
            break;
        case Screen::CATEGORY: {
            const char* items[10];
            for (size_t i = 0; i < 10; ++i) items[i] = ui_texts::CATEGORIES[i][L];
            renderList(items, 10, window, out, first, true);
            break;
        }
        case Screen::PEOPLE: {
            char values[PEOPLE_CHOICES][8];
            const char* items[PEOPLE_CHOICES];
            for (size_t i = 0; i + 1 < PEOPLE_CHOICES; ++i) { formatNumber(values[i], sizeof(values[i]), PEOPLE_VALUES[i]); items[i] = values[i]; }
            items[PEOPLE_CHOICES - 1] = label(Label::INNA, lang_);
            renderList(items, PEOPLE_CHOICES, window, out, first, true);
            break;
        }
        case Screen::DIGITS: {
            // Setki, dziesiątki, jednostki; znacznik pod zmienianą cyfrą.
            t.addLine(label(Label::INNA, lang_));
            snprintf(tmp, sizeof(tmp), "%u %u %u", digits_[0], digits_[1], digits_[2]);
            t.addLine(tmp);
            snprintf(tmp, sizeof(tmp), "%*s^", digitPos_ * 2, "");
            t.addLine(tmp);
            renderText(t, window, out, first);
            break;
        }
        case Screen::URGENCY: {
            const char* items[3] = {text(Id::PILNOSC_2, lang_), text(Id::PILNOSC_1, lang_), text(Id::PILNOSC_0, lang_)};
            renderList(items, 3, window, out, first, urgencyPicked_);
            break;
        }
        case Screen::URGENCY_CONFIRM:
            t.add(text(Id::PILNOSC_2_POTW, lang_));
            renderText(t, window, out, first);
            break;
        case Screen::PHRASE: {
            const size_t count = phraseListCount();
            const size_t none = draft_.category == 9 ? 0 : 1;
            const char* items[ui_texts::PHRASES_COUNT + 1];
            size_t n = 0;
            if (none) items[n++] = "-";
            for (size_t i = 0; i + none < count && n < ui_texts::PHRASES_COUNT + 1; ++i) items[n++] = host_->phrase(i, lang_);
            renderList(items, n, window, out, first, true);
            break;
        }
        case Screen::SUMMARY:
            buildSummary(t);
            renderText(t, window, out, first);
            break;
        case Screen::RESULT:
            switch (result_) {
                case Submit::STORED:
                    t.add(text(resultSilence_ ? Id::ZAPISANE_W_CISZY : Id::ZAPISANE_W_STACJI, lang_));
                    t.addShort(Id::ZAPISZ_NUMER, resultNumber_, lang_);
                    break;
                case Submit::NO_ADDRESS: t.add(text(Id::ADRES_BRAK, lang_)); break;
                case Submit::FULL: t.add(text(Id::KOLEJKA_PELNA, lang_)); break;
                case Submit::ERROR: t.add(text(Id::BLAD_PAMIECI, lang_)); break;
                case Submit::ANNOUNCED: t.add(text(Id::ADRES_OGLOSZONY, lang_)); break;
                case Submit::NOT_ANNOUNCED: t.add(text(Id::ADRES_NIE_OGLOSZONY, lang_)); break;
            }
            renderText(t, window, out, first);
            break;
        case Screen::DISCARD:
            t.add(text(Id::PORZUCIC, lang_));
            renderText(t, window, out, first);
            break;
        case Screen::MESSAGES: {
            // Własne: numer i kategoria; odebrane: "*" przed nieprzeczytaną treścią.
            const size_t count = host_ ? host_->itemCount() : 0;
            lastCount_ = static_cast<uint16_t>(count);
            if (cursor_ >= count) cursor_ = count ? static_cast<uint16_t>(count - 1) : 0;
            size_t top = top_;
            if (cursor_ < top) top = cursor_;
            if (cursor_ >= top + window) top = cursor_ - window + 1;
            if (top + window > count) top = count > window ? count - window : 0;
            top_ = static_cast<uint16_t>(top);
            for (size_t i = 0; i < window; ++i) {
                const size_t index = top + i;
                Item item;
                if (index < count && host_->item(index, item, true) && (item.own || host_->item(index, item))) {
                    char digits[8];
                    formatShort(digits, sizeof(digits), item.number);
                    if (item.own) snprintf(tmp, sizeof(tmp), "%s %s", digits, itemLabel(item));
                    else snprintf(tmp, sizeof(tmp), "%s%s", item.unread ? "*" : " ", item.text);
                    copyLine(out.text[first + i], LINE_BYTES, tmp);
                }
                out.inverted[first + i] = index < count && index == cursor_;
            }
            break;
        }
        case Screen::ITEM: {
            Item item;
            if (openItem(item)) {
                if (item.own) { stageText(item, s, tmp, sizeof(tmp)); t.add(tmp); }
                buildItem(item, t);
            }
            renderText(t, window, out, first);
            break;
        }
        case Screen::ITEM_MENU: {
            uint8_t menu[4];
            const size_t count = itemMenu(menu);
            const char* items[4];
            for (size_t i = 0; i < count; ++i) items[i] = label(static_cast<Label>(menu[i]), lang_);
            renderList(items, count, window, out, first, true);
            break;
        }
        case Screen::TEST: {
            const TestInfo info = host_ ? host_->test() : TestInfo();
            switch (info.state) {
                case TestState::SCHEDULED: t.addNumber(Id::TEST_ZAPLANOWANY, "[mm]", info.minutes, lang_); break;
                case TestState::SENT: t.add(text(Id::TEST_WYSLANY, lang_)); break;
                case TestState::CONFIRMED: t.add(text(STATE_TEXTS[info.confirmed >= 1 && info.confirmed <= 6 ? info.confirmed - 1 : 0], lang_)); break;
                case TestState::PAUSED: t.add(text(Id::TEST_WSTRZYMANY, lang_)); break;
                case TestState::NONE: t.addLine(label(Label::TEST, lang_)); break;
            }
            renderText(t, window, out, first);
            break;
        }
        case Screen::TEST_MENU: {
            const bool paused = host_ && host_->test().state == TestState::PAUSED;
            const char* items[2] = {label(Label::TEST, lang_), label(paused ? Label::WZNOW : Label::WSTRZYMAJ, lang_)};
            renderList(items, 2, window, out, first, true);
            break;
        }
        case Screen::HANDOVER:
            buildHandover(s, t);
            renderText(t, window, out, first);
            break;
        case Screen::SERVICES: {
            Service entries[SERVICE_ITEMS];
            const size_t count = services(entries);
            const char* items[SERVICE_ITEMS];
            for (size_t i = 0; i < count; ++i) {
                switch (entries[i]) {
                    case Service::ANNOUNCE: items[i] = label(Label::OGLOS_ADRES, lang_); break;
                    case Service::MUTE: items[i] = label(muted_ ? Label::WLACZ_DZWIEK : Label::WYCISZ_DZWIEK, lang_); break;
                    case Service::BACKUP: items[i] = label(Label::KLUCZ_ZAPASOWY, lang_); break;
                    case Service::DESTROY: items[i] = label(Label::ZNISZCZ_DANE, lang_); break;
                }
            }
            renderList(items, count, window, out, first, true);
            break;
        }
        case Screen::BACKUP:
            t.add(text(Id::KLUCZ_ZAPASOWY, lang_));
            renderText(t, window, out, first);
            break;
        case Screen::DESTROY:
            t.add(text(Id::ZNISZCZ_OSTRZEZENIE, lang_));
            renderText(t, window, out, first);
            break;
        case Screen::ALARM:
            if (alarm_.kind == AlarmKind::RADIO_FAULT) {
                t.add(text(Id::RADIO_AWARIA, lang_));
                renderText(t, window, out, first);
                break;
            }
            if (alarm_.kind == AlarmKind::NO_READ) t.add(text(Id::BRAK_ODCZYTU, lang_));
            else t.addNumber(Id::BRAK_POTWIERDZENIA, "[n]", alarm_.minutes, lang_);
            t.addShort(Id::ZAPISZ_NUMER, alarm_.number, lang_);
            renderText(t, window, out, first);
            break;
        case Screen::CONFIRM:
            substitute(text(QUESTION_TEXTS[static_cast<size_t>(question_)], lang_), question_ == Question::CARD ? "[x]" : "[xxxx]", questionDetail_,
                       tmp, sizeof(tmp));
            t.add(tmp);
            renderText(t, window, out, first);
            break;
        case Screen::COUNT:
            break;
    }
}

}  // namespace ui
