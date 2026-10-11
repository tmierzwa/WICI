// SPDX-License-Identifier: MIT
// Usługi ESP-IDF, których obraz bench-b używa z ROM albo sprzętu ESP32-S3, a których nie ma na
// wirtualnej płytce: akcelerator AES (esp_aes_setkey, esp_aes_crypt_ecb; używa ich biblioteka Crypto
// stosu, AESEsp32.cpp) jako programowy AES według FIPS-197. Kontekst jak esp_aes_context ESP-IDF:
// bajt 0 długość klucza w bajtach, bajt 1 znacznik klucza w sprzęcie, od bajtu 2 klucz.
// Alokator TLSF z ROM zastępuje kopia z biblioteki stosu (build.py, ROM_SOURCES).
#include <stdint.h>
#include <string.h>

namespace {

const uint8_t SBOX[256] = {
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76, 0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59,
    0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0, 0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1,
    0x71, 0xd8, 0x31, 0x15, 0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75, 0x09, 0x83,
    0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84, 0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b,
    0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf, 0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c,
    0x9f, 0xa8, 0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2, 0xcd, 0x0c, 0x13, 0xec,
    0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73, 0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee,
    0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb, 0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08, 0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6,
    0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a, 0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9,
    0x86, 0xc1, 0x1d, 0x9e, 0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf, 0x8c, 0xa1,
    0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16};

uint8_t inverse(uint8_t v) {
    static uint8_t table[256];
    static bool ready = false;
    if (!ready) {
        for (int i = 0; i < 256; ++i) table[SBOX[i]] = static_cast<uint8_t>(i);
        ready = true;
    }
    return table[v];
}

uint8_t xtime(uint8_t x) { return static_cast<uint8_t>((x << 1) ^ ((x & 0x80) ? 0x1b : 0)); }
uint8_t mul(uint8_t a, uint8_t b) {
    uint8_t r = 0;
    while (b) {
        if (b & 1) r ^= a;
        a = xtime(a);
        b >>= 1;
    }
    return r;
}

// Rozwinięcie klucza: (Nr + 1) × 16 B dla Nk = 4, 6, 8 słów.
int expand(const uint8_t* key, int bytes, uint8_t* w) {
    const int nk = bytes / 4, nr = nk + 6;
    memcpy(w, key, static_cast<size_t>(bytes));
    uint8_t rcon = 1;
    for (int i = nk; i < 4 * (nr + 1); ++i) {
        uint8_t t[4];
        memcpy(t, w + 4 * (i - 1), 4);
        if (i % nk == 0) {
            const uint8_t first = t[0];
            t[0] = static_cast<uint8_t>(SBOX[t[1]] ^ rcon);
            t[1] = SBOX[t[2]];
            t[2] = SBOX[t[3]];
            t[3] = SBOX[first];
            rcon = xtime(rcon);
        } else if (nk > 6 && i % nk == 4) {
            for (uint8_t& b : t) b = SBOX[b];
        }
        for (int j = 0; j < 4; ++j) w[4 * i + j] = static_cast<uint8_t>(w[4 * (i - nk) + j] ^ t[j]);
    }
    return nr;
}

void encrypt(const uint8_t* w, int nr, uint8_t s[16]) {
    for (int i = 0; i < 16; ++i) s[i] ^= w[i];
    for (int round = 1; round <= nr; ++round) {
        uint8_t t[16];
        for (int i = 0; i < 16; ++i) t[i] = SBOX[s[(i + 4 * (i % 4)) % 16]];   // SubBytes + ShiftRows
        if (round != nr) {
            for (int c = 0; c < 4; ++c) {
                uint8_t* col = t + 4 * c;
                const uint8_t a0 = col[0], a1 = col[1], a2 = col[2], a3 = col[3];
                col[0] = static_cast<uint8_t>(mul(a0, 2) ^ mul(a1, 3) ^ a2 ^ a3);
                col[1] = static_cast<uint8_t>(a0 ^ mul(a1, 2) ^ mul(a2, 3) ^ a3);
                col[2] = static_cast<uint8_t>(a0 ^ a1 ^ mul(a2, 2) ^ mul(a3, 3));
                col[3] = static_cast<uint8_t>(mul(a0, 3) ^ a1 ^ a2 ^ mul(a3, 2));
            }
        }
        for (int i = 0; i < 16; ++i) s[i] = static_cast<uint8_t>(t[i] ^ w[16 * round + i]);
    }
}

void decrypt(const uint8_t* w, int nr, uint8_t s[16]) {
    for (int i = 0; i < 16; ++i) s[i] ^= w[16 * nr + i];
    for (int round = nr - 1; round >= 0; --round) {
        uint8_t t[16];
        for (int i = 0; i < 16; ++i) t[(i + 4 * (i % 4)) % 16] = inverse(s[i]);   // InvShiftRows + InvSubBytes
        for (int i = 0; i < 16; ++i) t[i] ^= w[16 * round + i];
        if (round != 0) {
            for (int c = 0; c < 4; ++c) {
                uint8_t* col = t + 4 * c;
                const uint8_t a0 = col[0], a1 = col[1], a2 = col[2], a3 = col[3];
                col[0] = static_cast<uint8_t>(mul(a0, 14) ^ mul(a1, 11) ^ mul(a2, 13) ^ mul(a3, 9));
                col[1] = static_cast<uint8_t>(mul(a0, 9) ^ mul(a1, 14) ^ mul(a2, 11) ^ mul(a3, 13));
                col[2] = static_cast<uint8_t>(mul(a0, 13) ^ mul(a1, 9) ^ mul(a2, 14) ^ mul(a3, 11));
                col[3] = static_cast<uint8_t>(mul(a0, 11) ^ mul(a1, 13) ^ mul(a2, 9) ^ mul(a3, 14));
            }
        }
        memcpy(s, t, 16);
    }
}

}  // namespace

extern "C" {

int esp_aes_setkey(unsigned char* ctx, const unsigned char* key, unsigned int keybits) {
    if (keybits != 128 && keybits != 192 && keybits != 256) return -1;
    ctx[0] = static_cast<unsigned char>(keybits / 8);
    ctx[1] = 0;
    memcpy(ctx + 2, key, keybits / 8);
    return 0;
}

int esp_aes_crypt_ecb(unsigned char* ctx, int mode, const unsigned char* input, unsigned char* output) {
    uint8_t w[240];
    const int nr = expand(ctx + 2, ctx[0], w);
    uint8_t s[16];
    memcpy(s, input, 16);
    if (mode) encrypt(w, nr, s);
    else decrypt(w, nr, s);
    memcpy(output, s, 16);
    return 0;
}

}  // extern "C"
