// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// Transport stacji (etapy R1 i R2, firmware/reticulum-core.md): jeden cel SINGLE stacji, tablica znanych
// celów i tras w pamięci trwałej (table.h: tożsamość, ratchet z ogłoszenia, trasa, ogłoszenie w pamięci
// podręcznej), lista skrótów pakietów, ogłoszenie własne, przyjmowanie ogłoszeń, pakietów do stacji
// z dowodem i dowodów pakietów wysłanych, wysyłanie pakietu okazjonalnego z potwierdzeniem.
// Przekazywanie i zapytania o trasę: dalsze kroki R2. Wszystkie tablice mają stały rozmiar; czas w ms
// podaje wywołujący (licznik pracy stacji).
#pragma once

#include "hashlist.h"
#include "packet.h"
#include "rnscore.h"
#include "table.h"

namespace rnscore {

constexpr size_t RECEIPTS_MAX = 8;      // potwierdzenia czekające na dowód (decyzja tymczasowa, PR R1)
constexpr uint8_t PATHFINDER_M = 128;   // RNS/Transport.py: PATHFINDER_M
constexpr uint32_t PATHFINDER_E_S = 60UL * 60 * 24 * 7;   // RNS/Transport.py: PATHFINDER_E (tydzień)
constexpr uint8_t CONTEXT_PATH_RESPONSE = 0x0B;           // RNS/Packet.py: PATH_RESPONSE

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
    // Zgoda na weryfikację podpisu ogłoszenia, pytana tuż przed nią (po tanich odrzuceniach); fałsz:
    // ogłoszenie odpada bez kryptografii. Limit pracy procesora po stronie stacji, bez odpowiednika w Pythonie.
    bool (*mayVerify)(void* context) = nullptr;
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
    uint32_t tableFailed = 0; // zapis wpisu tablicy nieudany (pełna tablica celów chronionych, błąd pamięci)
};

enum class SendResult : uint8_t { SENT, UNKNOWN, TOO_LARGE, RECEIPTS_FULL, REFUSED };

class Transport {
public:
    // address nullptr: węzeł bez celu stacji (pakiety DATA i ogłoszenie własne odpadają). storage: obszar
    // tablicy znanych celów w pamięci trwałej (montowany tu); nowMs: czas pracy przy starcie.
    void begin(const uint8_t privateKey[KEY_SIZE], const uint8_t publicKey[KEY_SIZE],
               const uint8_t identityHash[TRUNCATED_HASH_SIZE], const uint8_t* address,
               const uint8_t nameHash[NAME_HASH_SIZE], const TransportHooks& hooks, TableStorage& storage, uint64_t nowMs);
    // Pakiet bez IFAC przyjęty przez interfejs (RNS/Transport.py: preprocess_inbound od unpack i _inbound).
    // Fałsz, gdy unpack go odrzuca.
    bool inbound(const uint8_t* raw, size_t length, uint64_t nowMs);
    // RNS/Destination.py: Destination.announce bez ratchetu; random: 5 B losowych (get_random_hash).
    bool announce(const uint8_t random[5], const uint8_t* appData, size_t length, uint64_t nowMs);
    // RNS/Identity.py: Identity.remember dla tożsamości z karty (bez trasy); znany cel z tym samym kluczem
    // bez zapisu. Fałsz przy pełnej tablicy bez wpisu do wyparcia albo przy błędzie zapisu.
    bool remember(const uint8_t destination[TRUNCATED_HASH_SIZE], const uint8_t publicKey[KEY_SIZE], uint64_t nowMs);
    // RNS/Packet.py: Packet.send dla celu SINGLE OUT z potwierdzeniem (Transport.outbound, PacketReceipt).
    // ephemeralKey i iv jak w encrypt (losowe i nowe); timeoutMs od wysłania; handle != 0 dla wyniku.
    SendResult send(const uint8_t destination[TRUNCATED_HASH_SIZE], const uint8_t* data, size_t length,
                    const uint8_t ephemeralKey[KEY_SIZE / 2], const uint8_t iv[16], uint32_t handle, uint64_t timeoutMs,
                    uint64_t nowMs);
    // RNS/Packet.py: PacketReceipt.check_timeout dla czekających potwierdzeń; RNS/Transport.py: jobs
    // (trasy nieużywane przez DESTINATION_TIMEOUT wygasają, sprawdzane raz na sekundę).
    void poll(uint64_t nowMs);

    // Wpis znanego celu (odczyt z pamięci trwałej ze sprawdzeniem); fałsz, gdy cel nieznany.
    bool lookup(const uint8_t destination[TRUNCATED_HASH_SIZE], KnownDestination& out, uint64_t nowMs);
    const uint8_t* cachedAnnounce() const { return table_.announce(); }   // ogłoszenie z ostatniego lookup()
    bool knows(const uint8_t destination[TRUNCATED_HASH_SIZE]) const { return table_.find(destination) >= 0; }
    bool hasPath(const uint8_t destination[TRUNCATED_HASH_SIZE]) const { return table_.hasPath(table_.find(destination)); }
    uint8_t hopsTo(const uint8_t destination[TRUNCATED_HASH_SIZE], uint64_t nowMs);   // Transport.hops_to
    size_t known() const { return table_.size(); }
    size_t paths() const { return table_.paths(); }
    uint32_t tableWrites() const { return table_.writes(); }
    size_t receiptsPending() const;
    size_t hashes() const { return hashlist_.size(); }
    const TransportCounters& counters() const { return counters_; }
    void setLimit(size_t limit) { table_.setLimit(limit); }   // próby: mniejsza tablica znanych celów (1..KNOWN_MAX)
    void clear();                  // halt: tablice i klucze skasowane w RAM, bez zapisów

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
    static bool pinnedHook(const uint8_t destination[TRUNCATED_HASH_SIZE], void* self);

    TransportHooks hooks_;
    const uint8_t* privateKey_ = nullptr;
    const uint8_t* publicKey_ = nullptr;
    const uint8_t* identityHash_ = nullptr;
    const uint8_t* address_ = nullptr;
    const uint8_t* nameHash_ = nullptr;
    Table table_;
    uint32_t cullS_ = 0;   // ostatni przegląd wygasania tras
    Receipt receipts_[RECEIPTS_MAX] = {};
    HashList hashlist_;
    TransportCounters counters_;
};

}  // namespace rnscore
