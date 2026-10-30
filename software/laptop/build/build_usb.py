# SPDX-License-Identifier: MIT
"""Build the USB tree of the laptop application for Windows, macOS and Linux (software/laptop/PLAN.md).

    python3.14 software/laptop/build/build_usb.py [--out dist/wici-usb] [--only linux-x86_64 ...]
                                                  [--windows-launcher START-WINDOWS.exe]

Every runtime comes from runtimes.json and is checked against its pinned SHA-256 before use. The
tree is small because:
  * one standard library for every system: only the modules the application imports (ModuleFinder),
    compiled once to bytecode without docstrings and asserts (-OO), in runtime/python314.zip;
  * of each runtime only the interpreter (python-build-standalone: statically linked, without
    lib/libpython*; Windows: python.exe with python314.dll) and the extension modules the application
    needs that are not built in are kept: no Tcl/Tk, tests, headers, pip, TLS or idle;
  * one START-MAC.app for Apple Silicon and Intel; the application itself is one zip of sources.
Each runtime finds the shared standard library runtime/python314.zip through a ._pth file next to the
interpreter, which also switches it to isolated mode (no environment variables, no user site-packages).

The bytecode is compiled by the Python running this script, so it must be the pinned minor version.
Downloads are cached in software/laptop/build/cache (not in Git). --out is replaced only when it is
empty or a previous build (build-manifest.json, no keys/ or kopia/ of a kit).
"""

import argparse
import hashlib
import json
import modulefinder
import os
import py_compile
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
LAPTOP = HERE.parent
ROOT = LAPTOP.parents[1]
CACHE = HERE / "cache"
PINS = json.loads((HERE / "runtimes.json").read_text(encoding="utf-8"))
VERSION = PINS["python"]
MINOR = ".".join(VERSION.split(".")[:2])          # 3.14
TAG = MINOR.replace(".", "")                       # 314
# Wydanie python-build-standalone ze ścieżki adresów (…/releases/download/20261009/…), jedno dla wszystkich.
PBS_RELEASE = ",".join(sorted({r["url"].split("/download/")[1].split("/")[0]
                               for r in PINS["runtimes"].values() if r["kind"] == "pbs"}))
STDLIB_ZIP = f"python{TAG}.zip"
BUDGET = 90_000_000                                 # cała pamięć USB poza obrazem Linuksa; zmierzone 83,6 MB; zob. PLAN.md
ZIP_TIME = (1980, 1, 1, 0, 0, 0)                   # powtarzalne archiwa: stałe znaczniki czasu

# Pakiety biblioteki dołączane w całości: kodeki ładowane po nazwie oraz pakiety, których aplikacja używa
# wprost; ich moduły bywają ładowane z kodu w C (np. ctypes._layout w 3.14), czego ModuleFinder nie widzi.
WHOLE_PACKAGES = ["encodings", "ctypes", "importlib", "json", "sqlite3", "http", "email", "urllib", "html",
                  "re", "collections"]
# Moduły ładowane z C albo po nazwie, a także potrzebne tylko na innym systemie niż ten, na którym trwa budowa.
EXTRA_MODULES = ["ntpath", "nturl2path", "runpy", "pkgutil", "_strptime", "_pydatetime", "_colorize",
                 "stringprep"]   # stringprep: kodek idna (socket.getfqdn w http.server)
# Duże części biblioteki, których aplikacja nie używa, choć importy innych modułów je wskazują
# (zwykle w try/except albo w rzadko używanych funkcjach). Kompletność reszty sprawdza --selftest.
EXCLUDE = ["tkinter", "turtle", "turtledemo", "idlelib", "test", "unittest", "pydoc", "pydoc_data", "doctest",
           "lib2to3", "ensurepip", "venv", "distutils", "setuptools", "pip", "curses", "dbm", "xmlrpc",
           "multiprocessing", "asyncio", "concurrent", "tomllib", "zoneinfo", "lzma", "bz2", "ssl", "ftplib",
           "imaplib", "poplib", "smtplib", "mailbox", "pdb", "bdb", "cProfile", "profile", "pstats", "trace",
           "tracemalloc", "_pyrepl", "readline", "rlcompleter", "ctypes.macholib", "__phello__", "__hello__"]

