// SPDX-License-Identifier: MIT
// Station-side fragment admission for the comparison with the receiver's SQLite inbox in
// tests/test_envelope_cross_language.py. Each stdin line "counter number now hex" is one
// authenticated fragment from receiver 2 to station 4; the output is partial, complete,
// duplicate or rejected. The order of checks follows wici_destination.cpp.
#include <stdio.h>
#include <string.h>

#include "envelope_parts.h"
#include "envelope_replay.h"
#include "hexstr.h"

namespace {

struct Memory : journal::Storage {
    uint8_t bytes[0x048000] = {};
    bool read(uint32_t at, uint8_t* out, size_t count) override {
        if (at > sizeof(bytes) || count > sizeof(bytes) - at) return false;
        memcpy(out, bytes + at, count);
        return true;
    }
    bool write(uint32_t at, const uint8_t* in, size_t count) override {
        if (at > sizeof(bytes) || count > sizeof(bytes) - at) return false;
        memcpy(bytes + at, in, count);
        return true;
    }
};

const char* receive(envelope::DurableReplay& replay, envelope::DurableParts& parts, const envelope::Part& part,
                    uint32_t now) {
    if (replay.accepted(part.counter)) return "duplicate";
    envelope::ReplayWindow proposed;
    if (!replay.propose(part.counter, proposed)) return "rejected";
    uint8_t full[envelope::MAX_SA1];
    size_t length = 0;
    switch (parts.ingest(part, now, full, length)) {
        case envelope::FragmentResult::PARTIAL: return "partial";
        case envelope::FragmentResult::DUPLICATE: return "duplicate";
        case envelope::FragmentResult::COMPLETE:
            return replay.commit(part.counter) && parts.clear() ? "complete" : "io_error";
        case envelope::FragmentResult::REJECTED: return "rejected";
        case envelope::FragmentResult::IO_ERROR: break;
    }
    return "io_error";
}

}  // namespace

int main() {
    static Memory memory;
    const uint8_t key[32] = {1};
    envelope::DurableReplay replay(memory, 0);
    envelope::DurableParts parts(memory, 0);
    if (!replay.begin(100, 4, 2, key) || !parts.begin(100, 4, 2, key)) return 2;
    unsigned long counter, number, now;
    char hex[2 * envelope::MAX_SA1 / 2 + 1];
    while (scanf("%lu %lu %lu %256s", &counter, &number, &now, hex) == 4) {
        envelope::Part part;
        part.sender = 2; part.recipient = 4;
        part.counter = static_cast<uint32_t>(counter);
        part.number = static_cast<uint8_t>(number);
        part.length = strlen(hex) / 2;
        if (!hexstr::decode(hex, part.plaintext, part.length)) return 2;
        puts(receive(replay, parts, part, static_cast<uint32_t>(now)));
    }
    return 0;
}
