// SPDX-License-Identifier: MIT
#include "envelope.h"
#include "envelope_counter.h"
#include "envelope_replay.h"
#include "wici_destination.h"

#include <stdio.h>
#include <string.h>

#include <Crypto.h>
#include <Curve25519.h>

#include "hexstr.h"

namespace {

struct Memory : journal::Storage {
    uint8_t data[0x048000] = {};
    int writesLeft = -1;
    bool read(uint32_t at, uint8_t* out, size_t count) override {
        if (at > sizeof(data) || count > sizeof(data) - at) return false;
        memcpy(out, data + at, count);
        return true;
    }
    bool write(uint32_t at, const uint8_t* in, size_t count) override {
        if (writesLeft == 0 || at > sizeof(data) || count > sizeof(data) - at) return false;
        if (writesLeft > 0) --writesLeft;
        memcpy(data + at, in, count);
        return true;
    }
};

void hex(const char* label, const uint8_t* bytes, size_t length) {
    printf("%s=", label);
    for (size_t i = 0; i < length; ++i) printf("%02x", bytes[i]);
    putchar('\n');
}

void publicKey(const uint8_t privateKey[32], uint8_t out[32]) {
    uint8_t scalar[32];
    memcpy(scalar, privateKey, 32);
    scalar[0] &= 0xF8;
    scalar[31] = (scalar[31] & 0x7F) | 0x40;
    Curve25519::eval(out, scalar, nullptr);
    clean(scalar, sizeof(scalar));
}

bool admit(uint16_t network, uint16_t sender, uint16_t recipient,
           const uint8_t* content, size_t length, void* context) {
    if (network != 0x1234 || sender != 10 || recipient != 20 || !content || !length) return false;
    ++*static_cast<int*>(context);
    return true;
}

}  // namespace

