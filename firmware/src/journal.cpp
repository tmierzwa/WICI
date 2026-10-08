// SPDX-License-Identifier: MIT
#include "journal.h"

#include <string.h>

#include "crc16.h"

namespace journal {

namespace {

void putU32(uint8_t* out, uint32_t value) {
    out[0] = static_cast<uint8_t>(value);
    out[1] = static_cast<uint8_t>(value >> 8);
    out[2] = static_cast<uint8_t>(value >> 16);
    out[3] = static_cast<uint8_t>(value >> 24);
}

uint32_t getU32(const uint8_t* in) {
    return static_cast<uint32_t>(in[0]) | (static_cast<uint32_t>(in[1]) << 8) | (static_cast<uint32_t>(in[2]) << 16) |
           (static_cast<uint32_t>(in[3]) << 24);
}

bool seqUsable(uint32_t seq) { return seq != 0 && seq != 0xFFFFFFFF; }  // pusta FRAM: same 0x00 albo 0xFF

constexpr size_t SMALL_CRC = 16;      // CRC(0..15) w bajtach 16..17
constexpr size_t SMALL_MARK = 18;     // znacznik zatwierdzenia

}  // namespace

bool blank(const uint8_t* data, size_t length) {
    bool zeros = true, ones = true;
    for (size_t i = 0; i < length; ++i) {
        zeros &= data[i] == 0x00;
        ones &= data[i] == 0xFF;
    }
    return zeros || ones;
}

// Rekord 24 B: 0..3 numer, 4..7 a, 8..11 b, 12..15 c, 16..17 CRC(0..15), 18 znacznik, 19..23 zapas.
void encodeSmall(const SmallRecord& record, uint8_t out[SMALL_RECORD]) {
    memset(out, 0, SMALL_RECORD);
    putU32(out, record.seq);
    putU32(out + 4, record.a);
    putU32(out + 8, record.b);
    putU32(out + 12, record.c);
    const uint16_t crc = p1::crc16(out, SMALL_CRC);
    out[SMALL_CRC] = static_cast<uint8_t>(crc >> 8);
    out[SMALL_CRC + 1] = static_cast<uint8_t>(crc & 0xFF);
}

bool decodeSmall(const uint8_t in[SMALL_RECORD], SmallRecord& record) {
    if (in[SMALL_MARK] != COMMITTED) return false;
    const uint16_t crc = static_cast<uint16_t>((in[SMALL_CRC] << 8) | in[SMALL_CRC + 1]);
    if (p1::crc16(in, SMALL_CRC) != crc) return false;
    record.seq = getU32(in);
    if (!seqUsable(record.seq)) return false;
    record.a = getU32(in + 4);
    record.b = getU32(in + 8);
    record.c = getU32(in + 12);
    return true;
}

// Rekord 64 B: 0..3 numer, 4..7 czas pracy, 8 długość, 9..61 tekst, 62..63 CRC(0..61).
void encodeEvent(const EventRecord& record, uint8_t out[EVENT_RECORD]) {
    memset(out, 0, EVENT_RECORD);
    putU32(out, record.seq);
    putU32(out + 4, record.uptimeS);
    size_t length = strlen(record.text);
    if (length > EVENT_TEXT) length = EVENT_TEXT;
    out[8] = static_cast<uint8_t>(length);
    memcpy(out + 9, record.text, length);
    const uint16_t crc = p1::crc16(out, EVENT_RECORD - 2);
    out[EVENT_RECORD - 2] = static_cast<uint8_t>(crc >> 8);
    out[EVENT_RECORD - 1] = static_cast<uint8_t>(crc & 0xFF);
}

bool decodeEvent(const uint8_t in[EVENT_RECORD], EventRecord& record) {
    const uint16_t crc = static_cast<uint16_t>((in[EVENT_RECORD - 2] << 8) | in[EVENT_RECORD - 1]);
    if (p1::crc16(in, EVENT_RECORD - 2) != crc) return false;
    record.seq = getU32(in);
    if (!seqUsable(record.seq) || in[8] > EVENT_TEXT) return false;
    record.uptimeS = getU32(in + 4);
    memcpy(record.text, in + 9, in[8]);
    record.text[in[8]] = '\0';
    return true;
}

Journal::Journal(Storage& storage) : storage_(storage) {}

bool Journal::scanSmall(uint32_t base, SmallRecord& latest, uint32_t& validCount, uint32_t& corruptCount) {
    latest = SmallRecord();
    validCount = 0;
    corruptCount = 0;
    uint8_t buffer[SMALL_RECORD];
    for (uint32_t slot = 0; slot < SMALL_SLOTS; ++slot) {
        if (!storage_.read(base + slot * SMALL_RECORD, buffer, SMALL_RECORD)) return false;
        SmallRecord record;
        if (decodeSmall(buffer, record)) {
            ++validCount;
            if (record.seq > latest.seq) latest = record;
        } else if (!blank(buffer, SMALL_RECORD) && buffer[SMALL_MARK] == COMMITTED) {
            // Zatwierdzony rekord z błędnym CRC; rekord bez znacznika to zapis przerwany zanikiem.
            ++corruptCount;
        }
    }
    return true;
}

bool Journal::begin() {
    ok_ = false;
    uint32_t valid = 0, corrupt = 0;
    if (!scanSmall(DEBT_BASE, debt_, debtValid_, corrupt)) return false;
    if (!scanSmall(CLOCK_BASE, clock_, valid, corrupt)) return false;
    if (!scanSmall(SETTINGS_BASE, settings_, valid, corrupt)) return false;
    if (!scanSmall(RESERVE_BASE, reserve_, valid, corrupt)) return false;
    if (!scanSmall(FORMAT_BASE, format_, valid, corrupt)) return false;
    if (valid) formatState_ = format_.b == static_cast<uint32_t>(FormatState::DESTROYING) ? FormatState::DESTROYING : FormatState::READY;
    else formatState_ = corrupt ? FormatState::CORRUPT : FormatState::BLANK;
    event_ = EventRecord();
    uint8_t buffer[EVENT_RECORD];
    for (uint32_t slot = 0; slot < EVENT_SLOTS; ++slot) {
        if (!storage_.read(EVENT_BASE + slot * EVENT_RECORD, buffer, EVENT_RECORD)) return false;
        EventRecord record;
        if (decodeEvent(buffer, record) && record.seq > event_.seq) event_ = record;
    }
    ok_ = true;
    return true;
}

bool Journal::writeSmall(uint32_t base, SmallRecord& current, uint32_t a, uint32_t b, uint32_t c) {
    if (!ok_) return false;
    SmallRecord next;
    next.seq = current.seq + 1;
    if (!seqUsable(next.seq)) next.seq = 1;
    next.a = a;
    next.b = b;
    next.c = c;
    const uint32_t address = base + (next.seq % SMALL_SLOTS) * SMALL_RECORD;  // najstarszy slot; najnowsze zostają
    uint8_t buffer[SMALL_RECORD];
    encodeSmall(next, buffer);
    if (!storage_.write(address, buffer, SMALL_RECORD)) return false;  // treść ze znacznikiem 0
    const uint8_t committed = COMMITTED;
    if (!storage_.write(address + SMALL_MARK, &committed, 1)) return false;   // zatwierdzenie po treści
    uint8_t check[SMALL_RECORD];
    SmallRecord back;
    if (!storage_.read(address, check, SMALL_RECORD) || !decodeSmall(check, back) || back.seq != next.seq ||
        back.a != a || back.b != b || back.c != c) {
        return false;
    }
    current = next;
    return true;
}

bool Journal::startClock() {
    return writeSmall(CLOCK_BASE, clock_, clock_.a + RESTART_SKIP_S, clock_.b + RESTART_SKIP_S, clock_.c + 1);
}

bool Journal::writeDebt(uint32_t debtMs, uint32_t uptimeS) {
    if (!writeSmall(DEBT_BASE, debt_, debtMs, uptimeS, 0)) return false;
    if (debtValid_ < SMALL_SLOTS) ++debtValid_;
    return true;
}

bool Journal::writeClock(uint32_t counterS) {
    if (counterS < clock_.a) return false;   // licznik się nie cofa
    return writeSmall(CLOCK_BASE, clock_, counterS, clock_.b, clock_.c);
}

bool Journal::writeSettings(uint32_t language, uint32_t flags) {
    return writeSmall(SETTINGS_BASE, settings_, language, flags, 0);
}

bool Journal::writeReservation(uint64_t upper) {
    if (upper < reservation()) return false;
    return writeSmall(RESERVE_BASE, reserve_, static_cast<uint32_t>(upper), static_cast<uint32_t>(upper >> 32), 0);
}

bool Journal::writeFormat(FormatState state, uint32_t flags) {
    if (!writeSmall(FORMAT_BASE, format_, FRAM_FORMAT, static_cast<uint32_t>(state), flags)) return false;
    formatState_ = state;
    return true;
}

bool Journal::eraseRing(uint32_t base, SmallRecord& current) {
    uint8_t zero[SMALL_RECORD] = {};
    for (uint32_t slot = 0; slot < SMALL_SLOTS; ++slot) {
        if (!storage_.write(base + slot * SMALL_RECORD, zero, SMALL_RECORD)) return false;
    }
    current = SmallRecord();
    return true;
}

bool Journal::erase() {
    if (!ok_) return false;
    if (!eraseRing(CLOCK_BASE, clock_) || !eraseRing(SETTINGS_BASE, settings_)) return false;
    uint8_t zero[EVENT_RECORD] = {};
    for (uint32_t slot = 0; slot < EVENT_SLOTS; ++slot) {
        if (!storage_.write(EVENT_BASE + slot * EVENT_RECORD, zero, EVENT_RECORD)) return false;
    }
    event_ = EventRecord();
    return true;
}

bool Journal::writeEvent(uint32_t uptimeS, const char* text) {
    if (!ok_) return false;
    EventRecord next;
    next.seq = event_.seq + 1;
    if (!seqUsable(next.seq)) next.seq = 1;
    next.uptimeS = uptimeS;
    strncpy(next.text, text, EVENT_TEXT);
    next.text[EVENT_TEXT] = '\0';
    uint8_t buffer[EVENT_RECORD];
    encodeEvent(next, buffer);
    if (!storage_.write(EVENT_BASE + (next.seq % EVENT_SLOTS) * EVENT_RECORD, buffer, EVENT_RECORD)) return false;
    event_ = next;
    return true;
}

bool Journal::readEvent(uint32_t back, EventRecord& record) {
    if (!ok_ || back >= EVENT_SLOTS || back >= event_.seq) return false;
    const uint32_t seq = event_.seq - back;
    uint8_t buffer[EVENT_RECORD];
    if (!storage_.read(EVENT_BASE + (seq % EVENT_SLOTS) * EVENT_RECORD, buffer, EVENT_RECORD)) return false;
    return decodeEvent(buffer, record) && record.seq == seq;
}

}  // namespace journal
