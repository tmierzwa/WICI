#!/bin/sh
# SPDX-License-Identifier: MIT
# START-MAC.app/Contents/MacOS/START: jeden program dla Maców z Apple Silicon i z procesorem Intel.
# Aplikacja działa w tle, a START kończy się po 2 s: macOS uznaje wtedy START-MAC za zamknięty, więc każde
# kolejne kliknięcie uruchamia nowy START (drugi START otwiera panel działającej aplikacji). Błędy startu
# pokazuje sama aplikacja (kod wyjścia 3); START pokazuje komunikat tylko, gdy Python w ogóle nie ruszył.
alert() {
  osascript -e 'on run argv' -e 'display alert "WICI" message (item 1 of argv) as critical' -e 'end run' "$1" >/dev/null 2>&1
}
here=$(cd "$(dirname "$0")/../../.." && pwd)
case "$here" in
  */AppTranslocation/*)
    alert "macOS uruchomił START-MAC z kopii tymczasowej, bo pliki na tej pamięci USB mają znacznik kwarantanny, i START nie widzi pozostałych plików pamięci. Otwórz Terminal, wpisz: xattr -dr com.apple.quarantine (ze spacją na końcu), przeciągnij do okna ikonę pamięci USB, naciśnij Enter i uruchom START-MAC ponownie."
    exit 1 ;;
esac
runtime=macos-x86_64
if [ "$(uname -m)" = arm64 ] || [ "$(sysctl -in sysctl.proc_translated 2>/dev/null)" = 1 ]; then
  runtime=macos-arm64   # także gdy START działa pod Rosettą na Apple Silicon
fi
python="$here/runtime/$runtime/bin/python3.14"
if [ ! -f "$python" ]; then
  alert "Brak plików aplikacji obok START. Uruchom START z kompletnej pamięci USB WICI."
  exit 1
fi
for arg; do   # starszy macOS i pierwsze „Otwórz mimo to” dodają -psn_…, którego aplikacja nie zna
  shift
  case "$arg" in -psn_*) ;; *) set -- "$@" "$arg" ;; esac
done
case " $* " in
  *" --selftest "*) exec "$python" -X utf8 "$here/app/wici.pyz" "$@" ;;   # CI: wynik i kod wyjścia wprost
esac
"$python" -X utf8 "$here/app/wici.pyz" "$@" &
pid=$!
i=0
while [ $i -lt 20 ] && kill -0 $pid 2>/dev/null; do
  sleep 0.1
  i=$((i + 1))
done
kill -0 $pid 2>/dev/null && exit 0   # działa: panel otwiera aplikacja
wait $pid
code=$?
if [ $code -ne 0 ] && [ $code -ne 3 ]; then
  alert "Aplikacja WICI nie uruchomiła się (kod $code). Uruchom START-MAC ponownie, a gdy to nie pomoże, użyj innego laptopa."
fi
exit $code
