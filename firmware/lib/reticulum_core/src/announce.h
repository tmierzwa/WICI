// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// Ogłoszenie celu SINGLE: dane pakietu ANNOUNCE to klucz publiczny 64 B, skrót nazwy 10 B, skrót
// losowy 10 B (5 B losowych i czas w s, 5 B big-endian), przy fladze kontekstu klucz ratchetu 32 B,
// podpis Ed25519 64 B, dane aplikacji. Podpis obejmuje skrót celu i wszystko poza samym podpisem.
#pragma once

#include "packet.h"
#include "rnscore.h"

namespace rnscore {

constexpr size_t RANDOM_HASH_SIZE = 10;
constexpr size_t ANNOUNCE_MIN_SIZE = KEY_SIZE + NAME_HASH_SIZE + RANDOM_HASH_SIZE + SIGNATURE_SIZE;
// Dane ogłoszenia mieszczą się w pakiecie HEADER_1 (Packet.pack odmawia ponad MTU), także po
// przepisaniu na HEADER_2 przez transport, bo dane się nie zmieniają.
constexpr size_t ANNOUNCE_MAX_SIZE = MTU - HEADER_1_SIZE;

// RNS/Destination.py: Destination.announce: random_hash = get_random_hash()[0:5] + int(time.time())
// jako 5 B big-endian. Czas podaje wywołujący (w stacji licznik pracy, firmware/reticulum-core.md).
void announceRandomHash(const uint8_t random[5], uint64_t timeS, uint8_t out[RANDOM_HASH_SIZE]);

// RNS/Destination.py: Destination.announce bez wysyłania: dane pakietu ANNOUNCE do out. ratchet
// nullptr: bez ratchetu (pakiet bez flagi kontekstu), inaczej klucz publiczny ratchetu 32 B (flaga
// kontekstu ustawiona). publicKey musi pochodzić z privateKey, destinationHash z nameHash i tożsamości.
// Zwraca długość danych albo 0, gdy przekraczają ANNOUNCE_MAX_SIZE lub capacity.
size_t buildAnnounce(const uint8_t privateKey[KEY_SIZE], const uint8_t publicKey[KEY_SIZE],
                     const uint8_t destinationHash[TRUNCATED_HASH_SIZE], const uint8_t nameHash[NAME_HASH_SIZE],
                     const uint8_t randomHash[RANDOM_HASH_SIZE], const uint8_t* ratchet, const uint8_t* appData,
                     size_t appDataLength, uint8_t* out, size_t capacity);

// Pola przyjętego ogłoszenia; wskaźniki do danych pakietu, który musi żyć dłużej.
struct Announce {
    const uint8_t* publicKey;
    const uint8_t* nameHash;
    const uint8_t* randomHash;
    const uint8_t* ratchet;   // nullptr bez flagi kontekstu
    const uint8_t* appData;
    size_t appDataLength;
};

// RNS/Identity.py: Identity.validate_announce: podpis (z odrzuceniem S ≥ L, validate) i skrót celu
// z nazwy i klucza. Fałsz także dla pakietu innego typu niż ANNOUNCE i za krótkich danych. Bez
// sprawdzeń wymagających tablic (znany cel z innym kluczem, czarna lista): robi je wywołujący.
// Odstępstwo: dane dłuższe niż ANNOUNCE_MAX_SIZE odrzucone (Python sprawdza je jak każde; takiego
// ogłoszenia nie złoży Packet.pack, więc zgodny nadawca go nie wyśle).
bool validateAnnounce(const Packet& packet, Announce& out);

}  // namespace rnscore
