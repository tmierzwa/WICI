// SPDX-License-Identifier: MIT
#include "power.h"

namespace power {

namespace {
uint32_t left(uint32_t now, uint32_t at) {
    const int32_t ms = static_cast<int32_t>(at - now);
    return ms > 0 ? static_cast<uint32_t>(ms) : 0;
}
}  // namespace

const char* sourceName(Source source) { return source == Source::CELLS ? "aa" : "12v"; }

Step Monitor::poll(uint32_t nowMs, uint32_t sinceTxMs) {
    if (!started_) {
        started_ = true;
        dueMs_ = nowMs;   // pierwszy pomiar zaraz po starcie
    }
    pollMs_ = nowMs;
    sinceTxMs_ = sinceTxMs;
    const bool quiet = sinceTxMs >= AFTER_TX_MS;
    if (settling_) {
        if (!quiet) {   // nadawanie w trakcie pomiaru: od nowa po przerwie
            settling_ = false;
            ++aborted_;
            return Step::DISABLE;
        }
        return nowMs - enabledMs_ >= SETTLE_MS ? Step::READ : Step::NONE;
    }
    if (left(nowMs, dueMs_) || !quiet) return Step::NONE;
    settling_ = true;
    enabledMs_ = nowMs;
    return Step::ENABLE;
}

void Monitor::sample(uint32_t nowMs, uint32_t cellsPinMv, uint32_t mainsPinMv) {
    settling_ = false;
    dueMs_ = nowMs + PERIOD_MS;
    const uint32_t cells = cellsPinMv * CELLS_DIVIDER_X10 / 10, mains = mainsPinMv * MAINS_DIVIDER;
    lastCellsMv_ = static_cast<uint16_t>(cells > 0xFFFF ? 0xFFFF : cells);
    mainsMv_ = static_cast<uint16_t>(mains > 0xFFFF ? 0xFFFF : mains);
    ring_[next_] = lastCellsMv_;
    next_ = static_cast<uint8_t>((next_ + 1) % AVERAGE);
    if (count_ < AVERAGE) ++count_;
    uint32_t sum = 0;
    for (uint8_t i = 0; i < count_; ++i) sum += ring_[i];
    cellsMv_ = static_cast<uint16_t>(sum / count_);
    if (cellsMv_ < REPLACE_MV) replace_ = true;
    else if (cellsMv_ >= CLEAR_MV) replace_ = false;
    if (mainsMv_ < MAINS_OFF_MV || mainsMv_ > MAINS_HIGH_MV) source_ = Source::CELLS;
    else if (mainsMv_ >= MAINS_ON_MV) source_ = Source::MAINS12;
}

uint32_t Monitor::untilMs(uint32_t nowMs) const {
    if (!started_) return 0;
    if (settling_) return left(nowMs, enabledMs_ + SETTLE_MS);
    const uint32_t due = left(nowMs, dueMs_);
    if (sinceTxMs_ >= AFTER_TX_MS) return due;
    // Po nadawaniu: najwcześniej po przerwie od końca nadawania. W trakcie nadawania (sinceTxMs 0) koniec nie
    // jest znany, więc cała przerwa; uśpienie i tak wstrzymuje wtedy radio (standby::RADIO_HOLD_MS).
    const uint32_t remaining = AFTER_TX_MS - sinceTxMs_, elapsed = nowMs - pollMs_;
    const uint32_t quietIn = elapsed >= remaining ? 0 : remaining - elapsed;
    return due > quietIn ? due : quietIn;
}

}  // namespace power
