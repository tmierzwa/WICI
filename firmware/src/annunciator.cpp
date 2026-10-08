// SPDX-License-Identifier: MIT
#include "annunciator.h"

namespace annunciator {

uint32_t Annunciator::poll(uint32_t nowMs, const Inputs& in) {
    // Dioda: błysk najpierw od razu, potem co FLASH_EVERY_MS. Błysk trwa co najmniej FLASH_MS
    // także przy wolnym obiegu pętli, a żaden okres nie zostaje bez błysku.
    active_ = in.alarmScreen || in.alarmCause || in.silence || in.unread > 0;
    if (led_) {
        if (nowMs - flashAt_ >= FLASH_MS) led_ = false;
    } else if (active_ && (!flashed_ || nowMs - flashAt_ >= FLASH_EVERY_MS)) {
        led_ = true;
        flashed_ = true;
        flashAt_ = nowMs;
    }
    if (!active_ && !led_) flashed_ = false;

    uint32_t beep = 0;
    if (in.alarmScreen) {
        if (!alarmBeeped_ || nowMs - alarmBeepAt_ >= ALARM_BEEP_EVERY_MS) {
            alarmBeeped_ = true;
            alarmBeepAt_ = nowMs;
            beep = ALARM_BEEP_MS;
        }
    } else {
        alarmBeeped_ = false;
    }
    // Nowa wiadomość: przyrost nieprzeczytanych (po starcie bez sygnału za wcześniejsze). Sygnał
    // alarmu ma pierwszeństwo.
    if (started_ && in.unread > unread_ && !in.muted && !beep) beep = MESSAGE_BEEP_MS;
    unread_ = in.unread;
    started_ = true;
    return beep;
}

}  // namespace annunciator
