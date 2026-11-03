// SPDX-License-Identifier: MIT
// Authenticated WICI-Link v3 frame codec. Routing and durable HACK admission are
// separate state machines; parsing a frame alone never authorizes a HACK.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace wici_link {

constexpr uint8_t VERSION = 3;  // v3: DATA without the v2 origin signature
constexpr size_t HEADER = 11;
constexpr size_t TAG = 8;               // network MAC
constexpr size_t HOP_TAG = 8;           // pairwise neighbor tag on unicast radio frames
constexpr size_t MAX_FRAME = 255;
constexpr size_t MAX_PAYLOAD = MAX_FRAME - HEADER - TAG - HOP_TAG;  // 228 B envelope
// A HACK repeats the first bytes of the acknowledged DATA's network MAC: after
// the 16-bit seq wraps, a recorded HACK for an older frame no longer matches
// (wici-link.md, rule 2). Two bytes keep the HACK in the same LoRa symbols.
constexpr size_t HACK_ECHO = 2;
constexpr size_t RADIO_HACK = HEADER + HACK_ECHO + TAG + HOP_TAG;  // HACK as transmitted
// BEACON payload: root, rank, epoch, parent (u16 each), flags, the root's
// epoch signature, then the sender's signature over the preceding bytes.
constexpr size_t BEACON_SIGNED = 9 + 64;
constexpr size_t BEACON_PAYLOAD = BEACON_SIGNED + 64;
constexpr size_t BEACON_FRAME = HEADER + BEACON_PAYLOAD + TAG;  // 156 B on air, no pairwise tag
constexpr uint16_t BROADCAST = 0xFFFF;
constexpr uint32_t HACK_WAIT_MS = 600;  // a sender waits this long for the HACK after its TX

enum class Type : uint8_t { DATA = 0, HACK = 1, BEACON = 2 };
// Local scheduler intent, never read from a radio frame's untrusted envelope header.
enum class TxClass : uint8_t { OWN, TRANSIT, CONTENDED_K2, BEACON };
// Radio side of a WICI node; the caller applies silence, CAD and airtime debt.
struct Air {
    virtual ~Air() = default;
    // true means the bare frame was accepted for transmission; the caller's
    // onTxDone() later reports whether it actually went out.
    virtual bool sendData(const uint8_t* frame, size_t length, TxClass traffic) = 0;
    // Without side effects: would sendData() now accept a frame of this class
    // that has `radioLength` bytes on air (with the pairwise tag on unicast)?
    // Silence, a busy radio and the airtime budget are checked. A caller asks
    // before it reserves a seq or signs a BEACON the radio would refuse;
    // sendData() still decides.
    virtual bool accepts(TxClass traffic, size_t radioLength) = 0;
    // Synchronous: true only if the HACK was transmitted within its deadline.
    virtual bool sendHack(const uint8_t* frame, size_t length, uint32_t receivedMs) = 0;
};
constexpr uint8_t ACKREQ = 1;
constexpr uint8_t DOWN = 2;

constexpr uint32_t REPEAT_HACK_S = 5;

// A HACK for a copy that was already admitted costs airtime and 12x silence
// debt, and a keyless listener can replay captured frames verbatim. Such
// repeated HACKs are limited to one per REPEAT_HACK_S per node.
class RepeatHack {
public:
    bool allow(uint32_t nowS) {
        if (sent_ && nowS >= lastS_ && nowS - lastS_ < REPEAT_HACK_S) return false;
        sent_ = true;
        lastS_ = nowS;
        return true;
    }
    void reset() { sent_ = false; }

private:
    uint32_t lastS_ = 0;
    bool sent_ = false;
};

struct Frame {
    Type type = Type::DATA;
    uint8_t flags = 0;
    uint16_t network = 0, source = 0, destination = 0, sequence = 0;
    uint8_t hops = 0, ttl = 0;
    uint8_t payload[MAX_PAYLOAD] = {};
    size_t length = 0;
};

// Derive a link-only key from the 16-byte IFAC. The envelope has an unrelated key.
bool deriveKey(const uint8_t ifac[16], uint16_t netId, uint8_t out[32]);
// Writes a full LoRa frame, or returns 0 on invalid fields/capacity.
size_t encode(const uint8_t key[32], const Frame& frame, uint8_t* out, size_t capacity);
// Verifies MAC in constant time before interpreting frame fields. Clears out on failure.
bool decode(const uint8_t key[32], uint16_t netId, const uint8_t* wire, size_t size, Frame& out);
// HACK from the frame's addressee to its link sender, echoing its sequence.
// `echo` is macEcho() of the bare DATA frame being acknowledged.
size_t encodeHack(const uint8_t key[32], const Frame& data, uint16_t echo, uint8_t* out, size_t capacity);
// The first HACK_ECHO bytes of a bare frame's network MAC (0 for a frame shorter than a MAC).
uint16_t macEcho(const uint8_t* bare, size_t length);
// The echo a decoded HACK carries.
inline uint16_t hackEcho(const Frame& hack) {
    return static_cast<uint16_t>((hack.payload[0] << 8) | hack.payload[1]);
}
// Authenticate an incoming DATA addressed to this relay, then prepare the next
// link frame. The ciphertext is copied unchanged. Callers must reserve `seq`
// durably and select a loop-safe next hop before calling this function.
size_t forward(const uint8_t key[32], uint16_t netId, uint16_t ownId, uint16_t nextId,
               uint16_t seq, const uint8_t* wire, size_t size, uint8_t* out, size_t capacity);

}  // namespace wici_link
