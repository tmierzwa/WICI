// SPDX-License-Identifier: MIT
// Model ekranu i przycisków stacji (docs/spec/oprogramowanie.md, "Ekran i przyciski stacji"):
// wybór języka po włączeniu, kontrola adresu i propozycja TEST startowego, ekran główny z pięciu
// krótkich form, cisza radiowa, pasek trybu przygotowania, menu (ZGŁOSZENIE, WIADOMOŚCI, TEST,
// STAN, JĘZYK), kreator zgłoszenia (kategoria, liczba osób z wpisem cyfr, pilność z potwierdzeniem
// pilności 2, fraza, podsumowanie, wynik), WIADOMOŚCI z etapami własnych zgłoszeń i działaniami
// (nowa rewizja, POTRZEBA USTAŁA, ANULUJ WYSYŁKĘ), TEST z WSTRZYMAJ/WZNÓW, STAN z PRZEKAZANIEM
// ZMIANY i USŁUGAMI (KLUCZ ZAPASOWY, ZNISZCZ DANE z sekwencją GÓRA, DÓŁ, GÓRA, OK), alarmy
// na cały ekran, przytrzymanie WSTECZ (2 s: porzucenie zgłoszenia, 3 s: wybór języka).
// Stacja w konfiguracji węzła stanowiska (Host::node) po wyborze języka pokazuje radio, kontakt
// z komputerem stanowiska (`komputer_osp`, `komputer_brak`) i zasilanie; menu ma tylko STAN
// i JĘZYK, a USŁUGI tylko WYCISZ DŹWIĘK i ZNISZCZ DANE.
// Polecenia USB `silence`, `close` i `destroy` pokazują pytanie (ask) z odpowiedzią OK albo WSTECZ;
// `card` pokazuje odcisk klucza stacji. Kanonicznych tekstów tych ekranów spec jeszcze nie ma (F107).
// Dane i działania stacji dostarcza Host (console.cpp nad magazynem FRAM i warstwą aplikacji).
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
// UTF-8 do 4 B na znak: tekst z radia i z konfiguracji może mieć znaki spoza BMP (font pokazuje je jako U+FFFD).
constexpr size_t LINE_BYTES = 4 * COLS + 1;
constexpr uint32_t IDLE_MS = 180000;          // powrót do ekranu głównego po 3 min bezczynności
constexpr uint32_t HOLD_DISCARD_MS = 2000;    // przytrzymanie WSTECZ w kreatorze: porzucić?
constexpr uint32_t HOLD_LANGUAGE_MS = 3000;   // przytrzymanie WSTECZ poza kreatorem: wybór języka
constexpr uint32_t REPEAT_DELAY_MS = 500;     // wpis cyfr: przytrzymanie przyspiesza zmianę
constexpr uint32_t REPEAT_MS = 150;
constexpr size_t STATUS_MAX_LINES = 17;
constexpr size_t TEXT_MAX_LINES = 24;
constexpr size_t ADDRESS_CHOICES = 8;        // lista obiektów (store::ADDRESSES)
constexpr size_t ITEM_TEXT = 193;             // treść REPLY/BULLETIN albo fraza (UTF-8)
constexpr uint16_t PEOPLE_MAX = 999;

enum class Button : uint8_t { UP, DOWN, OK, BACK };
enum class Screen : uint8_t {
    LANGUAGE, MAIN, MENU, STATUS, LANGUAGE_MENU,
    ADDRESS, ADDRESS_LIST, TEST_OFFER,
    CATEGORY, PEOPLE, DIGITS, URGENCY, URGENCY_CONFIRM, PHRASE, SUMMARY, RESULT, DISCARD,
    MESSAGES, ITEM, ITEM_MENU,
    TEST, TEST_MENU,
    HANDOVER, SERVICES, BACKUP, DESTROY,
    ALARM, CONFIRM,
    COUNT
};
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
    // Węzeł stanowiska: kontakt z komputerem stanowiska i liczniki pakietów interfejsu USB.
    bool computerHeard = false;  // pakiet od komputera od startu stacji
    uint32_t computerS = 0;      // czas od ostatniego pakietu od komputera [s]
    uint32_t usbIn = 0, usbOut = 0, usbDrop = 0;
};