# Moduły binarne zachowywane obok interpretera: na Windows pliki .pyd z archiwum embeddable (reszta jest
# w python314.dll). python-build-standalone ma je wbudowane w interpreter (w lib-dynload wydania 20261009
# są tylko _dbm i _tkinter); gdyby nowe wydanie wydzieliło któryś, trafi do lib-dynload, a brak innego
# wykaże --selftest w CI.
EXTENSIONS = {"_ctypes", "_sqlite3", "select", "_socket", "unicodedata", "_queue", "_uuid"}
WINDOWS_FILES = {"python.exe", "pythonw.exe", f"python{TAG}.dll", "python3.dll", "vcruntime140.dll", "vcruntime140_1.dll",
                 "libffi-8.dll", "sqlite3.dll"}


def log(*args):
    print(*args, flush=True)


def plain_console():
    """Polish messages must not crash a cp1252 console or pipe (Windows CI, older terminals)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")


# ---- pobieranie ------------------------------------------------------------------------------

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(pin, name):
    """Cached file of a pin {"url", "sha256"}: downloaded when missing, used only with the pinned SHA-256."""
    target = CACHE / PurePosixPath(pin["url"]).name.replace("%2B", "+")
    if not target.exists() or sha256(target) != pin["sha256"]:
        CACHE.mkdir(parents=True, exist_ok=True)
        log(f"pobieranie {pin['url']}")
        tmp = target.with_name(target.name + ".part")
        with urllib.request.urlopen(pin["url"], timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        if sha256(tmp) != pin["sha256"]:
            tmp.unlink()
            sys.exit(f"{name}: suma SHA-256 niezgodna z przypiętą; plik odrzucony")
        tmp.replace(target)
    return target


# ---- biblioteka standardowa ------------------------------------------------------------------

def pbs_members(archive):
    """Files of a python-build-standalone archive in archive order, read once:
    (path under python/, TarInfo, function returning the contents; called only for kept files)."""
    with tarfile.open(archive) as tar:
        for m in tar:
            if m.isfile() and m.name.startswith("python/"):
                yield m.name[len("python/"):], m, lambda m=m: tar.extractfile(m).read()


def needed_modules(stdlib):
    """Standard-library modules imported by the application, found statically from its sources."""
    finder = modulefinder.ModuleFinder(path=[str(LAPTOP), str(stdlib)], excludes=EXCLUDE)
    for name in ["wici"] + sorted(f"wici.{p.stem}" for p in (LAPTOP / "wici").glob("*.py") if p.stem != "__init__"):
        finder.import_hook(name)
    for name in EXTRA_MODULES:
        finder.import_hook(name)
    files = {}
    for name, module in finder.modules.items():
        if module.__file__ and name.split(".")[0] != "wici" and module.__file__.endswith(".py"):
            files[name] = Path(module.__file__)
    for package in WHOLE_PACKAGES:
        for path in (stdlib / package).rglob("*.py"):
            if any(part in ("test", "tests", "macholib", "idle_test") for part in path.relative_to(stdlib).parts):
                continue
            rel = path.relative_to(stdlib).with_suffix("")
            files[".".join(rel.parts[:-1] if rel.name == "__init__" else rel.parts)] = path
    return files


def build_stdlib(stdlib, out_zip):
    """Compile the needed modules with -OO and store them as one zip shared by every system."""
    if sys.version_info[:2] != tuple(map(int, MINOR.split("."))):
        sys.exit(f"bytecode must be compiled by Python {MINOR}; this is {sys.version.split()[0]}")
    files = needed_modules(stdlib)
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(out_zip, "w") as z:
        for name in sorted(files):
            src = files[name]
            rel = src.relative_to(stdlib).with_suffix(".pyc")
            pyc = Path(tmp) / rel
            pyc.parent.mkdir(parents=True, exist_ok=True)
            py_compile.compile(str(src), cfile=str(pyc), dfile=str(rel.with_suffix(".py")), doraise=True, optimize=2,
                               invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
            z.writestr(zip_entry(rel.as_posix()), pyc.read_bytes())
    return sorted(files)


def zip_entry(name):
    """Entry of a reproducible zip: fixed time and system, deflate level 9 (a ZipInfo given to writestr
    does not take the compresslevel of the ZipFile)."""
    info = zipfile.ZipInfo(name, ZIP_TIME)
    info.compress_type, info.compress_level = zipfile.ZIP_DEFLATED, 9
    info.create_system, info.external_attr = 3, 0o100644 << 16
    return info


# ---- środowiska ------------------------------------------------------------------------------

def write(path, data, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def extension_name(filename):
    return filename.split(".")[0]


def unpack_pbs(name, archive, out):
    """Interpreter and the extension modules of EXTENSIONS it does not have built in.

    PBS links the interpreter statically (needed modules included), so lib/libpython* is a second copy
    of the same code: 33 MB on Linux, 19 MB per Mac. Leaving it out is checked by --selftest in CI."""
    stdlib_prefix = f"lib/python{MINOR}/"
    dest = out / "runtime" / name
    interpreter = dynload = False
    for rel, member, read in pbs_members(archive):
        if rel == f"bin/python{MINOR}":
            write(dest / rel, read(), executable=bool(member.mode & 0o111))
            interpreter = True
        elif rel.startswith(stdlib_prefix + "lib-dynload/"):
            file = rel.rsplit("/", 1)[1]
            if extension_name(file) in EXTENSIONS:
                write(dest / "lib-dynload" / file, read())
                dynload = True
        elif rel == stdlib_prefix + "LICENSE.txt":
            write(out / "licenses" / f"python-{name}.txt", read())
    if not interpreter:
        sys.exit(f"{name}: brak bin/python{MINOR} w archiwum")
    # ._pth obok interpretera: wspólna biblioteka (i moduły binarne, jeśli są); tryb izolowany.
    pth = f"../../{STDLIB_ZIP}\n" + ("../lib-dynload\n" if dynload else "")
    write(dest / "bin" / f"python{MINOR}._pth", pth.encode())


def unpack_embeddable(archive, out):
    dest = out / "runtime" / "windows"
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            file = info.filename
            if file == "LICENSE.txt":
                write(out / "licenses" / "python-windows.txt", z.read(info))
            elif file in WINDOWS_FILES or (file.endswith(".pyd") and extension_name(file) in EXTENSIONS):
                write(dest / file, z.read(info))
    for need in ("python.exe", "pythonw.exe", f"python{TAG}.dll"):
        if not (dest / need).is_file():
            sys.exit(f"windows: brak {need} w archiwum")
    write(dest / f"python{TAG}._pth", f"..\\{STDLIB_ZIP}\r\n.\r\n".encode())


def stdlib_from_pbs(archive, tmp):
    """Extract only the pure-Python standard library of a PBS archive into tmp."""
    prefix = f"lib/python{MINOR}/"
    for rel, _, read in pbs_members(archive):
        if rel.startswith(prefix) and rel.endswith(".py") and "/site-packages/" not in rel:
            write(Path(tmp) / rel[len(prefix):], read())
    return Path(tmp)


# ---- aplikacja i programy START --------------------------------------------------------------

def app_file(rel):
    """Whether a file of wici/ goes into wici.pyz: no caches, dotfiles or editor and patch leftovers, and not
    the receiving station application (wici/stanowisko: Reticulum and LXMF, its own package, PLAN.md S10)."""
    parts = PurePosixPath(rel).parts
    name = parts[-1]
    return not (any(p.startswith(".") or p == "__pycache__" for p in parts) or name.startswith("#")
                or parts[:2] == ("wici", "stanowisko")
                or name.endswith(("~", ".pyc", ".swp", ".bak", ".orig", ".rej", ".tmp")))


def build_app(out_pyz):
    """The application as one zip of sources: readable, independent of the bytecode version."""
    files = sorted(p for p in (LAPTOP / "wici").rglob("*")
                   if p.is_file() and app_file(p.relative_to(LAPTOP).as_posix()))
    with zipfile.ZipFile(out_pyz, "w") as z:
        z.writestr(zip_entry("__main__.py"), "import sys\nfrom wici.__main__ import main\nsys.exit(main())\n")
        for p in files:
            z.writestr(zip_entry(p.relative_to(LAPTOP).as_posix()), p.read_bytes())


INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>START</string>
  <key>CFBundleIdentifier</key><string>pl.wici.start</string>
  <key>CFBundleName</key><string>WICI</string>
  <key>CFBundleDisplayName</key><string>WICI – przygotowanie stacji</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>{version}</string>
  <key>CFBundleVersion</key><string>{version}</string>
  <key>LSMinimumSystemVersion</key><string>10.15</string>
  <key>LSUIElement</key><true/>
</dict>
</plist>
"""

