# SPDX-License-Identifier: MIT
"""Standby loop rules (firmware/src/standby.h) and the deadline of the alarm LED and buzzer (annunciator.cpp).

The loop itself runs on the v2 board (main.cpp, standbyStep); here are its decisions: the 10 s VBUS rule and the
USB bus, reasons to stay awake and the sleep length from deadlines, the hold after an event and the EXTCOMIN
level driven by the loop while the MCPWM timer stops in light sleep (docs/spec/oprogramowanie.md, "Czuwanie")."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_radio_link_host import build_and_run, host_compiler, line  # noqa: E402  (stubs and host build)

HARNESS = r"""
#include <stdio.h>
#include "annunciator.h"
#include "standby.h"

using standby::Reason;

const char* yes(bool b) { return b ? "1" : "0"; }

// Usb state as "blocks window mounted until" after one update.
void usb(const char* tag, standby::Usb& u, uint32_t now, bool vbus, bool mounted, bool suspended = false) {
    u.update(now, vbus, mounted, suspended);
    const uint32_t left = u.untilMs(now);
    printf("%s %s %s %s %ld\n", tag, yes(u.blocks()), yes(u.window()), yes(u.mounted()),
           left == standby::NEVER ? -1L : static_cast<long>(left));
}

void plan(const char* tag, const standby::Plan& p) {
    printf("%s %s %lu\n", tag, standby::reasonName(p.reason()), static_cast<unsigned long>(p.sleepMs()));
}

