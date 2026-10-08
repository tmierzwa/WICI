// SPDX-License-Identifier: MIT
#include "console.h"

#include <string.h>

namespace console {

Console::Console(store::Store& store, station::Station& station, station::Services& services, journal::Journal* journal)
    : store_(store), station_(station), services_(services), journal_(journal) {}

const char* Console::address() { return store_.address(); }

size_t Console::phraseCount() {
    const uint8_t n = store_.config().phraseCount;
    return n ? n : ui_texts::PHRASES_COUNT;
}

const char* Console::phrase(size_t index, ui::Lang lang) {
    const store::Config& c = store_.config();
    const size_t L = static_cast<size_t>(lang);
    if (c.phraseCount) {
        if (index >= c.phraseCount) return "";
        const char* shown = c.phrases[index][L];
        return shown[0] ? shown : c.phrases[index][0];  // brak tłumaczenia: wersja polska
    }
    return index < ui_texts::PHRASES_COUNT ? ui_texts::PHRASES[index][L] : "";
}

void Console::rebuild() {
    // Własne zgłoszenia i TEST w najnowszej rewizji (bez zastąpionych), odpowiedzi i komunikaty; najnowsze najpierw.
    // Pamięć treści też od nowa: po ZNISZCZ DANE numery rekordów zaczynają się od 1.
    cachedSeq_ = 0;
    count_ = 0;
    for (size_t i = 0; i < store_.queueSize(); ++i) {
        const store::QueueEntry* e = store_.queueEntry(i);
        if (!e || (e->type != sa1::REQUEST && e->type != sa1::TEST) || (e->flags & store::REPLACED)) continue;
        bool newer = false;
        for (size_t j = 0; j < store_.queueSize() && !newer; ++j) {
            const store::QueueEntry* o = store_.queueEntry(j);
            newer = o && j != i && o->type == e->type && !memcmp(o->id, e->id, store::HASH) && o->revision > e->revision;
        }
        if (newer) continue;
        list_[count_++] = Ref{e->createdS, e->seq | OWN};
    }
    for (size_t i = 0; i < store::INBOX_SLOTS; ++i) {
        const store::InboxEntry* e = store_.inboxEntry(i);
        if (!e || (e->type != sa1::REPLY && e->type != sa1::BULLETIN)) continue;
        list_[count_++] = Ref{e->receivedS, e->seq};
    }
    for (size_t i = 1; i < count_; ++i) {  // sortowanie przez wstawianie: czas malejąco, przy równym numer malejąco
        const Ref r = list_[i];
        size_t j = i;
        while (j > 0 && (list_[j - 1].time < r.time || (list_[j - 1].time == r.time && (list_[j - 1].seq & ~OWN) < (r.seq & ~OWN)))) {
            list_[j] = list_[j - 1];
            --j;
        }
        list_[j] = r;
    }
    dirty_ = false;
}

size_t Console::itemCount() {
    if (dirty_) rebuild();
    return count_;
}

bool Console::brief(const Ref& ref, uint32_t nowS, ui::Item& out) {
    // Skrót z indeksu w RAM: listy i PRZEKAZANIE ZMIANY nie czytają rekordów z FRAM przy każdym rysowaniu.
    if (ref.seq & OWN) {
        for (size_t i = 0; i < store_.queueSize(); ++i) {
            const store::QueueEntry* e = store_.queueEntry(i);
            if (!e || e->seq != (ref.seq & ~OWN)) continue;
            out.ref = e->seq;
            out.own = true;
            out.type = e->type;
            out.number = store::shortNumber(e->id);
            out.category = e->category;
            out.urgency = e->aux;
            out.state = e->state;
            out.attempts = e->attempts;
            out.nextInS = e->nextTryS > nowS ? e->nextTryS - nowS : 0;
            out.ageS = nowS > e->createdS ? nowS - e->createdS : 0;
            out.cancelled = e->flags & store::CANCELLED;
            return true;
        }
        return false;
    }
    for (size_t i = 0; i < store::INBOX_SLOTS; ++i) {
        const store::InboxEntry* e = store_.inboxEntry(i);
        if (!e || e->seq != ref.seq) continue;
        out.ref = e->seq;
        out.type = e->type;
        out.number = store::shortNumber(e->id);
        out.ageS = nowS > e->receivedS ? nowS - e->receivedS : 0;
        out.unread = !(e->flags & store::INBOX_READ);
        return true;
    }
    return false;
}

bool Console::item(size_t index, ui::Item& out, bool briefOnly) {
    if (dirty_) rebuild();
    if (index >= count_) return false;
    const Ref ref = list_[index];
    out = ui::Item();
    if (!brief(ref, services_.uptimeS(), out)) return false;
    if (briefOnly) return true;
    if (cachedSeq_ != ref.seq) {
        // Liczba osób i treść tylko z rekordu w FRAM (SA1); stan i czasy są w indeksie.
        sa1::Message m;
        if (ref.seq & OWN) {
            store::QueueRecord r;
            if (!store_.queueRead(ref.seq & ~OWN, r) || sa1::decode(r.sa1, r.sa1Length, m)) return false;
        } else {
            store::InboxRecord r;
            if (!store_.inboxRead(ref.seq, r) || sa1::decode(r.sa1, r.sa1Length, m)) return false;
        }
        cachedSeq_ = ref.seq;
        cachedPeople_ = m.people;
        strncpy(cachedText_, m.text, sizeof(cachedText_) - 1);
        cachedText_[sizeof(cachedText_) - 1] = '\0';
    }
    if (out.own) out.people = cachedPeople_;
    memcpy(out.text, cachedText_, sizeof(out.text));
    return true;
}

void Console::markRead(uint32_t ref) {
    if (store_.inboxMarkRead(ref)) { dirty_ = true; services_.changed(); }
}

const char* Console::phraseText(const ui::Draft& draft) {
    // Do SA1 trafia wersja polska frazy; POTRZEBA USTAŁA to ostatnia fraza domyślna.
    if (draft.phrase == ui::PHRASE_RESOLVED) return ui_texts::PHRASES[ui_texts::PHRASES_COUNT - 1][0];
    if (draft.phrase < 0) return "";
    const store::Config& c = store_.config();
    const size_t index = static_cast<size_t>(draft.phrase);
    if (c.phraseCount) return index < c.phraseCount ? c.phrases[index][0] : "";
    return index < ui_texts::PHRASES_COUNT ? ui_texts::PHRASES[index][0] : "";
}

ui::Submit Console::submit(const ui::Draft& draft, uint16_t& number) {
    uint32_t seq = 0;
    station::Create result;
    if (draft.kind == ui::DraftKind::NEW) {
        result = station_.createRequest(draft.category, draft.people, draft.urgency, phraseText(draft), seq);
    } else {
        const char* text = draft.kind == ui::DraftKind::RESOLVED ? phraseText(draft) : nullptr;  // zmiana liczby/pilności zachowuje frazę
        result = station_.revise(draft.ref, draft.people, draft.urgency, text, seq);
    }
    dirty_ = true;
    switch (result) {
        case station::Create::STORED: {
            store::QueueRecord r;
            if (store_.queueRead(seq, r)) number = store::shortNumber(r.id);
            return ui::Submit::STORED;
        }
        case station::Create::NO_ADDRESS: return ui::Submit::NO_ADDRESS;
        case station::Create::FULL: return ui::Submit::FULL;
        default: return ui::Submit::ERROR;
    }
}

bool Console::cancel(uint32_t ref) {
    dirty_ = true;
    return station_.cancel(ref);
}

ui::TestInfo Console::test() {
    ui::TestInfo info;
    if (station_.testPaused()) { info.state = ui::TestState::PAUSED; return info; }
    const store::QueueEntry* newest = nullptr;
    for (size_t i = 0; i < store_.queueSize(); ++i) {
        const store::QueueEntry* e = store_.queueEntry(i);
        if (!e || e->type != sa1::TEST || (e->flags & (store::CANCELLED | store::REPLACED))) continue;
        if (!newest || e->createdS > newest->createdS || (e->createdS == newest->createdS && e->seq > newest->seq)) newest = e;
    }
    if (!newest) return info;
    const uint32_t nowS = services_.uptimeS();
    if (newest->state) { info.state = ui::TestState::CONFIRMED; info.confirmed = newest->state; }
    else if (newest->attempts == 0 && (newest->flags & store::ACTIVE)) {
        info.state = ui::TestState::SCHEDULED;
        info.minutes = newest->nextTryS > nowS ? (newest->nextTryS - nowS + 59) / 60 : 0;
    } else info.state = ui::TestState::SENT;
    return info;
}

bool Console::scheduleTest(bool startup) {
    uint32_t seq = 0;
    dirty_ = true;
    return station_.scheduleTest(startup, seq) == station::Create::STORED;
}

void Console::cancelTest() { dirty_ = true; station_.cancelTest(); }
void Console::pauseTest(bool paused) { dirty_ = true; station_.pauseTest(paused); }

bool Console::alarm(ui::AlarmInfo& out) {
    station::Alarm a;
    if (!station_.alarm(services_.uptimeS(), a)) return false;
    out.kind = a.kind == station::AlarmKind::NO_READ ? ui::AlarmKind::NO_READ : ui::AlarmKind::NO_CONFIRMATION;
    out.ref = a.seq;
    out.number = a.number;
    out.minutes = a.minutes;
    return true;
}

void Console::ackAlarm(const ui::AlarmInfo& alarm) {
    station::Alarm a;
    a.kind = alarm.kind == ui::AlarmKind::NO_READ ? station::AlarmKind::NO_READ : station::AlarmKind::NO_CONFIRMATION;
    a.seq = alarm.ref;
    station_.ackAlarm(a);
}

bool Console::announce() {
    const bool ok = services_.announce();
    services_.log(ok ? "announce requested (screen)" : "announce: stack not running");
    return ok;
}

bool Console::switchBackup() {
    // Tożsamość zapasowa OSP z karty; nieodwracalne (powrót tylko nową konfiguracją).
    store::Config c = store_.config();
    uint8_t zero[store::HASH] = {};
    if (!store_.configured() || !memcmp(c.osp[1], zero, store::HASH)) { services_.log("backup recipient: none configured"); return false; }
    c.activeOsp = 1;
    if (!store_.writeConfig(c)) { services_.log("backup recipient: write failed"); return false; }
    services_.log("switched to backup recipient");
    station_.backupSwitched();
    dirty_ = true;
    services_.changed();
    return true;
}

bool Console::destroy() {
    // ZNISZCZ DANE: konfiguracja, kolejka, skrzynka, zdarzenia, klucze odbioru i dziennik zdarzeń; dług ciszy zostaje.
    const bool storeOk = store_.destroy();
    const bool journalOk = !journal_ || journal_->eraseEvents();
    if (storeOk) services_.destroyed();   // jak polecenie destroy przez USB: także kod IFAC i tożsamość
    services_.log(storeOk && journalOk ? "data destroyed" : "destroy failed");
    dirty_ = true;
    services_.changed();
    return storeOk && journalOk;
}

}  // namespace console
