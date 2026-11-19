#!/bin/sh
# SPDX-License-Identifier: MIT
# Route the board with Freerouting 2.5.0 in stages; places the parts and prepares the board itself first:
#   1. checks/routing.dsn -> checks/routing.ses: the power nets and every net in the areas of the 12 V parts;
#   2. checks/routing-2.dsn -> checks/routing-2.ses: the rest, with the complete nets of stage 1 as fixed copper;
#   3. and on (checks/routing-N.*): the nets still open and their neighbours again, until nothing is open.
# Each session is kept with the checksum of its DSN, so build.sh imports it only for the same placement.
# Freerouting ends a run for good after ten passes without a better score; on the whole board at once that left
# about forty connections open. It skips the net classes Plane (GND, +3V3: they reach the planes through the vias
# of route_pcb.py) and Later (the nets that wait for a later stage or are complete).
# Environment: JAVA (Java 25+), FREEROUTING (freerouting-2.5.0.jar, SHA-256 f6f51bb0...5de3c7), KICAD_PY,
# PASSES (default 100), STAGES (most stages, default 8).
set -eu
cd "$(dirname "$0")/.."
JAVA=${JAVA:-$(/usr/libexec/java_home -v 25)/bin/java}
KICAD_PY=${KICAD_PY:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}
work=$(mktemp -d)
stage() {  # DSN, SES, classes to skip, log
  "$JAVA" -jar "$FREEROUTING" -de "$1" -do "$2" --router.autorouter.max_passes="${PASSES:-100}" \
    --gui.enabled=false --router.autorouter.ignore_net_classes="$3" \
    --user_data_path="$work" > "$work/out.txt" 2>&1 || true
  grep -E "Auto-routing stage completed|ERROR" "$work/out.txt" | sed 's/.*INFO *//' | tail -3
  shasum -a 256 "$1" | cut -d' ' -f1 > "$2.sha256"
  sed -i.bak "s#$(pwd)/##g" "$2" && rm "$2.bak"
  sed -e "s#$(pwd)/##g" -e "s#$HOME#~#g" "$work/out.txt" > "$4"
}
# Always from the prepared state: on a board that is routed already, stage 2 would see nothing open and the kept
# sessions would be thrown away.
(cd tools && "$KICAD_PY" make_pcb.py "${KICAD_SHARE:-/Applications/KiCad/KiCad.app/Contents/SharedSupport}/footprints" \
  && "$KICAD_PY" route_pcb.py prepare) 2>&1 | grep "placed\|prepared\|closer\|no room\|Error\|error" || true
test "$(shasum -a 256 checks/routing.dsn | cut -d' ' -f1)" != "" || exit 1
stage checks/routing.dsn checks/routing.ses Plane,Later,LaterHV checks/routing.log
prev=checks/routing; n=2
while [ "$n" -le "${STAGES:-8}" ]; do
  f=checks/routing-$n
  out=$(cd tools && "$KICAD_PY" route_pcb.py stage "$n" "../$prev.ses" 2>&1 | grep "imported\|open nets")
  echo "$out"
  # Without this line the stage step failed and the job of this stage is an old one: stop.
  case "$out" in *"open nets"*) ;; *) echo "route_pcb.py stage $n nie powiodło się" >&2; exit 1 ;; esac
  case "$out" in *"open nets: none"*) break ;; esac
  stage "$f.dsn" "$f.ses" Plane,Later,LaterHV "$f.log"
  prev=$f; n=$((n + 1))
done
while [ "$n" -le 20 ]; do rm -f checks/routing-$n.dsn checks/routing-$n.ses checks/routing-$n.ses.sha256 checks/routing-$n.log; n=$((n + 1)); done
rm -rf "$work"
