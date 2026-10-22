# SPDX-License-Identifier: MIT
"""Compile the station Reticulum core with the board toolchains and report stack and static RAM.

The station images do not link the core yet (stage R6, firmware/reticulum-core.md), so a regression
on the boards would stay hidden until then. For each PlatformIO environment given (default bench-a
for nRF52840 and l0 for ESP32-S3) this tool takes the compiler, flags, defines and include paths of
the image from `pio project metadata` and compiles every file of lib/reticulum_core with them, as
C++17 without exceptions and RTTI and with -Wall -Wextra -Werror; the Crypto units the core uses are
compiled like in the image (-w -Os, tools/stack_deps.py). Nothing is linked into an image.

From -fstack-usage and the relocations of the objects (calls between functions) it prints the
deepest stack of the core entry points with the call path. Calls through pointers are not in the
relocations: the virtual calls inside Crypto (Hash interface, SHA-256 and SHA-512) come from the
INDIRECT table, calls of the Transport hooks and of the table storage (rnscore::TableStorage, the FRAM
of rnsnode) lead out of the core (rnsnode callbacks, whose stack adds to the path) and any other indirect call (`blx rN` on ARM) fails the check. Library functions
(memcpy, the ESP-IDF AES driver) are covered by LIBRARY_RESERVE and one exception or interrupt frame
on the task stack by INTERRUPT_FRAME. Static RAM: the core files must have none (.data, .bss: no
globals in the library); the tables live in one rnscore::Transport object owned by rnsnode, so when
transport.h exists its size on the board is compared with RAM_BUDGET.

It fails when a core file warns, when a function has a dynamic stack (VLA, alloca), when the call
graph has recursion, when a core entry point needs more than STACK_LIMIT bytes of stack, when the
core files have static RAM or when rnscore::Transport exceeds RAM_BUDGET.

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
# Wywołania przez wskaźnik w bibliotece Crypto (wirtualne metody Hash, SHA256 i SHA512): ręczne krawędzie
# do funkcji o tej nazwie (każde przeciążenie i definicja), sprawdzone z kodem Crypto 984dc89.
INDIRECT = {
    "Hash::formatHMACKey": ["SHA256::reset", "SHA256::update", "SHA256::finalize", "SHA512::reset", "SHA512::update",
                            "SHA512::finalize"],
    "SHA256::finalizeHMAC": ["SHA256::update", "SHA256::finalize"],
    "SHA512::finalizeHMAC": ["SHA512::update", "SHA512::finalize"],
    "SHA256::finalize": [], "SHA512::finalize": [],   # hashSize(): stała, bez ramki
    "SHA256::clear": ["SHA256::reset"], "SHA512::clear": ["SHA512::reset"],
    "Ed25519::deriveKeys": ["SHA512::reset", "SHA512::update", "SHA512::finalize"],
}
# Wywołania przez wskaźnik w rdzeniu: tylko haki transportu (TransportHooks) i pamięć tablicy
# (TableStorage: FRAM w warstwie rnsnode, etap R2) do warstwy rnsnode.
HOOKS = re.compile(r"^rnscore::(?:Transport|Table)::")
# Funkcje bibliotek (memcpy, memset, sterownik AES ESP-IDF esp_aes_crypt_ecb) liczone jako stały zapas.
LIBRARY_RESERVE = 256
# Jedna ramka wyjątku albo przerwania na stosie zadania: Cortex-M4F z FPU 26 słów (104 B); ESP32-S3
# XT_STK_FRMSZ z xtensa_context.h ESP-IDF 5.5 (192 B). Obsługa przerwania biegnie potem na własnym stosie.
INTERRUPT_FRAME = {"arm": 104, "xtensa": 192}
# Cel dla RAM statycznej rdzenia z LXMF (reticulum-core.md, „Budżet RAM”): 56 KB, w tym lista skrótów,
# tablice tras i tożsamości; obiekt rnscore::Transport ma się w nim zmieścić z zapasem na LXMF.
RAM_BUDGET = 56 * 1024
# Przyrostki klonów funkcji GCC (.constprop.0 na ARM, $constprop$0 na Xtensie), których c++filt nie rozwija.
CLONE = re.compile(r"[.$](?:constprop|isra|part|cold|lto_priv)(?:[.$]\d+)*")


def metadata(env: str) -> dict:
    out = subprocess.run(["pio", "project", "metadata", "-e", env, "--json-output"], cwd=FIRMWARE, check=True,
                         capture_output=True, text=True).stdout
    # pio może wypisać przed JSON komunikaty o instalacji pakietów
    return json.loads(out[out.index("{"):])[env]


def image_flags(meta: dict) -> list[str]:
    """Image flags without the language standard, exceptions, RTTI and warning settings (the caller adds those)."""
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
    """Function name without return type, arguments and template arguments, common to .su and c++filt."""
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


def common_flags(meta: dict) -> list[str]:
    return [*image_flags(meta), *(f"-D{d}" for d in meta["defines"]), f"-I{CORE}", f"-I{CRYPTO}",
            *(f"-I{i}" for i in meta["includes"]["build"])]


def compile_units(env: str, out: Path) -> tuple[dict, list[Path], str]:
    meta = metadata(env)
    cxx = meta["cxx_path"]
    common = common_flags(meta)
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
    plain = subprocess.run([tool(meta, "c++filt")], input="\n".join(CLONE.sub("", n) for n in names), check=True,
                           capture_output=True, text=True).stdout.splitlines()
    return {m: symbol_name(p) for m, p in zip(names, plain)}


def stack_frames(meta: dict, objects: list[Path]) -> tuple[dict, dict, list[str]]:
    """Stack frame of every function, keyed by (object, name from the object file), because local
    functions with the same name (e.g. {anonymous}::hmac in hkdf.cpp and token.cpp) are in several objects.

    The .su file lists functions in the order the compiler emitted them, with names without types; with
    -ffunction-sections the .text.<name> sections of the object come in the same order. A name mismatch
    in a pair stops the check.
    """
    frames, names, dynamic = {}, {}, []
    for obj in objects:
        su = []
        for line in obj.with_suffix(".su").read_text().splitlines():
            where, size, kind = line.rsplit("\t", 2)
            printable = where.split(":", 3)[3]
            su.append((symbol_name(CLONE.sub("", printable)), int(size)))
            if "dynamic" in kind and "bounded" not in kind:
                dynamic.append(f"{obj.stem}: {printable} ({kind})")
        headers = subprocess.run([tool(meta, "readelf"), "-SW", str(obj)], check=True, capture_output=True,
                                 text=True).stdout
        sections = re.findall(r"\]\s+\.text\.(?:unlikely\.|hot\.|startup\.)?(\S+)\s", headers)
        plain = demangle(meta, sections)
        if [plain[m] for m in sections] != [name for name, _ in su]:
            raise SystemExit(f"{obj.name}: functions in .su and sections differ\n{sections}\n{su}")
        for mangled, (name, size) in zip(sections, su):
            frames[(obj.stem, mangled)] = size
            names[(obj.stem, mangled)] = name
    return frames, names, dynamic


def indirect_calls(meta: dict, objects: list[Path], names: dict) -> list[str]:
    """Functions with a call through a register (ARM: blx rN) that are in neither INDIRECT nor HOOKS."""
    if "arm" not in Path(meta["cxx_path"]).name:
        return []   # Xtensa z -mlongcalls woła wszystko przez rejestr (callx8): sprawdza to obraz ARM
    found = []
    for obj in objects:
        text = subprocess.run([tool(meta, "objdump"), "-d", str(obj)], check=True, capture_output=True,
                              text=True).stdout
        function = None
        for line in text.splitlines():
            m = re.match(r"^[0-9a-f]+ <(\S+)>:$", line)
            if m:
                function = names.get((obj.stem, m.group(1)), m.group(1))
            elif re.search(r"\tblx\s+r\d", line) and function not in INDIRECT and not HOOKS.match(function or ""):
                found.append(f"{obj.stem}: {function}")
    return sorted(set(found))


def call_graph(meta: dict, objects: list[Path], frames: dict, names: dict) -> dict:
    """Calls from relocations: section .text.F (and .literal.F on Xtensa) refers to function G; the target
    is looked up first in the same object (local functions), then in the others. Plus the INDIRECT edges."""
    by_mangled, by_name = {}, {}
    for key in frames:
        by_mangled.setdefault(key[1], []).append(key)
        by_name.setdefault(names[key], []).append(key)
    graph = {}
    for obj in objects:
        text = subprocess.run([tool(meta, "readelf"), "-rW", str(obj)], check=True, capture_output=True,
                              text=True).stdout
        section = None
        for line in text.splitlines():
            m = re.match(r"Relocation section '\.rela?\.(?:text|literal)\.(\S+)'", line)
            if line.startswith("Relocation section"):
                section = (obj.stem, m.group(1)) if m and (obj.stem, m.group(1)) in frames else None
                continue
            fields = line.split()
            if section and len(fields) >= 5 and re.match(r"^[0-9a-f]{8}$", fields[0]):
                target = fields[4]
                own = target.startswith(".")   # sekcja, np. własna pula literałów na Xtensie, nie wywołanie
                target = re.sub(r"^\.(?:text|literal)\.", "", target)
                if own and target == section[1]:
                    continue
                callees = [(obj.stem, target)] if (obj.stem, target) in frames else by_mangled.get(target, [])
                graph.setdefault(section, set()).update(callees)
    for key, name in names.items():
        for callee in INDIRECT.get(name, ()):
            graph.setdefault(key, set()).update(by_name.get(callee, []))
    return graph


def deepest(key: tuple, frames: dict, graph: dict, path: tuple = ()) -> tuple[int, list[tuple]]:
    if key in path:
        raise SystemExit(f"recursion: {' -> '.join(k[1] for k in path + (key,))}")
    best, best_path = 0, []
    for callee in sorted(graph.get(key, ())):
        size, sub = deepest(callee, frames, graph, path + (key,))
        if size > best:
            best, best_path = size, sub
    return frames[key] + best, [key, *best_path]


def static_ram(meta: dict, objects: list[Path]) -> int:
    text = subprocess.run([tool(meta, "size"), "-A", *map(str, objects)], check=True, capture_output=True,
                          text=True).stdout
    total = 0
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and re.match(r"^\.(data|bss|sbss|sdata|dram)", fields[0]):
            total += int(fields[1])
    return total


def transport_ram(meta: dict, out: Path) -> int | None:
    """RAM obiektu rnscore::Transport na płytce (.bss pliku z jednym obiektem), None bez transport.h."""
    if not (CORE / "transport.h").is_file():
        return None
    probe = out / "transport_ram.cpp"
    probe.write_text('#include "transport.h"\nrnscore::Transport wiciTransportRam;\n')
    obj = out / "transport_ram.o"
    subprocess.run([meta["cxx_path"], *common_flags(meta), *CORE_FLAGS, "-c", str(probe), "-o", str(obj)], check=True,
                   capture_output=True, text=True)
    return static_ram(meta, [obj])


def check(env: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        meta, objects, warnings = compile_units(env, Path(tmp))
        frames, names, dynamic = stack_frames(meta, objects)
        graph = call_graph(meta, objects, frames, names)
        arch = "arm" if "arm" in Path(meta["cxx_path"]).name else "xtensa"
        reserve = LIBRARY_RESERVE + INTERRUPT_FRAME[arch]
        entries = {}
        for key in sorted(frames):
            if ENTRY.match(names[key]) and key[0].startswith("core_"):
                size, path = deepest(key, frames, graph)
                hooks = any(HOOKS.match(names[k]) for k in path)
                entries.setdefault(names[key], {"stack": 0})
                if size + reserve > entries[names[key]]["stack"]:   # przeciążenia: najgłębsze
                    entries[names[key]] = {"stack": size + reserve, "path": [f"{names[k]} {frames[k]}" for k in path],
                                           "hooks": hooks}
        return {"env": env, "compiler": subprocess.run([meta["cxx_path"], "--version"], capture_output=True,
                                                       text=True).stdout.splitlines()[0],
                "warnings": warnings.strip(), "dynamic": dynamic, "indirect": indirect_calls(meta, objects, names),
                "static_ram": static_ram(meta, [o for o in objects if o.stem.startswith("core_")]),
                "transport_ram": transport_ram(meta, Path(tmp)),
                "reserve": reserve, "entries": entries}


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
        transport = r["transport_ram"]
        if r["warnings"] or r["dynamic"] or r["indirect"] or r["static_ram"] or over or (transport or 0) > RAM_BUDGET:
            failed = True
        if args.json:
            continue
        print(f"{env}: {r['compiler']}")
        print(f"  static RAM of the core files: {r['static_ram']} B; dynamic stack: {r['dynamic'] or 'none'}; "
              f"unlisted indirect calls: {r['indirect'] or 'none'}")
        print(f"  rnscore::Transport: {'no transport.h' if transport is None else f'{transport} B'} "
              f"(budget {RAM_BUDGET} B{', OVER' if (transport or 0) > RAM_BUDGET else ''})")
        if r["warnings"]:
            print(f"  warnings:\n{r['warnings']}")
        print(f"  stack incl. {r['reserve']} B reserve (library calls {LIBRARY_RESERVE} B, one interrupt frame); "
              "+hooks: rnsnode callbacks add their stack")
        for name, e in sorted(r["entries"].items(), key=lambda item: -item[1]["stack"]):
            print(f"  {e['stack']:6d} B{' +hooks' if e['hooks'] else ''}  {name}: {' > '.join(e['path'])}")
        for name in over:
            print(f"  over {STACK_LIMIT} B: {name}")
    if args.json:
        print(json.dumps(results, indent=1, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
