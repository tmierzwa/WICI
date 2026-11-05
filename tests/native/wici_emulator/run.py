# SPDX-License-Identifier: MIT
"""Buduje emulator WICI-Link i uruchamia scenariusze (opis: README.md).

Dwa pliki wykonywalne: `base` z niezmienionego firmware/src (obecny kod) i `variant` z kopii, na którą nałożono
variant.patch (rozstrzygnięcia z 2026-11-05 za przełącznikami). Firmware w repozytorium pozostaje bez zmian.
Użycie: python3 tests/native/wici_emulator/run.py build <katalog>
        python3 tests/native/wici_emulator/run.py matrix <katalog> <wyniki.jsonl>
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "firmware" / "src"
CRYPTO = ROOT / "firmware" / ".pio" / "stack" / "Crypto"
FIRMWARE = ("wici_radio", "wici_destination", "wici_hop", "wici_flood", "wici_route", "wici_relay", "wici_seen",
            "wici_seq", "wici_link", "wici_gateway", "wici_epoch", "wici_beacon", "wici_hop_auth", "wici_airtime",
            "kiss", "envelope", "envelope_counter", "envelope_parts", "envelope_replay", "sha2")
CRYPTO_UNITS = ("AuthenticatedCipher.cpp", "BigNumberUtil.cpp", "ChaCha.cpp", "ChaChaPoly.cpp", "Cipher.cpp", "Crypto.cpp",
                "Curve25519.cpp", "Ed25519.cpp", "Hash.cpp", "NoiseSource.cpp", "Poly1305.cpp", "RNG.cpp", "SHA256.cpp",
                "SHA512.cpp")
OWN = ("emulator.cpp", "scenarios.cpp")


def compiler():
    return shutil.which("clang++") or shutil.which("g++")


def available():
    return compiler() is not None and (CRYPTO / ".wici-stamp").exists()


def _compile(job):
    source, obj, flags = job
    if not obj.exists() or obj.stat().st_mtime < source.stat().st_mtime:
        built = subprocess.run([compiler(), *flags, "-c", str(source), "-o", str(obj)], capture_output=True, text=True)
        if built.returncode:
            raise RuntimeError(f"build failed in {source.name}:\n{built.stderr[-6000:]}")
    return obj


def _patched(directory):
    """Kopia firmware/src z nałożonym variant.patch; nieaktualna łatka przerywa budowanie."""
    if directory.exists():
        shutil.rmtree(directory)
    shutil.copytree(SRC, directory, ignore=shutil.ignore_patterns("host"))
    applied = subprocess.run(["patch", "-s", "-p3", "--fuzz=0", "-i", str(HERE / "variant.patch")],
                             capture_output=True, text=True, cwd=directory)
    if applied.returncode:
        raise RuntimeError("variant.patch nie pasuje do firmware/src:\n" + applied.stdout + applied.stderr)
    return directory


def build(out, sanitize=False, variant=True):
    """Zwraca słownik {"base": ścieżka, "variant": ścieżka}."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    extra = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g", "-O1"] if sanitize else ["-O2"]
    common = ["-std=c++17", "-fno-exceptions", "-fno-rtti", *extra, "-isystem", str(CRYPTO)]
    strict = ["-Wall", "-Wextra", "-Werror"]
    results = {}
    crypto_dir = out / "crypto"
    crypto_dir.mkdir(exist_ok=True)
    jobs = [(CRYPTO / unit, crypto_dir / (unit + ".o"), [*common, "-w"]) for unit in CRYPTO_UNITS]
    with ThreadPoolExecutor() as pool:
        crypto_objects = list(pool.map(_compile, jobs))
        for name in ("base", "variant") if variant else ("base",):
            source = _patched(out / "src-variant") if name == "variant" else SRC
            folder = out / name
            folder.mkdir(exist_ok=True)
            flags = [*common, f"-I{source}", f"-I{HERE}"]
            if name == "variant":
                flags.append("-DWICI_EMU_VARIANT")
            # Pliki firmware i emulatora zawsze od nowa: zależności od nagłówków nie są śledzone.
            for stale in folder.glob("*.o"):
                stale.unlink()
            units = FIRMWARE + (("wici_variant",) if name == "variant" else ())
            jobs = [(source / f"{unit}.cpp", folder / f"{unit}.o", [*flags, *strict]) for unit in units]
            jobs += [(HERE / unit, folder / f"{unit}.o", [*flags, "-Wall", "-Wextra"]) for unit in OWN]
            objects = list(pool.map(_compile, jobs))
            binary = out / f"wici_emulator_{name}"
            linked = subprocess.run([compiler(), *common, *map(str, objects + crypto_objects), "-o", str(binary)],
                                    capture_output=True, text=True)
            if linked.returncode:
                raise RuntimeError(f"link failed:\n{linked.stderr[-4000:]}")
            results[name] = binary
    return results