DESKTOP = """[Desktop Entry]
Type=Application
Name=WICI – przygotowanie stacji
Comment=Panel stacji WICI w przeglądarce
Exec=sh -c 'sh "$(dirname "$1")/START-LINUX.sh" || { echo; echo "Enter zamyka to okno."; read x; }' sh %k
Terminal=true
Categories=Utility;
"""


def windows_launcher(path):
    if path:
        return Path(path).read_bytes()
    for cc in ("x86_64-w64-mingw32-gcc", "gcc" if sys.platform == "win32" else ""):
        if cc and shutil.which(cc):
            with tempfile.TemporaryDirectory() as tmp:
                exe = Path(tmp) / "START-WINDOWS.exe"
                subprocess.run([cc, "-Os", "-s", "-municode", "-mwindows", "-o", str(exe),
                                str(HERE / "launcher" / "start-windows.c")], check=True)
                return exe.read_bytes()
    return None


def launchers(out, names):
    from wici import VERSION as APP_VERSION
    if any(n.startswith("macos") for n in names):
        app = out / "START-MAC.app" / "Contents"
        write(app / "Info.plist", INFO_PLIST.format(version=APP_VERSION).encode())
        write(app / "MacOS" / "START", (HERE / "launcher" / "start-mac.sh").read_bytes(), executable=True)
    if "linux-x86_64" in names:
        write(out / "START-LINUX.sh", (HERE / "launcher" / "start-linux.sh").read_bytes(), executable=True)
        write(out / "START-LINUX.desktop", DESKTOP.encode(), executable=True)


