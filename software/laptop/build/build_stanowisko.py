# SPDX-License-Identifier: MIT
"""Build the package of the receiving station application (software/laptop/PLAN.md, stage S10b).

    python3.14 software/laptop/build/build_stanowisko.py [--out dist/wici-stanowisko] [--only linux-x86_64 ...]

docs/spec/oprogramowanie.md, „Pakiet USB”: the station package has the build rules of the USB package
(pinned versions, manifest, interpreter and libraries in runtime/, sources and licences, nothing installed
by pip), but no START programs, keys/ or export/. It holds:
  * runtime/: the same interpreters as the USB package (runtimes.json) and the whole pure-Python standard
    library without tests, Tk and IDLE (Reticulum loads modules by name, so a static search like the USB
    package's would be fragile; the station package has no FAT32 size budget);
  * lib/: Reticulum e40191b and LXMF c3ff2d6 fetched with git at the pinned commit and checked by its id
    (like firmware/tools/stack_deps.py), pyserial 3.5 from PyPI with a pinned SHA-256 (stanowisko.json);
  * app/wici/: the application as files, with the reference model next to wzorzec.py;
  * stanowisko.sh, stanowisko.cmd: `python -m wici.stanowisko` with the interpreter of the system;
  * licenses/ and sources/ (archives of the library sources: `git archive` of the commit, pyserial as downloaded).
Downloads are cached in software/laptop/build/cache. --out is replaced only when it is empty or a previous
build of the station package.
"""

import argparse
import json
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

import build_usb as usb

HERE = usb.HERE
LIBS = json.loads((HERE / "stanowisko.json").read_text(encoding="utf-8"))["libraries"]
KIND = "wici-stanowisko"
# Części biblioteki standardowej bez znaczenia dla aplikacji stanowiska: testy, Tk, IDLE i narzędzia instalacji.
SKIP = {"test", "tests", "idle_test", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "__phello__",
        "site-packages"}

SH = """#!/bin/sh
# Aplikacja stanowiska odbiorczego WICI z interpreterem z pakietu: ./stanowisko.sh start --nosnik … --port …
here=$(cd "$(dirname "$0")" && pwd)
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) runtime=linux-x86_64 ;;
  Darwin-arm64) runtime=macos-arm64 ;;
  Darwin-x86_64) runtime=macos-x86_64 ;;
  *) echo "Pakiet stanowiska nie ma środowiska dla $(uname -s) $(uname -m)." >&2; exit 1 ;;
esac
exec "$here/runtime/$runtime/bin/python{minor}" -m wici.stanowisko "$@"
"""
CMD = "@echo off\r\nrem Aplikacja stanowiska odbiorczego WICI z interpreterem z pakietu.\r\n" \
      "\"%~dp0runtime\\windows\\python.exe\" -m wici.stanowisko %*\r\n"


def stdlib_files(stdlib):
    """Every module of the pure-Python standard library except SKIP: name -> path."""
    files = {}
    for path in stdlib.rglob("*.py"):
        rel = path.relative_to(stdlib).with_suffix("")
        if SKIP & set(rel.parts):
            continue
        files[".".join(rel.parts[:-1] if rel.name == "__init__" else rel.parts)] = path
    return files


def checkout(name, pin):
    """Working tree of the pinned commit in the cache: fetched with git and checked by its id; an archive of
    it (`git archive`) for sources/. Returns the archive path."""
    dest = usb.CACHE / f"{name}-{pin['commit']}"

    def git(*args):
        return subprocess.run(["git", *args], cwd=dest, check=True, capture_output=True, text=True).stdout.strip()
    if not (dest / ".git").is_dir() or git("rev-parse", "HEAD") != pin["commit"]:
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True)
        usb.log(f"pobieranie {pin['repository']} {pin['commit']}")
        git("init", "-q")
        git("fetch", "-q", "--depth", "1", pin["repository"], pin["commit"])
        git("checkout", "-q", "FETCH_HEAD")
    if git("rev-parse", "HEAD") != pin["commit"]:
        sys.exit(f"{name}: pobrany commit nie jest przypiętym {pin['commit']}")
    archive = usb.CACHE / f"{name}-{pin['commit']}.tar.gz"
    if not archive.is_file():
        top = Path(pin["repository"]).stem
        git("archive", "--format=tar.gz", f"--prefix={top}-{pin['commit']}/", "-o", str(archive), "HEAD")
    return archive


