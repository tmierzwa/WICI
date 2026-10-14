# SPDX-License-Identifier: MIT
"""Builds the station firmware image of bench B (firmware/platformio.ini, env:bench-b) for the simulator's
virtual board: the same source files, preprocessor paths and flags as the board image, with the pinned
Reticulum stack (firmware/tools/stack_deps.py), on the virtual ESP32-S3 + N1 board from hal/. Only the
MCU-specific files are replaced (REPLACED); the S2-LP, FRAM and Sharp chips are emulated on the SPI bus,
so their drivers run unchanged.

Targets:
    python3 software/simulator/build.py            web/wici-station.mjs (Emscripten, wasm inside) + web/build.json
    python3 software/simulator/build.py --native   build/wici-station (host compiler, for quick checks)
    python3 software/simulator/build.py --check    the committed build matches firmware, stack and simulator sources
    python3 software/simulator/build.py --sources  print the compiled files and flags

Emscripten: the pinned version EMSCRIPTEN (emsdk install/activate), em++ on PATH.
"""

from pathlib import Path
import argparse
import concurrent.futures
import configparser
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIRMWARE = ROOT / "firmware"
SRC = FIRMWARE / "src"
INI = FIRMWARE / "platformio.ini"
HAL = HERE / "hal"
WEB = HERE / "web"
BUILD = HERE / "build"
STAMP = WEB / "build.json"
ENV = "bench-b"
EMSCRIPTEN = "3.1.74"

# Pliki MCU obrazu bench-b zastąpione wykonaniami tego samego interfejsu na wirtualnej płytce.
REPLACED = {
    "platform_esp32.cpp": "hal/platform_sim.cpp",
    "sharp_extcomin_esp32.cpp": "hal/sharp_extcomin_sim.cpp",
}
HAL_SOURCES = ["hal/vboard.cpp", "hal/s2lp_chip.cpp", "hal/fram_sharp_chip.cpp", "hal/platform_sim.cpp", "hal/sharp_extcomin_sim.cpp",
               "hal/esp_rom.cpp"]
# Funkcje ROM ESP-IDF, których biblioteka stosu na ESP32 nie kompiluje (bo bierze je z ROM): jej własna kopia
# kompilowana bez ESP32. TLSF w ROM ESP32-S3 i tlsf.c microReticulum to ta sama implementacja (M. Conte).
ROM_SOURCES = {"microReticulum/src/microReticulum/Utilities/tlsf/tlsf.c": ["-UESP32"]}
# Rdzeń Arduino-ESP32 obrazu: makra platformy (ESP32, ARDUINO_ARCH_ESP32) i rdzenia (ARDUINO).
PLATFORM_DEFINES = ["-DARDUINO=10819", "-DARDUINO_ARCH_ESP32", "-DESP32", "-DWICI_SIM"]
# Pre-skrypt stosu (firmware/tools/stack_deps.py) dopisuje te flagi C++ w każdym środowisku.
CXX_FLAGS = ["-std=gnu++17", "-fexceptions", "-frtti"]
# Pliki, które budowa PlatformIO zapisuje w firmware/src (w .gitignore); nie są wejściami obrazu.
GENERATED = {"idf_component.yml"}



def _stack_deps():
    """Definitions of firmware/tools/stack_deps.py (pins, includes, fetch) without its PlatformIO hook."""
    source = (FIRMWARE / "tools" / "stack_deps.py").read_text(encoding="utf-8")
    namespace = {"__name__": "stack_deps", "__file__": str(FIRMWARE / "tools" / "stack_deps.py")}
    exec(compile(source.split("\nif __name__ ==")[0], "stack_deps.py", "exec"), namespace)
    return type("stack_deps", (), {k: staticmethod(v) if callable(v) else v for k, v in namespace.items() if not k.startswith("__")})


stack_deps = _stack_deps()


# ---- platformio.ini ---------------------------------------------------------------------------

def platformio():
    cfg = configparser.ConfigParser(interpolation=None, strict=False, comment_prefixes=(";", "#"), inline_comment_prefixes=(";",))
    cfg.optionxform = str
    cfg.read(INI, encoding="utf-8")
    return cfg


def resolve(cfg, value):
    def sub(match):
        sec, _, key = match.group(1).rpartition(".")
        return resolve(cfg, cfg.get(sec, key))
    return re.sub(r"\$\{([^}]+)\}", sub, value)


def env_get(cfg, env, key):
    """Value from [env:<env>], its `extends` chain and [env], with ${section.key} resolved."""
    section = f"env:{env}"
    while True:
        if cfg.has_option(section, key):
            return resolve(cfg, cfg.get(section, key))
        if not cfg.has_option(section, "extends"):
            break
        section = cfg.get(section, "extends").strip()
    return resolve(cfg, cfg.get("env", key)) if cfg.has_option("env", key) else ""


