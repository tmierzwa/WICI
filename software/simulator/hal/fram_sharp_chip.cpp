// SPDX-License-Identifier: MIT
// FRAM CY15B104Q (Infineon, 4 Mbit, SPI tryb 0): WREN, WRDI, RDSR, WRSR, READ, WRITE, RDID; zapis
// tylko po WREN, zatrzask WEL kasowany po zakończeniu zapisu, adres 19 bitów.
// Ekran Sharp LS027B7DH01A: strumień bitów w kolejności na linii, pierwszy bit M0 (zapis), M1 (VCOM),
// M2 (czyszczenie), 5 bitów odstępu; w trybie zapisu kolejno adres wiersza AG0..AG7 (1..240), 400 bitów
// danych (pierwszy = lewy piksel, 1 = biały) i 8 bitów odstępu; adres 0 kończy transmisję.
#include "chips.h"

#include <string.h>

namespace chips {

namespace {
constexpr uint8_t ID[9] = {0x7F, 0x7F, 0x7F, 0x7F, 0x7F, 0x7F, 0xC2, 0x26, 0x08};   // CY15B104Q-SXI
constexpr uint32_t ADDRESS_MASK = 0x7FFFF;
}  // namespace

uint8_t Fram::exchange(uint8_t wire) {
    const int i = index_++;
    if (i == 0) {
        opcode_ = wire;
        if (opcode_ == 0x06) wel_ = true;
        else if (opcode_ == 0x04) wel_ = false;
        wrote_ = false;
        return 0;
    }
    switch (opcode_) {
        case 0x05: return static_cast<uint8_t>(wel_ ? 0x02 : 0x00);
        case 0x9F: return i - 1 < 9 ? ID[i - 1] : 0x00;
        case 0x03:
        case 0x02:
            if (i <= 3) {
                address_ = ((address_ << 8) | wire) & ADDRESS_MASK;
                if (i == 1) address_ = wire & 0x07;
                return 0;
            }
            if (opcode_ == 0x03) {
                const uint8_t v = memory_[address_];
                address_ = (address_ + 1) & ADDRESS_MASK;
                return v;
            }
            if (wel_) {
                if (!failWrites) memory_[address_] = wire;
                wrote_ = true;
            }
            address_ = (address_ + 1) & ADDRESS_MASK;
            return 0;
        default: return 0;
    }
}

void Fram::deselect() {
    if (opcode_ == 0x02 && index_ > 0) wel_ = false;   // WEL kasowany po zapisie (także pustym)
    index_ = 0;
}

Sharp::Sharp() { memset(frame, 0xFF, sizeof(frame)); }

void Sharp::select() {
    phase_ = Phase::MODE;
    count_ = 0;
    mode_ = 0;
    changed_ = false;
}

uint8_t Sharp::exchange(uint8_t wire) {
    for (int b = 7; b >= 0; --b) bit((wire >> b) & 1u);
    return 0;
}

void Sharp::bit(bool b) {
    switch (phase_) {
        case Phase::MODE:
            if (count_ < 3 && b) mode_ |= static_cast<uint8_t>(1u << count_);
            if (++count_ == 8) {
                count_ = 0;
                address_ = 0;
                if (mode_ & 0x04) {   // M2: czyszczenie całej pamięci
                    memset(frame, 0xFF, sizeof(frame));
                    changed_ = true;
                    phase_ = Phase::DUMMY;
                } else {
                    phase_ = (mode_ & 0x01) ? Phase::ADDRESS : Phase::DUMMY;
                }
            }
            break;
        case Phase::ADDRESS:
            if (b) address_ |= static_cast<uint8_t>(1u << count_);
            if (++count_ == 8) {
                count_ = 0;
                phase_ = (address_ >= 1 && address_ <= 240) ? Phase::DATA : Phase::DUMMY;
                memset(line_, 0, sizeof(line_));
            }
            break;
        case Phase::DATA:
            if (b) line_[count_ / 8] |= static_cast<uint8_t>(1u << (count_ % 8));
            if (++count_ == 400) {
                count_ = 0;
                if (memcmp(frame[address_ - 1], line_, sizeof(line_))) {
                    memcpy(frame[address_ - 1], line_, sizeof(line_));
                    changed_ = true;
                }
                ++lineWrites;
                phase_ = Phase::GAP;
            }
            break;
        case Phase::GAP:   // 8 bitów odstępu po wierszu, potem adres następnego albo koniec
            if (++count_ == 8) {
                count_ = 0;
                address_ = 0;
                phase_ = Phase::ADDRESS;
            }
            break;
        case Phase::DUMMY: break;
    }
}

void Sharp::deselect() {
    if (changed_) ++version;
    changed_ = false;
}

}  // namespace chips
