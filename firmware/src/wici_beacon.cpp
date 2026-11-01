// SPDX-License-Identifier: MIT
#include "wici_beacon.h"
#include "wici_record.h"

#include <Ed25519.h>
#include <string.h>

namespace wici_beacon {
namespace {
using wici_record::id;
constexpr uint8_t LABEL[] = {'W','I','C','I',' ','r','o','u','t','e',' ','b','e','a','c','o','n',' ','v','1'};
void message(uint16_t network, uint16_t sender, const uint8_t content[CONTENT_BYTES],
             uint8_t out[sizeof(LABEL) + 4 + CONTENT_BYTES]) {
    memcpy(out, LABEL, sizeof(LABEL));
    out[sizeof(LABEL)] = static_cast<uint8_t>(network >> 8);
    out[sizeof(LABEL) + 1] = static_cast<uint8_t>(network);
    out[sizeof(LABEL) + 2] = static_cast<uint8_t>(sender >> 8);
    out[sizeof(LABEL) + 3] = static_cast<uint8_t>(sender);
    memcpy(out + sizeof(LABEL) + 4, content, CONTENT_BYTES);
}
}  // namespace

bool sign(const uint8_t identity[64], uint16_t network, uint16_t sender,
          const uint8_t content[CONTENT_BYTES], uint8_t signature[SIGNATURE_BYTES]) {
    if (!identity || !content || !signature || !id(network) || !id(sender)) return false;
    uint8_t publicKey[32], input[sizeof(LABEL) + 4 + CONTENT_BYTES];
    Ed25519::derivePublicKey(publicKey, identity + 32);
    message(network, sender, content, input);
    Ed25519::sign(signature, identity + 32, publicKey, input, sizeof(input));
    return true;
}

bool verify(const uint8_t senderEd25519[32], uint16_t network, uint16_t sender,
            const uint8_t content[CONTENT_BYTES], const uint8_t signature[SIGNATURE_BYTES]) {
    if (!senderEd25519 || !content || !signature || !id(network) || !id(sender)) return false;
    uint8_t input[sizeof(LABEL) + 4 + CONTENT_BYTES];
    message(network, sender, content, input);
    return Ed25519::verify(signature, senderEd25519, input, sizeof(input));
}
}  // namespace wici_beacon
