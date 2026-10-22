// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// Dowód dostarczenia pakietu: podpis Ed25519 pełnego skrótu pakietu (dowód niejawny, 64 B) albo skrót
// i podpis (dowód jawny, 96 B). Pakiet PROOF idzie do celu o skrócie równym uciętemu skrótowi pakietu.
#pragma once

#include "rnscore.h"

namespace rnscore {

constexpr size_t PROOF_IMPLICIT_SIZE = SIGNATURE_SIZE;               // RNS/Packet.py: PacketReceipt.IMPL_LENGTH
constexpr size_t PROOF_EXPLICIT_SIZE = HASH_SIZE + SIGNATURE_SIZE;   // PacketReceipt.EXPL_LENGTH

// RNS/Identity.py: Identity.prove: dane pakietu PROOF. implicitProof jak Reticulum.should_use_implicit_proof
// (w Pythonie domyślnie prawda). Zwraca długość dowodu w out. Cel pakietu PROOF: ProofDestination
// (RNS/Packet.py), skrót = pierwsze TRUNCATED_HASH_SIZE B packetHash, typ SINGLE, bez szyfrowania.
size_t prove(const uint8_t privateKey[KEY_SIZE], const uint8_t publicKey[KEY_SIZE], const uint8_t packetHash[HASH_SIZE],
             bool implicitProof, uint8_t out[PROOF_EXPLICIT_SIZE]);

// RNS/Packet.py: PacketReceipt.validate_proof: 96 B: skrót równy packetHash i podpis tego skrótu;
// 64 B: podpis skrótu; inna długość: fałsz. publicKey to klucz tożsamości celu wysłanego pakietu.
bool validateProof(const uint8_t publicKey[KEY_SIZE], const uint8_t packetHash[HASH_SIZE], const uint8_t* proof,
                   size_t length);

}  // namespace rnscore
