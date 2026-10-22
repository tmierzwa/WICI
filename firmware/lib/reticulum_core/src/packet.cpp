// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
#include "packet.h"

#include <string.h>

#include <SHA256.h>

namespace rnscore {

bool unpack(const uint8_t* raw, size_t length, Packet& out) {
    if (length < 2 || raw[1] >= MAX_HOPS) return false;
    const uint8_t flags = raw[0];
    out.headerType = static_cast<HeaderType>((flags >> 6) & 0x01);
    out.contextFlag = (flags >> 5) & 0x01;
    out.transportType = static_cast<TransportType>((flags >> 4) & 0x01);
    out.destinationType = static_cast<DestinationType>((flags >> 2) & 0x03);
    out.packetType = static_cast<PacketType>(flags & 0x03);
    out.hops = raw[1];

    const size_t header = out.headerType == HEADER_2 ? HEADER_2_SIZE : HEADER_1_SIZE;
    if (length <= header) return false;   // Python: brak pola, potem "Zero-length data field"
    const uint8_t* p = raw + 2;
    if (out.headerType == HEADER_2) {
        memcpy(out.transportId, p, TRUNCATED_HASH_SIZE);
        p += TRUNCATED_HASH_SIZE;
    } else {
        memset(out.transportId, 0, TRUNCATED_HASH_SIZE);
    }
    memcpy(out.destinationHash, p, TRUNCATED_HASH_SIZE);
    out.context = p[TRUNCATED_HASH_SIZE];
    out.data = raw + header;
    out.dataLength = length - header;
    return true;
}

size_t pack(const Packet& packet, uint8_t* out, size_t capacity) {
    const size_t header = packet.headerType == HEADER_2 ? HEADER_2_SIZE : HEADER_1_SIZE;
    const size_t length = header + packet.dataLength;
    if (packet.hops >= MAX_HOPS || packet.dataLength == 0 || packet.context == CONTEXT_LRPROOF || length > MTU ||
        length > capacity) {
        return 0;
    }
    // RNS/Packet.py: get_packed_flags.
    out[0] = static_cast<uint8_t>((packet.headerType & 0x01) << 6 | (packet.contextFlag & 0x01) << 5 |
                                  (packet.transportType & 0x01) << 4 | (packet.destinationType & 0x03) << 2 |
                                  (packet.packetType & 0x03));
    out[1] = packet.hops;
    uint8_t* p = out + 2;
    if (packet.headerType == HEADER_2) {
        memcpy(p, packet.transportId, TRUNCATED_HASH_SIZE);
        p += TRUNCATED_HASH_SIZE;
    }
    memcpy(p, packet.destinationHash, TRUNCATED_HASH_SIZE);
    p[TRUNCATED_HASH_SIZE] = packet.context;
    memcpy(out + header, packet.data, packet.dataLength);
    return length;
}

void packetHash(const uint8_t* raw, size_t length, uint8_t out[HASH_SIZE]) {
    const size_t skip = (raw[0] & 0x40) ? 2 + TRUNCATED_HASH_SIZE : 2;
    const uint8_t flags = raw[0] & 0x0F;
    SHA256 sha;
    sha.update(&flags, 1);
    sha.update(raw + skip, length - skip);
    sha.finalize(out, HASH_SIZE);
}

}  // namespace rnscore