# Konfiguracje raportu: (nazwa, plik wykonywalny, parametry). „obecny” to kod z firmware/src bez zmian.
OBECNY = ("obecny", "base", ())
NAUKA = ("nauka", "variant", ("learn=1",))
NAUKA_PRZEMIAN = ("nauka+przemian", "variant", ("learn=1", "alternate=1"))
PELNY = ("rozstrzygniecia", "variant", ("learn=1", "alternate=1", "leave=1800", "hold=7200", "flood=700"))
BEZ_ZMIANY_RODZICA = ("nauka+przemian+budzet", "variant", ("learn=1", "alternate=1", "flood=700"))
SEEDS = (1, 2, 3, 4, 5)
HOPS_P = (800, 900, 950)


def _leave(seconds):
    return (f"nauka+przemian+zmiana{seconds}", "variant",
            ("learn=1", "alternate=1", f"leave={seconds}", "hold=7200", "flood=700"))


def matrix():
    """Wszystkie przebiegi raportu: (scenariusz, konfiguracja, parametry)."""
    runs = []
    for scenario in ("koniec", "cala_siec"):
        for p in HOPS_P:
            for config in (OBECNY, NAUKA, NAUKA_PRZEMIAN, BEZ_ZMIANY_RODZICA, PELNY):
                runs.append((scenario, config, (f"p={p}", "hours=12")))
    for p in HOPS_P:
        for config in (OBECNY, NAUKA, NAUKA_PRZEMIAN, PELNY):
            runs.append(("zmiana_rodzica", config, (f"p={p}", "hours=6")))
    for scenario in ("porzucanie_dziecko", "porzucanie_koniec", "porzucanie_wszyscy"):
        for config in (OBECNY, PELNY):
            runs.append((scenario, config, ("p=900", "hours=12")))
    # Czasy wobec opóźnień: sieć bez awarii, z rodzicem zapasowym; każda zmiana rodzica to fałszywy alarm.
    for scenario in ("koniec", "cala_siec"):
        for p in HOPS_P:
            for config in (OBECNY, BEZ_ZMIANY_RODZICA, _leave(1800), _leave(3600), _leave(5400)):
                runs.append((scenario + "@czasy", config, (f"p={p}", "skip=700", "hours=12")))
    for config in (_leave(1800), _leave(3600), _leave(5400)):
        runs.append(("porzucanie_dziecko@czasy", config, ("p=900", "hours=12")))
    for p in HOPS_P:
        for config in (OBECNY, PELNY):
            for spread in (300, 60):
                runs.append(("nasycenie", config, (f"p={p}", f"spread={spread}", "hours=8")))
    for skip in (0, 700):
        for config in (OBECNY, PELNY, _leave(5400)):
            runs.append(("fala_beacon", config, ("p=900", f"skip={skip}")))
    for scenario in ("budzet_slysza_sie", "budzet_lancuchy"):
        for n in (50, 100):
            for name, flood in (("bez_budzetu", 0), ("budzet700", 700)):
                runs.append((scenario, (name, "variant", ("learn=1", "alternate=1", f"flood={flood}")), (f"n={n}", "p=900", "hours=4")))
    for scenario in ("wrogi_src", "wrogi_beacon"):
        for config in (OBECNY, NAUKA, NAUKA_PRZEMIAN, PELNY):
            runs.append((scenario, config, ("p=900", "hours=8")))
    # Nasycenie z rodzicem zapasowym: tu fałszywa zmiana rodzica kosztuje najwięcej.
    for config in (OBECNY, BEZ_ZMIANY_RODZICA, _leave(1800), _leave(3600), _leave(5400)):
        runs.append(("nasycenie@czasy", config, ("p=900", "spread=300", "skip=700", "hours=8")))
    # Blokada: zgłoszenia przez 10 h, więc widać też powrót do porzucającego rodzica po końcu blokady.
    runs.append(("porzucanie_dziecko@blokada", OBECNY, ("p=900", "spread=36000", "hours=2")))
    for hold in (0, 1800, 7200, 14400):
        config = (f"zmiana1800_blokada{hold}", "variant", ("learn=1", "alternate=1", "leave=1800", f"hold={hold}", "flood=700"))
        runs.append(("porzucanie_dziecko@blokada", config, ("p=900", "spread=36000", "hours=2")))
    # Wrażliwość na założenia kanału.
    for assumption in ("sense=2", "miss=0", "miss=100"):
        for config in (OBECNY, PELNY):
            runs.append(("koniec@zalozenia", config, ("p=900", assumption, "hours=12")))
            runs.append(("cala_siec@zalozenia", config, ("p=900", assumption, "hours=12")))
    return runs


