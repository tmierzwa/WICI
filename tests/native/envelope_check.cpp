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

// A station whose active receiver identity the test switches (KLUCZ ZAPASOWY).
struct Switching {
    int admitted = 0;
    bool backup = false;
};
bool admitEither(uint16_t, uint16_t, uint16_t, const uint8_t* content, size_t length, void* context) {
    if (!content || !length) return false;
    ++static_cast<Switching*>(context)->admitted;
    return true;
}
bool activeSlot(uint8_t peer, void* context) { return peer == (static_cast<Switching*>(context)->backup ? 1 : 0); }

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
    // L7/E3: a frame this station can never admit gets a HACK from a relay (no proof), none from the root.
    if (afterRestart.receive(radio, conflictLength, 106, hack, sizeof(hack), hackLength) !=  // allowance used at 101
        wici_destination::Outcome::SETTLED || admitted != 1 || hackLength != 21) return 29;
    wici_destination::Destination fromRoot(destinationMemory, {0x1234, 20, {10, 30}, 1},
                                           ifac, b, peers, admit, &admitted);
    if (!fromRoot.begin() || fromRoot.receive(radio, conflictLength, 110, hack, sizeof(hack), hackLength) !=
        wici_destination::Outcome::REJECTED || hackLength != 0) return 35;
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
    // Each permanent refusal from a relay: settled with a HACK, nothing admitted. Spaced by the 5 s allowance.
    const auto refused = [&](const envelope::Frame& envelopeFrame, uint32_t nowS, uint8_t tweak) {
        link.sequence = static_cast<uint16_t>(link.sequence + 1); link.length = envelopeFrame.length;
        memcpy(link.payload, envelopeFrame.bytes, link.length);
        if (tweak == 1) link.payload[2] = 11;                  // unknown receiver identity
        if (tweak == 2) link.payload[link.length / 2] ^= 1;    // envelope MAC fails
        const size_t n = wici_link::encode(linkKey, link, radio, sizeof(radio));
        return afterPart.receive(radio, n, nowS, hack, sizeof(hack), hackLength);
    };
    envelope::Frame single[2];
    if (envelope::seal(ab, 10, 20, 1000, plain, sizeof(plain), 236, single) != 1 ||
        refused(single[0], 110, 0) != wici_destination::Outcome::HACK_READY || admitted != 3) return 36;
    if (envelope::seal(ab, 10, 20, 900, plain, sizeof(plain), 236, single) != 1 ||
        refused(single[0], 120, 0) != wici_destination::Outcome::SETTLED || admitted != 3) return 37;  // below the window
    if (refused(single[0], 121, 0) != wici_destination::Outcome::REJECTED) return 38;  // repeat allowance used
    if (envelope::seal(ab, 10, 20, 1001, plain, sizeof(plain), 236, single) != 1 ||
        refused(single[0], 130, 1) != wici_destination::Outcome::SETTLED ||
        refused(single[0], 140, 2) != wici_destination::Outcome::SETTLED || admitted != 3) return 39;
    if (envelope::seal(ab, 10, 20, 1002, counters, 4, 236, single, envelope::TYPE_PROOF) != 1 ||
        refused(single[0], 150, 0) != wici_destination::Outcome::SETTLED || admitted != 3) return 40;  // proofs go up only
    // A part of another counter while one waits may be admitted later: no HACK, the relay retries.
    envelope::Frame halves[2], others[2];
    if (envelope::seal(ab, 10, 20, 1003, large, sizeof(large), 153, halves) != 2 ||
        envelope::seal(ab, 10, 20, 1004, large, sizeof(large), 153, others) != 2 ||
        refused(halves[0], 160, 0) != wici_destination::Outcome::HACK_READY ||
        refused(others[0], 170, 0) != wici_destination::Outcome::REJECTED || hackLength != 0) return 41;

    // E4: SA1 admission and the replay window are two writes. Power lost after each FRAM write of the
    // resolving part: the retry after restart still resolves the message, admitted at least once
    // (the station's SA1 admission is idempotent), and is never lost.
    const auto crashWindow = [&](const envelope::Frame* parts, size_t count) {
        // The station's SA1 transaction is a FRAM write too: after the cut it fails like the window.
        static Memory crash;
        struct Count { int times = 0; } count_;
        const wici_destination::AdmitFn durable = [](uint16_t, uint16_t, uint16_t, const uint8_t*, size_t, void* c) {
            const uint8_t mark = 1;
            if (!crash.write(sizeof(crash.data) - 1, &mark, 1)) return false;
            ++static_cast<Count*>(c)->times;
            return true;
        };
        bool betweenWrites = false;
        for (int cut = 0;; ++cut) {
            memset(crash.data, 0, sizeof(crash.data));
            crash.writesLeft = -1;
            count_ = Count();
            int& times = count_.times;
            wici_destination::Destination before(crash, {0x1234, 20, {10, 30}}, ifac, b, peers, durable, &count_);
            if (!before.begin()) return 1;
            uint32_t nowS = 200;
            const auto send = [&](wici_destination::Destination& d, size_t i, wici_destination::Resolved& resolved) {
                link.sequence = static_cast<uint16_t>(link.sequence + 1); link.length = parts[i].length;
                memcpy(link.payload, parts[i].bytes, link.length);
                const size_t n = wici_link::encode(linkKey, link, radio, sizeof(radio));
                return d.receive(radio, n, nowS += 10, hack, sizeof(hack), hackLength, &resolved);
            };
            wici_destination::Resolved resolved;
            for (size_t i = 0; i + 1 < count; ++i)
                if (send(before, i, resolved) != wici_destination::Outcome::HACK_READY) return 2;
            crash.writesLeft = cut;
            const auto first = send(before, count - 1, resolved);
            const bool uncut = crash.writesLeft > 0;
            crash.writesLeft = -1;
            if (uncut) return first == wici_destination::Outcome::HACK_READY && resolved.valid && times == 1 &&
                              betweenWrites ? 0 : 3;
            if (resolved.valid != (first == wici_destination::Outcome::HACK_READY) || times > 1) return 4;
            const bool proved = resolved.valid;
            wici_destination::Destination after(crash, {0x1234, 20, {10, 30}}, ifac, b, peers, durable, &count_);
            if (!after.begin() || send(after, count - 1, resolved) != wici_destination::Outcome::HACK_READY) return 5;
            // A message resolved before the cut is a repeat now: its proof was lost with the RAM list,
            // and the receiver's resend under a new counter proves it (wici-link.md, dowód doręczenia).
            if (proved ? resolved.valid || times != 1 : !resolved.valid || times < 1) return 6;
            if (times == 2) betweenWrites = true;
        }
    };
    envelope::Frame whole[2];
    if (envelope::seal(ab, 10, 20, 2000, plain, sizeof(plain), 236, whole) != 1 || crashWindow(whole, 1)) return 42;
    if (envelope::seal(ab, 10, 20, 2001, large, sizeof(large), 153, halves) != 2 || crashWindow(halves, 2)) return 43;

    // The receiver identity the station does not use yet (the backup before KLUCZ ZAPASOWY) and no longer
    // (the main one after it): no SA1 effect, no replay window, no proof; a relay gets its HACK, the root none.
    static Memory switchMemory;
    Switching station;
    wici_destination::Destination switching(switchMemory, {0x1234, 20, {10, 30}, 2}, ifac, b, peers,
                                            admitEither, &station);
    switching.setActive(activeSlot);
    uint8_t backupKey[32];
    if (!switching.begin() || !envelope::deriveKey(c, bp, 0x1234, 30, 20, 30, backupKey)) return 44;
    const auto deliver = [&](const uint8_t* key, uint16_t sender, uint32_t counter, uint16_t from, uint32_t nowS,
                             wici_destination::Resolved& resolved) {
        envelope::Frame one[2];
        if (envelope::seal(key, sender, 20, counter, plain, sizeof(plain), 236, one) != 1)
            return wici_destination::Outcome::IGNORED;
        link.source = from; link.sequence = static_cast<uint16_t>(link.sequence + 1); link.length = one[0].length;
        memcpy(link.payload, one[0].bytes, link.length);
        const size_t n = wici_link::encode(linkKey, link, radio, sizeof(radio));
        return switching.receive(radio, n, nowS, hack, sizeof(hack), hackLength, &resolved);
    };
    wici_destination::Resolved resolved;
    if (deliver(backupKey, 30, 1, 1, 200, resolved) != wici_destination::Outcome::SETTLED ||
        hackLength != 21 || station.admitted != 0 || resolved.valid) return 45;
    if (deliver(backupKey, 30, 1, 2, 206, resolved) != wici_destination::Outcome::REJECTED ||
        hackLength != 0 || station.admitted != 0 || resolved.valid) return 46;
    station.backup = true;   // the same counter after the switch: nothing of it was kept
    if (deliver(backupKey, 30, 1, 2, 212, resolved) != wici_destination::Outcome::HACK_READY ||
        station.admitted != 1 || !resolved.valid || resolved.peer != 1) return 47;
    if (deliver(ab, 10, 3000, 1, 218, resolved) != wici_destination::Outcome::SETTLED ||
        station.admitted != 1 || resolved.valid) return 48;
    link.source = 1;

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
