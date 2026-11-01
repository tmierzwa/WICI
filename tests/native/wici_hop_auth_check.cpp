// SPDX-License-Identifier: MIT
#include <assert.h>
#include <string.h>

#include <Curve25519.h>
#include "wici_hop_auth.h"
#include "wici_link.h"

int main() {
    uint8_t a[32] = {}, b[32] = {}, aPublic[32], bPublic[32];
    a[0] = 9; b[0] = 17;
    a[0] &= 0xF8; a[31] = (a[31] & 0x7F) | 0x40;
    b[0] &= 0xF8; b[31] = (b[31] & 0x7F) | 0x40;
    Curve25519::eval(aPublic, a, nullptr);
    Curve25519::eval(bPublic, b, nullptr);
    config::PriorityKey aPeer, bPeer;
    aPeer.station = 2; memcpy(aPeer.x25519, bPublic, 32);
    bPeer.station = 1; memcpy(bPeer.x25519, aPublic, 32);
    wici_hop_auth::Auth sender, receiver;
    assert(sender.begin(100, 1, a, &aPeer, 1));
    assert(receiver.begin(100, 2, b, &bPeer, 1));
    uint8_t groupKey[32], bare[255], radio[255], opened[255];
    uint8_t ifac[16] = {};
    assert(wici_link::deriveKey(ifac, 100, groupKey));
    wici_link::Frame frame;
    frame.type = wici_link::Type::HACK; frame.network = 100;
    frame.source = 1; frame.destination = 2; frame.sequence = 7; frame.ttl = 1;
    const size_t bareLength = wici_link::encode(groupKey, frame, bare, sizeof(bare));
    assert(bareLength == 19);
    size_t radioLength = sender.seal(bare, bareLength, radio, sizeof(radio));
    assert(radioLength == bareLength + wici_link::HOP_TAG && radioLength == wici_link::RADIO_HACK);
    size_t openedLength = 0;
    assert(receiver.open(radio, radioLength, opened, sizeof(opened), openedLength));
    assert(openedLength == bareLength && !memcmp(opened, bare, bareLength));
    radio[8] ^= 1;
    assert(!receiver.open(radio, radioLength, opened, sizeof(opened), openedLength));
    radio[8] ^= 1;
    frame.sequence = 8;
    assert(wici_link::encode(groupKey, frame, bare, sizeof(bare)) == bareLength);
    memcpy(radio, bare, bareLength);  // attacker knows the group key, not the pairwise key
    assert(!receiver.open(radio, radioLength, opened, sizeof(opened), openedLength));
    frame.sequence = 7;
    assert(wici_link::encode(groupKey, frame, bare, sizeof(bare)) == bareLength);
    assert(sender.seal(bare, bareLength, radio, sizeof(radio)) == radioLength);
    radio[3] = 0; radio[4] = 3;
    assert(!receiver.open(radio, radioLength, opened, sizeof(opened), openedLength));
    radio[4] = 1;
    assert(!receiver.open(bare, bareLength, opened, sizeof(opened), openedLength));
    frame.destination = wici_link::BROADCAST;
    frame.type = wici_link::Type::BEACON; frame.length = wici_link::BEACON_PAYLOAD;
    radioLength = wici_link::encode(groupKey, frame, bare, sizeof(bare));
    assert(radioLength);
    assert(sender.seal(bare, radioLength, radio, sizeof(radio)) == radioLength);
    assert(receiver.open(radio, radioLength, opened, sizeof(opened), openedLength));
    assert(openedLength == radioLength);
}
