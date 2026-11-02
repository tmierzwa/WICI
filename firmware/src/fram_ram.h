// SPDX-License-Identifier: MIT
// FRAM image in RAM for a board without FRAM (board_xiao.h: WICI_FRAM_PSRAM, 512 KiB in PSRAM). It is a
// journal::Storage like fram::Memory, so the journal, store, Reticulum tables and WICI-Link state use the
// same 4 Mbit map. The image is volatile: PSRAM keeps it across a software restart (REBOOT, role change,
// destroy, watchdog) but not across a power cycle, after which the station starts as new (new identity,
// no configuration). It is never mirrored to flash: silence-debt and clock records alone would wear it out.
// A 16 B marker in front of the image tells a kept image from power-on content or a block that the heap
// placed elsewhere; without it the image is cleared to 0x00 (blank, like a new chip). Every write is
// handed to `sync` (PSRAM: cache write-back), so a restart cannot lose a write the journal already counted.
// No Arduino dependency: checked on the host (tests/test_firmware_host.py).
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "fram_id.h"
#include "journal.h"

namespace fram {

class RamMemory : public journal::Storage {
public:
    static constexpr bool VOLATILE = true;  // INFO fram_volatile, FRAM volatile
    static constexpr size_t MARKER = 16;
    static constexpr size_t BLOCK = MARKER + SIZE;  // bytes to allocate for begin()

    explicit RamMemory(void (*sync)(const void* data, size_t count) = nullptr) : sync_(sync) {}

    // block: BLOCK bytes or nullptr (allocation failed: identify() reports no memory).
    void begin(uint8_t* block) {
        block_ = block;
        kept_ = block && !memcmp(block, MARK, MARKER);
        if (!block || kept_) return;
        memset(block + MARKER, 0, SIZE);
        flush(block + MARKER, SIZE);
        memcpy(block, MARK, MARKER);  // marker last: an image is kept only when fully cleared
        flush(block, MARKER);
    }
    bool kept() const { return kept_; }  // the image survived from before this start

    Id identify() const {
        Id id{};
        id.part = block_ ? Part::EMULATED : Part::UNKNOWN;
        return id;
    }

    bool read(uint32_t address, uint8_t* data, size_t count) override {
        if (!inside(address, count)) return false;
        memcpy(data, block_ + MARKER + address, count);
        return true;
    }

    bool write(uint32_t address, const uint8_t* data, size_t count) override {
        if (!inside(address, count)) return false;
        uint8_t* at = block_ + MARKER + address;
        memcpy(at, data, count);
        flush(at, count);
        return true;
    }

private:
    static constexpr uint8_t MARK[MARKER] = {'W', 'I', 'C', 'I', ' ', 'F', 'R', 'A', 'M', ' ', 'i', 'm', 'a', 'g', 'e', 1};

    bool inside(uint32_t address, size_t count) const { return block_ && address <= SIZE && count <= SIZE - address; }
    void flush(const void* data, size_t count) {
        if (sync_) sync_(data, count);
    }

    void (*sync_)(const void*, size_t);
    uint8_t* block_ = nullptr;
    bool kept_ = false;
};

}  // namespace fram
