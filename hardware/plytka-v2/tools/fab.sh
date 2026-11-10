#!/bin/sh
# SPDX-License-Identifier: MIT
# Fabrication files for JLC from the board build.sh has just made and checked (called at the end of build.sh):
#   fabrication/gerbers/           Gerbers of the 4 copper layers, masks, paste, silkscreen, outline; Excellon drills
#   fabrication/plytka-v2-gerber.zip   the same files, to upload
#   fabrication/jlc-bom.csv, jlc-cpl.csv   assembly BOM and placement (tools/fab.py)
# Coordinates are the absolute ones of the board file in every file (y of the placement = -y of KiCad, as in the
# Gerbers). Creation dates are taken out and the ZIP is written with fixed file times, so the files change only
# with the board.
# Environment: KICAD_CLI, KICAD_PY (KiCad 10.0.6).
set -eu
cd "$(dirname "$0")/.."
KICAD_CLI=${KICAD_CLI:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}
KICAD_PY=${KICAD_PY:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}
B=cad/plytka-v2.kicad_pcb
G=fabrication/gerbers
rm -rf "$G" fabrication/plytka-v2-gerber.zip && mkdir -p "$G"
"$KICAD_CLI" pcb export gerbers --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.Paste,F.SilkS,B.SilkS,Edge.Cuts \
  --subtract-soldermask --output "$G/" "$B" > /dev/null
"$KICAD_CLI" pcb export drill --format excellon --excellon-units mm --excellon-zeros-format decimal \
  --excellon-separate-th --drill-origin absolute --output "$G/" "$B" > /dev/null
rm -f "$G"/*.gbrjob
for f in "$G"/*; do
  sed -i.bak -e '/CreationDate/d' -e 's/^\(G04 Created by KiCad .*\) date .*\*$/\1*/' \
    -e 's/^\(; DRILL file .*\) date .*$/\1/' "$f" && rm "$f.bak"
  if grep -q "20[0-9][0-9]-[01][0-9]-[0-3][0-9]" "$f"; then echo "data w pliku $f" >&2; exit 1; fi
  touch -t 200001010000 "$f"
done
(cd "$G" && TZ=UTC zip -q -X -D ../plytka-v2-gerber.zip $(ls | LC_ALL=C sort))
(cd tools && "$KICAD_PY" fab.py)