struct Lines {
    char text[LINES][LINE_BYTES] = {};
    bool inverted[LINES] = {};
};

// Etap wysyłki własnego zgłoszenia (store::Stage; zgłoszenie anulowane nie trafia na listę).
enum class Stage : uint8_t { SAVED, SENDING, DELIVERED, RECEIVED };

// Pozycja listy WIADOMOŚCI: własne zgłoszenie albo TEST z rejestru, odpowiedź albo komunikat ze skrzynki.
struct Item {
    uint32_t ref = 0;        // wpis rejestru (own) albo numer wiadomości skrzynki
    bool own = false;
    uint8_t type = 0;        // SA1: 0 REQUEST, 3 REPLY, 4 BULLETIN, 5 TEST
    uint16_t number = 0;     // krótki numer zgłoszenia (own, REPLY)
    uint8_t category = 0;
    uint16_t people = 0;
    uint8_t urgency = 0;
    Stage stage = Stage::SAVED;
    uint8_t decision = 0;    // 0 albo stan 2-6 z STATUS
    bool sentOnce = false;   // `nadane`: ANULUJ WYSYŁKĘ niedostępne
    uint16_t attempts = 0;
    uint32_t nextInS = 0;    // do następnej próby nadania
    uint32_t ageS = 0;       // od utworzenia (own) albo odbioru
    bool unread = false;
    char text[ITEM_TEXT] = {};  // fraza PL (own) albo treść (REPLY, BULLETIN)
};

enum class DraftKind : uint8_t { NEW, PEOPLE, URGENCY, RESOLVED };
constexpr int8_t PHRASE_NONE = -1;
constexpr int8_t PHRASE_RESOLVED = -2;  // "potrzeba ustała"
constexpr int8_t PHRASE_KEPT = -3;      // rewizja liczby osób albo pilności: treść spoza listy fraz (z panelu)

struct Draft {
    DraftKind kind = DraftKind::NEW;
    uint32_t ref = 0;          // rewizja: numer rekordu zgłoszenia; 0 = nowe
    uint8_t category = 0;
    uint16_t people = 1;
    uint8_t urgency = 0;
    int8_t phrase = PHRASE_NONE;
};

enum class Submit : uint8_t { STORED, NO_ADDRESS, FULL, ERROR, ANNOUNCED, NOT_ANNOUNCED };  // (NOT_)ANNOUNCED: OGŁOŚ ADRES
// Pytanie polecenia USB (OK = tak, WSTECZ = nie) albo odcisk klucza dla `card` (dowolny przycisk zamyka).
enum class Question : uint8_t { SILENCE_ON, SILENCE_OFF, CLOSE, DESTROY, CARD };
enum class Answer : uint8_t { WAITING, YES, NO };
enum class TestState : uint8_t { NONE, SCHEDULED, SENT, CONFIRMED, PAUSED };
struct TestInfo {
    TestState state = TestState::NONE;
    uint32_t minutes = 0;    // SCHEDULED: do nadania
    uint8_t confirmed = 0;   // CONFIRMED: stan 1-6 (1: odebrany bez decyzji)
};
enum class AlarmKind : uint8_t { NONE, NO_CONFIRMATION, NO_READ };
struct AlarmInfo {
    AlarmKind kind = AlarmKind::NONE;
    uint32_t ref = 0;        // wpis rejestru (jak Item::ref)
    uint16_t number = 0;
    uint32_t minutes = 0;
};

