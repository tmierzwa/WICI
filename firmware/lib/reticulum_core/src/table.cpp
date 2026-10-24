// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
#include "table.h"

#include <string.h>

#include <Crypto.h>

namespace rnscore {

namespace {

constexpr uint8_t COMMITTED = 0xA5;
constexpr uint8_t FORMAT = 2;   // 2: klucz i skrót losowy w danych ogłoszenia (gniazdo 568 B)
// Czytane przy montowaniu: znacznik, wersja, gniazdo, numer, znaczniki, użycie, cel, wygaśnięcie i użycie trasy.
constexpr size_t HEADER = 40;
constexpr size_t AT_SLOT = 2, AT_SEQUENCE = 4, AT_FLAGS = 8, AT_HOPS = 9, AT_ANNOUNCE_LENGTH = 10, AT_USED = 12,
                 AT_DESTINATION = 16, AT_EXPIRES = 32, AT_PATH_USED = 36, AT_RATCHET_TIME = 40, AT_RATCHET_EMITTED = 44,
                 AT_NEXT_HOP = 48, AT_RATCHET = 64, AT_ANNOUNCE = 96, AT_CRC = 561;
// W danych ogłoszenia (RNS/Identity.py: validate_announce): klucz publiczny, skrót nazwy, skrót losowy.
constexpr size_t AT_PUBLIC_KEY = AT_ANNOUNCE, AT_RANDOM = AT_ANNOUNCE + KEY_SIZE + NAME_HASH_SIZE;
// FLAG_INTERFACE: trasa przez interfejs 1 (węzeł stanowiska: USB); w gniazdach sprzed etapu R4 zero, czyli P1.
constexpr uint8_t FLAG_PATH = 0x01, FLAG_RATCHET = 0x02, FLAG_CONTEXT = 0x04, FLAG_INTERFACE = 0x08;
constexpr uint8_t interfaceOf(uint8_t flags) { return (flags & FLAG_INTERFACE) ? 1 : 0; }
static_assert(AT_ANNOUNCE + ANNOUNCE_FORWARDABLE_SIZE <= AT_CRC, "ogłoszenie przed CRC");
static_assert(AT_CRC + 4 <= TABLE_SLOT_SIZE, "CRC w gnieździe");

uint32_t get32(const uint8_t* p) {
    return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) | (static_cast<uint32_t>(p[2]) << 16) |
           (static_cast<uint32_t>(p[3]) << 24);
}

void put32(uint8_t* p, uint32_t v) {
    for (int i = 0; i < 4; ++i) p[i] = static_cast<uint8_t>(v >> (8 * i));
}

uint16_t get16(const uint8_t* p) { return static_cast<uint16_t>(p[0] | (p[1] << 8)); }

void put16(uint8_t* p, uint16_t v) {
    p[0] = static_cast<uint8_t>(v);
    p[1] = static_cast<uint8_t>(v >> 8);
}

// CRC-32 (IEEE 802.3, odbite, jak src/crc32.h stacji), bez tablicy w RAM.
uint32_t crc32(const uint8_t* data, size_t length) {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < length; ++i) {
        crc ^= data[i];
        for (int b = 0; b < 8; ++b) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

uint32_t offsetOf(size_t slot) { return static_cast<uint32_t>(slot * TABLE_SLOT_SIZE); }

// Czas z gniazda najwyżej nowS: czas z przyszłości (zegar cofnięty przy starcie) nie przedłuża wpisu, a różnica
// nowS - czas się nie zawija.
uint32_t notAfter(uint32_t timeS, uint32_t nowS) { return timeS > nowS ? nowS : timeS; }

}  // namespace

void Table::setBit(uint8_t* bits, size_t slot, bool on) {
    const uint8_t mask = static_cast<uint8_t>(1u << (slot % 8));
    if (on) bits[slot / 8] |= mask;
    else bits[slot / 8] &= static_cast<uint8_t>(~mask);
}

void Table::drop(size_t slot) {
    if (!live(slot)) return;
    setBit(live_, slot, false);
    setBit(path_, slot, false);
    setBit(second_, slot, false);
    memset(&index_[slot], 0, sizeof(index_[slot]));
    if (bufferSlot_ == slot + 1) bufferSlot_ = 0;
    --count_;
}

bool Table::readHeader(size_t slot, uint8_t* header) { return storage_->read(offsetOf(slot), header, HEADER); }

void Table::mount(size_t slot, const uint8_t* header, uint32_t nowS) {
    memcpy(index_[slot].destination, header + AT_DESTINATION, TRUNCATED_HASH_SIZE);
    // Czas z przyszłości (zegar cofnięty) nie chroni wpisu przed wyparciem, a trasa nie wygasa od razu.
    index_[slot].usedS = notAfter(get32(header + AT_USED), nowS);
    index_[slot].pathUsedS = notAfter(get32(header + AT_PATH_USED), nowS);
    setBit(live_, slot, true);
    setBit(path_, slot, (header[AT_FLAGS] & FLAG_PATH) && interfaceOf(header[AT_FLAGS]) < interfaces_);
    setBit(second_, slot, interfaceOf(header[AT_FLAGS]) == 1);
    ++count_;
}

// RNS/Transport.py: Transport.start (wczytanie destination_table) i RNS/Identity.py: load_known_destinations.
void Table::begin(TableStorage& storage, uint32_t nowS, uint8_t interfaces) {
    memset(stale_, 0, sizeof(stale_));
    clear();
    storage_ = &storage;
    bootS_ = nowS;
    interfaces_ = interfaces;
    for (size_t slot = 0; slot < TABLE_SLOTS; ++slot) {
        uint8_t header[HEADER];
        if (!readHeader(slot, header)) continue;
        if (header[0] != COMMITTED || header[1] != FORMAT || get16(header + AT_SLOT) != slot) continue;
        const uint32_t sequence = get32(header + AT_SEQUENCE);
        if (sequence > sequence_) sequence_ = sequence;
        const int found = find(header + AT_DESTINATION);
        if (found >= 0) {
            // Dwie kopie celu (zanik zasilania przed unieważnieniem starej). Przegrana kopia jest unieważniana, żeby nie
            // wróciła po wyparciu zwycięskiej, ale dopiero po odczycie całej zwycięskiej z CRC. Błąd odczytu niczego nie
            // unieważnia: obie kopie zostają w FRAM, a w indeksie ta, którą już wczytano; rozstrzyga następny start.
            const size_t other = static_cast<size_t>(found);
            uint8_t otherHeader[HEADER];
            if (!readHeader(other, otherHeader)) continue;
            if (get32(otherHeader + AT_SEQUENCE) > sequence) {   // nowsza kopia już w indeksie
                if (load(other)) invalidate(slot);
                else if (!live(other)) mount(slot, header, nowS);   // jej treść uszkodzona: ta kopia zostaje
                continue;
            }
            drop(other);
            mount(slot, header, nowS);
            if (load(slot)) {
                invalidate(other);
            } else if (!live(slot)) {   // treść nowszej uszkodzona: wraca starsza
                mount(other, otherHeader, nowS);
            }
            continue;
        }
        mount(slot, header, nowS);
    }
}

int Table::find(const uint8_t destination[TRUNCATED_HASH_SIZE]) const {
    for (size_t slot = 0; slot < TABLE_SLOTS; ++slot) {
        if (live(slot) && memcmp(index_[slot].destination, destination, TRUNCATED_HASH_SIZE) == 0) return static_cast<int>(slot);
    }
    return -1;
}

// Obraz gniazda w buforze ze sprawdzeniem znacznika, numeru gniazda, celu i CRC (bez wygasania).
bool Table::load(size_t s) {
    bufferSlot_ = 0;
    const uint8_t* b = buffer_;
    if (!storage_->read(offsetOf(s), buffer_, sizeof(buffer_))) return false;   // np. chwilowy błąd SPI: wpis zostaje
    if (b[0] != COMMITTED || b[1] != FORMAT || get16(b + AT_SLOT) != s ||
        memcmp(b + AT_DESTINATION, index_[s].destination, TRUNCATED_HASH_SIZE) != 0 ||
        get32(b + AT_CRC) != crc32(b + 1, AT_CRC - 1) || get16(b + AT_ANNOUNCE_LENGTH) > ANNOUNCE_FORWARDABLE_SIZE) {
        drop(s);   // uszkodzone gniazdo: pominięte i wolne (nadpisze je następny zapis)
        ++corrupt_;
        return false;
    }
    bufferSlot_ = s + 1;
    return true;
}

bool Table::read(int slot, KnownDestination& out, uint32_t nowS) {
    if (slot < 0 || static_cast<size_t>(slot) >= TABLE_SLOTS || !live(static_cast<size_t>(slot))) return false;
    const size_t s = static_cast<size_t>(slot);
    if (!load(s)) return false;
    const uint8_t* b = buffer_;
    memcpy(out.destination, b + AT_DESTINATION, TRUNCATED_HASH_SIZE);
    memcpy(out.publicKey, b + AT_PUBLIC_KEY, KEY_SIZE);
    memcpy(out.ratchet, b + AT_RATCHET, RATCHET_SIZE);
    memcpy(out.randomHash, b + AT_RANDOM, RANDOM_HASH_SIZE);
    memcpy(out.nextHop, b + AT_NEXT_HOP, TRUNCATED_HASH_SIZE);
    out.pathExpiresS = get32(b + AT_EXPIRES);
    out.usedS = index_[s].usedS;
    out.pathUsedS = index_[s].pathUsedS;
    out.ratchetS = get32(b + AT_RATCHET_TIME);
    out.ratchetEmittedS = get32(b + AT_RATCHET_EMITTED);
    out.announceLength = get16(b + AT_ANNOUNCE_LENGTH);
    out.hops = b[AT_HOPS];
    out.interface = interfaceOf(b[AT_FLAGS]);
    // Transport.start: wpis path_table bez interfejsu odbioru nie wraca (trasa przez interfejs spoza liczby).
    out.hasPath = (b[AT_FLAGS] & FLAG_PATH) && out.interface < interfaces_;
    out.hasRatchet = b[AT_FLAGS] & FLAG_RATCHET;
    out.contextFlag = b[AT_FLAGS] & FLAG_CONTEXT;
    // Transport.jobs: trasa nieużywana dłużej niż DESTINATION_TIMEOUT usunięta z path_table (wpis w FRAM
    // zmienia następny zapis); expire() robi to samo w indeksie.
    if (out.hasPath && nowS - out.pathUsedS > DESTINATION_TIMEOUT_S) {
        out.hasPath = false;
        setBit(path_, s, false);
    }
    // Identity.get_ratchet: ratchet wczytany z pamięci po starcie tylko przed RATCHET_EXPIRY. Czas
    // z przyszłości to ratchet sprzed startu z cofniętym zegarem, w nieznanym wieku: bez ratchetu (stacja
    // szyfruje do klucza tożsamości celu do jego następnego ogłoszenia).
    if (out.hasRatchet && (out.ratchetS > nowS ||
                           (out.ratchetS < bootS_ && nowS >= out.ratchetS + static_cast<uint64_t>(RATCHET_EXPIRY_S)))) {
        out.hasRatchet = false;
    }
    return true;
}

bool Table::readKey(int slot, uint8_t out[KEY_SIZE]) {
    if (slot < 0 || static_cast<size_t>(slot) >= TABLE_SLOTS || !live(static_cast<size_t>(slot))) return false;
    return storage_->read(offsetOf(static_cast<size_t>(slot)) + AT_PUBLIC_KEY, out, KEY_SIZE);
}

const uint8_t* Table::announce() const { return buffer_ + AT_ANNOUNCE; }

bool Table::invalidate(size_t slot) {
    const uint8_t zero = 0;
    ++writes_;
    const bool ok = storage_->write(offsetOf(slot), &zero, 1);
    setBit(stale_, slot, !ok);
    return ok;
}

// Najdawniej używany cel bez ochrony (specyfikacja, „Pojemności stosu”) poza gniazdem keep; -1, gdy brak.
int Table::victim(int keep, bool (*pinned)(const uint8_t*, void*), void* context) const {
    int best = -1;
    for (size_t slot = 0; slot < TABLE_SLOTS; ++slot) {
        if (!live(slot) || static_cast<int>(slot) == keep) continue;
        if (pinned && pinned(index_[slot].destination, context)) continue;
        if (best < 0 || index_[slot].usedS < index_[best].usedS) best = static_cast<int>(slot);
    }
    return best;
}

// RNS/Identity.py: remember i _remember_ratchet, RNS/Transport.py: path_table[...] = ..., cache i
// save_path_table: tu jeden zapis gniazda przy każdej zmianie wpisu.
int Table::write(int slot, const KnownDestination& entry, Cached cached, const uint8_t* announce, size_t length,
                 bool (*pinned)(const uint8_t destination[TRUNCATED_HASH_SIZE], void* context), void* context) {
    if (!storage_ || (cached == Cached::SET && length && (!announce || length > ANNOUNCE_FORWARDABLE_SIZE))) return -1;
    if (slot >= 0 && (static_cast<size_t>(slot) >= TABLE_SLOTS || !live(static_cast<size_t>(slot)))) return -1;
    const bool keep = cached == Cached::KEEP && slot >= 0;
    if (keep && bufferSlot_ != static_cast<size_t>(slot) + 1) {   // ogłoszenie z gniazda: obraz musi być w buforze
        if (!load(static_cast<size_t>(slot))) return -1;
    }
    // Nowy cel przy pełnej tablicy: wyparcie przed zapisem (zanik zasilania gubi najwyżej wypierany wpis).
    while (slot < 0 && count_ >= (limit_ ? limit_ : KNOWN_MAX)) {
        const int v = victim(-1, pinned, context);
        if (v < 0) return -1;
        invalidate(static_cast<size_t>(v));
        drop(static_cast<size_t>(v));
    }
    int target = -1;
    for (size_t s = 0; s < TABLE_SLOTS && target < 0; ++s) {
        if (!live(s)) target = static_cast<int>(s);
    }
    if (target < 0) {   // indeks z montowania pełniejszy niż limit: miejsce po najdawniej używanym
        const int v = victim(slot, pinned, context);
        if (v < 0) return -1;
        invalidate(static_cast<size_t>(v));
        drop(static_cast<size_t>(v));
        target = v;
    }

    uint8_t* b = buffer_;
    const bool flag = keep ? (b[AT_FLAGS] & FLAG_CONTEXT) != 0 : entry.contextFlag;
    if (!keep) {
        if (length) memcpy(b + AT_ANNOUNCE, announce, length);
        put16(b + AT_ANNOUNCE_LENGTH, static_cast<uint16_t>(length));
    }   // inaczej ogłoszenie i jego długość zostają w buforze z read()
    size_t kept = get16(b + AT_ANNOUNCE_LENGTH);
    // Klucz i skrót losowy wpisu leżą w danych ogłoszenia; ogłoszenie z innymi nie zostaje w pamięci podręcznej.
    if (kept && (memcmp(b + AT_PUBLIC_KEY, entry.publicKey, KEY_SIZE) != 0 ||
                 memcmp(b + AT_RANDOM, entry.randomHash, RANDOM_HASH_SIZE) != 0)) {
        kept = 0;
        put16(b + AT_ANNOUNCE_LENGTH, 0);
    }
    memset(b + AT_ANNOUNCE + kept, 0, AT_CRC - AT_ANNOUNCE - kept);
    memcpy(b + AT_PUBLIC_KEY, entry.publicKey, KEY_SIZE);
    memcpy(b + AT_RANDOM, entry.randomHash, RANDOM_HASH_SIZE);
    b[0] = 0;
    b[1] = FORMAT;
    put16(b + AT_SLOT, static_cast<uint16_t>(target));
    put32(b + AT_SEQUENCE, ++sequence_);
    b[AT_FLAGS] = static_cast<uint8_t>((entry.hasPath ? FLAG_PATH : 0) | (entry.hasRatchet ? FLAG_RATCHET : 0) |
                                       (flag ? FLAG_CONTEXT : 0) | (entry.interface ? FLAG_INTERFACE : 0));
    b[AT_HOPS] = entry.hops;
    put32(b + AT_USED, entry.usedS);
    memcpy(b + AT_DESTINATION, entry.destination, TRUNCATED_HASH_SIZE);
    put32(b + AT_EXPIRES, entry.pathExpiresS);
    put32(b + AT_PATH_USED, entry.pathUsedS);
    put32(b + AT_RATCHET_TIME, entry.ratchetS);
    put32(b + AT_RATCHET_EMITTED, entry.ratchetEmittedS);
    memcpy(b + AT_NEXT_HOP, entry.nextHop, TRUNCATED_HASH_SIZE);
    memcpy(b + AT_RATCHET, entry.ratchet, RATCHET_SIZE);
    put32(b + AT_CRC, crc32(b + 1, AT_CRC - 1));
    memset(b + AT_CRC + 4, 0, TABLE_SLOT_SIZE - AT_CRC - 4);
    bufferSlot_ = 0;

    // Znacznik 0 przed treścią (gniazdo wolne mogło zostać zatwierdzone przez starszy zapis), potem treść
    // i znacznik zatwierdzenia; dopiero wtedy stare gniazdo jest unieważniane.
    const uint32_t at = offsetOf(static_cast<size_t>(target));
    const uint8_t committed = COMMITTED;
    writes_ += 2;
    if (!invalidate(static_cast<size_t>(target)) || !storage_->write(at + 1, b + 1, TABLE_SLOT_SIZE - 1) ||
        !storage_->write(at, &committed, 1)) {
        return -1;
    }
    if (slot >= 0) {
        invalidate(static_cast<size_t>(slot));
        drop(static_cast<size_t>(slot));
    }
    memcpy(index_[target].destination, entry.destination, TRUNCATED_HASH_SIZE);
    index_[target].usedS = entry.usedS;
    index_[target].pathUsedS = entry.pathUsedS;
    setBit(live_, static_cast<size_t>(target), true);
    setBit(path_, static_cast<size_t>(target), entry.hasPath);
    setBit(second_, static_cast<size_t>(target), entry.interface == 1);
    ++count_;
    return target;
}

void Table::touch(int slot, uint32_t nowS, bool path) {
    if (slot < 0 || static_cast<size_t>(slot) >= TABLE_SLOTS || !live(static_cast<size_t>(slot))) return;
    index_[slot].usedS = nowS;
    if (path) index_[slot].pathUsedS = nowS;
}

// RNS/Transport.py: jobs (przegląd path_table): tylko indeks, bez odczytu gniazd. Gniazdo poza indeksem,
// którego unieważnienie się nie udało, dostaje kolejną próbę (bez niej wróciłoby po restarcie).
void Table::expire(uint32_t nowS) {
    for (size_t slot = 0; slot < TABLE_SLOTS; ++slot) {
        if (hasPath(static_cast<int>(slot)) && nowS - index_[slot].pathUsedS > DESTINATION_TIMEOUT_S) setBit(path_, slot, false);
        if (storage_ && (stale_[slot / 8] & (1u << (slot % 8))) && !live(slot)) invalidate(slot);
    }
}

bool Table::hasPath(int slot) const {
    return slot >= 0 && static_cast<size_t>(slot) < TABLE_SLOTS && (path_[slot / 8] & (1u << (slot % 8)));
}

int Table::pathInterface(int slot) const {
    if (!hasPath(slot)) return -1;
    return (second_[slot / 8] & (1u << (slot % 8))) ? 1 : 0;
}

bool Table::routeMatches(size_t slot, uint8_t iface, uint8_t hops) const {
    if (pathInterface(static_cast<int>(slot)) != iface) return false;
    uint8_t stored = 0;
    return !hops || (storage_ && storage_->read(offsetOf(slot) + AT_HOPS, &stored, 1) && stored == hops);
}

size_t Table::routes(uint8_t iface, uint8_t hops, uint8_t (*out)[TRUNCATED_HASH_SIZE], size_t max) const {
    size_t n = 0;
    uint32_t below = UINT32_MAX;   // kolejne wybory: najnowsza trasa starsza od poprzedniej (równe czasy: wszystkie naraz)
    while (n < max) {
        uint32_t newest = 0;
        bool any = false;
        for (size_t slot = 0; slot < TABLE_SLOTS; ++slot) {
            const uint32_t used = index_[slot].pathUsedS;
            if (used < below && (!any || used > newest) && routeMatches(slot, iface, hops)) {
                newest = used;
                any = true;
            }
        }
        if (!any) break;
        for (size_t slot = 0; slot < TABLE_SLOTS && n < max; ++slot) {
            if (index_[slot].pathUsedS == newest && routeMatches(slot, iface, hops)) {
                memcpy(out[n++], index_[slot].destination, TRUNCATED_HASH_SIZE);
            }
        }
        if (newest == 0) break;
        below = newest;
    }
    return n;
}

size_t Table::paths() const {
    size_t n = 0;
    for (size_t slot = 0; slot < TABLE_SLOTS; ++slot) n += hasPath(static_cast<int>(slot));
    return n;
}

// Mniejszy limit działa od następnego nowego celu (wypieranie w write()).
void Table::setLimit(size_t limit) {
    if (limit >= 1 && limit <= KNOWN_MAX) limit_ = limit;
}

void Table::clear() {
    clean(index_, sizeof(index_));
    clean(buffer_, sizeof(buffer_));
    memset(live_, 0, sizeof(live_));
    memset(path_, 0, sizeof(path_));
    memset(second_, 0, sizeof(second_));
    memset(stale_, 0, sizeof(stale_));
    bufferSlot_ = 0;
    count_ = 0;
    sequence_ = 0;
}

}  // namespace rnscore
