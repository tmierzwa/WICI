// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// Transport stacji (etapy R1 i R2, firmware/reticulum-core.md): jeden cel SINGLE stacji, tablica znanych
// celów i tras w pamięci trwałej (table.h: tożsamość, ratchet z ogłoszenia, trasa, ogłoszenie w pamięci
// podręcznej), lista skrótów pakietów, ogłoszenie własne, przyjmowanie ogłoszeń, pakietów do stacji
// z dowodem i dowodów pakietów wysłanych, wysyłanie pakietu okazjonalnego z potwierdzeniem.
// Zapytania o trasę (rnstransport.path.request): odpowiedzi dla celu stacji i celów z trasą, własne
// zapytania. Transport włączony jak w porcie (Reticulum.transport_enabled): przekazywanie pakietów
// HEADER_2 z identyfikatorem stacji, tablica odwrotna dla dowodów, retransmisja przyjętych ogłoszeń.
// Jeden interfejs (P1), więc interfejs odbioru i nadania jest ten sam. Wszystkie tablice mają stały
// rozmiar; czas w ms podaje wywołujący (licznik pracy stacji).
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
constexpr uint8_t PATHFINDER_R = 1;                       // RNS/Transport.py: PATHFINDER_R (ponowienia)
constexpr uint32_t PATHFINDER_G_MS = 5000;                // PATHFINDER_G
constexpr uint32_t PATHFINDER_RW_MS = 500;                // PATHFINDER_RW
constexpr uint8_t LOCAL_REBROADCASTS_MAX = 2;             // LOCAL_REBROADCASTS_MAX
constexpr uint32_t PATH_REQUEST_GRACE_MS = 400;           // PATH_REQUEST_GRACE
constexpr uint32_t PATH_REQUEST_MI_MS = 20000;            // PATH_REQUEST_MI: odstęp własnych zapytań o ten sam cel
constexpr uint32_t PATH_REQUEST_GATE_MS = 45000;          // PATH_REQUEST_GATE_TIMEOUT: zapytanie „w drodze”
constexpr uint32_t PATH_REQUEST_TIMEOUT_MS = 15000;       // PATH_REQUEST_TIMEOUT: najkrótsze oczekiwanie odkrycia
// Odpowiedź na zapytanie o cel stacji najwyżej raz na sekundę (odstępstwo: każda wymaga podpisu Ed25519;
// odpowiedź jest rozgłaszana, więc słyszą ją wszyscy pytający).
constexpr uint32_t OWN_RESPONSE_MIN_MS = 1000;
// Dane ostatniego ogłoszenia własnego służą odpowiedziom na zapytania o cel stacji przez 30 s (jak okno
// znaczników zapytań): odpowiedź bez nowego podpisu, sam kod IFAC (odstępstwo, tabela różnic).
constexpr uint32_t OWN_RESPONSE_REUSE_MS = 30000;
constexpr size_t ANNOUNCE_TABLE_MAX = 16;   // tablica retransmisji ogłoszeń (reticulum-core.md, budżet RAM)
constexpr size_t PATH_TAGS_MAX = 128;       // znaczniki ostatnich zapytań o trasę (Python: 2 × 16 000)
constexpr size_t OWN_REQUESTS_MAX = 8;      // cele ostatnich własnych zapytań o trasę
constexpr size_t HELD_ANNOUNCES_MAX = 4;    // held_announces: wpisy wstrzymane na czas odpowiedzi na zapytanie
constexpr size_t INFLIGHT_MAX = 8;          // inflight_path_requests i discovery_path_requests (cele bez odpowiedzi)
constexpr size_t REVERSE_MAX = 32;          // tablica odwrotna (reticulum-core.md, budżet RAM)
constexpr uint32_t REVERSE_TIMEOUT_MS = 8UL * 60 * 1000;   // RNS/Transport.py: REVERSE_TIMEOUT
constexpr size_t PATH_REQUEST_SIZE = 3 * TRUNCATED_HASH_SIZE;   // cel, identyfikator transportu, znacznik
// Dane aplikacji ogłoszenia własnego (bez ratchetu) do ANNOUNCE_FORWARDABLE_SIZE.
constexpr size_t OWN_APP_DATA_MAX = ANNOUNCE_FORWARDABLE_SIZE - ANNOUNCE_MIN_SIZE;

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
    // Bajty losowe (RNS: os.urandom) dla odpowiedzi na zapytanie o trasę do celu stacji; fałsz: brak.
    bool (*random)(uint8_t* out, size_t length, void* context) = nullptr;
    // Interfejs przyjmie teraz pakiet (kod IFAC, bez ciszy, miejsce w kolejce); pytany przed pracą na
    // podpis, której wynik mógłby nie wyjść (odpowiedź własna, retransmisja). nullptr: zawsze.
    bool (*mayTransmit)(void* context) = nullptr;
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
    uint32_t tableFailed = 0; // zapis albo odczyt wpisu tablicy nieudany (pełna tablica celów chronionych, błąd pamięci)
    uint32_t pathRequests = 0;    // zapytania o trasę przyjęte (bez duplikatów znacznika)
    uint32_t pathAnswered = 0;    // z nich z odpowiedzią (cel stacji albo trasa znana)
    uint32_t pathResponses = 0;   // wysłane odpowiedzi (ogłoszenia PATH_RESPONSE)
    uint32_t pathLimited = 0;     // zapytania o cel stacji bez odpowiedzi (OWN_RESPONSE_MIN_MS)
    uint32_t announceTableFull = 0;   // retransmisja odrzucona przy pełnej tablicy ogłoszeń
    uint32_t requestsSent = 0;    // własne zapytania o trasę
    uint32_t pathGated = 0;       // zapytania o cel z zapytaniem „w drodze” (bez odpowiedzi, czekają na ogłoszenie)
    uint32_t forwarded = 0;       // pakiety HEADER_2 przekazane dalej według tablicy tras
    uint32_t noPath = 0;          // pakiety HEADER_2 do stacji jako następnego skoku bez trasy do celu (porzucone)
    uint32_t proofsForwarded = 0; // dowody przekazane według tablicy odwrotnej
    uint32_t reverseFull = 0;     // wpis tablicy odwrotnej wyparty przed czasem (pełna tablica)
    uint32_t rebroadcasts = 0;    // retransmisje przyjętych ogłoszeń (bez odpowiedzi na zapytania)
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
    // RNS/Transport.py: Transport.request_path węzła z transportem: zapytanie z identyfikatorem transportu
    // stacji i znacznikiem tag. Fałsz: zapytanie o ten cel w ostatnich PATH_REQUEST_MI_MS (odstępstwo,
    // tabela różnic) albo interfejs odmówił.
    bool requestPath(const uint8_t destination[TRUNCATED_HASH_SIZE], const uint8_t tag[TRUNCATED_HASH_SIZE], uint64_t nowMs);
    // Przepływność interfejsu (Interface.bitrate) dla czasu oczekiwania odkrycia trasy
    // (Transport.medium_path_timeout); 0: nieznana (15 s, PATH_REQUEST_TIMEOUT).
    void setBitrate(uint32_t bitsPerSecond);
    // RNS/Packet.py: PacketReceipt.check_timeout dla czekających potwierdzeń; RNS/Transport.py: jobs
    // (retransmisje z tablicy ogłoszeń; trasy nieużywane przez DESTINATION_TIMEOUT wygasają, sprawdzane raz
    // na sekundę). Najwyżej jedna retransmisja na wywołanie (najwcześniejsza zaległa), żadna przy
    // transmit = fałsz (obieg pętli stacji z krokiem odbioru, który mógł robić kryptografię).
    void poll(uint64_t nowMs, bool transmit = true);

    // Wpis znanego celu (odczyt z pamięci trwałej ze sprawdzeniem); fałsz, gdy cel nieznany.
    bool lookup(const uint8_t destination[TRUNCATED_HASH_SIZE], KnownDestination& out, uint64_t nowMs);
    const uint8_t* cachedAnnounce() const { return table_.announce(); }   // ogłoszenie z ostatniego lookup()
    bool knows(const uint8_t destination[TRUNCATED_HASH_SIZE]) const { return table_.find(destination) >= 0; }
    bool hasPath(const uint8_t destination[TRUNCATED_HASH_SIZE]) const { return table_.hasPath(table_.find(destination)); }
    uint8_t hopsTo(const uint8_t destination[TRUNCATED_HASH_SIZE], uint64_t nowMs);   // Transport.hops_to
    size_t known() const { return table_.size(); }
    size_t paths() const { return table_.paths(); }
    uint32_t tableCorrupt() const { return table_.corrupt(); }   // gniazda tablicy z błędną treścią od startu
    uint32_t tableWrites() const { return table_.writes(); }
    size_t receiptsPending() const;
    size_t announceTable() const;
    size_t heldAnnounces() const;   // retransmisje wstrzymane na czas odpowiedzi (held_announces)
    size_t reverseEntries(uint64_t nowMs) const;
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
    // RNS/Transport.py: announce_table (bez pakietu: ogłoszenie z pamięci podręcznej tablicy celów).
    struct AnnounceEntry {
        bool used;
        bool blockRebroadcasts;   // odpowiedź na zapytanie o trasę: kontekst PATH_RESPONSE
        uint8_t retries;
        uint8_t hops;
        uint8_t localRebroadcasts;
        uint8_t destination[TRUNCATED_HASH_SIZE];
        uint64_t retransmitMs;
    };
    bool emit(const uint8_t* raw, size_t length, bool rememberHash);
    bool ownAnnounce(const uint8_t random[5], uint64_t nowMs, bool pathResponse);
    bool sendOwnAnnounce(bool pathResponse);
    bool mayTransmit() const { return !hooks_.mayTransmit || hooks_.mayTransmit(hooks_.context); }
    void inboundPlain(const Packet& packet, const uint8_t* raw, size_t length, uint64_t nowMs);
    bool pathRequest(const uint8_t destination[TRUNCATED_HASH_SIZE], const uint8_t* requestor, uint64_t nowMs);
    AnnounceEntry* findAnnounce(const uint8_t destination[TRUNCATED_HASH_SIZE]);
    bool schedule(const uint8_t destination[TRUNCATED_HASH_SIZE], uint8_t hops, uint64_t atMs, uint8_t retries, bool block);
    void retransmit(AnnounceEntry& entry, uint64_t nowMs);
    void heardRebroadcast(const Packet& packet, uint64_t nowMs);
    bool forward(const Packet& packet, const uint8_t* raw, size_t length, const uint8_t hash[HASH_SIZE], uint64_t nowMs);
    bool forwardProof(const Packet& packet, const uint8_t* raw, size_t length, uint64_t nowMs);
    void inboundAnnounce(const Packet& packet, const uint8_t hash[HASH_SIZE], uint64_t nowMs);
    void inboundData(const Packet& packet, const uint8_t hash[HASH_SIZE]);
    void inboundProof(const Packet& packet, const uint8_t* raw, size_t length, uint64_t nowMs);
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
    AnnounceEntry announces_[ANNOUNCE_TABLE_MAX] = {};
    AnnounceEntry held_[HELD_ANNOUNCES_MAX] = {};
    // RNS/Transport.py: reverse_table (skrócony skrót przekazanego pakietu i czas; interfejsy: jeden P1).
    struct ReverseEntry {
        uint8_t hash[TRUNCATED_HASH_SIZE];
        uint64_t atMs;   // 0: wolny
    };
    ReverseEntry reverse_[REVERSE_MAX] = {};
    // RNS/Transport.py: inflight_path_requests (zapytanie bez odpowiedzi, PATH_REQUEST_GATE_MS) i
    // discovery_path_requests (kolejne zapytanie o ten cel czeka na ogłoszenie); czasy 0: brak.
    struct Inflight {
        uint8_t destination[TRUNCATED_HASH_SIZE];
        uint64_t atMs;
        uint64_t discoveryUntilMs;
    };
    Inflight inflight_[INFLIGHT_MAX] = {};
    uint32_t discoveryTimeoutMs_ = 0;   // 0: PATH_REQUEST_TIMEOUT_MS
    Inflight* findInflight(const uint8_t destination[TRUNCATED_HASH_SIZE], uint64_t nowMs);
    void discoveryResponse(const Packet& packet, uint64_t nowMs);
    uint64_t pathTags_[PATH_TAGS_MAX] = {};   // 8 B skrótu (cel + znacznik), pierścień
    size_t pathTagNext_ = 0;
    struct OwnRequest {
        uint8_t destination[TRUNCATED_HASH_SIZE];
        uint64_t atMs;
    };
    OwnRequest ownRequests_[OWN_REQUESTS_MAX] = {};
    uint8_t pathRequestDestination_[TRUNCATED_HASH_SIZE] = {};   // cel PLAIN "rnstransport.path.request"
    // Ogłoszenie własne: dane aplikacji z ostatniego announce() (Destination.default_app_data dla odpowiedzi
    // na zapytania o trasę) i bufor danych ogłoszenia (poza stosem).
    uint8_t ownAppData_[OWN_APP_DATA_MAX] = {};
    size_t ownAppDataLength_ = 0;
    uint8_t ownAnnounce_[ANNOUNCE_FORWARDABLE_SIZE] = {};
    size_t ownAnnounceLength_ = 0;   // dane ostatniego ogłoszenia własnego (0: brak)
    uint64_t ownAnnounceMs_ = 0;     // czas ich podpisu
    uint64_t ownResponseMs_ = 0;   // ostatnia odpowiedź na zapytanie o cel stacji (+1, 0: brak)
    HashList hashlist_;
    TransportCounters counters_;
};

}  // namespace rnscore
