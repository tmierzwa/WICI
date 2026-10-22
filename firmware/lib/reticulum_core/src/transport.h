// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// Transport stacji bez przekazywania (etap R1, firmware/reticulum-core.md): jeden cel SINGLE stacji,
// tablica znanych celów (tożsamość, ratchet z ogłoszenia, trasa), lista skrótów pakietów, ogłoszenie
// własne, przyjmowanie ogłoszeń, pakietów do stacji z dowodem i dowodów pakietów wysłanych, wysyłanie
// pakietu okazjonalnego z potwierdzeniem. Przekazywanie, zapytania o trasę i tablice w FRAM: etap R2.
// Wszystkie tablice mają stały rozmiar; czas w ms podaje wywołujący (licznik pracy stacji).
#pragma once

#include "hashlist.h"
#include "packet.h"
#include "rnscore.h"

namespace rnscore {

constexpr size_t KNOWN_MAX = 256;       // docs/spec/oprogramowanie.md, „Pojemności stosu”
constexpr size_t RECEIPTS_MAX = 8;      // potwierdzenia czekające na dowód (decyzja tymczasowa, PR R1)
constexpr uint8_t PATHFINDER_M = 128;   // RNS/Transport.py: PATHFINDER_M
constexpr uint32_t PATHFINDER_E_S = 60UL * 60 * 24 * 7;   // RNS/Transport.py: PATHFINDER_E (tydzień)
constexpr uint32_t DESTINATION_TIMEOUT_S = 60UL * 60 * 24 * 7;   // RNS/Transport.py: DESTINATION_TIMEOUT
constexpr uint8_t CONTEXT_PATH_RESPONSE = 0x0B;           // RNS/Packet.py: PATH_RESPONSE

// Wpis znanego celu: RNS/Identity.py: known_destinations i known_ratchets, RNS/Transport.py: path_table.
// Z listy skrótów losowych ogłoszeń (Python: do 64) wpis trzyma tylko ostatni (tabela różnic).
// Pola w kolejności bez dopełnienia: 168 B.
struct KnownDestination {
    uint8_t destination[TRUNCATED_HASH_SIZE];
    uint8_t publicKey[KEY_SIZE];
    uint8_t ratchet[RATCHET_SIZE];
    uint8_t randomHash[10];                     // ostatni skrót losowy ogłoszenia przyjętego do trasy
    uint8_t nextHop[TRUNCATED_HASH_SIZE];       // identyfikator transportu albo sam cel (sąsiad)
    uint8_t hops;
    bool used;
    bool hasRatchet;
    bool hasPath;
    uint64_t emitted;                           // czas z tego skrótu losowego (Transport.announce_emitted)
    uint32_t pathExpiresS;                      // IDX_PT_EXPIRES: should_add
    uint32_t pathUsedS;                         // IDX_PT_TIMESTAMP: trasa nieużywana 7 dni wygasa
    uint32_t ratchetEmittedS;                   // czas emisji ogłoszenia z zapisanym ratchetem (nasycony)
    uint32_t usedS;                             // ostatnie użycie: do wypierania
};

struct TransportHooks {
    // Pakiet do nadania przez interfejs; fałsz: interfejs odmówił (wtedy nic nie jest zapamiętane).
    bool (*transmit)(const uint8_t* raw, size_t length, void* context) = nullptr;
    // Ogłoszenie innego celu "wici.sa1" przyjęte do tablicy (bez odpowiedzi na zapytania o trasę).
    void (*announce)(const uint8_t destination[TRUNCATED_HASH_SIZE], const uint8_t* appData, size_t length,
                     void* context) = nullptr;
    // Pakiet do celu stacji po odszyfrowaniu; prawda: stos wysyła dowód (PROVE_APP).
    bool (*packet)(const uint8_t* data, size_t length, void* context) = nullptr;
    // Wynik potwierdzenia wysłanego pakietu.
    void (*receipt)(uint32_t handle, bool delivered, void* context) = nullptr;
    // Cel chroniony przed wyparciem z pełnej tablicy (odbiorca z karty).
    bool (*pinned)(const uint8_t destination[TRUNCATED_HASH_SIZE], void* context) = nullptr;
    void* context = nullptr;
};

struct TransportCounters {
    uint32_t duplicate = 0;   // pakiet ze skrótem z listy (packet_filter); ogłoszenie: kopia już sprawdzonego
    uint32_t ignored = 0;     // poza podzbiorem R1 albo nie do stacji: łącza, PLAIN, GROUP, cudzy transport, cudzy cel
    uint32_t invalid = 0;     // ogłoszenie odrzucone, pakiet nie do odszyfrowania, dowód bez czekającego potwierdzenia
    uint32_t announces = 0;   // ogłoszenia przyjęte do trasy
    uint32_t received = 0;    // pakiety do stacji po odszyfrowaniu
    uint32_t unproven = 0;    // z nich odrzucone przez warstwę aplikacji (bez dowodu)
    uint32_t sent = 0;
    uint32_t delivered = 0;
    uint32_t timedOut = 0;
};

enum class SendResult : uint8_t { SENT, UNKNOWN, TOO_LARGE, RECEIPTS_FULL, REFUSED };

class Transport {
public:
    // address nullptr: węzeł bez celu stacji (pakiety DATA i ogłoszenie własne odpadają).
    void begin(const uint8_t privateKey[KEY_SIZE], const uint8_t publicKey[KEY_SIZE],
               const uint8_t identityHash[TRUNCATED_HASH_SIZE], const uint8_t* address,
               const uint8_t nameHash[NAME_HASH_SIZE], const TransportHooks& hooks);
    // Pakiet bez IFAC przyjęty przez interfejs (RNS/Transport.py: preprocess_inbound od unpack i _inbound).
    // Fałsz, gdy unpack go odrzuca.
    bool inbound(const uint8_t* raw, size_t length, uint64_t nowMs);
    // RNS/Destination.py: Destination.announce bez ratchetu; random: 5 B losowych (get_random_hash).
    bool announce(const uint8_t random[5], const uint8_t* appData, size_t length, uint64_t nowMs);
    // RNS/Identity.py: Identity.remember dla tożsamości z karty (bez trasy). Fałsz przy pełnej tablicy
    // bez wpisu do wyparcia.
    bool remember(const uint8_t destination[TRUNCATED_HASH_SIZE], const uint8_t publicKey[KEY_SIZE], uint64_t nowMs);
    // RNS/Packet.py: Packet.send dla celu SINGLE OUT z potwierdzeniem (Transport.outbound, PacketReceipt).
    // ephemeralKey i iv jak w encrypt (losowe i nowe); timeoutMs od wysłania; handle != 0 dla wyniku.
    SendResult send(const uint8_t destination[TRUNCATED_HASH_SIZE], const uint8_t* data, size_t length,
                    const uint8_t ephemeralKey[KEY_SIZE / 2], const uint8_t iv[16], uint32_t handle, uint64_t timeoutMs,
                    uint64_t nowMs);
    // RNS/Packet.py: PacketReceipt.check_timeout dla czekających potwierdzeń; RNS/Transport.py: jobs
    // (trasy nieużywane przez DESTINATION_TIMEOUT wygasają, sprawdzane raz na sekundę).
    void poll(uint64_t nowMs);

