# SPDX-License-Identifier: MIT
"""Wake levels of the light sleep (firmware/src/mcu_sleep.h) and the sleep lists of the L0 and v2 board files.

ESP32-S3 light sleep wakes on a level, not an edge. The harness models one sleep: a line wakes the MCU when its
level during the sleep equals the armed level. A held state (laptop connected, power switch pressed) must not wake
a second time; a change of level must (docs/spec/oprogramowanie.md, "Czuwanie")."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_radio_link_host import build_and_run, host_compiler, line  # noqa: E402  (stubs and host build)

HARNESS = r"""
#include <stdio.h>
#include "mcu_sleep.h"

using mcu_sleep::Line;
using mcu_sleep::Wake;

// Lines as on board v2: DIO1, one button, INT of the power switch and the laptop detection (both active low).
const Line LINES[] = {{21, Wake::ACTIVE_HIGH, "dio1"}, {39, Wake::ANY_CHANGE, "ok"},
                      {48, Wake::ANY_CHANGE, "power_int"}, {3, Wake::ANY_CHANGE, "laptop"}};
constexpr size_t N = 4;
uint8_t levels[N] = {0, 1, 1, 1};  // idle: DIO1 low, button released, switch released, no laptop

// One sleep: arm from the present levels, then the levels during the sleep are `during`. Returns the name of the
// waking line, "busy" when arming refused, "timer" when no line matched. Levels stay as `during` afterwards.
const char* nap(const uint8_t* during) {
    uint8_t armed[N] = {};
    if (mcu_sleep::arm(LINES, N, levels, armed) >= 0) return "busy";
    for (size_t i = 0; i < N; ++i) levels[i] = during[i];
    const int w = mcu_sleep::woke(N, levels, armed);
    return w >= 0 ? LINES[w].name : "timer";
}

int main() {
    const uint8_t idle[N] = {0, 1, 1, 1};
    const uint8_t laptop[N] = {0, 1, 1, 0};
    const uint8_t pressed[N] = {0, 1, 0, 1};
    const uint8_t button[N] = {0, 0, 1, 1};
    const uint8_t frame[N] = {1, 1, 1, 1};

    printf("IDLE %s\n", nap(idle));
    printf("PLUG %s\n", nap(laptop));            // laptop connected: wakes once
    // One nap() per statement: it changes `levels`, and GCC evaluates printf arguments right to left.
    const char* first = nap(laptop);
    const char* second = nap(laptop);
    printf("HELD %s %s\n", first, second);  // still connected: no second wake
    printf("UNPLUG %s\n", nap(idle));            // disconnected: change of level wakes
    printf("AFTER %s\n", nap(idle));
    printf("PRESS %s\n", nap(pressed));          // switch pressed: INT low
    printf("HOLD %s\n", nap(pressed));           // INT held low for the 5-19 s of a long press: no wake
    printf("RELEASE %s\n", nap(idle));
    const char* press = nap(button);
    const char* hold = nap(button);
    const char* release = nap(idle);
    printf("BUTTON %s %s %s\n", press, hold, release);
    const char* end = nap(frame);
    const char* pending = nap(frame);
    printf("FRAME %s %s\n", end, pending);  // DIO1 high wakes; while high there is no sleep
    levels[0] = 0;
    // Level back before the wake-up was read (contact bounce): no line named.
    uint8_t armed[N] = {};
    uint8_t now[N] = {0, 1, 1, 1};
    mcu_sleep::arm(LINES, N, now, armed);
    printf("BOUNCE %d\n", mcu_sleep::woke(N, now, armed));
    printf("CAUSES %s %s %s %s %s\n", mcu_sleep::causeName(mcu_sleep::Cause::TIMER), mcu_sleep::causeName(mcu_sleep::Cause::LINE),
           mcu_sleep::causeName(mcu_sleep::Cause::OTHER), mcu_sleep::causeName(mcu_sleep::Cause::REJECTED),
           mcu_sleep::causeName(mcu_sleep::Cause::BUSY));
    return 0;
}
"""

BOARD_HARNESS = r"""
#include <stdio.h>
#include BOARD

