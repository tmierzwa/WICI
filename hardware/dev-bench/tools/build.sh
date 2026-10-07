#!/bin/sh
# SPDX-License-Identifier: MIT
# Regenerate the carrier from tools/design.py up to the placed, unrouted PCB.
# Environment: KICAD_CLI, KICAD_PY (KiCad 10.0.6), KICAD_SHARE (its SharedSupport).
set -eu
cd "$(dirname "$0")/.."
KICAD_CLI=${KICAD_CLI:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}
KICAD_PY=${KICAD_PY:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}
KICAD_SHARE=${KICAD_SHARE:-/Applications/KiCad/KiCad.app/Contents/SharedSupport}
test "$("$KICAD_CLI" version)" = "10.0.6" || { echo "wymagany KiCad 10.0.6" >&2; exit 1; }
mkdir -p cad checks
python3 tools/prepare_footprints.py "$KICAD_SHARE/footprints"
python3 tools/make_project.py
python3 tools/make_schematic.py "$KICAD_SHARE/symbols"
"$KICAD_CLI" sch erc --format json --severity-all --exit-code-violations --output checks/erc.json cad/plytka-nosna.kicad_sch
"$KICAD_CLI" sch export netlist --format kicadxml --output checks/netlist.xml cad/plytka-nosna.kicad_sch
(cd tools && "$KICAD_PY" make_board.py)
# pcbnew saves the project with its default DRC severities; write ours again.
python3 tools/make_project.py
python3 tools/strip_paths.py checks/netlist.xml checks/routing.dsn
