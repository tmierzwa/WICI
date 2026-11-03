# SPDX-License-Identifier: MIT
"""D21 bench tools for the lora-raw firmware (hardware/xiao-wici/tools): parsing, frames, airtime, pacing.

No hardware: the hostile loop runs against a simulated device with its own clock and USB latency.
"""

import io
import json
from pathlib import Path
import random
import sys
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hardware" / "xiao-wici" / "tools"))

import hostile  # noqa: E402
import lora_raw  # noqa: E402
import monitor  # noqa: E402
from wici.stanowisko import wici_link  # noqa: E402  (path set by lora_raw)

IFAC = bytes(range(16))
NET = 100
KEY = wici_link.derive_key(IFAC, NET)


class Airtime(unittest.TestCase):
    def test_profile_values(self):
        # 255 B: 24 + 4.25 + 378 symbols x 1.024 ms (firmware lora::frameAirUs(255) = 416000 us).
        self.assertAlmostEqual(lora_raw.airtime_s(255), 0.416, places=9)
        # HACK 29 B and BEACON 156 B as in docs/spec/wici-link.md (87 ms and 276 ms with ramp, rounded up).
        self.assertAlmostEqual(lora_raw.airtime_s(29), 0.0832, places=9)
        self.assertAlmostEqual(lora_raw.airtime_s(156), 0.27264, places=9)

    def test_same_formula_as_reference_model(self):
        from obliczenia import lora_frame_seconds
        for length in (1, 19, 52, 200, 255):
            self.assertEqual(lora_raw.airtime_s(length), lora_frame_seconds(length, 7, preamble_symbols=24))


class Header(unittest.TestCase):
    def test_v3_fields(self):
        raw = wici_link.encode(KEY, wici_link.Frame(wici_link.DATA, wici_link.ACKREQ, NET, 20, 10, 2, 7, 0x1234,
                                                    bytes(30)))
        header = lora_raw.v3_header(raw)
        self.assertEqual(header, {"version": 3, "type": 0, "type_name": "DATA", "flags": 1, "ackreq": True,
                                  "down": False, "net_id": NET, "l_src": 20, "l_dst": 10, "unicast": True,
                                  "hops": 2, "ttl": 7, "seq": 0x1234, "opts": 0})

    def test_not_v3(self):
        self.assertIsNone(lora_raw.v3_header(b"\x40" + bytes(20)))
        self.assertIsNone(lora_raw.v3_header(b"\xc0" + bytes(5)))
        self.assertEqual(lora_raw.frame_class(b"\x00" * 30), "other")
        self.assertEqual(lora_raw.frame_class(b"\xc0" * 30, crc=False), "crc_error")

    def test_rnode_header_breaks_v3(self):
        # RNode prepends one header byte (random upper nibble, bit 0 split flag): the frame is shifted by one
        # byte, so its MAC no longer verifies even when the random nibble happens to look like version 3.
        raw = wici_link.encode(KEY, wici_link.Frame(wici_link.HACK, 0, NET, 10, 20, 0, 1, 5, bytes(2))) + bytes(8)
        self.assertTrue(lora_raw.mac_ok(KEY, raw))
        for nibble in range(16):
            self.assertFalse(lora_raw.mac_ok(KEY, bytes([nibble << 4]) + raw))

    def test_mac_broadcast_and_unicast(self):
        rng = random.Random(1)
        for kind in ("data", "beacon", "unicast", "hack"):
            raw, fields = lora_raw.keyed_frame(rng, KEY, NET, kind, [7], [10])
            self.assertTrue(lora_raw.mac_ok(KEY, raw), kind)
            self.assertFalse(lora_raw.mac_ok(wici_link.derive_key(bytes(16), NET), raw), kind)
            self.assertEqual(fields["l_src"], 7)


