# SPDX-License-Identifier: MIT
"""Hostile node for the D21 bench (trial 9): a RAK4631 with lora-raw (hardware/lora-raw) loads the channel.

Modes: junk = random bytes in the LoRa profile without a key; keyed = WICI-Link v3 frames with the network
MAC (key from the network code and net_id) as a captured station: broadcast DATA floods with random envelopes,
BEACONs with garbage signatures, unicast DATA and HACK without a valid hop tag, from random l_src. No CAD,
no silence debt. The share of channel time is held at --occupancy from the device's measured TxDone times
(lora_raw.Pacer). Every transmission goes to the JSONL log.

Above 10 % occupancy the 869.4-869.65 MHz band limit is exceeded on air: run it only cabled through
attenuators or in a shielded enclosure (hardware/xiao-wici/README.md), and confirm with --conducted.
"""

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lora_raw  # noqa: E402

BAND_DUTY_CYCLE = 0.10


class Hostile:
    def __init__(self, device, out, make_frame, occupancy, clock=time.monotonic, sleep=time.sleep, wall=time.time):
        self.device = device
        self.out = out
        self.make_frame = make_frame
        self.pacer = lora_raw.Pacer(occupancy)
        self.clock, self.sleep, self.wall = clock, sleep, wall
        self.counts = {}
        self.airtime_us = {}
        self.errors = 0
        self.last_done = None  # (host monotonic time of the TxDone line, device done_us)

    def write(self, record):
        self.out.write(json.dumps(record, sort_keys=True) + "\n")
        self.out.flush()

    def device_now_us(self):
        host, done_us = self.last_done
        return done_us + (self.clock() - host) * 1e6

    def send_one(self):
        if self.last_done is not None:
            wait = self.pacer.wait_s(self.device_now_us())
            if wait > 0:
                self.sleep(wait)
        raw, fields = self.make_frame()
        self.device.command("tx " + raw.hex())
        try:
            host, record = self.device.wait_for(lambda r: r.get("tx") == "done" or "err" in r, 2.0)
        except TimeoutError:
            self.errors += 1
            self.write({"host_ts": round(self.wall(), 6), "error": "no TxDone", "hex": raw.hex(), **fields})
            return False
        if "err" in record:
            self.errors += 1
            self.write({"host_ts": round(self.wall(), 6), "error": record, "hex": raw.hex(), **fields})
            return False
        self.last_done = (host, record["done_us"])
        self.pacer.done(record["start_us"], record["done_us"])
        kind = fields["kind"]
        self.counts[kind] = self.counts.get(kind, 0) + 1
        self.airtime_us[kind] = self.airtime_us.get(kind, 0) + record["air_us"]
        self.write({"host_ts": round(self.wall(), 6), "len": len(raw), "hex": raw.hex(),
                    "start_us": record["start_us"], "done_us": record["done_us"], "air_us": record["air_us"],
                    "toa_us": record.get("toa_us"), "power_dbm": record.get("power_dbm"),
                    "occupancy": round(self.pacer.occupancy() or 0, 6), **fields})
        return True

    def run(self, duration_s, max_errors=20):
        started = self.clock()
        while self.clock() - started < duration_s:
            if not self.send_one() and self.errors >= max_errors:
                break
        return self.finish()

    def finish(self):
        span = (self.pacer.last_done - self.pacer.first_start) if self.pacer.first_start is not None else 0
        result = {"summary": {
            "target_occupancy": self.pacer.target,
            "occupancy": round(self.pacer.occupancy() or 0, 6),
            "span_s": round(span / 1e6, 3),
            "frames": dict(sorted(self.counts.items())),
            "airtime_s": {k: round(v / 1e6, 6) for k, v in sorted(self.airtime_us.items())},
            "errors": self.errors}, "host_ts": round(self.wall(), 6)}
        self.write(result)
        return result


