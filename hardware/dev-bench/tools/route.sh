#!/bin/sh
# SPDX-License-Identifier: MIT
# Route checks/routing.dsn with Freerouting 2.5.0 into checks/routing.ses.
# Environment: JAVA (a Java 21+ runtime), FREEROUTING (freerouting-2.5.0.jar).
set -eu
cd "$(dirname "$0")/.."
work=$(mktemp -d)
"$JAVA" -jar "$FREEROUTING" -de checks/routing.dsn -do checks/routing.ses -mp 60 \
  --gui.enabled=false --router.automatic_neckdown=false --user_data_path="$work" > "$work/out.txt" 2>&1
grep -E "Auto-routing stage completed|Optimization stage completed" "$work/out.txt" | sed 's/.*INFO *//'
rm -rf "$work"
