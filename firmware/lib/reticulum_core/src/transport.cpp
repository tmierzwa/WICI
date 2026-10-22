// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
#include "transport.h"

#include <string.h>

#include <Crypto.h>

#include "announce.h"
#include "destination.h"
#include "hash.h"
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
                      const uint8_t nameHash[NAME_HASH_SIZE], const TransportHooks& hooks, TableStorage& storage,
                      uint64_t nowMs) {
    privateKey_ = privateKey;
    publicKey_ = publicKey;
    identityHash_ = identityHash;
    address_ = address;
    nameHash_ = nameHash;
    hooks_ = hooks;
    table_.begin(storage, seconds(nowMs));
    // RNS/Transport.py: start: cel PLAIN "rnstransport.path.request" (Destination bez tożsamości).
    destinationHash("rnstransport.path.request", nullptr, pathRequestDestination_);
}

bool Transport::pinnedHook(const uint8_t destination[TRUNCATED_HASH_SIZE], void* self) {
    const TransportHooks& h = static_cast<Transport*>(self)->hooks_;
    return h.pinned && h.pinned(destination, h.context);
}

bool Transport::inbound(const uint8_t* raw, size_t length, uint64_t nowMs) {
    Packet packet;
    if (!unpack(raw, length, packet)) return false;

    // RNS/Transport.py: packet_filter. Pakiet w transporcie dla innego węzła oraz łącza (poza podzbiorem
    // rdzenia) nie trafiają na listę skrótów.
    if (packet.headerType == HEADER_2 && packet.packetType != ANNOUNCE &&
        memcmp(packet.transportId, identityHash_, TRUNCATED_HASH_SIZE) != 0) {
        ++counters_.ignored;
        return true;
    }
    // packet_filter: ogłoszenie celu PLAIN albo GROUP odpada, a ich pakiety tylko do 1 skoku (bez listy
    // skrótów: duplikaty zapytań o trasę odrzuca znacznik). GROUP i łącza są poza podzbiorem.
    if ((packet.destinationType == PLAIN || packet.destinationType == GROUP) && packet.packetType == ANNOUNCE) {
        ++counters_.invalid;
        return true;
    }
    if (packet.destinationType == PLAIN && packet.hops <= 1) {
        ++packet.hops;
        inboundPlain(packet, raw, length, nowMs);
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
    // _inbound: pakiet w transporcie ze stacją jako następnym skokiem (pakiety dla innych węzłów odpadły
    // wyżej, jak w packet_filter).
    if (packet.headerType == HEADER_2 && forward(packet, raw, length, hash, nowMs)) return true;
    switch (packet.packetType) {
        case DATA:
            inboundData(packet, hash);
            break;
        case PROOF:
            inboundProof(packet, raw, length, nowMs);
            break;
        default:
            ++counters_.ignored;
            break;
    }
    return true;
}

// RNS/Identity.py: validate_announce i remember, _remember_ratchet; RNS/Transport.py: _inbound
// (ANNOUNCE): tablica tras i wywołanie announce handlers z filtrem aspektu. Tanie sprawdzenia przed
// weryfikacją podpisu (ten sam wynik co w Pythonie, inne liczniki): własny cel, kopia ogłoszenia, które
// już przeszło weryfikację (sam indeks, bez odczytu FRAM), i kolizja klucza ze znanym wpisem (samo pole
// klucza 64 B z FRAM). Dopiero potem hak mayVerify (limit weryfikacji stacji), żeby tanio odrzucane
// ogłoszenia nie zużywały limitu; pełny odczyt wpisu z CRC po weryfikacji.
void Transport::inboundAnnounce(const Packet& packet, const uint8_t hash[HASH_SIZE], uint64_t nowMs) {
    // Ogłoszenie własnego celu (np. odbite przez węzeł transportowy) nie trafia do tablicy.
    if (address_ && memcmp(packet.destinationHash, address_, TRUNCATED_HASH_SIZE) == 0) {
        ++counters_.ignored;
        return;
    }
    const uint32_t now = seconds(nowMs);
    const int slot = table_.find(packet.destinationHash);
    // Skrót na liście: te same bajty ogłoszenia przeszły już weryfikację, a przy tym samym skrócie
    // losowym should_add jest fałszywe. Bez trasy (wyparta albo wygasła) ogłoszenie idzie całą drogą.
    if (table_.hasPath(slot) && hashlist_.contains(hash)) {
        if (packet.headerType == HEADER_2) heardRebroadcast(packet, nowMs);
        table_.touch(slot, now, false);
        ++counters_.duplicate;
        return;
    }
    KnownDestination e;
    bool known = false;
    // validate_announce: znany cel z innym kluczem publicznym (kolizja skrótu) odrzucony. Klucz to
    // pierwsze 64 B danych; krótsze dane odrzuci validateAnnounce. Inny klucz w polu gniazda potwierdza
    // pełny odczyt z CRC, więc uszkodzone pole nie blokuje celu (wpis z błędem CRC wypada).
    uint8_t key[KEY_SIZE];
    if (slot >= 0 && packet.dataLength >= KEY_SIZE && table_.readKey(slot, key) && memcmp(key, packet.data, KEY_SIZE) != 0) {
        known = table_.read(slot, e, now);
        if (known && memcmp(e.publicKey, packet.data, KEY_SIZE) != 0) {
            ++counters_.invalid;
            return;
        }
    }
    if (hooks_.mayVerify && !hooks_.mayVerify(hooks_.context)) return;   // licznik po stronie stacji
    Announce a;
    if (!validateAnnounce(packet, a)) {
        ++counters_.invalid;
        return;
    }
    if (!known && slot >= 0) {
        known = table_.read(slot, e, now);
        // Błąd odczytu (wpis został w indeksie): ogłoszenie odpada bez skrótu na liście, więc jego
        // powtórka przejdzie; nowy wpis obok starego zdublowałby cel.
        if (!known && table_.find(packet.destinationHash) == slot) {
            ++counters_.tableFailed;
            return;
        }
        if (known && memcmp(e.publicKey, a.publicKey, KEY_SIZE) != 0) {   // pole klucza zmieniło się po readKey
            ++counters_.invalid;
            return;
        }
    }
    hashlist_.add(hash);
    if (packet.headerType == HEADER_2) heardRebroadcast(packet, nowMs);
    if (!known) {
        memset(&e, 0, sizeof(e));
        memcpy(e.destination, packet.destinationHash, TRUNCATED_HASH_SIZE);
        memcpy(e.publicKey, a.publicKey, KEY_SIZE);
    }
    bool changed = !known;
    // _remember_ratchet: ogłoszenie bez ratchetu zostawia zapamiętany; ten sam ratchet bez zmiany (czas
    // emisji pierwszego ogłoszenia z nim wystarcza, bo nadawca nie wraca do starego ratchetu). Ratchet ze
    // starszego ogłoszenia (odtworzonego) nie zastępuje nowszego, choć Python go zastępuje (tabela różnic).
    const uint64_t emitted = emittedAt(a.randomHash);
    const uint32_t emittedS = emitted > UINT32_MAX ? UINT32_MAX : static_cast<uint32_t>(emitted);
    if (a.ratchet && (!e.hasRatchet || (emittedS >= e.ratchetEmittedS && memcmp(e.ratchet, a.ratchet, RATCHET_SIZE) != 0))) {
        memcpy(e.ratchet, a.ratchet, RATCHET_SIZE);
        e.hasRatchet = true;
        e.ratchetS = now;
        e.ratchetEmittedS = emittedS;
        changed = true;
    }
    e.usedS = now;

    // Transport._inbound: should_add. Z listy skrótów losowych wpis zna tylko ostatni (tabela różnic);
    // stan „trasa bez odpowiedzi” (path_is_unresponsive) nie występuje bez łączy.
    const bool newBlob = memcmp(a.randomHash, e.randomHash, RANDOM_HASH_SIZE) != 0;
    bool add;
    if (!e.hasPath) {
        add = true;
    } else if (packet.hops <= e.hops) {
        add = newBlob && emitted > emittedAt(e.randomHash);
    } else if (now >= e.pathExpiresS) {
        add = newBlob;
    } else {
        add = newBlob && emitted > emittedAt(e.randomHash);
    }
    if (add) {
        e.hasPath = true;
        e.hops = packet.hops;
        memcpy(e.nextHop, packet.headerType == HEADER_2 ? packet.transportId : packet.destinationHash, TRUNCATED_HASH_SIZE);
        memcpy(e.randomHash, a.randomHash, RANDOM_HASH_SIZE);
        e.pathExpiresS = now + PATHFINDER_E_S;
        e.pathUsedS = now;
        // Transport.cache: ogłoszenie trasy w pamięci podręcznej (do odpowiedzi na zapytania o trasę);
        // dane dłuższe niż ANNOUNCE_FORWARDABLE_SIZE nie przechodzą przez Packet.pack z HEADER_2.
        e.contextFlag = packet.contextFlag;
        changed = true;
    }
    // Zapis tylko przy zmianie wpisu (nowy cel, ratchet, trasa): powtórzone ogłoszenie nie zapisuje FRAM.
    if (changed) {
        const bool cache = add && packet.dataLength <= ANNOUNCE_FORWARDABLE_SIZE;
        // Nowa trasa: nowe ogłoszenie (długość 0: bez ogłoszenia); bez nowej trasy zostaje dotychczasowe.
        const Table::Cached cached = add ? Table::Cached::SET : Table::Cached::KEEP;
        if (table_.write(known ? slot : -1, e, cached, packet.data, cache ? packet.dataLength : 0, pinnedHook, this) < 0) {
            ++counters_.tableFailed;
            return;
        }
    } else {
        table_.touch(slot, now, false);
    }
    if (!add) return;
    ++counters_.announces;
    discoveryResponse(packet, nowMs);
    // _inbound: przyjęte ogłoszenie (poza odpowiedzią na zapytanie o trasę) do tablicy ogłoszeń bez
    // ponowień, z losową zwłoką do PATHFINDER_RW (RNS.rand()).
    if (packet.context != CONTEXT_PATH_RESPONSE) {
        uint8_t r[2] = {0, 0};
        if (hooks_.random) hooks_.random(r, sizeof(r), hooks_.context);
        const uint32_t delayMs = ((static_cast<uint32_t>(r[0]) << 8 | r[1]) * PATHFINDER_RW_MS) >> 16;
        schedule(packet.destinationHash, packet.hops, nowMs + delayMs, 0, false);
    }
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

// RNS/Transport.py: _inbound (PROOF bez LRPROOF): najpierw przekazanie według tablicy odwrotnej, potem
// dowód jawny tylko do potwierdzenia o tym skrócie, niejawny tylko do potwierdzenia o skrócie z celu
// dowodu; PacketReceipt.validate_proof.
void Transport::inboundProof(const Packet& packet, const uint8_t* raw, size_t length, uint64_t nowMs) {
    const bool forwarded = forwardProof(packet, raw, length, nowMs);
    const bool explicitProof = packet.dataLength == PROOF_EXPLICIT_SIZE;
    if (!explicitProof && packet.dataLength != PROOF_IMPLICIT_SIZE) {
        if (!forwarded) ++counters_.invalid;
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
    if (!forwarded) ++counters_.invalid;
}

// RNS/Transport.py: _inbound (pakiet w transporcie, stacja jako następny skok): według path_table nowy
// następny skok (do celu zostało więcej niż 1 skok) albo nagłówek HEADER_1 rozgłaszany (ostatni skok;
// jak w Pythonie bez flagi kontekstu), wpis tablicy odwrotnej dla dowodu i odświeżony czas trasy. Trasa
// w tablicy ma co najmniej 1 skok (skoki ogłoszenia po odbiorze), więc gałąź „0 skoków” klientów
// lokalnych nie występuje. Fałsz: brak trasy (Python porzuca pakiet; cel stacji idzie dalej do odbioru).
bool Transport::forward(const Packet& packet, const uint8_t* raw, size_t length, const uint8_t hash[HASH_SIZE],
                        uint64_t nowMs) {
    const int slot = table_.find(packet.destinationHash);
    KnownDestination e;
    if (slot < 0 || !table_.read(slot, e, seconds(nowMs)) || !e.hasPath || length > MTU || length < HEADER_2_SIZE) {
        if (!address_ || memcmp(packet.destinationHash, address_, TRUNCATED_HASH_SIZE) != 0) ++counters_.noPath;
        return false;
    }
    uint8_t out[MTU];
    const size_t tail = length - (2 + TRUNCATED_HASH_SIZE);   // od celu do końca pakietu
    size_t outLength;
    if (e.hops > 1) {
        out[0] = raw[0];
        memcpy(out + 2, e.nextHop, TRUNCATED_HASH_SIZE);
        memcpy(out + 2 + TRUNCATED_HASH_SIZE, raw + 2 + TRUNCATED_HASH_SIZE, tail);
        outLength = length;
    } else {
        out[0] = static_cast<uint8_t>(HEADER_1 << 6 | BROADCAST << 4 | (raw[0] & 0x0F));
        memcpy(out + 2, raw + 2 + TRUNCATED_HASH_SIZE, tail);
        outLength = 2 + tail;
    }
    out[1] = packet.hops;
    // reverse_table[truncated_packet_hash]: tego samego skrótu wpis nadpisany, inaczej wolny albo
    // przeterminowany, a przy pełnej tablicy najstarszy (licznik).
    ReverseEntry* r = nullptr;
    ReverseEntry* oldest = &reverse_[0];   // wolny, przeterminowany albo najstarszy
    for (ReverseEntry& x : reverse_) {
        if (x.atMs && memcmp(x.hash, hash, TRUNCATED_HASH_SIZE) == 0) {
            r = &x;
            break;
        }
        if (!oldest->atMs || nowMs - oldest->atMs > REVERSE_TIMEOUT_MS) continue;
        if (!x.atMs || nowMs - x.atMs > REVERSE_TIMEOUT_MS || x.atMs < oldest->atMs) oldest = &x;
    }
    if (!r) {
        r = oldest;
        if (r->atMs && nowMs - r->atMs <= REVERSE_TIMEOUT_MS) ++counters_.reverseFull;
    }
    memcpy(r->hash, hash, TRUNCATED_HASH_SIZE);
    r->atMs = nowMs ? nowMs : 1;
    if (hooks_.transmit && hooks_.transmit(out, outLength, hooks_.context)) ++counters_.forwarded;
    table_.touch(slot, seconds(nowMs), true);   // path_entry[IDX_PT_TIMESTAMP]
    return true;
}

// RNS/Transport.py: _inbound (PROOF): dowód do skrótu pakietu przekazanego przez stację wraca tą samą
// drogą (wpis tablicy odwrotnej zużyty), z liczbą skoków po odbiorze.
bool Transport::forwardProof(const Packet& packet, const uint8_t* raw, size_t length, uint64_t nowMs) {
    if (length > MTU) return false;
    for (ReverseEntry& r : reverse_) {
        if (!r.atMs || memcmp(r.hash, packet.destinationHash, TRUNCATED_HASH_SIZE) != 0) continue;
        const bool live = nowMs - r.atMs <= REVERSE_TIMEOUT_MS;
        r.atMs = 0;
        if (!live) return false;   // Transport.jobs usunąłby wpis po REVERSE_TIMEOUT
        uint8_t out[MTU];
        memcpy(out, raw, length);
        out[1] = packet.hops;
        if (hooks_.transmit && hooks_.transmit(out, length, hooks_.context)) ++counters_.proofsForwarded;
        return true;
    }
    return false;
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
    if (!address_ || length > OWN_APP_DATA_MAX) return false;
    if (length) memcpy(ownAppData_, appData, length);
    ownAppDataLength_ = length;
    return ownAnnounce(random, nowMs, false);
}

// RNS/Destination.py: Destination.announce bez ratchetu, z danymi aplikacji z ostatniego announce();
// pathResponse: kontekst PATH_RESPONSE (odpowiedź na zapytanie o trasę, Transport.path_request).
bool Transport::ownAnnounce(const uint8_t random[5], uint64_t nowMs, bool pathResponse) {
    uint8_t randomHash[RANDOM_HASH_SIZE];
    announceRandomHash(random, nowMs / 1000, randomHash);
    Packet packet = {};
    packet.headerType = HEADER_1;
    packet.transportType = BROADCAST;
    packet.destinationType = SINGLE;
    packet.packetType = ANNOUNCE;
    packet.context = pathResponse ? CONTEXT_PATH_RESPONSE : 0;
    memcpy(packet.destinationHash, address_, TRUNCATED_HASH_SIZE);
    ownAnnounceLength_ = buildAnnounce(privateKey_, publicKey_, address_, nameHash_, randomHash, nullptr, ownAppData_,
                                       ownAppDataLength_, ownAnnounce_, sizeof(ownAnnounce_));
    ownAnnounceMs_ = nowMs;
    return sendOwnAnnounce(pathResponse);
}

// Pakiet z danych ostatniego ogłoszenia własnego (kontekst nie jest podpisany, więc te same dane służą
// zwykłemu ogłoszeniu i odpowiedzi na zapytanie o trasę).
bool Transport::sendOwnAnnounce(bool pathResponse) {
    Packet packet = {};
    packet.headerType = HEADER_1;
    packet.transportType = BROADCAST;
    packet.destinationType = SINGLE;
    packet.packetType = ANNOUNCE;
    packet.context = pathResponse ? CONTEXT_PATH_RESPONSE : 0;
    memcpy(packet.destinationHash, address_, TRUNCATED_HASH_SIZE);
    packet.data = ownAnnounce_;
    packet.dataLength = ownAnnounceLength_;
    uint8_t raw[MTU];
    const size_t rawLength = packet.dataLength ? pack(packet, raw, sizeof(raw)) : 0;
    return rawLength && emit(raw, rawLength, true);
}

bool Transport::remember(const uint8_t destination[TRUNCATED_HASH_SIZE], const uint8_t publicKey[KEY_SIZE],
                         uint64_t nowMs) {
    const uint32_t now = seconds(nowMs);
    int slot = table_.find(destination);
    KnownDestination e;
    if (slot >= 0 && table_.read(slot, e, now)) {
        if (memcmp(e.publicKey, publicKey, KEY_SIZE) == 0) {
            table_.touch(slot, now, false);
            return true;
        }
    } else if (slot >= 0 && table_.find(destination) == slot) {   // błąd odczytu: wpis zostaje do ponowienia
        ++counters_.tableFailed;
        return false;
    }
    // Nowy cel; znany z innym kluczem (kolizja skrótu albo uszkodzone gniazdo) zastąpiony w całości.
    memset(&e, 0, sizeof(e));
    memcpy(e.destination, destination, TRUNCATED_HASH_SIZE);
    memcpy(e.publicKey, publicKey, KEY_SIZE);
    e.usedS = now;
    slot = table_.find(destination);
    if (table_.write(slot, e, Table::Cached::SET, nullptr, 0, pinnedHook, this) >= 0) return true;
    ++counters_.tableFailed;
    return false;
}

SendResult Transport::send(const uint8_t destination[TRUNCATED_HASH_SIZE], const uint8_t* data, size_t length,
                           const uint8_t ephemeralKey[KEY_SIZE / 2], const uint8_t iv[16], uint32_t handle, uint64_t timeoutMs,
                           uint64_t nowMs) {
    const int slot = table_.find(destination);
    KnownDestination e;
    if (slot < 0 || !table_.read(slot, e, seconds(nowMs))) return SendResult::UNKNOWN;
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
    const bool transported = e.hasPath && e.hops > 1;   // trasa wygasła: hasPath skasował read()
    const size_t header = transported ? HEADER_2_SIZE : HEADER_1_SIZE;
    if (length > MTU || header + tokenSize(length) > MTU) return SendResult::TOO_LARGE;

    // RNS/Destination.py: encrypt: Identity.encrypt z ratchetem z ogłoszenia (Identity.get_ratchet).
    uint8_t token[MTU];
    if (!encrypt(e.publicKey, e.hasRatchet ? e.ratchet : nullptr, ephemeralKey, iv, data, length, token,
                 sizeof(token))) {
        return SendResult::REFUSED;
    }
    Packet packet = {};
    packet.headerType = transported ? HEADER_2 : HEADER_1;
    packet.transportType = transported ? TRANSPORT : BROADCAST;
    packet.destinationType = SINGLE;
    packet.packetType = DATA;
    if (transported) memcpy(packet.transportId, e.nextHop, TRUNCATED_HASH_SIZE);
    memcpy(packet.destinationHash, destination, TRUNCATED_HASH_SIZE);
    packet.data = token;
    packet.dataLength = tokenSize(length);
    uint8_t raw[MTU];
    const size_t rawLength = pack(packet, raw, sizeof(raw));
    if (!rawLength || !emit(raw, rawLength, !e.hasPath)) return SendResult::REFUSED;

    receipt->used = true;
    receipt->handle = handle;
    packetHash(raw, rawLength, receipt->hash);
    memcpy(receipt->publicKey, e.publicKey, KEY_SIZE);
    receipt->deadlineMs = nowMs + timeoutMs;
    // _outbound: path_entry[IDX_PT_TIMESTAMP] odświeżany przy HEADER_2.
    table_.touch(slot, seconds(nowMs), transported);
    ++counters_.sent;
    return SendResult::SENT;
}

// RNS/Transport.py: preprocess_inbound (zapytanie o trasę: znacznik), _inbound (DATA do celu lokalnego
// PLAIN) i path_request_handler. Inne cele PLAIN nie są celami stacji. Znacznik i zapytanie „w drodze”
// tylko dla zapytania PLAIN DATA; Python rejestruje je dla każdego pakietu do tego celu (tabela różnic).
void Transport::inboundPlain(const Packet& packet, const uint8_t* raw, size_t length, uint64_t nowMs) {
    if (packet.packetType != DATA || memcmp(packet.destinationHash, pathRequestDestination_, TRUNCATED_HASH_SIZE) != 0 ||
        packet.dataLength < TRUNCATED_HASH_SIZE) {
        ++counters_.ignored;
        return;
    }
    // Dane: cel, identyfikator transportu pytającego (gdy jest też znacznik), znacznik do 16 B.
    const uint8_t* requestor = nullptr;
    const uint8_t* tag = nullptr;
    size_t tagLength = 0;
    if (packet.dataLength > 2 * TRUNCATED_HASH_SIZE) {
        requestor = packet.data + TRUNCATED_HASH_SIZE;
        tag = packet.data + 2 * TRUNCATED_HASH_SIZE;
        tagLength = packet.dataLength - 2 * TRUNCATED_HASH_SIZE;
    } else if (packet.dataLength > TRUNCATED_HASH_SIZE) {
        tag = packet.data + TRUNCATED_HASH_SIZE;
        tagLength = packet.dataLength - TRUNCATED_HASH_SIZE;
    }
    if (!tag) {   // zapytanie bez znacznika: odrzucone
        ++counters_.invalid;
        return;
    }
    if (tagLength > TRUNCATED_HASH_SIZE) tagLength = TRUNCATED_HASH_SIZE;
    // discovery_pr_tags: ten sam cel ze znacznikiem już był. Tu 8 B skrótu celu i znacznika w pierścieniu.
    uint8_t unique[2 * TRUNCATED_HASH_SIZE];
    memcpy(unique, packet.data, TRUNCATED_HASH_SIZE);
    memcpy(unique + TRUNCATED_HASH_SIZE, tag, tagLength);
    uint8_t digest[HASH_SIZE];
    fullHash(unique, TRUNCATED_HASH_SIZE + tagLength, digest);
    uint64_t key = 0;
    for (size_t i = 0; i < 8; ++i) key = (key << 8) | digest[i];
    if (!key) key = 1;
    for (uint64_t k : pathTags_) {
        if (k == key) {
            ++counters_.duplicate;
            return;
        }
    }
    pathTags_[pathTagNext_] = key;
    pathTagNext_ = (pathTagNext_ + 1) % PATH_TAGS_MAX;
    // preprocess_inbound: zapytanie o cel, o który poprzednie zapytanie jest jeszcze „w drodze”
    // (bez odpowiedzi), zostaje bez odpowiedzi i czeka na ogłoszenie celu (discovery_path_requests).
    Inflight* f = findInflight(packet.data, nowMs);
    if (f && f->atMs) {
        if (!f->discoveryUntilMs) f->discoveryUntilMs = nowMs + (discoveryTimeoutMs_ ? discoveryTimeoutMs_ : PATH_REQUEST_TIMEOUT_MS);
        ++counters_.pathGated;
        return;
    }
    if (!f) {
        // Wolny albo przeterminowany wpis, inaczej najstarszy żywy bez oczekiwania; wpisy czekające na
        // odkrycie (i z odpowiedzią do nadania) wypierane na końcu, bo czekają na nie pytający.
        auto rank = [](const Inflight& x) { return x.respond ? 3 : x.discoveryUntilMs ? 2 : x.atMs ? 1 : 0; };
        auto age = [](const Inflight& x) { return x.discoveryUntilMs ? x.discoveryUntilMs : x.atMs; };
        f = &inflight_[0];
        for (Inflight& x : inflight_) {
            if (rank(x) < rank(*f) || (rank(x) == rank(*f) && age(x) < age(*f))) f = &x;
        }
        memset(f, 0, sizeof(*f));
        memcpy(f->destination, packet.data, TRUNCATED_HASH_SIZE);
    }
    f->atMs = nowMs ? nowMs : 1;
    uint8_t hash[HASH_SIZE];
    packetHash(raw, length, hash);
    hashlist_.add(hash);
    ++counters_.pathRequests;
    if (pathRequest(packet.data, requestor, nowMs)) f->atMs = 0;   // path_request: answered
}

// Wpis zapytania o cel z żywym zapytaniem „w drodze” albo oczekiwaniem odkrycia; przeterminowane
// części wpisu skasowane (Transport.jobs).
Transport::Inflight* Transport::findInflight(const uint8_t destination[TRUNCATED_HASH_SIZE], uint64_t nowMs) {
    for (Inflight& f : inflight_) {
        if (f.atMs && nowMs - f.atMs > PATH_REQUEST_GATE_MS) f.atMs = 0;
        if (f.discoveryUntilMs && nowMs > f.discoveryUntilMs) f.discoveryUntilMs = 0;
    }
    for (Inflight& f : inflight_) {
        if ((f.atMs || f.discoveryUntilMs) && memcmp(f.destination, destination, TRUNCATED_HASH_SIZE) == 0) return &f;
    }
    return nullptr;
}

// RNS/Transport.py: _inbound (ANNOUNCE przyjęte do trasy): cel, na który czeka zapytanie
// (discovery_path_requests), dostaje od razu odpowiedź HEADER_2 z tym ogłoszeniem; zapytanie „w drodze”
// o ten cel się kończy.
void Transport::discoveryResponse(const Packet& packet, uint64_t nowMs) {
    Inflight* f = findInflight(packet.destinationHash, nowMs);
    if (!f) return;
    const bool waiting = f->discoveryUntilMs != 0;
    f->atMs = f->discoveryUntilMs = 0;
    // Odpowiedź wychodzi w następnym poll(): w tym obiegu pętli była już weryfikacja podpisu ogłoszenia,
    // a odpowiedź to podpis IFAC (jedna operacja asymetryczna na obieg). Python nadaje ją od razu.
    if (!waiting || packet.dataLength > ANNOUNCE_FORWARDABLE_SIZE) return;
    f->respond = true;
    f->respondHops = packet.hops;
}

// RNS/Transport.py: _inbound (ANNOUNCE celu z discovery_path_requests): ogłoszenie z pamięci podręcznej jako
// HEADER_2 z identyfikatorem stacji, kontekstem PATH_RESPONSE i liczbą skoków po odbiorze.
void Transport::sendDiscovery(Inflight& f, uint64_t nowMs) {
    f.respond = false;
    KnownDestination e;
    if (!lookup(f.destination, e, nowMs) || !e.announceLength) return;   // wpis wyparty w międzyczasie
    Packet out = {};
    out.headerType = HEADER_2;
    out.transportType = TRANSPORT;
    out.destinationType = SINGLE;
    out.packetType = ANNOUNCE;
    out.contextFlag = e.contextFlag;
    out.hops = f.respondHops;
    out.context = CONTEXT_PATH_RESPONSE;
    memcpy(out.transportId, identityHash_, TRUNCATED_HASH_SIZE);
    memcpy(out.destinationHash, f.destination, TRUNCATED_HASH_SIZE);
    out.data = table_.announce();
    out.dataLength = e.announceLength;
    uint8_t raw[MTU];
    const size_t rawLength = pack(out, raw, sizeof(raw));
    if (rawLength && emit(raw, rawLength, true)) ++counters_.pathResponses;
}

void Transport::setBitrate(uint32_t bitsPerSecond) {
    // medium_path_timeout: dwa przebiegi MTU przy najwolniejszym interfejsie i DEFAULT_PER_HOP_TIMEOUT (6 s).
    const uint32_t bps = bitsPerSecond < 5 ? 5 : bitsPerSecond;   // Reticulum.MINIMUM_BITRATE
    const uint64_t medium = bitsPerSecond ? 2ULL * MTU * 8 * 1000 / bps + 6000 : 0;
    discoveryTimeoutMs_ = static_cast<uint32_t>(medium > PATH_REQUEST_TIMEOUT_MS ? medium : PATH_REQUEST_TIMEOUT_MS);
}

// RNS/Transport.py: path_request (węzeł z transportem, bez klientów lokalnych i bez szukania celów
// nieznanych, które dotyczy tylko trybów interfejsu innych niż pełny). Prawda: zapytanie obsłużone
// (answered: cel stacji albo cel z trasą, także bez nadania).
bool Transport::pathRequest(const uint8_t destination[TRUNCATED_HASH_SIZE], const uint8_t* requestor, uint64_t nowMs) {
    if (address_ && memcmp(destination, address_, TRUNCATED_HASH_SIZE) == 0) {
        // Cel stacji: Destination.announce(path_response=True) od razu, z nowym skrótem losowym i podpisem;
        // najwyżej raz na OWN_RESPONSE_MIN_MS (odstępstwo, tabela różnic).
        ++counters_.pathAnswered;
        if (ownResponseMs_ && nowMs + 1 - ownResponseMs_ < OWN_RESPONSE_MIN_MS) {
            ++counters_.pathLimited;
            return true;
        }
        // Bez miejsca w interfejsie (cisza, pełna kolejka, brak IFAC) bez pracy na podpis.
        if (!mayTransmit()) {
            ++counters_.pathLimited;
            return true;
        }
        ownResponseMs_ = nowMs + 1;
        // Ogłoszenie podpisane w ostatnich OWN_RESPONSE_REUSE_MS idzie jeszcze raz (jego skrót losowy jest
        // dla pytającego nowy, jeśli go nie słyszał), bez nowego podpisu.
        if (ownAnnounceLength_ && nowMs - ownAnnounceMs_ < OWN_RESPONSE_REUSE_MS) {
            if (sendOwnAnnounce(true)) ++counters_.pathResponses;
            return true;
        }
        uint8_t random[5];
        if (!hooks_.random || !hooks_.random(random, sizeof(random), hooks_.context)) return true;
        if (ownAnnounce(random, nowMs, true)) ++counters_.pathResponses;
        return true;
    }
    KnownDestination e;
    if (!lookup(destination, e, nowMs) || !e.hasPath) return false;   // trasa nieznana: bez odpowiedzi
    ++counters_.pathAnswered;
    if (!e.announceLength) return true;               // get_cached_packet: brak ogłoszenia w pamięci
    if (requestor && memcmp(requestor, e.nextHop, TRUNCATED_HASH_SIZE) == 0) return true;   // następny skok pyta
    // held_announces: retransmisja ogłoszenia tego celu czekająca w tablicy wraca po wysłaniu odpowiedzi
    // (retransmit); przy pełnym miejscu na wstrzymane przepada (licznik).
    if (AnnounceEntry* pending = findAnnounce(destination)) {
        AnnounceEntry* held = nullptr;
        for (AnnounceEntry& h : held_) {
            if (h.used && memcmp(h.destination, destination, TRUNCATED_HASH_SIZE) == 0) {
                held = &h;
                break;
            }
            if (!h.used && !held) held = &h;
        }
        if (held) *held = *pending;
        else ++counters_.announceTableFull;
    }
    // announce_table: odpowiedź po PATH_REQUEST_GRACE z liczbą skoków trasy (PATHFINDER_R: jedno nadanie).
    schedule(destination, e.hops, nowMs + PATH_REQUEST_GRACE_MS, PATHFINDER_R, true);
    return true;
}

// Wpis tablicy ogłoszeń: wpis tego celu zastąpiony (jak słownik w Pythonie); przy pełnej tablicy nowy
// odpada z licznikiem.
Transport::AnnounceEntry* Transport::findAnnounce(const uint8_t destination[TRUNCATED_HASH_SIZE]) {
    for (AnnounceEntry& a : announces_) {
        if (a.used && memcmp(a.destination, destination, TRUNCATED_HASH_SIZE) == 0) return &a;
    }
    return nullptr;
}

bool Transport::schedule(const uint8_t destination[TRUNCATED_HASH_SIZE], uint8_t hops, uint64_t atMs, uint8_t retries,
                         bool block) {
    AnnounceEntry* slot = findAnnounce(destination);
    for (AnnounceEntry& a : announces_) {
        if (slot) break;
        if (!a.used) slot = &a;
    }
    if (!slot) {
        ++counters_.announceTableFull;
        return false;
    }
    slot->used = true;
    memcpy(slot->destination, destination, TRUNCATED_HASH_SIZE);
    slot->hops = hops;
    slot->retransmitMs = atMs;
    slot->retries = retries;
    slot->localRebroadcasts = 0;
    slot->blockRebroadcasts = block;
    return true;
}

// RNS/Transport.py: jobs (announce_table): ogłoszenie z pamięci podręcznej jako nowy pakiet HEADER_2
// z identyfikatorem transportu stacji i liczbą skoków z wpisu.
void Transport::retransmit(AnnounceEntry& entry, uint64_t nowMs) {
    entry.retransmitMs = nowMs + PATHFINDER_G_MS + PATHFINDER_RW_MS;
    ++entry.retries;
    KnownDestination e;
    if (!lookup(entry.destination, e, nowMs) || !e.announceLength) {   // wpis wyparty w międzyczasie
        entry.used = false;
        for (AnnounceEntry& h : held_) {   // wstrzymana retransmisja tego celu też nie ma czego nadać
            if (h.used && memcmp(h.destination, entry.destination, TRUNCATED_HASH_SIZE) == 0) h.used = false;
        }
        return;
    }
    Packet packet = {};
    packet.headerType = HEADER_2;
    packet.transportType = TRANSPORT;
    packet.destinationType = SINGLE;
    packet.packetType = ANNOUNCE;
    packet.contextFlag = e.contextFlag;
    packet.hops = entry.hops;
    packet.context = entry.blockRebroadcasts ? CONTEXT_PATH_RESPONSE : 0;
    memcpy(packet.transportId, identityHash_, TRUNCATED_HASH_SIZE);
    memcpy(packet.destinationHash, entry.destination, TRUNCATED_HASH_SIZE);
    packet.data = table_.announce();
    packet.dataLength = e.announceLength;
    uint8_t raw[MTU];
    const size_t rawLength = pack(packet, raw, sizeof(raw));
    if (rawLength && emit(raw, rawLength, true)) ++(entry.blockRebroadcasts ? counters_.pathResponses : counters_.rebroadcasts);
    for (AnnounceEntry& h : held_) {   // held_announces: wstrzymany wpis wraca do tablicy
        if (h.used && memcmp(h.destination, entry.destination, TRUNCATED_HASH_SIZE) == 0) {
            entry = h;
            h.used = false;
            break;
        }
    }
}

// RNS/Transport.py: _inbound (ANNOUNCE z identyfikatorem transportu): retransmisja tego ogłoszenia
// przez sąsiada. Ta sama liczba skoków co we wpisie: lokalna powtórka (po LOCAL_REBROADCASTS_MAX wpis
// z ponowieniem znika); o jeden skok więcej przed czasem ponowienia: następny węzeł już je przekazał.
void Transport::heardRebroadcast(const Packet& packet, uint64_t nowMs) {
    AnnounceEntry* a = findAnnounce(packet.destinationHash);
    if (!a) return;
    if (packet.hops - 1 == a->hops) {
        ++a->localRebroadcasts;
        if (a->retries > 0 && a->localRebroadcasts >= LOCAL_REBROADCASTS_MAX) a->used = false;
    }
    if (packet.hops - 1 == a->hops + 1 && a->retries > 0 && nowMs < a->retransmitMs) a->used = false;
}

bool Transport::requestPath(const uint8_t destination[TRUNCATED_HASH_SIZE], const uint8_t tag[TRUNCATED_HASH_SIZE],
                            uint64_t nowMs) {
    OwnRequest* slot = &ownRequests_[0];
    for (OwnRequest& r : ownRequests_) {
        if (r.atMs && memcmp(r.destination, destination, TRUNCATED_HASH_SIZE) == 0) {
            if (nowMs - r.atMs < PATH_REQUEST_MI_MS) return false;
            slot = &r;
            break;
        }
        if (r.atMs < slot->atMs) slot = &r;   // najstarszy albo wolny
    }
    uint8_t data[PATH_REQUEST_SIZE];
    memcpy(data, destination, TRUNCATED_HASH_SIZE);
    memcpy(data + TRUNCATED_HASH_SIZE, identityHash_, TRUNCATED_HASH_SIZE);
    memcpy(data + 2 * TRUNCATED_HASH_SIZE, tag, TRUNCATED_HASH_SIZE);
    Packet packet = {};
    packet.headerType = HEADER_1;
    packet.transportType = BROADCAST;
    packet.destinationType = PLAIN;
    packet.packetType = DATA;
    memcpy(packet.destinationHash, pathRequestDestination_, TRUNCATED_HASH_SIZE);
    packet.data = data;
    packet.dataLength = sizeof(data);
    uint8_t raw[HEADER_1_SIZE + PATH_REQUEST_SIZE];
    const size_t rawLength = pack(packet, raw, sizeof(raw));
    if (!rawLength || !emit(raw, rawLength, true)) return false;
    memcpy(slot->destination, destination, TRUNCATED_HASH_SIZE);
    slot->atMs = nowMs ? nowMs : 1;
    ++counters_.requestsSent;
    return true;
}

void Transport::poll(uint64_t nowMs, bool transmit) {
    for (Receipt& r : receipts_) {
        if (!r.used || nowMs < r.deadlineMs) continue;
        r.used = false;
        ++counters_.timedOut;
        if (hooks_.receipt) hooks_.receipt(r.handle, false, hooks_.context);
    }
    // Każda retransmisja to odczyt gniazda i podpis IFAC: najwyżej jedna na wywołanie, najwcześniejsza
    // zaległa; reszta czeka na kolejne obiegi pętli (Python nadaje wszystkie zaległe naraz w jobs).
    AnnounceEntry* due = nullptr;
    for (AnnounceEntry& a : announces_) {
        if (!a.used) continue;
        if ((a.retries > 0 && a.retries >= LOCAL_REBROADCASTS_MAX) || a.retries > PATHFINDER_R) {
            a.used = false;   // limit lokalnych powtórek albo ponowień osiągnięty
        } else if (nowMs > a.retransmitMs && (!due || a.retransmitMs < due->retransmitMs)) {
            due = &a;
        }
    }
    // Odpowiedź odkrycia przed retransmisjami (w Pythonie wychodzi od razu z ogłoszeniem).
    Inflight* respond = nullptr;
    for (Inflight& f : inflight_) {
        if (f.respond) {
            respond = &f;
            break;
        }
    }
    if (transmit && (respond || due) && mayTransmit()) {
        if (respond) sendDiscovery(*respond, nowMs);
        else retransmit(*due, nowMs);
    }
    // Wstrzymany wpis żyje tylko razem z wpisem odpowiedzi swojego celu (zastąpionym, wypartym albo
    // zakończonym bez nadania): bez niego zwalnia miejsce.
    for (AnnounceEntry& h : held_) {
        if (h.used && !findAnnounce(h.destination)) h.used = false;
    }
    // Transport.jobs: trasa nieużywana dłużej niż DESTINATION_TIMEOUT znika z path_table; wpis znanego
    // celu (tożsamość, ratchet) zostaje, jak known_destinations. Przegląd indeksu raz na sekundę.
    const uint32_t nowS = seconds(nowMs);
    if (nowS == cullS_) return;
    cullS_ = nowS;
    table_.expire(nowS);
}

size_t Transport::reverseEntries(uint64_t nowMs) const {
    size_t n = 0;
    for (const ReverseEntry& r : reverse_) n += r.atMs && nowMs - r.atMs <= REVERSE_TIMEOUT_MS;
    return n;
}

size_t Transport::heldAnnounces() const {
    size_t n = 0;
    for (const AnnounceEntry& h : held_) n += h.used;
    return n;
}

size_t Transport::announceTable() const {
    size_t n = 0;
    for (const AnnounceEntry& a : announces_) n += a.used;
    return n;
}

bool Transport::lookup(const uint8_t destination[TRUNCATED_HASH_SIZE], KnownDestination& out, uint64_t nowMs) {
    return table_.read(table_.find(destination), out, seconds(nowMs));
}

uint8_t Transport::hopsTo(const uint8_t destination[TRUNCATED_HASH_SIZE], uint64_t nowMs) {
    KnownDestination e;
    return lookup(destination, e, nowMs) && e.hasPath ? e.hops : PATHFINDER_M;
}

size_t Transport::receiptsPending() const {
    size_t n = 0;
    for (const Receipt& r : receipts_) n += r.used;
    return n;
}

void Transport::clear() {
    table_.clear();
    clean(receipts_, sizeof(receipts_));
    clean(announces_, sizeof(announces_));
    clean(held_, sizeof(held_));
    clean(reverse_, sizeof(reverse_));
    clean(inflight_, sizeof(inflight_));
    discoveryTimeoutMs_ = 0;
    clean(pathTags_, sizeof(pathTags_));
    clean(ownRequests_, sizeof(ownRequests_));
    clean(ownAppData_, sizeof(ownAppData_));
    clean(ownAnnounce_, sizeof(ownAnnounce_));
    ownAnnounceLength_ = 0;
    ownAnnounceMs_ = 0;
    pathTagNext_ = ownAppDataLength_ = 0;
    ownResponseMs_ = 0;
    hashlist_.clear();
    privateKey_ = publicKey_ = identityHash_ = address_ = nameHash_ = nullptr;
    hooks_ = TransportHooks();
}

}  // namespace rnscore