def library(name, pin, out):
    """The package directory of a pinned source archive into lib/, its licence and the archive into sources/."""
    archive = checkout(name, pin) if "commit" in pin else usb.fetch(pin, name)
    with tarfile.open(archive) as tar:
        top = tar.getmembers()[0].name.split("/")[0]
        prefix = f"{top}/{pin['package']}/"
        for m in tar:
            if not m.isfile():
                continue
            if m.name.startswith(prefix) and "__pycache__" not in m.name and not m.name.endswith(".pyc"):
                usb.write(out / "lib" / pin["package"] / m.name[len(prefix):], tar.extractfile(m).read())
            elif m.name == f"{top}/{pin['license']}":
                usb.write(out / "licenses" / f"{name}.txt", tar.extractfile(m).read())
    if not (out / "lib" / pin["package"] / "__init__.py").is_file() or not (out / "licenses" / f"{name}.txt").is_file():
        sys.exit(f"{name}: w archiwum nie ma pakietu {pin['package']} albo licencji")
    shutil.copyfile(archive, out / "sources" / archive.name)


def application(out):
    """wici/ as files (the station package also runs the laptop modules it imports), and the reference model."""
    for p in sorted((usb.LAPTOP / "wici").rglob("*")):
        rel = p.relative_to(usb.LAPTOP).as_posix()
        if p.is_file() and not any(part.startswith(".") or part == "__pycache__" for part in Path(rel).parts) \
                and not rel.endswith((".pyc", "~", ".swp", ".bak", ".orig", ".rej", ".tmp")):
            usb.write(out / "app" / rel, p.read_bytes())
    for name in ("reference.py", "schema.sql"):
        shutil.copyfile(usb.ROOT / "software" / "reference" / name, out / "app" / "wici" / "stanowisko" / name)


def runtimes(out, names, paths):
    """Interpreters as in the USB package, with ._pth files that add app/ and lib/."""
    for n in names:
        if usb.PINS["runtimes"][n]["kind"] == "embeddable":
            unpack_windows(paths[n], out)
        else:
            usb.unpack_pbs(n, paths[n], out)
            pth = out / "runtime" / n / "bin" / f"python{usb.MINOR}._pth"
            pth.write_text(pth.read_text(encoding="utf-8") + "../../../app\n../../../lib\n", encoding="utf-8")


def unpack_windows(archive, out):
    """Everything of the embeddable archive except its own standard library: the station package does not
    count megabytes, and a missing .pyd would show only on the station computer."""
    dest = out / "runtime" / "windows"
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if info.filename == "LICENSE.txt":
                usb.write(out / "licenses" / "python-windows.txt", z.read(info))
            elif not info.filename.endswith(("._pth", f"python{usb.TAG}.zip")) and not info.is_dir():
                usb.write(dest / info.filename, z.read(info))
    usb.write(dest / f"python{usb.TAG}._pth", f"..\\{usb.STDLIB_ZIP}\r\n.\r\n..\\..\\app\r\n..\\..\\lib\r\n".encode())


def self_check(out, names):
    """The interpreter of this system from the package imports the stack with Reticulum's own cryptography."""
    host = {"linux": "linux-x86_64", "darwin": "macos-arm64" if platform.machine() == "arm64" else "macos-x86_64",
            "win32": "windows-amd64"}.get(sys.platform)
    if host not in names:
        usb.log("sprawdzenie pominięte: pakiet nie ma środowiska tego systemu")
        return
    python = out / "runtime" / ("windows/python.exe" if host == "windows-amd64" else f"{host}/bin/python{usb.MINOR}")
    code = ("import RNS, LXMF, serial, wici.stanowisko.__main__, wici.stanowisko.zamkniecie\n"
            "from RNS.Cryptography import Provider\n"
            "assert Provider.backend() == 'internal', Provider.backend()\n"
            "print('stos', RNS.__version__ if hasattr(RNS, '__version__') else '', serial.VERSION)\n")
    subprocess.run([str(python), "-c", code], check=True)