int main() {
    // Start: 10 s window also without VBUS (laptop on the DevKitC connector at the bench), then sleep allowed.
    {
        standby::Usb u;
        usb("BOOT", u, 3000, false, false);
        usb("BOOT_END", u, 12999, false, false);
        usb("BOOT_OVER", u, 13000, false, false);
        // At the bench the host enumerates within the window: no sleep while mounted, also after 10 s.
        standby::Usb bench;
        bench.update(100, false, false, false);
        usb("BENCH", bench, 5000, false, true);
        usb("BENCH_HELD", bench, 60000, false, true);
        // Cable pulled at the bench: the PHY does not sense VBUS, so the bus looks suspended and the device stays
        // enumerated; without VBUS on the board socket that is no connection.
        usb("BENCH_UNPLUG", bench, 61000, false, true, true);
    }
    // Charger in the socket: VBUS without enumeration does not block after 10 s.
    {
        standby::Usb u;
        u.update(0, false, false, false);
        u.update(20000, false, false, false);
        usb("CHARGER", u, 30000, true, false);
        usb("CHARGER_9999", u, 39999, true, false);
        usb("CHARGER_10S", u, 40000, true, false);
        usb("CHARGER_HELD", u, 100000, true, false);
        // Laptop in place of the charger: VBUS drops and comes back, a new window, then the host enumerates.
        usb("SWAP_OFF", u, 100500, false, false);
        usb("SWAP_ON", u, 101000, true, false);
        usb("LAPTOP", u, 102000, true, true);
        usb("LAPTOP_HELD", u, 500000, true, true);
        // Laptop asleep with the cable in the socket: suspended, VBUS present, still connected.
        usb("LAPTOP_SLEEP", u, 550000, true, true, true);
        // Host ends the connection with VBUS present (e.g. the laptop shuts down the port): a new 10 s window.
        usb("UNMOUNT", u, 600000, true, false);
        usb("UNMOUNT_10S", u, 610000, true, false);
        // VBUS gone during a window ends it at once.
        usb("REPLUG", u, 700000, false, false);
        usb("REPLUG_ON", u, 700100, true, false);
        usb("REPLUG_OFF", u, 701000, false, false);
    }
    // Window across the wrap of millis().
    {
        standby::Usb u;
        const uint32_t t = 0xFFFFF000u;  // 4096 ms przed przejściem przez zero
        u.update(t - 30000u, false, false, false);
        u.update(t - 10000u, false, false, false);
        usb("WRAP", u, t, true, false);
        usb("WRAP_MID", u, t + 9999u, true, false);
        usb("WRAP_END", u, t + 10000u, true, false);
    }

    // Plan: first reason wins; without a reason the nearest deadline, at most 1 s; below 10 ms no sleep.
    {
        standby::Plan p(1000);
        plan("PLAN_IDLE", p);
        p.wakeIn(500);
        p.wakeIn(700);
        plan("PLAN_VCOM", p);
        p.wakeAt(1120);
        plan("PLAN_AT", p);
        p.wakeAt(1009);
        plan("PLAN_SHORT", p);
        p.block(Reason::RADIO);
        p.block(Reason::USB);
        plan("PLAN_BLOCK", p);
        standby::Plan past(1000);
        past.wakeAt(990);  // minął: bez uśpienia
        plan("PLAN_PAST", past);
        standby::Plan edge(1000);
        edge.wakeIn(10);
        plan("PLAN_MIN", edge);
        standby::Plan never(1000);
        never.wakeIn(standby::NEVER);
        plan("PLAN_NEVER", never);
        printf("PERSISTENT %s%s%s %s%s%s%s%s%s\n", yes(standby::persistent(Reason::PREP)), yes(standby::persistent(Reason::NODE)),
               yes(standby::persistent(Reason::USB)), yes(standby::persistent(Reason::RADIO)), yes(standby::persistent(Reason::PANEL)),
               yes(standby::persistent(Reason::SCREEN)), yes(standby::persistent(Reason::WORK)), yes(standby::persistent(Reason::SHORT)),
               yes(standby::persistent(Reason::SLEEP)));
        printf("NAMES %s %s %s %s %s %s %s %s %s\n", standby::reasonName(Reason::SLEEP), standby::reasonName(Reason::PREP),
               standby::reasonName(Reason::NODE), standby::reasonName(Reason::USB), standby::reasonName(Reason::RADIO),
               standby::reasonName(Reason::PANEL), standby::reasonName(Reason::SCREEN), standby::reasonName(Reason::WORK),
               standby::reasonName(Reason::SHORT));
    }

    // Hold: extended by later events, never shortened; across the wrap of millis().
    {
        standby::Hold h;
        const bool before = h.active(0);
        h.extend(1000, standby::RADIO_HOLD_MS);
        const bool during = h.active(2999);
        h.extend(1500, standby::INPUT_HOLD_MS);  // krótsze nie skraca
        const bool kept = h.active(2999);
        const bool after = h.active(3000);
        h.extend(0xFFFFFF00u, 1000);
        const bool wrapped = h.active(0x000002E7u);
        const bool wrappedEnd = h.active(0x000002E8u);
        printf("HOLD %s %s %s %s %s %s\n", yes(before), yes(during), yes(kept), yes(after), yes(wrapped), yes(wrappedEnd));
    }

    // EXTCOMIN: the loop takes the pin at the timer's level, inverts it every 500 ms of real time, also after
    // a late wake (once, then a full half period); released, the deadline is one half period.
    {
        standby::Vcom v;
        printf("VCOM_FREE %s %lu\n", yes(v.forced()), static_cast<unsigned long>(v.untilEdgeMs(0)));
        v.take(10000, true);
        const uint32_t left = v.untilEdgeMs(10200);
        const bool early = v.tick(10499);
        const bool edge = v.tick(10500);
        const bool level1 = v.level();
        const bool late = v.tick(11700);   // wybudzenie 700 ms po zmianie: jedna zmiana
        const bool again = v.tick(11701);
        const bool level2 = v.level();
        const uint32_t next = v.untilEdgeMs(11800);
        printf("VCOM %lu %s %s %s %s %s %s %lu\n", static_cast<unsigned long>(left), yes(early), yes(edge), yes(level1),
               yes(late), yes(again), yes(level2), static_cast<unsigned long>(next));
        printf("VCOM_DUE %lu\n", static_cast<unsigned long>(v.untilEdgeMs(12300)));
        v.release();
        printf("VCOM_RELEASED %s %s %lu\n", yes(v.forced()), yes(v.tick(20000)), static_cast<unsigned long>(v.untilEdgeMs(20000)));
    }

    // Alarm LED and buzzer: the loop wakes at the end of a flash, for the next flash and the next alarm beep.
    {
        annunciator::Annunciator a;
        annunciator::Inputs in;
        a.poll(0, in);
        const uint32_t idle = a.untilChangeMs(0);
        in.silence = true;
        a.poll(1000, in);          // błysk od razu
        const uint32_t flash = a.untilChangeMs(1020);
        a.poll(1050, in);          // koniec błysku
        const uint32_t next = a.untilChangeMs(1050);
        const uint32_t late = a.untilChangeMs(7000);
        in.alarmScreen = true;
        a.poll(2000, in);          // sygnał alarmu
        const uint32_t beep = a.untilChangeMs(2500);
        printf("ANNUNCIATOR %ld %lu %lu %lu %lu\n", idle == standby::NEVER ? -1L : static_cast<long>(idle),
               static_cast<unsigned long>(flash), static_cast<unsigned long>(next), static_cast<unsigned long>(late),
               static_cast<unsigned long>(beep));
    }
    return 0;
}
"""


@unittest.skipUnless(host_compiler(), "no host C++ compiler")
class StandbyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = build_and_run(HARNESS, ["annunciator.cpp"])

    def test_window_after_start_lets_a_bench_laptop_enumerate(self):
        # Fields: blocks, window, mounted, ms to the end of the window (-1: no window).
        self.assertEqual(line(self.out, "BOOT"), "BOOT 1 1 0 10000")
        self.assertEqual(line(self.out, "BOOT_END"), "BOOT_END 1 1 0 1")
        self.assertEqual(line(self.out, "BOOT_OVER"), "BOOT_OVER 0 0 0 -1")
        self.assertEqual(line(self.out, "BENCH"), "BENCH 1 0 1 -1")
        self.assertEqual(line(self.out, "BENCH_HELD"), "BENCH_HELD 1 0 1 -1")
        self.assertEqual(line(self.out, "BENCH_UNPLUG"), "BENCH_UNPLUG 0 0 0 -1")

    def test_vbus_without_connection_stops_blocking_after_10_s(self):
        self.assertEqual(line(self.out, "CHARGER"), "CHARGER 1 1 0 10000")
        self.assertEqual(line(self.out, "CHARGER_9999"), "CHARGER_9999 1 1 0 1")
        self.assertEqual(line(self.out, "CHARGER_10S"), "CHARGER_10S 0 0 0 -1")
        self.assertEqual(line(self.out, "CHARGER_HELD"), "CHARGER_HELD 0 0 0 -1")

    def test_new_vbus_opens_a_new_window_and_a_mounted_laptop_blocks(self):
        self.assertEqual(line(self.out, "SWAP_OFF"), "SWAP_OFF 0 0 0 -1")
        self.assertEqual(line(self.out, "SWAP_ON"), "SWAP_ON 1 1 0 10000")
        self.assertEqual(line(self.out, "LAPTOP"), "LAPTOP 1 0 1 -1")
        self.assertEqual(line(self.out, "LAPTOP_HELD"), "LAPTOP_HELD 1 0 1 -1")
        self.assertEqual(line(self.out, "LAPTOP_SLEEP"), "LAPTOP_SLEEP 1 0 1 -1")

    def test_host_ending_the_connection_opens_a_new_window(self):
        self.assertEqual(line(self.out, "UNMOUNT"), "UNMOUNT 1 1 0 10000")
        self.assertEqual(line(self.out, "UNMOUNT_10S"), "UNMOUNT_10S 0 0 0 -1")

    def test_vbus_gone_ends_the_window(self):
        self.assertEqual(line(self.out, "REPLUG"), "REPLUG 0 0 0 -1")
        self.assertEqual(line(self.out, "REPLUG_ON"), "REPLUG_ON 1 1 0 10000")
        self.assertEqual(line(self.out, "REPLUG_OFF"), "REPLUG_OFF 0 0 0 -1")

    def test_window_across_the_millis_wrap(self):
        self.assertEqual(line(self.out, "WRAP"), "WRAP 1 1 0 10000")
        self.assertEqual(line(self.out, "WRAP_MID"), "WRAP_MID 1 1 0 1")
        self.assertEqual(line(self.out, "WRAP_END"), "WRAP_END 0 0 0 -1")

    def test_sleep_length_is_the_nearest_deadline_capped_at_one_second(self):
        self.assertEqual(line(self.out, "PLAN_IDLE"), "PLAN_IDLE sleep 1000")
        self.assertEqual(line(self.out, "PLAN_VCOM"), "PLAN_VCOM sleep 500")
        self.assertEqual(line(self.out, "PLAN_AT"), "PLAN_AT sleep 120")
        self.assertEqual(line(self.out, "PLAN_NEVER"), "PLAN_NEVER sleep 1000")

    def test_deadline_below_10_ms_or_past_means_no_sleep(self):
        self.assertEqual(line(self.out, "PLAN_SHORT"), "PLAN_SHORT short 0")
        self.assertEqual(line(self.out, "PLAN_PAST"), "PLAN_PAST short 0")
        self.assertEqual(line(self.out, "PLAN_MIN"), "PLAN_MIN sleep 10")

    def test_first_reason_wins_and_only_prep_node_usb_end_standby(self):
        self.assertEqual(line(self.out, "PLAN_BLOCK"), "PLAN_BLOCK radio 0")
        self.assertEqual(line(self.out, "PERSISTENT"), "PERSISTENT 111 000000")
        self.assertEqual(line(self.out, "NAMES"), "NAMES sleep prep node usb radio panel screen work short")

    def test_hold_extends_never_shortens_and_survives_the_wrap(self):
        self.assertEqual(line(self.out, "HOLD"), "HOLD 0 1 1 0 1 0")

    def test_extcomin_inverts_every_half_second_of_real_time(self):
        self.assertEqual(line(self.out, "VCOM_FREE"), "VCOM_FREE 0 500")
        # 300 ms left 200 ms after taking the pin; no change at 499 ms, change at 500 ms (low); a wake 700 ms
        # late changes once (back high), and the next change is a full half period after that wake.
        self.assertEqual(line(self.out, "VCOM"), "VCOM 300 0 1 0 1 0 1 400")
        self.assertEqual(line(self.out, "VCOM_DUE"), "VCOM_DUE 0")
        self.assertEqual(line(self.out, "VCOM_RELEASED"), "VCOM_RELEASED 0 0 500")

    def test_alarm_led_and_buzzer_deadlines(self):
        # Nothing to show: none; flash on: 30 ms to its end; off: 4950 ms to the next flash, 0 when overdue;
        # alarm screen: 1500 ms to the next beep (before the next flash at 6000 ms).
        self.assertEqual(line(self.out, "ANNUNCIATOR"), "ANNUNCIATOR -1 30 4950 0 1500")


if __name__ == "__main__":
    unittest.main()
