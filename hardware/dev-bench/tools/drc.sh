#!/bin/sh
# SPDX-License-Identifier: MIT
# Full DRC of the carrier into checks/drc.json. Refills the zones and saves the
# board, so checksums are taken after this step. Exit code 5 on any violation.
# kicad-cli silently drops the whole custom rule file when one rule does not parse,
# so a copy of the project with a canary rule that must fire is checked first.
# Environment: KICAD_CLI (KiCad 10.0.6).
set -eu
cd "$(dirname "$0")/.."
KICAD_CLI=${KICAD_CLI:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp cad/plytka-nosna.kicad_pcb cad/plytka-nosna.kicad_pro cad/plytka-nosna.kicad_dru "$work/"
printf '%s\n' "(rule \"N1 canary\" (condition \"A.Type == 'via'\") (constraint via_diameter (min 50mm)))" >> "$work/plytka-nosna.kicad_dru"
"$KICAD_CLI" pcb drc --format json --severity-all --output "$work/canary.json" "$work/plytka-nosna.kicad_pcb" > /dev/null
grep -q "N1 canary" "$work/canary.json" || { echo "custom rules in cad/plytka-nosna.kicad_dru were not loaded" >&2; exit 1; }
"$KICAD_CLI" pcb drc --format json --all-track-errors --severity-all --schematic-parity \
  --exit-code-violations --refill-zones --save-board --output checks/drc.json cad/plytka-nosna.kicad_pcb
