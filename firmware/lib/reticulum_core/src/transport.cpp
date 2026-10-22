// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
#include "transport.h"

#include <string.h>

#include <Crypto.h>

#include "announce.h"
#include "proof.h"
#include "token.h"

namespace rnscore {

namespace {

uint32_t seconds(uint64_t ms) { return static_cast<uint32_t>(ms / 1000); }

// RNS/Transport.py: timebase_from_random_blob: ostatnie 5 B skrótu losowego, big-endian.
uint64_t emittedAt(const uint8_t randomHash[RANDOM_HASH_SIZE]) {
    uint64_t t = 0;
    for (size_t i = 5; i < RANDOM_HASH_SIZE; ++i) t = (t << 8) | randomHash[i];
    return t;
}

}  // namespace

void Transport::begin(const uint8_t privateKey[KEY_SIZE], const uint8_t publicKey[KEY_SIZE],
                      const uint8_t identityHash[TRUNCATED_HASH_SIZE], const uint8_t* address,
                      const uint8_t nameHash[NAME_HASH_SIZE], const TransportHooks& hooks) {
    privateKey_ = privateKey;
    publicKey_ = publicKey;
    identityHash_ = identityHash;
    address_ = address;
    nameHash_ = nameHash;
    hooks_ = hooks;
}

bool Transport::inbound(const uint8_t* raw, size_t length, uint64_t nowMs) {
    Packet packet;
    if (!unpack(raw, length, packet)) return false;

    // RNS/Transport.py: packet_filter. Pakiet w transporcie dla innego węzła, cele PLAIN i GROUP
    // (zapytania o trasę: R2) oraz łącza są poza podzbiorem R1 i nie trafiają na listę skrótów.
    if (packet.headerType == HEADER_2 && packet.packetType != ANNOUNCE &&
        memcmp(packet.transportId, identityHash_, TRUNCATED_HASH_SIZE) != 0) {
        ++counters_.ignored;
        return true;
    }
    if (packet.destinationType != SINGLE || packet.packetType == LINKREQUEST ||
        (packet.packetType == PROOF && packet.context == CONTEXT_LRPROOF)) {
        ++counters_.ignored;
        return true;
    }
    uint8_t hash[HASH_SIZE];
    packetHash(raw, length, hash);
    ++packet.hops;   // preprocess_inbound
    // Ogłoszenie SINGLE przechodzi także ze znanym skrótem (o trasie decydują skróty losowe); jego skrót
    // trafia na listę dopiero po weryfikacji podpisu (inboundAnnounce), jak w _inbound.
    if (packet.packetType == ANNOUNCE) {
        inboundAnnounce(packet, hash, nowMs);
        return true;
    }
    // _inbound: skrót zapamiętany przed przetworzeniem (jeden przegląd listy z filtrem duplikatów).
    if (!hashlist_.add(hash)) {
        ++counters_.duplicate;
        return true;
    }
    switch (packet.packetType) {
        case DATA:
            inboundData(packet, hash);
            break;
        case PROOF:
            inboundProof(packet);
            break;
        default:
            ++counters_.ignored;
            break;
    }
    return true;
}

// RNS/Identity.py: validate_announce i remember, _remember_ratchet; RNS/Transport.py: _inbound
// (ANNOUNCE): tablica tras i wywołanie announce handlers z filtrem aspektu. Tanie sprawdzenia przed
// weryfikacją podpisu (ten sam wynik co w Pythonie, inne liczniki): własny cel, kolizja klucza ze
// znanym wpisem i kopia ogłoszenia, które już przeszło weryfikację (tabela różnic).
void Transport::inboundAnnounce(const Packet& packet, const uint8_t hash[HASH_SIZE], uint64_t nowMs) {
    // Ogłoszenie własnego celu (np. odbite przez węzeł transportowy) nie trafia do tablicy.
    if (address_ && memcmp(packet.destinationHash, address_, TRUNCATED_HASH_SIZE) == 0) {
        ++counters_.ignored;
        return;
    }
    KnownDestination* e = findMutable(packet.destinationHash);
    // validate_announce: znany cel z innym kluczem publicznym (kolizja skrótu) odrzucony. Klucz to
    // pierwsze 64 B danych; krótsze dane odrzuci validateAnnounce.
    if (e && packet.dataLength >= KEY_SIZE && memcmp(e->publicKey, packet.data, KEY_SIZE) != 0) {
        ++counters_.invalid;
        return;
    }
    // Skrót na liście: te same bajty ogłoszenia przeszły już weryfikację, a przy tym samym skrócie
    // losowym should_add jest fałszywe. Bez trasy (wyparta albo wygasła) ogłoszenie idzie całą drogą.
    if (e && e->hasPath && hashlist_.contains(hash)) {
        e->usedS = seconds(nowMs);
        ++counters_.duplicate;
        return;
    }
    Announce a;
    if (!validateAnnounce(packet, a)) {
        ++counters_.invalid;
        return;
    }
    hashlist_.add(hash);
    if (!e) e = entry(packet.destinationHash);
    if (!e) {   // pełna tablica z samymi celami chronionymi
        ++counters_.ignored;
        return;
    }
    memcpy(e->publicKey, a.publicKey, KEY_SIZE);
    const uint64_t emitted = emittedAt(a.randomHash);
    // Ogłoszenie bez ratchetu zostawia zapamiętany (known_ratchets). Ratchet ze starszego ogłoszenia
    // (odtworzonego) nie zastępuje nowszego, choć Python go zastępuje (tabela różnic).
    const uint32_t emittedS = emitted > UINT32_MAX ? UINT32_MAX : static_cast<uint32_t>(emitted);
    if (a.ratchet && (!e->hasRatchet || emittedS >= e->ratchetEmittedS)) {
        memcpy(e->ratchet, a.ratchet, RATCHET_SIZE);
        e->hasRatchet = true;
        e->ratchetEmittedS = emittedS;
    }
    e->usedS = seconds(nowMs);

    // Transport._inbound: should_add. Z listy skrótów losowych wpis zna tylko ostatni (tabela różnic);
    // stan „trasa bez odpowiedzi” (path_is_unresponsive) jest w R2.
    const bool newBlob = memcmp(a.randomHash, e->randomHash, RANDOM_HASH_SIZE) != 0;
    bool add;
    if (!e->hasPath) {
        add = true;
    } else if (packet.hops <= e->hops) {
        add = newBlob && emitted > e->emitted;
    } else if (seconds(nowMs) >= e->pathExpiresS) {
        add = newBlob;
    } else {
        add = newBlob && emitted > e->emitted;
    }
    if (!add) return;
    e->hasPath = true;
    e->hops = packet.hops;
    memcpy(e->nextHop, packet.headerType == HEADER_2 ? packet.transportId : packet.destinationHash, TRUNCATED_HASH_SIZE);
    memcpy(e->randomHash, a.randomHash, RANDOM_HASH_SIZE);
    e->emitted = emitted;
    e->pathExpiresS = seconds(nowMs) + PATHFINDER_E_S;
    e->pathUsedS = seconds(nowMs);
    ++counters_.announces;
    // Filtr aspektu "wici.sa1": skrót celu z nazwy i tożsamości sprawdził validateAnnounce, więc wystarczy
    // skrót nazwy. Odpowiedzi na zapytania o trasę nie idą do warstwy aplikacji (receive_path_responses).
    if (hooks_.announce && packet.context != CONTEXT_PATH_RESPONSE && memcmp(a.nameHash, nameHash_, NAME_HASH_SIZE) == 0) {
        hooks_.announce(packet.destinationHash, a.appData, a.appDataLength, hooks_.context);
    }
}

// RNS/Transport.py: _inbound (DATA do celu lokalnego), RNS/Destination.py: receive i decrypt (bez
// własnych ratchetów), PROVE_APP; RNS/Identity.py: prove (dowód niejawny, should_use_implicit_proof).
void Transport::inboundData(const Packet& packet, const uint8_t hash[HASH_SIZE]) {
    if (!address_ || memcmp(packet.destinationHash, address_, TRUNCATED_HASH_SIZE) != 0) {
        ++counters_.ignored;
        return;
    }
    uint8_t plaintext[MTU];
    size_t plaintextLength = 0;
    if (!decrypt(privateKey_, publicKey_, packet.data, packet.dataLength, plaintext, sizeof(plaintext), &plaintextLength)) {
        ++counters_.invalid;
        return;
    }
    ++counters_.received;
    const bool prove = hooks_.packet && hooks_.packet(plaintext, plaintextLength, hooks_.context);
    clean(plaintext, sizeof(plaintext));
    if (!prove) {
        ++counters_.unproven;
        return;
    }
    uint8_t proof[PROOF_EXPLICIT_SIZE];
    Packet out = {};
    out.headerType = HEADER_1;
    out.transportType = BROADCAST;
    out.destinationType = SINGLE;   // RNS/Packet.py: ProofDestination
    out.packetType = PROOF;
    memcpy(out.destinationHash, hash, TRUNCATED_HASH_SIZE);
    out.data = proof;
    out.dataLength = rnscore::prove(privateKey_, publicKey_, hash, true, proof);
    uint8_t outRaw[MTU];
    const size_t outLength = pack(out, outRaw, sizeof(outRaw));
    if (outLength) emit(outRaw, outLength, true);
}

// RNS/Transport.py: _inbound (PROOF bez LRPROOF): dowód jawny tylko do potwierdzenia o tym skrócie,
// niejawny tylko do potwierdzenia o skrócie z celu dowodu; PacketReceipt.validate_proof.
void Transport::inboundProof(const Packet& packet) {
    const bool explicitProof = packet.dataLength == PROOF_EXPLICIT_SIZE;
    if (!explicitProof && packet.dataLength != PROOF_IMPLICIT_SIZE) {
        ++counters_.invalid;
        return;
    }
    // Python sprawdza dowód niejawny wobec każdego czekającego potwierdzenia, ale zawsze adresuje go do
    // skrótu skróconego pakietu (RNS/Packet.py: ProofDestination); tu najwyżej jedna weryfikacja na
    // dowód (tabela różnic).
    for (Receipt& r : receipts_) {
        if (!r.used) continue;
        if (explicitProof ? memcmp(r.hash, packet.data, HASH_SIZE) != 0
                          : memcmp(r.hash, packet.destinationHash, TRUNCATED_HASH_SIZE) != 0) {
            continue;
        }
        if (!validateProof(r.publicKey, r.hash, packet.data, packet.dataLength)) continue;
        r.used = false;
        ++counters_.delivered;
        if (hooks_.receipt) hooks_.receipt(r.handle, true, hooks_.context);
        return;
    }
    ++counters_.invalid;
}

bool Transport::emit(const uint8_t* raw, size_t length, bool rememberHash) {
    if (!hooks_.transmit || !hooks_.transmit(raw, length, hooks_.context)) return false;
    // Transport._outbound: skrót pakietu rozgłaszanego (bez znanej trasy) na listę skrótów.
    if (rememberHash) {
        uint8_t hash[HASH_SIZE];
        packetHash(raw, length, hash);
        hashlist_.add(hash);
    }
    return true;
}

bool Transport::announce(const uint8_t random[5], const uint8_t* appData, size_t length, uint64_t nowMs) {
    if (!address_) return false;
    uint8_t randomHash[RANDOM_HASH_SIZE];
    announceRandomHash(random, nowMs / 1000, randomHash);
    uint8_t data[ANNOUNCE_FORWARDABLE_SIZE];
    Packet packet = {};
    packet.headerType = HEADER_1;
    packet.transportType = BROADCAST;
    packet.destinationType = SINGLE;
    packet.packetType = ANNOUNCE;
    memcpy(packet.destinationHash, address_, TRUNCATED_HASH_SIZE);
    packet.dataLength = buildAnnounce(privateKey_, publicKey_, address_, nameHash_, randomHash, nullptr, appData, length, data,
                                      sizeof(data));
    packet.data = data;
    uint8_t raw[MTU];
    const size_t rawLength = packet.dataLength ? pack(packet, raw, sizeof(raw)) : 0;
    return rawLength && emit(raw, rawLength, true);
}

bool Transport::remember(const uint8_t destination[TRUNCATED_HASH_SIZE], const uint8_t publicKey[KEY_SIZE],
                         uint64_t nowMs) {
    KnownDestination* e = findMutable(destination);
    if (!e) e = entry(destination);
    if (!e) return false;
    memcpy(e->publicKey, publicKey, KEY_SIZE);
    e->usedS = seconds(nowMs);
    return true;
}

SendResult Transport::send(const uint8_t destination[TRUNCATED_HASH_SIZE], const uint8_t* data, size_t length,
                           const uint8_t ephemeralKey[KEY_SIZE / 2], const uint8_t iv[16], uint32_t handle, uint64_t timeoutMs,
                           uint64_t nowMs) {
    KnownDestination* e = findMutable(destination);
    if (!e) return SendResult::UNKNOWN;
    Receipt* receipt = nullptr;
    for (Receipt& r : receipts_) {
        if (!r.used) {
            receipt = &r;
            break;
        }
    }
    if (!receipt) return SendResult::RECEIPTS_FULL;
    // Transport._outbound: przy znanej trasie dłuższej niż 1 skok pakiet idzie do transportu (HEADER_2
    // z następnym skokiem); inaczej HEADER_1 rozgłaszany.
    const bool transported = e->hasPath && e->hops > 1;   // trasa wygasła: hasPath skasował poll()
    const size_t header = transported ? HEADER_2_SIZE : HEADER_1_SIZE;
    if (length > MTU || header + tokenSize(length) > MTU) return SendResult::TOO_LARGE;

    // RNS/Destination.py: encrypt: Identity.encrypt z ratchetem z ogłoszenia (Identity.get_ratchet).
    uint8_t token[MTU];
    if (!encrypt(e->publicKey, e->hasRatchet ? e->ratchet : nullptr, ephemeralKey, iv, data, length, token)) {
        return SendResult::REFUSED;
    }
    Packet packet = {};
    packet.headerType = transported ? HEADER_2 : HEADER_1;
    packet.transportType = transported ? TRANSPORT : BROADCAST;
    packet.destinationType = SINGLE;
    packet.packetType = DATA;
    if (transported) memcpy(packet.transportId, e->nextHop, TRUNCATED_HASH_SIZE);
    memcpy(packet.destinationHash, destination, TRUNCATED_HASH_SIZE);
    packet.data = token;
    packet.dataLength = tokenSize(length);
    uint8_t raw[MTU];
    const size_t rawLength = pack(packet, raw, sizeof(raw));
    if (!rawLength || !emit(raw, rawLength, !e->hasPath)) return SendResult::REFUSED;

    receipt->used = true;
    receipt->handle = handle;
    packetHash(raw, rawLength, receipt->hash);
    memcpy(receipt->publicKey, e->publicKey, KEY_SIZE);
    receipt->deadlineMs = nowMs + timeoutMs;
    e->usedS = seconds(nowMs);
    if (transported) e->pathUsedS = seconds(nowMs);   // _outbound: path_entry[IDX_PT_TIMESTAMP] przy HEADER_2
    ++counters_.sent;
    return SendResult::SENT;
}

void Transport::poll(uint64_t nowMs) {
    for (Receipt& r : receipts_) {
        if (!r.used || nowMs < r.deadlineMs) continue;
        r.used = false;
        ++counters_.timedOut;
        if (hooks_.receipt) hooks_.receipt(r.handle, false, hooks_.context);
    }
    // Transport.jobs: trasa nieużywana dłużej niż DESTINATION_TIMEOUT znika z path_table; wpis znanego
    // celu (tożsamość, ratchet) zostaje, jak known_destinations.
    const uint32_t nowS = seconds(nowMs);
    if (nowS == cullS_) return;
    cullS_ = nowS;
    for (size_t i = 0; i < limit_; ++i) {
        KnownDestination& k = known_[i];
        if (k.used && k.hasPath && nowS - k.pathUsedS > DESTINATION_TIMEOUT_S) k.hasPath = false;
    }
}

KnownDestination* Transport::findMutable(const uint8_t destination[TRUNCATED_HASH_SIZE]) {
    for (size_t i = 0; i < limit_; ++i) {
        if (known_[i].used && memcmp(known_[i].destination, destination, TRUNCATED_HASH_SIZE) == 0) return &known_[i];
    }
    return nullptr;
}

const KnownDestination* Transport::find(const uint8_t destination[TRUNCATED_HASH_SIZE]) const {
    return const_cast<Transport*>(this)->findMutable(destination);
}

// Nowy wpis: wolne miejsce albo wyparty najdawniej używany cel bez ochrony (specyfikacja, „Pojemności
// stosu”); nullptr, gdy wszystkie wpisy są chronione.
KnownDestination* Transport::entry(const uint8_t destination[TRUNCATED_HASH_SIZE]) {
    KnownDestination* slot = nullptr;
    for (size_t i = 0; i < limit_ && !slot; ++i) {
        if (!known_[i].used) slot = &known_[i];
    }
    if (!slot) {
        for (size_t i = 0; i < limit_; ++i) {
            KnownDestination& k = known_[i];
            if (hooks_.pinned && hooks_.pinned(k.destination, hooks_.context)) continue;
            if (!slot || k.usedS < slot->usedS) slot = &k;
        }
    }
    if (!slot) return nullptr;
    memset(slot, 0, sizeof(*slot));
    memcpy(slot->destination, destination, TRUNCATED_HASH_SIZE);
    slot->used = true;
    return slot;
}

uint8_t Transport::hopsTo(const uint8_t destination[TRUNCATED_HASH_SIZE]) const {
    const KnownDestination* e = find(destination);
    return e && e->hasPath ? e->hops : PATHFINDER_M;
}

size_t Transport::paths() const {
    size_t n = 0;
    for (size_t i = 0; i < limit_; ++i) n += known_[i].used && known_[i].hasPath;
    return n;
}

size_t Transport::receiptsPending() const {
    size_t n = 0;
    for (const Receipt& r : receipts_) n += r.used;
    return n;
}

void Transport::setLimit(size_t limit) {
    if (limit < 1 || limit > KNOWN_MAX) return;
    for (size_t i = limit; i < KNOWN_MAX; ++i) memset(&known_[i], 0, sizeof(known_[i]));
    limit_ = limit;
}

void Transport::clear() {
    clean(known_, sizeof(known_));
    clean(receipts_, sizeof(receipts_));
    hashlist_.clear();
    privateKey_ = publicKey_ = identityHash_ = address_ = nameHash_ = nullptr;
    hooks_ = TransportHooks();
}

}  // namespace rnscore
