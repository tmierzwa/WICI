// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// Pakiet Reticulum: flagi 1 B, liczba skoków 1 B, w HEADER_2 identyfikator transportu 16 B, skrót celu
// 16 B, kontekst 1 B, dane. Rozbiór, złożenie i skrót pakietu; szyfrowanie danych robi wywołujący (token).
#pragma once

#include "rnscore.h"

namespace rnscore {

// RNS/Reticulum.py: MTU, HEADER_MINSIZE, HEADER_MAXSIZE; RNS/Transport.py: PATHFINDER_M.
constexpr size_t MTU = 500;
constexpr size_t HEADER_1_SIZE = 2 + TRUNCATED_HASH_SIZE + 1;
constexpr size_t HEADER_2_SIZE = 2 + 2 * TRUNCATED_HASH_SIZE + 1;
constexpr uint8_t MAX_HOPS = 128;   // liczba skoków musi być mniejsza

// RNS/Packet.py: HEADER_1, HEADER_2, DATA, ANNOUNCE, LINKREQUEST, PROOF; RNS/Transport.py: BROADCAST,
// TRANSPORT; RNS/Destination.py: SINGLE, GROUP, PLAIN, LINK.
enum HeaderType : uint8_t { HEADER_1 = 0, HEADER_2 = 1 };
enum PacketType : uint8_t { DATA = 0, ANNOUNCE = 1, LINKREQUEST = 2, PROOF = 3 };
enum TransportType : uint8_t { BROADCAST = 0, TRANSPORT = 1 };
enum DestinationType : uint8_t { SINGLE = 0, GROUP = 1, PLAIN = 2, LINK = 3 };

struct Packet {
    HeaderType headerType;
    uint8_t contextFlag;   // 0 albo 1
    TransportType transportType;
    DestinationType destinationType;
    PacketType packetType;
    uint8_t hops;
    uint8_t transportId[TRUNCATED_HASH_SIZE];   // tylko HEADER_2
    uint8_t destinationHash[TRUNCATED_HASH_SIZE];
    uint8_t context;
    const uint8_t* data;   // po unpack wskazuje do bufora pakietu, który musi żyć dłużej
    size_t dataLength;
};

// RNS/Packet.py: Packet.unpack. Fałsz tam, gdzie Python odrzuca pakiet: za krótki nagłówek, brak
// danych, liczba skoków ≥ MAX_HOPS. Jak w Pythonie bit 7 flag (IFAC, zdejmuje go interfejs) jest
// pomijany, a długość ponad MTU nie jest sprawdzana (ogranicza ją interfejs).
bool unpack(const uint8_t* raw, size_t length, Packet& out);

// RNS/Packet.py: Packet.pack bez szyfrowania (dane już zaszyfrowane, jeśli trzeba) i bez kontekstu
// LRPROOF (łącza poza rdzeniem). Zwraca długość pakietu w out albo 0, gdy przekracza MTU lub capacity,
// gdy liczba skoków ≥ MAX_HOPS albo dane są puste (Python by ich nie przyjął). out nie może zachodzić na data.
size_t pack(const Packet& packet, uint8_t* out, size_t capacity);

// RNS/Packet.py: get_hash i get_hashable_part: SHA-256 z (flagi & 0x0F) i pakietu od skrótu celu, czyli
// bez liczby skoków, typu nagłówka, flagi kontekstu, typu transportu i identyfikatora transportu.
// raw musi być pakietem przyjętym przez unpack.
void packetHash(const uint8_t* raw, size_t length, uint8_t out[HASH_SIZE]);

}  // namespace rnscore