class KeyedFrames(unittest.TestCase):
    def test_kinds(self):
        rng = random.Random(2)
        for _ in range(50):
            raw, fields = lora_raw.keyed_frame(rng, KEY, NET, "data")
            frame = wici_link.decode(KEY, NET, raw)  # broadcast frames carry only the network MAC
            self.assertEqual((frame.kind, frame.flags, frame.destination), (wici_link.DATA, wici_link.DOWN,
                                                                            wici_link.BROADCAST))
            self.assertTrue(25 <= len(frame.payload) <= wici_link.MAX_PAYLOAD)
            self.assertTrue(1 <= fields["l_src"] <= 0xFFFE)
            raw, _ = lora_raw.keyed_frame(rng, KEY, NET, "beacon")
            self.assertEqual(len(raw), 156)
            self.assertEqual(wici_link.decode(KEY, NET, raw).kind, wici_link.BEACON)
            raw, fields = lora_raw.keyed_frame(rng, KEY, NET, "unicast", destinations=[10])
            header = lora_raw.v3_header(raw)
            self.assertTrue(header["ackreq"] and header["unicast"] and header["l_dst"] == 10)
            self.assertLessEqual(len(raw), 255)
            with self.assertRaises(wici_link.LinkError):  # MAC is not where a broadcast frame has it
                wici_link.decode(KEY, NET, raw)
            raw, _ = lora_raw.keyed_frame(rng, KEY, NET, "hack", destinations=[10])
            self.assertEqual(len(raw), 29)
            self.assertEqual(lora_raw.v3_header(raw)["type_name"], "HACK")

    def test_junk(self):
        rng = random.Random(3)
        lengths = set()
        for _ in range(500):
            raw = lora_raw.junk_frame(rng, 20, 255)
            lengths.add(len(raw))
            self.assertTrue(20 <= len(raw) <= 255)
            self.assertEqual(lora_raw.frame_class(raw), "other")
        self.assertIn(255, lengths)

    def test_mix_and_ids(self):
        self.assertEqual(lora_raw.parse_mix("data=2,hack"), [("data", 2.0), ("hack", 1.0)])
        with self.assertRaises(ValueError):
            lora_raw.parse_mix("ping=1")
        self.assertEqual(lora_raw.parse_ids("10, 20"), [10, 20])
        self.assertEqual(lora_raw.parse_ids(""), [])


