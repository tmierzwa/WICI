# SPDX-License-Identifier: MIT
"""RAM of the station stack with 32-bit pointers, from traffic recorded in the compatibility trial.

The "host" program (firmware/src/host/node_host.cpp) on a 64-bit computer gives only an upper bound
for the TLSF pool of the stack: pointers, std::vector and hash-map nodes are twice as large as on the
nRF52840. This tool builds the same program as a 32-bit (i386) Linux binary in Docker, with the stack
configuration from platformio.ini ([stack] rns_flags and pool_flags), and replays the datagrams that reference
Reticulum sent to the station during `rns_interop.py --fill N --capture FILE`: the announces fill the
path table and known identities through the P1 interface and IFAC as in the trial. Then the packet
hash list is filled to 4096 entries. The station status (pool used and peak, path table, FRAM file
system) after start and with full tables is printed as one JSON object {"start": ..., "full": ...}.

i386 has the same type sizes as arm-none-eabi (ILP32); 64-bit integers are 4-byte aligned in
structures on i386 and 8-byte aligned on ARM, so the result can be a few bytes per object lower than
on the MCU. Sources go into the container as a tar stream (no volume mounts); compilation runs under
emulation on non-x86 hosts (about 10 minutes).

  python3 firmware/tools/stack_deps.py   # fetch the pinned stack into firmware/.pio/stack
  python3 firmware/tools/rns_ram32.py --capture capture.hex
"""

import argparse
import configparser
import io
from pathlib import Path
import subprocess
import sys
import tarfile

FIRMWARE = Path(__file__).resolve().parents[1]
IMAGE = "debian:bookworm-slim"
SOURCES = ["src/framfs.cpp", "src/p1frame.cpp", "src/p1iface.cpp", "src/rns_node.cpp", "src/host/node_host.cpp"]
STACK_SOURCES = ["Crypto/*.cpp", "microReticulum/src/microReticulum/**/*.cpp", "microReticulum/src/microReticulum/**/*.c"]
INCLUDES = ["microReticulum/src", "microStore/include", "Crypto", "MsgPack", "ArxContainer", "ArxTypeTraits", "DebugLog",
            "ArduinoJson/src"]
NETWORK_KEY = "5749434954335f696661635f74657374"

REPLAY = r'''
import json, socket, subprocess, sys, time
lines = [l.strip() for l in open("/work/capture.hex") if l.strip()]
p = subprocess.Popen(["/work/program", "--fram", "/work/fram.bin", "--listen", "47600", "--peer", "47601", "--ifac", sys.argv[1]],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
def command(text, event):
    p.stdin.write(text + "\n"); p.stdin.flush()
    for line in p.stdout:
        if line.startswith("{") and json.loads(line)["event"] == event:
            return json.loads(line)
def ready():
    for line in p.stdout:
        if line.startswith("{") and json.loads(line)["event"] == "ready":
            return json.loads(line)
ready()
start = command("status", "status")
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
for line in lines:
    s.sendto(bytes.fromhex(line), ("127.0.0.1", 47600))
    time.sleep(float(sys.argv[3]))
last, stable = -1, 0
while stable < 3:
    time.sleep(5)
    status = command("status", "status")
    stable = stable + 1 if status["paths"] == last else 0
    last = status["paths"]
command("hashes %d" % max(0, int(sys.argv[2]) - status["hashes"]), "hashes")
status = command("status", "status")
status["datagrams_replayed"] = len(lines)
print(json.dumps({"start": start, "full": status}))
command("quit", "none")
'''


def stack_flags():
    config = configparser.ConfigParser(inline_comment_prefixes=(";",), interpolation=None)
    config.read(FIRMWARE / "platformio.ini")
    flags = []
    for line in (config["stack"]["rns_flags"] + "\n" + config["stack"]["pool_flags"]).splitlines():
        line = line.split(";")[0].strip()
        if line:
            flags.append(line)
    return flags


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", required=True, help="datagram file from rns_interop.py --capture")
    parser.add_argument("--hashes", type=int, default=4096)
    parser.add_argument("--spacing", type=float, default=0.3, help="seconds between replayed datagrams")
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args()
    stack = FIRMWARE / ".pio" / "stack"
    if not (stack / "microReticulum").is_dir():
        sys.exit("no pinned stack in firmware/.pio/stack: run python3 firmware/tools/stack_deps.py first")
    flags = ["-std=gnu++17", "-fexceptions", "-frtti", "-O1", "-w", "-DNATIVE", "-DRNS_HEAP_POOL_BUFFER_SIZE=1048576"]
    flags += [f.replace("-Isrc", "-I/fw/src") for f in stack_flags()]
    flags += [f"-isystem /fw/.pio/stack/{i}" for i in INCLUDES]
    sources = [f"/fw/{s}" for s in SOURCES]
    for pattern in STACK_SOURCES:
        sources += [f"/fw/.pio/stack/{p.relative_to(stack)}" for p in sorted(stack.glob(pattern))
                    if p.name != "main.cpp" and "/examples/" not in str(p) and "/test" not in str(p)]
    objects, compile_lines = [], []
    includes = " ".join(f"-isystem /fw/.pio/stack/{i}" for i in INCLUDES)
    for i, source in enumerate(sources):
        obj = f"/work/obj/{i}.o"
        objects.append(obj)
        if source.endswith(".c"):
            compile_lines.append(f"gcc -std=gnu11 -O1 -w {includes} -c {source} -o {obj}")
        else:
            compile_lines.append(f"g++ {' '.join(flags)} -c {source} -o {obj}")
    script = f"""set -e
apt-get update -qq >/dev/null && apt-get install -y -qq g++ python3 >/dev/null
mkdir -p /work/obj
tr '\\n' '\\0' < /work/compile.txt | xargs -0 -P {args.jobs} -I CMD sh -c CMD
g++ -o /work/program {' '.join(objects)}
python3 /work/replay.py {NETWORK_KEY} {args.hashes} {args.spacing}
"""
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        def skip_git(info):
            return None if "/.git" in info.name else info
        tar.add(FIRMWARE / "src", arcname="fw/src", filter=skip_git)
        for name in sorted({i.split("/")[0] for i in INCLUDES}):
            tar.add(stack / name, arcname=f"fw/.pio/stack/{name}", filter=skip_git)
        for name, text in (("capture.hex", Path(args.capture).read_text()), ("replay.py", REPLAY),
                           ("compile.txt", "\n".join(compile_lines) + "\n"), ("run.sh", script)):
            data = text.encode()
            info = tarfile.TarInfo(f"work/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    run = subprocess.run(["docker", "run", "-i", "--rm", "--platform", "linux/386", IMAGE, "sh", "-c",
                          "tar xf - -C / && sh /work/run.sh"], input=archive.getvalue(), capture_output=True)
    if run.returncode:
        sys.stderr.write(run.stdout.decode()[-4000:] + run.stderr.decode()[-4000:])
        return run.returncode
    print(run.stdout.decode().strip().splitlines()[-1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
