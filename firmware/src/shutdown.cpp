// SPDX-License-Identifier: MIT
#include "shutdown.h"

namespace shutdown {

namespace {
uint32_t left(uint32_t now, uint32_t since, uint32_t period) {
    const uint32_t elapsed = now - since;
    return elapsed >= period ? 0 : period - elapsed;
}
}  // namespace

const char* phaseName(Phase phase) {
    switch (phase) {
        case Phase::SAVING: return "saving";
        case Phase::REMOVABLE: return "removable";
        case Phase::KILLED: return "killed";
        case Phase::FAILED: return "failed";
        default: return "run";
    }
}

const char* reasonName(Reason reason) {
    switch (reason) {
        case Reason::BUTTON: return "button";
        case Reason::CELLS: return "cells";
        default: return "none";
    }
}

void Sequence::enter(Phase phase, uint32_t nowMs) {
    phase_ = phase;
    phaseMs_ = nowMs;
}

bool Sequence::poll(uint32_t nowMs, bool intLow, bool cellsEmpty) {
    const Phase before = phase_;
    const bool killBefore = kill_;
    if (!intLow) armed_ = true;
    if (intLow && !intWas_) intSinceMs_ = nowMs;
    intWas_ = intLow;
    switch (phase_) {
        case Phase::RUN:
            if (armed_ && intLow && nowMs - intSinceMs_ >= HOLD_MS) reason_ = Reason::BUTTON;
            else if (cellsEmpty) reason_ = Reason::CELLS;
            if (reason_ != Reason::NONE) enter(Phase::SAVING, nowMs);
            break;
        case Phase::SAVING: break;   // saved() kończy zapis
        case Phase::REMOVABLE:
            if (nowMs - phaseMs_ >= SHOW_MS) {
                enter(Phase::KILLED, nowMs);
                kill_ = true;
            }
            break;
        case Phase::KILLED:
            if (nowMs - phaseMs_ >= FAIL_MS) {
                enter(Phase::FAILED, nowMs);
                failedLog_ = true;
                killMs_ = nowMs;
            }
            break;
        case Phase::FAILED:
            // Ponowienie: KILL puszczony na RELEASE_MS co RETRY_MS i znowu ściągnięty.
            if (kill_ && nowMs - killMs_ >= RETRY_MS) {
                kill_ = false;
                killMs_ = nowMs;
            } else if (!kill_ && nowMs - killMs_ >= RELEASE_MS) {
                kill_ = true;
                killMs_ = nowMs;
                ++retries_;
            }
            break;
    }
    return phase_ != before || kill_ != killBefore;
}

void Sequence::saved(uint32_t nowMs) {
    if (phase_ == Phase::SAVING) enter(Phase::REMOVABLE, nowMs);
}

uint32_t Sequence::untilMs(uint32_t nowMs) const {
    switch (phase_) {
        case Phase::RUN: return intWas_ && armed_ ? left(nowMs, intSinceMs_, HOLD_MS) : 0xFFFFFFFFu;
        case Phase::SAVING: return 0;
        case Phase::REMOVABLE: return left(nowMs, phaseMs_, SHOW_MS);
        case Phase::KILLED: return left(nowMs, phaseMs_, FAIL_MS);
        case Phase::FAILED: return left(nowMs, killMs_, kill_ ? RETRY_MS : RELEASE_MS);
    }
    return 0xFFFFFFFFu;
}

}  // namespace shutdown