// Dane i działania stacji dla ekranu.
struct Host {
    virtual ~Host() = default;
    virtual const char* address() = 0;                        // wybrany obiekt; "" gdy stacja nie ma adresu
    // Lista obiektów z konfiguracji (oprogramowanie.md, „Start”): wybór przyciskami po języku.
    virtual size_t addressCount() { return address()[0] ? 1 : 0; }
    virtual const char* addressAt(size_t index) { return index ? "" : address(); }
    virtual size_t selectedAddress() { return 0; }
    virtual void selectAddress(size_t) {}
    virtual size_t phraseCount() = 0;
    virtual const char* phrase(size_t index, Lang lang) = 0;  // tekst ekranu
    virtual size_t itemCount() = 0;                           // najnowsze najpierw
    // brief = true: pola z indeksu w RAM bez odczytu rekordu FRAM (własne zgłoszenia bez frazy,
    // odebrane bez treści); listy i PRZEKAZANIE ZMIANY używają skrótu, otwarta pozycja pełni.
    virtual bool item(size_t index, Item& out, bool brief = false) = 0;
    virtual void markRead(uint32_t ref) = 0;
    virtual Submit submit(const Draft& draft, uint16_t& number) = 0;
    virtual bool cancel(uint32_t ref) = 0;
    virtual TestInfo test() = 0;
    virtual bool scheduleTest(bool startup) = 0;
    virtual void cancelTest() = 0;
    virtual void pauseTest(bool paused) = 0;
    virtual bool alarm(AlarmInfo& out) = 0;
    virtual void ackAlarm(const AlarmInfo& alarm) = 0;
    virtual bool switchBackup() = 0;
    virtual bool destroy() = 0;
    virtual bool announce() { return false; }   // OGŁOŚ ADRES: zlecenie ogłoszenia; false = stos nie działa
    virtual bool node() { return false; }       // konfiguracja węzła stanowiska
};

class Model {
public:
    void attach(Host* host) { host_ = host; }
    // Po włączeniu: ekran wyboru języka (lang to tylko położenie kursora).
    void start(Lang lang);
    // Po restarcie przez watchdog: język z pamięci i poprzedni ekran.
    void restore(Lang lang, Screen screen);
    // Zbocza przycisków: GÓRA, DÓŁ i OK działają przy naciśnięciu, WSTECZ przy zwolnieniu
    // (przytrzymanie ma inne znaczenie); press() = naciśnięcie i zwolnienie.
    void down(Button button, uint32_t nowMs);
    void up(Button button, uint32_t nowMs);
    void press(Button button, uint32_t nowMs);
    // Czas: bezczynność, przytrzymanie, powtarzanie, alarmy.
    void tick(uint32_t nowMs);
    void render(const Status& status, Lines& out);
    Lang language() const { return lang_; }
    Screen screen() const { return screen_; }
    // true jeden raz po zmianie języka, ekranu albo wyciszenia (do zapisu w FRAM).
    bool takeChange();
    // Wyciszenie zwykłego sygnału nowej wiadomości (USŁUGI); alarmów nie wycisza.
    bool muted() const { return muted_; }
    void setMuted(bool muted) { muted_ = muted; }
    // Pytanie polecenia USB na cały ekran (przed alarmem); answer() = WAITING do odpowiedzi.
    // detail: odcisk klucza dla CARD. dismiss(): koniec pytania bez odpowiedzi (limit czasu, port zamknięty).
    void ask(Question question, const char* detail = "");
    Answer answer() const { return answer_; }
    void dismiss();
    // Wiersze ekranu STAN (również do testów); zwraca ich liczbę.
    size_t statusLines(const Status& status, char out[][LINE_BYTES], size_t max) const;

private:
    struct Text;  // wiersze tekstu do przewijania
    enum class Service : uint8_t { ANNOUNCE, MUTE, BACKUP, DESTROY };
    bool node() const { return host_ && host_->node(); }
    size_t menu(ui_texts::Menu out[]) const;        // pozycje menu (węzeł stanowiska: STAN i JĘZYK)
    uint8_t menuIndex(ui_texts::Menu item) const;
    size_t services(Service out[]) const;           // pozycje USŁUG
    void computerLine(const Status& status, char* out, size_t size) const;
    void go(Screen screen);
    void act(Button button, uint32_t nowMs);
    void moveCursor(int delta, size_t count, size_t window);
    void renderMain(const Status& status, char out[][LINE_BYTES], size_t count) const;
    void renderList(const char* const* items, size_t count, size_t window, Lines& out, size_t first, bool mark);
    void renderText(Text& text, size_t window, Lines& out, size_t first);
    // Fraza po polsku (z SA1) w wybranym języku: lista fraz stacji, potem frazy domyślne, inaczej bez zmian.
    const char* shownPhrase(const char* polish) const;
    int8_t phraseIndex(const char* polish) const;   // indeks na liście fraz stacji albo PHRASE_*
    void scroll(bool up, bool down);               // przewijanie tekstu o wiersz
    void resetDraft();                              // pusty szkic z ostatnią liczbą osób
    const char* itemLabel(const Item& item) const;  // TEST albo kategoria
    void peopleLine(uint16_t people, uint8_t urgency, char* out, size_t size) const;   // „liczba pilność”
    void buildSummary(Text& text) const;
    void buildItem(const Item& item, Text& text) const;
    void buildHandover(const Status& status, Text& text);
    void stageText(const Item& item, const Status& status, char* out, size_t size) const;
    bool openItem(Item& item);  // otwarta pozycja po numerze rekordu (lista mogła się przesunąć)
    size_t phraseListCount() const;
    size_t itemMenu(uint8_t out[4]) const;
    Screen afterPeople() const;
    Screen afterUrgency() const;
    void beginWizard(DraftKind kind, uint32_t ref, const Item* item);
    void submit();
    bool inWizard() const;