# ---- manifest --------------------------------------------------------------------------------

def git_describe():
    """Commit of the build, with the tag when there is one and -dirty for uncommitted changes; "" without Git."""
    try:
        return subprocess.run(["git", "describe", "--always", "--dirty", "--abbrev=40"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def manifest(out, names, modules, commit):
    from wici import VERSION as APP_VERSION
    files, groups = {}, {}
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name != "build-manifest.json":
            rel = p.relative_to(out).as_posix()
            size = p.stat().st_size
            files[rel] = {"sha256": sha256(p), "size": size}
            parts = rel.split("/")
            group = "/".join(parts[:2]) if parts[0] == "runtime" and len(parts) > 2 else parts[0]
            groups[group] = groups.get(group, 0) + size
    doc = {"project": "WICI", "app": APP_VERSION, "python": VERSION, "commit": commit,
           "build_python": sys.version, "runtimes": {n: PINS["runtimes"][n] for n in names},
           "stdlib_modules": len(modules),
           "total_bytes": sum(f["size"] for f in files.values()), "groups": groups, "files": files}
    (out / "build-manifest.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def third_party_licenses(out, names):
    """Licences the runtime files in LICENSE.txt do not cover (licencje/zrodla.json).

    The python-build-standalone interpreter has OpenSSL, libffi, SQLite, expat and other libraries
    linked in statically; CPython itself incorporates code under other licences (Doc/license.rst)."""
    src = HERE / "licencje"
    pins = json.loads((src / "zrodla.json").read_text(encoding="utf-8"))
    if (pins["python"], pins["pbs_release"]) != (VERSION, PBS_RELEASE):
        sys.exit("licencje/zrodla.json opisuje inną wersję środowisk niż runtimes.json")
    shutil.copyfile(src / pins["cpython"]["file"], out / "licenses" / "python-kod-wbudowany.txt")
    if any(PINS["runtimes"][n]["kind"] == "pbs" for n in names):
        parts = [f"Biblioteki wkompilowane w interpreter Pythona {VERSION} z python-build-standalone {PBS_RELEASE}\n"
                 "(runtime/macos-*, runtime/linux-*). Źródło: licencje/zrodla.json w repozytorium WICI.\n"]
        for name in pins["pbs"]["files"] + [pins["zstd"]["file"]]:
            parts.append(f"\n{'=' * 72}\n{name}\n{'=' * 72}\n\n" + (src / name).read_text(encoding="utf-8"))
        (out / "licenses" / "python-biblioteki.txt").write_text("".join(parts), encoding="utf-8")


def build(out, names, launcher_exe=None, archives=None):
    """Build the tree into `out`. `archives` maps runtime names to local files (tests, offline builds)."""
    archives = archives or {}
    if out.exists() and any(out.iterdir()):
        # Usuwa tylko poprzednią budowę; pamięć zestawu z kontami albo kopią bazy i każdy inny katalog zostają.
        if not (out / "build-manifest.json").is_file() or any((out / d).exists() for d in ("keys", "kopia", "export")):
            sys.exit(f"{out}: to nie jest poprzednia budowa (brak build-manifest.json albo są keys/, kopia/, export/); "
                     "podaj pusty albo nowy katalog --out")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    paths = {n: Path(archives[n]) if n in archives else fetch(PINS["runtimes"][n], n) for n in names}
    # Czysty Python biblioteki jest ten sam na każdym systemie; źródłem jest archiwum Linuksa albo macOS.
    source = next((n for n in ("linux-x86_64", "macos-arm64", "macos-x86_64") if n in paths), "linux-x86_64")
    stdlib_source = paths.get(source) or Path(archives.get(source) or fetch(PINS["runtimes"][source], source))
    with tempfile.TemporaryDirectory() as tmp:
        modules = build_stdlib(stdlib_from_pbs(stdlib_source, tmp), out / "runtime" / STDLIB_ZIP)
    for n in names:
        if PINS["runtimes"][n]["kind"] == "embeddable":
            unpack_embeddable(paths[n], out)
        else:
            unpack_pbs(n, paths[n], out)
    commit = git_describe()
    (out / "runtime" / "VERSION").write_text(VERSION + "\n", encoding="utf-8")
    (out / "app").mkdir()
    build_app(out / "app" / "wici.pyz")
    launchers(out, names)
    if "windows-amd64" in names:
        exe = windows_launcher(launcher_exe)
        if exe is None:
            sys.exit("brak kompilatora MinGW-w64 dla START-WINDOWS.exe; podaj --windows-launcher")
        write(out / "START-WINDOWS.exe", exe)
    shutil.copyfile(HERE / "usb" / "INSTRUKCJA.html", out / "INSTRUKCJA.html")
    third_party_licenses(out, names)
    shutil.copyfile(ROOT / "LICENSES" / "MIT.txt", out / "licenses" / "WICI-MIT.txt")
    shutil.copyfile(ROOT / "LICENSES" / "CC-BY-SA-4.0.txt", out / "licenses" / "slowa-CC-BY-SA-4.0.txt")
    sources = json.loads((HERE / "slowa" / "zrodla.json").read_text(encoding="utf-8"))
    (out / "licenses" / "slowa.txt").write_text(
        "app/wici.pyz/wici/slowa.txt (lista słów do haseł z kopert) jest na licencji CC BY-SA 4.0.\nŹródła:\n"
        + "".join(dict.fromkeys(f"  {s['attribution']} ({s['license']})\n" for s in sources.values()))
        + "Zmiany: wybór form podstawowych bez polskich liter, wykluczenia, ranking według częstości;\n"
          "skrypt budowy w repozytorium WICI: software/laptop/build/slowa/.\n", encoding="utf-8")
    (out / "sources").mkdir()
    (out / "sources" / "README.txt").write_text(
        "Kod aplikacji WICI jest w app/wici.pyz jako czytelne pliki źródłowe (archiwum ZIP).\n"
        f"Repozytorium projektu, commit {commit or 'nieznany'}: software/laptop.\n"
        f"Środowiska Pythona {VERSION}: python.org (Windows) i python-build-standalone (macOS, Linux);\n"
        "adresy i sumy SHA-256 archiwów są w build-manifest.json.\n", encoding="utf-8")
    doc = manifest(out, names, modules, commit)
    for group, size in sorted(doc["groups"].items()):
        log(f"{size / 1e6:8.2f} MB  {group}")
    log(f"{doc['total_bytes'] / 1e6:8.2f} MB  razem, {len(doc['files'])} plików, {doc['stdlib_modules']} modułów biblioteki")
    if doc["total_bytes"] > BUDGET:
        sys.exit(f"przekroczony budżet {BUDGET / 1e6:.0f} MB")
    return doc


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "dist" / "wici-usb"))
    parser.add_argument("--only", nargs="*", choices=sorted(PINS["runtimes"]), help="tylko te środowiska")
    parser.add_argument("--windows-launcher", help="gotowy START-WINDOWS.exe zamiast kompilacji")
    plain_console()
    args = parser.parse_args()
    sys.path.insert(0, str(LAPTOP))
    build(Path(args.out), args.only or sorted(PINS["runtimes"]), args.windows_launcher)


if __name__ == "__main__":
    main()