def flag_list(text):
    # Flaga z cudzysłowem i odstępem poprzedzonym ukośnikiem (USB_PRODUCT) zostaje jednym elementem.
    return [f for f in re.split(r"(?<!\\)\s+", text) if f]


def build_flags(cfg):
    unflags = set(flag_list(env_get(cfg, ENV, "build_unflags")))
    flags = []
    for f in flag_list(env_get(cfg, ENV, "build_flags")):
        if f in unflags or f.startswith("--specs"):
            continue
        if f.startswith("-I") and not os.path.isabs(f[2:]):
            f = "-I" + str(FIRMWARE / f[2:])
        flags.append(f.replace('\\"', '"').replace("\\ ", " "))
    return flags


def portable(flags):
    """Flags as recorded in web/build.json: paths relative to the repository, the same on every machine."""
    return [f.replace(str(ROOT) + "/", "") for f in flags]


def firmware_sources(cfg):
    """Files of src/ selected by build_src_filter of the env, in PlatformIO order (later rules win)."""
    files = sorted(p.relative_to(SRC).as_posix() for p in SRC.rglob("*") if p.suffix in (".c", ".cpp"))
    selected = set()
    for sign, pattern in re.findall(r"([+-])<([^>]*)>", env_get(cfg, ENV, "build_src_filter") or "+<*>"):
        for f in files:
            if pattern == "*" or f == pattern or (pattern.endswith("/") and f.startswith(pattern)):
                (selected.add if sign == "+" else selected.discard)(f)
    return sorted(selected)


def stack_sources(stack):
    """Library sources as PlatformIO compiles them: src/ if present, else the root; library.json srcFilter;
    examples and tests excluded."""
    out = []
    for name, *_ in stack_deps.DEPS:
        lib = stack / name
        meta = json.loads((lib / "library.json").read_text(encoding="utf-8")) if (lib / "library.json").exists() else {}
        if "-<*>" in json.dumps(meta.get("build", {}).get("srcFilter", [])):
            continue
        base = lib / "src" if (lib / "src").is_dir() else lib
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(lib).as_posix()
            if p.suffix in (".c", ".cpp") and not re.search(r"(^|/)(examples?|tests?|extras)/", rel):
                out.append(p)
    return out


# Komputer stanowiska odbiorczego (post/post.cpp, model aplikacji): ten sam stos i moduły oprogramowania
# stacji, których używa (system plików FRAM, SA1, krótki numer), na tej samej wirtualnej płytce.
POST_FIRMWARE = ["config.cpp", "framfs.cpp", "journal.cpp", "jsonlite.cpp", "sa1.cpp", "sha2.cpp", "store.cpp"]
POST_SOURCES = ["post/post.cpp", "hal/vboard.cpp", "hal/s2lp_chip.cpp", "hal/fram_sharp_chip.cpp", "hal/esp_rom.cpp"]


def configuration(target="station"):
    cfg = platformio()
    stack = FIRMWARE / ".pio" / "stack"
    stack_deps.fetch(FIRMWARE)
    fw = firmware_sources(cfg)
    missing = [f for f in REPLACED if f not in fw]
    if missing:
        sys.exit(f"{ENV}: replaced files not in the image any more: {missing}")
    if target == "post":
        units = [SRC / f for f in POST_FIRMWARE] + [HERE / f for f in POST_SOURCES]
    else:
        units = [SRC / f for f in fw if f not in REPLACED] + [HERE / f for f in HAL_SOURCES]
    includes = [f"-I{HAL}", f"-I{SRC}"] + [f"-isystem{stack / i}" for i in stack_deps.INCLUDES]
    flags = PLATFORM_DEFINES + build_flags(cfg)
    return {"firmware": fw, "units": units, "stack": stack_sources(stack), "includes": includes, "flags": flags, "stack_dir": stack}


# ---- kompilacja -------------------------------------------------------------------------------

def compile_all(cc, cxx, conf, out_dir, extra, jobs=os.cpu_count()):
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks = []
    for path in conf["units"] + conf["stack"]:
        dependency = conf["stack_dir"] in path.parents
        cpp = path.suffix == ".cpp"
        flags = conf["flags"] + conf["includes"] + extra + (CXX_FLAGS if cpp else [])
        flags += ["-w", "-Os"] if dependency else ["-Wall", "-O2"]
        if dependency:
            flags += ROM_SOURCES.get(path.relative_to(conf["stack_dir"]).as_posix(), [])
        obj = out_dir / (hashlib.sha1(str(path).encode()).hexdigest()[:12] + "-" + path.stem + ".o")
        tasks.append(([cxx if cpp else cc, *flags, "-c", str(path), "-o", str(obj)], obj, path))

    def run(task):
        cmd, _obj, path = task
        result = subprocess.run(cmd, capture_output=True, text=True)
        return f"{path}:\n{result.stderr}" if result.returncode else None

    with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
        errors = [e for e in pool.map(run, tasks) if e]
    if errors:
        sys.exit("\n".join(errors[:6]))
    return [t[1] for t in tasks]


