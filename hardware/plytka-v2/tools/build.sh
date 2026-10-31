#!/bin/sh
# SPDX-License-Identifier: MIT
# Regenerate the preliminary v2 schematic and placement from tools/design.py and run ERC and DRC.
# Environment: KICAD_CLI, KICAD_SHARE (KiCad 10.0.6).
set -eu
cd "$(dirname "$0")/.."
KICAD_CLI=${KICAD_CLI:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}
KICAD_SHARE=${KICAD_SHARE:-/Applications/KiCad/KiCad.app/Contents/SharedSupport}
test "$("$KICAD_CLI" version)" = "10.0.6" || { echo "wymagany KiCad 10.0.6" >&2; exit 1; }
mkdir -p cad checks
KICAD_PY=${KICAD_PY:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}
(cd tools && "$KICAD_PY" prepare_libraries.py)
python3 tools/design.py
python3 tools/make_schematic.py "$KICAD_SHARE/symbols"
"$KICAD_CLI" sch erc --format json --severity-all --exit-code-violations --output checks/erc.json cad/plytka-v2.kicad_sch
"$KICAD_CLI" sch export netlist --format kicadxml --output checks/netlist.xml cad/plytka-v2.kicad_sch
"$KICAD_CLI" sch export pdf --output schemat.pdf cad/plytka-v2.kicad_sch
# Preliminary placement, no tracks: DRC may report only silkscreen notes and unconnected pads.
(cd tools && "$KICAD_PY" make_pcb.py "$KICAD_SHARE/footprints")
"$KICAD_CLI" pcb drc --format json --severity-all --output checks/drc.json cad/plytka-v2.kicad_pcb
python3 -c "
import json, sys
found = [v['type'] for v in json.load(open('checks/drc.json'))['violations'] if not v['type'].startswith('silk_')]
sys.exit(f'DRC: {found}' if found else 0)"
# The netlist names its source by absolute path; keep it relative to this board.
sed -i.bak "s#$(pwd)/##g" checks/netlist.xml && rm checks/netlist.xml.bak
