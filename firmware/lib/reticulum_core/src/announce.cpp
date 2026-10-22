// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
#include "announce.h"

#include <string.h>

#include "destination.h"
#include "identity.h"

namespace rnscore {

namespace {

// Dane podpisane: skrót celu i dane ogłoszenia bez podpisu (Destination.announce, signed_data).
constexpr size_t SIGNED_MAX = TRUNCATED_HASH_SIZE + ANNOUNCE_MAX_SIZE - SIGNATURE_SIZE;

size_t signedData(const uint8_t destinationHash[TRUNCATED_HASH_SIZE], const uint8_t* beforeSignature, size_t beforeLength,
                  const uint8_t* appData, size_t appDataLength, uint8_t out[SIGNED_MAX]) {
    memcpy(out, destinationHash, TRUNCATED_HASH_SIZE);
    memcpy(out + TRUNCATED_HASH_SIZE, beforeSignature, beforeLength);
    if (appDataLength) memcpy(out + TRUNCATED_HASH_SIZE + beforeLength, appData, appDataLength);
    return TRUNCATED_HASH_SIZE + beforeLength + appDataLength;
}

}  // namespace

void announceRandomHash(const uint8_t random[5], uint64_t timeS, uint8_t out[RANDOM_HASH_SIZE]) {
    memcpy(out, random, 5);
    for (int i = 0; i < 5; ++i) out[5 + i] = static_cast<uint8_t>(timeS >> (8 * (4 - i)));
}

size_t buildAnnounce(const uint8_t privateKey[KEY_SIZE], const uint8_t publicKey[KEY_SIZE],
                     const uint8_t destinationHash[TRUNCATED_HASH_SIZE], const uint8_t nameHash[NAME_HASH_SIZE],
                     const uint8_t randomHash[RANDOM_HASH_SIZE], const uint8_t* ratchet, const uint8_t* appData,
                     size_t appDataLength, uint8_t* out, size_t capacity) {
    const size_t before = KEY_SIZE + NAME_HASH_SIZE + RANDOM_HASH_SIZE + (ratchet ? RATCHET_SIZE : 0);
    const size_t length = before + SIGNATURE_SIZE + appDataLength;
    if (length > ANNOUNCE_MAX_SIZE || length > capacity) return 0;
    uint8_t* p = out;
    memcpy(p, publicKey, KEY_SIZE);
    memcpy(p += KEY_SIZE, nameHash, NAME_HASH_SIZE);
    memcpy(p += NAME_HASH_SIZE, randomHash, RANDOM_HASH_SIZE);
    if (ratchet) memcpy(p + RANDOM_HASH_SIZE, ratchet, RATCHET_SIZE);
    uint8_t message[SIGNED_MAX];
    const size_t messageLength = signedData(destinationHash, out, before, appData, appDataLength, message);
    sign(privateKey, publicKey, message, messageLength, out + before);
    if (appDataLength) memcpy(out + before + SIGNATURE_SIZE, appData, appDataLength);
    return length;
}

bool validateAnnounce(const Packet& packet, Announce& out) {
    if (packet.packetType != ANNOUNCE) return false;
    const bool hasRatchet = packet.contextFlag == 1;
    const size_t before = KEY_SIZE + NAME_HASH_SIZE + RANDOM_HASH_SIZE + (hasRatchet ? RATCHET_SIZE : 0);
    // Python: krótsze dane dają podpis krótszy niż 64 B albo zły klucz, więc validate zwraca fałsz.
    if (packet.dataLength < before + SIGNATURE_SIZE || packet.dataLength > ANNOUNCE_MAX_SIZE) return false;
    const uint8_t* data = packet.data;
    out.publicKey = data;
    out.nameHash = data + KEY_SIZE;
    out.randomHash = data + KEY_SIZE + NAME_HASH_SIZE;
    out.ratchet = hasRatchet ? data + KEY_SIZE + NAME_HASH_SIZE + RANDOM_HASH_SIZE : nullptr;
    out.appData = data + before + SIGNATURE_SIZE;
    out.appDataLength = packet.dataLength - before - SIGNATURE_SIZE;

    uint8_t message[SIGNED_MAX];
    const size_t messageLength =
        signedData(packet.destinationHash, data, before, out.appData, out.appDataLength, message);
    if (!validate(out.publicKey, data + before, SIGNATURE_SIZE, message, messageLength)) return false;

    // Skrót celu z nazwy i tożsamości z ogłoszenia (hash_material, expected_hash).
    uint8_t identity[TRUNCATED_HASH_SIZE], expected[TRUNCATED_HASH_SIZE];
    identityHash(out.publicKey, identity);
    destinationHashFrom(out.nameHash, identity, expected);
    return memcmp(expected, packet.destinationHash, TRUNCATED_HASH_SIZE) == 0;
}

}  // namespace rnscore