    Host* host_ = nullptr;
    Lang lang_ = Lang::PL;
    Screen screen_ = Screen::LANGUAGE;
    uint16_t cursor_ = 0;
    uint16_t top_ = 0;
    uint16_t lastCount_ = 0;      // liczba wierszy ostatnio pokazanej listy albo tekstu
    uint8_t item_ = 0;            // pozycja menu, z której wybrano ekran
    uint32_t lastPressMs_ = 0;
    bool changed_ = false;
    // Kreator.
    Draft draft_;
    uint16_t lastPeople_ = 1;
    uint8_t digits_[3] = {0, 0, 1};
    uint8_t digitPos_ = 0;
    bool urgencyPicked_ = false;
    Submit result_ = Submit::STORED;
    uint16_t resultNumber_ = 0;
    bool resultSilence_ = false;
    bool serviceResult_ = false;  // RESULT po usłudze (ogłoszenie, nieudane KLUCZ ZAPASOWY albo ZNISZCZ DANE): szkic zostaje
    bool muted_ = false;
    Status lastStatus_;           // stan z ostatniego rysowania (cisza przy wyniku, liczba wierszy STAN)
    Screen returnTo_ = Screen::MAIN;
    bool addressMissing_ = false;
    // Wiadomości.
    uint32_t itemRef_ = 0;
    size_t itemIndex_ = 0;
    uint16_t messagesCursor_ = 0;
    // Przytrzymanie i powtarzanie.
    bool held_[4] = {};
    uint32_t heldSinceMs_[4] = {};
    bool holdConsumed_ = false;
    uint32_t repeatMs_ = 0;
    // Sekwencja GÓRA, DÓŁ, GÓRA, OK i alarm.
    uint8_t sequence_ = 0;
    AlarmInfo alarm_;
    Screen beforeAlarm_ = Screen::MAIN;
    uint32_t alarmCheckMs_ = 0;
    // Pytanie polecenia USB.
    Question question_ = Question::SILENCE_ON;
    Answer answer_ = Answer::NO;
    char questionDetail_[24] = {};
    Screen beforeQuestion_ = Screen::MAIN;
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

}  // namespace ui