int main(int argc, char** argv) {
    uint8_t a[32], b[32], bp[32], ap[32], ab[32], derivedAtB[32];
    for (size_t i = 0; i < 32; ++i) { a[i] = static_cast<uint8_t>(i); b[i] = static_cast<uint8_t>(i + 32); }
    publicKey(a, ap);
    publicKey(b, bp);
    if (!envelope::deriveKey(a, bp, 0x1234, 10, 20, 10, ab) ||
        !envelope::deriveKey(b, ap, 0x1234, 10, 20, 20, derivedAtB) ||
        memcmp(ab, derivedAtB, 32)) return 1;
    hex("key", ab, sizeof(ab));

    const uint8_t plain[] = {'[', '1', ',', '1', ',', '2', ']'};
    envelope::Frame frames[2];
    if (envelope::seal(ab, 10, 20, 7, plain, sizeof(plain), 236, frames) != 1) return 2;
    hex("whole", frames[0].bytes, frames[0].length);
    envelope::Part opened;
    if (!envelope::openPart(ab, frames[0].bytes, frames[0].length, opened) ||
        opened.length != sizeof(plain) || memcmp(opened.plaintext, plain, sizeof(plain))) return 3;
    for (size_t index = 0; index < frames[0].length; ++index) {
        frames[0].bytes[index] ^= 1;
        if (envelope::openPart(ab, frames[0].bytes, frames[0].length, opened)) return 4;
        for (uint8_t byte : opened.plaintext) if (byte) return 5;
        frames[0].bytes[index] ^= 1;
    }

    // A delivery proof: two counters, whole u32 only; a station never opens one (SA1 only).
    const uint8_t counters[] = {0, 0, 0, 7, 0xFF, 0xFF, 0xFF, 0xFF};
    if (envelope::seal(ab, 10, 20, 8, counters, sizeof(counters), 236, frames, envelope::TYPE_PROOF) != 1) return 33;
    hex("proof", frames[0].bytes, frames[0].length);
    if (envelope::openPart(ab, frames[0].bytes, frames[0].length, opened) ||
        envelope::seal(ab, 10, 20, 9, counters, 3, 236, frames, envelope::TYPE_PROOF) ||
        envelope::seal(ab, 10, 20, 9, counters, 0, 236, frames, envelope::TYPE_PROOF) ||
        envelope::seal(ab, 10, 20, 9, plain, sizeof(plain), 236, frames, 2)) return 34;

    uint8_t large[256];
    for (size_t i = 0; i < sizeof(large); ++i) large[i] = static_cast<uint8_t>(i);
    if (envelope::seal(ab, 10, 20, 0xFFFFFFFF, large, sizeof(large), 153, frames) != 2) return 6;
    hex("first", frames[0].bytes, frames[0].length);
    hex("second", frames[1].bytes, frames[1].length);
    for (size_t i = 0; i < 2; ++i) {
        if (frames[i].length != 153 || !envelope::openPart(ab, frames[i].bytes, frames[i].length, opened) ||
            opened.number != i + 1 || opened.length != 128 || memcmp(opened.plaintext, large + 128 * i, 128)) return 7;
    }

    envelope::ReplayWindow window, next;
    if (!window.accept(20, next) || window.started || !next.accept(19, window) ||
        window.accept(19, next) || !window.accept(84, next) || next.accept(20, window)) return 8;
    Memory memory;
    envelope::Counter counter(memory, 0);
    if (!envelope::startCounters(memory) || !counter.begin(0x1234, 10, 20, ab) ||
        envelope::sealReserved(counter, ab, 0x1234, 10, 21, plain, sizeof(plain), 236, frames) != 0 ||
        envelope::sealReserved(counter, ab, 0x1234, 10, 20, plain, sizeof(plain), 236, frames) != 1 ||
        !envelope::openPart(ab, frames[0].bytes, frames[0].length, opened) || opened.counter != 0) return 9;
    envelope::DurableReplay replay(memory, 0);
    if (!replay.begin(0x1234, 10, 20, ab) || !replay.propose(8, next) ||
        replay.current().started || !replay.commit(8)) return 10;
    envelope::DurableReplay restored(memory, 0);
    if (!restored.begin(0x1234, 10, 20, ab) || !restored.current().started ||
        restored.current().highest != 8 || restored.current().mask != 1 ||
        restored.commit(8) || !restored.commit(9)) return 11;
    if (!restored.accepted(8) || !restored.accepted(9) || restored.accepted(7)) return 18;
    if (!restored.begin(0x1234, 10, 20, ab) || restored.propose(8, next) ||
        !restored.propose(10, next) || !restored.commit(10)) return 12;
    envelope::DurableReplay wrong(memory, 0);
    uint8_t rotated[32]; memcpy(rotated, ab, 32); rotated[0] ^= 1;
    if (!wrong.begin(0x1234, 10, 21, rotated) || wrong.current().started) return 13;
    static Memory cut;
    envelope::DurableReplay interrupted(cut, 1);
    if (!interrupted.begin(0x1234, 10, 21, ab)) return 14;
    cut.writesLeft = 2;
    if (interrupted.commit(5) || interrupted.ready()) return 15;
    cut.writesLeft = -1;
    envelope::DurableReplay afterCut(cut, 1);
    if (!afterCut.begin(0x1234, 10, 21, ab) || afterCut.current().started ||
        !afterCut.commit(5)) return 16;
    uint8_t& commitByte = cut.data[envelope::REPLAY_BASE + 2 * envelope::REPLAY_SLOT_BYTES + 31];
    commitByte = 0x5A;
    envelope::DurableReplay damaged(cut, 1);
    if (damaged.begin(0x1234, 10, 21, ab)) return 31;
    commitByte = 0xA5;
    cut.data[envelope::REPLAY_BASE + 2 * envelope::REPLAY_SLOT_BYTES + 14] ^= 1;
    envelope::DurableReplay corrupt(cut, 1);
    if (corrupt.begin(0x1234, 10, 21, ab)) return 17;

    static Memory destinationMemory;
    uint8_t c[32], cp[32], peers[2][32], ifac[16], linkKey[32];
    for (uint8_t i = 0; i < 32; ++i) c[i] = static_cast<uint8_t>(i + 64);
    for (uint8_t i = 0; i < 16; ++i) ifac[i] = i;
    publicKey(c, cp);
    memcpy(peers[0], ap, 32); memcpy(peers[1], cp, 32);
    if (!wici_link::deriveKey(ifac, 0x1234, linkKey)) return 19;
    int admitted = 0;
    wici_destination::Destination destination(destinationMemory, {0x1234, 20, {10, 30}},
                                              ifac, b, peers, admit, &admitted);
    if (!destination.begin()) return 20;
    wici_link::Frame link;
    link.type = wici_link::Type::DATA; link.flags = wici_link::ACKREQ;
    link.network = 0x1234; link.source = 1; link.destination = 20;
    link.ttl = 7; link.sequence = 8;
    link.length = frames[0].length;
    memcpy(link.payload, frames[0].bytes, link.length);
    uint8_t radio[255], hack[255];
    size_t radioLength = wici_link::encode(linkKey, link, radio, sizeof(radio)), hackLength = 0;
    if (!radioLength || destination.receive(radio, radioLength, 100, hack, sizeof(hack), hackLength) !=
                        wici_destination::Outcome::HACK_READY || admitted != 1 || hackLength != 21) return 21;
    wici_destination::Destination afterRestart(destinationMemory, {0x1234, 20, {10, 30}},
                                               ifac, b, peers, admit, &admitted);
    if (!afterRestart.begin() || afterRestart.receive(radio, radioLength, 101, hack, sizeof(hack), hackLength) !=
                                 wici_destination::Outcome::HACK_READY || admitted != 1) return 22;
    if (envelope::seal(ab, 10, 20, 1, large, sizeof(large), 153, frames) != 2) return 23;
    link.sequence = 9; link.length = frames[1].length;
    memcpy(link.payload, frames[1].bytes, link.length);
    radioLength = wici_link::encode(linkKey, link, radio, sizeof(radio));
    if (afterRestart.receive(radio, radioLength, 102, hack, sizeof(hack), hackLength) !=
        wici_destination::Outcome::HACK_READY || admitted != 1) return 24;
    envelope::Frame conflictingWhole[2];
    if (envelope::seal(ab, 10, 20, 1, plain, sizeof(plain), 236, conflictingWhole) != 1) return 28;
    link.sequence = 11; link.length = conflictingWhole[0].length;
    memcpy(link.payload, conflictingWhole[0].bytes, link.length);
    size_t conflictLength = wici_link::encode(linkKey, link, radio, sizeof(radio));
    if (afterRestart.receive(radio, conflictLength, 102, hack, sizeof(hack), hackLength) !=
        wici_destination::Outcome::REJECTED || admitted != 1) return 29;
    link.source = 20;
    conflictLength = wici_link::encode(linkKey, link, radio, sizeof(radio));
    if (afterRestart.receive(radio, conflictLength, 102, hack, sizeof(hack), hackLength) !=
        wici_destination::Outcome::REJECTED || admitted != 1) return 30;
    link.source = 1;
    wici_destination::Destination afterPart(destinationMemory, {0x1234, 20, {10, 30}},
                                            ifac, b, peers, admit, &admitted);
    if (!afterPart.begin()) return 25;
    link.sequence = 10; link.length = frames[0].length;
    memcpy(link.payload, frames[0].bytes, link.length);
    radioLength = wici_link::encode(linkKey, link, radio, sizeof(radio));
    if (afterPart.receive(radio, radioLength, 103, hack, sizeof(hack), hackLength) !=
        wici_destination::Outcome::HACK_READY || admitted != 2 ||
        afterPart.receive(radio, radioLength, 104, hack, sizeof(hack), hackLength) !=
        wici_destination::Outcome::HACK_READY || admitted != 2) return 26;
    radio[radioLength - 1] ^= 1;
    if (afterPart.receive(radio, radioLength, 105, hack, sizeof(hack), hackLength) !=
        wici_destination::Outcome::IGNORED || admitted != 2) return 27;

    // Correctly encrypted envelopes with a reserved kind type, from the Python side.
    for (int i = 1; i < argc; ++i) {
        uint8_t reserved[envelope::MAX_FRAME];
        const size_t reservedLength = strlen(argv[i]) / 2;
        if (reservedLength > sizeof(reserved) || !hexstr::decode(argv[i], reserved, reservedLength) ||
            envelope::openPart(ab, reserved, reservedLength, opened)) return 32;
    }
    if (argc > 1) puts("reserved=rejected");
    return 0;
}
