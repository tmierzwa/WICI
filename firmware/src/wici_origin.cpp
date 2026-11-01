// SPDX-License-Identifier: MIT
#include "wici_origin.h"

#include <string.h>

#include <Ed25519.h>

#include "envelope.h"

namespace wici_origin {
namespace {
constexpr uint8_t LABEL[] = {'W','I','C','I',' ','K','1',' ','o','r','i','g','i','n',' ','v','1'};
constexpr size_t INPUT_MAX = sizeof(LABEL) + 2 + wici_link::MAX_PAYLOAD;

bool input(uint16_t network, const uint8_t* payload, size_t length, uint8_t out[INPUT_MAX], size_t& size) {
    if (!network || network == wici_link::BROADCAST || !payload || length < envelope::OVERHEAD ||
        length > wici_link::MAX_PAYLOAD) return false;
    memcpy(out, LABEL, sizeof(LABEL));
    out[sizeof(LABEL)] = static_cast<uint8_t>(network >> 8);
    out[sizeof(LABEL) + 1] = static_cast<uint8_t>(network);
    memcpy(out + sizeof(LABEL) + 2, payload, length);
    size = sizeof(LABEL) + 2 + length;
    return true;
}
}  // namespace

bool sign(const uint8_t privateKey[64], const uint8_t publicKey[64], uint16_t network,
          const uint8_t* payload, size_t length, uint8_t out[wici_link::ORIGIN_SIGNATURE]) {
    if (!privateKey || !publicKey || !out) return false;
    uint8_t message[INPUT_MAX];
    size_t size = 0;
    if (!input(network, payload, length, message, size)) return false;
    Ed25519::sign(out, privateKey + 32, publicKey + 32, message, size);
    return true;
}

bool verify(const uint8_t publicKey[64], uint16_t network, const uint8_t* payload,
            size_t length, const uint8_t signature[wici_link::ORIGIN_SIGNATURE]) {
    if (!publicKey || !signature) return false;
    uint8_t message[INPUT_MAX];
    size_t size = 0;
    if (!input(network, payload, length, message, size)) return false;
    return Ed25519::verify(signature, publicKey + 32, message, size);
}
}  // namespace wici_origin
