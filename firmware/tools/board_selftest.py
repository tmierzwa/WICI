# SPDX-License-Identifier: MIT
"""Self-test and timing of the station Reticulum core on a board, in one command.

For an image with the core (env:bench-a or bench-n1 on nRF52840, env:bench-b-core or l0 on ESP32-S3; stage R6-3): optionally builds
and uploads it (--upload), opens the diagnostic port, reads the log (LOG) for a failed start-up
self-test or entropy health test, runs `RNS SELFTEST` --runs times and prints per check whether it
matched the vectors from Reticulum in Python and its time in µs (median of the runs), the stack state
and entropy health from INFO and the time of the start-up self-test from the log. The raw console
lines and the summary go to a JSON file for the report (firmware/README.md, "Samotest rdzenia na płytce").
Needs pyserial; upload needs PlatformIO (pio on PATH or WICI_PIO).

  python3 firmware/tools/board_selftest.py -e bench-a --port /dev/cu.usbmodem1101 --upload
"""

import argparse
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time

FIRMWARE = Path(__file__).resolve().parents[1]
ENVS = ("bench-a", "bench-n1", "bench-b-core", "l0")


def summarize(lines: list[str]) -> dict:
    """Wynik z wierszy konsoli: próby samotestu (zgodność i mediana czasu), wynik każdego przebiegu, stan
    stosu i zdrowie entropii z INFO, czas samotestu przy starcie i wpisy dziennika o stosie i entropii."""
    checks, runs, info, version, log, startup_ms = {}, [], {}, None, [], None
    for line in lines:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict):
            continue
        if "selftest" in message:
            entry = checks.setdefault(message["selftest"], {"ok": True, "us": []})
            entry["ok"] = entry["ok"] and message.get("ok") is True
            entry["us"].append(message.get("us"))
        elif "selftest_ok" in message:
            runs.append(message["selftest_ok"] is True)
            version = message.get("version")
        elif "rns_state" in message:
            info = {"rns_state": message["rns_state"], "entropy_ok": message.get("entropy_ok")}
        for event in message.get("log", []) if isinstance(message.get("log"), list) else []:
            text = event.get("text", "") if isinstance(event, dict) else ""
            m = re.match(r"core selftest ok (\d+) ms$", text)
            if m:
                startup_ms = int(m.group(1))   # ostatni start w dzienniku
            if text.startswith(("rns ", "core selftest", "entropy")):
                log.append(text)
    return {
        "version": version,
        **info,
        "startup_selftest_ms": startup_ms,
        "runs": runs,
        "ok": bool(runs) and all(runs),
        "checks": {name: {"ok": c["ok"], "us_median": statistics.median(c["us"]) if c["us"] else None,
                          "us": c["us"]} for name, c in checks.items()},
        "log": sorted(set(log)),
    }


def upload(env: str) -> None:
    pio = os.environ.get("WICI_PIO", "pio")
    subprocess.run([pio, "run", "-e", env, "-t", "upload"], cwd=FIRMWARE, check=True)


def console(port: str, commands: list[str], timeout_s: float) -> list[str]:
    import serial  # pyserial, tylko przy pracy z płytką

    lines = []
    deadline = time.monotonic() + 30
    while True:   # port znika na chwilę po wgraniu i restarcie
        try:
            link = serial.Serial(port, 115200, timeout=0.2)
            break
        except serial.SerialException:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)
    with link:
        time.sleep(2)   # obraz po otwarciu portu wysyła INFO, RADIO, FRAM i JOURNAL
        for command in commands:
            link.write(f"{command}\n".encode())
            end = time.monotonic() + timeout_s
            while time.monotonic() < end:
                raw = link.readline()
                if not raw:
                    continue
                line = raw.decode(errors="replace").strip()
                lines.append(line)
                if command.startswith("RNS SELFTEST") and '"selftest_ok"' in line:
                    break
                if not command.startswith("RNS SELFTEST") and line.startswith("{"):
                    end = min(end, time.monotonic() + 0.5)   # odpowiedź jednym wierszem (LOG: kilka)
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-e", "--env", choices=ENVS, required=True)
    parser.add_argument("--port", required=True, help="diagnostic port of the board (first CDC interface)")
    parser.add_argument("--upload", action="store_true", help="build and upload the image first")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", help="JSON file (default: selftest-<env>-<time>.json in the current folder)")
    args = parser.parse_args()
    if args.upload:
        upload(args.env)
    lines = console(args.port, ["INFO", "LOG 30", "RNS", *["RNS SELFTEST"] * args.runs], timeout_s=60)
    result = {"env": args.env, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **summarize(lines), "lines": lines}
    out = Path(args.out or f"selftest-{args.env}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    print(f"{args.env} {result['version']}: selftest {'ok' if result['ok'] else 'FAILED'} in {len(result['runs'])} runs, "
          f"rns_state {result.get('rns_state')}, entropy_ok {result.get('entropy_ok')}, "
          f"start-up selftest {result['startup_selftest_ms']} ms")
    for name, c in result["checks"].items():
        print(f"  {name:18s} {'ok' if c['ok'] else 'MISMATCH':8s} {c['us_median']} us")
    for text in result["log"]:
        print(f"  log: {text}")
    print(f"saved {out}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
