// SPDX-License-Identifier: MIT
#include "cells.h"

namespace cells {

namespace {
constexpr uint64_t UWMS_PER_UWH = 3600000;   // 1 µWh = 3600 µW·s
constexpr uint16_t SAVE_STEP_MV = 50;        // zmiana napięcia, od której stan idzie do FRAM bez zużycia energii
}  // namespace

uint32_t Estimator::inputUw(uint32_t awakeMs, uint32_t sleptMs, uint32_t txMs, uint16_t meanMv) {
    const uint64_t totalMs = static_cast<uint64_t>(awakeMs) + sleptMs;
    if (!totalMs) return 0;
    if (txMs > totalMs) txMs = static_cast<uint32_t>(totalMs);
    // Średni prąd szyny 3,3 V [µA]: MCU według udziału uśpienia, radio w odbiorze, w nadawaniu zamiast odbioru.
    const uint64_t mcuUa = (static_cast<uint64_t>(awakeMs) * AWAKE_UA + static_cast<uint64_t>(sleptMs) * SLEEP_UA) / totalMs;
    const uint64_t txUa = static_cast<uint64_t>(txMs) * (RADIO_TX_UA - RADIO_RX_UA) / totalMs;
    const uint64_t railUa = mcuUa + RADIO_RX_UA + OTHER_UA + txUa;
    const uint64_t railUw = railUa * RAIL_MV / 1000;
    // Wejście przetwornicy, potem dioda ogniw: ogniwa dają V × I, a przetwornica dostaje (V − spadek) × I.
    const uint64_t converterUw = railUw * 100 / EFFICIENCY_PERCENT;
    const uint32_t mv = meanMv > DIODE_MV + 1000 ? meanMv : DIODE_MV + 1000;
    return static_cast<uint32_t>(converterUw * mv / (mv - DIODE_MV));
}

void Estimator::begin(const Saved& saved) {
    if (!saved.valid) return;
    usedUwh_ = saved.usedUwh;
    lastMv_ = storedMv_ = saved.lastMv;
    lastOnCells_ = saved.lastOnCells;
}

bool Estimator::update(uint32_t awakeMs, uint32_t sleptMs, uint32_t txMs, uint16_t lastMv, uint16_t meanMv, bool onCells) {
    const bool first = !started_;
    started_ = true;
    const bool present = lastMv >= ABSENT_MV;
    bool save = false;
    // Nowy komplet: skok napięcia po starcie albo po przerwie bez ogniw (opis w cells.h). Zapisane pod obciążeniem,
    // a teraz bez niego: skok niczego nie dowodzi, więc rozstrzyga pierwszy pomiar z ogniw (pending_).
    if (present && (first || absent_ || pending_) && lastMv_) {
        const bool step = lastMv >= lastMv_ + FRESH_STEP_MV;
        pending_ = lastOnCells_ && !onCells && step;
        if (step && !pending_) {
            usedUwh_ = 0;
            remainderUwms_ = 0;
            ++freshSets_;
            save = true;
        }
    }
    absent_ = !present;
    if (onCells && present) {
        const uint32_t uw = inputUw(awakeMs, sleptMs, txMs, meanMv);
        const uint64_t ms = static_cast<uint64_t>(awakeMs) + sleptMs;
        if (ms && uw) {
            remainderUwms_ += static_cast<uint64_t>(uw) * ms;
            const uint64_t add = remainderUwms_ / UWMS_PER_UWH;
            remainderUwms_ -= add * UWMS_PER_UWH;
            usedUwh_ = usedUwh_ + add > CAPACITY_UWH * 2ULL ? CAPACITY_UWH * 2 : static_cast<uint32_t>(usedUwh_ + add);
            if (!averageUw_) averageUw_ = uw;
            else averageUw_ = static_cast<uint32_t>((static_cast<uint64_t>(averageUw_) * (AVERAGE_WEIGHT - 1) + uw) / AVERAGE_WEIGHT);
            save = true;
        }
    }
    if (present && !pending_) {   // w oczekiwaniu zostaje napięcie spod obciążenia
        const uint16_t diff = lastMv > storedMv_ ? lastMv - storedMv_ : storedMv_ - lastMv;
        if (diff >= SAVE_STEP_MV || onCells != lastOnCells_ || !storedMv_) save = true;
        lastMv_ = lastMv;
        lastOnCells_ = onCells;
    }
    if (save) storedMv_ = lastMv_;
    return save;
}

Saved Estimator::saved() const {
    Saved s;
    s.valid = true;
    s.usedUwh = usedUwh_;
    s.lastMv = lastMv_;
    s.lastOnCells = lastOnCells_;
    return s;
}

uint32_t Estimator::hours(bool replaceCells) const {
    if (!known()) return 0;
    if (replaceCells) return 1;   // „WYMIEŃ OGNIWA W CIĄGU 1 H”
    const uint32_t left = usedUwh_ < CAPACITY_UWH ? CAPACITY_UWH - usedUwh_ : 0;
    const uint32_t h = left / averageUw_;
    return h ? h : 1;
}

}  // namespace cells
