// SPDX-License-Identifier: MIT
#include "core_selftest.h"

#include <string.h>

#include "announce.h"
#include "hexstr.h"
#include "identity.h"
#include "ifac.h"
#include "packet.h"
#include "token.h"

namespace coreselftest {

namespace {

// Wektory z tests/vectors/reticulum.json (Reticulum w Pythonie, tools/rns_vectors.py): tożsamość 0, token
// 17 B tekstu jawnego do niej, podpis 4 B wiadomości i ta sama wiadomość zmieniona, ogłoszenie "plain",
// klucz IFAC i kod 16 B dla pakietu 3 B. tests/test_rnscore.py sprawdza, że każda
// stała jest wartością z tego pliku i że samotest przechodzi na komputerze.
constexpr char PRIVATE_KEY[] =
    "3d2cbb9d7dec8187b4e439e8f7b6f09ac8b340aa1c9623d7e6dcc7223ce5f496b4997c11db3ff4933cfdd0dd33aef3e7"
    "b2267791f097bdca8dd83ccd18ba248f";
constexpr char PUBLIC_KEY[] =
    "5c0505300c6a8d0115e5d0594d9ec95194bfeb8a526bb388f5f3bbc49385e21eb513b363ea5ea31d58fdc8baef4a32b8"
    "69fdf63c7472c3a5a4c591647796986b";
constexpr char TOKEN_EPHEMERAL[] =
    "65dc35d25693a4bf366cfc99a58cd59014653bee5e80d7ae78eead7b53cbd886";
constexpr char TOKEN_IV[] =
    "52da68445665f0621f2bedce1de2bbb8";
constexpr char TOKEN_PLAINTEXT[] =
    "8d8919d54c28477557aa14622da153f469";
constexpr char TOKEN[] =
    "05d6d4e836bd523c45830229658b71ffe977912045cf6bc7a636fe613af3e03952da68445665f0621f2bedce1de2bbb8"
    "d832536144d8dcd81be49c61765ec6c922d3c56ee6105a754fe21aaf20a9a9ce03e3585c1b2003ae0b71d14aa644c524"
    "1e7282e849f5f2aacf25105890619a9c";
constexpr char MESSAGE[] =
    "57494349";
constexpr char TAMPERED[] =
    "56494349";
constexpr char SIGNATURE[] =
    "a5a6995bbdb3e589873b8eb0facd74fea96aa955809b25b34301bbd481f7634b4a2013175ede13cc14af5fb5c9c9ce5a"
    "1c512123bb14d1587e4968a9f6dffa07";
constexpr char ANNOUNCE_PRIVATE_KEY[] =
    "81ffa6ac8c6416edf535f736714718099a61b3c80b17c366ac3172bd6ba53180dc957606847019c0422df10e673db24a"
    "3f50524f7c16286c3af8aaba409ae066";
constexpr char ANNOUNCE[] =
    "0100bce1b5026c520645a57fea9c7300e89400635b14385d8b66c21c978bcc7c2f6ecd3111f50413e66a9535f526fdcc"
    "3a8c1d86efd4c4d473537a559c65ce564277ff276382f84a61b3c98e2e2b442461190650995b0af352c2b98d5f641e6d"
    "cd4b006ab13b805b5dfdb59a1d0bd57542f0d19ce8ea864097494c591772786c6dc9eebebce0b933fd3466e91901345e"
    "856b87af0fbb89fe53d7d089f81e59453907c0e781740b";
constexpr char IFAC_KEY[] =
    "bfceb2aeddff6999a54f52422a9cf32aa28fc7efe107ecf84e15ed4dbaa2361313275d4639eecee3b4a3637e72e76d46"
    "bf0ea2e6fbc058e885383bb0c4930705";
constexpr char IFAC_RAW[] =
    "0000e8";
constexpr char IFAC_WIRE[] =
    "e6fa56b6cdceac7fbf466df47c2f583dfe058d";
// Fraza sieci to tekst kodu IFAC z konfiguracji stacji (32 cyfry szesnastkowe), jak w wektorach.
constexpr char IFAC_PASSPHRASE[] = "5749434954335f696661635f74657374";

template <size_t N>
bool equal(const uint8_t* data, const char (&hex)[N]) {
    uint8_t expected[(N - 1) / 2];
    return hexstr::decode(hex, expected, sizeof(expected)) && memcmp(data, expected, sizeof(expected)) == 0;
}

template <size_t N>
void bytes(const char (&hex)[N], uint8_t (&out)[(N - 1) / 2]) {
    hexstr::decode(hex, out, sizeof(out));
}

bool tokenDecrypt() {
    uint8_t privateKey[64], publicKey[64], token[sizeof(TOKEN) / 2], plaintext[sizeof(TOKEN) / 2];
    bytes(PRIVATE_KEY, privateKey);
    bytes(PUBLIC_KEY, publicKey);
    bytes(TOKEN, token);
    size_t length = 0;
    return rnscore::decrypt(privateKey, publicKey, token, sizeof(token), plaintext, sizeof(plaintext), &length) &&
           length == sizeof(TOKEN_PLAINTEXT) / 2 && equal(plaintext, TOKEN_PLAINTEXT);
}

bool tokenEncrypt() {
    uint8_t publicKey[64], ephemeral[32], iv[16], plaintext[sizeof(TOKEN_PLAINTEXT) / 2], token[sizeof(TOKEN) / 2];
    bytes(PUBLIC_KEY, publicKey);
    bytes(TOKEN_EPHEMERAL, ephemeral);
    bytes(TOKEN_IV, iv);
    bytes(TOKEN_PLAINTEXT, plaintext);
    static_assert(rnscore::tokenSize(sizeof(TOKEN_PLAINTEXT) / 2) == sizeof(TOKEN) / 2, "długość tokenu z wektora");
    return rnscore::encrypt(publicKey, nullptr, ephemeral, iv, plaintext, sizeof(plaintext), token, sizeof(token)) &&
           equal(token, TOKEN);
}

bool sign() {
    uint8_t privateKey[64], publicKey[64], message[sizeof(MESSAGE) / 2], signature[rnscore::SIGNATURE_SIZE];
    bytes(PRIVATE_KEY, privateKey);
    bytes(PUBLIC_KEY, publicKey);
    bytes(MESSAGE, message);
    rnscore::sign(privateKey, publicKey, message, sizeof(message), signature);
    return equal(signature, SIGNATURE);
}

// Podpis poprawny przyjęty.
bool validate() {
    uint8_t publicKey[64], message[sizeof(MESSAGE) / 2], signature[rnscore::SIGNATURE_SIZE];
    bytes(PUBLIC_KEY, publicKey);
    bytes(MESSAGE, message);
    bytes(SIGNATURE, signature);
    return rnscore::validate(publicKey, signature, sizeof(signature), message, sizeof(message));
}

// Ten sam podpis zmienionej wiadomości odrzucony.
bool validateReject() {
    uint8_t publicKey[64], tampered[sizeof(TAMPERED) / 2], signature[rnscore::SIGNATURE_SIZE];
    bytes(PUBLIC_KEY, publicKey);
    bytes(TAMPERED, tampered);
    bytes(SIGNATURE, signature);
    return !rnscore::validate(publicKey, signature, sizeof(signature), tampered, sizeof(tampered));
}

bool publicKey() {
    uint8_t privateKey[64], publicKey[64];
    bytes(PRIVATE_KEY, privateKey);
    rnscore::publicKey(privateKey, publicKey);
    return equal(publicKey, PUBLIC_KEY);
}

bool announceValidate() {
    uint8_t raw[sizeof(ANNOUNCE) / 2];
    bytes(ANNOUNCE, raw);
    rnscore::Packet packet;
    rnscore::Announce announce;
    return rnscore::unpack(raw, sizeof(raw), packet) && rnscore::validateAnnounce(packet, announce) &&
           announce.ratchet == nullptr && announce.appDataLength == 0;
}

// Te same bajty ogłoszenia z klucza, skrótu losowego i pól z wektora (skrót celu i nazwy z pakietu).
bool announceBuild() {
    uint8_t raw[sizeof(ANNOUNCE) / 2], privateKey[64], publicKey[64], data[rnscore::MTU];
    bytes(ANNOUNCE, raw);
    bytes(ANNOUNCE_PRIVATE_KEY, privateKey);
    rnscore::publicKey(privateKey, publicKey);
    rnscore::Packet packet;
    if (!rnscore::unpack(raw, sizeof(raw), packet)) return false;
    const uint8_t* fields = packet.data;   // klucz 64 B, skrót nazwy 10 B, skrót losowy 10 B
    const size_t length = rnscore::buildAnnounce(privateKey, publicKey, packet.destinationHash, fields + 64, fields + 74,
                                                 nullptr, nullptr, 0, data, sizeof(data));
    return length == packet.dataLength && memcmp(data, packet.data, length) == 0;
}

bool ifac() {
    rnscore::Ifac ifac;
    uint8_t raw[sizeof(IFAC_RAW) / 2], wire[sizeof(IFAC_WIRE) / 2], back[sizeof(IFAC_RAW) / 2];
    bytes(IFAC_RAW, raw);
    if (!rnscore::ifacSetup(nullptr, IFAC_PASSPHRASE, 16, ifac) || !equal(ifac.key, IFAC_KEY)) return false;
    if (rnscore::ifacApply(ifac, raw, sizeof(raw), wire, sizeof(wire)) != sizeof(wire) || !equal(wire, IFAC_WIRE)) return false;
    return rnscore::ifacCheck(ifac, wire, sizeof(wire), back, sizeof(back)) == sizeof(back) && equal(back, IFAC_RAW);
}

struct Check {
    const char* name;
    bool (*run)();
};

constexpr Check CHECKS[COUNT] = {
    {"token_decrypt", tokenDecrypt}, {"token_encrypt", tokenEncrypt}, {"sign", sign}, {"validate", validate},
    {"validate_reject", validateReject}, {"public_key", publicKey}, {"announce_validate", announceValidate}, {"announce_build", announceBuild}, {"ifac", ifac},
};

}  // namespace

bool run(Result* out, size_t count, uint32_t (*micros)()) {
    bool all = true;
    for (size_t i = 0; i < count && i < COUNT; ++i) {
        const uint32_t start = micros();
        out[i].ok = CHECKS[i].run();
        out[i].us = micros() - start;
        out[i].name = CHECKS[i].name;
        all = all && out[i].ok;
    }
    return all;
}

}  // namespace coreselftest
