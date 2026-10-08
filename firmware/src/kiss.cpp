// SPDX-License-Identifier: MIT
#include "kiss.h"

#include <string.h>

namespace kiss {

void Port::setOpen(bool open) {
    open_ = open;
    flowControl_ = false;
    readyOwed_ = false;
    inFrame_ = false;
    escape_ = false;
    command_ = -1;
    length_ = 0;
    tooLarge_ = false;
    txHead_ = 0;
    txCount_ = 0;
}

void Port::feed(const uint8_t* bytes, size_t count, uint32_t nowMs) {
    if (count && inFrame_ && (length_ || command_ >= 0) && nowMs - lastByteMs_ > FRAME_TIMEOUT_MS) {
        // Niepełna ramka po przerwie: porzucona, następny bajt FEND zaczyna nową.
        inFrame_ = false;
        escape_ = false;
        command_ = -1;
        length_ = 0;
        tooLarge_ = false;
    }
    for (size_t i = 0; i < count; ++i) {
        const uint8_t b = bytes[i];
        lastByteMs_ = nowMs;
        if (b == FEND) {
            if (inFrame_ && command_ >= 0) endFrame();
            // Bajt FEND kończy ramkę i zaczyna następną (także wspólny FEND między ramkami).
            inFrame_ = true;
            escape_ = false;
            command_ = -1;
            length_ = 0;
            tooLarge_ = false;
            hasValue_ = false;
            continue;
        }
        if (!inFrame_) continue;
        if (command_ < 0) {
            command_ = static_cast<int16_t>(b & 0x0F);
            // Miejsce w buforze ustalone na początku ramki; pop() w trakcie ramki go nie zmienia
            // (head_ + count_ jest stałe przy zdejmowaniu pakietów).
            target_ = count_ < RX_SLOTS ? static_cast<int16_t>((head_ + count_) % RX_SLOTS) : -1;
            continue;
        }
        uint8_t value = b;
        if (escape_) {
            escape_ = false;
            if (b == TFEND) value = FEND;
            else if (b == TFESC) value = FESC;
        } else if (b == FESC) {
            escape_ = true;
            continue;
        }
        if (command_ == CMD_DATA) {
            if (length_ >= MTU) { tooLarge_ = true; continue; }
            if (target_ >= 0) slots_[target_][length_] = value;
            ++length_;
        } else if (!hasValue_) {
            value_ = value;
            hasValue_ = true;
        }
    }
}

void Port::endFrame() {
    if (command_ == CMD_DATA) {
        if (tooLarge_) { ++counters_.rxTooLarge; return; }
        if (!length_) return;
        if (target_ < 0) { ++counters_.rxDropped; return; }
        lengths_[target_] = static_cast<uint16_t>(length_);
        ++count_;
        ++counters_.fromComputer;
        if (flowControl_) {
            if (count_ < RX_SLOTS) readyNow();
            else readyOwed_ = true;
        }
    } else if (command_ == CMD_READY) {
        if (hasValue_) flowControl_ = value_ != 0;
    } else {
        ++counters_.commands;   // TXDELAY, P, SLOTTIME, TXTAIL i inne: bez znaczenia dla P1
    }
}

bool Port::peek(const uint8_t*& data, size_t& length) const {
    if (!count_) return false;
    data = slots_[head_];
    length = lengths_[head_];
    return true;
}

void Port::pop() {
    if (!count_) return;
    head_ = (head_ + 1) % RX_SLOTS;
    --count_;
    if (readyOwed_) readyNow();
}

void Port::readyNow() {
    static const uint8_t frame[4] = {FEND, CMD_READY, 0x01, FEND};
    readyOwed_ = !put(frame, sizeof(frame));
    if (!readyOwed_) ++counters_.ready;
}

bool Port::put(const uint8_t* bytes, size_t count) {
    if (TX_BYTES - txCount_ < count) return false;
    for (size_t i = 0; i < count; ++i) tx_[(txHead_ + txCount_ + i) % TX_BYTES] = bytes[i];
    txCount_ += count;
    return true;
}

bool Port::send(const uint8_t* data, size_t length) {
    size_t encoded = 3;   // FEND, polecenie, FEND
    for (size_t i = 0; i < length; ++i) encoded += (data[i] == FEND || data[i] == FESC) ? 2 : 1;
    if (!open_ || !length || length > MTU || TX_BYTES - txCount_ < encoded) { ++counters_.txDropped; return false; }
    const uint8_t start[2] = {FEND, CMD_DATA};
    put(start, sizeof(start));
    for (size_t i = 0; i < length; ++i) {
        if (data[i] == FEND) { const uint8_t e[2] = {FESC, TFEND}; put(e, 2); }
        else if (data[i] == FESC) { const uint8_t e[2] = {FESC, TFESC}; put(e, 2); }
        else put(&data[i], 1);
    }
    put(&FEND, 1);
    ++counters_.toComputer;
    return true;
}

size_t Port::take(uint8_t* out, size_t max) {
    if (readyOwed_ && count_ < RX_SLOTS) readyNow();
    size_t n = 0;
    while (n < max && txCount_) {
        out[n++] = tx_[txHead_];
        txHead_ = (txHead_ + 1) % TX_BYTES;
        --txCount_;
    }
    return n;
}

}  // namespace kiss
