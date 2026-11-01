// SPDX-License-Identifier: MIT
#include "envelope.h"

#include <string.h>

#include <ChaChaPoly.h>
#include <Crypto.h>
#include <Curve25519.h>

#include "envelope_counter.h"
#include "fram_record.h"

namespace envelope {
namespace {
using namespace fram_record;

constexpr uint8_t VERSION = 1;
constexpr uint8_t LABEL[] = {'W', 'I', 'C', 'I', ' ', 'e', 'n', 'v', ' ', 'v', '1'};

void nonce(const uint8_t header[HEADER], uint8_t out[12]) {
    memcpy(out, header + 1, 4);
    out[4] = header[0];
    memset(out + 5, 0, 3);
    memcpy(out + 8, header + 5, 4);
}

}  // namespace

bool deriveKey(const uint8_t privateKey[32], const uint8_t peerPublic[32], uint16_t netId,
               uint16_t sender, uint16_t recipient, uint16_t ownId, uint8_t out[32]) {
    if (!privateKey || !peerPublic || !out || !id(netId) || !id(sender) || !id(recipient) ||
        sender == recipient || (ownId != sender && ownId != recipient)) return false;
    uint8_t scalar[32], publicKey[32], shared[32];
    memcpy(scalar, privateKey, 32);
    scalar[0] &= 0xF8;
    scalar[31] = (scalar[31] & 0x7F) | 0x40;
    Curve25519::eval(publicKey, scalar, nullptr);
    Curve25519::eval(shared, scalar, peerPublic);
    clean(scalar, sizeof(scalar));
    uint8_t any = 0;
    for (uint8_t byte : shared) any |= byte;
    if (!any) {
        clean(publicKey, sizeof(publicKey));
        clean(shared, sizeof(shared));
        return false;
    }
    uint8_t info[sizeof(LABEL) + 4 + 64];
    memcpy(info, LABEL, sizeof(LABEL));
    put16(info + sizeof(LABEL), sender);
    put16(info + sizeof(LABEL) + 2, recipient);
    uint8_t* senderPublic = info + sizeof(LABEL) + 4;
    uint8_t* recipientPublic = senderPublic + 32;
    memcpy(senderPublic, ownId == sender ? publicKey : peerPublic, 32);
    memcpy(recipientPublic, ownId == recipient ? publicKey : peerPublic, 32);
    uint8_t salt[3];
    put16(salt, netId);
    salt[2] = 1;
    sha2::hkdf(salt, sizeof(salt), shared, sizeof(shared), info, sizeof(info), out);
    clean(publicKey, sizeof(publicKey));
    clean(shared, sizeof(shared));
    clean(info, sizeof(info));
    return true;
}

size_t seal(const uint8_t key[32], uint16_t sender, uint16_t recipient, uint32_t counter,
            const uint8_t* plaintext, size_t length, size_t maxPayload, Frame out[2]) {
    if (!key || !out || (!plaintext && length) || length > MAX_SA1 || maxPayload < MIN_PAYLOAD ||
        !id(sender) || !id(recipient) || sender == recipient) return 0;
    // MIN_PAYLOAD fits a 128-byte half, so two parts always suffice.
    const size_t count = length + OVERHEAD <= maxPayload ? 1 : 2;
    const size_t first = count == 1 ? length : (length + 1) / 2;
    Frame local[2];
    for (size_t i = 0; i < count; ++i) {
        const size_t offset = i == 0 ? 0 : first;
        const size_t partLength = i == 0 ? first : length - first;
        Frame& frame = local[i];
        frame.bytes[0] = static_cast<uint8_t>((VERSION << 6) | ((count == 1 ? 0 : i + 1) << 4) | TYPE_SA1);
        put16(frame.bytes + 1, sender);
        put16(frame.bytes + 3, recipient);
        put32(frame.bytes + 5, counter);
        uint8_t iv[12];
        nonce(frame.bytes, iv);
        ChaChaPoly cipher;
        if (!cipher.setKey(key, 32) || !cipher.setIV(iv, sizeof(iv))) return 0;
        cipher.addAuthData(frame.bytes, HEADER);
        cipher.encrypt(frame.bytes + HEADER, partLength ? plaintext + offset : nullptr, partLength);
        cipher.computeTag(frame.bytes + HEADER + partLength, TAG);
        cipher.clear();
        frame.length = partLength + OVERHEAD;
    }
    for (size_t i = 0; i < count; ++i) out[i] = local[i];
    return count;
}

size_t sealReserved(Counter& counter, const uint8_t key[32], uint16_t netId, uint16_t sender,
                    uint16_t recipient, const uint8_t* plaintext, size_t length, size_t maxPayload,
                    Frame out[2]) {
    if (!counter.outgoing(netId, sender, recipient, key) || !out || (!plaintext && length) ||
        length > MAX_SA1 || maxPayload < MIN_PAYLOAD) return 0;
    uint32_t value;
    if (!counter.next(value)) return 0;
    return seal(key, sender, recipient, value, plaintext, length, maxPayload, out);
}

bool openPart(const uint8_t key[32], const uint8_t* frame, size_t length, Part& out) {
    out = Part();
    if (!key || !frame || length < OVERHEAD || length > MAX_FRAME) return false;
    const uint8_t kind = frame[0];
    const uint8_t part = static_cast<uint8_t>((kind >> 4) & 3);
    const uint16_t sender = get16(frame + 1), recipient = get16(frame + 3);
    if (kind >> 6 != VERSION || part == 3 || (kind & 15) != TYPE_SA1 ||
        !id(sender) || !id(recipient) || sender == recipient) return false;
    const size_t bodyLength = length - OVERHEAD;
    if (part && bodyLength > MAX_SA1 / 2) return false;
    uint8_t iv[12];
    nonce(frame, iv);
    ChaChaPoly cipher;
    if (!cipher.setKey(key, 32) || !cipher.setIV(iv, sizeof(iv))) return false;
    cipher.addAuthData(frame, HEADER);
    Part proposed;
    cipher.decrypt(proposed.plaintext, frame + HEADER, bodyLength);
    const bool valid = cipher.checkTag(frame + HEADER + bodyLength, TAG);
    cipher.clear();
    if (!valid) { clean(proposed.plaintext, sizeof(proposed.plaintext)); return false; }
    proposed.sender = sender;
    proposed.recipient = recipient;
    proposed.counter = get32(frame + 5);
    proposed.number = part;
    proposed.length = bodyLength;
    out = proposed;
    clean(proposed.plaintext, sizeof(proposed.plaintext));
    return true;
}

}  // namespace envelope
