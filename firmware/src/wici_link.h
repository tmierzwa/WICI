// SPDX-License-Identifier: MIT
// Authenticated WICI-Link v2 frame codec. Routing and durable HACK admission are
// separate state machines; parsing a frame alone never authorizes a HACK.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace wici_link {

constexpr uint8_t VERSION = 2;
constexpr size_t HEADER = 11;
constexpr size_t TAG = 8;               // network MAC
constexpr size_t HOP_TAG = 8;           // pairwise neighbor tag on unicast radio frames
constexpr size_t ORIGIN_SIGNATURE = 64;
constexpr size_t MAX_FRAME = 255;
constexpr size_t MAX_PAYLOAD = MAX_FRAME - HEADER - ORIGIN_SIGNATURE - TAG - HOP_TAG;
constexpr size_t RADIO_HACK = HEADER + TAG + HOP_TAG;  // HACK as transmitted
constexpr uint16_t BROADCAST = 0xFFFF;

enum class Type : uint8_t { DATA = 0, HACK = 1, BEACON = 2 };
// Local scheduler intent, never read from a radio frame's untrusted envelope header.
enum class TxClass : uint8_t { OWN, TRANSIT, CONTENDED_K2, BEACON };
constexpr uint8_t ACKREQ = 1;
constexpr uint8_t DOWN = 2;

struct Frame {
    Type type = Type::DATA;
    uint8_t flags = 0;
    uint16_t network = 0, source = 0, destination = 0, sequence = 0;
    uint8_t hops = 0, ttl = 0;
    uint8_t payload[MAX_PAYLOAD] = {};
    size_t length = 0;
    uint8_t originSignature[ORIGIN_SIGNATURE] = {};  // DATA only; preserved across hops
};

// Derive a link-only key from the 16-byte IFAC. The envelope has an unrelated key.
bool deriveKey(const uint8_t ifac[16], uint16_t netId, uint8_t out[32]);
// Writes a full LoRa frame, or returns 0 on invalid fields/capacity.
size_t encode(const uint8_t key[32], const Frame& frame, uint8_t* out, size_t capacity);
// Verifies MAC in constant time before interpreting frame fields. Clears out on failure.
bool decode(const uint8_t key[32], uint16_t netId, const uint8_t* wire, size_t size, Frame& out);
// Authenticate an incoming DATA addressed to this relay, then prepare the next
// link frame. The ciphertext is copied unchanged. Callers must reserve `seq`
// durably and select a loop-safe next hop before calling this function.
size_t forward(const uint8_t key[32], uint16_t netId, uint16_t ownId, uint16_t nextId,
               uint16_t seq, const uint8_t* wire, size_t size, uint8_t* out, size_t capacity);

}  // namespace wici_link
