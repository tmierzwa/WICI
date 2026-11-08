# SPDX-License-Identifier: MIT
"""Buduje emulator WICI-Link i uruchamia scenariusze (opis: README.md).

Dwa pliki wykonywalne: `base` z niezmienionego firmware/src (obecny kod) i `variant` z kopii, na którą nałożono
variant.patch (rozstrzygnięcia z 2026-11-05 za przełącznikami). Firmware w repozytorium pozostaje bez zmian.
Użycie: python3 tests/native/wici_emulator/run.py build <katalog>
        python3 tests/native/wici_emulator/run.py matrix <katalog> <wyniki.jsonl>
        python3 tests/native/wici_emulator/run.py pytania <katalog> <wyniki.jsonl>   (druga tura raportu)
        python3 tests/native/wici_emulator/run.py k1 <katalog> <wyniki.jsonl>        (wybór poprawki kolejki K1)
        python3 tests/native/wici_emulator/run.py regula_rodzica <katalog> <wyniki.jsonl>
        python3 tests/native/wici_emulator/run.py regula_rodzica_2 <katalog> <wyniki.jsonl>
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


# Druga tura raportu: reakcja na brak postępu. „Zestaw” to rozstrzygnięcia bez progu, z poprawką kolejki K1.
ZESTAW = ("learn=1", "alternate=1", "hold=7200", "flood=700", "k1flood=1")
CONFIRM_SEEDS = tuple(range(101, 111))
FINAL_SEEDS = tuple(range(201, 211))
PROGI = (("bez_progu", ()), ("30min", ("leave=1800",)), ("60min", ("leave=3600",)), ("90min", ("leave=5400",)),
         ("2proby", ("leaven=2",)), ("3proby", ("leaven=3",)), ("4proby", ("leaven=4",)))


def _config(name, *flags):
    return (name, "variant", (*ZESTAW, *flags))


def matrix_pytania_a():
    """Pytanie A: próg zmiany rodzica w czasie i w próbach, z tymi samymi ziarnami."""
    runs = []
    for name, flags in PROGI:
        config = _config(name, *flags)
        for scenario in ("koniec", "cala_siec"):
            for p in HOPS_P:
                runs.append((f"A:{scenario}", config, (f"p={p}", "skip=700", "hours=12")))
        for p in (800, 900):
            runs.append(("A:nasycenie", config, (f"p={p}", "spread=300", "skip=700", "hours=8")))
        for scenario in ("porzucanie_dziecko", "porzucanie_wszyscy"):
            runs.append((f"A:{scenario}", config, ("p=900", "hours=12")))
        for hours in (2, 4):
            runs.append(("A:przerwa", config, ("p=900", f"hours={hours}")))
    return runs


def matrix_pytania_c():
    """Pytanie C: przyczyna przy łączach zapasowych. Bez puli i bez „ostatnia wygrywa” to próby przyczyny, nie propozycje."""
    runs = []
    decisions = ("learn=1", "alternate=1", "flood=700")
    for p in HOPS_P:
        params = (f"p={p}", "skip=700", "hours=12")
        runs.append(("C:koniec", OBECNY, params))
        runs.append(("C:koniec", ("zestaw_bez_poprawki", "variant", decisions), params))
        runs.append(("C:koniec", ("poprawka_k1", "variant", (*decisions, "k1flood=1")), params))
        runs.append(("C:koniec", ("bez_puli", "variant", (*decisions, "nopool=1")), params))
        runs.append(("C:koniec", ("bez_ostatnia_wygrywa", "variant", (*decisions, "sticky=1")), params))
    for p in HOPS_P:
        runs.append(("C:bez_zapasowych@koniec", ("poprawka_k1", "variant", (*decisions, "k1flood=1")), (f"p={p}", "hours=12")))
    # Czy poprawka nie otwiera ataku: sąsiad podsuwa ramki w dół do numeru bez drogi.
    for name, flags in (("zestaw_bez_poprawki", decisions), ("poprawka_k1", (*decisions, "k1flood=1"))):
        runs.append(("C:atak_k1@porzucanie_koniec", (name, "variant", flags), ("p=900", "hours=8", "selective=2", "fake=2")))
    return runs


def matrix_pytania_b():
    """Pytanie B: próbka przekaźnika. Próg 2 próby, próbka po 20 min, najwyżej co 30 min."""
    probe = ("leaven=2", "probe=1200")
    variants = (("bez_probki", ("leaven=2",)), ("probka_ramka_w_dol", probe), ("probka_tylko_wlasna", (*probe, "probemode=2")))
    runs = []
    for hole in (2, 8, 13):
        for name, flags in variants:
            params = ("p=900", "hours=12", f"hole={hole}")
            runs.append(("B:porzucanie_koniec", _config(name, *flags), params))
            runs.append(("B:selektywny@porzucanie_koniec", _config(name, *flags), (*params, "selective=1")))
    for name, flags in variants:
        runs.append(("B:falszywy_powrot@porzucanie_koniec", _config(name, *flags), ("p=900", "hours=12", "hole=8", "fake=1")))
        for hours in (2, 4):
            runs.append(("B:przerwa", _config(name, *flags), ("p=900", f"hours={hours}")))
    for name, flags in variants[:2]:
        for scenario, params in (("koniec", ("p=900", "skip=700", "hours=12")), ("koniec", ("p=800", "skip=700", "hours=12")),
                                 ("nasycenie", ("p=900", "spread=300", "skip=700", "hours=8")),
                                 ("nasycenie", ("p=900", "spread=60", "skip=700", "hours=8"))):
            runs.append((f"B:{scenario}", _config(name, *flags), params))
        runs.append(("B:wrogi_src", _config(name, *flags), ("p=900", "hours=8")))
        runs.append(("B:bezczynna@wrogi_src", _config(name, *flags), ("p=900", "hours=8", "reports=1", "fullrun=1")))
    return runs


def matrix_zestaw():
    """Najlepszy zestaw na nowych ziarnach (CONFIRM_SEEDS) i drzewo. Ziarna 1-5 posłużyły do wyboru progu."""
    runs = []
    candidates = (("zestaw_30min", ("leave=1800",)), ("zestaw_60min", ("leave=3600",)), ("zestaw_2proby", ("leaven=2",)),
                  ("zestaw_3proby", ("leaven=3",)), ("zestaw_2proby_ta_wiadomosc", ("leaven=2", "permessage=1")))
    for scenario, params in (("koniec", ("p=800", "skip=700", "hours=12")), ("koniec", ("p=900", "skip=700", "hours=12")),
                             ("koniec", ("p=950", "skip=700", "hours=12")), ("cala_siec", ("p=800", "skip=700", "hours=12")),
                             ("cala_siec", ("p=900", "skip=700", "hours=12")), ("cala_siec", ("p=950", "skip=700", "hours=12")),
                             ("nasycenie", ("p=900", "spread=300", "skip=700", "hours=8")),
                             ("nasycenie", ("p=800", "spread=300", "skip=700", "hours=8")),
                             ("porzucanie_dziecko", ("p=900", "hours=12")), ("porzucanie_wszyscy", ("p=900", "hours=12"))):
        runs.append((f"Z:{scenario}", OBECNY, params))
        for name, flags in candidates:
            runs.append((f"Z:{scenario}", _config(name, *flags), params))
    runs.append(("Z:zestaw_bez_poprawki@koniec", ("zestaw_2proby_bez_poprawki", "variant",
                                                  ("learn=1", "alternate=1", "hold=7200", "flood=700", "leaven=2")),
                 ("p=800", "skip=700", "hours=12")))
    for params in (("p=900", "hours=12", "hole=8"), ("p=900", "hours=12", "hole=2")):
        runs.append(("Z:porzucanie_koniec", _config("zestaw_2proby", "leaven=2"), params))
        runs.append(("Z:porzucanie_koniec", _config("zestaw_2proby_probka", "leaven=2", "probe=1200"), params))
    return runs


def matrix_potwierdzenie():
    """Trzecie ziarna (FINAL_SEEDS): kandydaci wybrani na CONFIRM_SEEDS, bez dalszego strojenia."""
    runs = []
    candidates = (("zestaw_30min", ("leave=1800",)), ("zestaw_2proby_ta_wiadomosc", ("leaven=2", "permessage=1")),
                  ("zestaw_3proby_ta_wiadomosc", ("leaven=3", "permessage=1")))
    for scenario, params in (("koniec", ("p=800", "skip=700", "hours=12")), ("koniec", ("p=900", "skip=700", "hours=12")),
                             ("cala_siec", ("p=800", "skip=700", "hours=12")), ("cala_siec", ("p=900", "skip=700", "hours=12")),
                             ("cala_siec", ("p=950", "skip=700", "hours=12")),
                             ("nasycenie", ("p=900", "spread=300", "skip=700", "hours=8")),
                             ("nasycenie", ("p=800", "spread=300", "skip=700", "hours=8")),
                             ("porzucanie_dziecko", ("p=900", "hours=12")), ("porzucanie_wszyscy", ("p=900", "hours=12")),
                             ("przerwa", ("p=900", "hours=2"))):
        for name, flags in candidates:
            runs.append((f"P:{scenario}", _config(name, *flags), params))
    # Próbka z tym samym licznikiem, przy końcu łańcucha.
    for hole in (2, 8, 13):
        params = ("p=900", "hours=12", f"hole={hole}")
        runs.append(("P:porzucanie_koniec", _config("2proby_ta_wiadomosc", "leaven=2", "permessage=1"), params))
        runs.append(("P:porzucanie_koniec", _config("2proby_ta_wiadomosc_probka", "leaven=2", "permessage=1", "probe=1200"), params))
    for scenario in ("wrogi_src", "wrogi_beacon"):
        for name, flags in candidates:
            runs.append((f"P:{scenario}", _config(name, *flags), ("p=900", "hours=8")))
    # Ten sam atak na firmware bez zmian: czy cisza przekaźnika istnieje też w obecnym kodzie.
    runs.append(("P:atak_k1@porzucanie_koniec", OBECNY, ("p=900", "hours=8", "selective=2", "fake=2")))
    runs.append(("P:spokoj@porzucanie_koniec", OBECNY, ("p=900", "hours=8", "selective=2")))
    return runs


def matrix_drzewo():
    """Drzewo 50 stacji, 15 skoków, trzy obciążenia. Ten sam kształt bez i z poprawką."""
    runs = []
    for p in (800, 900):
        for skip in (0, 700):
            for spread in (3000, 600):
                params = (f"p={p}", f"skip={skip}", f"spread={spread}", "hours=8")
                runs.append(("D:drzewo", OBECNY, params))
                runs.append(("D:drzewo", ("zestaw_bez_poprawki", "variant",
                                          ("learn=1", "alternate=1", "hold=7200", "flood=700", "leaven=2")), params))
                runs.append(("D:drzewo", _config("zestaw_2proby", "leaven=2"), params))
                runs.append(("D:drzewo", _config("zestaw_2proby_ta_wiadomosc", "leaven=2", "permessage=1"), params))
    return runs


# Wybór poprawki kolejki K1. Trzy kody na tych samych ziarnach, w obu obrazach: bez nauki dróg (poprawka wejdzie
# wcześniej) i z zestawem przyjętym przez właściciela. Pierwszy kod bez przełączników to obecny (test zgodności).
OBRAZY = (("bez_nauki", ()), ("z_nauka", ("learn=1", "alternate=1", "hold=7200", "flood=700", "leaven=2", "permessage=1")))
KOD_K1 = (("obecny", ()), ("wariant1", ("k1flood=1",)), ("wariant2", ("k1routed=1",)))
K1_SEEDS = (1, 2, 3, 4, 5)
K1_NEW_SEEDS = tuple(range(301, 311))
ATTACK_SEEDS = (1, 2, 3, 4, 5, 301, 302, 303, 304, 305)


def _k1_configs():
    for picture, base in OBRAZY:
        for code, flags in KOD_K1:
            yield (f"{picture}:{code}", "variant", (*base, *flags))


def matrix_k1():
    """Działanie obu poprawek: łącza zapasowe 70%, koniec łańcucha, cała sieć, nasycenie, drzewo."""
    cases = [("K:koniec", (f"p={p}", "skip=700", "hours=12")) for p in HOPS_P]
    cases += [("K:cala_siec", (f"p={p}", "skip=700", "hours=12")) for p in HOPS_P]
    cases += [("K:bez_zapasowych@koniec", (f"p={p}", "hours=12")) for p in (800, 900)]
    cases += [("K:nasycenie", (f"p={p}", "spread=300", "skip=700", "hours=8")) for p in (800, 900)]
    cases += [("K:drzewo", (f"p={p}", "skip=700", f"spread={spread}", "hours=8")) for p in (800, 900) for spread in (3000, 600)]
    return [(name, config, params) for name, params in cases for config in _k1_configs()]


def matrix_k1_atak():
    """Sąsiad podsuwa ramki K1 do numerów bez drogi: łańcuch 15 skoków i 100 stacji słyszących się nawzajem."""
    cases = []
    for every in (0, 10, 2):
        chain_params = ("p=900", "skip=700", "hours=4", "reports=50", "spread=9000", f"fakeevery={every}")
        cases.append(("A:atak_k1", chain_params))
        cases.append(("A:koniec@atak_k1", (*chain_params, "fromend=1")))
        cases.append(("A:brzeg@atak_k1", (*chain_params, "hole=3")))
        cases.append(("A:slysza_sie@atak_k1", ("p=900", "n=100", "hours=2", "reports=20", "spread=4500", f"fakeevery={every}")))
    return [(name, config, params) for name, params in cases for config in _k1_configs()]


# Reguła „rozsyłanie w dół tylko od rodzica” na kodzie z poprawką K1. Tryb 1 to reguła właściciela, 2 dodaje bieżącego
# rodzica, 3 to kontrola pułapki (odrzucona kopia oznaczona jako widziana), tylko w próbach pułapki.
RODZIC_OBRAZY = (("bez_nauki", ("k1routed=1", "hold=7200")),
                 ("z_nauka", ("k1routed=1", "learn=1", "alternate=1", "hold=7200", "flood=700", "leaven=2", "permessage=1")))
RODZIC_SEEDS = (1, 2, 3, 4, 5, 301, 302, 303, 304, 305)


def matrix_regula_rodzica():
    chain = ("p=900", "skip=700", "hours=4", "reports=50", "spread=9000", "downrounds=4", "downevery=1800")
    clique = ("p=900", "n=100", "hours=2", "reports=20", "spread=4500", "downrounds=1")
    # Dwa łańcuchy po 12 skoków: droga przez łącze obejścia ma 13 skoków i mieści się w limicie 15.
    two = ("p=900", "two=1", "hops=12", "bridge=7", "hours=4", "downrounds=4", "downevery=1800", "spread=9000")
    cases = [(f"R:15_skokow_atak{e}", (*chain, f"fakeevery={e}")) for e in (0, 10, 2)]
    cases += [("R:15_skokow_atak2_przy_roocie", (*chain, "fakeevery=2", "hole=3")),
              ("R:15_skokow_p80", ("p=800", *chain[1:])),
              ("R:100_stacji_atak2_rozsylane", (*clique, "fakeevery=2", "fakebroadcast=1"))]
    cases += [(f"R:100_stacji_atak{e}", (*clique, f"fakeevery={e}")) for e in (0, 10, 2)]
    cases += [("R:martwy_rodzic_lancuch", (*chain, "dead=8", "fromend=1")),
              ("R:martwy_rodzic_100", (*clique, "dead=2")),
              ("R:martwy_rodzic_obejscie_ruch_w_gore", (*two, "dead=6", "reports=50", "fromend=1")),
              ("R:martwy_rodzic_obejscie_bez_ruchu", (*two, "dead=6", "reports=0")),
              ("R:zmiana_rodzica_lancuch", (*chain, "moved=8", "leaves=1")),
              ("R:zmiana_rodzica_dwa_razy", (*chain, "moved=8", "leaves=2")),
              ("R:zmiana_rodzica_obejscie", (*two, "moved=7", "leaves=1", "reports=50", "fromend=1"))]
    trap = {"R:15_skokow_atak0", "R:15_skokow_atak2", "R:100_stacji_atak0", "R:martwy_rodzic_obejscie_ruch_w_gore",
            "R:zmiana_rodzica_lancuch"}
    runs = []
    for name, params in cases:
        for picture, base in RODZIC_OBRAZY:
            for mode in (0, 1, 2, 3) if name in trap else (0, 1, 2):
                runs.append((f"{name}@regula_rodzica", (f"{picture}:tryb{mode}", "variant", (*base, f"floodparent={mode}")), params))
    return runs


def matrix_regula_martwy():
    """Dalsze ziarna tam, gdzie reguła wyglądała gorzej: martwy rodzic w łańcuchu z rodzicami zapasowymi."""
    params = ("p=900", "skip=700", "hours=4", "reports=50", "spread=9000", "downrounds=4", "downevery=1800", "dead=8", "fromend=1")
    return [("M:martwy_rodzic_lancuch@regula_rodzica", (f"{picture}:tryb{mode}", "variant", (*base, f"floodparent={mode}")), params)
            for picture, base in RODZIC_OBRAZY for mode in (0, 1)]


def matrix_regula_rodzica_2():
    """Druga tura reguły: napastnik jako bieżący rodzic, stara droga do stacji, która odmawia, dwie sąsiednie awarie."""
    chain = ("p=900", "skip=700", "hours=4", "reports=50", "spread=9000", "downrounds=4", "downevery=1800")
    clique = ("p=900", "n=100", "hours=2", "reports=20", "spread=4500", "downrounds=1")
    cases = []
    for name, shape in (("15_skokow_ofiara8", (*chain, "evilparent=8")), ("15_skokow_ofiara3", (*chain, "evilparent=3")),
                        ("100_stacji_8_ofiar", (*clique, "evilparent=8"))):
        cases += [(f"N:{name}_bez_ataku", shape), (f"N:{name}_atak2", (*shape, "fakeevery=2")),
                  (f"N:{name}_atak2_porzuca", (*shape, "fakeevery=2", "evildrop=1"))]
    cases += [("S:15_skokow_stara_droga", (*chain, "stale=1")),
              ("S:100_stacji_stara_droga", (*clique, "downrounds=4", "downevery=1200", "stale=8")),
              ("D:dwie_sasiednie_awarie", (*chain, "dead=8", "dead2=1", "fromend=1"))]
    return [(f"{name}@regula_rodzica", (f"{picture}:tryb{mode}", "variant", (*base, f"floodparent={mode}")), params)
            for name, params in cases for picture, base in RODZIC_OBRAZY for mode in (0, 1, 2)]


def run_matrix(binaries, out, seeds=SEEDS, workers=None, runs=None):
    """Uruchamia macierz i zapisuje jeden wiersz JSON na przebieg, w stałej kolejności."""
    jobs = [(scenario, config, params, seed) for scenario, config, params in (runs or matrix()) for seed in seeds]

    def one(job):
        scenario, (name, binary, flags), params, seed = job
        program = scenario.split(":")[-1].split("@")[-1] if ":" in scenario else scenario.split("@")[0]
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
    elif len(sys.argv) >= 4 and sys.argv[1] == "pytania":
        binaries = build(sys.argv[2])
        run_matrix(binaries, sys.argv[3], runs=[*matrix_pytania_c(), *matrix_pytania_a(), *matrix_pytania_b()])
        run_matrix(binaries, sys.argv[3] + ".drzewo", seeds=SEEDS[:3], runs=matrix_drzewo())
        run_matrix(binaries, sys.argv[3] + ".nowe_ziarna", seeds=CONFIRM_SEEDS, runs=matrix_zestaw())
        run_matrix(binaries, sys.argv[3] + ".potwierdzenie", seeds=FINAL_SEEDS, runs=matrix_potwierdzenie())
    elif len(sys.argv) >= 4 and sys.argv[1] == "k1":
        binaries = build(sys.argv[2])
        run_matrix(binaries, sys.argv[3], seeds=K1_SEEDS + K1_NEW_SEEDS, runs=matrix_k1())
        run_matrix(binaries, sys.argv[3] + ".atak", seeds=ATTACK_SEEDS, runs=matrix_k1_atak())
    elif len(sys.argv) >= 4 and sys.argv[1] == "regula_rodzica":
        binaries = build(sys.argv[2])
        run_matrix(binaries, sys.argv[3], seeds=RODZIC_SEEDS, runs=matrix_regula_rodzica())
        run_matrix(binaries, sys.argv[3] + ".martwy", seeds=tuple(range(401, 431)), runs=matrix_regula_martwy())
    elif len(sys.argv) >= 4 and sys.argv[1] == "regula_rodzica_2":
        run_matrix(build(sys.argv[2]), sys.argv[3], seeds=RODZIC_SEEDS, runs=matrix_regula_rodzica_2())
    elif len(sys.argv) >= 3 and sys.argv[1] == "summary":
        print("\n".join(summary(sys.argv[2])))
    else:
        print(__doc__)
