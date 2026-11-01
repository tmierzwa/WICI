// SPDX-License-Identifier: MIT
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "identity.h"
#include "wici_origin.h"

int main() {
    uint8_t secret[64], publicKey[64], envelope[25] = {};
    for (unsigned i = 0; i < sizeof(secret); ++i) secret[i] = static_cast<uint8_t>(i);
    envelope[0] = 0x40;
    envelope[2] = 4;
    envelope[4] = 2;
    rnscore::publicKey(secret, publicKey);
    uint8_t signature[64];
    assert(wici_origin::sign(secret, publicKey, 100, envelope, sizeof(envelope), signature));
    assert(wici_origin::verify(publicKey, 100, envelope, sizeof(envelope), signature));
    assert(!wici_origin::verify(publicKey, 101, envelope, sizeof(envelope), signature));
    envelope[4] = 3;
    assert(!wici_origin::verify(publicKey, 100, envelope, sizeof(envelope), signature));
    envelope[4] = 2;
    signature[0] ^= 1;
    assert(!wici_origin::verify(publicKey, 100, envelope, sizeof(envelope), signature));
    signature[0] ^= 1;
    for (uint8_t byte : signature) printf("%02x", byte);
    putchar('\n');
}