def build(out, names, archives=None):
    """Build the package into `out`. `archives` maps runtime names to local files (tests, offline builds)."""
    archives = archives or {}
    if out.exists() and any(out.iterdir()):
        previous = out / "build-manifest.json"
        if not previous.is_file() or json.loads(previous.read_text(encoding="utf-8")).get("kind") != KIND:
            sys.exit(f"{out}: to nie jest poprzednia budowa pakietu stanowiska; podaj pusty albo nowy katalog --out")
        shutil.rmtree(out)
    for d in ("runtime", "lib", "app", "licenses", "sources"):
        (out / d).mkdir(parents=True, exist_ok=True)
    paths = {n: Path(archives[n]) if n in archives else usb.fetch(usb.PINS["runtimes"][n], n) for n in names}
    source = next((n for n in ("linux-x86_64", "macos-arm64", "macos-x86_64") if n in paths), "linux-x86_64")
    stdlib_source = paths.get(source) or usb.fetch(usb.PINS["runtimes"][source], source)
    with tempfile.TemporaryDirectory() as tmp:
        stdlib = usb.stdlib_from_pbs(stdlib_source, tmp)
        modules = usb.build_stdlib(stdlib, out / "runtime" / usb.STDLIB_ZIP, stdlib_files(stdlib))
    runtimes(out, names, paths)
    (out / "runtime" / "VERSION").write_text(usb.VERSION + "\n", encoding="utf-8")
    for name, pin in LIBS.items():
        library(name, pin, out)
    application(out)
    if any(not n.startswith("windows") for n in names):
        usb.write(out / "stanowisko.sh", SH.format(minor=usb.MINOR).encode(), executable=True)
    if "windows-amd64" in names:
        usb.write(out / "stanowisko.cmd", CMD.encode())
    usb.third_party_licenses(out, names)
    shutil.copyfile(usb.ROOT / "LICENSES" / "MIT.txt", out / "licenses" / "WICI-MIT.txt")
    commit = usb.git_describe()
    (out / "sources" / "README.txt").write_text(
        "Kod aplikacji stanowiska WICI jest w app/wici jako pliki źródłowe; repozytorium projektu, commit "
        f"{commit or 'nieznany'}: software/laptop i software/reference.\n"
        "Reticulum, LXMF i pyserial: archiwa źródeł w tym katalogu; repozytoria i commity (Reticulum, LXMF) oraz adres i suma SHA-256 (pyserial) w build-manifest.json.\n"
        f"Środowiska Pythona {usb.VERSION}: python.org (Windows) i python-build-standalone (macOS, Linux).\n",
        encoding="utf-8")
    doc = usb.manifest(out, names, modules, commit)
    doc.update(kind=KIND, libraries=LIBS)
    (out / "build-manifest.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for group, size in sorted(doc["groups"].items()):
        usb.log(f"{size / 1e6:8.2f} MB  {group}")
    usb.log(f"{doc['total_bytes'] / 1e6:8.2f} MB  razem, {len(doc['files'])} plików, {doc['stdlib_modules']} modułów biblioteki")
    self_check(out, names)
    return doc


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(usb.ROOT / "dist" / "wici-stanowisko"))
    parser.add_argument("--only", nargs="*", choices=sorted(usb.PINS["runtimes"]), help="tylko te środowiska")
    usb.plain_console()
    args = parser.parse_args()
    sys.path.insert(0, str(usb.LAPTOP))
    build(Path(args.out), args.only or sorted(usb.PINS["runtimes"]))


if __name__ == "__main__":
    main()
