# SPDX-License-Identifier: MIT
"""Station simulator (software/simulator): it runs the bench-b firmware image without drift.

The committed WebAssembly build is the bench-b source set and flags of firmware/platformio.ini with the
pinned stack (build.json stamp of every input), only the MCU files listed in REPLACED are swapped for
virtual-board versions of the same interface, the firmware has no simulator hooks, the ROM AES stand-in
follows FIPS-197, every training exercise passes on the committed image (Node) and the R02 panel layout
follows hardware/r02/obudowa.md."""

from pathlib import Path
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "software" / "simulator"
SRC = ROOT / "firmware" / "src"
sys.path.insert(0, str(SIM))
import build  # noqa: E402


def functions(path, definitions):
    """Names of functions declared (`;`) or defined (`{`) at line start in `namespace platform`."""
    text = path.read_text(encoding="utf-8")
    body = text[text.index("namespace platform {"):]
    end = r"\{" if definitions else ";"
    return set(re.findall(r"^(?:\[\[\w+\]\]\s*)?[A-Za-z_][\w:<>&* ]*?\b(\w+)\([^;{]*\)\s*(?:const\s*)?" + end, body, re.M))


class SimulatorTest(unittest.TestCase):
    def test_committed_build_is_current(self):
        self.assertEqual(build.check(), [], "rebuild: python3 software/simulator/build.py (Emscripten %s)" % build.EMSCRIPTEN)

    def test_image_is_the_bench_b_source_set(self):
        cfg = build.platformio()
        image = build.firmware_sources(cfg)
        stamp = json.loads((SIM / "web" / "build.json").read_text(encoding="utf-8"))
        self.assertEqual(stamp["firmware"], image)
        self.assertEqual(stamp["env"], "bench-b")
        self.assertEqual(stamp["flags"], build.portable(build.PLATFORM_DEFINES + build.build_flags(cfg)))
        self.assertIn("-DWICI_BENCH_B", stamp["flags"])
        compiled = {Path(p).name for p in stamp["outputs"]["wici-station.mjs"]["sources"] if p.startswith("firmware/src/")}
        self.assertEqual(compiled, set(image) - set(build.REPLACED))
        self.assertEqual(sorted(stamp["stack"], key=lambda d: d["name"]),
                         sorted(({"name": d[0], "commit": d[2]} for d in build.stack_deps.DEPS), key=lambda d: d["name"]))

    def test_replaced_files_keep_the_interface(self):
        self.assertEqual(set(build.REPLACED), {"platform_esp32.cpp", "sharp_extcomin_esp32.cpp"})
        interface = functions(SRC / "platform.h", definitions=False)
        self.assertGreater(len(interface), 10)
        for impl in (SRC / "platform_esp32.cpp", SIM / "hal" / "platform_sim.cpp"):
            self.assertEqual(interface - functions(impl, definitions=True), set(), impl)
        self.assertIn("Display::beginExtcomin", (SIM / "hal" / "sharp_extcomin_sim.cpp").read_text(encoding="utf-8"))

    def test_firmware_has_no_simulator_hooks(self):
        for path in sorted(SRC.rglob("*")):
            if path.is_file():
                self.assertNotIn("WICI_SIM", path.read_text(encoding="utf-8", errors="replace"), path)

    @unittest.skipUnless(shutil.which("c++"), "no host C++ compiler")
    def test_rom_aes_matches_fips_197(self):
        main = r"""
#include <stdio.h>
extern "C" int esp_aes_setkey(unsigned char*, const unsigned char*, unsigned);
extern "C" int esp_aes_crypt_ecb(unsigned char*, int, const unsigned char*, unsigned char*);
int main() {
    unsigned char key[32], in[16], out[16], back[16], ctx[64];
    for (int i = 0; i < 32; i++) key[i] = i;
    for (int i = 0; i < 16; i++) in[i] = (i << 4) | i;
    for (unsigned bits = 128; bits <= 256; bits += 64) {
        esp_aes_setkey(ctx, key, bits);
        esp_aes_crypt_ecb(ctx, 1, in, out);
        esp_aes_crypt_ecb(ctx, 0, out, back);
        for (int i = 0; i < 16; i++) printf("%02x", out[i]);
        printf(" %d\n", back[0] == in[0] && back[15] == in[15]);
    }
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "main.cpp").write_text(main, encoding="utf-8")
            exe = Path(tmp) / "aes"
            subprocess.run(["c++", "-std=gnu++17", str(SIM / "hal" / "esp_rom.cpp"), str(Path(tmp) / "main.cpp"), "-o", str(exe)], check=True)
            out = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.split("\n")
        # FIPS-197, dodatek C.1–C.3
        self.assertEqual(out[:3], ["69c4e0d86a7b0430d8cdb78070b4c55a 1", "dda97ca4864cdfe06eaf70a0ec0d7191 1",
                                   "8ea2b7ca516745bfeafc49904b496089 1"])

    def test_panel_logo_is_the_project_logo(self):
        self.assertEqual((SIM / "web" / "wici-logo.svg").read_bytes(), (ROOT / "media" / "logo" / "WICI-na-jasnym.svg").read_bytes())
        self.assertEqual((SIM / "web" / "wici-logo-ciemne.svg").read_bytes(), (ROOT / "media" / "logo" / "WICI-na-ciemnym.svg").read_bytes())

    @unittest.skipUnless(shutil.which("node"), "Node.js not installed")
    def test_exercises_and_layout_rules(self):
        out = subprocess.run(["node", str(SIM / "test_scenarios.mjs")], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(out.stdout.count("\nok "), 8, out.stdout)
        script = ("import { R02, RULES } from './web/layouts.js';"
                  "console.log(JSON.stringify(RULES.map((r) => [r.id, r.test(R02).ok])));")
        out = subprocess.run(["node", "--input-type=module", "-e", script], cwd=SIM, capture_output=True, text=True, check=True)
        rules = dict(json.loads(out.stdout))
        self.assertTrue(all(rules.values()), rules)   # panel R02 spełnia zasady z obudowa.md


if __name__ == "__main__":
    unittest.main()