def frame_source(args, rng):
    if args.mode == "junk":
        return lambda: (lora_raw.junk_frame(rng, args.min_len, args.max_len), {"kind": "junk"})
    key = lora_raw.network_key(args.ifac, args.net_id)
    mix = lora_raw.parse_mix(args.mix)
    names, weights = [n for n, _ in mix], [w for _, w in mix]
    sources, destinations = lora_raw.parse_ids(args.src), lora_raw.parse_ids(args.dst)

    def make():
        kind = rng.choices(names, weights)[0]
        return lora_raw.keyed_frame(rng, key, args.net_id, kind, sources, destinations)
    return make


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("port", help="serial port of the RAK4631 with lora-raw")
    parser.add_argument("--mode", choices=("junk", "keyed"), required=True)
    parser.add_argument("--out", required=True, type=Path, help="JSONL log (appended)")
    parser.add_argument("--occupancy", type=float, default=0.5, help="target share of channel time (default 0.5)")
    parser.add_argument("--duration", type=float, default=7200, help="seconds (default 7200)")
    parser.add_argument("--power", type=int, default=-9, help="dBm at the SX1262, -9..22 (default -9)")
    parser.add_argument("--conducted", action="store_true",
                        help="confirm cabled attenuators or a shielded enclosure (required above 10%%)")
    parser.add_argument("--min-len", type=int, default=20, help="junk: shortest frame (default 20)")
    parser.add_argument("--max-len", type=int, default=255, help="junk: longest frame (default 255)")
    parser.add_argument("--ifac", help="keyed: network code, 32 hex digits")
    parser.add_argument("--net-id", type=int, help="keyed: net_id")
    parser.add_argument("--mix", default="data=2,beacon=1,unicast=1,hack=1", help="keyed: frame kinds and weights")
    parser.add_argument("--src", default="", help="keyed: l_src numbers, comma separated (default random)")
    parser.add_argument("--dst", default="", help="keyed: unicast l_dst numbers, e.g. B's number (default random)")
    parser.add_argument("--seed", type=int, help="random seed (log it in the report)")
    args = parser.parse_args(argv)
    if not 0 < args.occupancy < 1:
        parser.error("--occupancy must be in (0, 1)")
    if args.occupancy > BAND_DUTY_CYCLE and not args.conducted:
        parser.error("above 10% occupancy the band limit is exceeded on air: use attenuators or a shielded "
                     "enclosure and pass --conducted")
    if not 1 <= args.min_len <= args.max_len <= 255:
        parser.error("need 1 <= --min-len <= --max-len <= 255")
    if args.mode == "keyed" and not (args.ifac and args.net_id):
        parser.error("keyed mode needs --ifac and --net-id")
    rng = lora_raw.new_rng(args.seed)
    make = frame_source(args, rng)
    port = lora_raw.open_port(args.port)
    device = lora_raw.Device(port)
    try:
        port.reset_input_buffer()
        info = device.info()
        lora_raw.check_info(info)
        device.command("rx off")
        device.wait_for(lambda r: "rx_stream" in r, 2.0)
        device.command(f"power {args.power}")
        _, power = device.wait_for(lambda r: "power_dbm" in r or "err" in r, 2.0)
        if power.get("power_dbm") != args.power:
            raise RuntimeError(f"power not set: {power}")
        with args.out.open("a", encoding="utf-8") as out:
            hostile = Hostile(device, out, make, args.occupancy)
            hostile.write({"host_ts": round(time.time(), 6), "device": info, "tool": "hostile", "mode": args.mode,
                           "occupancy": args.occupancy, "power_dbm": args.power, "seed": args.seed,
                           "mix": args.mix if args.mode == "keyed" else None, "net_id": args.net_id})
            print(f"hostile {args.mode}: {args.occupancy:.0%} for {args.duration:.0f} s; Ctrl+C ends", file=sys.stderr)
            try:
                result = hostile.run(args.duration)
            except KeyboardInterrupt:
                result = hostile.finish()
        print(json.dumps(result["summary"], indent=2))
    finally:
        port.close()


if __name__ == "__main__":
    main()