def build_native():
    cc, cxx = shutil.which("clang") or "cc", shutil.which("clang++") or "c++"
    conf = configuration()
    objs = compile_all(cc, cxx, conf, BUILD / "native", ["-g"])
    cli = BUILD / "native" / "cli.o"
    subprocess.run([cxx, *CXX_FLAGS, "-c", str(HERE / "cli.cpp"), "-o", str(cli)], check=True)
    out = BUILD / "wici-station"
    subprocess.run([cxx, *map(str, objs), str(cli), "-o", str(out)], check=True)
    print(out)


TARGETS = {
    "station": {"output": WEB / "wici-station.mjs", "name": "createStation",
                "exports": ["_sim_input", "_sim_command", "_sim_fram", "_sim_fram_size", "_sim_noinit", "_sim_noinit_size", "_sim_lcd",
                            "_sim_lcd_version", "_sim_run", "_sim_reboot_reason"]},
    "post": {"output": WEB / "wici-post.mjs", "name": "createPost",
             "exports": ["_sim_input", "_sim_command", "_sim_run", "_sim_reboot_reason", "_post_command", "_post_disk", "_post_disk_size"]},
}


def build_wasm():
    emcc, empp = shutil.which("emcc"), shutil.which("em++")
    if not empp:
        sys.exit(f"em++ not found: emsdk install {EMSCRIPTEN} && emsdk activate {EMSCRIPTEN}")
    version = subprocess.run([empp, "--version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    if f" {EMSCRIPTEN} " not in version:
        sys.exit(f"Emscripten {EMSCRIPTEN} required, found: {version}")
    extra = ["-fwasm-exceptions", f"-ffile-prefix-map={ROOT}=."]
    outputs = {}
    for target, spec in TARGETS.items():
        conf = configuration(target)
        objs = compile_all(emcc, empp, conf, BUILD / "wasm" / target, extra)
        link = [empp, *map(str, objs), "-fwasm-exceptions", "-O2", "-sMODULARIZE=1", "-sEXPORT_ES6=1", f"-sEXPORT_NAME={spec['name']}",
                "-sSINGLE_FILE=1", "-sALLOW_MEMORY_GROWTH=1", "-sSTACK_SIZE=1048576", "-sENVIRONMENT=web,node",
                "-sEXPORTED_FUNCTIONS=" + ",".join(spec["exports"]), "-sEXPORTED_RUNTIME_METHODS=HEAPU8,UTF8ToString",
                "-sFILESYSTEM=0", "-o", str(spec["output"])]
        subprocess.run(link, check=True)
        outputs[spec["output"].name] = {"sha256": digest(spec["output"]), "bytes": spec["output"].stat().st_size,
                                        "sources": [str(p.relative_to(ROOT)) for p in conf["units"]]}
        print(f"{spec['output'].relative_to(ROOT)}: {outputs[spec['output'].name]['bytes']} B")
    station = configuration("station")
    stamp = {"env": ENV, "emscripten": version, "firmware": station["firmware"], "replaced": REPLACED, "flags": portable(station["flags"]),
             "stack": [{"name": d[0], "commit": d[2]} for d in stack_deps.DEPS], "outputs": outputs, "inputs": inputs()}
    STAMP.write_text(json.dumps(stamp, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(version)


# ---- kontrola aktualności ---------------------------------------------------------------------

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs():
    """Every input of the build: firmware src/, platformio.ini, stack pins and patches, simulator HAL and post."""
    files = sorted(p for p in SRC.rglob("*") if p.is_file() and p.name not in GENERATED)
    files += [INI, FIRMWARE / "tools" / "stack_deps.py"]
    files += sorted((FIRMWARE / "patches").rglob("*.patch")) + sorted(p for p in HAL.iterdir() if p.is_file())
    files += sorted((HERE / "post").iterdir()) + [Path(__file__)]
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in files}


def check():
    if not STAMP.exists():
        return ["web/build.json missing"]
    stamp = json.loads(STAMP.read_text(encoding="utf-8"))
    problems = []
    for name, info in stamp["outputs"].items():
        if not (WEB / name).exists() or digest(WEB / name) != info["sha256"]:
            problems.append(f"web/{name} does not match build.json")
    current = inputs()
    for name in sorted(set(current) | set(stamp["inputs"])):
        if current.get(name) != stamp["inputs"].get(name):
            problems.append(f"changed since the build: {name}")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--sources", action="store_true")
    args = parser.parse_args()
    if args.check:
        problems = check()
        print("\n".join(problems) or "ok")
        sys.exit(1 if problems else 0)
    if args.sources:
        conf = configuration()
        print("\n".join(str(p.relative_to(ROOT)) for p in conf["units"] + conf["stack"]))
        print(" ".join(conf["flags"]))
        return
    if args.native:
        build_native()
    else:
        build_wasm()


if __name__ == "__main__":
    main()
