#!/bin/sh
# SPDX-License-Identifier: MIT
# START-LINUX.sh: uruchamia aplikację WICI z pamięci USB na komputerze z Linuksem (x86_64): sh START-LINUX.sh
# Środowisko Pythona i aplikacja są kopiowane do katalogu podręcznego użytkownika i stamtąd uruchamiane
# (runtime/kopia.sh), więc wyjęcie pamięci nie zamyka aplikacji, a pamięć FAT bez prawa wykonywania
# (opcje showexec albo noexec) nie przeszkadza. Ścieżkę pamięci aplikacja dostaje w WICI_USB.
here=$(cd "$(dirname "$0")" && pwd)
if [ "$(uname -m)" != x86_64 ]; then
  echo "WICI: ten komputer ma procesor $(uname -m); pakiet obsługuje Linuksa tylko na x86_64." >&2
  exit 1
fi
. "$here/runtime/kopia.sh"
wici_copy "$here" linux-x86_64 "${XDG_CACHE_HOME:-$HOME/.cache}/wici" ||
  echo "WICI: nie udało się skopiować środowiska na dysk" >&2
if ! wici_runnable linux-x86_64; then
  echo "WICI: nie można uruchomić środowiska ani z kopii na dysku, ani z pamięci" >&2
  exit 1
fi
cd "$root" || exit 1   # katalog roboczy poza pamięcią: nie blokuje jej odmontowania
WICI_USB=$here exec "$python" -X utf8 "$root/app/wici.pyz" "$@"