int main() {
    printf("HOLD");
    for (uint8_t pin : board::SLEEP_HOLD) printf(" %u", pin);
    printf("\nWAKE");
    for (const mcu_sleep::Line& l : board::SLEEP_WAKE)
        printf(" %s:%u:%s", l.name, l.pin, l.wake == mcu_sleep::Wake::ACTIVE_HIGH ? "high" : "change");
    printf("\n");
    return 0;
}
"""

L0_HOLD = "9 10 42 8 7 17 16 18 15"  # sorted below; radio CS, RESET, RXEN, FRAM CS, LCD CS, EXTCOMIN, DISP, LED, buzzer
L0_WAKE = ["dio1:21:high", "up:41:change", "down:40:change", "ok:39:change", "back:2:change", "silence:1:change",
           "prep:6:change"]


@unittest.skipUnless(host_compiler(), "no host C++ compiler")
class WakeLevelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = build_and_run(HARNESS, [])

    def test_no_line_change_ends_on_the_timer(self):
        self.assertEqual(line(self.out, "IDLE"), "IDLE timer")

    def test_laptop_wakes_on_connect_and_disconnect_but_not_while_connected(self):
        self.assertEqual(line(self.out, "PLUG"), "PLUG laptop")
        self.assertEqual(line(self.out, "HELD"), "HELD timer timer")
        self.assertEqual(line(self.out, "UNPLUG"), "UNPLUG laptop")
        self.assertEqual(line(self.out, "AFTER"), "AFTER timer")

    def test_power_switch_held_does_not_wake_again(self):
        self.assertEqual(line(self.out, "PRESS"), "PRESS power_int")
        self.assertEqual(line(self.out, "HOLD"), "HOLD timer")
        self.assertEqual(line(self.out, "RELEASE"), "RELEASE power_int")

    def test_button_press_hold_release(self):
        self.assertEqual(line(self.out, "BUTTON"), "BUTTON ok timer ok")

    def test_pending_radio_interrupt_blocks_sleep(self):
        self.assertEqual(line(self.out, "FRAME"), "FRAME dio1 busy")

    def test_bounce_names_no_line(self):
        self.assertEqual(line(self.out, "BOUNCE"), "BOUNCE -1")

    def test_cause_names(self):
        self.assertEqual(line(self.out, "CAUSES"), "CAUSES timer line other rejected busy")


@unittest.skipUnless(host_compiler(), "no host C++ compiler")
class BoardSleepListTests(unittest.TestCase):
    """The lists in board_l0.h and board_v2.h: outputs pulled by board resistors are held, lines that keep their
    state (switch INT, laptop detection, buttons) wake on a change and DIO1 on its high level."""

    def lists(self, header):
        out = build_and_run(BOARD_HARNESS, [], flags=[f'-DBOARD="{header}"'])
        return sorted(int(p) for p in line(out, "HOLD").split()[1:]), line(out, "WAKE").split()[1:]

    def test_l0(self):
        hold, wake = self.lists("board_l0.h")
        self.assertEqual(hold, sorted(int(p) for p in L0_HOLD.split()))
        self.assertEqual(wake, L0_WAKE)

    def test_v2_adds_divider_converter_kill_switch_and_laptop(self):
        hold, wake = self.lists("board_v2.h")
        # DIV_EN GPIO46, PWM_SYNC GPIO45, KILL_MCU GPIO47 (hardware/plytka-v2/polaczenia.md)
        self.assertEqual(hold, sorted([int(p) for p in L0_HOLD.split()] + [46, 45, 47]))
        # PWR_INT GPIO48, USB_LAPTOP GPIO3
        self.assertEqual(wake, L0_WAKE + ["power_int:48:change", "laptop:3:change"])


if __name__ == "__main__":
    unittest.main()