class DeviceLines(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(lora_raw.parse_device_line(b'{"tx":"done","n":1}\r\n'), {"tx": "done", "n": 1})
        self.assertIsNone(lora_raw.parse_device_line(b"garbage\n"))
        self.assertIsNone(lora_raw.parse_device_line(b'{"broken\n'))
        self.assertIsNone(lora_raw.parse_device_line(""))

    def test_check_info(self):
        info = {"info": "lora-raw-0.2", "ready": True, **lora_raw.PROFILE}
        lora_raw.check_info(info)
        with self.assertRaises(RuntimeError):
            lora_raw.check_info({**info, "preamble": 8})
        with self.assertRaises(RuntimeError):
            lora_raw.check_info({**info, "ready": False})

    def test_monitor_records_and_summary(self):
        out = io.StringIO()
        clock = iter([0.0, 10.0])
        mon = monitor.Monitor(out, KEY, clock=lambda: next(clock), wall=lambda: 1700000000.0)
        beacon, _ = lora_raw.keyed_frame(random.Random(4), KEY, NET, "beacon", [1])
        hack, _ = lora_raw.keyed_frame(random.Random(5), KEY, NET, "hack", [10], [20])
        frame = mon.handle({"rx": beacon.hex(), "len": 156, "rssi": -40.5, "snr": 9.25, "crc": True, "t_us": 5_000_000})
        self.assertEqual(frame["class"], "BEACON")
        self.assertTrue(frame["mac_ok"])
        self.assertEqual(frame["start_us"], 5_000_000 - 272_640)
        self.assertEqual(frame["v3"]["l_src"], 1)
        mon.handle({"rx": hack.hex(), "len": 27, "rssi": -41.0, "snr": 8.0, "crc": True, "t_us": 6_000_000})
        mon.handle({"rx": "c0" * 40, "len": 40, "rssi": -100.0, "snr": -5.0, "crc": False, "t_us": 7_000_000})
        mon.handle({"rx": "00" * 10, "len": 10, "rssi": -90.0, "snr": 1.0, "crc": True, "t_us": 8_000_000})
        mon.handle({"err": "read", "code": -7})
        summary = mon.finish()["summary"]
        self.assertEqual(summary["frames"], {"BEACON": 1, "HACK": 1, "crc_error": 1, "other": 1})
        total = sum(lora_raw.airtime_s(n) for n in (156, 27, 40, 10))
        self.assertAlmostEqual(summary["airtime_total_s"], total, places=6)
        self.assertEqual(set(summary["airtime_by_l_src_s"]), {"1", "10"})
        self.assertAlmostEqual(summary["occupancy_pct"], 100 * total / 10.0, places=3)
        lines = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(len(lines), 6)
        self.assertEqual(lines[4]["device"]["err"], "read")


class MonitorReconnect(unittest.TestCase):
    def test_lost_usb_is_a_gap_not_the_end(self):
        info = {"info": "lora-raw-0.2", "ready": True, **lora_raw.PROFILE}
        frame = {"rx": "00" * 10, "len": 10, "rssi": -90.0, "snr": 1.0, "crc": True, "t_us": 1}

        class Port:
            def close(self):
                pass

        class Device:
            def __init__(self, records):
                self.records = list(records)

            def read(self):
                if not self.records:
                    return 0.0, None
                item = self.records.pop(0)
                if isinstance(item, Exception):
                    raise item
                return 0.0, item

        lost = OSError("device reports readiness to read but returned no data")
        sessions = [(Port(), Device([frame, lost]), info), OSError("port gone"), (Port(), Device([frame]), info)]

        def connect(name):
            item = sessions.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        tmp = Path(self.enterContext(__import__("tempfile").TemporaryDirectory())) / "monitor.jsonl"
        with unittest.mock.patch.object(monitor, "connect", connect), \
                unittest.mock.patch.object(monitor, "RECONNECT_S", 0), \
                unittest.mock.patch("sys.stdout", io.StringIO()), unittest.mock.patch("sys.stderr", io.StringIO()):
            monitor.main(["port", "--out", str(tmp), "--duration", "0.3"])
        lines = [json.loads(line) for line in tmp.read_text().splitlines()]
        kinds = ["gap" if "gap" in x else "frame" if x.get("len") == 10 else "summary" if "summary" in x else "start"
                 for x in lines]
        self.assertEqual(kinds, ["start", "frame", "gap", "frame", "summary"])
        self.assertEqual(lines[2]["error"], str(lost))
        self.assertEqual(sessions, [])
        self.assertEqual(lines[-1]["summary"]["frames"], {"other": 2})


class SimulatedDevice:
    """lora-raw stand-in: device clock = host clock + offset, USB latency each way, TX ramp."""

    def __init__(self, latency_s=0.004, ramp_us=250):
        self.now = 0.0
        self.offset_us = 123_456_789
        self.latency_s = latency_s
        self.ramp_us = ramp_us
        self.pending = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def command(self, text):
        name, _, argument = text.partition(" ")
        assert name == "tx"
        start_us = round((self.now + self.latency_s) * 1e6) + self.offset_us
        done_us = start_us + round(lora_raw.airtime_s(len(argument) // 2) * 1e6) + self.ramp_us
        self.pending.append({"tx": "done", "len": len(argument) // 2, "start_us": start_us, "done_us": done_us,
                             "air_us": done_us - start_us})

    def wait_for(self, predicate, timeout_s, on_other=None):
        record = self.pending.pop(0)
        self.now = (record["done_us"] - self.offset_us) / 1e6 + self.latency_s
        assert predicate(record)
        return self.now, record


class Pacing(unittest.TestCase):
    def test_pacer_math(self):
        pacer = lora_raw.Pacer(0.5)
        self.assertEqual(pacer.wait_s(0), 0.0)
        pacer.done(1_000_000, 1_100_000)
        self.assertEqual(pacer.next_start_us(), 1_200_000)
        self.assertAlmostEqual(pacer.wait_s(1_100_000), 0.1)
        self.assertEqual(pacer.wait_s(1_300_000), 0.0)
        with self.assertRaises(ValueError):
            lora_raw.Pacer(1.0)

    def run_hostile(self, mode, occupancy, latency_s):
        device = SimulatedDevice(latency_s)
        rng = random.Random(6)
        if mode == "junk":
            make = lambda: (lora_raw.junk_frame(rng), {"kind": "junk"})  # noqa: E731
        else:
            make = lambda: lora_raw.keyed_frame(rng, KEY, NET, rng.choice(["data", "beacon", "unicast", "hack"]))  # noqa: E731
        out = io.StringIO()
        node = hostile.Hostile(device, out, make, occupancy, clock=device.clock, sleep=device.sleep, wall=lambda: 0.0)
        summary = node.run(600)["summary"]
        lines = [json.loads(line) for line in out.getvalue().splitlines()]
        return summary, lines

    def test_occupancy_held_from_txdone(self):
        for mode, target, latency in (("junk", 0.5, 0.004), ("keyed", 0.5, 0.02), ("keyed", 0.1, 0.004)):
            summary, lines = self.run_hostile(mode, target, latency)
            self.assertEqual(summary["errors"], 0)
            self.assertAlmostEqual(summary["occupancy"], target, delta=0.002, msg=(mode, target))
            air = sum(line["air_us"] for line in lines[:-1]) / 1e6
            span = (lines[-2]["done_us"] - lines[0]["start_us"]) / 1e6
            self.assertAlmostEqual(air / span, summary["occupancy"], places=5)
            self.assertGreater(sum(summary["frames"].values()), 200)

    def test_hostile_refuses_on_air_above_band_limit(self):
        with self.assertRaises(SystemExit), unittest.mock.patch("sys.stderr", io.StringIO()):
            hostile.main(["PORT", "--mode", "junk", "--out", "x.jsonl", "--occupancy", "0.5"])


if __name__ == "__main__":
    unittest.main()