def run_matrix(binaries, out, seeds=SEEDS, workers=None):
    """Uruchamia macierz i zapisuje jeden wiersz JSON na przebieg, w stałej kolejności."""
    jobs = [(scenario, config, params, seed) for scenario, config, params in matrix() for seed in seeds]

    def one(job):
        scenario, (name, binary, flags), params, seed = job
        program = scenario.split("@")[0]
        done = subprocess.run([str(binaries[binary]), program, f"seed={seed}", *params, *flags],
                              capture_output=True, text=True)
        if done.returncode:
            raise RuntimeError(f"{job} failed:\n{done.stderr[-2000:]}")
        record = json.loads(done.stdout.splitlines()[-1])
        record.update(run=scenario, config=name, params=" ".join(params))
        return json.dumps(record, ensure_ascii=False, sort_keys=True)

    with ThreadPoolExecutor(workers) as pool, open(out, "w") as handle:
        for line in pool.map(one, jobs):
            handle.write(line + "\n")


def summary(path, fields=("closed", "reports", "arrive_max_s", "close_p50_s", "close_max_s", "flood", "busy_pm", "leaves",
                          "off_planned", "max_silent_s", "stations_silent_30min")):
    """Mediana i zakres po ziarnach dla każdego przebiegu macierzy, jako wiersze tekstu."""
    groups = {}
    for line in Path(path).read_text().splitlines():
        record = json.loads(line)
        extras = (record["params"],)
        groups.setdefault((record["run"], record["config"], extras), []).append(record)
    lines = []
    for (name, config, extras), records in groups.items():
        cells = []
        for field in fields:
            values = sorted(r[field] for r in records if field in r)
            if values:
                cells.append(f"{field}={values[len(values) // 2]}[{values[0]}..{values[-1]}]")
        lines.append(f"{name} {config} {' '.join(extras)}: " + " ".join(cells))
    return lines


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "build":
        print(build(sys.argv[2]))
    elif len(sys.argv) >= 4 and sys.argv[1] == "matrix":
        run_matrix(build(sys.argv[2]), sys.argv[3])
    elif len(sys.argv) >= 3 and sys.argv[1] == "summary":
        print("\n".join(summary(sys.argv[2])))
    else:
        print(__doc__)
