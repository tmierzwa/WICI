#!/bin/sh
# SPDX-License-Identifier: MIT
# Full DRC of the carrier into checks/drc.json. Refills the zones and saves the
# board, so checksums are taken after this step. Exit code 5 on any violation.
# Environment: KICAD_CLI (KiCad 10.0.6).
set -eu
cd "$(dirname "$0")/.."
KICAD_CLI=${KICAD_CLI:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}
"$KICAD_CLI" pcb drc --format json --all-track-errors --severity-all --schematic-parity \
  --exit-code-violations --refill-zones --save-board --output checks/drc.json cad/plytka-nosna.kicad_pcb
