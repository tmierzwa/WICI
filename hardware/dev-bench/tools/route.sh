#!/bin/sh
# SPDX-License-Identifier: MIT
# Route checks/routing.dsn with Freerouting 2.5.0 into checks/routing.ses.
# Environment: JAVA (a Java 25+ runtime; the 2.5.0 jar is built for Java 25), FREEROUTING (freerouting-2.5.0.jar).
# Freerouting exits 0 with nets left unrouted; this script then fails instead.
set -eu
cd "$(dirname "$0")/.."
work=$(mktemp -d)
"$JAVA" -jar "$FREEROUTING" -de checks/routing.dsn -do checks/routing.ses -mp 60 \
  --gui.enabled=false --router.automatic_neckdown=false --user_data_path="$work" > "$work/out.txt" 2>&1
grep -E "Auto-routing stage completed|Optimization stage completed" "$work/out.txt" | sed 's/.*INFO *//'
if grep -q "Auto-routing stage completed.*(0 unrouted and 0 violations)" "$work/out.txt"; then
  status=0
else
  echo "routing incomplete: fix placement or keepouts before importing the session" >&2
  status=1
fi
rm -rf "$work"
exit $status
