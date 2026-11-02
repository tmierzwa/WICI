// SPDX-License-Identifier: MIT
#include "wici_epoch.h"
#include "fram_record.h"

#include <Ed25519.h>

namespace wici_epoch {
namespace {
using namespace fram_record;
constexpr uint8_t LABEL[] = {'W','I','C','I',' ','r','o','o','t',' ','e','p','o','c','h',' ','v','1'};
void message(uint16_t network, uint16_t root, uint16_t epoch, uint8_t out[sizeof(LABEL) + 6]) {
    memcpy(out, LABEL, sizeof(LABEL));
    put16(out + sizeof(LABEL), network);
    put16(out + sizeof(LABEL) + 2, root);
    put16(out + sizeof(LABEL) + 4, epoch);
}
}  // namespace

bool sign(const uint8_t privateKey[64], const uint8_t publicKey[32], uint16_t network, uint16_t root,
          uint16_t epoch, uint8_t signature[SIGNATURE_BYTES]) {
    if (!privateKey || !publicKey || !signature || !id(network) || !id(root)) return false;
    uint8_t input[sizeof(LABEL) + 6];
    message(network, root, epoch, input);
    Ed25519::sign(signature, privateKey + 32, publicKey, input, sizeof(input));
    return true;
}

bool verify(const uint8_t rootEd25519[32], uint16_t network, uint16_t root,
            uint16_t epoch, const uint8_t signature[SIGNATURE_BYTES]) {
    if (!rootEd25519 || !signature || !id(network) || !id(root)) return false;
    uint8_t input[sizeof(LABEL) + 6];
    message(network, root, epoch, input);
    return Ed25519::verify(signature, rootEd25519, input, sizeof(input));
}
}  // namespace wici_epoch
