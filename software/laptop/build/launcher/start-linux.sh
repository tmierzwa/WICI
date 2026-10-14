#!/bin/sh
# SPDX-License-Identifier: MIT
# START-LINUX.sh: uruchamia aplikację WICI z pamięci USB na komputerze z Linuksem (x86_64).
# Pamięć FAT bywa montowana bez prawa wykonywania (opcje showexec albo noexec), wtedy środowisko
# Pythona jest kopiowane raz do katalogu podręcznego użytkownika i stamtąd uruchamiane.
here=$(cd "$(dirname "$0")" && pwd)
version=$(cat "$here/runtime/VERSION" 2>/dev/null || echo unknown)
python="$here/runtime/linux-x86_64/bin/python3.14"
if [ "$(uname -m)" != x86_64 ]; then
  echo "WICI: ten komputer ma procesor $(uname -m); pakiet obsługuje Linuksa tylko na x86_64." >&2
  exit 1
fi
if ! "$python" -c "" 2>/dev/null; then
  cache="${XDG_CACHE_HOME:-$HOME/.cache}/wici/$version/runtime"
  if ! "$cache/linux-x86_64/bin/python3.14" -c "" 2>/dev/null; then
    rm -rf "$cache" && mkdir -p "$cache" &&
      cp -R "$here/runtime/linux-x86_64" "$here/runtime/python314.zip" "$cache/" &&
      chmod -R u+rwX "$cache" && chmod +x "$cache/linux-x86_64/bin/python3.14" || exit 1
  fi
  python="$cache/linux-x86_64/bin/python3.14"
fi
exec "$python" -X utf8 "$here/app/wici.pyz" "$@"
