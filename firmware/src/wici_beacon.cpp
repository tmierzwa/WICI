// SPDX-License-Identifier: MIT
#include "wici_beacon.h"
#include "fram_record.h"

#include <Ed25519.h>
#include <string.h>

namespace wici_beacon {
namespace {
using fram_record::id;
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

bool sign(const uint8_t identity[64], const uint8_t publicKey[32], uint16_t network, uint16_t sender,
          const uint8_t content[CONTENT_BYTES], uint8_t signature[SIGNATURE_BYTES]) {
    if (!identity || !publicKey || !content || !signature || !id(network) || !id(sender)) return false;
    uint8_t input[sizeof(LABEL) + 4 + CONTENT_BYTES];
    message(network, sender, content, input);
    Ed25519::sign(signature, identity + 32, publicKey, input, sizeof(input));
    return true;
}

size_t encode(const uint8_t linkKey[32], const uint8_t identity[64], const uint8_t publicKey[32],
              uint16_t network, uint16_t sender, uint16_t sequence, const wici_route::Beacon& value,
              uint8_t* out, size_t capacity) {
    wici_link::Frame frame;
    frame.type = wici_link::Type::BEACON;
    frame.network = network;
    frame.source = sender;
    frame.destination = wici_link::BROADCAST;
    frame.sequence = sequence;
    frame.ttl = 1;
    frame.length = wici_link::BEACON_PAYLOAD;
    fram_record::put16(frame.payload, value.root);
    fram_record::put16(frame.payload + 2, value.rank);
    fram_record::put16(frame.payload + 4, value.epoch);
    fram_record::put16(frame.payload + 6, value.parent);
    frame.payload[8] = value.flags;
    memcpy(frame.payload + 9, value.epochSignature, wici_epoch::SIGNATURE_BYTES);
    return sign(identity, publicKey, network, sender, frame.payload, frame.payload + CONTENT_BYTES) ?
           wici_link::encode(linkKey, frame, out, capacity) : 0;
}

bool verify(const uint8_t senderEd25519[32], uint16_t network, uint16_t sender,
            const uint8_t content[CONTENT_BYTES], const uint8_t signature[SIGNATURE_BYTES]) {
    if (!senderEd25519 || !content || !signature || !id(network) || !id(sender)) return false;
    uint8_t input[sizeof(LABEL) + 4 + CONTENT_BYTES];
    message(network, sender, content, input);
    return Ed25519::verify(signature, senderEd25519, input, sizeof(input));
}
}  // namespace wici_beacon
