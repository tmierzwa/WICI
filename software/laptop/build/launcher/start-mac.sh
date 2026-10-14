#!/bin/sh
# SPDX-License-Identifier: MIT
# START-MAC.app/Contents/MacOS/START: jeden program dla Maców z Apple Silicon i z procesorem Intel.
here=$(cd "$(dirname "$0")/../../.." && pwd)
runtime=macos-x86_64
if [ "$(uname -m)" = arm64 ] || [ "$(sysctl -in sysctl.proc_translated 2>/dev/null)" = 1 ]; then
  runtime=macos-arm64   # także gdy START działa pod Rosettą na Apple Silicon
fi
python="$here/runtime/$runtime/bin/python3.14"
if [ ! -f "$python" ]; then
  osascript -e 'display alert "WICI" message "Brak plików aplikacji obok START. Uruchom START z kompletnej pamięci USB WICI." as critical' >/dev/null 2>&1
  exit 1
fi
exec "$python" -X utf8 "$here/app/wici.pyz" "$@"
