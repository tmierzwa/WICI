#!/bin/sh
# SPDX-License-Identifier: MIT
# Board from tools/build.py, DRC (must be clean apart from the two custom-footprint warnings), then
# Gerbers and drills for JLC (origin: lower-left corner) and one ZIP to upload.
# Environment: KICAD_CLI, KICAD_PY (KiCad 10.0.6).
set -eu
cd "$(dirname "$0")/.."
KICAD_CLI=${KICAD_CLI:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}
KICAD_PY=${KICAD_PY:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}
test "$("$KICAD_CLI" version)" = "10.0.6" || { echo "wymagany KiCad 10.0.6" >&2; exit 1; }
"$KICAD_PY" tools/build.py
B=cad/przetwornica-3v3.kicad_pcb
"$KICAD_CLI" pcb drc --format json --severity-all --output checks/drc.json "$B" >/dev/null
python3 - <<'PY'
import json
r = json.load(open("checks/drc.json"))
bad = [v["description"] for v in r["violations"] if v["type"] != "lib_footprint_issues"]
if bad or r["unconnected_items"]:
    raise SystemExit(f"DRC: {bad} unconnected {len(r['unconnected_items'])}")
print("DRC czysty")
PY
G=fabrication/gerbers
rm -rf "$G" && mkdir -p "$G"
"$KICAD_CLI" pcb export gerbers --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.Paste,F.SilkS,Edge.Cuts \
  --subtract-soldermask --use-drill-file-origin --output "$G/" "$B" >/dev/null
"$KICAD_CLI" pcb export drill --format excellon --excellon-units mm --excellon-zeros-format decimal \
  --excellon-separate-th --drill-origin plot --output "$G/" "$B" >/dev/null
rm -f fabrication/przetwornica-3v3-gerber.zip
(cd "$G" && zip -q ../przetwornica-3v3-gerber.zip ./*)
echo "fabrication/: gerber ZIP, jlc-bom.csv, jlc-cpl.csv"
