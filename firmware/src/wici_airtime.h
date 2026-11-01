// SPDX-License-Identifier: MIT
// Durable numbered-link airtime caps. Charges are committed before radio admission.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "envelope_parts.h"
#include "framfs.h"
#include "journal.h"

namespace wici_airtime {

constexpr uint32_t BASE = 0x047F80;
constexpr uint32_t COPY_BYTES = 64;
constexpr uint32_t BUCKET_S = 600;
constexpr uint8_t BUCKETS = 7;  // current plus 6 older buckets: conservative 3600 s window
constexpr uint32_t POOL_CAP_MS = 3600u * 1000u * 60u / 100u;
constexpr uint32_t BEACON_CAP_MS = 3600u * 1000u * 2u / 100u;
static_assert(BASE >= envelope::PARTS_BACKUP_BASE + 2 * envelope::PARTS_COPY_BYTES,
              "airtime ledger after envelope parts");
static_assert(BASE + 2 * COPY_BYTES <= framfs::FS_BASE, "airtime ledger before FRAM FS");

class Budget {
public:
    explicit Budget(journal::Storage& storage) : storage_(storage) {}
    bool begin(uint16_t network, uint16_t own);
    // Beacon cost is TX time; transit cost includes the 12x silence debt.
    // A successful reserve is intentionally charged even if later CAD/TX fails.
    bool reserve(bool beacon, uint32_t txMs, uint32_t nowS);
    bool ready() const { return ready_; }
    uint32_t poolUsed() const;
    uint32_t beaconUsed() const;

private:
    bool commit();
    void advance(uint32_t epoch);
    journal::Storage& storage_;
    uint16_t pool_[BUCKETS] = {}, beacon_[BUCKETS] = {};  // 100 ms units, rounded up
    uint32_t sequence_ = 0, epoch_ = 0;
    uint16_t network_ = 0, own_ = 0;
    uint8_t copy_ = 1;
    bool ready_ = false;
};

}  // namespace wici_airtime
