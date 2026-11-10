#!/bin/sh
# SPDX-License-Identifier: MIT
# Regenerate the preliminary v2 schematic, placement and copper from tools/design.py and run ERC and DRC.
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
# The netlist names its source by absolute path; keep it relative to this board.
sed -i.bak "s#$(pwd)/##g" checks/netlist.xml && rm checks/netlist.xml.bak
# Placement, then the copper (route_pcb.py): rules, hand-made copper, plane vias and the routing job
# checks/routing.dsn. The kept Freerouting sessions (tools/route.sh, several stages) are imported one after another,
# each only when it was made from exactly the DSN written here; after any change of placement or hand-made copper
# build.sh leaves the board with planes only and route.sh has to run again.
place() {
  (cd tools && "$KICAD_PY" make_pcb.py "$KICAD_SHARE/footprints" && "$KICAD_PY" route_pcb.py prepare)
}
place
stale=; prev=checks/routing; n=2
[ -f $prev.ses ] && [ "$(shasum -a 256 $prev.dsn | cut -d' ' -f1)" = "$(cat $prev.ses.sha256)" ] || stale=$prev
while [ -z "$stale" ]; do
  f=checks/routing-$n
  out=$(cd tools && "$KICAD_PY" route_pcb.py stage "$n" "../$prev.ses" 2>&1 | grep "open nets")
  case "$out" in *"open nets: none"*) break ;; esac
  [ -f $f.ses ] && [ "$(shasum -a 256 $f.dsn | cut -d' ' -f1)" = "$(cat $f.ses.sha256)" ] || stale=$f
  prev=$f; n=$((n + 1))
done
if [ -z "$stale" ]; then
  (cd tools && "$KICAD_PY" route_pcb.py finish)
else
  echo "$stale.ses nie pasuje do $stale.dsn: płytka bez ścieżek routera (uruchom tools/route.sh)" >&2
  place
  (cd tools && "$KICAD_PY" route_pcb.py planes)
fi
# kicad-cli drops the whole .kicad_dru without a word when one rule does not parse: a copy with a canary rule
# that must fire is checked first (as hardware/dev-bench/tools/drc.sh).
work=$(mktemp -d)
cp cad/plytka-v2.kicad_pcb cad/plytka-v2.kicad_pro cad/plytka-v2.kicad_dru "$work/"
printf '%s\n' "(rule \"v2 canary\" (condition \"A.Type == 'Via'\") (constraint via_diameter (min 50mm)))" >> "$work/plytka-v2.kicad_dru"
"$KICAD_CLI" pcb drc --format json --output "$work/canary.json" "$work/plytka-v2.kicad_pcb" > /dev/null
grep -q "v2 canary" "$work/canary.json" || { echo "reguły z cad/plytka-v2.kicad_dru nie zostały wczytane" >&2; exit 1; }
rm -rf "$work"
"$KICAD_CLI" pcb drc --format json --severity-all --refill-zones --save-board --output checks/drc.json cad/plytka-v2.kicad_pcb
python3 -c "
import json, sys
d = json.load(open('checks/drc.json'))
found = [v['type'] for v in d['violations'] if not v['type'].startswith('silk_') and v['type'] != 'lib_footprint_issues']
print(f'DRC: {len(found)} naruszeń poza sitodrukiem, {len(d[\"unconnected_items\"])} niepołączonych')
sys.exit(f'DRC: {found}' if found else 'DRC: niepołączone' if d['unconnected_items'] else 0)"
