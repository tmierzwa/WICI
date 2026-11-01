// SPDX-License-Identifier: MIT
#include "wici_hop_auth.h"
#include "fram_record.h"

#include <string.h>

#include "envelope.h"
#include "sha2.h"

namespace wici_hop_auth {
namespace {
using fram_record::get16;
constexpr size_t TAG = wici_link::HOP_TAG;
constexpr uint8_t LABEL[] = {'W','I','C','I',' ','h','o','p',' ','v','1'};
void tag(const uint8_t key[32], const uint8_t* frame, size_t length, uint8_t out[32]) {
    sha2::Hmac mac(key, 32);
    mac.update(LABEL, sizeof(LABEL));
    mac.update(frame, length);
    mac.finish(out);
}
}  // namespace

bool Auth::begin(uint16_t network, uint16_t own, const uint8_t privateKey[32],
                 const config::PriorityKey* peers, uint8_t count) {
    count_ = 0;
    network_ = own_ = 0;
    memset(keys_, 0, sizeof(keys_));
    if (!network || network == wici_link::BROADCAST || !own || own == wici_link::BROADCAST ||
        !privateKey || !peers || !count || count > config::PRIORITY_KEYS_MAX) return false;
    for (uint8_t i = 0; i < count; ++i) {
        const uint16_t peer = peers[i].station;
        if (!peer || peer == wici_link::BROADCAST || peer == own) return false;
        for (uint8_t j = 0; j < i; ++j) if (ids_[j] == peer) return false;
        uint8_t shared[32];
        const uint16_t low = own < peer ? own : peer;
        const uint16_t high = own < peer ? peer : own;
        if (!envelope::deriveKey(privateKey, peers[i].x25519, network,
                                 low, high, own, shared)) return false;
        sha2::Hmac derive(shared, sizeof(shared));
        derive.update(LABEL, sizeof(LABEL));
        derive.finish(keys_[i]);
        memset(shared, 0, sizeof(shared));
        ids_[i] = peer;
        ++count_;
    }
    network_ = network;
    own_ = own;
    return true;
}

const uint8_t* Auth::key(uint16_t peer) const {
    for (uint8_t i = 0; i < count_; ++i) if (ids_[i] == peer) return keys_[i];
    return nullptr;
}

size_t Auth::seal(const uint8_t* bare, size_t length, uint8_t* out, size_t capacity) const {
    if (!own_ || !bare || !out || length < wici_link::HEADER + wici_link::TAG ||
        length > wici_link::MAX_FRAME || get16(bare + 1) != network_ ||
        get16(bare + 3) != own_) return 0;
    const uint16_t dest = get16(bare + 5);
    const size_t extra = dest == wici_link::BROADCAST ? 0 : TAG;
    if (length + extra > capacity || length + extra > wici_link::MAX_FRAME) return 0;
    const uint8_t* peerKey = extra ? key(dest) : nullptr;
    if (extra && !peerKey) return 0;
    memcpy(out, bare, length);
    if (extra) {
        uint8_t digest[32];
        tag(peerKey, bare, length, digest);
        memcpy(out + length, digest, TAG);
        memset(digest, 0, sizeof(digest));
    }
    return length + extra;
}

bool Auth::open(const uint8_t* radio, size_t length, uint8_t* bare,
                size_t capacity, size_t& bareLength) const {
    bareLength = 0;
    if (!own_ || !radio || !bare || length < wici_link::HEADER + wici_link::TAG ||
        length > wici_link::MAX_FRAME || get16(radio + 1) != network_) return false;
    const uint16_t source = get16(radio + 3), dest = get16(radio + 5);
    if (source == own_ || (dest != own_ && dest != wici_link::BROADCAST)) return false;
    const size_t extra = dest == wici_link::BROADCAST ? 0 : TAG;
    if (length < wici_link::HEADER + wici_link::TAG + extra || length - extra > capacity) return false;
    const uint8_t* peerKey = extra ? key(source) : nullptr;
    if (extra && !peerKey) return false;
    if (extra) {
        uint8_t digest[32], mismatch = 0;
        tag(peerKey, radio, length - extra, digest);
        for (size_t i = 0; i < TAG; ++i) mismatch |= digest[i] ^ radio[length - extra + i];
        memset(digest, 0, sizeof(digest));
        if (mismatch) return false;
    }
    bareLength = length - extra;
    memcpy(bare, radio, bareLength);
    return true;
}

}  // namespace wici_hop_auth
