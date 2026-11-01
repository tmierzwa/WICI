// SPDX-License-Identifier: MIT
#include "migration_crypto.h"

#include <string.h>

#include <ChaChaPoly.h>
#include <Crypto.h>
#include <Curve25519.h>

#include "sha2.h"

namespace migration_crypto {
namespace {

void clamp(uint8_t scalar[KEY]) {
    scalar[0] &= 248;
    scalar[31] = static_cast<uint8_t>((scalar[31] & 127) | 64);
}

// HKDF with salt = mid and info = label || mid.
template <size_t N>
void hkdf(const uint8_t shared[KEY], const uint8_t mid[MID], const char (&label)[N], uint8_t out[KEY]) {
    uint8_t info[N - 1 + MID];
    memcpy(info, label, N - 1);
    memcpy(info + N - 1, mid, MID);
    sha2::hkdf(mid, MID, shared, KEY, info, sizeof(info), out);
}

void nonce(uint32_t index, uint8_t out[12]) {
    memset(out, 0, 12);
    out[0] = 'W'; out[1] = 'M'; out[2] = 'I'; out[3] = 'G';
    out[8] = static_cast<uint8_t>(index >> 24);
    out[9] = static_cast<uint8_t>(index >> 16);
    out[10] = static_cast<uint8_t>(index >> 8);
    out[11] = static_cast<uint8_t>(index);
}

void aad(const uint8_t hdr[HEADER], uint32_t index, ChaChaPoly& cipher) {
    cipher.addAuthData(hdr, HEADER);
    uint8_t number[4] = {static_cast<uint8_t>(index >> 24), static_cast<uint8_t>(index >> 16),
                         static_cast<uint8_t>(index >> 8), static_cast<uint8_t>(index)};
    cipher.addAuthData(number, sizeof(number));
}

bool kindValid(const char* kind) {
    return kind && (!strcmp(kind, "imported") || !strcmp(kind, "retired") || !strcmp(kind, "aborted"));
}

}  // namespace

bool publicKey(const uint8_t privateKey[KEY], uint8_t result[KEY]) {
    if (!privateKey || !result) return false;
    uint8_t scalar[KEY];
    memcpy(scalar, privateKey, KEY);
    clamp(scalar);
    const bool ok = Curve25519::eval(result, scalar, nullptr);
    clean(scalar, sizeof(scalar));
    return ok;
}

bool derive(const uint8_t privateKey[KEY], const uint8_t peerPublic[KEY],
            const uint8_t mid[MID], uint8_t confirmKey[KEY], uint8_t packageKey[KEY]) {
    if (!privateKey || !peerPublic || !mid || !confirmKey || !packageKey ||
        confirmKey == packageKey) return false;
    uint8_t scalar[KEY], shared[KEY];
    memcpy(scalar, privateKey, KEY);
    clamp(scalar);
    const bool ok = Curve25519::eval(shared, scalar, peerPublic);
    clean(scalar, sizeof(scalar));
    uint8_t any = 0;
    for (uint8_t value : shared) any |= value;
    if (!ok || !any) {
        clean(shared, sizeof(shared));
        return false;
    }
    hkdf(shared, mid, "WICI migrate", confirmKey);
    hkdf(shared, mid, "WICI migrate pkg", packageKey);
    clean(shared, sizeof(shared));
    return true;
}

void header(const uint8_t mid[MID], const uint8_t identityDigest[16],
            const uint8_t ephemeralPublic[KEY], const uint8_t packageHash[KEY],
            uint32_t plaintextSize, uint8_t out[HEADER]) {
    out[0] = 1;
    memcpy(out + 1, mid, MID);
    memcpy(out + 17, identityDigest, 16);
    memcpy(out + 33, ephemeralPublic, KEY);
    memcpy(out + 65, packageHash, KEY);
    out[97] = static_cast<uint8_t>(plaintextSize >> 24);
    out[98] = static_cast<uint8_t>(plaintextSize >> 16);
    out[99] = static_cast<uint8_t>(plaintextSize >> 8);
    out[100] = static_cast<uint8_t>(plaintextSize);
}

bool validHeader(const uint8_t bytes[HEADER], const uint8_t mid[MID], uint32_t maxSize) {
    if (!bytes || !mid || bytes[0] != 1 || memcmp(bytes + 1, mid, MID)) return false;
    const uint32_t size = (static_cast<uint32_t>(bytes[97]) << 24) |
                          (static_cast<uint32_t>(bytes[98]) << 16) |
                          (static_cast<uint32_t>(bytes[99]) << 8) | bytes[100];
    return size != 0 && size <= maxSize;
}

bool sealPart(const uint8_t packageKey[KEY], const uint8_t hdr[HEADER], uint32_t index,
              const uint8_t* plaintext, size_t length, uint8_t* output) {
    if (!packageKey || !hdr || !plaintext || !output || !length || length > PART || hdr[0] != 1) return false;
    uint8_t iv[12];
    nonce(index, iv);
    ChaChaPoly cipher;
    if (!cipher.setKey(packageKey, KEY) || !cipher.setIV(iv, sizeof(iv))) return false;
    aad(hdr, index, cipher);
    cipher.encrypt(output, plaintext, length);
    cipher.computeTag(output + length, TAG);
    cipher.clear();
    return true;
}

bool openPart(const uint8_t packageKey[KEY], const uint8_t hdr[HEADER], uint32_t index,
              const uint8_t* ciphertext, size_t length, uint8_t* output) {
    if (!packageKey || !hdr || !ciphertext || !output || length <= TAG || length > PART + TAG || hdr[0] != 1) return false;
    uint8_t iv[12];
    nonce(index, iv);
    ChaChaPoly cipher;
    if (!cipher.setKey(packageKey, KEY) || !cipher.setIV(iv, sizeof(iv))) return false;
    aad(hdr, index, cipher);
    cipher.decrypt(output, ciphertext, length - TAG);
    const bool ok = cipher.checkTag(ciphertext + length - TAG, TAG);
    cipher.clear();
    if (!ok) clean(output, length - TAG);
    return ok;
}

bool confirmation(const uint8_t confirmKey[KEY], const char* kind, const uint8_t mid[MID],
                  const uint8_t packageHash[KEY], uint8_t out[KEY]) {
    if (!confirmKey || !kindValid(kind) || !mid || !out ||
        (strcmp(kind, "aborted") && !packageHash)) return false;
    sha2::Hmac mac(confirmKey, KEY);
    mac.update(reinterpret_cast<const uint8_t*>(kind), strlen(kind));
    mac.update(mid, MID);
    if (strcmp(kind, "aborted")) mac.update(packageHash, KEY);
    mac.finish(out);
    return true;
}

bool verifyConfirmation(const uint8_t confirmKey[KEY], const char* kind, const uint8_t mid[MID],
                        const uint8_t packageHash[KEY], const uint8_t candidate[KEY]) {
    if (!candidate) return false;
    uint8_t expected[KEY];
    if (!confirmation(confirmKey, kind, mid, packageHash, expected)) return false;
    uint8_t difference = 0;
    for (size_t i = 0; i < KEY; ++i) difference |= expected[i] ^ candidate[i];
    clean(expected, sizeof(expected));
    return difference == 0;
}

}  // namespace migration_crypto
