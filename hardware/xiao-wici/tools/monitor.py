# SPDX-License-Identifier: MIT
"""Channel monitor for the D21 bench: a RAK4631 with lora-raw (hardware/lora-raw) logs every LoRa frame.

Writes one JSON line per received frame (host time, device RxDone time, raw hex, length, RSSI, SNR, CRC,
airtime and the plain WICI-Link v3 header when the version bits are 3; with --ifac and --net-id also whether
the network MAC is valid). On exit (Ctrl+C or --duration) appends and prints a summary: frames and airtime
per class, airtime per l_src and channel occupancy.
"""

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lora_raw  # noqa: E402


class Monitor:
    def __init__(self, out, key=None, clock=time.monotonic, wall=time.time):
        self.out = out
        self.key = key
        self.summary = lora_raw.Summary()
        self.clock = clock
        self.wall = wall
        self.started = clock()

    def write(self, record):
        self.out.write(json.dumps(record, sort_keys=True) + "\n")
        self.out.flush()

    def handle(self, record):
        """Log one device record; returns the frame record for rx lines, else None."""
        host_ts = self.wall()
        if "rx" in record:
            frame = lora_raw.receive_record(record, host_ts, self.key)
            source = frame["v3"]["l_src"] if "v3" in frame and frame["crc"] else None
            self.summary.add(frame["class"], frame["len"], source)
            self.write(frame)
            return frame
        if "err" in record or "info" in record:
            self.write({"host_ts": round(host_ts, 6), "device": record})
        return None

    def finish(self):
        result = {"summary": self.summary.result(self.clock() - self.started), "host_ts": round(self.wall(), 6)}
        self.write(result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("port", help="serial port of the RAK4631 with lora-raw")
    parser.add_argument("--out", required=True, type=Path, help="JSONL output file (appended)")
    parser.add_argument("--duration", type=float, default=0, help="seconds to record; 0 = until Ctrl+C")
    parser.add_argument("--ifac", help="network code, 32 hex digits (only to mark mac_ok)")
    parser.add_argument("--net-id", type=int, help="net_id for --ifac")
    args = parser.parse_args(argv)
    if bool(args.ifac) != bool(args.net_id):
        parser.error("--ifac and --net-id go together")
    key = lora_raw.network_key(args.ifac, args.net_id) if args.ifac else None
    port = lora_raw.open_port(args.port)
    device = lora_raw.Device(port)
    try:
        port.reset_input_buffer()
        info = device.info()
        lora_raw.check_info(info)
        device.command("rx on")
        with args.out.open("a", encoding="utf-8") as out:
            monitor = Monitor(out, key)
            monitor.write({"host_ts": round(time.time(), 6), "device": info, "tool": "monitor"})
            print(f"monitor: {args.port} -> {args.out}; Ctrl+C ends", file=sys.stderr)
            try:
                while not args.duration or time.monotonic() - monitor.started < args.duration:
                    _, record = device.read()
                    if record is not None:
                        frame = monitor.handle(record)
                        if frame:
                            name = frame["class"]
                            src = frame.get("v3", {}).get("l_src", "-")
                            print(f"{frame['len']:3d} B {name:9s} src {src} rssi {frame['rssi']} snr {frame['snr']}",
                                  file=sys.stderr)
            except KeyboardInterrupt:
                pass
            result = monitor.finish()
        print(json.dumps(result["summary"], indent=2))
    finally:
        port.close()


if __name__ == "__main__":
    main()
