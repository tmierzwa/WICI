// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
#include "proof.h"

#include <string.h>

#include "identity.h"

namespace rnscore {

size_t prove(const uint8_t privateKey[KEY_SIZE], const uint8_t publicKey[KEY_SIZE], const uint8_t packetHash[HASH_SIZE],
             bool implicitProof, uint8_t out[PROOF_EXPLICIT_SIZE]) {
    if (implicitProof) {
        sign(privateKey, publicKey, packetHash, HASH_SIZE, out);
        return PROOF_IMPLICIT_SIZE;
    }
    memcpy(out, packetHash, HASH_SIZE);
    sign(privateKey, publicKey, packetHash, HASH_SIZE, out + HASH_SIZE);
    return PROOF_EXPLICIT_SIZE;
}

bool validateProof(const uint8_t publicKey[KEY_SIZE], const uint8_t packetHash[HASH_SIZE], const uint8_t* proof,
                   size_t length) {
    if (length == PROOF_EXPLICIT_SIZE) {
        // Skrót jest jawny, porównanie nie musi być w stałym czasie.
        if (memcmp(proof, packetHash, HASH_SIZE) != 0) return false;
        return validate(publicKey, proof + HASH_SIZE, SIGNATURE_SIZE, packetHash, HASH_SIZE);
    }
    if (length == PROOF_IMPLICIT_SIZE) return validate(publicKey, proof, SIGNATURE_SIZE, packetHash, HASH_SIZE);
    return false;
}

}  // namespace rnscore
