// SPDX-License-Identifier: MIT
#pragma once

#include <stdint.h>
#include <string.h>

namespace commands {

constexpr size_t MAX_LINE = 90;

enum class Kind {
    Unknown, Info, Status, Stop, Help, Tx, Rdid, Led, Buzzer,
    Lcd, Pause, FramTest, FramVerify, Guard, Mixed
};
enum class Mode { Idle, Mixed, Guard };

struct Command {
    Kind kind = Kind::Unknown;
    uint32_t value = 0;
    const char* payload = nullptr;
};

inline bool parseSeed(const char* text, uint32_t& seed) {
    const size_t length = strlen(text);
    if (length == 0 || length > 8) return false;
    seed = 0;
    for (size_t i = 0; i < length; ++i) {
        const char c = text[i];
        unsigned digit;
        if (c >= '0' && c <= '9') digit = c - '0';
        else if (c >= 'a' && c <= 'f') digit = c - 'a' + 10;
        else if (c >= 'A' && c <= 'F') digit = c - 'A' + 10;
        else return false;
        seed = (seed << 4) | digit;
    }
    return true;
}

inline Command parse(const char* line) {
    Command result;
    const struct { const char* text; Kind kind; } fixed[] = {
        {"INFO", Kind::Info}, {"STATUS", Kind::Status}, {"STOP", Kind::Stop},
        {"HELP", Kind::Help}, {"RDID", Kind::Rdid}, {"PAUSE 10000", Kind::Pause},
        {"GUARD ERASE", Kind::Guard}, {"MIXSTART ERASE", Kind::Mixed}
    };
    for (const auto& entry : fixed) {
        if (strcmp(line, entry.text) == 0) {
            result.kind = entry.kind;
            return result;
        }
    }
    if (strncmp(line, "TX ", 3) == 0) {
        result.kind = Kind::Tx;
        result.payload = line + 3;
        return result;
    }
    const struct { const char* prefix; Kind kind; int maximum; } single[] = {
        {"LED ", Kind::Led, 1}, {"BUZZ ", Kind::Buzzer, 1}, {"LCD ", Kind::Lcd, 4}
    };
    for (const auto& entry : single) {
        const size_t length = strlen(entry.prefix);
        if (strncmp(line, entry.prefix, length) == 0 && strlen(line) == length + 1 &&
            line[length] >= '0' && line[length] <= '0' + entry.maximum) {
            result.kind = entry.kind;
            result.value = line[length] - '0';
            return result;
        }
    }
    const struct { const char* prefix; Kind kind; } seeded[] = {
        {"FRAMTEST ERASE ", Kind::FramTest}, {"FRAMVERIFY ", Kind::FramVerify}
    };
    for (const auto& entry : seeded) {
        const size_t length = strlen(entry.prefix);
        if (strncmp(line, entry.prefix, length) == 0 && parseSeed(line + length, result.value)) {
            result.kind = entry.kind;
            return result;
        }
    }
    return result;
}

inline bool allowed(Kind kind, Mode mode) {
    if (mode == Mode::Idle) return true;
    if (kind == Kind::Info || kind == Kind::Status || kind == Kind::Stop || kind == Kind::Help)
        return true;
    return mode == Mode::Mixed && kind == Kind::Tx;
}

// Reject an invalid/overlong line as a whole, including every suffix until LF.
class LineBuffer {
public:
    enum class Event { None, Complete, Invalid };
    Event append(char c) {
        if (c == '\n') {
            const bool complete = !discard_;
            discard_ = false;
            text_[length_] = '\0';
            length_ = 0;
            return complete ? Event::Complete : Event::None;
        }
        if (discard_ || c == '\r') return Event::None;
        if (c < 32 || c > 126 || length_ == MAX_LINE) {
            length_ = 0;
            discard_ = true;
            return Event::Invalid;
        }
        text_[length_++] = c;
        return Event::None;
    }
    const char* text() const { return text_; }
private:
    char text_[MAX_LINE + 1] = {};
    size_t length_ = 0;
    bool discard_ = false;
};

}  // namespace commands
