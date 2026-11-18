// SPDX-License-Identifier: MIT
// Dane i działania stacji dla ekranu (ui::Host) nad rejestrem i skrzynką w FRAM (store.h) i warstwą
// aplikacji (station.h): lista WIADOMOŚCI (własne zgłoszenia i TEST z rejestru bez anulowanych,
// odpowiedzi i komunikaty ze skrzynki, najnowsze najpierw), frazy z konfiguracji albo domyślne,
// zgłoszenie z kreatora, rewizje, ANULUJ WYSYŁKĘ, TEST, alarmy, KLUCZ ZAPASOWY, OGŁOŚ ADRES
// ZAMKNIJ ZDARZENIE (jak potwierdzone `close`) i ZNISZCZ DANE (przez usługi stacji, jak polecenie `destroy`).
// Bez zależności od Arduino; sprawdzany na komputerze razem z magazynem w RAM.
#pragma once

#include "station.h"
#include "store.h"
#include "ui.h"

namespace console {

// Usługi poza magazynem i warstwą aplikacji (main.cpp albo program testowy).
struct Actions {
    virtual ~Actions() = default;
    virtual bool announce() = 0;   // OGŁOŚ ADRES: false = stos nie działa albo cisza
    virtual bool destroy() = 0;    // ZNISZCZ DANE: magazyn, dziennik, tożsamość
    virtual bool node() = 0;       // konfiguracja węzła stanowiska
    virtual void log(const char* text) = 0;
};

class Console : public ui::Host {
public:
    Console(store::Store& store, station::Station& station, Actions& actions);
    void invalidate() { dirty_ = true; }  // po każdej zmianie rejestru albo skrzynki

    const char* address() override { return store_.address(); }
    size_t addressCount() override { return store_.addressCount(); }
    const char* addressAt(size_t index) override { return store_.addressAt(index); }
    size_t selectedAddress() override { return store_.selectedAddress(); }
    void selectAddress(size_t index) override { store_.selectAddress(index); }
    size_t phraseCount() override;
    const char* phrase(size_t index, ui::Lang lang) override;
    size_t itemCount() override;
    bool item(size_t index, ui::Item& out, bool briefOnly = false) override;
    void markRead(uint32_t ref) override;
    ui::Submit submit(const ui::Draft& draft, uint16_t& number) override;
    bool cancel(uint32_t ref) override;
    ui::TestInfo test() override;
    bool scheduleTest(bool startup) override;
    void cancelTest() override;
    void pauseTest(bool paused) override;
    bool alarm(ui::AlarmInfo& out) override;
    void ackAlarm(const ui::AlarmInfo& alarm) override;
    bool switchBackup() override;
    bool destroy() override;
    bool closeEvent() override;
    bool announce() override;
    bool node() override { return actions_.node(); }
    // Awaria układu radiowego (radio_awaria) i stosu sieciowego (brak_lacznosci), podawane przez main.cpp
    // przy każdym obiegu: alarm do potwierdzenia OK; po ustąpieniu przyczyny następna awaria alarmuje od nowa.
    // jammed: przyczyną jest zagłuszanie kanału (Bench::channelJammed), ten sam alarm co układ radiowy.
    void setRadioFault(bool fault, bool jammed = false) { radio_.set(fault); radioJammed_ = fault && jammed; }
    void setStackFault(bool fault) { stack_.set(fault); }
    // wymien_ogniwa (power.h): alarm do potwierdzenia OK jak awarie, dioda do wymiany ogniw, a po potwierdzeniu
    // przypomnienie dźwiękiem co 15 min (remindCells, annunciator.h).
    void setCellsLow(bool low) { cells_.set(low); }
    bool remindCells() const { return cells_.active && cells_.acked; }
    // Przeniesienie stacji w toku (usb-protocol.md, „Przeniesienie stacji”): magazyn celowo zamknięty do
    // końca albo wycofania przeniesienia, więc to nie awaria pamięci (bez blad_pamieci i bez alarmu).
    void setMigrationFrozen(bool frozen) { migrationFrozen_ = frozen; }
    // Przyczyna alarmu trwa (także po potwierdzeniu): awaria radia albo stosu, ogniwa do wymiany, magazyn
    // niedziałający albo alarm zgłoszenia. Alarmy zgłoszeń liczą się z indeksu w RAM, więc działają też po zatrzymaniu magazynu.
    bool alarmCause() const {
        return radio_.active || stack_.active || cells_.active || (!store_.ok() && !migrationFrozen_) || station_.alarmCause();
    }

private:
    static_assert(ui::ADDRESS_CHOICES == config::ADDRESSES, "lista obiektów ekranu i konfiguracji");
    static constexpr size_t MAX_ITEMS = store::REGISTER_SLOTS + store::INBOX_SLOTS;
    // Ref własnego zgłoszenia: bit 31, generacja gniazda w bitach 16..30, gniazdo w 0..15;
    // wiadomość skrzynki: jej numer `msg` (< 2^31).
    static constexpr uint32_t OWN = 0x80000000u;
    static uint32_t ownRef(size_t slot, uint16_t gen) { return OWN | (static_cast<uint32_t>(gen & 0x7FFF) << 16) | static_cast<uint32_t>(slot); }
    int ownSlot(uint32_t ref) const;   // gniazdo wpisu wskazanego przez ref albo -1
    struct Entry { uint32_t time; uint32_t ref; };
    void rebuild();
    bool brief(uint32_t ref, ui::Item& out);
    const char* phraseText(const ui::Draft& draft);

    store::Store& store_;
    station::Station& station_;
    Actions& actions_;
    bool dirty_ = true;
    // Awaria stacji jako alarm: trwa, póki trwa przyczyna; potwierdzenie OK do ustąpienia przyczyny.
    struct Fault {
        bool active = false;
        bool acked = false;
        void set(bool on) {
            if (!on) acked = false;
            active = on;
        }
        bool pending() const { return active && !acked; }
    };
    Fault* fault(ui::AlarmKind kind);
    Fault radio_;
    bool radioJammed_ = false;
    Fault memory_;   // magazyn wraca dopiero po restarcie, więc potwierdzenie trwa do niego
    bool migrationFrozen_ = false;
    Fault stack_;    // stos startuje tylko przy włączeniu, więc też do restartu
    Fault cells_;    // ogniwa: przyczyna schodzi po wymianie (średnia ≥ power::CLEAR_MV)
    size_t count_ = 0;
    Entry list_[MAX_ITEMS];
    // Treść ostatnio otwartej pozycji: liczba osób i fraza zmieniają się tylko z nową rewizją,
    // więc ekran pozycji nie dekoduje rekordu z FRAM przy każdym rysowaniu.
    uint32_t cachedRef_ = 0;           // 0 = pusto
    uint16_t cachedRevision_ = 0;
    uint8_t cachedEpoch_[store::EPOCH] = {};
    uint16_t cachedPeople_ = 0;
    char cachedText_[ui::ITEM_TEXT] = {};
};

}  // namespace console
