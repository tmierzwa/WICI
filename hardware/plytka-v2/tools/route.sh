#!/bin/sh
# SPDX-License-Identifier: MIT
# Route checks/routing.dsn (from route_pcb.py prepare) with Freerouting 2.5.0 into checks/routing.ses and record
# the DSN checksum in checks/routing.ses.sha256, so build.sh imports the session only for the same placement.
# Neck-down lets the wide 12 V and VSYS traces enter the narrow pins. Freerouting skips the net class Plane (GND, +3V3): they reach the planes through vias from route_pcb.py.
# Environment: JAVA (Java 25+), FREEROUTING (freerouting-2.5.0.jar, SHA-256 f6f51bb0...5de3c7), PASSES (default 100).
set -eu
cd "$(dirname "$0")/.."
JAVA=${JAVA:-$(/usr/libexec/java_home -v 25)/bin/java}
work=$(mktemp -d)
"$JAVA" -jar "$FREEROUTING" -de checks/routing.dsn -do checks/routing.ses --router.autorouter.max_passes="${PASSES:-100}" \
  --gui.enabled=false --router.automatic_neckdown=true --router.autorouter.ignore_net_classes=Plane \
  --user_data_path="$work" > "$work/out.txt" 2>&1 || true
grep -E "Auto-routing stage completed|Optimization stage completed|unrouted|ERROR" "$work/out.txt" | sed 's/.*INFO *//' | tail -5
shasum -a 256 checks/routing.dsn | cut -d' ' -f1 > checks/routing.ses.sha256
sed -i.bak "s#$(pwd)/##g" checks/routing.ses && rm checks/routing.ses.bak
sed -e "s#$(pwd)/##g" -e "s#$HOME#~#g" "$work/out.txt" > checks/routing.log
rm -rf "$work"
