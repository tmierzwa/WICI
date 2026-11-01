// SPDX-License-Identifier: MIT
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "hexstr.h"
#include "migration_crypto.h"

namespace mc = migration_crypto;

void line(const char* name, const uint8_t* bytes, size_t length) {
    char hex[2 * (mc::PART + mc::TAG) + 1];
    hexstr::encode(bytes, length, hex);
    printf("%s=%s\n", name, hex);
}

int main() {
    uint8_t source[32], target[32], mid[16], identity[16], hash[32];
    for (size_t i = 0; i < 32; ++i) {
        source[i] = static_cast<uint8_t>(i);
        target[i] = static_cast<uint8_t>(i + 32);
        hash[i] = static_cast<uint8_t>(i + 64);
        if (i < 16) { mid[i] = static_cast<uint8_t>(i + 96); identity[i] = static_cast<uint8_t>(i + 112); }
    }
    uint8_t sourcePublic[32], targetPublic[32], confirmKey[32], packageKey[32];
    uint8_t confirmOther[32], packageOther[32];
    assert(mc::publicKey(source, sourcePublic));
    assert(mc::publicKey(target, targetPublic));
    assert(mc::derive(source, targetPublic, mid, confirmKey, packageKey));
    assert(mc::derive(target, sourcePublic, mid, confirmOther, packageOther));
    assert(!memcmp(confirmKey, confirmOther, 32));
    assert(!memcmp(packageKey, packageOther, 32));
    assert(memcmp(confirmKey, packageKey, 32));
    uint8_t zero[32] = {};
    assert(!mc::derive(source, zero, mid, confirmOther, packageOther));
    uint8_t hdr[mc::HEADER];
    mc::header(mid, identity, sourcePublic, hash, 517, hdr);
    assert(mc::validHeader(hdr, mid, 517));
    assert(!mc::validHeader(hdr, mid, 516));
    uint8_t plain[mc::PART], cipher[mc::PART + mc::TAG], opened[mc::PART];
    for (size_t i = 0; i < sizeof(plain); ++i) plain[i] = static_cast<uint8_t>(i);
    assert(mc::sealPart(packageKey, hdr, 7, plain, sizeof(plain), cipher));
    assert(mc::openPart(packageKey, hdr, 7, cipher, sizeof(cipher), opened));
    assert(!memcmp(plain, opened, sizeof(plain)));
    memset(opened, 0xAA, sizeof(opened));
    assert(!mc::openPart(packageKey, hdr, 8, cipher, sizeof(cipher), opened));
    for (uint8_t byte : opened) assert(byte == 0);
    cipher[0] ^= 1;
    assert(!mc::openPart(packageKey, hdr, 7, cipher, sizeof(cipher), opened));
    cipher[0] ^= 1;
    uint8_t imported[32], retired[32], aborted[32];
    assert(mc::confirmation(confirmKey, "imported", mid, hash, imported));
    assert(mc::confirmation(confirmKey, "retired", mid, hash, retired));
    assert(mc::confirmation(confirmKey, "aborted", mid, nullptr, aborted));
    assert(mc::verifyConfirmation(confirmKey, "imported", mid, hash, imported));
    assert(!mc::verifyConfirmation(confirmKey, "retired", mid, hash, imported));
    line("source_public", sourcePublic, 32);
    line("target_public", targetPublic, 32);
    line("confirm_key", confirmKey, 32);
    line("package_key", packageKey, 32);
    line("header", hdr, sizeof(hdr));
    line("cipher", cipher, sizeof(cipher));
    line("imported", imported, 32);
    line("retired", retired, 32);
    line("aborted", aborted, 32);
}