    const KnownDestination* find(const uint8_t destination[TRUNCATED_HASH_SIZE]) const;
    uint8_t hopsTo(const uint8_t destination[TRUNCATED_HASH_SIZE]) const;   // Transport.hops_to
    size_t paths() const;
    size_t receiptsPending() const;
    size_t hashes() const { return hashlist_.size(); }
    const TransportCounters& counters() const { return counters_; }
    void setLimit(size_t limit);   // próby: mniejsza tablica znanych celów (1..KNOWN_MAX)
    void clear();                  // halt: tablice i klucze skasowane

private:
    struct Receipt {
        bool used;
        uint32_t handle;
        uint8_t hash[HASH_SIZE];
        uint8_t publicKey[KEY_SIZE];   // tożsamość celu z chwili wysłania (PacketReceipt.destination)
        uint64_t deadlineMs;
    };
    bool emit(const uint8_t* raw, size_t length, bool rememberHash);
    void inboundAnnounce(const Packet& packet, const uint8_t hash[HASH_SIZE], uint64_t nowMs);
    void inboundData(const Packet& packet, const uint8_t hash[HASH_SIZE]);
    void inboundProof(const Packet& packet);
    KnownDestination* entry(const uint8_t destination[TRUNCATED_HASH_SIZE]);
    KnownDestination* findMutable(const uint8_t destination[TRUNCATED_HASH_SIZE]);

    TransportHooks hooks_;
    const uint8_t* privateKey_ = nullptr;
    const uint8_t* publicKey_ = nullptr;
    const uint8_t* identityHash_ = nullptr;
    const uint8_t* address_ = nullptr;
    const uint8_t* nameHash_ = nullptr;
    KnownDestination known_[KNOWN_MAX] = {};
    size_t limit_ = KNOWN_MAX;
    uint32_t cullS_ = 0;   // ostatni przegląd wygasania tras
    Receipt receipts_[RECEIPTS_MAX] = {};
    HashList hashlist_;
    TransportCounters counters_;
};

}  // namespace rnscore
