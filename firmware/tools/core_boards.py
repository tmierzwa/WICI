# SPDX-License-Identifier: MIT
"""Compile the station Reticulum core with the board toolchains and report stack and static RAM.

The station images do not link the core yet (stage R6, firmware/reticulum-core.md), so a regression
on the boards would stay hidden until then. For each PlatformIO environment given (default bench-a
for nRF52840 and l0 for ESP32-S3) this tool takes the compiler, flags, defines and include paths of
the image from `pio project metadata` and compiles every file of lib/reticulum_core with them, as
C++17 without exceptions and RTTI and with -Wall -Wextra -Werror; the Crypto units the core uses are
compiled like in the image (-w -Os, tools/stack_deps.py). Nothing is linked into an image.

From -fstack-usage and the relocations of the objects (calls between functions) it prints the
deepest stack of the core entry points with the call path, and the static RAM of the core
(.data and .bss). It fails when a core file warns, when a function has a dynamic stack (VLA,
alloca), when the call graph has recursion, when a core entry point needs more than STACK_LIMIT
bytes of stack, or when the core has static RAM. Calls through function pointers or virtual
functions are not in the graph (the core has none; in Crypto only the Hash interface, called
directly by the core); library functions (memcpy, memset) count as 0 B.

  python3 firmware/tools/stack_deps.py
  python3 firmware/tools/core_boards.py [-e bench-a -e l0] [--json]
"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

FIRMWARE = Path(__file__).resolve().parents[1]
CORE = FIRMWARE / "lib" / "reticulum_core" / "src"
CRYPTO = FIRMWARE / ".pio" / "stack" / "Crypto"
# Z biblioteki Crypto tylko to, czego rdzeń używa (na ESP32 AES z modułu sprzętowego, AESEsp32.cpp).
CRYPTO_UNITS = ["AES256.cpp", "AESCommon.cpp", "AESEsp32.cpp", "BigNumberUtil.cpp", "BlockCipher.cpp", "Crypto.cpp",
                "Curve25519.cpp", "Ed25519.cpp", "Hash.cpp", "SHA256.cpp", "SHA512.cpp"]
CORE_FLAGS = ["-std=gnu++17", "-fno-exceptions", "-fno-rtti", "-Wall", "-Wextra", "-Werror"]
# Stos zadania stacji to 16 KB (main.cpp, STATION_STACK_WORDS i SET_LOOP_TASK_STACK_SIZE); rdzeń wywołany
# z warstwy rnsnode może wziąć najwyżej tyle, żeby zostało miejsce na stację, rnsnode i przerwania.
STACK_LIMIT = 4096
# Funkcje publiczne rdzenia (przestrzeń nazw rnscore poza anonimową), dla nich liczony jest stos.
ENTRY = re.compile(r"^rnscore::(?!\{anonymous\})")


def metadata(env: str) -> dict:
    out = subprocess.run(["pio", "project", "metadata", "-e", env, "--json-output"], cwd=FIRMWARE, check=True,
                         capture_output=True, text=True).stdout
    # pio może wypisać przed JSON komunikaty o instalacji pakietów
    return json.loads(out[out.index("{"):])[env]


def image_flags(meta: dict) -> list[str]:
    """Flagi obrazu bez standardu języka, wyjątków, RTTI i ustawień ostrzeżeń (te daje wywołujący)."""
    flags = []
    skip = False
    for flag in meta["cxx_flags"]:
        if skip:
            flags.append(flag)
            skip = False
            continue
        if flag in ("--param", "-u"):
            flags.append(flag)
            skip = True
            continue
        if flag.startswith(("-std=", "-W", "-MMD")) or flag in ("-fexceptions", "-frtti", "-w"):
            continue
        flags.append(flag)
    return flags


def symbol_name(name: str) -> str:
    """Nazwa funkcji bez typu wyniku, argumentów i argumentów szablonu, wspólna dla .su i c++filt."""
    name = name.replace("(anonymous namespace)", "{anonymous}")
    out, depth = "", 0
    for c in name:
        if c == "<":
            depth += 1
        elif c == ">":
            depth -= 1
        elif depth == 0:
            if c == "(":   # argumenty funkcji
                break
            out += c
    return out.split(" ")[-1]


def compile_units(env: str, out: Path) -> tuple[dict, list[Path], str]:
    meta = metadata(env)
    cxx = meta["cxx_path"]
    common = [*image_flags(meta), *(f"-D{d}" for d in meta["defines"]), f"-I{CORE}", f"-I{CRYPTO}",
              *(f"-I{i}" for i in meta["includes"]["build"])]
    objects, warnings = [], ""
    for source in sorted(CORE.glob("*.cpp")):
        objects.append(out / f"core_{source.stem}.o")
        r = subprocess.run([cxx, *common, *CORE_FLAGS, "-fstack-usage", "-c", str(source), "-o", str(objects[-1])],
                           capture_output=True, text=True)
        warnings += r.stderr
        if r.returncode:
            raise SystemExit(f"{env}: {source.name} does not compile with the image flags\n{r.stderr}")
    for unit in CRYPTO_UNITS:
        objects.append(out / f"crypto_{Path(unit).stem}.o")
        subprocess.run([cxx, *common, "-std=gnu++17", "-w", "-Os", "-fstack-usage", "-c", str(CRYPTO / unit), "-o",
                        str(objects[-1])], check=True, capture_output=True, text=True)
    return meta, objects, warnings


def tool(meta: dict, name: str) -> str:
    return re.sub(r"g\+\+$", name, meta["cxx_path"])


def demangle(meta: dict, names: list[str]) -> dict:
    plain = subprocess.run([tool(meta, "c++filt")], input="\n".join(names), check=True, capture_output=True,
                           text=True).stdout.splitlines()
    return {m: symbol_name(p) for m, p in zip(names, plain)}


def stack_frames(meta: dict, objects: list[Path]) -> tuple[dict, dict, list[str]]:
    """Ramka stosu każdej funkcji po nazwie z pliku obiektowego (przeciążenia osobno).

    Plik .su ma funkcje w kolejności, w jakiej kompilator je wypisał, z nazwą bez typów z pliku
    obiektowego; przy -ffunction-sections ta sama kolejność mają sekcje .text.<nazwa> w obiekcie.
    Rozbieżność nazw w parze przerywa sprawdzenie.
    """
    frames, names, dynamic = {}, {}, []
    for obj in objects:
        su = []
        for line in obj.with_suffix(".su").read_text().splitlines():
            where, size, kind = line.rsplit("\t", 2)
            printable = where.split(":", 3)[3]
            su.append((symbol_name(printable), int(size)))
            if "dynamic" in kind and "bounded" not in kind:
                dynamic.append(f"{obj.stem}: {printable} ({kind})")
        headers = subprocess.run([tool(meta, "readelf"), "-SW", str(obj)], check=True, capture_output=True,
                                 text=True).stdout
        sections = re.findall(r"\]\s+\.text\.(?:unlikely\.|hot\.|startup\.)?(\S+)\s", headers)
        plain = demangle(meta, sections)
        if [plain[m] for m in sections] != [name for name, _ in su]:
            raise SystemExit(f"{obj.name}: functions in .su and sections differ\n{sections}\n{su}")
        for mangled, (name, size) in zip(sections, su):
            frames[mangled] = size
            names[mangled] = name
    return frames, names, dynamic


def call_graph(meta: dict, objects: list[Path], known: dict) -> dict:
    """Wywołania z relokacji: sekcja .text.F (i .literal.F na Xtensie) odwołuje się do funkcji G."""
    graph = {}
    for obj in objects:
        text = subprocess.run([tool(meta, "readelf"), "-rW", str(obj)], check=True, capture_output=True,
                              text=True).stdout
        section = None
        for line in text.splitlines():
            m = re.match(r"Relocation section '\.rela?\.(?:text|literal)\.(\S+)'", line)
            if line.startswith("Relocation section"):
                section = m.group(1) if m else None
                continue
            fields = line.split()
            if section and len(fields) >= 5 and re.match(r"^[0-9a-f]{8}$", fields[0]):
                target = fields[4]
                own = target.startswith(".")   # sekcja, np. własna pula literałów na Xtensie, nie wywołanie
                target = re.sub(r"^\.(?:text|literal)\.", "", target)
                if section in known and target in known and not (own and target == section):
                    graph.setdefault(section, set()).add(target)
    return graph


def deepest(name: str, frames: dict, graph: dict, path: tuple = ()) -> tuple[int, list[str]]:
    if name in path:
        raise SystemExit(f"recursion: {' -> '.join(path + (name,))}")
    best, best_path = 0, []
    for callee in sorted(graph.get(name, ())):
        size, sub = deepest(callee, frames, graph, path + (name,))
        if size > best:
            best, best_path = size, sub
    return frames[name] + best, [name, *best_path]


def static_ram(meta: dict, objects: list[Path]) -> int:
    core = [str(o) for o in objects if o.stem.startswith("core_")]
    text = subprocess.run([tool(meta, "size"), "-A", *core], check=True, capture_output=True, text=True).stdout
    total = 0
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and re.match(r"^\.(data|bss|sbss|sdata|dram)", fields[0]):
            total += int(fields[1])
    return total


def check(env: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        meta, objects, warnings = compile_units(env, Path(tmp))
        frames, names, dynamic = stack_frames(meta, objects)
        graph = call_graph(meta, objects, frames)
        entries = {}
        for mangled in sorted(frames):
            if ENTRY.match(names[mangled]):
                size, path = deepest(mangled, frames, graph)
                entries[names[mangled]] = {"stack": size, "path": [f"{names[n]} {frames[n]}" for n in path]}
        return {"env": env, "compiler": subprocess.run([meta["cxx_path"], "--version"], capture_output=True,
                                                       text=True).stdout.splitlines()[0],
                "warnings": warnings.strip(), "dynamic": dynamic, "static_ram": static_ram(meta, objects),
                "entries": entries}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-e", "--env", action="append", help="PlatformIO environment (default: bench-a, l0)")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args()
    if not shutil.which("pio"):
        raise SystemExit("pio not found")
    if not (CRYPTO / ".wici-stamp").is_file():
        raise SystemExit("stack sources not fetched (python3 firmware/tools/stack_deps.py)")
    failed = False
    results = []
    for env in args.env or ["bench-a", "l0"]:
        r = check(env)
        results.append(r)
        over = {n: e for n, e in r["entries"].items() if e["stack"] > STACK_LIMIT}
        if r["warnings"] or r["dynamic"] or r["static_ram"] or over:
            failed = True
        if args.json:
            continue
        print(f"{env}: {r['compiler']}")
        print(f"  static RAM of the core: {r['static_ram']} B; dynamic stack: {r['dynamic'] or 'none'}")
        if r["warnings"]:
            print(f"  warnings:\n{r['warnings']}")
        for name, e in sorted(r["entries"].items(), key=lambda item: -item[1]["stack"]):
            print(f"  {e['stack']:6d} B  {name}: {' > '.join(e['path'])}")
        for name in over:
            print(f"  over {STACK_LIMIT} B: {name}")
    if args.json:
        print(json.dumps(results, indent=1, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
