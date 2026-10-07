// SPDX-License-Identifier: MIT
// Dane i działania stacji dla ekranu (ui::Host) nad magazynem FRAM i warstwą aplikacji:
// lista WIADOMOŚCI (własne zgłoszenia i TEST z kolejki w najnowszej rewizji, odpowiedzi
// i komunikaty ze skrzynki, najnowsze najpierw), frazy z konfiguracji albo domyślne,
// zgłoszenie z kreatora, rewizje, anulowanie, TEST, alarmy, ODBIORCA ZAPASOWY i ZNISZCZ DANE.
// Bez zależności od Arduino; sprawdzany na komputerze razem z magazynem w RAM.
#pragma once

#include "journal.h"
#include "station.h"
#include "store.h"
#include "ui.h"

namespace console {

class Console : public ui::Host {
public:
    Console(store::Store& store, station::Station& station, station::Services& services, journal::Journal* journal);
    void invalidate() { dirty_ = true; }  // po każdej zmianie kolejki albo skrzynki

    const char* address() override;
    size_t phraseCount() override;
    const char* phrase(size_t index, ui::Lang lang) override;
    size_t itemCount() override;
    bool item(size_t index, ui::Item& out) override;
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

private:
    static constexpr size_t MAX_ITEMS = store::QUEUE_SLOTS + store::INBOX_SLOTS;
    static constexpr uint32_t OWN = 0x80000000u;
    struct Ref { uint32_t time; uint32_t seq; };  // bit 31 seq = kolejka
    void rebuild();
    const char* phraseText(const ui::Draft& draft);

    store::Store& store_;
    station::Station& station_;
    station::Services& services_;
    journal::Journal* journal_;
    bool dirty_ = true;
    size_t count_ = 0;
    Ref list_[MAX_ITEMS];
};

}  // namespace console
