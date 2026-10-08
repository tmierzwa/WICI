// SPDX-License-Identifier: MIT
#include "console.h"

#include <string.h>

namespace console {

Console::Console(store::Store& store, station::Station& station, Actions& actions) : store_(store), station_(station), actions_(actions) {}

size_t Console::phraseCount() {
    const uint8_t n = store_.config().phraseCount;
    return n ? n : ui_texts::PHRASES_COUNT;
}

const char* Console::phrase(size_t index, ui::Lang lang) {
    const config::Config& c = store_.config();
    const size_t L = static_cast<size_t>(lang);
    if (c.phraseCount) {
        if (index >= c.phraseCount) return "";
        const char* shown = c.phrases[index][L];
        return shown[0] ? shown : c.phrases[index][0];  // brak tłumaczenia: wersja polska
    }
    return index < ui_texts::PHRASES_COUNT ? ui_texts::PHRASES[index][L] : "";
}

int Console::ownSlot(uint32_t ref) const {
    if (!(ref & OWN)) return -1;
    const size_t slot = ref & 0xFFFF;
    if (slot >= store::REGISTER_SLOTS) return -1;
    const store::RequestIndex& r = store_.request(slot);
    return r.used() && ownRef(slot, r.gen) == ref ? static_cast<int>(slot) : -1;
}

void Console::rebuild() {
    // Własne zgłoszenia i TEST bez anulowanych (znikają z listy), odpowiedzi i komunikaty; najnowsze najpierw.
    count_ = 0;
    for (size_t i = 0; i < store::REGISTER_SLOTS; ++i) {
        const store::RequestIndex& r = store_.request(i);
        if (!r.used() || r.stage == store::Stage::CANCELLED) continue;
        list_[count_++] = Entry{r.commitS, ownRef(i, r.gen)};
    }
    for (size_t i = 0; i < store::INBOX_SLOTS; ++i) {
        const store::MessageIndex& m = store_.message(i);
        if (m.used()) list_[count_++] = Entry{m.receivedS, m.number};
    }
    for (size_t i = 1; i < count_; ++i) {  // sortowanie przez wstawianie: czas malejąco, przy równym ref malejąco
        const Entry e = list_[i];
        size_t j = i;
        while (j > 0 && (list_[j - 1].time < e.time || (list_[j - 1].time == e.time && list_[j - 1].ref < e.ref))) {
            list_[j] = list_[j - 1];
            --j;
        }
        list_[j] = e;
    }
    dirty_ = false;
}

size_t Console::itemCount() {
    if (dirty_) rebuild();
    return count_;
}

bool Console::brief(uint32_t ref, ui::Item& out) {
    // Skrót z indeksu w RAM: listy i PRZEKAZANIE ZMIANY nie czytają rekordów z FRAM przy każdym rysowaniu.
    const uint32_t nowS = store_.now();
    const int slot = ownSlot(ref);
    if (slot >= 0) {
        const store::RequestIndex& r = store_.request(static_cast<size_t>(slot));
        if (r.stage == store::Stage::CANCELLED) return false;
        out.ref = ref;
        out.own = true;
        out.type = r.type;
        out.number = r.number();
        out.category = r.category;
        out.urgency = r.urgency;
        out.stage = static_cast<ui::Stage>(r.stage);
        out.decision = r.decision;
        out.sentOnce = r.flags & store::SENT_ONCE;
        out.attempts = r.attempts;
        out.nextInS = r.nextTryS > nowS ? r.nextTryS - nowS : 0;
        out.ageS = nowS > r.commitS ? nowS - r.commitS : 0;
        return true;
    }
    if (ref & OWN) return false;
    const int index = store_.findMessage(ref);
    if (index < 0) return false;
    const store::MessageIndex& m = store_.message(static_cast<size_t>(index));
    out.ref = ref;
    out.type = m.type;
    out.number = store::prefixNumber(m.idPrefix);
    out.ageS = nowS > m.receivedS ? nowS - m.receivedS : 0;
    out.unread = !m.read;
    return true;
}

bool Console::item(size_t index, ui::Item& out, bool briefOnly) {
    if (dirty_) rebuild();
    if (index >= count_) return false;
    const uint32_t ref = list_[index].ref;
    out = ui::Item();
    if (!brief(ref, out)) return false;
    if (briefOnly) return true;
    const int slot = ownSlot(ref);
    const uint16_t revision = slot >= 0 ? store_.request(static_cast<size_t>(slot)).rMax : 0;
    // Numer wiadomości liczy się od 1 w każdej epoce, więc klucz pamięci obejmuje epokę.
    if (cachedRef_ != ref || cachedRevision_ != revision || memcmp(cachedEpoch_, store_.meta().epoch, store::EPOCH)) {
        // Liczba osób i treść tylko z rekordu w FRAM (SA1); etap i czasy są w indeksie.
        sa1::Message m;
        if (slot >= 0) {
            store::Request r;
            if (!store_.readRequest(static_cast<size_t>(slot), r) || sa1::decode(r.sa1, r.sa1Length, m)) return false;
        } else {
            store::Message r;
            const int at = store_.findMessage(ref);
            if (at < 0 || !store_.readMessage(static_cast<size_t>(at), r) || sa1::decode(r.sa1, r.sa1Length, m)) return false;
        }
        cachedRef_ = ref;
        cachedRevision_ = revision;
        memcpy(cachedEpoch_, store_.meta().epoch, store::EPOCH);
        cachedPeople_ = m.people;
        strncpy(cachedText_, m.text, sizeof(cachedText_) - 1);
        cachedText_[sizeof(cachedText_) - 1] = '\0';
    }
    if (out.own) out.people = cachedPeople_;
    memcpy(out.text, cachedText_, sizeof(out.text));
    return true;
}

void Console::markRead(uint32_t ref) {
    if (!(ref & OWN) && station_.markRead(ref)) dirty_ = true;
}

const char* Console::phraseText(const ui::Draft& draft) {
    // Do SA1 trafia wersja polska frazy; POTRZEBA USTAŁA to ostatnia fraza domyślna.
    if (draft.phrase == ui::PHRASE_RESOLVED) return ui_texts::PHRASES[ui_texts::PHRASES_COUNT - 1][0];
    if (draft.phrase < 0) return "";
    const config::Config& c = store_.config();
    const size_t index = static_cast<size_t>(draft.phrase);
    if (c.phraseCount) return index < c.phraseCount ? c.phrases[index][0] : "";
    return index < ui_texts::PHRASES_COUNT ? ui_texts::PHRASES[index][0] : "";
}

ui::Submit Console::submit(const ui::Draft& draft, uint16_t& number) {
    station::Result result;
    if (draft.kind == ui::DraftKind::NEW) {
        result = station_.create(draft.category, draft.people, draft.urgency, phraseText(draft), number);
    } else {
        const int slot = ownSlot(draft.ref);
        const char* text = draft.kind == ui::DraftKind::RESOLVED ? phraseText(draft) : nullptr;  // zmiana liczby/pilności zachowuje frazę
        result = slot < 0 ? station::Result::NOT_FOUND : station_.revise(static_cast<uint16_t>(slot), draft.people, draft.urgency, text);
        if (result == station::Result::STORED) number = store_.request(static_cast<size_t>(slot)).number();
    }
    dirty_ = true;
    switch (result) {
        case station::Result::STORED: return ui::Submit::STORED;
        case station::Result::NO_ADDRESS: return ui::Submit::NO_ADDRESS;
        case station::Result::FULL: return ui::Submit::FULL;
        default: return ui::Submit::ERROR;   // blad_pamieci: zgłoszenie nie zapisane
    }
}

bool Console::cancel(uint32_t ref) {
    const int slot = ownSlot(ref);
    store::Request r;
    bool released = false;
    dirty_ = true;
    return slot >= 0 && store_.readRequest(static_cast<size_t>(slot), r) && station_.cancel(r.id, released) == station::Result::STORED;
}

ui::TestInfo Console::test() {
    ui::TestInfo info;
    if (station_.testPaused()) { info.state = ui::TestState::PAUSED; return info; }
    const int pending = station_.pendingTest();
    if (pending >= 0) {
        const uint32_t nowS = store_.now(), at = store_.request(static_cast<size_t>(pending)).nextTryS;
        info.state = ui::TestState::SCHEDULED;
        info.minutes = at > nowS ? (at - nowS + 59) / 60 : 0;
        return info;
    }
    const int latest = station_.latestTest();
    if (latest < 0) return info;
    const store::RequestIndex& r = store_.request(static_cast<size_t>(latest));
    if (r.stage == store::Stage::RECEIVED) {
        info.state = ui::TestState::CONFIRMED;
        info.confirmed = r.decision >= 2 ? r.decision : 1;
    } else info.state = ui::TestState::SENT;
    return info;
}

bool Console::scheduleTest(bool startup) {
    dirty_ = true;
    return station_.scheduleTest(startup) == station::Result::STORED;
}

void Console::cancelTest() { dirty_ = true; station_.cancelTest(); }
void Console::pauseTest(bool paused) { dirty_ = true; station_.pauseTest(paused); }

void Console::setRadioFault(bool fault) {
    if (!fault) radioAcked_ = false;
    radioFault_ = fault;
}

bool Console::alarm(ui::AlarmInfo& out) {
    station::Alarm a;
    if (!store_.ok() || !station_.alarm(a)) {
        if (!radioFault_ || radioAcked_) return false;
        out = ui::AlarmInfo();
        out.kind = ui::AlarmKind::RADIO_FAULT;
        return true;
    }
    out.kind = a.kind == station::AlarmKind::NO_READ ? ui::AlarmKind::NO_READ : ui::AlarmKind::NO_CONFIRMATION;
    out.ref = ownRef(a.slot, a.gen);
    out.number = a.number;
    out.minutes = a.minutes;
    return true;
}

void Console::ackAlarm(const ui::AlarmInfo& alarm) {
    if (alarm.kind == ui::AlarmKind::RADIO_FAULT) { radioAcked_ = true; return; }
    station::Alarm a;
    a.kind = alarm.kind == ui::AlarmKind::NO_READ ? station::AlarmKind::NO_READ : station::AlarmKind::NO_CONFIRMATION;
    a.slot = static_cast<uint16_t>(alarm.ref & 0xFFFF);
    a.gen = store_.request(a.slot < store::REGISTER_SLOTS ? a.slot : 0).gen;
    if (ownSlot(alarm.ref) >= 0) station_.ackAlarm(a);
}

bool Console::announce() {
    const bool ok = actions_.announce();
    actions_.log(ok ? "announce requested (screen)" : "announce: stack not running");
    return ok;
}

bool Console::switchBackup() {
    // KLUCZ ZAPASOWY: nieodwracalny (powrót tylko nową konfiguracją z kartą odbiorcy).
    const bool ok = station_.switchBackup();
    if (!ok) actions_.log("backup receiver: switch failed");
    dirty_ = true;
    return ok;
}

bool Console::destroy() {
    const bool ok = actions_.destroy();
    dirty_ = true;
    cachedRef_ = 0;   // po ZNISZCZ DANE numery i gniazda zaczynają się od nowa
    return ok;
}

}  // namespace console
