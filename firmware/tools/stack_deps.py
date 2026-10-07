# SPDX-License-Identifier: MIT
"""Pinned sources of the Reticulum stack (microReticulum and its libraries) for the station image.

The repository does not carry code of these dependencies. Before each build PlatformIO runs this
file (extra_scripts = pre:tools/stack_deps.py): every library is fetched at the pinned commit into
firmware/.pio/stack/<name>, the commit is checked, the WICI patches from firmware/patches/<name>/
are applied with git apply, and the result is used through lib_extra_dirs. PlatformIO does not
resolve library.json dependencies from lib_extra_dirs, so nothing unpinned enters the image.
A stamp file holds the commit and the patch hashes; a changed pin or patch fetches again.

Standalone: python3 tools/stack_deps.py [--list] (fetches into firmware/.pio/stack, or prints the pins).
"""

from pathlib import Path
import hashlib
import shutil
import subprocess
import sys

# Katalogi nagłówków bibliotek (względem .pio/stack): na komputerze dołączane też jako -isystem, żeby
# ostrzeżenia clang z nagłówków zależności nie trafiały do kompilacji kodu WICI (arm-none-eabi-gcc
# traktuje nagłówki z -isystem jak nagłówki C, więc obraz płytki ich nie używa).
INCLUDES = ["microReticulum/src", "microStore/include", "Crypto", "MsgPack", "ArxContainer", "ArxTypeTraits",
            "DebugLog", "ArduinoJson/src"]

# name, repository, commit, license (SPDX), version or note
DEPS = [
    ("microReticulum", "https://github.com/attermann/microReticulum.git",
     "40fa628809d57140180c1c833559ab96fec992c1", "Apache-2.0", "0.5.0"),
    ("microStore", "https://github.com/attermann/microStore.git",
     "0f28567fe00ab8ab14624a34c2e9e0a000a44c46", "Apache-2.0", "0.1.7"),
    ("Crypto", "https://github.com/attermann/Crypto.git",
     "984dc891330986c302a86c4e312d4f5abcc28359", "MIT", "0.4.0, rweather/arduinolibs"),
    ("MsgPack", "https://github.com/hideakitai/MsgPack.git",
     "1f552c31b940d6e9063ee17a4b3fa10c47b27169", "MIT", "0.4.2"),
    ("ArxContainer", "https://github.com/hideakitai/ArxContainer.git",
     "d6affcd0bc83219b863c20abf7c269214db8db2a", "MIT", "0.7.0"),
    ("ArxTypeTraits", "https://github.com/hideakitai/ArxTypeTraits.git",
     "702de9cc59c7e047cdc169ae3547718b289d2c02", "MIT", "0.3.2"),
    ("DebugLog", "https://github.com/hideakitai/DebugLog.git",
     "b581f7dde6c276c5df684e2328f406d9754d2f46", "MIT", "0.8.4"),
    ("ArduinoJson", "https://github.com/bblanchon/ArduinoJson.git",
     "733bc4ee82630c88c0a619a883cd3a206efae977", "MIT", "7.4.2"),
]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def patches(firmware: Path, name: str) -> list[Path]:
    folder = firmware / "patches" / name
    return sorted(folder.glob("*.patch")) if folder.is_dir() else []


def stamp_text(firmware: Path, name: str, commit: str) -> str:
    lines = [commit] + [f"{p.name} {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in patches(firmware, name)]
    return "\n".join(lines) + "\n"


def fetch(firmware: Path) -> Path:
    """Fetch every pinned library into firmware/.pio/stack and apply the patches; return that folder."""
    root = firmware / ".pio" / "stack"
    root.mkdir(parents=True, exist_ok=True)
    for name, url, commit, _license, _version in DEPS:
        dest = root / name
        stamp = dest / ".wici-stamp"
        wanted = stamp_text(firmware, name, commit)
        if stamp.is_file() and stamp.read_text() == wanted:
            continue
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir()
        git(dest, "init", "-q")
        git(dest, "fetch", "-q", "--depth", "1", url, commit)
        git(dest, "checkout", "-q", "FETCH_HEAD")
        if git(dest, "rev-parse", "HEAD") != commit:
            raise RuntimeError(f"{name}: fetched commit differs from the pin {commit}")
        for patch in patches(firmware, name):
            git(dest, "apply", "--whitespace=nowarn", str(patch))
        stamp.write_text(wanted)
        print(f"stack_deps: {name} {commit[:7]} with {len(patches(firmware, name))} patch(es)")
    return root


if __name__ == "__main__" and "SCons" not in sys.modules:
    here = Path(__file__).resolve().parents[1]
    if "--list" in sys.argv:
        for name, url, commit, license_id, version in DEPS:
            print(f"{name}\t{version}\t{license_id}\t{url}\t{commit}")
    else:
        print(fetch(here))
else:  # PlatformIO pre-script
    Import("env")  # noqa: F821
    stack = fetch(Path(env["PROJECT_DIR"]))  # noqa: F821
    if env.get("PIOPLATFORM") == "native":  # noqa: F821
        for folder in INCLUDES:
            env.Append(CCFLAGS=["-isystem", str(stack / folder)])  # noqa: F821
    # microReticulum wymaga C++17, wyjątków i RTTI; tylko dla C++, bo dla C GCC je odrzuca z ostrzeżeniem.
    env.Append(CXXFLAGS=["-std=gnu++17", "-fexceptions", "-frtti"])  # noqa: F821
    # Ostrzeżenia kodu zależności (nieużywane zmienne, przestarzałe API ArduinoJson w MsgPack)
    # nie są ostrzeżeniami WICI: pliki z .pio/stack kompilują się z -w, kod WICI z -Wall.
    # Rdzeń Adafruit kompiluje z -Ofast; stos z -Os, bo rozwinięte pętle Curve25519 i kontenery
    # zajmowały około 250 KB flash więcej (README, "Stos Reticulum").
    def quiet(builder, node):
        flags = ["-w"] if env.get("PIOPLATFORM") == "native" else ["-w", "-Os"]  # noqa: F821
        return builder.Object(node, CCFLAGS=builder["CCFLAGS"] + flags)
    env.AddBuildMiddleware(quiet, "*/.pio/stack/*")  # noqa: F821
